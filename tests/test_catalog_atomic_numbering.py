"""Owned decimal_v1 storage tests, not evidence of native 1C numbering parity."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import (
    BackendError, CatalogDraft, CatalogKey, CatalogSchema, CatalogWriteOutcome,
    FieldSchema, Revision, TabularRow, TabularSectionRows, TabularSectionSchema,
)
from yadinassi.configuration_xml import ConfigurationFile, ConfigurationImport, import_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View, _schema, _schema_data, _json
from sqlite_catalog_fixture import configuration_files
from test_catalog_commit_cleanup_recovery import FaultConnection


def numbered_configuration(width=2):
    """Host-authored opt-in; archived XML does not enable numbering."""
    lines = TabularSectionSchema(uuid4(), 'Lines', (FieldSchema(uuid4(), 'Text', 'string', (32,)),))
    return ConfigurationImport(config_uuid=uuid4(), name='OwnedNumbering', activation_issues=(),
        catalogs=(CatalogSchema(uuid4(), 'Products', width, 64, tabular_sections=(lines,), numbering='decimal_v1'),
                  CatalogSchema(uuid4(), 'Categories', width, 64, numbering='decimal_v1'),
                  CatalogSchema(uuid4(), 'Explicit', width, 64)),
        files=(ConfigurationFile(path='Configuration.xml', kind='xml', content=b'<owned/>'),), modules=())


class CatalogAtomicNumberingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.sqlite'
        self.config = numbered_configuration()
        self.backend = SQLiteCatalogBackend.create(self.path, self.config)
        self.addCleanup(lambda: self.backend.close())
        self.product, self.category, self.explicit = self.config.catalogs

    def draft(self, *, schema=None, code='', auto=True, identity=None, sections=None):
        schema = schema or self.product
        return CatalogDraft(CatalogKey(self.backend.database_id, schema.identity, identity or uuid4()),
                            code, 'owned', False, (), sections, auto_number=auto)

    def save(self, draft, operation=None):
        tx = self.backend.begin_write(operation or uuid4())
        try:
            tx.create(draft)
            return tx.commit_outcomes()[0]
        finally:
            tx.close()

    def read(self, key):
        view = self.backend.begin_read()
        try: return view.read_catalog(key)
        finally: view.close()

    def counter(self, schema=None):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute('SELECT next_value FROM catalog_sequence WHERE catalog_id=?',
                              (str((schema or self.product).identity),)).fetchone()[0]

    def sections(self):
        return (TabularSectionRows(self.product.tabular_sections[0].identity,
                                   (TabularRow(uuid4(), ('owned row',)),)),)

    def test_independent_scopes_skip_exact_collision_without_manual_counter_advance(self):
        self.assertEqual(self.backend.storage_version, 4)
        self.assertTrue(self.backend.capabilities().catalog_write_outcomes)
        for code in ('01', '1', '90'):
            self.save(self.draft(code=code, auto=False))
        self.assertEqual(self.counter(), 1)
        draft = self.draft()
        outcome = self.save(draft)
        self.assertIs(type(outcome), CatalogWriteOutcome)
        self.assertEqual(outcome.code, '02')
        self.assertEqual(draft.code, '')
        self.assertTrue(draft.auto_number)
        self.assertEqual(self.counter(), 3)
        self.assertEqual(self.save(self.draft(schema=self.category)).code, '01')
        self.assertEqual(self.counter(self.category), 2)
        self.assertEqual(self.save(self.draft()).code, '03')

    def test_full_rollback_restores_counter_owner_and_sections(self):
        draft = self.draft(sections=self.sections())
        operation = uuid4()
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        self.assertEqual(tx.read_catalog(draft.key).code, '01')
        tx.rollback()
        self.assertIsNone(self.read(draft.key))
        self.assertIsNone(self.backend.committed_operation(operation))
        self.assertEqual(self.counter(), 1)
        self.assertEqual(self.save(draft).code, '01')
        self.assertEqual(self.read(draft.key).tabular_sections, draft.tabular_sections)

    def test_failed_section_write_savepoint_restores_counter_and_keeps_prior_writes(self):
        first, failed, last = self.draft(), self.draft(sections=self.sections()), self.draft()
        tx = self.backend.begin_write(uuid4())
        try:
            tx.create(first)
            original = _View._replace_sections
            def fail_after_rows(view, draft, schema, sections):
                original(view, draft, schema, sections)
                raise BackendError('storage_error')
            with patch.object(_View, '_replace_sections', fail_after_rows):
                with self.assertRaisesRegex(BackendError, 'storage_error'): tx.create(failed)
            self.assertIsNone(tx.read_catalog(failed.key))
            tx.create(last)
            outcomes = tx.commit_outcomes()
        finally: tx.close()
        self.assertEqual([o.code for o in outcomes], ['01', '02'])
        self.assertEqual([o.revision.record_id for o in outcomes], [first.key.record_id, last.key.record_id])
        self.assertIsNone(self.read(failed.key))
        self.assertEqual(self.counter(), 3)

    def test_duplicate_identity_does_not_consume_number(self):
        draft = self.draft()
        self.save(draft)
        tx = self.backend.begin_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError, 'duplicate_identity'): tx.create(draft)
            tx.create(self.draft())
            self.assertEqual(tx.commit_outcomes()[0].code, '02')
        finally: tx.close()

    def test_two_backends_busy_then_serial_unique_and_reopen(self):
        other = SQLiteCatalogBackend(self.path)
        self.addCleanup(other.close)
        tx = self.backend.begin_write(uuid4())
        try:
            tx.create(self.draft())
            with self.assertRaisesRegex(BackendError, 'busy'): other.begin_write(uuid4())
            self.assertEqual(tx.commit_outcomes()[0].code, '01')
        finally: tx.close()
        tx = other.begin_write(uuid4())
        try:
            tx.create(self.draft())
            self.assertEqual(tx.commit_outcomes()[0].code, '02')
        finally: tx.close()
        other.close()
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path)
        self.assertEqual(self.save(self.draft()).code, '03')

    def test_exhaustion_is_bounded_and_does_not_destroy_prior_writes(self):
        path = Path(self.temp.name) / 'one-digit.sqlite'
        backend = SQLiteCatalogBackend.create(path, numbered_configuration(1))
        try:
            schema = backend._schemas[0]
            tx = backend.begin_write(uuid4())
            try:
                for number in range(1, 10):
                    tx.create(CatalogDraft(CatalogKey(backend.database_id, schema.identity, uuid4()),
                                           '', 'owned', False, (), auto_number=True))
                with self.assertRaisesRegex(BackendError, 'code_exhausted'):
                    tx.create(CatalogDraft(CatalogKey(backend.database_id, schema.identity, uuid4()),
                                           '', 'overflow', False, (), auto_number=True))
                self.assertEqual([o.code for o in tx.commit_outcomes()], [str(n) for n in range(1, 10)])
            finally: tx.close()
        finally: backend.close()

    def test_uncertain_before_commit_reuses_number_only_after_absent_receipt(self):
        draft, operation = self.draft(sections=self.sections()), uuid4()
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        tx._connection = FaultConnection(tx._connection, commit_fault='before')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'): tx.commit_outcomes()
        self.assertIsNone(self.backend.resolve_write_outcome(operation, draft))
        self.assertIsNone(self.read(draft.key))
        self.assertEqual(self.counter(), 1)
        outcome = self.save(draft, operation)
        self.assertEqual(outcome.code, '01')
        self.assertEqual(self.backend.resolve_write_outcome(operation, draft), outcome)

    def test_lost_commit_response_resolves_original_code_even_after_later_edit(self):
        draft, operation = self.draft(sections=self.sections()), uuid4()
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        tx._connection = FaultConnection(tx._connection, commit_fault='after')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'): tx.commit_outcomes()
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path)
        outcome = self.backend.resolve_write_outcome(operation, draft)
        self.assertEqual(outcome.code, '01')
        self.assertEqual(self.read(draft.key).tabular_sections, draft.tabular_sections)
        self.assertEqual(self.backend.resolve_write(operation, draft), outcome.revision)
        with self.assertRaisesRegex(BackendError, 'conflict'): self.backend.begin_write(operation)
        edited = replace(draft, code='88', auto_number=False, description='later')
        tx = self.backend.begin_write(uuid4())
        try:
            tx.update(edited, outcome.revision)
            self.assertEqual(tx.commit_outcomes()[0].code, '88')
        finally: tx.close()
        self.assertEqual(self.backend.resolve_write_outcome(operation, draft), outcome)
        self.assertEqual(self.counter(), 2)
        for forged in (replace(draft, auto_number=False, code='01'), replace(draft, description='changed'),
                       replace(draft, tabular_sections=())):
            with self.subTest(forged=forged), self.assertRaisesRegex(BackendError, 'conflict'):
                self.backend.resolve_write_outcome(operation, forged)

    def test_invalid_auto_intents_and_identifiers_fail_without_allocation(self):
        draft = self.draft()
        invalid = [replace(draft, auto_number=value) for value in (0, 1, None, 'true')]
        invalid += [replace(draft, code='01'), replace(draft, auto_number=False),
                    self.draft(schema=self.explicit),
                    replace(draft, key=replace(draft.key, record_id=UUID(int=0))),
                    replace(draft, key=replace(draft.key, database_id=uuid4())),
                    replace(draft, key=replace(draft.key, catalog_id='hostile'))]
        tx = self.backend.begin_write(uuid4())
        try:
            for bad in invalid:
                with self.subTest(draft=bad), self.assertRaises(BackendError): tx.create(bad)
            tx.create(draft)
            outcome = tx.commit_outcomes()[0]
        finally: tx.close()
        self.assertEqual(outcome.code, '01')
        tx = self.backend.begin_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError, 'invalid_input'): tx.update(draft, outcome.revision)
        finally: tx.close()
        self.assertEqual(self.counter(), 2)

    def test_corrupt_counter_fails_closed(self):
        for corrupt in ('DELETE FROM catalog_sequence',
                        "UPDATE catalog_sequence SET next_value='hostile'",
                        'UPDATE catalog_sequence SET next_value=101'):
            with self.subTest(sql=corrupt):
                with closing(sqlite3.connect(self.path)) as db, db: db.execute(corrupt)
                with self.assertRaises(BackendError): self.backend.begin_write(uuid4())
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute('DELETE FROM catalog_sequence')
                    db.executemany('INSERT INTO catalog_sequence VALUES(?,1)',
                                   [(str(s.identity),) for s in (self.product, self.category)])
        self.assertEqual(self.save(self.draft()).code, '01')

    def test_corrupt_receipt_codes_and_shapes_are_not_accepted(self):
        draft, operation = self.draft(), uuid4()
        self.save(draft, operation)
        with closing(sqlite3.connect(self.path)) as db, db:
            raw = db.execute('SELECT revisions_json FROM commit_receipt WHERE operation_id=?', (str(operation),)).fetchone()[0]
        entries = json.loads(raw)
        variants = [json.dumps([entries[0][:3]])]
        for code in ('', '00', '1', 'ab', '１２', '001', '02', None):
            variants.append(json.dumps([entries[0][:3] + [code]]))
        for encoded in variants:
            with self.subTest(receipt=encoded):
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute('UPDATE commit_receipt SET revisions_json=? WHERE operation_id=?', (encoded, str(operation)))
                with self.assertRaises(BackendError): self.backend.resolve_write_outcome(operation, draft)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE commit_receipt SET revisions_json=? WHERE operation_id=?', (raw, str(operation)))
        self.assertEqual(self.backend.resolve_write_outcome(operation, draft).code, '01')

    def test_legacy_revision_api_still_works_in_v4_and_v2_remains_explicit(self):
        draft, operation = self.draft(), uuid4()
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        revisions = tx.commit()
        self.assertIs(type(revisions[0]), Revision)
        self.assertEqual(self.backend.committed_operation(operation)[1], revisions)
        self.assertEqual(self.backend.resolve_write(operation, draft), revisions[0])
        config = replace(self.config, catalogs=(self.explicit,))
        legacy = SQLiteCatalogBackend.create(Path(self.temp.name) / 'legacy.sqlite', config)
        try:
            self.assertEqual(legacy.storage_version, 2)
            self.assertFalse(legacy.capabilities().catalog_write_outcomes)
            draft = CatalogDraft(CatalogKey(legacy.database_id, self.explicit.identity, uuid4()), '', '', False, ())
            tx = legacy.begin_write(uuid4())
            tx.create(draft)
            self.assertIs(type(tx.commit()[0]), Revision)
        finally: legacy.close()

    def test_schema_numbering_is_strict_and_xml_auto_numbering_stays_closed(self):
        numbered = _json(_schema_data(self.product))
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            _schema(numbered)  # Migration and legacy admission never opt in.
        self.assertEqual(_schema(numbered, allow_numbering=True), self.product)
        for mode, width in [('unknown', 2), (True, 2), ('decimal_v1', 0), ('decimal_v1', 10)]:
            with self.subTest(mode=mode, width=width):
                bad = replace(self.config, catalogs=(replace(self.product, numbering=mode, code_length=width),))
                with self.assertRaises(BackendError):
                    SQLiteCatalogBackend.create(Path(self.temp.name) / 'rejected.sqlite', bad)
        files = configuration_files()
        self.assertTrue(all(s.numbering == 'explicit' for s in import_configuration(files).catalogs))
        files['Catalogs/Products.xml'] = files['Catalogs/Products.xml'].replace(
            b'<Autonumbering>false</Autonumbering>', b'<Autonumbering>true</Autonumbering>')
        with self.assertRaisesRegex(ValueError, 'unsupported catalog semantics'):
            import_configuration(files)

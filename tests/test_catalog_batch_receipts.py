"""Exact ordered receipt recovery over owned SQLite, not native 1C evidence."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from legacy_demo_fixture import legacy_demo_files
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import (
    BackendError, Capabilities, CatalogDraft, CatalogKey, CatalogSchema,
    CatalogWriteOutcome, CatalogWriteRequest, FieldSchema, Revision,
    TabularRow, TabularSectionRows, TabularSectionSchema,
)
from yadinassi.configuration_xml import ConfigurationFile, ConfigurationImport
from yadinassi.sqlite_catalog import (
    SQLiteCatalogBackend, _APPLICATION_ID, _MAX_ROWS, _View,
    _intent, _json, _receipt_digest, _schema_data,
)
from yadinassi.sqlite_catalog_migration import _V1_DDL
from test_catalog_commit_cleanup_recovery import FaultConnection


class CatalogBatchReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def backend(self, version=2):
        path = Path(self.temp.name) / (str(uuid4()) + '.sqlite')
        target = CatalogSchema(uuid4(), 'Targets', 8, 64)
        fields = (FieldSchema(uuid4(), 'Text', 'string', (4,)),
                  FieldSchema(uuid4(), 'Amount', 'number', (8, 2, 'Any')),
                  FieldSchema(uuid4(), 'Target', 'catalog_ref', (), target.identity))
        sections = () if version < 3 else (TabularSectionSchema(uuid4(), 'Lines', fields),)
        owner = CatalogSchema(uuid4(), 'Owners', 8, 64, fields, sections,
                              'decimal_v1' if version == 4 else 'explicit')
        configuration = ConfigurationImport(config_uuid=uuid4(), name='OwnedBatch',
            catalogs=(owner, target), files=(ConfigurationFile(path='Configuration.xml',
                content=b'<owned/>', kind='xml'),), modules=(), activation_issues=())
        if version == 1:
            with closing(sqlite3.connect(path)) as db, db:
                for ddl in _V1_DDL: db.execute(ddl)
                db.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
                db.execute('PRAGMA user_version=1')
                db.execute('INSERT INTO database_info VALUES(1,?,1,?,?,1,?)',
                           (str(uuid4()), str(configuration.config_uuid), configuration.name, '[]'))
                db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)',
                           ('Configuration.xml', 'xml', b'<owned/>', hashlib.sha256(b'<owned/>').hexdigest()))
                for schema in configuration.catalogs:
                    db.execute('INSERT INTO catalog_schema VALUES(?,?,?)',
                               (str(schema.identity), schema.name, _json(_schema_data(schema))))
            backend = SQLiteCatalogBackend(path)
        else:
            backend = SQLiteCatalogBackend.create(path, configuration)
        self.addCleanup(backend.close)
        return backend, owner, target

    def draft(self, backend, schema, code='1', *, target=None, auto=False, sections=False):
        values = () if not schema.fields else ('text', Decimal('1.23'),
            target or CatalogKey(backend.database_id, schema.fields[-1].target_catalog_id, UUID(int=0)))
        rows = None
        if sections:
            rows = (TabularSectionRows(schema.tabular_sections[0].identity,
                                      (TabularRow(uuid4(), values),)),)
        return CatalogDraft(CatalogKey(backend.database_id, schema.identity, uuid4()),
                            '' if auto else code, 'original', False, values, rows, auto)

    def save(self, backend, requests, *, operation=None, fault=None, outcomes=False):
        operation = operation or uuid4()
        with closing(backend.begin_write(operation)) as tx:
            for request in requests:
                if request.expected_revision is None: tx.create(request.draft)
                else: tx.update(request.draft, request.expected_revision)
            if fault: tx._connection = FaultConnection(tx._connection, **fault)
            result = tx.commit_outcomes() if outcomes else tx.commit()
        return operation, result

    def pair(self, backend, schema, **kwargs):
        return tuple(CatalogWriteRequest(self.draft(backend, schema, str(i), **kwargs)) for i in (1, 2))

    def test_capability_defaults_closed_and_read_only_resolution_is_advertised(self):
        self.assertFalse(Capabilities().catalog_batch_receipts)
        backend, _, _ = self.backend()
        self.assertTrue(backend.capabilities().catalog_batch_receipts)
        with closing(SQLiteCatalogBackend(backend.path, read_only=True)) as reader:
            self.assertTrue(reader.capabilities().catalog_batch_receipts)
            self.assertFalse(reader.capabilities().catalog_create)

    def test_ordered_create_receipts_across_v1_v2_v3_v4(self):
        for version in (1, 2, 3, 4):
            with self.subTest(version=version):
                backend, schema, _ = self.backend(version)
                requests = self.pair(backend, schema, auto=version == 4, sections=version >= 3)
                operation, revisions = self.save(backend, requests)
                self.assertEqual(backend.resolve_writes(operation, requests), revisions)
                self.assertEqual([r.record_id for r in revisions], [r.draft.key.record_id for r in requests])
                if version == 4:
                    outcomes = backend.resolve_write_outcomes(operation, requests)
                    self.assertEqual([r.code for r in outcomes], ['00000001', '00000002'])
                    self.assertEqual(tuple(r.revision for r in outcomes), revisions)
                else:
                    with self.assertRaisesRegex(BackendError, 'unsupported'):
                        backend.resolve_write_outcomes(operation, requests)

    def test_mixed_creates_updates_and_cross_catalog_references(self):
        backend, owner, target = self.backend(3)
        existing = self.draft(backend, owner)
        _, revisions = self.save(backend, (CatalogWriteRequest(existing),))
        reference = self.draft(backend, target)
        changed = replace(existing, values=('new', Decimal('2.34'), reference.key))
        created = self.draft(backend, owner, '2', target=reference.key, sections=True)
        requests = (CatalogWriteRequest(reference), CatalogWriteRequest(changed, revisions[0]),
                    CatalogWriteRequest(created))
        operation, expected = self.save(backend, requests)
        self.assertEqual(backend.resolve_writes(operation, requests), expected)
        self.assertEqual([r.token for r in expected], ['1', '2', '1'])

    def test_repeated_writes_to_same_identity_retain_each_revision(self):
        backend, schema, _ = self.backend()
        draft = self.draft(backend, schema)
        operation = uuid4()
        with closing(backend.begin_write(operation)) as tx:
            tx.create(draft)
            revision = tx.read_catalog(draft.key).revision
            changed = replace(draft, description='second')
            tx.update(changed, revision)
            expected = tx.commit()
        requests = (CatalogWriteRequest(draft), CatalogWriteRequest(changed, revision))
        self.assertEqual(backend.resolve_writes(operation, requests), expected)
        self.assertEqual([r.token for r in expected], ['1', '2'])

    def test_uncertain_after_commit_recovers_whole_batch_after_reopen(self):
        for version in (2, 3, 4):
            with self.subTest(version=version):
                backend, schema, _ = self.backend(version)
                requests = self.pair(backend, schema, auto=version == 4, sections=version >= 3)
                operation = uuid4()
                with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                    self.save(backend, requests, operation=operation, fault={'commit_fault': 'after'})
                backend.close()
                with closing(SQLiteCatalogBackend(backend.path)) as reopened:
                    with patch.object(_View, 'commit', side_effect=AssertionError('must not replay')):
                        revisions = reopened.resolve_writes(operation, requests)
                    self.assertEqual(len(revisions), 2)
                    with closing(reopened.begin_read()) as view:
                        self.assertEqual(tuple(view.read_catalog(r.draft.key).revision for r in requests), revisions)
                    with self.assertRaisesRegex(BackendError, 'conflict'): reopened.begin_write(operation)

    def test_uncertain_before_commit_proves_absence_before_same_operation_retry(self):
        backend, schema, _ = self.backend(4)
        requests, operation = self.pair(backend, schema, auto=True, sections=True), uuid4()
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.save(backend, requests, operation=operation, fault={'commit_fault': 'before'})
        self.assertIsNone(backend.resolve_writes(operation, requests))
        self.assertIsNone(backend.resolve_write_outcomes(operation, requests))
        with closing(backend.begin_read()) as view:
            self.assertTrue(all(view.read_catalog(r.draft.key) is None for r in requests))
        _, outcomes = self.save(backend, requests, operation=operation, outcomes=True)
        self.assertEqual([r.code for r in outcomes], ['00000001', '00000002'])
        self.assertEqual(backend.resolve_write_outcomes(operation, requests), outcomes)

    def test_uncertain_close_after_commit_resolves_without_second_write(self):
        backend, schema, _ = self.backend()
        requests, operation = self.pair(backend, schema), uuid4()
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.save(backend, requests, operation=operation,
                      fault={'close_fault': 'after', 'close_count': 1})
        self.assertEqual(len(backend.resolve_writes(operation, requests)), 2)
        self.assertIsNone(backend._active)

    def test_original_numbered_outcomes_survive_later_code_and_section_edits(self):
        backend, schema, _ = self.backend(4)
        requests = self.pair(backend, schema, auto=True, sections=True)
        operation, expected = self.save(backend, requests, outcomes=True)
        edits = tuple(CatalogWriteRequest(replace(r.draft, code=str(i + 30), auto_number=False,
                       description='later', tabular_sections=()), o.revision)
                      for i, (r, o) in enumerate(zip(requests, expected)))
        self.save(backend, edits)
        self.assertEqual(backend.resolve_write_outcomes(operation, requests), expected)
        self.assertEqual(backend.resolve_writes(operation, requests), tuple(o.revision for o in expected))

    def test_order_prefix_suffix_duplicate_and_extra_requests_conflict(self):
        backend, schema, _ = self.backend()
        requests = self.pair(backend, schema)
        operation, _ = self.save(backend, requests)
        wrong = ((), requests[:1], requests[1:], requests[::-1],
                 (requests[0], requests[0]), requests + requests[:1])
        for value in wrong:
            with self.subTest(value=value), self.assertRaisesRegex(BackendError, 'conflict'):
                backend.resolve_writes(operation, value)
        self.assertIsNone(backend._active)

    def test_changed_scalar_and_section_intents_conflict(self):
        backend, schema, _ = self.backend(3)
        requests = self.pair(backend, schema, sections=True)
        operation, _ = self.save(backend, requests)
        draft = requests[0].draft
        for changed in (replace(draft, code='3'), replace(draft, description='changed'),
                        replace(draft, deletion_mark=True), replace(draft, tabular_sections=()),
                        replace(draft, tabular_sections=None),
                        replace(draft, values=('diff', *draft.values[1:]))):
            with self.subTest(changed=changed), self.assertRaisesRegex(BackendError, 'conflict'):
                backend.resolve_writes(operation, (CatalogWriteRequest(changed), requests[1]))

    def test_generated_code_substitution_is_not_original_automatic_intent(self):
        backend, schema, _ = self.backend(4)
        requests = self.pair(backend, schema, auto=True)
        operation, expected = self.save(backend, requests, outcomes=True)
        changed = CatalogWriteRequest(replace(requests[0].draft, code=expected[0].code, auto_number=False))
        with self.assertRaisesRegex(BackendError, 'conflict'):
            backend.resolve_write_outcomes(operation, (changed, requests[1]))

    def test_expected_revision_is_part_of_each_request(self):
        backend, schema, _ = self.backend()
        creates = self.pair(backend, schema)
        _, previous = self.save(backend, creates)
        updates = tuple(CatalogWriteRequest(replace(r.draft, description='updated'), old)
                        for r, old in zip(creates, previous))
        operation, expected = self.save(backend, updates)
        self.assertEqual(backend.resolve_writes(operation, updates), expected)
        for revision in (None, replace(previous[0], token='2'),
                         replace(previous[0], database_id=uuid4()),
                         replace(previous[0], configuration_generation=2),
                         replace(previous[0], record_id=uuid4()),
                         replace(previous[0], token='01')):
            with self.subTest(revision=revision), self.assertRaisesRegex(BackendError, 'conflict'):
                backend.resolve_writes(operation, (replace(updates[0], expected_revision=revision), updates[1]))

    def test_qualifier_normalization_matches_original_write_intents(self):
        backend, schema, _ = self.backend(3)
        draft = self.draft(backend, schema, sections=True)
        values = ('longtext', Decimal('1.234'), draft.values[-1])
        sections = (replace(draft.tabular_sections[0], rows=(TabularRow(uuid4(), values),)),)
        requests = (CatalogWriteRequest(replace(draft, values=values, tabular_sections=sections)),)
        operation, expected = self.save(backend, requests)
        self.assertEqual(backend.resolve_writes(operation, requests), expected)
        normalized = replace(requests[0].draft, values=('long', Decimal('1.23'), values[-1]),
                             tabular_sections=(replace(sections[0], rows=(replace(sections[0].rows[0],
                                 values=('long', Decimal('1.23'), values[-1])),)),))
        self.assertEqual(backend.resolve_writes(operation, (CatalogWriteRequest(normalized),)), expected)

    def test_empty_committed_transaction_is_distinct_from_absent_receipt(self):
        for version in (2, 4):
            with self.subTest(version=version):
                backend, _, _ = self.backend(version)
                self.assertIsNone(backend.resolve_writes(uuid4(), ()))
                operation, result = self.save(backend, ())
                self.assertEqual(result, ())
                self.assertEqual(backend.resolve_writes(operation, ()), ())
                if version == 4: self.assertEqual(backend.resolve_write_outcomes(operation, ()), ())

    def test_failed_record_is_not_part_of_successful_transaction_receipt(self):
        backend, schema, _ = self.backend(4)
        requests, operation = self.pair(backend, schema, auto=True), uuid4()
        with closing(backend.begin_write(operation)) as tx:
            tx.create(requests[0].draft)
            with self.assertRaisesRegex(BackendError, 'duplicate_identity'): tx.create(requests[0].draft)
            tx.create(requests[1].draft)
            outcomes = tx.commit_outcomes()
        self.assertEqual(backend.resolve_write_outcomes(operation, requests), outcomes)
        self.assertEqual([r.code for r in outcomes], ['00000001', '00000002'])

    def test_read_only_resolution_does_not_change_database_bytes(self):
        backend, schema, _ = self.backend(4)
        requests = self.pair(backend, schema, auto=True)
        operation, expected = self.save(backend, requests, outcomes=True)
        before = Path(backend.path).read_bytes()
        with closing(SQLiteCatalogBackend(backend.path, read_only=True)) as reader:
            with patch.object(reader, 'begin_write', side_effect=AssertionError('read only')):
                self.assertEqual(reader.resolve_write_outcomes(operation, requests), expected)
        self.assertEqual(Path(backend.path).read_bytes(), before)

    def test_invalid_batch_container_element_and_bound_refuse_before_io(self):
        backend, schema, _ = self.backend()
        requests = self.pair(backend, schema)
        with patch.object(backend, '_committed_results', side_effect=AssertionError('must validate first')):
            for invalid in (None, list(requests), iter(requests), (requests[0].draft,),
                            requests[:1] * (_MAX_ROWS + 1)):
                with self.subTest(invalid=type(invalid)), self.assertRaisesRegex(BackendError, 'invalid_input'):
                    backend.resolve_writes(uuid4(), invalid)

    def test_malformed_draft_cannot_match_a_receipt(self):
        backend, schema, _ = self.backend()
        requests = self.pair(backend, schema)
        operation, _ = self.save(backend, requests)
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            backend.resolve_writes(operation, (CatalogWriteRequest(None), requests[1]))
        self.assertIsNone(backend._active)

    def test_single_record_apis_do_not_accept_part_of_batch(self):
        backend, schema, _ = self.backend(4)
        requests = self.pair(backend, schema, auto=True)
        operation, _ = self.save(backend, requests)
        for request in requests:
            with self.assertRaisesRegex(BackendError, 'conflict'):
                backend.resolve_write(operation, request.draft)
            with self.assertRaisesRegex(BackendError, 'conflict'):
                backend.resolve_write_outcome(operation, request.draft)

    def test_single_record_and_batch_results_agree(self):
        for version in (1, 2, 3, 4):
            with self.subTest(version=version):
                backend, schema, _ = self.backend(version)
                request = CatalogWriteRequest(self.draft(backend, schema, auto=version == 4))
                operation, expected = self.save(backend, (request,))
                self.assertEqual(backend.resolve_write(operation, request.draft), expected[0])
                self.assertEqual(backend.resolve_writes(operation, (request,)), expected)
                if version == 4:
                    self.assertEqual(backend.resolve_write_outcome(operation, request.draft),
                                     backend.resolve_write_outcomes(operation, (request,))[0])

    def test_corrupt_revision_results_do_not_resolve(self):
        backend, schema, _ = self.backend()
        requests = self.pair(backend, schema)
        operation, _ = self.save(backend, requests)
        with closing(sqlite3.connect(backend.path)) as db, db:
            raw = db.execute('SELECT revisions_json FROM commit_receipt WHERE operation_id=?', (str(operation),)).fetchone()[0]
            entries = json.loads(raw)
            entries[1][2] = '9'
            db.execute('UPDATE commit_receipt SET revisions_json=? WHERE operation_id=?', (_json(entries), str(operation)))
        with self.assertRaisesRegex(BackendError, 'integrity'): backend.resolve_writes(operation, requests)

    def test_corrupt_numbered_outcome_digest_is_not_accepted(self):
        backend, schema, _ = self.backend(4)
        requests = self.pair(backend, schema, auto=True)
        operation, _ = self.save(backend, requests)
        with closing(sqlite3.connect(backend.path)) as db, db:
            raw = db.execute('SELECT revisions_json FROM commit_receipt WHERE operation_id=?', (str(operation),)).fetchone()[0]
            entries = json.loads(raw)
            entries[1][3] = '00000099'
            db.execute('UPDATE commit_receipt SET revisions_json=? WHERE operation_id=?', (_json(entries), str(operation)))
        with self.assertRaisesRegex(BackendError, 'conflict'): backend.resolve_write_outcomes(operation, requests)

    def test_active_transaction_and_closed_backend_refuse_resolution(self):
        backend, schema, _ = self.backend()
        requests = self.pair(backend, schema)
        operation, _ = self.save(backend, requests)
        with closing(backend.begin_read()):
            with self.assertRaisesRegex(BackendError, 'busy'): backend.resolve_writes(operation, requests)
        backend.close()
        with self.assertRaisesRegex(BackendError, 'closed'): backend.resolve_writes(operation, requests)

    def test_streamed_digest_matches_historical_canonical_json(self):
        backend, schema, _ = self.backend(4)
        draft = self.draft(backend, schema, auto=True, sections=True)
        revision = Revision(backend.database_id, 1, schema.identity, draft.key.record_id, '1')
        outcome = CatalogWriteOutcome(revision, '00000001')
        intents = [_intent(replace(draft, description='Текст 😀'), 1, '["a\\nb"]', None),
                   _intent(draft, 1, '[]', [['section', []]])]
        for values in ([], intents[:1], intents):
            for outcomes in (None, (), (outcome,)):
                payload = values if outcomes is None else ['write_outcomes_v1', values,
                    [[str(o.revision.catalog_id), str(o.revision.record_id), o.revision.token, o.code] for o in outcomes]]
                expected = hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
                with self.subTest(values=len(values), outcomes=outcomes):
                    self.assertEqual(_receipt_digest(iter(values), outcomes), expected)

    def test_v6_batch_receipt_survives_archived_source_drift_without_reactivation(self):
        files = legacy_demo_files()
        path = Path(self.temp.name) / 'demo.sqlite'
        with closing(SQLiteCatalogBackend.create_demo_directories(path, files)) as backend:
            schema = next(s for s in backend._schemas if s.name == 'Склады')
            requests = self.pair(backend, schema, auto=True)
            operation, expected = self.save(backend, requests, outcomes=True)
            source = 'Catalogs/Номенклатура/Ext/ObjectModule.bsl'
            content = files[source] + b'\n'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                           (content, hashlib.sha256(content).hexdigest(), source))
            self.assertEqual(backend.resolve_write_outcomes(operation, requests), expected)
            with self.assertRaisesRegex(BackendError, 'schema_changed'): backend.begin_write(uuid4())

    def test_inert_archive_has_no_batch_receipt_capability(self):
        from sqlite_catalog_fixture import configuration_files
        path = Path(self.temp.name) / 'inert.sqlite'
        with closing(SQLiteCatalogBackend.create_inert(path, configuration_files())) as backend:
            self.assertFalse(backend.capabilities().catalog_batch_receipts)
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.resolve_writes(uuid4(), ())
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.resolve_write_outcomes(uuid4(), ())

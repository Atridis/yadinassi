"""Atomic catalog batches and typed outcomes without persistent receipts."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import hashlib
from legacy_demo_fixture import legacy_demo_files
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.db.catalog.catalog_backend import (
    BackendError, Capabilities, CatalogDraft, CatalogKey, CatalogSchema,
    CatalogWriteRequest, FieldSchema,
    TabularRow, TabularSectionRows, TabularSectionSchema,
)
from yadinassi.configuration.configuration_xml import ConfigurationFile, ConfigurationImport
from yadinassi.db.sqlite.sqlite_catalog import (
    SQLiteCatalogBackend, _APPLICATION_ID, _View, _json, _schema_data,
)
from yadinassi.db.sqlite.sqlite_catalog_migration import _V1_DDL
from test_catalog_commit_cleanup_recovery import FaultConnection


class CatalogBatchCommitTests(unittest.TestCase):
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

    def read_cards(self, backend, requests):
        with closing(backend.begin_read()) as reader:
            return tuple(reader.read_catalog(request.draft.key) for request in requests)

    def test_capabilities_and_obsolete_apis_explicitly_disable_receipts(self):
        self.assertFalse(Capabilities().catalog_batch_receipts)
        backend, schema, _ = self.backend()
        request, = (CatalogWriteRequest(self.draft(backend, schema)),)
        operation = uuid4()
        for readonly in (False, True):
            with closing(SQLiteCatalogBackend(backend.path, read_only=readonly)) as view:
                self.assertFalse(view.capabilities().catalog_batch_receipts)
                if readonly:
                    self.assertFalse(view.capabilities().catalog_create)
                with patch.object(view, '_connect', side_effect=AssertionError('receipt I/O')):
                    for method, args in (
                            (view.resolve_write, (operation, request.draft)),
                            (view.resolve_write_outcome, (operation, request.draft)),
                            (view.resolve_writes, (operation, (request,))),
                            (view.resolve_write_outcomes, (operation, (request,))),
                            (view.committed_operation, (operation,))):
                        with self.assertRaisesRegex(BackendError, 'unsupported'):
                            method(*args)

    def test_ordered_commit_outcomes_across_v1_v2_v3_v4(self):
        for version in (1, 2, 3, 4):
            with self.subTest(version=version):
                backend, schema, _ = self.backend(version)
                requests = self.pair(backend, schema, auto=version == 4, sections=version >= 3)
                _, results = self.save(backend, requests, outcomes=version == 4)
                revisions = tuple(r.revision for r in results) if version == 4 else results
                self.assertEqual([r.record_id for r in revisions], [r.draft.key.record_id for r in requests])
                cards = self.read_cards(backend, requests)
                self.assertEqual(tuple(card.revision for card in cards), revisions)
                if version == 4:
                    self.assertEqual([r.code for r in results], ['00000001', '00000002'])
                    self.assertEqual(tuple(card.code for card in cards), tuple(r.code for r in results))
                if version >= 3:
                    self.assertEqual([card.tabular_sections for card in cards],
                                     [request.draft.tabular_sections for request in requests])

    def test_mixed_batch_can_reference_earlier_stage_and_keep_revisions(self):
        backend, owner, target = self.backend(3)
        existing = self.draft(backend, owner)
        _, revisions = self.save(backend, (CatalogWriteRequest(existing),))
        reference = self.draft(backend, target)
        changed = replace(existing, values=('new', Decimal('2.34'), reference.key))
        created = self.draft(backend, owner, '2', target=reference.key, sections=True)
        requests = (CatalogWriteRequest(reference), CatalogWriteRequest(changed, revisions[0]),
                    CatalogWriteRequest(created))
        _, expected = self.save(backend, requests)
        self.assertEqual([r.token for r in expected], ['1', '2', '1'])
        cards = self.read_cards(backend, requests)
        self.assertEqual(tuple(card.revision for card in cards), expected)
        self.assertEqual(cards[1].values[-1], reference.key)
        self.assertEqual(cards[2].tabular_sections, created.tabular_sections)

    def test_repeated_writes_to_same_identity_return_each_revision(self):
        backend, schema, _ = self.backend()
        draft = self.draft(backend, schema)
        with closing(backend.begin_write(uuid4())) as tx:
            tx.create(draft)
            revision = tx.read_catalog(draft.key).revision
            changed = replace(draft, description='second')
            tx.update(changed, revision)
            expected = tx.commit()
        self.assertEqual([r.token for r in expected], ['1', '2'])
        fresh, = self.read_cards(backend, (CatalogWriteRequest(changed),))
        self.assertEqual((fresh.description, fresh.revision), ('second', expected[-1]))

    def test_ambiguous_commit_requires_fresh_read_of_whole_batch(self):
        for version in (2, 3, 4):
            for when in ('before', 'after'):
                with self.subTest(version=version, fault=when):
                    backend, schema, _ = self.backend(version)
                    requests = self.pair(backend, schema, auto=version == 4, sections=version >= 3)
                    operation = uuid4()
                    with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                        self.save(backend, requests, operation=operation, fault={'commit_fault': when})
                    backend.close()
                    with closing(SQLiteCatalogBackend(backend.path)) as reopened:
                        with patch.object(_View, 'commit', side_effect=AssertionError('replay')):
                            with self.assertRaisesRegex(BackendError, 'unsupported'):
                                reopened.resolve_writes(operation, requests)
                            cards = self.read_cards(reopened, requests)
                        if when == 'before':
                            self.assertEqual(cards, (None, None))
                        else:
                            self.assertEqual([card.revision.token for card in cards], ['1', '1'])
                            if version == 4:
                                self.assertEqual([card.code for card in cards], ['00000001', '00000002'])
                        with closing(sqlite3.connect(backend.path)) as db:
                            self.assertEqual(db.execute('SELECT COUNT(*) FROM commit_receipt').fetchone(), (0,))

    def test_stale_batch_member_does_not_overwrite_and_remaining_batch_is_atomic(self):
        backend, schema, _ = self.backend()
        existing = self.draft(backend, schema)
        _, (old,) = self.save(backend, (CatalogWriteRequest(existing),))
        current = replace(existing, description='winner')
        _, (new,) = self.save(backend, (CatalogWriteRequest(current, old),))
        second = self.draft(backend, schema, '2')
        with closing(backend.begin_write(uuid4())) as tx:
            tx.create(second)
            with self.assertRaisesRegex(BackendError, 'conflict'):
                tx.update(replace(existing, description='loser'), old)
            only, = tx.commit()
        survivor, created = self.read_cards(backend, (CatalogWriteRequest(existing), CatalogWriteRequest(second)))
        self.assertEqual((survivor.description, survivor.revision), ('winner', new))
        self.assertEqual(created.revision, only)

    def test_qualifier_normalization_applies_to_scalar_and_section_values(self):
        backend, schema, _ = self.backend(3)
        draft = self.draft(backend, schema, sections=True)
        values = ('longtext', Decimal('1.234'), draft.values[-1])
        sections = (replace(draft.tabular_sections[0], rows=(TabularRow(uuid4(), values),)),)
        requests = (CatalogWriteRequest(replace(draft, values=values, tabular_sections=sections)),)
        _, (revision,) = self.save(backend, requests)
        card, = self.read_cards(backend, requests)
        normalized = ('long', Decimal('1.23'), values[-1])
        self.assertEqual(card.revision, revision)
        self.assertEqual(card.values, normalized)
        self.assertEqual(card.tabular_sections[0].rows[0].values, normalized)

    def test_empty_commit_and_failed_record_do_not_produce_extra_outcomes(self):
        backend, schema, _ = self.backend(4)
        _, outcomes = self.save(backend, (), outcomes=True)
        self.assertEqual(outcomes, ())
        requests = self.pair(backend, schema, auto=True)
        with closing(backend.begin_write(uuid4())) as tx:
            tx.create(requests[0].draft)
            with self.assertRaisesRegex(BackendError, 'duplicate_identity'): tx.create(requests[0].draft)
            tx.create(requests[1].draft)
            outcomes = tx.commit_outcomes()
        self.assertEqual([r.code for r in outcomes], ['00000001', '00000002'])
        self.assertEqual(tuple(card.revision for card in self.read_cards(backend, requests)),
                         tuple(outcome.revision for outcome in outcomes))

    def test_archived_source_drift_cannot_reactivate_old_writer(self):
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
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                backend.resolve_write_outcomes(operation, requests)
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                backend.begin_write(uuid4())

    def test_inert_archive_has_no_receipt_capability(self):
        from sqlite_catalog_fixture import configuration_files
        path = Path(self.temp.name) / 'inert.sqlite'
        with closing(SQLiteCatalogBackend.create_inert(path, configuration_files())) as backend:
            self.assertFalse(backend.capabilities().catalog_batch_receipts)
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.resolve_writes(uuid4(), ())
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.resolve_write_outcomes(uuid4(), ())

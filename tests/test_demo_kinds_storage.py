"""Partial exact-demo SQLite activation, not full demo/native acceptance."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration.configuration_xml import import_demo_kinds_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.forms.form_event_simulation import VerifiedFormDraftSession
from test_catalog_commit_cleanup_recovery import FaultConnection

from legacy_demo_fixture import legacy_demo_files


def files():
    return legacy_demo_files()


class DemoKindsStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.sqlite'
        self.files = files()
        self.backend = SQLiteCatalogBackend.create_demo_kinds(self.path, self.files)
        self.addCleanup(lambda: self.backend.close())
        self.schema = self.backend._schemas[0]

    def draft(self, description='Товары'):
        return CatalogDraft(CatalogKey(self.backend.database_id, self.schema.identity, uuid4()), '', description, False, (), auto_number=True)

    def save(self, draft):
        tx = self.backend.begin_write(uuid4())
        try:
            tx.create(draft)
            return tx.commit_outcomes()[0]
        finally: tx.close()

    def mutate_source(self):
        path = 'Catalogs/ВидыНоменклатуры.xml'
        raw = self.files[path] + b'\n'
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (raw, sha256(raw).hexdigest(), path))

    def test_full_archive_one_active_catalog_and_capabilities(self):
        self.assertEqual(self.backend.storage_version, 6)
        self.assertEqual(self.backend.export_configuration(), self.files)
        self.assertEqual(self.backend.active_form_catalogs(), (self.schema.identity,))
        view = self.backend.begin_read()
        try: self.assertEqual([s.name for s in view.catalogs()], ['ВидыНоменклатуры'])
        finally: view.close()
        self.assertTrue(self.backend.capabilities().catalog_write_outcomes)
        self.assertFalse(self.backend.capabilities().catalog_tabular_sections)
        self.assertEqual(self.backend.read_form_source(self.schema.identity).module_source,
                         self.files['Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form/Module.bsl'])

    def test_ordinary_create_cannot_downgrade_partial_profile(self):
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend.create_demo_kinds(Path(self.temp.name)/'invalid.sqlite', {})
        imported = import_demo_kinds_configuration(self.files)
        for activate in (False, True):
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                SQLiteCatalogBackend.create(Path(self.temp.name)/'wrong.sqlite', imported, activate=activate)

    def test_original_form_trim_refusal_and_real_persistence(self):
        session = VerifiedFormDraftSession(self.backend, self.schema.identity, code='', description='')
        state = session.change_description(' АБ ', revision=0)
        self.assertTrue(session.prepare_save(revision=state.revision).cancel)
        state = session.change_description(' Товары ', revision=state.revision)
        ready = session.prepare_save(revision=state.revision)
        self.assertFalse(ready.cancel)
        self.assertEqual(dict(ready.candidate)['Description'], 'Товары')
        outcome = self.save(self.draft(dict(ready.candidate)['Description']))
        self.assertEqual(outcome.code, '000000001')
        self.backend.close(); self.backend = SQLiteCatalogBackend(self.path)
        self.assertEqual(self.backend.export_configuration(), self.files)
        view = self.backend.begin_read()
        try: self.assertEqual(view.read_catalog(CatalogKey(self.backend.database_id, self.schema.identity, outcome.revision.record_id)).description, 'Товары')
        finally: view.close()

    def test_programmatic_write_does_not_apply_form_only_rule(self):
        context = SQLiteDBContext(self.path)
        try:
            context.require_active()
            vm = Interpreter(database_context=context)
            vm.execute('O=Catalogs.ВидыНоменклатуры.CreateItem();O.Description="АБ";O.Write();')
            self.assertEqual(vm.execute('O.Code'), '000000001')
            for name in ('Номенклатура', 'Склады'):
                with self.assertRaises(Exception): vm.execute('Catalogs.' + name + '.CreateItem()')
        finally: context.close()

    def test_source_change_blocks_new_work(self):
        draft = self.draft()
        self.assertEqual(self.save(draft).code, '000000001')
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(view.read_catalog(draft.key).description, draft.description)
        self.mutate_source()
        for action in (self.backend.begin_read, lambda: self.backend.begin_write(uuid4()),
                       lambda: self.backend.read_form_source(self.schema.identity),
                       lambda: SQLiteCatalogBackend(self.path)):
            with self.subTest(action=action), self.assertRaises(BackendError): action()
        self.assertIsNone(self.backend._active)
        with self.assertRaises(BackendError): self.save(self.draft())

    def test_generation_change_blocks_transaction(self):
        draft = self.draft()
        self.assertEqual(self.save(draft).code, '000000001')
        # Admit a read before changing the on-disk generation, too.
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(view.read_catalog(draft.key).description, draft.description)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE database_info SET generation=generation+1')
        for begin in (self.backend.begin_read, lambda: self.backend.begin_write(uuid4())):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                begin()
            self.assertIsNone(self.backend._active)

    def test_source_change_after_snapshot_before_begin_is_rejected(self):
        self.backend.read_form_source(self.schema.identity)
        self.mutate_source()
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.save(self.draft())
        from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier
        table = quote_identifier(self.backend._layout.table_name(self.schema.identity))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_write_lock_covers_source_check_and_record_commit(self):
        draft = self.draft()
        with closing(sqlite3.connect(self.path, timeout=0)) as competitor:
            with closing(self.backend.begin_write(uuid4())) as tx:
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    competitor.execute('UPDATE database_info SET generation=generation+1')
                tx.create(draft)
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    competitor.execute('UPDATE database_info SET generation=generation+1')
                self.assertEqual(tx.commit_outcomes()[0].code, '000000001')
            self.assertIsNone(self.backend._active)
            with competitor:
                self.assertEqual(competitor.execute(
                    'UPDATE database_info SET generation=generation').rowcount, 1)
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(view.read_catalog(draft.key).description, draft.description)

    def interrupted_write(self, draft, fault):
        with closing(self.backend.begin_write(uuid4())) as tx:
            tx.create(draft)
            connection = FaultConnection(tx._connection, commit_fault=fault)
            tx._connection = connection
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                tx.commit_outcomes()
            self.assertEqual(connection.commit_calls, 1)
        self.assertIsNone(self.backend._active)

    def test_uncertain_after_commit_current_record_is_present_on_reopen(self):
        draft = self.draft()
        self.interrupted_write(draft, 'after')
        with closing(SQLiteCatalogBackend(self.path, read_only=True)) as reader:
            with closing(reader.begin_read()) as view:
                record = view.read_catalog(draft.key)
                self.assertEqual((record.code, record.description), ('000000001', draft.description))
        self.assertEqual(self.save(self.draft('Other')).code, '000000002')

    def test_uncertain_before_commit_current_record_is_absent_on_reopen(self):
        draft = self.draft()
        self.interrupted_write(draft, 'before')
        with closing(SQLiteCatalogBackend(self.path, read_only=True)) as reader:
            with closing(reader.begin_read()) as view:
                self.assertIsNone(view.read_catalog(draft.key))
        self.assertEqual(self.save(self.draft('Other')).code, '000000001')
        with closing(self.backend.begin_read()) as view:
            self.assertIsNone(view.read_catalog(draft.key))

    def test_read_only_form_source_without_write_authority(self):
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        try:
            self.assertEqual(backend.active_form_catalogs(), (self.schema.identity,))
            self.assertEqual(backend.read_form_source(self.schema.identity).catalog_name, self.schema.name)
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.begin_write(uuid4())
        finally: backend.close()

    def test_v5_archive_remains_permanently_inert(self):
        backend = SQLiteCatalogBackend.create_inert(Path(self.temp.name)/'inert.sqlite', self.files)
        try:
            self.assertEqual(backend.active_form_catalogs(), ())
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.begin_write(uuid4())
            self.assertFalse(backend.capabilities().catalog_create)
        finally: backend.close()

"""Partial exact-demo SQLite activation, not full demo/native acceptance."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration_xml import import_demo_kinds_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.form_event_simulation import VerifiedFormDraftSession
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

    def save(self, draft, operation=None):
        tx = self.backend.begin_write(operation or uuid4())
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

    def test_source_change_blocks_new_work_but_resolves_historical_receipt(self):
        draft = self.draft(); operation = uuid4(); self.save(draft, operation)
        self.mutate_source()
        for action in (self.backend.begin_read, lambda: self.backend.begin_write(uuid4()),
                       lambda: self.backend.read_form_source(self.schema.identity),
                       lambda: SQLiteCatalogBackend(self.path)):
            with self.subTest(action=action), self.assertRaises(BackendError): action()
        self.assertIsNone(self.backend._active)
        with patch.object(_View, 'create', side_effect=AssertionError('replay')), patch.object(_View, 'commit', side_effect=AssertionError('recommit')):
            self.assertEqual(self.backend.resolve_write_outcome(operation, draft).code, '000000001')
        self.assertIsNone(self.backend.resolve_write_outcome(uuid4(), self.draft()))
        with self.assertRaises(BackendError): self.save(self.draft())

    def test_generation_change_blocks_transaction(self):
        draft = self.draft(); operation = uuid4(); self.save(draft, operation)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE database_info SET generation=generation+1')
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.backend.begin_write(uuid4())
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.backend.resolve_write_outcome(operation, draft)
        self.assertIsNone(self.backend._active)

    def test_source_change_after_snapshot_before_begin_is_rejected(self):
        self.backend.read_form_source(self.schema.identity)
        self.mutate_source()
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.save(self.draft())
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM commit_receipt').fetchone()[0], 0)

    def test_write_lock_covers_source_check_and_record_commit(self):
        with self.assertRaisesRegex(BackendError, 'unsupported'): self.backend._begin(uuid4(), _receipt_only=True)
        tx = self.backend.begin_write(uuid4())
        try:
            with closing(sqlite3.connect(self.path, timeout=0)) as connection:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute('UPDATE database_info SET generation=generation+1')
            tx.create(self.draft())
            self.assertEqual(tx.commit_outcomes()[0].code, '000000001')
        finally: tx.close()

    def test_uncertain_after_commit_resolves_once_after_reopen(self):
        draft = self.draft(); operation = uuid4()
        tx = self.backend.begin_write(operation); tx.create(draft)
        tx._connection = FaultConnection(tx._connection, commit_fault='after')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'): tx.commit_outcomes()
        self.backend.close(); self.backend = SQLiteCatalogBackend(self.path)
        with patch.object(_View, 'create', side_effect=AssertionError('replay')):
            outcome = self.backend.resolve_write_outcome(operation, draft)
        self.assertEqual(outcome.code, '000000001')
        self.assertEqual(self.save(self.draft()).code, '000000002')

    def test_uncertain_before_commit_can_retry_only_after_absence(self):
        draft = self.draft(); operation = uuid4()
        tx = self.backend.begin_write(operation); tx.create(draft)
        tx._connection = FaultConnection(tx._connection, commit_fault='before')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'): tx.commit_outcomes()
        self.assertIsNone(self.backend.resolve_write_outcome(operation, draft))
        self.assertEqual(self.save(draft, operation).code, '000000001')

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

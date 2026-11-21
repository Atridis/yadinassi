"""Direct catalog data uses opened configuration, not archive readmission."""
from contextlib import ExitStack, closing
from dataclasses import replace
import sqlite3
import os
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts.benchmark_extended_layers import database
from yadinassi import BSLError
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend


class CatalogRuntimeDataTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.path, self.context, self.vm, manager = database(stack)
        self.backend = self.context.backend
        self.catalog = str(manager._schema.identity)
        self.item = manager.create_item()
        self.item.set_member('Description', 'Initial')
        self.item.write()
        self.vm.variables['ref'] = self.item.get_member('Ref')
        self.table = self.backend._layout.table_name(manager._schema.identity)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(sql, args)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return (db.execute('SELECT revision,description FROM "' + self.table + '"').fetchone(),
                    db.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table' AND name='commit_receipt'").fetchone()[0])

    def test_default_bsl_get_and_write_without_full_admission(self):
        before, receipts = self.snapshot()
        with patch.object(self.backend, '_validate_transaction_admission',
                          side_effect=AssertionError('full admission')), \
             patch.object(self.backend, '_main_demo_write_source',
                          side_effect=AssertionError('unreached handler')):
            self.vm.execute('O=Ref.GetObject();O.Description="Updated";O.Write();')
            self.assertEqual(self.vm.execute('Ref.GetObject().Description'), 'Updated')
        self.assertEqual(self.snapshot(), ((before[0] + 1, 'Updated'), receipts))

    def test_warm_scalar_points_and_revision_update_are_single_statements(self):
        statements = []
        connect = sqlite3.connect
        def observe(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        if self.backend._read_handle is not None:
            self.backend._read_handle.connection.set_trace_callback(statements.append)
        with patch.object(sqlite3, 'connect', observe):
            # Use both handles first, outside the measured statements.
            self.vm.execute('O=Ref.GetObject();O.Write();')
            statements.clear()
            self.vm.execute('O=Ref.GetObject();O.Description="Standalone";O.Write();D=Ref.Description;')
        self.assertEqual(self.vm.variables['d'], 'Standalone')
        self.assertEqual([sql.split()[0] for sql in statements], ['SELECT', 'UPDATE', 'SELECT'])

    def test_implicit_update_with_unknown_ack_requires_fresh_object(self):
        from yadinassi.db.sqlite import sqlite_single_statement

        self.vm.execute('O=Ref.GetObject();')
        before = self.snapshot()[0][0]
        execute_write = sqlite_single_statement.execute_write
        def lose_ack(*args):
            self.assertEqual(execute_write(*args), 1)
            raise sqlite3.OperationalError('acknowledgement lost')

        with patch.object(sqlite_single_statement, 'execute_write', lose_ack):
            with self.assertRaisesRegex(BSLError, 'uncertain_commit'):
                self.vm.execute('O.Description="Persisted";O.Write();')
        with self.assertRaisesRegex(BSLError, 'uncertain_commit'):
            self.vm.execute('O.Description="Retry";O.Write();')
        self.assertEqual(self.snapshot()[0], (before + 1, 'Persisted'))
        self.assertIsNone(self.backend._active)
        self.vm.execute('O=Ref.GetObject();O.Description="Fresh";O.Write();')
        self.assertEqual(self.snapshot()[0], (before + 2, 'Fresh'))

    def test_two_catalogs_read_create_update_and_select_without_metadata_sql(self):
        # Both managers are part of the already opened data descriptor, with
        # distinct physical maps. SQL below records actual application work.
        statements=[]
        connect=sqlite3.connect
        def observe(*args,**kwargs):
            connection=connect(*args,**kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        handle=self.backend._read_handle
        if handle is not None:handle.connection.set_trace_callback(statements.append)
        for name in ('Склады','ВидыНоменклатуры'):
            self.vm._catalogs.get_member(name)
        statements.clear()
        with patch.object(sqlite3,'connect',observe), \
             patch.object(self.backend,'_validate_transaction_admission',
                          side_effect=AssertionError('ordinary record admission')):
            for name in ('Склады','ВидыНоменклатуры'):
                self.vm.execute(f'M=Catalogs.{name}; C=M.CreateItem(); C.Description="New"; C.Write();'
                                'R=C.Ref; O=R.GetObject(); O.Description="Updated"; O.Write();'
                                'N=R.Description; S=M.Select(); HasRow=S.Next(); '
                                'Found=M.FindByDescription("Updated",True); Exact=Found.Description="Updated"; '
                                'Same=M.FindByCode(C.Code)=R;')
                self.assertEqual(self.vm.variables['n'],'Updated')
                self.assertTrue(self.vm.variables['hasrow'])
                self.assertTrue(self.vm.variables['exact'])
                self.assertTrue(self.vm.variables['same'])
        forbidden=('database_info','sqlite_schema','sqlite_master','catalog_schema','storage_map')
        unexpected=[sql for sql in statements if any(name in sql.lower() for name in forbidden)]
        self.assertEqual(unexpected,[])
        for verb in ('SELECT','INSERT','UPDATE','COMMIT'):
            self.assertTrue(any(sql.startswith(verb) for sql in statements), (verb,statements))

    def test_source_bytes_do_not_reauthorize_data_or_code(self):
        self.mutate("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'", ('0' * 64,))
        with self.assertRaises(BackendError):
            self.backend.begin_read()
        with self.assertRaises(BackendError):
            self.backend.begin_unit_of_work(uuid4())
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(self.path)
        self.vm.execute('O=Ref.GetObject();O.Description="Opened layout";O.Write();')
        self.assertEqual(self.snapshot()[0][1], 'Opened layout')

    def assert_fresh_admission_rejects_external_edit(self):
        with self.assertRaises(BackendError):
            self.backend.begin_read()
        with self.assertRaises(BackendError):
            self.backend.begin_write(uuid4())
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(self.path)

    def test_ordinary_data_uses_open_layout_after_external_registry_edit(self):
        for table, key, name, value in (
                ('catalog_schema', 'identity', 'name', 'changed name'),
                ('catalog_storage_map', 'catalog_id', 'physical_name', 'changed_table')):
            with self.subTest(table=table), closing(sqlite3.connect(self.path)) as db:
                old = db.execute(f'SELECT {name} FROM {table} WHERE {key}=?', (self.catalog,)).fetchone()[0]
                before, receipts = self.snapshot()
                self.mutate(f'UPDATE {table} SET {name}=? WHERE {key}=?', (value, self.catalog))
                try:
                    self.assert_fresh_admission_rejects_external_edit()
                    self.assertEqual(self.vm.execute('Ref.GetObject().Description'), before[1])
                    self.vm.execute('O=Ref.GetObject();O.Description="Opened mapping";O.Write();')
                    self.assertEqual(self.snapshot(), ((before[0]+1, 'Opened mapping'), receipts))
                    self.assertEqual(db.execute(f'SELECT {name} FROM {table} WHERE {key}=?',
                                                (self.catalog,)).fetchone(), (value,))
                finally:
                    self.mutate(f'UPDATE {table} SET {name}=? WHERE {key}=?', (old, self.catalog))

    def test_external_trigger_is_not_executed_even_with_restored_cookie(self):
        self.vm.execute('O=Ref.GetObject();')
        before = self.snapshot()
        with closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute(f"""CREATE TRIGGER unopened_shape AFTER UPDATE ON "{self.table}"
                       BEGIN UPDATE "{self.table}" SET description='Unexpected'; END""")
            db.execute(f'PRAGMA schema_version={old}')
        self.assert_fresh_admission_rejects_external_edit()
        self.assertEqual(self.vm.execute('Ref.GetObject().Description'), before[0][1])
        with self.assertRaises(BSLError):
            self.vm.execute('O.Description="Should not persist";O.Write();')
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.backend._active)

    def test_open_generation_stays_fixed_while_fresh_admission_rejects_edit(self):
        before, receipts = self.snapshot()
        self.mutate('UPDATE database_info SET generation=2')
        self.assert_fresh_admission_rejects_external_edit()
        self.vm.execute('O=Ref.GetObject();O.Description="Opened generation";O.Write();')
        self.assertEqual(self.snapshot(), ((before[0]+1, 'Opened generation'), receipts))
        self.assertEqual(self.vm.variables['o']._revision.configuration_generation, 1)

    def test_ordinary_catalogs_refuse_replaced_file_even_with_same_database_identity(self):
        self.vm.execute('O=Ref.GetObject();')
        before = self.snapshot()
        self.backend._close_idle_read_handle()
        replacement = self.path.with_suffix('.replacement')
        shutil.copyfile(self.path,replacement)
        os.replace(replacement,self.path)
        with self.assertRaisesRegex(BSLError,'schema_changed'):
            self.vm.execute('Ref.GetObject()')
        with self.assertRaisesRegex(BSLError,'schema_changed'):
            self.vm.execute('O.Description="Replacement";O.Write();')
        self.assertEqual(self.snapshot(), before)

    def test_opened_handler_witness_cannot_be_replaced(self):
        self.vm.execute('O=Ref.GetObject();')
        before = self.snapshot()
        config = self.backend.accumulation_configuration
        with patch.object(self.backend, 'accumulation_configuration', replace(config, catalog_handlers=())):
            with self.assertRaises(BSLError):
                self.vm.execute('O.Write();')
        handlers = config.catalog_handlers
        object.__setattr__(config, 'catalog_handlers', ())
        try:
            with self.assertRaises(BSLError):
                self.vm.execute('O.Write();')
        finally:
            object.__setattr__(config, 'catalog_handlers', handlers)
        self.assertEqual(self.snapshot(), before)

    def test_stale_object_remains_conflicted_and_leaves_receipts_unchanged(self):
        self.vm.execute('A=Ref.GetObject();B=Ref.GetObject();A.Description="Winner";A.Write();')
        before = self.snapshot()
        with self.assertRaisesRegex(BSLError, 'conflict'):
            self.vm.execute('B.Description="Stale";B.Write();')
        self.assertEqual(self.snapshot(), before)

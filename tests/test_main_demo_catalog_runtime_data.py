"""Direct catalog data uses opened configuration, not archive readmission."""
from contextlib import ExitStack, closing
from dataclasses import replace
import sqlite3
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

    def test_selected_catalog_and_layout_mutation_are_refused(self):
        for table, key, name, value in (
                ('catalog_schema', 'identity', 'name', 'changed name'),
                ('catalog_storage_map', 'catalog_id', 'physical_name', 'changed_table')):
            with self.subTest(table=table), closing(sqlite3.connect(self.path)) as db:
                self.vm.execute('O=Ref.GetObject();')
                old = db.execute(f'SELECT {name} FROM {table} WHERE {key}=?', (self.catalog,)).fetchone()[0]
                before = self.snapshot()
                self.mutate(f'UPDATE {table} SET {name}=? WHERE {key}=?', (value, self.catalog))
                try:
                    with self.assertRaises(BSLError):
                        self.vm.execute('Ref.GetObject()')
                    with self.assertRaises(BSLError):
                        self.vm.execute('O.Description="Should not persist";O.Write();')
                    self.assertEqual(self.snapshot(), before)
                finally:
                    self.mutate(f'UPDATE {table} SET {name}=? WHERE {key}=?', (old, self.catalog))

    def test_real_ddl_change_even_with_restored_cookie_and_live_identity(self):
        self.vm.execute('O=Ref.GetObject();')
        before = self.snapshot()
        with closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute('CREATE TRIGGER unopened_shape AFTER UPDATE ON "' + self.table + '" BEGIN SELECT 1; END')
            db.execute(f'PRAGMA schema_version={old}')
        with self.assertRaises(BSLError):
            self.vm.execute('Ref.GetObject()')
        with self.assertRaises(BSLError):
            self.vm.execute('O.Description="Should not persist";O.Write();')
        self.assertEqual(self.snapshot(), before)
        self.mutate('DROP TRIGGER unopened_shape')
        self.mutate('UPDATE database_info SET generation=2')
        with self.assertRaises(BSLError):
            self.vm.execute('O.Write();')
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

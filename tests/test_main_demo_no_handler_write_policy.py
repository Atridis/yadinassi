"""Handler-free policy selection is lazy; writer admission remains mandatory."""
from contextlib import ExitStack, closing
from dataclasses import replace
import sqlite3
import unittest
from unittest.mock import patch

from scripts.benchmark_extended_layers import database
from yadinassi.db.catalog.catalog_backend import BackendError


class NoHandlerWritePolicyTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.path, self.context, self.owner, self.manager = database(self.stack)
        self.backend = self.context.backend
        self.item = self.manager.create_item()
        self.item.set_member('Description', 'Initial')
        self.item.write()

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as con:
            table = self.backend._layout.table_name(self.manager._schema.identity)
            return (con.execute('SELECT * FROM "' + table.replace('"', '""') + '"').fetchall(),
                    con.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name='commit_receipt'").fetchall())

    def test_no_handler_skips_lookup_but_write_still_admits(self):
        with patch.object(self.backend, '_main_demo_write_source', side_effect=AssertionError('redundant lookup')), \
             patch.object(self.backend, '_validate_transaction_admission', wraps=self.backend._validate_transaction_admission) as admit:
            self.item.set_member('Description', 'Updated')
            self.item.write()
        self.assertEqual(admit.call_count, 1)
        self.assertEqual(self.snapshot()[0][0][3], 'Updated')

    def test_external_source_change_cannot_write(self):
        before = self.snapshot()
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'", ('0' * 64,))
        self.item.set_member('Description', 'Must not persist')
        with self.assertRaises(BackendError):
            self.item.write()
        self.assertEqual(self.snapshot(), before)

    def test_local_handler_metadata_mutation_cannot_write(self):
        before = self.snapshot()
        config = self.backend.accumulation_configuration
        self.backend.accumulation_configuration = replace(config, catalog_handlers=())
        self.addCleanup(setattr, self.backend, 'accumulation_configuration', config)
        self.item.set_member('Description', 'Must not persist')
        with self.assertRaises(BackendError):
            self.item.write()
        self.assertEqual(self.snapshot(), before)

    def test_in_place_handler_metadata_mutation_cannot_write(self):
        before = self.snapshot()
        config = self.backend.accumulation_configuration
        handlers = config.catalog_handlers
        object.__setattr__(config, 'catalog_handlers', ())
        self.addCleanup(object.__setattr__, config, 'catalog_handlers', handlers)
        self.item.set_member('Description', 'Must not persist')
        with self.assertRaises(BackendError):
            self.item.write()
        self.assertEqual(self.snapshot(), before)

    def test_external_schema_change_cannot_write(self):
        before = self.snapshot()
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("UPDATE catalog_schema SET name='Changed' WHERE identity=?",
                        (str(self.manager._schema.identity),))
        self.item.set_member('Description', 'Must not persist')
        with self.assertRaises(BackendError):
            self.item.write()
        self.assertEqual(self.snapshot(), before)

    def test_existing_handler_keeps_validated_selection(self):
        config = self.backend.accumulation_configuration
        self.assertTrue(config.catalog_handlers)
        catalog_id, path, digest = config.catalog_handlers[0]
        with patch.object(self.backend, '_main_demo_write_source', wraps=self.backend._main_demo_write_source) as lookup:
            source = self.backend.catalog_write_preparation(catalog_id)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(source, dict(config.files)[path].decode('utf-8-sig'))

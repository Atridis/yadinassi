from contextlib import ExitStack, closing
from decimal import Decimal
import sqlite3
import unittest

from scripts.benchmark_sqlite_update_reference import make_update_reference, StaleRevisionError


class SQLiteUpdateReferenceTests(unittest.TestCase):
    def setUp(self):
        from scripts.benchmark_extended_layers import database
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.path, self.context, self.owner, self.manager = database(self.stack)
        item = self.manager.create_item()
        item.set_member('Description', 'Initial')
        item.write()
        self.ref = item.get_member('Ref')
        catalog_id = self.manager._schema.identity
        with closing(sqlite3.connect(self.path)) as connection:
            table = connection.execute('SELECT physical_name FROM catalog_storage_map WHERE catalog_id=?', (str(catalog_id),)).fetchone()[0]
            rid = connection.execute('SELECT record_id FROM "' + table.replace('"', '""') + '"').fetchone()[0]
        self.run = make_update_reference(self.path, catalog_id, rid, 3)
        self.stack.callback(self.run.close)

    def test_real_fixture_and_canonical_readback(self):
        before = self.run.read_record()
        self.assertEqual(self.run(), Decimal(3))
        self.run.verify()
        value = self.ref.get_object(self.ref)
        self.assertEqual(value.get_member('Description'), '3')
        after = self.run.read_record()
        self.assertEqual(after.revision, before.revision + 3)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table' AND name='commit_receipt'").fetchone()[0], 0)

    def test_warmed_trace_is_one_read_and_one_committed_update_per_iteration(self):
        statements = []
        self.run._reader.set_trace_callback(statements.append)
        self.run._writer.set_trace_callback(statements.append)
        try:
            self.assertEqual(self.run(), Decimal(3))
        finally:
            self.run._reader.set_trace_callback(None)
            self.run._writer.set_trace_callback(None)
        verbs = [sql.split()[0] for sql in statements]
        self.assertEqual(verbs, ['SELECT', 'UPDATE'] * 3)
        self.assertFalse(self.run._reader.in_transaction)
        self.assertFalse(self.run._writer.in_transaction)
        self.run.verify()

    def test_stale_revision_does_not_write(self):
        record = self.run.read_record()
        self.run.update_record(record, 'first')
        saved = self.run.read_record()
        with self.assertRaises(StaleRevisionError):
            self.run.update_record(record, 'stale')
        self.assertEqual(self.run.read_record(), saved)

    def test_sql_error_rolls_back_update(self):
        before = self.run.read_record()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(f"CREATE TRIGGER refuse_test_update BEFORE UPDATE ON {self.run.table} "
                               "BEGIN SELECT RAISE(ABORT, 'refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.run.update_record(before, 'must roll back')
        self.assertEqual(self.run.read_record(), before)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DROP TRIGGER refuse_test_update')
        self.run.update_record(before, 'saved')
        self.assertEqual(self.run.read_record().description, 'saved')

    def test_description_validation_and_zero_iterations(self):
        before = self.run.read_record()
        with self.assertRaises(ValueError):
            self.run.update_record(before, 'x' * 101)
        self.assertEqual(self.run.read_record(), before)
        zero = make_update_reference(self.path, self.run.catalog_id, self.run.record_id, 0)
        self.stack.callback(zero.close)
        self.assertEqual(zero(), Decimal(0))
        zero.verify()
        self.assertEqual(zero.read_record(), before)

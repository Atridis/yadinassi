from contextlib import ExitStack, closing
from decimal import Decimal
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

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

    def test_real_fixture_and_canonical_readback(self):
        before = self.run.read_record()
        self.assertEqual(self.run(), Decimal(3))
        self.run.verify()
        value = self.ref.get_object(self.ref)
        self.assertEqual(value.get_member('Description'), '3')
        after = self.run.read_record()
        self.assertEqual(after.revision, before.revision + 3)
        # Independent expected canonical receipt, not the helper's stored digest.
        outcomes = [[self.run.catalog_id, after.record_id, str(after.revision), after.code]]
        intent = [self.run.catalog_id, after.record_id, after.code, '3', bool(after.deletion_mark), '[]', after.revision]
        encoded = json.dumps(['write_outcomes_v1', [intent], outcomes], ensure_ascii=True, separators=(',', ':'), allow_nan=False)
        self.assertEqual(self.run._last_receipt[1], hashlib.sha256(encoded.encode()).hexdigest())

    def test_stale_revision_does_not_write_or_add_receipt(self):
        record = self.run.read_record()
        self.run.update_record(record, 'first')
        with closing(sqlite3.connect(self.path)) as c:
            count = c.execute('SELECT COUNT(*) FROM commit_receipt').fetchone()[0]
        with self.assertRaises(StaleRevisionError):
            self.run.update_record(record, 'stale')
        self.assertEqual(self.run.read_record().description, 'first')
        with closing(sqlite3.connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM commit_receipt').fetchone()[0], count)

    def test_receipt_failure_rolls_back_update(self):
        before = self.run.read_record()
        receipt = self.run.update_record(before, 'first')
        before = self.run.read_record()
        with patch('scripts.benchmark_sqlite_update_reference.uuid4', return_value=receipt[0]):
            with self.assertRaises(sqlite3.IntegrityError):
                self.run.update_record(before, 'must roll back')
        self.assertEqual(self.run.read_record(), before)
        self.run.update_record(before, 'recovered')
        self.assertEqual(self.run.read_record().description, 'recovered')

    def test_description_validation_and_zero_iterations(self):
        before = self.run.read_record()
        with self.assertRaises(ValueError):
            self.run.update_record(before, 'x' * 101)
        self.assertEqual(self.run.read_record(), before)
        zero = make_update_reference(self.path, self.run.catalog_id, self.run.record_id, 0)
        self.assertEqual(zero(), Decimal(0))
        zero.verify()
        self.assertEqual(zero.read_record(), before)

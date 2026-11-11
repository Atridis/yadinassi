"""Batch ports preserve point snapshots without partition-proportional SQL."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_recorder_movement_storage as recorder_fixture
import test_accumulation_movement_storage as accumulation_fixture
from yadinassi.catalog_backend import BackendError
from yadinassi.document_backend import DocumentKey


class BatchContract:
    def other_key(self):
        key = DocumentKey(self.db, self.doc, uuid4())
        self.c.execute('INSERT INTO document_record VALUES(?,?)',
                       (str(self.doc), str(key.record_id)))
        return key

    def traced_scan(self):
        statements = []
        self.c.set_trace_callback(statements.append)
        try:
            result = self.port.scan(self.reg)
        finally:
            self.c.set_trace_callback(None)
        return result, statements

    def test_empty_partition_sql_count_is_constant(self):
        self.port.replace(uuid4(), self.request(rows=()))
        _, initial = self.traced_scan()
        for _ in range(49):
            self.port.replace(uuid4(), self.request(self.other_key(), ()))
        result, statements = self.traced_scan()
        self.assertEqual(len(result), 50)
        self.assertEqual(len(statements), len(initial))
        self.assertLess(len(statements), 20)
        self.assertTrue(all(part.revision == 1 and part.rows == () for _, part in result))
        self.assertFalse(any(sql.startswith(('BEGIN', 'COMMIT', 'ROLLBACK')) for sql in statements))
        self.assertTrue(self.c.in_transaction)

    def test_mixed_partitions_exactly_match_point_snapshots(self):
        keys = [self.key] + [self.other_key() for _ in range(4)]
        for index, key in enumerate(keys):
            self.port.replace(uuid4(), self.request(key, () if index % 2 else None))
        expected = tuple((key, self.port.read(self.reg, key)) for key in
                         sorted(keys, key=lambda key: (str(key.document_id), str(key.record_id))))
        self.assertEqual(self.port.scan(self.reg), expected)

    def test_corrupt_last_payload_fails_whole_scan(self):
        for key in [self.key, self.other_key()]:
            self.port.replace(uuid4(), self.request(key))
        self.c.execute(f"UPDATE {self.table}_movement SET values_json='[]' WHERE record_id=?",
                       (max(row[0] for row in self.c.execute(f'SELECT record_id FROM {self.table}_partition')),))
        with self.assertRaises(BackendError) as caught:
            self.port.scan(self.reg)
        self.assertEqual(caught.exception.code, 'integrity')
        self.assertTrue(self.c.in_transaction)

    def test_scan_does_not_delegate_point_reads(self):
        self.port.replace(uuid4(), self.request())
        with patch.object(self.port, 'read', side_effect=AssertionError('N+1')):
            self.assertEqual(len(self.port.scan(self.reg)), 1)

    def test_borrowed_rollback_removes_staged_scan(self):
        self.port.replace(uuid4(), self.request())
        self.assertEqual(len(self.port.scan(self.reg)), 1)
        self.c.execute('ROLLBACK')
        self.c.execute('BEGIN')
        self.assertEqual(self.port.scan(self.reg), ())


class RecorderBatchTests(BatchContract, unittest.TestCase):
    setUp = recorder_fixture.RecorderStorageTests.setUp
    request = recorder_fixture.RecorderStorageTests.request
    table = 'recorder'


class AccumulationBatchTests(BatchContract, unittest.TestCase):
    setUp = accumulation_fixture.AccumulationStorageTests.setUp
    request = accumulation_fixture.AccumulationStorageTests.request
    table = 'accumulation'

    def test_duplicate_occurrences_remain_distinct(self):
        rows = (self.row, replace(self.row, line_number=2))
        for key in [self.key, self.other_key()]:
            self.port.replace(uuid4(), self.request(key, rows))
        self.assertEqual([part.rows for _, part in self.port.scan(self.reg)], [rows, rows])

    def test_configurable_partition_limit_is_not_register_limit(self):
        for key in [self.key, self.other_key()]:
            self.port.replace(uuid4(), self.request(key))
        with patch('yadinassi.sqlite_accumulation_movements.MAX_MOVEMENT_ROWS', 1):
            self.assertEqual(len(self.port.scan(self.reg)), 2)

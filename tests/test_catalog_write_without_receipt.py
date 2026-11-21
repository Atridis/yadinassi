"""A SQLite catalog commit does not insert or replay a durable receipt."""
from contextlib import closing
from dataclasses import replace
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_catalog_commit_cleanup_recovery import FaultConnection
import test_main_demo_catalog_runtime_data as fixture
from yadinassi.db.catalog.catalog_backend import BackendError


class CatalogWriteWithoutReceiptTests(unittest.TestCase):
    setUp = fixture.CatalogRuntimeDataTests.setUp
    mutate = fixture.CatalogRuntimeDataTests.mutate
    snapshot = fixture.CatalogRuntimeDataTests.snapshot

    def observe_begin(self, **fault):
        original = self.backend.begin_write
        observed, trace = [], []

        def begin(operation, **kwargs):
            view = original(operation, **kwargs)
            view._connection.set_trace_callback(trace.append)
            connection = FaultConnection(view._connection, **fault)
            view._connection = connection
            observed.append(connection)
            return view

        return patch.object(self.backend, 'begin_write', side_effect=begin), observed, trace

    def test_raw_default_does_not_read_or_modify_historical_receipt(self):
        operation = uuid4()
        record = (str(operation), '0' * 64, '[]')
        self.mutate('INSERT INTO commit_receipt VALUES(?,?,?)', record)
        statements = []
        connect = self.backend._connect

        def observe(*args, **kwargs):
            con = connect(*args, **kwargs)
            con.set_trace_callback(statements.append)
            return con

        key = self.item._key
        with patch.object(self.backend, '_connect', side_effect=observe):
            with closing(self.backend.begin_write(operation)) as writer:
                card = writer.read_catalog(key)
                draft = replace(self.item._write_draft(), description='Raw update')
                writer.update(draft, card.revision)
                outcome, = writer.commit_outcomes()
                self.assertEqual(int(outcome.revision.token), 1 + int(card.revision.token))
                self.assertIsNone(self.backend._active)
        sql = [s for s in statements if 'receipt' in s]
        self.assertTrue(all('sqlite_schema' in statement or 'sqlite_master' in statement for statement in sql), sql)
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(con.execute('SELECT * FROM commit_receipt').fetchall(), [record])
        self.assertEqual(self.snapshot()[0][1], 'Raw update')

    def test_ambiguous_result_never_replays_before_or_after_sql_commit(self):
        for fault, applied in (('before', False), ('after', True)):
            with self.subTest(fault=fault):
                item = self.item.get_member('Ref').get_object(self.item.get_member('Ref'))
                before, receipts = self.snapshot()
                item.set_member('Description', fault)
                instrument, observed, trace = self.observe_begin(commit_fault=fault)
                with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                    item.write()
                self.assertEqual(observed[0].commit_calls, 1)
                self.assertIsNone(item._pending_write)
                self.assertTrue(item._uncertain_write)
                self.assertIsNone(self.backend._active)
                with patch.object(self.backend, 'resolve_write_outcome', side_effect=AssertionError('lookup')), \
                     patch.object(self.backend, 'begin_write', side_effect=AssertionError('replay')):
                    with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                        item.write()
                    with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                        item.set_member('Description', 'replacement')
                self.assertFalse(any('receipt' in statement for statement in trace), trace)
                expected = (before[0] + 1, fault) if applied else before
                self.assertEqual(self.snapshot(), (expected, receipts))
                fresh = item.get_member('Ref').get_object(item.get_member('Ref'))
                self.assertEqual(fresh.get_member('Description'), expected[1])

    def test_confirmed_commit_keeps_outcome_even_if_close_fails(self):
        before, receipts = self.snapshot()
        self.item.set_member('Description', 'Confirmed')
        instrument, observed, _ = self.observe_begin(close_fault='before', close_count=1)
        with instrument, self.assertRaisesRegex(BackendError, 'storage_error'):
            self.item.write()
        self.assertFalse(self.item._uncertain_write)
        self.assertEqual(int(self.item._revision.token), before[0] + 1)
        self.assertEqual(observed[0].commit_calls, 1)
        self.assertIsNone(self.backend._active)
        self.assertEqual(self.snapshot(), ((before[0] + 1, 'Confirmed'), receipts))

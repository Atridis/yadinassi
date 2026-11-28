from contextlib import ExitStack
import sqlite3
import unittest

from scripts.benchmark_extended_layers import database
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_single_statement import fetch_one, run


def _allow(*unused):
    return sqlite3.SQLITE_OK


class SingleStatementConnectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        _, context, _, _ = database(self.stack)
        self.backend = context.backend

    def test_each_role_reuses_idle_handle_and_backend_close_retires_it(self):
        roles = {}
        def select(connection):
            roles.setdefault('read', []).append(connection)
            return fetch_one(connection, 'SELECT 1')

        def write_handle(connection):
            roles.setdefault('write', []).append(connection)
            return fetch_one(connection, 'SELECT 2')

        for _ in range(2):
            self.assertEqual(run(self.backend, select), (1,))
            self.assertEqual(run(self.backend, write_handle, write=True, authorizer=_allow), (2,))
        reader, writer = roles['read'][0], roles['write'][0]
        self.assertIs(reader, roles['read'][1])
        self.assertIs(writer, roles['write'][1])
        self.assertIsNot(reader, writer)
        self.assertFalse(reader.in_transaction)
        self.assertFalse(writer.in_transaction)
        self.assertEqual(fetch_one(reader, 'PRAGMA query_only'), (1,))
        self.assertEqual(fetch_one(writer, 'PRAGMA synchronous'), (2,))
        self.backend.close()
        for connection in (reader, writer):
            with self.assertRaises(sqlite3.ProgrammingError):
                fetch_one(connection, 'SELECT 1')

    def test_error_retires_failed_writer_and_active_view_is_not_bypassed(self):
        seen = []
        def refuse(connection):
            seen.append(connection)
            raise RuntimeError('fault')

        with self.assertRaisesRegex(RuntimeError, 'fault'):
            run(self.backend, refuse, write=True, authorizer=_allow)
        with self.assertRaises(sqlite3.ProgrammingError):
            fetch_one(seen[0], 'SELECT 1')

        view = self.backend.begin_read()
        try:
            with self.assertRaisesRegex(BackendError, 'busy'):
                run(self.backend, refuse, write=True, authorizer=_allow)
        finally:
            view.close()
        self.assertEqual(len(seen), 1)
        self.assertEqual(run(self.backend, lambda c: fetch_one(c, 'SELECT 1'),
                             write=True, authorizer=_allow), (1,))

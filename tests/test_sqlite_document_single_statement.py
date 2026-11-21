"""Single-statement Posted point reads are detached host data, not source authority."""
from contextlib import closing
from dataclasses import replace
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_main_demo_runtime as demo
from yadinassi.db import database_transactions as transactions
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend


class DocumentPostedStatementTests(unittest.TestCase):
    setUp = demo.MainDemoRuntimeTests.setUp

    def seed(self):
        self.vm.execute(demo.SEED + '''
D=Documents.Receipt.CreateDocument(); D.Number="r1"; D.Date=Date(2024,1,1);
D.Warehouse=Склад.Ссылка; L=D.Lines.Add(); L.Product=Карточка.Ссылка;
L.Quantity=5; L.Amount=10; L.Unit=Enums.Units.Piece;
D.Write(DocumentWriteMode.Posting);
''')
        return self.vm.variables['d']._key

    def test_readonly_host_point_uses_one_select_and_no_explicit_transaction(self):
        key = self.seed()
        with closing(SQLiteCatalogBackend(self.path, read_only=True)) as backend:
            self.assertIs(backend.read_document_posted(key), True)
            connection = backend._read_handle.connection
            trace = []
            connection.set_trace_callback(trace.append)
            with (patch.object(backend, '_validate_transaction_admission',
                               side_effect=AssertionError('ordinary Posted data admission')),
                  patch.object(backend, 'begin_read',
                               side_effect=AssertionError('explicit read view'))):
                self.assertIs(backend.read_document_posted(key), True)
                self.assertIsNone(backend.read_document_posted(replace(key, record_id=uuid4())))
            queries = [sql for sql in trace if sql.lstrip().upper().startswith('SELECT')]
            self.assertEqual(len(queries), 2, trace)
            self.assertTrue(all('LEFT JOIN document_posting_state' in sql for sql in queries), trace)
            self.assertFalse(any(sql.lstrip().upper().startswith(
                ('BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE')) for sql in trace), trace)
            self.assertFalse(connection.in_transaction)
            self.assertIsNone(backend._active)

    def test_live_posted_state_validation_and_explicit_owner_retained(self):
        key = self.seed()
        backend = self.context.backend
        with transactions.execution(backend):
            transactions.begin(backend)
            with patch('yadinassi.db.sqlite.sqlite_single_statement.run',
                       side_effect=AssertionError('borrowed transaction is not autocommit')):
                self.assertIs(backend.read_document_posted(key), True)
            self.assertTrue(transactions.active(backend))
            transactions.rollback(backend)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE document_posting_state SET document_revision=document_revision+100')
        with self.assertRaisesRegex(BackendError, 'integrity'):
            backend.read_document_posted(key)
        self.assertIsNone(backend._active)

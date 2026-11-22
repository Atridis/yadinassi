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

    def test_bsl_posted_aliases_missing_and_other_document_are_point_reads(self):
        self.seed()
        self.vm.variables['missing_ref'] = str(uuid4())
        self.vm.execute('''I=Documents.Issue.CreateDocument();I.Number="i1";I.Date=Date(2024,1,1);
I.Warehouse=Склад.Ссылка;I.Write();''')
        backend = self.context.backend
        self.assertTrue(self.vm.execute('D.Ref.Posted'))
        connection = backend._read_handle.connection
        trace = []
        connection.set_trace_callback(trace.append)
        try:
            with patch.object(backend,'_validate_transaction_admission',
                              side_effect=AssertionError('full document admission')):
                self.assertTrue(self.vm.execute('D.Ref.Проведён'))
                self.assertFalse(self.vm.execute('I.Ref.Проведен'))
                self.assertFalse(self.vm.execute('Documents.Receipt.EmptyRef().Posted'))
                self.assertFalse(self.vm.execute('Documents.Receipt.GetRef(New UUID(Missing_Ref)).Posted'))
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(len(trace),4,trace)
        self.assertTrue(all(sql.startswith('SELECT') and
                            'LEFT JOIN main.document_posting_state' in sql
                            and 'document_part_' not in sql for sql in trace),trace)
        self.assertFalse(connection.in_transaction)
        self.assertIsNone(backend._active)

    def test_bsl_live_posted_refuses_explicit_transfer_and_preserves_host_override(self):
        self.seed()
        backend = self.context.backend
        self.vm.execute('''BeginTransaction();
Denied=False;Try X=D.Ref.Posted;Except Denied=True;EndTry;
StillOwn=TransactionActive();RollbackTransaction();''')
        self.assertTrue(self.vm.execute('Denied And StillOwn'))
        with patch.object(backend,'begin_read',wraps=backend.begin_read) as override:
            self.assertTrue(self.vm.execute('D.Ref.Posted'))
            self.assertEqual(override.call_count,1)

    def test_bsl_posted_validates_selected_header_state_and_existing_owner(self):
        from yadinassi import BSLRuntimeError
        self.seed()
        backend = self.context.backend
        namespace = self.vm._metadata._enumerations
        self.vm._metadata._enumerations = object()
        try:
            with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Ref.Posted')
        finally:
            self.vm._metadata._enumerations = namespace
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute("UPDATE document_record SET date='invalid'")
        with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Ref.Posted')
        self.assertIsNone(backend._active)
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute("UPDATE document_record SET date='20240101000000'")
            peer.execute('UPDATE document_posting_state SET document_revision=document_revision+1')
        with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Ref.Posted')
        self.assertIsNone(backend._active)
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute('UPDATE document_record SET revision=revision+2')
        # The persisted state may legitimately refer to an earlier revision.
        self.assertTrue(self.vm.execute('D.Ref.Posted'))

    def test_bsl_posted_checks_live_identity_and_manifest_even_on_missing(self):
        from yadinassi import BSLRuntimeError
        self.seed()
        backend = self.context.backend
        for field, changed, old in (
                ('generation',2,1),('database_uuid',str(uuid4()),str(backend.database_id)),
                ('activated',0,1)):
            with self.subTest(field=field):
                with closing(sqlite3.connect(self.path)) as peer, peer:
                    peer.execute('UPDATE database_info SET '+field+'=?',(changed,))
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('Documents.Receipt.EmptyRef().Posted')
                self.assertIsNone(backend._active)
                with closing(sqlite3.connect(self.path)) as peer, peer:
                    peer.execute('UPDATE database_info SET '+field+'=?',(old,))
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute('UPDATE document_schema SET definition=definition||? WHERE name=?',(' ','Receipt'))
        with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Ref.Posted')
        self.assertIsNone(backend._active)

    def test_bsl_posted_checks_only_selected_attribute_row_presence(self):
        from yadinassi import BSLRuntimeError
        from yadinassi.db.sqlite.sqlite_document_layout import data_table
        key = self.seed()
        schema = self.vm._documents.get_index('Receipt')._schema
        self.assertTrue(self.vm.execute('D.Ref.Posted'))
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute('DELETE FROM "'+data_table(schema)+'" WHERE record_id=?',(str(key.record_id),))
        with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Ref.Posted')
        self.assertIsNone(self.context.backend._active)

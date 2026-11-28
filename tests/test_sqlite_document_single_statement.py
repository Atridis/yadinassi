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
D.Warehouse=Склад.Ссылка; D.State=Enums.States.Draft; L=D.Lines.Add(); L.Product=Карточка.Ссылка;
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

    def test_live_typed_document_fields_share_one_statement_per_access(self):
        self.seed()
        vm = self.vm
        vm.variables['missing_ref'] = str(uuid4())
        wanted = (
            ('D.Ref.Номер','r1'),
            ('(D.Ref.Дата=Date(2024,1,1))',True),
            ('D.Ref.ПометкаУдаления',False),
            ('(D.Ref.Warehouse=Склад.Ref)',True),
            ('(D.Ref.State=Enums.States.Draft)',True),
            ('Documents.Receipt.EmptyRef().Number',''),
            ('(Documents.Receipt.EmptyRef().Date=Date(1,1,1))',True),
            ('Documents.Receipt.EmptyRef().Warehouse.IsEmpty()',True),
            ('Documents.Receipt.GetRef(New UUID(Missing_Ref)).State.IsEmpty()',True),
        )
        self.assertEqual(vm.execute('D.Ref.Number'),'r1')
        backend = self.context.backend
        connection = backend._read_handle.connection
        trace = []
        connection.set_trace_callback(trace.append)
        try:
            with patch.object(backend,'_validate_transaction_admission',
                              side_effect=AssertionError('full document admission')):
                for expression,result in wanted:
                    with self.subTest(expression=expression):
                        self.assertEqual(vm.execute(expression),result)
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(len(trace),len(wanted),trace)
        self.assertTrue(all(sql.startswith('SELECT') and 'document_part_' not in sql for sql in trace),trace)
        self.assertIn('EXISTS(SELECT 1 FROM main."catalog_',trace[3])
        self.assertIsNone(backend._active)
        self.assertFalse(connection.in_transaction)

    def test_selected_warehouse_keeps_live_reference_presence_validation(self):
        from yadinassi import BSLRuntimeError
        from yadinassi.db.sqlite.sqlite_document_layout import data_table
        from yadinassi.db.sqlite.sqlite_typed_rows import attribute_column
        key = self.seed()
        schema = self.vm._documents.get_index('Receipt')._schema
        field = next(field for field in schema.fields if field.name=='Warehouse')
        column = attribute_column(field)
        table = data_table(schema)
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute(f'UPDATE "{table}" SET "{column}"=? WHERE record_id=?',
                         (str(uuid4()),str(key.record_id)))
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('D.Ref.Warehouse')
        self.assertIsNone(self.context.backend._active)
        # Number still validates its header, but not a different attribute.
        self.assertEqual(self.vm.execute('D.Ref.Number'),'r1')
        with closing(sqlite3.connect(self.path)) as peer, peer:
            peer.execute(f'UPDATE "{table}" SET "{column}"=NULL WHERE record_id=?',
                         (str(key.record_id),))
        self.assertTrue(self.vm.execute('D.Ref.Warehouse.IsEmpty()'))

    def test_catalog_exact_description_detached_duplicate_and_owned_code(self):
        vm = self.vm
        vm.execute("""W=Catalogs.Склады.CreateItem();W.Code="abc";W.Description="Point";W.Write();""")
        backend = self.context.backend
        self.assertTrue(vm.execute('(Catalogs.Склады.FindByDescription("Point",True)=W.Ref)'))
        connection = backend._read_handle.connection
        trace = []
        connection.set_trace_callback(trace.append)
        try:
            self.assertTrue(vm.execute('Catalogs.Склады.FindByDescription("point",True).IsEmpty()'))
            self.assertTrue(vm.execute('(Catalogs.Склады.FindByCode("abc")=W.Ref)'))
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(len(trace),2,trace)
        self.assertTrue(all(sql.startswith('SELECT') and sql.endswith('LIMIT 2') for sql in trace),trace)
        vm.execute("""V=Catalogs.Склады.CreateItem();V.Code="def";V.Description="Point";V.Write();""")
        from yadinassi import BSLRuntimeError
        with self.assertRaises(BSLRuntimeError):
            vm.execute('Catalogs.Склады.FindByDescription("Point",True)')
        self.assertIsNone(backend._active)
        vm.execute("""BeginTransaction();X=Catalogs.Склады.CreateItem();X.Code="stu";X.Description="Staged";X.Write();
StagedCode=Not Catalogs.Склады.FindByCode("stu").IsEmpty();
Denied=False;Try R=Catalogs.Склады.FindByDescription("Staged",True);Except Denied=True;EndTry;
RollbackTransaction();""")
        self.assertTrue(vm.execute('StagedCode And Denied And Catalogs.Склады.FindByCode("stu").IsEmpty()'))

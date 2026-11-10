"""Owned SQLite document lifecycle; no native compatibility evidence claimed."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError, CatalogKey, CatalogSelection, CatalogScanRequest, TabularRow, TabularSectionRows
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.document_backend import DocumentDraft, DocumentKey, DocumentSelection
from yadinassi.document_types import BSLDocumentReference
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_documents import DocumentView
from test_document_configuration_xml import document_files


class SQLiteDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'application.sqlite'
        self.files = document_files()
        self.imported = import_configuration(self.files)
        self.context = SQLiteDBContext.create(self.path,self.imported)
        self.schema = self.imported.documents[0]
        self.lines = []
        self.vm = Interpreter(database_context=self.context,output=self.lines.append)
    def tearDown(self): self.context.close(); self.temp.cleanup()
    def execute(self,code):
        self.lines.clear(); self.vm.execute(code); return list(self.lines)
    def object(self):
        self.vm.execute('D=Documents.Orders.CreateDocument();D.Date=Date(2026,11,9,12,30,5);')
        return self.vm.execute('D')
    def sql(self,query,args=()):
        # The connection context manager ends the transaction, not the handle.
        with closing(sqlite3.connect(self.path)) as c, c:
            return c.execute(query,args).fetchall()
    def draft(self):
        s = self.schema
        values = ('hello',Decimal('12.50'),True,datetime(2026,11,9),CatalogKey(self.context.backend.database_id,s.fields[-1].target_catalog_id,uuid4()))
        return DocumentDraft(DocumentKey(self.context.backend.database_id,s.identity,uuid4()),'',datetime(2026,11,9),False,values,(),True)

    def test_sql_helper_closes_connections_after_success_and_error(self):
        real_connect = sqlite3.connect
        connections = []
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connections.append(connection)
            return connection
        try:
            with patch('test_sqlite_documents.sqlite3.connect', side_effect=connect):
                self.assertEqual(self.sql('SELECT 1'), [(1,)])
                self.assertEqual(self.sql('UPDATE document_sequence SET next_value=?', (2,)), [])
                self.assertEqual(self.sql('SELECT next_value FROM document_sequence'), [(2,)])
                with self.assertRaises(sqlite3.OperationalError):
                    self.sql('SELECT * FROM no_such_table')
            self.assertEqual(len(connections), 4)
            # Retain each handle so garbage collection cannot conceal a leak,
            # including on platforms that allow deleting an open database.
            for connection in connections:
                with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
                    connection.execute('SELECT 1')
        finally:
            for connection in connections:
                connection.close()

    def test_bsl_create_read_update_reopen_with_catalog_reference(self):
        result = self.execute('''C=Catalogs.Categories.CreateItem();C.Code="C";C.Description="Customer";C.Write();
D=Documents.Orders.CreateDocument();Message(D.IsNew());Message(D.Ref.IsEmpty());D.Date=Date(2026,11,9,12,30,5);
D.Text="original";D.Amount=12.345;D.Active=True;D.Stamp=Date(2024,2,29);D.Category=C.Ref;
R=D.Lines.Add();R.Flag=True;D.Write();Message(D.Number);Message(D.IsNew());Message(D.Posted);
O=Documents.Orders.FindByNumber(D.Number).GetObject();Message(O.Category.Description);Message(O.Amount);
Message(O.Lines.Get(0).Flag);O.Text="changed";O.DeletionMark=True;O.Write();Message(D.Ref.Text);''')
        self.assertEqual(result,['Да','Да','000000001','Нет','Нет','Customer','12,35','Да','changed'])
        self.context.close(); self.context = SQLiteDBContext(self.path)
        vm = Interpreter(database_context=self.context)
        self.assertEqual(vm.execute('Documents.Orders.FindByNumber("000000001").Text'),'changed')
        self.assertTrue(vm.execute('Documents.Orders.FindByNumber("000000001").DeletionMark'))
        self.assertEqual(self.context.backend.export_configuration(),self.files)

    def test_local_types_metadata_and_no_native_presentation_or_codec(self):
        self.assertEqual(self.execute('''D=Documents.Orders.CreateDocument();
Message(TypeOf(D)=Type("DocumentObject.Orders"));Message(TypeOf(D.Ref)=Type("ДокументСсылка.Orders"));
Message(TypeOf(Documents.Orders)=Type("DocumentManager.Orders"));
Message(TypeOf(D.Lines)=Type("DocumentTabularSection.Orders.Lines"));
R=D.Lines.Add();Message(TypeOf(R)=Type("DocumentTabularSectionRow.Orders.Lines"));
Message(D.Metadata().FullName());Message(Metadata.Documents.Count());'''),['Да']*5+['Документ.Orders','1'])
        for expression in ('String(D)','String(Type("DocumentObject.Orders"))',
                           'String(Type("DocumentTabularSection.Orders.Lines"))','ValueToStringInternal(D)','ValueToStringInternal(D.Ref)','ValueToStringInternal(Type("DocumentTabularSection.Orders.Lines"))',
                           'ValueToStringInternal(Type("DocumentTabularSectionRow.Orders.Lines"))','New("DocumentObject.Orders")'):
            with self.subTest(expression=expression),self.assertRaises(BSLRuntimeError): self.vm.execute(expression)

    def test_catalog_document_namespace_isolation_and_document_query(self):
        view = self.context.backend.begin_read()
        try:
            self.assertNotIn(self.schema.identity,{s.identity for s in view.catalogs()})
            for call in (lambda:view.catalog_schema(self.schema.identity),
                         lambda:view.read_catalog(CatalogKey(view.database_id,self.schema.identity,uuid4())),
                         lambda:view.select_catalog(self.schema.identity,CatalogSelection()),
                         lambda:view.scan_catalog(self.schema.identity,CatalogScanRequest())):
                with self.assertRaises(BackendError): call()
        finally: view.close()
        for code in ('Catalogs.Orders','Metadata.Catalogs.Orders','Type("CatalogRef.Orders")',
                     'Q=New Query("SELECT Ref FROM Catalog.Orders");Q.Execute();'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError): self.vm.execute(code)
        self.assertEqual(self.vm.execute('Q=New Query("SELECT Ref FROM Document.Orders");Q.Execute().IsEmpty();'), True)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM catalog_schema')[0][0],2)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_schema')[0][0],1)

    def test_document_only_database_and_old_catalog_format_unchanged(self):
        files = document_files(catalogs=False,fields=False)
        db = SQLiteDBContext.create(Path(self.temp.name)/'only.sqlite',import_configuration(files))
        try:
            vm = Interpreter(database_context=db)
            vm.execute('O=Documents.Orders.CreateDocument();O.Write();')
            self.assertEqual(vm.execute('O.Number'),'000000001')
            self.assertEqual(vm.execute('Metadata.Catalogs.Count()'),Decimal(0))
        finally: db.close()
        from sqlite_catalog_fixture import configuration_files
        db = SQLiteCatalogBackend.create(Path(self.temp.name)/'catalog.sqlite',import_configuration(configuration_files()))
        try:
            self.assertEqual(db.storage_version,2)
            self.assertFalse(db.capabilities().document_read)
            with self.assertRaises(BackendError): db.begin_document_read()
        finally: db.close()

    def test_no_implicit_creation_or_old_format_upgrade(self):
        missing = Path(self.temp.name)/'missing.sqlite'
        with self.assertRaises(BackendError): SQLiteCatalogBackend(missing)
        self.assertFalse(missing.exists())
        self.assertEqual(self.context.backend.storage_version,7)
        self.assertEqual(self.sql('PRAGMA user_version'),[(7,)])

    def test_readonly_document_reads_but_creation_and_write_rejected(self):
        obj = self.object(); obj.write()
        self.context.close(); self.context._backend = SQLiteCatalogBackend(self.path,read_only=True)
        self.vm = Interpreter(database_context=self.context)
        self.assertEqual(self.vm.execute('Documents.Orders.FindByNumber("000000001").Number'),'000000001')
        for code in ('Documents.Orders.CreateDocument()', 'O=Documents.Orders.FindByNumber("000000001").GetObject();O.Write();'):
            with self.assertRaises(BSLRuntimeError): self.vm.execute(code)
        with self.assertRaises(BackendError): self.context.backend.begin_document_write(uuid4())
        self.assertIsNone(self.context.backend._active)

    def test_stale_update_and_duplicate_number_preserve_buffers(self):
        result = self.execute('''D=Documents.Orders.CreateDocument();D.Write();A=D.Ref.GetObject();B=D.Ref.GetObject();
A.Text="first";A.Write();B.Text="stale";Try B.Write();Except Message("conflict");EndTry;
Message(B.Text);Message(D.Ref.Text);N=Documents.Orders.CreateDocument();N.Number=D.Number;
Try N.Write();Except Message("duplicate");EndTry;Message(N.IsNew());Message(N.Ref.IsEmpty());''')
        self.assertEqual(result,['conflict','stale','first','duplicate','Да','Да'])

    def test_sections_detach_iteration_indices_and_atomic_owner_write(self):
        result = self.execute('''D=Documents.Orders.CreateDocument();A=D.Lines.Add();A["Flag"]=True;B=D.Lines.Add();
Message(A.LineNumber);Message(B.LineNumber);N=0;For Each R In D.Lines Do N=N+1;EndDo;Message(N);
D.Lines.Delete(A);Message(B.LineNumber);Try Message(A.Flag);Except Message("detached");EndTry;
D.Write();O=D.Ref.GetObject();Message(O.Lines.Count());O.Lines.Clear();O.Write();Message(D.Ref.GetObject().Lines.Count());''')
        self.assertEqual(result,['1','2','2','1','detached','1','0'])

    def test_section_and_owner_changes_roll_back_together(self):
        obj = self.object(); obj.get_member('Lines').add().set_member('Flag',True); obj.write()
        before = self.sql('SELECT revision,values_json,sections_json FROM document_record')
        obj.set_member('Text','uncommitted');obj.get_member('Lines').clear()
        tx = self.context.backend.begin_document_write(uuid4())
        try:
            original = tx._preflight; calls = [0]
            def fail_after_write(schema):
                calls[0] += 1
                if calls[0] == 3: raise BackendError('storage_error')
                return original(schema)
            with patch.object(tx,'_preflight',side_effect=fail_after_write):
                with self.assertRaises(BackendError): tx.update(replace(self.draft(),key=obj._key,number=obj.get_member('Number'),values=('uncommitted',Decimal(0),False,datetime(1,1,1),obj._manager._stored(self.schema.fields[-1],obj.get_member('Category'))),tabular_sections=(),auto_number=False),obj._revision)
        finally: tx.rollback()
        self.assertEqual(self.sql('SELECT revision,values_json,sections_json FROM document_record'),before)
        tx = self.context.backend.begin_document_write(uuid4())
        try:
            card = tx.read_document(obj._key)
            draft = DocumentDraft(replace(card.key,record_id=uuid4()),'',card.date,False,card.values,(),True)
            with patch('yadinassi.sqlite_documents.DocumentWriteOutcome',side_effect=MemoryError),self.assertRaises(MemoryError): tx.create(draft)
            self.assertIsNone(tx.read_document(draft.key))
            tx.create(replace(draft,key=replace(draft.key,record_id=uuid4())))
            outcome = tx.commit()
            self.assertEqual(outcome.number,'000000002')
        finally: tx.close()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(2,)])

    def test_uncertain_committed_response_resolves_without_replay(self):
        from test_catalog_commit_cleanup_recovery import FaultConnection
        faults = ({'commit_fault':'after'}, {'close_fault':'after','close_count':1},
                  {'close_fault':'before','close_count':100}, {'commit_fault':'interrupt'},
                  {'commit_fault':'memory'})
        for index,fault in enumerate(faults,1):
            with self.subTest(fault=fault):
                obj = self.object(); section = obj.get_member('Lines')
                section.add().set_member('Flag',True)
                backend = self.context.backend; original = backend.begin_document_write
                captured = []
                def begin(operation):
                    tx = original(operation)
                    tx._view._connection = FaultConnection(tx._view._connection,**fault)
                    captured.append(tx)
                    return tx
                expected = (KeyboardInterrupt if fault.get('commit_fault') == 'interrupt' else
                            MemoryError if fault.get('commit_fault') == 'memory' else BackendError)
                with patch.object(backend,'begin_document_write',side_effect=begin),self.assertRaises(expected): obj.write()
                self.assertTrue(obj.is_new())
                with self.assertRaises(BackendError): obj.set_member('Text','different')
                with self.assertRaises(BackendError): section.add()
                if fault.get('close_count') == 100:
                    self.assertIs(backend._active,captured[0]._view)
                    with self.assertRaisesRegex(BackendError,'closed'): captured[0].documents()
                    with self.assertRaisesRegex(BackendError,'busy'): backend.begin_document_read()
                    captured[0]._view._connection.close_count = 0
                    captured[0].close()
                self.assertIsNone(backend._active)
                with patch.object(DocumentView,'commit',side_effect=AssertionError('must not replay')): obj.write()
                self.assertFalse(obj.is_new()); self.assertEqual(obj.get_member('Number'),str(index).zfill(9))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(len(faults),)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_commit_receipt'),[(len(faults),)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM commit_receipt'),[(0,)])

    def test_uncertain_uncommitted_response_retries_same_frozen_intent(self):
        obj = self.object()
        def fail_before_commit(tx): tx.close(); raise BackendError('uncertain_commit')
        with patch.object(DocumentView,'commit',fail_before_commit),self.assertRaises(BackendError): obj.write()
        self.assertTrue(obj.is_new());self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(0,)])
        obj.write();self.assertEqual(obj.get_member('Number'),'000000001')

    def test_explicit_number_collision_skipped_and_rollback_does_not_consume(self):
        self.execute('D=Documents.Orders.CreateDocument();D.Number="000000001";D.Write();N=Documents.Orders.CreateDocument();N.Write();')
        self.assertEqual(self.vm.execute('N.Number'),'000000002')
        obj = self.object()
        with patch.object(DocumentView,'commit',new=lambda tx:(tx.close(),(_ for _ in ()).throw(BackendError('uncertain_commit')))[1]),self.assertRaises(BackendError): obj.write()
        self.assertEqual(self.sql('SELECT next_value FROM document_sequence'),[(3,)])
        obj.write();self.assertEqual(obj.get_member('Number'),'000000003')

    def test_select_order_bounds_snapshot_and_get_object(self):
        self.execute('A=Documents.Orders.CreateDocument();A.Date=Date(2026,11,10);A.Write();B=Documents.Orders.CreateDocument();B.Date=Date(2026,11,9);B.Write();S=Documents.Orders.Select();B.Text="later";B.Write();')
        self.assertEqual(self.execute('While S.Next() Do Message(S.Number);Message(S.GetObject().Text);EndDo;Message(S.Next());'),['000000002','','000000001','','Нет'])
        self.assertEqual(self.execute('S=Документы.Orders.Выбрать(Дата(2026,11,10),Дата(2026,11,10));While S.Следующий() Do Message(S.Номер);EndDo;'),['000000001'])
        view = self.context.backend.begin_document_read()
        try:
            with self.assertRaises(BackendError): view.select_documents(self.schema.identity,DocumentSelection(limit=1))
        finally: view.close()

    def test_find_missing_empty_and_custom_reference_identity(self):
        self.assertTrue(self.vm.execute('Documents.Orders.FindByNumber("absent").IsEmpty()'))
        self.assertEqual(self.vm.execute('Documents.Orders.EmptyRef().Date').ticks,0)
        self.assertIsNone(self.vm.execute('Documents.Orders.EmptyRef().GetObject()'))
        identity = str(uuid4())
        self.execute(f'R=Documents.Orders.GetRef(New UUID("{identity}"));D=Documents.Orders.CreateDocument();D.SetNewObjectRef(R);D.Write();')
        self.assertEqual(str(self.vm.execute('D.Ref.UUID()')),identity)
        self.assertEqual(self.vm.execute('D.Ref'),self.vm.execute('R'))

    def test_snapshot_type_and_cross_snapshot_reference_isolation(self):
        first = self.vm.execute('Documents.Orders.EmptyRef()')
        other = Interpreter(database_context=self.context)
        second = other.execute('Documents.Orders.EmptyRef()')
        self.assertNotEqual(first,second)
        with self.assertRaises(TypeError): self.object().set_new_object_ref(second)
        other.execute('C=Catalogs.Categories.CreateItem();C.Code="C";C.Write();')
        with self.assertRaises(TypeError): self.object().set_member('Category',other.execute('C.Ref'))

    def test_posting_and_unsupported_document_refs_are_explicit(self):
        self.object()
        for code in ('D.Posted=True','D.Write(True)','D.Post()','D.RegisterRecords','D.Category=D.Ref'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError): self.vm.execute(code)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(0,)])

    def test_closed_database_and_busy_document_view_cleanup(self):
        view = self.context.backend.begin_document_read()
        try:
            with self.assertRaises(BackendError): self.context.backend.begin_read()
            with self.assertRaises(BackendError): self.context.backend.begin_document_write(uuid4())
        finally: view.close()
        self.assertIsNone(self.context.backend._active)
        self.context.close()
        with self.assertRaises(BackendError): view.documents()
        with self.assertRaises(BackendError): self.context.backend.begin_document_read()

    def test_document_metadata_row_changes_rejected_without_schema_version_change(self):
        old = self.sql('PRAGMA schema_version')
        self.sql('UPDATE document_schema SET name=?',('Changed',))
        self.assertEqual(self.sql('PRAGMA schema_version'),old)
        with self.assertRaises(BackendError): self.context.backend.begin_document_read()
        self.assertIsNone(self.context.backend._active)

    def test_unexpected_ddl_or_document_registry_corruption_rejected(self):
        self.context.close();self.sql('CREATE TABLE unexpected(value TEXT)')
        with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)

    def test_invalid_persisted_scalar_and_sections_never_coerced(self):
        obj = self.object(); obj.write()
        original = self.sql('SELECT values_json,sections_json FROM document_record')[0]
        for assignment in ("values_json='[]'","sections_json='[]'","date='20260230000000'","number=''", "values_json='[null]'"):
            self.sql('UPDATE document_record SET '+assignment)
            with self.assertRaises(BackendError): obj._manager._read(obj._key.record_id)
            self.sql('UPDATE document_record SET values_json=?,sections_json=?,date=?,number=?',(*original,'20261109123005','000000001'))

    def test_reference_existence_and_foreign_database_rejected(self):
        draft = self.draft();tx = self.context.backend.begin_document_write(uuid4())
        try:
            with self.assertRaises(BackendError): tx.create(draft)
        finally: tx.close()
        draft = replace(draft,key=replace(draft.key,database_id=uuid4()))
        tx = self.context.backend.begin_document_write(uuid4())
        try:
            with self.assertRaises(BackendError): tx.create(draft)
        finally: tx.close()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(0,)])

    def test_normalized_numbers_and_scalar_qualifiers_apply_before_unique_check(self):
        self.assertEqual(self.execute('D=Documents.Orders.CreateDocument();D.Number="123456789suffix";D.Text="1234567890123456789012345678901234567890";D.Amount=12.345;D.Write();Message(D.Number);Message(D.Text);Message(D.Amount);'),['123456789','12345678901234567890123456789012','12,35'])
        self.assertEqual(self.vm.execute('D.Ref.Amount'),Decimal('12.35'))

    def test_persisted_receipt_mismatch_never_replayed(self):
        obj = self.object();original = DocumentView.commit
        with patch.object(DocumentView,'commit',new=lambda tx:(original(tx),(_ for _ in ()).throw(BackendError('uncertain_commit')))[1]),self.assertRaises(BackendError):obj.write()
        self.sql('UPDATE document_commit_receipt SET number=?',('000000002',))
        with self.assertRaises(BackendError): obj.write()
        self.sql('UPDATE document_commit_receipt SET number=?,request_hash=?',('000000001','0'*64))
        with self.assertRaises(BackendError):obj.write()
        self.assertTrue(obj.is_new());self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(1,)])

    def test_number_exhaustion_leaves_new_object_and_no_changes(self):
        self.sql('UPDATE document_sequence SET next_value=?',(10**9,))
        obj = self.object()
        with self.assertRaises(BackendError): obj.write()
        self.assertTrue(obj.is_new());self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(0,)])

    def test_backend_sections_none_preserves_and_empty_tuple_replaces(self):
        obj = self.object();obj.get_member('Lines').add().set_member('Flag',True);obj.write()
        view = self.context.backend.begin_document_read()
        try: card = view.read_document(obj._key)
        finally:view.close()
        draft = DocumentDraft(card.key,card.number,card.date,True,card.values,None)
        tx = self.context.backend.begin_document_write(uuid4())
        try:tx.update(draft,card.revision);outcome=tx.commit()
        finally:tx.close()
        self.assertEqual(obj._manager._read(obj._key.record_id).tabular_sections,card.tabular_sections)
        tx = self.context.backend.begin_document_write(uuid4())
        try:tx.update(replace(draft,tabular_sections=()),outcome.revision);tx.commit()
        finally:tx.close()
        self.assertEqual(obj._manager._read(obj._key.record_id).tabular_sections[0].rows,())

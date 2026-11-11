"""Bounded source-bound BSL posting, native14 observations and owner fences."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import current, execution, begin, rollback
from yadinassi.configuration_posting import import_posting_configuration, PROFILE
from yadinassi.document_posting import PostingLimitError
from yadinassi.document_posting_values import DocumentWriteMode
from test_configuration_posting import wrap

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'Documents/OwnedPostingDoc/Ext/ObjectModule.bsl'


def posting_source(module=None):
    root = ROOT/'scripts/document_posting_behavior'
    return {
        'Configuration.xml':wrap('Configuration',100,'<Name>PostingRuntime</Name>',
            '<Document>OwnedPostingDoc</Document><InformationRegister>OwnedPostingRows</InformationRegister>'),
        'Documents/OwnedPostingDoc.xml':(root/'Document.xml').read_bytes(),
        'InformationRegisters/OwnedPostingRows.xml':(root/'InformationRegister.xml').read_bytes(),
        MODULE:(root/'ObjectModule.bsl').read_bytes() if module is None else module.encode(),
    }


class PostingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self._counter = 0
        self.make()
    def make(self,module=None):
        self._counter += 1
        self.path = Path(self.temp.name)/('posting%d.sqlite'%self._counter)
        self.config = import_posting_configuration(posting_source(module),posting_runtime=PROFILE)
        self.context = SQLiteDBContext.create_posting(self.path,self.config)
        self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.lines = []
        self.vm = Interpreter(database_context=self.context,output=self.lines.append)
        self.addCleanup(self.vm.close)
    def new(self,number=3,mode=None):
        mode = number if mode is None else mode
        self.vm.execute('O=Documents.OwnedPostingDoc.CreateDocument();O.Number="%s";O.Date=Date(2024,1,1);O.AdditionalProperties.Insert("Trace","");O.AdditionalProperties.Insert("Mode",%s);'%(number,mode))
        return self.vm.execute('O')
    def rows(self,obj):
        return self.backend.read_recorder(self.config.registers[0].identity,obj._key).rows
    def trace(self,obj): return obj.get_member('AdditionalProperties').get_member('Trace')
    def sql(self,statement):
        with closing(sqlite3.connect(self.path)) as connection: return connection.execute(statement).fetchall()
    def post(self): self.vm.execute('O.Write(DocumentWriteMode.Posting);')

    def test_native_handler_and_observation_binding(self):
        source=posting_source()[MODULE]
        self.assertEqual(sha256(source).hexdigest(),'5aa22423943c61f4da3ab3bf5f660035aa3652a0748776e9720bd9d1c25b3270')
        self.assertEqual(len(json.loads((ROOT/'tests/fixtures/document_posting/observations.out').read_text())),14)

    def test_fourteen_measured_outcomes(self):
        observed=[]
        for case in range(1,15):
            obj=self.new(case); failed=False; cancel_trace=''
            if case in (4,5,6,7):
                self.vm.execute('O.AdditionalProperties.Insert("Mode",3);O.Write(DocumentWriteMode.Posting);'
                    'O.AdditionalProperties.Insert("Mode",%s);O.AdditionalProperties.Insert("Trace","");'%case)
            command=('O.Write(DocumentWriteMode.Write);' if case in (1,7) else
                'O.Write(DocumentWriteMode.UndoPosting);' if case==6 else 'O.Write(DocumentWriteMode.Posting);')
            if case==12: command='BeginTransaction();'+command+'RollbackTransaction();'
            try:self.vm.execute(command)
            except (BSLRuntimeError,BackendError):failed=True
            if case==10:
                cancel_trace=self.trace(obj)
                self.vm.execute('O.Number="101";O.AdditionalProperties.Insert("Trace","");')
                try:self.post()
                except (BSLRuntimeError,BackendError):failed=True
            posted=self.backend.read_document_posted(obj._key)
            rows=self.rows(obj)
            total=sum((row.values[1] for row in rows),Decimal(0))
            observed.append('%d|%s|%d,%s|%s%s'%(failed,'missing' if posted is None else int(posted),len(rows),total,cancel_trace,self.trace(obj)))
        self.assertEqual(observed,json.loads((ROOT/'tests/fixtures/document_posting/observations.out').read_text()))

    def test_two_documents_use_indexed_acceptance_among_internal_outcomes(self):
        a=self.new(3);b=self.new(14)
        self.vm.variables['a']=a;self.vm.variables['b']=b
        self.vm.execute('BeginTransaction();A.Write(DocumentWriteMode.Posting);B.Write(DocumentWriteMode.Posting);CommitTransaction();')
        self.assertFalse(a.is_new());self.assertFalse(b.is_new())
        self.assertEqual(len(self.rows(a)),2);self.assertEqual(len(self.rows(b)),1)
        self.assertTrue(self.backend.read_document_posted(a._key));self.assertTrue(self.backend.read_document_posted(b._key))

    def test_caught_handler_failure_preserves_earlier_outer_write(self):
        a=self.new(3);b=self.new(11);self.vm.variables['a']=a;self.vm.variables['b']=b
        self.vm.execute('BeginTransaction();A.Write(DocumentWriteMode.Posting);Try B.Write(DocumentWriteMode.Posting);Except EndTry;CommitTransaction();')
        self.assertFalse(a.is_new());self.assertTrue(b.is_new());self.assertEqual(self.rows(b),())
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(1,)])
        self.assertEqual(self.sql('SELECT count(*) FROM recorder_movement_receipt'),[(1,)])

    def test_outer_rollback_restores_posted_and_unlocks_document(self):
        obj=self.new(3)
        self.vm.execute('BeginTransaction();O.Write(DocumentWriteMode.Posting);RollbackTransaction();')
        self.assertTrue(obj.is_new());self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.rows(obj),())
        self.assertEqual(self.vm.execute('O.RegisterRecords.OwnedPostingRows.Count();'),Decimal(2))
        self.vm.execute('O.RegisterRecords.OwnedPostingRows.Clear();O.Number="4";O.Write();')
        self.assertFalse(obj.is_new())

    def test_multiple_explicit_writes_have_distinct_root_children(self):
        obj=self.new(9);self.post()
        self.assertEqual(self.rows(obj)[0].values[1],Decimal(88))
        self.assertEqual(self.sql('SELECT count(DISTINCT operation_id) FROM recorder_movement_receipt'),[(2,)])
        self.assertEqual(self.sql('SELECT count(*) FROM unit_of_work_receipt'),[(1,)])

    def test_movement_write_property_and_method_are_distinct(self):
        obj=self.new(3)
        self.assertIs(self.vm.execute('O.RegisterRecords.OwnedPostingRows.Write;'),False)
        self.post()
        self.assertIs(self.vm.execute('O.RegisterRecords.OwnedPostingRows.Write;'),True)
        self.assertEqual(len(self.rows(obj)),2)

    def test_detached_movement_write_never_commits(self):
        self.new(3)
        with self.assertRaises(BSLRuntimeError):self.vm.execute('O.RegisterRecords.OwnedPostingRows.Write();')
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_stale_document_conflict_rolls_back_full_operation(self):
        self.new(3);self.post()
        self.vm.execute('A=O.Ref.GetObject();B=O.Ref.GetObject();A.AdditionalProperties.Insert("Trace","");B.AdditionalProperties.Insert("Trace","");A.Write();')
        with self.assertRaises(BSLRuntimeError):self.vm.execute('B.Write(DocumentWriteMode.Posting);')
        self.assertEqual(self.sql('SELECT revision FROM document_record'),[(2,)])
        self.assertEqual(self.sql('SELECT count(*) FROM unit_of_work_receipt'),[(2,)])

    def assert_handler_control_denied(self,command):
        self.make('Procedure Posting(Cancel,Mode) '+command+' EndProcedure')
        obj=self.new(3)
        with self.assertRaises(BSLRuntimeError):self.post()
        self.assertTrue(obj.is_new());self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])
        self.vm.execute('BeginTransaction();RollbackTransaction();')
    def test_handler_cannot_begin(self):self.assert_handler_control_denied('BeginTransaction();')
    def test_handler_cannot_commit(self):self.assert_handler_control_denied('CommitTransaction();')
    def test_handler_cannot_rollback(self):self.assert_handler_control_denied('RollbackTransaction();')
    def test_handler_helper_cannot_commit(self):
        self.make('Procedure CommitHelper() CommitTransaction(); EndProcedure Procedure Posting(Cancel,Mode) CommitHelper(); EndProcedure')
        self.new(3)
        with self.assertRaises(BSLRuntimeError):self.post()
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_parent_host_commit_registration_is_not_inherited(self):
        self.make('Procedure Posting(Cancel,Mode) HostCommit(); EndProcedure')
        self.vm.register_function('HostCommit',self.vm._commit_transaction)
        self.new(3)
        with self.assertRaises(BSLRuntimeError):self.post()
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_parent_bound_commit_callback_keeps_handler_origin_denied(self):
        self.make('Procedure Posting(Cancel,Mode) Message("attempt"); EndProcedure')
        self.vm.output=lambda text:self.vm._commit_transaction()
        self.new(3)
        with self.assertRaises(BSLRuntimeError):self.post()
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])
        self.vm.execute('BeginTransaction();RollbackTransaction();')

    def test_captured_handler_control_cannot_gain_later_parent_authority(self):
        self.make('''Procedure Posting(Cancel,Mode)
AdditionalProperties.Insert("Commit",CommitTransaction);
AdditionalProperties.Insert("Rollback",RollbackTransaction);
EndProcedure''')
        self.new(3);self.post()
        self.vm.execute('''BeginTransaction();
Try O.AdditionalProperties.Commit(); Except CommitBlocked=True; EndTry;
Try O.AdditionalProperties.Rollback(); Except RollbackBlocked=True; EndTry;
RollbackTransaction();''')
        self.assertTrue(self.vm.execute('CommitBlocked'))
        self.assertTrue(self.vm.execute('RollbackBlocked'))

    def test_caught_forbidden_control_does_not_change_owner(self):
        self.make('Procedure Posting(Cancel,Mode) Try CommitTransaction(); Except EndTry; EndProcedure')
        obj=self.new(3);self.post();self.assertFalse(obj.is_new())
        self.vm.execute('BeginTransaction();RollbackTransaction();')
        self.assertEqual(self.vm.execution_context,'client')

    def test_handler_queries_types_and_temp_tables_share_owner_snapshot(self):
        self.make('''Procedure Posting(Cancel,Mode)
If TypeOf(ThisObject) <> Type("DocumentObject.OwnedPostingDoc") Then Raise "type snapshot"; EndIf;
Q=New Query("SELECT Number FROM Document.OwnedPostingDoc");
Q.TempTablesManager=New TempTablesManager;T=Q.Execute().Unload();
If T.Count()<>1 Then Raise "transaction query"; EndIf;
EndProcedure''')
        self.new(3);self.post()
        self.assertEqual(self.vm.execution_context,'client')

    def test_nested_document_write_is_not_an_authority_grant(self):
        self.make('Procedure Posting(Cancel,Mode) D=Documents.OwnedPostingDoc.CreateDocument();D.Number="nested";D.Write(); EndProcedure')
        self.new(3)
        with self.assertRaises(BSLRuntimeError):self.post()
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_source_preflight_rejects_initializer_before_any_write(self):
        self.make('Message("initializer"); Procedure Posting(Cancel,Mode) EndProcedure')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.new(3)
        self.assertEqual(self.lines,[]);self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_source_preflight_rejects_by_value_cancel(self):
        self.make('Procedure Posting(Val Cancel,Mode) EndProcedure')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.new(3)
        self.assertEqual(self.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_cancel_must_remain_boolean(self):
        self.make('Procedure OnWrite(Cancel) Cancel=1; EndProcedure')
        obj=self.new(3)
        with self.assertRaises(BSLRuntimeError):self.post()
        self.assertTrue(obj.is_new());self.assertEqual(self.rows(obj),())

    def test_budget_failure_cannot_be_caught_and_leaves_no_rows(self):
        self.make('Procedure Posting(Cancel,Mode) Try While True Do EndDo; Except EndTry; EndProcedure')
        obj=self.new(3)
        with patch('yadinassi.document_posting.MAX_STEPS',50):
            with self.assertRaises(PostingLimitError):self.post()
        self.assertTrue(obj.is_new());self.assertEqual(self.rows(obj),())
        self.vm.execute('BeginTransaction();RollbackTransaction();')

    def test_reopen_reads_posted_in_document_snapshot(self):
        obj=self.new(3);self.post()
        card=obj._manager._read(obj._key.record_id)
        with self.assertRaises(BackendError):obj._manager._fields(replace(card,posted='not Boolean'))
        self.context.close()
        context=SQLiteDBContext(self.path);self.addCleanup(context.close)
        vm=Interpreter(database_context=context)
        self.assertTrue(vm.execute('Documents.OwnedPostingDoc.FindByNumber("3").Posted'))
        self.assertTrue(vm.execute('D=Documents.OwnedPostingDoc.FindByNumber("3").GetObject();D.Posted'))
        self.assertEqual(vm.execute('S=Documents.OwnedPostingDoc.Select();S.Next();S.Posted'),True)

    def test_ordinary_write_on_posted_object_preserves_movements(self):
        obj=self.new(3);self.post();before=self.rows(obj)
        self.vm.execute('O.RegisterRecords.OwnedPostingRows.Clear();O.Write();')
        self.assertEqual(self.rows(obj),before);self.assertTrue(obj.get_member('Posted'))

    def test_unpost_clears_persistence_not_same_object_buffer(self):
        obj=self.new(3);self.post();self.vm.execute('O.Write(DocumentWriteMode.UndoPosting);')
        self.assertFalse(obj.get_member('Posted'));self.assertEqual(self.rows(obj),())
        self.assertEqual(self.vm.execute('O.RegisterRecords.OwnedPostingRows.Count()'),Decimal(2))

    def test_invalid_write_mode_cannot_open_transaction(self):
        self.new(3)
        with patch.object(self.backend,'begin_unit_of_work',wraps=self.backend.begin_unit_of_work) as begin_call:
            with self.assertRaises(BSLRuntimeError):self.vm.execute('O.Write("Posting");')
            begin_call.assert_not_called()

    def test_movement_rows_are_bounded_before_buffer_growth(self):
        self.new(3)
        with patch('yadinassi.document_posting_values.MAX_MOVEMENT_ROWS',1):
            self.vm.execute('O.RegisterRecords.OwnedPostingRows.Add();')
            with self.assertRaises(BSLRuntimeError):self.vm.execute('O.RegisterRecords.OwnedPostingRows.Add();')
        self.assertEqual(self.vm.execute('O.RegisterRecords.OwnedPostingRows.Count()'),Decimal(1))

    def test_movement_bytes_are_bounded_before_buffer_growth(self):
        self.new(3)
        with patch('yadinassi.document_posting_values.MAX_BUFFER_BYTES',1):
            with self.assertRaises(BSLRuntimeError):self.vm.execute('O.RegisterRecords.OwnedPostingRows.Add();')
        self.assertEqual(self.vm.execute('O.RegisterRecords.OwnedPostingRows.Count()'),Decimal(0))

    def test_cleared_movement_row_is_detached(self):
        self.new(3)
        self.vm.execute('R=O.RegisterRecords.OwnedPostingRows.Add();O.RegisterRecords.OwnedPostingRows.Clear();')
        with self.assertRaises(BSLRuntimeError):self.vm.execute('R.Amount=4;')

    def test_root_receipt_resolution_never_reexecutes_handlers(self):
        obj=self.new(9)
        with execution(self.backend):
            begin(self.backend)
            obj.write(DocumentWriteMode.POSTING)
            tx=current(self.backend);op=tx.unit.operation_id;requests=tx.unit.requests
            trace=self.trace(obj);tx.commit()
        resolved=self.backend.resolve_unit_of_work(op,requests)
        self.assertEqual(len(resolved),4);self.assertEqual(self.trace(obj),trace)
        self.assertEqual(self.rows(obj)[0].values[1],Decimal(88))

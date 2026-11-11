"""Public BSL Query integration, including the unchanged native14 observer."""
import json
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.configuration_posting import import_posting_configuration,PROFILE
from yadinassi.database_context import SQLiteDBContext
from test_document_posting_runtime import posting_source,ROOT


class PostingQueryRuntimeTests(unittest.TestCase):
    def make(self,module=None):
        temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(temp.cleanup)
        config=import_posting_configuration(posting_source(module),posting_runtime=PROFILE)
        context=SQLiteDBContext.create_posting(Path(temp.name)/'query.sqlite',config)
        self.addCleanup(context.close)
        vm=Interpreter(database_context=context,output=lambda line:None);self.addCleanup(vm.close)
        return vm,context

    def test_unchanged_native14_observer_uses_public_query(self):
        vm,context=self.make();observed=[];diagnostics=[]
        # Native diagnostic formatting is test instrumentation, not a posting API.
        vm.register_function('ПодробноеПредставлениеОшибки',lambda info:info.get_member('Description'))
        vm.register_function('PostingEmit',lambda number,value:observed.append((int(number),value)),returns_value=False)
        vm.register_function('PostingDiagnostic',lambda number,stage,error:diagnostics.append((int(number),stage,error)),returns_value=False)
        source=ROOT/'scripts/document_posting_behavior/observe.bsl'
        vm.execute(source.read_text(),str(source))
        self.assertEqual([number for number,_ in observed],list(range(1,15)))
        self.assertEqual([value for _,value in observed],json.loads((ROOT/'tests/fixtures/document_posting/observations.out').read_text()))
        self.assertEqual([(number,stage) for number,stage,_ in diagnostics],[(10,'write'),(10,'write'),(11,'write'),(13,'write')])
        self.assertEqual([error for _,_,error in diagnostics[:3]],
                         ['document write cancelled','document write cancelled','owned posting cancellation'])
        self.assertEqual(diagnostics[3][2],'storage_error')

    def test_query_sees_each_explicit_replacement_before_commit(self):
        vm,context=self.make('''Procedure Posting(Cancel,Mode)
Set=RegisterRecords.OwnedPostingRows;
Row=Set.Add();Row.Key=1;Row.Amount=5;Set.Write();
Q=New Query("SELECT SUM(R.Amount) AS Total FROM InformationRegister.OwnedPostingRows AS R");
S=Q.Execute().Select();S.Next();AdditionalProperties.Insert("First",S.Total);
Set.Clear();Row=Set.Add();Row.Key=2;Row.Amount=9;Set.Write();
S=Q.Execute().Select();S.Next();AdditionalProperties.Insert("Second",S.Total);
EndProcedure''')
        vm.execute('O=Documents.OwnedPostingDoc.CreateDocument();O.Number="1";O.Write(DocumentWriteMode.Posting);')
        self.assertEqual(vm.execute('O.AdditionalProperties.First'),Decimal(5))
        self.assertEqual(vm.execute('O.AdditionalProperties.Second'),Decimal(9))
        self.assertEqual(vm.execute('Q=New Query("SELECT SUM(Amount) AS Total FROM InformationRegister.OwnedPostingRows");S=Q.Execute().Select();S.Next();S.Total'),Decimal(9))

    def test_explicit_outer_query_reads_staged_posted_and_rolls_back(self):
        vm,context=self.make()
        vm.execute('''O=Documents.OwnedPostingDoc.CreateDocument();O.Number="3";O.AdditionalProperties.Insert("Trace","");O.AdditionalProperties.Insert("Mode",3);
BeginTransaction();O.Write(DocumentWriteMode.Posting);
Q=New Query("SELECT Posted FROM Document.OwnedPostingDoc");S=Q.Execute().Select();S.Next();WasPosted=S.Posted;
Q=New Query("SELECT COUNT(*) AS N FROM InformationRegister.OwnedPostingRows");S=Q.Execute().Select();S.Next();WasCount=S.N;
RollbackTransaction();''')
        self.assertTrue(vm.execute('WasPosted'));self.assertEqual(vm.execute('WasCount'),Decimal(2))
        self.assertTrue(vm.execute('Q=New Query("SELECT Ref FROM Document.OwnedPostingDoc");Q.Execute().IsEmpty()'))
        self.assertTrue(vm.execute('Q=New Query("SELECT Key FROM InformationRegister.OwnedPostingRows");Q.Execute().IsEmpty()'))

    def test_recorder_reference_projection_retains_document_snapshot_type(self):
        vm,context=self.make()
        vm.execute('O=Documents.OwnedPostingDoc.CreateDocument();O.Number="3";O.AdditionalProperties.Insert("Trace","");O.AdditionalProperties.Insert("Mode",3);O.Write(DocumentWriteMode.Posting);')
        self.assertTrue(vm.execute('''Q=New Query("SELECT Recorder FROM InformationRegister.OwnedPostingRows");
S=Q.Execute().Select();S.Next();S.Recorder=O.Ref'''))
        self.assertTrue(vm.execute('TypeOf(S.Recorder)=Type("DocumentRef.OwnedPostingDoc")'))

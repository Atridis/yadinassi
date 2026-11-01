"""Synthetic logical adapter regressions, not native storage evidence."""
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import UUID
import unittest
from yadinassi import Interpreter
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.storage.config_document_metadata import DocumentConfigSnapshot
from yadinassi.documents import BSLDocumentSelection

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
U='33333333-3333-4333-8333-333333333333'
V='44444444-4444-4444-8444-444444444444'

class DocumentScenarioTests(unittest.TestCase):
    def runtime(self, filled=True):
        identity=NS(name='Orders',metadata_uuid=A,sections=())
        snapshot=DocumentConfigSnapshot(((A,identity,()),),((B,NS(name='Categories'),()),))
        def row(uid,number,date,posted):
            values={'_NUMBER':number,'_DATE_TIME':date,'_POSTED':posted,'_MARKED':False}
            return NS(reference_uuid=UUID(uid),physical_record=NS(fields=tuple(
                NS(declaration=NS(name=k),value=v) for k,v in values.items())))
        rows=(row(U,'30',datetime(2024,2,29,12,34,56),True),row(V,'20',datetime(2001,1,1),False)) if filled else ()
        result=NS(identity=identity,config_snapshot=snapshot,binding=NS(attributes=()),rows=rows)
        context=Mock();context.document_metadata.return_value=snapshot;context.document_rows.return_value=result
        output=[];vm=Interpreter(output.append,database_context=context)
        self.addCleanup(vm.close)
        return vm,context,output,result

    def test_identity_namespace_and_closed_consumers(self):
        vm,context,out,_=self.runtime()
        vm.execute('''M=Documents.Orders; R=M.GetRef(New UUID("33333333-3333-4333-8333-333333333333"));
Message(TypeOf(R)=Type("DocumentRef.Orders"));
Message(TypeOf(M)=Type("DocumentManager.Orders"));
Message(TypeOf(TypeOf(R))=Type("Type"));
Message(R.Metadata()=Metadata.Documents.Orders);
Message(R=Catalogs.Categories.GetRef(R.UUID()));
Message(ValueIsFilled(R)); Message(ValueIsFilled(M.EmptyRef()));
Message(String(TypeOf(Documents)));''')
        self.assertEqual(out,['Да','Да','Да','Да','Нет','Да','Нет','Документы менеджер'])
        context.document_rows.assert_not_called();context.catalog_metadata.assert_not_called()
        for code in ('ValueToStringInternal(R);','T=New Array; T.Add(TypeOf(R)); New TypeDescription(T);',
                     'New (TypeOf(R));','Documents.Orders=M;'):
            with self.subTest(code=code),self.assertRaises(Exception):vm.execute(code)

    def test_document_types_and_refs_are_immutable_scoped_and_codec_closed(self):
        from dataclasses import FrozenInstanceError
        from yadinassi.type_values import type_of
        from yadinassi.serialization import value_to_string_internal
        vm,_,_,_=self.runtime()
        manager=vm._documents.get_index('Orders');ref=manager.get_ref()
        other,_,_,_=self.runtime()
        self.assertNotEqual(type_of(ref),type_of(other._documents.get_index('Orders').empty_ref()))
        for value in (ref,type_of(ref),manager,manager.select(),vm._documents):
            with self.assertRaises((ValueError,TypeError)):value_to_string_internal(value)
        with self.assertRaises(FrozenInstanceError):ref.reference_uuid=UUID(U)
        with self.assertRaises(FrozenInstanceError):ref.value_type.name='Other'

    def test_chronology_posted_lookup_range_and_terminal_cursor(self):
        vm,_,out,_=self.runtime()
        vm.execute('''M=Documents.Orders; S=M.Select(); Message(S.Number=Undefined);
While S.Next() Do Message(S.Number); Message(S.Posted); EndDo;
Message(S.Next()); Message(S.Next()); Message(S.Number);
Message(M.FindByNumber("30",Date(2024,2,29)).Posted);
Message(M.FindByNumber("missing").IsEmpty());
S=M.Select(Date(2024,2,29,12,34,56),Date(2024,2,29,12,34,56));
Message(S.Next()); Message(S.Number); Message(S.Next());''')
        self.assertEqual(out,['Да','20','Нет','30','Да','Нет','Нет','30','Да','Да','Да','30','Нет'])

    def test_empty_defaults_missing_reference_and_no_reset(self):
        vm,_,out,_=self.runtime(False)
        vm.execute('''M=Documents.Orders; R=M.EmptyRef();
Message(R.Number); Message(XMLString(R.Date)); Message(R.Posted);
S=M.Select(); Message(S.Next()); Message(S.Next()); Message(S.Number=Undefined);''')
        self.assertEqual(out,['','0001-01-01T00:00:00','Нет','Нет','Нет','Да'])
        for code in ('S.Reset();','M.Metadata();','M.CreateDocument();','M.GetRef("bad");'):
            with self.subTest(code=code),self.assertRaises(Exception):vm.execute(code)

    def test_lookup_refuses_unmeasured_ci_and_normalization(self):
        vm,_,_,result=self.runtime();manager=vm._documents.get_index('Orders')
        for value in (' 30','30 ','３０','123456789','A-B'):
            with self.assertRaises(ValueError):manager.find_by_number(value)
        result.rows[0].physical_record.fields[0].value='Ab'
        self.assertEqual(manager.get_ref(BSLUUID(U)).get_member('Number'),'Ab')
        with self.assertRaises(ValueError):manager.find_by_number('ab')

    def test_duplicate_dates_and_changed_identity_fail_closed(self):
        vm,context,_,result=self.runtime()
        manager=vm._documents.get_index('Orders')
        result.rows=(result.rows[0],result.rows[0])
        with self.assertRaises(ValueError):manager.select()
        result.identity=NS(name='Orders',metadata_uuid=B)
        with self.assertRaises(ValueError):manager.empty_ref().get_member('Number')

if __name__=='__main__':unittest.main()

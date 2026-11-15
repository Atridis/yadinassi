"""Source document module lifetime and real atomic OnWrite execution."""
import unittest
from uuid import uuid4
import test_source_document_records as document
import test_source_document_sections as section
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_definitions import source_document_definitions
from yadinassi.errors import BSLError

CREATE='D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); '
def package(module,body='',sections=False):
    return (section.package if sections else document.package)(body,extra={'Documents/Invoice/Ext/ObjectModule.bsl':module.encode()})

class SourceDocumentModuleTests(unittest.TestCase):
    setUp=document.SourceDocumentRecordTests.setUp
    def run_body(self,module,body='',sections=False):
        out=[];app=SourceApplication(package(module,body,sections),scratch_database=self.path,source_document_sections=sections,source_document_records=not sections,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_initializer(self):
        _,out=self.run_body('Number="INIT";','D=Documents.Invoice.CreateDocument(); Message(D.Number);');self.assertEqual(out,['INIT'])
    def test_date_constructor_initializer_and_export_ru_en(self):
        for spelling in ('Date','Дата'):
            with self.subTest(spelling=spelling):
                # Each source variant has its own scratch file and schema binding.
                old_path=self.path
                self.path=old_path.with_name(spelling+'.sqlite')
                try:
                    module=(f'{spelling}={spelling}(2026,1,1); '
                            f'Function Construct() Export Return {spelling}(2026,1,2); EndFunction')
                    _,out=self.run_body(module,
                        'D=Documents.Invoice.CreateDocument(); '
                        'Message(D.Date=Date(2026,1,1)); '
                        'Message(D.Construct()=Date(2026,1,2));')
                    self.assertEqual(out,['Да','Да'])
                finally:self.path=old_path
    def test_exports_and_instance_vars(self):
        _,out=self.run_body('Var Counter Export; Counter=0; Procedure Inc() Export Counter=Counter+1; EndProcedure', 'A=Documents.Invoice.CreateDocument(); B=Documents.Invoice.CreateDocument(); A.Inc(); Message(A.Counter); Message(B.Counter);');self.assertEqual(out,['1','0'])
    def test_thisobject(self):
        _,out=self.run_body('Procedure SetCode(Value) Export ThisObject.Number=Value; EndProcedure',CREATE+'D.SetCode("B"); Message(D.Number);');self.assertEqual(out,['B'])
    def test_field_byref(self):
        _,out=self.run_body('Procedure Change(Value) Value="B"; EndProcedure Procedure Adjust() Export Change(Number); EndProcedure',CREATE+'D.Adjust(); D.Write(); Message(D.Ref.Number);');self.assertEqual(out,['B'])
    def test_onwrite_after_sql(self):
        _,out=self.run_body('Procedure OnWrite(Cancel) Message(ThisObject.Ref.Number); EndProcedure',CREATE+'D.Write();');self.assertEqual(out,['A'])
    def test_onwrite_mutations_not_resaved(self):
        _,out=self.run_body('Procedure OnWrite(Cancel) Number="BUFFER"; EndProcedure',CREATE+'D.Write(); Message(D.Number); Message(D.Ref.Number);');self.assertEqual(out,['BUFFER','A'])
    def test_cancel_rolls_scalar(self):
        app,out=self.run_body('Procedure OnWrite(Cancel) Cancel=True; EndProcedure',CREATE+'Try D.Write(); Except Message("cancel"); EndTry; Message(D.IsNew());');self.assertEqual(out,['cancel','Да']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_error_rolls_scalar(self):
        app,_=self.run_body('Procedure OnWrite(Cancel) Raise "failed"; EndProcedure',CREATE+'Try D.Write(); Except EndTry;');self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_cancel_rolls_sections(self):
        app,_=self.run_body('Procedure OnWrite(Cancel) Cancel=True; EndProcedure',CREATE+'R=D.Lines.Add(); R.Flag=True; Try D.Write(); Except EndTry;',True);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_onwrite_sees_sections(self):
        _,out=self.run_body('Procedure OnWrite(Cancel) Q=New Query("SELECT COUNT(*) AS N FROM Document.Invoice.Lines"); S=Q.Execute().Select(); S.Next(); Message(S.N); EndProcedure',CREATE+'R=D.Lines.Add(); R.Flag=True; D.Write();',True);self.assertEqual(out,['1'])
    def test_sections_mutations_not_resaved(self):
        _,out=self.run_body('Procedure OnWrite(Cancel) Lines.Clear(); EndProcedure',CREATE+'R=D.Lines.Add(); R.Flag=True; D.Write(); Message(D.Lines.Count()); Message(D.Ref.GetObject().Lines.Count());',True);self.assertEqual(out,['0','1'])
    def test_loaded_values_override_initializer(self):
        _,out=self.run_body('Number="INIT";',CREATE+'D.Write(); O=D.Ref.GetObject(); Message(O.Number);');self.assertEqual(out,['A'])
    def test_loaded_sections_override_initializer(self):
        _,out=self.run_body('R=Lines.Add(); R.Flag=False;',CREATE+'D.Lines.Clear(); R=D.Lines.Add(); R.Flag=True; D.Write(); O=D.Ref.GetObject(); Message(O.Lines.Count()); Message(O.Lines.Get(0).Flag);',True);self.assertEqual(out,['1','Да'])
    def test_export_save_cancel_private_alias(self):
        app,out=self.run_body('Procedure Save() Export ThisObject.Write(); EndProcedure Procedure OnWrite(Cancel) Cancel=True; EndProcedure',CREATE+'Try D.Save(); Except Message("cancel"); EndTry;');self.assertEqual(out,['cancel']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_beforewrite_blocks_no_event_execution(self):
        app,out=self.run_body('Procedure BeforeWrite(Cancel,Mode,PostingMode) Message("bad"); EndProcedure Procedure OnWrite(Cancel) Message("bad"); EndProcedure',CREATE+'Try D.Write(); Except Message("unsupported"); EndTry;');self.assertEqual(out,['unsupported']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_blocked_module_exports_work(self):
        _,out=self.run_body('Procedure BeforeWrite(Cancel,Mode,PostingMode) EndProcedure Function Hello() Export Return "ok"; EndFunction','D=Documents.Invoice.CreateDocument(); Message(D.Hello());');self.assertEqual(out,['ok'])
    def test_invalid_onwrite_signature_before_initializer(self):
        defs,errors=source_document_definitions(package('Message("bad"); Procedure OnWrite() EndProcedure'));self.assertFalse(defs);self.assertIn('invoice',errors)
    def test_invalid_beforewrite_signature(self):
        defs,errors=source_document_definitions(package('Procedure BeforeWrite(Cancel) EndProcedure'));self.assertFalse(defs)
    def test_async_unsupported(self):
        defs,errors=source_document_definitions(package('Async Procedure Hello() Export EndProcedure'));self.assertFalse(defs)
    def test_reserved_field_conflict(self):
        defs,errors=source_document_definitions(package('Var Number;'));self.assertFalse(defs)
    def test_reserved_local_var_rejected_before_initializer(self):
        for name in ('Number','Номер','Date','Дата'):
            with self.subTest(name=name):
                defs,errors=source_document_definitions(package(
                    f'Message("must not run"); Procedure Change() Export Var {name}; EndProcedure'))
                self.assertFalse(defs)
                self.assertIn('invoice',errors)
    def test_recursive_write_refused(self):
        app,out=self.run_body('Procedure OnWrite(Cancel) Write(); EndProcedure',CREATE+'Try D.Write(); Except Message("recursive"); EndTry;');self.assertEqual(out,['recursive']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_initializer_write_refused(self):
        with self.assertRaises(BSLError):self.run_body('Number="A"; Date=Date(2026,1,1); Write();','D=Documents.Invoice.CreateDocument();')
    def test_initializer_cycle(self):
        with self.assertRaises(BSLError):self.run_body('O=Documents.Invoice.CreateDocument();','D=Documents.Invoice.CreateDocument();')
    def test_cancel_requires_boolean(self):
        app,_=self.run_body('Procedure OnWrite(Cancel) Cancel=1; EndProcedure',CREATE+'Try D.Write(); Except EndTry;');self.assertFalse(app.constant_store.read_documents('Invoice'))
    def test_explicit_transaction_uncommitted(self):
        app,out=self.run_body('Procedure OnWrite(Cancel) EndProcedure',CREATE+'BeginTransaction(); D.Write(); Message(TransactionActive()); RollbackTransaction();');self.assertEqual(out,['Да']);self.assertFalse(app.constant_store.read_documents('Invoice'))
    def test_moduleless_schema_unchanged(self):
        from yadinassi.source_document_definitions import document_definition_record
        defs,_=source_document_definitions(document.package());self.assertEqual(len(document_definition_record(defs['invoice'])),3)
    def test_onread_never_silently_skipped(self):
        module='Procedure OnRead() Message("bad"); EndProcedure'
        _,out=self.run_body(module,'D=Documents.Invoice.CreateDocument(); Try D.Read(); Except Message("read-unsupported"); EndTry; Try Documents.Invoice.EmptyRef().GetObject(); Except Message("load-unsupported"); EndTry;')
        self.assertEqual(out,['read-unsupported','load-unsupported'])

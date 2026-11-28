"""Direct nonposting documents and owned section lifecycle without VM execution."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_source_document_sections import package, CREATE
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.configuration.configuration_source import import_source
from yadinassi.types.errors import BSLError


class DirectSourceDocumentTests(unittest.TestCase):
    def app(self,body,extra=''):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        source=package(CREATE+body)
        files={entry.path:entry.content for entry in source.files}
        files['Ext/SessionModule.bsl']+=extra.encode()
        output=[]
        app=SourceApplication(import_source(files),scratch_database=Path(tmp.name)/'doc.sqlite',
                              source_document_sections=True,output=output.append)
        self.addCleanup(app.close);return app,output

    @contextmanager
    def no_vm(self):
        yield

    def test_write_getobject_select_and_section_roundtrip(self):
        app,out=self.app('Add=D.Lines.Add; R=Add(); R.Flag=True; D.Write(); P=D.Ref.GetObject(); Message(P.Lines[0].Flag); S=Documents.Invoice.Select(); Message(S.Next()); Message(S.GetObject().Lines.Count()); Message(D.Ref.UUID());')
        with self.no_vm():app.start()
        self.assertEqual(out[:3],['Да','Да','1']);self.assertEqual(len(out[3]),36)

    def test_row_property_byref_and_read_invalidation(self):
        app,out=self.app('R=D.Lines.Add(); R.Flag=False; Flip(R.Flag); D.Write(); Old=D.Lines; D.Read(); Message(D.Lines[0].Flag); Try Old.Count(); Except Message("stale section"); EndTry; Try Flip(R.Flag); Except Message("stale row"); EndTry;',
                         ' Procedure Flip(Value) Value=True; EndProcedure')
        with self.no_vm():app.start()
        self.assertEqual(out,['Да','stale section','stale row'])

    def test_outer_transaction_rolls_back_document_and_catalog(self):
        app,out=self.app('BeginTransaction(); C=Catalogs.Items.CreateItem(); C.Code="C"; C.Write(); R=D.Lines.Add(); R.Flag=True; D.Write(); RollbackTransaction(); S=Documents.Invoice.Select(); Message(S.Next()); C=Catalogs.Items.Select(); Message(C.Next());')
        with self.no_vm():app.start()
        self.assertEqual(out,['Нет','Нет']);self.assertFalse(app.constant_store.transaction_active)

    def test_incomplete_bundle_rolls_back_outer_transaction(self):
        app,out=self.app('BeginTransaction(); C=Catalogs.Items.CreateItem(); C.Code="C"; C.Write(); D.Lines.Add(); Try D.Write(); Except Message("incomplete"); EndTry; S=Catalogs.Items.Select(); Message(S.Next());')
        with self.no_vm():app.start()
        self.assertEqual(out,['incomplete','Нет']);self.assertFalse(app.constant_store.transaction_active)

    def test_write_modes_refused_before_argument_effect(self):
        app,out=self.app('D.Write(Effect());',' Function Effect() Message("effect"); Return True; EndFunction')
        with self.no_vm(),self.assertRaisesRegex(BSLError,'posting unsupported'):app.start()
        self.assertEqual(out,[])

    def test_saved_section_method_rechecks_invalidation(self):
        app,out=self.app('Add=D.Lines.Add; D.Write(); D.Read(); Try Add(); Except Message("stale method"); EndTry; Message(D.Lines.Count());')
        with self.no_vm():app.start()
        self.assertEqual(out,['stale method','0'])

    def test_mutation_during_iteration_still_denied(self):
        app,out=self.app('R=D.Lines.Add(); R.Flag=True; R=D.Lines.Add(); R.Flag=False; Try For Each Row In D.Lines Do D.Lines.Clear(); EndDo; Except Message("changed"); EndTry;')
        with self.no_vm():app.start()
        self.assertEqual(out,['changed'])


if __name__=='__main__':unittest.main()

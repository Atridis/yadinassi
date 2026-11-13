"""DocumentRef fields retain their exact source identity across persistence."""
import unittest
from uuid import uuid4
import test_source_document_records as document
import test_source_document_sections as section
import test_source_catalog_definitions as catalog
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

def package(body='',where='document',target='Invoice'):
    field=catalog.attribute('Link','<v8:Type>cfg:DocumentRef.'+target+'</v8:Type>')
    children=field if where=='document' else section.SECTION.replace(catalog.attribute('Flag'),field) if where=='section' else ''
    source=document.package(body,children=children)
    files={f.path:f.content for f in source.files}
    if where=='catalog':files['Catalogs/Items.xml']=next(f.content for f in catalog.config(children=field).files if f.path=='Catalogs/Items.xml')
    path='Catalogs/Items.xml' if where=='catalog' else 'Documents/Invoice.xml'
    files[path]=files[path].replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')
    return import_source(files)

CREATE='D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); '
class SourceDocumentRelationTests(unittest.TestCase):
    setUp=document.SourceDocumentRecordTests.setUp
    def run_body(self,body,where='document'):
        out=[];app=SourceApplication(package(body,where),scratch_database=self.path,source_document_sections=where=='section',source_document_records=where!='section',output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_self_document(self):
        _,out=self.run_body(CREATE+'D.Link=Documents.Invoice.EmptyRef(); D.Write(); D.Link=D.Ref; D.Write(); Message(D.Ref.GetObject().Link=D.Ref);');self.assertEqual(out,['Да'])
    def test_catalog_navigation(self):
        _,out=self.run_body(CREATE+'D.Write(); C=Catalogs.Items.CreateItem(); C.Code="C"; C.Link=D.Ref; C.Write(); Message(C.Ref.Link.Number);',where='catalog');self.assertEqual(out,['A'])
    def test_section_navigation(self):
        _,out=self.run_body(CREATE+'D.Write(); R=D.Lines.Add(); R.Link=D.Ref; D.Write(); Message(D.Ref.GetObject().Lines.Get(0).Link.Number);',where='section');self.assertEqual(out,['A'])
    def test_catalog_query_join(self):
        _,out=self.run_body(CREATE+'D.Write(); C=Catalogs.Items.CreateItem(); C.Code="C"; C.Link=D.Ref; C.Write(); Q=New Query("SELECT D.Number AS N FROM Catalog.Items AS C INNER JOIN Document.Invoice AS D ON C.Link=D.Ref"); S=Q.Execute().Select(); S.Next(); Message(S.N);',where='catalog');self.assertEqual(out,['A'])
    def test_document_query_join(self):
        _,out=self.run_body(CREATE+'D.Link=Documents.Invoice.EmptyRef(); D.Write(); D.Link=D.Ref; D.Write(); Q=New Query("SELECT B.Number AS N FROM Document.Invoice AS A INNER JOIN Document.Invoice AS B ON A.Link=B.Ref"); S=Q.Execute().Select(); S.Next(); Message(S.N);');self.assertEqual(out,['A'])
    def test_section_query_join(self):
        _,out=self.run_body(CREATE+'D.Write(); R=D.Lines.Add(); R.Link=D.Ref; D.Write(); Q=New Query("SELECT D.Number AS N FROM Document.Invoice.Lines AS L INNER JOIN Document.Invoice AS D ON L.Link=D.Ref"); S=Q.Execute().Select(); S.Next(); Message(S.N);',where='section');self.assertEqual(out,['A'])
    def test_typed_temp(self):
        _,out=self.run_body(CREATE+'D.Link=Documents.Invoice.EmptyRef(); D.Write(); D.Link=D.Ref; D.Write(); Q=New Query("SELECT Link AS R INTO T FROM Document.Invoice; SELECT R FROM T"); S=Q.Execute().Select(); S.Next(); Message(S.R.Number);');self.assertEqual(out,['A'])
    def test_unload_requery(self):
        _,out=self.run_body(CREATE+'D.Link=Documents.Invoice.EmptyRef(); D.Write(); Q=New Query("SELECT Link AS R FROM Document.Invoice"); T=Q.Execute().Unload(); Q.Text="SELECT R FROM &Input"; Q.SetParameter("Input",T); S=Q.Execute().Select(); S.Next(); Message(S.R.IsEmpty());');self.assertEqual(out,['Да'])
    def test_no_guessed_default(self):
        with self.assertRaises(BSLError):self.run_body(CREATE+'D.Write();')
    def test_wrong_reference_family(self):
        with self.assertRaises(BSLError):self.run_body(CREATE+'D.Link=Catalogs.Items.EmptyRef();')
    def test_scalar_refused(self):
        with self.assertRaises(BSLError):self.run_body(CREATE+'D.Link="fake";')
    def test_dangling_identity_not_fake_record(self):
        _,out=self.run_body(CREATE+'D.Link=Documents.Invoice.GetRef(New UUID("00000000-0000-0000-0000-000000000111")); D.Write(); Try Message(D.Ref.Link.Number); Except Message("missing"); EndTry;');self.assertEqual(out,['missing'])
    def test_find_by_attribute_document_ref(self):
        _,out=self.run_body(CREATE+'D.Write(); C=Catalogs.Items.CreateItem(); C.Code="C"; C.Link=D.Ref; C.Write(); Message(Catalogs.Items.FindByAttribute("Link",D.Ref)=C.Ref);',where='catalog');self.assertEqual(out,['Да'])
    def test_v4_neutral_ref_roundtrip(self):
        source=package('C=Catalogs.Items.CreateItem(); C.Code="C"; C.Link=Documents.Invoice.EmptyRef(); C.Write(); Message(C.Ref.Link.IsEmpty());',where='catalog');out=[]
        app=SourceApplication(source,scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['Да'])
    def test_v4_document_query_explicitly_unavailable(self):
        source=package('C=Catalogs.Items.CreateItem(); C.Code="C"; C.Link=Documents.Invoice.EmptyRef(); C.Write(); Q=New Query("SELECT Link FROM Catalog.Items"); Q.Execute();',where='catalog')
        app=SourceApplication(source,scratch_database=self.path,source_catalog_records=True);self.addCleanup(app.close)
        with self.assertRaises(BSLError):app.start()
    def test_reopen_rebinds(self):
        source=package(CREATE+'D.Link=Documents.Invoice.EmptyRef(); D.Write();')
        app=SourceApplication(source,scratch_database=self.path,source_document_records=True);app.start();old=app.references.snapshot;app.close()
        other=SourceApplication(source,existing_scratch_database=self.path,source_document_records=True);self.addCleanup(other.close)
        ref=other.constant_store.read_documents('Invoice')[0][2]['link'];self.assertIsNot(ref.value_type.snapshot,old);self.assertIs(ref.value_type,other.references.definition('Document','Invoice')[1])

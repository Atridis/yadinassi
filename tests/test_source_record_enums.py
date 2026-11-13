"""Source-owned enumeration fields persist without string/default coercions."""
import unittest
from dataclasses import replace
from uuid import uuid4
import test_source_document_records as document
import test_source_document_sections as section
import test_source_catalog_definitions as catalog
from test_source_enums import xml, value
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_definitions import source_catalog_definitions
from yadinassi.source_document_definitions import source_document_definitions
from yadinassi.source_constant_store import _encode
from yadinassi.errors import BSLError


def package(body='',where='catalog'):
    field=catalog.attribute('Choice','<v8:Type>cfg:EnumRef.State</v8:Type>')
    children=field if where=='document' else section.SECTION.replace(catalog.attribute('Flag'),field) if where=='section' else ''
    files={f.path:f.content for f in document.package(body,children=children).files}
    if where=='catalog':
        files['Catalogs/Items.xml']=next(f.content for f in catalog.config(children=field).files if f.path=='Catalogs/Items.xml')
    path='Catalogs/Items.xml' if where=='catalog' else 'Documents/Invoice.xml'
    files[path]=files[path].replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</Configuration>',b'<ChildObjects><Catalog>Items</Catalog><Document>Invoice</Document><Enum>State</Enum><Enum>Mode</Enum></ChildObjects></Configuration>')
    files['Enums/State.xml']=xml('Enum','State',value('Active')+value('Inactive'))
    files['Enums/Mode.xml']=xml('Enum','Mode',value('Auto'))
    return import_source(files)

CAT='C=Catalogs.Items.CreateItem(); C.Code="A"; '
DOC='D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); '
class SourceRecordEnumTests(unittest.TestCase):
    setUp=document.SourceDocumentRecordTests.setUp
    def app(self,source,where='catalog',existing=False):
        kwargs={'existing_scratch_database' if existing else 'scratch_database':self.path,
                'source_document_sections' if where=='section' else 'source_document_records' if where=='document' else 'source_catalog_records':True}
        out=[];app=SourceApplication(source,output=out.append,**kwargs);self.addCleanup(app.close);return app,out
    def run_body(self,body,where='catalog'):
        app,out=self.app(package(body,where),where);app.start();return app,out
    def test_catalog_roundtrip(self):
        _,out=self.run_body(CAT+'C.Choice=Enums.State.Active; C.Write(); Message(C.Ref.Choice=Enums.State.Active);');self.assertEqual(out,['Да'])
    def test_document_roundtrip(self):
        _,out=self.run_body(DOC+'D.Choice=Enums.State.Inactive; D.Write(); Message(D.Ref.GetObject().Choice=Enums.State.Inactive);','document');self.assertEqual(out,['Да'])
    def test_section_roundtrip(self):
        _,out=self.run_body(DOC+'R=D.Lines.Add(); R.Choice=Enums.State.Active; D.Write(); Message(D.Ref.GetObject().Lines.Get(0).Choice=Enums.State.Active);','section');self.assertEqual(out,['Да'])
    def test_empty_reference_explicit(self):
        _,out=self.run_body(CAT+'C.Choice=Enums.State.EmptyRef(); C.Write(); Message(C.Ref.Choice.IsEmpty());');self.assertEqual(out,['Да'])
    def test_no_guessed_default(self):
        with self.assertRaises(BSLError):self.run_body(CAT+'C.Write();')
    def test_scalar_refused(self):
        with self.assertRaises(BSLError):self.run_body(CAT+'C.Choice="Active";')
    def test_wrong_enum_refused(self):
        with self.assertRaises(BSLError):self.run_body(DOC+'D.Choice=Enums.Mode.Auto;','document')
    def test_lookup_by_attribute(self):
        _,out=self.run_body(CAT+'C.Choice=Enums.State.Active; C.Write(); Message(Catalogs.Items.FindByAttribute("Choice",Enums.State.Active)=C.Ref); Message(Catalogs.Items.FindByAttribute("Choice",Enums.State.Inactive).IsEmpty());');self.assertEqual(out,['Да','Да'])
    def test_reopen_rebinds_canonical(self):
        source=package(CAT+'C.Choice=Enums.State.Active; C.Write();');app,_=self.app(source);app.start();old=app.enumerations.get_member('State')._values[0];app.close()
        other,_=self.app(source,existing=True);stored=other.constant_store.read_records('Items')[0][2]['choice'];self.assertIs(stored,other.enumerations.get_member('State')._values[0]);self.assertIsNot(stored,old)
    def test_section_reopen_rebinds_canonical(self):
        source=package(DOC+'R=D.Lines.Add(); R.Choice=Enums.State.Active; D.Write();','section');app,_=self.app(source,'section');app.start();identity=app.constant_store.read_documents('Invoice')[0][0];app.close()
        other,_=self.app(source,'section',True);stored=other.constant_store.read_document_bundle('Invoice',identity)[3]['lines'][0]['choice'];self.assertIs(stored,other.enumerations.get_member('State')._values[0])
    def test_foreign_enum_refused(self):
        source=package();app,_=self.app(source);other=SourceApplication(source);self.addCleanup(other.close)
        field=next(f for f in app.constant_store.catalog('Items').fields if f.name=='Choice')
        with self.assertRaises(TypeError):_encode(other.enumerations.get_member('State')._values[0],field)
    def test_forged_enum_refused(self):
        app,_=self.app(package());field=next(f for f in app.constant_store.catalog('Items').fields if f.name=='Choice');ref=app.enumerations.get_member('State')._values[0]
        for forged in (replace(ref,metadata=object()),replace(ref,value_type=replace(ref.value_type)),replace(ref,reference_uuid=uuid4())):
            with self.subTest(forged=type(forged).__name__),self.assertRaises(TypeError):_encode(forged,field)
    def test_parsers_create_owned_namespace(self):
        for where in ('catalog','document','section'):
            with self.subTest(where=where):
                defs,errors=(source_catalog_definitions(package(where=where)) if where=='catalog' else source_document_definitions(package(where=where),allow_sections=where=='section'))
                self.assertFalse(errors);definition=defs['items' if where=='catalog' else 'invoice'];fields=definition.sections[0].fields if where=='section' else definition.fields
                field=next(f for f in fields if f.name=='Choice');self.assertEqual(field.kind,'enum_ref');self.assertIsNotNone(field.enum_namespace)

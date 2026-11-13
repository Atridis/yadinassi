"""Exact source lookup and authorized live reference fields, not native parity."""
import unittest
from unittest.mock import patch
from dataclasses import replace
from uuid import uuid4
import test_source_catalog_queries as fixture
from test_source_catalog_relations import source as related_source, CREATE
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_runtime import reference_member, reference_call
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.errors import BSLError

class SourceCatalogLookupTests(unittest.TestCase):
    setUp=fixture.SourceCatalogQueryTests.setUp
    run_body=fixture.SourceCatalogQueryTests.run_body

    def test_find_code_live_field(self):
        _,out=self.run_body('Message(Catalogs.Items.FindByCode("1").Description);');self.assertEqual(out,['Alpha'])
    def test_find_code_missing_empty(self):
        _,out=self.run_body('Message(Catalogs.Items.FindByCode("missing").IsEmpty());');self.assertEqual(out,['Да'])
    def test_russian_find(self):
        _,out=self.run_body('Сообщить(Справочники.Items.НайтиПоКоду("1").Наименование);');self.assertEqual(out,['Alpha'])
    def test_find_description_exact(self):
        _,out=self.run_body('Message(Catalogs.Items.FindByDescription("Beta",True).Code);');self.assertEqual(out,['2'])
    def test_find_description_omitted_rejected(self):
        with self.assertRaises(BSLError):self.run_body('Catalogs.Items.FindByDescription("Alpha");')
    def test_find_description_false_rejected(self):
        with self.assertRaises(BSLError):self.run_body('Catalogs.Items.FindByDescription("Alpha",False);')
    def test_find_description_no_partial(self):
        _,out=self.run_body('Message(Catalogs.Items.FindByDescription("Al",True).IsEmpty());');self.assertEqual(out,['Да'])
    def test_duplicate_description_refused(self):
        with self.assertRaisesRegex(BSLError,'ambiguous'):
            self.run_body('O=Catalogs.Items.FindByCode("2").GetObject(); O.Description="Alpha"; O.Write(); Catalogs.Items.FindByDescription("Alpha",True);')
    def test_find_attribute(self):
        _,out=self.run_body('Message(Catalogs.Items.FindByAttribute("Description","Beta").Code);');self.assertEqual(out,['2'])
    def test_attribute_unknown(self):
        with self.assertRaises(BSLError):self.run_body('Catalogs.Items.FindByAttribute("Missing",True);')
    def test_attribute_wrong_type(self):
        with self.assertRaises(BSLError):self.run_body('Catalogs.Items.FindByAttribute("DeletionMark","false");')
    def test_attribute_duplicate_boolean(self):
        with self.assertRaisesRegex(BSLError,'ambiguous'):self.run_body('Catalogs.Items.FindByAttribute("DeletionMark",False);')
    def test_code_not_coerced(self):
        with self.assertRaises(BSLError):self.run_body('Catalogs.Items.FindByCode(1);')
    def test_saved_lookup_method(self):
        _,out=self.run_body('F=Catalogs.Items.FindByCode; Message(F("2").Description);');self.assertEqual(out,['Beta'])
    def test_empty_reference_field_refused(self):
        with self.assertRaisesRegex(BSLError,'not found'):self.run_body('Message(Catalogs.Items.EmptyRef().Description);')
    def test_dangling_reference_field_refused(self):
        with self.assertRaisesRegex(BSLError,'not found'):self.run_body('Message(Catalogs.Items.GetRef(New UUID("01234567-89ab-cdef-0123-456789abcdef")).Code);')
    def test_live_reference_refresh(self):
        _,out=self.run_body('R=Catalogs.Items.FindByCode("1"); O=R.GetObject(); O.Description="new"; O.Write(); Message(R.Description);');self.assertEqual(out,['new'])
    def test_reference_assignment_refused(self):
        with self.assertRaisesRegex(BSLError,'readonly'):self.run_body('R=Catalogs.Items.FindByCode("1"); R.Description="bad";')
    def test_reference_neutral_in_safe_mode(self):
        _,out=self.run_body('R=Catalogs.Items.EmptyRef(); SetSafeMode(True); Message(R.IsEmpty()); Message(R.Metadata().Name);');self.assertEqual(out,['Да','Items'])
    def test_reference_fields_safe_mode_denied(self):
        with self.assertRaises(BSLError):self.run_body('R=Catalogs.Items.FindByCode("1"); SetSafeMode(True); Message(R.Code);')
    def test_exact_lookup_transaction(self):
        _,out=self.run_body('BeginTransaction(); O=Catalogs.Items.CreateItem(); O.Code="3"; O.Write(); Message(Catalogs.Items.FindByCode("3").IsEmpty()); RollbackTransaction(); Message(Catalogs.Items.FindByCode("3").IsEmpty());');self.assertEqual(out,['Нет','Да'])
    def test_lookup_one_snapshot(self):
        original=SourceCatalogStore.read_records;calls=[]
        def read(store,name,identity=None):calls.append(name);return original(store,name,identity)
        with patch.object(SourceCatalogStore,'read_records',read):self.run_body('Catalogs.Items.FindByCode("1");')
        self.assertEqual(calls,['Items'])
    def test_ref_callback_forgery_rejected(self):
        app,_=self.run_body('');ref=app.references.ref('Catalog','Items',self.ids[0]);calls=[]
        forged=replace(ref,read_member=lambda *args:calls.append(args))
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        with self.assertRaises(TypeError):reference_member(app.interpreter,forged,'Description')
        from yadinassi.source_catalog_runtime import is_source_reference
        forged_without_metadata=replace(forged,metadata=None)
        self.assertTrue(is_source_reference(forged_without_metadata))
        with self.assertRaises(TypeError):reference_member(app.interpreter,forged_without_metadata,'Description')
        with self.assertRaises(TypeError):reference_call(app.interpreter,forged,'GetObject')
        self.assertEqual(calls,[])
    def test_catalogref_lookup_and_navigation(self):
        source=related_source(CREATE+'R=Catalogs.Items.FindByAttribute("Category",G.Ref); Message(R.Category.Description);')
        out=[];app=SourceApplication(source,scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['Group'])
    def test_foreign_source_reference_field_refused(self):
        app,_=self.run_body('');other=SourceApplication(app.source);self.addCleanup(other.close)
        ref=other.references.ref('Catalog','Items',self.ids[0])
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        with self.assertRaises(TypeError):reference_member(app.interpreter,ref,'Description')
    def test_closed_source_reference_field_refused(self):
        app,_=self.run_body('');ref=app.references.ref('Catalog','Items',self.ids[0]);app.close()
        with self.assertRaises(ValueError):reference_member(app.interpreter,ref,'Description')

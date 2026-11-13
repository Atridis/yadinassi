"""Independent record-preservation and lifecycle guards for reference access."""
import unittest
import test_source_catalog_object_modules as modules
from yadinassi.errors import BSLError

class SourceCatalogLookupGuards(unittest.TestCase):
    setUp=modules.SourceCatalogModuleTests.setUp
    run_body=modules.SourceCatalogModuleTests.run_body

    def test_reference_read_does_not_initialize_an_object(self):
        _,out=self.run_body('Message("init");',modules.CREATE+'O.Description="saved"; O.Write(); Message(O.Ref.Description); Message(Catalogs.Items.FindByCode("A").Description);')
        self.assertEqual(out,['init','saved','saved'])

    def test_reference_assignment_does_not_mutate_record(self):
        app,out=self.run_body('',modules.CREATE+'O.Description="saved"; O.Write(); R=O.Ref; Try R.Description="changed"; Except Message("readonly"); EndTry; Message(R.Description);')
        self.assertEqual(out,['readonly','saved']);self.assertEqual(app.constant_store.read_records('Items')[0][2]['description'],'saved')

    def test_reference_byref_assignment_does_not_mutate_record(self):
        _,out=self.run_body('Procedure Change(V) Export V="changed"; EndProcedure',modules.CREATE+'O.Description="saved"; O.Write(); Try O.Change(O.Ref.Description); Except Message("readonly"); EndTry; Message(O.Ref.Description);')
        self.assertEqual(out,['readonly','saved'])

    def test_lookup_and_reference_observe_explicit_transaction(self):
        app,out=self.run_body('', 'BeginTransaction(); '+modules.CREATE+'O.Description="uncommitted"; O.Write(); Message(Catalogs.Items.FindByCode("A").Description); RollbackTransaction(); Message(Catalogs.Items.FindByCode("A").IsEmpty());')
        self.assertEqual(out,['uncommitted','Да']);self.assertEqual(app.constant_store.read_records('Items'),[])

    def test_module_initializer_can_lookup_saved_records(self):
        _,out=self.run_body('Existing=Catalogs.Items.FindByCode("A"); If Not Existing.IsEmpty() Then Message(Existing.Description); EndIf;',modules.CREATE+'O.Description="saved"; O.Write(); P=Catalogs.Items.CreateItem();')
        self.assertEqual(out,['saved'])

    def test_readonly_reference_does_not_run_write_handlers(self):
        _,out=self.run_body('Procedure BeforeWrite(Cancel) Description="handler"; EndProcedure',modules.CREATE+'O.Write(); R=Catalogs.Items.FindByDescription("handler",True); Message(R.Description); Message(R.DeletionMark);')
        self.assertEqual(out,['handler','Нет'])

"""Host-selected catalog bridge; original writer validation is not bypassed."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.configuration_main_demo import PROFILE,import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from test_main_demo_configuration import source

class DirectDatabaseTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.context=SQLiteDBContext.create_main_demo(Path(folder.name)/'db.sqlite',import_main_demo_configuration(source(),profile=PROFILE))
        self.addCleanup(self.context.close)
        self.vm=Interpreter(database_context=self.context);self.addCleanup(self.vm.close)

    def test_objects_fields_sections_and_no_argument_add(self):
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            self.vm.execute('A=Catalogs.Номенклатура.CreateItem(); A.Description=" Item "; Row=A.Склады.Add(); N=A.Склады.Count();')
        self.assertEqual(self.vm.variables['a'].get_member('Description'),' Item ')
        self.assertEqual(self.vm.variables['n'],1)

    def test_plain_catalog_write_readback_uses_existing_writer(self):
        self.vm.execute('A=Catalogs.Склады.CreateItem(); A.Description="Warehouse"; A.Write(); B=A.Ref.GetObject();')
        self.assertEqual(self.vm.variables['b'].get_member('Description'),'Warehouse')
        self.assertFalse(self.vm.variables['b'].is_new())

    def test_foreign_receiver_and_backend_attributes_deny(self):
        self.vm.execute('A=Catalogs.Склады.CreateItem();')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreign']=self.vm.variables['a']
        with self.assertRaises(BoundaryViolation):other.execute('foreign.Description="bad";')
        with self.assertRaises(Exception):self.vm.execute('secret=A._manager;')

    def test_transactions_rejected_before_effect_and_flag_restored(self):
        with patch('yadinassi.database_transactions.begin',side_effect=AssertionError('effect')) as begin:
            with self.assertRaises(Exception):self.vm.execute('BeginTransaction();')
            begin.assert_not_called()
        self.assertTrue(self.vm._transaction_activation_allowed)

    def test_query_selection_on_real_sqlite_without_vm_dispatch(self):
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура"); S=Q.Execute().Select(); Found=S.Next(); N=S.N;')
        self.assertTrue(self.vm.variables['found'])
        self.assertEqual(self.vm.variables['n'],0)
        self.vm.execute('Again=S.Next(); Last=S.N;')
        self.assertFalse(self.vm.variables['again'])
        self.assertEqual(self.vm.variables['last'],0)

    def test_foreign_query_and_query_private_fields_rejected(self):
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура");')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreign']=self.vm.variables['q']
        with self.assertRaises(BoundaryViolation):other.execute('foreign.Execute();')
        with self.assertRaises(Exception):self.vm.execute('secret=Q._catalogs;')

    def test_document_and_enum_buffer_protocol_without_persistence(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument(); D.Number="draft"; L=D.Lines.Add(); L.Unit=Enums.Units.Piece; L.Quantity=3; Mode=DocumentWriteMode.Posting; N=D.Lines.Count();')
        self.assertEqual(self.vm.variables['d'].get_member('Number'),'draft')
        self.assertEqual(self.vm.variables['l'].get_member('Quantity'),3)
        self.assertEqual(self.vm.variables['n'],1)
        from yadinassi.document_posting_values import DocumentWriteMode
        self.assertIs(self.vm.variables['mode'],DocumentWriteMode.POSTING)
        self.assertTrue(self.vm.variables['d'].is_new())

    def test_foreign_document_receiver_denied(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument();')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreign']=self.vm.variables['d']
        with self.assertRaises(BoundaryViolation):other.execute('foreign.Number="bad";')
        self.assertEqual(self.vm.variables['d'].get_member('Number'),'')

    def test_document_additional_properties_output_reference(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument(); D.AdditionalProperties.Insert("Mode",2); Mode=0; Found=D.AdditionalProperties.Property("Mode",Mode);')
        self.assertTrue(self.vm.variables['found'])
        self.assertEqual(self.vm.variables['mode'],2)

    def test_prepared_namespace_profile_rejects_transfer_before_effects(self):
        plain=Interpreter();self.addCleanup(plain.close)
        plain_plan=plain.prepare('Touched=1; Catalogs=1;')
        with self.assertRaisesRegex(Exception, 'contract changed'):
            self.vm.execute_prepared(plain_plan)
        self.assertNotIn('touched',self.vm.variables)
        self.assertNotIn('catalogs',self.vm.variables)
        db_plan=self.vm.prepare('Touched=1; N=Catalogs.Склады.Count();')
        with self.assertRaisesRegex(Exception, 'contract changed'):
            plain.execute_prepared(db_plan)
        self.assertNotIn('touched',plain.variables)

    def test_prepared_database_profile_rebinds_to_current_vm(self):
        plan=self.vm.prepare('A=Catalogs.Склады.CreateItem(); A.Description="fresh";')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.execute_prepared(plan)
        self.assertNotIn('a',self.vm.variables)
        self.assertEqual(other.variables['a'].get_member('Description'),'fresh')
        other.execute('A.Description="current";')
        self.assertEqual(other.variables['a'].get_member('Description'),'current')

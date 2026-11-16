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

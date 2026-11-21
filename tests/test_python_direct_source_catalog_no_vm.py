"""Existing catalog module lifecycle contracts cannot invoke legacy dispatch."""
import unittest
from unittest.mock import patch
import test_source_catalog_object_modules as lifecycle
import test_source_catalog_module_guards as guards
from yadinassi.runtime import Interpreter


class NoVM:
    def setUp(self):
        super().setUp()
        for name in ('_execute_program', 'call_routine'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start();self.addCleanup(poison.stop)


class DirectCatalogLifecycleNoVM(NoVM,lifecycle.SourceCatalogModuleTests):
    def test_bare_standard_methods(self):
        _,out=self.run_body('Procedure Save() Export Code="bare"; Write(); EndProcedure',
            'O=Catalogs.Items.CreateItem(); O.Save(); Message(O.Ref.GetObject().Code);')
        self.assertEqual(out,['bare'])

    def test_captured_standard_method(self):
        _,out=self.run_body('Procedure Save() Export Code="saved"; F=Write; F(); EndProcedure',
            'O=Catalogs.Items.CreateItem(); O.Save(); Message(O.Ref.GetObject().Code);')
        self.assertEqual(out,['saved'])

    def test_exported_byref_default(self):
        _,out=self.run_body('Procedure Change(V, Val S="changed") Export V=S; EndProcedure',
            'O=Catalogs.Items.CreateItem(); X="initial"; O.Change(X); Message(X);')
        self.assertEqual(out,['changed'])


class DirectCatalogGuardsNoVM(NoVM,guards.SourceCatalogModuleGuardTests):
    pass


if __name__=='__main__':unittest.main()

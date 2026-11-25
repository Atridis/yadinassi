"""Ordinary direct temporary-table managers use the registered VM factory."""
import unittest

from yadinassi import Interpreter
from yadinassi.db.query.query_packages import BSLTempTablesManager
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class DirectTempTablesManagerTests(unittest.TestCase):
    def test_bilingual_no_database_create_and_close(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('A=New TempTablesManager; B=Новый МенеджерВременныхТаблиц();')
        for name in ('a', 'b'):
            manager = vm.variables[name]
            self.assertIs(type(manager), BSLTempTablesManager)
            self.assertIs(manager._owner, vm._catalogs._metadata)
            self.assertFalse(manager._closed)
        vm.execute('A.Close(); B.Закрыть();')
        self.assertTrue(vm.variables['a']._closed)
        self.assertTrue(vm.variables['b']._closed)

    def test_foreign_manager_stays_outside_member_boundary(self):
        owner, borrower = Interpreter(), Interpreter()
        self.addCleanup(borrower.close)
        self.addCleanup(owner.close)
        owner.execute('M=New TempTablesManager;')
        borrower.variables['m'] = manager = owner.variables['m']
        with self.assertRaises(BoundaryViolation):
            borrower.execute('M.Close();')
        self.assertFalse(manager._closed)

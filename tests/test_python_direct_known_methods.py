from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_database import CatalogBoundary
from yadinassi.syntax.parser import parse


class KnownMethodTests(unittest.TestCase):
    def test_named_tables_use_normal_decimal_count(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('T=New ValueTable; A=T.Count(); U=New ТаблицаЗначений; B=U.Количество();'))
        original=CatalogBoundary.resolve_member
        visited=[]
        def observe(context,value,name):
            visited.append(name.casefold())
            return original(context,value,name)
        with patch.object(CatalogBoundary,'resolve_member',observe):
            vm.execute_prepared(plan)
        self.assertFalse({'count','количество'} & set(visited))
        self.assertEqual((type(vm.variables['a']),type(vm.variables['b'])),(Decimal,Decimal))
        self.assertEqual((vm.variables['a'],vm.variables['b']),(0,0))

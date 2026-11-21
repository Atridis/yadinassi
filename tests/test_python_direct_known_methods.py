from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_database import CatalogBoundary
from yadinassi.syntax.parser import parse


class KnownMethodTests(unittest.TestCase):
    def test_routine_local_table_alias_keeps_direct_count_after_rebind(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source=('Function Work() Var T; T=New ValueTable; Alias=T; T=0; '
                'Return Alias.Count(); EndFunction\nWork()')
        plan=vm.prepare_program(parse(source))
        generated=plan._plan.generated_source
        self.assertIn('.count()',generated)
        self.assertNotIn('_known_detached_after_publication',generated)
        with patch.object(CatalogBoundary,'resolve_member',side_effect=AssertionError('generic count')):
            self.assertEqual(vm.execute(source),Decimal(0))
            self.assertEqual(vm.execute_prepared(plan),Decimal(0))

    def test_routine_reference_escape_does_not_bind_to_old_receiver(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source=('Procedure Swap(Value) Value=New Array; Value.Add(1); EndProcedure\n'
                'Function Work() T=New ValueTable; Swap(T); Return T.Count(); EndFunction\nWork()')
        plan=vm.prepare_program(parse(source))
        self.assertNotIn('_known_construct_table',plan._plan.generated_source)
        self.assertEqual(vm.execute(source),Decimal(1))
        self.assertEqual(vm.execute_prepared(plan),Decimal(1))

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

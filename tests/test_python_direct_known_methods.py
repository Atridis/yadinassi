from contextlib import ExitStack
from decimal import Decimal
import unittest
from unittest.mock import patch

from scripts.benchmark_extended_layers import database
from yadinassi import Interpreter
from yadinassi.db.query.queries import BSLQueryResultSelection
from yadinassi.execution.direct.python_direct_database import CatalogBoundary
from yadinassi.syntax.parser import parse
from yadinassi.types.values import HostFunction


class KnownMethodTests(unittest.TestCase):
    def test_query_select_and_named_next_keep_ordinary_sql_and_return_values(self):
        with ExitStack() as stack:
            _,_,vm,manager=database(stack)
            manager.create_item().write()
            source='Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); S=Q.Execute().Select(); B=S.Next(); R=S.N;'
            generic=CatalogBoundary.resolve_member
            visits=[]
            def observe(context,value,name):
                visits.append(name.casefold())
                return generic(context,value,name)
            for route in ('default','prepared'):
                program=parse(source)
                run=(lambda:vm.execute_program(program)) if route=='default' else (
                    lambda plan=vm.prepare_program(program):vm.execute_prepared(plan))
                with patch.object(CatalogBoundary,'resolve_member',observe):
                    run()
                self.assertEqual(vm.variables['r'],Decimal(1))
                self.assertIs(vm.variables['b'],True)
            self.assertFalse(set(visits) & {'execute','select','next'})

    def test_prepared_query_uses_rebound_method_protocol_via_original_fallback(self):
        with ExitStack() as stack:
            _,_,vm,_=database(stack)
            plan=vm.prepare_program(parse('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); B=Q.Execute().Select().Next();'))
            original=BSLQueryResultSelection.get_method
            calls=[]
            def changed(value,name):
                if name.casefold()=='next':
                    calls.append(name)
                    return HostFunction(name,lambda:False)
                return original(value,name)
            with patch.object(BSLQueryResultSelection,'get_method',changed):
                vm.execute_prepared(plan)
            self.assertEqual(calls,['Next'])
            self.assertIs(vm.variables['b'],False)
            vm.execute_prepared(plan)
            self.assertIs(vm.variables['b'],True)

    def test_named_tables_use_normal_decimal_count(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('T=New ValueTable; A=T.Count(); U=New ТаблицаЗначений; B=U.Количество();'))
        vm.execute_prepared(plan)
        self.assertEqual((type(vm.variables['a']),type(vm.variables['b'])),(Decimal,Decimal))
        self.assertEqual((vm.variables['a'],vm.variables['b']),(0,0))

"""Counts stay native only where a closed compiler path consumes them safely."""
import unittest
from decimal import Decimal as D
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.collections.plain_value_table_runtime import BSLValueTable


class NativeCollectionCountTests(unittest.TestCase):
    def test_table_last_row_index_and_publication(self):
        for method in ('Count', 'Количество'):
            for prepared in (False, True):
                vm=Interpreter();self.addCleanup(vm.close)
                source=f'T=New ValueTable; T.Columns.Add("N"); R=T.Add(); R.N=7; C=T.{method}(); V=T[T.{method}()-1][0]; C;'
                seen=[];original=BSLValueTable.get
                def get(table,index):
                    seen.append(type(index));return original(table,index)
                with patch.object(BSLValueTable,'get',get):
                    plan=vm.prepare(source)
                    result=vm.execute_prepared(plan) if prepared else vm.execute_program(parse(source))
                self.assertEqual(seen,[int]);self.assertIs(type(result),D)
                self.assertEqual(result,D(1));self.assertEqual(vm.variables['v'],D(7))
                self.assertIs(type(vm.variables['c']),D)
                self.assertIn('len(',plan._plan.generated_source)
                self.assertNotIn('.count()',plan._plan.generated_source)

    def test_empty_last_index_preserves_error_and_partial_state(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaisesRegex(Exception,'table index out of range'):
            vm.execute('T=New ValueTable; C=T.Count(); R=T[T.Count()-1]; After=1;')
        self.assertEqual(vm.variables['c'],D(0));self.assertIs(type(vm.variables['c']),D)
        self.assertNotIn('after',vm.variables)

    def test_columns_count_and_dynamic_host_stay_decimal(self):
        vm=Interpreter();self.addCleanup(vm.close)
        result=vm.execute('T=New ValueTable; T.Columns.Add("N"); C=T.Columns.Count(); C;')
        self.assertEqual(result,D(1));self.assertIs(type(result),D)
        seen=[];vm.register_function('Observe',lambda value:seen.append(type(value)))
        vm.execute('Observe(T.Count()); Observe(T.Columns.Count());')
        self.assertEqual(seen,[D,D])
        self.assertIs(type(vm.variables['t'].count()),D)

    def test_array_upper_bound_index_without_payload_int_leak(self):
        for name in ('UBound','ВГраница'):
            vm=Interpreter();self.addCleanup(vm.close)
            plan=vm.prepare(f'A=New Array; A.Add(7); A.Add(A.Count()); X=A[A.{name}()]; X;')
            self.assertEqual(vm.execute_prepared(plan),D(1))
            self.assertTrue(all(type(value) is D for value in vm.variables['a']))
            self.assertIs(type(vm.variables['x']),D)
            self.assertIn('len(',plan._plan.generated_source)

    def test_table_and_column_index_of_stay_native_inside_plan(self):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare('T=New ValueTable; N=T.Columns.Add("N"); Row=T.Add(); Row.N=7;'
                        'Other=New ValueTable; Foreign=Other.Add(); Missing=T.IndexOf(Foreign);'
                        'I=T.IndexOf(Row); J=T.Columns.Индекс(N); X=T[I][J]; X;')
        self.assertEqual(vm.execute_prepared(plan),D(7))
        self.assertTrue(all(type(vm.variables[key]) is D for key in ('i','j','x','missing')))
        self.assertEqual(vm.variables['missing'],D(-1))
        self.assertEqual(plan._plan.generated_source.count('._index_of('),3)

    def test_other_collection_payloads_not_broadened(self):
        for source,name in (
            ('A=New Array; A.Add(A.Count()); A.Count();','a'),
            ('A=New Map; A.Insert(1,A.Count()); A.Count();','a'),
            ('A=New ValueList; A.Add(A.Count()); A.Count();','a')):
            vm=Interpreter();self.addCleanup(vm.close)
            result=vm.execute(source)
            self.assertIs(type(result),D)

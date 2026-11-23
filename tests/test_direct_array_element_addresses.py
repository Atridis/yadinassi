import ast
from decimal import Decimal as D
import unittest

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import BSLArray


class DirectArrayElementAddressTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        return vm

    def test_hot_loop_uses_direct_addresses_and_same_slot_alias_is_live(self):
        vm=self.vm()
        source=('Procedure Rewrite(A, Val K, B) A=A*K; B=B+1; EndProcedure '
                'T=New Array; T.Add(2); For I=1 To 3 Do Rewrite(T[0],2,T[0]); EndDo;')
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        loop=next(node for node in ast.walk(tree) if type(node) is ast.For)
        calls=[node.func.id for node in ast.walk(loop)
               if type(node) is ast.Call and type(node.func) is ast.Name]
        self.assertEqual(calls.count('_checked_literal_array_index'),2)
        self.assertNotIn('_adapt_native_cell',calls)
        self.assertNotIn('_IndexRef',calls)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['t'],[D(23)])
        self.assertIs(type(vm.variables['t'][0]),D)
        vm.execute('X=2; Y=3; Rewrite(X, 5, Y);')
        self.assertEqual((vm.variables['x'],vm.variables['y']),(D(10),D(4)))

    def test_ordinary_indexed_assignment_keeps_direct_address_calls(self):
        vm=self.vm()
        source=('Procedure SetOrAdd(A, Val K) A=A+K; EndProcedure '
                'T=New Array; T.Add(5); IX=0; T[IX]=2; '
                'For I=1 To 3 Do SetOrAdd(T[0],2); EndDo;')
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        loop=next(node for node in ast.walk(tree) if type(node) is ast.For)
        hot=ast.unparse(loop)
        self.assertIn('_checked_literal_array_index',hot)
        self.assertNotIn('_adapt_native_cell',hot)
        self.assertNotIn('_context._check()',hot)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['t'],[D(8)])

    def test_indexed_assignment_validates_after_rhs_and_never_truncates(self):
        for index,rhs,expected in (('-1','1/0','Деление на ноль'),
                                   ('-1','2','Индекс массива вне границ'),
                                   ('0.5','2','Ожидается целое число')):
            with self.subTest(index=index,rhs=rhs):
                vm=self.vm()
                source=('Procedure Update(X) X=X+1; EndProcedure '
                        f'T=New Array; T.Add(5); T[{index}]={rhs}; Update(T[0]);')
                with self.assertRaisesRegex(BSLRuntimeError,expected):
                    vm.execute_prepared(vm.prepare(source))
                self.assertEqual(vm.variables['t'],[D(5)])

    def test_bad_address_precedes_later_actual_and_write_survives_error(self):
        for prepare in (False,True):
            vm=self.vm()
            for index,error,value in (('1','Индекс массива вне границ',D(2)),
                                      ('0.5','Ожидается целое число',D(2)),
                                      ('-0','Деление на ноль',D(9))):
                with self.subTest(prepare=prepare,index=index):
                    if index=='-0':
                        source=('Procedure Change(X) X=9; X=1/0; EndProcedure '
                                'T=New Array; T.Add(2); Change(T[-0]);')
                    else:
                        source=('Procedure Change(X, Val Y) X=9; EndProcedure '
                                f'T=New Array; T.Add(2); Change(T[{index}],1/0);')
                    with self.assertRaisesRegex(BSLRuntimeError,error):
                        if prepare:vm.execute_prepared(vm.prepare(source))
                        else:vm.execute(source)
                    self.assertEqual(vm.variables['t'],[value])

    def test_guarded_local_boxed_array_addresses_keep_aliases_and_argument_order(self):
        vm=Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        values=BSLArray(D(1))
        values.set(D(0),D(2))
        vm.variables['values']=values
        calls=[]
        vm.register_function('Later',lambda: calls.append('later') or D(3))
        definition='Procedure Change(A, Val N, B) A=A*N; B=B+1; EndProcedure\n'
        bad=definition+'Change(Values[1],Later(),Values[0]);'
        with self.assertRaisesRegex(BSLRuntimeError,'Индекс массива вне границ'):
            vm.execute(bad)
        self.assertEqual(calls,[])
        plan=vm.prepare(definition+'Change(Values[0],Later(),Values[0]);')
        vm.execute_prepared(plan)
        self.assertEqual(values.items,[D(7)])
        self.assertEqual(calls,['later'])

    def test_guarded_local_boxed_array_address_refuses_replaced_storage(self):
        vm=Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        values=BSLArray(D(1))
        original=values.items
        vm.variables['values']=values
        def swap():
            values.items=[D(42)]
            return D(0)
        vm.register_function('Swap',swap)
        source='Procedure Change(A, Val Ignored) A=9; EndProcedure\nChange(Values[0],Swap());'
        with self.assertRaisesRegex(BoundaryViolation,'canonical array address storage or hooks changed'):
            vm.execute(source)
        self.assertEqual(original,[None])
        self.assertEqual(values.items,[D(42)])

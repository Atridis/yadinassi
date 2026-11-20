import ast
from decimal import Decimal as D
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


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

"""Detached builtin BSLArray positions participate in known-local ByRef only."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.codegen.direct_reference_runtime import bind_local_index_reference
from yadinassi.execution.direct.python_direct import make_boundary
from yadinassi.types.values import BSLArray, BSLFixedArray


DECLARATIONS = 'Procedure Store(X,Val Y) X=Y; EndProcedure '
SETUP = '''
Var A, Trace;
T=New ValueTable; T.Columns.Add("X"); T.Add().X=1; T.Add().X=2; T.Add().X=3;
A=T.UnloadColumn("X"); Trace="";
'''


class LocalBoxedArrayCellsTests(unittest.TestCase):
    def vm(self, **options):
        vm=Interpreter(**options)
        self.addCleanup(vm.close)
        return vm

    def test_actual_api_array_reference_keeps_live_position_and_evaluation_order(self):
        vm=self.vm()
        plan=vm.prepare(SETUP+'''
            Function Receiver() Trace=Trace+"R"; Return A; EndFunction
            Function Position() Trace=Trace+"I"; Return 0; EndFunction
            Function Later() Trace=Trace+"V"; A.Delete(0); Return 6; EndFunction
            Function Step(X,Val N) X=X+N; Return X; EndFunction
            R=Step(Receiver()[Position()],Later());
        ''')
        vm.execute_prepared(plan)
        self.assertIs(type(vm.variables['a']),BSLArray)
        self.assertEqual(vm.variables['r'],8)
        self.assertEqual(vm.variables['trace'],'RIV')
        self.assertEqual(vm.variables['a'].items,[8,3])

    def test_address_formation_and_live_bounds_before_write(self):
        vm=self.vm()
        with self.assertRaisesRegex(BSLError,'Индекс массива вне границ'):
            vm.execute(SETUP+DECLARATIONS+'''
                Function Later() Trace="ran"; Return 9; EndFunction
                Store(A[4],Later());
            ''')
        self.assertEqual(vm.variables['trace'],'')
        with self.assertRaisesRegex(BSLError,'Индекс массива вне границ'):
            vm.execute(SETUP+DECLARATIONS+'''
                Function Later() Trace="ran"; A.Clear(); Return 9; EndFunction
                Store(A[0],Later());
            ''')
        self.assertEqual(vm.variables['trace'],'ran')
        self.assertEqual(vm.variables['a'].items,[])

    def test_alias_and_partial_write_are_not_copyout(self):
        vm=self.vm()
        vm.execute(SETUP+'''
            Procedure Change(AliasA,AliasB)
                AliasA=4; AliasB=AliasB+AliasA; Raise "after assignment";
            EndProcedure
            Try Change(A[0],A[0]); Except EndTry;
        ''')
        self.assertEqual(vm.variables['a'].items,[8,2,3])

    def test_exact_owner_backing_and_lease_remain_live(self):
        vm=self.vm()
        context=make_boundary(vm)
        context.enter()
        self.addCleanup(context.leave)
        array=BSLArray()
        array.items=[Decimal(2)]
        address=bind_local_index_reference(context,array)(Decimal(0))
        self.assertEqual(address.get(),2)
        original=array.items
        array.items=[Decimal(7)]
        for operation in (address.get,lambda:address.set(8)):
            with self.assertRaises(BoundaryViolation):operation()
        self.assertEqual((original,array.items),([2],[7]))
        array.items=original
        context.revoke()
        with self.assertRaisesRegex(BoundaryViolation,'authority revoked'):address.set(8)
        self.assertEqual(original,[2])

    def test_subclass_and_malformed_backing_do_not_invoke_hooks(self):
        vm=self.vm()
        seen=[]
        class Foreign(BSLArray):
            def get(self,index):seen.append('foreign');raise AssertionError
        class ListSubclass(list):
            def __getitem__(self,index):seen.append('items');raise AssertionError
        class ForeignIndex:
            def __index__(self):seen.append('index');raise AssertionError
        ordinary=BSLArray()
        ordinary.items=ListSubclass([2])
        for receiver in (Foreign(),ordinary):
            vm.variables['a']=receiver
            with self.assertRaises(BoundaryViolation):vm.execute(DECLARATIONS+'Store(A[0],9);')
        ordinary.items=[Decimal(2)]
        vm.variables.update(a=ordinary,i=ForeignIndex())
        with self.assertRaisesRegex(BSLError,'Ожидается число'):
            vm.execute(DECLARATIONS+'Store(A[I],9);')
        self.assertEqual(seen,[])
        self.assertEqual(ordinary.items,[2])

    def test_touched_method_hook_is_not_invoked(self):
        for extensions in (False,True):
            with self.subTest(allow_extensions=extensions):
                vm=self.vm(allow_extensions=extensions)
                vm.execute(SETUP)
                plan=vm.prepare(DECLARATIONS+'Store(A[0],9);')
                seen=[]
                def hostile(*_args):seen.append('set');raise AssertionError
                with patch.object(BSLArray,'set',hostile):
                    with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
                self.assertEqual(seen,[])
                self.assertEqual(vm.variables['a'].items,[1,2,3])

    def test_dynamic_invocation_does_not_gain_reference(self):
        for extensions in (False,True):
            with self.subTest(allow_extensions=extensions):
                vm=self.vm(allow_extensions=extensions)
                vm.execute(SETUP)
                vm.execute(DECLARATIONS)
                with self.assertRaises(BoundaryViolation):vm.execute('Store(A[0],9);')
                self.assertEqual(vm.variables['a'].items,[1,2,3])

    def test_known_local_invocation_keeps_reference_in_either_mode(self):
        for extensions in (False,True):
            with self.subTest(allow_extensions=extensions):
                vm=self.vm(allow_extensions=extensions)
                vm.execute(SETUP)
                vm.execute(DECLARATIONS+'Store(A[0],9);')
                self.assertIs(type(vm.variables['a']),BSLArray)
                self.assertEqual(vm.variables['a'].items,[9,2,3])

    def test_fixed_array_stays_readonly_and_bad_numbers_are_rejected(self):
        vm=self.vm()
        vm.execute(SETUP)
        vm.variables['f']=BSLFixedArray(vm.variables['a'])
        with self.assertRaises(BSLError):vm.execute(DECLARATIONS+'Store(F[0],9);')
        self.assertEqual(vm.variables['f'].items,(1,2,3))
        with self.assertRaisesRegex(BSLError,'Ожидается целое число'):
            vm.execute(DECLARATIONS+'Store(A[0.5],9);')
        with self.assertRaisesRegex(BSLError,'вне границ'):
            vm.execute(DECLARATIONS+'Store(A[-1],9);')

"""Only the canonical mutable Array family receives an opaque display label."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.values import BSLArray, BSLFixedArray
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.direct_scalar_semantics import presentation, concatenate, typed_find


class ArrayPresentationSecurityTests(unittest.TestCase):
    def test_regular_and_subclass_presentation_matches_existing_backend_contract(self):
        class Array(BSLArray):
            def __str__(self):raise AssertionError('host str')
        for kind in (BSLArray,Array):
            output=[];vm=Interpreter(output=output.append)
            self.addCleanup(vm.close);vm.variables['a']=kind()
            vm.execute('Message(a);Message(String(a));Message("type:"+a);')
            self.assertEqual(output,['Массив','Массив','type:Массив'])

    def test_no_fields_or_metaclass_descriptors_are_read(self):
        class Meta(type):
            @property
            def __mro__(cls):raise AssertionError('descriptor')
            def __getattribute__(cls,name):raise AssertionError('class attr')
            def __eq__(cls,other):raise AssertionError('class eq')
            def __hash__(cls):raise AssertionError('class hash')
        class Array(BSLArray,metaclass=Meta):
            def __getattribute__(self,name):raise AssertionError('payload')
            def __str__(self):raise AssertionError('str')
            def __eq__(self,other):raise AssertionError('eq')
        value=object.__new__(Array)
        self.assertEqual(presentation(value),'Массив')
        self.assertEqual(concatenate('x:',value),'x:Массив')

    def test_foreign_spoof_and_fixed_array_are_not_added_to_domain(self):
        class Fake:
            @property
            def __class__(self):return BSLArray
            def __str__(self):raise AssertionError('host str')
        for value in (Fake(),BSLFixedArray(BSLArray())):
            with self.assertRaises(BoundaryViolation):presentation(value)
        with patch('yadinassi.types.values.BSLArray',Fake):
            with self.assertRaises(BoundaryViolation):presentation(Fake())

    def test_display_label_does_not_grant_fields_find_or_receiver_authority(self):
        class Array(BSLArray):pass
        value=Array();boundary=BoundaryContext();boundary.start()
        self.assertEqual(presentation(value),'Массив')
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'items')
        with self.assertRaises(BoundaryViolation):typed_find([value],value)
        with self.assertRaises(BoundaryViolation):typed_find(value,None)
        boundary.revoke()
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'items')

    def test_operand_order_and_close_are_preserved(self):
        events=[];output=[];vm=Interpreter(output=output.append, allow_extensions=True);self.addCleanup(vm.close)
        vm.register_function('Left',lambda:events.append('left') or 'type:')
        vm.register_function('Right',lambda:events.append('right') or BSLArray())
        vm.execute('Message(Left()+Right());')
        self.assertEqual(events,['left','right']);self.assertEqual(output,['type:Массив'])
        def close():vm.close();return BSLArray()
        vm.register_function('CloseOwner',close)
        with self.assertRaises(BoundaryViolation):vm.execute('Message("type:"+CloseOwner());')
        self.assertEqual(output,['type:Массив'])

    def test_extension_string_and_numeric_addition_in_prepared_routines(self):
        source = '''
Function AppendOne(Val Value)
    Return Value + 1;
EndFunction
Result = AppendOne(Supply());
'''
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter(allow_extensions=True)
                self.addCleanup(vm.close)
                value = iter(('prefix:', Decimal(2)))
                vm.register_function('Supply', lambda: next(value))
                plan = vm.prepare(source) if prepared else None
                for expected in ('prefix:1', Decimal(3)):
                    if plan is None:
                        vm.execute(source)
                    else:
                        vm.execute_prepared(plan)
                    self.assertEqual(vm.variables['result'], expected)

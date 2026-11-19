"""Generic direct calls cannot execute interpreter-only descriptors or argument effects."""
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.types.values import HostFunction, InterpreterCall
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation


class InterpreterDescriptorPreflightTests(unittest.TestCase):
    def test_named_captured_returned_and_alias_calls_reject_before_arguments(self):
        for statement in ('Denied(Touch());', 'Alias=Captured;Alias(Touch());',
                          'GetDescriptor()(Touch());'):
            with self.subTest(statement=statement):
                effects=[]
                descriptor=InterpreterCall(0,1,lambda *_:effects.append('authorize'),
                                           lambda *_:effects.append('dispatch'))
                vm=Interpreter(output=lambda _:None)
                self.addCleanup(vm.close)
                vm.register_function('Denied',descriptor)
                vm.variables['captured']=vm.functions['denied']
                vm.register_function('Touch',lambda:effects.append('argument'))
                vm.register_function('GetDescriptor',lambda:vm.functions['denied'])
                with self.assertRaisesRegex(BSLError,'explicit interpreter dispatch'):
                    vm.execute(statement)
                self.assertEqual(effects,[])

    def test_bsl_can_catch_unsupported_call_without_argument_effects(self):
        output=[]
        vm=Interpreter(output=output.append);self.addCleanup(vm.close)
        vm.register_function('Denied',InterpreterCall(0,1,lambda *_:None,lambda *_:None))
        vm.execute('Try Denied(Message("bad")); Except Message("caught"); EndTry;')
        self.assertEqual(output,['caught'])

    def test_generic_boundary_never_calls_descriptor_callbacks(self):
        effects=[]
        class Hostile:
            def __call__(self,*args):raise AssertionError('descriptor callback executed')
        descriptor=InterpreterCall(0,1,Hostile(),Hostile())
        function=HostFunction('Denied',descriptor)
        boundary=BoundaryContext(services={'Denied':function});boundary.start()
        for resolve in (lambda:boundary.resolve_service('Denied'),
                        lambda:boundary.resolve_callable(function)):
            with self.assertRaisesRegex(ValueError,'explicit interpreter dispatch'):resolve()
        self.assertEqual(effects,[])

    def test_ordinary_host_callable_with_invoke_attribute_is_not_descriptor(self):
        effects=[]
        class Ordinary:
            def __call__(self,value):effects.append(value);return value
            def invoke(self,*args):raise AssertionError('duck dispatch')
        vm=Interpreter(output=lambda _:None);self.addCleanup(vm.close)
        vm.register_function('Ordinary',Ordinary())
        self.assertEqual(vm.execute('Ordinary(7)'),7)
        self.assertEqual(effects,[7])

    def test_exact_identity_does_not_adopt_public_class_replacements_or_duck_types(self):
        class Custom(InterpreterCall):
            def __call__(self,value):return value
        vm=Interpreter(output=lambda _:None);self.addCleanup(vm.close)
        vm.register_function('Custom',Custom(0,1,lambda *_:None,lambda *_:None))
        with patch('yadinassi.types.values.InterpreterCall',Custom):
            self.assertEqual(vm.execute('Custom(8)'),8)
            vm.register_function('Denied',InterpreterCall(0,1,lambda *_:None,lambda *_:None))
            with self.assertRaisesRegex(BSLError,'explicit interpreter dispatch'):
                vm.execute('Denied(8)')

    def test_revoked_boundary_is_fatal_before_descriptor_inspection(self):
        function=HostFunction('Denied',InterpreterCall(0,1,lambda *_:None,lambda *_:None))
        boundary=BoundaryContext(services={'Denied':function});boundary.start();boundary.revoke()
        for resolve in (lambda:boundary.resolve_service('Denied'),lambda:boundary.resolve_callable(function)):
            with self.assertRaises(BoundaryViolation):resolve()

    def test_late_descriptor_replacement_never_dispatches_callbacks(self):
        effects=[]
        vm=Interpreter(output=lambda _:None);self.addCleanup(vm.close)
        vm.register_function('Target',lambda value:effects.append('ordinary'))
        def change():
            effects.append('argument')
            vm.functions['target'].function=InterpreterCall(0,1,
                lambda *_:effects.append('authorize'),lambda *_:effects.append('dispatch'))
        vm.register_function('Change',change)
        with self.assertRaisesRegex(BSLError,'explicit interpreter dispatch'):
            vm.execute('Target(Change())')
        self.assertEqual(effects,['argument'])

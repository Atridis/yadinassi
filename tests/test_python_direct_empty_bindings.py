"""Skip absent work without caching persistent admission or host authority."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.python_direct import PythonDirectUnsupported


class DirectEmptyBindingTests(unittest.TestCase):
    def test_host_services_do_not_enter_missing_persistent_binding_path(self):
        for persistent in (False,True):
            vm=Interpreter()
            if persistent:vm.execute('Function F(Val X) Return X+1; EndFunction')
            with patch('yadinassi.python_direct_routines.resolve',side_effect=AssertionError('persistent miss')):
                vm.execute('R=StrLen("abc");')
            self.assertEqual(vm.variables['r'],3)
    def test_existing_persistent_name_still_uses_current_validation(self):
        vm=Interpreter();vm.execute('Function F(Val X) Return X+1; EndFunction')
        vm.execute('R=F(2);');self.assertEqual(vm.variables['r'],3)
        vm._compilation_profile='managed-thick-file'
        with self.assertRaises(PythonDirectUnsupported):vm.execute('Effect=1;F(2);')
        self.assertNotIn('effect',vm.variables)
    def test_empty_validation_does_not_touch_a_registry(self):
        from yadinassi.python_direct_routines import validate_calls
        from yadinassi.python_direct import _admit_bindings
        class Unreadable:
            def __getattribute__(self,name):raise AssertionError('unexpected read: '+name)
        validate_calls(Unreadable(),frozenset())
        _admit_bindings(Unreadable(),frozenset(),frozenset(),frozenset())
    def test_host_boundary_checks_before_and_after_effect_remain(self):
        for persistent in (False,True):
            for change in ('close','restricted'):
                vm=Interpreter()
                if persistent:vm.execute('Function F() Return 1;EndFunction')
                def effect():
                    if change=='close':vm.close()
                    else:vm._configuration_runtime=object()
                    return Decimal(3)
                vm.register_function('Host',effect)
                with self.assertRaises(BoundaryViolation):vm.execute('R=Host();')
                self.assertNotIn('r',vm.variables)
    def test_overridden_constructor_remains_denied(self):
        vm=Interpreter();vm.execute('Function F() Return New Array; EndFunction')
        vm.register_type('Array',lambda:[])
        with self.assertRaises(PythonDirectUnsupported):vm.execute('Effect=1;F();')
        self.assertNotIn('effect',vm.variables)
    def test_host_registry_is_live_between_calls(self):
        vm=Interpreter();vm.execute('Function F() Return 1;EndFunction')
        vm.register_function('Host',lambda:Decimal(1))
        vm.execute('R=Host();');self.assertEqual(vm.variables['r'],1)
        vm.register_function('Host',lambda:Decimal(2))
        vm.execute('R=Host();');self.assertEqual(vm.variables['r'],2)

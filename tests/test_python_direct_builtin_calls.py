"""Direct lowering for known builtins must preserve dynamic BSL bindings."""
import cProfile
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class DirectBuiltinCallsTests(unittest.TestCase):
    def vm(self, **kwargs):
        vm = Interpreter(**kwargs)
        self.addCleanup(vm.close)
        return vm

    def test_multiple_builtins_and_aliases_do_not_use_public_service_dispatch(self):
        vm = self.vm()
        vm.variables['s'] = 'Яa😀'
        plan = vm.prepare('R=0; For I=1 To 20 Do R=R+StrLen(S)+СтрДлина(S); EndDo; U=Upper(S); L=Лев(S,2);')
        profile = cProfile.Profile()
        profile.runcall(vm.execute_prepared, plan)
        self.assertEqual(vm.variables['r'], Decimal(160))
        self.assertEqual(vm.variables['u'], 'ЯA😀')
        self.assertEqual(vm.variables['l'], 'Яa')
        calls = {entry.code.co_name for entry in profile.getstats()
                 if not isinstance(entry.code, str)}
        self.assertNotIn('resolve_service', calls)
        self.assertNotIn('_reload_module', calls)

    def test_prepared_call_uses_later_bsl_routine_and_its_byref_signature(self):
        vm = self.vm()
        vm.variables['s'] = 'abc'
        plan = vm.prepare('R=StrLen(S);')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], Decimal(3))
        vm.execute('Function StrLen(S) S="changed"; Return 17; EndFunction')
        with patch('yadinassi.execution.direct.python_direct._nodes',
                   side_effect=AssertionError('prepared execution walked source')), \
             patch('yadinassi.execution.direct.python_direct._compile',
                   side_effect=AssertionError('prepared execution recompiled')):
            vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], Decimal(17))
        self.assertEqual(vm.variables['s'], 'changed')

    def test_local_bsl_routine_has_precedence_in_same_module(self):
        vm = self.vm()
        vm.execute('Function Upper(Val S) Return S+"!"; EndFunction R=Upper("abc");')
        self.assertEqual(vm.variables['r'], 'abc!')

    def test_python_extension_override_still_uses_extension_dispatch(self):
        vm = self.vm(allow_extensions=True)
        vm.register_function('StrLen', lambda s: 'custom:'+s)
        plan = vm.prepare('R=StrLen("abc");')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], 'custom:abc')

    def test_changed_builtin_registry_is_checked_at_actual_call_not_in_dead_branch(self):
        vm = self.vm()
        live = vm.prepare('R=StrLen("abc");')
        dead = vm.prepare('If False Then R=StrLen("abc"); EndIf; R=5;')
        effects = []
        vm.functions['strlen'].function = lambda s: effects.append(s)
        vm.execute_prepared(dead)
        self.assertEqual(vm.variables['r'], Decimal(5))
        with self.assertRaises(BoundaryViolation):
            vm.execute_prepared(live)
        self.assertEqual(effects, [])

    def test_dynamic_string_coercion_remains_a_host_boundary(self):
        vm = self.vm()
        class ClosesInterpreter:
            def __str__(self):
                vm.close()
                return 'abc'
        vm.variables['s'] = ClosesInterpreter()
        with self.assertRaises(BoundaryViolation):
            vm.execute('R=StrLen(S); After=True;')
        self.assertNotIn('after', vm.variables)

    def test_output_callback_can_rebind_a_later_call_in_plain_mode(self):
        attempts = []

        def output(_message):
            vm.functions['strlen'].function = lambda s: attempts.append(s)

        vm = self.vm(output=output)
        vm.variables['s'] = 'abc'
        with self.assertRaises(BoundaryViolation):
            vm.execute('Message("rebind"); R=StrLen(S);')
        self.assertEqual(attempts, [])
        self.assertNotIn('r', vm.variables)

    def test_eval_and_execute_use_the_live_bsl_routine(self):
        vm = self.vm()
        vm.execute('Function StrLen(Val S) Return 91; EndFunction')
        vm.execute('R=Eval("StrLen(""abc"")"); A=0; Execute("A=StrLen(""def"");");')
        self.assertEqual((vm.variables['r'], vm.variables['a']), (Decimal(91), Decimal(91)))

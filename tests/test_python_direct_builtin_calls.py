"""Direct lowering for known builtins must preserve dynamic BSL bindings."""
import cProfile
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


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

    def test_pure_prefix_before_effect_uses_live_suffix_state(self):
        observed = []

        def output(message):
            observed.append((message, vm.variables['r'], vm.variables['i']))
            vm.variables['r'] = Decimal(41)

        vm = self.vm(output=output)
        plan = vm.prepare('R=0; For I=1 To 20 Do R=R+StrLen("abc"); EndDo; Message("tail"); R+1')
        profile = cProfile.Profile()
        self.assertEqual(profile.runcall(vm.execute_prepared, plan), Decimal(42))
        self.assertEqual(observed, [('tail', Decimal(60), Decimal(21))])
        self.assertEqual(vm.variables['r'], Decimal(41))
        counts = {entry.code.co_name: entry.callcount for entry in profile.getstats()
                  if not isinstance(entry.code, str) and entry.code.co_name.startswith('_reload')}
        self.assertEqual(counts, {'_reload_module': 1})

    def test_pure_prefix_does_not_capture_suffix_after_output(self):
        observed = []

        def output(message):
            observed.append((message, vm.variables['r']))
            vm.functions['strlen'].function = lambda value: self.fail('unregistered extension called')

        vm = self.vm(output=output)
        plan = vm.prepare('R=StrLen("abc"); Message("tail"); S=StrLen("abcd");')
        with self.assertRaises(BoundaryViolation):
            vm.execute_prepared(plan)
        self.assertEqual(observed, [('tail', Decimal(3))])
        self.assertNotIn('s', vm.variables)

    def test_prepared_pure_prefix_declines_new_routine_binding(self):
        observed = []
        vm = self.vm(output=observed.append)
        plan = vm.prepare('R=StrLen("abc"); Message(R);')
        vm.execute_prepared(plan)
        vm.execute('Function StrLen(Val X) Return 17; EndFunction')
        with patch('yadinassi.execution.direct.python_direct._compile',
                   side_effect=AssertionError('prepared execution recompiled')):
            vm.execute_prepared(plan)
        self.assertEqual(observed, ['3', '17'])

    def test_pure_prefix_preserves_decimal_counter_rounding(self):
        start = '99999999999999999999999999999999999999'
        end = '100000000000000000000000000000000000001'
        expected = Decimal('1.0000000000000000000000000000000000000E+38')
        for prepared in (False, True):
            for boundary, body in ((start, ''), (end, 'If R>=9 Then Break; EndIf;')):
                with self.subTest(prepared=prepared, boundary=boundary):
                    vm = self.vm(output=[].append)
                    source = (f'R=0; For I={start} To {boundary} Do R=R+StrLen("abc"); '
                              f'{body} EndDo; Message("tail"); I')
                    result = vm.execute_prepared(vm.prepare(source)) if prepared else vm.execute(source)
                    self.assertEqual(result.as_tuple(), expected.as_tuple())
                    self.assertEqual(vm.variables['i'].as_tuple(), expected.as_tuple())

    def test_pure_prefix_does_not_displace_existing_table_region(self):
        vm = self.vm()
        plan = vm.prepare('R=StrLen("abc"); T=New ValueTable; T.Columns.Add("X"); '
                          'For I=1 To 30 Do Row=T.Add(); Row.X=I; EndDo; T.Count()')
        profile = cProfile.Profile()
        self.assertEqual(profile.runcall(vm.execute_prepared, plan), Decimal(30))
        self.assertEqual(vm.variables['r'], Decimal(3))
        self.assertEqual(vm.execute('T[29].X'), Decimal(30))
        calls = {entry.code.co_name for entry in profile.getstats()
                 if not isinstance(entry.code, str)}
        self.assertNotIn('resolve_member_call', calls)
    def test_literal_output_collection_does_not_synchronize_unused_registers(self):
        output = []
        vm = self.vm(output=output.append)
        prefix = ''.join(f'X{i}={i};' for i in range(64))
        plan = vm.prepare(prefix + 'For I=1 To 50 Do Message("e"); Сообщить("р"); EndDo; R=42; R')
        profile = cProfile.Profile()
        self.assertEqual(profile.runcall(vm.execute_prepared, plan), Decimal(42))
        self.assertEqual(output, ['e', 'р'] * 50)
        self.assertEqual([vm.variables[f'x{i}'] for i in range(64)], list(range(64)))
        counts = {entry.code.co_name: entry.callcount for entry in profile.getstats()
                  if not isinstance(entry.code, str)}
        self.assertEqual(counts['_publish_module'], 1)
        self.assertNotIn('_reload_module', counts)

    def test_prepared_literal_output_collection_declines_observing_sink(self):
        output = []
        vm = self.vm(output=output.append)
        plan = vm.prepare('X=1; For I=1 To 3 Do Message("effect"); EndDo; X')
        traced = []

        def sink(message):
            traced.append((message, vm.variables['i'], vm.variables['x']))
            vm.variables['x'] += 1

        vm.output = sink
        self.assertEqual(vm.execute_prepared(plan), Decimal(4))
        self.assertEqual(traced, [
            ('effect', Decimal(1), Decimal(1)),
            ('effect', Decimal(2), Decimal(2)),
            ('effect', Decimal(3), Decimal(3)),
        ])
        self.assertEqual(output, [])

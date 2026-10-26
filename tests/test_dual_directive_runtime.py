"""Bounded dual-NoContext runtime guards, not additional native observations.

Imported/stored exported dual receivers are intentionally excluded by this project
slice. Only the ThisObject form-module restriction has the cited native basis.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import BSLError, Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse


DUAL = '&AtClientAtServerNoContext\n'


class DualDirectiveRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def tearDown(self):
        self.vm.close()

    def assert_restored(self):
        self.assertEqual(self.vm._context_stack, ['client'])
        self.assertEqual(self.vm._module_context_stack, [True])
        self.assertIsNone(self.vm.locals)

    def test_three_caller_lanes_select_independent_profiles_and_drop_capability(self):
        seen = []
        self.vm.register_function('Observe', lambda: seen.append(
            (self.vm.execution_context, self.vm._has_module_context)))
        self.vm.execute('''&AtClientAtServerNoContext
Function D()
Observe();
#If Client Then
Return "client";
#ElsIf Server Then
Return "server";
#Else
Return "neither";
#EndIf
EndFunction
&AtServer
Function ContextServer() R=D(); Observe(); Return R; EndFunction
&AtServerNoContext
Function DetachedServer() R=D(); Observe(); Return R; EndFunction
Message(D()); Observe(); Message(ContextServer()); Message(DetachedServer());
''')
        self.assertEqual(self.output, ['client', 'server', 'server'])
        self.assertEqual(seen, [('client', False), ('client', True),
                               ('server', False), ('server', True),
                               ('server', False), ('server', False)])
        self.assertIsNot(self.vm.routines['d'].body, self.vm.server_routines['d'].body)
        self.assert_restored()

    def test_same_side_reference_val_handle_return_alias_and_escaping_write_all_lanes(self):
        helper = '''&AtClientAtServerNoContext
Function D(X, Val A)
X=X+10; A[0]=A[0]+10; Return A;
EndFunction
&НаКлиентеНаСервереБезКонтекста
Procedure Escape(X) X=X+11; Raise "dual-escape"; EndProcedure
'''
        body = '''X=1; A=New Array; A.Add(2); R=D(X,A); R[0]=R[0]+20;
E=6; Try Escape(E); Except Text=ErrorDescription(); EndTry;
P=New Array; P.Add(X); P.Add(A[0]); P.Add(E); P.Add(R=A); P.Add(Text); Return P;'''
        self.vm.execute(helper + '\nFunction ClientLane() ' + body + ' EndFunction\n'
            '&AtServer\nFunction ServerLane() ' + body + ' EndFunction\n'
            '&AtServerNoContext\nFunction NoContextLane() ' + body + ' EndFunction\n')
        for caller in ('ClientLane', 'ServerLane', 'NoContextLane'):
            with self.subTest(caller=caller):
                result = self.vm.execute(caller + '()')
                self.assertEqual(result.items[:4], [Decimal(11), Decimal(32), Decimal(17), True])
                self.assertIn('dual-escape', result.items[4])
                self.assert_restored()

    def test_nested_dual_recursion_and_same_storage_alias(self):
        self.vm.execute('''&AtClientAtServerNoContext
Function Inner(X,Y,Val Depth)
If Depth>0 Then Return Inner(X,Y,Depth-1); EndIf;
X=X+10; Y=Y+1; Return X;
EndFunction
&НаКлиентеНаСервереБезКонтекста
Function Outer(X) Return Inner(X,X,3); EndFunction
&AtServer
Function Server() X=6; R=Outer(X); Return X*100+R; EndFunction
X=6; R=Outer(X); Message(X*100+R); Message(Server());
''')
        self.assertEqual([item.replace('\u00a0', '') for item in self.output], ['1717', '1717'])
        self.assert_restored()

    def test_client_dual_never_clones_activates_or_replays_initializers(self):
        self.vm.execute('''&AtClientAtServerNoContext
Function D(Val X) X.Insert("N",7); Return X; EndFunction
#If AtServer Then
Raise "initializer must not run";
#EndIf
X=New Map;
''')
        with mock.patch.object(Interpreter, '_copy_context_packet',
                               side_effect=AssertionError('dual must not copy')), \
             mock.patch.object(Interpreter, '_new_server_activation',
                               side_effect=AssertionError('dual must not activate')):
            result = self.vm.execute('D(X)')
        self.assertIs(result, self.vm.variables['x'])
        self.assertEqual(result.get('N'), Decimal(7))
        self.assert_restored()

    def test_server_dual_does_not_replay_initializer_and_restores_caller_storage(self):
        initializations = []
        self.vm.register_function('Init', lambda: initializations.append(1))
        self.vm.execute('''&AtServer
Var State;
&AtClientAtServerNoContext
Procedure D() State=99; EndProcedure
&AtServer
Function Server() D(); D(); State=State+1; Return State; EndFunction
#If AtServer Then
State=40; Init();
#EndIf
Message(Server());
''')
        self.assertEqual(self.output, ['41'])
        self.assertEqual(initializations, [1])
        self.assert_restored()

    def test_explicit_client_dual_to_nocontext_retains_packet_contract(self):
        self.vm.execute('''&AtServerNoContext
Function N(X,Val A) X=X+10; A[0]=A[0]+10; Return A; EndFunction
&AtServerNoContext
Procedure Escape(X) X=X+10; Raise "explicit-crossing"; EndProcedure
&AtClientAtServerNoContext
Function D()
X=1; A=New Array; A.Add(2); R=N(X,A); R[0]=R[0]+20;
E=6; Try Escape(E); Except EndTry;
Return X*10000+A[0]*100+R[0]+E*1000000;
EndFunction
&AtServer
Function Server() Return D(); EndFunction
Message(D()); Message(Server());
''')
        # Client D makes a real transition: Val A is copied and escape has no
        # copyback. Server D calls N same-side, retaining both mutations.
        self.assertEqual([item.replace('\u00a0', '') for item in self.output], ['6110232', '16113232'])
        self.assert_restored()

    def test_server_initializer_calls_dual_in_existing_activation(self):
        activations = []
        original = Interpreter._new_server_activation
        def create(owner, **kwargs):
            activations.append(1)
            return original(owner, **kwargs)
        self.vm.execute('''&AtServer
Var State;
&AtClientAtServerNoContext
Function D(X) X=X+1; Return X; EndFunction
&AtServer
Function Server() Return State; EndFunction
#If AtServer Then
State=40; D(State);
#EndIf
''')
        with mock.patch.object(Interpreter, '_new_server_activation', create):
            self.assertEqual(self.vm.execute('Server()'), Decimal(41))
        self.assertEqual(activations, [1])
        self.assert_restored()

    def test_imported_ordinary_client_wrapper_calls_its_own_dual(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'M.bsl').write_text('''Var State;
&AtClientAtServerNoContext
Function D(X) X=X+10; Return X; EndFunction
Function Wrapper(X) Export D(X); State=State+1; Return State; EndFunction
State=40;
''', encoding='utf-8')
            self.vm.execute('// #Import M.bsl\n' + DUAL +
                'Function D(X) X=999; Return X; EndFunction\n'
                'X=2; Result=M.Wrapper(X);', str(root / 'Root.bsl'))
        self.assertEqual(self.vm.variables['x'], Decimal(12))
        self.assertEqual(self.vm.variables['result'], Decimal(41))
        self.assert_restored()

    def test_missing_server_variant_tombstone_blocks_host_value_alias(self):
        calls = []
        self.vm.register_function('Only', lambda: calls.append('host'))
        self.vm.execute('#If Client Then\n' + DUAL +
            'Function Only() Return 7; EndFunction\n#EndIf\n'
            '&AtServerNoContext\nFunction Server() Alias=Only; Return Alias(); EndFunction')
        with self.assertRaises(BSLError):
            self.vm.execute('Server()')
        self.assertEqual(calls, [])
        self.assert_restored()

    def test_missing_variant_rejected_before_actuals_and_host_fallback(self):
        for side in ('Client', 'Server'):
            with self.subTest(retained=side):
                vm = Interpreter()
                calls = []
                vm.register_function('Only', lambda value: calls.append('host'))
                vm.register_function('Effect', lambda: calls.append('effect'))
                vm.execute('#If ' + side + ' Then\n' + DUAL +
                    'Function Only(Val X) Return X; EndFunction\n#EndIf\n'
                    '&AtServer\nFunction ContextServer() Return Only(Effect()); EndFunction\n'
                    '&AtServerNoContext\nFunction DetachedServer() Return Only(Effect()); EndFunction')
                callers = ('ContextServer()', 'DetachedServer()') if side == 'Client' else ('Only(Effect())',)
                for caller in callers:
                    with self.assertRaisesRegex(BSLError, 'недоступна на стороне'):
                        vm.execute(caller)
                self.assertEqual(calls, [])
                self.assertIn('only', vm._dual_routine_names)
                self.assertEqual(vm._module_context_stack, [True])
                vm.close()

    def test_family_replacement_removes_stale_opposite_side_and_tombstone(self):
        self.vm.execute(DUAL + 'Function F() Return 1; EndFunction')
        self.assertIn('f', self.vm.routines)
        self.assertIn('f', self.vm.server_routines)
        self.vm.execute('#If Server Then\n' + DUAL + 'Function F() Return 2; EndFunction\n#EndIf')
        self.assertNotIn('f', self.vm.routines)
        self.assertIn('f', self.vm.server_routines)
        self.assertIn('f', self.vm._dual_routine_names)
        with self.assertRaisesRegex(BSLError, 'недоступна на стороне'):
            self.vm.execute('F()')
        self.vm.execute('Function F() Return 3; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(3))
        self.assertNotIn('f', self.vm.server_routines)
        self.assertNotIn('f', self.vm._dual_routine_names)
        self.vm.execute(DUAL + 'Function F() Return 4; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(4))
        self.assertEqual(set(self.vm.routines), {'f'})
        self.assertEqual(set(self.vm.server_routines), {'f'})

    def test_all_incoming_groups_validate_before_any_replacement_or_effect(self):
        self.vm.execute(DUAL + 'Function F() Return 1; EndFunction')
        old_client = self.vm.routines.copy()
        old_server = self.vm.server_routines.copy()
        old_markers = self.vm._dual_routine_names.copy()
        replacement = parse(DUAL + 'Function F() Return 2; EndFunction', 'replacement.bsl')
        pair = [n for n in parse(DUAL + 'Function G() Return 3; EndFunction') if isinstance(n, ast.Routine)]
        ordinary = next(n for n in parse('Function G() Return 4; EndFunction') if isinstance(n, ast.Routine))
        bad_groups = ([pair[0], pair[0]],
                      [pair[0], replace(pair[1], token=replace(pair[1].token, line=99))],
                      [pair[0], replace(pair[1], token=replace(pair[1].token, source='other.bsl'))],
                      [pair[0], replace(pair[1], token=replace(pair[1].token, column=99))],
                      [pair[0], replace(pair[1], token=replace(pair[1].token, kind='PROCEDURE'))],
                      [pair[0], pair[1], pair[0]], [pair[0], ordinary], [ordinary, ordinary])
        for group in bad_groups:
            with self.subTest(group=group):
                with self.assertRaises(BSLError):
                    self.vm.execute_program(replacement + parse('Message("must not run"); Var NewStorage;') + group)
                self.assertEqual(self.vm.routines, old_client)
                self.assertEqual(self.vm.server_routines, old_server)
                self.assertEqual(self.vm._dual_routine_names, old_markers)
                self.assertNotIn('newstorage', self.vm.variables)
        self.assertEqual(self.output, [])
        self.assertEqual(self.vm.execute('F()'), Decimal(1))

    def test_forged_ast_context_flags_and_async_dual_are_rejected_before_effects(self):
        dual = next(n for n in parse(DUAL + 'Function F() Return 1; EndFunction') if isinstance(n, ast.Routine))
        for changes in ({'is_dual': 1}, {'is_dual': 'yes'}, {'module_context': 0},
                        {'module_context': True}, {'execution_context': 'dual'},
                        {'is_async': True}, {'is_async': 1},
                        {'is_dual': False, 'module_context': False, 'execution_context': 'client'}):
            with self.subTest(changes=changes), self.assertRaises(BSLError):
                self.vm.execute_program(parse('Message("must not run");') + [replace(dual, **changes)])
        self.assertEqual(self.output, [])
        self.assertFalse(self.vm.routines)
        self.assertFalse(self.vm.server_routines)
        self.assertFalse(self.vm._dual_routine_names)
        self.assert_restored()

    def test_module_storage_and_context_calls_hidden_direct_eval_execute(self):
        bodies = ('Return Secret;', 'Return Eval("Secret");',
                  'Execute("X=Secret;"); Return X;',
                  'Return Context();', 'Return Eval("Context()");',
                  'Execute("X=Context();"); Return X;')
        for body in bodies:
            with self.subTest(body=body):
                vm = Interpreter()
                vm.execute('Var Secret; Secret=42;\n&AtServer\nVar Secret;\n'
                    'Function Context() Return Secret; EndFunction\n' + DUAL +
                    'Function D() ' + body + ' EndFunction\n'
                    '&AtServer\nFunction Server() Return D(); EndFunction\n'
                    '#If AtServer Then\nSecret=43;\n#EndIf')
                for caller in ('D()', 'Server()'):
                    with self.assertRaises(BSLError):
                        vm.execute(caller)
                    self.assertTrue(vm._has_module_context)
                self.assertEqual(vm.execute('Secret'), Decimal(42))
                vm.close()

    def test_forbidden_context_calls_rejected_before_argument_effects_in_all_lanes(self):
        calls = []
        self.vm.register_function('Effect', lambda: calls.append('effect'))
        self.vm.execute('''Function C(Val X) Return X; EndFunction
&AtServer
Function S(Val X) Return X; EndFunction
&AtClientAtServerNoContext
Function D(Val Which)
If Which=0 Then Return C(Effect()); EndIf;
Return S(Effect());
EndFunction
&AtServer
Function Server(Val Which) Return D(Which); EndFunction
&AtServerNoContext
Function NoContext(Val Which) Return D(Which); EndFunction
''')
        for caller in ('D', 'Server', 'NoContext'):
            for which in (0, 1):
                with self.subTest(caller=caller, which=which), self.assertRaises(BSLError):
                    self.vm.execute(f'{caller}({which})')
                self.assert_restored()
        self.assertEqual(calls, [])

    def test_implicit_thisobject_hidden_but_explicit_shadowing_legal(self):
        for body in ('Return ThisObject;', 'Return ЭтотОбъект;',
                     'Return Eval("ThisObject");', 'Execute("X=ThisObject;"); Return X;'):
            with self.subTest(body=body):
                self.vm.execute(DUAL + 'Function D() ' + body + ' EndFunction')
                with self.assertRaises(BSLError):
                    self.vm.execute('D()')
                self.assert_restored()
        self.vm.execute(DUAL + 'Function D(Val ThisObject) Return Eval("ThisObject"); EndFunction')
        self.assertEqual(self.vm.execute('D(7)'), Decimal(7))
        self.vm.execute(DUAL + 'Function D() Var ЭтотОбъект; ЭтотОбъект=8; Return ЭтотОбъект; EndFunction')
        self.assertEqual(self.vm.execute('D()'), Decimal(8))

    def test_exported_dual_receiver_calls_are_explicit_project_restriction(self):
        calls = []
        self.vm.register_function('Effect', lambda: calls.append(1))
        self.vm.execute(DUAL + 'Function D(Val X=1) Export Return X; EndFunction\nSaved=ThisObject;')
        self.assertEqual(self.vm.execute('D()'), Decimal(1))
        for call in ('ThisObject.D(Effect())', 'Saved.D(Effect())', 'Saved.D(,)'):
            with self.subTest(call=call), self.assertRaises(BSLError):
                self.vm.execute(call)
        self.assertEqual(calls, [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'M.bsl').write_text(DUAL + 'Function D(Val X) Export Return X; EndFunction', encoding='utf-8')
            self.vm.execute('// #Import M.bsl', str(root / 'Root.bsl'))
            with self.assertRaisesRegex(BSLError, 'через объект модуля'):
                self.vm.execute('M.D(Effect())')
        self.assertEqual(calls, [])

    def test_stored_receiver_does_not_allow_context_callee_from_dual(self):
        calls = []
        self.vm.register_function('Effect', lambda: calls.append(1))
        self.vm.execute('''Function C(Val X) Export Return X; EndFunction
&AtClientAtServerNoContext
Function D(Val Receiver) Return Receiver.C(Effect()); EndFunction
''')
        with self.assertRaisesRegex(BSLError, 'не может вызывать контекстную'):
            self.vm.execute('D(ThisObject)')
        self.assertEqual(calls, [])
        self.assert_restored()

    def test_module_receiver_cannot_restore_storage_capability(self):
        calls = []
        self.vm.register_function('Effect', lambda: calls.append(1))
        self.vm.execute('Var Secret Export; Secret=7;\n' + DUAL +
            'Function Inner(X) X=99; Return X; EndFunction')
        for body in ('Return Receiver.Secret;', 'Return Eval("Receiver.Secret");',
                     'Execute("X=Receiver.Secret;"); Return X;',
                     'Receiver.Secret=Effect(); Return 0;',
                     'Return Inner(Receiver.Secret);'):
            with self.subTest(body=body):
                self.vm.execute(DUAL + 'Function D(Val Receiver) ' + body + ' EndFunction')
                with self.assertRaisesRegex(BSLError, 'Хранилище модуля недоступно'):
                    self.vm.execute('D(ThisObject)')
                self.assertEqual(self.vm.execute('Secret'), Decimal(7))
                self.assert_restored()
        self.assertEqual(calls, [])

    def test_explicit_field_reference_bound_by_context_caller_keeps_alias(self):
        self.vm.execute('''Var Secret Export;
&AtClientAtServerNoContext
Procedure D(X) X=X+1; EndProcedure
Secret=7;
''')
        self.vm.execute('D(ThisObject.Secret);')
        self.assertEqual(self.vm.execute('Secret'), Decimal(8))
        self.assert_restored()

    def test_entry_argument_failure_does_not_leak_side_or_capability(self):
        self.vm.execute(DUAL + 'Function D(Val X) Return X; EndFunction')
        for call in ('D(1/0)', 'D()', 'D(1,2)'):
            with self.subTest(call=call), self.assertRaises(BSLError):
                self.vm.execute(call)
            self.assert_restored()

    def test_interleaved_async_callers_preserve_capability_diagnostics_and_storage(self):
        gates = {1: self.vm._scheduler.new_pending(), 2: self.vm._scheduler.new_pending()}
        seen = []
        contexts = []
        self.vm.register_function('Gate', lambda value: gates[int(value)])
        self.vm.register_function('Observe', lambda label: seen.append(
            (label, self.vm.execution_context, self.vm._has_module_context)))
        self.vm.register_function('Capture', lambda: contexts.append(self.vm._scheduler.active_context))
        self.vm.execute('''Var State;
&AtClientAtServerNoContext
Function D(X,Val Label,Val Fail)
Observe(Label); X=X+10; If Fail Then Raise "dual-error"; EndIf; Return X;
EndFunction
&AtServer
Function Server(Val Id)
X=Id; R=D(X,"server",False); Return X+R;
EndFunction
Async Function Work(Val Id)
X=Id; D(X,"before",False); State=State+1; Observe("client-before");
Await Gate(Id);
Try D(X,"after",True); Except Text=ErrorDescription(); EndTry;
Observe("client-after"); State=State+1;
Y=Server(Id); Capture(); Await 0;
Return New Structure("Value,Server,Text,State",X,Y,Text,State);
EndFunction
State=0; P=Work(1); Q=Work(2);
''')
        self.assertEqual(seen, [('before', 'client', False), ('client-before', 'client', True)] * 2)
        self.assertEqual(self.vm.variables['state'], Decimal(2))
        self.assert_restored()
        self.vm._scheduler.resolve(gates[2], None)
        self.vm.run_until_idle()
        self.vm._scheduler.resolve(gates[1], None)
        self.vm.run_until_idle()
        for name, identifier, state in (('p', 1, 4), ('q', 2, 3)):
            promise = self.vm.variables[name]
            self.assertEqual(promise.state, 'fulfilled')
            result = promise.result
            self.assertEqual(result.get('Value'), Decimal(identifier + 20))
            self.assertEqual(result.get('Server'), Decimal(2 * (identifier + 10)))
            self.assertIn('dual-error', result.get('Text'))
            self.assertEqual(result.get('State'), Decimal(state))
        self.assertEqual(seen[4:], [('after', 'client', False), ('client-after', 'client', True),
                                   ('server', 'server', False)] * 2)
        self.assertEqual(len(contexts), 2)
        self.assertIsNot(contexts[0], contexts[1])
        for context in contexts:
            self.assertEqual(context.locals, {})
            self.assertEqual(context.module_context_stack, [True])
            self.assertEqual(context.context_stack, ['client'])
            self.assertTrue(set(context.state) <= {self.vm})
        self.assert_restored()


if __name__ == '__main__':
    unittest.main()

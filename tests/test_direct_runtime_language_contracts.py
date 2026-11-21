"""Language checks formerly embedded in retired-engine instrumentation tests."""
import gc
import unittest
import weakref
from decimal import Decimal

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


class DirectRuntimeLanguageContractsTests(unittest.TestCase):
    def vm(self, *, allow_extensions=False):
        vm = Interpreter(allow_extensions=allow_extensions)
        self.addCleanup(vm.close)
        return vm

    def test_control_flow_in_source_and_prepared_execution(self):
        cases = (
            ('s=0;For i=1 To 3 Do For j=1 To 5 Do '
             'If j=2 Then Continue;EndIf;If j=4 Then Break;EndIf;'
             's=s+i*j;EndDo;EndDo;', {'s': 24}),
            ('a=New Array;a.Add(1);a.Add(2);s=0;'
             'For Each x In a Do j=0;While j<3 Do j=j+1;s=s+x;EndDo;EndDo;', {'s': 9}),
            ('x=0;Try Try x=1;Raise "inner";Except x=x+1;EndTry;'
             'Raise "outer";Except x=x+10;EndTry;', {'x': 12}),
            ('Function F(x) Try For i=1 To 3 Do x=x+1;'
             'If i=2 Then Return x;EndIf;EndDo;Except x=99;EndTry;EndFunction '
             'x=4;r=F(x);', {'x': 6, 'r': 6}),
            ('Function F() s=0;i=0;Try For i=1 To 3 Do '
             's=s+1;s=s/(2-i);EndDo;Except Return s;EndTry;EndFunction result=F();',
             {'result': 2}),
            ('s=0;For i=1 To 10 Do i=i+1;If i=4 Then Continue;EndIf;'
             'If i=8 Then Break;EndIf;s=s+i;EndDo;', {'i': 8, 's': 8}),
        )
        for source, expected in cases:
            for prepared in (False, True):
                with self.subTest(source=source, prepared=prepared):
                    vm = self.vm()
                    if prepared:
                        vm.execute_prepared(vm.prepare(source))
                    else:
                        vm.execute(source)
                    self.assertEqual({key: vm.variables[key] for key in expected}, expected)

    def test_cross_block_goto_retains_language_expectation(self):
        vm = self.vm()
        vm.execute('x=0;While True Do If True Then x=1;Goto ~done;EndIf;EndDo;~done:x=x+2;')
        self.assertEqual(vm.variables['x'], 3)

    def test_nested_label_goto_retains_language_expectation(self):
        vm = self.vm()
        vm.execute('x=0;If True Then ~again:x=x+1;If x<3 Then Goto ~again;EndIf;EndIf;')
        self.assertEqual(vm.variables['x'], 3)

    def test_partial_state_on_uncaught_arithmetic_error(self):
        vm = self.vm()
        with self.assertRaises(BSLRuntimeError) as raised:
            vm.execute('x=0;\nFor i=1 To 3 Do If i=2 Then x=x+1;z=1/0;EndIf;x=x+10;EndDo;',
                       'partial-state.bsl')
        self.assertEqual((raised.exception.source, raised.exception.line), ('partial-state.bsl', 2))
        self.assertEqual((vm.variables['i'], vm.variables['x']), (2, 11))
        self.assertNotIn('z', vm.variables)

    def test_omitted_default_and_indexed_by_reference_argument(self):
        vm = self.vm()
        vm.execute('Procedure F(x, Val y=2) x=x+y;EndProcedure '
                   'x=3;F(x,);a=New Array;a.Add(x);F(a[0],4);r=a[0];')
        self.assertEqual((vm.variables['x'], vm.variables['r']), (5, 9))

    def test_eval_and_execute_scopes_and_handler(self):
        vm = self.vm()
        output = []
        vm.output = output.append
        vm.execute('x=3;r=Eval("x+2");Execute "x=x+4;localonly=9;";'
                   'Try z=Eval("1/0");Except Message("caught");EndTry;')
        self.assertEqual((vm.variables['x'], vm.variables['r']), (7, 5))
        self.assertNotIn('localonly', vm.variables)
        self.assertNotIn('z', vm.variables)
        self.assertEqual(output, ['caught'])

    def test_retained_routine_defaults_and_values(self):
        vm = self.vm()
        vm.execute('Function F(Val x=7) Return (x+1);EndFunction')
        for _ in range(3):
            vm.execute('unrelated=99;')
        vm.execute('a=F();b=F(4);text="vm result _s _nodes";vm=text;')
        self.assertEqual((vm.variables['a'], vm.variables['b']), (8, 5))
        self.assertEqual(vm.variables['vm'], 'vm result _s _nodes')

    def test_distinct_operator_bindings(self):
        vm = self.vm()
        vm.execute('a=8+2;b=8-2;c=8*2;d=8/2;')
        self.assertEqual([vm.variables[k] for k in 'abcd'], [10, 6, 16, 4])

    def test_gc_state_unchanged_after_success_and_failure(self):
        original = gc.isenabled()
        try:
            for enabled in False, True:
                with self.subTest(gc_enabled=enabled):
                    (gc.enable if enabled else gc.disable)()
                    vm = self.vm()
                    vm.execute('s=0;For i=1 To 3 Do s=s+i;EndDo;')
                    self.assertEqual(vm.variables['s'], Decimal(6))
                    self.assertEqual(gc.isenabled(), enabled)
                    with self.assertRaises(BSLRuntimeError):
                        vm.execute('r=1/0;')
                    self.assertEqual(gc.isenabled(), enabled)
        finally:
            (gc.enable if original else gc.disable)()

    def test_discarded_result_released_after_handled_error(self):
        vm = self.vm(allow_extensions=True)
        refs = []
        seen = []

        class Payload:
            pass

        def make():
            value = Payload()
            refs.append(weakref.ref(value))
            return value

        def check():
            gc.collect()
            seen.append(refs[-1]() is None)

        vm.register_function('Make', make)
        vm.register_function('Check', check)
        vm.execute('Try Make();Raise "failure";Except x=1;EndTry;Check();')
        self.assertEqual(seen, [True])

    def test_for_upper_bound_is_evaluated_once(self):
        vm = self.vm()
        vm.execute('Function F(Val n=3) count=0;Var count;'
                   'For i=1 To n Do n=0;count=count+1;EndDo;'
                   'Return ?(False And 1/0,count/0,count*10+i);'
                   'EndFunction result=F();')
        self.assertEqual(vm.variables['result'], 34)

    def test_semantics_do_not_depend_on_python_tracing(self):
        import sys
        old = sys.gettrace()
        try:
            sys.settrace(lambda *args: None)
            vm = self.vm()
            vm.execute('Function F(Val n) Return n+1;EndFunction result=F(3);')
        finally:
            sys.settrace(old)
        self.assertEqual(vm.variables['result'], 4)

    def test_undefined_for_counter_bound_does_not_execute_loop(self):
        from yadinassi import BSLError
        vm = self.vm(allow_extensions=True)
        effects = []
        vm.register_function('Effect', lambda: effects.append(1))
        with self.assertRaisesRegex(BSLError, r'(?i)(i|присваивани)'):
            vm.execute('Function F() For i=i To 3 Do Effect();EndDo;Return i;'
                       'EndFunction result=F();')
        self.assertEqual(effects, [])
        self.assertNotIn('result', vm.variables)

    def test_single_registered_effect_and_result(self):
        vm = self.vm(allow_extensions=True)
        effects = []
        vm.register_function('Effect', lambda: effects.append(1) or 7)
        vm.execute('r=Effect();')
        self.assertEqual(effects, [1])
        self.assertEqual(vm.variables['r'], 7)

    def test_malformed_ast_does_not_call_the_host(self):
        from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
        from yadinassi.syntax import ast
        from yadinassi.syntax.parser import parse

        def malformed_target(program):
            program[1].target = program[1].value

        def omitted_value(program):
            program[1].value = ast.OmittedArgument(program[1].token)

        def statement_operand(program):
            program[1].value = ast.Group(program[1].token, program[0])

        def metadata_statement(program):
            program.append(ast.Parameter(program[1].token, 'p', True))

        for mutate in (malformed_target, omitted_value, statement_operand, metadata_statement):
            with self.subTest(case=mutate.__name__):
                vm = self.vm(allow_extensions=True)
                effects = []
                vm.register_function('Effect', lambda: effects.append(1))
                program = parse('Effect();x=1;', 'roles.bsl')
                mutate(program)
                with self.assertRaises(PythonDirectUnsupported):
                    vm.execute_program(program)
                self.assertEqual(effects, [])
                self.assertNotIn('x', vm.variables)

    def test_callable_can_return_array_without_copying_it(self):
        vm = self.vm()
        vm.execute('Function F(Val x) Return x;EndFunction '
                   'a=New Array;a.Add(3);result=F(a);')
        self.assertIs(vm.variables['result'], vm.variables['a'])

    def test_short_circuit_skips_unselected_expression(self):
        vm = self.vm()
        vm.execute('Function F(Val n) s=False AND 1/0=0;'
                   'Return ?(s,1/0,n+2);EndFunction result=F(8);')
        self.assertEqual(vm.variables['result'], 10)

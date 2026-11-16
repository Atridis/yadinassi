"""Contract gates for the new translated synchronous-routine specialization."""
import gc
import sys
import unittest
import weakref
from decimal import Decimal
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.owned_syntax import syntax_kind
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi.python_translation_expressions import ExpressionExecution
from yadinassi.python_translation_blocks import Execution


class PythonSyncRoutineContractTests(unittest.TestCase):
    def setUp(self):
        # Exercise eligibility/authority even for tiny fixtures; production uses
        # a static profitability threshold to avoid costly small-call leases.
        gate=patch.object(Engine,'MIN_SYNC_ROUTINE_NODES',0)
        gate.start();self.addCleanup(gate.stop)
    def test_default_tiny_call_avoids_added_lease(self):
        with patch.object(Engine,'MIN_SYNC_ROUTINE_NODES',32):
            vm=Interpreter(execution_backend='compiled-strict')
            vm.execute('Function F(Val x) Return x+1;EndFunction result=F(2);')
        self.assertEqual(vm.variables['result'],3)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls',0),0)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
    def pair(self, source, expected):
        for mode in ('interpreter', 'compiled-strict'):
            vm = Interpreter(execution_backend=mode)
            vm.execute(source)
            self.assertEqual(vm.variables['result'], expected)
            self.assertIsNone(vm.locals)
            if mode == 'compiled-strict':
                self.assertGreater(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)
                self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)
                self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls', 0), 0)
                self.assertTrue(vm._compiled().FORCE_PYTHON_TRANSLATION)

    def test_for_continue_break_counter_write_and_exit_value(self):
        self.pair('''Function F(Val n)
        sum=0;
        For i=1 To n Do
          If i=2 Then Continue;EndIf;
          If i=4 Then Break;EndIf;
          sum=sum+i;
        EndDo;
        Return sum*10+i;
        EndFunction result=F(8);''', 44)
        self.pair('''Function F() sum=0;
        For i=1 To 10 Do i=i+2;sum=sum+i;EndDo;
        Return sum*100+i;
        EndFunction result=F();''', 3013)

    def test_cached_bound_short_circuit_and_var_redeclaration(self):
        self.pair('''Function F(Val n=3)
        count=0;Var count;
        For i=1 To n Do n=0;count=count+1;EndDo;
        Return ?(False And 1/0,count/0,count*10+i);
        EndFunction result=F();''', 34)

    def test_while_nested_loop_and_early_return(self):
        self.pair('''Function F(Val n)
        i=0;sum=0;
        While i<n Do
          i=i+1;
          For j=1 To 2 Do
            If j=1 Then Continue;EndIf;
            sum=sum+i;
          EndDo;
          If i=3 Then Return sum;EndIf;
        EndDo;
        Return -1;
        EndFunction result=F(20);''', 6)

    def test_instrumented_boundaries_decline_specialization(self):
        source = 'Function F(Val n) r=0;For i=1 To n Do r=r+i;EndDo;Return r;EndFunction result=F(3);'
        for owner, name in ((Engine, 'verify_node'), (Execution, 'guard'),
                            (ExpressionExecution, 'leaf')):
            original = getattr(owner, name)
            seen = []
            def observed(*args, **kwargs):
                seen.append(1)
                return original(*args, **kwargs)
            with self.subTest(owner=owner.__name__, name=name), patch.object(owner, name, observed):
                vm = Interpreter(execution_backend='compiled-strict')
                vm.execute(source)
                self.assertEqual(vm.variables['result'], 6)
                self.assertTrue(seen)
                self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)

    def test_trace_declines_specialization(self):
        previous = sys.gettrace()
        vm = Interpreter(execution_backend='compiled-strict')
        try:
            sys.settrace(lambda *args: None)
            vm.execute('Function F(Val n) Return n+1;EndFunction result=F(3);')
        finally:
            sys.settrace(previous)
        self.assertEqual(vm.variables['result'], 4)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)

    def test_byref_and_opaque_service_stay_general_translated(self):
        for source, expected in (
            ('Procedure F(x) x=x+1;EndProcedure result=3;F(result);', 4),
            ('Function F(Val x) Return StrLen(x);EndFunction result=F("abc");', 3),
        ):
            vm = Interpreter(execution_backend='compiled-strict')
            vm.execute(source)
            self.assertEqual(vm.variables['result'], expected)
            self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)
            self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def test_error_location_matches_general_translated_and_frame_is_released(self):
        source = 'Function F(Val n)\n r=n+1;\n Return r/(n-n);\nEndFunction\nresult=F(2);'
        errors = []
        for instrumented in (False, True):
            vm = Interpreter(execution_backend='compiled-strict')
            if instrumented:
                vm.compiled_before = lambda node: None
            try:
                vm.execute(source, 'sync-error.bsl')
            except Exception as error:
                errors.append((type(error), str(error)))
            else:
                self.fail('division by zero was not raised')
            self.assertIsNone(vm.locals)
            self.assertEqual(vm._compiled()._active_frames, 0)
        self.assertEqual(errors[0], errors[1])

    def test_retained_specialization_does_not_pin_unrelated_payload(self):
        class Payload: pass
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('Function F(Val n) r=0;For i=1 To n Do r=r+i;EndDo;Return r;EndFunction x=0;')
        payload = Payload()
        reference = weakref.ref(payload)
        program[-1].value.value = payload
        vm.execute_program(program)
        del payload, program
        vm.variables.pop('x')
        gc.collect()
        self.assertIsNone(reference())
        vm.execute('other=1;')
        vm.execute('result=F(4);')
        self.assertEqual(vm.variables['result'], 10)
        self.assertGreater(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)

    def test_revoked_descendant_cannot_run_via_specialization(self):
        for kind in (ast.Binary, ast.Name, ast.Literal, ast.Assign, ast.Return):
            with self.subTest(kind=kind.__name__):
                vm = Interpreter(execution_backend='compiled-strict')
                vm.execute('Function F(Val n) r=n+1;Return r;EndFunction')
                engine = vm._compiled()
                node = next(plan.node for plan in engine._nodes.values() if syntax_kind(plan.node) is kind)
                del engine._nodes[id(node)]
                with self.assertRaises(CompiledUnsupported):
                    vm.execute('result=F(2);')
                self.assertNotIn('result', vm.variables)
                self.assertEqual(engine._active_frames, 0)

    def test_revoked_nested_block_provenance_cannot_be_coalesced_away(self):
        vm = Interpreter(execution_backend='compiled-strict')
        vm.execute('Function F(Val n) r=0;For i=1 To n Do r=r+i;EndDo;Return r;EndFunction')
        engine = vm._compiled()
        loop = next(plan.node for plan in engine._nodes.values() if syntax_kind(plan.node) is ast.For)
        del engine._owned.versions[id(loop.body)]
        with self.assertRaises(CompiledUnsupported):
            vm.execute('result=F(2);')
        self.assertNotIn('result', vm.variables)
        self.assertEqual(engine._active_frames, 0)

    def test_scalar_type_error_and_operator_matrix(self):
        expressions = ('x+1', '1+x', 'x-1', 'x*2', 'x/2', 'x%2', '-x',
                       'Not x', 'x=1', 'x<1', '?(x,1,2)', 'x And True', 'False Or x')
        for expression in expressions:
            for argument in ('2', 'True', 'False', '"a"', 'Undefined'):
                with self.subTest(expression=expression, argument=argument):
                    source = f'Function F(Val x) Return {expression};EndFunction result=F({argument});'
                    outcomes = []
                    for observed in (True, False):
                        vm = Interpreter(execution_backend='compiled-strict')
                        if observed:
                            vm.compiled_before = lambda node: None
                        try:
                            vm.execute(source, 'scalar-matrix.bsl')
                            outcomes.append(('value', vm.variables['result']))
                        except Exception as error:
                            outcomes.append((type(error), str(error)))
                        if not observed:
                            self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls'), 1)
                    self.assertEqual(outcomes[0], outcomes[1])

    def test_nonscalar_value_parameter_declines_specialization(self):
        vm = Interpreter(execution_backend='compiled-strict')
        vm.execute('Function F(Val x) Return x;EndFunction a=New Array;a.Add(3);result=F(a);')
        self.assertIs(vm.variables['result'], vm.variables['a'])
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

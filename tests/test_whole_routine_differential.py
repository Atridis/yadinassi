"""Whole-routine rollout matrix, not a claim of universal direct lowering.

Compare the explicit interpreter oracle and translated execution with the legacy
plain-routine option both disabled and enabled. That compatibility option no
longer selects an adapter. Preserve values/effects/errors, cleanup and no fallback.
"""
from decimal import Decimal, localcontext, getcontext
import unittest
from unittest.mock import patch
from yadinassi.compiled_backend import Engine
from yadinassi import Interpreter


class WholeRoutineDifferentialTests(unittest.TestCase):
    def execute(self, source, names, **options):
        # Each mode gets the same precision/traps and clean flags, not the
        # preceding mode's sticky Decimal state.
        with localcontext() as context:
            context.clear_flags()
            return self._execute(source, names, **options)

    def _execute(self, source, names, *, mode, host=False, hook=False, inputs=None):
        effects = []
        vm = Interpreter(output=lambda value: effects.append(('output', str(value))),
                         execution_backend='interpreter' if mode == 'oracle' else 'compiled-strict',
                         compiled_plain_routines=mode == 'translated-plain-option')
        try:
            vm.variables.update(inputs or {})
            if host:
                def tick(value):
                    effects.append(('host', str(value)))
                    return value + Decimal(1)
                vm.register_function('Tick', tick)
            if hook:
                # Both compiled paths must honour a live host policy. This is not
                # an interpreter instrumentation test or a direct-lowering witness.
                original = vm.compiled_before
                def before(node):
                    from yadinassi.owned_syntax import syntax_kind
                    kind = syntax_kind(node).__name__
                    effects.append(('before', kind))
                    if kind == 'Return':
                        raise ValueError('policy denies return')
                    return original(node)
                vm.compiled_before = before
            error = None
            try:
                vm.execute(source)
            except Exception as caught:
                error = (type(caught).__name__, str(caught))
            def capture(value):
                if value is None or type(value) in (str, bool, Decimal):
                    return value
                if hasattr(value, 'result'):
                    return ('promise', capture(value.result))
                raise AssertionError('select scalar controls, not lossy repr: ' + type(value).__name__)
            values = tuple((name, name in vm.variables, capture(vm.variables.get(name))) for name in names)
            stats = dict(vm.compiled_backend_stats)
            self.assertIsNone(vm.locals)
            self.assertEqual(vm.pending_promises, ())
            if mode != 'oracle':
                self.assertEqual(stats.get('interpreter_fallbacks', 0), 0)
                self.assertEqual(vm._compiled().active_frames, 0)
                self.assertEqual(stats.get('plain_adapter_blocks',0),0)
                self.assertGreater(stats.get('python_translated_blocks',0)+sum(stats.get('python_translated_node_kinds',{}).values()),0)
            flags = tuple(sorted(signal.__name__ for signal, set_flag in getcontext().flags.items() if set_flag))
            return (values, tuple(effects), error, flags), stats
        finally:
            vm.close()

    def pair(self, source, names=('r',), **options):
        expected, _ = self.execute(source, names, mode='oracle', **options)
        self.assertIsNone(expected[2], expected)
        for mode in ('translated-default', 'translated-plain-option'):
            with self.subTest(mode=mode):
                actual, stats = self.execute(source, names, mode=mode, **options)
                self.assertEqual(actual, expected)
        return stats

    @patch.object(Engine, "DETAILED_INLINE_STATS", True)
    def test_val_decimal_direct_witness_and_fractional_loop(self):
        stats = self.pair('''Function Sum(Val n)
s=0;For i=0.5 To n Do s=s+i;EndDo;Return s;
EndFunction r=Sum(3);''')
        self.assertGreater(stats.get('python_translated_node_kinds',{}).get('Return',0),0)

    def test_byref_alias_and_val_copy_do_not_change_call_order(self):
        self.pair('''Procedure Mutate(a,b,Val c)
a=a+1;b=b+2;c=c+100;
EndProcedure x=3;y=7;Mutate(x,x,y);r=x+y;''', ('r','x','y'))

    def test_defaults_omissions_and_nested_calls(self):
        self.pair('''Function Add(Val a,Val b=4) Return a+b;EndFunction
Function Outer(Val x) Return Add(Add(x),);EndFunction
r=Outer(2);''')

    def test_live_collection_alias_and_reference_writeback(self):
        self.pair('''Procedure Change(x) x=x+3;EndProcedure
Function Work(Val a) a.Add(4);Change(a[0]);Return a[0];EndFunction
items=New Array();alias=items;r=Work(items);n=alias.Count();v=alias[0];''', ('r','n','v'))

    def test_loop_control_goto_and_short_circuit(self):
        self.pair('''Function Work(Val n)
s=0;For i=1 To n Do
If i=2 Then Continue;EndIf;
If i=5 Then Break;EndIf;s=s+i;
EndDo;
If False And Tick(99)>0 Then s=999;EndIf;
Goto ~Done;s=888;~Done:Return s;
EndFunction r=Work(10);''', host=True)

    def test_dynamic_execute_eval_and_module_state(self):
        self.pair('''Var total;
Function Work(Val x)
Execute "total=total+1;";
Return Eval("x+total");EndFunction
total=3;r=Work(4);after=total;''', ('r','after'))

    def test_server_context_and_byref_copyback(self):
        self.pair('''&AtServer
Function Work(x,Val y) x=x+y;Return x*2;EndFunction
n=3;r=Work(n,4);''', ('r','n'))

    def test_async_and_await_keep_activation_cleanup(self):
        self.pair('''Async Function Work(Val n)
x=Await n;Return x+1;EndFunction
p=Work(4);''', ('p',))

    def test_opaque_effect_occurs_once_before_translated_result(self):
        self.pair('''Function Work(Val x)
y=Tick(x);Message(y);Return y+1;
EndFunction r=Work(4);''', host=True)

    def test_errors_and_decimal_context_match(self):
        sources = [
            'Function F(Val x)\nReturn x+1;\nEndFunction\nr=F(n);',
            'Function F(Val x)\nReturn x/0;\nEndFunction\nr=F(2);',
        ]
        # Use exact host Decimal input; no string conversion function can
        # reject first and mask arithmetic/error-location behavior.
        for source in sources:
            with self.subTest(source=source), localcontext() as context:
                context.prec = 7
                baseline, _ = self.execute(source, ('r',), mode='oracle', inputs={'n': Decimal('sNaN')})
                self.assertIsNotNone(baseline[2])
                for mode in ('translated-default', 'translated-plain-option'):
                    actual, _ = self.execute(source, ('r',), mode=mode, inputs={'n': Decimal('sNaN')})
                    self.assertEqual(actual, baseline)

    def test_wide_control_and_effect_order_matrix(self):
        cases = [
            ('Function F(Val x) While x<4 Do x=x+1;EndDo;Return x;EndFunction r=F(1);', ('r',)),
            ('Function F(Val x) Try x=1/0;Except x=7;EndTry;Return x;EndFunction r=F(1);', ('r',)),
            ('Function F(Val x) If x>1 Then Return x*2;Else Return x+1;EndIf;EndFunction r=F(3);', ('r',)),
            ('Function F(Val a) s=0;For Each x In a Do s=s+x;EndDo;Return s;EndFunction a=New Array();a.Add(2);a.Add(3);r=F(a);', ('r',)),
            ('Procedure F(x) x=x+1;Return; x=99;EndProcedure n=4;F(n);r=n;', ('r','n')),
            ('Function F(Val x) Return Tick(x)+Tick(x+1);EndFunction r=F(2);', ('r',)),
            ('Function F(Val x) Return x;EndFunction r=F(Tick(2));', ('r',)),
        ]
        for source, names in cases:
            with self.subTest(source=source):
                self.pair(source, names, host=True)

    def test_repeated_calls_observe_live_module_and_argument_state(self):
        self.pair('Var total;\nFunction F(Val x) total=total+1;Return x+total;EndFunction\ntotal=0;a=F(3);b=F(5);r=a+b;', ('a','b','r','total'))

    def test_live_policy_hook_cannot_be_skipped_by_translation(self):
        source = 'Function F(Val x) Return x+1;EndFunction r=F(4);'
        baseline, _ = self.execute(source, ('r',), mode='translated-default', hook=True)
        actual, stats = self.execute(source, ('r',), mode='translated-plain-option', hook=True)
        self.assertIsNotNone(baseline[2])
        self.assertEqual(actual, baseline)
        self.assertEqual(stats.get('plain_routine_calls', 0), 0)


if __name__ == '__main__':
    unittest.main()

"""Executable continuation coverage; host-injected pending signals are not native evidence."""
from decimal import Decimal, getcontext
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.async_runtime import Promise
from yadinassi.errors import BSLRuntimeError
from yadinassi.parser import parse


class AsyncRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def run_code(self, code):
        return self.vm.execute(code, 'async-test.bsl')

    def test_eager_call_and_yield_even_settled(self):
        self.run_code('''
        Async Function Leaf() Message("leaf"); Return 7; EndFunction
        Async Function Branch() Message("start"); x=Await Leaf(); Message("resume"); Return x; EndFunction
        p=Branch(); Message("caller");
        ''')
        self.assertEqual(self.output, ['start', 'leaf', 'caller', 'resume'])
        self.assertIsInstance(self.vm.variables['p'], Promise)
        self.assertEqual(self.vm.variables['p'].result, Decimal(7))

    def test_val_scalar_mutable_alias_and_default(self):
        self.run_code('''
        Async Function F(x, Val y, a, z=7)
            x=6; y=8; a[0]=a[0]+1; Return Await x+y+z;
        EndFunction
        x=5;y=4;a=New Array;a.Add(9);p=F(x,y,a);
        ''')
        self.assertEqual(self.vm.variables['x'], Decimal(5))
        self.assertEqual(self.vm.variables['y'], Decimal(4))
        self.assertEqual(self.vm.variables['a'].get(Decimal(0)), Decimal(10))
        self.assertEqual(self.vm.variables['p'].result, Decimal(21))

    def test_pending_host_signal_preserves_siblings_locals(self):
        signal = self.vm._scheduler.new_pending()
        self.vm.register_function('Signal', lambda: signal)
        self.run_code('''
        Var total;
        Async Function F(n) local=n; x=Await Signal(); total=total+1; Return local+x; EndFunction
        total=0;a=F(10);b=F(20);
        ''')
        self.assertEqual(self.vm.variables['a'].state, 'pending')
        self.assertEqual(self.vm.variables['total'], Decimal(0))
        self.assertTrue(self.vm.pending_promises)
        self.vm._scheduler.resolve(signal, Decimal(3))
        self.vm.run_until_idle()
        self.assertEqual(self.vm.variables['a'].result, Decimal(13))
        self.assertEqual(self.vm.variables['b'].result, Decimal(23))
        self.assertEqual(self.vm.variables['total'], Decimal(2))
        self.assertEqual(self.vm.pending_promises, ())
        self.assertIsNone(self.vm.locals)

    def test_nested_promise_adoption(self):
        self.run_code('''
        Async Function Inner() Return Await 31; EndFunction
        Async Function Outer() Return Inner(); EndFunction
        Async Procedure Main() x=Await Outer(); Message(x); EndProcedure
        Main();
        ''')
        self.assertEqual(self.output,['31'])

    def test_function_rejection_not_call_catch_repeat_await(self):
        self.run_code('''
        Async Function Bad() Raise("bad",ErrorCategory.ConfigurationError,"code","detail",Undefined); EndFunction
        Async Procedure Main()
          Try p=Bad(); Message("returned"); Except Message("wrong"); EndTry;
          For i=1 To 2 Do
            Try x=Await p; Except Message(ErrorInfo().Description); Message(ErrorInfo().Code); EndTry;
          EndDo;
        EndProcedure Main();
        ''')
        self.assertEqual(self.output,['returned','bad','code','bad','code'])

    def test_pending_rejection_and_bare_rethrow(self):
        signal=self.vm._scheduler.new_pending()
        self.vm.register_function('Signal',lambda:signal)
        self.run_code('''
        Async Function F()
          Try x=Await Signal(); Except y=Await 1; Raise; EndTry;
        EndFunction
        Async Procedure Main()
          Try x=Await F(); Except Message(ErrorDescription()); EndTry;
        EndProcedure Main();
        ''')
        self.vm._scheduler.reject(signal,BSLRuntimeError('pending failure','signal',2,1))
        self.vm.run_until_idle()
        self.assertEqual(self.output,['signal:2:1: pending failure'])

    def test_task_error_context_does_not_leak(self):
        self.run_code('''
        Async Function F(n)
          Try Raise n; Except x=Await 1; Return ErrorDescription(); EndTry;
        EndFunction
        Async Procedure Main()
          a=F("first"); b=F("second"); Message(Await a); Message(Await b);
        EndProcedure Main();
        ''')
        self.assertEqual([line.rsplit(': ',1)[-1] for line in self.output],['first','second'])
        self.assertEqual(self.vm._error_description(),'')

    def test_async_procedure_error_is_out_of_band(self):
        with self.assertRaisesRegex(BSLRuntimeError,'procedure failure'):
            self.run_code('''
            Async Procedure P() x=Await 1; Raise "procedure failure"; EndProcedure
            Try P(); Except Message("wrong"); EndTry; Message("returned");
            ''')
        self.assertEqual(self.output,['returned'])

    def test_argument_failure_stays_in_caller(self):
        self.run_code('''
        Async Function F(x) Return x; EndFunction
        Try p=F(1/0); Except Message("caught"); EndTry;
        ''')
        self.assertEqual(self.output,['caught'])

    def test_loops_return_continue_and_break(self):
        self.run_code('''
        Async Function F()
          sum=0;
          For i=1 To 5 Do
            x=Await i;
            If x=2 Then Continue; EndIf;
            If x=4 Then Break; EndIf;
            sum=sum+x;
          EndDo;
          Return sum;
        EndFunction p=F();
        ''')
        self.assertEqual(self.vm.variables['p'].result,Decimal(4))

    def test_goto_and_while_keep_continuation(self):
        self.run_code('''
        Async Function F()
          n=0; ~Again: n=n+Await 1;
          If n<3 Then Goto ~Again; EndIf;
          While n<5 Do n=n+Await 1; EndDo;
          Return n;
        EndFunction p=F();
        ''')
        self.assertEqual(self.vm.variables['p'].result,Decimal(5))

    def test_argument_and_assignment_side_effects_once(self):
        self.run_code('''
        Var count, a;
        Function Index() count=count+1; Return 0; EndFunction
        Function Add(x,y) Return x+y; EndFunction
        Async Function F()
          a[Index()]=Add(Await 2,Await 3); Return a[0];
        EndFunction
        count=0;a=New Array;a.Add(0);p=F();
        ''')
        self.assertEqual(self.vm.variables['count'],Decimal(1))
        self.assertEqual(self.vm.variables['p'].result,Decimal(5))

    def test_short_circuit_and_conditional(self):
        self.run_code('''
        Async Function F()
          x=False And Await Missing(); y=True Or Await Missing();
          Return ?(Await True,Await 9,Await Missing());
        EndFunction p=F();
        ''')
        self.assertEqual(self.vm.variables['p'].result,Decimal(9))

    def test_eval_execute_calls_work_without_inheriting_await_permission(self):
        self.run_code('''
        Async Function F() Return Await 9; EndFunction
        Async Procedure Main()
          p=Eval("F()"); Message(Await p);
          Try x=Eval("Await F()"); Except Message("eval blocked"); EndTry;
          Try Execute("x=Await F();"); Except Message("execute blocked"); EndTry;
        EndProcedure Main();
        ''')
        self.assertEqual(self.output,['9','eval blocked','execute blocked'])

    def test_import_shared_module_globals_separate_async_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'M.bsl').write_text('''
            Var total Export;
            Async Function F(n) Export
              own=n; x=Await 1; total=total+1; Return own+x;
            EndFunction total=0;
            ''',encoding='utf-8')
            self.vm.execute('''// #Импорт M.bsl
            Async Procedure Main()
              a=M.F(10);b=M.F(20);Message(Await a);Message(Await b);Message(M.total);
            EndProcedure Main();''',str(root/'Main.bsl'))
        self.assertEqual(self.output,['11','21','2'])

    def test_direct_ast_rejected_before_effects(self):
        program=parse('Message("wrong"); Async Function F() Return Await 1; EndFunction')
        program[-1].is_async=False
        with self.assertRaises(BSLError):self.vm.execute_program(program)
        self.assertEqual(self.output,[])

    def test_promise_no_constructor_or_public_members(self):
        self.run_code('''Async Function F() Return 1; EndFunction p=F();''')
        for code in ['New Promise','p.state','p.Resolve(3)']:
            with self.subTest(code=code),self.assertRaises(BSLError):self.run_code(code)

    def test_detached_server_activation_state_released(self):
        self.run_code('&AtServer\n        Function F(Val x) Try Raise "x"; Except Return x; EndTry; EndFunction\n        For i=1 To 100 Do x=F(i); EndDo;')
        self.assertEqual(self.vm._scheduler.active_context.locals,{})
        self.assertNotIn(True,[owner is not self.vm for owner in self.vm._scheduler.active_context.state])

    def test_blocked_lifecycle_never_claims_completion(self):
        signal=self.vm._scheduler.new_pending()
        self.vm.register_function('Signal',lambda:signal)
        self.run_code("Async Function F() Return Await Signal(); EndFunction p=F();")
        with self.assertRaisesRegex(BSLRuntimeError,'незавершенные'):
            self.vm.ensure_complete()
        self.vm.close()
        self.assertEqual(self.vm.pending_promises,())
        self.assertEqual(self.vm.variables['p'].state,'rejected')

    def test_promise_codecs_fail_as_language_errors(self):
        self.run_code("Async Function F() Return 1; EndFunction p=F();")
        for expression in ['p', 'Type("Promise")', 'New TypeDescription("Promise")']:
            with self.subTest(expression=expression):
                self.run_code('Try x=ValueToStringInternal('+expression+'); Except Message("blocked"); EndTry;')
        self.run_code('a=New Array;a.Add(p);Try x=ValueToStringInternal(a);Except Message("blocked");EndTry;')
        self.assertEqual(self.output,['blocked']*4)

    def test_exported_receiver_readiness_after_suspension(self):
        self.run_code('Var value Export;\n        Async Function F()\n          Try x=ThisObject.value; Except Message("not ready"); EndTry;\n          x=Await 1; Return ThisObject.value;\n        EndFunction value=4;p=F();')
        self.assertEqual(self.output,['not ready'])
        self.assertEqual(self.vm.variables['p'].result,Decimal(4))

    def test_decimal_precision_restored(self):
        original=getcontext().prec
        try:
            getcontext().prec=7
            self.vm.register_function('Precision',lambda:Decimal(getcontext().prec))
            self.run_code('Async Function F() before=Precision(); x=Await 1; Return before+Precision(); EndFunction p=F();')
            self.assertEqual(self.vm.variables['p'].result,Decimal(76))
            self.assertEqual(getcontext().prec,7)
        finally:getcontext().prec=original

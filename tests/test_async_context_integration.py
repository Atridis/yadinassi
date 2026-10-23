"""Local integration guards for continuations plus measured packet transport.

Suspended argument cases test composition of the implemented contracts, not new
native observations about async/server interactions.
"""
from decimal import Decimal
import unittest

from yadinassi import Interpreter


class AsyncContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def tearDown(self):
        self.vm.close()

    def test_crossing_named_val_late_expression_early_after_await(self):
        self.vm.execute('''
        Var x, calls;
        &AtServer
        Function Capture(Val Named, Val Expression, Val Token)
            Return Named*100+Expression;
        EndFunction
        Function Identity(Val Value) Return Value; EndFunction
        Async Function Effect()
            calls=calls+1; token=Await 0; x=9; Return 0;
        EndFunction
        Async Function Main() Return Capture(x,Identity(x),Await Effect()); EndFunction
        x=1;calls=0;p=Main();
        ''')
        self.assertEqual(self.vm.variables['p'].result, Decimal(901))
        self.assertEqual(self.vm.variables['calls'], Decimal(1))

    def test_async_actual_values_are_early_even_without_val(self):
        self.vm.execute('''
        Var x, calls;
        Async Function Capture(Named, Val Other, Token)
            Named=Named+1; Return Await (Named*100+Other);
        EndFunction
        Async Function Effect()
            calls=calls+1; token=Await 0; x=9; Return 0;
        EndFunction
        Async Function Main() Return Await Capture(x,x,Await Effect()); EndFunction
        x=1;calls=0;p=Main();
        ''')
        self.assertEqual(self.vm.variables['p'].result, Decimal(201))
        self.assertEqual(self.vm.variables['x'], Decimal(9))
        self.assertEqual(self.vm.variables['calls'], Decimal(1))

    def test_named_object_rebinding_and_expression_handle_during_suspension(self):
        self.vm.execute('''
        Var x, old;
        &AtServer
        Function Capture(Val Named, Val Expression, Val Token)
            Named.N=Named.N+1; Expression.N=Expression.N+1;
            Return Named.N*100+Expression.N;
        EndFunction
        Function Identity(Val Value) Return Value; EndFunction
        Async Function Effect()
            token=Await 0; old.N=3; x=New Structure("N",9); Return 0;
        EndFunction
        Async Function Main() Return Capture(x,Identity(x),Await Effect()); EndFunction
        x=New Structure("N",1);old=x;p=Main();
        ''')
        self.assertEqual(self.vm.variables['p'].result, Decimal(1004))
        self.assertEqual(self.vm.variables['x'].get('N'), Decimal(9))
        self.assertEqual(self.vm.variables['old'].get('N'), Decimal(3))

    def test_nonval_copyback_targets_original_storage_after_suspension(self):
        self.vm.execute('''
        Var x, old;
        &AtServer
        Procedure Change(Value, Val Token) Value.N=Value.N+1; EndProcedure
        Async Function Effect()
            token=Await 0; x=New Structure("N",9); Return 0;
        EndFunction
        Async Function Main() Change(x,Await Effect()); Return x.N; EndFunction
        x=New Structure("N",1);old=x;p=Main();
        ''')
        self.assertEqual(self.vm.variables['p'].result, Decimal(10))
        self.assertEqual(self.vm.variables['old'].get('N'), Decimal(1))

    def test_packet_failure_after_resume_keeps_all_caller_roots(self):
        self.vm.execute('''
        Var x,y,oldx,oldy;
        &AtServer
        Procedure Change(A,B,Val Token)
            A.N=43; B=New Structure("Unsupported",New Map);
        EndProcedure
        Async Function Main()
            Try Change(x,y,Await 0); Except Return "caught"; EndTry;
        EndFunction
        x=New Structure("N",1);y=New Structure("N",2);oldx=x;oldy=y;p=Main();
        ''')
        self.assertEqual(self.vm.variables['p'].result, 'caught')
        self.assertIs(self.vm.variables['x'], self.vm.variables['oldx'])
        self.assertIs(self.vm.variables['y'], self.vm.variables['oldy'])
        self.assertEqual(self.vm.variables['x'].get('N'), Decimal(1))
        self.assertEqual(self.vm.variables['y'].get('N'), Decimal(2))

    def test_server_diagnostics_detached_in_suspended_client_handlers(self):
        contexts = []
        self.vm.register_function('CaptureContext', lambda: contexts.append(
            self.vm._scheduler.active_context))
        self.vm.execute('''
        &AtServer
        Function Server(Val Value)
            Try Raise "server"; Except Return Value; EndTry;
        EndFunction
        Async Function F(Label)
            Try Raise Label; Except
                token=Await 0;
                For i=1 To 10 Do value=Server(New Structure("N",i)); EndDo;
                CaptureContext(); token=Await 0; Return ErrorInfo().Description;
            EndTry;
        EndFunction
        a=F("first");b=F("second");
        ''')
        self.assertEqual(self.vm.variables['a'].result, 'first')
        self.assertEqual(self.vm.variables['b'].result, 'second')
        self.assertEqual(len(contexts), 2)
        self.assertIsNot(contexts[0], contexts[1])
        for context in contexts:
            self.assertEqual(context.locals, {})
            self.assertEqual(set(context.state), {self.vm})
            self.assertEqual(context.state[self.vm]['_handled_errors'], [])

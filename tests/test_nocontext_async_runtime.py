"""Local coroutine composition guards, not additional native observations."""
from decimal import Decimal
import gc
import unittest
from unittest import mock
import weakref
from yadinassi import Interpreter
from yadinassi.async_runtime import AwaitRequest

class NoContextAsyncRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output=[]
        self.vm=Interpreter(self.output.append)
    def tearDown(self): self.vm.close()

    def test_spawn_copies_capability_and_await_restores_task_view(self):
        scheduler=self.vm._scheduler
        pending=scheduler.new_pending(); seen=[]
        scheduler.active_context.module_context_stack=[True,False]
        def task():
            seen.append(list(self.vm._module_context_stack))
            yield AwaitRequest(pending)
            seen.append(list(self.vm._module_context_stack))
            return Decimal(7)
        result=scheduler.start(task())
        scheduler.active_context.module_context_stack.pop()
        self.assertEqual(self.vm._module_context_stack,[True])
        scheduler.resolve(pending,None);self.vm.run_until_idle()
        self.assertEqual(seen,[[True,False],[True,False]])
        self.assertEqual(result.result,Decimal(7))
        self.assertEqual(self.vm._module_context_stack,[True])

    def test_interleaved_client_tasks_cross_and_restore_after_await(self):
        gates={1:self.vm._scheduler.new_pending(),2:self.vm._scheduler.new_pending()}
        seen=[]
        self.vm.register_function('Gate',lambda n:gates[int(n)])
        self.vm.register_function('Observe',lambda:seen.append((self.vm.execution_context,self.vm._has_module_context)))
        self.vm.execute('''&AtServerNoContext
Function N(X) Observe(); X=X+10; Return X; EndFunction
Async Function Work(Val Id)
X=Id; Await Gate(Id); R=N(X); Observe(); Await 0;
Return X*100+R;
EndFunction
P=Work(1);Q=Work(2);
''')
        self.assertEqual(seen,[])
        self.vm._scheduler.resolve(gates[2],None);self.vm.run_until_idle()
        self.vm._scheduler.resolve(gates[1],None);self.vm.run_until_idle()
        self.assertEqual(seen,[('server',False),('client',True)]*2)
        self.assertEqual(self.vm.variables['p'].result,Decimal(1111))
        self.assertEqual(self.vm.variables['q'].result,Decimal(1212))
        self.assertEqual(self.vm._module_context_stack,[True])
        self.assertEqual(self.vm._context_stack,['client'])

    def test_escaping_nocontext_after_await_has_no_copyout_or_owner_retention(self):
        gate=self.vm._scheduler.new_pending();self.vm.register_function('Gate',lambda:gate)
        refs=[];contexts=[];original=Interpreter._new_server_activation
        def create(owner,**kwargs):
            activation=original(owner,**kwargs);refs.append(weakref.ref(activation))
            contexts.append(owner._scheduler.active_context);return activation
        with mock.patch.object(Interpreter,'_new_server_activation',create):
            self.vm.execute('''&AtServerNoContext
Procedure N(X) X.N=99; Raise "no-context-error"; EndProcedure
Async Function Work()
X=New Structure("N",1);Await Gate();
Try N(X);Except Text=ErrorDescription();EndTry;
Await 0;Return New Structure("Value,Text",X.N,Text);
EndFunction
P=Work();
''')
            self.vm._scheduler.resolve(gate,None);self.vm.run_until_idle()
        result=self.vm.variables['p'].result
        self.assertEqual(result.get('Value'),Decimal(1));self.assertIn('no-context-error',result.get('Text'))
        gc.collect();self.assertTrue(refs);self.assertTrue(all(r() is None for r in refs))
        for context in contexts:
            self.assertEqual(context.locals,{})
            self.assertEqual(context.module_context_stack,[True])
            self.assertTrue(set(context.state)<={self.vm})
        self.assertTrue(self.vm._has_module_context)

    def test_initializer_failure_then_nocontext_after_await_recovers(self):
        self.vm.execute('''&AtServer
Function S() Return 1; EndFunction
&AtServerNoContext
Function N() Return 7; EndFunction
#If AtServer Then
Raise "initializer-error";
#EndIf
Async Function Work()
Await 0;Try S();Except EndTry;Await 0;Return N();
EndFunction
P=Work();
''')
        self.vm.run_until_idle()
        self.assertEqual(self.vm.variables['p'].result,Decimal(7))
        self.assertEqual(self.vm._module_context_stack,[True])
        self.assertEqual(self.vm._context_stack,['client'])

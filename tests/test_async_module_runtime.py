"""Local composition guards, not new native Async/server observations."""
from decimal import Decimal
import gc
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import weakref

from yadinassi import Interpreter


class AsyncModuleRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def tearDown(self):
        self.vm.close()

    def test_suspended_actual_then_initializer_failure_has_no_copyout_or_retention(self):
        signal = self.vm._scheduler.new_pending()
        self.vm.register_function('Signal', lambda: signal)
        activations = []
        contexts = []
        original = Interpreter._new_server_activation
        def create(owner):
            activation = original(owner)
            activations.append(weakref.ref(activation))
            contexts.append(owner._scheduler.active_context)
            return activation
        with mock.patch.object(Interpreter, '_new_server_activation', create):
            self.vm.execute('''
Var x, effects;
&AtServer
Var State;
&AtServer
Procedure Change(Value, Val Token) Value.N=99; Message("body"); EndProcedure
#If AtServer Then
State=42; Raise "initializer";
#EndIf
Async Function Effect()
    token=Await Signal(); effects=effects+1; x.N=7; Return 0;
EndFunction
Async Function Main()
    Try Change(x,Await Effect()); Except Return ErrorInfo().Description; EndTry;
EndFunction
x=New Structure("N",1);effects=0;p=Main();
''')
            root = self.vm.variables['x']
            self.assertEqual(activations, [])
            self.assertEqual(self.vm.variables['p'].state, 'pending')
            self.vm._scheduler.resolve(signal, Decimal(0))
            self.vm.run_until_idle()
        self.assertEqual(self.vm.variables['p'].result, 'initializer')
        self.assertIs(self.vm.variables['x'], root)
        self.assertEqual(root.get('N'), Decimal(7))
        self.assertEqual(self.vm.variables['effects'], Decimal(1))
        self.assertEqual(self.output, [])
        self.assertEqual(len(activations), 1)
        gc.collect()
        self.assertTrue(all(ref() is None for ref in activations))
        for context in contexts:
            self.assertEqual(context.locals, {})
            self.assertTrue(set(context.state) <= {self.vm})
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execution_context, 'client')

    def test_module_parameter_collision_nested_sharing_and_repeated_reset_after_await(self):
        self.vm.execute('''
&AtServer
Var S;
&AtServer
Function Nested() S=S+1; Return S; EndFunction
&AtServer
Function Read(Val S) Return Nested()*100+S; EndFunction
#If AtServer Then
If S<>Undefined Then Raise "retained module"; EndIf;
S=40; S=Nested();
#EndIf
Async Function Main()
    token=Await 0; a=Read(10); token=Await 0; Return a*10000+Read(20);
EndFunction
p=Main();
''')
        self.assertEqual(self.vm.variables['p'].result, Decimal(42104220))
        self.assertNotIn('s', self.vm.variables)

    def test_initializer_failure_then_fresh_success_during_sibling_handlers(self):
        calls = []
        contexts = []
        def fail_once():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError('first initialization')
        self.vm.register_function('FailOnce', fail_once)
        self.vm.register_function('Capture', lambda: contexts.append(self.vm._scheduler.active_context))
        self.vm.execute('''
&AtServer
Var S;
&AtServer
Function Read() Return S; EndFunction
#If AtServer Then
If S<>Undefined Then Raise "retained"; EndIf;
S=42; FailOnce();
Try Raise "server handled"; Except EndTry;
#EndIf
Async Function Main(Label)
    Try Raise Label; Except
        token=Await 0;
        Try value=Read(); Except value=0; EndTry;
        Capture(); token=Await 0;
        Return ErrorInfo().Description;
    EndTry;
EndFunction
a=Main("first");b=Main("second");
''')
        # The first client's nested handler intentionally clears its own outer
        # diagnostic; it must not clear the sibling task's outer diagnostic.
        self.assertEqual(self.vm.variables['a'].result, '')
        self.assertEqual(self.vm.variables['b'].result, 'second')
        self.assertEqual(len(calls), 2)
        for context in contexts:
            self.assertEqual(context.locals, {})
            self.assertEqual(set(context.state), {self.vm})
            self.assertEqual(context.state[self.vm]['_handled_errors'], [])

    def test_imported_modules_keep_client_state_and_fresh_server_state_separate(self):
        source = '''
Var Count;
&AtServer
Var S;
&AtServer
Function Nested() S=S+1; Return S; EndFunction
&AtServer
Function Read() Return Nested(); EndFunction
#If AtServer Then
S=__BASE__;
#EndIf
Async Function Run() Export
    token=Await 0; Count=Count+1; Return Read()*100+Count;
EndFunction
Count=0;
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, base in (('A', '10'), ('B', '20')):
                (root / (name+'.bsl')).write_text(source.replace('__BASE__', base), encoding='utf-8')
            self.vm.execute('''// #Import A.bsl
// #Import B.bsl
pa=A.Run();pb=B.Run();pc=A.Run();''', str(root/'Main.bsl'))
        self.assertEqual([self.vm.variables[name].result for name in ('pa','pb','pc')],
                         [Decimal(1101), Decimal(2101), Decimal(1102)])
        self.assertNotIn('count', self.vm.variables)
        self.assertNotIn('s', self.vm.variables)

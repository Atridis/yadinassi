from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectNoContextTests(unittest.TestCase):
    def test_source_ast_prepared_persistent_context_and_copyback(self):
        from yadinassi.syntax.parser import parse
        source='''&AtServerNoContext
Function F(X,Val N=2) X=X+N;Return Scope();EndFunction
X=3;R=F(X);'''
        for route in ('source','ast','prepared'):
            vm=Interpreter(allow_extensions=True);vm.register_function('Scope',lambda:vm.execution_context+':'+str(vm._has_module_context))
            if route=='source':vm.execute(source)
            elif route=='ast':vm.execute_program(parse(source))
            else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual((vm.variables['x'],vm.variables['r']),(5,'server:False'))
            vm.execute('F(X,3);');self.assertEqual(vm.variables['x'],8)
            self.assertEqual(vm.execution_context,'client');self.assertTrue(vm._has_module_context)

    def test_no_server_or_client_globals_and_no_initialization(self):
        vm=Interpreter(compilation_profile='managed-thick-file', allow_extensions=True);effects=[];vm.register_function('Tick',lambda:effects.append(1))
        vm.execute('''Var Client;Client=9;
&AtServer
Var N;
&AtServer
Function Contextual() Return N;EndFunction
&AtServerNoContext
Function ReadN() Return N;EndFunction
&AtServerNoContext
Function ReadClient() Return Client;EndFunction
#If AtServer Then
N=100;Tick();
#EndIf
''')
        for name in ('ReadN','ReadClient'):
            with self.assertRaisesRegex(BSLRuntimeError, "не определена"):vm.execute(name+'();')
            self.assertEqual(effects,[]);self.assertTrue(vm._has_module_context)
        vm.execute('R=Contextual();');self.assertEqual(vm.variables['r'],100);self.assertEqual(effects,[1])

    def test_same_side_nocontext_updates_ref_even_on_escape(self):
        vm=Interpreter();vm.execute('''&AtServerNoContext
Procedure Change(X) X=9;Raise "fail";EndProcedure
&AtServer
Function Caller()
 X=1;Try Change(X);Except Caught=True;EndTry;
 Return X;
EndFunction
R=Caller();''')
        self.assertEqual(vm.variables['r'],9);self.assertTrue(vm._has_module_context)
        vm.execute('X=1;Try Change(X);Except Caught=True;EndTry;')
        self.assertEqual(vm.variables['x'],1)

    def test_contextual_and_client_calls_from_nocontext_refuse_before_args(self):
        for target in ('Contextual','ClientCall'):
            vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1))
            vm.execute('Function ClientCall(Val X) Return X;EndFunction\n&AtServer\nFunction Contextual(Val X) Return X;EndFunction\n&AtServerNoContext\nFunction N() Return '+target+'(Effect());EndFunction')
            with self.assertRaises(BSLRuntimeError):vm.execute('N();')
            self.assertEqual(effects,[]);self.assertTrue(vm._has_module_context)

    def test_nested_separate_nocontext_modules_preserve_byref(self):
        vm=Interpreter();vm.execute('&AtServerNoContext\nProcedure Add(X) X=X+1;EndProcedure')
        vm.execute('&AtServerNoContext\nFunction F(X) Add(X);Return X;EndFunction')
        vm.execute('X=1;R=F(X);');self.assertEqual((vm.variables['x'],vm.variables['r']),(2,2))

    def test_normal_initializer_can_call_nocontext_without_recursive_init(self):
        vm=Interpreter(compilation_profile='managed-thick-file')
        vm.execute('''&AtServer
Var N;
&AtServerNoContext
Function Seed() Return 42;EndFunction
&AtServer
Function Read() Return N;EndFunction
#If AtServer Then
N=Seed();
#EndIf
R=Read();''')
        self.assertEqual(vm.variables['r'],42)

    def test_nocontext_only_code_does_not_acquire_later_module_names(self):
        vm=Interpreter();vm.execute('&AtServerNoContext\nFunction F() Return 7;EndFunction')
        vm.execute('&AtServer\nVar Later;\n&AtServer\nFunction Read() Return Later;EndFunction')
        vm.execute('R=F();');self.assertEqual(vm.variables['r'],7)

    def test_revocation_and_module_capability_tampering_restore_scopes(self):
        for action in ('close','context','reset'):
            vm=Interpreter(allow_extensions=True)
            def change():
                if action=='close':vm.close()
                elif action=='reset':vm.cancel_pending()
                else:vm._module_context_stack[-1]=True
            vm.register_function('Change',change)
            vm.execute('&AtServerNoContext\nProcedure F(X) X=9;Change();EndProcedure X=1;')
            if action=='reset':
                with patch.object(vm._scheduler,'reset',wraps=vm._scheduler.reset) as reset:
                    with self.assertRaisesRegex(RuntimeError,'^Cannot reset an active scheduler$') as caught:
                        vm.execute('F(X);')
                    self.assertIs(type(caught.exception),RuntimeError)
                    reset.assert_not_called()
            else:
                with self.assertRaises(BoundaryViolation):vm.execute('F(X);')
            self.assertEqual(vm.variables['x'],1);self.assertTrue(vm._has_module_context)
            self.assertEqual(vm.execution_context,'client')

    def test_original_nocontext_witness_matches_native_projection(self):
        text=Path('scripts/native_1c_bootstrap/client_probe.bsl').read_text(encoding='utf-8')
        source=text.split('// BEGIN bounded no-context witness\n',1)[1].split('// BEGIN bounded dual witness',1)[0]
        vm=Interpreter(compilation_profile='managed-thick-file')
        vm.execute(source)
        # Complete native core projection pinned in test_native_nocontext_measurement.
        rows=list(vm.execute('RunNoContextProbe()'))
        self.assertEqual(rows,['nocontext.core.v3',12,22,0,12,2,True,16,True,6,14,14,True,7,18])
        for slot in (6,8,12):
            self.assertIs(rows[slot],True)

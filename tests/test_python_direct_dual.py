from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

DUAL='''&AtClientAtServerNoContext
Function F(X,Val N=2)
 X=X+N;
 Return Scope();
EndFunction
&AtServer
Function S() X=1;Return F(X);EndFunction
'''

class DirectDualTests(unittest.TestCase):
    def test_source_ast_prepared_persistent_select_side_without_vm(self):
        for route in ('source','ast','prepared'):
            vm=Interpreter(allow_extensions=True);vm.register_function('Scope',lambda:vm.execution_context+':'+str(vm._has_module_context))
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(DUAL)
                elif route=='ast':vm.execute_program(parse(DUAL))
                else:vm.execute_prepared(vm.prepare(DUAL))
                vm.execute('X=1;R=F(X);T=S();')
            self.assertEqual((vm.variables['x'],vm.variables['r'],vm.variables['t']),(3,'client:False','server:False'))
            self.assertEqual(vm._module_context_stack,[True])

    def test_original_positive_operation_preserves_side_masks_aliases(self):
        source=Path('scripts/native_1c_bootstrap/client_probe.bsl').read_text(encoding='utf-8').split('// BEGIN bounded dual witness\n',1)[1].split('// BEGIN bounded Date Null measurement',1)[0]
        outputs=[]
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(compilation_profile='managed-thick-file',execution_backend=backend)
            vm.execute(source)
            vm.execute('X=1;A=New Array;A.Add(2);R=DualProbeOperation(X,A,False);M=R.Mask;R.Container[0]=32;V=A[0];Y=X;')
            outputs.append((vm.variables['m'],vm.variables['v'],vm.variables['y']))
        self.assertEqual(outputs,[(0,32,12),(0,32,12)])

    def test_profile_branches_for_each_side(self):
        vm=Interpreter()
        vm.execute('''&AtClientAtServerNoContext
Function F()
 N=0;
#If Client Then
 N=N+4;
#EndIf
#If Server Then
 N=N+8;
#EndIf
 Return N;
EndFunction
&AtServer
Function S() Return F();EndFunction
&AtServerNoContext
Function N() Return F();EndFunction
A=F();B=S();C=N();''')
        self.assertEqual([vm.variables[k] for k in ('a','b','c')],[4,8,8])

    def test_same_side_alias_and_error_keep_writes(self):
        vm=Interpreter();vm.execute('''&AtClientAtServerNoContext
Procedure Change(X,Val A) X=9;A[0]=7;Raise "dual-error";EndProcedure
X=1;A=New Array;A.Add(2);Try Change(X,A);Except Caught=True;EndTry;''')
        self.assertEqual(vm.variables['x'],9);self.assertEqual(vm.variables['a'],[7])

    def test_no_module_globals_and_no_initializer(self):
        vm=Interpreter(compilation_profile='managed-thick-file', allow_extensions=True);effects=[];vm.register_function('Tick',lambda:effects.append(1))
        vm.execute('''Var X;X=5;
&AtServer
Var Z;
&AtServer
Function S() Return Z;EndFunction
&AtClientAtServerNoContext
Function F() Return X;EndFunction
#If AtServer Then
Z=100;Tick();
#EndIf
''')
        with self.assertRaisesRegex(BSLRuntimeError, "не определена"):vm.execute('F();')
        self.assertEqual(effects,[])

    def test_contextual_targets_refuse_before_argument_effects(self):
        for target in ('C','S'):
            vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1))
            vm.execute('Function C(Val X) Return X;EndFunction\n&AtServer\nFunction S(Val X) Return X;EndFunction\n&AtClientAtServerNoContext\nFunction F() Return '+target+'(Effect());EndFunction')
            with self.assertRaises(BSLRuntimeError):vm.execute('F();')
            self.assertEqual(effects,[])

    def test_nested_persistent_dual_calls(self):
        vm=Interpreter();vm.execute('&AtClientAtServerNoContext\nProcedure Add(X) X=X+1;EndProcedure')
        vm.execute('&AtClientAtServerNoContext\nProcedure F(X) Add(X);EndProcedure')
        vm.execute('X=1;F(X);');self.assertEqual(vm.variables['x'],2)

    def test_close_reset_and_context_tampering_restore_root(self):
        for action in ('close','reset','context'):
            vm=Interpreter(allow_extensions=True)
            def change():
                if action=='close':vm.close()
                elif action=='reset':vm.cancel_pending()
                else:vm._module_context_stack[-1]=True
            vm.register_function('Change',change)
            vm.execute('&AtClientAtServerNoContext\nProcedure F() Change();EndProcedure')
            if action=='reset':
                with patch.object(vm._scheduler,'reset',wraps=vm._scheduler.reset) as reset:
                    with self.assertRaisesRegex(RuntimeError,'^Cannot reset an active scheduler$') as caught:
                        vm.execute('F();')
                    self.assertIs(type(caught.exception),RuntimeError)
                    reset.assert_not_called()
            else:
                with self.assertRaises(BoundaryViolation):vm.execute('F();')
            self.assertEqual(vm._module_context_stack,[True]);self.assertEqual(vm.execution_context,'client')

    def test_malformed_pairs_refuse_before_effects(self):
        source='Effect=1;\n&AtClientAtServerNoContext\nFunction F(X) Return X;EndFunction'
        for mutation in ('missing','side','signature','token'):
            tree=parse(source);left,right=tree[-2:]
            if mutation=='missing':tree.pop()
            elif mutation=='side':right.execution_context='client'
            elif mutation=='signature':right.parameters[0].by_value=True
            else:
                from dataclasses import replace
                right.token=replace(right.token,line=right.token.line+1)
            vm=Interpreter()
            with self.assertRaises(PythonDirectUnsupported):vm.execute_program(tree)
            self.assertEqual(vm.variables,{})

    def test_original_dual_witness_matches_control(self):
        source=Path('scripts/native_1c_bootstrap/client_probe.bsl').read_text(encoding='utf-8').split('// BEGIN bounded dual witness\n',1)[1].split('// BEGIN bounded Date Null measurement',1)[0]
        rows=[]
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(compilation_profile='managed-thick-file',execution_backend=backend)
            vm.execute(source);rows.append(list(vm.execute('CollectDualDirectiveProbe()')))
        self.assertEqual([len(row) for row in rows],[9,9]);self.assertEqual(*rows)

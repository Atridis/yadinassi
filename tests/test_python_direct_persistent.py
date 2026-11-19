"""Persistent routine code binds to fresh direct execution state, never a VM call."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse


class PersistentDirectTests(unittest.TestCase):
    def test_client_state_byref_default_and_recursion_without_vm_dispatch(self):
        vm=Interpreter(compilation_profile='managed-thick-file')
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy call')):
            vm.execute('Var Total;Total=0;Procedure Add(X,Val N=2) X=X+N;Total=Total+X;EndProcedure Function Fact(Val N) If N=0 Then Return 1;EndIf;Return N*Fact(N-1);EndFunction')
            vm.execute('X=3;Add(X);R=Fact(5);')
            vm.execute('Add(X,3);')
        self.assertEqual((vm.variables['x'],vm.variables['total'],vm.variables['r']),(8,13,120))

    def test_one_compile_and_code_only_persistent_plan(self):
        from yadinassi.execution.direct import python_direct
        for prepared in (False,True):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',wraps=python_direct._compile) as compile_module:
                if prepared:vm.execute_prepared(vm.prepare('Var N;N=2;Function F() Return N;EndFunction'))
                else:vm.execute('Var N;N=2;Function F() Return N;EndFunction')
                self.assertEqual(compile_module.call_count,1)
            stored=vm._direct_routine_modules['f'].plan
            self.assertIsNone(stored.last_state);self.assertIsNone(stored.output)
            vm.execute('N=3;R=F();');self.assertEqual(vm.variables['r'],3)
            self.assertIsNone(stored.last_state);self.assertIsNone(stored.output)

    def test_module_statements_are_not_replayed(self):
        vm=Interpreter();vm.execute('Var N;N=10;Function Read() Return N;EndFunction')
        vm.execute('N=20;R=Read();');self.assertEqual(vm.variables['r'],20)

    def test_live_host_registry_and_globals_are_rebound(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Host',lambda:Decimal(1))
        vm.execute('Var N;N=2;Function Read() Return N+Host();EndFunction')
        vm.execute('R=Read();');self.assertEqual(vm.variables['r'],3)
        vm.register_function('Host',lambda:Decimal(5));vm.variables['n']=Decimal(10)
        vm.execute('R=Read();');self.assertEqual(vm.variables['r'],15)

    def test_deleted_global_is_not_reinitialized_by_binding(self):
        vm=Interpreter(allow_extensions=True);vm.execute('Var N;N=3;Function Read() Return N;EndFunction')
        vm.register_function('Drop',lambda:vm.variables.pop('n'))
        with self.assertRaisesRegex(BSLRuntimeError,'не определена'):vm.execute('Drop();R=Read();')
        self.assertNotIn('n',vm.variables);self.assertNotIn('r',vm.variables)

    def test_byref_partial_effect_and_definition_source_error(self):
        vm=Interpreter();vm.execute('Procedure Fail(X)\n X=X+1;\n R=1/0;\nEndProcedure',source='definition.bsl')
        with self.assertRaises(BSLRuntimeError) as caught:vm.execute('X=4;Fail(X);',source='caller.bsl')
        self.assertEqual(vm.variables['x'],5)
        self.assertIn('definition.bsl:3:',str(caught.exception))

    def test_separate_modules_and_prepared_caller_use_current_definition(self):
        vm=Interpreter();vm.execute('Function F() Return 1;EndFunction')
        vm.execute('Function G() Return F()+1;EndFunction')
        caller=vm.prepare('R=G();');vm.execute_prepared(caller);self.assertEqual(vm.variables['r'],2)
        vm.execute('Function F() Return 5;EndFunction')
        vm.execute_prepared(caller);self.assertEqual(vm.variables['r'],6)

    def test_partial_redefinition_of_joint_module_fails_explicitly(self):
        vm=Interpreter();vm.execute('Function F() Return 1;EndFunction Function G() Return F();EndFunction')
        vm.execute('Function F() Return 9;EndFunction')
        with self.assertRaisesRegex(PythonDirectUnsupported,'partially replaced'):vm.execute('Effect=1;R=G();')
        self.assertNotIn('effect',vm.variables)

    def test_profile_layout_and_constructor_changes_refuse_before_effects(self):
        for change in ('profile','layout','constructor'):
            vm=Interpreter(allow_extensions=True);vm.execute('Function F() Return New Array;EndFunction')
            if change=='profile':vm._compilation_profile='managed-thick-file'
            elif change=='layout':vm.execute('Var Later;')
            else:vm.register_type('Array',lambda:[])
            with self.subTest(change=change),self.assertRaises(PythonDirectUnsupported):vm.execute('Effect=1;F();')
            self.assertNotIn('effect',vm.variables)

    def test_prepared_declarations_are_owned_and_portable_between_owners(self):
        source=parse('Var N;Function F() Return N;EndFunction')
        first=Interpreter();plan=first.prepare_program(source);source.clear()
        for value in (3,7):
            vm=Interpreter();vm.execute_prepared(plan);vm.variables['n']=Decimal(value)
            vm.execute('R=F();');self.assertEqual(vm.variables['r'],value)

    def test_argument_and_procedure_value_errors_are_catchable(self):
        vm=Interpreter();vm.execute('Procedure P(X) X=X+1;EndProcedure Function F(Val X) Return X;EndFunction')
        vm.execute('Try R=P(1);Except A=True;EndTry;Try R=F();Except B=True;EndTry;Try R=F(1,2);Except C=True;EndTry;')
        self.assertEqual([vm.variables[k] for k in ('a','b','c')],[True]*3)

    def test_arity_rejection_precedes_argument_effects(self):
        vm=Interpreter(allow_extensions=True);effects=[]
        vm.register_function('Arg',lambda:effects.append(1) or Decimal(1))
        vm.execute('Function F(Val X) Return X;EndFunction')
        vm.execute('Try F(Arg(),Arg());Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught']);self.assertEqual(effects,[])

    def test_indirect_host_function_call_is_unchanged(self):
        from yadinassi.types.values import HostFunction
        vm=Interpreter(allow_extensions=True);vm.register_function('Get',lambda:HostFunction('F',lambda:Decimal(7)))
        self.assertEqual(vm.execute('Get()();'),7)

    def test_prospective_registry_and_layout_refuse_before_effects(self):
        for prepared in (False,True):
            for source in ('Function F() Return 9;EndFunction Effect=1;R=G();',
                           'Var Later;Effect=1;R=G();'):
                vm=Interpreter();vm.execute('Function F() Return 1;EndFunction Function G() Return F();EndFunction')
                with self.subTest(prepared=prepared,source=source):
                    with self.assertRaises(PythonDirectUnsupported):
                        if prepared:vm.execute_prepared(vm.prepare(source))
                        else:vm.execute(source)
                    self.assertNotIn('effect',vm.variables)
                    self.assertNotIn('later',vm.module_names)
                    vm.execute('R=G();');self.assertEqual(vm.variables['r'],1)

    def test_actual_unchanged_regex_helpers_persist_after_initial_replay(self):
        output=[];vm=Interpreter(output.append,compilation_profile='managed-thick-file')
        vm.execute(Path('integrational_tests/measurements/regex_family.bsl').read_text())
        original=output.copy();self.assertEqual(len(original),42)
        vm.execute('RFObserve(7);RFObserve(22);')
        self.assertEqual(output[-2:],[original[8],original[23]])
        self.assertEqual(len(output),44)

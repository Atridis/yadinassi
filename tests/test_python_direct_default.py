import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.python_direct import PythonDirectUnsupported

class PythonDirectDefaultTests(unittest.TestCase):
 def test_default_without_experimental_environment(self):
  with patch.dict(os.environ,{},clear=True):
   vm=Interpreter();self.assertEqual(vm.execution_backend,'python-direct')
   vm.execute('a=New Array;a.Add(2);r=a[0]+1;')
   self.assertEqual(vm.variables['r'],3);self.assertIs(type(vm.variables['a']),list)
   self.assertEqual(vm.execution_backend_stats['python_direct_modules'],1)
   self.assertEqual(vm.execution_backend_stats['fallback'],0)
 def test_api_existing_source_functions_and_host_output(self):
  output=[];vm=Interpreter(output.append)
  vm.execute('Function F(Val x) Return x+1;EndFunction r=F(2);Message(r);')
  self.assertEqual(output,['3'])
 def test_execute_program_does_not_reparse_or_prepare_legacy_engine(self):
  vm=Interpreter();program=parse('r=2+3;')
  with patch('yadinassi.experimental_naked_collections.parse',side_effect=AssertionError('reparsed')),patch.object(vm,'_compiled',side_effect=AssertionError('legacy')):
   vm.execute_program(program)
  self.assertEqual(vm.variables['r'],5)
 def test_repeated_variables_and_declared_globals(self):
  vm=Interpreter();original=vm.variables
  vm.execute('Var x;x=1;');vm.execute('Function F() x=x+1;Return x;EndFunction r=F();')
  self.assertIs(vm.variables,original);self.assertEqual(vm.variables['r'],2)
  vm.execute('x=x+1;');self.assertEqual(vm.variables['x'],3)
 def test_cross_execute_routine_uses_direct_definition(self):
  vm=Interpreter();vm.execute('Function F() Return 1;EndFunction')
  vm.execute('x=8;r=F();')
  self.assertEqual((vm.variables['x'],vm.variables['r']),(8,1))
 def test_observable_callback_values(self):
  vm=Interpreter();vm.register_function('Write',lambda:vm.variables.__setitem__('x',Decimal(9)))
  vm.execute('x=1;Write();r=x;');self.assertEqual(vm.variables['r'],9)
 def test_legacy_and_oracle_remain_explicit(self):
  for mode in ('compiled-strict','interpreter'):
   vm=Interpreter(execution_backend=mode);vm.execute('r=1+2;')
   self.assertEqual(vm.variables['r'],3);self.assertNotIn('python_direct_modules',vm.execution_backend_stats)
 def test_subclass_custom_policy_configuration_rejected_before_effects(self):
  class Restricted(Interpreter):pass
  for vm in (Restricted(),Interpreter(),Interpreter()):
   if type(vm) is Interpreter:
    if not hasattr(self,'_patched'):
     vm.compiled_before=lambda node:None;self._patched=True
    else:vm._configuration_runtime=object()
   with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;')
   self.assertNotIn('x',vm.variables)
 def test_no_context_and_active_application_rejected(self):
  vm=Interpreter();vm._module_context_stack[-1]=False
  with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;')
  from yadinassi import safe_mode
  token=safe_mode._CURRENT.set(object())
  try:
   with self.assertRaises(PythonDirectUnsupported):Interpreter().execute('x=1;')
  finally:safe_mode._CURRENT.reset(token)
 def test_unsupported_syntax_has_no_silent_fallback_or_prior_effect(self):
  vm=Interpreter()
  with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;Execute "r=2;";')
  self.assertEqual(vm.variables,{})
 def test_constructor_override_not_silently_ignored(self):
  effects=[];vm=Interpreter();vm.register_type('Array',lambda:effects.append(1))
  with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;a=New Array;')
  self.assertEqual(vm.variables,{});self.assertEqual(effects,[])
 def test_cli_default_and_legacy(self):
  for args in ([],['--legacy'],['--execution-backend','interpreter']):
   env=dict(os.environ);env.pop('YADINASSI_UNSAFE_COLLECTION_ABLATION',None)
   p=subprocess.run([sys.executable,'-m','yadinassi',*args,'-c','Сообщить(2+3);'],capture_output=True,text=True,env=env)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'5')
 def test_cli_legacy_conflict_rejected(self):
  p=subprocess.run([sys.executable,'-m','yadinassi','--legacy','--execution-backend','interpreter','-c','x=1;'],capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0)
 def test_experimental_gate_still_required_for_manual_prepare(self):
  from yadinassi.experimental_naked_collections import prepare
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(RuntimeError):prepare('x=1;')
 def test_nested_direct_execution_is_explicitly_rejected(self):
  vm=Interpreter();vm.register_function('Nested',lambda:vm.execute('nested=1;'))
  with self.assertRaisesRegex(Exception,'nested or asynchronous'):vm.execute('Nested();')
  self.assertNotIn('nested',vm.variables)

 def test_final_expression_returns_native_value(self):
  vm=Interpreter();self.assertEqual(vm.execute('2+3'),5)
  vm.execute('a=New Array;a.Add(7);')
  self.assertIs(vm.execute('a'),vm.variables['a'])
  self.assertEqual(vm.execute('a.Get(0)'),7)

 def test_missing_ast_tokens_rejected_before_effects(self):
  from yadinassi.syntax import ast
  vm=Interpreter()
  with self.assertRaisesRegex(PythonDirectUnsupported,'source tokens'):
   vm.execute_program([ast.ExpressionStatement(None,ast.Literal(None,Decimal(1)))])
  self.assertEqual(vm.variables,{})
 def test_legacy_generator_entries_reject_before_effects(self):
  vm=Interpreter();source=parse('x=7;')
  with self.assertRaises(PythonDirectUnsupported):vm._scheduler.run_inline(vm.block(source))
  call=parse('Host();')[0].expression;events=[];vm.register_function('Host',lambda:events.append(1))
  with self.assertRaises(PythonDirectUnsupported):vm._scheduler.run_inline(vm.call(call,require_value=False))
  routine=parse('Procedure F() x=7;EndProcedure')[0]
  with self.assertRaises(PythonDirectUnsupported):vm._scheduler.run_inline(vm.call_routine(routine,[],vm,require_value=False))
  self.assertEqual(vm.variables,{});self.assertEqual(events,[])
 def test_host_context_install_stops_before_following_write(self):
  from yadinassi.experimental_naked_boundaries import BoundaryViolation
  vm=Interpreter();vm.register_function('Install',lambda:setattr(vm,'_configuration_runtime',object()))
  with self.assertRaises(BoundaryViolation):vm.execute('Install();x=7;')
  self.assertNotIn('x',vm.variables)
 def test_host_safe_mode_install_stops_before_following_write(self):
  from yadinassi import safe_mode
  from yadinassi.experimental_naked_boundaries import BoundaryViolation
  tokens=[];vm=Interpreter();vm.register_function('Install',lambda:tokens.append(safe_mode._CURRENT.set(object())))
  try:
   with self.assertRaises(BoundaryViolation):vm.execute('Install();x=7;')
   self.assertNotIn('x',vm.variables)
  finally:
   for token in reversed(tokens):safe_mode._CURRENT.reset(token)

import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported

class PythonDirectDefaultTests(unittest.TestCase):
 def test_default_without_experimental_environment(self):
  with patch.dict(os.environ,{},clear=True):
   vm=Interpreter();self.assertEqual(vm.execution_backend,'python-direct')
   vm.execute('a=New Array;a.Add(2);r=a[0]+1;')
   self.assertEqual(vm.variables['r'],3);self.assertEqual(vm.variables['a'][0],2)
 def test_api_existing_source_functions_and_host_output(self):
  output=[];vm=Interpreter(output.append)
  vm.execute('Function F(Val x) Return x+1;EndFunction r=F(2);Message(r);')
  self.assertEqual(output,['3'])
 def test_execute_program_does_not_reparse(self):
  vm=Interpreter();program=parse('r=2+3;')
  with patch('yadinassi.runtime.parse',side_effect=AssertionError('reparsed')):
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
 def test_platform_binding_is_canonical_without_enabling_extensions(self):
  from yadinassi.types.values import HostFunction
  from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
  vm=Interpreter();self.addCleanup(vm.close)
  with self.assertRaisesRegex(ValueError,'allow_extensions=True'):
   vm.register_function('Custom',lambda:1)
  vm.functions['unrelated']=HostFunction('Unrelated',lambda:1)
  vm._register_platform_function('Platform',lambda:Decimal(42),'Служебная')
  vm._register_platform_type('PlatformType',lambda:None,'СлужебныйТип')
  vm.execute('R=Platform()+Служебная();')
  self.assertEqual(vm.variables['r'],84)
  self.assertFalse(vm.allow_extensions)
  self.assertIs(vm._builtin_types['служебныйтип'][0],vm.types['platformtype'])
  with self.assertRaises(BoundaryViolation):vm.execute('Unrelated();')
 def test_observable_callback_values(self):
  vm=Interpreter(allow_extensions=True);vm.register_function('Write',lambda:vm.variables.__setitem__('x',Decimal(9)))
  vm.execute('x=1;Write();r=x;');self.assertEqual(vm.variables['r'],9)
 def test_subclass_custom_policy_configuration_rejected_before_effects(self):
  class Restricted(Interpreter):pass
  for vm in (Restricted(),Interpreter(),Interpreter()):
   if type(vm) is Interpreter:
    if not hasattr(self,'_patched'):
     vm.set_variable=lambda name,value:None;self._patched=True
    else:vm._configuration_runtime=object()
   with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;')
   self.assertNotIn('x',vm.variables)
 def test_no_context_and_active_application_rejected(self):
  vm=Interpreter();vm._module_context_stack[-1]=False
  with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;')
  from yadinassi.execution import safe_mode
  token=safe_mode._CURRENT.set(object())
  try:
   with self.assertRaises(PythonDirectUnsupported):Interpreter().execute('x=1;')
  finally:safe_mode._CURRENT.reset(token)
 def test_unsupported_syntax_has_no_silent_fallback_or_prior_effect(self):
  # Outward Goto is supported; the combination with a routine Var
  # declaration still requires initialization analysis (docs/direct-goto.md).
  for prepared in (False,True):
   out=[];vm=Interpreter(out.append);self.addCleanup(vm.close)
   with self.subTest(prepared=prepared):
    def run(source):
     if prepared:return vm.execute_prepared(vm.prepare(source))
     return vm.execute(source)

    with self.assertRaisesRegex(PythonDirectUnsupported,'outward Goto with routine Var'):
     run('x=1;Message("before");Function F() If True Then Goto ~finish;EndIf;Var N;~finish:Return N;EndFunction;F();')
    self.assertEqual(vm.variables,{});self.assertEqual(out,[])
    run('x=1;If True Then Goto ~finish;EndIf;Message("skipped");x=99;~finish:x=2;')
    self.assertEqual(vm.variables,{'x':2});self.assertEqual(out,[])
 def test_constructor_override_not_silently_ignored(self):
  effects=[];vm=Interpreter(allow_extensions=True);vm.register_type('Array',lambda:effects.append(1))
  with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;a=New Array;')
  self.assertEqual(vm.variables,{});self.assertEqual(effects,[])
 def test_cli_default_and_explicit_direct(self):
  for args in ([],['--execution-backend','python-direct']):
   env=dict(os.environ);env.pop('YADINASSI_UNSAFE_COLLECTION_ABLATION',None)
   p=subprocess.run([sys.executable,'-m','yadinassi',*args,'-c','Сообщить(2+3);'],capture_output=True,text=True,env=env)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'5')
 def test_nested_direct_execution_is_explicitly_rejected(self):
  vm=Interpreter(allow_extensions=True);vm.register_function('Nested',lambda:vm.execute('nested=1;'))
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
 def test_host_context_install_stops_before_following_write(self):
  from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
  vm=Interpreter(allow_extensions=True);vm.register_function('Install',lambda:setattr(vm,'_configuration_runtime',object()))
  with self.assertRaises(BoundaryViolation):vm.execute('Install();x=7;')
  self.assertNotIn('x',vm.variables)
 def test_host_safe_mode_install_stops_before_following_write(self):
  from yadinassi.execution import safe_mode
  from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
  tokens=[];vm=Interpreter(allow_extensions=True);vm.register_function('Install',lambda:tokens.append(safe_mode._CURRENT.set(object())))
  try:
   with self.assertRaises(BoundaryViolation):vm.execute('Install();x=7;')
   self.assertNotIn('x',vm.variables)
  finally:
   for token in reversed(tokens):safe_mode._CURRENT.reset(token)

"""Direct execution snapshot and live-authority behavior retained from IR probes.

The deleted Engine FULL/OFF matrix is not a supported execution mode. These
probes assert behavior through the direct API; failures are not skipped. Child
probe assertions remain enabled even when imported runtime modules use -O.
See docs/retired-owned-ir-test-migration.md for the coverage disposition.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

_ROOT = Path(__file__).resolve().parents[1]
_PRELUDE = """
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
"""

class OwnedIRSubprocessTests(unittest.TestCase):
    def probe(self, source):
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join((str(_ROOT), str(_ROOT / 'tests')))
        env['PYTHONIOENCODING'] = 'utf-8'
        flags = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
        launcher = 'exec(compile(' + ascii(_PRELUDE + source) + ', "<direct-probe>", "exec", optimize=0))'
        process = subprocess.run([sys.executable, *flags, '-c', launcher],
            cwd=_ROOT, env=env, capture_output=True, encoding='utf-8', timeout=60)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_probe_failure_preserves_unicode_diagnostics(self):
        with self.assertRaisesRegex(AssertionError, 'Диагностика'):
            self.probe("raise ValueError('Диагностика')")

    def test_direct_rhs_mutation_keeps_admitted_assignment_target(self):
        self.probe('''
vm=Interpreter(execution_backend='python-direct', allow_extensions=True);program=parse('target=Mutate();')
calls=[]
def mutate():
 calls.append('rhs');program[0].target.name='hijacked';return 42
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['rhs'] and vm.variables['target']==42 and 'hijacked' not in vm.variables
''')

    def test_direct_actual_mutation_does_not_redirect_admitted_callee(self):
        self.probe('''
vm=Interpreter(execution_backend='python-direct', allow_extensions=True)
program=parse('Function Original(x) Return 1;EndFunction Function Hijack(x) Return 99;EndFunction r=Original(Mutate());')
calls=[]
def mutate():
 calls.append('actual');program[-1].value.callee.name='Hijack';return 0
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['actual'] and vm.variables['r']==1
''')

    def test_direct_actual_mutation_keeps_parameter_binding_flags_and_default(self):
        self.probe('''
vm=Interpreter(execution_backend='python-direct', allow_extensions=True)
program=parse('Function F(Val x, trigger, Val y=7) x=9;Return y;EndFunction a=1;r=F(a,Mutate());')
calls=[]
def mutate():
 calls.append('actual')
 program[0].parameters[0].by_value=False
 program[0].parameters[0].name='renamed'
 program[0].parameters[2].default.value=99
 return 0
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['actual'] and vm.variables['r']==7 and vm.variables['a']==1
''')

    def test_direct_block_append_and_future_literal_do_not_change_snapshot(self):
        self.probe('''
vm=Interpreter(execution_backend='python-direct', allow_extensions=True);program=parse('Mutate();final=1;')
calls=[]
def mutate():
 calls.append('append');program[-1].value.value=99;program.extend(parse('injected=42;'))
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['append'] and vm.variables['final']==1 and 'injected' not in vm.variables
''')

    def test_direct_caught_bsl_host_error_uses_admitted_handler(self):
        self.probe('''
from yadinassi.types.errors import BSLRuntimeError
vm=Interpreter(execution_backend='python-direct', allow_extensions=True);program=parse('Try Boom();Except caught=1;EndTry;')
calls=[]
def boom():
 calls.append('boom');program[0].handler[0].target.name='hijacked';program[0].handler[0].value.value=99
 raise BSLRuntimeError('expected host BSL error')
vm.register_function('Boom',boom);vm.execute_program(program)
assert calls==['boom'] and vm.variables['caught']==1 and 'hijacked' not in vm.variables
''')

    def test_direct_opaque_value_callbacks_cannot_inject_changed_syntax(self):
        self.probe('''
from decimal import Decimal
for mode in ('equality','decimal','metaclass'):
 vm=Interpreter(execution_backend='python-direct');calls=[]
 source={'equality':'r=(x=x);final=1;','decimal':'r=-x;final=1;','metaclass':'r=Construct();final=1;'}[mode]
 program=parse(source)
 def change():
  calls.append(mode);program[-1].value.value=99
 class HostValue:
  def __eq__(self,other):change();return True
 class HostDecimal(Decimal):
  def copy_negate(self):change();return Decimal(-1)
 class Meta(type):
  def __call__(cls):change();return Decimal(3)
 class Construct(metaclass=Meta):pass
 if mode=='equality':vm.variables['x']=HostValue()
 elif mode=='decimal':vm.variables['x']=HostDecimal(1)
 else:vm.register_function('Construct',Construct)
 vm.execute_program(program)
 assert calls==[mode] and vm.variables['final']==1
 assert vm.variables['r']=={'equality':True,'decimal':Decimal(-1),'metaclass':Decimal(3)}[mode]
''')

    def test_direct_routine_selection_reads_frozen_dual_metadata(self):
        self.probe('''
for initially_dual in (False,True):
 vm=Interpreter(execution_backend='python-direct', allow_extensions=True)
 directive='&AtClientAtServerNoContext\\n' if initially_dual else ''
 program=parse(directive+'Function F() Return 7;EndFunction Mutate();r=F();')
 def mutate():
  program[0].is_dual=not initially_dual
  program[0].execution_context='server'
 vm.register_function('Mutate',mutate);vm.execute_program(program)
 assert vm.variables['r']==7
''')

    def test_direct_module_export_gate_and_ready_remain_separate(self):
        self.probe('''
import unittest
from yadinassi.execution.execution_policy import execution_backend_policy
names=[
 'tests.test_python_direct_imports.DirectImportBoundaryTests.test_cache_namespace_and_family_rebindings_precede_arguments',
 'tests.test_python_direct_imports.DirectImportBoundaryTests.test_retained_callable_and_export_reference_expire_with_caller',
 'tests.test_python_direct_imports.DirectImportBoundaryTests.test_prepared_late_namespace_layout_change_refuses_before_effects']
with execution_backend_policy('python-direct'):
 result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
assert not result.skipped and result.wasSuccessful()
''')

    def test_direct_json_and_completion_validation_use_admitted_metadata(self):
        self.probe('''
from pathlib import Path
from tempfile import TemporaryDirectory
for kind in ('completion','json'):
 with TemporaryDirectory() as directory:
  path=Path(directory)/'Side.bsl'; main=str(Path(directory)/'Main.bsl')
  routine=('Function F(Result,Extra) Export Return Result;EndFunction' if kind=='completion'
    else 'Function F(Property,Value,Extra) Export Return Value;EndFunction')
  path.write_text(routine,encoding='utf-8')
  vm=Interpreter(execution_backend='python-direct');calls=[]
  def mutate():
   calls.append(kind)
   path.write_text('Procedure F() EndProcedure',encoding='utf-8')
  vm.register_function('Mutate',mutate)
  tail=('c=New CallbackDescription("F",Side);r=RunCallback(c,7);' if kind=='completion'
    else 'reader=New JSONReader;reader.SetString("7");r=ReadJSON(reader,False,,,"F",Side);')
  vm.execute('// #Import Side.bsl\\nMutate();'+tail,main)
  assert calls==[kind] and vm.variables['r']==7
''')

    def test_existing_custom_ast_setter_is_not_replaced(self):
        self.probe('''
def custom(self,name,value): object.__setattr__(self,name,value)
ast.Node.__setattr__=custom
vm=Interpreter(execution_backend='python-direct')
vm.execute('r=1;')
assert ast.Node.__setattr__ is custom
assert vm.variables['r']==1
''')

    def test_configuration_authority_callbacks_and_form_quiescent_replacement(self):
        self.probe('''
import unittest
from yadinassi.execution.execution_policy import execution_backend_policy
names=[
 'tests.test_compiled_contexts.StrictContextTests.test_configuration_cross_owner_defaults_and_callbacks',
 'tests.test_compiled_contexts.StrictContextTests.test_source_value_manager_references',
 'tests.test_form_app.FormControllerTests.test_server_error_keeps_authoritative_state_and_finite_reason']
with execution_backend_policy('python-direct'):
 result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
assert result.wasSuccessful()
''')

    def test_reuse_rejects_forged_or_wrong_origin_execution_views(self):
        self.probe('''
from types import SimpleNamespace
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_source_runtime import SourceApplication
vm=Interpreter(execution_backend='python-direct')
first=parse('Function F() Return 1;EndFunction')[0]
second=parse('Function G() Return 2;EndFunction')[0]
correct=first
wrong=second
fake=SimpleNamespace(is_function=True,name='F',origin=first)
for method in (ConfigurationApplication.reusable_call, SourceApplication.reusable_call):
 holder=SimpleNamespace(_reuse_routines={})
 for candidate in (wrong,fake):
  try: method(holder,None,None,first,True,execution_routine=candidate)
  except ValueError as error: assert 'origin mismatch' in str(error)
  else: raise AssertionError('forged reuse execution view accepted')
 assert method(holder,None,None,first,True,execution_routine=correct) is None
''')

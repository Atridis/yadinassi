"""Isolated owned-view checks retain closed context guards and by-reference writes."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
PRELUDE='''
from types import SimpleNamespace
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.owned_syntax import enable_isolated_process_experiment, syntax_kind
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
enable_isolated_process_experiment()
Engine.OWNED_SNAPSHOT=True
Engine.ORIGIN_MUTATION_MONITOR=False
def check(condition):
    if not condition: raise AssertionError('owned context contract')
def view(vm,node):
    vm._compiled().prepare_node(node)
    return vm._compiled().execution_view(node)
'''


class OwnedContextGuardTests(unittest.TestCase):
    def probe(self,body):
        env=dict(os.environ,PYTHONPATH=str(ROOT),YADINASSI_OWNED_IR_EXPERIMENT='isolated-process-v1')
        flags=['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []
        result=subprocess.run([sys.executable,*flags,'-c',PRELUDE+body],cwd=ROOT,env=env,
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_owned_event_and_object_guards_keep_unknown_nodes_closed(self):
        self.probe('''
from yadinassi.form_event_simulation import _EventInterpreter
from yadinassi.catalog_object_preparation import _ObjectInterpreter
vm=_EventInterpreter(lambda record: None)
node=parse('42;')[0].expression
owned=view(vm,node)
check(type(owned) is not ast.Literal and syntax_kind(owned) is ast.Literal)
remaining=vm._remaining
vm.compiled_before(owned)
check(vm._remaining==remaining-1)
class Foreign(ast.Literal): pass
foreign=Foreign(node.token,42)
check(syntax_kind(foreign) is Foreign)
try:vm.compiled_before(foreign)
except ValueError:pass
else:raise AssertionError('foreign context node admitted')
try:vm._compiled().prepare_node(foreign)
except CompiledUnsupported:pass
else:raise AssertionError('foreign compiler node admitted')
obj=object.__new__(_ObjectInterpreter)
Interpreter.__init__(obj,execution_backend='compiled-strict')
obj.remaining=10;obj.text_budget=100;obj.functions={}
obj.compiled_before(owned)
check(obj.remaining==9)
try:obj.compiled_before(foreign)
except ValueError:pass
else:raise AssertionError('foreign object node admitted')
# Admission security still treats unregistered instances of the private class as foreign.
forged=object.__new__(type(owned))
object.__setattr__(forged,'token',node.token);object.__setattr__(forged,'value',42)
check(syntax_kind(forged) is type(forged))
try:vm._compiled().prepare_node(forged)
except CompiledUnsupported:pass
else:raise AssertionError('unregistered private node admitted')
''')

    def test_owned_constant_and_posting_arguments_preserve_live_references(self):
        self.probe('''
from yadinassi.source_constant_managers import _ValueInterpreter
from yadinassi.document_posting import _PostingInterpreter
storage={'value':7}
vm=object.__new__(_ValueInterpreter)
Interpreter.__init__(vm,execution_backend='compiled-strict')
vm.manager=SimpleNamespace(value_read=lambda caller:storage['value'],
                          value_write=lambda caller,value:storage.__setitem__('value',value))
node=view(vm,parse('Value;')[0].expression)
reference=vm._scheduler.run_inline(vm.argument(node))
check(reference.get()==7);reference.set(8);check(storage['value']==8)
vm=object.__new__(_PostingInterpreter)
Interpreter.__init__(vm,execution_backend='compiled-strict')
vm._document=SimpleNamespace(_values={'name':3},_sections={},
    get_member=lambda name:storage['value'],set_member=lambda name,value:storage.__setitem__('value',value))
node=view(vm,parse('Name;')[0].expression)
reference=vm._scheduler.run_inline(vm.argument(node))
check(reference.get()==8);reference.set(9);check(storage['value']==9)
''')

    def test_configured_owned_program_retains_original_authority_and_import_guard(self):
        self.probe('''
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.errors import BSLError
original=parse('Procedure Protected() EndProcedure')[0]
owner=SimpleNamespace(require_open=lambda:None,_definitions={'protected':object()},
    _global_names=set(),_events={},_declared_routines={id(original):original})
vm=Interpreter(execution_backend='compiled-strict')
owned=view(vm,original)
ConfigurationApplication.check_program(owner,[original])
ConfigurationApplication.check_program(owner,[owned])
other=view(vm,parse('Procedure Protected() EndProcedure')[0])
try:ConfigurationApplication.check_program(owner,[other])
except BSLError:pass
else:raise AssertionError('foreign declaration authority accepted')
# Ordinary Import AST has the same closed execution kind as its owned view.
import_node=ast.Import(original.token,'foreign.bsl')
owned_import=view(vm,import_node)
try:ConfigurationApplication.check_program(owner,[owned_import])
except BSLError:pass
else:raise AssertionError('owned import escaped configured guard')
''')

"""Closed private ownership representation without public class mutation."""
import unittest
from tests import test_owned_ir_experiment as probes


class OwnedPrivateNodeTests(unittest.TestCase):
    probe = probes.OwnedIRSubprocessTests.probe

    def test_no_public_mutation_and_custom_original_hooks_survive(self):
        self.probe('''
from yadinassi import owned_syntax as owned
before=dict(vars(ast.Node))
events=[]
def custom(self,name,value):
    events.append(name);object.__setattr__(self,name,value)
ast.Node.__setattr__=custom
p=parse('x=1;'); vm=Interpreter(execution_backend='compiled-strict');e=vm._compiled();e.prepare(p)
v=e.execution_view(p[0])
assert ast.Node.__setattr__ is custom
assert type(v) is not ast.Assign and isinstance(v,ast.Assign)
assert type(v).__name__=='Assign' and owned.syntax_kind(v) is ast.Assign
p[0].target.name='y';assert events[-1]=='name'
try:v.target.name='z'
except TypeError:pass
else:raise AssertionError('owned write accepted')
del ast.Node.__setattr__
assert dict(vars(ast.Node))==before
''')

    def test_original_and_owned_vms_and_copy_identity(self):
        self.probe('''
import copy
from yadinassi import owned_syntax as owned
original=parse('x=1;');payload=[];original[0].value.value=payload
vm=Interpreter(execution_backend='compiled-strict');e=vm._compiled();e.prepare(original)
v=e.execution_view(original[0])
assert copy.copy(v) is v and copy.deepcopy(v) is v
block=e._owned.existing(original)
assert copy.copy(block) is block and copy.deepcopy(block) is block
assert v.value.value is payload
ordinary=Interpreter(execution_backend='interpreter');ordinary.execute('x=3;')
assert ordinary.variables['x']==3
original[0].target.name='changed';assert v.target.name=='x'
assert owned.origin_node(v) is original[0]
''')

    def test_unregistered_private_and_unknown_subclass_reject(self):
        self.probe('''
from yadinassi import owned_syntax as owned
p=parse('x=1;');vm=Interpreter(execution_backend='compiled-strict');e=vm._compiled();e.prepare(p)
v=e.execution_view(p[0]);fake=object.__new__(type(v))
for key,value in vars(p[0]).items():object.__setattr__(fake,key,value)
assert not owned.is_owned(fake) and owned.syntax_kind(fake) is type(fake)
class Unknown(ast.Assign):pass
u=Unknown(p[0].token,p[0].target,p[0].value)
for bad in (fake,u):
    try:e.prepare_node(bad)
    except CompiledUnsupported:pass
    else:raise AssertionError('unregistered class admitted')
''')

    def test_provenance_payload_backlink_cycle_collects(self):
        self.probe('''
import gc,weakref
from yadinassi import owned_syntax as owned
def make():
    p=parse('x=1;');payload=[];p[0].value.value=payload
    vm=Interpreter(execution_backend='compiled-strict');e=vm._compiled();e.prepare(p)
    v=e.execution_view(p[0]);payload.append(v)
    result=(weakref.ref(p[0]),weakref.ref(v));e.release();return result
refs=make();gc.collect();assert all(r() is None for r in refs)
''')

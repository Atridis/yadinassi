"""Research AST region lowering using the unchanged canonical admission/helpers."""
import subprocess
import sys
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast as direct
import test_python_direct_collection_regions as canonical

class DirectASTRegionTests(unittest.TestCase):
    def test_reference_workloads_have_independent_results(self):
        for source in (
            'T=New ValueTable;T.Columns.Add("N");For I=0 To 7 Do Row=T.Add();Row.N=I;EndDo;R=0;For I=0 To 7 Do R=R+T.Get(I).N;EndDo;',
            'T=New ValueList;For I=0 To 7 Do Item=T.Add(I);EndDo;R=0;For I=0 To 7 Do R=R+T.Get(I).Value;EndDo;',
        ):
            vm=Interpreter();self.addCleanup(vm.close);vm.execute(source)
            self.assertEqual(vm.variables['r'],28)
        from yadinassi import BSLError
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(BSLError):
            vm.execute('T=New ValueTable;T.Columns.Add("N");For I=0 To 3 Do Row=T.Add();Row.N=1%(2-I);EndDo;')
        self.assertEqual(len(vm.variables['t'].rows),3)
        self.assertEqual(vm.variables['i'],2)

    def test_import_time_partial_replacement_rejects_before_effects(self):
        script=r"""
import functools,importlib,sys
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast as old
real=functools.partial
class Fake:
    __new__=real.__new__
Fake.__name__='partial';Fake.__module__='functools'
if old._native_partial_binding(Fake):raise AssertionError('spoof accepted')
class Meta(type):
    def __getattribute__(self,name):raise AssertionError('descriptor callback')
class Hostile(metaclass=Meta):pass
if old._native_partial_binding(Hostile):raise AssertionError('metaclass accepted')
seen=[]
def callback(*args,**kwargs):
    seen.append('callback');return real(*args,**kwargs)
functools.partial=callback
sys.modules.pop('yadinassi.experimental_direct_ast')
research=importlib.import_module('yadinassi.experimental_direct_ast')
functools.partial=real
vm=Interpreter()
with patch.object(python_direct,'_compile',research.compile_module):
    try:vm.execute('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
    except python_direct.PythonDirectUnsupported as error:
        if 'noncanonical partial' not in str(error):raise
    else:raise AssertionError('replaced factory executed')
if vm.variables or seen:raise AssertionError((vm.variables,seen))
"""
        subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',script],check=True)

    def test_import_time_operator_replacement_rejects_before_effects(self):
        script=r"""
import _operator,importlib,sys
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast
spoof=set().add
spoof.__module__='_operator'
if experimental_direct_ast._native_operator_binding(spoof,'add'):raise AssertionError('bound method spoof accepted')
if experimental_direct_ast._native_operator_binding(_operator.getitem,'add'):raise AssertionError('wrong native function accepted')
if not experimental_direct_ast._native_operator_binding(_operator.add,'add'):raise AssertionError('native add rejected')
real=_operator.add;seen=[]
def callback(*args):seen.append('callback');return real(*args)
_operator.add=callback
sys.modules.pop('yadinassi.experimental_direct_ast')
research=importlib.import_module('yadinassi.experimental_direct_ast')
_operator.add=real
vm=Interpreter()
with patch.object(python_direct,'_compile',research.compile_module):
    try:vm.execute('T=New ValueList;For I=0 To 2 Do T.Add(I+1);EndDo;')
    except python_direct.PythonDirectUnsupported as error:
        if 'noncanonical operator' not in str(error):raise
    else:raise AssertionError('replaced operator executed')
if vm.variables or seen:raise AssertionError((vm.variables,seen))
"""
        subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',script],check=True)

    def test_nested_tracked_get_emits_linear_nodes(self):
        counts=[]
        for depth in (4,8,12):
            expression='0'
            for _ in range(depth):expression='T.Get('+expression+').N'
            source='T=New ValueTable;T.Columns.Add("N");For I=0 To 0 Do Row=T.Add();Row.N=0;EndDo;For I=0 To 0 Do R='+expression+';EndDo;'
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module):
                plan=vm.prepare(source);vm.execute_prepared(plan)
            self.assertEqual(vm.variables['r'],0)
            counts.append(plan._plan._research_lowering_counts[2]);vm.close()
        self.assertEqual(counts[2]-counts[1],counts[1]-counts[0])

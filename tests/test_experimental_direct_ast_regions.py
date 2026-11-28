"""Production collection lowering does not need a separate region compiler."""
import ast
from contextlib import closing
import subprocess
import sys
import unittest
from yadinassi import Interpreter

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

    def _run_without_binding(self, module_name, name):
        script = r"""
import importlib
import sys
from yadinassi import Interpreter

def unexpected(*args, **kwargs):
    raise AssertionError('plain ValueList code called the old binding')

module = importlib.import_module(sys.argv[1])
setattr(module, sys.argv[2], unexpected)
vm = Interpreter()
vm.execute('T=New ValueList;For I=0 To 2 Do T.Add(I+1);EndDo;R=T.Get(2).Value;')
if vm.variables['r'] != 3:
    raise AssertionError(vm.variables['r'])
"""
        result = subprocess.run(
            [sys.executable, *(['-O'] if sys.flags.optimize else []),
             '-c', script, module_name, name], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_replacement_is_not_used_by_ordinary_value_list_calls(self):
        self._run_without_binding('yadinassi.execution.codegen.direct_emitter', 'partial')

    def test_operator_replacement_is_not_used_by_native_addition(self):
        self._run_without_binding('_operator', 'add')

    def test_nested_get_emits_linear_python_nodes(self):
        counts = []
        for depth in (4, 8, 12):
            expression = '0'
            for _ in range(depth):
                expression = 'T.Get(' + expression + ').N'
            source = ('T=New ValueTable;T.Columns.Add("N");Row=T.Add();Row.N=0;'
                      'R=' + expression + ';')
            with closing(Interpreter()) as vm:
                plan = vm.prepare(source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'], 0)
                counts.append(sum(1 for _ in ast.walk(ast.parse(plan._plan.generated_source))))
        self.assertGreater(counts[1], counts[0])
        self.assertEqual(counts[2] - counts[1], counts[1] - counts[0])

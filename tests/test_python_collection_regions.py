"""Public direct collection behavior, independent of retired region/lease internals."""
from contextlib import closing
import unittest
from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class PythonCollectionRegionTests(unittest.TestCase):
    def run_modes(self, source, observe):
        outcomes=[]
        for prepared in (False, True):
            with closing(Interpreter()) as vm:
                if prepared: vm.execute_prepared(vm.prepare(source))
                else: vm.execute(source)
                outcomes.append(observe(vm))
        self.assertEqual(outcomes[0],outcomes[1])
        return outcomes[0]

    def test_array_aliases_and_live_foreach(self):
        result=self.run_modes('A=New Array;B=A;A.Add(1);A.Add(2);S=0;For Each X In A Do S=S+X;If X=1 Then A.Add(3);EndIf;EndDo;B[1]=9;',lambda vm:(vm.variables['a'] is vm.variables['b'],list(vm.variables['a']),vm.variables['s']))
        self.assertEqual(result,(True,[1,9,3],6))

    def test_native_map_numeric_key_contract(self):
        result=self.run_modes('M=New Map;M.Insert(True,11);M.Insert(1,22);N=M.Count();R=M.Get(True);Numeric=M[1];Missing=M.Get("absent");',lambda vm:tuple(vm.variables[k] for k in ('n','r','numeric','missing')))
        self.assertEqual(result,(2,11,22,None))

    def test_structure_casefold_and_member_method_independence(self):
        result=self.run_modes('S=New Structure("Name,Count",1,7);S.NAME=2;S.Insert("nAmE",3);R=S.name+S.Count+S.Count();',lambda vm:vm.variables['r'])
        self.assertEqual(result,12)

    def test_bad_index_preserves_prior_effects_and_is_catchable(self):
        result=self.run_modes('A=New Array;A.Add(1);Try A[9]=4;Except Caught=True;EndTry;',lambda vm:(list(vm.variables['a']),vm.variables['caught']))
        self.assertEqual(result,([1],True))

    def test_foreign_map_key_rejected_without_protocol_hooks(self):
        class Key:
            def __hash__(self):raise AssertionError('foreign hash')
            def __eq__(self,other):raise AssertionError('foreign equality')
        with closing(Interpreter()) as vm:
            vm.variables['key']=Key()
            with self.assertRaises((BSLError,BoundaryViolation)):
                vm.execute('M=New Map;M.Insert(Key,1);')

    def test_fixed_snapshot_preserves_nested_identity_not_source_storage(self):
        result=self.run_modes('A=New Array;M=New Map;M.Insert("x",A);F=New FixedMap(M);M.Insert("x",7);A.Add(9);R=F.Get("x").Count();',lambda vm:vm.variables['r'])
        self.assertEqual(result,1)

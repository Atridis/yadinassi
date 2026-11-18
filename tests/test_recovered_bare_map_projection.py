import unittest
from unittest.mock import patch
from recovered_bare_fixture import Interpreter
from yadinassi.native_bare_collections import BareMap, BareMapEntry, BareArray
from yadinassi.python_direct import PythonDirectUnsupported
import yadinassi.native_bare_compiler as compiler

class RecoveredMapProjection(unittest.TestCase):
    def run_counted(self,source,setup=None):
        seen=[]
        def entry(*args):
            seen.append(args)
            return BareMapEntry(*args)
        vm=Interpreter()
        if setup:setup(vm)
        with patch.object(compiler,'BareMapEntry',entry):plan=vm.prepare(source)
        vm.execute_prepared(plan)
        return vm,seen,plan.generated_source
    def test_conditional_assignment_only_materializes_when_executed(self):
        source='M=New Map; For I=0 To 7 Do M.Insert(I,I+10); EndDo; R=0; For Each P In M Do R=R+P.Value; If P.Key=3 Then Alias=P; EndIf; EndDo; V=Alias.Value;'
        vm,seen,generated=self.run_counted(source)
        self.assertEqual(seen,[(3,13)])
        self.assertIs(type(vm.variables['alias']),BareMapEntry)
        self.assertEqual((vm.variables['r'],vm.variables['v']),(108,13))
        self.assertIn('dict.items(',generated)
        self.assertIn('[1]',generated)
    def test_false_branch_allocates_zero_entries(self):
        vm,seen,_=self.run_counted('M=New Map; M.Insert("a",7); For Each P In M Do If False Then Alias=P; EndIf; R=P.Value; EndDo;')
        self.assertEqual(seen,[]);self.assertEqual(vm.variables['r'],7)
    def test_passed_map_and_post_loop_assignment(self):
        def setup(vm):
            vm.variables['m']=BareMap({'a':7,'b':9})
        vm,seen,_=self.run_counted('For Each P In M Do R=P.Value; EndDo; Alias=P; V=Alias.Key;',setup)
        self.assertEqual(seen,[('b',9)]);self.assertEqual(vm.variables['v'],'b')
    def test_scalar_array_loop_does_not_materialize(self):
        vm,seen,_=self.run_counted('A=New Array; A.Add(7); For Each P In A Do Alias=P; EndDo;')
        self.assertEqual(seen,[]);self.assertEqual(vm.variables['alias'],7)
    def test_unsupported_whole_entry_argument_no_hidden_eager_path(self):
        vm=Interpreter()
        with self.assertRaises(PythonDirectUnsupported):vm.execute('M=New Map; M.Insert(1,2); A=New Array; For Each P In M Do A.Add(P); EndDo;')
        self.assertEqual(list(vm.variables['a']),[])
    def test_nested_source_size_is_linear(self):
        import ast
        sizes=[]
        for depth in (2,4,8,16):
            # Unknown external receivers previously duplicated the entire body.
            source=''.join(f'For Each P{i} In A{i} Do ' for i in range(depth))+'R=1; '+'EndDo; '*depth
            plan=Interpreter().prepare(source)
            tree=ast.parse(plan.generated_source)
            self.assertEqual(sum(isinstance(n,ast.For) for n in ast.walk(tree)),depth)
            sizes.append(len(plan.generated_source))
        self.assertLess(sizes[-1],sizes[0]*12)
    def test_known_map_has_no_per_item_branch(self):
        import ast
        source='M=New Map; M.Insert(1,7); R=0; For Each P In M Do R=R+P.Value; EndDo;'
        tree=ast.parse(Interpreter().prepare(source).generated_source)
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For))
        self.assertFalse(any(isinstance(n,(ast.If,ast.IfExp)) for n in ast.walk(loop)))
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr=='get_member' for n in ast.walk(loop)))
    def test_branch_and_zero_loop_kind_facts_do_not_leak(self):
        for change in ('If False Then M=New Map; EndIf;', 'For I=1 To 0 Do M=New Map; EndDo;', 'While False Do M=New Map; EndDo;'):
            vm=Interpreter();vm.execute('M=New Array; '+change+' M.Add(7); For Each P In M Do R=P; EndDo;')
            self.assertEqual(vm.variables['r'],7)
    def test_condition_byref_invalidation_reaches_false_branch(self):
        source='Function Change(X) X=New Array; X.Add(7); Return False; EndFunction; M=New Map; If Change(M) Then R=0; Else For Each P In M Do R=P; EndDo; EndIf;'
        vm=Interpreter();vm.execute(source);self.assertEqual(vm.variables['r'],7)
    def test_conditional_iterator_kind_is_explicitly_unsupported_after_branch(self):
        with self.assertRaises(PythonDirectUnsupported):
            Interpreter().prepare('M=New Map; M.Insert(1,7); If True Then For Each P In M Do R=P.Value; EndDo; EndIf; Alias=P;')
    def test_loop_carried_receiver_kind_is_not_assumed_from_first_iteration(self):
        bodies=('For J=1 To 2 Do ', 'J=0; While J<2 Do J=J+1; ')
        for loop in bodies:
            source='M=New Map; M.Insert(1,7); N=0; '+loop+' For Each P In M Do N=N+1; EndDo; M=New Array; M.Add(8); EndDo;'
            vm=Interpreter();vm.execute(source);self.assertEqual(vm.variables['n'],2)

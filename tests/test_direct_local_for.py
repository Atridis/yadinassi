import ast
import unittest
from decimal import Decimal as D
from yadinassi import Interpreter


class LocalForTests(unittest.TestCase):
    def run_source(self, source, **functions):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        for name,function in functions.items():vm.register_function(name,function)
        plan=vm.prepare(source);result=vm.execute_prepared(plan)
        return vm,plan,result

    def loops(self,plan):
        tree=ast.parse(plan._plan.generated_source)
        return [node for node in ast.walk(tree) if isinstance(node,(ast.For,ast.While))]

    def test_unrelated_host_call_no_longer_disables_range(self):
        seen=[]
        vm,plan,result=self.run_source('S=0; For i=1 To 3 Do S=S+i; EndDo; Before(); Observe(i); S;',Before=lambda:None,Observe=lambda x:seen.append(x))
        self.assertIsInstance(self.loops(plan)[0],ast.For)
        self.assertEqual(result,D(6));self.assertEqual(seen,[D(4)])
        self.assertIs(type(seen[0]),D)
        self.assertTrue(all(type(x) is D for x in vm.variables.values()))

    def test_break_continue_empty_and_error_publication(self):
        for body,expected in (('S=S+i; Continue;',{'s':D(6),'i':D(4)}),('S=S+i; Break;',{'s':D(1),'i':D(1)})):
            vm,plan,_=self.run_source('S=0; For i=1 To 3 Do '+body+' EndDo; Host();',Host=lambda:None)
            self.assertIsInstance(self.loops(plan)[0],ast.For);self.assertEqual(vm.variables,expected)
        vm,plan,_=self.run_source('For i=3 To 1 Do X=7; EndDo; Host();',Host=lambda:None)
        self.assertEqual(vm.variables,{'i':D(3)})
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);vm.register_function('Host',lambda:None)
        with self.assertRaises(Exception):vm.execute('S=0; For i=1 To 3 Do S=1/(2-i); EndDo; Host();')
        self.assertEqual(vm.variables,{'s':D(1),'i':D(2)})

    def test_mutation_callback_and_byref_still_use_while(self):
        for source in ('Host(); S=0; For i=1 To 3 Do i=i+1; S=S+i; EndDo;',
                       'S=0; For i=1 To 3 Do Host(); S=S+i; EndDo;',
                       'Procedure P(x) x=3; EndProcedure For i=1 To 3 Do P(i); EndDo;'):
            _,plan,_=self.run_source(source,Host=lambda:None)
            self.assertIsInstance(self.loops(plan)[0],ast.While)

    def test_fractional_scaled_and_dynamic_bounds_keep_existing_semantics(self):
        for source,expected in (('Host(); S=0; For i=0.5 To 2.5 Do S=S+i; EndDo;',D('3.5')),
                                ('Host(); For i=1.0 To 3.0 Do S=i; EndDo;',D('4.0')),
                                ('N=3; For i=1 To N Do S=i; EndDo;',D(4))):
            vm,plan,_=self.run_source(source,Host=lambda:None)
            self.assertIsInstance(self.loops(plan)[0],ast.While)
            self.assertEqual(vm.variables['i'].as_tuple(),expected.as_tuple())

    def test_opaque_operator_and_known_routine_are_not_assumed_pure(self):
        vm=Interpreter();self.addCleanup(vm.close)
        class Effect:
            def __add__(self, other):
                vm.variables['i']=D(3)
                return D(8)
        vm.variables['payload']=Effect()
        plan=vm.prepare('For i=1 To 3 Do X=Payload+1; EndDo;')
        self.assertIsInstance(self.loops(plan)[0],ast.While)
        # No assumption about whether an unsupported external value can execute:
        # the generator must not erase its possible effect on the counter.
        vm,plan,_=self.run_source('Var i; Procedure P() i=3; EndProcedure For i=1 To 3 Do P(); EndDo;')
        self.assertIsInstance(self.loops(plan)[0],ast.While)
        self.assertEqual(vm.variables['i'],D(4))

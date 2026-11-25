"""Exact direct Map identity, separately evidenced from Array/Structure."""
from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap, _NakedMap
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_scalar_semantics import map_identity_operators
from yadinassi.execution.codegen.experimental_naked_structure import new_structure


class DirectMapIdentityTests(unittest.TestCase):
    def test_alias_copy_equal_content_cycles_and_canonical_control(self):
        source='A=New Map;B=New Map;A.Insert("X",1);B.Insert("X",1);Alias=A;Equal=(A=B);Different=(A<>B);Self=(A=A);Shared=(A=Alias);A.Insert("Self",A);B.Insert("Self",A);Cycle=(A=B);Fixed=New FixedMap(A);Copy=New Map(Fixed);CopyEqual=(Copy=A);'
        for backend in ('python-direct',):
            vm=Interpreter(execution_backend=backend);vm.execute(source)
            self.assertEqual(tuple(vm.variables[k] for k in ('equal','different','self','shared','cycle','copyequal')),(False,True,True,True,False,False))
        native=(Path(__file__).resolve().parents[1]/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        self.assertIn('internal.map.independent-equal.restored-pair-equal: [false]\n',native)
        self.assertIn('internal.map.repeated-reference.restored-pair-equal: [false]\n',native)

    def test_source_ast_prepared_execute_eval_no_vm(self):
        source='A=New Map;B=New Map;R=(A=B);N=(A<>B);'
        for route in ('source','ast','prepared','execute','eval'):
            vm=Interpreter()
            with self.subTest(route=route),patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                elif route=='execute':vm.execute('Var A,B,R,N;Execute("'+source+'");')
                else:vm.execute('A=New Map;B=New Map;R=Eval("A=B");N=Eval("A<>B");')
            self.assertIs(vm.variables['r'],False);self.assertIs(vm.variables['n'],True)

    def test_map_payload_and_foreign_comparison_hooks_never_run(self):
        equal,not_equal=map_identity_operators();seen=[]
        class Hostile:
            def __eq__(self,other):seen.append('eq');raise AssertionError
            def __ne__(self,other):seen.append('ne');raise AssertionError
        a=_TypedMap();b=_TypedMap();a['X']=Hostile();b['X']=Hostile();a['Self']=a;b['Self']=b
        for left,right in ((a,b),(a,Hostile()),(Hostile(),a)):
            self.assertIs(equal(left,right),False);self.assertIs(not_equal(left,right),True)
        self.assertIs(equal(a,a),True);self.assertEqual(seen,[])

    def test_other_kinds_and_separate_ne_protocol_remain_unchanged(self):
        equal,not_equal=map_identity_operators()
        class Host:
            def __eq__(self,other):return 'eq'
            def __ne__(self,other):return 'ne'
        self.assertEqual(equal(Host(),Host()),'eq');self.assertEqual(not_equal(Host(),Host()),'ne')
        for left,right in (({},{}),(_NakedMap(),_NakedMap()),([],[])):
            self.assertIs(equal(left,right),True);self.assertIs(not_equal(left,right),False)
        # The common structure now implements BSL identity natively. The map
        # helper must still delegate to the receiver's own equality protocol.
        left,right=new_structure(),new_structure()
        self.assertIs(equal(left,right),left==right)
        self.assertIs(not_equal(left,right),left!=right)


    def test_boolean_key_domain_is_distinct_and_equal_numbers_replace(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('M=New Map;M.Insert(True,3);M.Insert(1,4);M.Insert(1.00,5);M.Insert("1",6);Boolean=M[True];Number=M[1];Text=M["1"];Count=M.Count();')
        self.assertEqual(tuple(vm.variables[k] for k in ('boolean','number','text','count')),(3,5,6,3))
        vm.execute('K=New Map;M.Insert(K,7);K[1]=8;')
        self.assertEqual(vm.execute('M[K]'),7)
        self.assertIsNone(vm.execute('M[New Map]'))
        self.assertEqual(vm.execute('M.Count()'),4)

    def test_date_boundary_and_operand_effect_order(self):
        from yadinassi.temporal.dates import BSLDate,MAX_TICKS,UnsupportedDateRange
        equal,not_equal=map_identity_operators();m=_TypedMap();boundary=BSLDate(MAX_TICKS,boundary=True)
        for left,right in ((m,boundary),(boundary,m)):
            with self.assertRaises(UnsupportedDateRange):equal(left,right)
            with self.assertRaises(UnsupportedDateRange):not_equal(left,right)
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Left',lambda:seen.append('left') or _TypedMap())
        vm.register_function('Right',lambda:seen.append('right') or _TypedMap())
        self.assertIs(vm.execute('(Left()=Right())'),False);self.assertEqual(seen,['left','right'])

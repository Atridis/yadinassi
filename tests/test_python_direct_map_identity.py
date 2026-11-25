"""Exact direct Map identity, separately evidenced from Array/Structure."""
from yadinassi.execution.codegen.direct_collections import _TypedMap, _NakedMap
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.direct_structure import new_structure


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
            with self.subTest(route=route):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                elif route=='execute':vm.execute('Var A,B,R,N;Execute("'+source+'");')
                else:vm.execute('A=New Map;B=New Map;R=Eval("A=B");N=Eval("A<>B");')
            self.assertIs(vm.variables['r'],False);self.assertIs(vm.variables['n'],True)


    def test_boolean_key_domain_is_distinct_and_equal_numbers_replace(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('M=New Map;M.Insert(True,3);M.Insert(1,4);M.Insert(1.00,5);M.Insert("1",6);Boolean=M[True];Number=M[1];Text=M["1"];Count=M.Count();')
        self.assertEqual(tuple(vm.variables[k] for k in ('boolean','number','text','count')),(3,5,6,3))
        vm.execute('K=New Map;M.Insert(K,7);K[1]=8;')
        self.assertEqual(vm.execute('M[K]'),7)
        self.assertIsNone(vm.execute('M[New Map]'))
        self.assertEqual(vm.execute('M.Count()'),4)

    def test_operand_effect_order(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Left',lambda:seen.append('left') or _TypedMap())
        vm.register_function('Right',lambda:seen.append('right') or _TypedMap())
        self.assertIs(vm.execute('(Left()=Right())'),False);self.assertEqual(seen,['left','right'])

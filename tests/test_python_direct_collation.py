"""Bounded relational UCA ordering, not equality or full native-locale parity."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.text import collation


class DirectCollationTests(unittest.TestCase):
    def test_source_ast_prepared_execute_eval_and_literals_without_vm(self):
        source='A="a";B="A";R=A<B;S="a"<"A";E=(A=B);N=(A<>B);'
        for route in ('source','ast','prepared','execute','eval'):
            vm=Interpreter()
            with self.subTest(route=route):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                elif route=='execute':vm.execute('Var A,B,R,S,E,N;Execute("'+source.replace('"','""')+'");')
                else:vm.execute('A="a";B="A";R=Eval("A<B");S=Eval("""a""<""A""");E=(A=B);N=(A<>B);')
            self.assertEqual(tuple(vm.variables[k] for k in ('r','s','e','n')),(True,True,False,True))


    def test_only_ordering_that_can_see_two_strings_uses_collation(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('A=1; R=A<(2); N=(A<>2); S="a"<"A"; E=("a"="A");')
        generated = plan._plan.generated_source
        self.assertIn('r = a < 2', generated)
        self.assertIn('n = a != 2', generated)
        self.assertIn("e = 'a' == 'A'", generated)
        self.assertEqual(generated.count('_CompareOrder('), 1)
        vm.execute_prepared(plan)
        self.assertEqual(tuple(vm.variables[k] for k in ('r', 'n', 's', 'e')),
                         (True, True, True, False))

    def test_literal_errors_are_runtime_catchable_and_dead_branches_do_no_io(self):
        collation._collator.cache_clear()
        try:
            vm=Interpreter()
            with patch('yadinassi.text.collation.Path.read_bytes',return_value=b'changed') as read:
                plan=vm.prepare('If False Then X="a"<"A";EndIf;Try R="a"<"A";Except Caught=True;EndTry;After=7;')
                self.assertEqual(read.call_count,0)
                vm.execute_prepared(plan)
                self.assertTrue(vm.variables['caught']);self.assertEqual(vm.variables['after'],7)
                self.assertEqual(read.call_count,1)
        finally:collation._collator.cache_clear()


    def test_operand_effects_order_and_registered_kernel_rebinding(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Left',lambda:seen.append('left') or 'a')
        vm.register_function('Right',lambda:seen.append('right') or 'A')
        with patch.object(collation,'string_key',side_effect=AssertionError('foreign kernel')):
            vm.execute('R=Left()<Right();')
        self.assertIs(vm.variables['r'],True);self.assertEqual(seen,['left','right'])

    def test_prepared_reuse_still_checks_resource_bounds(self):
        vm=Interpreter();vm.variables.update(a='a',b='A');plan=vm.prepare('R=A<B;')
        vm.execute_prepared(plan);self.assertIs(vm.variables['r'],True)
        vm.variables['a']='a'*(collation.MAX_STRING_LENGTH+1)
        with self.assertRaises(BSLError):vm.execute_prepared(plan)
        self.assertIs(vm.variables['r'],True)
        self.assertTrue(vm.execute('(A=A)'))

    def test_equality_map_keys_and_find_do_not_use_collation_equivalence(self):
        vm=Interpreter();vm.execute('A="é";B="é";Same=(A=B);LessOrEqual=A<=B;GreaterOrEqual=A>=B;M=New Map;M.Insert(A,1);M.Insert(B,2);Count=M.Count();List=New Array;List.Add(A);Missing=(List.Find(B)=Undefined);')
        self.assertEqual(tuple(vm.variables[k] for k in ('same','lessorequal','greaterorequal','count','missing')),(False,True,True,2,True))

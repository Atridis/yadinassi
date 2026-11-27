import ast
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_plain_map import PlainMap


class DirectMethodDefaultTests(unittest.TestCase):
    def test_ordinary_calls_emit_python_methods_not_a_resolver(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare(
            'M=New Map;M.Вставить(1,2);A=New Array;A.Add(M.Получить(1));'
            'S=New Structure;S.Insert("number",A.Get(0));R=S.number;'
        )
        tree = ast.parse(plan._plan.generated_source)
        call_names = [node.func.id for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertNotIn('_Member', call_names)
        self.assertNotIn('_MethodReceiver', call_names)
        method_calls = [node.func for node in ast.walk(tree)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        receiver_calls = [node for node in method_calls if node.attr.startswith('_bsl_')]
        self.assertEqual({node.attr for node in receiver_calls},
                         {'_bsl_proc_insert', '_bsl_proc_add', '_bsl_value_get'})
        self.assertTrue(all(isinstance(node.value, ast.Name) for node in receiver_calls))
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], Decimal(2))

    def test_foreign_objects_do_not_run_method_hooks(self):
        seen = []

        class Foreign(PlainMap):
            def __getattribute__(self, name):
                seen.append(name)
                raise AssertionError('foreign attribute hook ran')

        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.variables['m'] = Foreign()
        with self.assertRaises(BoundaryViolation):
            vm.execute('R=M.Get(1);')
        self.assertEqual(seen, [])


    def test_fixed_array_read_methods_do_not_bind_instance_attributes(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('A=New Array;A.Add(9);F=New FixedArray(A);A.Set(0,3);')
        self.assertEqual(vm.execute('F.Count()+F.UBound()+F.Get(0)'), Decimal(10))
        with self.assertRaisesRegex(BSLError, 'целое число'):
            vm.execute('F.Get(0.5);')
        with self.assertRaises(BSLError):
            vm.execute('F.Add(7);')

        seen = []
        vm.variables['f']._bsl_value_count = lambda: seen.append(True)
        with self.assertRaises(BoundaryViolation):
            vm.execute('R=F.Count();')
        self.assertEqual(seen, [])


    def test_fixed_structure_property_preserves_output_semantics(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('S=New FixedStructure("Name",9); X=0; Y=99; '
                   'R=S.Property(" NAME ",X); N=S.Count(); U=S.Property("missing",Y);')
        self.assertEqual(tuple(vm.variables[k] for k in ('x','r','n','u','y')),
                         (Decimal(9), True, Decimal(1), False, None))

    def test_codec_collections_keep_boxed_types_and_direct_count(self):
        from yadinassi.collections.maps import BSLMap
        from yadinassi.collections.structures import BSLStructure
        from yadinassi.types.values import BSLArray

        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute("""
A=New Array; A.Add(1); A.Add(2);
S=New Structure("Name",3);
M=New Map; M.Insert("key",4);
RA=ValueFromStringInternal(ValueToStringInternal(A));
RS=ValueFromStringInternal(ValueToStringInternal(S));
RM=ValueFromStringInternal(ValueToStringInternal(M));
N=RA.Count()+RS.Count()+RM.Count();
""")
        self.assertIs(type(vm.variables['ra']), BSLArray)
        self.assertIs(type(vm.variables['rs']), BSLStructure)
        self.assertIs(type(vm.variables['rm']), BSLMap)
        self.assertEqual(vm.variables['n'], Decimal(4))

    def test_table_reads_and_column_growth_use_the_same_owner(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; Columns=T.Columns; N=T.Count(); '
                   'C=Columns.Add("Named"); R=C.Name; Row=T.Add(); Row.Named=7; M=T.Count();')
        self.assertEqual(vm.variables['n'], Decimal(0))
        self.assertEqual(vm.variables['r'], 'Named')
        self.assertEqual(vm.variables['m'], Decimal(1))
        self.assertEqual(vm.execute('Row.Named'), Decimal(7))
        vm.variables['t'].rows = []
        with self.assertRaises(BoundaryViolation):
            vm.execute('N=T.Count();')
        self.assertEqual(vm.variables['n'], Decimal(0))

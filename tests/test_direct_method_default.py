import ast
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_plain_map import PlainMap


class DirectMethodDefaultTests(unittest.TestCase):
    def test_unsupported_direct_method_is_recoverable_without_running_actuals(self):
        events = []
        vm = Interpreter(events.append)
        self.addCleanup(vm.close)
        vm.execute('Function SideEffect() Message("argument"); Return 1; EndFunction')
        source = 'Chars.LF(SideEffect());'
        with self.assertRaises(BSLError):
            vm.execute(source)
        vm.execute('Try '+source+' Except Message("caught"); EndTry;')
        self.assertEqual(events, ["caught"])

    def test_attribute_error_inside_a_method_is_not_a_missing_direct_method(self):
        from unittest.mock import patch

        events = []
        vm = Interpreter(events.append)
        self.addCleanup(vm.close)
        fault = AttributeError("implementation bug", name="_bsl_value_fake")
        with patch("yadinassi.formats.xml.xml_processing.delete_disallowed_xml_characters",
                   side_effect=fault):
            with self.assertRaises(AttributeError) as raised:
                vm.execute('Try X=XMLStringProcessing.DeleteDisallowedXMLCharacters("x"); '
                           'Except Message("should not recover"); EndTry;')
        self.assertIs(raised.exception, fault)
        self.assertEqual(events, [])

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

    def test_value_list_omission_uses_concrete_signature_without_receiver_check(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('L=New ValueList; Item=L.Add(37,,True,); L.Insert(0);')
        source = plan._plan.generated_source
        self.assertIn("l._bsl_value_add_omitted(37, '', True)", source)
        self.assertIn('l._bsl_proc_insert(0)', source)
        self.assertNotIn('_MethodReceiver', source)
        vm.execute_prepared(plan)
        self.assertEqual(vm.execute('Item.Value'), Decimal(37))
        self.assertTrue(vm.execute('Item.Check'))
        self.assertEqual(vm.execute('L.Count()'), Decimal(2))

    def test_json_memory_lifecycle_does_not_open_or_flush_a_file_sink(self):
        from io import StringIO

        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('W=New JSONWriter; W.SetString(New JSONWriterSettings(JSONLineBreak.None)); '
                          'W.WriteStartArray(); W.WriteValue("ok"); W.WriteEndArray(); '
                          'Encoded=W.Close(); Reader=New JSONReader; Reader.SetString(Encoded); '
                          'N=ReadJSON(Reader).Count(); Reader.Close();')
        self.assertNotIn('_MethodReceiver', plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['encoded'], '["ok"]')
        self.assertEqual(vm.variables['n'], Decimal(1))

        writer = vm.variables['w']
        writer.set_string()
        sink = StringIO()
        writer._file = sink
        for source in ('W.SetString();', 'Text=W.Close();'):
            with self.subTest(source=source), self.assertRaises(BSLError):
                vm.execute(source)
            self.assertIs(writer._file, sink)
            self.assertEqual(sink.getvalue(), '')
        writer._file = None
        sink.close()

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

    def test_array_presentation_uses_the_bsl_type_name(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        source = 'A=New Array; A.Add("x"); R=String(A);'
        vm.execute(source)
        self.assertEqual(vm.variables['r'], 'Массив')

    def test_fixed_array_find_accepts_both_python_number_representations(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        source = (
            'A=New Array; A.Add(True); A.Add(1); A.Add("one"); F=New FixedArray(A);'
            'I=F.Найти(1.0); J=F.Find("one"); K=F.Find(False);'
        )
        plan = vm.prepare(source)
        self.assertIn('f._bsl_value_find(', plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['i'], vm.variables['j'], vm.variables['k']), (1, 2, None))

        class Meta(type):
            def __eq__(self, other):
                raise AssertionError("host type equality ran")

        class Foreign(metaclass=Meta):
            def __eq__(self, other):
                raise AssertionError("host value equality ran")

        fixed = vm.variables['f']
        fixed.items = (Foreign(),) + fixed.items
        self.assertEqual(vm.execute('F.Find(1)'), Decimal(2))

    def test_value_table_index_mutations_are_direct(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        source = (
            'T=New ValueTable; T.Columns.Add("A"); T.Columns.Add("B"); I=T.Indexes;'
            'A=I.Add("A"); B=I.Add("B"); I.Удалить(0); C=I.Count();'
            'I.Delete(B); D=I.Count(); I.Add("A"); I.Очистить(); E=I.Count();'
        )
        plan = vm.prepare(source)
        self.assertIn('i._bsl_proc_delete(0)', plan._plan.generated_source)
        self.assertIn('i._bsl_proc_clear()', plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual(tuple(vm.variables[k] for k in ('c', 'd', 'e')), (1, 0, 0))

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

    def test_codec_collections_keep_mutation_on_the_native_objects(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        for code, key in (('S=New Structure; R=ValueFromStringInternal(ValueToStringInternal(S)); '
                           'R.Вставить("a",23); V=R.A;', 'v'),
                          ('M=New Map; R=ValueFromStringInternal(ValueToStringInternal(M)); '
                           'R.Вставить("a",23); V=R.Count()*23;', 'v')):
            plan = vm.prepare(code)
            self.assertIn("r._bsl_proc_insert('a', 23)", plan._plan.generated_source)
            vm.execute_prepared(plan)
            self.assertEqual(vm.variables[key], Decimal(23))

    def test_table_read_methods_keep_the_bounded_slice_limit(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable;T.Columns.Add("Amount");R=T.Add();R.Amount=12;')
        self.assertIs(vm.execute('T.Find(12,"Amount")'), vm.variables['r'])
        self.assertEqual(vm.execute('T.ВыгрузитьКолонку("Amount")').items, [Decimal(12)])
        self.assertEqual(vm.execute('T.Итог("Amount")'), Decimal(12))
        vm.variables['t']._bounded_slice_read = True
        self.assertEqual(vm.execute('T.Count()'), Decimal(1))
        for expr in ('T.Find(12,"Amount")', 'T.ВыгрузитьКолонку("Amount")', 'T.Итог("Amount")'):
            with self.subTest(expr=expr), self.assertRaises(BSLError):
                vm.execute(expr)

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

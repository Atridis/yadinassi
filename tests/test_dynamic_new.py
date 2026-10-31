"""Documented functional New syntax; no synthetic native output fixtures."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.values import BSLArray, BSLType


class DynamicNewTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()

    def test_keyword_and_type_aliases(self):
        for keyword in ('Новый', 'New', 'нОвЫй', 'nEw'):
            for name in ('Массив', 'Array', 'мАсСиВ', 'aRrAy'):
                with self.subTest(keyword=keyword, name=name):
                    self.assertIsInstance(self.vm.execute(f'{keyword}("{name}")'), BSLArray)
                    self.assertIsInstance(self.vm.execute(f'{keyword}(Type("{name}"))'), BSLArray)

    def test_empty_mutable_collections(self):
        for name in ('Array', 'Structure', 'Map'):
            self.vm.execute(f'x = New("{name}");')
            self.assertEqual(self.vm.execute('x.Count()'), Decimal(0))
            self.assertEqual(self.vm.execute('TypeOf(x)'), self.vm.execute(f'Type("{name}")'))

    def test_each_concrete_type_identity_is_supported_or_rejected(self):
        for value_type in BSLType:
            self.vm.variables['kind'] = value_type
            if value_type in (BSLType.ARRAY, BSLType.STRUCTURE, BSLType.MAP, BSLType.FIXED_STRUCTURE,
                              BSLType.NUMBER_QUALIFIERS, BSLType.STRING_QUALIFIERS,
                              BSLType.DATE_QUALIFIERS, BSLType.BINARY_DATA_QUALIFIERS,
                              BSLType.TYPE_DESCRIPTION, BSLType.VALUE_TABLE, BSLType.VALUE_LIST, BSLType.VALUE_TREE,
                              BSLType.UUID, BSLType.TEXT_DOCUMENT, BSLType.JSON_READER,
                              BSLType.JSON_WRITER, BSLType.JSON_WRITER_SETTINGS,
                              BSLType.TEXT_READER, BSLType.TEXT_WRITER,
                              BSLType.XML_READER, BSLType.XML_WRITER,
                              BSLType.XML_READER_SETTINGS, BSLType.XML_WRITER_SETTINGS):
                self.assertEqual(self.vm.execute('TypeOf(New(kind))'), value_type)
            else:  # FixedArray/FixedMap need arguments; other scalar types have no factory.
                with self.assertRaises(BSLError):
                    self.vm.execute('New(kind)')

    def test_constructor_parameter_array_and_multidimensional_shape(self):
        self.vm.execute('args = New Array; args.Add(2); args.Add(3); x = New(Type("Array"), args); '
                        'x[0][1] = "Я😀";')
        self.assertEqual(self.vm.execute('x.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('x[0].Count()'), Decimal(3))
        self.assertEqual(self.vm.execute('x[0][1]'), 'Я😀')
        self.assertIsNone(self.vm.execute('x[1][1]'))
        self.assertEqual(self.vm.execute('args[0]'), Decimal(2))

    def test_structure_values_keep_references(self):
        self.vm.execute('child = New Array; args = New Array; args.Add("Имя,Данные"); '
                        'args.Add("Я😀"); args.Add(child); x = New("Structure", args); '
                        'child.Add(7); args[1] = "other";')
        self.assertEqual(self.vm.execute('x.Имя'), 'Я😀')
        self.assertIs(self.vm.execute('x.Данные'), self.vm.execute('child'))
        self.assertEqual(self.vm.execute('x.Данные[0]'), Decimal(7))

    def test_all_fixed_constructors_and_mutable_inverse(self):
        for mutable, fixed, setup, read in (
                ('Array', 'FixedArray', 'source.Add("Я😀");', 'target[0]'),
                ('Structure', 'FixedStructure', 'source.Insert("Имя", "Я😀");', 'target.Имя'),
                ('Map', 'FixedMap', 'source.Insert("Имя", "Я😀");', 'target["Имя"]')):
            with self.subTest(fixed=fixed):
                self.vm.execute(f'source = New("{mutable}"); {setup} '
                                f'args = New Array; args.Add(source); target = New(Type("{fixed}"), args);')
                self.assertEqual(self.vm.execute(read), 'Я😀')
                self.assertEqual(self.vm.execute('TypeOf(target)'), self.vm.execute(f'Type("{fixed}")'))
                self.vm.execute(f'args[0] = target; target = New("{mutable}", args);')
                self.assertEqual(self.vm.execute(read), 'Я😀')
                self.assertEqual(self.vm.execute('TypeOf(target)'), self.vm.execute(f'Type("{mutable}")'))

    def test_non_array_second_argument_is_ignored_as_documented(self):
        for value in ('Undefined', '0', 'True', '"ignored"', 'Type("Array")',
                      'New Structure', 'New Map', 'New FixedArray(New Array(3))'):
            with self.subTest(value=value):
                self.assertEqual(self.vm.execute(f'New("Array", {value}).Count()'), Decimal(0))

    def test_non_array_does_not_bypass_required_constructor_arguments(self):
        for value in ('Undefined', '1', 'New FixedArray(New Array)'):
            with self.assertRaises(BSLError):
                self.vm.execute(f'New("FixedArray", {value})')

    def test_empty_argument_array_means_no_constructor_arguments(self):
        self.assertEqual(self.vm.execute('New("Array", New Array).Count()'), Decimal(0))
        with self.assertRaises(BSLError):
            self.vm.execute('New("FixedArray", New Array)')

    def test_parameter_array_is_not_deep_copied(self):
        self.vm.execute('args = New Array; args.Add("Self"); args.Add(args); '
                        'x = New("Structure", args);')
        self.assertIs(self.vm.execute('x.Self'), self.vm.execute('args'))

    def test_argument_expressions_evaluated_once_left_to_right(self):
        self.vm.execute('Var trace; '
                        'Function Kind() trace = trace + "T"; Return Type("Array"); EndFunction '
                        'Function Params() trace = trace + "P"; a = New Array; a.Add(2); Return a; EndFunction '
                        'trace = ""; x = New(Kind(), Params());')
        self.assertEqual(self.vm.execute('trace'), 'TP')
        self.assertEqual(self.vm.execute('x.Count()'), Decimal(2))

    def test_ignored_second_expression_still_executes(self):
        self.vm.execute('Var calls; Function Ignore() calls = calls + 1; Return False; EndFunction '
                        'calls = 0; x = New("Array", Ignore());')
        self.assertEqual(self.vm.execute('calls'), Decimal(1))
        self.assertEqual(self.vm.execute('x.Count()'), Decimal(0))

    def test_first_expression_error_prevents_second_expression(self):
        self.vm.execute('Var calls; Function Params() calls = calls + 1; Return New Array; EndFunction '
                        'calls = 0; Try x = New(1 / 0, Params()); Except caught = True; EndTry;')
        self.assertEqual(self.vm.execute('calls'), Decimal(0))

    def test_invalid_type_values_and_names(self):
        for expression in ('Undefined', '1', 'True', 'New Array', '""', '"Unknown"',
                           '" Array "', '"__import__"', 'Type("String")', '"Number"'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(f'New({expression})')

    def test_existing_target_preserved_on_constructor_error_and_recovery(self):
        self.vm.execute('target = "old"; args = New Array; args.Add(-1); '
                        'Try target = New("Array", args); Except caught = True; EndTry;')
        self.assertEqual(self.vm.execute('target'), 'old')
        self.assertTrue(self.vm.execute('caught'))
        self.vm.execute('args[0] = 2; target = New("Array", args);')
        self.assertEqual(self.vm.execute('target.Count()'), Decimal(2))

    def test_invalid_syntax_prevents_all_execution(self):
        for expression in ('New()', 'New(,)', 'New("Array",)', 'New("Array",,)',
                           'New("Array", New Array, 1)', 'New("Array"', 'New(Undefined,)'):
            self.vm.execute('saved = 0;')
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(f'saved = 1; x = {expression};')
            self.assertEqual(self.vm.execute('saved'), Decimal(0))

    def test_nested_conditional_group_and_postfix(self):
        self.assertEqual(self.vm.execute('(New(?(True, "Array", "bad"))).Count()'), Decimal(0))
        self.vm.execute('x = New("Structure", New("Array")); x.Insert("Имя", 7);')
        self.assertEqual(self.vm.execute('x.Имя'), Decimal(7))

    def test_eval_and_execute_use_current_context(self):
        self.vm.execute('kind = Type("Array"); args = New Array; args.Add(2); '
                        'x = Eval("New(kind, args)"); Execute("x = New(kind);");')
        self.assertEqual(self.vm.execute('x.Count()'), Decimal(0))

    def test_routine_returns_and_value_parameters(self):
        self.vm.execute('Function Make(Val kind, Val params) Return New(kind, params); EndFunction '
                        'args = New Array; args.Add(3); x = Make(Type("Array"), args);')
        self.assertEqual(self.vm.execute('x.Count()'), Decimal(3))

    def test_internal_serialization_both_directions_all_collection_types(self):
        for name in ('Array', 'Structure', 'Map', 'FixedArray', 'FixedStructure', 'FixedMap'):
            source = {'FixedArray': 'New Array', 'FixedStructure': 'New Structure',
                      'FixedMap': 'New Map'}.get(name)
            self.vm.execute('args = New Array;')
            if source:
                self.vm.execute(f'args.Add({source});')
            self.vm.execute(f'original = New(Type("{name}"), args); '
                            'encoded = ValueToStringInternal(original); '
                            'copy = ValueFromStringInternal(encoded);')
            self.assertEqual(self.vm.execute('TypeOf(copy)'), self.vm.execute(f'Type("{name}")'))
            self.assertEqual(self.vm.execute('ValueToStringInternal(copy)'), self.vm.execute('encoded'))
            self.assertIsNot(self.vm.execute('copy'), self.vm.execute('original'))

    def test_restored_type_is_usable_and_payload_roundtrips(self):
        self.vm.execute('kind = ValueFromStringInternal(ValueToStringInternal(Type("Structure"))); '
                        'args = New Array; args.Add("Имя"); args.Add("Я😀"); '
                        'x = New(kind, args); copy = ValueFromStringInternal(ValueToStringInternal(x));')
        self.assertEqual(self.vm.execute('copy.Имя'), 'Я😀')

    def test_hostile_values_are_not_coerced_or_iterated(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('str called')
            def __iter__(self):
                raise AssertionError('iter called')
        self.vm.variables['hostile'] = Hostile()
        self.assertEqual(self.vm.execute('New("Array", hostile).Count()'), Decimal(0))
        with self.assertRaises(BSLError):
            self.vm.execute('New(hostile)')
        class HostileString(str):
            def casefold(self):
                raise AssertionError('casefold called')
        self.vm.variables['hostile'] = HostileString('Array')
        with self.assertRaises(BSLError):
            self.vm.execute('New(hostile)')

    def test_dynamic_and_static_use_same_explicit_host_registry(self):
        calls = []
        def factory(*args):
            calls.append(args)
            return 'made'
        self.vm.register_type('Factory', factory, 'Фабрика')
        self.assertEqual(self.vm.execute('New("фАБРИКА")'), 'made')
        self.vm.execute('args = New Array; args.Add("Я😀"); args.Add(7);')
        self.assertEqual(self.vm.execute('New("Factory", args)'), 'made')
        self.assertEqual(calls, [(), ('Я😀', Decimal(7))])

    def test_constructor_resource_limits_are_shared_with_static_form(self):
        self.vm.execute('args = New Array; args.Add(1000001);')
        with self.assertRaisesRegex(BSLError, "предел ресурсов"):
            self.vm.execute('New("Array", args)')
        self.assertEqual(self.vm.execute('args[0]'), Decimal(1000001))

    def test_ignored_second_expression_error_is_not_swallowed(self):
        self.vm.execute('saved = "old"; '
                        'Try saved = New("Array", 1 / 0); Except caught = True; EndTry;')
        self.assertEqual(self.vm.execute('saved'), 'old')
        self.assertTrue(self.vm.execute('caught'))

    def test_argument_effects_precede_type_validation_like_host_calls(self):
        self.vm.execute('Var calls; Function Params() calls = calls + 1; Return 1; EndFunction '
                        'calls = 0; Try x = New("Missing", Params()); Except caught = True; EndTry;')
        self.assertEqual(self.vm.execute('calls'), Decimal(1))
        self.assertTrue(self.vm.execute('caught'))

    def test_constructor_error_reports_dynamic_new_source_location(self):
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('x = 1;\nvalue = New("Missing");', '/virtual/Динамический.bsl')
        message = str(caught.exception)
        self.assertIn('/virtual/Динамический.bsl:2:9:', message)
        self.assertNotIn('Traceback', message)

    def test_imported_exported_factory_with_bom_and_canonical_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            (root/'factory.bsl').write_text('Function Make(Val kind, Val args) Export '
                                           'Return New(kind, args); EndFunction', encoding='utf-8-sig')
            main = root/'main.bsl'
            main.write_text('// #import factory.bsl\nargs = New Array; args.Add(2); '
                            'x = factory.Make(Type("Array"), args);', encoding='utf-8-sig')
            self.vm.execute(main.read_text(encoding="utf-8-sig"), str(main))
            self.assertEqual(self.vm.execute('x.Count()'), Decimal(2))


if __name__ == '__main__':
    unittest.main()

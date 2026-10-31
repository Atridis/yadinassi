"""Supported type identities and their boundaries; not native-1C goldens."""

from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.values import BSLArray, BSLObject, BSLType


class TypeValueTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def evaluate(self, expression):
        # Top-level unparenthesized = is assignment in the existing parser.
        return self.vm.execute(f"({expression})")

    def test_type_names_and_function_names_are_bilingual_and_case_insensitive(self):
        pairs = [('Неопределено', 'Undefined'), ('Булево', 'Boolean'),
                 ('Число', 'Number'), ('Строка', 'String'), ('Массив', 'Array'),
                 ('Структура', 'Structure'), ('Соответствие', 'Map'),
                 ('ФиксированныйМассив', 'FixedArray'),
                 ('ФиксированнаяСтруктура', 'FixedStructure'),
                 ('ФиксированноеСоответствие', 'FixedMap'),
                 ('КлючИЗначение', 'KeyAndValue'), ('Тип', 'Type')]
        values = []
        for russian, english in pairs:
            with self.subTest(type=english):
                value = self.vm.execute(f'Тип("{russian}")')
                self.assertIs(type(value), BSLType)
                self.assertEqual(self.vm.execute(f'tYpE("{english.upper()}")'), value)
                self.assertEqual(self.vm.execute(f'тИп("{russian.lower()}")'), value)
                self.assertEqual(self.vm.execute(f'String(Type("{english}"))'),
                                 'Не определено' if english == 'Undefined' else russian)
                self.assertIs(self.evaluate(f'TypeOf(Type("{english}")) = Тип("Тип")'), True)
                values.append(value)
        self.assertEqual(len(set(values)), 12)

    def test_type_of_each_supported_value(self):
        cases = [('Undefined', 'Undefined'), ('Неопределено', 'Undefined'),
                 ('True', 'Boolean'), ('False', 'Boolean'), ('0', 'Number'),
                 ('-0', 'Number'), ('1.25', 'Number'), ('Number("42")', 'Number'),
                 ('""', 'String'), ('"Число"', 'String'), ('New Array', 'Array'),
                 ('New Structure', 'Structure'), ('New Map', 'Map'),
                 ('New FixedArray(New Array)', 'FixedArray'),
                 ('New FixedStructure(New Structure)', 'FixedStructure'),
                 ('New FixedMap(New Map)', 'FixedMap'),
                 ('Тип("Число")', 'Type')]
        for expression, name in cases:
            with self.subTest(expression=expression):
                self.assertIs(self.evaluate(f'тИпЗнЧ({expression}) = tYpE("{name}")'), True)
                self.assertIs(self.evaluate(f'TyPeOf({expression}) <> Тип("{name}")'), False)
        self.vm.execute('Var empty;')
        self.assertIs(self.evaluate('TypeOf(empty) = Type("Undefined")'), True)

    def test_fixed_and_mutable_types_remain_distinct_identities(self):
        for mutable, fixed in [('Array', 'FixedArray'), ('Structure', 'FixedStructure'),
                               ('Map', 'FixedMap')]:
            with self.subTest(type=fixed):
                self.assertIs(self.evaluate(f'Type("{mutable}") = Type("{fixed}")'), False)
                self.assertIs(self.evaluate(f'TypeOf(New {fixed}(New {mutable})) = Type("{mutable}")'), False)
                self.vm.execute(f'''
                    kinds = New Map; kinds[Type("{mutable}")] = "mutable";
                    kinds[Type("{fixed}")] = "fixed";
                    Message(kinds.Count()); Message(kinds[TypeOf(New {fixed}(New {mutable}))]);
                ''')
        self.assertEqual(self.output, ['2', 'fixed'] * 3)

    def test_type_of_tracks_current_value_not_variable_declaration(self):
        self.vm.execute('''
            Var value;
            Message(TypeOf(value) = Type("Undefined"));
            value = 1; Message(TypeOf(value) = Type("Number"));
            value = True; Message(TypeOf(value) = Type("Boolean"));
            value = "1"; Message(TypeOf(value) = Type("String"));
            value = Type("Map"); Message(TypeOf(value) = Type("Type"));
        ''')
        self.assertEqual(self.output, ['Да'] * 5)

    def test_distinct_types_and_presentations_never_compare_equal(self):
        for expression in ['TypeOf(True) = TypeOf(1)',
                           'TypeOf(False) = TypeOf(0)',
                           'TypeOf(1) = TypeOf("1")',
                           'Type("Number") = "Число"',
                           '"Число" = Type("Number")',
                           'Type("Undefined") = Undefined',
                           'Type("Type") = Type("Number")',
                           'Type("Number") = 1', 'Type("Boolean") = True']:
            with self.subTest(expression=expression):
                self.assertIs(self.evaluate(expression), False)
        self.assertIs(self.evaluate('Type("Number") <> "Число"'), True)

    def test_types_can_be_stored_found_and_used_as_value_based_map_keys(self):
        self.vm.execute('''
            types = New Array;
            types.Add(Type("Число")); types.Add(Type("String"));
            Message(types.Find(TypeOf(42))); Message(types.Find(Type("Array")) = Undefined);
            record = New Structure("Kind", types[0]);
            Message(record.Kind = Type("Number"));
            map = New Map;
            map[Type("Number")] = "first";
            map.Insert(TypeOf(0), "updated");
            map["Число"] = "string";
            map[Type("Boolean")] = "boolean";
            Message(map.Count()); Message(map[record.Kind]);
            Message(map[TypeOf(True)]); Message(map["Число"]);
            map.Delete(Type("ЧИСЛО"));
            Message(map.Get(TypeOf(1)) = Undefined); Message(map.Count());
        ''')
        self.assertEqual(self.output, ['0', 'Да', 'Да', '3', 'updated',
                                       'boolean', 'string', 'Да', '2'])

    def test_type_of_collection_pairs_and_their_fields(self):
        for collection in ['New Structure("Amount", Type("Number"))', 'New Map']:
            with self.subTest(collection=collection):
                self.vm.execute(f'items = {collection};')
                if collection == 'New Map':
                    self.vm.execute('items["Amount"] = Type("Number");')
                self.vm.execute('''
                    For Each pair In items Do
                        Message(TypeOf(pair) = Type("KeyAndValue"));
                        Message(TypeOf(pair.Key) = Type("String"));
                        Message(TypeOf(pair.Value) = Type("Type"));
                        Message(pair.Value = TypeOf(3));
                    EndDo;
                ''')
        self.assertEqual(self.output, ['Да'] * 8)

    def test_routine_pass_return_val_and_reference_rebinding(self):
        self.vm.execute('''
            Function Echo(Val value) Return value; EndFunction
            Procedure ByValue(Val value) value = Type("String"); EndProcedure
            Procedure ByReference(value) value = Type("String"); EndProcedure
            original = Type("Number");
            Message(Echo(original) = TypeOf(1));
            ByValue(original); Message(original = Type("Number"));
            ByReference(original); Message(original = Type("String"));
            Message(TypeOf(Echo(original)) = Type("Type"));
        ''')
        self.assertEqual(self.output, ['Да'] * 4)

    def test_type_queries_evaluate_arguments_once_and_allow_lazy_dispatch(self):
        self.vm.execute('''
            Var calls;
            Function NextValue() calls = calls + 1; Return 42; EndFunction
            Function TypeName() calls = calls + 1; Return "Number"; EndFunction
            calls = 0;
            Message(TypeOf(NextValue()) = Type(TypeName()));
            Message(calls);
            value = New Array;
            Message(?(TypeOf(value) = Type("Array"), value.Count(), Type("Missing")));
            Message(TypeOf(1) = Type("Number") Or Type("Missing") = Type("Type"));
        ''')
        self.assertEqual(self.output, ['Да', '2', '0', 'Да'])

    def test_display_and_string_concatenation_use_russian_presentation(self):
        self.vm.execute('''
            Message(Type("Number")); Message(String(Type("Type")));
            Message("Тип: " + TypeOf(New Map));
        ''')
        self.assertEqual(self.output, ['Число', 'Тип', 'Тип: Соответствие'])

    def test_unknown_and_out_of_scope_type_names_are_catchable(self):
        for name in ['', ' Number ', 'Число ', 'UnknownTree', 'НеизвестноеДерево', 'UnknownTreeRow',
                     'FixedList', 'ФиксированныйСписок', 'UnsupportedBinaryStream',
                     'СправочникСсылка.Товары', '__class__', 'Decimal', 'int']:
            with self.subTest(name=name):
                self.vm.execute(f'''Try Type("{name}");
                    Except Message("caught"); EndTry;''')
        self.assertEqual(self.output, ['caught'] * 13)

    def test_type_name_does_not_implicitly_convert_other_values(self):
        for expression in ['1', 'True', 'Undefined', 'New Array', 'Type("Number")']:
            with self.subTest(expression=expression), self.assertRaisesRegex(
                    BSLRuntimeError, 'Имя типа должно быть строкой'):
                self.vm.execute(f'Type({expression})')

    def test_exact_one_argument_required_and_omissions_rejected(self):
        for expression in ['Type()', 'Type("Number", "String")', 'TypeOf()',
                           'TypeOf(1, 2)', 'Type(,)', 'TypeOf(,)']:
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)
        self.assertIs(self.evaluate('TypeOf(Undefined) = Type("Undefined")'), True)

    def test_type_values_are_opaque_and_not_ordered_numeric_or_callable(self):
        self.vm.execute('t = Type("Number");')
        for expression in ['t.Name', 't.Value', 't.__class__', 't.name = "String"',
                           't.value = "Строка"', 't[0]', 't()', 't.Get()',
                           't < t', 't <= t', 't > t', 't >= t', 't + 1',
                           '-t', 'Not t', 'Boolean(t)', 'Number(t)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
            self.assertIs(self.evaluate('t = Type("Число")'), True)
        for code in ['For Each x In t Do EndDo;', 'If t Then Message(1); EndIf;']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)

    def test_type_values_do_not_add_scalar_constructors(self):
        for code in ['New Type("Number")', 'New Тип("Число")',
                     'New Number', 'New Undefined', 'New KeyAndValue',
                     'New (Type("Number"))']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertIs(self.evaluate('TypeOf(New Array) = Type("Array")'), True)
        self.assertIs(self.evaluate('TypeOf(New (Type("Array"))) = Type("Array")'), True)

    def test_error_location_and_recovery_preserve_existing_type_value(self):
        self.vm.execute('t = Type("Number");')
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('\n t = Type("Missing");', 'types.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('types.bsl', 2))
        self.assertIs(self.evaluate('t = Type("Number")'), True)
        self.vm.execute('''Try Type("Missing");
            Except Message(Find(ErrorDescription(), "Тип не поддерживается") > 0); EndTry;
            Message(TypeOf(1) = Type("Number"));''')
        self.assertEqual(self.output, ['Да', 'Да'])

    def test_imports_and_independent_interpreters_share_type_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / 'Kinds.bsl'
            module.write_text('''Function Kind(Val value) Export Return TypeOf(value); EndFunction
                Function NumberKind() Export Return Type("Number"); EndFunction
                Function Table() Export
                    result = New Map; result[Type("Number")] = "imported"; Return result;
                EndFunction''', encoding='utf-8-sig')
            self.vm.execute('''// #Импорт Kinds.bsl
                Message(Kinds.Kind(Type("Map")) = Type("Type"));
                Message(Kinds.NumberKind() = TypeOf(1));
                map = Kinds.Table(); Message(map[TypeOf(42)]);''', str(root / 'Main.bsl'))
            self.assertEqual(self.output, ['Да', 'Да', 'imported'])
        other = Interpreter()
        self.assertEqual(self.vm.execute('Type("Number")'), other.execute('TypeOf(42)'))

    def test_host_extensions_remain_constructible_but_are_not_reflected(self):
        class Extension(BSLObject):
            pass

        self.vm.register_type('Extension', Extension)
        self.vm.execute('item = New Extension;')
        self.assertIsInstance(self.vm.variables['item'], Extension)
        for expression in ['TypeOf(item)', 'Type("Extension")', 'TypeOf(Message)']:
            with self.subTest(expression=expression), self.assertRaisesRegex(
                    BSLRuntimeError, 'не поддерживается'):
                self.vm.execute(expression)

    def test_host_subclasses_and_metaclass_hooks_are_not_called(self):
        class HostileMeta(type):
            def __eq__(self, other):
                raise AssertionError('metaclass equality must not run')

            def __hash__(self):
                raise AssertionError('metaclass hashing must not run')

        class Hostile(metaclass=HostileMeta):
            pass

        class ArraySubclass(BSLArray):
            pass

        class StringSubclass(str):
            pass

        for value in [1, 1.5, object(), Hostile(), ArraySubclass(), StringSubclass('Number')]:
            with self.subTest(kind=type(value).__name__):
                self.vm.variables['host'] = value
                with self.assertRaisesRegex(BSLRuntimeError, 'не поддерживается'):
                    self.vm.execute('TypeOf(host)')
        self.vm.variables['host'] = StringSubclass('Number')
        with self.assertRaisesRegex(BSLRuntimeError, 'должно быть строкой'):
            self.vm.execute('Type(host)')


if __name__ == '__main__':
    unittest.main()

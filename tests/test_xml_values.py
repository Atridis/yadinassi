"""Native-backed scalar XML subset; additional case variants are local policy."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.values import BSLType
from yadinassi.xml_values import xml_string, xml_value


class XMLValueTests(unittest.TestCase):
    def test_writer_aliases_and_types(self):
        vm = Interpreter()
        for name in ('XMLСтрока', 'XMLString', 'xMlСтРоКа', 'xMlStRiNg'):
            for value, expected in [('Я😀<&"', 'Я😀<&"'), ('', ''), (True, 'true'), (False, 'false')]:
                vm.variables['value'] = value
                actual = vm.execute(f'{name}(value)')
                self.assertIs(type(actual), str)
                self.assertEqual(actual, expected)

    def test_reader_aliases_and_type_identities(self):
        vm = Interpreter()
        for name in ('XMLЗначение', 'XMLValue', 'xMlЗнАчЕнИе', 'xMlVaLuE'):
            for type_name in ('Булево', 'Boolean', 'бУлЕвО', 'bOoLeAn'):
                for text, expected in [('true', True), ('false', False), ('1', True), ('0', False),
                                       ('TRUE', True), ('FALSE', False), ('TrUe', True), ('FaLsE', False)]:
                    vm.variables['text'] = text
                    actual = vm.execute(f'{name}(Type("{type_name}"), text)')
                    self.assertIs(actual, expected)
        self.assertIs(vm.execute('XMLValue(TypeOf(True), "false")'), False)

    def test_strings_are_unchanged_and_never_parsed(self):
        values = ['', ' \t\nЯ😀\r ', '<x>&amp;&#65;</x>',
                  '<!DOCTYPE x SYSTEM "file:///never-read"><x>&entity;</x>',
                  '\x00\ud800', 'e\u0301', 'true', '1', 'a' * 100000]
        for text in values:
            self.assertIs(xml_string(text), text)
            self.assertIs(xml_value(BSLType.STRING, text), text)

    def test_boolean_reader_rejects_whitespace_and_invalid_tokens(self):
        for text in ('', ' true ', '\ttrue', 'false\n', '\r0\n', 'falſe', 'ＴＲＵＥ', 'Да', 'Нет', '2', '-0', '01', '1.0',
                     ' true false ', 'tr ue', '\vtrue', '\ftrue', '\u00a0true',
                     '\u0085false', 'true\x00', '&true;', '<x>true</x>'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                xml_value(BSLType.BOOLEAN, text)

    def test_roundtrip_and_internal_serialization_both_directions(self):
        vm = Interpreter()
        for value in (True, False, '', 'Я😀<&"\n'):
            vm.variables['value'] = value
            self.assertEqual(vm.execute('XMLValue(TypeOf(value), XMLString(value))'), value)
            self.assertIs(type(vm.execute('XMLValue(TypeOf(value), XMLString(value))')), type(value))
            self.assertEqual(vm.execute('ValueFromStringInternal(ValueToStringInternal(XMLString(value)))'), xml_string(value))
            self.assertEqual(vm.execute('XMLValue(TypeOf(value), ValueFromStringInternal(ValueToStringInternal(XMLString(value))))'), value)
            self.assertEqual(vm.execute('ValueFromStringInternal(ValueToStringInternal(XMLValue(TypeOf(value), XMLString(value))))'), value)
        self.assertEqual(vm.execute('ValueToStringInternal(XMLValue(Type("Boolean"), "1"))'), '{"B",1}')
        self.assertEqual(vm.execute('ValueToStringInternal(XMLString(False))'), '{"S","false"}')

    def test_unsupported_types_do_not_coerce_or_call_host_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('host string hook')
            def __eq__(self, other):
                raise AssertionError('host comparison hook')
        for value in (None, Decimal(1), 1, BSLType.STRING, Hostile()):
            with self.assertRaises(TypeError):
                xml_string(value)
        for kind in (None, 'String', True, Hostile()):
            with self.assertRaises(TypeError):
                xml_value(kind, 'true')
        for text in (None, True, Decimal(1), Hostile()):
            with self.assertRaises(TypeError):
                xml_value(BSLType.STRING, text)
        for kind in BSLType:
            if kind not in (BSLType.STRING, BSLType.BOOLEAN):
                with self.assertRaisesRegex(TypeError, 'пока поддерживаются'):
                    xml_value(kind, '')

    def test_arity_errors_preservation_and_recovery(self):
        vm = Interpreter()
        expressions = ('XMLString()', 'XMLString(True, False)', 'XMLValue()',
                       'XMLValue(Type("String"))', 'XMLValue(Type("String"), "x", 1)',
                       'XMLValue(, "x")', 'XMLString(1)', 'XMLString(Undefined)',
                       'XMLString(New Array)', 'XMLValue("String", "x")',
                       'XMLValue(Type("String"), 1)', 'XMLValue(Type("Number"), "1")',
                       'XMLValue(Type("Boolean"), " true ")')
        for expression in expressions:
            with self.subTest(expression=expression):
                vm.execute('saved = "old";')
                with self.assertRaises(BSLError):
                    vm.execute('saved = ' + expression)
                self.assertEqual(vm.execute('saved'), 'old')
                vm.execute(f'Try saved = {expression}; Except caught = True; EndTry;')
                self.assertTrue(vm.execute('caught'))
                self.assertEqual(vm.execute('saved'), 'old')
                self.assertIs(vm.execute('XMLValue(Type("Boolean"), "1")'), True)

    def test_arguments_evaluate_once_left_to_right(self):
        vm = Interpreter()
        vm.execute('''Перем Порядок;
Функция Первый()
    Порядок = Порядок + "1";
    Возврат Тип("Булево");
КонецФункции
Функция Второй()
    Порядок = Порядок + "2";
    Возврат "true";
КонецФункции
Порядок = "";
Результат = XMLЗначение(Первый(), Второй());''')
        self.assertEqual(vm.execute('Порядок'), '12')
        self.assertIs(vm.execute('Результат'), True)

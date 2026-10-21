"""Owner-backed XML cleanup and explicit local safety/standard boundaries."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi import xml_processing
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLType, HostFunction, NULL
from yadinassi.xml_processing import (
    BSLXMLStringProcessingManager, XML_STRING_PROCESSING,
    delete_disallowed_xml_characters as clean,
)


ROOT = Path(__file__).resolve().parents[1]
MANAGER_ID = '8f646b4e-fc39-44c7-85a2-c2eb39cdf361'
CONTROLS = ''.join(map(chr, (0, 1, 8, 9, 10, 11, 12, 13, 14, 31,
                             32, 127, 132, 133, 134, 159, 160)))


class XMLCharacterCleanupTests(unittest.TestCase):
    def test_observed_controls_and_default(self):
        xml10 = ''.join(map(chr, (9, 10, 13, 32, 127, 132, 133, 134, 159, 160)))
        xml11 = ''.join(map(chr, (9, 10, 13, 32, 133, 160)))
        self.assertEqual(clean(CONTROLS), xml10)
        self.assertEqual(clean(CONTROLS, '1.0'), xml10)
        self.assertEqual(clean(CONTROLS, '1.1'), xml11)

    def test_observed_unicode_boundaries_and_separated_surrogates(self):
        original = '\ud7ff😀\ue000\ufdd0\ufffd\ufffe\uffff\ud800A\udc00'
        for version in ('1.0', '1.1'):
            self.assertEqual(clean(original, version), '\ud7ff😀\ue000\ufdd0\ufffdA')
            self.assertEqual(clean('\ud800\x00\udc00', version), '')

    def test_xml_standard_character_ranges(self):
        # Extends native boundary observations with the documented XML ranges;
        # this exhaustive BMP check is local coverage, not a new native fixture.
        text = ''.join(chr(code) for code in range(0x10000))
        # The input contains one adjacent high/low pair at U+DBFF / U+DC00.
        pair = chr(0x10FC00)
        expected10 = '\t\n\r' + ''.join(map(chr, range(0x20, 0xD800)))
        expected10 += pair + ''.join(map(chr, range(0xE000, 0xFFFE)))
        expected11 = expected10.translate(dict.fromkeys(
            [*range(0x7F, 0x85), *range(0x86, 0xA0)]))
        self.assertEqual(clean(text, '1.0'), expected10)
        self.assertEqual(clean(text, '1.1'), expected11)
        # XML permits supplementary-plane characters, including noncharacters.
        supplementary = '\U00010000\U0001fffe\U0001ffff\U0010fffe\U0010ffff'
        self.assertEqual(clean(supplementary), supplementary)
        self.assertEqual(clean(supplementary, '1.1'), supplementary)

    def test_pairing_uses_original_neighbors_and_canonicalizes_valid_pairs(self):
        cases = {
            '\ud83d\ude00': '😀', '\ud800\udc00': '\U00010000',
            '\udbff\udfff': '\U0010ffff', '\ud800A\udc00': 'A',
            '\ud800\ud800\udc00': '\U00010000',
            '\ud800\udc00\udc00': '\U00010000',
            '\udc00\ud800': '', '\ud800😀\udc00': '😀',
            '\ud800\ufffe\udc00': '', '\ud800\x01\udc00': '',
            '\ud800': '', '\udc00': '',
        }
        for version in ('1.0', '1.1'):
            for text, expected in cases.items():
                with self.subTest(version=version, text=repr(text)):
                    self.assertEqual(clean(text, version), expected)

    def test_literal_markup_whitespace_and_normalization_are_untouched(self):
        for text in ('', '<x>&amp;&#0;</x>', '<x a="one"> &unknown; </x>',
                     '<!DOCTYPE x SYSTEM "file:///never-read"><x>&entity;</x>',
                     '\t\n\r\r\n Я😀 e\u0301 \u00a0\u0085\u2028', 'a' * 100000):
            for version in ('1.0', '1.1'):
                with self.subTest(text=repr(text[:60]), version=version):
                    self.assertEqual(clean(text, version), text)
                    self.assertIs(type(clean(text, version)), str)
                    self.assertEqual(read(write(clean(text, version))), text)

    def test_exact_types_and_versions_without_host_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('string hook')
            def __eq__(self, other):
                raise AssertionError('equality hook')
            def __len__(self):
                raise AssertionError('length hook')
            def __iter__(self):
                raise AssertionError('iteration hook')

        class HostileString(str):
            def __eq__(self, other):
                raise AssertionError('string equality hook')
            def __len__(self):
                raise AssertionError('string length hook')
            def __iter__(self):
                raise AssertionError('string iteration hook')

        for value in (None, NULL, True, Decimal(123), 123, BSLType.STRING,
                      XML_STRING_PROCESSING, Hostile(), HostileString('text')):
            with self.subTest(kind=type(value)), self.assertRaises(TypeError):
                clean(value)
            with self.subTest(version_kind=type(value)), self.assertRaises(TypeError):
                clean('text', value)
        for version in ('', '2.0', '1', '1.00', ' 1.0', '1.1 ', '1.0\x00', '１.０'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                clean('text', version)

    def test_resource_budget_counts_utf16_before_result_allocation(self):
        with patch.object(xml_processing, '_MAX_TEXT_UNITS', 4):
            self.assertEqual(clean('abcd'), 'abcd')
            self.assertEqual(clean('😀😀'), '😀😀')
            self.assertEqual(clean('\ud83d\ude00\ud83d\ude00'), '😀😀')
            self.assertEqual(clean('\x00' * 4), '')
            for text in ('abcde', '😀😀a', '\x00' * 5, '\ud83d\ude00😀a'):
                with self.subTest(text=repr(text)), self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                    clean(text)
        self.assertEqual(clean('\x00valid'), 'valid')


class XMLStringProcessingManagerTests(unittest.TestCase):
    def test_only_explicit_methods_are_case_insensitive_and_read_only(self):
        for name in ('УдалитьНедопустимыеСимволыXML', 'DeleteDisallowedXMLCharacters',
                     'уДаЛиТьНеДоПуСтИмЫеСиМвОлЫxMl', 'dElEtEdIsAlLoWeDxMlChArAcTeRs'):
            method = XML_STRING_PROCESSING.get_member(name)
            self.assertIs(type(method), HostFunction)
            self.assertTrue(method.returns_value)
            self.assertEqual(method.reference_parameters, frozenset())
            self.assertEqual(method('A\x00B'), 'AB')
            with self.assertRaisesRegex(ValueError, 'недоступно для записи'):
                XML_STRING_PROCESSING.set_member(name, None)
            with self.assertRaises(FrozenInstanceError):
                setattr(XML_STRING_PROCESSING, name, None)
        for name in ('__dict__', '__class__', 'get_member', 'set_member', 'get_method',
                     'FindDisallowedXMLCharacters', 'НайтиНедопустимыеСимволыXML',
                     'delete_disallowed_xml_characters', 'Count', 'Version', 'items'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                XML_STRING_PROCESSING.get_member(name)

    def test_bilingual_global_method_and_type_aliases(self):
        vm = Interpreter()
        vm.variables['text'] = CONTROLS
        for global_name in ('ОбработкаСтрокиXML', 'XMLStringProcessing',
                            'оБрАбОтКаСтРоКиXmL', 'xMlStRiNgPrOcEsSiNg'):
            self.assertIs(vm.execute(global_name), XML_STRING_PROCESSING)
            for method in ('УдалитьНедопустимыеСимволыXML', 'DeleteDisallowedXMLCharacters'):
                self.assertEqual(vm.execute(f'{global_name}.{method}(text)'), clean(CONTROLS))
                self.assertEqual(vm.execute(f'{global_name}.{method}(text, "1.1")'), clean(CONTROLS, '1.1'))
            self.assertIs(vm.execute(f'TypeOf({global_name})'), BSLType.XML_STRING_PROCESSING_MANAGER)
        for name in ('МенеджерОбработкиСтрокиXML', 'XMLStringProcessingManager'):
            self.assertIs(type_by_name(name.swapcase()), BSLType.XML_STRING_PROCESSING_MANAGER)
        self.assertIs(type_of(XML_STRING_PROCESSING), BSLType.XML_STRING_PROCESSING_MANAGER)

    def test_no_implicit_globals_constructor_iteration_or_reflection(self):
        vm = Interpreter()
        vm.variables['manager'] = XML_STRING_PROCESSING
        for expression in ('DeleteDisallowedXMLCharacters("text")',
                           'УдалитьНедопустимыеСимволыXML("text")',
                           'New XMLStringProcessingManager', 'New МенеджерОбработкиСтрокиXML',
                           'New (TypeOf(manager))', 'manager()', 'manager[0]',
                           'manager.__class__', 'manager.__dict__', 'manager.get_member("x")',
                           'manager.FindDisallowedXMLCharacters("x")',
                           'manager.DeleteDisallowedXMLCharacters = 1;',
                           'For Each item In manager Do EndDo;'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute(expression)

    def test_arity_validation_and_failed_assignment_recovery(self):
        vm = Interpreter()
        prefix = 'XMLStringProcessing.DeleteDisallowedXMLCharacters'
        for arguments in ('()', '("x", "1.0", "extra")', '(, "1.0")',
                          '(Undefined)', '(Null)', '(123)',
                          '("x", Undefined)', '("x", Null)', '("x", 1)', '("x", "2.0")'):
            expression = prefix + arguments
            with self.subTest(arguments=arguments):
                vm.execute('saved = "before"; caught = False;')
                with self.assertRaises(BSLError):
                    vm.execute('saved = ' + expression)
                self.assertEqual(vm.execute('saved'), 'before')
                vm.execute(f'Try saved = {expression}; Except caught = True; EndTry;')
                self.assertTrue(vm.execute('caught'))
                self.assertEqual(vm.execute('saved'), 'before')
                self.assertEqual(vm.execute(prefix + '("after")'), 'after')
        # Trailing omissions are a parser limitation, so Try cannot catch one.
        with self.assertRaises(BSLError):
            vm.execute(prefix + '("x",)')

    def test_receiver_and_arguments_evaluate_once_left_to_right(self):
        vm = Interpreter()
        seen = []
        def record(label, value):
            def call():
                seen.append(label)
                return value
            return call
        vm.register_function('Manager', record('manager', XML_STRING_PROCESSING))
        vm.register_function('Text', record('text', CONTROLS))
        vm.register_function('Version', record('version', '1.1'))
        self.assertEqual(vm.execute('Manager().DeleteDisallowedXMLCharacters(Text(), Version())'),
                         clean(CONTROLS, '1.1'))
        self.assertEqual(seen, ['manager', 'text', 'version'])

    def test_native_manager_record_and_inverse(self):
        descriptor = BSLType.XML_STRING_PROCESSING_MANAGER
        record = '{"#",' + MANAGER_ID + '}'
        self.assertEqual(write(XML_STRING_PROCESSING), record)
        self.assertIsNone(read(record))
        self.assertEqual(write(descriptor), '{"T",' + MANAGER_ID + '}')
        self.assertIs(read(write(descriptor)), descriptor)
        for text in ('{"#",' + MANAGER_ID + ',0}', '{"#",' + MANAGER_ID + ',{0}}',
                     '{"#","' + MANAGER_ID + '"}', '{"T",' + MANAGER_ID + ',0}'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(text)

    def test_host_subclasses_cannot_impersonate_manager_type_or_codec(self):
        class HostManager(BSLXMLStringProcessingManager):
            def __str__(self):
                raise AssertionError('string hook')
        for function in (type_of, write):
            with self.assertRaises(TypeError):
                function(HostManager())

    def test_native_manager_and_cleanup_records_are_unchanged(self):
        output = []
        Interpreter(output.append).execute(
            (ROOT / 'integrational_tests/tests/values.bsl').read_text(encoding='utf-8-sig'))
        actual = {line.split(': [', 1)[0]: line for line in output
                  if line.startswith(('xml.manager.', 'xml.clean.'))}
        native = (ROOT / 'tests/fixtures/native_windows/values.out').read_text(encoding='utf-8-sig')
        expected = {match.group(1): match.group(0).rstrip()
                    for match in re.finditer(r'(?ms)^(xml\.(?:manager|clean)\.[^:]+): \[.*?(?=^xml\.|\Z)', native)}
        self.assertEqual(len(expected), 13)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()

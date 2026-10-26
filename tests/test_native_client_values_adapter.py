"""Offline full-values adapter contracts, not evidence of native 1C parity."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from yadinassi import BSLError, Interpreter
import test_native_1c_full_stage as fixtures

suite = fixtures.suite
ROOT = fixtures.REPOSITORY
NONCE = fixtures.NONCE
COUNT = 534
DECLARATIONS = (3, 19, 27, 35, 49, 64, 71, 80, 89, 96, 102, 115, 122, 143, 158, 163, 169, 174, 178, 199, 208, 215, 236, 253, 288, 295, 300, 305, 311, 319, 327, 337, 349, 358, 368, 376, 387, 403, 407, 426, 436, 446, 458, 470, 476, 505, 524, 536, 570, 602, 621)
SITES = (7, 12, 14, 53, 58, 60, 147, 152, 154, 240, 245, 247, 362, 364, 440, 442, 483, 490, 497, 500, 577, 593, 596, 625, 631, 634, 688, 767, 904, 932, 992, 1034, 1053, 1081)
CAPTURE = 'ЗначенияКлиентЗахват'
VARIABLES = ('ЗначенияКлиентСообщения', 'ЗначенияКлиентСимволы')


def interpreter_module(module: str) -> str:
    """Private offline shim for the two form-variable directives, not statements.

    Standalone supports client routines, but not client-decorated form variables.
    Strip exactly those two directives only in this test copy. Production keeps
    both, and the native compiler/round-trip/witness establishes actual context.
    """
    for name in VARIABLES:
        annotated = '&НаКлиенте\nПерем ' + name + ';\n'
        if module.count(annotated) != 1:
            raise AssertionError('missing or duplicated form-variable declaration')
        module = module.replace(annotated, 'Перем ' + name + ';\n', 1)
    return module


class ClientValuesAdapterTests(unittest.TestCase):
    def setUp(self):
        self.source_path = ROOT / 'integrational_tests/tests/values.bsl'
        self.template_path = ROOT / suite.CLIENT_SOURCE
        self.source = self.source_path.read_bytes()
        self.template = self.template_path.read_bytes()
        # Offline fixtures model the LF-pinned Linux executor under Git autocrlf.
        # Never normalize production input or edit repository source fixtures.
        if os.name == 'nt':
            self.source = self.source.replace(b'\r\n', b'\n')
            self.template = self.template.replace(b'\r\n', b'\n')
        self.template = suite.client_parity_template(self.template)

    def module(self):
        return suite.client_values_module(self.source, self.template).decode('utf-8-sig')

    def vm(self):
        vm = Interpreter(output=lambda _: self.fail('adapter leaked a native message'))
        vm.execute(interpreter_module(self.module()))
        return vm

    def test_source_template_and_message_count_are_pinned(self):
        self.assertEqual(suite.digest(self.source),
                         '16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5')
        self.assertEqual(suite.digest(self.template),
                         '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        self.assertEqual(suite.digest(self.source), suite.CLIENT_VALUES_SOURCE_SHA256)
        self.assertEqual(suite.digest(self.template), suite.CLIENT_VALUES_TEMPLATE_SHA256)
        self.assertEqual(suite.CLIENT_VALUES_MESSAGE_COUNT, COUNT)
        generated = suite.client_values_module(self.source, self.template)
        self.assertTrue(generated.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r', generated)

    def test_raw_source_tampering_is_rejected_without_normalization(self):
        lines = self.source.splitlines(keepends=True)
        swapped = lines.copy()
        swapped[437], swapped[438] = swapped[438], swapped[437]
        removed_helper = lines[:19] + lines[26:]
        mutants = [
            b''.join(lines[:437] + lines[438:]),
            b''.join(lines[:437] + [lines[437]] + lines[437:]),
            b''.join(swapped), b''.join(removed_helper),
            b''.join(lines[:19] + lines[19:26] + lines[19:]),
            self.source + b'\n', self.source[:-1],
            self.source.replace(b'NULL', b'Undefined', 1),
            self.source.replace(b'[error]', b'[ok]', 1),
            self.source.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + self.source,
            self.source.replace('Сообщить('.encode(), 'Message('.encode(), 1),
            self.source + '\n&НаСервере\nПроцедура Вызов()\nКонецПроцедуры\n'.encode(),
            self.source + '\nВызватьНаСервере();\n'.encode(),
        ]
        for source in mutants:
            with self.subTest(digest=suite.digest(source)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_values_module(source, self.template)

    def test_template_changes_and_substitution_are_rejected(self):
        marker = '&НаКлиенте\nФункция ВычислитьПробу()\n'.encode()
        mutants = [
            self.template + b'\n', self.template.replace(b'6 * 7', b'42'),
            self.template.replace('НаКлиенте'.encode(), 'НаСервере'.encode(), 1),
            self.template.replace(b'"client"', b'"server"', 1),
            self.template.replace(marker, b'', 1),
            self.template + marker + 'КонецФункции\n'.encode(),
            self.template.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + self.template,
            self.source,
        ]
        for template in mutants:
            with self.subTest(digest=suite.digest(template)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_values_module(self.source, template)
        with self.assertRaises(suite.FullError):
            suite.client_values_module(self.template, self.source)

    def test_structure_and_case_insensitive_collisions_fail_even_if_hash_is_rebased(self):
        # Future source rebasing must deliberately revisit these shape checks too.
        lines = self.source.splitlines(keepends=True)
        replacements = [(3, lines[3].replace('НаблюдатьNull'.encode(), b'ObserveNull')),
                        (16, 'КонецФункции\n'.encode()),
                        (7, lines[7].replace(b'[error]', b'[changed]')),
                        (639, lines[640]),
                        (0, '&НаКлиенте\n'.encode()),
                        (0, '&НаСервере\n'.encode()),
                        (0, '#Если Сервер Тогда\n'.encode())]
        replacements += [(0, ('// ' + name.swapcase() + '\n').encode())
                         for name in (CAPTURE, *VARIABLES, 'ЗначенияКлиентВыполнить')]
        for index, replacement in replacements:
            changed = lines.copy()
            changed[index] = replacement
            source = b''.join(changed)
            with self.subTest(index=index, replacement=replacement):
                with mock.patch.object(suite, 'CLIENT_VALUES_SOURCE_SHA256', suite.digest(source)):
                    with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                        suite.client_values_module(source, self.template)
        for replacement in ('// значенияклиентзахват\n',
                            '&НаКлиенте\nФункция ВычислитьПробу()\nКонецФункции\n'):
            template = self.template + replacement.encode()
            with mock.patch.object(suite, 'CLIENT_VALUES_TEMPLATE_SHA256', suite.digest(template)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_values_module(self.source, template)

    def test_reverse_generated_source_preserves_all_1225_lines_and_expressions(self):
        module = self.module()
        start = module.index('// Нативный checkpoint специальных значений: Null.')
        end = module.index('\nКонецПроцедуры\n\n&НаКлиенте\nФункция ВычислитьПробу()', start)
        restored = module[start:end]
        self.assertEqual(restored.count('&НаКлиенте\n'), len(DECLARATIONS) + 1)
        self.assertEqual(restored.count('Процедура ЗначенияКлиентВыполнить()\n'), 1)
        self.assertEqual(restored.count(CAPTURE + '('), len(SITES))
        restored = restored.replace('&НаКлиенте\n', '')
        restored = restored.replace('Процедура ЗначенияКлиентВыполнить()\n', '')
        restored = restored.replace(CAPTURE + '(', 'Сообщить(') + '\n'
        self.assertEqual(restored.encode(), self.source)
        self.assertEqual(len(restored.splitlines()), 1225)
        self.assertEqual(tuple(i for i, line in enumerate(restored.splitlines())
                               if re.match(r'^(Процедура|Функция) ', line)), DECLARATIONS)
        self.assertEqual(tuple(i for i, line in enumerate(restored.splitlines())
                               if re.match(r'^\s*Сообщить\(', line)), SITES)

    def test_all_declarations_and_calls_are_direct_client_only_without_new_conversion(self):
        module = self.module()
        declarations = re.findall(r'^([^\n]+)\n((?:Процедура|Функция|Перем) [^\n]+)', module, re.M)
        self.assertEqual(len(declarations), 59)
        self.assertTrue(all(directive == '&НаКлиенте' for directive, _ in declarations))
        self.assertNotIn('&НаСервере', module)
        self.assertNotIn('Сообщить(', module)
        for conversion in (r'(?<!\w)Строка\(', r'(?<!\w)String\('):
            self.assertEqual(re.findall(conversion, module),
                             re.findall(conversion, self.source.decode()))
        self.assertIn('ЗначенияКлиентСообщения.Добавить(Текст);', module)
        self.assertIn('ЗначенияКлиентСообщения.Количество() >= 534', module)
        self.assertIn(f'> {(suite.MAX_OUTPUT - COUNT) // 4}', module)
        self.assertIn('ЗначенияКлиентВыполнить();', module)
        self.assertIn('Возврат ЗначенияКлиентСообщения;', module)
        self.assertEqual(module.count('ВычислитьПробу();'), 1)
        self.assertEqual(module.count(CAPTURE + '('), len(SITES) + 1)

    def test_witness_writer_and_onopen_are_byte_unchanged(self):
        module = self.module()
        harness = self.template.decode()
        witness = harness[:harness.index('&НаКлиенте\nФункция ВычислитьПробу()')]
        suffix = harness[harness.index('&НаКлиенте\nПроцедура ЗаписатьПробу'):]
        self.assertIn(witness, module)
        self.assertTrue(module.endswith(suffix))
        self.assertNotIn('Значения.Добавить(6 * 7);', module)

    def test_complete_interpreter_capture_matches_unmodified_source_without_filtering(self):
        before = {path: path.read_bytes() for path in (self.source_path, self.template_path)}
        expected = []
        Interpreter(output=expected.append).execute(self.source.decode())
        captured = list(self.vm().execute('ВычислитьПробу()'))
        self.assertEqual(len(expected), COUNT)
        self.assertEqual(len(captured), COUNT)
        self.assertTrue(all(type(item) is str for item in captured))
        self.assertEqual(captured, expected)  # Every string, including protected error paths.
        self.assertEqual(suite.serialize_messages(captured), suite.serialize_messages(expected))
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_capture_repeated_execution_resets_without_reusing_previous_results(self):
        vm = self.vm()
        first = vm.execute('ВычислитьПробу()')
        expected = list(first)
        second = vm.execute('ВычислитьПробу()')
        self.assertIsNot(first, second)
        self.assertEqual(list(first), expected)
        self.assertEqual(list(second), expected)
        self.assertEqual(len(expected), COUNT)

    def test_capture_rejects_non_strings_before_conversion_or_mutation(self):
        vm = self.vm()
        vm.execute('ЗначенияКлиентСообщения = Новый Массив; ЗначенияКлиентСимволы = 0;')
        for value in ('1', 'Истина', 'Неопределено', 'Null', 'Новый Массив'):
            with self.subTest(value=value):
                with self.assertRaises(BSLError):
                    vm.execute(f'{CAPTURE}({value});')
                self.assertEqual(vm.execute('ЗначенияКлиентСообщения.Количество()'), 0)
                self.assertEqual(vm.execute('ЗначенияКлиентСимволы'), 0)
        vm.execute(f'{CAPTURE}(" Привет " + Символ(13) + Символ(10) + "конец ");')
        self.assertEqual(list(vm.execute('ЗначенияКлиентСообщения')), [' Привет \r\nконец '])

    def test_capture_message_and_character_limits_fail_before_mutation(self):
        vm = self.vm()
        vm.execute('ЗначенияКлиентСообщения = Новый Массив; ЗначенияКлиентСимволы = 0;')
        vm.execute(f'Для i = 1 По {COUNT} Цикл {CAPTURE}(""); КонецЦикла;')
        with self.assertRaises(BSLError):
            vm.execute(f'{CAPTURE}("");')
        self.assertEqual(vm.execute('ЗначенияКлиентСообщения.Количество()'), COUNT)
        budget = (suite.MAX_OUTPUT - COUNT) // 4
        vm.execute('ЗначенияКлиентСообщения = Новый Массив; '
                   f'ЗначенияКлиентСимволы = {budget - 1};')
        vm.execute(f'{CAPTURE}("я");')
        with self.assertRaises(BSLError):
            vm.execute(f'{CAPTURE}("я");')
        self.assertEqual(list(vm.execute('ЗначенияКлиентСообщения')), ['я'])
        self.assertEqual(vm.execute('ЗначенияКлиентСимволы'), budget)


class ClientValuesMarkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / 'marker.json'
        if os.name == 'nt':
            reader = mock.patch.object(suite, 'secure_bytes', fixtures.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def record(self, values=None, phase='completed'):
        return {'schema': 1, 'nonce': NONCE, 'phase': phase, 'witness': 'client',
                'values': [f'line {i}' for i in range(COUNT)] if values is None else values}

    def read(self, record, phase='completed'):
        self.path.write_text(json.dumps(record), encoding='utf-8')
        return suite.client_values_marker(self.path, NONCE, phase)

    def test_empty_report_matches_dates_shape_with_independent_mutable_diagnostics(self):
        first = suite.empty_values_report()
        self.assertEqual(first, suite.empty_dates_report())
        self.assertEqual(first['status'], 'not_started')
        self.assertIsNone(first['output_sha256'])
        self.assertIsNone(first['output_size'])
        self.assertIsNone(first['message_count'])
        self.assertIsNot(first['process_diagnostics'], suite.empty_values_report()['process_diagnostics'])

    def test_entered_empty_and_completed_exact_string_count(self):
        entered = self.record([], 'entered')
        self.assertEqual(self.read(entered, 'entered'), entered)
        completed = self.record()
        self.assertEqual(self.read(completed), completed)
        self.assertEqual(self.read(self.record([''] * COUNT))['values'], [''] * COUNT)

    def test_missing_extra_wrong_types_and_schema_fail_closed(self):
        edits = [lambda r: r['values'].pop(), lambda r: r['values'].append('extra'),
                 lambda r: r['values'].__setitem__(0, 1),
                 lambda r: r['values'].__setitem__(0, True),
                 lambda r: r['values'].__setitem__(0, None),
                 lambda r: r['values'].__setitem__(0, []),
                 lambda r: r['values'].__setitem__(0, {}),
                 lambda r: r.update(values=None), lambda r: r.update(values={}),
                 lambda r: r.update(schema=True), lambda r: r.update(schema=1.0),
                 lambda r: r.update(schema=2), lambda r: r.update(witness='server'),
                 lambda r: r.update(witness=True), lambda r: r.update(nonce='0' * 32),
                 lambda r: r.update(phase='error'), lambda r: r.update(extra=1)]
        edits += [lambda r, key=key: r.pop(key)
                  for key in ('schema', 'nonce', 'phase', 'witness', 'values')]
        for edit in edits:
            record = self.record()
            edit(record)
            with self.subTest(edit=edit):
                with self.assertRaisesRegex(suite.FullError, '^invalid_result$'):
                    self.read(record)
        for record, phase in ((self.record(['unexpected'], 'entered'), 'entered'),
                              (self.record([], 'completed'), 'completed'),
                              (self.record(), 'entered'),
                              (self.record([], 'entered'), 'completed')):
            with self.assertRaises(suite.FullError):
                self.read(record, phase)

    def test_reordered_multiline_and_trailing_space_values_are_preserved(self):
        original = self.record()
        changed = self.record()
        changed['values'].reverse()
        accepted = self.read(changed)
        self.assertEqual(accepted, changed)
        self.assertNotEqual(suite.serialize_messages(accepted['values']),
                            suite.serialize_messages(original['values']))
        changed['values'][:6] = ['first\r\nsecond', '', ' Привет\rworld ', '\\n\\r',
                                 'trailing  ', 'last\n']
        accepted = self.read(changed)
        self.assertEqual(accepted, changed)
        self.assertTrue(suite.serialize_messages(accepted['values']).startswith(
            'first\nsecond\n\n Привет\nworld \n\\n\\r\ntrailing  \nlast\n\n'.encode()))

    def test_trailing_bytes_duplicate_keys_invalid_unicode_nonfinite_and_depth_fail(self):
        data = json.dumps(self.record()).encode()
        bad = [data + b' garbage', data + b'{}', data[:-1], b'[]', b'null', b'\xff',
               data.replace(b'line 0', b'\\ud800'), data.replace(b'line 0', b'\\udfff'),
               data.replace(b'line 0', b'\xff'),
               data.replace(b'"line 0"', b'NaN'),
               data.replace(b'"line 0"', b'Infinity'), b'[' * 20 + b']' * 20]
        for key in ('schema', 'nonce', 'phase', 'witness', 'values'):
            value = self.record()[key]
            field = json.dumps(key).encode() + b': ' + json.dumps(value).encode()
            bad.append(data.replace(field, field + b', ' + field, 1))
        for raw in bad:
            with self.subTest(raw=raw[:60]):
                self.path.write_bytes(raw)
                with self.assertRaises(suite.FullError):
                    suite.client_values_marker(self.path, NONCE, 'completed')

    def test_byte_bound_includes_one_lf_per_message_and_multibyte_utf8(self):
        values = [''] * COUNT
        values[0] = 'a' * (suite.MAX_OUTPUT - COUNT)
        self.assertEqual(len(suite.serialize_messages(self.read(self.record(values))['values'])),
                         suite.MAX_OUTPUT)
        for first in (values[0] + 'a', 'я' * (suite.MAX_OUTPUT // 2),
                      '😀' * (suite.MAX_OUTPUT // 4),
                      '\r\n' * (suite.MAX_OUTPUT // 2 + 1)):
            with self.subTest(length=len(first)):
                with self.assertRaises(suite.FullError):
                    self.read(self.record([first] + [''] * (COUNT - 1)))

    def test_private_json_envelope_cap_is_independent_of_decoded_output_cap(self):
        record = self.record(['\x00' * (suite.MAX_RESULT // 6)] + [''] * (COUNT - 1))
        self.assertLess(len(suite.serialize_messages(record['values'])), suite.MAX_OUTPUT)
        with self.assertRaises(suite.FullError):
            self.read(record)

    def test_invalid_requested_nonce_phase_and_replayed_nonce_fail(self):
        self.read(self.record())
        for nonce, phase in ((NONCE, 'error'), ('../bad', 'completed'),
                             ('A' * 32, 'completed'), ('0' * 31, 'completed'),
                             (None, 'completed')):
            with self.subTest(nonce=nonce, phase=phase):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_values_marker(self.path, nonce, phase)
        with self.assertRaisesRegex(suite.FullError, '^invalid_result$'):
            suite.client_values_marker(self.path, 'f' * 32, 'completed')

    def test_missing_empty_directory_and_oversize_fail_closed(self):
        with self.assertRaises(suite.FullError):
            suite.client_values_marker(self.path, NONCE, 'completed')
        for raw in (b'', b' ' * (suite.MAX_RESULT + 1)):
            self.path.write_bytes(raw)
            with self.assertRaises(suite.FullError):
                suite.client_values_marker(self.path, NONCE, 'completed')
        with self.assertRaises(suite.FullError):
            suite.client_values_marker(self.path.parent, NONCE, 'completed')


if __name__ == '__main__':
    unittest.main()

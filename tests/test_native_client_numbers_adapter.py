"""Offline source/type contracts only; no claim of native conversion or UI evidence."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock
from yadinassi import Interpreter, BSLError
import test_native_1c_full_stage as fixtures

suite = fixtures.suite
ROOT = fixtures.REPOSITORY
NONCE = fixtures.NONCE
COUNT = 350
DECLARATIONS = (2, 11, 20, 29, 45, 54, 76, 102, 110, 118, 141, 149, 162, 177, 182, 199, 208, 225, 235)
SITES = (178, 304, 305, 306)
CAPTURE = 'ЧислаКлиентЗахват'
VARIABLES = ('ЧислаКлиентСообщения', 'ЧислаКлиентСимволы')

class ClientNumbersAdapterTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'integrational_tests/tests/numbers.bsl').read_bytes()
        self.template = (ROOT / suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt':
            self.source = self.source.replace(b'\r\n', b'\n')
            self.template = self.template.replace(b'\r\n', b'\n')

    def module(self):
        return suite.client_numbers_module(self.source, self.template).decode('utf-8-sig')

    def vm(self):
        module = self.module()
        for name in VARIABLES:
            module = module.replace('&НаКлиенте\nПерем ' + name, 'Перем ' + name)
        vm = Interpreter(output=lambda _: self.fail('unexpected native message'))
        vm.execute(module)
        return vm

    def test_source_template_count_and_raw_site_are_pinned(self):
        self.assertEqual(suite.digest(self.source), '72837cfab6a37506e22408c8b7e620fe8582e9c63214d09e85bb087b1c2a7d86')
        self.assertEqual(suite.digest(self.template), '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        self.assertEqual(suite.CLIENT_NUMBERS_MESSAGE_COUNT, COUNT)
        self.assertEqual(suite.CLIENT_NUMBERS_RAW_ORDINAL, 30)
        self.assertEqual(self.source.decode().splitlines()[306], 'Сообщить(1234.5);')
        self.assertEqual(self.module().count('ЧислаКлиентЧисло(1234.5);'), 1)

    def test_inverse_reconstruction_preserves_every_original_byte_and_scope(self):
        module = self.module()
        start = module.index('// Числовой checkpoint:')
        end = module.index('\nКонецПроцедуры\n\n&НаКлиенте\nФункция ВычислитьПробу()', start)
        restored = module[start:end]
        self.assertEqual(restored.count('&НаКлиенте\n'), len(DECLARATIONS) + 1)
        self.assertEqual(restored.count(CAPTURE + '('), 3)
        self.assertEqual(restored.count('ЧислаКлиентЧисло('), 1)
        restored = restored.replace('&НаКлиенте\n', '').replace('Процедура ЧислаКлиентВыполнить()\n', '')
        restored = restored.replace(CAPTURE + '(', 'Сообщить(').replace('ЧислаКлиентЧисло(', 'Сообщить(') + '\n'
        self.assertEqual(restored.encode(), self.source)
        self.assertEqual(len(restored.splitlines()), 659)
        self.assertEqual(tuple(i for i, line in enumerate(restored.splitlines()) if re.match(r'^(Процедура|Функция) ', line)), DECLARATIONS)
        self.assertEqual(tuple(i for i, line in enumerate(restored.splitlines()) if re.match(r'^\s*Сообщить\(', line)), SITES)

    def test_only_one_extra_native_conversion_no_server_trampoline(self):
        module = self.module()
        self.assertNotIn('&НаСервере', module)
        self.assertNotIn('Сообщить(', module)
        self.assertEqual(module.count('Строка('), self.source.decode().count('Строка(') + 1)
        self.assertIn('ЧислаКлиентЗахват(Строка(Значение));', module)
        self.assertIn('Значение <> 1234.5 Или ЧислаКлиентСообщения.Количество() <> 30', module)
        suffix = self.template.decode().split('&НаКлиенте\nПроцедура ЗаписатьПробу', 1)[1]
        self.assertTrue(module.endswith(suffix))

    def test_mutations_and_rebased_structural_drift_fail_closed(self):
        for source in (self.source + b'\n', self.source.replace(b'1234.5', b'1234.6'), self.source.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + self.source):
            with self.assertRaises(suite.FullError):
                suite.client_numbers_module(source, self.template)
        for index, text in ((306, 'Сообщить(1234.6);\n'), (178, '    Сообщить(Значение);\n'), (2, 'Процедура Other()\n'), (9, 'КонецФункции\n'), (251, 'Треть = 1;\n'), (0, '// числаклиентчисло\n'), (0, '&НаСервере\n')):
            lines = self.source.decode().splitlines(True)
            lines[index] = text
            changed = ''.join(lines).encode()
            with mock.patch.object(suite, 'CLIENT_NUMBERS_SOURCE_SHA256', suite.digest(changed)):
                with self.assertRaises(suite.FullError):
                    suite.client_numbers_module(changed, self.template)
        for template in (self.template + b'\n', self.template.replace(b'"client"', b'"server"'), self.source):
            with self.assertRaises(suite.FullError):
                suite.client_numbers_module(self.source, template)

    def test_complete_offline_capture_retains_all_cases_not_native_evidence(self):
        expected = []
        Interpreter(output=expected.append).execute(self.source.decode())
        vm = self.vm()
        actual = list(vm.execute('ВычислитьПробу()'))
        self.assertEqual(len(actual), COUNT)
        self.assertEqual(actual, expected)
        self.assertEqual(list(vm.execute('ВычислитьПробу()')), expected)

    def test_string_capture_rejects_every_non_string(self):
        vm = self.vm()
        vm.execute('ЧислаКлиентСообщения = Новый Массив; ЧислаКлиентСимволы = 0;')
        for value in ('1234.5', 'Истина', 'Неопределено', 'Null', 'Новый Массив'):
            with self.assertRaises(BSLError):
                vm.execute(CAPTURE + '(' + value + ');')
            self.assertEqual(vm.execute('ЧислаКлиентСообщения.Количество()'), 0)

    def test_numeric_capture_accepts_only_exact_type_value_and_ordinal(self):
        vm = self.vm()
        vm.execute('ЧислаКлиентСообщения = Новый Массив; ЧислаКлиентСимволы = 0;')
        with self.assertRaises(BSLError):
            vm.execute('ЧислаКлиентЧисло(1234.5);')
        vm.execute('Для Н = 1 По 30 Цикл ЧислаКлиентЗахват(""); КонецЦикла;')
        for value in ('1234.6', '1234', 'Истина', 'Неопределено', 'Null', '"1234.5"'):
            with self.assertRaises(BSLError):
                vm.execute('ЧислаКлиентЧисло(' + value + ');')
            self.assertEqual(vm.execute('ЧислаКлиентСообщения.Количество()'), 30)
        vm.execute('ЧислаКлиентЧисло(1234.5);')
        self.assertEqual(vm.execute('ЧислаКлиентСообщения.Количество()'), 31)
        with self.assertRaises(BSLError):
            vm.execute('ЧислаКлиентЧисло(1234.5);')


class ClientNumbersMarkerTests(unittest.TestCase):
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
        return suite.client_numbers_marker(self.path, NONCE, phase)

    def test_empty_report_has_false_conversion_and_independent_mutable_diagnostics(self):
        first = suite.empty_numbers_report()
        self.assertEqual(first, dict(suite.empty_dates_report(), conversion_verified=False))
        self.assertIs(first['conversion_verified'], False)
        self.assertEqual(first['status'], 'not_started')
        self.assertIsNone(first['output_sha256'])
        self.assertIsNone(first['output_size'])
        self.assertIsNone(first['message_count'])
        self.assertIsNot(first['process_diagnostics'], suite.empty_numbers_report()['process_diagnostics'])

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
                    suite.client_numbers_marker(self.path, NONCE, 'completed')

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
                    suite.client_numbers_marker(self.path, nonce, phase)
        with self.assertRaisesRegex(suite.FullError, '^invalid_result$'):
            suite.client_numbers_marker(self.path, 'f' * 32, 'completed')

    def test_missing_empty_directory_and_oversize_fail_closed(self):
        with self.assertRaises(suite.FullError):
            suite.client_numbers_marker(self.path, NONCE, 'completed')
        for raw in (b'', b' ' * (suite.MAX_RESULT + 1)):
            self.path.write_bytes(raw)
            with self.assertRaises(suite.FullError):
                suite.client_numbers_marker(self.path, NONCE, 'completed')
        with self.assertRaises(suite.FullError):
            suite.client_numbers_marker(self.path.parent, NONCE, 'completed')


if __name__ == '__main__':
    unittest.main()

"""Offline dates adapter contracts. Synthetic markers are not native evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import test_native_1c_full_stage as fixtures

suite = fixtures.suite
ROOT = fixtures.REPOSITORY
NONCE = fixtures.NONCE


class ClientDatesAdapterTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'integrational_tests/tests/dates.bsl').read_bytes()
        self.template = (ROOT / suite.CLIENT_SOURCE).read_bytes()
        # Offline fixtures model the LF-pinned Linux executor, even under Windows
        # Git autocrlf. Production rejects raw source changes without normalization.
        if os.name == 'nt':
            self.source = self.source.replace(b'\r\n', b'\n')
            self.template = self.template.replace(b'\r\n', b'\n')
        self.template = suite.client_parity_template(self.template)

    def test_pins_source_and_template_and_rejects_every_tamper(self):
        self.assertEqual(suite.digest(self.source), suite.CLIENT_DATES_SOURCE_SHA256)
        self.assertEqual(suite.digest(self.template), suite.CLIENT_DATES_TEMPLATE_SHA256)
        lines = self.source.splitlines(keepends=True)
        reordered = lines.copy()
        reordered[30], reordered[31] = reordered[31], reordered[30]
        for source, template in (
            (b''.join(lines[:30] + lines[31:]), self.template),
            (b''.join(lines[:30] + [lines[30]] + lines[30:]), self.template),
            (b''.join(reordered), self.template),
            (self.source + b'\n', self.template),
            (self.source.replace(b'2024', b'2025', 1), self.template),
            (self.source.replace(b'\n', b'\r\n'), self.template),
            (b'\xef\xbb\xbf' + self.source, self.template),
            (self.source, self.template + b'\n'),
            (self.source, self.template.replace('НаКлиенте'.encode(), 'НаСервере'.encode(), 1)),
        ):
            with self.subTest(source=suite.digest(source), template=suite.digest(template)):
                with self.assertRaises(suite.FullError):
                    suite.client_dates_module(source, template)

    def test_reverse_generated_source_preserves_all_219_lines(self):
        module = suite.client_dates_module(self.source, self.template).decode('utf-8-sig')
        start = module.index('// Нативный checkpoint')
        end = module.index('\nКонецПроцедуры\n\n&НаКлиенте\nФункция ВычислитьПробу()', start)
        restored = module[start:end]
        restored = restored.replace('&НаКлиенте\n', '')
        restored = restored.replace('Процедура ДатыКлиентВыполнить()\n', '')
        restored = restored.replace('ДатыКлиентЗахват(', 'Сообщить(') + '\n'
        self.assertEqual(restored, self.source.decode())
        self.assertEqual(len(restored.splitlines()), 219)
        self.assertEqual(restored.count('Сообщить('), 6)
        self.assertEqual(restored.count('\nНаблюдатьДату('), 182)

    def test_all_declarations_and_calls_are_direct_client_only(self):
        module = suite.client_dates_module(self.source, self.template).decode('utf-8-sig')
        declarations = re.findall(r'^([^\n]+)\n((?:Процедура|Функция|Перем) [^\n]+)', module, re.M)
        self.assertEqual(len(declarations), 10)
        self.assertTrue(all(directive == '&НаКлиенте' for directive, _ in declarations))
        self.assertNotIn('&НаСервере', module)
        self.assertNotIn('Сообщить(', module)
        self.assertNotIn('Строка(Текст)', module)
        self.assertIn('ДатыКлиентСообщения.Добавить(Текст);', module)
        self.assertIn('ДатыКлиентСообщения.Количество() >= 185', module)
        self.assertIn(f'> {(suite.MAX_OUTPUT - 185) // 4}', module)
        self.assertIn('ДатыКлиентВыполнить();', module)
        self.assertIn('Возврат ДатыКлиентСообщения;', module)
        self.assertEqual(module.count('ВычислитьПробу();'), 1)
        self.assertEqual(module.count('ДатыКлиентЗахват('), 7)

    def test_witness_writer_and_onopen_are_unchanged(self):
        module = suite.client_dates_module(self.source, self.template).decode('utf-8-sig')
        harness = self.template.decode()
        witness = harness[:harness.index('&НаКлиенте\nФункция ВычислитьПробу()')]
        suffix = harness[harness.index('&НаКлиенте\nПроцедура ЗаписатьПробу'):]
        self.assertIn(witness, module)
        self.assertTrue(module.endswith(suffix))
        self.assertNotIn('6 * 7', module)


class ClientDatesMarkerTests(unittest.TestCase):
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
                'values': [f'line {i}' for i in range(185)] if values is None else values}

    def read(self, record, phase='completed'):
        self.path.write_text(json.dumps(record), encoding='utf-8')
        return suite.client_dates_marker(self.path, NONCE, phase)

    def test_entered_empty_and_completed_exact_string_count(self):
        entered = self.record([], 'entered')
        self.assertEqual(self.read(entered, 'entered'), entered)
        completed = self.record()
        self.assertEqual(self.read(completed), completed)

    def test_missing_extra_wrong_types_and_schema_fail_closed(self):
        edits = [lambda r: r['values'].pop(), lambda r: r['values'].append('extra'),
                 lambda r: r['values'].__setitem__(0, 1),
                 lambda r: r['values'].__setitem__(0, True),
                 lambda r: r.update(values=None), lambda r: r.update(schema=True),
                 lambda r: r.update(witness='server'), lambda r: r.update(nonce='0' * 32),
                 lambda r: r.update(phase='error'), lambda r: r.update(extra=1),
                 lambda r: r.pop('values')]
        for edit in edits:
            record = self.record()
            edit(record)
            with self.subTest(record=record):
                with self.assertRaises(suite.FullError):
                    self.read(record)
        with self.assertRaises(suite.FullError):
            self.read(self.record(['unexpected'], 'entered'), 'entered')

    def test_reordered_and_multiline_values_preserved_for_byte_comparison(self):
        original = self.record()
        changed = self.record()
        changed['values'][0], changed['values'][1] = changed['values'][1], changed['values'][0]
        accepted = self.read(changed)
        self.assertNotEqual(suite.serialize_messages(accepted['values']),
                            suite.serialize_messages(original['values']))
        changed['values'][:4] = ['first\r\nsecond', '', ' Привет\rworld ', '\\n\\r']
        accepted = self.read(changed)
        self.assertEqual(accepted, changed)
        self.assertTrue(suite.serialize_messages(accepted['values']).startswith(
            'first\nsecond\n\n Привет\nworld \n\\n\\r\n'.encode()))

    def test_trailing_bytes_duplicate_keys_invalid_unicode_fail(self):
        data = json.dumps(self.record()).encode()
        for raw in (data + b' garbage', data + b'{}',
                    data.replace(b'"schema": 1', b'"schema": 1, "schema": 1'),
                    data.replace(b'line 0', b'\\ud800')):
            self.path.write_bytes(raw)
            with self.assertRaises(suite.FullError):
                suite.client_dates_marker(self.path, NONCE, 'completed')

    def test_byte_bound_includes_newline_per_message_and_utf8(self):
        values = [''] * 185
        values[0] = 'a' * (suite.MAX_OUTPUT - 185)
        self.assertEqual(len(suite.serialize_messages(self.read(self.record(values))['values'])),
                         suite.MAX_OUTPUT)
        for first in (values[0] + 'a', 'я' * (suite.MAX_OUTPUT // 2),
                      '\r\n' * (suite.MAX_OUTPUT // 2 + 1)):
            with self.assertRaises(suite.FullError):
                self.read(self.record([first] + [''] * 184))

    def test_existing_private_json_envelope_cap_is_unchanged(self):
        # Decoded payload fits MAX_OUTPUT, but escaping exceeds MAX_RESULT.
        record = self.record(["\x00" * (suite.MAX_RESULT // 6)] + [""] * 184)
        self.assertLess(len(suite.serialize_messages(record["values"])), suite.MAX_OUTPUT)
        with self.assertRaises(suite.FullError):
            self.read(record)

    def test_invalid_requested_nonce_or_phase(self):
        self.read(self.record())
        for nonce, phase in ((NONCE, 'error'), ('../bad', 'completed')):
            with self.assertRaises(suite.FullError):
                suite.client_dates_marker(self.path, nonce, phase)


if __name__ == '__main__':
    unittest.main()

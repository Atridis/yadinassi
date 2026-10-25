"""Independent source/transport contracts, not native UUID behavior evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest import mock

import test_native_1c_full_stage as fixtures
from scripts.native_historical_replay import without_uuid_probes
from yadinassi import Interpreter
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SHA = '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c'
OLD_SHA = 'dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12'
START = '// Begin bounded UUID observations (candidate; not native evidence).\n'
HELPERS = '// Begin bounded UUID helpers (candidate; not native evidence).\n'

def checkout(raw, platform):
    return raw.replace(b'\r\n', b'\n') if platform == 'nt' else raw

class UUIDMeasurementContract(unittest.TestCase):
    def setUp(self):
        self.source = checkout((ROOT/'integrational_tests/tests/values.bsl').read_bytes(), os.name)
        self.template = checkout((ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes(), os.name)
        self.text = self.source.decode()
        self.block = self.text.split(START)[1]
        self.calls = re.findall(r'^НаблюдатьUUID\("([^"]+)", "(.*)"\);$', self.block, re.M)
        self.codes = {label: code.replace('""', '"') for label, code in self.calls}

    def test_exact_source_budget_and_historical_inverse(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), SHA)
        previous = without_uuid_probes(self.text)
        self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(), OLD_SHA)
        from test_native_uuid_codec_measurement import without_codec_blocks
        self.assertLess(len(without_codec_blocks(self.text).encode()) - len(previous.encode()), 12000)
        self.assertEqual(len(self.calls), 30)
        self.assertEqual(len(self.codes), 30)
        self.assertEqual(fixtures.suite.CLIENT_VALUES_MESSAGE_COUNT, 441)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 866)
        self.assertEqual(self.text.count(HELPERS), 1)
        self.assertEqual(self.text.count(START), 1)

    def test_each_fixed_dynamic_statement_parses_without_static_uuid_names(self):
        parse(self.text)
        for label, code in self.codes.items():
            with self.subTest(label=label):
                parse(code)
                self.assertIn('Результат = ', code)
        helpers = self.text.split(HELPERS)[1].split('// End bounded UUID helpers.')[0]
        self.assertNotIn('Новый УникальныйИдентификатор', helpers)
        self.assertNotIn('Новый UUID', helpers)
        self.assertNotIn('Новый UniqueIdentifier', helpers)
        self.assertEqual(helpers.count('Выполнить(Код);'), 1)
        self.assertEqual(helpers.count('Исключение'), 1)
        self.assertEqual(helpers.count('Сообщить('), 2)

    def test_aliases_type_and_constructors_are_independent(self):
        for name in ('УникальныйИдентификатор', 'UUID', 'UniqueIdentifier'):
            self.assertEqual(self.codes['type.' + name], f'Результат = Строка(Тип("{name}"));')
            self.assertIn(f'Новый {name}("01234567-89ab-4cde-8f01-23456789abcd")',
                          self.codes['constructor.' + name])

    def test_no_random_identifier_can_be_direct_result_or_raw_output(self):
        random = {k: v for k, v in self.codes.items() if k.startswith('default.')}
        self.assertEqual(set(random), {'default.' + k for k in
                                      ('format', 'nonzero', 'roundtrip', 'distinct', 'version')})
        for code in random.values():
            self.assertTrue(code.startswith('Значение = Новый УникальныйИдентификатор(); '))
            self.assertNotIn('Результат = Строка(Значение)', code)
            self.assertNotIn('Результат = Значение;', code)
        self.assertTrue(random['default.version'].endswith(
            'Результат = Сред(НРег(Строка(Значение)), 15, 1);'))
        self.assertNotIn('= "4"', random['default.version'])
        for label, code in self.codes.items():
            self.assertNotIn('Сообщить', code)
            self.assertNotIn('ЗначениеВСтрокуВнутр', code)
            if label.startswith('description.'):
                self.assertNotIn('+ Строка(Значение);', code)

    def test_format_projection_is_bounded_and_detects_bad_hex(self):
        vm = Interpreter(lambda _: None)
        vm.execute(self.text[:self.text.index('// Значение, тип и настоящий прямой/обратный кодек.')])
        for guid, expected in [('01234567-89ab-4cde-8f01-23456789abcd', True),
                               ('01234567-89AB-4CDE-8F01-23456789ABCD', True),
                               ('01234567-89ab-4cde-8f01-23456789abcg', False),
                               ('01234567889ab-4cde-8f01-23456789abcd', False), ('', False)]:
            self.assertIs(vm.execute(f'ФорматUUID("{guid}")'), expected)

    def test_surprising_input_success_is_projected_and_canonical_text_is_guarded(self):
        for label, code in self.codes.items():
            if label.startswith('input.'):
                self.assertIn('Результат = ПроекцияВходаUUID(Значение);', code)
                self.assertNotIn('Результат = Строка(Значение)', code)
            if label.startswith('canonical.'):
                self.assertIn('Если НРег(Текст) = "01234567-89ab-4cde-8f01-23456789abcd" Тогда', code)
                self.assertIn('Иначе Результат = "unexpected-format-or-value";', code)
        vm = Interpreter(lambda _: None)
        vm.execute(self.text[:self.text.index('// Значение, тип и настоящий прямой/обратный кодек.')])
        for guid, nibble in [('00000000-0000-0000-0000-000000000000', '0'),
                             ('01234567-89ab-4cde-8f01-23456789abcd', '4'),
                             ('01234567-89ab-1cde-8f01-23456789abce', '1')]:
            result = vm.execute(f'ПроекцияВходаUUID("{guid}")')
            self.assertNotIn(guid, result)
            self.assertEqual(len(result.split('/')), 5)
            self.assertTrue(result.endswith('/' + nibble))

    def test_one_dynamic_failure_does_not_hide_next_record(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute(self.text[:self.text.index('// Значение, тип и настоящий прямой/обратный кодек.')])
        vm.execute('НаблюдатьUUID("bad", "Результат = Новый DefinitelyMissing();"); '
                   'НаблюдатьUUID("next", "Результат = 17;");')
        self.assertEqual(output, ['uuid.bad: [error]', 'uuid.next: [17]'])

    def test_complete_adapter_keeps_every_statement_byte_identical(self):
        module = fixtures.suite.client_values_module(self.source, self.template)
        self.assertIn((START + self.block).encode(), module)
        for _, encoded in self.calls:
            self.assertIn(encoded.encode(), module)

    def test_production_and_inverse_reject_crlf_bom_tamper_and_old_source(self):
        for raw in (self.source.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf'+self.source,
                    self.source+b'\n', without_uuid_probes(self.text).encode()):
            with self.subTest(sha=hashlib.sha256(raw).hexdigest()):
                with self.assertRaises(fixtures.suite.FullError):
                    fixtures.suite.client_values_module(raw, self.template)
                with self.assertRaises(ValueError):
                    without_uuid_probes(raw.decode())

    def test_simulated_windows_fixture_only_normalization(self):
        crlf = self.source.replace(b'\n', b'\r\n')
        self.assertEqual(checkout(crlf, 'nt'), self.source)
        self.assertEqual(checkout(crlf, 'posix'), crlf)
        self.assertEqual(without_uuid_probes(checkout(crlf, 'nt').decode()),
                         without_uuid_probes(self.text))

    def test_harness_inverse_exact_hash_fails_closed(self):
        from test_native_async_fixture import without_value_tree_measurement
        for host, path in ((False, 'scripts/native_1c_bootstrap/full_suite.py'),
                           (True, 'scripts/native_1c_full_host.py')):
            source = (ROOT/path).read_text()
            without_value_tree_measurement(source, host=host)
            with self.assertRaises(AssertionError):
                without_value_tree_measurement(source+'\n', host=host)


class UUIDHistoricalAdapterBoundary(unittest.TestCase):
    def test_exact_402_adapter_output_and_live_441_rejection_remain_separate(self):
        from test_native_async_fixture import historical_uuid_values_module
        source = checkout((ROOT/'integrational_tests/tests/values.bsl').read_bytes(), os.name)
        template = checkout((ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes(), os.name)
        module = historical_uuid_values_module(source, template)
        self.assertEqual(hashlib.sha256(module).hexdigest(),
                         '814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824')
        self.assertEqual(fixtures.suite.CLIENT_VALUES_MESSAGE_COUNT, 441)
        with self.assertRaises(fixtures.suite.FullError):
            fixtures.suite.client_values_module(without_uuid_probes(source.decode()).encode(), template)
        for changed in (source+b'\n', source.replace(b'uuid-fixed-input', b'uuid-fixed-other', 1)):
            with self.assertRaises(ValueError):
                historical_uuid_values_module(changed, template)

"""Source-only exception probes: package safety, never predicted native answers."""
import hashlib
from pathlib import Path
import re
import unittest

from scripts.native_historical_replay import (
    without_uuid_probes, without_fill_exclude_probes, EXTENDED_EXCEPTION_PROBE_BLOCKS, HISTORICAL_FUNCTIONS_BLOB,
    HISTORICAL_FUNCTIONS_OUTPUT_BLOB, git_blob, historical_functions_source,
    without_extended_exception_probes, without_exception_context_probes,
)
from yadinassi import Interpreter, ast
from yadinassi.native_targets import WINDOWS_8_3_27_2342, LINUX_8_3_27_1508
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    'statement-en', 'statement-ru', 'functional-one-en', 'functional-one-ru',
    'functional-five-en', 'functional-five-ru', 'category-only', 'code-only',
    'additional-only', 'cause-only', 'omitted-all', 'undefined-all', 'empty-fields',
    'rethrow-en', 'rethrow-ru', 'routine-en', 'routine-ru',
    'nested-cause-en', 'nested-cause-ru', 'nested-configuration-cause', 'forbidden-category',
)
UNCHANGED_SCENARIOS = {
    'collections': ('e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232', 841),
    'values': ('dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12', 402),
    'numbers': ('65075fff9adc854a317c74821052a9f9afa2b064d5fbb55b21dbab1ecb87556d', 421),
    'dates': ('392761c5ce8f599d569400672b07590184f147c9e4d5cd3f07decee1cffb029e', 185),
}


class ExtendedExceptionCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = without_exception_context_probes(
            (ROOT / 'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8'))
        cls.original = without_extended_exception_probes(cls.source)
        cls.native = (ROOT / 'tests/fixtures/native_windows/functions.out').read_bytes()

    def test_exact_complete_88_record_source_and_output_binding(self):
        self.assertEqual(git_blob(self.original.encode()), HISTORICAL_FUNCTIONS_BLOB)
        self.assertEqual(git_blob(self.native.replace(b'\r\n', b'\n')), HISTORICAL_FUNCTIONS_OUTPUT_BLOB)
        for ending in ('\n', '\r\n'):
            with self.subTest(ending=ending):
                source = self.source.replace('\n', ending).encode()
                output = self.native.replace(b'\r\n', b'\n').replace(b'\n', ending.encode())
                self.assertEqual(historical_functions_source(source, output), self.original.encode())

    def test_projection_rejects_changed_old_source_output_or_boundaries(self):
        for mutant in (self.source + '\n', '\ufeff' + self.source,
                       self.source.replace('Перем МодульноеВычисления;', 'Перем Изменено;', 1),
                       self.source.replace(EXTENDED_EXCEPTION_PROBE_BLOCKS[0][1], '// missing\n', 1),
                       self.source + EXTENDED_EXCEPTION_PROBE_BLOCKS[1][0]):
            with self.subTest(mutant=mutant[-70:]), self.assertRaises(ValueError):
                without_extended_exception_probes(mutant)
        native = self.native.replace(b'\r\n', b'\n')
        for ending in (b'\n', b'\r\n'):
            output = native.replace(b'\n', ending)
            for mutant in (output + ending, output.replace(b'5' + ending, b'6' + ending, 1)):
                with self.subTest(ending=ending, mutant=mutant[-70:]):
                    self.assertNotEqual(mutant, output)
                    with self.assertRaises(ValueError):
                        historical_functions_source(self.source.encode(), mutant)

    def test_declarations_precede_original_body_and_cases_are_bounded(self):
        started = False
        for node in parse(self.source):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True
        calls = re.findall(r'^ПроверитьРасширеннуюОшибку\("([^"]+)"', self.source, re.M)
        self.assertEqual(tuple(calls), CASES)
        self.assertEqual(len(set(calls)), len(CASES))
        helper = self.source.split(EXTENDED_EXCEPTION_PROBE_BLOCKS[0][0])[1].split(
            EXTENDED_EXCEPTION_PROBE_BLOCKS[0][1])[0]
        self.assertNotRegex(helper, r'\b(?:Пока|Для|Перейти|While|For|Goto)\b')
        for text in ('ErrorInfo()', 'ИнформацияОбОшибке()', 'ErrorCategory.ConfigurationError',
                     'КатегорияОшибки.ОшибкаКонфигурации', 'Инфо.Description', 'Инфо.Code',
                     'Инфо.AdditionalInformation', 'Инфо.Cause', 'Инфо.IsErrorOfCategory',
                     'Инфо.ЯвляетсяОшибкойКатегории',
                     'КатегорияОшибки.ОшибкаВоВремяВыполненияВстроенногоЯзыка'):
            self.assertIn(text, helper)
        for field in ('ModuleName', 'LineNumber', 'InitialString', 'ИмяМодуля', 'НомерСтроки', 'ИсходнаяСтрока'):
            self.assertNotIn(field, helper)
        self.assertIn('ТекстОшибки = ОписаниеОшибки(); Инфо = ', helper)
        self.assertIn('Выполнить(КодОбработчика);', helper)

    def test_complete_old_prefix_and_checkpoint_run_on_both_targets(self):
        expected_prefix = self.native.decode('utf-8').replace('\r\n', '\n').splitlines()
        self.assertEqual(len(expected_prefix), 88)
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                old, current = [], []
                Interpreter(old.append, native_target=target).execute(self.original)
                Interpreter(current.append, native_target=target).execute(self.source)
                self.assertEqual(old, expected_prefix)
                self.assertEqual(current[:88], old)
                self.assertEqual(len(current), 111)
                self.assertEqual([line.split(':', 1)[0] for line in current[88:-2]],
                                 ['exception.' + label for label in CASES])
                for line in current[88:-2]:
                    self.assertRegex(line, r'^exception\.[^:]+: \[(raised|info-error|execute-error|not-raised);')
                    for field in ('type', 'description', 'code', 'additional', 'cause-undefined',
                                  'cause-description', 'cause-code', 'cause-configuration', 'all', 'runtime', 'compile',
                                  'raised', 'configuration', 'other', 'aliases', 'runtime-alias',
                                  'category-alias', 'error-description-token'):
                        self.assertIn(';' + field + '=', line)
                self.assertTrue(current[-2].startswith('exception.handler-state: [before='))
                self.assertEqual(current[-1], 'exception.checkpoint.complete: [ok]')

    def test_other_four_scenario_sources_and_counts_are_unchanged(self):
        # Existing dedicated suites verify their complete outputs. Exact source pins
        # prevent this checkpoint from changing any of their 1849 records.
        self.assertEqual(sum(count for _, count in UNCHANGED_SCENARIOS.values()), 1849)
        for name, (expected, _) in UNCHANGED_SCENARIOS.items():
            raw = (ROOT / f'integrational_tests/tests/{name}.bsl').read_bytes()
            if name == 'values':
                raw = without_uuid_probes(raw.replace(b'\r\n', b'\n').decode('utf-8')).encode('utf-8')
            if name == 'collections':
                raw = without_fill_exclude_probes(raw.replace(b'\r\n', b'\n').decode('utf-8-sig')).encode('utf-8-sig')
            self.assertEqual(hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest(), expected)

    def test_native_manifest_and_all_six_outputs_are_unchanged(self):
        from test_native_1c_full_stage import suite
        self.assertEqual(len(suite.INPUT_FILES) + 1, 24)
        self.assertEqual(suite.CLIENT_SOURCE, 'scripts/native_1c_bootstrap/client_probe.bsl')
        self.assertEqual(suite.SCENARIOS, ('collections', 'dates', 'functions', 'numbers', 'strings', 'values'))
        self.assertEqual(suite.INPUT_FILES['integrational_tests/tests/functions.bsl'], 'scenarios/functions.bsl')
        # The native module is the entire current source, not historical projection.
        module = suite.generated_module(self.source.encode())
        self.assertEqual(module.decode('utf-8-sig'), self.source)
        self.assertIn(b'exception.checkpoint.complete', module)


if __name__ == '__main__':
    unittest.main()

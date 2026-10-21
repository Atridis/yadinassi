"""Safety/packaging of owner-confirmed probes, never an interpreter-generated oracle."""
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    'numbers': ('numeric.control.complete: [ok]', 'numeric-bits', 30),
    'collections': ('fill.checkpoint.complete: [ok]', 'array-delete', 3),
}


def normalize(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


class NumericBitsCheckpointTests(unittest.TestCase):
    def source(self, name):
        return (ROOT / 'integrational_tests/tests' / (name + '.bsl')).read_text(encoding='utf-8-sig')

    def output_parts(self, name):
        output = []
        Interpreter(output=output.append).execute(self.source(name))
        lines = normalize('\n'.join(output) + '\n').splitlines()
        boundary = lines.index(SCENARIOS[name][0]) + 1
        # This historical checkpoint ends at its own sentinel. Later independent
        # checkpoints must not change its exact count or per-line assertions.
        end = lines.index(SCENARIOS[name][1] + '.checkpoint.complete: [ok]', boundary) + 1
        return lines[:boundary], lines[boundary:end]

    def test_declarations_precede_executable_body(self):
        for name in SCENARIOS:
            started = False
            for node in parse(self.source(name)):
                if isinstance(node, ast.Routine):
                    self.assertFalse(started, (name, node.name))
                elif not isinstance(node, ast.Var):
                    started = True

    def test_exact_case_counts_and_unique_labels(self):
        patterns = {
            'ПроверитьДвоичноеЧисло': 11,
            'ПроверитьШестнадцатеричноеЧисло': 10,
            'ПроверитьСдвигВлево': 6,
            'ПроверитьПобитовыйКонтроль': 3,
            'ПроверитьУдалениеЗаГраницей': 3,
        }
        text = self.source('numbers') + self.source('collections')
        for helper, count in patterns.items():
            labels = re.findall(r'^' + helper + r'\("([^"]+)"', text, re.MULTILINE)
            self.assertEqual(len(labels), count, helper)
            self.assertEqual(len(set(labels)), count, helper)

    def test_new_helpers_are_bounded_and_use_portable_error_markers(self):
        text = self.source('numbers').split('// Скалярные записи', 1)[0]
        text += self.source('collections').split('// Три независимых контроля', 1)[1].split(
            '// ЗаполнитьЗначенияСвойств:', 1)[0]
        self.assertNotRegex(text, r'\b(?:Пока|Для|Перейти|While|For|Goto|Выполнить|Execute|Вычислить|Eval|ОписаниеОшибки)\b')
        source = self.source('numbers')
        binary = re.findall(r'^ПроверитьДвоичноеЧисло\("[^"]+", "([^"]*)"\);$', source, re.MULTILINE)
        hexa = re.findall(r'^ПроверитьШестнадцатеричноеЧисло\("[^"]+", "([^"]*)"\);$', source, re.MULTILINE)
        self.assertEqual(max(map(len, binary)), 130)
        self.assertEqual(max(map(len, hexa)), 34)
        self.assertIn('0b' + '1' * 128, binary)
        self.assertIn('0x' + 'F' * 32, hexa)
        shifts = re.findall(r'^ПроверитьСдвигВлево\("[^"]+", (\d+), (\d+)\);$', source, re.MULTILINE)
        self.assertEqual(len(shifts), 6)
        for value, shift in shifts:
            self.assertLessEqual(int(value), 2**32 - 1)
            self.assertLessEqual(int(shift), 31)

    def test_existing_native_prefixes_are_unchanged(self):
        for name, (marker, _, _) in SCENARIOS.items():
            native = normalize((ROOT / 'tests/fixtures/native_windows' / (name + '.out')).read_text(
                encoding='utf-8-sig')).splitlines()
            native_prefix = native[:native.index(marker) + 1]
            actual_prefix, _ = self.output_parts(name)
            self.assertEqual(actual_prefix, native_prefix, name)

    def test_all_cases_reach_final_sentinels_without_raw_diagnostics(self):
        for name, (_, prefix, count) in SCENARIOS.items():
            _, added = self.output_parts(name)
            self.assertEqual(len(added), count + 1, name)
            self.assertEqual(added[-1], prefix + '.checkpoint.complete: [ok]')
            labels = [line.split(': ', 1)[0] for line in added[:-1]]
            self.assertEqual(len(set(labels)), count)
            for line in added[:-1]:
                self.assertTrue(line.startswith(prefix + '.'))
                self.assertRegex(line, r': \[(?:error(?:;[^\n]+)?|\{"N",[^\n]+\}|ok;[^\n]+)\]$')

    def test_local_controls_preserve_numeric_payloads_and_array_state(self):
        # These are local regressions for already implemented operations, not new goldens.
        _, numeric = self.output_parts('numbers')
        self.assertIn('numeric-bits.control.and-not: [{"N",2147483647}]', numeric)
        self.assertIn('numeric-bits.control.not-zero: [{"N",4294967295}]', numeric)
        self.assertIn('numeric-bits.control.right-shift: [{"N",1}]', numeric)
        _, arrays = self.output_parts('collections')
        self.assertEqual(arrays[0], 'array-delete.control.empty: [error;{"N",0};{"N",-1}]')
        self.assertTrue(arrays[1].startswith('array-delete.control.above-bound: [error;{"N",2};{"N",1};{"S",'))
        self.assertTrue(arrays[1].endswith(';{"N",7}]'))
        # Historical probe label retained byte-for-byte; the first deletion errors,
        # so its following valid deletion is never executed.
        self.assertEqual(arrays[2], arrays[1].replace('above-bound', 'valid-after-noop'))


if __name__ == '__main__':
    unittest.main()

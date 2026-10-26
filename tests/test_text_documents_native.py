"""Finite TextDocument witnesses transcribed from an authenticated native run.

These are measured inputs/states, not a universal platform model. Native run
40254792139 executed the exact values485 source on Linux 1C 8.3.27.1508, server
and managed client; the original host comparison failed because TextDocument was
intentionally unimplemented. Replaying these observations is not fresh native
acceptance of the runtime under test.

No native capture/log/archive is loaded here. Expected raw text/lines and query
answers were transcribed from the independently verified 44-record ledger; they
are not computed by the interpreter or its projection helper. Mutator R=U in the
native stream was the harness's initialized sentinel, NOT a method-return probe.
"""
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = {
    'run_id': 40254792139,
    'run_attempt': 1,
    'head': '72dad51af3b2a800688555fb3e57c50397a77574',
    'merge': 'aaa6cc41f66cf1c79d3d7df7ef06d5781c52dea4',
    'tree': '09f578df3fda85b57d92fcfc3740fd56ae830bfb',
    'source_sha256': 'be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76',
    'native_values_sha256': '97df58bbf44f04bddc3861221aa8ad342cd45ad9985eb9be0be645d244b03fe4',
    'native_version': '8.3.27.1508',
    'native_source_file_count': 513,
    'native_staged_pin_count': 24,
    'native_runtime_source_file_count': 62,
    'native_message_count': 485,
    'observed_text_document_records': 44,
}
OBSERVATION_START = '// Begin bounded TextDocument observations (measurement only; no native answers).\n'
OBSERVATION_END = '// End bounded TextDocument observations.\n'

# (label, exact GetText result, exact ordered GetLine results). None marks the
# two Type lookup probes, which deliberately did not construct a document.
# Counts are explicitly checked against the number of these observed lines;
# this is not a split()/newline algorithm used to generate expected output.
OBSERVED_STATES = (
    ('constructor.ru', '', ()),
    ('constructor.en', '', ()),
    ('type.ru', None, None),
    ('type.en', None, None),
    ('typeof', '', ()),
    ('object.string', '', ()),
    ('set.empty', '', ()),
    ('set.single.ru', 'A', ('A',)),
    ('set.lf', 'A\nB', ('A', 'B')),
    ('set.cr', 'A\rB', ('A', 'B')),
    ('set.crlf', 'A\r\nB', ('A', 'B')),
    ('set.trailing.lf', 'A\n', ('A',)),
    ('set.trailing.cr', 'A\r', ('A',)),
    ('set.trailing.crlf', 'A\r\n', ('A',)),
    ('set.only.breaks', '\r\n\r\n', ('', '')),
    ('set.unicode', 'А\U0001f600e\u0301\u2028Z', ('А\U0001f600e\u0301\u2028Z',)),
    ('set.single.en', 'E', ('E',)),
    ('get.valid.en', 'A\r\nB', ('A', 'B')),
    ('get.zero', 'A\r\nB', ('A', 'B')),
    ('get.past', 'A\r\nB', ('A', 'B')),
    ('get.empty.one', '', ()),
    ('count.en', 'A\r\nB', ('A', 'B')),
    ('add.blank.ru', '\n', ('',)),
    ('add.single.en', 'A\nB\n', ('A', 'B')),
    ('add.multiline', 'A\r\nB\nX\nY\n', ('A', 'B', 'X', 'Y')),
    ('add.after.trailing.crlf', 'A\r\nB\n', ('A', 'B')),
    ('insert.begin.ru', 'X\nA\r\nB', ('X', 'A', 'B')),
    ('insert.middle.en', 'A\r\nX\nB', ('A', 'X', 'B')),
    ('insert.end', 'A\r\nB\nX\n', ('A', 'B', 'X')),
    ('insert.zero', 'X\nA\r\nB', ('X', 'A', 'B')),
    ('insert.past', 'A\r\nB\nX\n', ('A', 'B', 'X')),
    ('replace.first.ru', 'X\nB', ('X', 'B')),
    ('replace.last.en', 'A\r\nX\n', ('A', 'X')),
    ('replace.multiline', 'A\r\nX\nY\n', ('A', 'X', 'Y')),
    ('replace.zero', 'X\n', ('X',)),
    ('replace.past', 'A\r\nB', ('A', 'B')),
    ('delete.first.ru', 'B', ('B',)),
    ('delete.last.en', 'A\r\n', ('A',)),
    ('delete.only', '', ()),
    ('delete.zero', '', ()),
    ('delete.past', 'A\r\nB', ('A', 'B')),
    ('clear.ru', '', ()),
    ('clear.en', '', ()),
    ('clear.empty', '', ()),
)

# Only these ten native actions actually assigned a query answer. In particular,
# no mutator is put into an expression merely to inspect an unmeasured return.
OBSERVED_ANSWERS = {
    'type.ru': 'Текстовый документ',
    'type.en': 'Текстовый документ',
    'typeof': 'Текстовый документ',
    'object.string': 'ТекстовыйДокумент',
    'set.single.en': 'E',
    'get.valid.en': 'B',
    'get.zero': '',
    'get.past': '',
    'get.empty.one': '',
    'count.en': Decimal(2),
}


def measured_cases():
    """Extract only the native source's fixed setup/action strings, hash-bound."""
    source = (ROOT / 'integrational_tests/tests/values.bsl').read_bytes()
    # Match the repository's other offline fixture readers under Git autocrlf.
    # This does not normalize production input or permit changed source bytes.
    if os.name == 'nt':
        source = source.replace(b'\r\n', b'\n')
    if hashlib.sha256(source).hexdigest() != CAPTURE['source_sha256']:
        raise AssertionError('Native TextDocument observation source changed')
    text = source.decode('utf-8')
    if text.count(OBSERVATION_START) != 1 or text.count(OBSERVATION_END) != 1:
        raise AssertionError('Native TextDocument observation boundaries changed')
    block = text.split(OBSERVATION_START, 1)[1].split(OBSERVATION_END, 1)[0]
    cases = []
    for line in block.splitlines():
        if not line.startswith('НаблюдатьТекстовыйДокумент('):
            raise AssertionError('Unexpected native TextDocument observation statement')
        fields = re.findall(r'"((?:[^"]|"")*)"', line)
        if len(fields) != 4:
            raise AssertionError('Native TextDocument observation arity changed')
        label, setup, action, _readback = (field.replace('""', '"') for field in fields)
        cases.append((label, setup, action))
    if tuple(case[0] for case in cases) != tuple(case[0] for case in OBSERVED_STATES):
        raise AssertionError('Native TextDocument observation coverage/order changed')
    return cases


class TextDocumentNativeObservations(unittest.TestCase):
    def test_exact_source_and_all_44_measured_inputs_are_retained(self):
        cases = measured_cases()
        self.assertEqual(len(cases), CAPTURE['observed_text_document_records'])
        self.assertEqual(len({label for label, _, _ in cases}), 44)
        self.assertEqual(len(OBSERVED_ANSWERS), 10)
        self.assertEqual(sum(text is not None for _, text, _ in OBSERVED_STATES), 42)
        for label, _setup, action in cases:
            if label in OBSERVED_ANSWERS:
                self.assertIn('Ответ = ', action)
            elif label not in {'constructor.ru', 'constructor.en'}:
                self.assertNotIn('Ответ = ', action)

    def test_all_44_native_witnesses_through_independent_raw_field_reads(self):
        expected_states = {label: (text, lines) for label, text, lines in OBSERVED_STATES}
        for label, setup, action in measured_cases():
            with self.subTest(observation=label):
                output = []
                vm = Interpreter(output=output.append)
                vm.execute('Документ = Неопределено; Ответ = Неопределено;')
                # Native execution reported action=ok for every witness. These
                # calls must not be wrapped in catch-and-accept error handling.
                vm.execute(setup, source=f'native-textdoc-{label}-setup.bsl')
                vm.execute(action, source=f'native-textdoc-{label}-action.bsl')
                self.assertEqual(output, [])
                if label in OBSERVED_ANSWERS:
                    expected = OBSERVED_ANSWERS[label]
                    with self.subTest(field='query answer'):
                        actual = vm.execute('Ответ')
                        self.assertIs(type(actual), type(expected))
                        self.assertEqual(actual, expected)
                text, lines = expected_states[label]
                if text is None:
                    continue
                # Read raw fields directly, not through the measurement writer
                # or another production formatter used to construct expected data.
                with self.subTest(field='GetText'):
                    actual = vm.execute('Документ.ПолучитьТекст()')
                    self.assertIs(type(actual), str)
                    self.assertEqual(actual, text)
                with self.subTest(field='LineCount'):
                    actual = vm.execute('Документ.КоличествоСтрок()')
                    self.assertIs(type(actual), Decimal)
                    self.assertEqual(actual, Decimal(len(lines)))
                for index, expected in enumerate(lines, 1):
                    with self.subTest(field='GetLine', index=index):
                        actual = vm.execute(f'Документ.ПолучитьСтроку({index})')
                        self.assertIs(type(actual), str)
                        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()

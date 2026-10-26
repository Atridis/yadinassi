"""Finite native NStr witnesses, not a universal grammar/coercion/default model.

Run 40268511954 on Linux 1C 8.3.27.1508 authenticated all 49 observations;
only values failed host parity because NStr was not implemented. Replaying
these finite, fixed public inputs/results is not fresh native acceptance.
No private capture, log, archive or environment-derived text is included.
"""
import hashlib
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = {
    'run_id': 40268511954,
    'run_attempt': 1,
    'head': 'f898454785b7b0794577f2a4093f45349963549c',
    'merge': '452755d97c339433c8f597bb1191b4188b42ad2b',
    'tree': 'd80d1f6c7f0c783dabeb0f06f53e25849dedf96e',
    'source_sha256': '16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5',
    'native_values_sha256': '3958adc4220f5c51d8c0ded811847b43be8f71427f7d36410395f25449bba651',
    'ledger49_sha256': 'a506d12a8fff44bbb7ee8ddfbbebbfa49022d5cf09db23e0f5eed954b36a5d0c',
    'ledger13_sha256': '11599292635bc7a77f5755c80642648ccfe328ff931971346f657596a73410b1',
    'native_version': '8.3.27.1508',
    'source_file_count': 535,
    'staged_source_count': 24,
    'runtime_source_count': 63,
    'values_message_count': 534,
    'nstr_observation_count': 49,
    'configuration_language_metadata_observed': False,
}

# Literal (label, exact fixed expression, exact String, UTF-16BE units).
# These expected values were transcribed from the authenticated native ledger,
# never produced by the interpreter, parser or measurement projection helper.
OBSERVATIONS = (
    ('alias.ru.ru', 'НСтр("ru=\'А\';en=\'B\'", "ru")', 'А', '0410'),
    ('alias.ru.en', 'НСтр("ru=\'А\';en=\'B\'", "en")', 'B', '0042'),
    ('alias.en.ru', 'NStr("ru=\'А\';en=\'B\'", "ru")', 'А', '0410'),
    ('alias.en.en', 'NStr("ru=\'А\';en=\'B\'", "en")', 'B', '0042'),
    ('order.ru', 'НСтр("en=\'B\';ru=\'А\'", "ru")', 'А', '0410'),
    ('order.en', 'NStr("en=\'B\';ru=\'А\'", "en")', 'B', '0042'),
    ('spaces', 'НСтр("  ru = \' А \' ; en = \' B \'  ", "ru")', ' А ', '002004100020'),
    ('tabs', 'НСтр("ru" + Символ(9) + "=" + Символ(9) + "\'А\';en=\'B\'", "ru")', 'А', '0410'),
    ('empty.template', 'НСтр("", "ru")', '', ''),
    ('empty.ru', 'НСтр("ru=\'\';en=\'B\'", "ru")', '', ''),
    ('empty.en', 'NStr("ru=\'А\';en=\'\'", "en")', '', ''),
    ('separator.trailing', 'НСтр("ru=\'А\';en=\'B\';", "ru")', 'А', '0410'),
    ('separator.double', 'НСтр("ru=\'А\';;en=\'B\'", "ru")', 'А', '0410'),
    ('quote.apostrophe', 'НСтр("ru=\'O\'\'Brien\';en=\'B\'", "ru")', "O'Brien", '004f00270042007200690065006e'),
    ('quote.double', 'НСтр("ru=\'A""B\';en=\'B\'", "ru")', 'A"B', '004100220042'),
    ('content.semicolon.equals', 'НСтр("ru=\'A;B=C\';en=\'B\'", "ru")', 'A;B=C', '0041003b0042003d0043'),
    ('unicode', 'НСтр("ru=\'Я😀é\';en=\'B\'", "ru")', 'Я😀é', '042fd83dde0000650301'),
    ('language.upper', 'НСтр("ru=\'А\';en=\'B\'", "RU")', 'А', '0410'),
    ('language.mixed', 'НСтр("ru=\'А\';en=\'B\'", "rU")', 'А', '0410'),
    ('language.missing', 'НСтр("ru=\'А\';en=\'B\'", "de")', '', ''),
    ('language.missing.reordered', 'NStr("en=\'B\';ru=\'А\'", "de")', '', ''),
    ('duplicate.first', 'НСтр("ru=\'A\';ru=\'B\';en=\'C\'", "ru")', 'A', '0041'),
    ('duplicate.reordered', 'НСтр("ru=\'B\';ru=\'A\';en=\'C\'", "ru")', 'B', '0042'),
    ('duplicate.case', 'НСтр("RU=\'A\';ru=\'B\';en=\'C\'", "ru")', 'A', '0041'),
    ('malformed.unquoted', 'НСтр("ru=A;en=\'B\'", "ru")', 'A', '0041'),
    ('malformed.unterminated', 'НСтр("ru=\'A;en=\'B\'", "ru")', '', ''),
    ('malformed.no.equals', 'НСтр("ru\'A\';en=\'B\'", "ru")', '', ''),
    ('malformed.trailing', 'НСтр("ru=\'А\';en=\'B\'X", "ru")', '', ''),
    ('language.omitted', 'НСтр("ru=\'А\';en=\'B\'")', 'А', '0410'),
    ('language.empty', 'НСтр("ru=\'А\';en=\'B\'", "")', 'А', '0410'),
    ('language.undefined', 'НСтр("ru=\'А\';en=\'B\'", Неопределено)', 'А', '0410'),
    ('language.number', 'НСтр("ru=\'А\';en=\'B\'", 1)', '', ''),
    ('language.boolean', 'НСтр("ru=\'А\';en=\'B\'", Истина)', '', ''),
    ('language.null', 'НСтр("ru=\'А\';en=\'B\'", Null)', 'А', '0410'),
    ('template.number', 'НСтр(1, "ru")', '', ''),
    ('template.undefined', 'НСтр(Неопределено, "ru")', '', ''),
    ('default.reordered.omitted', 'НСтр("en=\'B\';ru=\'А\'")', 'А', '0410'),
    ('default.reordered.empty', 'НСтр("en=\'B\';ru=\'А\'", "")', 'А', '0410'),
    ('default.reordered.undefined', 'НСтр("en=\'B\';ru=\'А\'", Неопределено)', 'А', '0410'),
    ('default.reordered.null', 'НСтр("en=\'B\';ru=\'А\'", Null)', 'А', '0410'),
    ('default.enonly.omitted', 'НСтр("en=\'B\'")', '', ''),
    ('default.enonly.empty', 'НСтр("en=\'B\'", "")', '', ''),
    ('default.enonly.undefined', 'НСтр("en=\'B\'", Неопределено)', '', ''),
    ('default.enonly.null', 'НСтр("en=\'B\'", Null)', '', ''),
    ('default.enonly.explicit', 'НСтр("en=\'B\'", "en")', 'B', '0042'),
    ('coercion.number.value', 'НСтр("1=\'N\';ru=\'R\'", 1)', '', ''),
    ('coercion.number.string', 'НСтр("1=\'N\';ru=\'R\'", Строка(1))', '', ''),
    ('coercion.boolean.value', 'НСтр("Да=\'T\';ru=\'R\'", Истина)', 'T', '0054'),
    ('coercion.boolean.string', 'НСтр("Да=\'T\';ru=\'R\'", Строка(Истина))', 'T', '0054'),
)


def measured_source():
    source = (ROOT / 'integrational_tests/tests/values.bsl').read_bytes()
    # Offline checkout normalization only; live admission stays LF/hash strict.
    if os.name == 'nt':
        source = source.replace(b'\r\n', b'\n')
    if hashlib.sha256(source).hexdigest() != CAPTURE['source_sha256']:
        raise AssertionError('Native NStr observation source changed')
    return source.decode('utf-8')


def measured_cases():
    source = measured_source()
    cases = []
    for line in source.splitlines():
        if line.startswith('НаблюдатьНСтр('):
            fields = re.findall(r'"((?:[^"]|"")*)"', line)
            if len(fields) != 2:
                raise AssertionError('Native NStr observation arity changed')
            cases.append(tuple(field.replace('""', '"') for field in fields))
    if tuple(cases) != tuple(row[:2] for row in OBSERVATIONS):
        raise AssertionError('Native NStr finite inputs/order changed')
    return cases


class NStrNativeObservations(unittest.TestCase):
    def test_exact_source_all49_and_original36_are_retained(self):
        self.assertEqual(len(measured_cases()), CAPTURE['nstr_observation_count'])
        self.assertEqual(len({row[0] for row in OBSERVATIONS}), 49)
        self.assertEqual(OBSERVATIONS[35][0], 'template.undefined')
        self.assertEqual(OBSERVATIONS[36][0], 'default.reordered.omitted')
        self.assertFalse(CAPTURE['configuration_language_metadata_observed'])

    def test_all49_raw_results_match_independent_native_string_and_utf16_literals(self):
        for label, expression, expected, units in OBSERVATIONS:
            with self.subTest(label=label):
                output = []
                vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
                actual = vm.execute(expression, source='native-nstr-' + label + '.bsl')
                self.assertIs(type(actual), str)
                self.assertEqual(actual, expected)
                self.assertEqual(actual.encode('utf-16-be', errors='surrogatepass').hex(), units)
                self.assertEqual(output, [])

    def test_complete534_output_matches_native_bytes_without_filtering(self):
        output = []
        # Match the existing native host driver's explicit timezone for the
        # unrelated date records in this whole scenario. NStr never reads it.
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Etc/UTC'}):
            Interpreter(output.append, native_target=LINUX_8_3_27_1508).execute(measured_source())
        self.assertEqual(len(output), CAPTURE['values_message_count'])
        # Established six-scenario wire newline framing, not an NStr model.
        raw = ''.join(line.replace('\r\n', '\n').replace('\r', '\n') + '\n'
                      for line in output).encode('utf-8')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CAPTURE['native_values_sha256'])

    def test_controls_do_not_turn_equal_empty_numbers_into_coercion_evidence(self):
        expected = {row[0]: row[2] for row in OBSERVATIONS}
        self.assertEqual(expected['coercion.number.string'], '')
        self.assertEqual(expected['coercion.number.value'], '')
        self.assertNotEqual(expected['coercion.boolean.string'], '')
        self.assertEqual(expected['coercion.boolean.value'], expected['coercion.boolean.string'])
        self.assertEqual(expected['default.enonly.explicit'], 'B')
        for suffix in ('omitted', 'empty', 'undefined', 'null'):
            self.assertEqual(expected['default.reordered.' + suffix], 'А')
            self.assertEqual(expected['default.enonly.' + suffix], '')


if __name__ == '__main__':
    unittest.main()

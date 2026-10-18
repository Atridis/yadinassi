"""Date probe packaging, not an oracle for native Date behavior."""
import hashlib
from pathlib import Path
import unittest

from integrational_tests.test_launcher import collect_scripts
from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/dates.bsl'
FINAL = 'date.checkpoint.complete: [ok]'


def source():
    # This checkpoint owns its prefix through its required marker. Later date
    # families can append observations without weakening any foundation checks.
    text = SOURCE.read_text(encoding='utf-8-sig')
    end = 'Сообщить("' + FINAL + '");'
    return text[:text.index(end) + len(end)] + '\n'


def calls():
    return [node.expression for node in parse(source())
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьДату']


def expressions():
    return {call.arguments[0].value: call.arguments[1].value for call in calls()}


def helper():
    return source().split('НаблюдатьДату("', 1)[0]


class DateCheckpointTests(unittest.TestCase):
    def test_discovery_includes_new_scenario_and_existing_five(self):
        scripts = {path.name for path in collect_scripts(SOURCE.parent)}
        self.assertTrue({'basic.bsl', 'functions.bsl', 'collections.bsl',
                         'numbers.bsl', 'strings.bsl', 'dates.bsl'} <= scripts)

    def test_exact_probe_count_unique_labels_and_bounded_payloads(self):
        probes = calls()
        self.assertEqual(len(probes), 50)
        self.assertEqual(len(expressions()), 50)
        for call in probes:
            self.assertEqual(len(call.arguments), 2)
            label, expression = (arg.value for arg in call.arguments)
            self.assertRegex(label, r'^[a-z0-9.-]+$')
            self.assertLessEqual(len(expression), 300, label)
            self.assertNotRegex(expression, r'[;\r\n]')
            self.assertNotRegex(expression, r'(?i)\b(?:Import|Execute|Eval|While|For|Goto)\b')

    def test_declarations_precede_body_and_literals_are_dynamic(self):
        started = False
        routines = []
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
                routines.append(node.name)
            else:
                started = True
        self.assertEqual(routines, ['НаблюдатьДату', 'ПроверитьКлючиДат'])
        # Date literals are strings passed to Eval: no unsupported lexical token
        # may prevent the whole checkpoint reaching its completion marker.
        self.assertEqual(sum(label.startswith('literal.') for label in expressions()), 6)

    def test_complete_output_labels_and_final_sentinel(self):
        output = []
        Interpreter(output=output.append).execute(source())
        self.assertEqual(len(output), 51)
        self.assertEqual(output[-1], FINAL)
        expected = ['date.' + call.arguments[0].value for call in calls()]
        self.assertEqual([line.split(': [', 1)[0] for line in output[:-1]], expected)
        for message in output[:-1]:
            self.assertRegex(message, r'(?s)^date\.[a-z0-9.-]+: \[(?:error|serialize-error|\{.*\})\]$')

    def test_helper_isolates_evaluation_and_serialization_failures(self):
        output = []
        interpreter = Interpreter(output=output.append)
        interpreter.register_function('HostOnly', lambda: object())
        interpreter.execute(helper() + '''
НаблюдатьДату("missing", "NoSuchFunction()");
НаблюдатьДату("syntax", "@");
НаблюдатьДату("unserializable", "HostOnly()");
НаблюдатьДату("number", "2 + 3");
НаблюдатьДату("string", "String(5)");
''')
        self.assertEqual(output, ['date.missing: [error]', 'date.syntax: [error]',
                                 'date.unserializable: [serialize-error]',
                                 'date.number: [{"N",5}]', 'date.string: [{"S","5"}]'])

    def test_core_type_and_inverse_codec_are_not_guessed(self):
        values = expressions()
        self.assertEqual(values['codec.type-ru'], 'Тип("Дата")')
        self.assertEqual(values['codec.type-en'], 'Type("Date")')
        self.assertIn('TypeOf(Date(', values['codec.typeof'])
        for label in ('codec.roundtrip', 'codec.type-roundtrip', 'precision.roundtrip'):
            self.assertIn('ValueFromStringInternal(ValueToStringInternal(', values[label])
        self.assertNotRegex(source(), r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')

    def test_precision_witnesses_preserve_numeric_differences(self):
        values = expressions()
        for label, expression in values.items():
            if label.startswith('precision.delta-'):
                self.assertRegex(expression, r'\) - Date\(')
        self.assertEqual(sum(label.startswith('precision.delta-') for label in values), 6)
        for label in ('precision.half-second', 'precision.negative-half-second'):
            for fraction in ('0.4', '0.5', '0.6'):
                self.assertIn(fraction, values[label])
        self.assertIn(') - Date(', values['construct.fraction'])
        self.assertIn(') - Date(', values['precision.roundtrip'])
        self.assertIn('Second(', values['precision.second-component'])

    def test_constructor_and_literal_arity_discriminators(self):
        values = expressions()
        self.assertEqual(values['construct.ymdh'], 'Date(2024, 2, 29, 12)')
        self.assertEqual(values['construct.ymdhm'], 'Date(2024, 2, 29, 12, 34)')
        self.assertIn(', , ,', values['construct.omitted'])
        for literal in ("'20240229'", "'2024022912'", "'202402291234'", "'20240229123456'"):
            self.assertIn(literal, values.values())

    def test_component_family_and_equal_map_key_roundtrip(self):
        values = expressions()
        for name in ('Year', 'Month', 'Day', 'Hour', 'Minute', 'Second'):
            self.assertIn(name + '(Date(', values['components.all'])
        self.assertEqual(values['codec.map-value-keys'], 'ПроверитьКлючиДат()')
        code = helper()
        self.assertEqual(code.count('Таблица.Вставить('), 2)
        self.assertIn('ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Таблица))', code)
        self.assertIn('Восстановлено.Получить(Ключ)', code)

    def test_bounded_readonly_deterministic_program(self):
        self.assertNotRegex(source(), r'\b(?:Пока|Для|Перейти|Выполнить|ОписаниеОшибки|ТекущаяДата|CurrentDate)\b')
        self.assertEqual(source().count('Вычислить('), 1)
        self.assertEqual(source().count('date.checkpoint.complete'), 1)
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_execution_does_not_write_goldens_or_metadata(self):
        paths = [path for path in (ROOT / 'integrational_tests/output').rglob('*') if path.is_file()]
        paths.append(ROOT / 'integrational_tests/meta.md')
        before = {path: path.read_bytes() for path in paths}
        Interpreter(output=lambda message: None).execute(source())
        after_paths = [path for path in (ROOT / 'integrational_tests/output').rglob('*') if path.is_file()]
        after_paths.append(ROOT / 'integrational_tests/meta.md')
        self.assertEqual(before, {path: path.read_bytes() for path in after_paths})


class DateCalendarCheckpointTests(unittest.TestCase):
    FINAL = 'date.calendar.checkpoint.complete: [ok]'

    def full_source(self):
        return SOURCE.read_text(encoding='utf-8-sig')

    def calendar_expressions(self):
        return {node.expression.arguments[0].value: node.expression.arguments[1].value
                for node in parse(self.full_source())
                if isinstance(node, ast.ExpressionStatement)
                and isinstance(node.expression, ast.Call)
                and isinstance(node.expression.callee, ast.Name)
                and node.expression.callee.name == 'НаблюдатьДату'
                and node.expression.arguments[0].value.startswith('calendar.')}

    def assert_foundation_prefix(self, raw):
        # Git checkout can expand LF to CRLF on Windows. Verify the exact stored
        # source bytes after only this transport normalization, not whitespace.
        raw = raw.replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(raw[:7119]).hexdigest(),
                         '5fbe934ac9d0ca1829a7f87e5f770fac797c9f9d9b52105110ddf24731f0fa6e')
        self.assertEqual(raw[:7119].decode('utf-8-sig'), source())

    def test_foundation_source_prefix_is_byte_exact(self):
        self.assert_foundation_prefix(SOURCE.read_bytes())

    def test_foundation_source_hash_accepts_checkout_crlf_only(self):
        raw = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        self.assert_foundation_prefix(raw.replace(b'\n', b'\r\n'))
        for changed in (b' ' + raw, raw.replace(b'\n', b' \n', 1), raw.replace(b'\n', b'\r', 1)):
            with self.subTest(prefix=changed[:80]):
                with self.assertRaises(AssertionError):
                    self.assert_foundation_prefix(changed)

    def test_exact_bounded_calendar_observations_and_labels(self):
        values = self.calendar_expressions()
        self.assertEqual(len(values), 48)
        self.assertEqual(sum(k.startswith('calendar.period.') for k in values), 14)
        self.assertEqual(sum(k.startswith('calendar.month.') for k in values), 14)
        self.assertEqual(sum(k.startswith('calendar.number.') for k in values), 12)
        self.assertEqual(sum(k.startswith('calendar.edge.') for k in values), 8)
        for label, expression in values.items():
            self.assertRegex(label, r'^calendar\.[a-z0-9.-]+$')
            self.assertLessEqual(len(expression), 300, label)
            self.assertNotRegex(expression, r'[;\r\n]')
            # Parse expressions without evaluating unsupported calendar behavior.
            self.assertTrue(parse('x = ' + expression + ';'), label)
        calls = [node.expression for node in parse(self.full_source())
                 if isinstance(node, ast.ExpressionStatement)
                 and isinstance(node.expression, ast.Call)
                 and isinstance(node.expression.callee, ast.Name)
                 and node.expression.callee.name == 'НаблюдатьДату']
        self.assertEqual(len(calls), 98)
        self.assertEqual(len({call.arguments[0].value for call in calls}), 98)
        self.assertTrue(all(len(call.arguments) == 2 for call in calls))

    def test_period_precision_is_numeric_against_explicit_whole_date(self):
        values = self.calendar_expressions()
        for unit, russian in (('Minute', 'Минуты'), ('Hour', 'Часа'), ('Day', 'Дня'),
                              ('Week', 'Недели'), ('Month', 'Месяца'),
                              ('Quarter', 'Квартала'), ('Year', 'Года')):
            for prefix, function in (('begin-', 'BegOf' + unit), ('end-', 'Конец' + russian)):
                expression = values['calendar.period.' + prefix + unit.lower()]
                self.assertIn('New Structure("Value,Delta",', expression)
                self.assertEqual(expression.count(function + '('), 2)
                self.assertEqual(expression.count('+ 0.1234'), 2)
                self.assertRegex(expression, r'\) - Date\([0-9,]+\)\)$')
                self.assertNotIn('ValueFromStringInternal', expression)

    def test_month_precision_fractional_counts_and_clipping_are_observed(self):
        values = self.calendar_expressions()
        for key in ('forward-year', 'backward-year', 'zero-fraction', 'leap-january'):
            self.assertIn('0.1234', values['calendar.month.' + key])
            self.assertIn(' - Date(', values['calendar.month.' + key])
        for key, count in (('pos-half', '0.5'), ('neg-half', '-0.5'),
                           ('pos-one-half', '1.5'), ('neg-one-half', '-1.5')):
            self.assertTrue(values['calendar.month.count-' + key].endswith(',' + count + ')'))
        for key in ('leap-january', 'common-january', 'leap-year', 'reverse-end',
                    'chain', 'min-underflow', 'max-overflow'):
            self.assertIn('calendar.month.' + key, values)

    def test_numbering_distinguishes_week_conventions_and_leap_ordinals(self):
        values = self.calendar_expressions()
        for year in (2015, 2018, 2019, 2020, 2021, 2022, 2023):
            expression = values[f'calendar.number.january-{year}']
            for function in ('WeekOfYear', 'WeekDay', 'DayOfYear'):
                self.assertIn(f'{function}(Date({year},1,1))', expression)
        for key in ('year-end', 'first-monday', 'february'):
            self.assertIn('НеделяГода(Date(', values['calendar.number.' + key])
        self.assertIn('Date(2024,2,29)', values['calendar.number.leap-ordinals'])
        self.assertIn('Date(2024,3,3)', values['calendar.number.common-and-weekdays'])
        self.assertIn('Date(2024,3,4)', values['calendar.number.common-and-weekdays'])
        for day in (3, 4):
            self.assertIn(f'WeekOfYear(Date(2024,3,{day}))',
                          values['calendar.number.common-and-weekdays'])

    def test_both_sentinels_and_all_labels_reached_without_guessing_results(self):
        output = []
        Interpreter(output=output.append).execute(self.full_source())
        self.assertEqual(len(output), 100)
        self.assertEqual(output[50], FINAL)
        self.assertEqual(output[-1], self.FINAL)
        expected = ['date.' + label for label in self.calendar_expressions()]
        self.assertEqual([line.split(': [', 1)[0] for line in output[51:-1]], expected)
        for message in output[51:-1]:
            self.assertRegex(message, r'(?s)^date\.calendar\.[a-z0-9.-]+: \[(?:error|serialize-error|\{.*\})\]$')

    def test_readonly_bounded_append_reuses_protected_observer(self):
        text = self.full_source()
        self.assertEqual(text.count('Вычислить('), 1)
        self.assertEqual(text.count(FINAL), 1)
        self.assertEqual(text.count(self.FINAL), 1)
        self.assertTrue(text.rstrip().endswith('Сообщить("' + self.FINAL + '");'))
        self.assertNotRegex(text, r'\b(?:Пока|Для|Перейти|Выполнить|ОписаниеОшибки|ТекущаяДата|CurrentDate)\b')
        self.assertNotRegex(text[len(source()):], r'\b(?:Процедура|Функция)\b')
        raw = (ROOT / 'integrational_tests/output/dates.out').read_bytes()
        before = hashlib.sha256(raw).hexdigest()
        Interpreter(output=lambda message: None).execute(text)
        self.assertEqual(hashlib.sha256((ROOT / 'integrational_tests/output/dates.out').read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()

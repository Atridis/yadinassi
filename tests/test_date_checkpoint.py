"""Date probe packaging, not an oracle for native Date behavior."""
from pathlib import Path
import unittest

from integrational_tests.test_launcher import collect_scripts
from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/dates.bsl'
FINAL = 'date.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


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


if __name__ == '__main__':
    unittest.main()

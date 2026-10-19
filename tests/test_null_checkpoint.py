"""Special-value checkpoint packaging; no invented native Null semantics."""
from pathlib import Path
import unittest

from integrational_tests.test_launcher import collect_scripts
from scripts.smoke_test import null_checkpoint_source
from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
FINAL = 'null.checkpoint.complete: [ok]'


def source():
    # XML and future thematic observations have their own packaging guards.
    # Keep these assertions scoped to the original owner-confirmed Null block.
    return null_checkpoint_source(SOURCE.read_text(encoding='utf-8-sig'))


def calls():
    return [node.expression for node in parse(source())
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьNull']


def expressions():
    return {call.arguments[0].value: call.arguments[1].value for call in calls()}


def helper():
    return source().split('НаблюдатьNull("', 1)[0]


class NullCheckpointTests(unittest.TestCase):
    def test_null_extraction_ignores_other_helpers_and_appended_observations(self):
        original = source()
        body_start = '// Значение, тип и настоящий прямой/обратный кодек.'
        helpers, _, body = original.partition(body_start)
        extended = helpers + '''// Нативный checkpoint скалярного XML.
Процедура НаблюдатьXML(Знач Выражение)
    Сообщить(Вычислить(Выражение));
КонецПроцедуры

''' + body_start + body + '''
// Скалярный XML: наблюдения без заранее заданных ответов.
НаблюдатьXML("NoSuchFunction()");
Сообщить("xml.checkpoint.complete: [ok]");
'''
        self.assertEqual(null_checkpoint_source(extended), original)

    def test_null_extraction_requires_unique_ordered_boundaries(self):
        original = source()
        body_start = '// Значение, тип и настоящий прямой/обратный кодек.'
        final = 'Сообщить("' + FINAL + '");'
        malformed = [original.replace(body_start, ''), original + body_start,
                     original.replace(final, ''), original + final,
                     final + original.replace(final, '')]
        for program in malformed:
            with self.subTest(program=program), self.assertRaises(AssertionError):
                null_checkpoint_source(program)

    def test_discovery_keeps_five_existing_scenarios_and_adds_values(self):
        self.assertEqual({p.name for p in collect_scripts(SOURCE.parent)},
                         {name + '.bsl' for name in
                          ('functions', 'strings', 'numbers',
                           'collections', 'dates', 'values')})

    def test_exact_unique_bounded_observations(self):
        self.assertEqual(len(calls()), 40)
        self.assertEqual(len(expressions()), 40)
        for call in calls():
            self.assertEqual(len(call.arguments), 2)
            label, expression = (arg.value for arg in call.arguments)
            self.assertRegex(label, r'^[a-z0-9.-]+$')
            self.assertLessEqual(len(expression), 100, label)
            self.assertNotRegex(expression, r'[;\r\n]')
            self.assertNotRegex(expression, r'(?i)\b(?:Import|Execute|Eval|While|For|Goto)\b')

    def test_helpers_precede_executable_body(self):
        started = False
        routines = []
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
                routines.append(node.name)
            else:
                started = True
        self.assertEqual(routines,
                         ['НаблюдатьNull', 'ВложенныйNull', 'ПоискNull', 'КлючNull'])
        # Null is evaluated only dynamically. The native module can reach its
        # marker even when an individual expression or its serialization fails.
        self.assertNotRegex(helper(), r'(?i)\b(?:=|return|возврат)\s+null\b')

    def test_complete_ordered_output_and_final_marker(self):
        output = []
        Interpreter(output=output.append).execute(source())
        self.assertEqual(len(output), 41)
        self.assertEqual(output[-1], FINAL)
        self.assertEqual([line.split(': [', 1)[0] for line in output[:-1]],
                         ['null.' + call.arguments[0].value for call in calls()])
        for line in output[:-1]:
            self.assertRegex(line, r'(?s)^null\.[a-z0-9.-]+: \[(?:error|serialize-error|\{.*\})\]$')

    def test_evaluation_and_serialization_failures_are_isolated(self):
        output = []
        interpreter = Interpreter(output=output.append)
        interpreter.register_function('HostOnly', lambda: object())
        interpreter.execute(helper() + '''
НаблюдатьNull("missing", "NoSuchFunction()");
НаблюдатьNull("syntax", "@");
НаблюдатьNull("unserializable", "HostOnly()");
НаблюдатьNull("next", "2 + 3");
''')
        self.assertEqual(output, ['null.missing: [error]', 'null.syntax: [error]',
                                 'null.unserializable: [serialize-error]',
                                 'null.next: [{"N",5}]'])

    def test_value_and_type_codecs_are_observed_not_guessed(self):
        values = expressions()
        self.assertEqual(values['type.ru'], 'ТипЗнч(Null)')
        self.assertEqual(values['type.en'], 'TypeOf(Null)')
        self.assertEqual(values['type.name'], 'Type("Null")')
        for label in ('codec.value-roundtrip', 'codec.type-roundtrip'):
            self.assertIn('ValueFromStringInternal(ValueToStringInternal(', values[label])
        self.assertNotRegex(source(), r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')

    def test_logic_observes_both_positions_without_assuming_sql(self):
        values = expressions()
        for operation in ('And', 'Or'):
            for boolean in ('True', 'False'):
                self.assertIn(f'Null {operation} {boolean}', values.values())
                self.assertIn(f'{boolean} {operation} Null', values.values())
        self.assertEqual(values['conditional'], '?(Null, "then", "else")')
        self.assertIn('Null = Null', values.values())
        self.assertIn('Null <> Null', values.values())
        self.assertIn('Null = Undefined', values.values())

    def test_collections_observe_undefined_separation_and_nested_inverse(self):
        values = expressions()
        self.assertEqual(values['collection.nested-roundtrip'], 'ВложенныйNull(Null)')
        self.assertEqual(values['collection.find'], 'ПоискNull(Null)')
        self.assertEqual(values['collection.map-roundtrip'], 'КлючNull(Null)')
        self.assertEqual(helper().count('ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр('), 2)
        self.assertIn('Карта.Вставить(Неопределено, "undefined")', helper())
        self.assertEqual(helper().count('Карта.Вставить(Значение,'), 2)
        self.assertIn('МассивЗначений.Найти(Неопределено)', helper())

    def test_checkpoint_is_bounded_readonly_and_deterministic(self):
        self.assertNotRegex(source(), r'\b(?:Пока|Для|Перейти|Выполнить|ОписаниеОшибки|ТекущаяДата|CurrentDate)\b')
        self.assertEqual(source().count('Вычислить('), 1)
        self.assertEqual(source().count('null.checkpoint.complete'), 1)
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_local_execution_preserves_owner_outputs_and_metadata(self):
        paths = list((ROOT / 'integrational_tests/output').rglob('*'))
        paths += [ROOT / 'integrational_tests/meta.md', ROOT / 'tests/fixtures/basic.out']
        before = {p: p.read_bytes() for p in paths if p.is_file()}
        Interpreter(output=lambda message: None).execute(source())
        paths = list((ROOT / 'integrational_tests/output').rglob('*'))
        paths += [ROOT / 'integrational_tests/meta.md', ROOT / 'tests/fixtures/basic.out']
        self.assertEqual(before, {p: p.read_bytes() for p in paths if p.is_file()})


if __name__ == '__main__':
    unittest.main()

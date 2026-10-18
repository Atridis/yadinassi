"""Bounded packaging checks for pending native evidence; not native expectations."""
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/strings.bsl'
PREVIOUS_MARKER = 'strings.compare-xml.complete: [ok]'
FINAL_MARKER = 'search.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def normalize(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def checkpoint_calls():
    return [node for node in parse(source())
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name in (
                'ПроверитьВыражениеПоиска', 'ПроверитьОбъектПоиска', 'ПроверитьБлокПоиска')]


class SearchDirectionCheckpointTests(unittest.TestCase):
    def outputs(self):
        output = []
        Interpreter(output=output.append).execute(source())
        lines = normalize('\n'.join(output) + '\n').splitlines()
        boundary = lines.index(PREVIOUS_MARKER) + 1
        return lines[:boundary], lines[boundary:]

    def test_declarations_precede_executable_body(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_exact_case_counts_and_unique_labels(self):
        counts = {'ПроверитьВыражениеПоиска': 40, 'ПроверитьОбъектПоиска': 3,
                  'ПроверитьБлокПоиска': 5}
        all_labels = []
        for helper, count in counts.items():
            labels = re.findall(r'^' + helper + r'\("([^"]+)"', source(), re.MULTILINE)
            self.assertEqual(len(labels), count, helper)
            all_labels.extend(labels)
        self.assertEqual(len(set(all_labels)), 48)

    def test_existing_native_prefix_unchanged(self):
        native = normalize((ROOT / 'integrational_tests/output/strings.out').read_text(
            encoding='utf-8-sig')).splitlines()
        prefix = native[:native.index(PREVIOUS_MARKER) + 1]
        self.assertEqual(self.outputs()[0], prefix)

    def test_every_observation_reaches_sentinel(self):
        _, added = self.outputs()
        self.assertEqual(len(added), 61)
        self.assertEqual(added[-1], FINAL_MARKER)
        labels = [line.split(': ', 1)[0] for line in added[:-1]]
        self.assertEqual(len(set(labels)), 60)
        self.assertTrue(all(label.startswith('search.') for label in labels))
        for line in added[:-1]:
            self.assertRegex(line, r': \[(?:error|\{[^\n]+\})\]$')

    def test_dynamic_payloads_parse_and_are_bounded(self):
        # The payload syntax must parse locally even when the optional API is absent.
        calls = checkpoint_calls()
        self.assertEqual(len(calls), 48)
        for node in calls:
            label, payload = (argument.value for argument in node.expression.arguments)
            self.assertLess(len(payload), 512, label)
            self.assertNotIn('\n', payload, label)
            self.assertNotRegex(payload, r'(?i)\b(?:Пока|While|Goto|Перейти)\b')
            parse(payload if node.expression.callee.name == 'ПроверитьБлокПоиска'
                  else 'Результат = ' + payload + ';')
        self.assertIn('Если Количество > 2 Тогда ВызватьИсключение ""limit"";', source())

    def test_unknown_api_and_invalid_dynamic_code_do_not_hide_later_cases(self):
        helpers = source().split('// Строковый конвейер', 1)[0]
        output = []
        vm = Interpreter(output=output.append)
        vm.execute(helpers + '''
Процедура Показать(Знач Метка, Знач Данные)
    Сообщить(Метка + ": [" + Строка(Данные) + "]");
КонецПроцедуры
ПроверитьВыражениеПоиска("unknown", "UnimplementedSearchProbe()");
ПроверитьБлокПоиска("invalid", "x = ;");
ПроверитьВыражениеПоиска("recovery", "StrFind(""abc"", ""b"")");
ПроверитьБлокПоиска("assigned", "Результат = 7;");
''')
        self.assertEqual(output, ['unknown: [error]', 'invalid: [error]',
                                  'recovery: [{"N",2}]', 'assigned: [{"N",7}]'])

    def test_namespace_readback_is_observed_without_identity_assumption(self):
        helpers = source().split('// Строковый конвейер', 1)[0]
        output = []
        vm = Interpreter(output=output.append)
        vm.execute(helpers + '''
Процедура Показать(Знач Метка, Знач Данные)
    Сообщить(Метка + ": [" + Строка(Данные) + "]");
КонецПроцедуры
ПроверитьОбъектПоиска("control.namespace", "RoundMode");
''')
        # Existing owner-confirmed RoundMode behavior tests the observer itself.
        self.assertEqual(len(output), 5)
        self.assertEqual(output[3], 'control.namespace.readback: [{"U"}]')
        self.assertTrue(output[4].startswith('control.namespace.readback-type: [{"T",'))

    def test_boundary_cases_discriminate_unknown_semantics(self):
        text = source()
        for fragment in (
            'StrFind(""abc"", ""a"", SearchDirection.FromBegin, 1.9)',
            'StrFind(""abcabcabc"", ""bc"", SearchDirection.FromBegin, 3, 2)',
            'StrFind(""abcabcabc"", ""bc"", SearchDirection.FromEnd, 6, 2)',
            'StrFind(""abc"", ""b"", SearchDirection.FromEnd, Undefined)',
            'StrFind("""", """", SearchDirection.FromEnd)',
            'StrFind(""abc"", """", SearchDirection.FromBegin, 1, 0)',
        ):
            self.assertIn(fragment, text)
        helpers = text.split('// Строковый конвейер', 1)[0]
        self.assertNotIn('ОписаниеОшибки', helpers)
        self.assertEqual(helpers.count('Показать(Метка, "error")'), 2)


if __name__ == '__main__':
    unittest.main()

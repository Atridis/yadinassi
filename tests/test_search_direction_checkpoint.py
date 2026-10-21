"""Bounded packaging checks for pending native evidence; not native expectations."""
from hashlib import sha256
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/strings.bsl'
PREVIOUS_MARKER = 'strings.compare-xml.complete: [ok]'
FINAL_MARKER = 'search.checkpoint.complete: [ok]'
EMPTY_MARKER = 'search.empty-checkpoint.complete: [ok]'
ORIGINAL_END = 'Показать("search.checkpoint.complete", "ok");'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def normalize(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def original_source():
    return source().split(ORIGINAL_END, 1)[0] + ORIGINAL_END


def empty_source():
    return source().split(ORIGINAL_END, 1)[1]


def checkpoint_calls(text=None):
    return [node for node in parse(original_source() if text is None else text)
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
        end = lines.index(FINAL_MARKER) + 1
        return lines[:boundary], lines[boundary:end]

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
            labels = re.findall(r'^' + helper + r'\("([^"]+)"', original_source(), re.MULTILINE)
            self.assertEqual(len(labels), count, helper)
            all_labels.extend(labels)
        self.assertEqual(len(set(all_labels)), 48)

    def test_existing_native_prefix_unchanged(self):
        native = normalize((ROOT / 'tests/fixtures/native_windows/strings.out').read_text(
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



    def test_empty_supplement_exact_ten_independent_cases(self):
        expected = {}
        for direction, label in (('FromBegin', 'forward'), ('FromEnd', 'backward')):
            for start, occurrence in ((3, 1), (1, 3), (3, 2)):
                expected[f'search.empty.{label}.start{start}-occurrence{occurrence}'] = (
                    f'StrFind("abc", "", SearchDirection.{direction}, {start}, {occurrence})')
            expected[f'search.empty.{label}.defaults'] = (
                f'StrFind("abc", "", SearchDirection.{direction})')
            expected[f'search.empty.both-empty.{label}.occurrence2'] = (
                f'StrFind("", "", SearchDirection.{direction}, 1, 2)')
        calls = checkpoint_calls(empty_source())
        self.assertEqual(len(calls), 10)
        actual = {}
        for node in calls:
            self.assertEqual(node.expression.callee.name, 'ПроверитьВыражениеПоиска')
            label, payload = (argument.value for argument in node.expression.arguments)
            self.assertNotIn(label, actual)
            actual[label] = payload
        self.assertEqual(actual, expected)

    def test_empty_supplement_reaches_distinct_sentinel(self):
        output = []
        Interpreter(output=output.append).execute(source())
        lines = normalize('\n'.join(output) + '\n').splitlines()
        boundary = lines.index(FINAL_MARKER) + 1
        self.assertEqual(boundary, 375)
        added = lines[boundary:]
        self.assertEqual(len(added), 11)
        self.assertEqual(added[-1], EMPTY_MARKER)
        labels = [line.split(': ', 1)[0] for line in added[:-1]]
        self.assertEqual(len(set(labels)), 10)
        self.assertTrue(all(label.startswith('search.empty.') for label in labels))
        for line in added[:-1]:
            self.assertRegex(line, r': \[(?:error|\{[^\n]+\})\]$')

    def test_owner_native_golden_keeps_all_375_lines(self):
        # Owner output is evidence, not a golden generated by the interpreter.
        native = (ROOT / 'tests/fixtures/native_windows/strings.out').read_text(
            encoding='utf-8-sig')
        self.assertGreaterEqual(len(native.splitlines()), 375)
        prefix = ''.join(native.splitlines(keepends=True)[:375])
        self.assertEqual(prefix.splitlines()[-1], FINAL_MARKER)
        self.assertEqual(sha256(prefix.encode('utf-8')).hexdigest(),
                         '55b60f30e9e113797b02b9df024af84b33a91400dc565fdcb2ae72f8412204b6')
        self.assertNotIn(EMPTY_MARKER, prefix)

    def test_empty_payloads_are_bounded_and_recover_after_errors(self):
        nodes = parse(empty_source())
        calls = checkpoint_calls(empty_source())
        self.assertEqual(len(nodes), 11)  # Only ten dynamic probes and the sentinel.
        self.assertEqual(len(calls), 10)
        for node in calls:
            label, payload = (argument.value for argument in node.expression.arguments)
            self.assertLess(len(payload), 128, label)
            self.assertNotIn('\n', payload, label)
            self.assertNotRegex(payload, r'(?i)\b(?:Пока|While|Goto|Перейти)\b')
            parse('Результат = ' + payload + ';')
        output = []
        helpers = source().split('// Строковый конвейер', 1)[0]
        Interpreter(output=output.append).execute(helpers + '''
Процедура Показать(Знач Метка, Знач Данные)
    Сообщить(Метка + ": [" + Строка(Данные) + "]");
КонецПроцедуры
ПроверитьВыражениеПоиска("unknown", "UnimplementedSearchProbe()");
ПроверитьВыражениеПоиска("invalid", "StrFind(");
''' + empty_source() + '''
ПроверитьВыражениеПоиска("recovery", "StrFind(""abc"", ""b"")");
''')
        self.assertEqual(len(output), 14)
        self.assertEqual(output[:2], ['unknown: [error]', 'invalid: [error]'])
        self.assertEqual(output[-2:], [EMPTY_MARKER, 'recovery: [{"N",2}]'])


if __name__ == '__main__':
    unittest.main()

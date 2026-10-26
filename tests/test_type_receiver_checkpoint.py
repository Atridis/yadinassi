"""Compact receiver supplement confirmed by owner commit f28dcc51a6b631cb4a8a3526dfcdc57172efbfc6."""
from pathlib import Path
import hashlib
import unittest

from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse, parse_expression
from yadinassi.errors import BSLError
from yadinassi.values import BSLObject, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
HELPER = '// Дополнение нативной проверки: вызов через переменную.'
ORIGINAL = '// Нативный checkpoint описаний типов.'
BODY = '// Дополнение описаний типов: вызов через переменную.'
FINAL = 'types-extra.checkpoint.complete: [ok]'


def historical_source():
    from scripts.native_historical_replay import historical_values_source
    output = ROOT / 'tests/fixtures/native_windows/values.out'
    return historical_values_source(SOURCE.read_bytes(), output.read_bytes()).decode('utf-8')


def source():
    return historical_source()


def helpers():
    return HELPER + source().split(HELPER, 1)[1].split(ORIGINAL, 1)[0]


def expressions():
    result = {}
    for node in parse(source()):
        if (isinstance(node, ast.ExpressionStatement) and isinstance(node.expression, ast.Call)
                and isinstance(node.expression.callee, ast.Name)
                and node.expression.callee.name == 'НаблюдатьДополнениеТипов'):
            call = node.expression
            assert len(call.arguments) == 2
            assert all(isinstance(a, ast.Literal) and type(a.value) is str for a in call.arguments)
            label, expression = [a.value for a in call.arguments]
            assert label not in result
            result[label] = expression
    return result


class TypeReceiverCheckpointTests(unittest.TestCase):
    def test_compact_formatter_preserves_scalar_bytes_and_container_kinds(self):
        # Local formatter contract, never a newly manufactured native golden.
        from decimal import Decimal
        from yadinassi.serialization import value_to_string_internal
        from yadinassi.structures import BSLStructure
        from yadinassi.values import BSLArray, NULL
        vm = Interpreter()
        vm.execute(helpers())
        scalars = [None, NULL, False, Decimal(0), '0', '',
                   'quotes " and delimiters ;[]= with \\n and CR\rLF\nTAB\t Я😀']
        for value in scalars:
            vm.register_function('FormatterValue', lambda: value)
            actual = vm.execute('ПолеКомпактногоДополнения(FormatterValue())')
            expected = value_to_string_internal(value).replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n')
            self.assertEqual(actual, expected)
            self.assertNotIn('\r', actual)
            self.assertNotIn('\n', actual)
        representations = []
        for value in (BSLArray(), BSLStructure(), BSLStructure('Count', Decimal(0))):
            vm.register_function('FormatterValue', lambda: value)
            representations.append(vm.execute('ПоляКомпактногоДополнения(FormatterValue(), "value")'))
        self.assertEqual(len(set(representations)), 3)

        # Actual controls and their literal escape spellings must never collide.
        from yadinassi.serialization import value_from_string_internal
        pairs = ['\n', r'\n', '\r', r'\r', '\\', '"', ';[]=', '\t', r'\t', '\x00']
        encoded = []
        for value in pairs:
            vm.register_function('FormatterValue', lambda: value)
            text = vm.execute('ПолеКомпактногоДополнения(FormatterValue())')
            encoded.append(text)
            restored, position = [], 0
            escapes = {'\\': '\\', 'n': '\n', 'r': '\r', 't': '\t'}
            while position < len(text):
                if text[position] == '\\':
                    self.assertLess(position + 1, len(text))
                    self.assertIn(text[position + 1], escapes)
                    restored.append(escapes[text[position + 1]])
                    position += 2
                else:
                    restored.append(text[position])
                    position += 1
            self.assertEqual(value_from_string_internal(''.join(restored)), value)
        self.assertEqual(len(set(encoded)), len(pairs))

    def test_matrix_has_fourteen_receiver_replacements_and_four_syntax_controls(self):
        probes = expressions()
        self.assertEqual(len(probes), 23)
        self.assertEqual(len([x for x in probes if x.startswith('default.')]), 10)
        self.assertEqual(len([x for x in probes if x.startswith('contains.')]), 3)
        self.assertIn('properties.aliases', probes)
        self.assertEqual(len([x for x in probes if x.startswith('qualifiers.')]), 5)
        self.assertEqual(len([x for x in probes if x.startswith('syntax.')]), 4)
        for label, expression in probes.items():
            self.assertRegex(label, r'^[a-z0-9.-]+$')
            self.assertLess(len(expression), 300)
            self.assertNotRegex(expression, r'[\r\n]')
            self.assertNotRegex(expression, r'(?i)\b(?:Eval|Execute|Import|Goto|While|For)\b')
            if label in ('syntax.array-direct', 'syntax.array-parentheses',
                         'syntax.description-parentheses'):
                with self.assertRaises(BSLError):
                    parse_expression(expression)
            else:
                parse_expression(expression)
            if not label.startswith('syntax.'):
                self.assertNotIn(').', expression)
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_helpers_before_main_and_type_constructors_inside_guarded_expressions(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            else:
                started = True
        self.assertNotIn('New TypeDescription', helpers())
        self.assertNotIn('Новый ОписаниеТипов', helpers())
        for name in ('Описание.ContainsType', 'Описание.СодержитТип',
                     'Описание.AdjustValue()', 'Описание.ПривестиЗначение()',
                     'Массив.Count()'):
            self.assertIn(name, helpers())

    def test_owner_output_is_byte_preserved(self):
        # Only transport CRLF is normalized, as in the strict native comparator.
        data = (ROOT / 'tests/fixtures/native_windows/values.out').read_bytes().replace(b'\r\n', b'\n')
        marker = b'types.checkpoint.complete: [ok]\n'
        self.assertEqual(data.count(marker), 1)
        original = data.split(marker)[0] + marker
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '07f4380d7974632c74960dbb4343c5a3f30c774659f41fc63f7179d70aa0075d')
        self.assertEqual(len(original.splitlines()), 917)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         'bb50c5728bd570027aec834333da515ad11d45c32402c1242c824d0a5746465b')
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                         '016f30d6f3bdb1a814e86a70e3bcf424383a0d27')
        legacy = b'\n'.join(data.split(b'\n')[:784]) + b'\n'
        self.assertEqual(hashlib.sha256(legacy).hexdigest(),
                         'ca84b5219516ed4089d6e5c294d5223015013b756b951998a172728e1d39479e')
        self.assertEqual(len(data), 55991)
        self.assertEqual(len(data.splitlines()), 941)
        self.assertTrue(data.endswith((FINAL + '\n').encode()))
        labels = [line.decode().split(': [', 1)[0] for line in data.splitlines()
                  if line.startswith(b'types-extra.')]
        self.assertEqual(labels, ['types-extra.' + label for label in expressions()]
                         + ['types-extra.checkpoint.complete'])
        self.assertFalse((ROOT / 'tests/fixtures/native_windows/values.err').exists())

    def test_observer_recovers_after_each_error(self):
        output = []
        vm = Interpreter(output=output.append)
        vm.register_function('UnknownHost', lambda: object())
        vm.execute(helpers() + '''
НаблюдатьДополнениеТипов("missing", "NoSuchFunction()");
НаблюдатьДополнениеТипов("syntax", "@");
НаблюдатьДополнениеТипов("serialize", "UnknownHost()");
НаблюдатьДополнениеТипов("next", "КоличествоМассиваДополнения(New Array())");
''')
        self.assertEqual(output, ['types-extra.missing: [error]', 'types-extra.syntax: [error]',
                                 'types-extra.serialize: [serialize-error]',
                                 'types-extra.next: [value={"N",0}]'])

    def test_default_helper_really_calls_receiver_methods_without_arguments(self):
        seen = []
        class SyntheticDescription(BSLObject):
            def get_member(self, name):
                def default():
                    seen.append(name)
                    return 'synthetic'
                return HostFunction(name, default)
        vm = Interpreter()
        vm.register_function('SyntheticDescription', SyntheticDescription)
        vm.execute(helpers())
        result = vm.execute('УмолчаниеТипаДополнения(SyntheticDescription())')
        self.assertEqual(result.get('Value'), 'synthetic')
        self.assertEqual(result.get('Russian'), 'synthetic')
        self.assertEqual(seen, ['AdjustValue', 'ПривестиЗначение'])

    def test_full_program_reaches_native_marker_with_all_labels(self):
        output = []
        Interpreter(output=output.append).execute(source())
        tail = [line for line in output if line.startswith('types-extra.')]
        self.assertEqual(len(tail), 24)
        self.assertEqual(tail[-1], FINAL)
        self.assertEqual([line.split(': [', 1)[0] for line in tail[:-1]],
                         ['types-extra.' + label for label in expressions()])


if __name__ == '__main__':
    unittest.main()

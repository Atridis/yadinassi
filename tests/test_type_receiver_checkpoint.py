"""Compact receiver supplement, immutable old output, and pending native confirmation."""
from pathlib import Path
import hashlib
import unittest

from yadinassi import Interpreter, ast
from yadinassi.parser import parse, parse_expression
from yadinassi.errors import BSLError
from yadinassi.values import BSLObject, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
HELPER = '// Дополнение нативной проверки: вызов через переменную.'
ORIGINAL = '// Нативный checkpoint описаний типов.'
BODY = '// Дополнение описаний типов: вызов через переменную.'
FINAL = 'types-extra.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


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
        data = (ROOT / 'integrational_tests/output/values.out').read_bytes().replace(b'\r\n', b'\n')
        marker = b'types.checkpoint.complete: [ok]\n'
        self.assertEqual(data.count(marker), 1)
        original = data.split(marker)[0] + marker
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '0b80e880cde1ba4a9e189e3ed1cd36e2560f27efa374b0853a839d245e3608b2')
        self.assertEqual(len(original.splitlines()), 5182)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         'e87c380a2b83a4d411f41b48d006bf41d0dcc66dc3b19664cebaab9c22b821d4')
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                         '4ee5695345a6f50ffe78f35e47027c88c75a973f')
        self.assertEqual(len(data), 81485)
        self.assertEqual(len(data.splitlines()), 5736)
        self.assertTrue(data.endswith((FINAL + '\n').encode()))
        labels = [line.decode().split(': [', 1)[0] for line in data.splitlines()
                  if line.startswith(b'types-extra.')]
        self.assertEqual(labels, ['types-extra.' + label for label in expressions()]
                         + ['types-extra.checkpoint.complete'])
        self.assertFalse((ROOT / 'integrational_tests/output/values.err').exists())

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

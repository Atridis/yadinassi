"""Native-first table observations: source integrity, never invented goldens."""
from dataclasses import fields, is_dataclass
import hashlib
from pathlib import Path
import unittest

from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
START = '// Нативный checkpoint ТаблицыЗначений: без придуманных ответов.'
END = '// Конец помощников checkpoint ТаблицыЗначений.\n'
BODY = '// ТаблицаЗначений: фиксированные изолированные наблюдения.'
FINAL = 'table.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def parts():
    prefix, rest = source().split('\n\n' + START, 1)
    helpers, rest = rest.split(END, 1)
    old_tail, body = rest.split('\n' + BODY, 1)
    return prefix + old_tail, START + helpers, BODY + body


def walk(value):
    if is_dataclass(value):
        yield value
        for field in fields(value):
            yield from walk(getattr(value, field.name))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)


def calls():
    return [n.expression for n in parse(parts()[2])
            if isinstance(n, ast.ExpressionStatement)
            and isinstance(n.expression, ast.Call)
            and isinstance(n.expression.callee, ast.Name)
            and n.expression.callee.name == 'НаблюдатьТаблицы']


class ValueTableCheckpointTests(unittest.TestCase):
    def test_legacy_source_and_owner_output_are_untouched(self):
        old, _, _ = parts()
        # Transport-normalized source; no legacy procedure or statement changed.
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),
                         '97d7928e7c59828f916f88d4f31632e2c9bcd8f1ab57786f81ee18978246dfc1')
        output = ROOT / 'integrational_tests/output/collections.out'
        self.assertEqual(hashlib.sha256(output.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                         '06f0517acf577d357a2b52e6808da8d208b040025d505c143f08fc1a47f47f69')
        self.assertEqual(len(output.read_bytes().splitlines()), 1451)

    def test_fixed_bounded_unique_observations(self):
        observations = calls()
        self.assertEqual(len(observations), 142)
        labels = set()
        for call in observations:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(a, ast.Literal) and type(a.value) is str
                                for a in call.arguments))
            label, expression = [a.value for a in call.arguments]
            self.assertNotIn(label, labels)
            labels.add(label)
            self.assertRegex(label, r'^[a-z0-9.-]+$')
            self.assertLess(len(expression), 260)
            self.assertNotRegex(expression, r'[\r\n]')
            parse('Проверка = ' + expression + ';')
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_declarations_precede_body_and_new_types_are_only_eval_strings(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True
        for node in walk(parse(parts()[1])):
            if isinstance(node, ast.New):
                self.assertIn(node.name.casefold(), ('структура', 'массив', 'описаниетипов'))
        self.assertNotIn('Новый ТаблицаЗначений;', parts()[1])

    def test_every_fixed_read_expression_parses_and_uses_receivers(self):
        for call in calls():
            expression = call.arguments[1].value
            parsed = parse('Проверка = ' + expression + ';')
            for node in walk(parsed):
                if isinstance(node, ast.Call) and isinstance(node.callee, ast.Name):
                    if node.callee.name == 'ЧтениеТаблицыПробы':
                        parse('Проверка = ' + node.arguments[0].value + ';')
                if isinstance(node, ast.Attribute):
                    self.assertNotIsInstance(node.object, (ast.New, ast.Group))

    def test_four_types_codecs_and_readonly_boundaries_are_visible(self):
        labels = {c.arguments[0].value for c in calls()}
        for label in ('codec.empty', 'codec.table', 'codec.row', 'codec.column',
                      'codec.columns', 'links.codec-object-graph', 'links.codec-sharing',
                      'links.deleted-row', 'links.deleted-column', 'links.found-live',
                      'links.unload-sharing', 'mutate.column-readonly-type',
                      'mutate.columns-readonly', 'mutate.column-readonly-slot',
                      'mutate.row-readonly-slot', 'mutate.column-delete-final',
                      'typed.fixed-string', 'typed.date-only', 'typed.time-only',
                      'typed.qualified-overflow', 'mutate.untyped-mixed-total'):
            self.assertIn(label, labels)
        helpers = parts()[1]
        for name in ('ReadType', 'ReadWrite', 'ReadView', 'TypeWrite', 'TypeRead',
                     'Nested', 'RowOwner', 'Columns', 'Column', 'Row'):
            self.assertIn(name, helpers)
        self.assertIn('[snapshot-error]', helpers)

    def test_current_unsupported_runtime_finishes_with_explicit_errors(self):
        messages = []
        Interpreter(output=messages.append).execute(source())
        labels = ['table.' + c.arguments[0].value + ': [error]' for c in calls()]
        self.assertEqual(messages[-143:], labels + [FINAL])
        # These are unsupported-runtime diagnostics, never native answers.
        actual = '\n'.join(messages[:-143]) + '\n'
        expected = (ROOT / 'integrational_tests/output/collections.out').read_text(encoding='utf-8-sig')
        self.assertEqual(actual.replace('\r\n', '\n').replace('\r', '\n'), expected)

    def test_full_native_gate_rejects_missing_owner_tail(self):
        if __package__:
            from .test_native_outputs import NativeOutputTests
        else:
            from test_native_outputs import NativeOutputTests
        case = NativeOutputTests('test_native_outputs')
        with self.assertRaises(AssertionError) as caught:
            case.compare_script(SOURCE)
        self.assertIn('collections.bsl: вывод отличается', str(caught.exception))

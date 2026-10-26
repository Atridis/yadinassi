"""Native-first instrumentation; interpreter observations are not a 1C oracle."""
import hashlib
from pathlib import Path
import unittest

from scripts.native_historical_replay import (
    without_service_filled_probes, FIXED_STRING_PROBE_BLOCKS, historical_values_source, without_fixed_string_probes,
)
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse, parse_expression

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
PREVIOUS_SHA = '5fd00b472332044f4bae4c12973bcc66c074b27f7c98fe58b21b149088166fff'


class FixedStringCheckpointTests(unittest.TestCase):
    def source(self):
        return without_service_filled_probes(SOURCE.read_bytes().replace(b'\r\n', b'\n').decode('utf-8'))

    def test_exact_previous_source_and_all_previous_messages_are_preserved(self):
        current = self.source()
        previous = without_fixed_string_probes(current)
        self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(), PREVIOUS_SHA)
        old, new = [], []
        Interpreter(old.append).execute(previous)
        Interpreter(new.append).execute(current)
        self.assertEqual(len(old), 361)
        self.assertEqual(len(new), 377)
        self.assertEqual(new[:361], old)
        self.assertEqual(len(new[261:361]), 100)
        self.assertEqual(new[-1], 'types-extra.fixed-default.checkpoint.complete: [ok]')
        self.assertTrue(all(x.startswith('types-extra.fixed-default.') for x in new[361:]))
        self.assertTrue(all(all(ord(c) >= 32 for c in x) for x in new[361:]))
        historical_values_source(current.encode(),
                                 (ROOT / 'tests/fixtures/native_windows/values.out').read_bytes())

    def test_separate_arguments_and_qualifiers_are_pinned_in_a_bounded_matrix(self):
        expressions = {}
        started = False
        for node in parse(self.source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started)
            else:
                started = True
            if (isinstance(node, ast.ExpressionStatement)
                    and isinstance(node.expression, ast.Call)
                    and isinstance(node.expression.callee, ast.Name)
                    and node.expression.callee.name == 'НаблюдатьДополнениеТипов'):
                label, expr = [a.value for a in node.expression.arguments]
                if not label.startswith('fixed-default.'):
                    continue
                self.assertNotIn(label, expressions)
                parse_expression(expr)
                expressions[label] = expr
        self.assertEqual(len(expressions), 15)
        for label, length, mode in [('fixed1', 1, 'Fixed'), ('fixed4', 4, 'Fixed'),
                                    ('fixed0', 0, 'Fixed'), ('variable4', 4, 'Variable'),
                                    ('restored4', 4, 'Fixed')]:
            desc = f'New TypeDescription("String", , New StringQualifiers({length},AllowedLength.{mode}))'
            if label == 'restored4':
                desc = f'ValueFromStringInternal(ValueToStringInternal({desc}))'
            expected = {'omitted': f'УмолчаниеТипаДополнения({desc})',
                        'undefined': f'ПриведениеТипов({desc}, Undefined)',
                        'empty': f'ПриведениеТипов({desc}, "")'}
            for arg, expr in expected.items():
                self.assertEqual(expressions[f'fixed-default.{label}.{arg}'],
                                 f'ПроекцияУмолчанияСтроки({expr})')

    def test_projection_preserves_type_value_internal_and_visible_length(self):
        helpers = self.source().split('// Значение, тип и настоящий прямой/обратный кодек.', 1)[0]
        out = []
        vm = Interpreter(out.append)
        vm.execute(helpers)
        for expr in ('""', '"    "', 'Undefined', 'Null', '42', 'Char(10)'):
            vm.execute('НаблюдатьДополнениеТипов("projection", '
                       f'"ПроекцияУмолчанияСтроки(New Structure(""Value,Type"", {expr.replace(chr(34), chr(34)*2)}, TypeOf({expr.replace(chr(34), chr(34)*2)})))");')
        self.assertEqual(len(out), 6)
        self.assertTrue(all('[error]' not in x and '[serialize-error]' not in x for x in out))
        self.assertTrue(all('value.Type=' in x and 'value.Internal=' in x and 'value.Length=' in x for x in out))
        self.assertTrue(all(all(ord(c) >= 32 for c in x) for x in out))
        self.assertIn('value.Length={"N",4}', out[1])
        self.assertIn('value.Length={"U"}', out[2])

    def test_source_boundary_and_baseline_mutations_fail_closed(self):
        source = self.source()
        mutants = [source + '\n', source.replace('NULL', 'Null', 1)]
        for start, end in FIXED_STRING_PROBE_BLOCKS:
            mutants.extend([source.replace(start, '', 1), source + end])
        for changed in mutants:
            with self.subTest(changed=changed[-80:]), self.assertRaises(ValueError):
                without_fixed_string_probes(changed)

from scripts.native_historical_replay import without_uuid_probes
"""Source-only service-value observations: local execution is not native evidence."""
import hashlib
from pathlib import Path
import unittest

from scripts.native_historical_replay import (
    SERVICE_FILLED_PROBE_BLOCK, without_service_filled_probes, historical_values_source,
)
from yadinassi import Interpreter, ast
from yadinassi.parser import parse, parse_expression

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ('type.number', 'Type("Number")'), ('type.string', 'Type("String")'),
    ('round.down', 'RoundMode.Round15as10'), ('round.up', 'RoundMode.Round15as20'),
    ('round.namespace', 'RoundMode'), ('description.empty', 'New TypeDescription'),
    ('description.number', 'New TypeDescription("Number")'),
    ('description.string', 'New TypeDescription("String")'),
    ('number.default', 'New NumberQualifiers'),
    ('number.qualified', 'New NumberQualifiers(10,2,AllowedSign.Any)'),
    ('string.default', 'New StringQualifiers'),
    ('string.fixed4', 'New StringQualifiers(4,AllowedLength.Fixed)'),
)


class ServiceFilledCheckpointTests(unittest.TestCase):
    def source(self):
        return without_uuid_probes((ROOT / 'integrational_tests/tests/values.bsl').read_text(encoding='utf-8'))

    def test_exact_prior_source_and_every_prior_observation_are_preserved(self):
        source = self.source()
        previous = without_service_filled_probes(source)
        self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(),
                         'eaf36b0deed933ea1c3eabcfbde0be59f2f1d8bf6b07b5533f4df2e8cc967b45')
        old, new = [], []
        Interpreter(old.append).execute(previous)
        Interpreter(new.append).execute(source)
        self.assertEqual(len(old), 377)
        self.assertEqual(len(new), 402)
        self.assertEqual(new[:377], old)
        labels = [f'types-extra.service-filled.{label}.{lang}:'
                  for label, _ in CASES for lang in ('ru', 'en')]
        self.assertEqual([item.split(' ', 1)[0] for item in new[377:-1]], labels)
        self.assertEqual(new[-1], 'types-extra.service-filled.checkpoint.complete: [ok]')
        for item in new[377:-1]:
            self.assertIn(item.split(': ', 1)[1], ('[error]', '[value={"B",0}]', '[value={"B",1}]'))
        historical_values_source(source.encode(),
                                 (ROOT / 'tests/fixtures/native_windows/values.out').read_bytes())

    def test_exact_finite_matrix_and_independent_global_aliases(self):
        expressions = {}
        for node in parse(self.source()):
            if (isinstance(node, ast.ExpressionStatement)
                    and isinstance(node.expression, ast.Call)
                    and isinstance(node.expression.callee, ast.Name)
                    and node.expression.callee.name == 'НаблюдатьДополнениеТипов'):
                label, expr = [a.value for a in node.expression.arguments]
                if label.startswith('service-filled.'):
                    self.assertNotIn(label, expressions)
                    parse_expression(expr)
                    expressions[label] = expr
        expected = {f'service-filled.{label}.{lang}': f'{alias}({expr})'
                    for label, expr in CASES
                    for lang, alias in [('ru', 'ЗначениеЗаполнено'), ('en', 'ValueIsFilled')]}
        self.assertEqual(expressions, expected)
        # Establish locally that constructors/member access themselves are supported.
        # This does not predict the native result of the enclosing global call.
        vm = Interpreter(lambda _: None)
        for _, expr in CASES:
            vm.execute(expr)

    def test_restoration_is_exact_and_fails_closed(self):
        source = self.source()
        mutants = [source + '\n', source.replace('NULL', 'Null', 1)]
        for marker in SERVICE_FILLED_PROBE_BLOCK:
            mutants.extend([source.replace(marker, '', 1), source + marker])
        for mutant in mutants:
            with self.subTest(mutant=mutant[-80:]), self.assertRaises(ValueError):
                without_service_filled_probes(mutant)

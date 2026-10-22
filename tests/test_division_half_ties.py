"""Native PR83 ties: bounded observations, not universal precision evidence."""
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.values import divide
from test_division_tie_checkpoint import probes
ROOT = Path(__file__).resolve().parents[1]


class NativeDivisionHalfTieTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / 'tests/fixtures/division_half_ties_linux.json').read_text(encoding='utf-8'))

    def test_full_live_source_matches_all_71_native_suffix_records(self):
        source = (ROOT / 'integrational_tests/tests/numbers.bsl').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(source).hexdigest(), self.fixture['source_sha256'])
        self.assertEqual(self.fixture['native_run'], 39779498177)
        self.assertEqual(self.fixture['contexts'], ['server', 'managed-client'])
        output = []
        Interpreter(output.append).execute(source.decode())
        previous = (ROOT / 'tests/fixtures/native_windows/numbers.out').read_text(encoding='utf-8-sig').splitlines()
        self.assertEqual(len(output), 421)
        self.assertEqual(output[:350], previous)
        self.assertEqual(output[350:], self.fixture['records'])
        self.assertEqual(hashlib.sha256(('\n'.join(output) + '\n').encode()).hexdigest(), self.fixture['output_sha256'])

    def test_each_measured_expression_and_adjacent_comparison_is_exact(self):
        vm = Interpreter()
        for (label, expression), record in zip(probes().items(), self.fixture['records']):
            with self.subTest(label=label):
                value = vm.execute(expression)
                self.assertIs(type(value), bool if '.lower' in label or '.upper' in label else Decimal)
                payload = vm.execute('ValueToStringInternal(' + expression + ')')
                self.assertEqual(record, 'math.' + label + ': [' + payload + ']')

    def test_measured_direct_halves_use_unsigned_magnitude_increment(self):
        cases = probes()
        count = 0
        for label, expression in cases.items():
            if label + '.lower' not in cases or '.pow.' in label:
                continue
            a, b = map(Decimal, expression.split(' / '))
            lower = Fraction(cases[label + '.lower'].split(' = ')[1])
            upper = Fraction(cases[label + '.upper'].split(' = ')[1])
            exact = Fraction(a) / Fraction(b)
            self.assertEqual(exact, (lower + upper) / 2)
            self.assertEqual(Fraction(divide(a, b)), upper if exact > 0 else lower)
            count += 1
        self.assertEqual(count, 16)

    def test_half_result_does_not_depend_on_host_decimal_context(self):
        with localcontext() as context:
            context.prec = 1
            context.Emax, context.Emin = 2, -2
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            before = context.copy()
            for a, b, expected in (
                ('1', '268435456', '0.000000003725290298461914063'),
                ('3', '-268435456', '-0.000000011175870895385742188'),
                ('-1', '-0.268435456', '3.725290298461914063'),
                ('-3', '268435456000000000', '-0.000000000000000011175870895385742188'),
            ):
                self.assertEqual(divide(Decimal(a), Decimal(b)), Decimal(expected))
            self.assertEqual(context.flags, before.flags)
            self.assertEqual(context.traps, before.traps)


if __name__ == '__main__':
    unittest.main()

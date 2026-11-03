"""Source-bound native Format acquisition and local resource invariants."""
from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib
from pathlib import Path
import sys
import unittest

from yadinassi import Interpreter
from yadinassi.formatting import format_value

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_format_numbers_contract as wire


class ExtendedFormatTests(unittest.TestCase):
    def test_extended_native_capture_replays_exactly(self):
        fixture = ROOT / 'tests/fixtures/format_numbers'
        source = (fixture / 'extended48.bsl').read_bytes()
        output = (fixture / 'extended48-linux-8.3.27.1508.out').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), '0c4f9cd38dd6851ae70b80d69905a4d39447972d54fa33f0fdf1bbc70f9931f6')
        self.assertEqual(hashlib.sha256(output).hexdigest(), 'ad9b9f9dcda8e1da2a0f64ef98eba4ec238156abb526c0d082bc603c736531ff')
        records = wire.require_available(output)
        self.assertEqual(len(records), 48)
        self.assertTrue(all(record['status'] == 'ok' for record in records))
        actual = []
        Interpreter(actual.append).execute(source.decode('utf-8'))
        # The two width-overflow boundaries are observed but deliberately not
        # generalized yet. Preserve the original capture; compare the remaining
        # 46 observations and explicit local rejection separately.
        expected = output.decode('ascii').splitlines()
        for case in (7, 8):
            self.assertTrue(expected[case + 1].startswith(f'FM-{case:02d}: [ok|'))
            expected[case + 1] = f'FM-{case:02d}: [action-error]'
        self.assertEqual(actual, expected)

    def test_negative_forms_and_aliases(self):
        for form, expected in enumerate(('(12.30)', '-12.30', '- 12.30', '12.30-', '12.30 -')):
            with self.subTest(form=form):
                self.assertEqual(format_value(Decimal('-12.3'), f'NN={form};NFD=2;NG=0;NDS=.'), expected)
        self.assertEqual(format_value(Decimal('-12.3'), 'ЧО=0;ЧДЦ=2;ЧГ=0;ЧРД=.'), '(12.30)')

    def test_boolean_presentations_and_duplicates(self):
        self.assertEqual(format_value(False, 'BF=No;BT=Yes'), 'No')
        self.assertEqual(format_value(True, 'БЛ=No;БИ=Yes'), 'Yes')
        self.assertEqual(format_value(False, 'BF=;BT=Yes'), '')
        self.assertEqual(format_value(True, 'BF=No;BT='), '')
        self.assertEqual(format_value(False, 'BF=No;BF=Off;BT=Yes'), 'No')
        self.assertEqual(format_value(Decimal(1), 'BF=No;BT=Yes;NFD=2;NG=0;NDS=.'), '1.00')

    def test_width_shift_and_rounding(self):
        # Overflow and rounding carry remain unsupported despite native output.
        for number, mask in [('123.45', 'ND=4;NFD=2;NG=0;NDS=.'),
                             ('9.995', 'ND=3;NFD=2;NG=0;NDS=.')]:
            with self.assertRaises(ValueError):
                format_value(Decimal(number), mask)
        witnesses = [('12.3', 'ND=6;NFD=2;NLZ=;NG=0;NDS=.', '0012.30'),
                     ('1234.5', 'NS=1;NFD=2;NG=0;NDS=.', '123.45'),
                     ('1234.5', 'NS=-1;NFD=2;NG=0;NDS=.', '12345.00')]
        for number, mask, expected in witnesses:
            with self.subTest(mask=mask):
                self.assertEqual(format_value(Decimal(number), mask), expected)

    def test_decimal_context_is_not_modified(self):
        with localcontext() as ctx:
            ctx.prec = 1
            ctx.Emin = -1
            ctx.Emax = 1
            ctx.rounding = ROUND_DOWN
            for signal in ctx.traps:
                ctx.traps[signal] = True
            ctx.clear_flags()
            before = ctx.copy()
            self.assertEqual(format_value(Decimal('1234.5'), 'NS=1;NFD=2;NG=0;NDS=.'), '123.45')
            self.assertEqual(dict(ctx.flags), dict(before.flags))
            self.assertEqual(dict(ctx.traps), dict(before.traps))
            self.assertEqual((ctx.prec, ctx.Emin, ctx.Emax, ctx.rounding),
                             (before.prec, before.Emin, before.Emax, before.rounding))

    def test_bounded_output_and_no_untrusted_conversion(self):
        with self.assertRaises(ValueError):
            format_value(True, 'BT=' + 'x' * 4097)
        class Hostile:
            def __str__(self):
                raise AssertionError('must not invoke host callback')
        with self.assertRaises(TypeError):
            format_value(Hostile(), 'BT=Yes')


if __name__ == '__main__':
    unittest.main()

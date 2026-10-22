"""Deterministic Exp, including certified subnormal rounding and limits."""

from decimal import Context, Decimal, DefaultContext, ROUND_DOWN, localcontext
import importlib
import math
from pathlib import Path
import unittest

from scripts.native_historical_replay import historical_numbers_source
from unittest.mock import patch

from yadinassi.binary_exp import binary_exp
from yadinassi.math_conversion import UnsupportedConversionRange, decimal_to_binary64


MODULE = importlib.import_module('yadinassi.binary_exp')


class BinaryExpTests(unittest.TestCase):
    def test_native_observations(self):
        cases = {
            '0': '1',
            '1': '2.71828182845905',
            '-744': '9.88131291682493e-324',
            '-745': '4.94065645841247e-324',
            '-746': '0',
            '709.7827128933839': '1.79769313486207e+308',
            '709.78271289338396': '1.79769313486207e+308',
            '709.78271289338397': '1.79769313486207e+308',
            '709.782712893383970000000001': '1.79769313486207e+308',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                result = binary_exp(decimal_to_binary64(Decimal(text)))
                self.assertEqual(format(result, '.15g'), expected)
        self.assertEqual(binary_exp(decimal_to_binary64(Decimal('709.78271289338398'))),
                         math.inf)

    def test_binary64_zero_and_first_subnormal_boundary(self):
        # The two adjacent input doubles straddle log(2**-1075).
        lower = float.fromhex('-0x1.74910d52d3052p+9')
        upper = math.nextafter(lower, math.inf)
        self.assertEqual(binary_exp(lower).hex(), '0x0.0p+0')
        self.assertEqual(binary_exp(upper).hex(), '0x0.0000000000001p-1022')
        self.assertEqual(binary_exp(-745.0).hex(), '0x0.0000000000001p-1022')
        self.assertEqual(binary_exp(-744.0).hex(), '0x0.0000000000002p-1022')

    def test_subnormal_to_normal_boundary(self):
        # These adjacent inputs straddle log(the least normal binary64).
        upper = float.fromhex('-0x1.6232bdd7abcd2p+9')
        lower = math.nextafter(upper, -math.inf)
        normal_minimum = float.fromhex('0x1.0000000000000p-1022')
        self.assertLess(binary_exp(lower), normal_minimum)
        self.assertGreater(binary_exp(upper), normal_minimum)

    def test_finite_to_overflow_boundary(self):
        last_input = float.fromhex('0x1.62e42fefa39efp+9')
        overflow_input = math.nextafter(last_input, math.inf)
        self.assertTrue(math.isfinite(binary_exp(last_input)))
        self.assertEqual(binary_exp(overflow_input), math.inf)
        self.assertEqual(binary_exp(710.0), math.inf)

    def test_resource_bounds_skip_decimal_exp(self):
        with patch.object(MODULE, 'Context', side_effect=AssertionError('unexpected exp')):
            for value in (-1e308, math.nextafter(-746.0, -math.inf)):
                self.assertEqual(binary_exp(value), 0.0)
            for value in (1e308, math.nextafter(710.0, math.inf)):
                self.assertEqual(binary_exp(value), math.inf)

    def test_host_libm_flush_or_error_is_irrelevant(self):
        for replacement in ({'return_value': 0.0}, {'side_effect': OverflowError}):
            with self.subTest(replacement=replacement), patch('math.exp', **replacement) as host:
                self.assertEqual(binary_exp(-745.0).hex(), '0x0.0000000000001p-1022')
                self.assertEqual(binary_exp(-744.0).hex(), '0x0.0000000000002p-1022')
                self.assertEqual(binary_exp(1.0), math.e)
                host.assert_not_called()

    def test_registered_wrapper_ignores_flushing_host_exp(self):
        from yadinassi import Interpreter

        output = []
        with patch('math.exp', return_value=0.0) as host:
            Interpreter(output=output.append).execute('''
Message(ValueToStringInternal(Exp(-745)));
Message(ValueToStringInternal(Exp(-744)));
Message(ValueToStringInternal(Exp(-746)));
Message(ValueToStringInternal(Exp(1)));
Try Exp(709.78271289338398); Except Message("overflow"); EndTry;
''')
        self.assertEqual(len(output), 5)
        self.assertEqual(Decimal(output[0][5:-1]), Decimal('4.94065645841247e-324'))
        self.assertEqual(Decimal(output[1][5:-1]), Decimal('9.88131291682493e-324'))
        self.assertEqual(output[2:], ['{"N",0}', '{"N",2.71828182845905}', 'overflow'])
        host.assert_not_called()

    def test_complete_native_scenario_with_host_exp_disabled(self):
        from yadinassi import Interpreter
        root = Path(__file__).resolve().parents[1] / 'integrational_tests'
        expected = (root.parent / 'tests/fixtures/native_windows/numbers.out').read_text(encoding='utf-8-sig').splitlines()
        source = historical_numbers_source((root / 'tests/numbers.bsl').read_bytes(),
            (root.parent / 'tests/fixtures/native_windows/numbers.out').read_bytes()).decode('utf-8-sig')
        for replacement in ({'return_value': 0.0}, {'side_effect': OverflowError}):
            with self.subTest(replacement=replacement), patch('math.exp', **replacement) as host:
                output = []
                Interpreter(output=output.append).execute(source)
                self.assertEqual(output, expected)
                host.assert_not_called()

    def test_ambient_and_default_contexts_do_not_change_results(self):
        original_default = DefaultContext.copy()
        try:
            DefaultContext.prec = 2
            DefaultContext.rounding = ROUND_DOWN
            DefaultContext.Emin = -1
            DefaultContext.Emax = 1
            DefaultContext.capitals = 0
            DefaultContext.clamp = 1
            for signal in DefaultContext.traps:
                DefaultContext.traps[signal] = True
                DefaultContext.flags[signal] = True
            with localcontext() as ambient:
                ambient.prec = 2
                ambient.rounding = ROUND_DOWN
                ambient.Emin = -1
                ambient.Emax = 1
                for signal in ambient.traps:
                    ambient.traps[signal] = True
                ambient.clear_flags()
                with patch.object(MODULE, 'Context', wraps=Context) as constructor:
                    self.assertEqual(binary_exp(-745.0).hex(), '0x0.0000000000001p-1022')
                self.assertFalse(any(ambient.flags.values()))
                self.assertEqual(constructor.call_count, 1)
                self.assertEqual(constructor.call_args.kwargs['prec'], 80)
                self.assertEqual(constructor.call_args.kwargs['traps'], [])
                self.assertEqual(constructor.call_args.kwargs['flags'], [])
                self.assertTrue(all(DefaultContext.flags.values()))
        finally:
            for name in ('prec', 'rounding', 'Emin', 'Emax', 'capitals', 'clamp'):
                setattr(DefaultContext, name, getattr(original_default, name))
            DefaultContext.traps.update(original_default.traps)
            DefaultContext.flags.update(original_default.flags)

    def test_precision_is_increased_only_if_binary_rounding_is_uncertain(self):
        def first_imprecise(**kwargs):
            if kwargs['prec'] == 80:
                kwargs['prec'] = 1
            return Context(**kwargs)

        with patch.object(MODULE, 'Context', side_effect=first_imprecise) as constructor:
            self.assertEqual(binary_exp(1.0), math.e)
        self.assertEqual([call.kwargs['prec'] for call in constructor.call_args_list], [80, 160])

    def test_unresolved_rounding_is_explicitly_unsupported(self):
        def imprecise(**kwargs):
            kwargs['prec'] = 1
            return Context(**kwargs)

        with patch.object(MODULE, 'Context', side_effect=imprecise) as constructor:
            with self.assertRaisesRegex(UnsupportedConversionRange, '320'):
                binary_exp(1.0)
        self.assertEqual([call.kwargs['prec'] for call in constructor.call_args_list],
                         [80, 160, 320])

    def test_zero_sign_and_small_arguments(self):
        for value in (0.0, -0.0, 1e-300, -1e-300):
            with self.subTest(value=value):
                self.assertEqual(binary_exp(value), 1.0)

    def test_nonfinite_and_nonfloat_inputs_rejected(self):
        for value in (math.nan, math.inf, -math.inf, 1, True, '1', Decimal(1), None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    binary_exp(value)


if __name__ == '__main__':
    unittest.main()

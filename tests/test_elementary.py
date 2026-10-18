"""Native math evidence plus explicitly separate general behavior checks."""
from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
from pathlib import Path
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi import elementary


class ElementaryTests(unittest.TestCase):
    def test_complete_owner_numeric_output(self):
        root = Path(__file__).resolve().parents[1] / 'integrational_tests'
        actual = []
        Interpreter(output=actual.append).execute(
            (root / 'tests/numbers.bsl').read_text(encoding='utf-8-sig'))
        self.assertEqual(actual, (root / 'output/numbers.out').read_text(
            encoding='utf-8-sig').splitlines())

    def test_all_names_are_case_insensitive(self):
        vm = Interpreter()
        for name, argument in [('Sqrt','4'), ('Log','1'), ('Log10','100'),
                               ('Exp','0'), ('Sin','0'), ('Cos','0'),
                               ('Tan','0'), ('ASin','0'), ('ACos','1'),
                               ('ATan','0'), ('Pow','2, 3')]:
            with self.subTest(name=name):
                self.assertEqual(vm.execute(f'{name}({argument})'),
                                 vm.execute(f'{name.swapcase()}({argument})'))

    def test_exact_decimal_domain_before_conversion(self):
        vm = Interpreter()
        expressions = ('Sqrt(-0.0000000000000001)', 'Log(0)', 'Log(-1)',
                       'Log10(0)', 'ASin(1.0000000000000001)',
                       'ACos(-1.0000000000000001)', 'Pow(-2, 3.0000000000000001)',
                       'Pow(0, -0.5)', 'Exp(710)', 'Pow(10, 309.5)')
        for expression in expressions:
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute(expression)

    def test_arity_conversion_and_invalid_values(self):
        vm = Interpreter()
        self.assertEqual(vm.execute('Sqrt("4")'), Decimal(2))
        self.assertEqual(vm.execute('Sin(True)'), Decimal('0.841470984807897'))
        for name, function, _ in elementary.BUILTINS:
            for value in (None, 'invalid', Decimal('NaN'), Decimal('Infinity')):
                args = (value, Decimal('0.5')) if name == 'Pow' else (value,)
                with self.subTest(name=name, value=value), self.assertRaises((ValueError, TypeError, ArithmeticError)):
                    function(*args)
            for expression in (f'{name}()', f'{name}(1, 2, 3)'):
                with self.subTest(expression=expression), self.assertRaises(BSLError):
                    vm.execute(expression)

    def test_host_decimal_context_does_not_affect_helpers(self):
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.Emax = 9
            context.Emin = -9
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(elementary.sqrt(Decimal(2)), Decimal('1.4142135623731'))
            self.assertEqual(elementary.exp(Decimal(-745)), Decimal('4.94065645841247e-324'))
            self.assertEqual(elementary.tan(Decimal('1.5707963267948968')),
                             Decimal('-2611942160735620'))
            self.assertEqual(elementary.power(Decimal('1.1'), Decimal(20)),
                             Decimal('6.72749994932560009201'))
            self.assertFalse(any(context.flags.values()))

    def test_native_precision_regressions(self):
        self.assertEqual(elementary.exp(Decimal('709.78271289338397')),
                         Decimal('1.79769313486207e308'))
        self.assertEqual(elementary.exp(Decimal('709.782712893383970000000001')),
                         Decimal('1.79769313486207e308'))
        with self.assertRaises((ValueError, OverflowError)):
            elementary.exp(Decimal('709.78271289338398'))
        self.assertEqual(elementary.cos(Decimal('1.5707963267948968')),
                         Decimal('-3.82856869892695e-16'))
        self.assertEqual(elementary.tan(Decimal('1.5707963267948967')),
                         Decimal('16331239353195400'))
        self.assertEqual(elementary.exp(Decimal(-746)), Decimal(0))

    def test_unverified_conversion_domain_edge_is_explicit(self):
        # Local model limit, not a native expected value or a reason to clamp.
        from yadinassi.math_conversion import UnsupportedConversionRange
        for value in (Decimal('0.' + '9' * 37), Decimal('-0.' + '9' * 37)):
            for function in (elementary.asin, elementary.acos):
                with self.subTest(value=value, function=function.__name__):
                    with self.assertRaises(UnsupportedConversionRange):
                        function(value)

    def test_zero_sign_and_fractional_power(self):
        self.assertEqual(elementary.power(Decimal(9), Decimal('0.5')), Decimal(3))
        self.assertEqual(elementary.power(Decimal(0), Decimal('0.5')), Decimal(0))
        for function in (elementary.sqrt, elementary.sin, elementary.tan,
                         elementary.asin, elementary.atan):
            result = function(Decimal('-0'))
            self.assertEqual(result.as_tuple().sign, 0)


if __name__ == '__main__':
    unittest.main()

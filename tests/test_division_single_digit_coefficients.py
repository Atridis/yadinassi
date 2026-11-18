"""One-digit coefficient extraction preserves the bounded division model."""
from decimal import Decimal, localcontext
from fractions import Fraction
import random
import unittest
from yadinassi.values import divide
from test_division import fraction_oracle, model_scale

class SingleDigitCoefficientTests(unittest.TestCase):
    def test_all_digit_pairs_scaled_signed_and_padded(self):
        for a in range(1,10):
            for b in range(1,10):
                for ae,be in ((0,0),(-19,10),(27,-28)):
                    for sign in (0,1):
                        left=Decimal((sign,(a,0,0),ae-2));right=Decimal((1-sign,(b,0),be-1))
                        actual=divide(left,right)
                        self.assertEqual(Fraction(actual),fraction_oracle(left,right))
                        self.assertEqual(actual.as_tuple().exponent,-model_scale(left,right))

    def test_mixed_and_extreme_precision(self):
        rng=random.Random(184337)
        for _ in range(400):
            small=Decimal((rng.randrange(2),(rng.randrange(1,10),),rng.randrange(-120,120)))
            large=Decimal((rng.randrange(2),tuple([rng.randrange(1,10)]+[rng.randrange(10) for _ in range(45)]),rng.randrange(-120,120)))
            for left,right in ((small,large),(large,small)):
                self.assertEqual(Fraction(divide(left,right)),fraction_oracle(left,right))
        for left,right in ((Decimal('1e-1000'),Decimal(3)),(Decimal('1e1000'),Decimal(7)),(Decimal('123456789'*100),Decimal(9))):
            self.assertEqual(Fraction(divide(left,right)),fraction_oracle(left,right))

    def test_context_zero_and_limits(self):
        cases=[(Decimal('1e-19'),Decimal('-3e10')),(Decimal(7),Decimal('9e-28'))]
        expected=[divide(a,b).as_tuple() for a,b in cases]
        with localcontext() as ctx:
            ctx.prec=1;ctx.Emin=-2;ctx.Emax=2
            for signal in ctx.traps:ctx.traps[signal]=True
            ctx.clear_flags()
            self.assertEqual([divide(a,b).as_tuple() for a,b in cases],expected)
            self.assertEqual(divide(Decimal('-0'),Decimal(1)).as_tuple(),Decimal(0).as_tuple())
            self.assertFalse(any(ctx.flags.values()))
            for a,b in ((Decimal('1e5000'),Decimal(1)),(Decimal(1),Decimal('1e-5000'))):
                with self.assertRaisesRegex(ValueError,'предел ресурсов'):divide(a,b)
            with self.assertRaisesRegex(ValueError,'Деление на ноль'):divide(Decimal(1),Decimal('-0'))

    def test_decimal_subclasses_keep_validated_decimal_coefficient_extraction(self):
        events=[]
        class Digit(int):
            def __mul__(self, other):
                events.append('multiply');raise AssertionError('digit hook')
        class HostDecimal(Decimal):
            def as_tuple(self):return (0,(Digit(1),),0)
        self.assertEqual(divide(HostDecimal(1),Decimal(3)),Decimal('0.'+'3'*27))
        self.assertEqual(divide(Decimal(3),HostDecimal(1)),Decimal(3))
        self.assertEqual(events,[])
        class InvalidDecimal(Decimal):
            def as_tuple(self):return (0,(12,),0)
        for a,b in ((InvalidDecimal(1),Decimal(3)),(Decimal(3),InvalidDecimal(1))):
            with self.assertRaises(ValueError):divide(a,b)

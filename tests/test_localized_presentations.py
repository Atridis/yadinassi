"""Real source-bound native captures and explicit bounded local policies."""
from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib
import os
import subprocess
import sys
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.dates import date, BSLDate
from yadinassi.number_in_words import number_in_words
from yadinassi.period_presentation import period_presentation

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/localized_presentation'


class LocalizedPresentationTests(unittest.TestCase):
    def _replay(self, name, source_hash, output_hash, count):
        source = (FIXTURE / (name + '.bsl')).read_bytes()
        expected = (FIXTURE / (name + '.out')).read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), source_hash)
        self.assertEqual(hashlib.sha256(expected).hexdigest(), output_hash)
        self.assertEqual(len(expected.splitlines()), count + 2)
        output = []
        Interpreter(output.append).execute(source.decode('utf-8'))
        self.assertEqual(('\n'.join(output) + '\n').encode('ascii'), expected)

    def test_number_in_words_exact_native_capture(self):
        self._replay('number-in-words', '433a8ee21a7fb9d33d981556c1d90ec36e0af9a81a911e650c75a4d7ad2bb73f',
                     '443c903ccea6670936ed3f83c1b58c7bb5012e38e8ea13a9157636a5bb84bb98', 29)

    def test_period_presentation_exact_native_capture(self):
        self._replay('period-presentation', '15d1986a4e9c08d2b0e76fd09f3ed6b6d4a8f0a91364119e1edcb6673ddb3e57',
                     'e2c9d78f8a192528ac16160dcfed88e51e72a556f3bb47f66bbb52b6001a90bd', 28)

    def test_russian_inflections_generalize_across_hundreds(self):
        subject = 'рубль, рубля, рублей, м'
        for value, noun in [(101, 'рубль'), (102, 'рубля'), (105, 'рублей'), (111, 'рублей'),
                            (121, 'рубль'), (122, 'рубля'), (125, 'рублей')]:
            with self.subTest(value=value):
                self.assertTrue(number_in_words(Decimal(value), 'L=ru', subject).endswith(' ' + noun + ' 00 '))

    def test_english_composed_hundreds_and_subject(self):
        self.assertEqual(number_in_words(Decimal('1457.25'), 'L=en_US', 'dollar, dollars, cent, cents, 2'),
                         'One thousand four hundred fifty seven dollars 25 cents')
        self.assertEqual(number_in_words(Decimal('1.01'), 'L=en_US', 'dollar, dollars, cent, cents, 2'),
                         'One dollar 01 cent')

    def test_number_context_preserved(self):
        with localcontext() as ctx:
            ctx.prec = 1; ctx.Emin = -1; ctx.Emax = 1; ctx.rounding = ROUND_DOWN
            for signal in ctx.traps: ctx.traps[signal] = True
            ctx.clear_flags(); before = ctx.copy()
            self.assertEqual(number_in_words(Decimal('2.25'), 'L=ru', 'рубль, рубля, рублей, м'), 'Два рубля 25 ')
            self.assertEqual(dict(ctx.flags), dict(before.flags)); self.assertEqual(dict(ctx.traps), dict(before.traps))
            self.assertEqual((ctx.prec, ctx.Emin, ctx.Emax, ctx.rounding), (before.prec, before.Emin, before.Emax, before.rounding))

    def test_number_bounds_and_unsupported_formats_fail_closed(self):
        for value in (Decimal('NaN'), Decimal('Infinity'), Decimal('1E100000'), Decimal('1.234'), Decimal('9' * 10000)):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                number_in_words(value)
        for spec in ('L=de', 'XX=1', 'ДП=other', 'L=ru;Л=en', 'ДП=Истина;ДП=Ложь', 'L=' + 'x' * 4097):
            with self.subTest(spec=spec[:20]), self.assertRaises(ValueError):
                number_in_words(Decimal(1), spec)
        class Hostile:
            def __str__(self): raise AssertionError('host callback must not execute')
        with self.assertRaises(TypeError): number_in_words(Hostile())

    def test_period_calendar_classification(self):
        self.assertEqual(period_presentation(date('20270401000000'), date('20270630235959')), '2 квартал 2027 г.')
        self.assertEqual(period_presentation(date('20270101000000'), date('20270630235959'), 'ФП=Истина'), '1 полугодие 2027 г.')
        self.assertEqual(period_presentation(date('20270101000000'), date('20270131235959'), 'L=en_US'), 'January 2027')

    def test_cli_executes_both_public_apis(self):
        source = ('Message(NumberInWords(1, "L=en_US", "dollar, dollars, cent, cents, 2"));\n'
                  "Message(PeriodPresentation('20260101000000', '20260131235959', \"L=en_US\"));")
        result = subprocess.run([sys.executable, '-m', 'yadinassi', '-c', source], cwd=ROOT,
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'One dollar 00 cents\nJanuary 2026\n')
        self.assertEqual(result.stderr, '')

    def test_period_boundaries_and_unknown_values(self):
        self.assertEqual(period_presentation(BSLDate(0), BSLDate(0)), '')
        with self.assertRaises(ValueError): period_presentation(date('20270201000000'), date('20270101235959'))
        with self.assertRaises(ValueError): period_presentation(date('20270101000000'), date('20270102235959'), 'L=de')
        with self.assertRaises(ValueError): period_presentation(date('20270701000000'), date('20271231235959'), 'ФП=Истина')
        with self.assertRaises(ValueError): period_presentation(BSLDate(0), date('20270101235959'), 'L=en_US')
        with self.assertRaises(TypeError): period_presentation('20270101', date('20270102235959'))
        with self.assertRaises(ValueError): period_presentation(BSLDate(1), date('20270102235959'))

if __name__ == '__main__':
    unittest.main()

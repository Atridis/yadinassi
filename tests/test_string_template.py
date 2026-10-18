"""Documented substitution and separately labelled unprobed edge contracts."""

from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.strings import template
from yadinassi.values import BSLArray


class StringTemplateTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_bilingual_case_insensitive_names(self):
        for name in ('СтрШаблон', 'StrTemplate', 'сТрШаБлОн', 'sTrTeMpLaTe'):
            self.assertEqual(self.vm.execute(f'{name}("Привет, %1!", "мир")'), 'Привет, мир!')
            self.assertTrue(self.vm.execute(f'(TypeOf({name}("")) = Type("String"))'))

    def test_official_example(self):
        self.assertEqual(template('Ошибка в данных в строке %1 (требуется тип %2)',
                                  Decimal(2), 'Дата'),
                         'Ошибка в данных в строке 2 (требуется тип Дата)')

    def test_empty_literal_and_escaped_percent(self):
        for text, expected in [('', ''), ('literal', 'literal'), ('%%', '%'),
                               ('%%1 %%10 %%(1)', '%1 %10 %(1)'),
                               ('%%%%', '%%'), ('100%% готово', '100% готово')]:
            self.assertEqual(template(text), expected)

    def test_repeated_reordered_and_sparse_numbering(self):
        # Highest referenced number determines arity, not occurrence count.
        self.assertEqual(template('%2/%1/%2', 'one', 'two'), 'two/one/two')
        self.assertEqual(template('%3', 'unused', 'unused', 'three'), 'three')

    def test_tenth_parameter_and_digit_disambiguation(self):
        values = tuple(str(i) for i in range(1, 11))
        self.assertEqual(template('%10 %(10)0 %1', *values), '10 100 1')
        self.assertEqual(template('%(1)1cv8c.exe', '/bin/'), '/bin/1cv8c.exe')
        self.assertEqual(template('%(1)0', 'x'), 'x0')
        self.assertEqual(template('%%%1/%%%%%1', 'x'), '%x/%%x')

    def test_undefined_is_empty(self):
        self.assertEqual(template('[%1]', None), '[]')
        self.assertEqual(self.vm.execute('StrTemplate("[%1][%2]", Undefined, "x")'), '[][x]')

    def test_substitutions_are_not_recursively_interpreted(self):
        self.assertEqual(template('%1 %2', '%2', '%1%%%(10)'), '%2 %1%%%(10)')

    def test_shared_presentations_are_not_new_native_evidence(self):
        self.assertEqual(template('%1|%2|%3|%4', Decimal('1234.5'), True, False, BSLArray()),
                         '1\u00a0234,5|Да|Нет|Массив')
        self.assertEqual(template(None), '')
        self.assertEqual(template(Decimal(12)), '12')

    def test_utf16_and_nul_shared_contract_not_new_native_evidence(self):
        self.assertEqual(template('😀[%1]\0', 'Ж'), '😀[Ж]\0')
        self.assertEqual(template('\ud83d%1', '\ude00'), '😀')
        self.assertEqual(template('%1%2', '\ud83d', '\ude00'), '😀')
        self.assertEqual(template('%1', '\ud83d'), '\ud83d')
        self.assertEqual(template('\ud83d\ude00'), '😀')

    def test_existing_string_serialization_round_trip(self):
        self.assertEqual(self.vm.execute('ValueFromStringInternal(ValueToStringInternal('
                                         'StrTemplate("[%1]", "😀")))'), '[😀]')

    def test_missing_values_are_empty_and_excess_arguments_fail(self):
        for text, values in [('%1', ()), ('%2', ('x',)), ('%10', tuple('123456789'))]:
            with self.subTest(text=text):
                self.assertEqual(template(text, *values), '')
        self.assertEqual(template('[%1]|[%2]|%(3)', 'x'), '[x]|[]|')
        for text, values in [('', ('x',)), ('%%1', ('x',)), ('%1', ('x', 'y')),
                              ('%10', tuple(range(11)))]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'очень много'):
                template(text, *values)

    def test_malformed_markers_are_rejected_not_claimed_native_diagnostics(self):
        for text in ('%', '%x', '%0', '%00', '%01', '%11', '%100', '%()', '%(1',
                     '%(0)', '%(01)', '%(11)', '%(-1)', '%( 1)', '%١', '%１', '%1%'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'недопустимый формат'):
                template(text, 'x')

    def test_errors_preserve_assignment_and_recover_in_try(self):
        for expression in ('StrTemplate()', 'StrTemplate("", 1)',
                           'СтрШаблон("%0", 1)', 'StrTemplate("%11", 1)'):
            self.vm.execute('saved = "old"')
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute('saved = ' + expression, 'template.bsl')
            self.assertEqual(self.vm.execute('saved'), 'old')
            self.assertTrue(self.vm.execute('caught = False; Try ' + expression +
                                            '; Except caught = True; EndTry; caught'))
            self.assertEqual(self.vm.execute('StrTemplate("%1", "new")'), 'new')

    def test_long_input_and_many_markers(self):
        self.assertEqual(template('Ж' * 100000), 'Ж' * 100000)
        self.assertEqual(template('%1' * 10000, '😀'), '😀' * 10000)
        with self.assertRaisesRegex(ValueError, 'недопустимый формат'):
            template('%' + '9' * 100000)


if __name__ == '__main__':
    unittest.main()

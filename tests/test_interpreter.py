from decimal import Decimal
from pathlib import Path
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import IncompleteInput
from yadinassi.parser import parse
from yadinassi.values import BSLObject, HostFunction


ROOT = Path(__file__).resolve().parents[1]


class InterpreterTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def run_bsl(self, code):
        self.vm.execute(code, "test.bsl")
        return self.output

    def test_basic_sample_exact_output(self):
        code = (ROOT / "code_samples" / "basic.bsl").read_text(encoding="utf-8")
        expected = (ROOT / "tests" / "fixtures" / "basic.out").read_text(encoding="utf-8")
        self.assertEqual("\n".join(self.run_bsl(code)) + "\n", expected)

    def test_arithmetic_precedence_and_decimal_precision(self):
        self.assertEqual(self.run_bsl('''
            Сообщить(2 + 3 * 4); Сообщить((2 + 3) * 4);
            Сообщить(-2 * -3 + 7 % 4); Сообщить(0.1 + 0.2);
            Сообщить(1 / 4); Сообщить(10.000);
        '''), ["14", "20", "9", "0.3", "0.25", "10"])

    def test_unicode_case_insensitivity_and_english_aliases(self):
        self.assertEqual(self.run_bsl('''
            ЁЖ = 3; сОоБщИтЬ(ёж);
            If TRUE Then Message("ok"); EndIf;
            a = New Array; a.ADD(5); Message(a.COUNT());
        '''), ["3", "ok", "1"])

    def test_string_quotes_comments_and_multiline(self):
        self.assertEqual(self.run_bsl('''
            // ignored "
            Сообщить("Он сказал ""Привет"" // это строка");
            Сообщить("первая
                |вторая");
            Сообщить("C:\\temp");
        '''), ['Он сказал "Привет" // это строка', "первая\nвторая", "C:\\temp"])

    def test_if_elseif_nested_and_comparison_assignment(self):
        self.assertEqual(self.run_bsl('''
            x = 5; результат = x = 5;
            Если x < 0 Тогда Сообщить("bad");
            ИначеЕсли результат Тогда
                Если x <> 6 Тогда Сообщить("ok"); КонецЕсли;
            Иначе Сообщить("bad"); КонецЕсли;
            Если x >= 5 И x <= 5 Тогда Сообщить("equal"); КонецЕсли;
        '''), ["ok", "equal"])

    def test_short_circuit_and_not_precedence(self):
        self.assertEqual(self.run_bsl('''
            Если Ложь И Неизвестно() Тогда Сообщить("bad"); КонецЕсли;
            Если Истина Или Неизвестно() Тогда Сообщить("ok"); КонецЕсли;
            Если Не 1 = 2 И 3 > 2 Тогда Сообщить("not"); КонецЕсли;
            Сообщить(Истина = 1);
        '''), ["ok", "not", "Нет"])

    def test_for_bounds_evaluated_once_and_empty_loop(self):
        self.assertEqual(self.run_bsl('''
            предел = 3;
            Для i = 1 По предел Цикл
                Сообщить(i); предел = 0;
            КонецЦикла;
            Для j = 5 По 1 Цикл Сообщить("bad"); КонецЦикла;
        '''), ["1", "2", "3"])

    def test_nested_loops_break_and_continue(self):
        self.assertEqual(self.run_bsl('''
            Для i = 1 По 3 Цикл
                Если i = 2 Тогда Продолжить; КонецЕсли;
                Для j = 1 По 5 Цикл
                    Если j = 2 Тогда Прервать; КонецЕсли;
                    Сообщить("" + i + j);
                КонецЦикла;
            КонецЦикла;
            x = 0;
            Пока x < 3 Цикл x = x + 1; КонецЦикла;
            Сообщить(x);
        '''), ["11", "31", "3"])

    def test_array_indexing_methods_and_foreach(self):
        self.assertEqual(self.run_bsl('''
            a = Новый Массив(2); a[0] = "a"; a.Установить(1, "b");
            a.Вставить(1, "c"); a.Добавить("d"); a.Удалить(2);
            Сообщить(a.Количество()); Сообщить(a.ВГраница());
            Для Каждого x Из a Цикл Сообщить(x); КонецЦикла;
            Сообщить(a.Получить(0)); Сообщить(a.Найти("d"));
            Сообщить(a.Найти("нет") = Неопределено);
            a.Очистить(); Сообщить(a.Количество());
        '''), ["3", "2", "a", "c", "d", "a", "2", "Да", "0"])

    def test_variables_conversions_and_persistent_state(self):
        self.run_bsl("Перем а, б; а = 41;")
        self.assertEqual(self.run_bsl('''
            а = а + 1; Сообщить(а); Сообщить(б = Неопределено);
            Сообщить(Число("2.5") * 2); Сообщить(Строка(Истина));
            Сообщить(СтрДлина("ёж")); Сообщить(Булево(0));
        '''), ["42", "Да", "5", "Да", "2", "Нет"])

    def test_extension_function_and_type(self):
        class Counter(BSLObject):
            def get_member(self, name):
                if name.casefold() == "значение":
                    return HostFunction(name, lambda: Decimal(7))
                return super().get_member(name)

        self.vm.register_function("Удвоить", lambda x: x * 2)
        self.vm.register_type("Счетчик", Counter)
        self.assertEqual(self.run_bsl('''
            c = Новый Счетчик; Сообщить(Удвоить(c.Значение()));
        '''), ["14"])

    def test_errors_are_source_aware(self):
        cases = [
            ("\nСообщить(неизвестно);", "не определена", 2),
            ("Сообщить(1 / 0)", "Деление на ноль", 1),
            ("Сообщить(1 % 0)", "Деление на ноль", 1),
            ("а = Новый Массив; Сообщить(а[-1]);", "вне границ", 1),
            ("а = Новый Массив(1); а[0.5] = 1;", "целое", 1),
            ("а = Новый Массив; а.НетМетода();", "не найдено", 1),
            ("а = Новый НеизвестныйТип;", "Тип не определен", 1),
            ('Сообщить(1 + "x");', "Ожидается число", 1),
            ('Если "x" Тогда КонецЕсли;', "булево", 1),
            ('Сообщить("x".__class__);', "не имеет методов", 1),
            ("Сообщить();", "value", 1),
            ("Прервать;", "внутри цикла", 1),
            ("Продолжить;", "внутри цикла", 1),
            ("x = 1 y = 2", "между операторами", 1),
            ("@", "Неожиданный символ", 1),
        ]
        for code, message, line in cases:
            with self.subTest(code=code):
                with self.assertRaises(BSLError) as caught:
                    self.vm.execute(code, "bad.bsl")
                self.assertIn(message, str(caught.exception))
                self.assertEqual(caught.exception.source, "bad.bsl")
                self.assertEqual(caught.exception.line, line)
                self.assertGreater(caught.exception.column, 0)

    def test_incomplete_input_detection(self):
        for code in ('Если Истина Тогда\n', 'Для i = 1 По 2 Цикл\n',
                     'Сообщить(', 'x =', 'Сообщить("первая\n'):
            with self.subTest(code=code), self.assertRaises(IncompleteInput):
                parse(code)

    def test_entire_program_parsed_before_side_effects(self):
        with self.assertRaises(BSLError):
            self.run_bsl('Сообщить("не должно исполниться"); Если Тогда')
        self.assertEqual(self.output, [])


if __name__ == "__main__":
    unittest.main()

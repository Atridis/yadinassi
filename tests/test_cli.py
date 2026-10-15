import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def run_cli(self, *arguments, stdin=None):
        return subprocess.run([sys.executable, "-m", "yadinassi", *arguments],
                              input=stdin, capture_output=True, encoding="utf-8",
                              cwd=ROOT, timeout=10)

    def test_command_flags(self):
        for flag in ("-c", "-с", "--command"):
            with self.subTest(flag=flag):
                result = self.run_cli(flag, 'Сообщить("Привет")')
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "Привет\n", ""))

    def test_file_and_bom(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "пример.bsl"
            path.write_text('Сообщить("файл")', encoding="utf-8-sig")
            result = self.run_cli(str(path))
            self.assertEqual((result.returncode, result.stdout), (0, "файл\n"))

    def test_conditional_command_and_multiline_repl(self):
        result = self.run_cli("-c", 'Сообщить(?(Истина, 42, 1 / 0))')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))
        result = self.run_cli(stdin='?(\nЛожь,\n1 / 0,\n42)\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))

    def test_routine_command_and_multiline_repl(self):
        code = 'Функция Ответ() Возврат 42; КонецФункции Сообщить(Ответ());'
        result = self.run_cli("-c", code)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))
        result = self.run_cli(stdin='Function F()\nReturn 42;\nEndFunction\nF()\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))

    def test_parameter_command_and_multiline_repl(self):
        code = ('Функция ПолучитьСумму(Знач а, Знач б) Возврат а + б; '
                'КонецФункции Сообщить(ПолучитьСумму(1, 2));')
        result = self.run_cli("-c", code)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "3\n", ""))
        result = self.run_cli(stdin='Procedure P(\nx)\nx = x + 1;\nEndProcedure\n'
                                   'x = 7;\nP(x)\nx\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "8\n", ""))

    def test_default_parameters_command_file_and_multiline_repl(self):
        code = ('Функция Сумма(Знач а = 2, б = 3) Возврат а + б; '
                'КонецФункции Сообщить(Сумма()); Сообщить(Сумма(, 5));')
        result = self.run_cli("-c", code)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "5\n7\n", ""))
        result = self.run_cli("-", stdin=code)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "5\n7\n", ""))
        result = self.run_cli(stdin='Function F(x =\n-2)\nReturn x;\nEndFunction\n'
                                   'F()\nF(\n-2)\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "-2\n-2\n", ""))

    def test_missing_required_argument_has_clean_cli_error(self):
        code = 'Procedure P(a = 1, b) EndProcedure P()'
        result = self.run_cli("-c", code)
        self.assertEqual(result.returncode, 1)
        self.assertIn("<команда>:1:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cp1251_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.bsl"
            path.write_text('Сообщить("Привет")', encoding="cp1251")
            result = self.run_cli("--encoding", "cp1251", str(path))
            self.assertEqual((result.returncode, result.stdout), (0, "Привет\n"))

    def test_file_stdin(self):
        result = self.run_cli("-", stdin='Сообщить("stdin")')
        self.assertEqual((result.returncode, result.stdout), (0, "stdin\n"))

    def test_repl_state_multiline_and_expressions(self):
        result = self.run_cli(stdin='''x = 40;
Если Истина Тогда
x = x + 2;
КонецЕсли;
x
Сообщить(
"многострочный вызов"
)
/exit
''')
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "42\nмногострочный вызов\n", ""))

    def test_repl_recovers_from_parse_and_runtime_errors(self):
        result = self.run_cli(stdin='@\nСообщить(1/0);\nСообщить("жив");\n/exit\n')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "жив\n")
        self.assertIn("Неожиданный символ", result.stderr)
        self.assertIn("Деление на ноль", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_incomplete_repl_at_eof(self):
        result = self.run_cli(stdin="Если Истина Тогда\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Не завершен блок", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_empty_command(self):
        result = self.run_cli("-c", "")
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_argument_conflict(self):
        result = self.run_cli("code_samples/basic.bsl", "-c", "")
        self.assertEqual(result.returncode, 2)
        self.assertIn("нельзя", result.stderr)

    def test_missing_file_and_unknown_encoding(self):
        for arguments in (("missing.bsl",), ("--encoding", "no-such-codec", "code_samples/basic.bsl")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("Traceback", result.stderr)

    def test_runtime_error_exit_code(self):
        result = self.run_cli("-c", "Сообщить(1/0)")
        self.assertEqual(result.returncode, 1)
        self.assertIn("<команда>:1:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX pseudo-terminal test")
    def test_interactive_console_editing_and_history(self):
        from scripts.console_check import check_console

        output = check_console([sys.executable, "-m", "yadinassi"], cwd=ROOT)
        self.assertIn("— Yet Another oDIN ASS Interpreter.", output)


if __name__ == "__main__":
    unittest.main()

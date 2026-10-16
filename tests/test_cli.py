import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def run_cli(self, *arguments, stdin=None, cwd=ROOT):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(ROOT), environment.get("PYTHONPATH")]))
        return subprocess.run([sys.executable, "-m", "yadinassi", *arguments],
                              input=stdin, capture_output=True, encoding="utf-8",
                              cwd=cwd, env=environment, timeout=10)

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

    def test_client_compilation_command_stdin_and_repl(self):
        code = ('#If Server Then\n&AtServer\nunsupported !\n#Else\n'
                '&НаКлиенте\nФункция Ответ() Возврат 42; КонецФункции\n'
                'Сообщить(Ответ());\n#EndIf\n')
        for arguments, stdin in [(('-c', code), None), (('-',), code), ((), code + '/exit\n')]:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, stdin=stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))
        result = self.run_cli(stdin='&AtClient\nFunction F()\nReturn 42;\nEndFunction\nF()\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))

    def test_client_compilation_imported_file_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / 'project'
            project.mkdir()
            (project / 'Side.bsl').write_text(
                '#If Client Then\n&AtClient\nFunction F() Export Return 42; EndFunction\n'
                '#Else\n&AtServer\nunsupported !\n#EndIf', encoding='utf-8')
            main = project / 'Main.bsl'
            main.write_text('#If AtClient Then\n// #Импорт Side.bsl\n#Else\n'
                            '// #Импорт Missing.bsl\n#EndIf\nMessage(Side.F());', encoding='utf-8-sig')
            result = self.run_cli(str(main), cwd=root)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))

    def test_client_compilation_clean_diagnostics_and_unfinished_repl(self):
        cases = [('&AtServer\nProcedure P() EndProcedure', 'только клиентский контекст'),
                 ('#If Client Then\nMessage(1);', '#КонецЕсли'),
                 ('#Else', 'соответствующей #Если')]
        for code, message in cases:
            with self.subTest(code=code):
                result = self.run_cli('-c', code)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertIn('<команда>:', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertEqual(result.stdout, '')
        result = self.run_cli(stdin='#If Client Then\nMessage(1);\n')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('#КонецЕсли', result.stderr)

    def test_regions_command_file_stdin_and_multiline_repl(self):
        code = ('#Область Модуль\n#Region Routines\nФункция Ответ()\n'
                '    #Область Тело\n    Возврат 42;\n    #КонецОбласти\n'
                'КонецФункции\n#EndRegion\nСообщить(Ответ());\n#КонецОбласти\n')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Области.bsl'
            path.write_text(code, encoding='utf-8-sig')
            cases = [(('-c', code), None), ((str(path),), None),
                     (('-',), code), ((), code + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, '42\n', ''))

    def test_region_repl_executes_nested_block_once_after_closing(self):
        code = ('счетчик = 0;\n#Область Внешняя\nсчетчик = счетчик + 1;\n'
                '#Region Inner\nсчетчик = счетчик + 1;\n#EndRegion\n'
                'Сообщить(счетчик);\n#КонецОбласти\nсчетчик\n/exit\n')
        result = self.run_cli(stdin=code)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '2\n2\n', ''))

    def test_unfinished_regions_do_not_execute_in_command_file_stdin_or_repl(self):
        code = ('#Область Внешняя\nСообщить("рано");\n#Region Inner\n'
                'Сообщить("тоже рано");\n#EndRegion\n')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Незавершенная.bsl'
            path.write_text(code, encoding='utf-8')
            cases = [(('-c', code), None, '<команда>'),
                     ((str(path),), None, str(path)),
                     (('-',), code, '<stdin>'), ((), code, '<консоль>')]
            for arguments, stdin, source in cases:
                with self.subTest(source=source):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout), (1, ''))
                    self.assertIn(source + ':1:', result.stderr)
                    self.assertIn('#КонецОбласти', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_malformed_regions_have_clean_diagnostics_and_repl_recovers(self):
        cases = [('#КонецОбласти', 1), ('#EndRegion', 1),
                 ('#Область', 1), ('#Region', 1),
                 ('#Область 123', 1), ('#Region 123', 1),
                 ('#Область Имя хвост', 1), ('#Region Name extra', 1),
                 ('#Область Имя\n#КонецОбласти хвост', 2),
                 ('#Region Name\n#EndRegion extra', 2)]
        for code, line in cases:
            for arguments, stdin, source, stdout in [
                    (('-c', code), None, '<команда>', ''),
                    (('-',), code, '<stdin>', ''),
                    ((), code + '\nСообщить("жив");\n/exit\n', '<консоль>', 'жив\n')]:
                with self.subTest(code=code, source=source):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout), (1, stdout))
                    self.assertIn(f'{source}:{line}:', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_regions_preserve_runtime_error_source_lines(self):
        code = ('#Область Внешняя\n#Region Inner\nСообщить(1 / 0);\n'
                '#EndRegion\n#КонецОбласти\n')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Ошибка.bsl'
            path.write_text(code, encoding='utf-8')
            cases = [(('-c', code), None, '<команда>'),
                     ((str(path),), None, str(path)),
                     (('-',), code, '<stdin>'), ((), code + '/exit\n', '<консоль>')]
            for arguments, stdin, source in cases:
                with self.subTest(source=source):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout), (1, ''))
                    self.assertIn(source + ':3:', result.stderr)
                    self.assertIn('Деление на ноль', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_regions_imported_file_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / 'project'
            project.mkdir()
            main = project / 'Основное.bsl'
            main.write_text('#Область Импорты\n// #Импорт Побочное.bsl\n'
                            '#КонецОбласти\nСообщить(Побочное.Ответ());\n', encoding='utf-8-sig')
            (project / 'Побочное.bsl').write_text(
                '#Region PublicAPI\nФункция Ответ() Экспорт\n#Область Тело\n'
                'Возврат 42;\n#КонецОбласти\nКонецФункции\n#EndRegion\n',
                encoding='utf-8-sig')
            for path in (main, Path('project') / main.name):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=directory)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, '42\n', ''))

    def test_imported_regions_preserve_error_source_lines(self):
        cases = [('#Область API\nФункция Ответ() Экспорт\n#Region Body\n'
                  'Возврат 1 / 0;\n#EndRegion\nКонецФункции\n#КонецОбласти\n',
                  4, 'Деление на ноль'),
                 ('#Область API\n// комментарий\n#КонецОбласти хвост\n',
                  3, '#КонецОбласти'),
                 ('// комментарий\n#EndRegion\n', 2, '#Область')]
        for code, line, message in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                main = directory / 'Основное.bsl'
                main.write_text('// #Импорт Побочное.bsl\nСообщить(Побочное.Ответ());\n',
                                encoding='utf-8')
                module = directory / 'Побочное.bsl'
                module.write_text(code, encoding='utf-8-sig')
                result = self.run_cli(str(main))
                self.assertEqual((result.returncode, result.stdout), (1, ''))
                self.assertIn(f'{module.resolve()}:{line}:', result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_missing_required_argument_has_clean_cli_error(self):
        code = 'Procedure P(a = 1, b) EndProcedure P()'
        result = self.run_cli("-c", code)
        self.assertEqual(result.returncode, 1)
        self.assertIn("<команда>:1:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_import_symlink_loop_has_clean_source_aware_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            main = Path(temporary) / "Main.bsl"
            main.write_text("// #Импорт Side.bsl\n", encoding="utf-8")
            side = Path(temporary) / "Side.bsl"
            try:
                side.symlink_to(side.name)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are not available on this host")
            result = self.run_cli(str(main))
            self.assertEqual(result.returncode, 1)
            self.assertIn(str(main) + ":1:", result.stderr)
            self.assertIn("Side.bsl", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_cp1251_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.bsl"
            path.write_text('Сообщить("Привет")', encoding="cp1251")
            result = self.run_cli("--encoding", "cp1251", str(path))
            self.assertEqual((result.returncode, result.stdout), (0, "Привет\n"))

    def test_import_resolves_beside_file_from_unrelated_cwd_with_bom(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / "project"
            project.mkdir()
            main = project / "Основное.bsl"
            main.write_text('// #Импорт Побочное.bsl\nСообщить(Побочное.Ответ());',
                            encoding="utf-8-sig")
            (project / "Побочное.bsl").write_text(
                'Функция Ответ() Экспорт Возврат "соседний"; КонецФункции',
                encoding="utf-8-sig")
            (directory / "Побочное.bsl").write_text('Сообщить("не тот файл");', encoding="utf-8")
            result = self.run_cli(str(main), cwd=directory)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "соседний\n", ""))
            result = self.run_cli(str(Path("project") / main.name), cwd=directory)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "соседний\n", ""))

    def test_nested_import_from_unrelated_cwd_with_bom_and_shared_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / "project"
            nested = project / "Справочник"
            deeper = nested / "Вложенное"
            deeper.mkdir(parents=True)
            main = project / "Основное.bsl"
            main.write_text(
                '// #Импорт Справочник.Побочное.bsl\n'
                '// #Импорт Справочник.Вложенное.Другое.bsl\n'
                'Сообщить(справочник.ПОБОЧНОЕ.получитьсумму(1, 2));\n'
                'Сообщить(СПРАВОЧНИК.вложенное.ДРУГОЕ.ответ());',
                encoding="utf-8-sig")
            (nested / "Побочное.bsl").write_text(
                'Функция ПолучитьСумму(А, Б) Экспорт Возврат А + Б; КонецФункции',
                encoding="utf-8-sig")
            (deeper / "Другое.bsl").write_text(
                'Функция Ответ() Экспорт Возврат "вложенный"; КонецФункции',
                encoding="utf-8-sig")
            wrong = directory / "Справочник"
            wrong.mkdir()
            (wrong / "Побочное.bsl").write_text('Сообщить("не тот файл");', encoding="utf-8")
            for path in (main, Path("project") / main.name):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=directory)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, "3\nвложенный\n", ""))

    def test_directory_import_from_other_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / "project"
            package = project / "Справочник"
            package.mkdir(parents=True)
            (package / "Побочное.bsl").write_text(
                'Функция ПолучитьСумму(А, Б) Экспорт Возврат А + Б; КонецФункции',
                encoding="cp1251")
            main = project / "Основное.bsl"
            main.write_text('// #Импорт Справочник\n'
                            'Сообщить(Справочник.Побочное.ПолучитьСумму(1, 2));',
                            encoding="cp1251")
            for path in (main, Path("project") / main.name):
                with self.subTest(path=path):
                    result = self.run_cli("--encoding", "cp1251", str(path), cwd=directory)
                    self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "3\n", ""))

    def test_nested_import_errors_have_clean_source_aware_diagnostics(self):
        cases = [('// #Импорт Справочник.Нет.bsl\n', 'Основное.bsl:1:'),
                 ('// #Импорт НетКаталога\n', 'Основное.bsl:1:'),
                 ('// #Импорт Справочник.Побочное.bsl\n'
                  'Сообщить(Справочник.Побочное.Ошибка());', 'Побочное.bsl:2:')]
        for source, location in cases:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                nested = directory / "Справочник"
                nested.mkdir()
                (nested / "Побочное.bsl").write_text(
                    'Функция Ошибка() Экспорт\nВозврат 1 / 0;\nКонецФункции',
                    encoding="utf-8")
                main = directory / "Основное.bsl"
                main.write_text(source, encoding="utf-8")
                result = self.run_cli(str(main))
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(location, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_encoding_option_applies_to_transitive_imports(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            main = directory / "Основное.bsl"
            main.write_text('// #Импорт Побочное.bsl\nСообщить(Побочное.Ответ());', encoding="cp1251")
            (directory / "Побочное.bsl").write_text(
                '// #Импорт Третье.bsl\nФункция Ответ() Экспорт Возврат Третье.Текст(); КонецФункции',
                encoding="cp1251")
            (directory / "Третье.bsl").write_text(
                'Функция Текст() Экспорт Возврат "Привет"; КонецФункции', encoding="cp1251")
            result = self.run_cli("--encoding", "cp1251", str(main))
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "Привет\n", ""))

    def test_import_errors_have_clean_cli_diagnostics(self):
        cases = [(None, 'Side.F()', 'Main.bsl:1:'),
                 ('\n@', 'Side.F()', 'Side.bsl:2:'),
                 ('Function F() Export\nReturn 1 / 0;\nEndFunction',
                  'Side.F()', 'Side.bsl:2:'),
                 ('Function F() Return 42; EndFunction', 'Side.F()', 'Main.bsl:2:'),
                 ('// #Импорт Main.bsl\n', 'Side.F()', 'Side.bsl:1:')]
        for module, call, location in cases:
            with self.subTest(module=module), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                main = directory / "Main.bsl"
                main.write_text('// #Импорт Side.bsl\n' + call, encoding="utf-8")
                if module is not None:
                    (directory / "Side.bsl").write_text(module, encoding="utf-8")
                result = self.run_cli(str(main))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn(location, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_import_without_source_file_is_rejected_in_command_stdin_and_repl(self):
        code = '// #Импорт Side.bsl\n'
        cases = [(('-c', code), None, '<команда>'),
                 (('-',), code, '<stdin>'),
                 ((), code + '/exit\n', '<консоль>')]
        for arguments, stdin, source in cases:
            with self.subTest(source=source):
                result = self.run_cli(*arguments, stdin=stdin)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn(source + ':1:', result.stderr)
                self.assertIn("путь исходного файла", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_import_decode_error_is_clean_cli_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            main = directory / "Main.bsl"
            main.write_text('// #Импорт Side.bsl\n', encoding="utf-8")
            (directory / "Side.bsl").write_text('Сообщить("Привет")', encoding="cp1251")
            result = self.run_cli(str(main))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Main.bsl:1:", result.stderr)
            self.assertIn("Side.bsl", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

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
        result = self.run_cli("integrational_tests/tests/basic.bsl", "-c", "")
        self.assertEqual(result.returncode, 2)
        self.assertIn("нельзя", result.stderr)

    def test_missing_file_and_unknown_encoding(self):
        for arguments in (("missing.bsl",),
                          ("--encoding", "no-such-codec", "integrational_tests/tests/basic.bsl")):
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

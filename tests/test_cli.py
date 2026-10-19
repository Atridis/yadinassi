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

    def test_dates_all_flags_bom_file_stdin_and_console(self):
        from scripts.smoke_test import DATE_PROGRAM, DATE_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'КалендарныеДаты.bsl'
            source.write_text(DATE_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, DATE_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), DATE_PROGRAM),
                      ((), DATE_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, DATE_OUTPUT, ''))

    def test_date_diagnostics_and_console_state_recovery(self):
        from scripts.smoke_test import DATE_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаДаты.bsl'
            for expression, message in DATE_FAILURES:
                code = f'savedDate = Date(2024, 2, 29);\nsavedDate = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source.resolve()) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'ValueToStringInternal(savedDate)\n/exit\n',
                           '{"D",20240229000000}\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_dates_cross_bom_imported_routines_and_literal_defaults(self):
        from scripts.smoke_test import DATE_MODULE, DATE_IMPORT_PROGRAM, DATE_IMPORT_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            project = temporary / 'project'
            project.mkdir()
            module = project / 'Даты.bsl'
            module.write_text(DATE_MODULE, encoding='utf-8-sig')
            main = project / 'Основное.bsl'
            main.write_text(DATE_IMPORT_PROGRAM, encoding='utf-8-sig')
            for path in (main, main.relative_to(temporary)):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, DATE_IMPORT_OUTPUT, ''))
            main.write_text('// #Импорт Даты.bsl\nДаты.Failure();\n', encoding='utf-8-sig')
            for path in (main, main.relative_to(temporary)):
                with self.subTest(error_path=path):
                    result = self.run_cli(str(path), cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout), (1, ''))
                    self.assertIn(str(module.resolve()) + ':8:', result.stderr)
                    self.assertIn('Ожидается дата', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
            main.write_text('// #Импорт Даты.bsl\nTry Даты.Failure(); Except\n'
                            'Message(ErrorDescription()); EndTry;\n'
                            'Message(Даты.DefaultDate() = \'20240229123456\');\n',
                            encoding='utf-8-sig')
            result = self.run_cli(str(main.relative_to(temporary)), cwd=temporary)
            self.assertEqual((result.returncode, result.stderr), (0, ''))
            self.assertTrue(result.stdout.startswith(str(module.resolve()) + ':8:'))
            self.assertTrue(result.stdout.endswith('Ожидается дата\nДа\n'))

    def test_date_literal_errors_and_unfinished_console_input_recover(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ЛитералДаты.bsl'
            for literal, message in [("'2024022912'", 'Дата: ожидается каноническая запись даты'),
                                     ("'20240229", 'Незавершенный литерал даты')]:
                code = '// строка перед ошибкой\nsavedDate = ' + literal
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, str(source.resolve()) + ':2:'),
                          (('-',), code, '<stdin>:2:')]
                for arguments, stdin, location in cases:
                    with self.subTest(literal=literal, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, ''))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)
        result = self.run_cli(stdin="savedDate = '20240229';\nsavedDate = '20240229\n"
                              'ValueToStringInternal(savedDate)\n'
                              'savedDate = Date(\n2024, 2, 29, 12, 34, 56);\n'
                              'ValueToStringInternal(savedDate)\n/exit\n')
        self.assertEqual((result.returncode, result.stdout),
                         (1, '{"D",20240229000000}\n{"D",20240229123456}\n'))
        self.assertEqual(result.stderr.count('<консоль>:1:'), 1)
        self.assertIn('Перенос строки в литерале даты не поддерживается', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_eval_all_cli_inputs(self):
        from scripts.smoke_test import EVAL_PROGRAM, EVAL_OUTPUT
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ВычислениеВыражения.bsl'
            source.write_text(EVAL_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, EVAL_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), EVAL_PROGRAM),
                      ((), EVAL_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, EVAL_OUTPUT, ''))

    def test_goto_all_cli_inputs(self):
        from scripts.smoke_test import GOTO_PROGRAM, GOTO_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'Переходы.bsl'
            source.write_text(GOTO_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, GOTO_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), GOTO_PROGRAM),
                      ((), GOTO_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, GOTO_OUTPUT, ''))

    def test_goto_static_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import GOTO_ERRORS

        for program, message in GOTO_ERRORS:
            for arguments, stdin, source in [
                (('-c', program), None, '<команда>'),
                (('-',), program, '<stdin>'),
            ]:
                with self.subTest(program=program, arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout), (1, ''))
                    self.assertIn(source + ':1:', result.stderr)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
        result = self.run_cli(stdin='saved = 42;\nGoto ~missing;\nsaved\n'
                              '~done: Message("recovered");\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, '42\nrecovered\n'))
        self.assertIn('Метка не определена', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_numeric_boolean_comparisons_all_cli_inputs(self):
        from scripts.smoke_test import COMPARISON_PROGRAM, COMPARISON_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'Сравнения.bsl'
            source.write_text(COMPARISON_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, COMPARISON_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), COMPARISON_PROGRAM),
                      ((), COMPARISON_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, COMPARISON_OUTPUT, ''))

    def test_numeric_boolean_comparison_diagnostics_and_console_recovery(self):
        result = self.run_cli(stdin='value = True = 1;\nvalue = True < "1";\nvalue\nFalse = 0\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, 'Да\nДа\n'))
        self.assertIn('<консоль>:1:', result.stderr)
        self.assertIn('Значения несовместимы для сравнения', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_numeric_helpers_all_cli_inputs(self):
        from scripts.smoke_test import NUMERIC_HELPERS_PROGRAM, NUMERIC_HELPERS_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ЦелаяЧасть.bsl'
            source.write_text(NUMERIC_HELPERS_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, NUMERIC_HELPERS_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), NUMERIC_HELPERS_PROGRAM),
                      ((), NUMERIC_HELPERS_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, NUMERIC_HELPERS_OUTPUT, ''))

    def test_native_string_parity_all_cli_inputs(self):
        from scripts.smoke_test import STRING_PARITY_PROGRAM, STRING_PARITY_OUTPUT
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ВхожденияШаблона.bsl'
            source.write_text(STRING_PARITY_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, STRING_PARITY_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), STRING_PARITY_PROGRAM),
                      ((), STRING_PARITY_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, STRING_PARITY_OUTPUT, ''))

    def test_array_gap_all_cli_inputs(self):
        from scripts.smoke_test import ARRAY_GAP_PROGRAM, ARRAY_GAP_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ПромежуткиМассива.bsl'
            source.write_text(ARRAY_GAP_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, ARRAY_GAP_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), ARRAY_GAP_PROGRAM),
                      ((), ARRAY_GAP_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, ARRAY_GAP_OUTPUT, ''))

    def test_array_gap_diagnostics_and_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаПромежутка.bsl'
            code = 'a = New Array; a.Add("old");\na.Insert(100000000000000000000);\n'
            source.write_text(code, encoding='utf-8-sig')
            cases = [((flag, code), None, '', '<команда>:2:') for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None, '', str(source) + ':2:'),
                      (('-',), code, '', '<stdin>:2:'),
                      ((), code + 'a.Count()\na[0]\n/exit\n', '1\nold\n', '<консоль>:1:')]
            for arguments, stdin, stdout, location in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, stdout)
                    self.assertIn(location, result.stderr)
                    self.assertIn('предел роста массива Yadinassi', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_array_defaults_all_cli_inputs(self):
        from scripts.smoke_test import ARRAY_DEFAULT_PROGRAM, ARRAY_DEFAULT_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ПустыеЭлементы.bsl'
            source.write_text(ARRAY_DEFAULT_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, ARRAY_DEFAULT_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), ARRAY_DEFAULT_PROGRAM),
                      ((), ARRAY_DEFAULT_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, ARRAY_DEFAULT_OUTPUT, ''))

    def test_value_filled_all_cli_inputs(self):
        from scripts.smoke_test import VALUE_FILLED_PROGRAM, VALUE_FILLED_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'Заполненность.bsl'
            source.write_text(VALUE_FILLED_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, VALUE_FILLED_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), VALUE_FILLED_PROGRAM),
                      ((), VALUE_FILLED_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, VALUE_FILLED_OUTPUT, ''))

    def test_value_filled_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import VALUE_FILLED_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаЗаполненности.bsl'
            for expression, message in VALUE_FILLED_FAILURES:
                code = f'saved = "old";\nsaved = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'saved\nValueIsFilled(False)\n/exit\n',
                           'old\nДа\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_string_lines_all_cli_inputs(self):
        from scripts.smoke_test import STRING_LINES_PROGRAM, STRING_LINES_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'МногострочныйТекст.bsl'
            source.write_text(STRING_LINES_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, STRING_LINES_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), STRING_LINES_PROGRAM),
                      ((), STRING_LINES_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, STRING_LINES_OUTPUT, ''))

    def test_string_lines_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import STRING_LINES_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаСтроки.bsl'
            for expression, message in STRING_LINES_FAILURES:
                code = f'saved = "old";\nsaved = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'saved\nStrGetLine("new", 1)\n/exit\n',
                           'old\nnew\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_string_template_all_cli_inputs(self):
        from scripts.smoke_test import STRING_TEMPLATE_PROGRAM, STRING_TEMPLATE_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ШаблонСтроки.bsl'
            source.write_text(STRING_TEMPLATE_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, STRING_TEMPLATE_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), STRING_TEMPLATE_PROGRAM),
                      ((), STRING_TEMPLATE_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, STRING_TEMPLATE_OUTPUT, ''))

    def test_string_template_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import STRING_TEMPLATE_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаШаблона.bsl'
            for expression, message in STRING_TEMPLATE_FAILURES:
                code = f'saved = "old";\nsaved = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'saved\nStrTemplate("%1", "new")\n/exit\n',
                           'old\nnew\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_string_boundaries_all_cli_inputs(self):
        from scripts.smoke_test import STRING_BOUNDARY_PROGRAM, STRING_BOUNDARY_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ГраницыСтрок.bsl'
            source.write_text(STRING_BOUNDARY_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, STRING_BOUNDARY_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), STRING_BOUNDARY_PROGRAM),
                      ((), STRING_BOUNDARY_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, STRING_BOUNDARY_OUTPUT, ''))

    def test_string_boundary_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import STRING_BOUNDARY_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаГраницы.bsl'
            for expression, message in STRING_BOUNDARY_FAILURES:
                code = f'saved = True;\nsaved = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'saved\nStrStartsWith("A", "A")\n/exit\n',
                           'Да\nДа\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_characters_all_cli_inputs(self):
        from scripts.smoke_test import CHARACTER_PROGRAM, CHARACTER_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'Символы.bsl'
            source.write_text(CHARACTER_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, CHARACTER_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), CHARACTER_PROGRAM),
                      ((), CHARACTER_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, CHARACTER_OUTPUT, ''))

    def test_character_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import CHARACTER_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаСимвола.bsl'
            for expression, message in CHARACTER_FAILURES:
                code = f'saved = Символ(65);\nsaved = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'saved\nКодСимвола(saved)\n/exit\n',
                           'A\n65\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_integer_part_diagnostics_and_console_recovery(self):
        result = self.run_cli(stdin='value = Int(-12.9);\nvalue = Int();\nvalue\nInt(0.9)\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, '-12\n0\n'))
        self.assertIn('<консоль>:1:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_rounding_all_cli_inputs(self):
        from scripts.smoke_test import ROUNDING_PROGRAM, ROUNDING_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'Округление.bsl'
            source.write_text(ROUNDING_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, ROUNDING_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), (('-',), ROUNDING_PROGRAM),
                      ((), ROUNDING_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, ROUNDING_OUTPUT, ''))

    def test_rounding_diagnostics_and_console_recovery(self):
        from scripts.smoke_test import ROUNDING_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаОкругления.bsl'
            for expression, message in ROUNDING_FAILURES:
                code = f'value = Round(12.345, 2);\nvalue = {expression};\n'
                source.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(source),), None, '', str(source) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'value\nОкр(-1.5)\n/exit\n',
                           '12,35\n-2\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

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

    def test_division_and_bounded_presentation_all_flags_bom_file_stdin_and_console(self):
        from scripts.smoke_test import DIVISION_PROGRAM, DIVISION_OUTPUT

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            path = temporary / 'Деление.bsl'
            path.write_text(DIVISION_PROGRAM, encoding='utf-8-sig')
            cases = [((flag, DIVISION_PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(path),), None), (('-',), DIVISION_PROGRAM),
                      ((), DIVISION_PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, DIVISION_OUTPUT, ''))

    def test_bounded_presentation_bare_console_diagnostics_and_recovery(self):
        from scripts.smoke_test import PRESENTATION_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            for expression, message in PRESENTATION_FAILURES:
                code = ('value = 1 / 7;\n' + expression + '\n'
                        'value\nTypeOf(value)\n1 / 8\n/exit\n')
                with self.subTest(expression=expression):
                    result = self.run_cli(stdin=code, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout),
                                     (1, '0,142857142857142857142857143\nЧисло\n0,125\n'))
                    self.assertIn('<консоль>:1:', result.stderr)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_division_diagnostics_and_console_state_recovery(self):
        from scripts.smoke_test import DIVISION_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            path = temporary / 'ОшибкаДеления.bsl'
            for expression, message in (DIVISION_FAILURES[index] for index in (0, 2, 6)):
                code = f'value = 1 / 7;\nvalue = {expression};\n'
                path.write_text(code, encoding='utf-8-sig')
                cases = [((flag, code), None, '', '<команда>:2:')
                         for flag in ('-c', '-с', '--command')]
                cases += [((str(path),), None, '', str(path) + ':2:'),
                          (('-',), code, '', '<stdin>:2:'),
                          ((), code + 'value\nTypeOf(value)\n1 / 8\n/exit\n',
                           '0,142857142857142857142857143\nЧисло\n0,125\n', '<консоль>:1:')]
                for arguments, stdin, stdout, location in cases:
                    with self.subTest(expression=expression, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, stdout))
                        self.assertIn(location, result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_division_crosses_bom_exported_imports_from_unrelated_cwd(self):
        from scripts.smoke_test import DIVISION_FAILURES

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            project = temporary / 'project'
            project.mkdir()
            module = project / 'Доли.bsl'
            module.write_text(
                'Function Divide(a, b) Export\nReturn a / b;\nEndFunction\n'
                'Function Seventh() Export Return 1 / 7; EndFunction\n', encoding='utf-8-sig')
            main = project / 'Основное.bsl'
            main.write_text(
                '// #Импорт Доли.bsl\nvalue = Доли.Seventh();\n'
                'Message(value); Message(Доли.Divide(value, 3));\n'
                'Message(Доли.Divide(1, 0.3)); Message(TypeOf(value));\n'
                'Message(value = Number("0.142857142857142857142857143"));\n'
                'Try value = Доли.Divide(1, 268435456); Except Message("caught"); EndTry;\n'
                'Message(value); Message(Доли.Divide(1, 8));\n', encoding='utf-8-sig')
            expected = ('0,142857142857142857142857143\n'
                        '0,047619047619047619047619047666666666666666666666666667\n'
                        '3,333333333333333333\nЧисло\nДа\ncaught\n'
                        '0,142857142857142857142857143\n0,125\n')
            for path in (main, main.relative_to(temporary)):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))
            for expression, message in (DIVISION_FAILURES[index] for index in (0, 2, 6)):
                main.write_text('// #Импорт Доли.bsl\nДоли.Divide(' +
                                expression.replace(' / ', ', ') + ');\n', encoding='utf-8-sig')
                for path in (main, main.relative_to(temporary)):
                    with self.subTest(expression=expression, path=path):
                        result = self.run_cli(str(path), cwd=temporary)
                        self.assertEqual((result.returncode, result.stdout), (1, ''))
                        self.assertIn(str(module.resolve()) + ':2:', result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_numeric_presentation_all_flags_bom_file_stdin_and_console(self):
        code = '''value = nUmBeR("-1234.5000");
mEsSaGe(value); сОоБщИтЬ(сТрОкА(value));
Message("value=" + value); Message(чИсЛо("1\u00a0234,5000"));
Message(String(-0.000)); Message(String(1000.000));
Message(TypeOf(value) = Тип("Число"));
Message(Number(String(value)) = value);
Message(Найти(value, ",")); Message(StrReplace(value, ",", "."));
Message(StrConcat(StrSplit(value, ","), "|"));
Message(СтрДлина(value));
exact = Number("123456789012345678901234567890.123456789");
Message(exact); Message(Number(String(exact)) = exact);
Message(Number("+12\u00a0345")); Message(Number("-123\u00a0456,000100"));
Message(Number("1\u00a0234\u00a0567")); Message(Number("001\u00a0234,5000"));
Message(String("1234.5000"));
'''
        expected = ('-1\u00a0234,5\n-1\u00a0234,5\nvalue=-1\u00a0234,5\n'
                    '1\u00a0234,5\n0\n1\u00a0000\nДа\nДа\n7\n'
                    '-1\u00a0234.5\n-1\u00a0234|5\n8\n'
                    '123\u00a0456\u00a0789\u00a0012\u00a0345\u00a0678'
                    '\u00a0901\u00a0234\u00a0567\u00a0890,123456789\nДа\n'
                    '12\u00a0345\n-123\u00a0456,0001\n1\u00a0234\u00a0567\n1\u00a0234,5\n1234.5000\n')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Числа.bsl'
            path.write_text(code, encoding='utf-8-sig')
            cases = [((flag, code), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(path),), None), (('-',), code), ((), code + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))

    def test_invalid_numeric_conversion_is_catchable_across_cli_entries(self):
        invalid = ['1,2.3', '1.2,3', '1,,2', '1,2,3', '1 234,5',
                   'NaN', 'Infinity', 'not a number', '1,', ',5', '1,2e3',
                   '1_000,25', '1,2_5', '١,٢', '12\u00a034,5',
                   '1234\u00a0567', '1\u00a02345', '1\u00a0\u00a0234',
                   '1\u00a0234.5', '1\u00a0234,5e2', '1\u202f234,5',
                   '1\u00a0234 567,5', '1\u00a0٢٣٤,5']
        code = 'value = Number("1\u00a0234,5");\n'
        for text in invalid:
            code += (f'Try\nvalue = Число("{text}");\nExcept\n'
                     'Message("caught");\nEndTry;\n')
        code += 'Message(value); Message(TypeOf(value)); Message(Number("0,125"));\n'
        expected = 'caught\n' * len(invalid) + '1\u00a0234,5\nЧисло\n0,125\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ОшибкиЧисел.bsl'
            path.write_text(code, encoding='utf-8-sig')
            cases = [((flag, code), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(path),), None), (('-',), code), ((), code + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))

    def test_numeric_conversion_cli_diagnostics_and_console_recovery(self):
        code = 'value = Number("1\u00a0234,5");\nvalue = Number("12\u00a034,5");\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ОшибкаЧисла.bsl'
            path.write_text(code, encoding='utf-8-sig')
            cases = [((flag, code), None, '', '<команда>:2:')
                     for flag in ('-c', '-с', '--command')]
            cases += [((str(path),), None, '', str(path) + ':2:'),
                      (('-',), code, '', '<stdin>:2:'),
                      ((), code + 'value\nTypeOf(value)\nNumber("0,125")\n/exit\n',
                       '1\u00a0234,5\nЧисло\n0,125\n', '<консоль>:1:')]
            for arguments, stdin, stdout, location in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout), (1, stdout))
                    self.assertIn(location, result.stderr)
                    self.assertIn('Невозможно преобразовать значение в число', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_numeric_presentation_crosses_bom_imports_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / 'project'
            project.mkdir()
            module = project / 'Числа.bsl'
            module.write_text(
                'Function Parse(text) Export Return чИсЛо(text); EndFunction\n'
                'Function Present(value) Export Return сТрОкА(value); EndFunction\n'
                'Procedure Show(value) Export Сообщить(value); EndProcedure\n'
                'Function Fail() Export\nReturn Number("12\u00a034,5");\nEndFunction\n',
                encoding='utf-8-sig')
            main = project / 'Основное.bsl'
            code = ('// #Импорт Числа.bsl\nvalue = числа.Parse("-1\u00a0234,5000");\n'
                    'Message(TypeOf(value)); Message(value); Числа.Show(value);\n'
                    'Message(Числа.Present(value)); Message("value=" + value);\n'
                    'Message(Number(Числа.Present(value)) = value);\n'
                    'Try Числа.Fail(); Except Message("caught"); EndTry;\n'
                    'Message(Числа.Parse("0.125"));\n')
            main.write_text(code, encoding='utf-8-sig')
            expected = ('Число\n-1\u00a0234,5\n-1\u00a0234,5\n-1\u00a0234,5\n'
                        'value=-1\u00a0234,5\nДа\ncaught\n0,125\n')
            for path in (main, main.relative_to(temporary)):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))
            main.write_text('// #Импорт Числа.bsl\nЧисла.Fail();\n', encoding='utf-8-sig')
            for path in (main, main.relative_to(temporary)):
                with self.subTest(error_path=path):
                    result = self.run_cli(str(path), cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout), (1, ''))
                    self.assertIn(str(module.resolve()) + ':5:', result.stderr)
                    self.assertIn('Невозможно преобразовать значение в число', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_type_values_command_file_stdin_and_console(self):
        types = [('Undefined', 'Неопределено', 'Undefined'),
                 ('Boolean', 'Булево', 'True'),
                 ('Number', 'Число', '12.5'),
                 ('String', 'Строка', '"ёж"'),
                 ('Array', 'Массив', 'New Array'),
                 ('Structure', 'Структура', 'New Structure'),
                 ('Map', 'Соответствие', 'New Map'),
                 ('FixedArray', 'ФиксированныйМассив', 'New FixedArray(New Array)'),
                 ('FixedStructure', 'ФиксированнаяСтруктура', 'New FixedStructure'),
                 ('FixedMap', 'ФиксированноеСоответствие', 'New FixedMap(New Map)'),
                 ('KeyAndValue', 'КлючИЗначение', 'pair'),
                 ('Type', 'Тип', 'Type("Number")')]
        code = ('s = New Structure("Item", 1);\n'
                'For Each pair In s Do EndDo;\n')
        for english, russian, expression in types:
            code += (f'Message(tYpE("{english.swapcase()}"));\n'
                     f'Сообщить(тИп("{russian.swapcase()}") = Type("{english}"));\n'
                     f'Message(tYpEoF({expression}) = Тип("{russian}"));\n'
                     f'Сообщить(тИпЗнЧ({expression}));\n')
        expected = ''.join(f'{presentation}\nДа\nДа\n{presentation}\n'
                           for english, russian, _ in types
                           for presentation in ['Не определено' if english == 'Undefined' else russian])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Типы.bsl'
            path.write_text(code, encoding='utf-8-sig')
            cases = [(('-c', code), None), ((str(path),), None),
                     (('-',), code), ((), code + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))

    def test_fixed_collections_command_file_stdin_and_console(self):
        code = '''source = New Array(2);
source[0] = 10; source[1] = 20;
frozen = Новый ФиксированныйМассив(source);
source[0] = 99; source.Add(30);
Message(frozen.Count()); Сообщить(frozen.ВГраница());
Message(frozen.Get(0)); Сообщить(frozen.Получить(1));
Message(frozen.Find(20)); Message(frozen.Найти(99) = Undefined);
total = 0;
For Each item In frozen Do total = total + item; EndDo;
Message(total);
record = New FixedStructure("Name,Count", "ёж", 7);
Message(record.NAME); Message(record["name"]);
Message(record.Count); Message(record.Count());
Var found;
Message(record.Property("nAmE", found)); Message(found);
Сообщить(record.Свойство("Missing", found)); Message(found = Undefined);
mutableRecord = Новый Структура("Name", "исходное");
snapshot = Новый ФиксированнаяСтруктура(mutableRecord);
mutableRecord.Name = "изменено"; mutableRecord.Insert("Extra", 1);
Message(snapshot.Name); Message(snapshot.Количество());
visited = 0;
For Each pair In record Do
    visited = visited + 1;
    Message(TypeOf(pair) = Type("KeyAndValue"));
EndDo;
Message(visited);
sourceMap = New Map;
sourceMap[True] = "булево"; sourceMap[1] = "число";
lookup = Новый ФиксированноеСоответствие(sourceMap);
sourceMap[1] = "изменено"; sourceMap.Insert("extra", 3);
Message(lookup.Count()); Message(lookup.Get(True));
Message(lookup.Получить(1)); Message(lookup.Get("missing") = Undefined);
visited = 0;
For Each pair In lookup Do visited = visited + 1; EndDo;
Message(visited);
arrayCopy = New Array(frozen); arrayCopy[0] = 40; arrayCopy.Add(50);
recordCopy = New Structure(record); recordCopy.Name = "копия";
mapCopy = New Map(lookup); mapCopy[1] = "копия"; mapCopy.Insert(2, 2);
Message(frozen[0]); Message(arrayCopy.Count());
Message(record.Name); Message(recordCopy.Name);
Message(lookup[1]); Message(mapCopy.Count());
Message(TypeOf(frozen) = Тип("ФиксированныйМассив"));
Message(TypeOf(record) = Type("FixedStructure"));
Message(TypeOf(lookup) = Type("FixedMap"));
Message(TypeOf(arrayCopy)); Message(TypeOf(recordCopy)); Message(TypeOf(mapCopy));
'''
        expected = ('2\n1\n10\n20\n1\nДа\n30\nёж\nёж\n7\n2\nДа\nёж\nНет\nДа\n'
                    'исходное\n1\nДа\nДа\n2\n2\nбулево\nчисло\nДа\n2\n10\n3\n'
                    'ёж\nкопия\nчисло\n3\nДа\nДа\nДа\nМассив\nСтруктура\nСоответствие\n')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Фиксированные.bsl'
            path.write_text(code, encoding='utf-8-sig')
            cases = [(('-c', code), None), ((str(path),), None),
                     (('-',), code), ((), code + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))

    def test_fixed_collection_mutations_and_invalid_operations_are_catchable(self):
        setup = ('a = New FixedArray(New Array(1));\n'
                 's = New FixedStructure("Name", "original");\n'
                 'm = New FixedMap(New Map); keys = New Map;\n'
                 'cyclic = New Array; cyclic.Add(cyclic);\n')
        actions = ['a[0] = 1', 's.Name = "changed"', 's["Name"] = "changed"',
                   'm[1] = 1', 'a.Add(1)', 'a.Добавить(1)', 'a.Set(0, 1)',
                   'a.Установить(0, 1)', 'a.Insert(0, 1)', 'a.Вставить(0, 1)',
                   'a.Delete(0)', 'a.Удалить(0)', 'a.Clear()', 'a.Очистить()',
                   's.Insert("Other", 1)', 's.Вставить("Other", 1)',
                   's.Delete("Name")', 's.Удалить("Name")',
                   's.Clear()', 's.Очистить()', 'm.Insert(1, 1)',
                   'm.Вставить(1, 1)', 'm.Delete(1)', 'm.Удалить(1)',
                   'm.Clear()', 'm.Очистить()']
        actions += ['m["missing"]', 'm[a]', 'New FixedArray(cyclic)', 'New FixedArray(a)',
                    'New FixedStructure(s)', 'New FixedMap(m)']
        code = setup + ''.join(f'Try\n{action};\nExcept\nMessage("blocked");\nEndTry;\n'
                               for action in actions)
        code += ('Message(a.Count()); Message(a[0] = Undefined);\n'
                 'Message(s.Name); Message(s.Count()); Message(m.Count()); Message(keys.Count());\n')
        expected = 'blocked\n' * len(actions) + '1\nДа\noriginal\n1\n0\n0\n'
        for arguments, stdin in [(('-c', code), None), (('-',), code),
                                 ((), code + '/exit\n')]:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, stdin=stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, expected, ''))

    def test_native_fixed_collection_contracts_work_across_cli_entry_points(self):
        code = '''
leaf = New Array; leaf.Add(5); root = New Array; root.Add(leaf);
fixed = New FixedArray(root); leaf[0] = 6;
Message(TypeOf(fixed[0]) = Type("FixedArray")); Message(fixed[0][0]);
copy = New Array(fixed); copy[0][0] = 7; Message(fixed[0][0]); Message(copy[0][0]);
Message(СтрСоединить(New FixedArray(StrSplit("а,б", ",")), ";"));
'''
        expected = 'Да\n5\n5\n7\nа;б\n'
        for constructor in ['New FixedArray(New Array(1))',
                            'New FixedStructure("Value", 1)', 'New FixedMap(New Map)']:
            code += f'''
first = {constructor}; other = {constructor}; alias = first;
Message(first = alias); Message(first = other); Message(first <> other);
bag = New Array; bag.Add(first); frozenBag = New FixedArray(bag);
Message(bag.Find(alias)); Message(frozenBag.Найти(alias));
Message(bag.Find(other) = Undefined);
keys = New Map; keys.Insert(first, 7); keys.Вставить(other, 8);
snapshot = New FixedMap(keys); keys.Удалить(alias);
Message(snapshot[alias]); Message(snapshot.Получить(other)); Message(keys.Count());
Message(snapshot.Get("missing") = Undefined);
Try snapshot["missing"]; Except Message("missing"); EndTry;
'''
            expected += 'Да\nНет\nДа\n0\n0\nДа\n7\n8\n1\nДа\nmissing\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'NativeFixed.bsl'
            path.write_text(code, encoding='utf-8-sig')
            for arguments, stdin in [(('-c', code), None), ((str(path),), None),
                                     (('-',), code), ((), code + '/exit\n')]:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))

    def test_fixed_collection_errors_command_file_and_stdin_diagnostics(self):
        cases = [('a = New FixedArray(New Array(1));', 'a[0] = 2;', 'недоступны для записи'),
                 ('s = New FixedStructure("Name", 1);', 's.Name = 2;', 'недоступно для записи'),
                 ('m = New FixedMap(New Map);', 'm[1] = 2;', 'недоступны для записи'),
                 ('a = New FixedArray(New Array(1));', 'a.Add(2);', 'не найдено: Add'),
                 ('s = New FixedStructure("Name", 1);', 's.Clear();', 'не найден: Clear'),
                 ('m = New FixedMap(New Map);', 'm.Insert(1, 2);', 'не найден: Insert'),
                 ('// incorrect source', 'New FixedArray(1);', 'ожидает массив'),
                 ('// incorrect source', 'New FixedStructure(1);', 'ожидает строку свойств или структуру'),
                 ('// incorrect source', 'New FixedMap(1);', 'ожидает соответствие')]
        cases = [(setup, action, message, 1) for setup, action, message in cases] + [
            ('m = New FixedMap(New Map);', 'm["missing"];',
             'Ключ фиксированного соответствия не найден', 2),
            ('a = New FixedArray(New Array); m = New FixedMap(New Map);', 'm[a];',
             'Ключ фиксированного соответствия не найден', 2),
            ('a = New Array; a.Add(a);', 'New FixedArray(a);',
             'ФиксированныйМассив с циклическими вложенными массивами пока не поддерживается', 1),
            ('s = New FixedStructure;', 'New FixedStructure(s);',
             'ФиксированнаяСтруктура ожидает строку свойств или структуру', 1),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / 'project'
            project.mkdir()
            path = project / 'ОшибкаФиксированной.bsl'
            for setup, action, message, column in cases:
                code = setup + '\n' + action + '\n'
                path.write_text(code, encoding='utf-8-sig')
                for arguments, stdin, source in [
                        (('-c', code), None, '<команда>'),
                        ((str(path.resolve()),), None, str(path.resolve())),
                        ((str(Path('project') / path.name),), None, str(Path('project') / path.name)),
                        (('-',), code, '<stdin>')]:
                    with self.subTest(action=action, source=source, arguments=arguments):
                        result = self.run_cli(*arguments, stdin=stdin, cwd=directory)
                        self.assertEqual((result.returncode, result.stdout), (1, ''))
                        self.assertIn(f'{source}:2:{column}:', result.stderr)
                        if not source.startswith('<'):
                            label = result.stderr.split(f':2:{column}:', 1)[0]
                            diagnostic_path = Path(label)
                            if not diagnostic_path.is_absolute():
                                diagnostic_path = directory / diagnostic_path
                            self.assertEqual(diagnostic_path.resolve(), path.resolve())
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_fixed_collection_console_multiline_state_and_error_recovery(self):
        code = '''Function Frozen(Val size)
Return New FixedArray(
New Array(size));
EndFunction
frozen = Frozen(2);
record = New FixedStructure(
"Name,Count", "сохранено", 7);
lookup = New FixedMap(New Map);
frozen[0] = 99;
frozen.Count()
record.Name = "потеряно";
record.Name
lookup[1] = 99;
lookup.Count()
frozen.Add(99);
frozen.UBound()
TypeOf(frozen)
Var value;
record.Property("NAME", value)
value
Try
record.Clear();
Except
Message("перехвачено");
EndTry;
copy = New Array(frozen);
copy[0] = 5;
copy[0]
(frozen[0] = Undefined)
/exit
'''
        result = self.run_cli(stdin=code)
        self.assertEqual((result.returncode, result.stdout),
                         (1, '2\nсохранено\n0\n1\nФиксированныйМассив\nДа\nсохранено\n'
                          'перехвачено\n5\nДа\n'))
        self.assertEqual(result.stderr.count('<консоль>:1:'), 4)
        self.assertEqual(result.stderr.count('недоступны для записи'), 2)
        self.assertIn('недоступно для записи', result.stderr)
        self.assertIn('не найдено: Add', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_fixed_collections_cross_imported_routines(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / 'project'
            project.mkdir()
            (project / 'Снимки.bsl').write_text(
                'Function Values() Export Return New FixedArray(New Array(2)); EndFunction\n'
                'Function Record() Export Return New FixedStructure("Name", "из модуля"); EndFunction\n'
                'Function Lookup() Export\n'
                'm = New Map; m["key"] = 42; Return New FixedMap(m);\nEndFunction\n',
                encoding='utf-8-sig')
            main = project / 'Основное.bsl'
            main.write_text('// #Импорт Снимки.bsl\n'
                            'a = Снимки.Values(); s = Снимки.Record(); m = Снимки.Lookup();\n'
                            'Message(a.Count()); Message(s.Name); Message(m["key"]);\n'
                            'Message(TypeOf(a)); Message(TypeOf(s)); Message(TypeOf(m));\n',
                            encoding='utf-8-sig')
            for path in (main, Path('project') / main.name):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=directory)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, '2\nиз модуля\n42\nФиксированныйМассив\n'
                                      'ФиксированнаяСтруктура\nФиксированноеСоответствие\n', ''))

    def test_imported_fixed_collection_errors_preserve_canonical_path(self):
        actions = [('a = New FixedArray(New Array(1));', 'a[0] = 99;', 'недоступны для записи'),
                   ('s = New FixedStructure("Name", 1);', 's.Name = 99;', 'недоступно для записи'),
                   ('m = New FixedMap(New Map);', 'm[1] = 99;', 'недоступны для записи')]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / 'project'
            project.mkdir()
            module = project / 'Фиксированные.bsl'
            main = project / 'Основное.bsl'
            for setup, action, message in actions:
                module.write_text('Procedure Fail() Export\n' + setup + '\n' + action +
                                  '\nEndProcedure\n', encoding='utf-8-sig')
                main.write_text('// #Импорт Фиксированные.bsl\nФиксированные.Fail();\n',
                                encoding='utf-8')
                with self.subTest(action=action):
                    result = self.run_cli(str(Path('project') / main.name), cwd=directory)
                    self.assertEqual((result.returncode, result.stdout), (1, ''))
                    self.assertIn(f'{module.resolve()}:3:', result.stderr)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    main.write_text('// #Импорт Фиксированные.bsl\nTry\nФиксированные.Fail();\n'
                                    'Except\nMessage(ErrorDescription());\nEndTry;\n'
                                    'Message("продолжено");\n', encoding='utf-8')
                    result = self.run_cli(str(main), cwd=directory)
                    self.assertEqual((result.returncode, result.stderr), (0, ''))
                    self.assertTrue(result.stdout.startswith(f'{module.resolve()}:3:'))
                    self.assertIn(message, result.stdout)
                    self.assertTrue(result.stdout.endswith('\nпродолжено\n'))

    def test_fixed_collection_file_diagnostic_identifies_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            actual = directory / 'actual'
            actual.mkdir()
            link = directory / 'linked'
            try:
                link.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('Symlinks are not available on this host')
            path = link / 'Ошибка.bsl'
            path.write_text('a = New FixedArray(New Array(1));\na[0] = 2;\n', encoding='utf-8-sig')
            result = self.run_cli(str(path), cwd=directory)
            self.assertEqual((result.returncode, result.stdout), (1, ''))
            self.assertIn(f'{path}:2:1:', result.stderr)
            label = result.stderr.split(':2:1:', 1)[0]
            self.assertEqual(Path(label).resolve(), (actual / path.name).resolve())
            self.assertIn('недоступны для записи', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_type_values_console_state_collections_and_multiline_calls(self):
        code = '''kind = Тип("число");
values = New Array;
values.Add(kind);
s = New Structure("Kind", values[0]);
m = New Map;
m[s.Kind] = "тип числа";
m["Число"] = "строковый ключ";
m[TypeOf(1)]
m["Число"]
m.Count()
values.Find(Type("Number"))
TypeOf(
kind)
(kind = "Число")
(TypeOf(True) = TypeOf(1))
Function Echo(Val item)
Return TypeOf(item);
EndFunction
Echo(s.Kind)
For Each pair In m Do
Message(TypeOf(pair) = Type("КлючИЗначение"));
EndDo;
/exit
'''
        result = self.run_cli(stdin=code)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, 'тип числа\nстроковый ключ\n2\n0\nТип\nНет\nНет\nТип\nДа\nДа\n', ''))

    def test_type_errors_are_catchable_in_command_stdin_and_console(self):
        code = '''Попытка
    Тип("СписокЗначений");
Исключение
    Сообщить("неизвестный тип");
КонецПопытки;
Try
    Type(1);
Except
    Message("имя не строка");
EndTry;
Try
    TypeOf(Message);
Except
    Message("внешнее значение");
EndTry;
Try
    Type("Number").value;
Except
    Message("непрозрачный тип");
EndTry;
Сообщить(ТипЗнч(Тип("Массив")));
'''
        for arguments, stdin in [(('-c', code), None), (('-',), code),
                                 ((), code + '/exit\n')]:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, stdin=stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, 'неизвестный тип\nимя не строка\nвнешнее значение\n'
                                  'непрозрачный тип\nТип\n', ''))

    def test_type_errors_have_clean_command_file_and_stdin_diagnostics(self):
        failures = [('Тип("СписокЗначений")', 'Тип не поддерживается: СписокЗначений'),
                    ('Type(1)', 'Имя типа должно быть строкой'),
                    ('TypeOf(Message)', 'ТипЗнч для этого значения пока не поддерживается')]
        with tempfile.TemporaryDirectory() as temporary:
            path = (Path(temporary) / 'ОшибкаТипа.bsl').resolve()
            for expression, message in failures:
                code = '// строка перед ошибкой\n' + expression + ';\n'
                path.write_text(code, encoding='utf-8-sig')
                cases = [(('-c', code), None, '<команда>'),
                         ((str(path),), None, str(path)),
                         (('-',), code, '<stdin>')]
                for arguments, stdin, source in cases:
                    with self.subTest(expression=expression, source=source):
                        result = self.run_cli(*arguments, stdin=stdin)
                        self.assertEqual((result.returncode, result.stdout), (1, ''))
                        self.assertIn(source + ':2:', result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_type_console_recovers_without_overwriting_existing_value(self):
        result = self.run_cli(stdin='kind = Type("Array");\n'
                                   'kind = Type("ValueList");\nkind\n'
                                   'TypeOf(Message)\nTypeOf(kind)\n'
                                   'Message(TypeOf(New Array) = kind);\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, 'Массив\nТип\nДа\n'))
        self.assertEqual(result.stderr.count('<консоль>:1:'), 2)
        self.assertIn('Тип не поддерживается: ValueList', result.stderr)
        self.assertIn('ТипЗнч для этого значения пока не поддерживается', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_type_values_cross_imported_routines_and_map_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / 'project'
            project.mkdir()
            (project / 'Побочное.bsl').write_text(
                'Function Kind(Val value) Export Return TypeOf(value); EndFunction\n'
                'Function Mapping() Export\n'
                'm = New Map; m[Тип("Число")] = Тип("Строка"); Return m;\n'
                'EndFunction\n'
                'Procedure SetKind(value) Export value = Type("Array"); EndProcedure\n',
                encoding='utf-8-sig')
            main = project / 'Основное.bsl'
            main.write_text('// #Импорт Побочное.bsl\n'
                            'kind = Тип("Булево"); Побочное.SetKind(kind);\n'
                            'Сообщить(kind); Сообщить(Побочное.Kind(kind));\n'
                            'm = Побочное.Mapping(); Сообщить(m[TypeOf(42)]);\n'
                            'Сообщить(m[Тип("Число")] = Type("String"));\n', encoding='utf-8-sig')
            for path in (main, Path('project') / main.name):
                with self.subTest(path=path):
                    result = self.run_cli(str(path), cwd=directory)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, 'Массив\nТип\nСтрока\nДа\n', ''))

    def test_imported_type_errors_preserve_canonical_path_and_are_catchable(self):
        failures = [('Type("ValueList")', 12, 'Тип не поддерживается: ValueList'),
                    ('TypeOf(Message)', 14, 'ТипЗнч для этого значения пока не поддерживается')]
        for expression, column, message in failures:
            with self.subTest(expression=expression), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                module = directory / 'Побочное.bsl'
                module.write_text('Function Kind() Export\n'
                                  f'Return {expression};\nEndFunction\n', encoding='utf-8-sig')
                main = directory / 'Основное.bsl'
                main.write_text('// #Импорт Побочное.bsl\nПобочное.Kind();\n', encoding='utf-8')
                result = self.run_cli(str(main))
                self.assertEqual((result.returncode, result.stdout), (1, ''))
                self.assertIn(f'{module.resolve()}:2:', result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                main.write_text('// #Импорт Побочное.bsl\nTry\nПобочное.Kind();\n'
                                'Except\nMessage(ErrorDescription());\nEndTry;\n'
                                'Message(TypeOf(1) = Type("Число"));\n', encoding='utf-8')
                result = self.run_cli(str(main))
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertEqual(result.stdout,
                                 f'{module.resolve()}:2:{column}: {message}\nДа\n')

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
                     ((str(path.resolve()),), None, str(path.resolve())),
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
                     ((str(path.resolve()),), None, str(path.resolve())),
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
        result = self.run_cli("basic.bsl", "-c", "")
        self.assertEqual(result.returncode, 2)
        self.assertIn("нельзя", result.stderr)

    def test_missing_file_and_unknown_encoding(self):
        for arguments in (("missing.bsl",),
                          ("--encoding", "no-such-codec", "basic.bsl")):
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

"""Optional file context on every CLI entry point, with secret-free auth errors.

The .1CD fixture has recognized header geometry, not a real/native database.
All source fixtures and subprocess input are explicitly UTF-8 with binary LF.
"""
import os
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
AUTH_ERROR = "yadinassi: authentication options --user/--psw are not supported\n"
EMPTY_DATABASE_ERROR = "yadinassi: --f requires a non-empty directory\n"
NO_DATABASE = "db required for further code execution"


def run_cli(*arguments, stdin=None, cwd=ROOT):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT), environment.get("PYTHONPATH")]))
    result = subprocess.run([sys.executable, "-m", "yadinassi", *arguments],
                            input=None if stdin is None else stdin.encode("utf-8"),
                            capture_output=True, cwd=cwd, env=environment, timeout=10)
    # Console line endings are host-dependent; source/input bytes above are not.
    return SimpleNamespace(returncode=result.returncode,
                           stdout=result.stdout.decode("utf-8").replace("\r\n", "\n"),
                           stderr=result.stderr.decode("utf-8").replace("\r\n", "\n"))


def write_source(path, code):
    path.write_bytes(code.encode("utf-8"))
    return path


def make_header_fixture(directory):
    directory.mkdir()
    raw = (b"1CDBMSV8" + bytes((8, 3, 8, 0)) + (3).to_bytes(4, "little")
           + b"\0" * 4 + (4096).to_bytes(4, "little"))
    with (directory / "1Cv8.1CD").open("wb") as stream:
        stream.write(raw)
        stream.truncate(3 * 4096)
    return directory


class DatabaseAuthCLITests(unittest.TestCase):
    def test_empty_database_is_fixed_usage_error_before_help_parsing_or_execution(self):
        for empty in (("--f", ""), ("--f=",)):
            for other in (("-c", 'Message("MUST_NOT_EXECUTE");'), ("--help",),
                          ("--version",), ("--unknown=private-other",)):
                for arguments in (empty + other, other + empty):
                    with self.subTest(arguments=arguments):
                        result = run_cli(*arguments)
                        self.assertEqual((result.returncode, result.stdout, result.stderr),
                                         (2, "", EMPTY_DATABASE_ERROR))
            result = run_cli(*empty, "--psw=private-value")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (2, "", AUTH_ERROR))

    def test_empty_database_does_not_construct_context_interpreter_or_read_source(self):
        from yadinassi import cli
        for arguments in (("--f", "", "missing.bsl"), ("--f=", "missing.bsl")):
            with self.subTest(arguments=arguments), \
                 mock.patch.object(cli, "FileDBContext") as context, \
                 mock.patch.object(cli, "Interpreter") as interpreter, \
                 mock.patch.object(cli.Path, "read_text") as read_source, \
                 redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(cli.main(list(arguments)), 2)
                self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", EMPTY_DATABASE_ERROR))
                context.assert_not_called()
                interpreter.assert_not_called()
                read_source.assert_not_called()

    def test_empty_database_scan_excludes_source_and_option_boundary(self):
        from yadinassi.cli import _has_empty_database_option
        for flag in ("-c", "-с", "--command"):
            self.assertFalse(_has_empty_database_option([flag, "--f=", ""]))
            self.assertFalse(_has_empty_database_option([flag, "--f", ""]))
        for arguments in (("--command=--f=",), ("--", "--f=",), ("--", "--f", "")):
            self.assertFalse(_has_empty_database_option(list(arguments)))
        with tempfile.TemporaryDirectory() as temporary:
            write_source(Path(temporary) / "--f=", "Message(42);\n")
            result = run_cli("--", "--f=", cwd=temporary)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))

    def test_auth_rejected_without_values_before_source_help_or_parse_errors(self):
        code = 'Message("MUST_NOT_EXECUTE");'
        for flag in ("--user", "--psw"):
            for auth in ((flag, "private-value-Ж"), (flag + "=private-value-Ж",),
                         (flag, ""), (flag + "=",), (flag,)):
                for other in (("-c", code), ("--help",), ("--version",),
                              ("--unknown=private-other",), ("--f",)):
                    for arguments in (auth + other, other + auth):
                        with self.subTest(arguments=arguments):
                            result = run_cli(*arguments)
                            self.assertEqual((result.returncode, result.stdout, result.stderr),
                                             (2, "", AUTH_ERROR))

    def test_auth_after_malformed_options_and_repeated_commands(self):
        for arguments in (("--f", "--user", "private"),
                          ("--encoding", "--psw=private"),
                          ("-c", "Message(1);", "--command=Message(2);", "--psw", "private"),
                          ("-c", "--user=source-literal", "--psw=private")):
            with self.subTest(arguments=arguments):
                result = run_cli(*arguments)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (2, "", AUTH_ERROR))

    def test_auth_scan_distinguishes_command_operands_and_option_boundary(self):
        from yadinassi.cli import _has_auth_option
        for flag in ("-c", "-с", "--command"):
            for value in ("--user", "--psw=code-not-credentials", "--user="):
                with self.subTest(flag=flag, value=value):
                    self.assertFalse(_has_auth_option([flag, value]))
                    result = run_cli(flag, value)
                    self.assertNotIn(AUTH_ERROR.strip(), result.stderr)
            self.assertFalse(_has_auth_option([flag, "--", "--psw=filename"]))
        for arguments in (("--command=--user",), ("--command=--psw=code",),
                          ("-c--user",), ("-с--psw",),
                          ("--", "--user", "--psw=filename"),
                          ("--f=--user",), ("--encoding=--psw",)):
            with self.subTest(arguments=arguments):
                self.assertFalse(_has_auth_option(list(arguments)))

    def test_auth_looking_source_and_filename_are_not_rejected(self):
        code = '// --psw=source-comment\nMessage("--user=source-text");\n'
        for flag in ("-c", "-с", "--command"):
            result = run_cli(flag, code)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "--user=source-text\n", ""))
        result = run_cli("--command=" + code)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "--user=source-text\n", ""))
        with tempfile.TemporaryDirectory() as temporary:
            write_source(Path(temporary) / "--user", "Message(42);\n")
            result = run_cli("--", "--user", cwd=temporary)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))


class DatabaseContextCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.database = make_header_fixture(self.root / "База с пробелами")
        self.source = self.root / "Код.bsl"

    def entry_points(self, code):
        write_source(self.source, code)
        return [((flag, code), None) for flag in ("-c", "-с", "--command")] + [
            ((str(self.source),), None), (("-",), code), ((), code + "/exit\n")]

    def assert_success(self, arguments, stdin, expected):
        result = run_cli(*arguments, stdin=stdin, cwd=self.root)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, ""))

    def test_without_database_all_inputs_still_execute_arithmetic(self):
        code = 'Message(6 * 7);\n'
        for arguments, stdin in self.entry_points(code):
            with self.subTest(arguments=arguments):
                self.assert_success(arguments, stdin, "42\n")

    def test_database_context_all_inputs_preserves_aliases_and_client_default(self):
        code = ('Message(InfoBaseConnectionString());\n'
                'Message(СтрокаСоединенияИнформационнойБазы());\n'
                '#If AtClient Then\nMessage("client");\n#Else\nMessage("wrong");\n#EndIf\n')
        expected = (f'File="{self.database}";\n' * 2) + "client\n"
        before = (self.database / "1Cv8.1CD").read_bytes()
        for arguments, stdin in self.entry_points(code):
            with self.subTest(arguments=arguments):
                self.assert_success(("--f", str(self.database), *arguments), stdin, expected)
        self.assertEqual((self.database / "1Cv8.1CD").read_bytes(), before)

    def test_relative_database_is_anchored_at_startup_cwd_not_script_directory(self):
        project = self.root / "project"
        project.mkdir()
        source = write_source(project / "main.bsl", "Message(InfoBaseConnectionString());\n")
        result = run_cli(str(source), "--f", "./База с пробелами/../База с пробелами/.", cwd=self.root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, f'File="{self.database}";\n', ""))

    def test_missing_database_is_catchable_in_all_inputs_and_aliases(self):
        code = ('Try InfoBaseConnectionString(); Except Message(ErrorInfo().Description); EndTry;\n'
                'Попытка СтрокаСоединенияИнформационнойБазы(); '
                'Исключение Сообщить(ИнформацияОбОшибке().Описание); КонецПопытки;\n'
                'Message(42);\n')
        for arguments, stdin in self.entry_points(code):
            with self.subTest(arguments=arguments):
                self.assert_success(arguments, stdin, (NO_DATABASE + "\n") * 2 + "42\n")

    def test_bad_context_is_lazy_for_arithmetic_and_untaken_calls(self):
        code = ('If False Then InfoBaseConnectionString(); EndIf;\n'
                'Message(?(True, 42, СтрокаСоединенияИнформационнойБазы()));\n')
        for path in (str(self.root / "missing"), str(self.source), 'bad"path', "bad;path", "bad\npath"):
            for arguments, stdin in self.entry_points(code):
                with self.subTest(path=path, arguments=arguments):
                    self.assert_success(("--f", path, *arguments), stdin, "42\n")

    def test_bad_context_does_not_replace_syntax_error(self):
        result = run_cli("--f", 'bad"path', "-c", "@", cwd=self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Неожиданный символ", result.stderr)
        self.assertNotIn("database", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_or_unrecognized_header_fails_only_on_call_and_is_catchable(self):
        invalid = self.root / "unrecognized"
        invalid.mkdir()
        (invalid / "1Cv8.1CD").write_bytes(b"not a database")
        code = ('Try InfoBaseConnectionString(); Except Message("caught"); EndTry;\n'
                'Message(42);\n')
        for directory in (self.root / "missing", invalid):
            result = run_cli("--f", str(directory), "-c", code, cwd=self.root)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "caught\n42\n", ""))

    def test_uncaught_missing_database_reports_source_and_console_recovers(self):
        result = run_cli("-c", "\nInfoBaseConnectionString();", cwd=self.root)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("<команда>:2:", result.stderr)
        self.assertIn(NO_DATABASE, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        result = run_cli(stdin="InfoBaseConnectionString()\n6 * 7\n/exit\n", cwd=self.root)
        self.assertEqual((result.returncode, result.stdout), (1, "42\n"))
        self.assertIn("<консоль>:1:", result.stderr)
        self.assertIn(NO_DATABASE, result.stderr)

    def test_help_and_version_do_not_validate_database(self):
        for option in ("--help", "--version"):
            result = run_cli("--f", 'bad"path', option, cwd=self.root)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
        result = run_cli("--help")
        self.assertIn("--f DIRECTORY", result.stdout)


if __name__ == "__main__":
    unittest.main()

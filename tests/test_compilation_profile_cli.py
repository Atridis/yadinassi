"""UTF-8 CLI entry points for explicit compilation profiles, not native evidence."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter, cli
from yadinassi.parser import parse
from yadinassi.preprocessor import COMPILATION_PROFILES


ROOT = Path(__file__).resolve().parents[1]
AUTH_ERROR = "yadinassi: authentication options --user/--psw are not supported\n"
PROGRAM = """#If ThinClient Or ВебКлиент Or ThickClientOrdinaryApplication Or ТолстыйКлиентУправляемоеПриложение Or ExternalConnection Then
invalid !!! syntax "
// #Import Missing.bsl
#Else
#If AtClient And Client And Not Server And Not AtServer Then
Message("standalone:Я😀");
#Else
Message("wrong-context");
#EndIf
#EndIf
"""


def run_cli(*arguments, stdin=None, cwd=ROOT):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(ROOT), environment.get("PYTHONPATH"))))
    return subprocess.run([sys.executable, "-B", "-m", "yadinassi", *arguments],
                          input=stdin, text=True, encoding="utf-8", errors="strict",
                          capture_output=True, cwd=cwd, env=environment, timeout=15)


class CompilationProfileCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="compilation-profile-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "Профиль с пробелами.bsl"
        self.source.write_text(PROGRAM, encoding="utf-8")

    def entry_points(self):
        return [((flag, PROGRAM), None) for flag in ("-c", "-с", "--command")] + [
            ((str(self.source),), None), (("-",), PROGRAM), ((), PROGRAM + "/exit\n")]

    def test_default_and_explicit_profile_work_for_every_entry_point(self):
        for profile in ((), ("--preprocessor-profile", "standalone"),
                        ("--preprocessor-profile=standalone",)):
            for arguments, stdin in self.entry_points():
                with self.subTest(profile=profile, arguments=arguments):
                    result = run_cli(*profile, *arguments, stdin=stdin, cwd=self.root)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, "standalone:Я😀\n", ""))

    def test_bom_file_and_non_utf8_host_locale_still_use_explicit_utf8(self):
        self.source.write_text("\ufeff" + PROGRAM, encoding="utf-8")
        with mock.patch("subprocess._text_encoding", return_value="cp1252"):
            file_result = run_cli("--preprocessor-profile", "standalone", str(self.source),
                                  cwd=self.root)
            stdin_result = run_cli("--preprocessor-profile", "standalone", "-",
                                   stdin=PROGRAM, cwd=self.root)
        for result in (file_result, stdin_result):
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "standalone:Я😀\n", ""))

    def test_unsupported_profile_identifiers_are_usage_errors_before_source_effects(self):
        for value in ("", "Standalone", "STANDALONE", "standalone ", " standalone",
                      "client", "server", "auto", "native", '{"Client":true}'):
            with self.subTest(value=value):
                result = run_cli("--preprocessor-profile", value, "-c",
                                 'Message("MUST_NOT_EXECUTE");', cwd=self.root)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("--preprocessor-profile", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        result = run_cli("--preprocessor-profile", cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_invalid_profile_does_not_construct_interpreter_or_read_file(self):
        with mock.patch.object(cli, "Interpreter") as constructor, \
                mock.patch.object(cli.Path, "read_text") as read_source, \
                redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as caught:
            cli.main(["--preprocessor-profile", "native", str(self.source)])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        constructor.assert_not_called()
        read_source.assert_not_called()

    def test_cli_explicitly_supplies_default_and_selected_profile_to_interpreter(self):
        for arguments in (("-c", "42"),
                          ("--preprocessor-profile", "standalone", "--command", "42")):
            with self.subTest(arguments=arguments), \
                    mock.patch.object(cli, "Interpreter", wraps=Interpreter) as constructor, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(list(arguments)), 0)
            self.assertEqual(constructor.call_count, 1)
            self.assertEqual(constructor.call_args.kwargs.get("compilation_profile"), "standalone")

    def test_repl_preparse_explicitly_supplies_profile_on_every_continuation(self):
        output = []
        interpreter = Interpreter(output.append, compilation_profile="standalone")
        self.addCleanup(interpreter.close)
        with mock.patch.object(cli, "parse", wraps=parse) as parser, \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("builtins.input", side_effect=[*PROGRAM.splitlines(), "/exit"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(cli.repl(interpreter), 0)
        self.assertEqual(output, ["standalone:Я😀"])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(parser.call_count, len(PROGRAM.splitlines()))
        for call in parser.call_args_list:
            self.assertEqual(call.kwargs.get("compilation_profile"), "standalone")

    def test_unknown_condition_precedes_effects_for_file_command_and_stdin(self):
        code = ('Message("MUST_NOT_EXECUTE");\n#If ThinClient Then\n'
                "#If MobileClient Then\n#EndIf\n#EndIf\n")
        self.source.write_text(code, encoding="utf-8")
        entries = [((flag, code), None) for flag in ("-c", "-с", "--command")]
        entries.extend((((str(self.source),), None), (("-",), code)))
        for arguments, stdin in entries:
            with self.subTest(arguments=arguments):
                result = run_cli("--preprocessor-profile", "standalone", *arguments,
                                 stdin=stdin, cwd=self.root)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("Неподдерживаемый символ", result.stderr)
                self.assertIn("MobileClient", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_repl_recovers_from_unknown_profile_symbol(self):
        result = run_cli("--preprocessor-profile", "standalone", stdin=(
            "#If MobileClient Then\nMessage(42);\n/exit\n"), cwd=self.root)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "42\n")
        self.assertIn("Неподдерживаемый символ", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_auth_guard_precedes_profile_validation_help_and_execution_without_echo(self):
        secret = "synthetic-do-not-echo-Ж"
        for authentication in (("--user", secret), ("--psw=" + secret,),
                               ("--user",), ("--psw", "")):
            for other in (("--preprocessor-profile", "standalone", "-c",
                           'Message("MUST_NOT_EXECUTE");'),
                          ("--preprocessor-profile", "native"),
                          ("--preprocessor-profile",),
                          ("--preprocessor-profile", "standalone", "--help"),
                          ("--preprocessor-profile", "standalone", "--version")):
                for arguments in (authentication + other, other + authentication):
                    with self.subTest(arguments=arguments):
                        result = run_cli(*arguments, cwd=self.root)
                        self.assertEqual((result.returncode, result.stdout, result.stderr),
                                         (2, "", AUTH_ERROR))
                        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_auth_guard_does_not_construct_or_read_sources_with_profile(self):
        with mock.patch.object(cli, "Interpreter") as constructor, \
                mock.patch.object(cli.Path, "read_text") as read_source, \
                redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            result = cli.main(["--preprocessor-profile", "standalone", "--psw=synthetic-secret",
                               str(self.source)])
        self.assertEqual((result, stdout.getvalue(), stderr.getvalue()), (2, "", AUTH_ERROR))
        constructor.assert_not_called()
        read_source.assert_not_called()

    def test_profile_does_not_make_source_literals_or_option_boundary_into_auth_options(self):
        code = '// --psw=source-comment\nMessage("--user=source-text");\n'
        for flag in ("-c", "-с", "--command"):
            with self.subTest(flag=flag):
                result = run_cli("--preprocessor-profile", "standalone", flag, code, cwd=self.root)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, "--user=source-text\n", ""))
        (self.root / "--user").write_text("Message(42);\n", encoding="utf-8")
        result = run_cli("--preprocessor-profile", "standalone", "--", "--user", cwd=self.root)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "42\n", ""))


MANAGED_PROFILE = "managed-thick-file"
MANAGED_PROGRAM = """#If Client And Server And ThickClientManagedApplication Then
#If AtClient And Not AtServer And Not (ThinClient Or WebClient Or ThickClientOrdinaryApplication Or ExternalConnection) Then
Message("managed:Я😀");
#Else
Message("wrong-context");
#EndIf
#Else
// #Import Missing.bsl
invalid !!! syntax "
#EndIf
"""


class ManagedCompilationProfileCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="managed-profile-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "Управляемый профиль с пробелами.bsl"
        self.source.write_text(MANAGED_PROGRAM, encoding="utf-8")

    def test_explicit_profile_in_command_file_stdin_and_console(self):
        entries = [((flag, MANAGED_PROGRAM), None) for flag in ("-c", "-с", "--command")]
        entries.extend((((str(self.source),), None), (("-",), MANAGED_PROGRAM),
                        ((), MANAGED_PROGRAM + "/exit\n")))
        for profile in (("--preprocessor-profile", MANAGED_PROFILE),
                        ("--preprocessor-profile=" + MANAGED_PROFILE,)):
            for arguments, stdin in entries:
                with self.subTest(profile=profile, arguments=arguments):
                    result = run_cli(*profile, *arguments, stdin=stdin, cwd=self.root)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, "managed:Я😀\n", ""))
        self.source.write_text("\ufeff" + MANAGED_PROGRAM, encoding="utf-8")
        result = run_cli("--preprocessor-profile", MANAGED_PROFILE, str(self.source), cwd=self.root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "managed:Я😀\n", ""))

    def test_help_uses_closed_profile_choices_and_rejects_approximate_identifiers(self):
        result = run_cli("--help", cwd=self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("{" + ",".join(COMPILATION_PROFILES) + "}", result.stdout)
        for value in ("Managed-Thick-File", "managed_thick_file", "managed-thick-file ",
                      " managed-thick-file", "managed-thick", "MANAGED-THICK-FILE"):
            with self.subTest(value=value):
                result = run_cli("--preprocessor-profile", value, "-c",
                                 'Message("MUST_NOT_EXECUTE");', cwd=self.root)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("--preprocessor-profile", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_cli_and_repl_pass_explicit_profile_without_changing_root_context(self):
        with mock.patch.object(cli, "Interpreter", wraps=Interpreter) as constructor, \
                redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(cli.main(["--preprocessor-profile", MANAGED_PROFILE,
                                       "--command", MANAGED_PROGRAM]), 0)
        self.assertEqual(constructor.call_args.kwargs.get("compilation_profile"), MANAGED_PROFILE)
        self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("managed:Я😀\n", ""))
        output = []
        interpreter = Interpreter(output.append, compilation_profile=MANAGED_PROFILE)
        self.addCleanup(interpreter.close)
        with mock.patch.object(cli, "parse", wraps=parse) as parser, \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("builtins.input", side_effect=[*MANAGED_PROGRAM.splitlines(), "/exit"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(cli.repl(interpreter), 0)
        self.assertEqual(output, ["managed:Я😀"])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(parser.call_count, len(MANAGED_PROGRAM.splitlines()))
        self.assertEqual(interpreter.execution_context, "client")
        for call in parser.call_args_list:
            self.assertEqual(call.kwargs.get("compilation_profile"), MANAGED_PROFILE)

    def test_managed_profile_does_not_create_database_context_or_allow_authentication(self):
        result = run_cli("--preprocessor-profile", MANAGED_PROFILE, "-c",
                         "InfoBaseConnectionString()", cwd=self.root)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("db required for further code execution", result.stderr)
        for arguments in (("--user", "synthetic-secret"), ("--psw=synthetic-secret",)):
            result = run_cli("--preprocessor-profile", MANAGED_PROFILE, *arguments,
                             "-c", 'Message("MUST_NOT_EXECUTE");', cwd=self.root)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (2, "", AUTH_ERROR))

    def test_unknown_combined_symbols_fail_before_effects_and_console_recovers(self):
        for symbol in ("ClientAtServer", "AtClientAtServer", "НаКлиентеНаСервере"):
            code = f'Message("MUST_NOT_EXECUTE");\n#If Client Or {symbol} Then\n#EndIf\n'
            self.source.write_text(code, encoding="utf-8")
            for arguments, stdin in ((("-c", code), None), ((str(self.source),), None),
                                     (("-",), code)):
                with self.subTest(symbol=symbol, arguments=arguments):
                    result = run_cli("--preprocessor-profile", MANAGED_PROFILE, *arguments,
                                     stdin=stdin, cwd=self.root)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("Неподдерживаемый символ", result.stderr)
                    self.assertIn(symbol, result.stderr)
            result = run_cli("--preprocessor-profile", MANAGED_PROFILE,
                             stdin=f"#If {symbol} Then\nMessage(42);\n/exit\n", cwd=self.root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "42\n")
            self.assertIn("Неподдерживаемый символ", result.stderr)


if __name__ == "__main__":
    unittest.main()

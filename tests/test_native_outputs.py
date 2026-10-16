"""Compare yadinassi with saved 1C output, without running 1C or writing goldens."""

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integrational_tests.test_launcher import LaunchError, collect_scripts


ROOT = Path(__file__).resolve().parents[1] / "integrational_tests"
# Normalize each message before writing bytes: Windows stdout translation must not
# turn an embedded CRLF into CRCRLF. A child process also bounds loops/isolates state.
EXECUTE_SCRIPT = r'''
import sys
from pathlib import Path
from yadinassi import Interpreter


def emit(message):
    message = message.replace("\r\n", "\n").replace("\r", "\n")
    sys.stdout.buffer.write((message + "\n").encode("utf-8"))


script = Path(sys.argv[1])
Interpreter(output=emit).execute(script.read_text(encoding="utf-8-sig"), str(script))
'''


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


class NativeOutputTests(unittest.TestCase):
    native_root = ROOT
    maxDiff = None

    def test_native_outputs(self):
        try:
            scripts = collect_scripts(self.native_root / "tests")
        except (LaunchError, OSError) as error:
            self.fail(f"Не удалось найти нативные BSL-тесты: {error}")
        for script in scripts:
            with self.subTest(script=script.name):
                self.compare_script(script)

    def compare_script(self, script: Path) -> None:
        expected_path = self.native_root / "output" / (script.stem + ".out")
        error_path = expected_path.with_suffix(".err")
        if error_path.exists():
            self.fail(f"Нативный запуск завершился ошибкой: {error_path}. "
                      "Проверьте ошибку и заново выполните тест на реальной 1С.")
        if not expected_path.is_file():
            self.fail(f"Нет нативного результата: {expected_path}. "
                      "Сначала сгенерируйте .out на реальной 1С.")
        try:
            # Decode explicitly: only line-ending transport differences are ignored.
            expected = normalize_newlines(expected_path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeError) as error:
            self.fail(f"Не удалось прочитать нативный результат {expected_path}: {error}")
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            result = subprocess.run(
                [sys.executable, "-c", EXECUTE_SCRIPT, str(script)],
                cwd=ROOT.parent, env=environment, capture_output=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            self.fail(f"Yadinassi не выполнил {script}: истек таймаут 10 с.")
        except OSError as error:
            self.fail(f"Не удалось запустить Yadinassi для {script}: {error}")
        self.assertEqual(result.returncode, 0,
                         f"Yadinassi не выполнил {script}:\n"
                         + result.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(result.stderr, b"", f"Неожиданный stderr при исполнении {script}")
        actual = result.stdout.decode("utf-8")
        self.assertMultiLineEqual(
            expected, actual,
            f"{script.name}: вывод отличается (- 1С: {expected_path}; + Yadinassi). "
            "Если исходник менялся, сначала обновите результат на реальной 1С; "
            "свежесть .out автоматически не проверяется.",
        )


class NativeOutputRunnerTests(unittest.TestCase):
    """Exercise the runner with synthetic, temporary fixtures, never repository goldens."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native output пробел ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "tests").mkdir()
        (self.root / "output").mkdir()

    def add_case(self, name="sample.bsl", code='Сообщить("Привет");',
                 output="Привет\n".encode("utf-8")):
        script = self.root / "tests" / name
        script.write_text(code, encoding="utf-8-sig", newline="\n")
        if output is not None:
            (self.root / "output" / (script.stem + ".out")).write_bytes(output)
        return script

    def run_comparison(self):
        case = NativeOutputTests("test_native_outputs")
        case.native_root = self.root
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(case)
        return result, stream.getvalue()

    def assert_comparison_passes(self):
        result, report = self.run_comparison()
        self.assertTrue(result.wasSuccessful(), report)

    def assert_comparison_fails(self, *details):
        result, report = self.run_comparison()
        self.assertFalse(result.wasSuccessful(), report)
        self.assertEqual(result.errors, [], report)
        for detail in details:
            self.assertIn(detail, report)
        return result, report

    def test_utf8_bom_source_unicode_paths_and_checkout_newlines(self):
        self.add_case("Пробел в имени.BSL", 'Сообщить(" Привет "); Сообщить("");',
                      " Привет \r\n\r\n".encode("utf-8"))
        self.assert_comparison_passes()

    def test_message_serialization_preserves_blank_lines_and_spaces(self):
        self.add_case(code='Сообщить(" первая\r\n|вторая \r|третья\n|"); Сообщить("");',
                      output=" первая\nвторая \nтретья\n\n\n".encode("utf-8"))
        self.assert_comparison_passes()
        # CRLF/lone CR in messages follow the native launcher's transport contract.
        self.assertEqual(normalize_newlines(" a\r\nb\rc\n\n "), " a\nb\nc\n\n ")

    def test_no_messages_is_different_from_one_empty_message(self):
        self.add_case("none.bsl", "// Нет сообщений", b"")
        self.add_case("empty.bsl", 'Сообщить("");', b"\n")
        self.assert_comparison_passes()
        (self.root / "output" / "none.out").write_bytes(b"\n")
        (self.root / "output" / "empty.out").write_bytes(b"")
        result, _ = self.assert_comparison_fails("none.bsl", "empty.bsl", "вывод отличается")
        self.assertEqual(len(result.failures), 2)

    def test_meaningful_whitespace_unicode_and_final_newline_are_not_trimmed(self):
        for expected in (b"value", b"value \n", b" value\n", b"value\n\n",
                         "value\u00a0\n".encode(), "\ufeffvalue\n".encode()):
            with self.subTest(expected=expected):
                self.add_case(code='Сообщить("value");', output=expected)
                self.assert_comparison_fails("sample.bsl", "вывод отличается", "свежесть .out")

    def test_missing_output_requires_native_generation_before_execution(self):
        self.add_case(code="@", output=None)
        self.assert_comparison_fails("sample.out", "сгенерируйте .out на реальной 1С")
        self.assertFalse((self.root / "output" / "sample.out").exists())

    def test_native_error_marker_rejects_partial_or_missing_output(self):
        for output in (b"partial\n", None):
            with self.subTest(output=output):
                self.add_case(code="@", output=output)
                if output is None:
                    (self.root / "output" / "sample.out").unlink()
                (self.root / "output" / "sample.err").write_bytes(b"")
                self.assert_comparison_fails("sample.err", "Нативный запуск завершился ошибкой")

    def test_invalid_utf8_output_and_source_fail_clearly(self):
        script = self.add_case(output=b"\xff")
        self.assert_comparison_fails("Не удалось прочитать нативный результат", "sample.out")
        (self.root / "output" / "sample.out").write_bytes(b"")
        script.write_bytes(b"\xff")
        self.assert_comparison_fails("Yadinassi не выполнил", "sample.bsl")

    def test_parse_and_runtime_errors_fail_even_if_partial_output_matches(self):
        for code in ("@", 'Сообщить("partial"); ВызватьИсключение "ошибка";'):
            with self.subTest(code=code):
                self.add_case(code=code, output=b"partial\n")
                self.assert_comparison_fails("Yadinassi не выполнил", "sample.bsl")

    def test_every_script_uses_fresh_interpreter_and_source_path(self):
        self.add_case("first.bsl", "x = 5;", b"")
        self.add_case("second.bsl", "Сообщить(x);", b"5\n")
        result, report = self.assert_comparison_fails("second.bsl", "Yadinassi не выполнил")
        self.assertEqual(len(result.failures), 1, report)
        self.assertIn(str(self.root / "tests" / "second.bsl") + ":1:", report)

    def test_discovery_matches_native_launcher_and_continues_after_failure(self):
        for name in ("z.bsl", "B.BSL", "a.bsl"):
            self.add_case(name, output=None)
        self.add_case("ignored.txt", output=None)
        nested = self.root / "tests" / "nested"
        nested.mkdir()
        (nested / "ignored.bsl").write_text("@", encoding="utf-8")
        (self.root / "output" / "orphan.out").write_bytes(b"ignored")
        result, report = self.assert_comparison_fails("a.bsl", "B.BSL", "z.bsl")
        self.assertEqual(len(result.failures), 3, report)
        self.assertEqual([case.params["script"] for case, _ in result.failures],
                         ["a.bsl", "B.BSL", "z.bsl"])

    def test_empty_suite_and_case_insensitive_stem_collisions_fail(self):
        self.assert_comparison_fails("нет .bsl-тестов")
        self.add_case("same.bsl")
        self.add_case("same.BSL")
        # On case-insensitive filesystems the second path aliases the first.
        if len(list((self.root / "tests").iterdir())) == 2:
            self.assert_comparison_fails("совпадают без учета регистра")
        else:
            paths = [self.root / "tests" / "same.bsl", self.root / "tests" / "same.BSL"]
            with patch.object(Path, "iterdir", return_value=iter(paths)), \
                    patch.object(Path, "is_file", return_value=True):
                self.assert_comparison_fails("совпадают без учета регистра")

    def test_missing_test_directory_fails(self):
        (self.root / "tests").rmdir()
        self.assert_comparison_fails("Не удалось найти нативные BSL-тесты")

    def test_timeout_and_process_start_failure_are_reported(self):
        self.add_case()
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("test", 10)):
            self.assert_comparison_fails("sample.bsl", "истек таймаут 10 с")
        with patch.object(subprocess, "run", side_effect=OSError("test start failure")):
            self.assert_comparison_fails("sample.bsl", "Не удалось запустить Yadinassi")

    def test_comparison_never_changes_input_or_native_results(self):
        self.add_case()
        (self.root / "meta.md").write_text("test metadata\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assert_comparison_passes()
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*")
                                  if path.is_file()})


if __name__ == "__main__":
    unittest.main()

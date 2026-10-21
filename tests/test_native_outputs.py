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
source = Path(sys.argv[2]) if len(sys.argv) > 2 else script
Interpreter(output=emit).execute(source.read_text(encoding="utf-8-sig"), str(script))
'''


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


from scripts.native_historical_replay import (
    historical_collections_source, git_blob, FINAL_PROBE_BLOCKS,
    HISTORICAL_COLLECTIONS_BLOB, HISTORICAL_COLLECTIONS_OUTPUT_BLOB,
)


class NativeOutputTests(unittest.TestCase):
    native_root = ROOT
    fixture_root = ROOT.parent / "tests/fixtures/native_windows"
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
        expected_path = self.fixture_root / (script.stem + ".out")
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
        # Replay the owner-confirmed Windows timezone using its CLDR mapping.
        # Only execution context changes; every native output byte is compared.
        # See docs/native-testing.md; never inherit a CI host timezone.
        environment["YADINASSI_TIMEZONE"] = "Europe/Warsaw"
        try:
            with tempfile.TemporaryDirectory(prefix="native-historical-") as temporary:
                arguments = [sys.executable, "-c", EXECUTE_SCRIPT, str(script)]
                if self.native_root == ROOT and script.name == "collections.bsl":
                    replay = Path(temporary) / script.name
                    replay.write_bytes(historical_collections_source(
                        script.read_bytes(), expected_path.read_bytes()))
                    arguments.append(str(replay))
                result = subprocess.run(
                    arguments, cwd=ROOT.parent, env=environment,
                    capture_output=True, timeout=10,
                )
        except subprocess.TimeoutExpired:
            self.fail(f"Yadinassi не выполнил {script}: истек таймаут 10 с.")
        except (OSError, ValueError) as error:
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

    def test_recorded_timezone_overrides_ambient_context_without_changing_output(self):
        self.add_case(code='Сообщить(XMLString(XMLValue(Type("Date"), "2024-02-29T12:34:56Z")));',
                      output=b'2024-02-29T13:34:56\n')
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Asia/Kathmandu'}):
            self.assert_comparison_passes()

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
        case.fixture_root = self.root / "output"
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





class HistoricalCollectionsBindingTests(unittest.TestCase):
    def setUp(self):
        # Canonical mutation inputs keep the negative controls effective on CRLF checkouts.
        # The explicit CRLF transport case below still exercises production normalization.
        self.source = (ROOT / 'tests/collections.bsl').read_bytes().replace(b'\r\n', b'\n')
        self.output = (ROOT.parent / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')

    def test_full_historical_source_and_all_output_bytes_are_bound(self):
        replay = historical_collections_source(self.source, self.output)
        self.assertEqual(git_blob(replay), HISTORICAL_COLLECTIONS_BLOB)
        self.assertEqual(len(self.output.replace(b'\r\n', b'\n').splitlines()), 4579)
        self.assertIn(b'table.list.string-cache.checkpoint.complete', replay)
        self.assertNotIn(b'table.list.string-cache.final.complete', replay)
        self.assertIn(b'table.list.string-cache.final.complete', self.source)
        self.assertEqual(historical_collections_source(
            self.source.replace(b'\n', b'\r\n'), self.output.replace(b'\n', b'\r\n')), replay)

    def test_changed_historical_source_or_output_fails_closed(self):
        for source, output in (
            (self.source + b'// mutation\n', self.output),
            (self.source.replace(b'list.string.empty', b'list.string.other'), self.output),
            (self.source, self.output + b'\n'),
            (self.source, self.output[:-32]),
            (self.source, self.output.replace(b'list.string.empty', b'list.string.other')),
        ):
            with self.subTest(source_changed=source != self.source, output_changed=output != self.output):
                with self.assertRaises(ValueError):
                    historical_collections_source(source, output)

    def test_missing_duplicated_or_reordered_boundaries_fail_closed(self):
        start, end = FINAL_PROBE_BLOCKS[0]
        for source in (self.source.replace(start.encode(), b''),
                       self.source + start.encode(),
                       self.source.replace(end.encode(), b''),
                       self.source.replace(start.encode(), b'__SWAP__').replace(
                           end.encode(), start.encode()).replace(b'__SWAP__', end.encode())):
            with self.assertRaises(ValueError):
                historical_collections_source(source, self.output)


    def test_mutation_controls_work_with_crlf_checkout(self):
        original = Path.read_bytes
        def crlf_bytes(path):
            data = original(path)
            if path in (ROOT / 'tests/collections.bsl', ROOT.parent / 'tests/fixtures/native_windows/collections.out'):
                return data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            return data
        names = (
            'test_full_historical_source_and_all_output_bytes_are_bound',
            'test_changed_historical_source_or_output_fails_closed',
            'test_missing_duplicated_or_reordered_boundaries_fail_closed',
        )
        suite = unittest.TestSuite(type(self)(name) for name in names)
        stream = io.StringIO()
        with patch.object(Path, 'read_bytes', crlf_bytes):
            result = unittest.TextTestRunner(stream=stream).run(suite)
        self.assertTrue(result.wasSuccessful(), stream.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Standalone checks for the 1C output generator; no yadinassi imports or real 1C runs."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

if __package__:
    from . import test_launcher as launcher
else:
    import test_launcher as launcher


class IntegrationLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="1c launcher пробел ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "tests").mkdir()
        self.platform = launcher.Platform(Path(sys.executable), self.root / "база с пробелом")
        self.commands = []
        self.modules = []

    def fake_platform(self, command, directory, log, timeout):
        """Simulate the external platform protocol, not BSL execution."""
        self.commands.append(command)
        log.write_text("simulated platform\n", encoding="utf-8")
        if command[1] == "DESIGNER":
            index = command.index("/LoadExternalDataProcessorOrReportFromFiles")
            source = Path(command[index + 1])
            destination = Path(command[index + 2])
            ET.parse(source)
            if source.stem == "TestModule":
                module = source.parent / "TestModule" / "Ext" / "ObjectModule.bsl"
                text = module.read_text(encoding="utf-8-sig")
                self.modules.append(text)
                destination.write_text(text, encoding="utf-8")
            else:
                destination.write_bytes(b"simulated launcher")
            Path(command[command.index("/DumpResult") + 1]).write_text(
                "0\n", encoding="utf-16")
        else:
            request = json.loads(Path(command[command.index("/C") + 1]).read_text(encoding="utf-8"))
            source = Path(request["module"]).read_text(encoding="utf-8")
            if "FAIL" in source:
                result = {"messages": ["до ошибки"], "error": "Ошибка теста"}
            elif "EMPTY" in source:
                result = {"messages": [], "error": ""}
            else:
                result = {"messages": ["Привет\r\nмир", ""], "error": ""}
            Path(request["result"]).write_text(json.dumps(result, ensure_ascii=False),
                                               encoding="utf-8-sig")

    def run_suite(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return launcher.run_suite(self.platform, self.root)

    def test_suite_builds_complete_modules_and_continues_after_runtime_failure(self):
        module = ('Функция Ответ()\nВозврат 42;\nКонецФункции\n'
                  'Сообщить(Ответ());\n')
        for name, source in [("a.bsl", module), ("b.bsl", "// FAIL"), ("c.BSL", "// EMPTY")]:
            (self.root / "tests" / name).write_text(source, encoding="utf-8-sig")
        (self.root / "output").mkdir()
        for name in ("a.out", "a.err", "b.out", "b.err"):
            (self.root / "output" / name).write_text("stale result", encoding="utf-8")

        with patch.object(launcher, "run_process", side_effect=self.fake_platform):
            self.assertEqual(self.run_suite(), 1)

        self.assertEqual(self.modules, [module, "// FAIL", "// EMPTY"])
        self.assertEqual((self.root / "output" / "a.out").read_bytes(),
                         "Привет\nмир\n\n".encode("utf-8"))
        self.assertFalse((self.root / "output" / "a.err").exists())
        self.assertEqual((self.root / "output" / "b.out").read_bytes(), "до ошибки\n".encode())
        self.assertIn("Ошибка теста", (self.root / "output" / "b.err").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "output" / "c.out").read_bytes(), b"")
        self.assertEqual([command[1] for command in self.commands],
                         ["DESIGNER", "DESIGNER", "ENTERPRISE", "DESIGNER", "ENTERPRISE",
                          "DESIGNER", "ENTERPRISE"])
        for command in self.commands:
            self.assertEqual(command[command.index("/F") + 1], str(self.platform.database))
        # Sources are replaced in copies, never in the committed template.
        self.assertIn("Python заменяет", (launcher.TEMPLATES / "TestModule" / "Ext"
                                         / "ObjectModule.bsl").read_text(encoding="utf-8"))

    def test_success_and_empty_output_are_successful_tests(self):
        (self.root / "tests" / "empty.bsl").write_text("// EMPTY", encoding="utf-8")
        with patch.object(launcher, "run_process", side_effect=self.fake_platform):
            self.assertEqual(self.run_suite(), 0)
        self.assertEqual((self.root / "output" / "empty.out").read_bytes(), b"")

    def test_missing_enterprise_response_is_failure_and_stale_output_is_removed(self):
        (self.root / "tests" / "case.bsl").write_text("Сообщить(1);", encoding="utf-8")
        (self.root / "output").mkdir()
        (self.root / "output" / "case.out").write_text("stale", encoding="utf-8")

        def no_response(command, directory, log, timeout):
            if command[1] == "DESIGNER":
                self.fake_platform(command, directory, log, timeout)

        with patch.object(launcher, "run_process", side_effect=no_response):
            self.assertEqual(self.run_suite(), 1)
        self.assertFalse((self.root / "output" / "case.out").exists())
        self.assertIn("result.json", (self.root / "output" / "case.err").read_text(encoding="utf-8"))

    def test_build_requires_platform_verdict_and_nonempty_artifact(self):
        for verdict, artifact in [(None, b"epf"), ("1", b"epf"), ("0", b""), ("0", None)]:
            with self.subTest(verdict=verdict, artifact=artifact):
                destination = self.root / "test.epf"
                result = destination.with_suffix(".build-result.txt")
                destination.unlink(missing_ok=True)
                result.unlink(missing_ok=True)

                def incomplete_build(*args):
                    if verdict is not None:
                        result.write_text(verdict, encoding="utf-8-sig")
                    if artifact is not None:
                        destination.write_bytes(artifact)

                with patch.object(launcher, "run_process", side_effect=incomplete_build):
                    with self.assertRaises(launcher.LaunchError):
                        launcher.build_epf(self.platform, self.root / "test.xml", destination)

    def test_case_build_failure_does_not_stop_next_test(self):
        for name in ("a.bsl", "b.bsl"):
            (self.root / "tests" / name).write_text("// EMPTY", encoding="utf-8")

        def fail_first_case(command, directory, log, timeout):
            if command[1] == "DESIGNER" and directory.name == "test-0001":
                raise launcher.LaunchError("Ошибка сборки")
            self.fake_platform(command, directory, log, timeout)

        with patch.object(launcher, "run_process", side_effect=fail_first_case):
            self.assertEqual(self.run_suite(), 1)
        self.assertFalse((self.root / "output" / "a.out").exists())
        self.assertEqual((self.root / "output" / "b.out").read_bytes(), b"")
        self.assertIn("Ошибка сборки", (self.root / "output" / "a.err").read_text(encoding="utf-8"))

    def test_malformed_response_is_not_treated_as_empty_success(self):
        path = self.root / "response.json"
        for text in ("not json", "[]", "{}", '{"messages": [5], "error": ""}',
                     '{"messages": [], "error": null}'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(launcher.LaunchError):
                    launcher.read_result(path)

    def test_no_tests_and_conflicting_output_names_are_rejected(self):
        with self.assertRaises(launcher.LaunchError):
            launcher.collect_scripts(self.root / "tests")
        # Distinct extensions also collide on case-insensitive filesystems.
        for name in ("same.bsl", "same.Bsl"):
            (self.root / "tests" / name).write_text("", encoding="utf-8")
        if len(list((self.root / "tests").iterdir())) == 1:
            # Mock the listing on filesystems which cannot hold both names.
            paths = [self.root / "same.bsl", self.root / "same.BSL"]
            with patch.object(Path, "iterdir", return_value=iter(paths)), \
                    patch.object(Path, "is_file", return_value=True):
                with self.assertRaises(launcher.LaunchError):
                    launcher.collect_scripts(self.root / "tests")
        else:
            with self.assertRaises(launcher.LaunchError):
                launcher.collect_scripts(self.root / "tests")

    def test_subprocess_preserves_arguments_logs_and_exit_status(self):
        log = self.root / "process.log"
        launcher.run_process(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", "path with spaces"],
            self.root, log, 10,
        )
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "path with spaces")
        with self.assertRaisesRegex(launcher.LaunchError, "кодом 7"):
            launcher.run_process([sys.executable, "-c", "raise SystemExit(7)"],
                                 self.root, log, 10)

    def test_timeout_terminates_the_started_process(self):
        with self.assertRaisesRegex(launcher.LaunchError, "таймаут"):
            launcher.run_process([sys.executable, "-c", "import time; time.sleep(30)"],
                                 self.root, self.root / "timeout.log", 0.1)

    def test_cli_rejects_invalid_database_and_timeout(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for extra in ([], ["--timeout", "0"], ["--timeout", "nan"]):
                with self.subTest(extra=extra), self.assertRaises(SystemExit) as error:
                    launcher.main(["--bd", str(self.root), "--path-1c", str(self.root), *extra])
                self.assertEqual(error.exception.code, 2)

    def test_platform_search_handles_version_directory_and_missing_designer(self):
        with self.assertRaises(launcher.LaunchError):
            launcher.find_platform(self.root)
        binary = self.root / "bin" / ("1cv8.exe" if os.name == "nt" else "1cv8")
        binary.parent.mkdir()
        binary.write_bytes(b"fake platform")
        binary.chmod(0o755)
        self.assertEqual(launcher.find_platform(self.root), binary.resolve())
        self.assertEqual(launcher.find_platform(binary.parent), binary.resolve())

    def test_templates_have_linked_default_form_and_open_handler(self):
        metadata = {"m": "http://v8.1c.ru/8.3/MDClasses"}
        forms = {"f": "http://v8.1c.ru/8.3/xcf/logform"}
        for path in launcher.TEMPLATES.rglob("*.xml"):
            ET.parse(path)
        root = ET.parse(launcher.TEMPLATES / "Launcher.xml")
        default = root.find(".//m:DefaultForm", metadata)
        self.assertEqual(default.text, "ExternalDataProcessor.Launcher.Form.Main")
        form = ET.parse(launcher.TEMPLATES / "Launcher" / "Forms" / "Main" / "Ext" / "Form.xml")
        event = form.find(".//f:Event[@name='OnOpen']", forms)
        self.assertEqual(event.text, "ПриОткрытии")

    def test_explicit_training_executable_preserves_selected_edition(self):
        executable = self.root / ("1cv8t.exe" if os.name == "nt" else "1cv8t")
        executable.write_bytes(b"placeholder; never executed")
        executable.chmod(0o755)
        self.assertEqual(launcher.validate_executable(executable), executable.resolve())
        (self.root / "1Cv8.1CD").write_bytes(b"placeholder database")
        with patch.object(launcher, "run_suite", return_value=0) as run:
            self.assertEqual(launcher.main([
                "--bd", str(self.root), "--executable-1c", str(executable),
            ]), 0)
        selected = run.call_args.args[0]
        self.assertEqual(selected.executable, executable.resolve())
        self.assertEqual(selected.command("DESIGNER")[0], str(executable.resolve()))
        self.assertEqual(selected.command("ENTERPRISE")[0], str(executable.resolve()))

    def test_explicit_executable_rejects_missing_file_and_directory(self):
        for path in (self.root / "missing-1cv8t", self.root):
            with self.subTest(path=path), self.assertRaises(launcher.LaunchError):
                launcher.validate_executable(path)

    @unittest.skipIf(os.name == "nt", "Windows does not use POSIX executable bits")
    def test_explicit_executable_rejects_nonexecutable_file(self):
        executable = self.root / "1cv8t"
        executable.write_bytes(b"placeholder; never executed")
        executable.chmod(0o644)
        with self.assertRaisesRegex(launcher.LaunchError, "Нет права на исполнение"):
            launcher.validate_executable(executable)

    def test_cli_requires_exactly_one_platform_selection(self):
        # Valid unrelated arguments prevent a database error masking selector bugs.
        (self.root / "1Cv8.1CD").write_bytes(b"placeholder database")
        executable = self.root / ("1cv8.exe" if os.name == "nt" else "1cv8")
        executable.write_bytes(b"placeholder; never executed")
        executable.chmod(0o755)
        with contextlib.redirect_stderr(io.StringIO()), \
                patch.object(launcher, "run_suite", return_value=0) as run:
            for arguments in ([], ["--path-1c", str(self.root),
                                   "--executable-1c", str(self.root / "1cv8t")]):
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as error:
                    launcher.main(["--bd", str(self.root), *arguments])
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_existing_directory_cli_still_selects_regular_platform(self):
        executable = self.root / ("1cv8.exe" if os.name == "nt" else "1cv8")
        executable.write_bytes(b"placeholder; never executed")
        executable.chmod(0o755)
        (self.root / "1Cv8.1CD").write_bytes(b"placeholder database")
        with patch.object(launcher, "run_suite", return_value=0) as run:
            self.assertEqual(launcher.main([
                "--bd", str(self.root), "--path-1c", str(self.root),
            ]), 0)
        self.assertEqual(run.call_args.args[0].executable, executable.resolve())


if __name__ == "__main__":
    unittest.main()

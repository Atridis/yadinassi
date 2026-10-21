"""Offline client-probe contracts. Synthetic fixtures are never native evidence."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import test_native_1c_full_stage as stage_fixture
import test_native_1c_full_host as host_fixture
from test_native_1c_smoke import smoke

suite = stage_fixture.suite
full = smoke.FULL
NONCE = stage_fixture.NONCE
ROOT = stage_fixture.REPOSITORY
CLIENT_KEYS = {"status", "failure_kind", "source_sha256", "module_sha256",
               "roundtrip_sha256", "entered", "completed", "process_exited",
               "quiet", "witness_verified", "process_diagnostics"}
PROCESS_CLASSES = ("native", "display", "session_bus", "shell", "python", "other", "unreadable")


def process_diagnostics(*, stage="after_exit", reason="none", classes=None, zombie_count=0):
    counts = dict.fromkeys(PROCESS_CLASSES, 0)
    counts.update(classes or {})
    return {"stage": stage, "reason": reason, "unexpected_count": sum(counts.values()),
            "zombie_count": zombie_count, "classes": counts}


def marker(phase, *, nonce=NONCE):
    return {"schema": 1, "nonce": nonce, "phase": phase, "witness": "client",
            "values": [] if phase == "entered" else [42, "client-probe", 3, 6]}


def write_marker(path, phase):
    path.write_bytes(json.dumps(marker(phase), separators=(",", ":")).encode())


class ClientMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / "marker.json"
        if os.name == "nt":
            reader = mock.patch.object(suite, "secure_bytes", new=stage_fixture.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def test_exact_entered_and_completed_records(self):
        for phase in ("entered", "completed"):
            write_marker(self.path, phase)
            self.assertEqual(suite.client_marker(self.path, NONCE, phase), marker(phase))

    def test_unknown_phase_and_invalid_expected_nonce_fail_closed(self):
        for phase, nonce in (("error", NONCE), ("completed", "../PRIVATE"),
                             ("completed", "A" * 32), ("completed", "0" * 31)):
            with self.subTest(phase=phase, nonce=nonce):
                self.path.write_bytes(json.dumps(marker(phase, nonce=nonce)).encode())
                with self.assertRaises(suite.FullError):
                    suite.client_marker(self.path, nonce, phase)

    def test_unknown_fields_wrong_types_and_witness_are_rejected(self):
        edits = [lambda d: d.update(extra="PRIVATE"), lambda d: d.pop("witness"),
                 lambda d: d.update(schema=True), lambda d: d.update(schema=2),
                 lambda d: d.update(nonce="0" * 32), lambda d: d.update(phase="entered"),
                 lambda d: d.update(witness="server"), lambda d: d.update(witness=True),
                 lambda d: d.update(values=None), lambda d: d.update(values=[]),
                 lambda d: d.update(values=[42, "client-probe", True, 6]),
                 lambda d: d.update(values=[42, "client-probe", 3, 6, 0]),
                 lambda d: d.update(values=[42, "client-probe", 3, 7]),
                 lambda d: d.update(values=["42", "client-probe", 3, 6])]
        for edit in edits:
            value = marker("completed")
            edit(value)
            with self.subTest(value=value):
                self.path.write_bytes(json.dumps(value).encode())
                with self.assertRaisesRegex(suite.FullError, "^invalid_result$"):
                    suite.client_marker(self.path, NONCE, "completed")
        value = marker("entered")
        value["values"] = [42, "client-probe", 3, 6]
        self.path.write_bytes(json.dumps(value).encode())
        with self.assertRaises(suite.FullError):
            suite.client_marker(self.path, NONCE, "entered")

    def test_duplicate_trailing_nonfinite_unicode_and_depth_rejected(self):
        good = json.dumps(marker("completed"), separators=(",", ":")).encode()
        bad = [good.replace(b'"schema":1', b'"schema":1,"schema":1'),
               good + b" PRIVATE", good[:-1], b"[]", b"null", b"\xff",
               good.replace(b'42,', b'42.0,'), good.replace(b'42,', b'NaN,'),
               good.replace(b'42,', b'Infinity,'),
               good.replace(b'"client-probe"', b'"\\ud800"'),
               b"[" * 20 + b"]" * 20]
        for raw in bad:
            with self.subTest(raw=raw[:60]):
                self.path.write_bytes(raw)
                with self.assertRaises(suite.FullError):
                    suite.client_marker(self.path, NONCE, "completed")

    def test_missing_empty_directory_and_oversize_rejected(self):
        with self.assertRaises(suite.FullError):
            suite.client_marker(self.path, NONCE, "completed")
        for raw in (b"", b" " * 2049):
            self.path.write_bytes(raw)
            with self.assertRaises(suite.FullError):
                suite.client_marker(self.path, NONCE, "completed")
        with self.assertRaises(suite.FullError):
            suite.client_marker(self.root, NONCE, "completed")

    @unittest.skipUnless(os.name == "posix", "POSIX descriptor boundary")
    def test_symlink_parent_symlink_hardlink_and_fifo_rejected(self):
        write_marker(self.path, "completed")
        link = self.root / "link"
        link.symlink_to(self.path)
        with self.assertRaises(suite.FullError):
            suite.client_marker(link, NONCE, "completed")
        link.unlink()
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(suite.FullError):
            suite.client_marker(link / self.path.name, NONCE, "completed")
        link.unlink()
        os.link(self.path, link)
        with self.assertRaises(suite.FullError):
            suite.client_marker(self.path, NONCE, "completed")
        link.unlink()
        os.mkfifo(link)
        with self.assertRaises(suite.FullError):
            suite.client_marker(link, NONCE, "completed")


class ClientProbeHarness(unittest.TestCase):
    """Run real Python orchestration with explicitly fake build/dump/client bytes."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.inputs = self.root / "inputs"
        for source, target in {**suite.INPUT_FILES, suite.CLIENT_SOURCE: suite.CLIENT_TARGET}.items():
            path = self.inputs / target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, path)
        if os.name == "nt":
            reader = mock.patch.object(suite, "secure_bytes", new=stage_fixture.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)
        self.launcher = stage_fixture.load_launcher(self.inputs / "launcher/test_launcher.py")
        self.platform = self.launcher.Platform(Path("/approved/1cv8t"), self.root / "db", 120, "NativeSmoke")
        self.hashes = suite.input_hashes(self.inputs, client_probe=True)
        self.work = self.root / "client-probe"
        self.events = []
        self.hook = None
        self.run_markers = ("entered", "completed")
        self.run_error = None
        self.quiet = True
        self.request = None
        for patcher in (
                mock.patch.object(suite, "run_process", side_effect=self.fake_native),
                mock.patch.object(suite, "native_processes_quiet", side_effect=lambda _: self.quiet if "enterprise" in self.events else True),
                mock.patch.object(suite, "client_process_baseline", return_value=set()),
                mock.patch.object(suite, "client_process_snapshot", return_value=set()),
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("Offline test must not launch native processes"))):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def argument(command, flag):
        return command[command.index(flag) + 1]

    def fake_native(self, command, directory, log, timeout, *, require_clean_tree=False):
        mode = ("build" if "/LoadExternalDataProcessorOrReportFromFiles" in command else
                "dump" if "/DumpExternalDataProcessorOrReportToFiles" in command else "enterprise")
        self.events.append(mode)
        self.assertEqual(directory, self.work)
        self.assertEqual(timeout, 120)
        self.assertIs(require_clean_tree, True)
        self.assertEqual(self.argument(command, "/N"), "NativeSmoke")
        self.assertNotIn("/P", command)
        self.assertFalse(log.exists())
        log.write_bytes(b"PRIVATE native fake diagnostics")
        if mode == "build":
            index = command.index("/LoadExternalDataProcessorOrReportFromFiles")
            self.assertEqual(Path(command[index + 1]), self.work / "src/Launcher.xml")
            Path(command[index + 2]).write_bytes(b"OFFLINE fake compiled EPF")
            Path(self.argument(command, "/DumpResult")).write_bytes(b"0\n")
        elif mode == "dump":
            destination = Path(self.argument(command, "/DumpExternalDataProcessorOrReportToFiles")).parent
            shutil.copytree(self.work / "src", destination, dirs_exist_ok=True)
            Path(self.argument(command, "/DumpResult")).write_bytes(b"0\n")
        else:
            self.assertIn("/RunModeManagedApplication", command)
            self.assertEqual(self.argument(command, "/VL"), "ru_RU")
            self.assertEqual(Path(self.argument(command, "/Execute")), self.work / "ClientProbe.epf")
            self.request = json.loads(Path(self.argument(command, "/C")).read_text())
            self.assertEqual(set(self.request), {"nonce", "entered", "completed", "mode"})
            self.assertEqual(self.request["nonce"], NONCE)
            for phase in self.run_markers:
                target = Path(self.request[phase])
                self.assertFalse(target.exists(), "Markers must be fresh before the fake invocation")
                write_marker(target, phase)
        if self.hook:
            self.hook(mode)
        if mode == "enterprise" and self.run_error:
            raise suite.FullError(self.run_error)

    def run_probe(self, **kwargs):
        return suite.run_client_probe(self.platform, self.work, self.inputs, NONCE,
                                      self.hashes, **kwargs)

    def reset(self):
        if self.work.exists():
            shutil.rmtree(self.work)
        self.events.clear()

    def test_success_builds_roundtrips_executes_exact_client_and_exports_only_metadata(self):
        source = (self.inputs / suite.CLIENT_TARGET).read_bytes()
        module = suite.generated_module(source)
        result = self.run_probe()
        self.assertEqual(result, {"status": "ok", "failure_kind": "none",
            "process_diagnostics": process_diagnostics(),
            "source_sha256": suite.digest(source), "module_sha256": suite.digest(module),
            "roundtrip_sha256": suite.digest(module), **dict.fromkeys(suite.CLIENT_FLAGS, True)})
        self.assertEqual(self.events, ["build", "dump", "enterprise"])
        self.assertEqual(self.request["mode"], "normal")
        self.assertFalse((self.work / "src/TestModule.xml").exists())
        self.assertFalse((self.work / "src/TestModule").exists())
        self.assertEqual((self.work / "src" / suite.CLIENT_MODULE).read_bytes(), module)
        public = json.dumps(result)
        for private in ("PRIVATE", "entered.json", "completed.json", str(self.work), "client-probe"):
            self.assertNotIn(private, public)

    def test_stall_is_explicit_private_request_and_never_a_success_after_timeout(self):
        self.run_markers = ("entered",)
        self.run_error = "timeout"
        result = self.run_probe(stall=True)
        self.assertEqual(self.request["mode"], "stall")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_kind"], "timeout")
        self.assertTrue(result["entered"])
        self.assertFalse(result["completed"])
        self.assertFalse(result["witness_verified"])

    def test_timeout_before_entry_after_entry_and_after_completion_are_distinct_failures(self):
        for phases in ((), ("entered",), ("entered", "completed")):
            with self.subTest(phases=phases):
                self.run_markers, self.run_error = phases, "timeout"
                result = self.run_probe()
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failure_kind"], "timeout")
                self.assertEqual(result["entered"], "entered" in phases)
                self.assertEqual(result["completed"], "completed" in phases)
                self.assertFalse(result["process_exited"])
                self.assertTrue(result["quiet"])
                self.assertFalse(result["witness_verified"])
                self.reset()

    def test_nonzero_exit_with_both_markers_is_not_success(self):
        self.run_error = "process_failed"
        result = self.run_probe()
        self.assertEqual(result["failure_kind"], "process_failed")
        self.assertTrue(result["entered"] and result["completed"])
        self.assertFalse(result["witness_verified"])

    def test_live_process_blocks_success_even_with_complete_fresh_markers(self):
        self.quiet = False
        result = self.run_probe()
        self.assertEqual(result["failure_kind"], "process_failed")
        self.assertTrue(result["process_exited"])
        self.assertTrue(result["entered"] and result["completed"])
        self.assertFalse(result["quiet"])
        self.assertFalse(result["witness_verified"])

    def test_live_native_process_before_start_prevents_any_build(self):
        with mock.patch.object(suite, "native_processes_quiet", return_value=False):
            result = self.run_probe()
        self.assertEqual(result["failure_kind"], "process_failed")
        self.assertEqual(self.events, [])
        self.assertEqual(result["process_diagnostics"], process_diagnostics(stage="before_probe", reason="native_not_quiet"))
        self.assertIsNone(result["source_sha256"])

    def test_baseline_rejection_exposes_only_fixed_diagnostics_before_source_hashing(self):
        diagnostic = process_diagnostics(stage="baseline", reason="unexpected_processes", classes={"session_bus": 1})
        with mock.patch.object(suite, "client_process_baseline", side_effect=suite.ClientProcessError(diagnostic)):
            result = self.run_probe()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_kind"], "process_failed")
        self.assertEqual(result["process_diagnostics"], diagnostic)
        self.assertTrue(all(result[key] is None for key in ("source_sha256", "module_sha256", "roundtrip_sha256")))
        self.assertTrue(all(result[key] is False for key in suite.CLIENT_FLAGS))
        self.assertEqual(self.events, [])

    def test_uninspectable_baseline_remains_unverified_without_inventing_counts(self):
        with mock.patch.object(suite, "client_process_baseline", side_effect=suite.FullError("process_failed")):
            result = self.run_probe()
        self.assertEqual(result["failure_kind"], "process_failed")
        self.assertEqual(result["process_diagnostics"], process_diagnostics(stage="baseline", reason="unverified"))
        self.assertEqual(self.events, [])

    def test_new_same_user_process_or_reused_pid_blocks_success(self):
        for before, after in ((set(), {(987, "1000")}),
                              ({(987, "1000")}, {(987, "2000")})):
            with self.subTest(before=before, after=after), \
                    mock.patch.object(suite, "client_process_baseline", return_value=before), \
                    mock.patch.object(suite, "client_process_snapshot", return_value=after):
                result = self.run_probe()
                self.assertEqual(result["failure_kind"], "process_failed")
                self.assertTrue(result["process_exited"])
                self.assertFalse(result["quiet"])
                self.assertFalse(result["witness_verified"])
                self.reset()

    def test_disappeared_baseline_process_does_not_make_census_fail(self):
        with mock.patch.object(suite, "client_process_baseline", return_value={(987, "1000")}), \
                mock.patch.object(suite, "client_process_snapshot", return_value=set()):
            self.assertEqual(self.run_probe()["status"], "ok")

    def test_missing_entered_or_completed_never_claims_client_witness(self):
        for phases in ((), ("entered",), ("completed",)):
            with self.subTest(phases=phases):
                self.run_markers = phases
                result = self.run_probe()
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failure_kind"], "artifact_missing")
                self.assertFalse(result["witness_verified"])
                self.reset()

    def test_completed_timestamp_before_entered_is_rejected_but_equal_resolution_is_valid(self):
        for entered_ns, completed_ns, status in ((2_000_000_000, 1_000_000_000, "failed"),
                                                 (2_000_000_000, 2_000_000_000, "ok")):
            def change(mode):
                if mode == "enterprise":
                    os.utime(self.work / "entered.json", ns=(entered_ns, entered_ns))
                    os.utime(self.work / "completed.json", ns=(completed_ns, completed_ns))
            self.hook = change
            with self.subTest(entered_ns=entered_ns, completed_ns=completed_ns):
                result = self.run_probe()
                self.assertEqual(result["status"], status)
                self.assertEqual(result["failure_kind"], "invalid_result" if status == "failed" else "none")
                self.assertEqual(result["witness_verified"], status == "ok")
                self.reset()

    def test_wrong_nonce_or_server_witness_is_invalid_not_a_completed_checkpoint(self):
        for field, value in (("nonce", "0" * 32), ("witness", "server"), ("values", [42, "client-probe", 3, 7])):
            def change(mode):
                if mode == "enterprise":
                    data = marker("completed")
                    data[field] = value
                    (self.work / "completed.json").write_bytes(json.dumps(data).encode())
            self.hook = change
            with self.subTest(field=field):
                result = self.run_probe()
                self.assertEqual(result["failure_kind"], "invalid_result")
                self.assertTrue(result["entered"])
                self.assertFalse(result["completed"])
                self.assertFalse(result["witness_verified"])
                self.reset()

    def test_stale_root_prevents_any_build(self):
        self.work.mkdir()
        result = self.run_probe()
        self.assertEqual(result["failure_kind"], "stale_evidence")
        self.assertEqual(self.events, [])

    def test_preexisting_marker_or_request_prevents_enterprise(self):
        for name in ("entered.json", "completed.json", "request.json"):
            self.hook = lambda mode: (self.work / name).write_bytes(b"") if mode == "dump" else None
            with self.subTest(name=name):
                result = self.run_probe()
                self.assertEqual(result["failure_kind"], "stale_evidence")
                self.assertEqual(self.events, ["build", "dump"])
                self.reset()

    def test_source_or_metadata_provenance_change_prevents_any_build(self):
        for target in (suite.CLIENT_TARGET, "launcher/launcher_1c/Launcher.xml"):
            path = self.inputs / target
            before = path.read_bytes()
            path.write_bytes(before + b"\n")
            with self.subTest(target=target):
                result = self.run_probe()
                self.assertEqual(result["failure_kind"], "invalid_input")
                self.assertEqual(self.events, [])
                self.reset()
            path.write_bytes(before)

    def test_generated_module_mutation_at_build_dump_and_execution_fails(self):
        for phase, target in (("build", "src"), ("dump", "roundtrip"), ("enterprise", "src")):
            def change(mode):
                if mode == phase:
                    (self.work / target / suite.CLIENT_MODULE).write_bytes(b"// changed PRIVATE source")
            self.hook = change
            with self.subTest(phase=phase):
                result = self.run_probe()
                self.assertEqual(result["failure_kind"], "module_mismatch")
                self.assertFalse(result["witness_verified"])
                self.assertNotIn("PRIVATE", json.dumps(result))
                self.reset()

    def test_dumped_form_wiring_or_object_fallback_prevents_enterprise(self):
        changes = [("Launcher.xml", "ExternalDataProcessor.Launcher.Form.Main", "ExternalDataProcessor.Launcher.Form.Other"),
                   ("Launcher/Forms/Main.xml", "<FormType>Managed</FormType>", "<FormType>Ordinary</FormType>"),
                   ("Launcher/Forms/Main/Ext/Form.xml", "OnOpen", "OnClose"),
                   ("Launcher/Forms/Main/Ext/Form.xml", "ПриОткрытии", "OtherHandler"),
                   ("Launcher/Ext/ObjectModule.bsl", None, "Сообщить(42);")]
        for relative, old, new in changes:
            def change(mode):
                if mode == "dump":
                    path = self.work / "roundtrip" / relative
                    text = path.read_text(encoding="utf-8-sig")
                    path.write_text(new if old is None else text.replace(old, new), encoding="utf-8")
            self.hook = change
            with self.subTest(relative=relative, new=new):
                result = self.run_probe()
                self.assertEqual(result["failure_kind"], "module_mismatch")
                self.assertEqual(self.events, ["build", "dump"])
                self.reset()

    def test_invalid_platform_nonce_or_stall_never_runs(self):
        invalid_platforms = [self.launcher.Platform(Path("/approved"), self.root / "db", 121, "NativeSmoke"),
                             self.launcher.Platform(Path("/approved"), self.root / "db", 120, "Other"),
                             self.launcher.Platform(Path("/approved"), self.root / "db", 120, "NativeSmoke", "PRIVATE")]
        for platform in invalid_platforms:
            with self.subTest(platform=platform):
                result = suite.run_client_probe(platform, self.work, self.inputs, NONCE, self.hashes)
                self.assertEqual(result["failure_kind"], "invalid_input")
                self.assertEqual(self.events, [])
        self.assertEqual(self.run_probe(stall=1)["failure_kind"], "invalid_input")
        result = suite.run_client_probe(self.platform, self.work, self.inputs, "PRIVATE", self.hashes)
        self.assertEqual(result["failure_kind"], "invalid_input")
        self.assertEqual(self.events, [])


class ClientOptInTests(host_fixture.SyntheticFilesystemCase):
    def test_legacy_defaults_and_opt_in_have_exact_23_and_24_inputs(self):
        self.assertEqual(len(smoke.staged_files(True, False)), 23)
        self.assertEqual(len(smoke.staged_files(True, True)), 24)
        self.assertEqual(smoke.staged_files(True, True), {**suite.INPUT_FILES, suite.CLIENT_SOURCE: suite.CLIENT_TARGET})
        self.assertNotIn("client_probe", suite.empty_report(NONCE))
        record = suite.empty_report(NONCE, client_probe=True)["client_probe"]
        self.assertEqual(set(record), CLIENT_KEYS)
        self.assertEqual(record, suite.empty_client_report())
        for key in suite.CLIENT_FLAGS:
            self.assertIs(record[key], False)

    def test_opt_in_stages_only_extra_probe_and_passes_exact_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve() / "inputs"
            hashes = smoke.stage_inputs(directory, full_suite=True, client_probe=True)
            self.assertEqual(len(hashes), 24)
            self.assertEqual((directory / suite.CLIENT_TARGET).read_bytes(), (ROOT / suite.CLIENT_SOURCE).read_bytes())
            command = smoke.container_command(directory, "onec-smoke-test", full_suite=True,
                                               nonce=NONCE, client_probe=True)
            self.assertEqual(command[-4:], ["--full-suite", "--invocation-nonce", NONCE, "--client-probe"])
            self.assertEqual(command.count("--mount"), 1)
            self.assertNotIn("--client-probe", smoke.container_command(smoke.PROBE, "onec-smoke-test"))
            with self.assertRaises(smoke.SmokeError):
                smoke.validate_input_tree(directory, full_suite=True)

    def test_missing_opt_in_input_fails_tree_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve() / "inputs"
            smoke.stage_inputs(directory, full_suite=True)
            with self.assertRaises(smoke.SmokeError):
                smoke.validate_input_tree(directory, full_suite=True, client_probe=True)

    def test_client_probe_requires_full_suite_at_each_public_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for action in (lambda: smoke.staged_files(False, True),
                           lambda: smoke.stage_inputs(root / "inputs", client_probe=True),
                           lambda: smoke.container_command(smoke.PROBE, "onec-smoke-test", client_probe=True),
                           lambda: smoke.run_smoke(root, client_probe=True)):
                with self.assertRaisesRegex(smoke.SmokeError, "^client_probe_requires_full_suite$"):
                    action()
            with mock.patch.object(smoke, "run_smoke") as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    smoke.main(["--execute-approved-image", "--client-probe"])
                self.assertEqual(caught.exception.code, 2)
                run.assert_not_called()

    def test_probe_source_is_client_only_with_explicit_witness_and_nonmodal_stall(self):
        source = (ROOT / suite.CLIENT_SOURCE).read_text(encoding="utf-8-sig")
        self.assertEqual(source.count("&НаКлиенте"), 4)
        self.assertIn("#Если Клиент Тогда", source)
        self.assertIn('Возврат "client";', source)
        self.assertIn('ВызватьИсключение "not-client";', source)
        self.assertIn('Запрос.mode = "stall"', source)
        self.assertIn("Пока Истина Цикл", source)
        self.assertIn("ЗавершитьРаботуСистемы(Ложь)", source)
        for forbidden in ("&НаСервере", "ЗапуститьТестНаСервере", "ВнешниеОбработки.Создать",
                          "SecurityTypes=None", "ЗащитаОтОпасныхДействий", "UnsafeOperationProtection"):
            self.assertNotIn(forbidden, source)

    def test_stage_controller_rejects_probe_without_fixed_full_arguments(self):
        spec = importlib.util.spec_from_file_location("client_probe_test_controller", stage_fixture.HELPERS / "run_stage.py")
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        bad_arguments = (["--client-probe"], ["--client-probe", "--full-suite"],
                         ["--full-suite", "--client-probe"],
                         ["--full-suite", "--invocation-nonce", "../x", "--client-probe"],
                         ["--full-suite", "--invocation-nonce", NONCE, "--client-probe", "--client-probe"])
        for arguments in bad_arguments:
            with self.subTest(arguments=arguments), mock.patch.object(controller, "run") as run:
                self.assertEqual(controller.main(arguments), 2)
                run.assert_not_called()

    def test_watchdog_opt_in_requires_client_and_full_suite_at_public_boundaries(self):
        self.assertNotIn("client_watchdog", suite.empty_report(NONCE, client_probe=True))
        self.assertEqual(suite.empty_report(NONCE, client_probe=True, watchdog_check=True)["client_watchdog"],
                         suite.empty_watchdog_report())
        with self.assertRaises(suite.FullError):
            suite.empty_report(NONCE, watchdog_check=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for action in (lambda: smoke.container_command(smoke.PROBE, "onec-smoke-test", watchdog_check=True),
                           lambda: smoke.run_smoke(root, watchdog_check=True)):
                with self.assertRaisesRegex(smoke.SmokeError, "^watchdog_check_requires_client_probe$"):
                    action()
            for arguments in (["--execute-approved-image", "--client-watchdog-check"],
                              ["--execute-approved-image", "--full-suite", "--client-watchdog-check"],
                              ["--execute-approved-image", "--client-probe", "--client-watchdog-check"]):
                with self.subTest(arguments=arguments), mock.patch.object(smoke, "run_smoke") as run, \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        smoke.main(arguments)
                    self.assertEqual(caught.exception.code, 2)
                    run.assert_not_called()

    def test_watchdog_uses_same_24_inputs_and_both_explicit_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve() / "inputs"
            self.assertEqual(len(smoke.stage_inputs(directory, full_suite=True, client_probe=True)), 24)
            command = smoke.container_command(directory, "onec-smoke-test", full_suite=True,
                nonce=NONCE, client_probe=True, watchdog_check=True)
            self.assertEqual(command[-5:], ["--full-suite", "--invocation-nonce", NONCE,
                                            "--client-probe", "--client-watchdog-check"])


class ClientWatchdogTests(unittest.TestCase):
    """The deliberate negative must not reinterpret an ordinary failed probe."""
    argument = staticmethod(ClientProbeHarness.argument)
    fake_native = ClientProbeHarness.fake_native
    reset = ClientProbeHarness.reset

    def setUp(self):
        ClientProbeHarness.setUp(self)
        self.run_markers = ("entered",)
        self.run_error = "timeout"

    def run_watchdog(self):
        return suite.run_client_watchdog(self.platform, self.work, self.inputs, NONCE, self.hashes)

    def test_exact_expected_stall_only_is_accepted_with_distinct_timeout_proof(self):
        result = self.run_watchdog()
        source = (self.inputs / suite.CLIENT_TARGET).read_bytes()
        module_hash = suite.digest(suite.generated_module(source))
        self.assertEqual(result, {"status": "ok", "failure_kind": "none",
            "process_diagnostics": process_diagnostics(),
            "source_sha256": suite.digest(source), "module_sha256": module_hash,
            "roundtrip_sha256": module_hash, "entered": True, "completed": False,
            "process_exited": False, "quiet": True, "witness_verified": False,
            "timeout_verified": True})
        self.assertEqual(self.request["mode"], "stall")
        self.assertEqual(self.events, ["build", "dump", "enterprise"])
        self.assertFalse((self.work / "completed.json").exists())
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_no_entry_completed_timeout_nonzero_or_ordinary_exit_is_not_expected_stall(self):
        cases = [((), "timeout"), (("entered", "completed"), "timeout"),
                 (("entered",), "process_failed"), (("entered",), None),
                 (("entered", "completed"), None)]
        for markers, error in cases:
            self.run_markers, self.run_error = markers, error
            with self.subTest(markers=markers, error=error):
                result = self.run_watchdog()
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["timeout_verified"])
                self.assertFalse(result["witness_verified"])
                self.reset()

    def test_any_terminal_file_even_invalid_partial_or_wrong_nonce_rejects_stall(self):
        for raw in (b"", b"{", b"PRIVATE", json.dumps(marker("completed", nonce="0" * 32)).encode()):
            self.hook = lambda mode: (self.work / "completed.json").write_bytes(raw) if mode == "enterprise" else None
            with self.subTest(raw=raw):
                result = self.run_watchdog()
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["timeout_verified"])
                self.reset()

    @unittest.skipUnless(os.name == "posix", "POSIX symlink boundary")
    def test_dangling_completed_symlink_is_not_absence(self):
        self.hook = lambda mode: (self.work / "completed.json").symlink_to(self.work / "missing") if mode == "enterprise" else None
        result = self.run_watchdog()
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["timeout_verified"])

    def test_live_native_or_new_same_uid_process_prevents_expected_timeout_acceptance(self):
        self.quiet = False
        result = self.run_watchdog()
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["timeout_verified"])
        self.reset()
        self.quiet = True
        with mock.patch.object(suite, "client_process_snapshot", return_value={(987, "1000")}):
            result = self.run_watchdog()
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["quiet"])
        self.assertFalse(result["timeout_verified"])

    def test_entered_nonce_is_rechecked_after_probe_diagnostics(self):
        real_probe = suite.run_client_probe
        def mutate(*args, **kwargs):
            record = real_probe(*args, **kwargs)
            self.assertTrue(record["entered"])
            (self.work / "entered.json").write_bytes(json.dumps(marker("entered", nonce="0" * 32)).encode())
            return record
        with mock.patch.object(suite, "run_client_probe", side_effect=mutate):
            result = self.run_watchdog()
        self.assertEqual(result["failure_kind"], "invalid_result")
        self.assertFalse(result["timeout_verified"])


@unittest.skipUnless(os.name == "posix", "Linux native process groups")
class ClientCleanProcessTests(unittest.TestCase):
    def invoke(self, *, group_present, returncode=0):
        child = mock.MagicMock()
        child.pid = 456
        child.wait.return_value = returncode
        child.__enter__.return_value = child
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(suite.subprocess, "Popen", return_value=child) as popen, \
                mock.patch.object(suite.os, "killpg", side_effect=None if group_present else ProcessLookupError()) as kill, \
                mock.patch.object(suite.time, "monotonic", side_effect=[0, 6]), \
                mock.patch.object(suite, "_stop_group") as stop:
            root = Path(temporary)
            try:
                suite.run_process(["fake-native"], root, root / "console", 120, require_clean_tree=True)
                result = "ok"
            except suite.FullError as error:
                result = error.kind
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            child.wait.assert_called_once_with(timeout=120)
            if group_present:
                stop.assert_called_once_with(child)
            else:
                stop.assert_not_called()
            kill.assert_called_once_with(456, 0)
        return result

    def test_zero_leader_exit_with_remaining_child_is_cleaned_and_rejected(self):
        self.assertEqual(self.invoke(group_present=True), "process_failed")

    def test_zero_exit_with_gone_group_can_complete(self):
        self.assertEqual(self.invoke(group_present=False), "ok")

    def test_nonzero_exit_with_gone_group_still_fails(self):
        self.assertEqual(self.invoke(group_present=False, returncode=2), "process_failed")

    def test_snapshot_parses_process_identity_and_rejects_unreadable_live_pid(self):
        process = mock.MagicMock()
        process.name = "123"
        process.stat.return_value.st_uid = os.geteuid()
        process.__truediv__.return_value.read_text.return_value = "123 (name (with) spaces) " + " ".join(["S"] + ["0"] * 18 + ["900"])
        proc = mock.MagicMock()
        proc.iterdir.return_value = [process]
        with mock.patch.object(suite, "Path", return_value=proc):
            self.assertEqual(suite.client_process_snapshot(), {(123, "900")})
            process.stat.return_value.st_uid = os.geteuid() + 1
            self.assertEqual(suite.client_process_snapshot(), {(123, "900")})
            process.stat.return_value.st_uid = os.geteuid()
            process.__truediv__.return_value.read_text.side_effect = PermissionError()
            with self.assertRaisesRegex(suite.FullError, "^process_failed$"):
                suite.client_process_snapshot()
            process.__truediv__.return_value.read_text.side_effect = FileNotFoundError()
            process.exists.return_value = True
            with self.assertRaisesRegex(suite.FullError, "^process_failed$"):
                suite.client_process_snapshot()
            process.exists.return_value = False
            self.assertEqual(suite.client_process_snapshot(), set())


class ClientBaselineTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {"schema": 1, "nonce": NONCE, "processes": [[1, "10"], [2, "20"]]}

    def validate(self, value=None, *, current=None, raw=None):
        raw = json.dumps(self.baseline if value is None else value).encode() if raw is None else raw
        current = {(1, "10"), (2, "20"), (3, "30")} if current is None else current
        with mock.patch.object(suite, "secure_bytes", return_value=raw) as read, \
                mock.patch.object(suite, "client_process_snapshot", return_value=current), \
                mock.patch.object(suite.os, "getpid", return_value=3):
            result = suite.client_process_baseline(NONCE)
        read.assert_called_once_with(Path("/tmp/onec-smoke/client-process-baseline.json"), 16384)
        return result

    def test_baseline_allows_only_exact_original_identities_plus_current_runner(self):
        self.assertEqual(self.validate(), {(1, "10"), (2, "20"), (3, "30")})
        self.assertEqual(self.validate(current={(1, "10"), (3, "30")}), {(1, "10"), (2, "20"), (3, "30")})

    def test_stale_process_reused_pid_missing_runner_or_ambiguous_runner_rejected(self):
        for current in ({(1, "10"), (2, "20"), (3, "30"), (4, "40")},
                        {(1, "10"), (2, "999"), (3, "30")},
                        {(1, "10"), (2, "20")},
                        {(1, "10"), (3, "30"), (3, "31")}):
            with self.subTest(current=current), self.assertRaisesRegex(suite.FullError, "^process_failed$"):
                self.validate(current=current)

    def test_finite_strict_schema_nonce_types_ranges_and_unique_identities(self):
        edits = [lambda d: d.update(extra="PRIVATE"), lambda d: d.pop("schema"),
                 lambda d: d.update(schema=True), lambda d: d.update(schema=2),
                 lambda d: d.update(nonce="0" * 32), lambda d: d.update(processes=[]),
                 lambda d: d.update(processes={}), lambda d: d.update(processes=[[1, "10"]] * 2),
                 lambda d: d.update(processes=[[0, "10"]]), lambda d: d.update(processes=[[4_194_305, "10"]]),
                 lambda d: d.update(processes=[[True, "10"]]), lambda d: d.update(processes=[[1, 10]]),
                 lambda d: d.update(processes=[[1, "-1"]]), lambda d: d.update(processes=[[1, ""]]),
                 lambda d: d.update(processes=[[1, "1" * 21]]), lambda d: d.update(processes=[[1, "PRIVATE"]]),
                 lambda d: d.update(processes=[[1, "10", "extra"]]),
                 lambda d: d.update(processes=[[number, "10"] for number in range(1, 258)])]
        for index, edit in enumerate(edits):
            value = copy.deepcopy(self.baseline)
            edit(value)
            with self.subTest(index=index), self.assertRaises(suite.FullError):
                self.validate(value)
        raw = json.dumps(self.baseline).encode().replace(b'"schema": 1', b'"schema": 1, "schema": 1')
        with self.assertRaises(suite.FullError):
            self.validate(raw=raw)

    def test_snapshot_failure_cannot_be_treated_as_an_empty_baseline(self):
        with mock.patch.object(suite, "secure_bytes", return_value=json.dumps(self.baseline).encode()), \
                mock.patch.object(suite, "client_process_snapshot", side_effect=suite.FullError("process_failed")), \
                self.assertRaisesRegex(suite.FullError, "^process_failed$"):
            suite.client_process_baseline(NONCE)


class ClientProcessDiagnosticsTests(unittest.TestCase):
    def test_default_is_exact_finite_schema_and_independent_per_record(self):
        expected = process_diagnostics(stage="not_checked")
        self.assertEqual(suite.empty_process_diagnostics(), expected)
        self.assertEqual(tuple(suite.PROCESS_CLASSES), PROCESS_CLASSES)
        first, second = suite.empty_client_report(), suite.empty_client_report()
        first["process_diagnostics"]["classes"]["native"] = 5
        self.assertEqual(second["process_diagnostics"], expected)
        self.assertEqual(full.validate_process_diagnostics(expected), expected)

    def test_allowed_reason_stage_and_boundary_counts_roundtrip(self):
        for value in (process_diagnostics(stage="not_checked"),
                      process_diagnostics(stage="baseline", reason="unverified"),
                      process_diagnostics(stage="before_probe", reason="native_not_quiet"),
                      process_diagnostics(),
                      process_diagnostics(stage="baseline", reason="unexpected_processes",
                                          classes={"unreadable": 256}, zombie_count=256)):
            with self.subTest(value=value):
                self.assertEqual(full.validate_process_diagnostics(value), value)

    def test_unknown_fields_enums_wrong_types_bounds_and_inconsistent_counts_fail_closed(self):
        edits = [lambda d: d.update(pid=12345), lambda d: d.update(command_line="PRIVATE"),
                 lambda d: d.pop("classes"), lambda d: d.update(stage="PRIVATE"),
                 lambda d: d.update(stage=[]), lambda d: d.update(reason="PRIVATE"),
                 lambda d: d.update(reason=[]), lambda d: d.update(unexpected_count=True),
                 lambda d: d.update(unexpected_count=-1), lambda d: d.update(unexpected_count=257),
                 lambda d: d.update(unexpected_count=1), lambda d: d.update(zombie_count=True),
                 lambda d: d.update(zombie_count=-1), lambda d: d.update(zombie_count=1),
                 lambda d: d.update(zombie_count=257), lambda d: d.update(classes=[]),
                 lambda d: d["classes"].pop("other"), lambda d: d["classes"].update(PRIVATE=0),
                 lambda d: d["classes"].update(native=True), lambda d: d["classes"].update(native=-1),
                 lambda d: d["classes"].update(native=257), lambda d: d["classes"].update(native=1),
                 lambda d: d.update(classes={**d["classes"], "native": 1}, unexpected_count=1)]
        envelope, inputs, modules = host_fixture.fixture()
        inputs[suite.CLIENT_SOURCE] = "c" * 64
        modules["client_probe"] = "d" * 64
        record = suite.empty_client_report()
        record.update(status="failed", failure_kind="process_failed")
        envelope["report"]["stage3"].update(status="failed", failure_kind="process_failed", client_probe=record)
        envelope["report"].update(status="stage3_failed", native_tests_completed=False)
        envelope["outputs"] = []
        for index, edit in enumerate(edits):
            changed = copy.deepcopy(envelope)
            edit(changed["report"]["stage3"]["client_probe"]["process_diagnostics"])
            with self.subTest(index=index), self.assertRaisesRegex(full.FullError, "^invalid_full_envelope$"):
                host_fixture.validate(changed, inputs, modules)

    def test_classification_exports_counts_only_not_pids_names_paths_or_starttimes(self):
        entries = [(11111, "native", "/opt/1cv8t/x86_64/8.3.27.1508/1cv8t", "S"),
                   (11112, "display", "/usr/bin/Xtigervnc", "S"),
                   (11113, "session_bus", "/usr/bin/dbus-daemon", "S"),
                   (11114, "shell", "/bin/bash", "S"),
                   (11115, "python", "/usr/bin/python3.10", "S"),
                   (11116, "other", "/PRIVATE/unknown-executable", "S"),
                   (11117, "other", "/PRIVATE/deleted (deleted)", "Z"),
                   (11118, "unreadable", None, "Z")]
        processes = {}
        for pid, _, executable, state in entries:
            process, stat_file, executable_file = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
            stat_file.read_text.return_value = f"{pid} (PRIVATE command (with) spaces) " + " ".join([state] + ["0"] * 18 + ["987654321"])
            if executable is None:
                executable_file.readlink.side_effect = PermissionError("PRIVATE")
            else:
                # Exact Linux /proc text, not the host OS's Path normalization.
                executable_file.readlink.return_value = executable
            process.__truediv__.side_effect = lambda name, stat_file=stat_file, executable_file=executable_file: stat_file if name == "stat" else executable_file
            processes[str(pid)] = process
        proc = mock.MagicMock()
        proc.__truediv__.side_effect = processes.__getitem__
        with mock.patch.object(suite, "Path", return_value=proc):
            diagnostic = suite.unexpected_process_diagnostics({(pid, "987654321") for pid, *_ in entries}, "baseline")
        expected = process_diagnostics(stage="baseline", reason="unexpected_processes",
            classes={"native": 1, "display": 1, "session_bus": 1, "shell": 1, "python": 1, "other": 2, "unreadable": 1},
            zombie_count=2)
        self.assertEqual(diagnostic, expected)
        self.assertEqual(full.validate_process_diagnostics(diagnostic), diagnostic)
        rendered = json.dumps(diagnostic)
        for private in ("PRIVATE", "/usr/", "/opt/", "11111", "987654321", "command"):
            self.assertNotIn(private, rendered)

    def test_reused_identity_and_unreadable_stat_are_unreadable_not_invented_classes(self):
        proc, process = mock.MagicMock(), mock.MagicMock()
        proc.__truediv__.return_value = process
        stat_file = process.__truediv__.return_value
        with mock.patch.object(suite, "Path", return_value=proc):
            for raw in ("123 (x) " + " ".join(["S"] + ["0"] * 18 + ["new-start"]), "PRIVATE"):
                stat_file.read_text.return_value = raw
                result = suite.unexpected_process_diagnostics({(123, "old-start")}, "after_exit")
                self.assertEqual(result, process_diagnostics(stage="after_exit", reason="unexpected_processes", classes={"unreadable": 1}))
            stat_file.read_text.side_effect = FileNotFoundError()
            result = suite.unexpected_process_diagnostics({(123, "old-start")}, "after_exit")
            self.assertEqual(result["classes"]["unreadable"], 1)

    def test_more_than_256_unexpected_processes_fail_before_inspection(self):
        with mock.patch.object(suite, "Path") as path, self.assertRaisesRegex(suite.FullError, "^process_failed$"):
            suite.unexpected_process_diagnostics({(number, "1") for number in range(1, 258)}, "baseline")
        path.assert_not_called()


class ClientHostContractTests(unittest.TestCase):
    def setUp(self):
        self.envelope, self.inputs, self.modules = host_fixture.fixture()
        self.inputs[suite.CLIENT_SOURCE] = "c" * 64
        self.modules["client_probe"] = "d" * 64
        self.client = {"status": "ok", "failure_kind": "none", "source_sha256": "c" * 64,
                       "process_diagnostics": process_diagnostics(),
                       "module_sha256": "d" * 64, "roundtrip_sha256": "d" * 64,
                       **dict.fromkeys(suite.CLIENT_FLAGS, True)}
        self.envelope["report"]["stage3"]["client_probe"] = self.client

    def validate(self, envelope=None):
        return host_fixture.validate(self.envelope if envelope is None else envelope,
                                     self.inputs, self.modules)

    def test_conditional_client_section_roundtrips_only_finite_metadata(self):
        report, outputs = self.validate()
        self.assertEqual(report["stage3"]["client_probe"], self.client)
        self.assertEqual(list(outputs), list(full.SCENARIOS))
        self.assertEqual(set(self.client), CLIENT_KEYS)
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_missing_client_section_or_module_identity_cannot_claim_opt_in_success(self):
        self.envelope["report"]["stage3"].pop("client_probe")
        with self.assertRaises(full.FullError):
            self.validate()
        self.envelope["report"]["stage3"]["client_probe"] = self.client
        self.modules.pop("client_probe")
        with self.assertRaises(full.FullError):
            self.validate()

    def test_unrequested_client_section_cannot_appear_in_legacy_report(self):
        envelope, inputs, modules = host_fixture.fixture()
        envelope["report"]["stage3"]["client_probe"] = self.client
        with self.assertRaises(full.FullError):
            host_fixture.validate(envelope, inputs, modules)

    def test_success_rejects_unknown_fields_values_types_hashes_and_incomplete_flags(self):
        edits = [lambda d: d.update(raw_marker="PRIVATE"), lambda d: d.pop("quiet"),
                 lambda d: d.update(status="PRIVATE"), lambda d: d.update(status=True),
                 lambda d: d.update(status=[]), lambda d: d.update(failure_kind="PRIVATE"),
                 lambda d: d.update(failure_kind="timeout"), lambda d: d.update(source_sha256="e" * 64),
                 lambda d: d.update(module_sha256="e" * 64), lambda d: d.update(roundtrip_sha256="e" * 64)]
        for key in suite.CLIENT_FLAGS:
            for value in (False, 1, None, "true"):
                edits.append(lambda d, key=key, value=value: d.update({key: value}))
        for key in ("source_sha256", "module_sha256", "roundtrip_sha256"):
            edits.append(lambda d, key=key: d.update({key: None}))
        for index, edit in enumerate(edits):
            envelope = copy.deepcopy(self.envelope)
            edit(envelope["report"]["stage3"]["client_probe"])
            with self.subTest(index=index), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_timeout_after_completion_remains_failure_and_exports_no_case_payloads(self):
        self.client.update(status="failed", failure_kind="timeout", process_exited=False, witness_verified=False)
        self.envelope["report"].update(status="stage3_failed", native_tests_completed=False)
        self.envelope["report"]["stage3"].update(status="failed", failure_kind="timeout")
        with self.assertRaises(full.FullError):
            self.validate()
        self.envelope["outputs"] = []
        report, outputs = self.validate()
        self.assertEqual(outputs, {})
        self.assertTrue(report["stage3"]["client_probe"]["completed"])
        self.assertFalse(report["native_tests_completed"])
        for update in ({"witness_verified": True}, {"failure_kind": "none"}, {"failure_kind": "prerequisites_failed"}):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["client_probe"].update(update)
            with self.subTest(update=update), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_not_started_client_has_no_evidence_and_cannot_satisfy_success(self):
        not_started = suite.empty_client_report()
        self.assertEqual(full.validate_client_probe(not_started, "c" * 64, "d" * 64), not_started)
        for key, value in (("entered", True), ("source_sha256", "c" * 64),
                           ("failure_kind", "timeout"), ("witness_verified", True)):
            changed = copy.deepcopy(not_started)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                full.validate_client_probe(changed, "c" * 64, "d" * 64)
        self.envelope["report"]["stage3"]["client_probe"] = not_started
        with self.assertRaises(full.FullError):
            self.validate()

    def test_positive_success_requires_verified_after_exit_process_diagnostics(self):
        diagnostics = [process_diagnostics(stage="not_checked"), process_diagnostics(stage="baseline"),
                       process_diagnostics(stage="before_probe"),
                       process_diagnostics(reason="unverified"), process_diagnostics(reason="native_not_quiet"),
                       process_diagnostics(reason="unexpected_processes", classes={"other": 1})]
        for diagnostic in diagnostics:
            changed = copy.deepcopy(self.envelope)
            changed["report"]["stage3"]["client_probe"]["process_diagnostics"] = diagnostic
            with self.subTest(diagnostic=diagnostic), self.assertRaises(full.FullError):
                self.validate(changed)
        record = suite.empty_client_report()
        record["process_diagnostics"] = process_diagnostics()
        with self.assertRaises(ValueError):
            full.validate_client_probe(record, "c" * 64, "d" * 64)

    def test_client_cannot_start_before_all_six_native_cases_complete(self):
        stage = suite.empty_report(host_fixture.NONCE, client_probe=True)
        stage.update(status="failed", failure_kind="process_failed", input_sha256=self.inputs)
        stage["client_probe"] = self.client
        self.envelope["report"].update(status="stage3_failed", native_tests_completed=False, stage3=stage)
        self.envelope["outputs"] = []
        with self.assertRaises(full.FullError):
            self.validate()
        stage["client_probe"] = suite.empty_client_report()
        report, outputs = self.validate()
        self.assertEqual(outputs, {})
        self.assertEqual(report["stage3"]["client_probe"]["status"], "not_started")


class ClientWatchdogHostTests(unittest.TestCase):
    def setUp(self):
        ClientHostContractTests.setUp(self)
        self.watchdog = {**self.client, "completed": False, "process_exited": False,
                         "witness_verified": False, "timeout_verified": True}
        self.envelope["report"]["stage3"]["client_watchdog"] = self.watchdog

    def validate(self, envelope=None, *, watchdog_check=True):
        return full.validate_envelope(host_fixture.encode(self.envelope if envelope is None else envelope),
            host_fixture.NONCE, self.inputs, self.modules, smoke.validate_report, watchdog_check=watchdog_check)

    def test_explicit_expected_negative_proof_roundtrips_with_positive_client_separate(self):
        report, outputs = self.validate()
        self.assertEqual(report["stage3"]["client_watchdog"], self.watchdog)
        self.assertTrue(report["stage3"]["client_probe"]["witness_verified"])
        self.assertFalse(report["stage3"]["client_watchdog"]["witness_verified"])
        self.assertEqual(list(outputs), list(full.SCENARIOS))

    def test_watchdog_section_required_only_when_explicitly_requested(self):
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=False)
        self.envelope["report"]["stage3"].pop("client_watchdog")
        with self.assertRaises(full.FullError):
            self.validate()
        report, _ = self.validate(watchdog_check=False)
        self.assertNotIn("client_watchdog", report["stage3"])
        self.inputs.pop(suite.CLIENT_SOURCE)
        self.envelope["report"]["stage3"].pop("client_probe")
        with self.assertRaises(full.FullError):
            self.validate()

    def test_expected_negative_schema_is_exact_including_bool_types_and_hashes(self):
        for key in self.watchdog:
            value = self.watchdog[key]
            replacements = (not value, 1 if value else 0, None) if type(value) is bool else (None, "PRIVATE")
            for replacement in replacements:
                envelope = copy.deepcopy(self.envelope)
                envelope["report"]["stage3"]["client_watchdog"][key] = replacement
                with self.subTest(key=key, replacement=replacement), self.assertRaises(full.FullError):
                    self.validate(envelope)
        for edit in (lambda d: d.pop("timeout_verified"), lambda d: d.update(path="PRIVATE"),
                     lambda d: d.update(failure_kind="timeout")):
            envelope = copy.deepcopy(self.envelope)
            edit(envelope["report"]["stage3"]["client_watchdog"])
            with self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_failed_watchdog_cannot_export_six_payloads_or_claim_timeout_verified(self):
        self.watchdog.update(status="failed", failure_kind="invalid_result", timeout_verified=False)
        self.envelope["report"].update(status="stage3_failed", native_tests_completed=False)
        self.envelope["report"]["stage3"].update(status="failed", failure_kind="invalid_result")
        with self.assertRaises(full.FullError):
            self.validate()
        self.envelope["outputs"] = []
        report, outputs = self.validate()
        self.assertEqual(outputs, {})
        self.assertFalse(report["native_tests_completed"])
        self.watchdog["timeout_verified"] = True
        with self.assertRaises(full.FullError):
            self.validate()

    def test_watchdog_cannot_start_before_positive_client_finishes(self):
        self.client.update(status="failed", failure_kind="timeout", process_exited=False, witness_verified=False)
        self.envelope["report"].update(status="stage3_failed", native_tests_completed=False)
        self.envelope["report"]["stage3"].update(status="failed", failure_kind="timeout")
        self.envelope["outputs"] = []
        with self.assertRaises(full.FullError):
            self.validate()
        self.envelope["report"]["stage3"]["client_watchdog"] = suite.empty_watchdog_report()
        report, outputs = self.validate()
        self.assertEqual(outputs, {})
        self.assertEqual(report["stage3"]["client_watchdog"]["status"], "not_started")

    def test_success_cannot_be_substituted_for_explicit_timeout_proof(self):
        self.envelope["report"]["stage3"]["client_watchdog"] = {**self.client, "timeout_verified": False}
        with self.assertRaises(full.FullError):
            self.validate()

    def test_accepted_watchdog_requires_verified_after_exit_process_diagnostics(self):
        for diagnostic in (process_diagnostics(stage="not_checked"), process_diagnostics(stage="baseline"),
                           process_diagnostics(reason="unverified"),
                           process_diagnostics(reason="native_not_quiet"),
                           process_diagnostics(reason="unexpected_processes", classes={"session_bus": 1})):
            changed = copy.deepcopy(self.envelope)
            changed["report"]["stage3"]["client_watchdog"]["process_diagnostics"] = diagnostic
            with self.subTest(diagnostic=diagnostic), self.assertRaises(full.FullError):
                self.validate(changed)


class ClientSuiteIntegrationTests(unittest.TestCase):
    """Reuse scenario fixtures without inheriting and rerunning their test suite."""
    use_fixture_reader = os.name == "nt"
    argument = staticmethod(stage_fixture.FullSuiteHarness.argument)
    native = stage_fixture.FullSuiteHarness.native

    def setUp(self):
        stage_fixture.FullSuiteHarness.setUp(self)
        path = self.inputs / suite.CLIENT_TARGET
        path.write_bytes((ROOT / suite.CLIENT_SOURCE).read_bytes())
        source = path.read_bytes()
        module = suite.generated_module(source)
        self.client = {"status": "ok", "failure_kind": "none", "source_sha256": suite.digest(source),
                       "process_diagnostics": process_diagnostics(),
                       "module_sha256": suite.digest(module), "roundtrip_sha256": suite.digest(module),
                       **dict.fromkeys(suite.CLIENT_FLAGS, True)}

    def run_suite(self):
        return suite.run_suite(self.launcher, self.platform, self.epf, self.work,
                               self.inputs, NONCE, client_probe=True)

    def test_probe_runs_only_after_all_six_cases_and_includes_24_source_hashes(self):
        def probe(platform, root, inputs, nonce, hashes):
            self.assertEqual(self.events, [(name, mode) for name in suite.SCENARIOS for mode in ("build", "enterprise")])
            self.assertEqual((platform, root, inputs, nonce), (self.platform, self.work / "client-probe", self.inputs, NONCE))
            self.assertEqual(len(hashes), 24)
            return self.client
        with mock.patch.object(suite, "run_client_probe", side_effect=probe) as run:
            result = self.run_suite()
        run.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["client_probe"], self.client)
        self.assertEqual(len(result["input_sha256"]), 24)
        modules = {name: suite.digest(suite.generated_module((self.inputs / f"scenarios/{name}.bsl").read_bytes()))
                   for name in suite.SCENARIOS}
        modules["client_probe"] = self.client["module_sha256"]
        report = host_fixture.bootstrap_report()
        report.update(stage3=result, native_tests_completed=True)
        raw = suite.build_envelope(report, NONCE, self.work, quiet=True)
        accepted, outputs = full.validate_envelope(raw, NONCE, result["input_sha256"], modules, smoke.validate_report)
        self.assertEqual(accepted["stage3"]["client_probe"], self.client)
        self.assertEqual(list(outputs), list(suite.SCENARIOS))

    def test_six_case_failure_keeps_probe_not_started(self):
        self.failure = ("dates", "enterprise")
        with mock.patch.object(suite, "run_client_probe") as run:
            result = self.run_suite()
        run.assert_not_called()
        self.assertEqual(result["failure_kind"], "process_failed")
        self.assertEqual(result["failed_case"], "dates")
        self.assertEqual(result["client_probe"], suite.empty_client_report())

    def test_client_failure_suppresses_all_outputs_but_retains_six_case_completion_metadata(self):
        self.client.update(status="failed", failure_kind="timeout", process_exited=False, witness_verified=False)
        with mock.patch.object(suite, "run_client_probe", return_value=self.client):
            result = self.run_suite()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_kind"], "timeout")
        self.assertIsNone(result["failed_case"])
        self.assertTrue(all(case["status"] == "ok" for case in result["cases"]))
        report = {"status": "stage3_failed", "native_tests_completed": False, "stage3": result}
        envelope = json.loads(suite.build_envelope(report, NONCE, self.work, quiet=True))
        self.assertEqual(envelope["outputs"], [])

    def test_missing_probe_source_fails_before_any_native_case(self):
        (self.inputs / suite.CLIENT_TARGET).unlink()
        with mock.patch.object(suite, "run_client_probe") as run:
            result = self.run_suite()
        run.assert_not_called()
        self.assertEqual(result["failure_kind"], "artifact_missing")
        self.assertEqual(result["input_sha256"], {})
        self.assertEqual(self.events, [])

    def test_watchdog_follows_positive_in_separate_fresh_directory_and_host_validates(self):
        calls = []
        watchdog = {**self.client, "completed": False, "process_exited": False,
                    "witness_verified": False, "timeout_verified": True}
        def probe(platform, root, inputs, nonce, hashes):
            calls.append("positive")
            self.assertEqual(root, self.work / "client-probe")
            self.assertEqual(len(self.events), 12)
            return self.client
        def negative(platform, root, inputs, nonce, hashes):
            self.assertEqual(calls, ["positive"])
            calls.append("negative")
            self.assertEqual(root, self.work / "client-watchdog")
            self.assertEqual((platform, inputs, nonce), (self.platform, self.inputs, NONCE))
            self.assertEqual(len(hashes), 24)
            return watchdog
        with mock.patch.object(suite, "run_client_probe", side_effect=probe), \
                mock.patch.object(suite, "run_client_watchdog", side_effect=negative):
            result = suite.run_suite(self.launcher, self.platform, self.epf, self.work, self.inputs,
                                     NONCE, client_probe=True, watchdog_check=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(calls, ["positive", "negative"])
        modules = {case["name"]: case["module_sha256"] for case in result["cases"]}
        modules["client_probe"] = self.client["module_sha256"]
        report = host_fixture.bootstrap_report()
        report.update(stage3=result, native_tests_completed=True)
        raw = suite.build_envelope(report, NONCE, self.work, quiet=True)
        accepted, outputs = full.validate_envelope(raw, NONCE, result["input_sha256"], modules,
                                                   smoke.validate_report, watchdog_check=True)
        self.assertEqual(accepted["stage3"]["client_watchdog"], watchdog)
        self.assertEqual(list(outputs), list(suite.SCENARIOS))

    def test_failed_positive_never_runs_watchdog_and_leaves_explicit_not_started_record(self):
        self.client.update(status="failed", failure_kind="timeout", process_exited=False, witness_verified=False)
        with mock.patch.object(suite, "run_client_probe", return_value=self.client), \
                mock.patch.object(suite, "run_client_watchdog") as negative:
            result = suite.run_suite(self.launcher, self.platform, self.epf, self.work, self.inputs,
                                     NONCE, client_probe=True, watchdog_check=True)
        negative.assert_not_called()
        self.assertEqual(result["failure_kind"], "timeout")
        self.assertEqual(result["client_watchdog"], suite.empty_watchdog_report())

    def test_failed_watchdog_suppresses_payload_without_relabeling_positive_witness(self):
        watchdog = suite.empty_watchdog_report()
        watchdog.update(status="failed", failure_kind="invalid_result")
        with mock.patch.object(suite, "run_client_probe", return_value=self.client), \
                mock.patch.object(suite, "run_client_watchdog", return_value=watchdog):
            result = suite.run_suite(self.launcher, self.platform, self.epf, self.work, self.inputs,
                                     NONCE, client_probe=True, watchdog_check=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_kind"], "invalid_result")
        self.assertTrue(result["client_probe"]["witness_verified"])
        self.assertFalse(result["client_watchdog"]["timeout_verified"])
        self.assertIsNone(result["failed_case"])
        report = {"status": "stage3_failed", "native_tests_completed": False, "stage3": result}
        self.assertEqual(json.loads(suite.build_envelope(report, NONCE, self.work, quiet=True))["outputs"], [])


class ClientSummaryTests(unittest.TestCase):
    """Public summary must not promote six-case success over a failed client gate."""
    def probe(self, *, client=True, watchdog=False, completed=False):
        report = host_fixture.fixture()[0]["report"]
        report.update(status="ok" if completed else "stage3_failed", native_tests_completed=completed,
            native_cases_completed=True, native_evidence_accepted=False, native_transport_validated=False,
            private_payloads_removed=True, container_cleanup_verified=True, windows_goldens_unchanged=True,
            native_target=full.WINDOWS_TARGET, comparison_mode=full.BYTE_EXACT,
            comparison={"schema": 2, "status": "not_run", "acceptance_status": "not_run",
                        "native_target": full.WINDOWS_TARGET, "comparison_mode": full.BYTE_EXACT, "cases": []})
        stage = report["stage3"]
        stage.update(status="ok" if completed else "failed", failure_kind="none" if completed else "process_failed")
        if client:
            record = suite.empty_client_report()
            record.update(status="failed", failure_kind="process_failed",
                          process_diagnostics=process_diagnostics(stage="before_probe", reason="native_not_quiet"))
            if completed:
                record.update(status="ok", failure_kind="none", source_sha256="c" * 64,
                              module_sha256="d" * 64, roundtrip_sha256="d" * 64,
                              process_diagnostics=process_diagnostics(),
                              **dict.fromkeys(suite.CLIENT_FLAGS, True))
            stage["client_probe"] = record
        if watchdog:
            record = suite.empty_watchdog_report()
            if completed:
                record.update(status="ok", failure_kind="none", source_sha256="c" * 64,
                              module_sha256="d" * 64, roundtrip_sha256="d" * 64,
                              process_diagnostics=process_diagnostics(),
                              entered=True, quiet=True, timeout_verified=True)
            stage["client_watchdog"] = record
        return report

    def invoke(self, *, client=True, watchdog=False, completed=False, raised=False, missing_report=False):
        probe = self.probe(client=client, watchdog=watchdog, completed=completed)
        arguments = ["--execute-approved-image", "--full-suite"]
        if client:
            arguments.append("--client-probe")
        if watchdog:
            arguments.append("--client-watchdog-check")
        error = smoke.SmokeError("container_cleanup_unverified", validated_report=None if missing_report else probe)
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()) as stdout, \
                mock.patch.object(smoke, "run_smoke", side_effect=error if raised else None, return_value=probe):
            path = Path(temporary) / "report.json"
            code = smoke.main(arguments + ["--output", str(path)])
            report = json.loads(path.read_bytes())
            self.assertEqual(json.loads(stdout.getvalue()), report)
        return code, report

    def test_client_failure_after_six_cases_never_claims_all_native_tests_completed(self):
        for raised in (False, True):
            with self.subTest(raised=raised):
                code, report = self.invoke(raised=raised)
                self.assertEqual(code, 1)
                self.assertTrue(report["native_cases_completed"])
                self.assertFalse(report["native_tests_completed"])
                self.assertFalse(report["smoke_completed"])
                self.assertEqual(report["purpose"], "isolated-six-scenario-client-proof")

    def test_watchdog_failure_preserves_its_purpose_and_incomplete_gate(self):
        for raised in (False, True):
            with self.subTest(raised=raised):
                code, report = self.invoke(watchdog=True, raised=raised)
                self.assertEqual(code, 1)
                self.assertTrue(report["native_cases_completed"])
                self.assertFalse(report["native_tests_completed"])
                self.assertFalse(report["interpreter_comparison_completed"])
                self.assertEqual(report["purpose"], "isolated-six-scenario-client-watchdog-proof")

    def test_early_failure_without_validated_report_still_preserves_requested_purpose(self):
        for watchdog in (False, True):
            with self.subTest(watchdog=watchdog):
                code, report = self.invoke(watchdog=watchdog, raised=True, missing_report=True)
                self.assertEqual(code, 1)
                self.assertFalse(report["native_cases_completed"])
                self.assertFalse(report["native_tests_completed"])
                self.assertEqual(report["purpose"], "isolated-six-scenario-client-watchdog-proof" if watchdog else
                                                    "isolated-six-scenario-client-proof")

    def test_complete_requested_native_gate_can_be_reported_without_claiming_comparison(self):
        for watchdog in (False, True):
            with self.subTest(watchdog=watchdog):
                _, report = self.invoke(watchdog=watchdog, completed=True)
                self.assertTrue(report["native_cases_completed"])
                self.assertTrue(report["native_tests_completed"])
                self.assertFalse(report["interpreter_comparison_completed"])
                self.assertFalse(report["smoke_completed"])

    def test_legacy_mode_retains_six_case_completion_meaning_and_purpose(self):
        _, report = self.invoke(client=False)
        self.assertTrue(report["native_cases_completed"])
        self.assertTrue(report["native_tests_completed"])
        self.assertEqual(report["purpose"], "isolated-six-scenario-utc-comparison")


if __name__ == "__main__":
    unittest.main()

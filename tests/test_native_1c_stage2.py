"""Offline controller tests. Synthetic evidence is never a native 1C result.

The real stage controller, evidence gates, and EPF launcher execute here, but
synthetic metadata replaces the native dump and every process boundary is mocked. No Docker, 1C, or network is
needed, including on Windows. Process-group behavior is tested separately with
Linux-only mocks rather than starting or killing real processes.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
HELPERS = REPOSITORY / "scripts/native_1c_bootstrap"
# run_stage deliberately imports its colocated, script-style helpers.
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


from inject_modules import ROLE_NAME, ROLE_FILES, inject as inject_fixture


def load_controller():
    spec = importlib.util.spec_from_file_location(
        "native_stage2_under_test", HELPERS / "run_stage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPORT_FLAGS = {
    "modules_reimported", "bootstrap_verified", "named_designer_verified",
    "named_user_verified", "control_removed", "launcher_built",
    "simple_epf_passed", "security_change_attempted",
}
REPORT_KEYS = REPORT_FLAGS | {
    "schema", "status", "failed_stage", "failure_kind", "actual_version",
    "version_source", "simple_output_sha256", "security_settings_state", "diagnostics", "protection_observation",
}
SUCCESS_EVENTS = [
    "inject", "load", "redump", "bootstrap", "named_designer", "verify",
    "launcher_build", "test_module_build", "simple_epf",
]
EXPECTED_OUTPUT = b"native-smoke-v1\n42\n"


class Stage2Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "runtime with spaces"
        self.root.mkdir()
        self.inputs = self.directory / "inputs with spaces"
        launcher_inputs = self.inputs / "launcher"
        launcher_inputs.mkdir(parents=True)
        shutil.copyfile(REPOSITORY / "integrational_tests/test_launcher.py",
                        launcher_inputs / "test_launcher.py")
        shutil.copytree(REPOSITORY / "integrational_tests/launcher_1c",
                        launcher_inputs / "launcher_1c")
        (self.inputs / "bootstrap").mkdir()
        shutil.copyfile(HELPERS / "simple_smoke.bsl",
                        self.inputs / "bootstrap/simple_smoke.bsl")
        (self.root / "config").mkdir()
        shutil.copyfile(REPOSITORY / "tests/fixtures/native_bootstrap/Configuration.xml",
                        self.root / "config/Configuration.xml")
        self.module = load_controller()
        self.module.ROOT = self.root
        self.module.INPUTS = self.inputs
        self.module.ONEC = self.directory / "not a real platform" / "1cv8t"
        self.events = []
        self.commands = []
        self.manifest = None
        self.evidence = None
        self.failures = {}
        self.dump_results = {}
        self.missing_markers = set()
        self.marker_overrides = {}
        self.raw_markers = {}
        self.reimport_changes = set()
        self.metadata_changes = {}
        self.logs = {}
        self.artifacts_missing = set()
        self.simple_result = {"messages": ["native-smoke-v1", "42"], "error": ""}
        self.raw_simple_result = None
        self.native_hook = None
        self.inject_error = None
        # A regression must fail the test instead of ever launching an executable.
        self.start_patch(mock.patch.object(
            self.module.subprocess, "Popen",
            side_effect=AssertionError("Tests must never start a native process"),
        ))
        self.start_patch(mock.patch.object(self.module, "inject", side_effect=self.inject))
        self.start_patch(mock.patch.object(self.module, "process", side_effect=self.native))
        original_loader = self.module.load_launcher

        def load_launcher():
            launcher = original_loader()
            launcher.run_process = self.native
            return launcher

        self.start_patch(mock.patch.object(self.module, "load_launcher", side_effect=load_launcher))

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def inject(self, source, destination, *, run_id, user, evidence):
        self.events.append("inject")
        if self.inject_error is not None:
            raise self.inject_error
        self.assertEqual(source, self.root / "config")
        self.assertEqual(user, "NativeSmoke")
        self.evidence = Path(evidence)
        self.assertEqual(destination, self.evidence / "injected")
        # Only the rendered BSL literal represents a Linux container path. The
        # harness filesystem paths above remain native to Windows/macOS/Linux.
        # No rendered BSL executes in these offline tests.
        self.manifest = inject_fixture(source, destination, run_id=run_id, user=user,
                                       evidence="/tmp/native-offline/" + run_id)
        # Synthetic fixture XML and no native calls; this is not a native result.
        return self.manifest

    def marker(self, stage, hook):
        marker = {
            "protocol": self.module.PROTOCOL, "run_id": self.manifest["run_id"],
            "stage": stage, "hook": hook, "user": "NativeSmoke",
            "status": "ok", "error": "",
        }
        if hook == "session":
            marker.update(
                users_before=0 if stage == "bootstrap" else 1, users_after=1,
                persisted_user="NativeSmoke", persisted_protection_type="UnsafeOperationProtectionDescription",
                persisted_warning_type="Boolean",
                observed_protection_type="UnsafeOperationProtectionDescription",
                observed_warning_type="Boolean",
                persisted_warning=False, standard_authentication=True,
                current_user_at_start="" if stage == "bootstrap" else "NativeSmoke",
                current_protection_verified=stage == "verify", persisted_roles=[ROLE_NAME],
            )
            if stage == "verify":
                marker.update(current_protection_type="UnsafeOperationProtectionDescription",
                              current_warning_type="Boolean", current_warning=False, current_roles=[ROLE_NAME])
            else:
                marker["assigned_roles"] = [ROLE_NAME]
        else:
            marker.update(actual_version="8.3.27.1508", server_hook_verified=True)
        marker.update(self.marker_overrides.get((stage, hook), {}))
        return marker

    @staticmethod
    def argument(command, flag):
        return command[command.index(flag) + 1]

    def native(self, command, directory, console, timeout=120):
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], str(self.module.ONEC))
        self.assertEqual(self.argument(command, "/F"), str(self.root / "db"))
        self.assertEqual(timeout, 120)
        control = self.evidence / "control.json"
        if "/LoadConfigFromFiles" in command:
            stage = "load"
        elif "/DumpConfigToFiles" in command:
            stage = "named_designer" if "/N" in command else "redump"
        elif "/LoadExternalDataProcessorOrReportFromFiles" in command:
            index = command.index("/LoadExternalDataProcessorOrReportFromFiles")
            target = Path(command[index + 2])
            stage = "launcher_build" if target.name == "Launcher.epf" else "test_module_build"
        elif "/Execute" in command:
            stage = "simple_epf"
        else:
            self.assertTrue(control.is_file())
            stage = json.loads(control.read_text(encoding="utf-8"))["stage"]
        self.events.append(stage)
        self.commands.append((stage, command[:]))
        if stage in {"bootstrap", "verify"}:
            self.assertEqual(
                json.loads(control.read_text(encoding="utf-8")),
                {"protocol": self.module.PROTOCOL, "run_id": self.manifest["run_id"],
                 "stage": stage, "launch_token": self.manifest[stage + "_token"]},
            )
            self.assertEqual(self.argument(command, "/C"), self.manifest[stage + "_token"])
        else:
            self.assertFalse(control.exists(), "Control file leaked into " + stage)
        self.assertFalse(Path(console).exists())
        Path(console).write_bytes(b"offline console\n")
        log = Path(self.argument(command, "/Out"))
        log.write_text(self.logs.get(stage, "offline log\n"), encoding="utf-8")
        if self.native_hook is not None:
            self.native_hook(stage, command, directory)
        if stage in self.failures:
            raise self.module.StageError(self.failures[stage])
        if "/DumpResult" in command:
            result = self.dump_results.get(stage, b"0\n")
            if result is not None:
                Path(self.argument(command, "/DumpResult")).write_bytes(result)
        if stage in {"redump", "named_designer"}:
            target = Path(self.argument(command, "/DumpConfigToFiles"))
            shutil.copytree(self.evidence / "injected", target, dirs_exist_ok=True)
            if stage in self.reimport_changes:
                (target / "Ext/SessionModule.bsl").write_text("// changed\n", encoding="utf-8")
            if stage in self.metadata_changes:
                name, old, new = self.metadata_changes[stage]
                path = target / name
                path.write_text(path.read_text(encoding="utf-8-sig").replace(old, new), encoding="utf-8")
        elif stage in {"bootstrap", "verify"}:
            for hook in ("session", "managed"):
                key = stage, hook
                if key in self.missing_markers:
                    continue
                data = self.raw_markers.get(key)
                if data is None:
                    data = json.dumps(self.marker(stage, hook)).encode("utf-8")
                (self.evidence / (stage + "-" + hook + ".json")).write_bytes(data)
        elif stage in {"launcher_build", "test_module_build"}:
            if stage not in self.artifacts_missing:
                target.write_bytes(b"offline nonempty EPF fixture")
        elif stage == "simple_epf":
            request = json.loads(Path(self.argument(command, "/C")).read_text(encoding="utf-8"))
            data = self.raw_simple_result
            if data is None:
                data = json.dumps(self.simple_result).encode("utf-8")
            Path(request["result"]).write_bytes(data)

    def assert_report_schema(self, report):
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertIs(type(report["schema"]), int)
        self.assertEqual(report["schema"], 1)
        for flag in REPORT_FLAGS:
            self.assertIs(type(report[flag]), bool, flag)
        self.assertIn(report["status"], {"ok", "failed"})
        self.assertIn(report["failure_kind"], self.module.KINDS)
        self.assertIn(report["failed_stage"], self.module.STAGES | {None})
        self.assertIn(report["security_settings_state"], {"not_attempted", "unverified", "verified"})

    def assert_failed(self, report, stage, kind=None):
        self.assert_report_schema(report)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_stage"], stage)
        if kind is not None:
            self.assertEqual(report["failure_kind"], kind)
        self.assertFalse(report["simple_epf_passed"])
        self.assertIsNone(report["simple_output_sha256"])
        if self.evidence is not None:
            self.assertFalse((self.evidence / "control.json").exists())


class Stage2FlowTests(Stage2Harness):
    def test_injected_evidence_literal_is_container_posix_on_every_host(self):
        report = self.module.run()
        self.assertEqual(report["status"], "ok")
        expected = "/tmp/native-offline/" + self.manifest["run_id"]
        self.assertEqual(self.manifest["evidence_root"], expected)
        self.assertEqual(self.manifest["request_path"], expected + "/control.json")
        self.assertNotEqual(str(self.evidence), expected)
        self.assertTrue((self.evidence / "injected/Ext/SessionModule.bsl").is_file())

    def test_complete_flow_has_exact_report_and_no_control_at_named_designer_or_epfs(self):
        report = self.module.run()
        self.assert_report_schema(report)
        self.assertEqual(report, {
            "schema": 1, "status": "ok", "failed_stage": None,
            "failure_kind": "none", "actual_version": "8.3.27.1508",
            "version_source": "SystemInfo.AppVersion",
            "simple_output_sha256": hashlib.sha256(EXPECTED_OUTPUT).hexdigest(),
            "security_settings_state": "verified", "diagnostics": self.module.empty_diagnostics(),
            "protection_observation": dict(stage="verify", property_type="UnsafeOperationProtectionDescription", warning_type="Boolean"),
            **dict.fromkeys(REPORT_FLAGS, True),
        })
        self.assertEqual(self.events, SUCCESS_EVENTS)
        self.assertEqual((self.evidence / "simple.out").read_bytes(), EXPECTED_OUTPUT)
        self.assertFalse((self.evidence / "control.json").exists())
        self.assertEqual(self.module.EXPECTED_MESSAGES, ["native-smoke-v1", "42"])

    def test_anonymous_bootstrap_and_exact_separate_named_user_arguments(self):
        self.assertEqual(self.module.run()["status"], "ok")
        for stage, command in self.commands:
            with self.subTest(stage=stage):
                if stage in {"load", "redump", "bootstrap"}:
                    self.assertNotIn("/N", command)
                    self.assertNotIn("NativeSmoke", command)
                else:
                    self.assertEqual(command.count("/N"), 1)
                    self.assertEqual(self.argument(command, "/N"), "NativeSmoke")
                    self.assertEqual(command.count("NativeSmoke"), 1)
                self.assertNotIn("/NNativeSmoke", command)
                self.assertNotIn("/N NativeSmoke", command)
                self.assertNotIn("/P", command)
                self.assertNotIn("/UC", command)
                self.assertIn("/DisableStartupDialogs", command)
                self.assertIn("/DisableStartupMessages", command)

    def test_injection_failure_stops_before_native_and_security_attempt(self):
        self.inject_error = self.module.DraftError("private fixture rejection")
        report = self.module.run()
        self.assert_failed(report, "inject", "metadata_rejected")
        self.assertEqual(self.events, ["inject"])
        self.assertFalse(report["security_change_attempted"])
        self.assertEqual(report["security_settings_state"], "not_attempted")
        self.assertNotIn("private fixture rejection", json.dumps(report))

    def test_nonzero_load_stops_redump_and_bootstrap(self):
        self.failures["load"] = "process_failed"
        report = self.module.run()
        self.assert_failed(report, "load", "process_failed")
        self.assertEqual(self.events, ["inject", "load"])
        self.assertFalse(report["modules_reimported"])
        self.assertTrue(report["security_change_attempted"])
        self.assertEqual(report["security_settings_state"], "unverified")

    def test_load_missing_dumpresult_stops_even_when_process_succeeds(self):
        self.dump_results["load"] = None
        report = self.module.run()
        self.assert_failed(report, "load", "invalid_dump_result")
        self.assertEqual(self.events, ["inject", "load"])
        self.assertTrue(report["security_change_attempted"])

    def test_load_nonzero_dumpresult_stops_even_when_process_succeeds(self):
        self.dump_results["load"] = b"1\n"
        report = self.module.run()
        self.assert_failed(report, "load", "invalid_dump_result")
        self.assertEqual(self.events, ["inject", "load"])

    def test_reimport_mismatch_stops_before_user_creation(self):
        self.reimport_changes.add("redump")
        report = self.module.run()
        self.assert_failed(report, "redump", "module_mismatch")
        self.assertEqual(self.events, SUCCESS_EVENTS[:3])
        self.assertFalse(report["modules_reimported"])
        self.assertTrue(report["security_change_attempted"])
        self.assertEqual(report["security_settings_state"], "unverified")

    def test_bootstrap_timeout_is_attempted_but_not_verified_and_cleans_control(self):
        self.failures["bootstrap"] = "timeout"
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "timeout")
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])
        self.assertTrue(report["modules_reimported"])
        self.assertTrue(report["security_change_attempted"])
        self.assertFalse(report["bootstrap_verified"])
        self.assertEqual(report["security_settings_state"], "unverified")
        self.assertIsNone(report["actual_version"])
        self.assertEqual(report["version_source"], "not_measured")

    def test_bootstrap_missing_session_marker_is_not_success(self):
        self.missing_markers.add(("bootstrap", "session"))
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "hook_missing")
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])
        self.assertTrue(report["security_change_attempted"])
        self.assertEqual(report["security_settings_state"], "unverified")
        self.assertFalse(report["bootstrap_verified"])

    def test_bootstrap_missing_managed_marker_is_not_success(self):
        self.missing_markers.add(("bootstrap", "managed"))
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "hook_missing")
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])
        self.assertIsNone(report["actual_version"])

    def test_malformed_session_marker_is_rejected_and_control_removed(self):
        self.raw_markers["bootstrap", "session"] = b"not JSON"
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "marker_invalid")
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])
        self.assertFalse(report["bootstrap_verified"])
        self.assertEqual(report["security_settings_state"], "unverified")

    def test_malformed_managed_marker_is_rejected_without_disclosing_native_text(self):
        self.raw_markers["bootstrap", "managed"] = b'{"private":"do not disclose",'
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "marker_invalid")
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])
        self.assertFalse(report["bootstrap_verified"])
        self.assertIsNone(report["actual_version"])
        self.assertNotIn("do not disclose", json.dumps(report))

    def test_wrong_bootstrap_version_is_rejected_but_numeric_measurement_is_reported(self):
        self.marker_overrides["bootstrap", "managed"] = {"actual_version": "8.3.26.9999"}
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "version_mismatch")
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])
        self.assertEqual(report["actual_version"], "8.3.26.9999")
        self.assertEqual(report["version_source"], "SystemInfo.AppVersion")
        self.assertFalse(report["bootstrap_verified"])
        self.assertEqual(report["security_settings_state"], "unverified")

    def test_wrong_verify_version_reports_fresh_measurement_without_verification(self):
        self.marker_overrides["verify", "managed"] = {"actual_version": "8.3.26.9999"}
        report = self.module.run()
        self.assert_failed(report, "verify", "version_mismatch")
        self.assertEqual(self.events, SUCCESS_EVENTS[:6])
        self.assertEqual(report["actual_version"], "8.3.26.9999")
        self.assertEqual(report["version_source"], "SystemInfo.AppVersion")
        self.assertTrue(report["bootstrap_verified"])
        self.assertFalse(report["named_user_verified"])

    def test_version_from_wrong_identity_is_never_exported(self):
        self.marker_overrides["bootstrap", "managed"] = {
            "run_id": "stale-run", "actual_version": "8.3.26.9999",
        }
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "marker_invalid")
        self.assertIsNone(report["actual_version"])
        self.assertEqual(report["version_source"], "not_measured")
        self.assertNotIn("8.3.26.9999", json.dumps(report))
        self.assertEqual(self.events, SUCCESS_EVENTS[:4])

    def test_unbounded_version_text_is_never_exported(self):
        self.marker_overrides["bootstrap", "managed"] = {
            "actual_version": "8.3.27.1508 private native error",
        }
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "marker_invalid")
        self.assertIsNone(report["actual_version"])
        self.assertNotIn("private native error", json.dumps(report))

    def test_managed_version_requires_valid_session_pair_before_export(self):
        self.marker_overrides["bootstrap", "session"] = {"persisted_warning": True}
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "marker_invalid")
        self.assertIsNone(report["actual_version"])
        self.assertEqual(report["version_source"], "not_measured")
        self.assertEqual(report["security_settings_state"], "unverified")

    def test_named_designer_failure_prevents_verification_and_epfs(self):
        self.failures["named_designer"] = "process_failed"
        report = self.module.run()
        self.assert_failed(report, "named_designer", "process_failed")
        self.assertEqual(self.events, SUCCESS_EVENTS[:5])
        self.assertTrue(report["bootstrap_verified"])
        self.assertFalse(report["named_designer_verified"])
        self.assertFalse(report["named_user_verified"])
        self.assertFalse(report["launcher_built"])
        self.assertTrue(report["security_change_attempted"])
        self.assertEqual(report["security_settings_state"], "verified")

    def test_named_designer_reimport_mismatch_stops_verification(self):
        self.reimport_changes.add("named_designer")
        report = self.module.run()
        self.assert_failed(report, "named_designer")
        self.assertEqual(self.events, SUCCESS_EVENTS[:5])
        self.assertFalse(report["named_designer_verified"])
        self.assertFalse(report["named_user_verified"])

    def test_named_metadata_permission_change_stops_verification(self):
        self.metadata_changes["named_designer"] = (ROLE_FILES[1], "<name>ThickClient</name>", "<name>ThinClient</name>")
        report = self.module.run()
        self.assert_failed(report, "named_designer", "module_mismatch")
        self.assertEqual(self.events, SUCCESS_EVENTS[:5])
        self.assertFalse(report["named_designer_verified"])
        self.assertFalse(report["named_user_verified"])

    def test_initial_metadata_permission_change_stops_before_user_creation(self):
        self.metadata_changes["redump"] = (ROLE_FILES[1], "<setForNewObjects>false", "<setForNewObjects>true")
        report = self.module.run()
        self.assert_failed(report, "redump", "module_mismatch")
        self.assertEqual(self.events, SUCCESS_EVENTS[:3])
        self.assertTrue(report["security_change_attempted"])
        self.assertEqual(report["security_settings_state"], "unverified")
        self.assertFalse(report["bootstrap_verified"])

    def test_assigned_role_marker_is_required_before_bootstrap_success(self):
        self.marker_overrides["bootstrap", "session"] = {"assigned_roles": []}
        report = self.module.run()
        self.assert_failed(report, "bootstrap", "marker_invalid")
        self.assertFalse(report["bootstrap_verified"])
        self.assertEqual(report["security_settings_state"], "unverified")

    def test_fresh_role_marker_is_required_before_epf_execution(self):
        self.marker_overrides["verify", "session"] = {"current_roles": [ROLE_NAME, "Other"]}
        report = self.module.run()
        self.assert_failed(report, "verify", "marker_invalid")
        self.assertFalse(report["named_user_verified"])
        self.assertFalse(report["launcher_built"])

    def test_named_verify_cannot_pass_with_incorrect_current_user(self):
        self.marker_overrides["verify", "session"] = {"current_user_at_start": "SomeoneElse"}
        report = self.module.run()
        self.assert_failed(report, "verify", "marker_invalid")
        self.assertEqual(self.events, SUCCESS_EVENTS[:6])
        self.assertTrue(report["bootstrap_verified"])
        self.assertTrue(report["named_designer_verified"])
        self.assertFalse(report["named_user_verified"])
        self.assertFalse(report["launcher_built"])

    def test_named_verify_requires_actual_boolean_false_not_zero(self):
        self.marker_overrides["verify", "session"] = {"current_warning": 0}
        report = self.module.run()
        self.assert_failed(report, "verify", "marker_invalid")
        self.assertEqual(self.events, SUCCESS_EVENTS[:6])
        self.assertFalse(report["named_user_verified"])

    def test_launcher_build_failure_stops_test_module_and_execution(self):
        self.failures["launcher_build"] = "process_failed"
        report = self.module.run()
        self.assert_failed(report, "launcher_build", "process_failed")
        self.assertEqual(self.events, SUCCESS_EVENTS[:7])
        self.assertTrue(report["control_removed"])
        self.assertTrue(report["named_user_verified"])
        self.assertFalse(report["launcher_built"])

    def test_launcher_build_requires_dumpresult_even_if_epf_exists(self):
        self.dump_results["launcher_build"] = None
        report = self.module.run()
        self.assert_failed(report, "launcher_build")
        self.assertEqual(self.events, SUCCESS_EVENTS[:7])
        self.assertTrue((self.evidence / "Launcher.epf").is_file())
        self.assertFalse(report["launcher_built"])

    def test_launcher_build_requires_epf_even_if_dumpresult_is_zero(self):
        self.artifacts_missing.add("launcher_build")
        report = self.module.run()
        self.assert_failed(report, "launcher_build")
        self.assertEqual(self.events, SUCCESS_EVENTS[:7])
        self.assertFalse(report["launcher_built"])

    def test_test_module_failure_does_not_execute_simple_epf(self):
        self.dump_results["test_module_build"] = b"1\n"
        report = self.module.run()
        self.assert_failed(report, "simple_epf")
        self.assertEqual(self.events, SUCCESS_EVENTS[:8])
        self.assertTrue(report["launcher_built"])
        self.assertFalse(report["simple_epf_passed"])

    def test_simple_output_message_mismatch_rejects_completed_process(self):
        self.simple_result["messages"] = ["native-smoke-v1", "41"]
        report = self.module.run()
        self.assert_failed(report, "simple_epf", "output_mismatch")
        self.assertEqual(self.events, SUCCESS_EVENTS)
        self.assertTrue(report["launcher_built"])

    def test_simple_result_extra_key_rejected_by_strict_gate(self):
        self.simple_result["unexpected"] = "must not be exported"
        report = self.module.run()
        self.assert_failed(report, "simple_epf", "output_mismatch")
        self.assertNotIn("must not be exported", json.dumps(report))

    def test_native_compile_error_is_bounded_classification_not_report_text(self):
        self.failures["load"] = "process_failed"
        self.logs["load"] = "Ошибка компиляции: private source and credentials must stay local"
        report = self.module.run()
        self.assert_failed(report, "load", "process_failed")
        self.assertEqual(report["diagnostics"]["category"], "compile_error")
        self.assertNotIn("private source", json.dumps(report))
        self.assertEqual(self.events, SUCCESS_EVENTS[:2])

    def test_native_permission_error_cannot_look_like_success(self):
        self.failures["named_designer"] = "process_failed"
        self.logs["named_designer"] = "Access denied: private directory"
        report = self.module.run()
        self.assert_failed(report, "named_designer", "process_failed")
        self.assertEqual(report["diagnostics"]["category"], "permission_denied")
        self.assertNotIn("private directory", json.dumps(report))

    def test_unique_evidence_directories_are_not_reused_across_runs(self):
        first = self.module.run()
        first_evidence = self.evidence
        second = self.module.run()
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertNotEqual(first_evidence, self.evidence)
        self.assertTrue(first_evidence.is_dir())
        self.assertTrue(self.evidence.is_dir())

    def test_main_writes_only_exact_report_and_exit_status(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main()
        self.assertEqual(code, 0)
        report = json.loads((self.root / "stage2-report.json").read_text(encoding="utf-8"))
        self.assert_report_schema(report)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_main_failure_is_sanitized_and_nonzero(self):
        self.inject_error = RuntimeError("private unexpected exception")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main()
        self.assertEqual(code, 1)
        text = (self.root / "stage2-report.json").read_text(encoding="utf-8")
        self.assert_report_schema(json.loads(text))
        self.assertNotIn("private unexpected exception", text)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")


class Stage2UnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = load_controller()

    def test_empty_report_exact_schema_all_unverified(self):
        self.assertEqual(self.module.empty_report(), {
            "schema": 1, "status": "failed", "failed_stage": "inject",
            "failure_kind": "unexpected_failure", "actual_version": None,
            "version_source": "not_measured", "simple_output_sha256": None,
            "security_settings_state": "not_attempted", "diagnostics": self.module.empty_diagnostics(),
            "protection_observation": self.module.empty_protection_observation(),
            **dict.fromkeys(REPORT_FLAGS, False),
        })

    def test_command_preserves_spaces_and_username_as_distinct_arguments(self):
        self.module.ONEC = self.root / "platform directory" / "1cv8t"
        database = self.root / "database with spaces"
        command = self.module.command("DESIGNER", database, "NativeSmoke")
        self.assertEqual(command, [
            str(self.module.ONEC), "DESIGNER", "/F", str(database),
            "/N", "NativeSmoke", "/AppAutoCheckVersion-", "/DisableStartupDialogs",
            "/DisableStartupMessages", "/L", "ru",
        ])
        self.assertNotIn("/N", self.module.command("ENTERPRISE", database))

    def test_strict_simple_result_requires_exact_keys_types_and_messages(self):
        result, output = self.root / "result.json", self.root / "simple.out"
        output.write_bytes(EXPECTED_OUTPUT)
        invalid = [
            {}, {"messages": ["native-smoke-v1", "42"]},
            {"messages": ["native-smoke-v1", "42"], "error": "", "extra": True},
            {"messages": ["native-smoke-v1", 42], "error": ""},
            {"messages": ["native-smoke-v1", "42"], "error": None},
            {"messages": ["native-smoke-v1", "42"], "error": "native error"},
            {"messages": ["42", "native-smoke-v1"], "error": ""},
            {"messages": ["native-smoke-v1", "42", ""], "error": ""},
            {"messages": "native-smoke-v1\n42\n", "error": ""},
        ]
        for value in invalid:
            with self.subTest(value=value):
                result.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(self.module.StageError) as raised:
                    self.module.strict_simple_result(result, output)
                self.assertEqual(raised.exception.kind, "output_mismatch")
        result.write_text(json.dumps({"messages": ["native-smoke-v1", "42"], "error": ""}),
                          encoding="utf-8")
        self.assertEqual(self.module.strict_simple_result(result, output),
                         hashlib.sha256(EXPECTED_OUTPUT).hexdigest())

    def test_strict_simple_result_requires_exact_utf8_lf_output(self):
        result, output = self.root / "result.json", self.root / "simple.out"
        result.write_text(json.dumps({"messages": ["native-smoke-v1", "42"], "error": ""}),
                          encoding="utf-8")
        for data in (b"native-smoke-v1\r\n42\r\n", b"\xef\xbb\xbf" + EXPECTED_OUTPUT,
                     EXPECTED_OUTPUT.rstrip(b"\n"), EXPECTED_OUTPUT + b"\n", b"42\n"):
            with self.subTest(data=data):
                output.write_bytes(data)
                with self.assertRaises(self.module.StageError) as raised:
                    self.module.strict_simple_result(result, output)
                self.assertEqual(raised.exception.kind, "output_mismatch")

    def test_strict_simple_result_rejects_malformed_and_duplicate_json(self):
        result, output = self.root / "result.json", self.root / "simple.out"
        output.write_bytes(EXPECTED_OUTPUT)
        for data in (b"[1,2]", b"{", b'{"messages":[],"messages":["native-smoke-v1","42"],"error":""}'):
            with self.subTest(data=data):
                result.write_bytes(data)
                with self.assertRaises(self.module.DraftError):
                    self.module.strict_simple_result(result, output)

    def test_batch_requires_numeric_zero_dumpresult_after_successful_process(self):
        result = self.root / "load.result"
        cases = (None, b"", b"1", b"OK", b"0 error", b"\xff", b"0" * 129)
        for data in cases:
            with self.subTest(data=data):
                result.unlink(missing_ok=True)

                def fake_process(*args, **kwargs):
                    if data is not None:
                        result.write_bytes(data)

                with mock.patch.object(self.module, "process", side_effect=fake_process), \
                     self.assertRaises(self.module.StageError) as raised:
                    self.module.batch("load", self.root / "db", self.root, ["/UpdateDBCfg"])
                self.assertEqual(raised.exception.kind, "invalid_dump_result")
        for data in (b"0\n", "0\r\n".encode("utf-16")):
            with self.subTest(data=data):
                result.unlink(missing_ok=True)
                with mock.patch.object(self.module, "process",
                                       side_effect=lambda *args, **kwargs: result.write_bytes(data)):
                    self.module.batch("load", self.root / "db", self.root, ["/UpdateDBCfg"])

    def test_batch_process_failure_cannot_be_overridden_by_zero_dumpresult(self):
        def fail(*args, **kwargs):
            (self.root / "load.result").write_bytes(b"0")
            raise self.module.StageError("process_failed")

        with mock.patch.object(self.module, "process", side_effect=fail), \
             self.assertRaises(self.module.StageError) as raised:
            self.module.batch("load", self.root / "db", self.root, ["/UpdateDBCfg"])
        self.assertEqual(raised.exception.kind, "process_failed")

    def test_stale_batch_artifacts_prevent_process_execution(self):
        for name in ("load.result", "load.log"):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(b"stale")
                with mock.patch.object(self.module, "process") as process, \
                     self.assertRaises(self.module.StageError) as raised:
                    self.module.batch("load", self.root / "db", self.root, ["/UpdateDBCfg"])
                self.assertEqual(raised.exception.kind, "stale_evidence")
                process.assert_not_called()
                path.unlink()

    def test_stale_control_file_is_not_reused_or_removed(self):
        path = self.root / "control.json"
        path.write_bytes(b"stale control")
        with mock.patch.object(self.module, "process") as process, \
             self.assertRaises(self.module.StageError) as raised:
            self.module.enterprise("bootstrap", self.root / "db", self.root, {}, {}, None)
        self.assertEqual(raised.exception.kind, "stale_evidence")
        process.assert_not_called()
        self.assertEqual(path.read_bytes(), b"stale control")

    def test_absent_rejects_mocked_symlink_without_os_symlink_privileges(self):
        path = mock.Mock(spec=Path)
        path.exists.return_value = False
        path.is_symlink.return_value = True
        with self.assertRaises(self.module.StageError) as raised:
            self.module.absent(path)
        self.assertEqual(raised.exception.kind, "stale_evidence")

    def test_process_nonzero_exit_is_failure_and_keeps_command_list(self):
        child = mock.MagicMock()
        child.__enter__.return_value = child
        child.wait.return_value = 7
        command = ["never executed", "DESIGNER", "/F", "path with spaces"]
        with mock.patch.object(self.module.subprocess, "Popen", return_value=child) as popen, \
             self.assertRaises(self.module.StageError) as raised:
            self.module.process(command, self.root, self.root / "console.log", 5)
        self.assertEqual(raised.exception.kind, "process_failed")
        self.assertEqual(popen.call_args.args, (command,))
        self.assertEqual(popen.call_args.kwargs["cwd"], self.root)
        self.assertNotIn("shell", popen.call_args.kwargs)
        child.wait.assert_called_once_with(timeout=5)

    def test_process_stale_console_prevents_popen(self):
        console = self.root / "console.log"
        console.write_bytes(b"stale")
        with mock.patch.object(self.module.subprocess, "Popen") as popen, \
             self.assertRaises(self.module.StageError) as raised:
            self.module.process(["never executed"], self.root, console)
        self.assertEqual(raised.exception.kind, "stale_evidence")
        popen.assert_not_called()
        self.assertEqual(console.read_bytes(), b"stale")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process-group contract")
    def test_process_timeout_kills_mocked_group_and_reaps_before_failing(self):
        child = mock.MagicMock(pid=32101)
        child.__enter__.return_value = child
        child.wait.side_effect = [subprocess.TimeoutExpired(["never executed"], 2), -9]
        with mock.patch.object(self.module.subprocess, "Popen", return_value=child) as popen, \
             mock.patch.object(self.module.os, "killpg") as killpg, \
             self.assertRaises(self.module.StageError) as raised:
            self.module.process(["never executed"], self.root, self.root / "console.log", 2)
        self.assertEqual(raised.exception.kind, "timeout")
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        killpg.assert_called_once_with(child.pid, self.module.signal.SIGKILL)
        self.assertEqual(child.wait.call_args_list, [mock.call(timeout=2), mock.call()])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process-group contract")
    def test_process_timeout_still_reaps_if_group_has_already_exited(self):
        child = mock.MagicMock(pid=32102)
        child.__enter__.return_value = child
        child.wait.side_effect = [subprocess.TimeoutExpired(["never executed"], 2), -9]
        with mock.patch.object(self.module.subprocess, "Popen", return_value=child), \
             mock.patch.object(self.module.os, "killpg", side_effect=ProcessLookupError), \
             self.assertRaises(self.module.StageError) as raised:
            self.module.process(["never executed"], self.root, self.root / "console.log", 2)
        self.assertEqual(raised.exception.kind, "timeout")
        self.assertEqual(child.wait.call_count, 2)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process-group contract")
    def test_process_interrupt_kills_mocked_group_then_propagates_interrupt(self):
        child = mock.MagicMock(pid=32103)
        child.__enter__.return_value = child
        child.wait.side_effect = [KeyboardInterrupt, -9]
        with mock.patch.object(self.module.subprocess, "Popen", return_value=child), \
             mock.patch.object(self.module.os, "killpg") as killpg, \
             self.assertRaises(KeyboardInterrupt):
            self.module.process(["never executed"], self.root, self.root / "console.log", 2)
        killpg.assert_called_once_with(child.pid, self.module.signal.SIGKILL)
        self.assertEqual(child.wait.call_count, 2)

    def test_main_catches_unexpected_run_failure_without_raw_error(self):
        self.module.ROOT = self.root
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(self.module, "run", side_effect=OSError("private error")), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main()
        self.assertEqual(code, 1)
        report = json.loads((self.root / "stage2-report.json").read_text(encoding="utf-8"))
        expected = self.module.empty_report()
        expected.update(failed_stage="unknown", security_change_attempted=True,
                        security_settings_state="unverified")
        self.assertEqual(report, expected)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_main_refuses_overwriting_prior_report(self):
        self.module.ROOT = self.root
        report = self.root / "stage2-report.json"
        report.write_bytes(b"prior report")
        with mock.patch.object(self.module, "run", return_value=self.module.empty_report()), \
             self.assertRaises(FileExistsError):
            self.module.main()
        self.assertEqual(report.read_bytes(), b"prior report")


if __name__ == "__main__":
    unittest.main()

"""Offline tests only: never download or execute a container image."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_1c_smoke", ROOT / "scripts/native_1c_smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def valid_report():
    return {
        "schema": 1, "status": "ok", "python_version": "3.10.12",
        **{key: key not in {"native_tests_completed", "security_settings_changed"} for key in smoke.BOOL_KEYS},
        "runtime_version": None, "runtime_version_source": "not_measured",
        "configuration_format": {
            "root": "MetaDataObject", "kind": "Configuration",
            "namespace": "http://v8.1c.ru/8.3/MDClasses", "schema_version": "2.20",
            "element_count": 91, "sha256": "a" * 64,
            "known_elements": ["Name", "DefaultRunMode"],
            "managed_application_module_present": False, "session_module_present": False,
        },
    }


class ReportTests(unittest.TestCase):
    def test_success_roundtrip(self):
        data = valid_report()
        self.assertEqual(smoke.validate_report(json.dumps(data).encode()), data)

    def test_missing_or_unsupported_python(self):
        for status in ("python_missing", "python_unsupported"):
            value = {"schema": 1, "status": status}
            self.assertEqual(smoke.validate_report(json.dumps(value).encode()), value)

    def test_rejects_untrusted_values_and_false_success(self):
        edits = [
            lambda d: d.update(env="SECRET"),
            lambda d: d.update(status="SECRET"),
            lambda d: d.update(schema=True),
            lambda d: d.update(nonroot=False),
            lambda d: d.update(display_started=1),
            lambda d: d.update(runtime_version="8.3.27.1508"),
            lambda d: d.update(runtime_version_source="path"),
            lambda d: d.update(security_settings_changed=True),
            lambda d: d.update(native_tests_completed=True),
            lambda d: d.update(python_version="3.10.12 SECRET"),
            lambda d: d.update(python_version="3.9.9"),
            lambda d: d.update(python_version="0.0.0"),
            lambda d: d.update(configuration_format=None),
            lambda d: d["configuration_format"].update(extra="SECRET"),
            lambda d: d["configuration_format"].update(known_elements=["SECRET"]),
            lambda d: d["configuration_format"].update(schema_version="SECRET"),
            lambda d: d["configuration_format"].update(element_count=True),
            lambda d: d["configuration_format"].update(element_count=4097),
            lambda d: d["configuration_format"].update(sha256="SECRET"),
            lambda d: d["configuration_format"].update(managed_application_module_present="SECRET"),
        ]
        for edit in edits:
            with self.subTest(edit=edit):
                data = copy.deepcopy(valid_report())
                edit(data)
                with self.assertRaisesRegex(smoke.SmokeError, "^invalid_container_report$"):
                    smoke.validate_report(json.dumps(data).encode())

    def test_invalid_json_and_duplicates(self):
        for value in (b"SECRET", b"\xff", b"[]", b"null", b"{}", b"x" * (smoke.MAX_OUTPUT + 1),
                      b'{"schema":1,"schema":1,"status":"python_missing"}', b"[" * 1200):
            with self.subTest(value=value[:40]):
                with self.assertRaises(smoke.SmokeError):
                    smoke.validate_report(value)

    def test_partial_failure_is_not_success(self):
        data = valid_report()
        data.update(status="display_failed", display_started=False, infobase_created=False,
                    configuration_dumped=False, configuration_format=None)
        self.assertEqual(smoke.validate_report(json.dumps(data).encode())["status"], "display_failed")


class IsolationTests(unittest.TestCase):
    def test_fixed_digest_and_run_isolation(self):
        args = smoke.container_command(smoke.PROBE, "onec-smoke-test")
        required = {
            "--network": "none", "--user": "1000:1000", "--cap-drop": "ALL",
            "--security-opt": "no-new-privileges:true", "--pull": "never",
            "--platform": "linux/amd64", "--pids-limit": "256", "--memory": "2g",
            "--memory-swap": "2g", "--cpus": "2", "--entrypoint": "/usr/bin/env",
            "--ipc": "private", "--log-driver": "none",
        }
        for flag, expected in required.items():
            self.assertEqual(args[args.index(flag) + 1], expected)
        for flag in ("--read-only", "--no-healthcheck", "--init"):
            self.assertIn(flag, args)
        self.assertRegex(smoke.IMAGE, r"^ghcr\.io/atridis/onec-ubuntu22@sha256:[a-f0-9]{64}$")
        self.assertEqual(args.count("--mount"), 1)
        mount = args[args.index("--mount") + 1]
        self.assertIn("dst=/smoke/probe.sh,readonly", mount)
        self.assertIn("/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777", args)
        for forbidden in ("-p", "-P", "--publish", "--publish-all", "--privileged", "--env-file", "--env", "-e", "--volume", "-v", "--rm"):
            self.assertNotIn(forbidden, args)
        self.assertNotIn("docker.sock", " ".join(args))
        self.assertEqual(args[args.index(smoke.IMAGE) + 1], "-i")

    def test_directory_and_symlink_probe_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaises(smoke.SmokeError):
                smoke.container_command(directory, "onec-smoke-test")
            if os.name != "nt":
                link = directory / "probe.sh"
                link.symlink_to(smoke.PROBE)
                with self.assertRaises(smoke.SmokeError):
                    smoke.container_command(link, "onec-smoke-test")

    def test_environment_is_allowlisted(self):
        with mock.patch.dict(os.environ, {"GHCR_TOKEN": "secret", "DOCKER_HOST": "danger", "LD_PRELOAD": "danger"}):
            env = smoke.docker_environment(Path("/tmp/private/config"))
        self.assertEqual(set(env), {"PATH", "HOME", "DOCKER_CONFIG", "LANG", "LC_ALL"})
        self.assertNotIn("secret", str(env))

    def test_no_inherited_entrypoint_security_mutation_or_install(self):
        text = "\n".join(line for line in smoke.PROBE.read_text().splitlines() if not line.lstrip().startswith("#"))
        for bad in ("apt-get", "pip install", "SecurityTypes=None", " -ac ", "ЗащитаОтОпасныхДействий", "UnsafeOperationProtection"):
            self.assertNotIn(bad, text)
        self.assertIn("-rfbport -1 -nolisten tcp", text)
        self.assertIn("/DumpResult /tmp/onec-smoke/create-result.txt", text)
        self.assertIn("/DumpResult /tmp/onec-smoke/dump-result.txt", text)
        self.assertIn("check_result /tmp/onec-smoke/create-result.txt", text)
        self.assertIn("check_result /tmp/onec-smoke/dump-result.txt", text)

    def test_missing_libraries_fail_closed(self):
        source = smoke.PROBE.read_text().split("<<'PYLIBRARIES'\n", 1)[1].split("\nPYLIBRARIES", 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ldd.log"
            for payload, expected in ((b"libc.so.6 => /lib/libc.so.6", 0),
                                      (b"libmissing.so => not found", 1),
                                      (b"", 1), (b"x" * 65537, 1)):
                path.write_bytes(payload)
                result = subprocess.run([sys.executable, "-c", source, str(path)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, expected)
            path.unlink()
            result = subprocess.run([sys.executable, "-c", source, str(path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)

    def test_workflow_trigger_permissions_artifact_are_narrow(self):
        text = (ROOT / ".github/workflows/native-1c-isolated-smoke.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/codex/native-1c-isolated-smoke'", text)
        self.assertIn("github.actor == 'Atridis'", text)
        self.assertIn("github.triggering_actor == 'Atridis'", text)
        self.assertIn("github.repository == 'Atridis/yadinassi'", text)
        self.assertIn("github.event_name == 'push'", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("write", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("path: native-smoke/report.json", text)
        self.assertNotIn("path: native-smoke/\n", text)


class OrchestrationTests(unittest.TestCase):
    def fake_runner(self, fail_operation=None, platform=b"linux/amd64|0\n"):
        operations = []
        auth_dirs = []

        def silent(args, env, seconds, input_bytes=None):
            op = args[1]
            operations.append(op)
            self.assertNotIn("GHCR_TOKEN", os.environ)
            self.assertNotIn("GHCR_TOKEN", env)
            if op == "login":
                self.assertEqual(input_bytes, b"private-token")
                directory = Path(env["DOCKER_CONFIG"])
                auth_dirs.append(directory)
                (directory / "config.json").write_text("secret")
            if op == fail_operation:
                raise smoke.SmokeError("docker_command_failed")

        def bounded(args, env, seconds, limit=smoke.MAX_OUTPUT):
            op = args[1]
            operations.append(op)
            self.assertTrue(auth_dirs)
            self.assertFalse(auth_dirs[0].exists(), "registry auth must be gone BEFORE image inspection/run")
            self.assertFalse((Path(env["DOCKER_CONFIG"]) / "config.json").exists())
            if op == "image":
                return 0, platform
            if op == fail_operation:
                raise smoke.SmokeError("container_timeout")
            return 0, json.dumps(valid_report()).encode()
        return silent, bounded, operations, auth_dirs

    def invoke(self, fail_operation=None, platform=b"linux/amd64|0\n"):
        silent, bounded, operations, auth_dirs = self.fake_runner(fail_operation, platform)
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"GHCR_TOKEN": "private-token", "GHCR_USER": "Atridis"}), mock.patch.object(smoke, "run_silent", side_effect=silent), mock.patch.object(smoke, "bounded_run", side_effect=bounded):
            try:
                result = smoke.run_smoke(Path(temp))
            except smoke.SmokeError as error:
                result = str(error)
            self.assertTrue(all(not path.exists() for path in auth_dirs))
        return result, operations

    def test_order_and_auth_removed_before_process(self):
        result, operations = self.invoke()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(operations, ["login", "pull", "image", "run", "rm"])
        self.assertEqual(result["container_exit_code"], 0)

    def test_login_and_pull_failure_never_executes_image(self):
        for failure in ("login", "pull"):
            result, operations = self.invoke(failure)
            self.assertEqual(result, "docker_command_failed")
            self.assertNotIn("run", operations)

    def test_platform_or_implicit_volume_rejected(self):
        for platform in (b"linux/arm64|0\n", b"linux/amd64|1\n", b"SECRET"):
            result, operations = self.invoke(platform=platform)
            self.assertEqual(result, "unexpected_image_platform_or_volumes")
            self.assertNotIn("run", operations)

    def test_timeout_always_cleans_container(self):
        result, operations = self.invoke("run")
        self.assertEqual(result, "container_timeout")
        self.assertEqual(operations[-1], "rm")

    def test_cleanup_failure_cannot_be_success(self):
        result, operations = self.invoke("rm")
        self.assertEqual(result, "container_cleanup_unverified")


@unittest.skipIf(os.name == "nt", "bounded POSIX pipe reader is used only on Ubuntu Actions")
class BoundedProcessTests(unittest.TestCase):
    def test_normal_output(self):
        result = smoke.bounded_run([sys.executable, "-c", "print('ok')"], dict(os.environ), 5)
        self.assertEqual(result, (0, b"ok\n"))

    def test_stderr_does_not_escape(self):
        result = smoke.bounded_run([sys.executable, "-c", "import sys; sys.stderr.write('SECRET'); print('ok')"], dict(os.environ), 5)
        self.assertEqual(result, (0, b"ok\n"))

    def test_output_limit(self):
        with self.assertRaisesRegex(smoke.SmokeError, "^container_output_limit$"):
            smoke.bounded_run([sys.executable, "-c", "print('SECRET' * 10000)"], dict(os.environ), 5, 64)

    def test_timeout(self):
        with self.assertRaisesRegex(smoke.SmokeError, "^container_timeout$"):
            smoke.bounded_run([sys.executable, "-c", "import time; time.sleep(5)"], dict(os.environ), 0.1)


@unittest.skipUnless(sys.platform == "linux", "fake Bash probe requires Linux and GNU timeout")
class FakeProbeTests(unittest.TestCase):
    # Exercise the real shell control flow with local, inert fake tools.
    def run_probe(self, mode, *, bootstrap=False, stage2_value=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            native = bin_dir / "fakeonec"
            work = root / "work"
            source = smoke.PROBE.read_text().replace(
                "/opt/1cv8t/x86_64/8.3.27.1508/1cv8t", str(native)
            ).replace("/tmp/onec-smoke", str(work)).replace("/tmp/.X11-unix", str(root / "x11"))
            stage2_script = root / "fake_stage2.py"
            if bootstrap:
                source = source.replace("/smoke/bootstrap/run_stage.py", str(stage2_script))
                if mode == "stage2_missing_report":
                    stage2_script.write_text("raise SystemExit(1)\n")
                else:
                    stage2_script.write_text(
                        "from pathlib import Path\n" +
                        "Path(" + repr(str(work / "stage2-report.json")) + ").write_text(" +
                        repr(json.dumps(stage2_value)) + ")\n" +
                        "raise SystemExit(" + ("0" if stage2_value['status'] == 'ok' else "1") + ")\n")
            probe = root / "probe.sh"
            probe.write_text(source)
            def executable(name, body):
                file = bin_dir / name
                file.write_text(body)
                file.chmod(0o755)
            py = "#!" + sys.executable + "\n"
            executable("fakeonec", py + r"""
import os
from pathlib import Path
import sys
args = sys.argv[1:]
mode = os.environ.get("MOCK_MODE", "ok")
Path(os.environ["MOCK_CALLS"]).open("a").write(args[0] + "\n")
result = Path(args[args.index("/DumpResult") + 1])
if args[0] == "CREATEINFOBASE":
    target = Path(args[1].split('"')[1])
    target.mkdir()
    (target / "1Cv8.1CD").write_bytes(b"fake database, not 1C")
    result.write_text("1" if mode == "create_failed" else "0")
else:
    target = Path(args[args.index("/DumpConfigToFiles") + 1])
    (target / "Configuration.xml").write_text('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20"><Configuration><Properties><Name/></Properties></Configuration></MetaDataObject>')
    result.write_text("1" if mode == "dump_failed" else "0")
    if mode == "stage2_missing_report":
        (target / "Configuration.xml").write_text("invalid native XML")
""")
            executable("id", "#!/bin/sh\nprintf '1000\\n'\n")
            executable("ldd", py + "import os; print('libmissing => not found' if os.environ['MOCK_MODE'] == 'libraries_failed' else 'libc => /lib/libc.so')\n")
            executable("Xtigervnc", py + "import time; time.sleep(30)\n")
            for tool in ("xauth", "xdpyinfo"):
                executable(tool, "#!/bin/sh\nexit 0\n")
            (bin_dir / "python3").symlink_to(sys.executable)
            env = {"PATH": str(bin_dir) + ":/usr/bin:/bin", "HOME": str(root / "home"),
                   "XDG_RUNTIME_DIR": str(root / "runtime"), "DISPLAY": ":99",
                   "MOCK_MODE": mode, "MOCK_CALLS": str(root / "calls")}
            result = subprocess.run(["/bin/bash", str(probe)] + (["--bootstrap-simple-epf"] if bootstrap else []), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(result.stderr, b"")
            calls = (root / "calls").read_text().splitlines() if (root / "calls").exists() else []
            return result.returncode, json.loads(result.stdout), calls

    def test_happy_path_is_only_create_and_dump(self):
        code, report, calls = self.run_probe("ok")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(calls, ["CREATEINFOBASE", "DESIGNER"])
        self.assertTrue(report["libraries_resolved"])
        self.assertFalse(report["security_settings_changed"])
        self.assertIsNone(report["runtime_version"])

    def test_stage2_shell_handoff_reports_validated_version_and_security(self):
        code, report, calls = self.run_probe("ok", bootstrap=True, stage2_value=valid_stage2())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["stage2"], valid_stage2())
        self.assertEqual(report["runtime_version"], "8.3.27.1508")
        self.assertIs(report["security_settings_changed"], True)
        self.assertEqual(calls, ["CREATEINFOBASE", "DESIGNER"])

    def test_missing_stage2_plus_bad_format_cannot_claim_unchanged_security(self):
        code, report, _ = self.run_probe("stage2_missing_report", bootstrap=True)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["status"], "stage2_failed")
        self.assertIsNone(report["stage2"])
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_report(json.dumps(report).encode(), bootstrap=True)

    def test_missing_library_stops_before_native_invocation(self):
        code, report, calls = self.run_probe("libraries_failed")
        self.assertNotEqual(code, 0)
        self.assertEqual(report["status"], "libraries_failed")
        self.assertFalse(report["libraries_resolved"])
        self.assertEqual(calls, [])

    def test_native_result_file_failure_stops_progress(self):
        for mode, expected_calls in (("create_failed", ["CREATEINFOBASE"]),
                                     ("dump_failed", ["CREATEINFOBASE", "DESIGNER"])):
            with self.subTest(mode=mode):
                code, report, calls = self.run_probe(mode)
                self.assertNotEqual(code, 0)
                self.assertEqual(report["status"], mode)
                self.assertEqual(calls, expected_calls)
                self.assertFalse(report["configuration_dumped"])



def valid_stage2():
    return {"schema": 1, "status": "ok", "failed_stage": None, "failure_kind": "none",
            "actual_version": "8.3.27.1508", "version_source": "SystemInfo.AppVersion",
            "simple_output_sha256": smoke.SIMPLE_OUTPUT_SHA256,
            "security_change_attempted": True, "security_settings_state": "verified",
            "diagnostics": smoke.DIAGNOSTICS.empty_diagnostics(),
            "protection_observation": {"stage": "verify", "property_type": "UnsafeOperationProtectionDescription", "warning_type": "Boolean"},
            **{key: True for key in smoke.STAGE_FLAGS}}


def bootstrap_report():
    data = valid_report()
    data.update(stage2=valid_stage2(), runtime_version="8.3.27.1508",
                runtime_version_source="SystemInfo.AppVersion", security_settings_changed=True)
    return data


class BootstrapReportTests(unittest.TestCase):
    def test_checked_success_and_no_full_suite_claim(self):
        data = bootstrap_report()
        self.assertEqual(smoke.validate_report(json.dumps(data).encode(), bootstrap=True), data)
        self.assertFalse(data['native_tests_completed'])

    def test_refuses_downgrade_and_unknown_reports(self):
        for data in (valid_report(), {**valid_report(), 'stage2': None}):
            with self.assertRaises(smoke.SmokeError):
                smoke.validate_report(json.dumps(data).encode(), bootstrap=True)
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_report(json.dumps(bootstrap_report()).encode())

    def test_stage2_schema_types_gate_order_version_and_digest(self):
        edits = [lambda d: d.update(secret='PRIVATE'),
                 lambda d: d.update(schema=True),
                 lambda d: d.update(status='PRIVATE'),
                 lambda d: d.update(failed_stage='PRIVATE'),
                 lambda d: d.update(failure_kind='PRIVATE'),
                 lambda d: d.update(simple_epf_passed=1),
                 lambda d: d.update(modules_reimported=False),
                 lambda d: d.update(actual_version='8.3.27.1508 PRIVATE'),
                 lambda d: d.update(actual_version='8.3.26.1'),
                 lambda d: d.update(version_source='path'),
                 lambda d: d.update(security_change_attempted=False),
                 lambda d: d.update(security_settings_state='not_attempted'),
                 lambda d: d.update(simple_output_sha256='0' * 64)]
        for edit in edits:
            with self.subTest(edit=edit):
                data = bootstrap_report()
                edit(data['stage2'])
                with self.assertRaises(smoke.SmokeError):
                    smoke.validate_report(json.dumps(data).encode(), bootstrap=True)

    def test_partial_security_change_is_unknown_not_false(self):
        data = bootstrap_report()
        data.update(status='stage2_failed', runtime_version=None,
                    runtime_version_source='not_measured', security_settings_changed=None)
        data['stage2'].update(status='failed', failed_stage='bootstrap', failure_kind='hook_missing',
                              actual_version=None, version_source='not_measured',
                              simple_output_sha256=None, security_settings_state='unverified',
                              protection_observation=smoke.DIAGNOSTICS.empty_protection_observation(),
                              **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
        self.assertIsNone(smoke.validate_report(json.dumps(data).encode(), bootstrap=True)['security_settings_changed'])
        data['security_settings_changed'] = False
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_report(json.dumps(data).encode(), bootstrap=True)

    def test_mismatched_version_cannot_claim_named_gate_verified(self):
        data = bootstrap_report()
        data.update(status="stage2_failed", runtime_version="8.3.26.1")
        data["stage2"].update(status="failed", failed_stage="verify", failure_kind="version_mismatch",
                              actual_version="8.3.26.1", simple_output_sha256=None,
                              **{key: index < 3 for index, key in enumerate(smoke.STAGE_FLAGS)})
        self.assertEqual(smoke.validate_report(json.dumps(data).encode(), bootstrap=True)["runtime_version"], "8.3.26.1")
        data["stage2"]["named_user_verified"] = True
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_report(json.dumps(data).encode(), bootstrap=True)

    def test_host_uncertain_failure_does_not_claim_unchanged_security(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'report.json'
            for uncertain, expected in ((False, False), (True, None)):
                with mock.patch.object(smoke, 'run_smoke', side_effect=smoke.SmokeError('container_timeout', security_uncertain=uncertain)), contextlib.redirect_stdout(io.StringIO()):
                    code = smoke.main(['--execute-approved-image', '--bootstrap-simple-epf', '--output', str(output)])
                self.assertEqual(code, 1)
                self.assertIs(json.loads(output.read_text())['security_settings_changed'], expected)


class BootstrapStagingTests(unittest.TestCase):
    def test_stages_only_exact_trusted_files_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'staged'
            hashes = smoke.stage_inputs(root)
            self.assertEqual(set(hashes), set(smoke.STAGED_FILES))
            self.assertEqual({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}, set(smoke.STAGED_FILES.values()))
            for source, target in smoke.STAGED_FILES.items():
                self.assertEqual((smoke.ROOT / source).read_bytes(), (root / target).read_bytes())
            args = smoke.container_command(root, 'onec-smoke-test', bootstrap=True)
            self.assertEqual(args.count('--mount'), 1)
            self.assertTrue(args[args.index('--mount') + 1].endswith(',dst=/smoke,readonly'))
            self.assertEqual(args[-1], '--bootstrap-simple-epf')
            self.assertNotIn(str(smoke.ROOT), args)
            (root / 'extra-private-file').write_text('not allowed')
            with self.assertRaises(smoke.SmokeError):
                smoke.container_command(root, 'onec-smoke-test', bootstrap=True)

    @unittest.skipIf(os.name == 'nt', 'POSIX permission semantics')
    def test_staged_tree_is_traversable_with_restrictive_umask(self):
        with tempfile.TemporaryDirectory() as temp:
            previous = os.umask(0o077)
            try:
                root = Path(temp) / 'staged'
                smoke.stage_inputs(root)
            finally:
                os.umask(previous)
            for path in [root, *root.rglob('*')]:
                self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)


if __name__ == "__main__":
    unittest.main()

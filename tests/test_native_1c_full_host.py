"""Offline contract tests: synthetic bytes are not evidence of native 1C behavior."""
import base64
import contextlib
import copy
import io
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_native_1c_smoke import smoke, bootstrap_report

full = smoke.FULL
NONCE = "1234567890abcdef" * 2

# The real native host is Linux. Windows CI runs the same finite-schema,
# comparison, staging and orchestration assertions with synthetic files, not
# NTFS as a claimed emulation of Linux descriptor/path metadata equality.
_USE_SYNTHETIC_FILE_READER = os.name == "nt"


def read_synthetic_file(path, limit, *, nonempty=False):
    """Test-only bounded stable fixture reads; never used by the native runner.

    Linux tests retain the production descriptor-relative no-follow reader.
    This adapter uses one metadata API consistently for static Windows fixtures;
    it does not claim to prove the production descriptor-race security boundary.
    """
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("link")
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError("file")
        with path.open("rb") as source:
            data = source.read(limit + 1)
        after = path.lstat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                                 info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if (identity(before) != identity(after) or len(data) != before.st_size
                or len(data) > limit or (nonempty and not data)):
            raise ValueError("unstable")
        return data
    except (OSError, ValueError):
        raise full.FullError("invalid_private_file") from None


class SyntheticFilesystemCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        if _USE_SYNTHETIC_FILE_READER:
            patcher = mock.patch.object(full, "read_regular", side_effect=read_synthetic_file)
            patcher.start()
            self.addCleanup(patcher.stop)



def fixture(payload=b" PRIVATE synthetic output \n\n", *, input_hashes=None, modules=None):
    inputs = input_hashes or {path: "a" * 64 for path in smoke.FULL_STAGED_FILES}
    modules = modules or {name: "b" * 64 for name in full.SCENARIOS}
    report = bootstrap_report()
    report["native_tests_completed"] = True
    report["stage3"] = {"schema": 1, "nonce": NONCE, "status": "ok", "failure_kind": "none",
        "failed_case": None, "input_sha256": inputs, "cases": [
            {"name": name, "status": "ok", "source_sha256": inputs[f"integrational_tests/tests/{name}.bsl"],
             "module_sha256": modules[name], "output_sha256": full.digest(payload),
             "output_size": len(payload), "message_count": payload.count(b"\n")} for name in full.SCENARIOS]}
    envelope = {"schema": full.SCHEMA, "nonce": NONCE, "report": report, "outputs": [
        {"name": name + ".out", "size": len(payload), "sha256": full.digest(payload),
         "data_b64": base64.b64encode(payload).decode()} for name in full.SCENARIOS]}
    return envelope, inputs, modules


def encode(data):
    return json.dumps(data, separators=(",", ":")).encode()


def validate(data, inputs, modules):
    return full.validate_envelope(encode(data), NONCE, inputs, modules, smoke.validate_report)


class SyntheticReaderTests(unittest.TestCase):
    def test_fixture_adapter_preserves_bytes_bounds_and_empty_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "fixture.out"
            path.write_bytes(b"x\r\n\x00\xff")
            self.assertEqual(read_synthetic_file(path, 8), b"x\r\n\x00\xff")
            with self.assertRaises(full.FullError): read_synthetic_file(path, 2)
            with self.assertRaises(full.FullError): read_synthetic_file(path.parent, 8)
            path.write_bytes(b"")
            self.assertEqual(read_synthetic_file(path, 8), b"")
            with self.assertRaises(full.FullError): read_synthetic_file(path, 8, nonempty=True)


class EnvelopeTests(unittest.TestCase):
    def test_exact_six_immutable_bytes_roundtrip_and_no_payload_in_report(self):
        payload = b" \n\x00\xff\r\nPRIVATE\n"
        data, inputs, modules = fixture(payload)
        report, outputs = validate(data, inputs, modules)
        self.assertEqual(list(outputs), list(full.SCENARIOS))
        self.assertTrue(all(value == payload for value in outputs.values()))
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertLess(len(encode(report)), full.MAX_REPORT)

    def test_empty_exact_output_is_valid(self):
        data, inputs, modules = fixture(b"")
        self.assertEqual(validate(data, inputs, modules)[1], dict.fromkeys(full.SCENARIOS, b""))

    def test_rejects_unknown_fields_wrong_types_and_inconsistent_evidence(self):
        edits = [
            lambda d: d.update(extra="PRIVATE"), lambda d: d.update(nonce="0" * 32),
            lambda d: d.update(schema=1), lambda d: d.update(outputs=[]),
            lambda d: d["outputs"].reverse(), lambda d: d["outputs"].append(d["outputs"][0]),
            lambda d: d["outputs"][0].update(name="../collections.out"),
            lambda d: d["outputs"][0].update(name="Collections.out"),
            lambda d: d["outputs"][0].update(size=True),
            lambda d: d["outputs"][0].update(size=full.MAX_FILE + 1),
            lambda d: d["outputs"][0].update(size=0),
            lambda d: d["outputs"][0].update(sha256="0" * 64),
            lambda d: d["outputs"][0].update(sha256="A" * 64),
            lambda d: d["outputs"][0].update(extra="PRIVATE"),
            lambda d: d["outputs"][0].update(data_b64="%%%%"),
            lambda d: d["outputs"][0].update(data_b64="QQ==\n"),
            lambda d: d["outputs"][0].update(data_b64="QR=="),
            lambda d: d["report"].update(native_tests_completed=False),
            lambda d: d["report"].update(status="stage3_failed"),
            lambda d: d["report"]["stage3"].update(nonce="0" * 32),
            lambda d: d["report"]["stage3"].update(schema=True),
            lambda d: d["report"]["stage3"].update(input_sha256={}),
            lambda d: d["report"]["stage3"]["cases"].pop(),
            lambda d: d["report"]["stage3"]["cases"][0].update(module_sha256="c" * 64),
            lambda d: d["report"]["stage3"]["cases"][0].update(source_sha256="c" * 64),
            lambda d: d["report"]["stage3"]["cases"][0].update(output_sha256="c" * 64),
            lambda d: d["report"]["stage3"]["cases"][0].update(message_count=True),
            lambda d: d["report"]["stage3"]["cases"][0].update(message_count=32769),
        ]
        for edit in edits:
            data, inputs, modules = fixture()
            edit(data)
            with self.subTest(edit=edit), self.assertRaises((full.FullError, smoke.SmokeError)) as caught:
                validate(data, inputs, modules)
            self.assertNotIn("PRIVATE", str(caught.exception))

    def test_strict_json_depth_duplicates_nonfinite_unicode_trailing(self):
        data, inputs, modules = fixture()
        valid = encode(data)
        cases = [b"[" * 1200, b"\xff", valid + b"{}", valid[:-1], b"x" * (full.MAX_TRANSPORT + 1),
                 valid.replace(b'"nonce":', b'"nonce":"' + NONCE.encode() + b'","nonce":', 1),
                 valid.replace(b'"schema":1', b'"schema":NaN', 1),
                 valid.replace(b'"schema":1', b'"schema":1.0', 1),
                 valid.replace(b'"schema":1', b'"schema":123456789012', 1),
                 valid.replace(b'"schema":1', b'"schema":"\\ud800"', 1),
                 valid.decode().encode("utf-16")]
        for raw in cases:
            with self.subTest(prefix=raw[:20]), self.assertRaises((full.FullError, smoke.SmokeError)):
                full.validate_envelope(raw, NONCE, inputs, modules, smoke.validate_report)

    def test_file_aggregate_transport_and_separate_report_caps(self):
        for payload in (b"x" * (full.MAX_FILE + 1), b"x" * (full.MAX_TOTAL // 6 + 1)):
            data, inputs, modules = fixture(payload)
            with self.assertRaises(full.FullError):
                validate(data, inputs, modules)
        data, inputs, modules = fixture()
        data["report"]["private"] = "x" * full.MAX_REPORT
        with self.assertRaises(full.FullError):
            validate(data, inputs, modules)

    def test_failed_suite_never_accepts_payload_or_out_of_order_success(self):
        data, inputs, modules = fixture()
        data["outputs"] = []
        report = data["report"]
        report.update(status="stage3_failed", native_tests_completed=False)
        suite = report["stage3"]
        suite.update(status="failed", failed_case="dates", failure_kind="process_failed")
        for index, case in enumerate(suite["cases"]):
            if index:
                case.update(status="failed" if index == 1 else "not_started",
                            output_sha256=None, output_size=None, message_count=None)
                if index > 1:
                    case.update(source_sha256=None, module_sha256=None)
        self.assertEqual(validate(data, inputs, modules)[1], {})
        bad = copy.deepcopy(data)
        bad["outputs"] = fixture()[0]["outputs"]
        with self.assertRaises(full.FullError): validate(bad, inputs, modules)
        bad = copy.deepcopy(data)
        bad["report"]["stage3"]["cases"][4] = fixture()[0]["report"]["stage3"]["cases"][4]
        with self.assertRaises(full.FullError): validate(bad, inputs, modules)

    def test_early_failure_can_report_no_established_input_provenance(self):
        data, inputs, modules = fixture()
        data["outputs"] = []
        data["report"].update(status="stage3_failed", native_tests_completed=False)
        suite = data["report"]["stage3"]
        suite.update(status="failed", failure_kind="invalid_input", input_sha256={})
        for case in suite["cases"]:
            case.update({key: None for key in full.CASE_KEYS - {"name", "status"}})
            case["status"] = "not_started"
        self.assertEqual(validate(data, inputs, modules)[1], {})

    def test_unverified_bootstrap_cannot_claim_native_suite_success(self):
        data, inputs, modules = fixture()
        data["report"]["stage2"]["simple_epf_passed"] = False
        with self.assertRaises(smoke.SmokeError): validate(data, inputs, modules)


class CaptureTests(SyntheticFilesystemCase):
    def test_private_exclusive_fixed_files_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            payloads = dict.fromkeys(full.SCENARIOS, b"PRIVATE\n")
            target = full.quarantine_outputs(parent, payloads)
            self.assertEqual(sorted(p.name for p in target.iterdir()), sorted(name + ".out" for name in full.SCENARIOS))
            for path in target.iterdir():
                self.assertEqual(full.read_regular(path, 100), b"PRIVATE\n")
                if os.name != "nt": self.assertEqual(path.stat().st_mode & 0o777, 0o400)
            if os.name != "nt": self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(full.FullError): full.quarantine_outputs(parent, payloads)
            with self.assertRaises(full.FullError): full.quarantine_outputs(parent, {"../x": b"PRIVATE"})

    @unittest.skipIf(os.name == "nt", "POSIX no-follow, hardlink and FIFO semantics")
    def test_no_link_or_special_file_read_and_no_link_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real"
            real.write_bytes(b"PRIVATE")
            link = root / "link"
            link.symlink_to(real)
            with self.assertRaises(full.FullError): full.read_regular(link, 100)
            link.unlink()
            os.link(real, link)
            with self.assertRaises(full.FullError): full.read_regular(real, 100)
            link.unlink()
            os.mkfifo(link)
            with self.assertRaises(full.FullError): full.read_regular(link, 100)
            link.unlink()
            (root / "native-capture").symlink_to(root, target_is_directory=True)
            with self.assertRaises(full.FullError): full.quarantine_outputs(root, dict.fromkeys(full.SCENARIOS, b"PRIVATE"))

    def test_module_transform_is_exact_launcher_bom_and_lf_serialization(self):
        self.assertEqual(full.generated_module(b"\xef\xbb\xbfx\r\ny\rz\n"), b"\xef\xbb\xbfx\ny\nz\n")
        self.assertNotEqual(full.generated_module(b"x"), b"x")


class StagingTests(SyntheticFilesystemCase):
    def test_full_exact23_inputs_no_goldens_repository_or_interpreter_mount(self):
        self.assertEqual(len(smoke.STAGED_FILES), 16)
        self.assertEqual(len(smoke.FULL_STAGED_FILES), 23)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "staged"
            hashes = smoke.stage_inputs(path, full_suite=True)
            self.assertEqual(set(hashes), set(smoke.FULL_STAGED_FILES))
            command = smoke.container_command(path, "onec-smoke-test", full_suite=True, nonce=NONCE)
            self.assertEqual(command[-3:], ["--full-suite", "--invocation-nonce", NONCE])
            self.assertEqual(command.count("--mount"), 1)
            self.assertTrue(command[command.index("--mount") + 1].endswith(",dst=/smoke,readonly"))
            for key, value in {"--network":"none", "--user":"1000:1000", "--cap-drop":"ALL", "--security-opt":"no-new-privileges:true", "--log-driver":"none"}.items():
                self.assertEqual(command[command.index(key) + 1], value)
            for flag in ("--read-only", "--no-healthcheck", "--init"): self.assertIn(flag, command)
            self.assertFalse(any(".out" in str(p) or "yadinassi" in str(p.relative_to(path)) for p in path.rglob("*")))
            (path / "unexpected").mkdir()
            with self.assertRaises(smoke.SmokeError): smoke.validate_input_tree(path, full_suite=True)

    def test_nonce_and_wrong_mode_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "staged"
            smoke.stage_inputs(path)
            for nonce in (None, "x", "0" * 31, "A" * 32, "0" * 32):
                with self.assertRaises(smoke.SmokeError):
                    smoke.container_command(path, "onec-smoke-test", full_suite=True, nonce=nonce)

    def test_workflow_only_finite_report_exact_host_deps_and_existing_scope(self):
        text = (smoke.ROOT / ".github/workflows/native-1c-isolated-smoke.yml").read_text()
        self.assertIn("timeout-minutes: 60", text)
        self.assertIn("--full-suite --client-probe --client-watchdog-check --client-dates-parity --client-values-parity --client-collections-parity --client-numbers-parity --output native-smoke/report.json", text)
        self.assertIn("path: native-smoke/report.json", text)
        self.assertNotIn("path: native-smoke/\n", text)
        self.assertNotIn("tee", text)
        self.assertEqual(smoke.FULL_MAX_RUNTIME, 2400)
        for name, version in full.DEPENDENCIES.items(): self.assertIn(name + "==" + version, text)


class ComparisonTests(SyntheticFilesystemCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "integrational_tests/tests").mkdir(parents=True)
        self.payload = b" value \\n\n\n"
        self.inputs = {}
        for name in full.SCENARIOS:
            path = self.root / f"integrational_tests/tests/{name}.bsl"
            path.write_bytes(b'// synthetic public script\n')
            self.inputs[f"integrational_tests/tests/{name}.bsl"] = full.digest(path.read_bytes())
        self.capture = full.quarantine_outputs(self.root, dict.fromkeys(full.SCENARIOS, self.payload))
        self.stage3 = fixture(self.payload, input_hashes=self.inputs)[0]["report"]["stage3"]

    def compare(self, runner):
        return full.compare_outputs(self.root, self.capture, self.stage3, self.inputs, runner=runner)

    def test_fresh_real_source_path_complete_bytes_and_no_normalization(self):
        calls = []
        def runner(args, cwd):
            calls.append(args[-2])
            self.assertEqual(args[-1], full.WINDOWS_TARGET)
            self.assertIn("-I", args)
            self.assertIn("-B", args)
            self.assertTrue(any(value.startswith("pycache_prefix=") for value in args))
            self.assertEqual(cwd, self.root)
            return 0, self.payload, b""
        self.assertEqual(self.compare(runner)["status"], "ok")
        self.assertEqual(calls, [str(self.root / f"integrational_tests/tests/{name}.bsl") for name in full.SCENARIOS])
        for wrong in (self.payload.rstrip(), self.payload + b"\n", self.payload.replace(b"\n", b"\r\n")):
            report = self.compare(lambda *args: (0, wrong, b""))
            self.assertEqual(report["status"], "failed")
            self.assertTrue(all(case["status"] == "mismatched" for case in report["cases"]))
            self.assertNotIn("value", json.dumps(report).replace("values", ""))

    def test_failure_and_stderr_never_accept_matching_prefix_or_leak_output(self):
        for response in ((1, self.payload, b"PRIVATE ERROR"), (0, self.payload, b"PRIVATE ERROR")):
            report = self.compare(lambda *args: response)
            self.assertTrue(all(case["status"] == "error" for case in report["cases"]))
            self.assertNotIn("PRIVATE", json.dumps(report))
        def timeout(*args): raise full.FullError("interpreter_timeout")
        self.assertTrue(all(case["status"] == "timeout" for case in self.compare(timeout)["cases"]))

    def test_source_and_payload_revalidated_before_replay(self):
        source = self.root / "integrational_tests/tests/dates.bsl"
        source.write_bytes(b"changed")
        report = self.compare(lambda *args: (0, self.payload, b""))
        self.assertEqual(report["cases"][1]["failure_kind"], "source_changed")
        path = self.capture / "numbers.out"
        path.chmod(0o600)
        path.write_bytes(b"changed")
        report = self.compare(lambda *args: (0, self.payload, b""))
        self.assertEqual(report["cases"][3]["failure_kind"], "native_capture_changed")

    def test_truncated_or_reordered_case_coverage_cannot_pass(self):
        self.stage3["cases"] = []
        with self.assertRaises(full.FullError): self.compare(lambda *args: (0, self.payload, b""))

    def test_utc_environment_overrides_hostile_ambient_and_drops_credentials(self):
        with mock.patch.dict(os.environ, {"TZ":"Europe/Warsaw", "YADINASSI_TIMEZONE":"Asia/Kathmandu", "PYTHONPATH":"/evil", "GHCR_TOKEN":"PRIVATE"}):
            env = full.child_environment()
        self.assertEqual(env["TZ"], "Etc/UTC")
        self.assertEqual(env["YADINASSI_TIMEZONE"], "Etc/UTC")
        self.assertNotIn("GHCR_TOKEN", env)
        self.assertNotIn("PYTHONPATH", env)


@unittest.skipIf(os.name == "nt", "bounded POSIX pipe/process-group implementation used on Ubuntu Actions only")
class ChildTests(unittest.TestCase):
    def test_stderr_stdout_bounds_and_finite_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            code, output, error = full.bounded_child([sys.executable, "-c", "import os; print(os.environ['YADINASSI_TIMEZONE'])"], root)
            self.assertEqual((code, output, error), (0, b"Etc/UTC\n", b""))
            # Overflow coverage must allow interpreter startup on loaded CI
            # runners; the intentionally short deadline is tested separately.
            # Delay past that short deadline to regress the original masking.
            for script in ("import time; time.sleep(.25); print('PRIVATE'*100)",
                           "import time, sys; time.sleep(.25); sys.stderr.write('PRIVATE'*100)"):
                with self.subTest(script=script), self.assertRaisesRegex(full.FullError, "^interpreter_output_limit$"):
                    full.bounded_child([sys.executable, "-c", script], root, seconds=10, stdout_limit=64, stderr_limit=64)

    def test_timeout_has_its_own_short_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaisesRegex(full.FullError, "^interpreter_timeout$"):
                full.bounded_child([sys.executable, "-c", "import time; time.sleep(30)"],
                                   root, seconds=.1, stdout_limit=64, stderr_limit=64)

    def test_private_cache_prefix_ignores_tampered_repository_bytecode(self):
        import py_compile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "yadinassi"
            package.mkdir()
            module = package / "__init__.py"
            template = 'class Interpreter:\n def __init__(self, output, **options): self.output = output\n def execute(self, *args): self.output("%s")\n'
            module.write_text(template % "POISON")
            before = module.stat()
            py_compile.compile(str(module), doraise=True)
            module.write_text(template % "SOURCE")
            os.utime(module, ns=(before.st_atime_ns, before.st_mtime_ns))
            (root / "integrational_tests/tests").mkdir(parents=True)
            inputs = {}
            for name in full.SCENARIOS:
                source = root / f"integrational_tests/tests/{name}.bsl"
                source.write_bytes(b"// synthetic")
                inputs[f"integrational_tests/tests/{name}.bsl"] = full.digest(source.read_bytes())
            # Prove this valid timestamp/size cache actually wins without the guard.
            _, unsafe, _ = full.bounded_child([sys.executable, "-I", "-c", full.EXECUTE_SCRIPT,
                                              str(root), str(source)], root)
            self.assertEqual(unsafe, b"POISON\n")
            capture = full.quarantine_outputs(root, dict.fromkeys(full.SCENARIOS, b"SOURCE\n"))
            stage = fixture(b"SOURCE\n", input_hashes=inputs)[0]["report"]["stage3"]
            self.assertEqual(full.compare_outputs(root, capture, stage, inputs)["status"], "ok")

    def test_ignored_top_level_bytecode_cannot_shadow_standard_dependencies(self):
        import py_compile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "yadinassi"
            package.mkdir()
            (package / "__init__.py").write_text('class Interpreter:\n def __init__(self, output, **options): self.output = output\n def execute(self, *args):\n  import decimal\n  self.output(getattr(decimal, "CHECK", "SOURCE"))\n')
            shadow = root / "shadow-source.py"
            shadow.write_text('CHECK = "POISON"\n')
            py_compile.compile(str(shadow), cfile=str(root / "decimal.pyc"), doraise=True)
            shadow.unlink()
            source = root / "test.bsl"
            source.write_text("// synthetic")
            code, output, error = full.bounded_child([sys.executable, "-I", "-c", full.EXECUTE_SCRIPT,
                                                     str(root), str(source)], root)
            self.assertEqual((code, output, error), (0, b"SOURCE\n", b""))

    def test_real_interpreter_serialization_and_utc(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "case.bsl"
            path.write_text('Сообщить(XMLString(XMLValue(Type("Date"), "2024-02-29T12:34:56Z"))); Сообщить(" "); Сообщить("");', encoding="utf-8")
            with mock.patch.dict(os.environ, {"TZ":"Europe/Warsaw", "YADINASSI_TIMEZONE":"Europe/Warsaw"}):
                code, output, error = full.bounded_child([sys.executable, "-I", "-c", full.EXECUTE_SCRIPT, str(smoke.ROOT), str(path)], smoke.ROOT)
            self.assertEqual((code, error), (0, b""))
            self.assertEqual(output, b"2024-02-29T12:34:56\n \n\n")


class OrchestrationTests(SyntheticFilesystemCase):
    def invoke(self, *, cleanup_bad=False, mismatch=False, exit_code=0, bad_nonce=False, return_error=False):
        operations = []
        captured_dirs = []
        def silent(args, env, seconds, input_bytes=None):
            operations.append(args[1])
            if args[1] == "login":
                self.assertEqual(input_bytes, b"PRIVATE-TOKEN")
                (Path(env["DOCKER_CONFIG"]) / "config.json").write_text("PRIVATE-TOKEN")
        def bounded(args, env, seconds, limit=smoke.MAX_OUTPUT):
            operations.append(args[1])
            if args[1] == "image": return 0, b"linux/amd64|0\n"
            if args[1] == "ps": return (0, b"still-exists\n") if cleanup_bad else (0, b"")
            self.assertEqual(seconds, 2400)
            self.assertEqual(limit, full.MAX_TRANSPORT)
            mount = args[args.index("--mount") + 1]
            directory = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            inputs = {src: full.digest((directory / dst).read_bytes()) for src, dst in smoke.FULL_STAGED_FILES.items()}
            modules = {name: full.digest(full.generated_module((directory / f"scenarios/{name}.bsl").read_bytes())) for name in full.SCENARIOS}
            data = fixture(input_hashes=inputs, modules=modules)[0]
            nonce = args[-1]
            data["nonce"] = "0" * 32 if bad_nonce else nonce
            data["report"]["stage3"]["nonce"] = nonce
            return exit_code, encode(data)
        real_compare = full.compare_outputs
        def compare(root, capture, stage3, inputs, **kwargs):
            captured_dirs.append(capture)
            self.assertEqual(operations[-1], "ps")
            self.assertTrue(capture.is_dir())
            return real_compare(root, capture, stage3, inputs,
                runner=lambda *args: (0, b"different\n" if mismatch else b" PRIVATE synthetic output \n\n", b""), **kwargs)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, {"GHCR_USER":"Atridis", "GHCR_TOKEN":"PRIVATE-TOKEN"}), \
                mock.patch.object(smoke, "run_silent", side_effect=silent), mock.patch.object(smoke, "bounded_run", side_effect=bounded), \
                mock.patch.object(full, "repository_provenance", return_value={"commit":"c"*40,"tree":"d"*40}), \
                mock.patch.object(full, "interpreter_provenance", return_value={"source_sha256":"e"*64}), \
                mock.patch.object(full, "compare_outputs", side_effect=compare):
            try:
                report = smoke.run_smoke(Path(temporary).resolve(), full_suite=True)
            except smoke.SmokeError as error:
                report = error if return_error else str(error)
            self.assertEqual(list(Path(temporary).resolve().iterdir()), [])
        self.assertTrue(all(not path.exists() for path in captured_dirs))
        return report, operations

    def test_cleanup_before_comparison_and_private_removal_before_success(self):
        report, operations = self.invoke()
        self.assertEqual(report["comparison"]["status"], "ok")
        self.assertTrue(report["native_evidence_accepted"])
        self.assertTrue(report["private_payloads_removed"])
        self.assertTrue(report["container_cleanup_verified"])
        self.assertEqual(operations, ["login", "pull", "image", "run", "rm", "ps"])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_cleanup_failure_bad_nonce_and_exit_cannot_claim_success(self):
        for kwargs, expected in (({"cleanup_bad":True}, "container_cleanup_unverified"),
                                 ({"bad_nonce":True}, "invalid_full_envelope"),
                                 ({"exit_code":1}, "inconsistent_container_exit")):
            report, operations = self.invoke(**kwargs)
            self.assertEqual(report, expected)
            self.assertEqual(operations[-2:], ["rm", "ps"])

    def test_native_success_remains_separate_from_interpreter_mismatch(self):
        report, _ = self.invoke(mismatch=True)
        self.assertTrue(report["native_tests_completed"])
        self.assertEqual(report["comparison"]["status"], "failed")
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(smoke, "run_smoke", return_value=report), contextlib.redirect_stdout(io.StringIO()) as stdout:
            output = Path(temporary).resolve() / "report.json"
            code = smoke.main(["--execute-approved-image", "--full-suite", "--output", str(output)])
            public = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertFalse(public["smoke_completed"])
        self.assertTrue(public["native_tests_completed"])
        self.assertFalse(public["interpreter_comparison_completed"])
        self.assertNotIn("PRIVATE", stdout.getvalue())

    def test_primary_failure_survives_cleanup_failure_with_separate_status(self):
        error, _ = self.invoke(bad_nonce=True, cleanup_bad=True, return_error=True)
        self.assertEqual(str(error), "invalid_full_envelope")
        self.assertEqual(error.cleanup_error, "container_cleanup_unverified")
        self.assertIsNone(error.validated_report)

    def test_known_native_success_survives_host_cleanup_failure(self):
        error, _ = self.invoke(cleanup_bad=True, return_error=True)
        self.assertTrue(error.validated_report["native_cases_completed"])
        self.assertTrue(error.validated_report["private_payloads_removed"])
        self.assertFalse(error.validated_report["container_cleanup_verified"])
        self.assertFalse(error.validated_report["native_evidence_accepted"])
        self.assertTrue(error.validated_report["native_transport_validated"])
        self.assertEqual(error.validated_report["comparison"]["status"], "not_run")
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(smoke, "run_smoke", side_effect=error), contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary).resolve() / "summary.json"
            self.assertEqual(smoke.main(["--execute-approved-image", "--full-suite", "--output", str(output)]), 1)
            public = json.loads(output.read_text())
        self.assertTrue(public["native_tests_completed"])
        self.assertTrue(public["runtime_version_verified"])
        self.assertTrue(public["security_settings_changed"])
        self.assertFalse(public["smoke_completed"])

    def test_windows_integrity_unknown_or_changed_is_not_flattened_to_false(self):
        report, _ = self.invoke()
        for unchanged, expected in ((None, None), (False, True)):
            report["windows_goldens_unchanged"] = unchanged
            error = smoke.SmokeError("windows_goldens_changed", validated_report=report)
            with tempfile.TemporaryDirectory() as temporary, mock.patch.object(smoke, "run_smoke", side_effect=error), contextlib.redirect_stdout(io.StringIO()):
                output = Path(temporary).resolve() / "summary.json"
                self.assertEqual(smoke.main(["--execute-approved-image", "--full-suite", "--output", str(output)]), 1)
                self.assertIs(json.loads(output.read_text())["windows_goldens_modified"], expected)


class ProvenanceTests(SyntheticFilesystemCase):
    def test_rejects_dirty_sha_mismatch_and_ignored_untracked_project_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "yadinassi").mkdir()
            (root / "yadinassi/__init__.py").write_text("# clean")
            state = {"dirty": b""}
            def git(args, cwd, **kwargs):
                command = args[3:]
                if command == ["rev-parse", "HEAD^{commit}"]: return 0, b"c" * 40 + b"\n", b""
                if command == ["rev-parse", "HEAD^{tree}"]: return 0, b"d" * 40 + b"\n", b""
                if command[0] == "status": return 0, state["dirty"], b""
                if command[0] == "ls-files": return 0, b"yadinassi/__init__.py\n", b""
                raise AssertionError(command)
            with mock.patch.object(full, "bounded_child", side_effect=git), mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(full.repository_provenance(root), {"commit":"c"*40,"tree":"d"*40})
                state["dirty"] = b" M yadinassi/__init__.py\n"
                with self.assertRaisesRegex(full.FullError, "repository_identity_unverified"): full.repository_provenance(root)
                state["dirty"] = b""
                with mock.patch.dict(os.environ, {"GITHUB_SHA":"e"*40}):
                    with self.assertRaisesRegex(full.FullError, "repository_commit_mismatch"): full.repository_provenance(root)
                (root / "yadinassi/ignored.py").write_text("# hidden by .gitignore")
                with self.assertRaisesRegex(full.FullError, "repository_sources_unverified"): full.repository_provenance(root)

    def test_fixed_dependency_versions_and_bounded_interpreter_digest(self):
        with mock.patch.object(full.importlib.metadata, "version", side_effect=lambda name: full.DEPENDENCIES[name]):
            data = full.interpreter_provenance(smoke.ROOT)
        self.assertEqual(data["dependencies"], full.DEPENDENCIES)
        self.assertGreater(data["source_file_count"], 10)
        self.assertTrue(full.is_digest(data["source_sha256"]))
        with mock.patch.object(full.importlib.metadata, "version", return_value="PRIVATE WRONG VERSION"):
            with self.assertRaisesRegex(full.FullError, "^interpreter_dependency_invalid$"):
                full.interpreter_provenance(smoke.ROOT)


class SemanticComparisonTests(ComparisonTests):
    """Fake verifier verdicts isolate host gates; verifier tests cover real payloads."""
    def setUp(self):
        super().setUp()
        source = smoke.ROOT / "integrational_tests/tests/collections.bsl"
        # This synthetic fixture represents the reviewed LF source, not the
        # checkout's platform-specific line endings. Never normalize inputs in
        # the production staging, reader, or comparator to satisfy this gate.
        reviewed = source.read_bytes().replace(b"\r\n", b"\n")
        self.assertTrue(reviewed.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(full.digest(reviewed), full.COLLECTIONS_SOURCE_SHA256)
        (self.root / "integrational_tests/tests/collections.bsl").write_bytes(reviewed)
        self.inputs["integrational_tests/tests/collections.bsl"] = full.COLLECTIONS_SOURCE_SHA256
        self.stage3 = fixture(self.payload, input_hashes=self.inputs)[0]["report"]["stage3"]
        self.context = bootstrap_report()
        self.context.update(stage3=self.stage3, invocation_nonce=NONCE, container_exit_code=0,
            image=smoke.IMAGE, platform="linux/amd64", native_target=full.LINUX_TARGET,
            comparison_mode=full.MAP_MODE, trusted_input_sha256=self.inputs,
            configured_timezone="Etc/UTC", configured_native_locale="ru_RU",
            container_cleanup_verified=True, native_cases_completed=True,
            native_transport_validated=True, native_evidence_accepted=True)
        self.contract = full.map_contract()

    def verdict(self, *, equal=False):
        return {"profile":full.MAP_MODE, "status":"equivalent", "records":854,
                "byte_equal_records":854 if equal else 853,
                "accepted_labels":[] if equal else [self.contract.ELIGIBLE_LABELS[0]], "reason":"none"}

    def semantic_compare(self, *, verdict=None, equal=False, other_diff=False, context=None):
        calls = []
        def runner(args, cwd):
            self.assertEqual(args[-1], full.LINUX_TARGET)
            calls.append(Path(args[-2]).stem)
            different = (calls[-1] == "collections" and not equal) or (calls[-1] == "dates" and other_diff)
            return 0, self.payload + b"x" if different else self.payload, b""
        verifier = mock.Mock(return_value=self.verdict(equal=equal) if verdict is None else verdict)
        self.contract.compare_collections = verifier
        with mock.patch.object(full, "map_contract", return_value=self.contract):
            result = full.compare_outputs(self.root, self.capture, self.stage3, self.inputs,
                runner=runner, native_target=full.LINUX_TARGET, comparison_mode=full.MAP_MODE,
                runtime_evidence=self.context if context is None else context)
        return result, verifier, calls

    def test_semantic_acceptance_keeps_raw_mismatch_and_explicit_target(self):
        before = full.read_regular(self.capture / "collections.out", full.MAX_FILE)
        result, verifier, calls = self.semantic_compare()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["acceptance_status"], "accepted")
        case = result["cases"][0]
        self.assertEqual(case["status"], "mismatched")
        self.assertIsNotNone(case["mismatch"])
        self.assertNotEqual(case["native_sha256"], case["interpreter_sha256"])
        self.assertEqual(case["semantic"], self.verdict())
        verifier.assert_called_once_with(self.payload, self.payload + b"x", full.COLLECTIONS_SOURCE_SHA256)
        self.assertEqual(calls, list(full.SCENARIOS))
        self.assertEqual(full.read_regular(self.capture / "collections.out", full.MAX_FILE), before)
        self.assertTrue(all(case["semantic"] is None for case in result["cases"][1:]))

    def test_byte_identical_payload_still_requires_full_semantic_validation(self):
        rejected = {"profile":full.MAP_MODE, "status":"rejected", "records":0,
                    "byte_equal_records":0, "accepted_labels":[], "reason":"unsupported_payload"}
        result, verifier, _ = self.semantic_compare(verdict=rejected, equal=True)
        verifier.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["acceptance_status"], "rejected")
        self.assertEqual(result["cases"][0]["status"], "matched")

    def test_all_other_five_outputs_remain_byte_strict(self):
        result, _, _ = self.semantic_compare(other_diff=True)
        self.assertEqual(result["acceptance_status"], "rejected")
        self.assertEqual(result["cases"][1]["status"], "mismatched")
        self.assertIsNone(result["cases"][1]["semantic"])
        self.assertEqual(result["cases"][1]["acceptance_status"], "rejected")

    def test_unknown_options_and_stale_context_cannot_run_verifier(self):
        for target, mode in ((full.WINDOWS_TARGET,full.MAP_MODE), ("auto",full.BYTE_EXACT),
                             (full.LINUX_TARGET,"typed-map-order-v2"), (None,full.BYTE_EXACT)):
            with self.subTest(target=target, mode=mode), self.assertRaises(full.FullError):
                full.compare_outputs(self.root,self.capture,self.stage3,self.inputs,
                                     native_target=target, comparison_mode=mode)
        edits = [lambda r:r.update(configured_timezone="Europe/Warsaw"),
            lambda r:r.pop("configured_native_locale"), lambda r:r.update(configured_native_locale="en_US"),
            lambda r:r.update(runtime_version="8.3.27.2342"),
            lambda r:r.update(runtime_version_source="image_label"), lambda r:r.update(platform="windows/amd64"),
            lambda r:r.update(image=smoke.IMAGE[:-1]+"0"), lambda r:r.update(native_target=full.WINDOWS_TARGET),
            lambda r:r.update(comparison_mode=full.BYTE_EXACT), lambda r:r.update(container_exit_code=1),
            lambda r:r.update(container_cleanup_verified=False), lambda r:r.update(native_transport_validated=False),
            lambda r:r.update(native_evidence_accepted=False), lambda r:r.update(native_cases_completed=False),
            lambda r:r.update(invocation_nonce="0"*32), lambda r:r.update(trusted_input_sha256={}),
            lambda r:r["stage2"].update(actual_version="8.3.27.2342"),
            lambda r:r["stage2"].update(named_user_verified=False),
            lambda r:r["stage3"]["cases"][0].update(source_sha256="a"*64),
            lambda r:r["stage3"]["input_sha256"].update({"integrational_tests/tests/collections.bsl":"a"*64}),
            lambda r:r["stage3"]["cases"][1].update(output_size=999)]
        for edit in edits:
            context = copy.deepcopy(self.context); edit(context)
            with self.subTest(edit=edit), self.assertRaisesRegex(full.FullError,"^semantic_context_invalid$"):
                self.semantic_compare(context=context)

    def test_malformed_semantic_claims_fail_closed(self):
        edits = [lambda v:v.update(extra="PRIVATE"), lambda v:v.pop("profile"),
            lambda v:v.update(profile="typed-map-order-v2"), lambda v:v.update(status=[]),
            lambda v:v.update(records=True), lambda v:v.update(records=853),
            lambda v:v.update(byte_equal_records=854), lambda v:v.update(accepted_labels=[]),
            lambda v:v.update(accepted_labels=["PRIVATE"]), lambda v:v.update(reason="PRIVATE"),
            lambda v:v.update(reason=[]), lambda v:v.update(status="rejected", reason="typed_difference")]
        for edit in edits:
            verdict=self.verdict(); edit(verdict)
            with self.subTest(edit=edit), self.assertRaisesRegex(full.FullError,"^semantic_result_invalid$"):
                self.semantic_compare(verdict=verdict)

    def test_comparison_schema_and_aggregate_claims_cannot_disagree(self):
        result, _, _ = self.semantic_compare()
        edits = [lambda r:r.update(extra="PRIVATE"),lambda r:r.update(schema=1),
            lambda r:r.pop("acceptance_status"),lambda r:r.update(acceptance_status="rejected"),
            lambda r:r.update(status="ok"),lambda r:r.update(native_target=full.WINDOWS_TARGET),
            lambda r:r["cases"][0].update(status="matched"),lambda r:r["cases"][0].update(semantic=None),
            lambda r:r["cases"][0].update(mismatch=None),lambda r:r["cases"][0].update(acceptance_status="rejected"),
            lambda r:r["cases"][1].update(semantic=self.verdict()),lambda r:r["cases"].pop()]
        for edit in edits:
            changed=copy.deepcopy(result);edit(changed)
            with self.subTest(edit=edit),self.assertRaisesRegex(full.FullError,"^comparison_evidence_invalid$"):
                full.validate_comparison(changed,self.stage3,full.LINUX_TARGET,full.MAP_MODE)


class SemanticFixtureTests(unittest.TestCase):
    def test_lf_and_crlf_checkout_setup_keeps_reviewed_fixture_and_strict_source_gate(self):
        source = smoke.ROOT / "integrational_tests/tests/collections.bsl"
        read_bytes = Path.read_bytes
        reviewed = read_bytes(source).replace(b"\r\n", b"\n")
        for ending, checkout in (("LF", reviewed), ("CRLF", reviewed.replace(b"\n", b"\r\n"))):
            with self.subTest(checkout=ending):
                case = SemanticComparisonTests("test_semantic_acceptance_keeps_raw_mismatch_and_explicit_target")
                try:
                    def read_checkout(path):
                        return checkout if path == source else read_bytes(path)
                    with mock.patch.object(Path, "read_bytes", read_checkout):
                        case.setUp()
                    copied = case.root / "integrational_tests/tests/collections.bsl"
                    self.assertEqual(copied.read_bytes(), reviewed)
                    self.assertTrue(copied.read_bytes().startswith(b"\xef\xbb\xbf"))
                    self.assertEqual(full.digest(copied.read_bytes()), full.COLLECTIONS_SOURCE_SHA256)
                    case.test_semantic_acceptance_keeps_raw_mismatch_and_explicit_target()
                    # The production comparator must still reject any change
                    # after fixture setup, including line endings or the BOM.
                    for mutation, changed in (("CRLF", reviewed.replace(b"\n", b"\r\n")),
                                              ("missing BOM", reviewed[3:]),
                                              ("content", reviewed + b"// changed\n")):
                        with self.subTest(mutation=mutation):
                            copied.write_bytes(changed)
                            result, verifier, calls = case.semantic_compare()
                            self.assertEqual(result["acceptance_status"], "rejected")
                            self.assertEqual(result["cases"][0]["status"], "error")
                            self.assertEqual(result["cases"][0]["failure_kind"], "source_changed")
                            verifier.assert_not_called()
                            self.assertEqual(calls, list(full.SCENARIOS[1:]))
                finally:
                    case.doCleanups()

    def test_fixture_setup_rejects_unreviewed_checkout_bytes(self):
        source = smoke.ROOT / "integrational_tests/tests/collections.bsl"
        read_bytes = Path.read_bytes
        reviewed = read_bytes(source).replace(b"\r\n", b"\n")
        for mutation, checkout in (("missing BOM", reviewed[3:]),
                                   ("bare CR", reviewed.replace(b"\n", b"\r")),
                                   ("content", reviewed + b"// changed\n")):
            with self.subTest(mutation=mutation):
                case = SemanticComparisonTests("test_semantic_acceptance_keeps_raw_mismatch_and_explicit_target")
                try:
                    def read_checkout(path):
                        return checkout if path == source else read_bytes(path)
                    with mock.patch.object(Path, "read_bytes", read_checkout), self.assertRaises(AssertionError):
                        case.setUp()
                finally:
                    case.doCleanups()


if __name__ == "__main__":
    unittest.main()

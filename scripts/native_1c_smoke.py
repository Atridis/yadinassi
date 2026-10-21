#!/usr/bin/env python3
"""Run the explicitly approved image once; emit only a validated public report.

The image's stdout/stderr, environment, labels, database, binaries and native XML
are never published. Exact test outputs require a separate explicit export opt-in. No runtime package install or host-writable mount is used.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

IMAGE = "ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728"
PROBE = Path(__file__).with_name("native_1c_smoke_probe.sh")
MAX_OUTPUT = 32_768
MAX_RUNTIME = 480
BOOTSTRAP_MAX_RUNTIME = 900
FULL_MAX_RUNTIME = 2400
ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_SPEC = importlib.util.spec_from_file_location(
    "native_smoke_diagnostics", ROOT / "scripts/native_1c_bootstrap/diagnostics.py")
DIAGNOSTICS = importlib.util.module_from_spec(DIAGNOSTIC_SPEC)
DIAGNOSTIC_SPEC.loader.exec_module(DIAGNOSTICS)
FULL_SPEC = importlib.util.spec_from_file_location(
    "native_full_host", ROOT / "scripts/native_1c_full_host.py")
FULL = importlib.util.module_from_spec(FULL_SPEC)
FULL_SPEC.loader.exec_module(FULL)
STAGED_FILES = {
    "scripts/native_1c_smoke_probe.sh": "probe.sh",
    **{f"scripts/native_1c_bootstrap/{name}": f"bootstrap/{name}" for name in (
        "run_stage.py", "inject_modules.py", "evidence_gates.py", "diagnostics.py", "simple_smoke.bsl",
        "modules/SessionModule.bsl", "modules/ManagedApplicationModule.bsl")},
    "integrational_tests/test_launcher.py": "launcher/test_launcher.py",
    **{f"integrational_tests/launcher_1c/{name}": f"launcher/launcher_1c/{name}" for name in (
        "Launcher.xml", "Launcher/Ext/ObjectModule.bsl", "Launcher/Forms/Main.xml",
        "Launcher/Forms/Main/Ext/Form.xml", "Launcher/Forms/Main/Ext/Form/Module.bsl",
        "TestModule.xml", "TestModule/Ext/ObjectModule.bsl")},
}
FULL_STAGED_FILES = {
    **STAGED_FILES,
    "scripts/native_1c_bootstrap/full_suite.py": "bootstrap/full_suite.py",
    **{f"integrational_tests/tests/{name}.bsl": f"scenarios/{name}.bsl" for name in FULL.SCENARIOS},
}
STAGE_FLAGS = ("modules_reimported", "bootstrap_verified", "named_designer_verified",
               "named_user_verified", "control_removed", "launcher_built", "simple_epf_passed")
STAGES = {"inject", "load", "redump", "bootstrap", "named_designer", "verify", "launcher_build", "simple_epf", "unknown"}
FAILURE_KINDS = {"none", "timeout", "process_failed", "invalid_dump_result", "artifact_missing",
                 "metadata_rejected", "module_mismatch", "compile_error", "permission_denied",
                 "hook_missing", "marker_invalid", "version_mismatch", "output_mismatch",
                 "unexpected_failure", "stale_evidence", "unsupported_api"}
EXPECTED_VERSION = "8.3.27.1508"
SIMPLE_OUTPUT_SHA256 = hashlib.sha256(b"native-smoke-v1\n42\n").hexdigest()
STATUS = {"ok", "python_missing", "python_unsupported", "capabilities_failed", "libraries_failed", "display_failed", "create_failed", "dump_failed", "format_failed", "stage2_failed"}
BOOL_KEYS = {"nonroot", "executable_available", "libraries_resolved", "display_started", "infobase_created", "configuration_dumped", "native_tests_completed", "security_settings_changed"}
KNOWN_ELEMENTS = {
    "Name", "Synonym", "Comment", "NamePrefix", "ConfigurationExtensionCompatibilityMode",
    "DefaultRunMode", "UsePurposes", "ScriptVariant", "DefaultRoles", "BriefInformation",
    "DetailedInformation", "Copyright", "Vendor", "Version", "CompatibilityMode",
    "DefaultLanguage", "DefaultStyle", "DefaultInterface", "UseManagedFormInOrdinaryApplication",
    "UseOrdinaryFormInManagedApplication", "EnableManagedLock", "MainClientApplicationWindowMode",
    "DefaultDataLockControlMode", "ModalityUseMode", "SynchronousPlatformExtensionAndAddInCallUseMode",
    "InterfaceCompatibilityMode", "DatabaseTablespacesUseMode", "MobileApplicationURLs",
    "CommonPictures", "Roles", "Languages", "CommonModules", "Subsystems", "SessionParameters",
}


class SmokeError(Exception):
    """Only fixed, non-sensitive error codes may escape an external command."""

    def __init__(self, code: str, *, security_uncertain: bool = False, validated_report=None, cleanup_error=None):
        super().__init__(code)
        self.security_uncertain = security_uncertain
        self.validated_report = validated_report
        self.cleanup_error = cleanup_error


def docker_environment(config: Path) -> dict[str, str]:
    # Do not propagate Actions credentials, auth helpers, DOCKER_HOST/context,
    # proxies, LD_PRELOAD or any arbitrary runner environment to Docker.
    return {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": str(config.parent), "DOCKER_CONFIG": str(config),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def run_silent(args: list[str], env: dict[str, str], seconds: int,
               input_bytes: bytes | None = None) -> None:
    try:
        result = subprocess.run(args, input=input_bytes, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=env, timeout=seconds,
                                check=False)
    except subprocess.TimeoutExpired:
        raise SmokeError("docker_command_timeout") from None
    except OSError:
        raise SmokeError("docker_command_unavailable") from None
    if result.returncode:
        raise SmokeError("docker_command_failed")


def bounded_run(args: list[str], env: dict[str, str], seconds: int,
                limit: int = MAX_OUTPUT) -> tuple[int, bytes]:
    """Drain bounded stdout; never print untrusted container/Docker output."""
    output = bytearray()
    deadline = time.monotonic() + seconds
    try:
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=env) as process:
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                try:
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise SmokeError("container_timeout")
                        if not selector.select(min(remaining, 0.25)):
                            continue
                        chunk = os.read(process.stdout.fileno(), 4096)
                        if not chunk:
                            selector.unregister(process.stdout)
                            break
                        output.extend(chunk)
                        if len(output) > limit:
                            raise SmokeError("container_output_limit")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SmokeError("container_timeout")
                    code = process.wait(timeout=remaining)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
    except subprocess.TimeoutExpired:
        raise SmokeError("container_timeout") from None
    except OSError:
        raise SmokeError("docker_command_unavailable") from None
    return code, bytes(output)


def staged_files(full_suite: bool, client_probe: bool) -> dict:
    if client_probe and not full_suite:
        raise SmokeError("client_probe_requires_full_suite")
    return {**(FULL_STAGED_FILES if full_suite else STAGED_FILES),
            **({"scripts/native_1c_bootstrap/client_probe.bsl": "bootstrap/client_probe.bsl"}
               if client_probe else {})}


def stage_inputs(destination: Path, *, full_suite: bool = False, client_probe: bool = False) -> dict[str, str]:
    if destination.is_symlink():
        raise SmokeError("invalid_staged_inputs")
    destination = destination.parent.resolve(strict=True) / destination.name
    destination.mkdir(mode=0o755)
    destination.chmod(0o755)
    digests = {}
    for source_name, target_name in staged_files(full_suite, client_probe).items():
        source = ROOT / source_name
        if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent != ROOT):
            raise SmokeError("invalid_staged_source")
        if not source.is_file() or not 0 < source.stat().st_size <= 1_048_576:
            raise SmokeError("invalid_staged_source")
        target = destination / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            source_bytes = FULL.read_regular(source, 1_048_576, nonempty=True)
        except FULL.FullError:
            raise SmokeError("invalid_staged_source") from None
        target.write_bytes(source_bytes)
        target.chmod(0o644)
        digests[source_name] = hashlib.sha256(target.read_bytes()).hexdigest()
    for directory in destination.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    validate_input_tree(destination, full_suite=full_suite, client_probe=client_probe)
    return digests


def validate_input_tree(root: Path, *, full_suite: bool = False, client_probe: bool = False) -> None:
    files = staged_files(full_suite, client_probe)
    if root.is_symlink() or not root.is_dir():
        raise SmokeError("invalid_staged_inputs")
    root = root.resolve(strict=True)
    actual = set()
    allowed_directories = {parent.as_posix() for name in files.values()
                           for parent in Path(name).parents if parent.as_posix() != "."}
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise SmokeError("invalid_staged_inputs")
        if path.is_dir() and path.relative_to(root).as_posix() not in allowed_directories:
            raise SmokeError("invalid_staged_inputs")
        if path.is_file():
            try:
                FULL.read_regular(path, 1_048_576, nonempty=True)
            except FULL.FullError:
                raise SmokeError("invalid_staged_inputs") from None
            actual.add(path.relative_to(root).as_posix())
    if actual != set(files.values()):
        raise SmokeError("invalid_staged_inputs")


def container_command(probe: Path, name: str, *, bootstrap: bool = False,
                      full_suite: bool = False, nonce: str | None = None, client_probe: bool = False, watchdog_check: bool = False) -> list[str]:
    if watchdog_check and not client_probe:
        raise SmokeError("watchdog_check_requires_client_probe")
    if client_probe and not full_suite:
        raise SmokeError("client_probe_requires_full_suite")
    if full_suite:
        bootstrap = True
        if type(nonce) is not str or not re.fullmatch(r"[0-9a-f]{32}", nonce):
            raise SmokeError("invalid_invocation_nonce")
    if probe.is_symlink():
        raise SmokeError("invalid_probe_path")
    probe = probe.resolve(strict=True)
    if (not bootstrap and not probe.is_file()) or "," in str(probe):
        raise SmokeError("invalid_probe_path")
    if bootstrap:
        validate_input_tree(probe, full_suite=full_suite, client_probe=client_probe)
    target = "/smoke" if bootstrap else "/smoke/probe.sh"
    return [
        "docker", "run", "--name", name, "--hostname", "onec-smoke",
        "--pull", "never", "--platform", "linux/amd64", "--network", "none",
        "--user", "1000:1000", "--read-only", "--no-healthcheck", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true", "--pids-limit", "256",
        "--memory", "2g", "--memory-swap", "2g", "--cpus", "2",
        "--ulimit", "nofile=1024:1024", "--ulimit", "fsize=67108864:67108864",
        "--ipc", "private", "--shm-size", "128m", "--log-driver", "none",
        "--stop-timeout", "10", "--init",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777",
        "--mount", f"type=bind,src={probe},dst={target},readonly",
        "--workdir", "/tmp", "--entrypoint", "/usr/bin/env", IMAGE,
        "-i", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/tmp/home", "XDG_RUNTIME_DIR=/tmp/runtime", "DISPLAY=:99",
        "LANG=ru_RU.UTF-8", "LC_ALL=ru_RU.UTF-8", "TZ=Etc/UTC",
        "/bin/bash", "--noprofile", "--norc", "/smoke/probe.sh",
    ] + (["--full-suite", "--invocation-nonce", nonce] if full_suite else
         ["--bootstrap-simple-epf"] if bootstrap else []) + (["--client-probe"] if client_probe else []) + (["--client-watchdog-check"] if watchdog_check else [])


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def validate_stage2(data: object) -> dict:
    if type(data) is not dict or set(data) != set(STAGE_FLAGS) | {
        "schema", "status", "failed_stage", "failure_kind", "actual_version", "version_source",
        "simple_output_sha256", "security_change_attempted", "security_settings_state", "diagnostics", "protection_observation"}:
        raise ValueError("stage2 keys")
    if type(data["schema"]) is not int or data["schema"] != 1 or data["status"] not in {"ok", "failed"}:
        raise ValueError("stage2 status")
    DIAGNOSTICS.validate_diagnostics(data["diagnostics"], success=data["status"] == "ok",
                                     primary_kind=data["failure_kind"])
    if data["failed_stage"] not in {"bootstrap", "verify"} and any(
            data["diagnostics"][key] != "not_checked" for key in ("session_marker", "managed_marker")):
        raise ValueError("diagnostic marker stage")
    if any(type(data[key]) is not bool for key in (*STAGE_FLAGS, "security_change_attempted")):
        raise ValueError("stage2 flag")
    if data["failure_kind"] not in FAILURE_KINDS or data["failed_stage"] not in STAGES | {None}:
        raise ValueError("stage2 failure")
    if data["security_settings_state"] not in {"not_attempted", "unverified", "verified"}:
        raise ValueError("security state")
    # Role loading is already a potential security mutation. Unknown outcomes
    # must remain conservative; only rejection before native load is unchanged.
    if data["security_change_attempted"] is not (data["failed_stage"] != "inject"):
        raise ValueError("security attempt disagrees with reached native stage")
    expected_security = "verified" if data["bootstrap_verified"] else "unverified" if data["security_change_attempted"] else "not_attempted"
    if data["security_settings_state"] != expected_security or (data["bootstrap_verified"] and not data["security_change_attempted"]):
        raise ValueError("security claim")
    # Verified stages form a prefix; a later positive gate cannot hide a prior failure.
    stopped = False
    for key in STAGE_FLAGS:
        if stopped and data[key]:
            raise ValueError("out-of-order gate")
        stopped |= not data[key]
    if data["status"] == "failed":
        completed = {"inject": 0, "load": 0, "redump": 0, "bootstrap": 1,
                     "named_designer": 2, "verify": 3, "launcher_build": 5,
                     "simple_epf": 6, "unknown": 0}.get(data["failed_stage"])
        if completed is None or any(data[key] is not (index < completed)
                                    for index, key in enumerate(STAGE_FLAGS)):
            raise ValueError("failed-stage gate claims")
    observation = DIAGNOSTICS.validate_protection_observation(data["protection_observation"])
    observed_stage = observation["stage"]
    supported_shape = (observation["property_type"] == "UnsafeOperationProtectionDescription"
                       and observation["warning_type"] == "Boolean")
    if observed_stage == "bootstrap" and (not data["modules_reimported"]
            or (data["failed_stage"] == "bootstrap" and data["failure_kind"] == "stale_evidence")):
        raise ValueError("unreached bootstrap type observation")
    if observed_stage == "verify" and (not data["named_designer_verified"]
            or (data["failed_stage"] == "verify" and data["failure_kind"] == "stale_evidence")):
        raise ValueError("unreached named type observation")
    if data["bootstrap_verified"] and (observed_stage is None
            or (observed_stage == "bootstrap" and not supported_shape)):
        raise ValueError("verified bootstrap without supported observed shape")
    if data["named_user_verified"] and (observed_stage != "verify" or not supported_shape):
        raise ValueError("verified named user without supported observed shape")
    version = data["actual_version"]
    if version is None:
        if data["version_source"] != "not_measured" or data["bootstrap_verified"]:
            raise ValueError("version claim")
    elif (type(version) is not str or not re.fullmatch(r"[0-9]{1,4}(?:\.[0-9]{1,4}){3}", version)
          or data["version_source"] != "SystemInfo.AppVersion"):
        raise ValueError("runtime version")
    if data["bootstrap_verified"] and version != EXPECTED_VERSION:
        if not (data["status"] == "failed" and data["failed_stage"] == "verify"
                and data["failure_kind"] == "version_mismatch" and not data["named_user_verified"]):
            raise ValueError("verified unexpected version")
    if data["simple_output_sha256"] != (SIMPLE_OUTPUT_SHA256 if data["simple_epf_passed"] else None):
        raise ValueError("simple output digest")
    if data["status"] == "ok":
        if not all(data[key] for key in STAGE_FLAGS) or data["failed_stage"] is not None or data["failure_kind"] != "none":
            raise ValueError("incomplete stage2 success")
    elif data["failed_stage"] is None or data["failure_kind"] == "none" or data["simple_epf_passed"]:
        raise ValueError("inconsistent stage2 failure")
    return data


def validate_report(raw: bytes, *, bootstrap: bool = False, full_suite: bool = False) -> dict[str, object]:
    try:
        if len(raw) > MAX_OUTPUT:
            raise ValueError("oversized")
        data = FULL.strict_json(raw, MAX_OUTPUT)
        if type(data) is not dict or type(data.get("schema")) is not int or data["schema"] != 1:
            raise ValueError("schema")
        if data in ({"schema": 1, "status": "python_missing"}, {"schema": 1, "status": "python_unsupported"}):
            return data
        expected = BOOL_KEYS | {"schema", "status", "python_version", "runtime_version",
                                "runtime_version_source", "configuration_format"}
        if bootstrap:
            expected.add("stage2")
        if full_suite:
            expected.add("stage3")
        if set(data) != expected or data["status"] not in STATUS | ({"stage3_failed"} if full_suite else set()):
            raise ValueError("keys")
        if any(type(data[key]) is not bool for key in BOOL_KEYS - {"security_settings_changed"}):
            raise ValueError("boolean")
        stage2 = data.get("stage2")
        if stage2 is not None:
            validate_stage2(stage2)
        version = stage2["actual_version"] if stage2 else None
        source = stage2["version_source"] if stage2 else "not_measured"
        security = (True if stage2["security_settings_state"] == "verified" else None
                    if stage2["security_settings_state"] == "unverified" else False) if stage2 else False
        if (data["runtime_version"] != version or data["runtime_version_source"] != source
                or data["security_settings_changed"] is not security or (data["native_tests_completed"] and not full_suite)):
            raise ValueError("invalid claim")
        if data["status"] == "ok" and bootstrap and (stage2 is None or stage2["status"] != "ok"):
            raise ValueError("stage2 missing")
        if data["status"] == "stage2_failed" and (stage2 is None or stage2["status"] != "failed"):
            raise ValueError("stage2 failure missing")
        if not isinstance(data["python_version"], str) or not re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}", data["python_version"]):
            raise ValueError("version")
        if tuple(map(int, data["python_version"].split(".")[:2])) < (3, 10):
            raise ValueError("unsupported Python")
        fmt = data["configuration_format"]
        if fmt is not None:
            expected_format = {"root", "kind", "namespace", "schema_version", "element_count", "sha256", "known_elements", "managed_application_module_present", "session_module_present"}
            if type(fmt) is not dict or set(fmt) != expected_format:
                raise ValueError("format keys")
            if (fmt["root"], fmt["kind"], fmt["namespace"]) != ("MetaDataObject", "Configuration", "http://v8.1c.ru/8.3/MDClasses"):
                raise ValueError("format namespace")
            if not isinstance(fmt["schema_version"], str) or not re.fullmatch(r"[0-9]{1,2}(?:\.[0-9]{1,3}){1,3}", fmt["schema_version"]):
                raise ValueError("schema version")
            if type(fmt["element_count"]) is not int or not 1 <= fmt["element_count"] <= 4096:
                raise ValueError("element count")
            if not isinstance(fmt["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", fmt["sha256"]):
                raise ValueError("digest")
            if type(fmt["known_elements"]) is not list or any(type(item) is not str for item in fmt["known_elements"]):
                raise ValueError("known elements")
            if len(fmt["known_elements"]) > len(KNOWN_ELEMENTS) or not set(fmt["known_elements"]) <= KNOWN_ELEMENTS:
                raise ValueError("unknown elements")
            if any(type(fmt[key]) is not bool for key in ("managed_application_module_present", "session_module_present")):
                raise ValueError("module presence")
        if data["status"] == "ok" and (not all(data[key] for key in BOOL_KEYS - {"native_tests_completed", "security_settings_changed"}) or fmt is None):
            raise ValueError("incomplete success")
        return data
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise SmokeError("invalid_container_report") from None


def run_smoke(temp_root: Path, *, bootstrap: bool = False, full_suite: bool = False,
              export_native_outputs: bool = False, native_target: str = FULL.WINDOWS_TARGET,
              comparison_mode: str = FULL.BYTE_EXACT, client_probe: bool = False, watchdog_check: bool = False) -> dict[str, object]:
    if watchdog_check and not client_probe:
        raise SmokeError("watchdog_check_requires_client_probe")
    if client_probe and not full_suite:
        raise SmokeError("client_probe_requires_full_suite")
    if export_native_outputs and not full_suite:
        raise SmokeError("native_artifact_requires_full_suite")
    FULL.validate_comparison_options(native_target, comparison_mode)
    if not full_suite and (native_target != FULL.WINDOWS_TARGET or comparison_mode != FULL.BYTE_EXACT):
        raise SmokeError("comparison_requires_full_suite")
    retained_outputs = None
    bootstrap = bootstrap or full_suite
    # Remove the secret from the process environment before any external command.
    token = os.environ.pop("GHCR_TOKEN", "")
    actor = os.environ.pop("GHCR_USER", "")
    if not token or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", actor):
        raise SmokeError("registry_credentials_missing")
    name = "onec-smoke-" + uuid.uuid4().hex
    nonce = uuid.uuid4().hex if full_suite else None
    baseline = FULL.windows_fingerprints(ROOT) if full_suite else None
    provenance = FULL.repository_provenance(ROOT) if full_suite else None
    interpreter = FULL.interpreter_provenance(ROOT) if full_suite else None
    work_name = None
    report = None
    try:
        with tempfile.TemporaryDirectory(prefix="onec-smoke-", dir=temp_root) as work_name:
            work = Path(work_name).resolve()
            staged = work / "staged-inputs"
            input_hashes = stage_inputs(staged, full_suite=full_suite, client_probe=client_probe) if bootstrap else None
            module_hashes = ({case: FULL.digest(FULL.generated_module(
                FULL.read_regular(staged / f"scenarios/{case}.bsl", FULL.MAX_FILE, nonempty=True)))
                for case in FULL.SCENARIOS} if full_suite else None)
            if client_probe:
                module_hashes["client_probe"] = FULL.digest(FULL.generated_module(
                    FULL.read_regular(staged / "bootstrap/client_probe.bsl", FULL.MAX_FILE, nonempty=True)))
            auth = work / "registry-auth"
            auth.mkdir(mode=0o700)
            auth_env = docker_environment(auth)
            try:
                run_silent(["docker", "login", "ghcr.io", "--username", actor, "--password-stdin"], auth_env, 60, token.encode())
                token = ""
                run_silent(["docker", "pull", "--platform", "linux/amd64", IMAGE], auth_env, 600)
            finally:
                token = ""
                shutil.rmtree(auth)
            clean = work / "no-auth"
            clean.mkdir(mode=0o700)
            env = docker_environment(clean)
            code, platform = bounded_run(["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}", IMAGE], env, 30, 128)
            if code != 0 or platform.strip() != b"linux/amd64|0":
                raise SmokeError("unexpected_image_platform_or_volumes")
            run_command = container_command(staged if bootstrap else PROBE, name, bootstrap=bootstrap,
                                            full_suite=full_suite, nonce=nonce, client_probe=client_probe, watchdog_check=watchdog_check)
            payloads = {}
            report = None
            primary_error = None
            cleanup_error = None
            try:
                runtime = FULL_MAX_RUNTIME if full_suite else BOOTSTRAP_MAX_RUNTIME if bootstrap else MAX_RUNTIME
                if full_suite:
                    code, raw = bounded_run(run_command, env, runtime, FULL.MAX_TRANSPORT)
                    report, payloads = FULL.validate_envelope(raw, nonce, input_hashes, module_hashes, validate_report, watchdog_check=watchdog_check)
                    del raw
                else:
                    code, raw = bounded_run(run_command, env, runtime)
                    report = validate_report(raw, bootstrap=bootstrap)
                report["container_exit_code"] = code
                if bootstrap:
                    report["trusted_input_sha256"] = input_hashes
                if code != 0 and report["status"] == "ok":
                    raise SmokeError("inconsistent_container_exit")
                if not -64 <= code <= 255:
                    raise SmokeError("unexpected_container_exit_code")
            except (SmokeError, FULL.FullError) as error:
                primary_error = str(error)
            finally:
                try:
                    run_silent(["docker", "rm", "--force", name], env, 30)
                    if full_suite:
                        cleanup_code, remaining = bounded_run(
                            ["docker", "ps", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"],
                            env, 30, 128)
                        if cleanup_code != 0 or remaining.strip():
                            raise SmokeError("container_cleanup_unverified")
                except SmokeError:
                    cleanup_error = "container_cleanup_unverified"
            if full_suite and report is not None:
                report.update(invocation_nonce=nonce, repository=provenance, interpreter=interpreter,
                              image=IMAGE, platform="linux/amd64",
                              native_target=native_target, comparison_mode=comparison_mode,
                              configured_timezone="Etc/UTC", configured_native_locale="ru_RU",
                              container_cleanup_verified=cleanup_error is None,
                              native_cases_completed=all(case["status"] == "ok" for case in report["stage3"]["cases"]),
                              native_transport_validated=bool(payloads) and primary_error is None,
                              native_evidence_accepted=False,
                              private_payloads_removed=False,
                              comparison={"schema": 2, "status": "not_run", "acceptance_status": "not_run",
                                          "native_target": native_target, "comparison_mode": comparison_mode, "cases": []})
            if primary_error or cleanup_error:
                payloads.clear()
                raise SmokeError(primary_error or cleanup_error, security_uncertain=bootstrap,
                                 validated_report=report if full_suite else None,
                                 cleanup_error=cleanup_error if primary_error else None)
            if full_suite:
                try:
                    if payloads:
                        capture = FULL.quarantine_outputs(work, payloads)
                        report["native_evidence_accepted"] = True
                        payloads.clear()
                        report["comparison"] = FULL.compare_outputs(ROOT, capture, report["stage3"], input_hashes,
                            native_target=native_target, comparison_mode=comparison_mode, runtime_evidence=report)
                    report["windows_goldens_unchanged"] = FULL.windows_fingerprints(ROOT) == baseline
                    if not report["windows_goldens_unchanged"]:
                        raise FULL.FullError("windows_goldens_changed")
                    if FULL.interpreter_provenance(ROOT) != interpreter or FULL.repository_provenance(ROOT) != provenance:
                        raise FULL.FullError("execution_provenance_changed")
                    if export_native_outputs and report["native_evidence_accepted"]:
                        retained_outputs = FULL.retain_output_bytes(capture, report["stage3"])
                except FULL.FullError as error:
                    payloads.clear()
                    raise SmokeError(str(error), security_uncertain=True, validated_report=report) from None
    except SmokeError as error:
        if full_suite and error.validated_report is not None and work_name is not None:
            error.validated_report["private_payloads_removed"] = not Path(work_name).exists()
            try:
                error.validated_report["windows_goldens_unchanged"] = FULL.windows_fingerprints(ROOT) == baseline
            except FULL.FullError:
                error.validated_report["windows_goldens_unchanged"] = None
        raise
    except Exception as error:
        original = error.__context__ if isinstance(error.__context__, SmokeError) else None
        private_removed = work_name is not None and not Path(work_name).exists()
        if full_suite and report is not None:
            report["private_payloads_removed"] = private_removed
        raise SmokeError(str(original) if original else "unexpected_host_failure",
                         security_uncertain=bootstrap, validated_report=report if full_suite else None,
                         cleanup_error="private_cleanup_unverified" if not private_removed else None) from None
    if full_suite:
        if Path(work_name).exists():
            raise SmokeError("private_cleanup_unverified", security_uncertain=True)
        report["private_payloads_removed"] = True
        if export_native_outputs:
            report["native_output_artifact_ready"] = False
            if retained_outputs is not None:
                try:
                    # Only bounded bytes survive in memory until private cleanup
                    # has completed. No directory is exposed before these gates.
                    files = FULL.output_artifact_files(retained_outputs, report, IMAGE)
                    FULL.export_output_artifact(ROOT, files)
                    report["native_output_artifact_sha256"] = {name: FULL.digest(data) for name, data in files.items()}
                    report["native_output_artifact_ready"] = True
                except FULL.FullError as error:
                    raise SmokeError(str(error), validated_report=report,
                                     cleanup_error=getattr(error, "cleanup_error", None)) from None
                finally:
                    retained_outputs.clear()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-image", action="store_true", required=True,
                        help="Explicitly execute the already approved, fixed custom image")
    parser.add_argument("--bootstrap-simple-epf", action="store_true",
                        help="Run internal user bootstrap and one fixed EPF after capabilities")
    parser.add_argument("--full-suite", action="store_true",
                        help="Run six approved native scenarios and compare privately on the host under UTC")
    parser.add_argument("--client-watchdog-check", action="store_true",
                        help="Require a controlled client stall to time out and clean up")
    parser.add_argument("--client-probe", action="store_true",
                        help="Also require fresh managed-form client-only execution proof")
    parser.add_argument("--export-native-outputs", action="store_true",
                        help="Explicitly retain six genuine outputs plus provenance at native-smoke/native-outputs")
    parser.add_argument("--native-target", choices=(FULL.WINDOWS_TARGET, FULL.LINUX_TARGET),
                        default=FULL.WINDOWS_TARGET, help="Explicit host interpreter native checkpoint, never auto-detected")
    parser.add_argument("--comparison-mode", choices=(FULL.BYTE_EXACT, FULL.MAP_MODE),
                        default=FULL.BYTE_EXACT, help="Raw-byte comparison or the reviewed, source-bound typed Map contract")
    parser.add_argument("--output", type=Path, default=Path("native-smoke-report.json"))
    args = parser.parse_args(argv)
    if args.client_watchdog_check and not args.client_probe:
        parser.error("--client-watchdog-check requires --client-probe and --full-suite")
    if args.client_probe and not args.full_suite:
        parser.error("--client-probe requires --full-suite")
    if args.export_native_outputs and not args.full_suite:
        parser.error("--export-native-outputs requires --full-suite")
    try:
        FULL.validate_comparison_options(args.native_target, args.comparison_mode)
    except FULL.FullError:
        parser.error("typed-map-order-v1 requires --native-target linux-8.3.27.1508")
    if not args.full_suite and (args.native_target != FULL.WINDOWS_TARGET or args.comparison_mode != FULL.BYTE_EXACT):
        parser.error("comparison options require --full-suite")
    report: dict[str, object] = {
        "schema": 1, "image": IMAGE, "platform": "linux/amd64", "purpose": "empty-infobase-capability-smoke",
        "runtime_version_verified": False, "native_tests_completed": False,
        "security_settings_changed": False, "windows_goldens_modified": False,
    }
    artifact_evidence_validated = False
    try:
        report["probe"] = run_smoke(Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())), bootstrap=args.bootstrap_simple_epf, full_suite=args.full_suite, export_native_outputs=args.export_native_outputs, native_target=args.native_target, comparison_mode=args.comparison_mode, client_probe=args.client_probe, watchdog_check=args.client_watchdog_check)
        if args.bootstrap_simple_epf or args.full_suite:
            report["purpose"] = "isolated-bootstrap-and-simple-epf"
            stage2 = report["probe"].get("stage2")
            report["runtime_version_verified"] = bool(stage2 and stage2["named_user_verified"]
                                                      and stage2["actual_version"] == EXPECTED_VERSION)
            report["simple_epf_completed"] = bool(stage2 and stage2["simple_epf_passed"])
            report["security_settings_changed"] = report["probe"].get("security_settings_changed", False)
        success = report["probe"]["status"] == "ok"
        if args.full_suite:
            probe = report["probe"]
            if probe["native_target"] != args.native_target or probe["comparison_mode"] != args.comparison_mode:
                raise FULL.FullError("comparison_configuration_invalid")
            if probe["comparison"]["status"] != "not_run":
                FULL.validate_comparison(probe["comparison"], probe["stage3"], args.native_target, args.comparison_mode)
                if args.comparison_mode == FULL.MAP_MODE:
                    FULL.validate_semantic_context(probe, IMAGE)
                artifact_evidence_validated = bool(probe["status"] == "ok" and all(
                    probe.get(key) is True for key in ("native_evidence_accepted", "native_transport_validated",
                        "native_cases_completed", "container_cleanup_verified", "private_payloads_removed",
                        "windows_goldens_unchanged")))
            report["purpose"] = ("isolated-six-scenario-client-watchdog-proof" if args.client_watchdog_check else
                                 "isolated-six-scenario-client-proof" if args.client_probe else
                                 "isolated-six-scenario-utc-comparison")
            report["native_tests_completed"] = report["probe"].get("native_tests_completed", False)
            report["interpreter_comparison_completed"] = report["probe"]["comparison"]["status"] == "ok"
            report["interpreter_acceptance_completed"] = report["probe"]["comparison"].get("acceptance_status") == "accepted"
            success = bool(success and report["interpreter_acceptance_completed"]
                           and artifact_evidence_validated)
    except (SmokeError, FULL.FullError) as error:
        report["error"] = str(error)
        if getattr(error, "validated_report", None) is not None:
            report["probe"] = error.validated_report
        if getattr(error, "cleanup_error", None) is not None:
            report["cleanup_error"] = error.cleanup_error
        if getattr(error, "security_uncertain", args.full_suite):
            report["security_settings_changed"] = None
        success = False
    except Exception:
        # Never emit traceback/exception text that could contain external output.
        report["error"] = "unexpected_host_failure"
        if args.bootstrap_simple_epf or args.full_suite:
            report["security_settings_changed"] = None
        success = False
    if args.full_suite:
        report["purpose"] = ("isolated-six-scenario-client-watchdog-proof" if args.client_watchdog_check else
                             "isolated-six-scenario-client-proof" if args.client_probe else
                             "isolated-six-scenario-utc-comparison")
        probe = report.get("probe", {})
        stage2 = probe.get("stage2")
        report["native_cases_completed"] = probe.get("native_cases_completed", False)
        report["native_tests_completed"] = (probe.get("native_tests_completed", False)
                                             if args.client_probe else report["native_cases_completed"])
        report["native_evidence_accepted"] = probe.get("native_evidence_accepted", False)
        report["windows_goldens_modified"] = (not probe["windows_goldens_unchanged"]
            if type(probe.get("windows_goldens_unchanged")) is bool else None)
        report["interpreter_comparison_completed"] = probe.get("comparison", {}).get("status") == "ok"
        report["native_target"] = args.native_target
        report["comparison_mode"] = args.comparison_mode
        report["interpreter_acceptance_completed"] = bool(success and probe.get("comparison", {}).get("acceptance_status") == "accepted")
        if stage2:
            report["runtime_version_verified"] = bool(stage2["named_user_verified"] and stage2["actual_version"] == EXPECTED_VERSION)
            report["simple_epf_completed"] = stage2["simple_epf_passed"]
            report["security_settings_changed"] = probe["security_settings_changed"]
    if args.full_suite and report.get("probe", {}).get("native_output_artifact_ready") is True and not artifact_evidence_validated:
        report["probe"]["native_output_artifact_ready"] = False
    report["smoke_completed"] = success
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_within_limit = len(rendered.encode("utf-8")) <= MAX_OUTPUT
    if not report_within_limit:
        rendered = json.dumps({"schema": 1, "error": "public_report_limit", "smoke_completed": False}) + "\n"
        success = False
    args.output.write_text(rendered, encoding="utf-8")
    if args.export_native_outputs and report_within_limit and report.get("probe", {}).get("native_output_artifact_ready") is True:
        try:
            FULL.verify_output_artifact(ROOT, report["probe"]["native_output_artifact_sha256"])
        except FULL.FullError as error:
            report["probe"]["native_output_artifact_ready"] = False
            report["error"] = str(error)
            report["smoke_completed"] = success = False
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            report_within_limit = len(rendered.encode("utf-8")) <= MAX_OUTPUT
            if not report_within_limit:
                rendered = json.dumps({"schema": 1, "error": "public_report_limit", "smoke_completed": False}) + "\n"
            args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.export_native_outputs and report_within_limit and report.get("probe", {}).get("native_output_artifact_ready") is True:
        # Raw mismatches remain visible; only the explicit typed contract can
        # accept eligible Map-order differences. Complete diagnostic captures
        # may still export on rejection. No stale-path test.
        output_file = os.environ.get("GITHUB_OUTPUT")
        if output_file:
            with open(output_file, "a", encoding="utf-8") as stream:
                stream.write("native_outputs_ready=true\n")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the explicitly approved image once; emit only a validated public report.

The image's stdout/stderr, environment, labels, database, binaries and native XML
are never published. No runtime package install or host-writable mount is used.
"""
from __future__ import annotations

import argparse
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
STATUS = {"ok", "python_missing", "python_unsupported", "capabilities_failed", "libraries_failed", "display_failed", "create_failed", "dump_failed", "format_failed"}
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


def container_command(probe: Path, name: str) -> list[str]:
    if probe.is_symlink():
        raise SmokeError("invalid_probe_path")
    probe = probe.resolve(strict=True)
    if not probe.is_file() or "," in str(probe):
        raise SmokeError("invalid_probe_path")
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
        "--mount", f"type=bind,src={probe},dst=/smoke/probe.sh,readonly",
        "--workdir", "/tmp", "--entrypoint", "/usr/bin/env", IMAGE,
        "-i", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/tmp/home", "XDG_RUNTIME_DIR=/tmp/runtime", "DISPLAY=:99",
        "LANG=ru_RU.UTF-8", "LC_ALL=ru_RU.UTF-8", "TZ=Etc/UTC",
        "/bin/bash", "--noprofile", "--norc", "/smoke/probe.sh",
    ]


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def validate_report(raw: bytes) -> dict[str, object]:
    try:
        if len(raw) > MAX_OUTPUT:
            raise ValueError("oversized")
        data = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
        if type(data) is not dict or type(data.get("schema")) is not int or data["schema"] != 1:
            raise ValueError("schema")
        if data in ({"schema": 1, "status": "python_missing"}, {"schema": 1, "status": "python_unsupported"}):
            return data
        expected = BOOL_KEYS | {"schema", "status", "python_version", "runtime_version",
                                "runtime_version_source", "configuration_format"}
        if set(data) != expected or data["status"] not in STATUS:
            raise ValueError("keys")
        if any(type(data[key]) is not bool for key in BOOL_KEYS):
            raise ValueError("boolean")
        if (data["runtime_version"] is not None or data["runtime_version_source"] != "not_measured"
                or data["security_settings_changed"] or data["native_tests_completed"]):
            raise ValueError("invalid claim")
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


def run_smoke(temp_root: Path) -> dict[str, object]:
    # Remove the secret from the process environment before any Docker operation.
    token = os.environ.pop("GHCR_TOKEN", "")
    actor = os.environ.pop("GHCR_USER", "")
    if not token or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", actor):
        raise SmokeError("registry_credentials_missing")
    name = "onec-smoke-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="onec-smoke-", dir=temp_root) as work:
        work = Path(work)
        auth = work / "registry-auth"
        auth.mkdir(mode=0o700)
        auth_env = docker_environment(auth)
        try:
            run_silent(["docker", "login", "ghcr.io", "--username", actor, "--password-stdin"], auth_env, 60, token.encode())
            token = ""
            run_silent(["docker", "pull", "--platform", "linux/amd64", IMAGE], auth_env, 600)
        finally:
            token = ""
            # No logout command is needed: config is isolated, and deleting all
            # files avoids contacting registries or invoking credential helpers.
            shutil.rmtree(auth)
        clean = work / "no-auth"
        clean.mkdir(mode=0o700)
        env = docker_environment(clean)
        code, platform = bounded_run(["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}", IMAGE], env, 30, 128)
        if code != 0 or platform.strip() != b"linux/amd64|0":
            raise SmokeError("unexpected_image_platform_or_volumes")
        try:
            code, raw = bounded_run(container_command(PROBE, name), env, MAX_RUNTIME)
            report = validate_report(raw)
            if code != 0 and report["status"] == "ok":
                raise SmokeError("inconsistent_container_exit")
            if not -64 <= code <= 255:
                raise SmokeError("unexpected_container_exit_code")
            report["container_exit_code"] = code  # Host-observed, never container-supplied.
            return report
        finally:
            # docker run timeout/interrupt does not necessarily stop its container.
            try:
                run_silent(["docker", "rm", "--force", name], env, 30)
            except SmokeError:
                # A failed cleanup must never be represented as a clean success.
                # The ephemeral hosted runner/job timeout remains the backstop.
                raise SmokeError("container_cleanup_unverified") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-image", action="store_true", required=True,
                        help="Explicitly execute the already approved, fixed custom image")
    parser.add_argument("--output", type=Path, default=Path("native-smoke-report.json"))
    args = parser.parse_args(argv)
    report: dict[str, object] = {
        "schema": 1, "image": IMAGE, "platform": "linux/amd64", "purpose": "empty-infobase-capability-smoke",
        "runtime_version_verified": False, "native_tests_completed": False,
        "security_settings_changed": False, "windows_goldens_modified": False,
    }
    try:
        report["probe"] = run_smoke(Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
        success = report["probe"]["status"] == "ok"
    except SmokeError as error:
        report["error"] = str(error)
        success = False
    except Exception:
        # Never emit traceback/exception text that could contain external output.
        report["error"] = "unexpected_host_failure"
        success = False
    report["smoke_completed"] = success
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

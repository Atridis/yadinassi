"""Private, bounded six-scenario capture validation and UTC host comparison.

Only finite metadata leaves this module. Native payloads live in an exclusive
host temporary directory, never in the repository or the public report.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time

SCENARIOS = ("collections", "dates", "functions", "numbers", "strings", "values")
SCHEMA = "native-1c-full-v1"
MAX_FILE = 1_048_576
MAX_TOTAL = 2_097_152
MAX_TRANSPORT = 3_145_728
MAX_REPORT = 32_768
MAX_STDERR = 65_536
CASE_SECONDS = 10
DEPENDENCIES = {"prompt-toolkit": "3.0.53", "pyuca": "1.2", "tzdata": "2026.5", "wcwidth": "0.8.2"}
FAILURES = {"none", "prerequisites_failed", "stale_evidence", "invalid_input",
            "invalid_result", "invalid_dump_result", "artifact_missing", "output_mismatch",
            "output_limit", "module_mismatch", "timeout", "process_failed", "unexpected_failure",
            "export_failed"}
CASE_KEYS = {"name", "status", "source_sha256", "module_sha256", "output_sha256",
             "output_size", "message_count"}
EXECUTE_SCRIPT = r'''
import sys
import importlib.util
from pathlib import Path
# Load only the verified package, not arbitrary modules beside the checkout.
package = Path(sys.argv[1]) / "yadinassi"
spec = importlib.util.spec_from_file_location("yadinassi", package / "__init__.py",
                                            submodule_search_locations=[str(package)])
module = importlib.util.module_from_spec(spec)
sys.modules["yadinassi"] = module
spec.loader.exec_module(module)
Interpreter = module.Interpreter

def emit(message):
    message = message.replace("\r\n", "\n").replace("\r", "\n")
    sys.stdout.buffer.write((message + "\n").encode("utf-8"))

source = Path(sys.argv[2])
Interpreter(output=emit).execute(source.read_text(encoding="utf-8-sig"), str(source))
'''


class FullError(Exception):
    """Fixed error codes only; never include source/native/exception text."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def is_int(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("constant")


def strict_json(raw: bytes, limit: int):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ValueError("size")
    # UTF-8 (not JSON's permissive UTF-16 autodetection), no BOM or surrogates.
    text = raw.decode("utf-8")
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 12:
                raise ValueError("depth")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("depth")
    result = json.loads(text, object_pairs_hook=unique_pairs, parse_constant=reject_constant,
                        parse_int=lambda value: int(value) if len(value) <= 10 else reject_constant(value))
    def bounded(value, depth=0):
        if depth > 12:
            raise ValueError("depth")
        if type(value) is dict:
            if len(value) > 128:
                raise ValueError("members")
            for key, item in value.items():
                key.encode("utf-8")
                bounded(item, depth + 1)
        elif type(value) is list:
            if len(value) > 128:
                raise ValueError("items")
            for item in value:
                bounded(item, depth + 1)
        elif type(value) is str:
            value.encode("utf-8")
        elif value is not None and type(value) not in (int, bool):
            raise ValueError("scalar")
    bounded(result)
    return result


def _open_private(path: Path) -> int:
    # Descriptor-relative traversal prevents parent-directory symlink races.
    path = path.absolute()
    if os.open in os.supports_dir_fd:
        directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in path.parts[1:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                os.close(directory)
                directory = child
            return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                           dir_fd=directory)
        finally:
            os.close(directory)
    # Offline Windows validation only; the execution workflow is Linux-only.
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("link")
    return os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))


def read_regular(path: Path, limit: int, *, nonempty=False) -> bytes:
    """No links/special files; bound bytes and check stable opened descriptor."""
    try:
        fd = _open_private(path)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError("file")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
                                   s.st_mtime_ns, s.st_ctime_ns)
            if (signature(before) != signature(after) or signature(after) != signature(path.lstat())
                    or len(data) != before.st_size or len(data) > limit or (nonempty and not data)):
                raise ValueError("unstable")
            return data
    except (OSError, ValueError):
        raise FullError("invalid_private_file") from None


def generated_module(source: bytes) -> bytes:
    return source.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8-sig")


def validate_stage3(data, nonce: str, input_hashes: dict, module_hashes: dict, *, prerequisites: bool):
    if type(data) is not dict or set(data) != {"schema", "nonce", "status", "failure_kind", "failed_case", "input_sha256", "cases"}:
        raise ValueError("stage3 keys")
    if type(data["schema"]) is not int or data["schema"] != 1 or data["nonce"] != nonce:
        raise ValueError("stage3 identity")
    status = data["status"]
    if status not in {"not_started", "failed", "ok"} or data["failure_kind"] not in FAILURES:
        raise ValueError("stage3 status")
    if type(data["input_sha256"]) is not dict:
        raise ValueError("inputs")
    if data["input_sha256"] != input_hashes and not (status != "ok" and data["input_sha256"] == {}):
        raise ValueError("inputs")
    cases = data["cases"]
    if type(cases) is not list or len(cases) != len(SCENARIOS):
        raise ValueError("cases")
    seen_incomplete = False
    failed = []
    for name, case in zip(SCENARIOS, cases):
        if type(case) is not dict or set(case) != CASE_KEYS or case["name"] != name:
            raise ValueError("case keys")
        if case["status"] not in {"not_started", "failed", "ok"}:
            raise ValueError("case status")
        if seen_incomplete and case["status"] != "not_started":
            raise ValueError("case order")
        seen_incomplete |= case["status"] != "ok"
        source_hash = input_hashes[f"integrational_tests/tests/{name}.bsl"]
        if case["status"] == "ok":
            if (case["source_sha256"] != source_hash or case["module_sha256"] != module_hashes[name]
                    or not is_digest(case["output_sha256"]) or not is_int(case["output_size"], MAX_FILE)
                    or not is_int(case["message_count"], 32_768)):
                raise ValueError("case evidence")
        elif case["status"] == "not_started":
            if any(case[key] is not None for key in CASE_KEYS - {"name", "status"}):
                raise ValueError("unreached evidence")
        else:
            failed.append(name)
            if (case["source_sha256"] not in (None, source_hash)
                    or case["module_sha256"] not in (None, module_hashes[name])
                    or any(case[key] is not None for key in ("output_sha256", "output_size", "message_count"))):
                raise ValueError("failed evidence")
    if sum(case["output_size"] or 0 for case in cases) > MAX_TOTAL:
        raise ValueError("aggregate")
    if data["input_sha256"] != input_hashes and any(case["status"] != "not_started" for case in cases):
        raise ValueError("inputs not established")
    if status == "ok":
        if (not prerequisites or seen_incomplete or data["failure_kind"] != "none" or data["failed_case"] is not None):
            raise ValueError("success")
    elif status == "not_started":
        if (prerequisites or any(case["status"] != "not_started" for case in cases)
                or data["failure_kind"] != "prerequisites_failed" or data["failed_case"] is not None):
            raise ValueError("not started")
    elif (not prerequisites or data["failure_kind"] in {"none", "prerequisites_failed"}
            or (failed and data["failed_case"] != failed[0])
            or (not failed and data["failed_case"] is not None)):
        raise ValueError("failed")
    return data


def validate_envelope(raw: bytes, nonce: str, input_hashes: dict, module_hashes: dict, report_validator):
    """Return validated report and exact bytes, never the unchecked envelope."""
    try:
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            raise ValueError("nonce")
        data = strict_json(raw, MAX_TRANSPORT)
        if (type(data) is not dict or set(data) != {"schema", "nonce", "report", "outputs"}
                or data["schema"] != SCHEMA or data["nonce"] != nonce):
            raise ValueError("envelope")
        report_raw = json.dumps(data["report"], separators=(",", ":"), ensure_ascii=True).encode()
        if len(report_raw) > MAX_REPORT:
            raise ValueError("report limit")
        report = report_validator(report_raw, bootstrap=True, full_suite=True)
        prerequisites = bool(report.get("stage2") and report["stage2"]["status"] == "ok")
        stage3 = validate_stage3(report["stage3"], nonce, input_hashes, module_hashes,
                                 prerequisites=prerequisites)
        if report["native_tests_completed"] is not (stage3["status"] == "ok"):
            raise ValueError("completion")
        if (report["status"] == "ok") is not (stage3["status"] == "ok"):
            raise ValueError("success")
        if prerequisites and stage3["status"] != "ok" and report["status"] != "stage3_failed":
            raise ValueError("status")
        outputs = data["outputs"]
        if type(outputs) is not list:
            raise ValueError("outputs")
        if stage3["status"] != "ok":
            if outputs:
                raise ValueError("failed payload")
            return report, {}
        if len(outputs) != len(SCENARIOS):
            raise ValueError("coverage")
        result = {}
        total = 0
        for name, case, entry in zip(SCENARIOS, stage3["cases"], outputs):
            if (type(entry) is not dict or set(entry) != {"name", "size", "sha256", "data_b64"}
                    or entry["name"] != name + ".out" or not is_int(entry["size"], MAX_FILE)
                    or not is_digest(entry["sha256"]) or type(entry["data_b64"]) is not str):
                raise ValueError("entry")
            if len(entry["data_b64"]) > 4 * ((MAX_FILE + 2) // 3):
                raise ValueError("base64 limit")
            payload = base64.b64decode(entry["data_b64"], validate=True)
            if base64.b64encode(payload).decode("ascii") != entry["data_b64"]:
                raise ValueError("base64 canonical")
            total += len(payload)
            if (len(payload) != entry["size"] or digest(payload) != entry["sha256"]
                    or entry["size"] != case["output_size"] or entry["sha256"] != case["output_sha256"]
                    or total > MAX_TOTAL):
                raise ValueError("payload evidence")
            result[name] = payload
        return report, result
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, binascii.Error):
        raise FullError("invalid_full_envelope") from None


def quarantine_outputs(parent: Path, payloads: dict[str, bytes]) -> Path:
    """Exclusive host-chosen directory; caller must remove it on every outcome."""
    if list(payloads) != list(SCENARIOS) or any(type(b) is not bytes or len(b) > MAX_FILE for b in payloads.values()) or sum(map(len, payloads.values())) > MAX_TOTAL:
        raise FullError("invalid_private_payloads")
    if parent.is_symlink() or not parent.is_dir():
        raise FullError("invalid_private_directory")
    target = parent / "native-capture"
    try:
        target.mkdir(mode=0o700)
        for name in SCENARIOS:
            fd = os.open(target / (name + ".out"), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payloads[name])
                stream.flush()
                os.fsync(stream.fileno())
            (target / (name + ".out")).chmod(0o400)
        for name in SCENARIOS:
            if read_regular(target / (name + ".out"), MAX_FILE) != payloads[name]:
                raise FullError("private_capture_failed")
        return target
    except OSError:
        raise FullError("private_capture_failed") from None


def child_environment() -> dict[str, str]:
    # No credentials, PYTHONPATH/PYTHONSTARTUP, locale or timezone inherited.
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "Etc/UTC",
            "YADINASSI_TIMEZONE": "Etc/UTC", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def bounded_child(args: list[str], cwd: Path, *, seconds=CASE_SECONDS,
                  stdout_limit=MAX_FILE, stderr_limit=MAX_STDERR):
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + seconds
    try:
        with subprocess.Popen(args, cwd=cwd, env=child_environment(), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True) as process:
            try:
                with selectors.DefaultSelector() as selector:
                    for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                        selector.register(stream, selectors.EVENT_READ, name)
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise FullError("interpreter_timeout")
                        for key, _ in selector.select(min(remaining, 0.1)):
                            chunk = os.read(key.fileobj.fileno(), 4096)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            buffers[key.data].extend(chunk)
                            limit = stdout_limit if key.data == "stdout" else stderr_limit
                            if len(buffers[key.data]) > limit:
                                raise FullError("interpreter_output_limit")
                    code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                return code, bytes(buffers["stdout"]), bytes(buffers["stderr"])
            finally:
                # Reap the direct child and kill any descendants, including one
                # that outlives a successful process after closing its pipes.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    except subprocess.TimeoutExpired:
        raise FullError("interpreter_timeout") from None
    except OSError:
        raise FullError("interpreter_unavailable") from None


def mismatch_metadata(expected: bytes, actual: bytes) -> dict:
    shared = min(len(expected), len(actual))
    differing = sum(a != b for a, b in zip(expected, actual)) + abs(len(expected) - len(actual))
    first = next((i for i in range(shared) if expected[i] != actual[i]), shared)
    return {"different_byte_positions": differing, "first_mismatch_byte": first,
            "first_mismatch_native_line": expected[:first].count(b"\n") + 1,
            "native_line_count": expected.count(b"\n"), "interpreter_line_count": actual.count(b"\n")}


def compare_outputs(root: Path, capture: Path, stage3: dict, input_hashes: dict, *, runner=bounded_child) -> dict:
    if (stage3.get("status") != "ok" or len(stage3.get("cases", [])) != len(SCENARIOS)
            or [case.get("name") for case in stage3["cases"]] != list(SCENARIOS)
            or any(case.get("status") != "ok" for case in stage3["cases"])):
        raise FullError("comparison_coverage_invalid")
    records = []
    for name, case in zip(SCENARIOS, stage3["cases"]):
        record = {"name": name, "status": "error", "failure_kind": "none",
                  "native_size": case["output_size"], "native_sha256": case["output_sha256"],
                  "interpreter_size": None, "interpreter_sha256": None, "mismatch": None}
        try:
            source = root / f"integrational_tests/tests/{name}.bsl"
            if digest(read_regular(source, MAX_FILE, nonempty=True)) != input_hashes[f"integrational_tests/tests/{name}.bsl"]:
                raise FullError("source_changed")
            expected = read_regular(capture / (name + ".out"), MAX_FILE)
            if digest(expected) != case["output_sha256"] or len(expected) != case["output_size"]:
                raise FullError("native_capture_changed")
            # An ignored stale/tampered repository __pycache__ is not source
            # provenance. Use a new empty private cache prefix and never write it.
            with tempfile.TemporaryDirectory(prefix="interpreter-cache-", dir=capture.parent) as cache:
                code, actual, stderr = runner([sys.executable, "-I", "-B", "-X", "pycache_prefix=" + cache,
                                              "-c", EXECUTE_SCRIPT, str(root), str(source)], root)
            if code != 0 or stderr:
                raise FullError("interpreter_failed")
            record.update(interpreter_size=len(actual), interpreter_sha256=digest(actual))
            record["status"] = "matched" if actual == expected else "mismatched"
            if actual != expected:
                record["mismatch"] = mismatch_metadata(expected, actual)
        except FullError as error:
            record["failure_kind"] = str(error)
            record["status"] = "timeout" if str(error) == "interpreter_timeout" else "error"
        records.append(record)
    return {"schema": 1, "configured_timezone": "Etc/UTC", "configured_locale": "C.UTF-8",
            "status": "ok" if all(case["status"] == "matched" for case in records) else "failed", "cases": records}


def windows_fingerprints(root: Path) -> dict[str, str]:
    names = [f"integrational_tests/output/{name}.out" for name in SCENARIOS] + ["integrational_tests/meta.md"]
    return {name: digest(read_regular(root / name, MAX_FILE, nonempty=True)) for name in names}


def repository_provenance(root: Path) -> dict:
    def git(*args):
        code, stdout, stderr = bounded_child(["git", "-C", str(root), *args], root,
                                             stdout_limit=8192, stderr_limit=8192)
        if code != 0 or stderr:
            raise FullError("repository_identity_unverified")
        return stdout.decode("ascii").strip()
    commit = git("rev-parse", "HEAD^{commit}")
    tree = git("rev-parse", "HEAD^{tree}")
    if (not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{40}", tree)
            or git("status", "--porcelain", "--untracked-files=all")):
        raise FullError("repository_identity_unverified")
    tracked = set(git("ls-files", "--", "yadinassi").splitlines())
    actual = {path.relative_to(root).as_posix() for path in (root / "yadinassi").rglob("*")
              if not path.is_dir() and "__pycache__" not in path.parts}
    if not tracked or actual != tracked:
        raise FullError("repository_sources_unverified")
    expected = os.environ.get("GITHUB_SHA")
    if expected is not None and expected != commit:
        raise FullError("repository_commit_mismatch")
    result = {"commit": commit, "tree": tree}
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = os.environ.get(key)
        if value is not None:
            if not re.fullmatch(r"[0-9]{1,20}", value):
                raise FullError("workflow_identity_invalid")
            result[key.lower()] = value
    return result


def interpreter_provenance(root: Path) -> dict:
    files = sorted([path for path in (root / "yadinassi").rglob("*")
                    if not path.is_dir() and "__pycache__" not in path.parts])
    if any(path.suffix not in {".py", ".txt"} for path in files):
        raise FullError("unexpected_interpreter_source")
    files += [root / "pyproject.toml", root / "scripts/native_1c_full_host.py", root / "scripts/native_1c_smoke.py"]
    if not files or len(files) > 512:
        raise FullError("interpreter_provenance_invalid")
    hashes = {path.relative_to(root).as_posix(): digest(read_regular(path, 4 * MAX_FILE, nonempty=True)) for path in files}
    dependencies = {}
    for package, expected_version in DEPENDENCIES.items():
        try:
            value = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            raise FullError("interpreter_dependency_missing") from None
        if value != expected_version:
            raise FullError("interpreter_dependency_invalid")
        dependencies[package] = value
    return {"python_version": ".".join(map(str, sys.version_info[:3])),
            "dependencies": dependencies, "source_file_count": len(hashes),
            "source_sha256": digest(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()),
            "comparison_driver_sha256": hashes["scripts/native_1c_full_host.py"]}

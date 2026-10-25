"""Private, bounded six-scenario capture validation and UTC host comparison.

By default only finite metadata leaves this module. An explicit opt-in may retain
exactly six validated native outputs and bounded provenance after all cleanup gates.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.metadata
import importlib.util
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
import types
import uuid

SCENARIOS = ("collections", "dates", "functions", "numbers", "strings", "values")
SCHEMA = "native-1c-full-v1"
MAX_FILE = 1_048_576
MAX_TOTAL = 2_097_152
MAX_TRANSPORT = 3_145_728
MAX_REPORT = 32_768
MAX_STDERR = 65_536
ARTIFACT_DIRECTORY = "native-smoke/native-outputs"
ARTIFACT_FILES = tuple(name + ".out" for name in SCENARIOS) + ("provenance.json",)
WINDOWS_TARGET = "windows-8.3.27.2342"
LINUX_TARGET = "linux-8.3.27.1508"
BYTE_EXACT = "byte_exact"
MAP_MODE = "typed-map-order-v1"
APPROVED_IMAGE = "ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728"
COLLECTIONS_SOURCE_SHA256 = "b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27"
CASE_SECONDS = 10
DEPENDENCIES = {"prompt-toolkit": "3.0.53", "pyuca": "1.2", "tzdata": "2026.5", "wcwidth": "0.8.2"}
FAILURES = {"none", "prerequisites_failed", "stale_evidence", "invalid_input",
            "invalid_result", "invalid_dump_result", "artifact_missing", "output_mismatch",
            "output_limit", "module_mismatch", "timeout", "process_failed", "unexpected_failure",
            "export_failed"}
CASE_KEYS = {"name", "status", "source_sha256", "module_sha256", "output_sha256",
             "output_size", "message_count"}
POST_CREATE_DIRECTIVE = "// NativePostCreate: ExportProbeAfterCreate"
POST_CREATE_FAILURE = "interpreter_post_create_failed"
# Labels, not values: a completed callback must retain every guarded observation.
POST_CREATE_LABELS = tuple("export-variable.post-create." + label for label in (
    "object-context", "initial-undefined", "read", "write-routine-read",
    "routine-write-read", "private-list-entry", "private-write", "second-export-entry",
    "undeclared-read", "undeclared-write", "local-shadow", "reference-alias",
    "value-parameter", "reference-after-error", "collection-shared", "receiver-identity",
    "self-read", "self-write"))
EXECUTE_SCRIPT = r'''
import sys
import re
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

POST_CREATE_DIRECTIVE = "// NativePostCreate: ExportProbeAfterCreate"


def post_create_requested(source: str) -> bool:
    """A visible fixed test-driver action, never an executable routine name."""
    lines = source.removeprefix("\ufeff").splitlines()
    directives = [(index, line) for index, line in enumerate(lines)
                  if re.match(r"\s*//\s*NativePostCreate", line)]
    if not directives:
        return False
    if directives != [(0, POST_CREATE_DIRECTIVE)]:
        raise ValueError("Invalid NativePostCreate directive")
    return True


source = Path(sys.argv[2])
source_text = source.read_text(encoding="utf-8-sig")
post_create = post_create_requested(source_text)
options = {"native_target": sys.argv[3]} if len(sys.argv) > 3 else {}
interpreter = Interpreter(output=emit, **options)
interpreter.execute(source_text, str(source))
if post_create:
    emit("export-phase.post-create: [begin]")
    try:
        interpreter.execute("ThisObject.ExportProbeAfterCreate(ThisObject);", "<post-create>")
    except module.BSLError as error:
        description = error.message
        kind = "other"
        if "Метод объекта не обнаружен" in description:
            kind = "method-missing"
        named = '{"B",1}' if "exportprobeaftercreate" in description.lower() else '{"B",0}'
        emit("export-phase.post-create: [error;kind=" + kind + ";named=" + named + "]")
        sys.exit(3)  # An unavailable entrypoint must never yield a green comparison.
    else:
        emit("export-phase.post-create: [ok]")
'''


class FullError(Exception):
    """Fixed error codes only; never include source/native/exception text."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def is_int(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def post_create_requested(source: str) -> bool:
    """Use exactly the launcher's fail-closed canonical directive grammar."""
    lines = source.removeprefix("\ufeff").splitlines()
    directives = [(index, line) for index, line in enumerate(lines)
                  if re.match(r"\s*//\s*NativePostCreate", line)]
    if not directives:
        return False
    if directives != [(0, POST_CREATE_DIRECTIVE)]:
        raise ValueError("Invalid NativePostCreate directive")
    return True


def post_create_phase(payload: bytes) -> tuple[bool, list[bytes]]:
    """Validate bounded, exact full-line framing without interpreting probe values."""
    if type(payload) is not bytes or len(payload) > MAX_FILE or not payload.endswith(b"\n"):
        raise ValueError("post-create framing")
    lines = [line.removesuffix(b"\r") for line in payload[:-1].split(b"\n")]
    if any(b"\r" in line for line in lines):
        raise ValueError("post-create line ending")
    markers = [(index, line) for index, line in enumerate(lines)
               if b"export-phase.post-create" in line]
    if (len(markers) != 2 or markers[0][1] != b"export-phase.post-create: [begin]"
            or markers[1][0] != len(lines) - 1):
        raise ValueError("post-create phase")
    final = markers[1][1]
    completed = final == b"export-phase.post-create: [ok]"
    if not completed and re.fullmatch(
            rb'export-phase\.post-create: \[error;kind=(?:other|method-missing);named=\{"B",[01]\}\]',
            final) is None:
        raise ValueError("post-create result")
    return completed, lines[markers[0][0] + 1:markers[1][0]]


def interpreter_post_create_failed(source: bytes, code: int, actual: bytes, stderr: bytes) -> bool:
    """Only the verified directive plus the driver's finite failure may be retained."""
    if code != 3 or stderr != b"":
        return False
    try:
        if not post_create_requested(source.decode("utf-8-sig")):
            return False
        completed, _ = post_create_phase(actual)
        return not completed
    except (ValueError, UnicodeError):
        return False


def validate_native_post_create(payload: bytes) -> None:
    completed, rows = post_create_phase(payload)
    all_probe_rows = [line.removesuffix(b"\r") for line in payload[:-1].split(b"\n")
                      if b"export-variable.post-create" in line]
    if all_probe_rows != rows:
        raise ValueError("post-create probe placement")
    if completed:
        if (any(b": " not in row for row in rows)
                or [row.partition(b": ")[0] for row in rows] != [label.encode("ascii") for label in POST_CREATE_LABELS]):
            raise ValueError("post-create probe inventory")
    elif rows:
        # The fixed callback guards each probe. An entrypoint failure has no rows;
        # partial callbacks are not a complete native observation set.
        raise ValueError("post-create incomplete callback")


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


CLIENT_SOURCE = "scripts/native_1c_bootstrap/client_probe.bsl"
# Exact finite witness contract, independently executed by the host interpreter.
CLIENT_VALUES = [
    42,
    'client-probe',
    3,
    6,
    'directive.call.add: {"N",42}',
    'directive.preprocessor.server: server',
    'directive.preprocessor.client: client',
    'directive.call.nested: server',
    'directive.param.val: {"N",7}',
    'directive.exception: {"B",1}',
    'directive.return.number: {"N",42}',
    'directive.return.string: {"S","x"}',
    'directive.return.boolean: {"B",1}',
    'directive.return.undefined: {"U"}',
    'directive.call.recovery: {"N",42}',
]
# Audited pinned native scalar-copyback capture, not interpreter-generated data.
CLIENT_VALUES += ['copyback.core.v1', '{"B",1}', '{"B",0}', '{"N",43}', '{"B",0}', '{"N",1}', '{"B",0}', '{"N",97}', '{"N",43}', '{"B",0}', '{"B",1}', '{"N",47}', '{"B",1}', '{"B",1}', '{"N",1}', '{"N",2}', '{"N",3}', '{"B",0}', '{"N",1}', '{"N",1}', '{"B",0}', '{"N",52}', '{"B",0}', '{"N",1}', '{"B",0}', '{"N",1}', '{"B",0}', '{"N",1}', '{"B",0}', '{"N",192}', '{"N",9}', '{"N",2}', '{"B",0}', '{"N",43}', '{"B",1}']

# Audited pinned object capture, including named/expression timing; not local expected generation.
CLIENT_VALUES += ['object.transfer.v1'] + [True, False, 1, 1, 1, False, 2, 21, 23, 23, 2, False, 3, 3, 3, False, 41, 42, 4, False, 5, 51, 51, 51, 51, 52, 51, 5, True, True, False, 6, 6, 6, False, 7, 8, False, 73, 73, 73, 72, 1, False, True, 82, 10, True, False, 73, 72, 72, 74, 11, 73, 74, 72, 1]

# Native run39974330047: exact side-local module context observations.
CLIENT_VALUES += ['module.context.v1'] + [10, 100, 111, True, 100, True, 100, True, 11]
# Logical-context projection of audited profile mask19; new exact source needs native validation.
CLIENT_VALUES += ['nocontext.core.v3'] + [12, 22, 0, 12, 2, True, 16, True, 6, 14, 14, True, 7, 18]

# One exact dense witness, projected from the audited nine-slot native capture.
CLIENT_VALUES += ['dual.v1:000032017000017041000032017']

# Audited native checkpoint40078699477; exact eight Date/Null observations.
CLIENT_VALUES += ['dn.v1:22222277']
# Historical 136 values remain unchanged for legacy adapters and their proofs.
# Current source-bound admission executes and requires all 137 values.
CLIENT_RUNTIME_VALUES = CLIENT_VALUES + ['ibc.v1:121122221122021122021122021122']


CLIENT_FLAGS = {"entered", "completed", "process_exited", "quiet", "witness_verified"}
CLIENT_HASHES = {"source_sha256", "module_sha256", "roundtrip_sha256"}



CLIENT_MODULE_TEMPLATE_SHA256 = 'a3e4fd9b809013b1d704a6a7af5b77353e04a129f3a0cd0ca3a40692458c1e17'
CLIENT_MODULE_SHARED_SHA256 = '6e29d85372e623c412e0662ad7514fbc76963fb5bd42bde6a100a4b5c7a2b120'
CLIENT_MODULE_PREFIX = b'// BEGIN bounded module context declarations\n&AtClient\nVar ContextClientCounter;\n&AtServer\nVar ContextServerCounter;\n&AtServer\nVar ContextServerUninitialized;\n\n// END bounded module context declarations\n'
CLIENT_MODULE_SUFFIX = b'\n// BEGIN bounded module context measurement\n&AtServer\nFunction ContextModuleNested()\n    ContextServerCounter = ContextServerCounter + 1;\n    Return ContextServerCounter;\nEndFunction\n\n&AtServer\nFunction ContextModuleCall(Val Escape)\n    Var Initial, Nested, WasUndefined;\n    Initial = ContextServerCounter;\n    WasUndefined = ContextServerUninitialized = Undefined;\n    ContextServerCounter = ContextServerCounter + 10;\n    ContextServerUninitialized = 7;\n    Nested = ContextModuleNested();\n    If Escape Then\n        Raise "module-context-controlled-failure";\n    EndIf;\n    Return New Structure("Initial,Nested,WasUndefined", Initial, Nested, WasUndefined);\nEndFunction\n\n&AtClient\nProcedure ContextModuleRecord(Records, Val Label, Val Value)\n    If Value = Undefined Then\n        Records.Add("U");\n    Else\n        Records.Add(Value);\n    EndIf;\nEndProcedure\n\n&AtClient\nFunction RunModuleContextProbe()\n    Var Records, First, Second, Third, Failed, Matched;\n    Records = New Array;\n    Records.Add("module.context.v1");\n    ContextModuleRecord(Records, "client.initial", ContextClientCounter);\n    ContextClientCounter = ContextClientCounter + 1;\n    First = ContextModuleCall(False);\n    ContextModuleRecord(Records, "server.initial", First.Initial);\n    ContextModuleRecord(Records, "server.nested", First.Nested);\n    ContextModuleRecord(Records, "server.undefined", First.WasUndefined);\n    Second = ContextModuleCall(False);\n    ContextModuleRecord(Records, "server.repeated.initial", Second.Initial);\n    Failed = False;\n    Matched = False;\n    Try\n        ContextModuleCall(True);\n    Except\n        Failed = True;\n        Matched = Find(ErrorDescription(), "module-context-controlled-failure") > 0;\n    EndTry;\n    Third = ContextModuleCall(False);\n    ContextModuleRecord(Records, "escaped.caught", Failed And Matched);\n    ContextModuleRecord(Records, "server.recovery.initial", Third.Initial);\n    ContextModuleRecord(Records, "server.recovery.undefined", Third.WasUndefined);\n    ContextModuleRecord(Records, "client.retained", ContextClientCounter);\n    Return Records;\nEndFunction\n\n&AtClient\nProcedure ContextModuleAppend(RecordsOut)\n    Var ModuleContextValue;\n    For Each ModuleContextValue In RunModuleContextProbe() Do\n        RecordsOut.Add(ModuleContextValue);\n    EndDo;\nEndProcedure\n\n// Initialization runs in its explicitly compiled side only. Do not infer that\n// arbitrary unguarded standalone root statements should run on the server.\n#If AtClient Then\nContextClientCounter = 10;\n#EndIf\n#If AtServer Then\nContextServerCounter = 100;\n#EndIf\n'
CLIENT_MODULE_CALL = b'    ContextModuleAppend(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f);\n'


def module_context_shared_source(raw: bytes) -> bytes:
    """Exact measured prefix/call/suffix inverse, not generic source stripping."""
    if (digest(raw) != CLIENT_MODULE_TEMPLATE_SHA256
            or not raw.startswith(CLIENT_MODULE_PREFIX)
            or not raw.endswith(CLIENT_MODULE_SUFFIX)
            or raw.count(CLIENT_MODULE_CALL) != 1):
        raise FullError('source_changed')
    restored = raw[len(CLIENT_MODULE_PREFIX):-len(CLIENT_MODULE_SUFFIX)].replace(
        CLIENT_MODULE_CALL, b'', 1)
    if digest(restored) != CLIENT_MODULE_SHARED_SHA256:
        raise FullError('source_changed')
    return restored



CLIENT_NOCONTEXT_TEMPLATE_SHA256 = 'b79c23abb756c3b3965e3a46ad7212e582db917ff319facc70a1efb18a470e14'
CLIENT_NOCONTEXT_SHARED_SHA256 = 'a3e4fd9b809013b1d704a6a7af5b77353e04a129f3a0cd0ca3a40692458c1e17'
CLIENT_NOCONTEXT_BLOCK = b'\n// BEGIN bounded no-context witness\n&AtServerNoContext\nFunction NoContextLeaf(Value)\n    Value = Value + 1;\n    Return Value;\nEndFunction\n\n&AtServerNoContext\nFunction NoContextOperation(Value, Val PrivateValue, Val Mode)\n    Var Initial, Nested, ProfileMask, Caught;\n    Initial = Value;\n    Value = Value + 10;\n    PrivateValue = PrivateValue + 20;\n    Nested = NoContextLeaf(Value);\n    ProfileMask = 0;\n#If AtClient Then\n    ProfileMask = ProfileMask + 1;\n#EndIf\n#If AtServer Then\n    ProfileMask = ProfileMask + 2;\n#EndIf\n    Caught = False;\n    If Mode = 1 Then\n        Try\n            Raise "nocontext-controlled-failure";\n        Except\n            Caught = Find(ErrorDescription(), "nocontext-controlled-failure") > 0;\n        EndTry;\n    EndIf;\n    If Mode = 2 Then\n        Raise "nocontext-controlled-failure";\n    EndIf;\n    Return New Structure("Initial,Nested,PrivateValue,ProfileMask,Caught", Initial, Nested, PrivateValue, ProfileMask, Caught);\nEndFunction\n\n&AtServer\nFunction NoContextFromContext(Val Escape)\n    Var LocalValue, PrivateValue, Result, Failed, Matched;\n    LocalValue = 3;\n    PrivateValue = 4;\n    Failed = False;\n    Matched = False;\n    Result = Undefined;\n    Try\n        If Escape Then\n            Result = NoContextOperation(LocalValue, PrivateValue, 2);\n        Else\n            Result = NoContextOperation(LocalValue, PrivateValue, 0);\n        EndIf;\n    Except\n        Failed = True;\n        Matched = Find(ErrorDescription(), "nocontext-controlled-failure") > 0;\n    EndTry;\n    Return New Structure("Value,PrivateValue,Failed,Matched,Result", LocalValue, PrivateValue, Failed, Matched, Result);\nEndFunction\n\n&AtClient\nProcedure NoContextRecord(Records, Val Label, Val Value)\n    If Value = Undefined Then\n        Records.Add("U");\n    Else\n        Records.Add(Value);\n    EndIf;\nEndProcedure\n\n&AtClient\nFunction RunNoContextProbe()\n    Var Records, Value, PrivateValue, Result, Failed, Matched, Nested;\n    Records = New Array;\n    Records.Add("nocontext.core.v3");\n    Value = 1;\n    PrivateValue = 2;\n    Result = NoContextOperation(Value, PrivateValue, 0);\n    NoContextRecord(Records, "normal.nested", Result.Nested);\n    NoContextRecord(Records, "normal.private", Result.PrivateValue);\n    NoContextRecord(Records, "normal.profile", Result.ProfileMask);\n    NoContextRecord(Records, "normal.caller", Value);\n    NoContextRecord(Records, "normal.val.caller", PrivateValue);\n    Value = 5;\n    Result = NoContextOperation(Value, PrivateValue, 1);\n    NoContextRecord(Records, "caught.matched", Result.Caught);\n    NoContextRecord(Records, "caught.caller", Value);\n    Value = 6;\n    Failed = False;\n    Matched = False;\n    Try\n        NoContextOperation(Value, PrivateValue, 2);\n    Except\n        Failed = True;\n        Matched = Find(ErrorDescription(), "nocontext-controlled-failure") > 0;\n    EndTry;\n    NoContextRecord(Records, "escape.caught", Failed And Matched);\n    NoContextRecord(Records, "escape.caller", Value);\n    Nested = NoContextFromContext(False);\n    NoContextRecord(Records, "context.normal.value", Nested.Value);\n    Nested = NoContextFromContext(True);\n    NoContextRecord(Records, "context.escape.value", Nested.Value);\n    NoContextRecord(Records, "context.escape.caught", Nested.Failed And Nested.Matched);\n    Value = 7;\n    Result = NoContextOperation(Value, PrivateValue, 0);\n    NoContextRecord(Records, "recovery.initial", Result.Initial);\n    NoContextRecord(Records, "recovery.caller", Value);\n    Return Records;\nEndFunction\n\n&AtClient\nProcedure NoContextAppend(RecordsOut)\n    Var NoContextValue;\n    For Each NoContextValue In RunNoContextProbe() Do\n        RecordsOut.Add(NoContextValue);\n    EndDo;\nEndProcedure\n'
CLIENT_NOCONTEXT_INITIALIZER = b'// Initialization runs in its explicitly compiled side only. Do not infer that\n// arbitrary unguarded standalone root statements should run on the server.\n#If AtClient Then\nContextClientCounter = 10;\n#EndIf\n#If AtServer Then\nContextServerCounter = 100;\n#EndIf\n'
CLIENT_NOCONTEXT_CALL = b'    NoContextAppend(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f);\n'


def nocontext_shared_source(raw: bytes) -> bytes:
    """Exact pre-initializer witness/call inverse for legacy adapters only."""
    tail = CLIENT_NOCONTEXT_BLOCK + CLIENT_NOCONTEXT_INITIALIZER
    if (digest(raw) != CLIENT_NOCONTEXT_TEMPLATE_SHA256
            or not raw.endswith(tail)
            or raw.count(CLIENT_NOCONTEXT_CALL) != 1):
        raise FullError('source_changed')
    restored = (raw[:-len(tail)] + CLIENT_NOCONTEXT_INITIALIZER).replace(
        CLIENT_NOCONTEXT_CALL, b'', 1)
    if digest(restored) != CLIENT_NOCONTEXT_SHARED_SHA256:
        raise FullError('source_changed')
    return restored


CLIENT_EXECUTE_SCRIPT = r'''
import sys
import re
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

import json
from decimal import Decimal
from yadinassi.database_context import FileDBContext
if len(sys.argv) != 5 or sys.argv[2] not in ("standalone", "managed-thick-file"):
    raise RuntimeError("invalid compilation profile")
vm = Interpreter(lambda value: (_ for _ in ()).throw(RuntimeError("unexpected message")),
                 database_context=FileDBContext(sys.argv[4]), compilation_profile=sys.argv[2])
vm.execute(Path(sys.argv[3]).read_text(encoding="utf-8-sig"))
values = list(vm.execute("ВычислитьПробу()"))
result = []
for value in values:
    if type(value) is Decimal and value.is_finite() and value == value.to_integral_value():
        result.append(int(value))
    elif type(value) in (str, bool):
        result.append(value)
    else:
        raise RuntimeError("unexpected witness type")
sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
'''



# BEGIN bounded Date Null measurement source binding
DATE_NULL_SOURCE_SHA256 = '56dc0e682f31a13e52d3b5d278e1effe20d6899110770b94671dd0ba426aa751'
DATE_NULL_MODULE_SHA256 = '840b3d19ef6eb100af3cc685788692eec7f6aec863518b003046beae995b8062'
DATE_NULL_BASE_SHA256 = 'c991b9fbf808a59fad6edc10ad9768efe85bc3bd2da9d7b63c1daa5cdb118413'
DATE_NULL_CORE_SHA256 = '1b6c51fba57161907d26d78b3c96d317ff1f4b65098d6bf5a0815ed5fb575a70'
DATE_NULL_PREFIX = b'\n// BEGIN bounded Date Null measurement\n'
DATE_NULL_SUFFIX = b'// END bounded Date Null measurement\n'
DATE_NULL_CALL = b'    DNAppend(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f);\n'
DATE_NULL_OLD_WRITER = b'\xd0\x9f\xd1\x80\xd0\xbe\xd1\x86\xd0\xb5\xd0\xb4\xd1\x83\xd1\x80\xd0\xb0 \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb0\xd1\x82\xd1\x8c\xd0\x9f\xd1\x80\xd0\xbe\xd0\xb1\xd1\x83(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x9f\xd1\x83\xd1\x82\xd1\x8c, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x9d\xd0\xbe\xd0\xbc\xd0\xb5\xd1\x80, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\xa4\xd0\xb0\xd0\xb7\xd0\xb0, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x9a\xd0\xbe\xd0\xbd\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f)\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c = \xd0\x9d\xd0\xbe\xd0\xb2\xd1\x8b\xd0\xb9 \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8cJSON;\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c.\xd0\x9e\xd1\x82\xd0\xba\xd1\x80\xd1\x8b\xd1\x82\xd1\x8c\xd0\xa4\xd0\xb0\xd0\xb9\xd0\xbb(\xd0\x9f\xd1\x83\xd1\x82\xd1\x8c);\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb0\xd1\x82\xd1\x8cJSON(\xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c, \xd0\x9d\xd0\xbe\xd0\xb2\xd1\x8b\xd0\xb9 \xd0\xa1\xd1\x82\xd1\x80\xd1\x83\xd0\xba\xd1\x82\xd1\x83\xd1\x80\xd0\xb0("schema,nonce,phase,witness,values",\n        1, \xd0\x9d\xd0\xbe\xd0\xbc\xd0\xb5\xd1\x80, \xd0\xa4\xd0\xb0\xd0\xb7\xd0\xb0, \xd0\x9a\xd0\xbe\xd0\xbd\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f));\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c.\xd0\x97\xd0\xb0\xd0\xba\xd1\x80\xd1\x8b\xd1\x82\xd1\x8c();\n\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x9f\xd1\x80\xd0\xbe\xd1\x86\xd0\xb5\xd0\xb4\xd1\x83\xd1\x80\xd1\x8b'
DATE_NULL_COMPACT_WRITER = b'\xd0\x9f\xd1\x80\xd0\xbe\xd1\x86\xd0\xb5\xd0\xb4\xd1\x83\xd1\x80\xd0\xb0 \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb0\xd1\x82\xd1\x8c\xd0\x9f\xd1\x80\xd0\xbe\xd0\xb1\xd1\x83(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x9f\xd1\x83\xd1\x82\xd1\x8c, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x9d\xd0\xbe\xd0\xbc\xd0\xb5\xd1\x80, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\xa4\xd0\xb0\xd0\xb7\xd0\xb0, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x9a\xd0\xbe\xd0\xbd\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87 \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f)\n    \xd0\x9f\xd0\xb5\xd1\x80\xd0\xb5\xd0\xbc \xd0\x9f\xd0\xb0\xd1\x80\xd0\xb0\xd0\xbc\xd0\xb5\xd1\x82\xd1\x80\xd1\x8bJSON, \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c;\n    \xd0\x9f\xd0\xb0\xd1\x80\xd0\xb0\xd0\xbc\xd0\xb5\xd1\x82\xd1\x80\xd1\x8bJSON = \xd0\x9d\xd0\xbe\xd0\xb2\xd1\x8b\xd0\xb9 \xd0\x9f\xd0\xb0\xd1\x80\xd0\xb0\xd0\xbc\xd0\xb5\xd1\x82\xd1\x80\xd1\x8b\xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb8JSON(\xd0\x9f\xd0\xb5\xd1\x80\xd0\xb5\xd0\xbd\xd0\xbe\xd1\x81\xd0\xa1\xd1\x82\xd1\x80\xd0\xbe\xd0\xbaJSON.\xd0\x9d\xd0\xb5\xd1\x82, " ", \xd0\x98\xd1\x81\xd1\x82\xd0\xb8\xd0\xbd\xd0\xb0);\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c = \xd0\x9d\xd0\xbe\xd0\xb2\xd1\x8b\xd0\xb9 \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8cJSON;\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c.\xd0\x9e\xd1\x82\xd0\xba\xd1\x80\xd1\x8b\xd1\x82\xd1\x8c\xd0\xa4\xd0\xb0\xd0\xb9\xd0\xbb(\xd0\x9f\xd1\x83\xd1\x82\xd1\x8c, , , \xd0\x9f\xd0\xb0\xd1\x80\xd0\xb0\xd0\xbc\xd0\xb5\xd1\x82\xd1\x80\xd1\x8bJSON);\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb0\xd1\x82\xd1\x8cJSON(\xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c, \xd0\x9d\xd0\xbe\xd0\xb2\xd1\x8b\xd0\xb9 \xd0\xa1\xd1\x82\xd1\x80\xd1\x83\xd0\xba\xd1\x82\xd1\x83\xd1\x80\xd0\xb0("schema,nonce,phase,witness,values",\n        1, \xd0\x9d\xd0\xbe\xd0\xbc\xd0\xb5\xd1\x80, \xd0\xa4\xd0\xb0\xd0\xb7\xd0\xb0, \xd0\x9a\xd0\xbe\xd0\xbd\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82, \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f));\n    \xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c.\xd0\x97\xd0\xb0\xd0\xba\xd1\x80\xd1\x8b\xd1\x82\xd1\x8c();\n\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x9f\xd1\x80\xd0\xbe\xd1\x86\xd0\xb5\xd0\xb4\xd1\x83\xd1\x80\xd1\x8b'


def date_null_shared_source(raw: bytes) -> bytes:
    """Exact legacy adapter inverse only; never the strict136 host preflight."""
    if (type(raw) is not bytes or digest(raw) != DATE_NULL_SOURCE_SHA256
            or raw.count(DATE_NULL_PREFIX) != 1 or raw.count(DATE_NULL_SUFFIX) != 1
            or raw.count(DATE_NULL_CALL) != 1 or raw.count(DATE_NULL_COMPACT_WRITER) != 1
            or not raw.endswith(DATE_NULL_SUFFIX + CLIENT_NOCONTEXT_INITIALIZER)):
        raise FullError('source_changed')
    start = raw.index(DATE_NULL_PREFIX)
    end = raw.index(DATE_NULL_SUFFIX, start)
    core = raw[start + len(DATE_NULL_PREFIX):end]
    if digest(core) != DATE_NULL_CORE_SHA256:
        raise FullError('source_changed')
    restored = raw[:start] + raw[end + len(DATE_NULL_SUFFIX):]
    restored = restored.replace(DATE_NULL_CALL, b'', 1).replace(
        DATE_NULL_COMPACT_WRITER, DATE_NULL_OLD_WRITER, 1)
    if digest(restored) != DATE_NULL_BASE_SHA256:
        raise FullError('source_changed')
    return restored

# END bounded Date Null measurement source binding


# BEGIN bounded preprocessor profile observation binding
PREPROCESSOR_SOURCE_SHA256 = '0dc26abc7a2bb786c7875d934fd2821c7e5f9e31175a0cf694c9b1170801f285'
PREPROCESSOR_MODULE_SHA256 = '6e64719f7a086388730e5ce9d8a8944b67db58a4919866b6562cde6a1369285e'
PREPROCESSOR_BASE_SHA256 = 'baa71011295cb3f4e5d030d88ebc56218a9d218e17f8226570ba73dd3fce3f6d'
PREPROCESSOR_CORE_SHA256 = '5cda3cc687bc4b89a223fce03d06602c381a0ef84b57687c4d190897318b1ee7'
PREPROCESSOR_DEFAULT_TOKEN = 'pp.v1:005005010010002002001001002002'
# Audited native run40208015242; independent of runtime execution context.
PREPROCESSOR_RUNTIME_TOKEN = 'pp.v1:135135139139131131131131131131'
PREPROCESSOR_COMPILATION_PROFILE = 'managed-thick-file'
# No native expected token exists until a separately audited capture.
PREPROCESSOR_CORE = b'// BEGIN bounded preprocessor profile observation\n// Direct literal compilation at each site; never infer flags from execution side.\n&AtClient\nFunction PPClient()\n    Var EnglishMask, RussianMask;\n    EnglishMask = 0;\n    RussianMask = 0;\n#If Client Then\n    EnglishMask = EnglishMask + 1;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 1;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If Server Then\n    EnglishMask = EnglishMask + 2;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 2;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtClient Then\n    EnglishMask = EnglishMask + 4;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 4;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtServer Then\n    EnglishMask = EnglishMask + 8;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 8;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThinClient Then\n    EnglishMask = EnglishMask + 16;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbd\xd0\xba\xd0\xb8\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 16;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If WebClient Then\n    EnglishMask = EnglishMask + 32;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xb5\xd0\xb1\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 32;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientOrdinaryApplication Then\n    EnglishMask = EnglishMask + 64;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\x9e\xd0\xb1\xd1\x8b\xd1\x87\xd0\xbd\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 64;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientManagedApplication Then\n    EnglishMask = EnglishMask + 128;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xa3\xd0\xbf\xd1\x80\xd0\xb0\xd0\xb2\xd0\xbb\xd1\x8f\xd0\xb5\xd0\xbc\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 128;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ExternalConnection Then\n    EnglishMask = EnglishMask + 256;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xbd\xd0\xb5\xd1\x88\xd0\xbd\xd0\xb5\xd0\xb5\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 256;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n    Return PPEncode(EnglishMask) + PPEncode(RussianMask);\nEndFunction\n\n&AtServer\nFunction PPServer()\n    Var EnglishMask, RussianMask;\n    EnglishMask = 0;\n    RussianMask = 0;\n#If Client Then\n    EnglishMask = EnglishMask + 1;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 1;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If Server Then\n    EnglishMask = EnglishMask + 2;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 2;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtClient Then\n    EnglishMask = EnglishMask + 4;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 4;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtServer Then\n    EnglishMask = EnglishMask + 8;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 8;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThinClient Then\n    EnglishMask = EnglishMask + 16;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbd\xd0\xba\xd0\xb8\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 16;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If WebClient Then\n    EnglishMask = EnglishMask + 32;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xb5\xd0\xb1\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 32;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientOrdinaryApplication Then\n    EnglishMask = EnglishMask + 64;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\x9e\xd0\xb1\xd1\x8b\xd1\x87\xd0\xbd\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 64;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientManagedApplication Then\n    EnglishMask = EnglishMask + 128;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xa3\xd0\xbf\xd1\x80\xd0\xb0\xd0\xb2\xd0\xbb\xd1\x8f\xd0\xb5\xd0\xbc\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 128;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ExternalConnection Then\n    EnglishMask = EnglishMask + 256;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xbd\xd0\xb5\xd1\x88\xd0\xbd\xd0\xb5\xd0\xb5\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 256;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n    Return PPEncode(EnglishMask) + PPEncode(RussianMask);\nEndFunction\n\n&AtServerNoContext\nFunction PPServerNoContext()\n    Var EnglishMask, RussianMask;\n    EnglishMask = 0;\n    RussianMask = 0;\n#If Client Then\n    EnglishMask = EnglishMask + 1;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 1;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If Server Then\n    EnglishMask = EnglishMask + 2;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 2;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtClient Then\n    EnglishMask = EnglishMask + 4;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 4;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtServer Then\n    EnglishMask = EnglishMask + 8;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 8;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThinClient Then\n    EnglishMask = EnglishMask + 16;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbd\xd0\xba\xd0\xb8\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 16;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If WebClient Then\n    EnglishMask = EnglishMask + 32;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xb5\xd0\xb1\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 32;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientOrdinaryApplication Then\n    EnglishMask = EnglishMask + 64;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\x9e\xd0\xb1\xd1\x8b\xd1\x87\xd0\xbd\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 64;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientManagedApplication Then\n    EnglishMask = EnglishMask + 128;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xa3\xd0\xbf\xd1\x80\xd0\xb0\xd0\xb2\xd0\xbb\xd1\x8f\xd0\xb5\xd0\xbc\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 128;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ExternalConnection Then\n    EnglishMask = EnglishMask + 256;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xbd\xd0\xb5\xd1\x88\xd0\xbd\xd0\xb5\xd0\xb5\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 256;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n    Return PPEncode(EnglishMask) + PPEncode(RussianMask);\nEndFunction\n\n&AtClientAtServerNoContext\nFunction PPDual()\n    Var EnglishMask, RussianMask;\n    EnglishMask = 0;\n    RussianMask = 0;\n#If Client Then\n    EnglishMask = EnglishMask + 1;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 1;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If Server Then\n    EnglishMask = EnglishMask + 2;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 2;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtClient Then\n    EnglishMask = EnglishMask + 4;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 4;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If AtServer Then\n    EnglishMask = EnglishMask + 8;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x9d\xd0\xb0\xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 8;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThinClient Then\n    EnglishMask = EnglishMask + 16;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbd\xd0\xba\xd0\xb8\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 16;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If WebClient Then\n    EnglishMask = EnglishMask + 32;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xb5\xd0\xb1\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 32;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientOrdinaryApplication Then\n    EnglishMask = EnglishMask + 64;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\x9e\xd0\xb1\xd1\x8b\xd1\x87\xd0\xbd\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 64;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ThickClientManagedApplication Then\n    EnglishMask = EnglishMask + 128;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\xa2\xd0\xbe\xd0\xbb\xd1\x81\xd1\x82\xd1\x8b\xd0\xb9\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xa3\xd0\xbf\xd1\x80\xd0\xb0\xd0\xb2\xd0\xbb\xd1\x8f\xd0\xb5\xd0\xbc\xd0\xbe\xd0\xb5\xd0\x9f\xd1\x80\xd0\xb8\xd0\xbb\xd0\xbe\xd0\xb6\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 128;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n#If ExternalConnection Then\n    EnglishMask = EnglishMask + 256;\n#EndIf\n#\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8 \xd0\x92\xd0\xbd\xd0\xb5\xd1\x88\xd0\xbd\xd0\xb5\xd0\xb5\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xa2\xd0\xbe\xd0\xb3\xd0\xb4\xd0\xb0\n    RussianMask = RussianMask + 256;\n#\xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8\n    Return PPEncode(EnglishMask) + PPEncode(RussianMask);\nEndFunction\n\n&AtClientAtServerNoContext\nFunction PPEncode(Val Mask)\n    Var Digits, Hundreds, Tens, Units;\n    If TypeOf(Mask) <> Type("Number") Then Raise "pp-invalid-type"; EndIf;\n    If Mask < 0 Or Mask > 511 Or Int(Mask) <> Mask Then Raise "pp-invalid-mask"; EndIf;\n    Digits = "0123456789";\n    Hundreds = Int(Mask / 100);\n    Tens = Int(Mask / 10) - Hundreds * 10;\n    Units = Mask - Int(Mask / 10) * 10;\n    Return Mid(Digits, Hundreds + 1, 1) + Mid(Digits, Tens + 1, 1)\n        + Mid(Digits, Units + 1, 1);\nEndFunction\n\n&AtServer\nFunction PPServerDual()\n    Return PPDual();\nEndFunction\n\n&AtClient\nProcedure PPAppend(RecordsOut)\n    Var Encoded;\n    Encoded = "pp.v1:" + PPClient() + PPServer() + PPServerNoContext()\n        + PPDual() + PPServerDual();\n    If StrLen(Encoded) <> 36 Then Raise "pp-invalid-token"; EndIf;\n    RecordsOut.Add(Encoded);\nEndProcedure\n// END bounded preprocessor profile observation\n'
PREPROCESSOR_CALL = b'    PPAppend(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f);\n'


def preprocessor_shared_source(raw: bytes) -> bytes:
    """Exact historical adapter inverse, never current-source host admission."""
    if (type(raw) is not bytes or digest(raw) != PREPROCESSOR_SOURCE_SHA256
            or raw.count(PREPROCESSOR_CORE) != 1 or raw.count(PREPROCESSOR_CALL) != 1):
        raise FullError('invalid_input')
    restored = raw.replace(PREPROCESSOR_CORE, b'', 1).replace(PREPROCESSOR_CALL, b'', 1)
    if digest(restored) != PREPROCESSOR_BASE_SHA256:
        raise FullError('invalid_input')
    return restored


def validate_preprocessor_profile(value):
    """Finite bilingual observation only; no parity or alias-equality assumption."""
    if (type(value) is not str or len(value) != 36
            or re.fullmatch(r'pp\.v1:(?:(?:[0-4][0-9]{2}|50[0-9]|51[01])){10}', value) is None):
        raise ValueError('preprocessor profile token')
    return value
# END bounded preprocessor profile observation binding


# BEGIN bounded infobase-context measurement binding
INFOBASE_CONTEXT_SOURCE_SHA256 = 'baa71011295cb3f4e5d030d88ebc56218a9d218e17f8226570ba73dd3fce3f6d'
INFOBASE_CONTEXT_MODULE_SHA256 = '8f0e26621fed3a26f3073764f51dbf1c2164e4ebcc9a50b24f052487ba2b3be9'
INFOBASE_CONTEXT_BASE_SHA256 = '56dc0e682f31a13e52d3b5d278e1effe20d6899110770b94671dd0ba426aa751'
# Independently audited capture: run 40137786320, not a synthetic prediction.
INFOBASE_CONTEXT_EXPECTED_TOKEN = 'ibc.v1:121122221122021122021122021122'
INFOBASE_CONTEXT_CORE = b'// BEGIN bounded infobase context measurement\n// Only ordinary /tmp/onec-smoke/db, verified by the native host.\n// Zero-argument calls are direct; arity rejection is dynamic, not static.\n&AtClient\nFunction IBCClient()\n    Var Profile, EnglishValue, RussianValue;\n    Profile = 0;\n#If AtClient Then\n    Profile = Profile + 1;\n#EndIf\n#If AtServer Then\n    Profile = Profile + 2;\n#EndIf\n    Try\n        EnglishValue = InfoBaseConnectionString();\n        RussianValue = \xd0\xa1\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f\xd0\x98\xd0\xbd\xd1\x84\xd0\xbe\xd1\x80\xd0\xbc\xd0\xb0\xd1\x86\xd0\xb8\xd0\xbe\xd0\xbd\xd0\xbd\xd0\xbe\xd0\xb9\xd0\x91\xd0\xb0\xd0\xb7\xd1\x8b();\n    Except\n        Return IBCEncode(Profile, 1, 0, 0, 0, 0);\n    EndTry;\n    Return IBCObserve(Profile, EnglishValue, RussianValue);\nEndFunction\n\n&AtServer\nFunction IBCServer()\n    Var Profile, EnglishValue, RussianValue;\n    Profile = 0;\n#If AtClient Then\n    Profile = Profile + 1;\n#EndIf\n#If AtServer Then\n    Profile = Profile + 2;\n#EndIf\n    Try\n        EnglishValue = InfoBaseConnectionString();\n        RussianValue = \xd0\xa1\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f\xd0\x98\xd0\xbd\xd1\x84\xd0\xbe\xd1\x80\xd0\xbc\xd0\xb0\xd1\x86\xd0\xb8\xd0\xbe\xd0\xbd\xd0\xbd\xd0\xbe\xd0\xb9\xd0\x91\xd0\xb0\xd0\xb7\xd1\x8b();\n    Except\n        Return IBCEncode(Profile, 1, 0, 0, 0, 0);\n    EndTry;\n    Return IBCObserve(Profile, EnglishValue, RussianValue);\nEndFunction\n\n&AtServerNoContext\nFunction IBCNoContext()\n    Var Profile, EnglishValue, RussianValue;\n    Profile = 0;\n#If AtClient Then\n    Profile = Profile + 1;\n#EndIf\n#If AtServer Then\n    Profile = Profile + 2;\n#EndIf\n    Try\n        EnglishValue = InfoBaseConnectionString();\n        RussianValue = \xd0\xa1\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f\xd0\x98\xd0\xbd\xd1\x84\xd0\xbe\xd1\x80\xd0\xbc\xd0\xb0\xd1\x86\xd0\xb8\xd0\xbe\xd0\xbd\xd0\xbd\xd0\xbe\xd0\xb9\xd0\x91\xd0\xb0\xd0\xb7\xd1\x8b();\n    Except\n        Return IBCEncode(Profile, 1, 0, 0, 0, 0);\n    EndTry;\n    Return IBCObserve(Profile, EnglishValue, RussianValue);\nEndFunction\n\n&AtClientAtServerNoContext\nFunction IBCDual()\n    Var Profile, EnglishValue, RussianValue;\n    Profile = 0;\n#If AtClient Then\n    Profile = Profile + 1;\n#EndIf\n#If AtServer Then\n    Profile = Profile + 2;\n#EndIf\n    Try\n        EnglishValue = InfoBaseConnectionString();\n        RussianValue = \xd0\xa1\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f\xd0\x98\xd0\xbd\xd1\x84\xd0\xbe\xd1\x80\xd0\xbc\xd0\xb0\xd1\x86\xd0\xb8\xd0\xbe\xd0\xbd\xd0\xbd\xd0\xbe\xd0\xb9\xd0\x91\xd0\xb0\xd0\xb7\xd1\x8b();\n    Except\n        Return IBCEncode(Profile, 1, 0, 0, 0, 0);\n    EndTry;\n    Return IBCObserve(Profile, EnglishValue, RussianValue);\nEndFunction\n\n&AtClientAtServerNoContext\nFunction IBCObserve(Val Profile, Val EnglishValue, Val RussianValue)\n    Var Shape, Aliases, EnglishArity, RussianArity, IBCArityTemporary;\n    If TypeOf(EnglishValue) <> Type("String") Or TypeOf(RussianValue) <> Type("String") Then\n        Return IBCEncode(Profile, 3, 0, 0, 0, 0);\n    EndIf;\n    Shape = 0;\n    If EnglishValue = "File=""/tmp/onec-smoke/db"";" Then Shape = 1; EndIf;\n    If EnglishValue = "File=""/tmp/onec-smoke/db""" Then Shape = 2; EndIf;\n    Aliases = 0;\n    If EnglishValue = RussianValue Then Aliases = 1; EndIf;\n    // Arity runs in this dual no-context observer, on the same side.\n    // It does not measure the originating routine\'s arity profile.\n    EnglishArity = 1;\n    Try\n        Execute("IBCArityTemporary = InfoBaseConnectionString(1);");\n    Except\n        EnglishArity = 2;\n    EndTry;\n    RussianArity = 1;\n    Try\n        Execute("IBCArityTemporary = \xd0\xa1\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\xd0\xa1\xd0\xbe\xd0\xb5\xd0\xb4\xd0\xb8\xd0\xbd\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f\xd0\x98\xd0\xbd\xd1\x84\xd0\xbe\xd1\x80\xd0\xbc\xd0\xb0\xd1\x86\xd0\xb8\xd0\xbe\xd0\xbd\xd0\xbd\xd0\xbe\xd0\xb9\xd0\x91\xd0\xb0\xd0\xb7\xd1\x8b(1);");\n    Except\n        RussianArity = 2;\n    EndTry;\n    Return IBCEncode(Profile, 2, Shape, Aliases, EnglishArity, RussianArity);\nEndFunction\n\n&AtClientAtServerNoContext\nFunction IBCEncode(Val Profile, Val Status, Val Shape, Val Aliases, Val EnglishArity, Val RussianArity)\n    Return Mid("0123", Profile + 1, 1) + Mid("0123", Status + 1, 1)\n        + Mid("012", Shape + 1, 1) + Mid("01", Aliases + 1, 1)\n        + Mid("012", EnglishArity + 1, 1) + Mid("012", RussianArity + 1, 1);\nEndFunction\n\n&AtServer\nFunction IBCServerDual()\n    Return IBCDual();\nEndFunction\n\n&AtClient\nProcedure IBCAppend(RecordsOut)\n    Var Encoded;\n    Encoded = "ibc.v1:" + IBCClient() + IBCServer() + IBCNoContext()\n        + IBCDual() + IBCServerDual();\n    If StrLen(Encoded) <> 37 Then Raise "ibc-invalid-token"; EndIf;\n    RecordsOut.Add(Encoded);\nEndProcedure\n// END bounded infobase context measurement\n'
INFOBASE_CONTEXT_CALL = '    IBCAppend(Значения);\n'.encode('utf-8')


def infobase_shared_source(raw: bytes) -> bytes:
    """Exact measurement inverse; no generic routine stripping or API emulation."""
    if (type(raw) is not bytes or digest(raw) != INFOBASE_CONTEXT_SOURCE_SHA256
            or raw.count(INFOBASE_CONTEXT_CORE) != 1 or raw.count(INFOBASE_CONTEXT_CALL) != 1):
        raise FullError('source_changed')
    restored = raw.replace(INFOBASE_CONTEXT_CORE, b'', 1).replace(INFOBASE_CONTEXT_CALL, b'', 1)
    if digest(restored) != INFOBASE_CONTEXT_BASE_SHA256:
        raise FullError('source_changed')
    return restored


def validate_infobase_context(value):
    """Finite native observation, not a native expected result or parity claim."""
    if (type(value) is not str or len(value) != 37
            or re.fullmatch(r'ibc\.v1:(?:[0-3][1-3][0-2][01][0-2][0-2]){5}', value) is None):
        raise ValueError('infobase context token')
    for offset in range(7, 37, 6):
        slot = value[offset:offset + 6]
        if ((slot[1] in '13' and slot[2:] != '0000')
                or (slot[1] == '2' and (slot[4] not in '12' or slot[5] not in '12'))):
            raise ValueError('infobase context observation combination')
    return value


def discard_infobase_capture(report):
    """Discard only optional observation after later failure; retain old evidence."""
    if type(report) is not dict:
        return
    stage = report.get('stage3', report)
    if type(stage) is dict and type(stage.get('client_probe')) is dict:
        stage['client_probe'].pop('infobase_context', None)
        stage['client_probe'].pop('preprocessor_profile', None)
        if stage.get('schema') in (5, 9):
            stage['preprocessor_status'] = 'not_started' if stage.get('status') == 'not_started' else 'failed'
# END bounded infobase-context measurement binding


CLIENT_WITNESS_SOURCE_SHA256 = INFOBASE_CONTEXT_SOURCE_SHA256


def _load_infobase_fixture():
    """Load the source-inventoried Linux fixture helper from this checkout only."""
    path = Path(__file__).with_name("native_infobase_fixture.py")
    source = read_regular(path, 4 * MAX_FILE, nonempty=True)
    # Never execute ignored timestamp-valid bytecode beside this safety helper.
    module = types.ModuleType("_native_infobase_fixture")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def verify_client_interpreter(root: Path, source: Path, source_hash: str, *, runner=None, preprocessor_measurement=False) -> None:
    """Execute exact current whole138 (or explicitly historical137) source with a real, exclusively owned file DB.

    This preflight is Linux-only and assumes a trusted single-job host. Its
    fixture is header-recognized synthetic storage, not a valid native database.
    The historical inverse is used by legacy adapters only, never admission.
    """
    raw = read_regular(source, MAX_FILE, nonempty=True)
    if type(preprocessor_measurement) is not bool:
        raise FullError("invalid_input")
    current = source_hash == PREPROCESSOR_SOURCE_SHA256
    expected_sources = {PREPROCESSOR_SOURCE_SHA256} if preprocessor_measurement else {PREPROCESSOR_SOURCE_SHA256, CLIENT_WITNESS_SOURCE_SHA256}
    profile = PREPROCESSOR_COMPILATION_PROFILE if current and not preprocessor_measurement else "standalone"
    if digest(raw) != source_hash or source_hash not in expected_sources:
        raise FullError("source_changed")
    fixture_module = _load_infobase_fixture()
    try:
        with fixture_module.OwnedInfobase() as fixture:
            fixture.verify()
            with tempfile.TemporaryDirectory(prefix="client-interpreter-cache-") as cache:
                arguments = [sys.executable, "-I", "-B", "-X", "pycache_prefix=" + cache,
                             "-c", CLIENT_EXECUTE_SCRIPT, str(root), profile, str(source), str(fixture.directory)]
                if runner is None:
                    code, output, stderr = fixture.run_child(
                        arguments, root, env=child_environment(), seconds=CASE_SECONDS,
                        stdout_limit=MAX_FILE, stderr_limit=MAX_STDERR)
                else:
                    # Explicit offline injection only; production always runs
                    # the bounded child above with the genuine runtime context.
                    code, output, stderr = runner(arguments, root)
                fixture.verify()
                if read_regular(source, MAX_FILE, nonempty=True) != raw:
                    raise FullError("source_changed")
            values = CLIENT_RUNTIME_VALUES + ([PREPROCESSOR_DEFAULT_TOKEN if preprocessor_measurement
                                               else PREPROCESSOR_RUNTIME_TOKEN] if current else [])
            expected = json.dumps(values, ensure_ascii=False,
                                  separators=(",", ":")).encode()
            if code != 0 or stderr or output != expected:
                raise FullError("interpreter_failed")
    except fixture_module.FixtureError as error:
        # Translation stays outside the owner so an uncertain child shutdown
        # prevents fixture removal before finite public reporting.
        raise FullError(error.code) from None


def validate_process_diagnostics(value):
    classes = {"native", "display", "session_bus", "shell", "python", "other", "unreadable"}
    if (type(value) is not dict
            or set(value) != {"stage", "reason", "unexpected_count", "zombie_count", "classes"}
            or value["stage"] not in {"not_checked", "baseline", "before_probe", "after_exit"}
            or value["reason"] not in {"none", "unverified", "native_not_quiet", "unexpected_processes"}
            or not is_int(value["unexpected_count"], 256) or not is_int(value["zombie_count"], 256)
            or value["zombie_count"] > value["unexpected_count"]
            or type(value["classes"]) is not dict or set(value["classes"]) != classes
            or any(not is_int(count, 256) for count in value["classes"].values())
            or sum(value["classes"].values()) != value["unexpected_count"]):
        raise ValueError("process diagnostics")
    if value["reason"] != "unexpected_processes" and value["unexpected_count"] != 0:
        raise ValueError("process diagnostic reason")
    return value


def validate_marker_diagnostics(value, *, preprocessor_measurement=False):
    count = len(CLIENT_RUNTIME_VALUES) + (1 if preprocessor_measurement else 0)
    if (type(value) is not dict
            or set(value) != {'phase', 'kind', 'ordinal', 'error_stage'}
            or type(value['phase']) is not str
            or value['phase'] not in {'invalid', 'error', 'completed'}
            or type(value['kind']) is not str
            or value['kind'] not in {'none', 'count', 'type', 'value', 'runtime_error'}
            or type(value['ordinal']) is not int or not -1 <= value['ordinal'] <= count
            or type(value['error_stage']) is not int or not 0 <= value['error_stage'] <= 11):
        raise ValueError('client marker diagnostics')
    if value['phase'] != 'completed':
        valid = value['kind'] == 'none' and value['ordinal'] == -1 and value['error_stage'] == 0
    elif value['kind'] == 'runtime_error':
        valid = 1 <= value['error_stage'] <= 11 and value['ordinal'] == value['error_stage'] + 3
    elif value['kind'] == 'count':
        valid = 0 <= value['ordinal'] <= count and value['error_stage'] == 0
    elif value['kind'] in {'type', 'value'}:
        valid = 0 <= value['ordinal'] < count and value['error_stage'] == 0
    else:
        valid = value['ordinal'] == -1 and value['error_stage'] == 0
    if not valid:
        raise ValueError('client marker diagnostics combination')
    return value


def validate_client_probe(data, source_hash, module_hash, *, infobase_allowed=False, preprocessor_allowed=False, preprocessor_runtime=False):
    if type(data) is dict and "preprocessor_profile" in data:
        if (not preprocessor_allowed or source_hash != PREPROCESSOR_SOURCE_SHA256
                or module_hash != PREPROCESSOR_MODULE_SHA256 or data.get("status") != "ok"):
            raise ValueError("preprocessor observation source or outcome")
        validate_preprocessor_profile(data["preprocessor_profile"])
        if preprocessor_runtime and data["preprocessor_profile"] != PREPROCESSOR_RUNTIME_TOKEN:
            raise ValueError("preprocessor runtime mismatch")
        data = {key: value for key, value in data.items() if key != "preprocessor_profile"}
    if type(data) is dict and 'infobase_context' in data:
        if (not infobase_allowed or (source_hash, module_hash) not in {
                (INFOBASE_CONTEXT_SOURCE_SHA256, INFOBASE_CONTEXT_MODULE_SHA256),
                (PREPROCESSOR_SOURCE_SHA256, PREPROCESSOR_MODULE_SHA256)} or data.get('status') != 'ok'):
            raise ValueError('infobase context source or outcome')
        validate_infobase_context(data['infobase_context'])
        if data['infobase_context'] != INFOBASE_CONTEXT_EXPECTED_TOKEN:
            raise ValueError('infobase context runtime mismatch')
        data = {key: value for key, value in data.items() if key != 'infobase_context'}
    if type(data) is dict and "marker_diagnostics" in data:
        validate_marker_diagnostics(data["marker_diagnostics"],
                                    preprocessor_measurement=source_hash == PREPROCESSOR_SOURCE_SHA256)
        if data.get("status") != "failed" or data.get("failure_kind") != "invalid_result" or data.get("witness_verified") is not False:
            raise ValueError("client marker diagnostics outcome")
        data = {key: value for key, value in data.items() if key != "marker_diagnostics"}
    if (type(data) is not dict
            or set(data) != CLIENT_FLAGS | CLIENT_HASHES | {"status", "failure_kind", "process_diagnostics"}
            or any(type(data[key]) is not bool for key in CLIENT_FLAGS)
            or data["status"] not in {"not_started", "failed", "ok"}
            or data["failure_kind"] not in FAILURES):
        raise ValueError("client probe schema")
    diagnostic = validate_process_diagnostics(data["process_diagnostics"])
    expected = {"source_sha256": source_hash, "module_sha256": module_hash,
                "roundtrip_sha256": module_hash}
    if any(data[key] not in (None, expected[key]) for key in CLIENT_HASHES):
        raise ValueError("client probe identity")
    if data["status"] == "ok":
        if (diagnostic["stage"] != "after_exit" or diagnostic["reason"] != "none"
                or data["failure_kind"] != "none" or not all(data[key] for key in CLIENT_FLAGS)
                or any(data[key] != expected[key] for key in CLIENT_HASHES)):
            raise ValueError("client probe completion")
    elif data["status"] == "not_started":
        if (diagnostic["stage"] != "not_checked" or diagnostic["reason"] != "none"
                or data["failure_kind"] != "prerequisites_failed"
                or any(data[key] for key in CLIENT_FLAGS)
                or any(data[key] is not None for key in CLIENT_HASHES)):
            raise ValueError("client probe unreached")
    elif data["failure_kind"] in {"none", "prerequisites_failed"} or data["witness_verified"]:
        raise ValueError("client probe failed")
    return data



CLIENT_OUTPUT_KEYS = {"output_sha256", "output_size", "message_count"}
COLLECTIONS_SOURCE = "integrational_tests/tests/collections.bsl"
DATES_SOURCE = "integrational_tests/tests/dates.bsl"
VALUES_SOURCE = "integrational_tests/tests/values.bsl"
VALUES_SOURCE_SHA256 = "0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c"


def validate_client_dates(data, source_hash, module_hash, server_case):
    """Bind the client witness to this invocation's server dates evidence."""
    if type(data) is not dict or not CLIENT_OUTPUT_KEYS <= set(data):
        raise ValueError("client dates schema")
    base = {key: value for key, value in data.items() if key not in CLIENT_OUTPUT_KEYS}
    validate_client_probe(base, source_hash, module_hash)
    if data["status"] == "ok":
        if (server_case["status"] != "ok"
                or not is_digest(data["output_sha256"])
                or not is_int(data["output_size"], MAX_FILE)
                or type(data["message_count"]) is not int or data["message_count"] != 185
                or any(data[key] != server_case[key] for key in CLIENT_OUTPUT_KEYS)):
            raise ValueError("client dates output identity")
    elif any(data[key] is not None for key in CLIENT_OUTPUT_KEYS):
        raise ValueError("client dates incomplete output")
    return data


def validate_client_values(data, source_hash, module_hash, server_case):
    """Bind the client witness to this invocation's server values evidence."""
    if (source_hash != VALUES_SOURCE_SHA256
            or type(data) is not dict or not CLIENT_OUTPUT_KEYS <= set(data)):
        raise ValueError("client values schema")
    base = {key: value for key, value in data.items() if key not in CLIENT_OUTPUT_KEYS}
    validate_client_probe(base, source_hash, module_hash)
    if data["status"] == "ok":
        if (server_case["status"] != "ok"
                or not is_digest(data["output_sha256"])
                or not is_int(data["output_size"], MAX_FILE)
                or type(data["message_count"]) is not int or data["message_count"] != 441
                or any(data[key] != server_case[key] for key in CLIENT_OUTPUT_KEYS)):
            raise ValueError("client values output identity")
    elif any(data[key] is not None for key in CLIENT_OUTPUT_KEYS):
        raise ValueError("client values incomplete output")
    return data


NUMBERS_SOURCE = "integrational_tests/tests/numbers.bsl"
NUMBERS_SOURCE_SHA256 = '65075fff9adc854a317c74821052a9f9afa2b064d5fbb55b21dbab1ecb87556d'

def validate_client_numbers(data, source_hash, module_hash, server_case):
    """Bind the client witness to this invocation's server numbers evidence."""
    if (source_hash != NUMBERS_SOURCE_SHA256
            or type(data) is not dict or not CLIENT_OUTPUT_KEYS | {"conversion_verified"} <= set(data)
            or type(data["conversion_verified"]) is not bool):
        raise ValueError("client numbers schema")
    base = {key: value for key, value in data.items() if key not in CLIENT_OUTPUT_KEYS | {"conversion_verified"}}
    validate_client_probe(base, source_hash, module_hash)
    if data["status"] == "ok":
        if (data["conversion_verified"] is not True or server_case["status"] != "ok"
                or not is_digest(data["output_sha256"])
                or not is_int(data["output_size"], MAX_FILE)
                or type(data["message_count"]) is not int or data["message_count"] != 421
                or any(data[key] != server_case[key] for key in CLIENT_OUTPUT_KEYS)):
            raise ValueError("client numbers output identity")
    elif data["conversion_verified"] or any(data[key] is not None for key in CLIENT_OUTPUT_KEYS):
        raise ValueError("client numbers incomplete output")
    return data


def validate_client_collections(data, source_hash, module_hash, server_case):
    """Bind the client witness to this invocation's server collections evidence."""
    if (source_hash != COLLECTIONS_SOURCE_SHA256
            or type(data) is not dict or not CLIENT_OUTPUT_KEYS <= set(data)):
        raise ValueError("client collections schema")
    base = {key: value for key, value in data.items() if key not in CLIENT_OUTPUT_KEYS | {"mismatch"}}
    validate_client_probe(base, source_hash, module_hash)
    if data["status"] == "ok":
        if (server_case["status"] != "ok"
                or not is_digest(data["output_sha256"])
                or not is_int(data["output_size"], MAX_FILE)
                or type(data["message_count"]) is not int or data["message_count"] != 866
                or any(data[key] != server_case[key] for key in CLIENT_OUTPUT_KEYS)):
            raise ValueError("client collections output identity")
    elif any(data[key] is not None for key in CLIENT_OUTPUT_KEYS):
        raise ValueError("client collections incomplete output")
    mismatch = data.get("mismatch")
    if mismatch is not None:
        # Diagnostic metadata is never evidence of acceptance. It is only valid
        # after a complete, identity-bound client run failed the exact byte gate.
        if (data["status"] != "failed" or data["failure_kind"] != "output_mismatch"
                or any(data[key] is not True for key in ("entered", "completed", "process_exited", "quiet"))
                or data["witness_verified"] is not False
                or data["source_sha256"] != source_hash or data["module_sha256"] != module_hash
                or data["roundtrip_sha256"] != module_hash
                or data["process_diagnostics"]["stage"] != "after_exit"
                or data["process_diagnostics"]["reason"] != "none"
                or server_case["status"] != "ok" or server_case["source_sha256"] != source_hash
                or type(server_case["message_count"]) is not int or server_case["message_count"] != 866):
            raise ValueError("client collections mismatch context")
        keys = {"count", "first", "ordinals", "client_sha256", "server_sha256", "client_size", "server_size"}
        if (type(mismatch) is not dict or set(mismatch) != keys
                or not is_int(mismatch["count"], 866) or mismatch["count"] < 1
                or not is_int(mismatch["first"], 866) or mismatch["first"] < 1
                or mismatch["count"] > 867 - mismatch["first"]
                or not is_digest(mismatch["client_sha256"]) or not is_digest(mismatch["server_sha256"])
                or mismatch["client_sha256"] == mismatch["server_sha256"]
                or any(not is_int(mismatch[key], MAX_FILE) or mismatch[key] < 1
                       for key in ("client_size", "server_size"))
                or type(mismatch["ordinals"]) is not list
                or len(mismatch["ordinals"]) != min(mismatch["count"], 16)
                or any(not is_int(value, 866) or value < 1 for value in mismatch["ordinals"])
                or mismatch["ordinals"] != sorted(set(mismatch["ordinals"]))
                or mismatch["ordinals"][0] != mismatch["first"]
                or mismatch["count"] - len(mismatch["ordinals"]) > 866 - mismatch["ordinals"][-1]):
            raise ValueError("client collections mismatch schema")
    return data


def validate_client_watchdog(data, source_hash, module_hash):
    if type(data) is not dict or type(data.get("timeout_verified")) is not bool:
        raise ValueError("watchdog schema")
    base = {key: value for key, value in data.items() if key != "timeout_verified"}
    if data["timeout_verified"]:
        diagnostic = validate_process_diagnostics(base.get("process_diagnostics"))
        if diagnostic["stage"] != "after_exit" or diagnostic["reason"] != "none":
            raise ValueError("watchdog process diagnostics")
        expected = {"process_diagnostics": diagnostic,
                    "status": "ok", "failure_kind": "none", "source_sha256": source_hash,
                    "module_sha256": module_hash, "roundtrip_sha256": module_hash,
                    "entered": True, "completed": False, "process_exited": False,
                    "quiet": True, "witness_verified": False}
        if (set(base) != set(expected) or any(type(base[key]) is not type(value)
                or base[key] != value for key, value in expected.items())):
            raise ValueError("watchdog timeout proof")
    else:
        validate_client_probe(base, source_hash, module_hash)
        if base["status"] == "ok":
            raise ValueError("watchdog not verified")
    return data


CLIENT_WIRE_HASHES = ("source_sha256", "module_sha256", "roundtrip_sha256")
CLIENT_WIRE_PROOF = ("entered", "completed", "process_exited", "quiet", "witness_verified")
CLIENT_WIRE_RECORDS = ("client_probe", "client_dates", "client_values", "client_collections", "client_watchdog")
CLIENT_WIRE_V3_RECORDS = CLIENT_WIRE_RECORDS + ("client_numbers",)
CLIENT_WIRE_DIAGNOSTICS = ("stage", "reason", "unexpected_count", "zombie_count", "classes")
CLIENT_WIRE_CLASSES = ("native", "display", "session_bus", "shell", "python", "other", "unreadable")
MAX_STAGE_REPORT = 8192


def decode_stage3_wire(data):
    if type(data) is dict and type(data.get('schema')) is int and data['schema'] in (9, 10, 11, 12):
        if (data.get('compilation_profile') != PREPROCESSOR_COMPILATION_PROFILE
                or data.get('preprocessor_status') not in ('not_started', 'failed', 'matched')
                or len(json.dumps(data, separators=(',', ':'), allow_nan=False).encode()) > MAX_STAGE_REPORT):
            raise ValueError("preprocessor runtime wire")
        base = {key: value for key, value in data.items()
                if key not in ('compilation_profile', 'preprocessor_status')}
        base['schema'] = data['schema'] - 8
        return {**decode_stage3_wire(base), 'schema': 9, 'compilation_profile': PREPROCESSOR_COMPILATION_PROFILE,
                'preprocessor_status': data['preprocessor_status']}
    if type(data) is dict and type(data.get("schema")) is int and data["schema"] in (5, 6, 7, 8):
        if (data.get("preprocessor_status") not in ("not_started", "failed", "observed")
                or len(json.dumps(data, separators=(",", ":"), allow_nan=False).encode()) > MAX_STAGE_REPORT):
            raise ValueError("preprocessor observation wire")
        base = {key: value for key, value in data.items() if key != "preprocessor_status"}
        base["schema"] = data["schema"] - 4
        return {**decode_stage3_wire(base), "schema": 5,
                "preprocessor_status": data["preprocessor_status"]}
    if type(data) is dict and type(data.get("schema")) is int and data["schema"] == 4:
        if ("client_async" not in data or "client_probe" not in data
                or any(key in data for key in ("client_dates","client_values","client_collections","client_numbers","client_watchdog"))
                or len(json.dumps(data,separators=(",",":"),allow_nan=False).encode()) > MAX_STAGE_REPORT):
            raise ValueError("async wire")
        base = {key:value for key,value in data.items() if key != "client_async"}
        base["schema"] = 1
        return {**decode_stage3_wire(base),"client_async":decode_async_wire(data["client_async"])}
    """Decode lossless schema-2/3 wire; public evidence retains named schema 1.

    Schema 1 is the legacy named representation. Schema 2 requires *every*
    present client record to be compact, never an ambiguous per-record hybrid.
    Schema 3 additionally packs diagnostic field/class names for numbers opt-in.
    The ordinary validators below bind array positions to independently generated
    identities and verify all proof values, including failed/unreached records.
    """
    if type(data) is not dict or type(data.get("schema")) is not int or data["schema"] not in (1, 2, 3):
        raise ValueError("stage wire schema")
    if any(type(key) is str and key.startswith("client_") and key not in CLIENT_WIRE_V3_RECORDS for key in data):
        raise ValueError("stage wire client family")
    if data["schema"] == 1:
        if any(type(data.get(key)) is dict and ({"hashes", "proof"} & set(data[key])
               or type(data[key].get("process_diagnostics")) is list)
               for key in CLIENT_WIRE_V3_RECORDS):
            raise ValueError("stage wire hybrid")
        return data
    if ((data["schema"] == 2 and ("client_collections" not in data or "client_numbers" in data))
            or (data["schema"] == 3 and "client_numbers" not in data)):
        raise ValueError("stage wire client family")
    if len(json.dumps(data, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()) > MAX_STAGE_REPORT:
        raise ValueError("stage wire limit")
    result = {**data, "schema": 1}
    for key in CLIENT_WIRE_V3_RECORDS:
        if key not in data:
            continue
        record = data[key]
        if (type(record) is not dict or not {"hashes", "proof"} <= set(record)
                or (CLIENT_HASHES | CLIENT_FLAGS) & set(record)):
            raise ValueError("stage wire record")
        if data["schema"] == 3:
            values = record.get("process_diagnostics")
            if (type(values) is not list or len(values) != 5
                    or type(values[0]) is not str or type(values[1]) is not str
                    or type(values[4]) is not list or len(values[4]) != len(CLIENT_WIRE_CLASSES)):
                raise ValueError("stage wire diagnostics")
            diagnostic = validate_process_diagnostics({
                **dict(zip(CLIENT_WIRE_DIAGNOSTICS[:4], values[:4])),
                "classes": dict(zip(CLIENT_WIRE_CLASSES, values[4]))})
        elif type(record.get("process_diagnostics")) is not dict:
            raise ValueError("stage wire diagnostics")
        hashes, proof = record["hashes"], record["proof"]
        if (type(hashes) is not list or len(hashes) != 3
                or any(value is not None and not is_digest(value) for value in hashes)
                or type(proof) is not list or len(proof) != 5
                or any(type(value) is not bool for value in proof)):
            raise ValueError("stage wire arrays")
        result[key] = {**{name: value for name, value in record.items() if name not in {"hashes", "proof"}},
                       **dict(zip(CLIENT_WIRE_HASHES, hashes)), **dict(zip(CLIENT_WIRE_PROOF, proof))}
        if data["schema"] == 3:
            result[key]["process_diagnostics"] = diagnostic
    return result


def validate_stage3(data, nonce: str, input_hashes: dict, module_hashes: dict, *, prerequisites: bool, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False, client_async: bool = False, preprocessor_measurement: bool = False):
    raw_schema = data.get("schema") if type(data) is dict else None
    if type(preprocessor_measurement) is not bool:
        raise ValueError("preprocessor mode")
    if preprocessor_measurement:
        if (raw_schema not in (5, 6, 7, 8)
                or input_hashes.get(CLIENT_SOURCE) != PREPROCESSOR_SOURCE_SHA256
                or module_hashes.get("client_probe") != PREPROCESSOR_MODULE_SHA256):
            raise ValueError("preprocessor requires exact observation schema")
    preprocessor_runtime = not preprocessor_measurement and input_hashes.get(CLIENT_SOURCE) == PREPROCESSOR_SOURCE_SHA256
    if preprocessor_runtime:
        if (raw_schema not in (9, 10, 11, 12)
                or module_hashes.get("client_probe") != PREPROCESSOR_MODULE_SHA256
                or data.get("compilation_profile") != PREPROCESSOR_COMPILATION_PROFILE):
            raise ValueError("preprocessor requires exact runtime schema and profile")
    elif not preprocessor_measurement and raw_schema in (5, 6, 7, 8, 9, 10, 11, 12):
        raise ValueError("unsolicited preprocessor evidence")
    logical_schema = raw_schema - (8 if preprocessor_runtime else 4 if preprocessor_measurement else 0)
    if client_async:
        if (not CLIENT_SOURCE in input_hashes or watchdog_check or client_dates or client_values or client_collections or client_numbers or logical_schema != 4):
            raise ValueError("async requires separate schema4 measurement")
    elif logical_schema == 4:
        raise ValueError("unsolicited async schema")
    data = decode_stage3_wire(data)
    client_requested = CLIENT_SOURCE in input_hashes
    expected_keys = {"schema", "nonce", "status", "failure_kind", "failed_case", "input_sha256", "cases"}
    if preprocessor_measurement or preprocessor_runtime:
        expected_keys.add("preprocessor_status")
    if preprocessor_runtime:
        expected_keys.add("compilation_profile")
    if client_async:
        expected_keys.add("client_async")
    if client_numbers:
        if not client_requested:
            raise ValueError("client numbers requires client")
        expected_keys.add("client_numbers")
    if client_collections:
        if not client_requested:
            raise ValueError("client collections requires client")
        expected_keys.add("client_collections")
    if client_values:
        if not client_requested:
            raise ValueError("client values requires client")
        expected_keys.add("client_values")
    if client_dates:
        if not client_requested:
            raise ValueError("client dates requires client")
        expected_keys.add("client_dates")
    if watchdog_check:
        if not client_requested:
            raise ValueError("watchdog requires client")
        expected_keys.add("client_watchdog")
    if client_requested:
        expected_keys.add("client_probe")
    if type(data) is not dict or set(data) != expected_keys:
        raise ValueError("stage3 keys")
    if type(data["schema"]) is not int or data["schema"] != (9 if preprocessor_runtime else 5 if preprocessor_measurement else 1) or data["nonce"] != nonce:
        raise ValueError("stage3 identity")
    status = data["status"]
    if (preprocessor_measurement or preprocessor_runtime) and data["preprocessor_status"] != {
            "not_started": "not_started", "failed": "failed", "ok": "matched" if preprocessor_runtime else "observed"}.get(status):
        raise ValueError("preprocessor observation status")
    if status not in {"not_started", "failed", "ok"} or data["failure_kind"] not in (FAILURES | {"unsupported_observation"} if client_async else FAILURES):
        raise ValueError("stage3 status")
    if type(data["input_sha256"]) is not dict:
        raise ValueError("inputs")
    if data["input_sha256"] != input_hashes and not (status != "ok" and data["input_sha256"] == {}):
        raise ValueError("inputs")
    cases = data["cases"]
    if type(cases) is not list or len(cases) != len(SCENARIOS):
        raise ValueError("cases")
    infobase_requested = client_requested and input_hashes[CLIENT_SOURCE] in (INFOBASE_CONTEXT_SOURCE_SHA256, PREPROCESSOR_SOURCE_SHA256)
    client = (validate_client_probe(data["client_probe"], input_hashes[CLIENT_SOURCE],
                                    module_hashes["client_probe"],
                                    infobase_allowed=infobase_requested and status == 'ok',
                                    preprocessor_allowed=(preprocessor_measurement or preprocessor_runtime) and status == 'ok',
                                    preprocessor_runtime=preprocessor_runtime)
              if client_requested else None)
    if (infobase_requested and status == 'ok'
            and 'infobase_context' not in data['client_probe']):
        raise ValueError('infobase context observation missing')
    if ((preprocessor_measurement or preprocessor_runtime) and status == "ok"
            and "preprocessor_profile" not in data["client_probe"]):
        raise ValueError("preprocessor observation missing")
    watchdog = (validate_client_watchdog(data["client_watchdog"], input_hashes[CLIENT_SOURCE],
                module_hashes["client_probe"]) if watchdog_check else None)
    if watchdog is not None:
        if client["status"] != "ok" and watchdog["status"] != "not_started":
            raise ValueError("watchdog order")
        if status == "ok" and watchdog["status"] != "ok":
            raise ValueError("watchdog missing")
        if status == "not_started" and watchdog["status"] != "not_started":
            raise ValueError("watchdog unreached")
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
    if client is not None:
        if any(case["status"] != "ok" for case in cases) and client["status"] != "not_started":
            raise ValueError("client probe order")
        if status == "ok" and client["status"] != "ok":
            raise ValueError("client probe missing")
        if status == "not_started" and client["status"] != "not_started":
            raise ValueError("client probe unreached")
    if client_dates:
        dates = validate_client_dates(data["client_dates"], input_hashes[DATES_SOURCE],
                                      module_hashes["client_dates"], cases[SCENARIOS.index("dates")])
        if client["status"] != "ok" and dates["status"] != "not_started":
            raise ValueError("client dates order")
        if watchdog is not None and dates["status"] != "ok" and watchdog["status"] != "not_started":
            raise ValueError("client dates watchdog order")
        if status == "ok" and dates["status"] != "ok":
            raise ValueError("client dates missing")
        if status == "not_started" and dates["status"] != "not_started":
            raise ValueError("client dates unreached")
    if client_values:
        values = validate_client_values(data["client_values"], input_hashes[VALUES_SOURCE],
                                        module_hashes["client_values"], cases[SCENARIOS.index("values")])
        if client["status"] != "ok" and values["status"] != "not_started":
            raise ValueError("client values order")
        if client_dates and dates["status"] != "ok" and values["status"] != "not_started":
            raise ValueError("client dates values order")
        if watchdog is not None and values["status"] != "ok" and watchdog["status"] != "not_started":
            raise ValueError("client values watchdog order")
        if status == "ok" and values["status"] != "ok":
            raise ValueError("client values missing")
        if status == "not_started" and values["status"] != "not_started":
            raise ValueError("client values unreached")
    if client_collections:
        collections = validate_client_collections(data["client_collections"], input_hashes[COLLECTIONS_SOURCE],
                    module_hashes["client_collections"], cases[SCENARIOS.index("collections")])
        if client["status"] != "ok" and collections["status"] != "not_started":
            raise ValueError("client collections order")
        if client_dates and dates["status"] != "ok" and collections["status"] != "not_started":
            raise ValueError("client dates collections order")
        if client_values and values["status"] != "ok" and collections["status"] != "not_started":
            raise ValueError("client values collections order")
        if watchdog is not None and collections["status"] != "ok" and watchdog["status"] != "not_started":
            raise ValueError("client collections watchdog order")
        if status == "ok" and collections["status"] != "ok":
            raise ValueError("client collections missing")
        if status == "not_started" and collections["status"] != "not_started":
            raise ValueError("client collections unreached")
    if client_numbers:
        numbers = validate_client_numbers(data["client_numbers"], input_hashes[NUMBERS_SOURCE],
                    module_hashes["client_numbers"], cases[SCENARIOS.index("numbers")])
        if client["status"] != "ok" and numbers["status"] != "not_started":
            raise ValueError("client numbers order")
        if client_dates and dates["status"] != "ok" and numbers["status"] != "not_started":
            raise ValueError("client dates numbers order")
        if client_values and values["status"] != "ok" and numbers["status"] != "not_started":
            raise ValueError("client values numbers order")
        if client_collections and collections["status"] != "ok" and numbers["status"] != "not_started":
            raise ValueError("client collections numbers order")
        if watchdog is not None and numbers["status"] != "ok" and watchdog["status"] != "not_started":
            raise ValueError("client numbers watchdog order")
        if status == "ok" and numbers["status"] != "ok":
            raise ValueError("client numbers missing")
        if status == "not_started" and numbers["status"] != "not_started":
            raise ValueError("client numbers unreached")
    if client_async:
        identity = module_hashes["client_async"]
        measurement = validate_client_async(data["client_async"], identity["template"], identity["modules"])
        if client["status"] != "ok" and measurement["status"] != "not_started":
            raise ValueError("async order")
        if status == "ok" and measurement["status"] != "ok":
            raise ValueError("async incomplete")
        if status == "not_started" and measurement["status"] != "not_started":
            raise ValueError("async unreached")
    if status == "ok":
        if (not prerequisites or seen_incomplete or data["failure_kind"] != "none" or data["failed_case"] is not None):
            raise ValueError("success")
    elif status == "not_started":
        if (prerequisites or any(case["status"] != "not_started" for case in cases)
                or data["failure_kind"] != "prerequisites_failed" or data["failed_case"] is not None):
            raise ValueError("not started")
    elif (not prerequisites or data["failure_kind"] == "none"
            or (data["failure_kind"] == "prerequisites_failed" and not (client_async and measurement["status"] == "failed" and measurement["failure_kind"] == "prerequisites_failed"))
            or (failed and data["failed_case"] != failed[0])
            or (not failed and data["failed_case"] is not None)):
        raise ValueError("failed")
    return data


def validate_envelope(raw: bytes, nonce: str, input_hashes: dict, module_hashes: dict, report_validator, *, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False, client_async: bool = False, preprocessor_measurement: bool = False):
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
                                 prerequisites=prerequisites, watchdog_check=watchdog_check, client_dates=client_dates, client_values=client_values, client_collections=client_collections, client_numbers=client_numbers, **({"client_async": True} if client_async else {}), preprocessor_measurement=preprocessor_measurement)
        report["stage3"] = stage3
        if len(json.dumps(report, separators=(",", ":"), ensure_ascii=True).encode()) > MAX_REPORT:
            raise ValueError("expanded report limit")
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


def validate_comparison_options(native_target: str, comparison_mode: str) -> None:
    if (type(native_target) is not str or native_target not in {WINDOWS_TARGET, LINUX_TARGET}
            or type(comparison_mode) is not str or comparison_mode not in {BYTE_EXACT, MAP_MODE}
            or (comparison_mode == MAP_MODE and native_target != LINUX_TARGET)):
        raise FullError("comparison_configuration_invalid")


def validate_semantic_context(report: dict, image: str) -> None:
    """Only this measured native checkpoint may use the reviewed semantic contract."""
    try:
        stage2, stage3 = report["stage2"], report["stage3"]
        if (image != APPROVED_IMAGE or report["image"] != image or report["platform"] != "linux/amd64"
                or report["native_target"] != LINUX_TARGET or report["comparison_mode"] != MAP_MODE
                or report["configured_timezone"] != "Etc/UTC" or report["configured_native_locale"] != "ru_RU"
                or report["status"] != "ok" or report["container_exit_code"] != 0
                or report["runtime_version"] != "8.3.27.1508"
                or report["runtime_version_source"] != "SystemInfo.AppVersion"
                or stage2["status"] != "ok" or stage2["actual_version"] != "8.3.27.1508"
                or stage2["version_source"] != "SystemInfo.AppVersion"
                or stage2["named_user_verified"] is not True
                or stage3["status"] != "ok" or stage3["nonce"] != report["invocation_nonce"]
                or not re.fullmatch(r"[0-9a-f]{32}", report["invocation_nonce"])
                or stage3["input_sha256"]["integrational_tests/tests/collections.bsl"] != COLLECTIONS_SOURCE_SHA256
                or stage3["cases"][0]["source_sha256"] != COLLECTIONS_SOURCE_SHA256
                or report["trusted_input_sha256"] != stage3["input_sha256"]
                or any(report[key] is not True for key in ("container_cleanup_verified",
                    "native_cases_completed", "native_transport_validated", "native_evidence_accepted"))):
            raise ValueError("semantic context")
    except (KeyError, TypeError, ValueError, IndexError):
        raise FullError("semantic_context_invalid") from None


def map_contract():
    # Compile the checked helper source directly, ignoring any repository bytecode.
    path = Path(__file__).with_name("native_1c_map_contract.py")
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location("native_1c_map_contract", path))
    exec(compile(read_regular(path, 4 * MAX_FILE, nonempty=True), str(path), "exec"), module.__dict__)
    return module



ASYNC_ACTUAL_LIMIT = 8192
ASYNC_EXECUTE_SCRIPT = r"""
import sys
import importlib.util
from pathlib import Path
try:
    root = Path(sys.argv[1])
    path = root / "scripts/native_async_comparison.py"
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location("native_async_comparison", path))
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    source = (root / "scripts/native_1c_bootstrap/full_suite.py").read_bytes()
    template, bodies = module.read_pinned_sources(source)
    package = root / "yadinassi"
    spec = importlib.util.spec_from_file_location("yadinassi", package / "__init__.py",
                                                submodule_search_locations=[str(package)])
    runtime = importlib.util.module_from_spec(spec)
    sys.modules["yadinassi"] = runtime
    spec.loader.exec_module(runtime)
    sys.stdout.buffer.write(module.canonical(module.execute_actual(bodies)))
except BaseException:
    sys.exit(1)
"""


def async_contract(root: Path):
    path = root / "scripts/native_async_comparison.py"
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location("native_async_comparison", path))
    exec(compile(read_regular(path, 4 * MAX_FILE, nonempty=True), str(path), "exec"), module.__dict__)
    return module


def validate_async_comparison(result):
    if (type(result) is not dict or set(result) != {"profile", "status", "cases", "actual_sha256"}
            or result["profile"] != "async-language-8-v1"
            or type(result["status"]) is not str or result["status"] not in {"matched", "mismatched"}
            or not is_digest(result["actual_sha256"])
            or type(result["cases"]) is not list or len(result["cases"]) != 8):
        raise FullError("async_comparison_invalid")
    for row in result["cases"]:
        if (type(row) is not list or len(row) != 2 or any(type(v) is not str for v in row)
                or row[0] not in {"matched", "mismatched"}
                or row[1] not in {"none", "runtimeerror", "lifecycle", "trace", "values", "errors"}
                or (row[0] == "matched") != (row[1] == "none")):
            raise FullError("async_comparison_invalid")
    if (result["status"] == "matched") != all(row[0] == "matched" for row in result["cases"]):
        raise FullError("async_comparison_invalid")
    return result


def compare_async_runtime(root: Path, private: Path, report: dict, input_hashes: dict, *, runner=bounded_child):
    """Execute actual-only rows in isolation; compare accepted same-run evidence here."""
    source_path = "scripts/native_1c_bootstrap/full_suite.py"
    validate_semantic_context(report, APPROVED_IMAGE)
    if report["trusted_input_sha256"] != input_hashes:
        raise FullError("async_evidence_invalid")
    before = interpreter_provenance(root)
    source = read_regular(root / source_path, 294912, nonempty=True)
    if digest(source) != input_hashes.get(source_path):
        raise FullError("async_source_changed")
    if (report.get("native_evidence_accepted") is not True
            or report.get("container_cleanup_verified") is not True
            or report.get("native_transport_validated") is not True):
        raise FullError("async_evidence_invalid")
    try:
        contract = async_contract(root)
        template, bodies = contract.read_pinned_sources(source)
        native = report["stage3"]["client_async"]
        contract.validate_inputs(template, bodies, native)
        with tempfile.TemporaryDirectory(prefix="async-cache-", dir=private) as cache:
            code, stdout, stderr = runner([sys.executable, "-I", "-B", "-X", "pycache_prefix=" + cache,
                "-c", ASYNC_EXECUTE_SCRIPT, str(root)], root,
                stdout_limit=ASYNC_ACTUAL_LIMIT, stderr_limit=MAX_STDERR)
        if code or stderr:
            raise FullError("async_execution_failed")
        actual = strict_json(stdout, ASYNC_ACTUAL_LIMIT)
        result = contract.compare_observations(template, bodies, native, actual)
    except FullError:
        raise
    except Exception:
        raise FullError("async_comparison_invalid") from None
    if (interpreter_provenance(root) != before
            or read_regular(root / source_path, 294912, nonempty=True) != source):
        raise FullError("execution_provenance_changed")
    return validate_async_comparison(result)

def validate_semantic_result(result: dict, *, raw_matched: bool) -> None:
    contract = map_contract()
    if type(result) is not dict or set(result) != {"status", "profile", "records", "byte_equal_records", "accepted_labels", "reason"}:
        raise FullError("semantic_result_invalid")
    if (type(result) is not dict or set(result) != {"status", "profile", "records", "byte_equal_records", "accepted_labels", "reason"}
            or type(result["status"]) is not str or result["status"] not in {"equivalent", "rejected"} or result["profile"] != MAP_MODE
            or type(result["reason"]) is not str or result["reason"] not in contract.REASONS
            or not is_int(result["records"], 866) or not is_int(result["byte_equal_records"], result["records"])
            or type(result["accepted_labels"]) is not list
            or any(type(label) is not str or label not in contract.ELIGIBLE_LABELS for label in result["accepted_labels"])
            or len(set(result["accepted_labels"])) != len(result["accepted_labels"])):
        raise FullError("semantic_result_invalid")
    if result["status"] == "equivalent":
        if (result["reason"] != "none" or result["records"] != 866
                or result["byte_equal_records"] + len(result["accepted_labels"]) != 866
                or raw_matched != (result["byte_equal_records"] == 866)):
            raise FullError("semantic_result_invalid")
    elif (result["reason"] == "none" or result["records"] != 0
            or result["byte_equal_records"] != 0 or result["accepted_labels"]):
        raise FullError("semantic_result_invalid")
    if result["accepted_labels"] != [label for label in contract.ELIGIBLE_LABELS if label in result["accepted_labels"]]:
        raise FullError("semantic_result_invalid")


def validate_comparison(comparison: dict, stage3: dict, native_target: str, comparison_mode: str) -> None:
    """Validate both raw evidence and separately named acceptance, never conflate them."""
    validate_comparison_options(native_target, comparison_mode)
    try:
        if (type(comparison) is not dict or set(comparison) != {"schema", "configured_timezone", "configured_locale",
                "native_target", "comparison_mode", "status", "acceptance_status", "cases"}
                or type(comparison["schema"]) is not int or comparison["schema"] != 2
                or comparison["configured_timezone"] != "Etc/UTC" or comparison["configured_locale"] != "C.UTF-8"
                or comparison["native_target"] != native_target or comparison["comparison_mode"] != comparison_mode
                or comparison["status"] not in {"ok", "failed"}
                or comparison["acceptance_status"] not in {"accepted", "rejected"}
                or type(comparison["cases"]) is not list or len(comparison["cases"]) != len(SCENARIOS)
                or type(stage3["cases"]) is not list or len(stage3["cases"]) != len(SCENARIOS)):
            raise ValueError("comparison")
        for name, native, case in zip(SCENARIOS, stage3["cases"], comparison["cases"]):
            if (type(case) is not dict or set(case) != {"name", "status", "failure_kind", "native_size", "native_sha256",
                    "interpreter_size", "interpreter_sha256", "mismatch", "acceptance_status", "semantic"}
                    or case["name"] != name or native["name"] != name
                    or not is_int(case["native_size"], MAX_FILE) or not is_int(native["output_size"], MAX_FILE)
                    or not is_digest(case["native_sha256"]) or not is_digest(native["output_sha256"])
                    or case["native_size"] != native["output_size"] or case["native_sha256"] != native["output_sha256"]
                    or case["status"] not in {"matched", "mismatched", "error", "timeout"}
                    or case["acceptance_status"] not in {"accepted", "rejected"}):
                raise ValueError("case")
            if case["status"] in {"error", "timeout"}:
                if (case["acceptance_status"] != "rejected" or case["semantic"] is not None
                        or case["mismatch"] is not None or case["interpreter_size"] is not None
                        or case["interpreter_sha256"] is not None
                        or case["failure_kind"] not in {"source_changed", "native_capture_changed", "invalid_private_file",
                            "interpreter_timeout", "interpreter_output_limit", "interpreter_unavailable", "interpreter_failed",
                            POST_CREATE_FAILURE}
                        or (case["status"] == "timeout") != (case["failure_kind"] == "interpreter_timeout")):
                    raise ValueError("failure")
                continue
            matched = case["status"] == "matched"
            if (case["failure_kind"] != "none" or not is_digest(case["interpreter_sha256"])
                    or not is_int(case["interpreter_size"], MAX_FILE)
                    or matched != (case["interpreter_sha256"] == case["native_sha256"] and case["interpreter_size"] == case["native_size"])):
                raise ValueError("raw")
            if matched:
                if case["mismatch"] is not None:
                    raise ValueError("mismatch")
            else:
                mismatch = case["mismatch"]
                if (type(mismatch) is not dict or set(mismatch) != {"different_byte_positions", "first_mismatch_byte",
                        "first_mismatch_native_line", "native_line_count", "interpreter_line_count"}
                        or any(not is_int(value, MAX_FILE + 1) for value in mismatch.values())
                        or not 1 <= mismatch["different_byte_positions"] <= max(case["native_size"], case["interpreter_size"])
                        or mismatch["first_mismatch_byte"] > min(case["native_size"], case["interpreter_size"])
                        or not 1 <= mismatch["first_mismatch_native_line"] <= mismatch["native_line_count"] + 1):
                    raise ValueError("mismatch")
            semantic = case["semantic"]
            if comparison_mode == MAP_MODE and name == "collections":
                if native["source_sha256"] != COLLECTIONS_SOURCE_SHA256:
                    raise ValueError("source")
                validate_semantic_result(semantic, raw_matched=matched)
                accepted = semantic["status"] == "equivalent"
            else:
                if semantic is not None:
                    raise ValueError("unexpected semantic")
                accepted = matched
            if (case["acceptance_status"] == "accepted") != accepted:
                raise ValueError("acceptance")
        if ((comparison["status"] == "ok") != all(case["status"] == "matched" for case in comparison["cases"])
                or (comparison["acceptance_status"] == "accepted") != all(case["acceptance_status"] == "accepted" for case in comparison["cases"])):
            raise ValueError("aggregate")
    except (KeyError, TypeError, ValueError, FullError):
        raise FullError("comparison_evidence_invalid") from None


def compare_outputs(root: Path, capture: Path, stage3: dict, input_hashes: dict, *, runner=bounded_child,
                    native_target=WINDOWS_TARGET, comparison_mode=BYTE_EXACT, runtime_evidence=None) -> dict:
    validate_comparison_options(native_target, comparison_mode)
    if comparison_mode == MAP_MODE:
        validate_semantic_context(runtime_evidence, APPROVED_IMAGE)
        if runtime_evidence["stage3"] != stage3 or runtime_evidence["trusted_input_sha256"] != input_hashes:
            raise FullError("semantic_context_invalid")
    if (stage3.get("status") != "ok" or len(stage3.get("cases", [])) != len(SCENARIOS)
            or [case.get("name") for case in stage3["cases"]] != list(SCENARIOS)
            or any(case.get("status") != "ok" for case in stage3["cases"])):
        raise FullError("comparison_coverage_invalid")
    records = []
    for name, case in zip(SCENARIOS, stage3["cases"]):
        record = {"name": name, "status": "error", "failure_kind": "none",
                  "native_size": case["output_size"], "native_sha256": case["output_sha256"],
                  "interpreter_size": None, "interpreter_sha256": None, "mismatch": None,
                  "acceptance_status": "rejected", "semantic": None}
        try:
            source = root / f"integrational_tests/tests/{name}.bsl"
            source_bytes = read_regular(source, MAX_FILE, nonempty=True)
            if digest(source_bytes) != input_hashes[f"integrational_tests/tests/{name}.bsl"]:
                raise FullError("source_changed")
            expected = read_regular(capture / (name + ".out"), MAX_FILE)
            if digest(expected) != case["output_sha256"] or len(expected) != case["output_size"]:
                raise FullError("native_capture_changed")
            # An ignored stale/tampered repository __pycache__ is not source
            # provenance. Use a new empty private cache prefix and never write it.
            with tempfile.TemporaryDirectory(prefix="interpreter-cache-", dir=capture.parent) as cache:
                code, actual, stderr = runner([sys.executable, "-I", "-B", "-X", "pycache_prefix=" + cache,
                                              "-c", EXECUTE_SCRIPT, str(root), str(source), native_target], root)
            if code != 0 or stderr:
                if interpreter_post_create_failed(source_bytes, code, actual, stderr):
                    raise FullError(POST_CREATE_FAILURE)
                raise FullError("interpreter_failed")
            record.update(interpreter_size=len(actual), interpreter_sha256=digest(actual))
            record["status"] = "matched" if actual == expected else "mismatched"
            if actual != expected:
                record["mismatch"] = mismatch_metadata(expected, actual)
            if name == "collections" and comparison_mode == MAP_MODE:
                result = map_contract().compare_collections(expected, actual, case["source_sha256"])
                validate_semantic_result(result, raw_matched=actual == expected)
                record["semantic"] = result
                accepted = result["status"] == "equivalent"
            else:
                accepted = actual == expected
            record["acceptance_status"] = "accepted" if accepted else "rejected"
        except FullError as error:
            if str(error) == "semantic_result_invalid":
                raise
            record["failure_kind"] = str(error)
            record["status"] = "timeout" if str(error) == "interpreter_timeout" else "error"
        records.append(record)
    result = {"schema": 2, "configured_timezone": "Etc/UTC", "configured_locale": "C.UTF-8",
              "native_target": native_target, "comparison_mode": comparison_mode,
              "status": "ok" if all(case["status"] == "matched" for case in records) else "failed",
              "acceptance_status": "accepted" if all(case["acceptance_status"] == "accepted" for case in records) else "rejected",
              "cases": records}
    validate_comparison(result, stage3, native_target, comparison_mode)
    return result


def windows_fingerprints(root: Path) -> dict[str, str]:
    names = [f"tests/fixtures/native_windows/{name}.out" for name in SCENARIOS] + ["integrational_tests/meta.md"]
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
    tracked = set(git("ls-files", "--", "yadinassi", "scripts/native_infobase_fixture.py").splitlines())
    actual = {path.relative_to(root).as_posix() for path in (root / "yadinassi").rglob("*")
              if not path.is_dir() and "__pycache__" not in path.parts}
    actual.add("scripts/native_infobase_fixture.py")
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
    files += [root / "pyproject.toml", root / "scripts/native_1c_full_host.py", root / "scripts/native_1c_smoke.py",
              root / "scripts/native_1c_map_contract.py", root / "scripts/native_async_comparison.py",
              root / "scripts/native_infobase_fixture.py"]
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
            "comparison_driver_sha256": hashes["scripts/native_1c_full_host.py"],
            "map_contract_sha256": hashes["scripts/native_1c_map_contract.py"]}



def retain_output_bytes(capture: Path, stage3: dict) -> dict[str, bytes]:
    """Retain only the six already validated captures, without transforming bytes."""
    try:
        if (capture.is_symlink() or not capture.is_dir()
                or set(path.name for path in capture.iterdir()) != set(ARTIFACT_FILES[:-1])
                or stage3["status"] != "ok"
                or [case["name"] for case in stage3["cases"]] != list(SCENARIOS)):
            raise ValueError("coverage")
        result = {}
        for name, case in zip(SCENARIOS, stage3["cases"]):
            payload = read_regular(capture / (name + ".out"), MAX_FILE)
            if (case["status"] != "ok" or len(payload) != case["output_size"]
                    or digest(payload) != case["output_sha256"]):
                raise ValueError("identity")
            result[name + ".out"] = payload
        if sum(map(len, result.values())) > MAX_TOTAL:
            raise ValueError("aggregate")
        return result
    except (OSError, KeyError, TypeError, ValueError, FullError):
        raise FullError("native_artifact_capture_invalid") from None


def output_artifact_files(payloads: dict[str, bytes], report: dict, image: str) -> dict[str, bytes]:
    """Rebuild a finite allowlisted manifest; never copy logs or exception strings."""
    try:
        if (list(payloads) != list(ARTIFACT_FILES[:-1])
                or any(type(value) is not bytes or len(value) > MAX_FILE for value in payloads.values())
                or sum(map(len, payloads.values())) > MAX_TOTAL
                or any(report[key] is not True for key in ("native_evidence_accepted",
                    "native_transport_validated", "native_cases_completed", "container_cleanup_verified",
                    "private_payloads_removed", "windows_goldens_unchanged"))
                or report["status"] != "ok" or report["container_exit_code"] != 0
                or report["runtime_version_source"] != "SystemInfo.AppVersion"
                or report["runtime_version"] != "8.3.27.1508"
                or report["configured_timezone"] != "Etc/UTC"
                or report["configured_native_locale"] != "ru_RU"
                or not re.fullmatch(r"[0-9a-f]{32}", report["invocation_nonce"])
                or not re.fullmatch(r"ghcr\.io/atridis/onec-ubuntu22@sha256:[0-9a-f]{64}", image)):
            raise ValueError("gates")
        repository = report["repository"]
        if (set(repository) - {"commit", "tree", "github_run_id", "github_run_attempt"}
                or any(not re.fullmatch(r"[0-9a-f]{40}", repository[key]) for key in ("commit", "tree"))
                or any(not re.fullmatch(r"[0-9]{1,20}", repository[key])
                       for key in set(repository) - {"commit", "tree"})):
            raise ValueError("repository")
        interpreter = report["interpreter"]
        if (set(interpreter) != {"python_version", "dependencies", "source_file_count",
                               "source_sha256", "comparison_driver_sha256", "map_contract_sha256"}
                or not re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}", interpreter["python_version"])
                or interpreter["dependencies"] != DEPENDENCIES
                or not is_int(interpreter["source_file_count"], 512)
                or interpreter["source_file_count"] == 0
                or not is_digest(interpreter["source_sha256"])
                or not is_digest(interpreter["comparison_driver_sha256"])
                or not is_digest(interpreter["map_contract_sha256"])):
            raise ValueError("interpreter")
        stage3 = report["stage3"]
        comparison = report["comparison"]
        native_target, comparison_mode = report["native_target"], report["comparison_mode"]
        validate_comparison(comparison, stage3, native_target, comparison_mode)
        if comparison_mode == MAP_MODE:
            validate_semantic_context(report, image)
        if (stage3["status"] != "ok" or stage3["nonce"] != report["invocation_nonce"]
                or [case["name"] for case in stage3["cases"]] != list(SCENARIOS)
                or [case["name"] for case in comparison["cases"]] != list(SCENARIOS)
                or comparison["status"] not in {"ok", "failed"}):
            raise ValueError("coverage")
        cases = []
        for name, native, compared in zip(SCENARIOS, stage3["cases"], comparison["cases"]):
            payload = payloads[name + ".out"]
            post_create_failure = compared["status"] == "error" and compared["failure_kind"] == POST_CREATE_FAILURE
            if (native["status"] != "ok" or native["output_sha256"] != digest(payload)
                    or native["output_size"] != len(payload)
                    or not is_digest(native["source_sha256"]) or not is_digest(native["module_sha256"])
                    or native["source_sha256"] != stage3["input_sha256"][f"integrational_tests/tests/{name}.bsl"]
                    or not is_int(native["message_count"], 32_768)
                    or (compared["status"] not in {"matched", "mismatched"} and not post_create_failure)
                    or compared["native_sha256"] != native["output_sha256"]
                    or compared["native_size"] != native["output_size"]):
                raise ValueError("case")
            if post_create_failure:
                # Comparison validation requires rejected acceptance and null host
                # hashes/size/mismatch/semantic. Native framing is checked anew.
                validate_native_post_create(payload)
            elif (not is_digest(compared["interpreter_sha256"])
                    or not is_int(compared["interpreter_size"], MAX_FILE)
                    or (compared["status"] == "matched") != (compared["interpreter_sha256"] == native["output_sha256"]
                        and compared["interpreter_size"] == native["output_size"])):
                raise ValueError("case")
            cases.append({"name": name, "file": name + ".out",
                          **{key: native[key] for key in ("source_sha256", "module_sha256",
                              "output_sha256", "output_size", "message_count")},
                          "comparison_status": compared["status"],
                          "interpreter_sha256": compared["interpreter_sha256"],
                          "interpreter_size": compared["interpreter_size"],
                          "mismatch": compared["mismatch"],
                          "acceptance_status": compared["acceptance_status"],
                          "semantic": compared["semantic"]})
        if (comparison["status"] == "ok") != all(case["comparison_status"] == "matched" for case in cases):
            raise ValueError("comparison")
        metadata = {"schema": "native-1c-outputs-v2", "image": image, "platform": "linux/amd64",
                    "runtime_version": report["runtime_version"], "runtime_version_source": "SystemInfo.AppVersion",
                    "invocation_nonce": report["invocation_nonce"], "repository": repository,
                    "interpreter": interpreter, "configured_timezone": "Etc/UTC", "configured_native_locale": "ru_RU",
                    "container_cleanup_verified": True, "private_payloads_removed": True,
                    "windows_goldens_unchanged": True, "comparison_status": comparison["status"],
                    "native_target": native_target, "comparison_mode": comparison_mode,
                    "acceptance_status": comparison["acceptance_status"], "cases": cases}
        if "client_async" in report.get("stage3", {}):
            measurement = validate_client_async(report["stage3"]["client_async"], ASYNC_EXPECTED_IDENTITY["template"], ASYNC_EXPECTED_IDENTITY["modules"])
            if measurement.get("status") != "ok":
                raise ValueError("async measurement incomplete")
            metadata["client_async"] = measurement
            metadata["client_async_measurement_completed"] = True
            metadata["client_async_parity_claimed"] = False
            if "async_comparison" in report:
                validate_semantic_context(report, image)
                metadata["async_comparison"] = validate_async_comparison(report["async_comparison"])
                metadata["client_async_parity_claimed"] = bool(
                    metadata["async_comparison"]["status"] == "matched"
                    and comparison["acceptance_status"] == "accepted")
            metadata["purpose"] = "client-async-language-measurement-v1"
        if stage3.get("schema") == 9:
            if (stage3.get("preprocessor_status") != "matched"
                    or stage3.get("compilation_profile") != PREPROCESSOR_COMPILATION_PROFILE
                    or report.get("preprocessor_host_profile") != PREPROCESSOR_COMPILATION_PROFILE):
                raise ValueError("preprocessor runtime incomplete")
            validate_client_probe(stage3["client_probe"], PREPROCESSOR_SOURCE_SHA256,
                                  PREPROCESSOR_MODULE_SHA256, infobase_allowed=True,
                                  preprocessor_allowed=True, preprocessor_runtime=True)
            if stage3["client_probe"].get("preprocessor_profile") != PREPROCESSOR_RUNTIME_TOKEN:
                raise ValueError("preprocessor runtime missing")
            metadata["purpose"] = "client-preprocessor-runtime-v1"
            metadata["compilation_profile"] = PREPROCESSOR_COMPILATION_PROFILE
            metadata["preprocessor_parity_claimed"] = bool(comparison["acceptance_status"] == "accepted"
                and ("client_async" not in stage3 or report.get("async_comparison", {}).get("status") == "matched"))
        if stage3.get("schema") == 5:
            if stage3.get("preprocessor_status") != "observed":
                raise ValueError("preprocessor observation incomplete")
            validate_client_probe(stage3["client_probe"], PREPROCESSOR_SOURCE_SHA256,
                                  PREPROCESSOR_MODULE_SHA256, infobase_allowed=True,
                                  preprocessor_allowed=True)
            validate_preprocessor_profile(stage3["client_probe"].get("preprocessor_profile"))
            metadata["purpose"] = "client-preprocessor-observation-v1"
            metadata["preprocessor_parity_claimed"] = False
        raw = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(raw) > MAX_REPORT:
            raise ValueError("limit")
        return {**payloads, "provenance.json": raw}
    except (KeyError, TypeError, ValueError, UnicodeError, FullError):
        raise FullError("native_artifact_evidence_invalid") from None


def _artifact_directory(path: Path) -> int:
    """Pin every directory without following any symlink, including ancestors."""
    directory = os.open(path.absolute().anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.absolute().parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def _verify_artifact_directory(path: Path, descriptor: int) -> None:
    visible = _artifact_directory(path)
    try:
        expected, actual = os.fstat(descriptor), os.fstat(visible)
        if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
            raise FullError("native_artifact_directory_changed")
    finally:
        os.close(visible)


def _rename_artifact_exclusive(parent: int, source: str, destination: str) -> None:
    # POSIX rename replaces empty destinations. Linux RENAME_NOREPLACE instead
    # atomically refuses *any* existing target, even one raced into place.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise FullError("native_artifact_atomic_rename_unavailable")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, source.encode("ascii"), parent, destination.encode("ascii"), 1) != 0:
        raise FullError("native_artifact_promotion_failed")


def export_output_artifact(root: Path, files: dict[str, bytes]) -> None:
    """Publish one complete directory atomically; Linux only, no replace fallback."""
    if (not sys.platform.startswith("linux") or list(files) != list(ARTIFACT_FILES)
            or any(type(value) is not bytes for value in files.values())
            or any(len(files[name]) > MAX_FILE for name in ARTIFACT_FILES[:-1])
            or sum(len(files[name]) for name in ARTIFACT_FILES[:-1]) > MAX_TOTAL
            or not 0 < len(files["provenance.json"]) <= MAX_REPORT):
        raise FullError("native_artifact_export_invalid")
    root_fd = parent_fd = stage_fd = None
    staging = ".native-outputs-" + uuid.uuid4().hex
    created = promoted = False
    failure = None
    cleanup_failed = False
    try:
        root_fd = _artifact_directory(root)
        try:
            os.mkdir("native-smoke", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        parent_fd = os.open("native-smoke", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        # Early refusal is useful; the atomic rename below also closes the race.
        try:
            os.stat("native-outputs", dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FullError("native_artifact_target_exists")
        os.mkdir(staging, mode=0o700, dir_fd=parent_fd)
        created = True
        stage_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        for name in ARTIFACT_FILES:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=stage_fd)
            with os.fdopen(fd, "wb") as stream:
                stream.write(files[name])
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o400)
        if set(os.listdir(stage_fd)) != set(ARTIFACT_FILES):
            raise FullError("native_artifact_files_invalid")
        for name in ARTIFACT_FILES:
            if read_regular(root / "native-smoke" / staging / name, MAX_REPORT if name == "provenance.json" else MAX_FILE) != files[name]:
                raise FullError("native_artifact_files_invalid")
        os.fsync(stage_fd)
        _verify_artifact_directory(root, root_fd)
        _verify_artifact_directory(root / "native-smoke", parent_fd)
        _verify_artifact_directory(root / "native-smoke" / staging, stage_fd)
        _rename_artifact_exclusive(parent_fd, staging, "native-outputs")
        promoted = True
        # Actions opens visible paths later, not our descriptors. A swapped
        # ancestor or staging path must never produce the upload-ready signal.
        _verify_artifact_directory(root, root_fd)
        _verify_artifact_directory(root / "native-smoke", parent_fd)
        _verify_artifact_directory(root / ARTIFACT_DIRECTORY, stage_fd)
        if set(os.listdir(stage_fd)) != set(ARTIFACT_FILES):
            raise FullError("native_artifact_files_invalid")
        for name in ARTIFACT_FILES:
            if read_regular(root / ARTIFACT_DIRECTORY / name, MAX_REPORT if name == "provenance.json" else MAX_FILE) != files[name]:
                raise FullError("native_artifact_files_invalid")
        _verify_artifact_directory(root / "native-smoke", parent_fd)
        _verify_artifact_directory(root / ARTIFACT_DIRECTORY, stage_fd)
    except OSError:
        failure = FullError("native_artifact_export_failed")
    except BaseException as error:
        failure = error
    finally:
        try:
            if failure is not None and created and stage_fd is not None:
                # Remove only our pinned directory's fixed files, never a
                # replacement directory reached through a changed visible path.
                for name in ARTIFACT_FILES:
                    try:
                        os.unlink(name, dir_fd=stage_fd)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        cleanup_failed = True
                try:
                    selected = "native-outputs" if promoted else staging
                    visible = os.stat(selected, dir_fd=parent_fd, follow_symlinks=False)
                    pinned = os.fstat(stage_fd)
                    if (visible.st_dev, visible.st_ino) != (pinned.st_dev, pinned.st_ino):
                        cleanup_failed = True
                    else:
                        os.rmdir(selected, dir_fd=parent_fd)
                except OSError:
                    cleanup_failed = True
        finally:
            for descriptor in (stage_fd, parent_fd, root_fd):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        cleanup_failed = True
    if cleanup_failed:
        if failure is None:
            failure = FullError("native_artifact_cleanup_unverified")
        failure.cleanup_error = "native_artifact_cleanup_unverified"
    if failure is not None:
        raise failure from None


def verify_output_artifact(root: Path, expected_hashes: dict[str, str]) -> None:
    """Recheck the exact visible upload tree immediately before signaling readiness."""
    directory = None
    try:
        if set(expected_hashes) != set(ARTIFACT_FILES) or not all(is_digest(value) for value in expected_hashes.values()):
            raise ValueError("hashes")
        target = root / ARTIFACT_DIRECTORY
        directory = _artifact_directory(target)
        if set(os.listdir(directory)) != set(ARTIFACT_FILES):
            raise ValueError("coverage")
        total = 0
        for name in ARTIFACT_FILES:
            raw = read_regular(target / name, MAX_REPORT if name == "provenance.json" else MAX_FILE)
            if digest(raw) != expected_hashes[name]:
                raise ValueError("identity")
            if name != "provenance.json":
                total += len(raw)
        if total > MAX_TOTAL or set(os.listdir(directory)) != set(ARTIFACT_FILES):
            raise ValueError("aggregate or coverage")
        _verify_artifact_directory(target, directory)
    except (OSError, ValueError, TypeError, FullError):
        raise FullError("native_artifact_final_verification_failed") from None
    finally:
        if directory is not None:
            os.close(directory)


# This reads only reviewed literal data from a trusted staged input. It never
# imports or executes the staged Python to reconstruct the native async module.
def async_source_identity(source: bytes) -> dict:
    import ast
    try:
        tree = ast.parse(source.decode('utf-8'))
        names = {'ASYNC_TEMPLATE', 'ASYNC_CASE_SOURCES'}
        found = {}
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else []
            for target in targets:
                if isinstance(target, ast.Name) and target.id in names:
                    if len(targets) != 1 or target.id in found:
                        raise ValueError('duplicate async source')
                    value = node.value
                    if target.id == 'ASYNC_TEMPLATE':
                        if not isinstance(value, ast.Constant) or type(value.value) is not str:
                            raise ValueError('async template literal')
                        found[target.id] = value.value
                    else:
                        if (not isinstance(value, ast.Tuple) or len(value.elts) != 8
                                or any(not isinstance(item, ast.Constant) or type(item.value) is not str for item in value.elts)):
                            raise ValueError('async cases literal')
                        found[target.id] = tuple(item.value for item in value.elts)
        if set(found) != names:
            raise ValueError('async source missing')
        template, cases = found['ASYNC_TEMPLATE'], found['ASYNC_CASE_SOURCES']
        if any(template.count(token) != 1 for token in ('__ASYNC_CASE_ID__', '__ASYNC_CASE_SOURCE__')):
            raise ValueError('async placeholders')
        if any('__ASYNC_CASE_' in case for case in cases):
            raise ValueError('async nested placeholder')
        fixture_hash = digest(json.dumps([template,cases],ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        if fixture_hash != '83a6e22dbb4788498985e51e06ea610d2a9bc95702852da396cb6d7779bf1c5a':
            raise ValueError('async fixture not pinned')
        modules = [generated_module(template.replace('__ASYNC_CASE_ID__', str(i)).replace('__ASYNC_CASE_SOURCE__', case).encode('utf-8')) for i, case in enumerate(cases)]
        identity = {'template': digest(template.encode('utf-8')), 'modules': [digest(module) for module in modules]}
        if identity != ASYNC_EXPECTED_IDENTITY:
            raise ValueError('async module pins')
        return identity
    except (SyntaxError, UnicodeError, TypeError, ValueError):
        raise FullError('native_artifact_evidence_invalid') from None
# Independent host verifier for client-async finite protocol v1.
# No stage Python is executed or imported. Only trusted literal source is extracted elsewhere.
HOST_ASYNC_FAILURES = ('none', 'prerequisites_failed', 'stale_evidence', 'invalid_input', 'invalid_result', 'invalid_dump_result', 'artifact_missing', 'output_mismatch', 'output_limit', 'module_mismatch', 'timeout', 'process_failed', 'unexpected_failure', 'export_failed', 'unsupported_observation')
HOST_ASYNC_SLOTS = (4, 3, 5, 3, 4, 7, 3, 3)
HOST_ASYNC_BASE_EVENTS = ((10, 11, 12, 13, 14, 15, 16, 17, 18), (10, 11, 12, 13, 14, 15, 16, 17, 25, 26), (10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28), (10, 13, 16), (10, 11, 12, 13, 14, 15, 16, 19), (10, 11, 12, 13, 14, 15, 16), (10, 11, 12), (10, 11, 12, 13, 14, 15, 16, 17, 18))
HOST_ASYNC_EDGES = (((10, 11), (11, 12), (10, 13), (13, 14), (12, 14), (14, 15), (15, 16), (16, 17), (17, 18)), ((10, 11), (11, 12), (12, 25), (25, 26), (26, 13), (13, 14), (14, 17), (10, 15), (15, 16), (16, 17)), ((10, 11), (11, 12), (12, 25), (25, 26), (26, 13), (13, 14), (14, 22), (10, 15), (15, 16), (16, 17), (17, 18), (18, 27), (27, 28), (28, 19), (19, 20), (20, 23), (16, 21), (21, 22), (22, 23), (23, 24)), ((10, 11), (10, 12), (11, 13), (12, 13), (13, 14), (13, 15), (14, 16), (15, 16), (16, 17), (16, 18)), ((10, 11), (11, 12), (12, 13), (11, 14), (14, 16), (10, 15), (15, 16), (16, 17), (16, 18), (17, 19), (18, 19), (13, 19)), ((10, 11), (11, 12), (12, 13), (13, 14), (14, 16), (10, 15), (15, 16)), ((10, 11), (11, 12), (10, 13), (12, 14), (13, 15), (15, 16), (15, 17), (12, 16), (12, 17), (16, 18), (17, 18), (18, 19), (18, 20), (12, 19), (12, 20)), ((10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (17, 18)))


def _host_async_require(condition, label):
    if not condition:
        raise ValueError('async ' + label)


def _host_async_number(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _host_async_sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_async_case_observation(case_id, trace, values, errors):
    require = _host_async_require
    number = _host_async_number
    require(number(case_id,0,7),'case')
    require(type(trace) is list and 5 <= len(trace) <= 24,'trace length')
    require(all(number(token,0,28) for token in trace),'event type')
    require(trace[:2] == [0,1] and trace[-3:] == [2,3,4],'root boundaries')
    require(len(trace) == len(set(trace)),'duplicate event')
    require(type(values) is list and len(values) == HOST_ASYNC_SLOTS[case_id],'slots')
    require(type(errors) is list and len(errors) <= 3,'errors')
    for pair in values:
        require(type(pair) is list and len(pair) == 2,'value pair')
        tag,payload = pair
        require(number(tag,0,7) and number(payload,-999999,999999),'value type')
        ranges = {0:(0,0),1:(0,0),2:(0,0),3:(0,1),4:(-999999,999999),5:(0,7),6:(0,0),7:(0,2)}
        require(ranges[tag][0] <= payload <= ranges[tag][1],'value payload')
    for entry in errors:
        require(type(entry) is list and len(entry) == 7,'error row')
        require(number(entry[0],0,6) and all(number(x,0,4) for x in entry[1:4])
                and all(number(x,0,3) for x in entry[4:6]) and _host_async_sha(entry[6]),'error fields')
    tags = [v[0] for v in values]
    selected = set(HOST_ASYNC_BASE_EVENTS[case_id]) | {0,1,2,3,4}
    absent_slots = set()
    if case_id == 3:
        for slot,returned,rejected in ((0,11,12),(1,14,15),(2,17,18)):
            selected.add(rejected if tags[slot] == 7 else returned)
    if case_id == 4:
        if tags[1] == 6:
            selected.add(17)
        else:
            selected.add(18)
            absent_slots.add(2)
    if case_id == 6:
        if tags[0] == 7:
            selected.add(14)
            absent_slots = {1,2}
        else:
            selected |= {13,15,18,17 if tags[1] == 7 else 16,20 if tags[2] == 7 else 19}
    require(set(trace) == selected,'conditional inventory')
    seen = set()
    for token in trace:
        for before,after in HOST_ASYNC_EDGES[case_id]:
            if after == token and before in selected:
                require(before in seen,'causal order')
        seen.add(token)
    phases = {3:{0:3,1:4,2:5},6:{0:0,1:1,2:2},7:{2:6}}.get(case_id,{})
    next_error = 0
    for index,(tag,payload) in enumerate(values):
        require((tag == 0) == (index in absent_slots),'not-executed slot')
        if tag == 7:
            require(index in phases and payload == next_error and next_error < len(errors),'error ordinal')
            require(errors[next_error][0] == phases[index],'error phase')
            next_error += 1
    require(next_error == len(errors),'unreferenced error')
    require(case_id != 7 or tags[2] == 7,'handler observation')
    return trace,values,errors


def _host_async_diagnostic(value):
    _host_async_require(type(value) is dict and set(value) == {'stage','reason','unexpected_count','zombie_count','classes'},'diagnostic keys')
    _host_async_require(type(value['stage']) is str and type(value['reason']) is str,'diagnostic enums')
    return validate_process_diagnostics(value)


def validate_async_marker_failure(data):
    """Independent finite failure-only hint validation, never marker acceptance."""
    value = data['marker_validation_failure']
    if value is None: return
    require, number = _host_async_require, _host_async_number
    hint = data.get('failure_diagnostics')
    require(data.get('status') == 'failed' and data.get('failure_kind') == 'invalid_result', 'marker failure applicability')
    require(type(hint) is list and len(hint) == 4 and hint[0] == 4, 'marker failure stage')
    require(type(value) is list and len(value) == 4, 'marker failure fields')
    phase,site,descriptor,locator = value
    require(number(phase,0,1) and number(site,1,42) and number(descriptor,0,3) and number(locator,0,31), 'marker failure codes')
    require(hint[phase+1] == 2 and (phase == 0 or hint[1] == 3), 'marker failure observation')
    rows = data.get('cases')
    require(type(rows) is list and len(rows) == 8, 'marker failure rows')
    failures = [index for index,row in enumerate(rows) if type(row) is list and len(row) == 8 and row[1:3] == [2,4]]
    require(len(failures) == 1, 'marker failure case')
    case_id = failures[0]
    require(phase == 1 or site in set(range(1,10)) | {42}, 'marker failure phase')
    if site in range(14,27):
        require(descriptor < 3, 'marker descriptor ordinal')
        allowed = ({31} if site in (14,26) else {0} if site == 15 else {1} if site == 16
                   else set(range(2,10)) | ({31} if site == 25 else set()))
        require(locator in allowed, 'marker descriptor field')
    elif site in (34,35):
        require(descriptor < 3 and locator in range(HOST_ASYNC_SLOTS[case_id]), 'marker reference locator')
    else:
        require(descriptor == 3, 'marker descriptor sentinel')
        if site in (29,38,39): allowed = set(range(29))
        elif site in (31,32,33,37): allowed = set(range(HOST_ASYNC_SLOTS[case_id]))
        elif site == 40: allowed = set(range(len(HOST_ASYNC_EDGES[case_id])))
        elif site == 41: allowed = {2} if case_id == 7 else set()
        else: allowed = {31}
        require(locator in allowed, 'marker field locator')


def validate_async_failure_diagnostics(data):
    validate_async_marker_failure(data)
    value = data['failure_diagnostics']
    if value is None:
        return
    require = _host_async_require
    number = _host_async_number
    require(data.get('status') in ('failed', 'inconclusive'), 'failure diagnostic applicability')
    require(type(value) is list and len(value) == 4, 'failure diagnostic fields')
    stage, entered, completed, category = value
    require(number(stage, 0, 5) and number(entered, 0, 3)
            and number(completed, 0, 3) and number(category, 0, 43), 'failure diagnostic codes')
    require(stage >= 3 or (entered == 0 and completed == 0), 'failure marker applicability')
    require(stage != 0 or category == 0, 'failure log applicability')
    require(category < 13 or stage >= 3, 'entry log applicability')
    require(completed != 3 or entered == 3, 'failure marker order')


def validate_client_async(data, template_hash, module_hashes):
    require = _host_async_require
    number = _host_async_number
    require(_host_async_sha(template_hash) and type(module_hashes) in (tuple,list)
            and len(module_hashes) == 8 and all(_host_async_sha(x) for x in module_hashes),'trusted hashes')
    require(type(data) is dict and set(data) == {'version','status','failure_kind','template_sha256','continuity_sha256','process_diagnostics','failure_diagnostics','marker_validation_failure','cases'},'record fields')
    require(number(data['version'],2,2),'version')
    require(type(data['status']) is str and data['status'] in ('not_started','ok','failed','inconclusive'),'status')
    require(type(data['failure_kind']) is str and data['failure_kind'] in HOST_ASYNC_FAILURES,'reason')
    require(data['template_sha256'] is None or _host_async_sha(data['template_sha256']) and data['template_sha256'] == template_hash,'template identity')
    require(_host_async_sha(data['continuity_sha256']) if data['status'] == 'ok' else data['continuity_sha256'] is None,'continuity anchor')
    diag = _host_async_diagnostic(data['process_diagnostics'])
    validate_async_failure_diagnostics(data)
    require(type(diag['stage']) is str and type(diag['reason']) is str,'diagnostic types')
    rows = data['cases']
    require(type(rows) is list and len(rows) == 8,'eight cases')
    states = []
    for case_id,row in enumerate(rows):
        require(type(row) is list and len(row) == 8,'eight fields')
        cid,status,failure,module,bits,trace,values,errors = row
        require(number(cid,case_id,case_id) and number(status,0,3) and number(failure,0,14) and number(bits,0,63),'row codes')
        require(module is None or _host_async_sha(module) and module == module_hashes[case_id],'module identity')
        states.append(status)
        if status == 1:
            require(failure == 0 and bits == 63 and module == module_hashes[case_id],'observed proof')
            validate_async_case_observation(case_id,trace,values,errors)
        else:
            require(bits == 0 and all(type(x) is list and x == [] for x in (trace,values,errors)),'failed private boundary')
            if status == 0:
                require(failure == 1 and module is None,'unreached')
            elif status == 2:
                require(1 <= failure <= 13,'failed reason')
            else:
                require(failure == 14 and module == module_hashes[case_id],'inconclusive')
    if data['status'] == 'not_started':
        require(states == [0]*8 and data['failure_kind'] == 'prerequisites_failed'
                and data['template_sha256'] is None and diag['stage'] == 'not_checked' and diag['reason'] == 'none','unstarted aggregate')
    elif data['status'] == 'ok':
        require(states == [1]*8 and data['failure_kind'] == 'none' and data['template_sha256'] == template_hash
                and diag['stage'] == 'after_exit' and diag['reason'] == 'none','completed aggregate')
    else:
        failure_state = 3 if data['status'] == 'inconclusive' else 2
        require(states.count(failure_state) == 1,'single failure')
        index = states.index(failure_state)
        require(states == [1]*index + [failure_state] + [0]*(7-index),'failure prefix')
        require(data['failure_kind'] == HOST_ASYNC_FAILURES[rows[index][2]],'aggregate reason')
        if index or rows[index][3] is not None:
            require(data['template_sha256'] == template_hash,'aggregate identity')
    return data


def decode_async_wire(record):
    if type(record) is not dict or not {'process_diagnostics', 'failure_diagnostics', 'marker_validation_failure'} <= set(record):
        raise ValueError('async wire')
    validate_async_failure_diagnostics(record)
    wire = record['process_diagnostics']
    if (type(wire) is not list or len(wire) != 5 or type(wire[4]) is not list or len(wire[4]) != 7):
        raise ValueError('async process wire')
    names = ('native','display','session_bus','shell','python','other','unreadable')
    diagnostic = _host_async_diagnostic({'stage':wire[0],'reason':wire[1],'unexpected_count':wire[2],
            'zombie_count':wire[3],'classes':dict(zip(names,wire[4]))})
    if type(diagnostic['stage']) is not str or type(diagnostic['reason']) is not str:
        raise ValueError('async process wire type')
    return {**record,'process_diagnostics':diagnostic}


def encode_async_wire(record):
    if type(record) is not dict or not {'process_diagnostics', 'failure_diagnostics', 'marker_validation_failure'} <= set(record):
        raise ValueError('async wire')
    validate_async_failure_diagnostics(record)
    diagnostic = _host_async_diagnostic(record['process_diagnostics'])
    names = ('native','display','session_bus','shell','python','other','unreadable')
    encoded = {**record,'process_diagnostics':[diagnostic['stage'],diagnostic['reason'],diagnostic['unexpected_count'],
            diagnostic['zombie_count'],[diagnostic['classes'][name] for name in names]]}
    if decode_async_wire(encoded) != record:
        raise ValueError('async wire roundtrip')
    return encoded


def validate_async_private_descriptor(value):
    """Independent selected-field check. Not a whole ErrorInfo serializer."""
    require = _host_async_require
    number = _host_async_number
    fields = ('description','code','additional','category','cause','module','line','source')
    require(type(value) is dict and set(value) == {'schema','phase',*fields},'private keys')
    require(number(value['schema'],1,1) and number(value['phase'],0,6),'private version')
    forms = ({0,1,2,3,4},{0,1,2,3,4},{0,1,2,3,4},{0,1,3,5},{0,1,5},{0,2},{0,1,3},{0,2})
    for field,allowed in zip(fields,forms):
        pair = value[field]
        require(type(pair) is list and len(pair) == 2 and number(pair[0],0,5) and pair[0] in allowed,'private tagged field')
        tag,payload = pair
        if tag < 2:
            require(payload is None,'private absent')
        elif tag == 2:
            require(type(payload) is str and len(payload) <= 512,'private text')
            require(len(payload.encode('utf-8')) <= 512,'private text bytes')
        elif tag == 3:
            require(number(payload,0,999999),'private integer')
        elif tag == 4:
            require(type(payload) is bool,'private boolean')
        else:
            require(number(payload,0,1) and payload == (1 if field == 'category' else 0),'private native type')
    raw = json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    require(len(raw) <= 4096,'private descriptor size')
    result = [value['phase']]
    for field,literal in zip(fields,('ASYNC-REJECT','ASYNC-CODE','ASYNC-DETAIL')):
        tag,payload = value[field]
        result.append(4 if tag == 0 else 0 if tag == 1 else 1 if payload == '' and tag == 2 else 2 if payload == literal and tag == 2 else 3)
    category = value['category']
    result.append(3 if category[0] == 0 else 0 if category[0] == 1 else 1 if category == [3,1] else 2)
    result.append({0:3,1:0,5:1}[value['cause'][0]])
    result.append(hashlib.sha256(raw).hexdigest())
    return result


def validate_async_marker_raw(raw, nonce, case_id, phase):
    """Read with the host's duplicate-key/depth/UTF-8/size security helper."""
    require = _host_async_require
    require(type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}',nonce) is not None
            and _host_async_number(case_id,0,7) and phase in ('entered','completed'),'marker inputs')
    data = strict_json(raw,16_384)
    keys = {'schema','nonce','case','phase','witness'}
    if phase == 'completed':
        keys |= {'status','failure','trace','values','errors'}
    require(type(data) is dict and set(data) == keys,'marker keys')
    require(_host_async_number(data['schema'],1,1) and _host_async_number(data['case'],case_id,case_id)
            and type(data['nonce']) is str and data['nonce'] == nonce and type(data['phase']) is str and data['phase'] == phase
            and type(data['witness']) is str and data['witness'] == 'client','marker binding')
    if phase == 'entered':
        return data
    require(_host_async_number(data['status'],1,3) and _host_async_number(data['failure'],0,14),'marker codes')
    if data['status'] == 1:
        require(data['failure'] == 0 and type(data['errors']) is list and len(data['errors']) <= 3,'marker success')
        errors = [validate_async_private_descriptor(x) for x in data['errors']]
        validate_async_case_observation(case_id,data['trace'],data['values'],errors)
        return {**data,'errors':errors}
    require((data['status'] == 2 and 1 <= data['failure'] <= 13) or (data['status'] == 3 and data['failure'] == 14),'marker failure')
    require(all(type(data[key]) is list and data[key] == [] for key in ('trace','values','errors')),'marker failed privacy')
    return data


ASYNC_EXPECTED_IDENTITY = {'template': '4177f7bc3e4690e6a67e48af06db4dba78405bb76f16151867fd006c35ba713f', 'modules': ['9c35b55df6f304166f83535490b7cffe51f0bac3383663fa4d2c201dfd4f3317', '2f1521d54fef7ecd73f8dce7f36f983111ff2fdb98112a89bd47f01988072676', '6e1a01c33d77681426c6d3f0c0d648fde353514edad381ba2c6bd2b586284959', 'a3959ce4beb9fe01cc1d3f3416bdb2ac7ef56ecb9cdcce11c0b41d96f347bc78', 'a5a2d09e4a7be7749121b0a26c30670bcd122d76ae81e6b5158fdb9de7ff2b1b', '761b8ed069ac9451cd9eb918c5e7e7d6d84a9d380155bc56b36ffd05717d76f6', '395dfd07a0171d361fd5c029e6a2400ef8d72097f506e073c75fedb1bc3105f4', '3ac1cd874da474e939006034f5a7216e7d2a26e9f9a9fb87f0c0813b1968a45a']}

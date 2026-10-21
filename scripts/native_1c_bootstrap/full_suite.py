"""Bounded, private stage-three execution and live-container output transport.

This helper never prints native diagnostics. The six payloads are the unchanged
launcher's saved bytes, not a replacement reference synthesized by the interpreter.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time

from evidence_gates import require_epf, require_zero_result
from inject_modules import DraftError

SCENARIOS = ('collections', 'dates', 'functions', 'numbers', 'strings', 'values')
WIRE_SCHEMA = 'native-1c-full-v1'
MAX_REPORT = 32_768
MAX_STAGE_REPORT = 8_192
MAX_OUTPUT = 1_048_576
MAX_TOTAL = 2_097_152
MAX_TRANSPORT = 3_145_728
MAX_RESULT = 2_097_152
MAX_MESSAGES = 32_768
INPUT_FILES = {
    'scripts/native_1c_smoke_probe.sh': 'probe.sh',
    **{f'scripts/native_1c_bootstrap/{name}': f'bootstrap/{name}' for name in (
        'run_stage.py', 'inject_modules.py', 'evidence_gates.py', 'diagnostics.py',
        'simple_smoke.bsl', 'modules/SessionModule.bsl',
        'modules/ManagedApplicationModule.bsl', 'full_suite.py')},
    'integrational_tests/test_launcher.py': 'launcher/test_launcher.py',
    **{f'integrational_tests/launcher_1c/{name}': f'launcher/launcher_1c/{name}' for name in (
        'Launcher.xml', 'Launcher/Ext/ObjectModule.bsl', 'Launcher/Forms/Main.xml',
        'Launcher/Forms/Main/Ext/Form.xml', 'Launcher/Forms/Main/Ext/Form/Module.bsl',
        'TestModule.xml', 'TestModule/Ext/ObjectModule.bsl')},
    **{f'integrational_tests/tests/{name}.bsl': f'scenarios/{name}.bsl'
       for name in SCENARIOS},
}
FAILURE_KINDS = {'none', 'prerequisites_failed', 'stale_evidence', 'invalid_input',
                 'invalid_result', 'invalid_dump_result', 'artifact_missing',
                 'output_mismatch', 'output_limit', 'module_mismatch', 'timeout',
                 'process_failed', 'unexpected_failure', 'export_failed'}


class FullError(Exception):
    """Only a fixed, non-sensitive reason is allowed across the boundary."""

    def __init__(self, kind: str):
        self.kind = kind if kind in FAILURE_KINDS else 'unexpected_failure'
        super().__init__(self.kind)


def valid_nonce(nonce: object) -> bool:
    return type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}', nonce) is not None


def empty_report(nonce: str) -> dict:
    if not valid_nonce(nonce):
        raise FullError('invalid_input')
    return {'schema': 1, 'nonce': nonce, 'status': 'not_started',
            'failure_kind': 'prerequisites_failed', 'failed_case': None,
            'input_sha256': {}, 'cases': [
                {'name': name, 'status': 'not_started', 'source_sha256': None,
                 'module_sha256': None, 'output_sha256': None,
                 'output_size': None, 'message_count': None} for name in SCENARIOS]}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def absent(*paths: Path) -> None:
    if any(path.exists() or path.is_symlink() for path in paths):
        raise FullError('stale_evidence')


def _open_no_follow(path: Path) -> int:
    """Walk each directory through descriptors on the actual Linux executor."""
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
    # Only offline Windows tests use this branch; real execution is Linux only.
    # A final descriptor/path identity check below also rejects replaced files.
    if any(parent.is_symlink() for parent in path.parents) or path.is_symlink():
        raise FullError('artifact_missing')
    return os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))


def secure_bytes(path: Path, limit: int, *, allow_empty: bool = False) -> bytes:
    try:
        descriptor = _open_no_follow(path)
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not (0 if allow_empty else 1) <= before.st_size <= limit):
                raise FullError('artifact_missing')
            chunks = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65_536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            identity = lambda value: (value.st_dev, value.st_ino, value.st_mode,
                                      value.st_nlink, value.st_size,
                                      value.st_mtime_ns, value.st_ctime_ns)
            if identity(before) != identity(after):
                raise FullError('artifact_missing')
            # Detect an unlinked/replaced path even if the open descriptor survived.
            current = path.lstat()
            if identity(after) != identity(current):
                raise FullError('artifact_missing')
            data = b''.join(chunks)
            if len(data) != before.st_size or len(data) > limit:
                raise FullError('artifact_missing')
            return data
        finally:
            os.close(descriptor)
    except (OSError, ValueError, OverflowError):
        raise FullError('artifact_missing') from None


def strict_json(data: bytes, *, max_depth: int = 8) -> object:
    """Reject excessive nesting before json.loads can recursively allocate it."""
    try:
        text = data.decode('utf-8-sig')
        depth, quoted, escaped = 0, False, False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == '\\':
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in '[{':
                depth += 1
                if depth > max_depth:
                    raise ValueError
            elif character in ']}':
                depth -= 1
                if depth < 0:
                    raise ValueError
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        def number(value):
            if len(value) > 10:
                raise ValueError
            return int(value)
        def forbidden(value):
            raise ValueError
        return json.loads(text, object_pairs_hook=pairs, parse_int=number,
                          parse_float=forbidden, parse_constant=forbidden)
    except (ValueError, UnicodeError, RecursionError):
        raise FullError('invalid_result') from None


def parse_native_result(data: bytes) -> tuple[list[str], str]:
    if len(data) > MAX_RESULT:
        raise FullError('invalid_result')
    value = strict_json(data, max_depth=3)
    if (type(value) is not dict or set(value) != {'messages', 'error'}
            or type(value['messages']) is not list
            or len(value['messages']) > MAX_MESSAGES
            or any(type(item) is not str for item in value['messages'])
            or value['error'] != '' or type(value['error']) is not str):
        raise FullError('invalid_result')
    try:
        if sum(len(item.encode('utf-8')) for item in value['messages']) > MAX_OUTPUT:
            raise FullError('output_limit')
        # Includes LF-per-message, including empty messages; no prefix acceptance.
        serialize_messages(value['messages'])
    except UnicodeError:
        raise FullError('invalid_result') from None
    return value['messages'], ''


def read_native_result(path: Path) -> tuple[list[str], str]:
    return parse_native_result(secure_bytes(path, MAX_RESULT))


def serialize_messages(messages: list[str]) -> bytes:
    try:
        data = ''.join(item.replace('\r\n', '\n').replace('\r', '\n') + '\n'
                       for item in messages).encode('utf-8')
    except UnicodeError:
        raise FullError('invalid_result') from None
    if len(data) > MAX_OUTPUT:
        raise FullError('output_limit')
    return data


def generated_module(source: bytes) -> bytes:
    try:
        return source.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8-sig')
    except UnicodeError:
        raise FullError('invalid_input') from None


def input_hashes(inputs: Path) -> dict[str, str]:
    result = {}
    for source, target in INPUT_FILES.items():
        result[source] = digest(secure_bytes(inputs / target, MAX_OUTPUT))
    return result


def _stop_group(child: subprocess.Popen) -> None:
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()
    # --init adopts/reaps descendants. Do not proceed while a process group lives.
    deadline = time.monotonic() + 5
    while True:
        try:
            os.killpg(child.pid, 0)
        except ProcessLookupError:
            return
        if time.monotonic() >= deadline:
            raise FullError('process_failed')
        time.sleep(0.02)


def run_process(command: list[str], directory: Path, log: Path, timeout: float) -> None:
    if os.name != 'posix' or timeout != 120:
        raise FullError('invalid_input')
    absent(log)
    with log.open('xb') as output:
        with subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                              stdout=output, stderr=subprocess.STDOUT,
                              start_new_session=True) as child:
            try:
                code = child.wait(timeout=120)
            except subprocess.TimeoutExpired:
                try:
                    _stop_group(child)
                finally:
                    raise FullError('timeout') from None
            except BaseException:
                _stop_group(child)
                raise
            _stop_group(child)
    if code:
        raise FullError('process_failed')
    if '/DumpResult' in command:
        result = Path(command[command.index('/DumpResult') + 1])
        data = secure_bytes(result, 128)
        try:
            value = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig').strip()
            if not re.fullmatch(r'[+-]?[0-9]+', value) or int(value) != 0:
                raise ValueError
        except (ValueError, UnicodeError):
            raise FullError('invalid_dump_result') from None


def run_suite(launcher, platform, launcher_epf: Path, root: Path,
              inputs: Path, nonce: str) -> dict:
    report = empty_report(nonce)
    report.update(status='failed', failure_kind='unexpected_failure')
    active = None
    old_reader, old_process, old_build = launcher.read_result, launcher.run_process, launcher.build_epf
    try:
        report['input_sha256'] = input_hashes(inputs)
        absent(root)
        root.mkdir(mode=0o700)
        if platform.timeout != 120 or platform.user != 'NativeSmoke' or platform.password is not None:
            raise FullError('invalid_input')
        # The unchanged launcher must not parse unbounded/permissive JSON first.
        launcher.read_result = read_native_result
        launcher.run_process = run_process
        def build_epf(platform_argument, source_xml, destination):
            # Verify the exact generated source at the compile boundary, not only
            # after execution. This wraps, but never edits, the reviewed launcher.
            module = secure_bytes(source_xml.parent / 'TestModule/Ext/ObjectModule.bsl', MAX_OUTPUT + 3)
            if module != expected_module:
                raise FullError('module_mismatch')
            active['module_sha256'] = digest(module)
            old_build(platform_argument, source_xml, destination)
        launcher.build_epf = build_epf
        total = 0
        for active in report['cases']:
            name = active['name']
            report['failed_case'] = name
            active['status'] = 'failed'
            source = inputs / 'scenarios' / (name + '.bsl')
            source_data = secure_bytes(source, MAX_OUTPUT)
            active['source_sha256'] = digest(source_data)
            if active['source_sha256'] != report['input_sha256'][f'integrational_tests/tests/{name}.bsl']:
                raise FullError('invalid_input')
            expected_module = generated_module(source_data)
            directory, output = root / (name + '-case'), root / (name + '.out')
            absent(directory, output, root / (name + '.err'), output.with_suffix('.out.tmp'))
            launcher.run_case(platform, source, launcher_epf, directory, output)
            # Every artifact is fresh because its exclusive parent was absent.
            require_zero_result(directory / 'TestModule.build-result.txt', 0)
            require_epf(directory / 'TestModule.epf')
            module = secure_bytes(directory / 'src/TestModule/Ext/ObjectModule.bsl', MAX_OUTPUT + 3)
            if module != expected_module:
                raise FullError('module_mismatch')
            active['module_sha256'] = digest(module)
            messages, _ = read_native_result(directory / 'result.json')
            actual = secure_bytes(output, MAX_OUTPUT, allow_empty=True)
            if actual != serialize_messages(messages):
                raise FullError('output_mismatch')
            absent(root / (name + '.err'), directory / 'result.err')
            total += len(actual)
            if total > MAX_TOTAL:
                raise FullError('output_limit')
            active.update(status='ok', output_sha256=digest(actual),
                          output_size=len(actual), message_count=len(messages))
        if input_hashes(inputs) != report['input_sha256']:
            active = None
            report['failed_case'] = None
            raise FullError('invalid_input')
        report.update(status='ok', failure_kind='none', failed_case=None)
    except Exception as error:
        if isinstance(error, FullError):
            kind = error.kind
        elif isinstance(error, DraftError):
            kind = 'invalid_dump_result'
        elif error.__class__.__name__ == 'LaunchError':
            kind = 'timeout' if 'таймаут' in str(error).casefold() else 'process_failed'
        elif isinstance(error, OSError):
            kind = 'artifact_missing'
        else:
            kind = 'unexpected_failure'
        report['failure_kind'] = kind
    finally:
        launcher.read_result, launcher.run_process, launcher.build_epf = old_reader, old_process, old_build
    return report


def write_report(path: Path, report: dict) -> None:
    data = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(data) > MAX_STAGE_REPORT:
        raise FullError('export_failed')
    with path.open('xb') as target:
        target.write(data)


def native_processes_quiet(executable: Path) -> bool:
    """No native process from earlier stages may still be writing evidence."""
    try:
        expected = executable.resolve(strict=True)
        for directory in Path('/proc').iterdir():
            if not directory.name.isdecimal():
                continue
            try:
                target = (directory / 'exe').readlink()
            except FileNotFoundError:
                # A disappeared PID is harmless; an existing uninspectable PID
                # (including an unreaped zombie) is not evidence of quiescence.
                if directory.exists():
                    return False
                continue
            except PermissionError:
                # Kernel/root processes are outside this non-root container user.
                if directory.stat().st_uid == os.geteuid():
                    return False
                continue
            if target == expected or str(target) == str(expected) + ' (deleted)':
                return False
        return True
    except OSError:
        return False


def build_envelope(report: dict, nonce: str, root: Path, *, quiet: bool) -> bytes:
    """Materialize payload only after complete native success; never emit partials."""
    if not valid_nonce(nonce):
        raise FullError('invalid_input')
    outputs = []
    stage = report['stage3']
    if report['status'] == 'ok' and stage['status'] == 'ok':
        try:
            if not quiet or stage['nonce'] != nonce:
                raise FullError('export_failed')
            if [case['name'] for case in stage['cases']] != list(SCENARIOS):
                raise FullError('export_failed')
            total = 0
            for case in stage['cases']:
                if case['status'] != 'ok':
                    raise FullError('export_failed')
                name = case['name'] + '.out'
                data = secure_bytes(root / name, MAX_OUTPUT, allow_empty=True)
                total += len(data)
                if (total > MAX_TOTAL or len(data) != case['output_size']
                        or digest(data) != case['output_sha256']):
                    raise FullError('export_failed')
                outputs.append({'name': name, 'size': len(data), 'sha256': digest(data),
                                'data_b64': base64.b64encode(data).decode('ascii')})
        except (FullError, OSError, KeyError, TypeError):
            outputs = []
            stage.update(status='failed', failure_kind='export_failed', failed_case=None)
            report.update(status='stage3_failed', native_tests_completed=False)
    if len(json.dumps(report, separators=(',', ':'), allow_nan=False).encode('utf-8')) > MAX_REPORT:
        raise FullError('export_failed')
    raw = json.dumps({'schema': WIRE_SCHEMA, 'nonce': nonce, 'report': report,
                      'outputs': outputs}, sort_keys=True, separators=(',', ':'),
                     allow_nan=False).encode('utf-8') + b'\n'
    if len(raw) > MAX_TRANSPORT:
        raise FullError('export_failed')
    return raw

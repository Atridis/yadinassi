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


def empty_report(nonce: str, *, client_probe: bool = False, watchdog_check: bool = False) -> dict:
    if not valid_nonce(nonce) or (watchdog_check and not client_probe):
        raise FullError('invalid_input')
    return {**({'client_probe': empty_client_report()} if client_probe else {}),
            **({'client_watchdog': empty_watchdog_report()} if watchdog_check else {}),
            'schema': 1, 'nonce': nonce, 'status': 'not_started',
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


def input_hashes(inputs: Path, *, client_probe: bool = False) -> dict[str, str]:
    result = {}
    for source, target in {**INPUT_FILES, **({CLIENT_SOURCE: CLIENT_TARGET} if client_probe else {})}.items():
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


def run_process(command: list[str], directory: Path, log: Path, timeout: float,
                *, require_clean_tree: bool = False) -> None:
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
            if require_clean_tree:
                # A zero-exit leader is not completion while descendants remain.
                deadline = time.monotonic() + 5
                while True:
                    try:
                        os.killpg(child.pid, 0)
                    except ProcessLookupError:
                        break
                    if time.monotonic() >= deadline:
                        _stop_group(child)
                        raise FullError('process_failed')
                    time.sleep(0.02)
            else:
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
              inputs: Path, nonce: str, *, client_probe: bool = False, watchdog_check: bool = False) -> dict:
    report = empty_report(nonce, client_probe=client_probe, watchdog_check=watchdog_check)
    report.update(status='failed', failure_kind='unexpected_failure')
    active = None
    old_reader, old_process, old_build = launcher.read_result, launcher.run_process, launcher.build_epf
    try:
        report['input_sha256'] = input_hashes(inputs, client_probe=client_probe)
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
        active = None
        report['failed_case'] = None
        if client_probe:
            report['client_probe'] = run_client_probe(platform, root / 'client-probe', inputs,
                                                       nonce, report['input_sha256'])
            if report['client_probe']['status'] != 'ok':
                raise FullError(report['client_probe']['failure_kind'])
        if watchdog_check:
            report['client_watchdog'] = run_client_watchdog(
                platform, root / 'client-watchdog', inputs, nonce, report['input_sha256'])
            if report['client_watchdog']['status'] != 'ok':
                raise FullError(report['client_watchdog']['failure_kind'])
        if input_hashes(inputs, client_probe=client_probe) != report['input_sha256']:
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


CLIENT_SOURCE = 'scripts/native_1c_bootstrap/client_probe.bsl'
CLIENT_TARGET = 'bootstrap/client_probe.bsl'
CLIENT_MODULE = 'Launcher/Forms/Main/Ext/Form/Module.bsl'
CLIENT_VALUES = [42, 'client-probe', 3, 6]
CLIENT_FLAGS = ('entered', 'completed', 'process_exited', 'quiet', 'witness_verified')
PROCESS_CLASSES = ('native', 'display', 'session_bus', 'shell', 'python', 'other', 'unreadable')


def empty_process_diagnostics() -> dict:
    return {'stage': 'not_checked', 'reason': 'none', 'unexpected_count': 0,
            'zombie_count': 0, 'classes': {key: 0 for key in PROCESS_CLASSES}}


class ClientProcessError(FullError):
    def __init__(self, diagnostics):
        super().__init__('process_failed')
        self.diagnostics = diagnostics


def unexpected_process_diagnostics(identities, stage):
    result = empty_process_diagnostics()
    result.update(stage=stage, reason='unexpected_processes', unexpected_count=len(identities))
    if len(identities) > 256:
        raise FullError('process_failed')
    names = {'/opt/1cv8t/x86_64/8.3.27.1508/1cv8t': 'native',
             '/opt/1cv8t/x86_64/8.3.27.1508/1cv8': 'native',
             '/usr/bin/Xtigervnc': 'display', '/usr/bin/Xvfb': 'display',
             '/usr/bin/dbus-daemon': 'session_bus', '/usr/bin/dbus-launch': 'session_bus',
             '/usr/bin/bash': 'shell', '/usr/bin/dash': 'shell', '/bin/bash': 'shell',
             '/usr/bin/python3.10': 'python'}
    for pid, started in identities:
        directory = Path('/proc') / str(pid)
        category = 'unreadable'
        try:
            raw = (directory / 'stat').read_text()
            fields = raw[raw.rindex(')') + 2:].split()
            if fields[19] != started:
                raise ValueError
            result['zombie_count'] += fields[0] == 'Z'
            category = names.get(str((directory / 'exe').readlink()), 'other')
        except (OSError, ValueError, IndexError):
            pass
        result['classes'][category] += 1
    return result


def empty_client_report() -> dict:
    return {'status': 'not_started', 'failure_kind': 'prerequisites_failed',
            'process_diagnostics': empty_process_diagnostics(),
            'source_sha256': None, 'module_sha256': None, 'roundtrip_sha256': None,
            **{key: False for key in CLIENT_FLAGS}}


def client_marker(path: Path, nonce: str, phase: str) -> dict:
    if not valid_nonce(nonce) or phase not in {'entered', 'completed'}:
        raise FullError('invalid_input')
    value = strict_json(secure_bytes(path, 2048), max_depth=3)
    expected = [] if phase == 'entered' else CLIENT_VALUES
    if (type(value) is not dict
            or set(value) != {'schema', 'nonce', 'phase', 'witness', 'values'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or value['phase'] != phase
            or value['witness'] != 'client' or type(value['values']) is not list
            or len(value['values']) != len(expected)
            or any(type(a) is not type(b) or a != b for a, b in zip(value['values'], expected))):
        raise FullError('invalid_result')
    return value


def client_wiring(root: Path) -> None:
    """Check the actual re-dumped managed form, not a context label in JSON."""
    import xml.etree.ElementTree as ET
    try:
        def elements(path, local):
            tree = ET.fromstring(secure_bytes(root / path, MAX_OUTPUT))
            return [node for node in tree.iter() if node.tag.rsplit('}', 1)[-1] == local]
        defaults = elements('Launcher.xml', 'DefaultForm')
        forms = elements('Launcher/Forms/Main.xml', 'FormType')
        events = elements('Launcher/Forms/Main/Ext/Form.xml', 'Event')
        if (len(defaults) != 1 or defaults[0].text != 'ExternalDataProcessor.Launcher.Form.Main'
                or len(forms) != 1 or forms[0].text != 'Managed'
                or len(events) != 1 or events[0].attrib != {'name': 'OnOpen'}
                or events[0].text != 'ПриОткрытии'):
            raise FullError('module_mismatch')
        # No object-body fallback can perform the calculations.
        body = secure_bytes(root / 'Launcher/Ext/ObjectModule.bsl', MAX_OUTPUT,
                            allow_empty=True).decode('utf-8-sig')
        if any(line.strip() and not line.lstrip().startswith('//') for line in body.splitlines()):
            raise FullError('module_mismatch')
    except (ET.ParseError, UnicodeError):
        raise FullError('module_mismatch') from None


def client_process_snapshot() -> set[tuple[int, str]]:
    """Fail closed on new namespace processes, even setsid/non-dumpable children.

    Snapshot identities are invocation-local and never exported. No process from
    this census is killed; only the launched process group is cleanup-owned.
    Container teardown owns any escaped descendant on failure.
    """
    if os.name != 'posix':
        raise FullError('process_failed')
    result = set()
    try:
        for directory in Path('/proc').iterdir():
            if not directory.name.isdecimal():
                continue
            try:
                # Do not use proc-directory ownership: non-dumpable children can
                # appear root-owned despite retaining their original UID.
                # comm may contain spaces/parentheses; field 22 is starttime.
                raw = (directory / 'stat').read_text()
                fields = raw[raw.rindex(')') + 2:].split()
                result.add((int(directory.name), fields[19]))
            except FileNotFoundError:
                if directory.exists():
                    raise FullError('process_failed')
        return result
    except (OSError, ValueError, IndexError):
        raise FullError('process_failed') from None


def client_process_baseline(nonce: str) -> set[tuple[int, str]]:
    """Use the census taken after X startup, before the first native invocation."""
    value = strict_json(secure_bytes(Path('/tmp/onec-smoke/client-process-baseline.json'), 16384))
    if (type(value) is not dict or set(value) != {'schema', 'nonce', 'processes'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or type(value['processes']) is not list
            or not 1 <= len(value['processes']) <= 256):
        raise FullError('invalid_result')
    baseline = set()
    for item in value['processes']:
        if (type(item) is not list or len(item) != 2 or type(item[0]) is not int
                or not 1 <= item[0] <= 4194304 or type(item[1]) is not str
                or re.fullmatch(r'[0-9]{1,20}', item[1]) is None
                or tuple(item) in baseline):
            raise FullError('invalid_result')
        baseline.add(tuple(item))
    current = client_process_snapshot()
    own = {identity for identity in current if identity[0] == os.getpid()}
    if len(own) != 1:
        raise FullError('process_failed')
    if not current <= baseline | own:
        raise ClientProcessError(unexpected_process_diagnostics(current - (baseline | own), 'baseline'))
    return baseline | own


def run_client_probe(platform, root: Path, inputs: Path, nonce: str,
                     hashes: dict, *, stall: bool = False) -> dict:
    """Fresh client-only EPF; stall is the explicitly requested negative checkpoint."""
    record = empty_client_report()
    record.update(status='failed', failure_kind='unexpected_failure')
    try:
        if (not valid_nonce(nonce) or type(stall) is not bool or platform.timeout != 120
                or platform.user != 'NativeSmoke' or platform.password is not None):
            raise FullError('invalid_input')
        record['process_diagnostics'].update(stage='baseline', reason='unverified')
        baseline = client_process_baseline(nonce)
        record['process_diagnostics'].update(stage='before_probe', reason='native_not_quiet')
        if not native_processes_quiet(platform.executable):
            raise FullError('process_failed')
        record['process_diagnostics'].update(reason='none')
        absent(root)
        root.mkdir(mode=0o700)
        source = secure_bytes(inputs / CLIENT_TARGET, MAX_OUTPUT)
        if digest(source) != hashes[CLIENT_SOURCE]:
            raise FullError('invalid_input')
        record['source_sha256'] = digest(source)
        module = generated_module(source)
        src = root / 'src'
        src.mkdir()
        # Only the verified launcher metadata is copied; no TestModule/server code.
        for relative in ('Launcher.xml', 'Launcher/Ext/ObjectModule.bsl',
                         'Launcher/Forms/Main.xml', 'Launcher/Forms/Main/Ext/Form.xml'):
            origin = inputs / 'launcher/launcher_1c' / relative
            raw = secure_bytes(origin, MAX_OUTPUT)
            if digest(raw) != hashes['integrational_tests/launcher_1c/' + relative]:
                raise FullError('invalid_input')
            destination = src / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        (src / CLIENT_MODULE).parent.mkdir(parents=True, exist_ok=True)
        (src / CLIENT_MODULE).write_bytes(module)
        client_wiring(src)
        record['module_sha256'] = digest(secure_bytes(src / CLIENT_MODULE, MAX_OUTPUT))
        epf = root / 'ClientProbe.epf'
        run_process(platform.command('DESIGNER') + [
            '/LoadExternalDataProcessorOrReportFromFiles', str(src / 'Launcher.xml'), str(epf),
            '/Out', str(root / 'build.log'), '/DumpResult', str(root / 'build.result')],
            root, root / 'build-console.log', 120, require_clean_tree=True)
        require_epf(epf)
        if secure_bytes(src / CLIENT_MODULE, MAX_OUTPUT) != module:
            raise FullError('module_mismatch')
        dumped = root / 'roundtrip'
        dumped.mkdir()
        run_process(platform.command('DESIGNER') + [
            '/DumpExternalDataProcessorOrReportToFiles', str(dumped / 'Launcher.xml'), str(epf),
            '/Out', str(root / 'dump.log'), '/DumpResult', str(root / 'dump.result')],
            root, root / 'dump-console.log', 120, require_clean_tree=True)
        actual = generated_module(secure_bytes(dumped / CLIENT_MODULE, MAX_OUTPUT))
        if actual != module:
            raise FullError('module_mismatch')
        client_wiring(dumped)
        record['roundtrip_sha256'] = digest(actual)
        entered, completed = root / 'entered.json', root / 'completed.json'
        request = root / 'request.json'
        absent(entered, completed, request)
        with request.open('x', encoding='utf-8') as stream:
            json.dump({'nonce': nonce, 'entered': str(entered), 'completed': str(completed),
                       'mode': 'stall' if stall else 'normal'}, stream)
        try:
            run_process(platform.command('ENTERPRISE') + [
                '/RunModeManagedApplication', '/VL', 'ru_RU', '/Execute', str(epf),
                '/C', str(request), '/Out', str(root / 'enterprise.log')],
                root, root / 'enterprise-console.log', 120, require_clean_tree=True)
            record['process_exited'] = True
        finally:
            record['process_diagnostics'].update(stage='after_exit', reason='unverified')
            survivors = client_process_snapshot() - baseline
            if survivors:
                record['process_diagnostics'] = unexpected_process_diagnostics(survivors, 'after_exit')
            else:
                record['process_diagnostics'].update(reason='native_not_quiet')
                record['quiet'] = native_processes_quiet(platform.executable)
                if record['quiet']:
                    record['process_diagnostics'].update(reason='none')
            # Diagnostic phase only. A timeout/nonzero exit never becomes success.
            for path, phase in ((entered, 'entered'), (completed, 'completed')):
                try:
                    client_marker(path, nonce, phase)
                    record[phase] = True
                except FullError:
                    pass
        client_marker(entered, nonce, 'entered')
        client_marker(completed, nonce, 'completed')
        if completed.stat().st_mtime_ns < entered.stat().st_mtime_ns:
            raise FullError('invalid_result')
        if not record['quiet']:
            raise FullError('process_failed')
        if secure_bytes(src / CLIENT_MODULE, MAX_OUTPUT) != module:
            raise FullError('module_mismatch')
        record.update(status='ok', failure_kind='none', witness_verified=True)
    except Exception as error:
        if isinstance(error, ClientProcessError):
            record['process_diagnostics'] = error.diagnostics
        record['failure_kind'] = (error.kind if isinstance(error, FullError) else
                                  'artifact_missing' if isinstance(error, (OSError, DraftError)) else
                                  'unexpected_failure')
    return record


def empty_watchdog_report() -> dict:
    return {**empty_client_report(), 'timeout_verified': False}


def run_client_watchdog(platform, root: Path, inputs: Path, nonce: str, hashes: dict) -> dict:
    record = {**run_client_probe(platform, root, inputs, nonce, hashes, stall=True),
              'timeout_verified': False}
    # This is a narrow negative assertion, never generic timeout acceptance.
    try:
        if (record['status'] != 'failed' or record['failure_kind'] != 'timeout'
                or record['entered'] is not True or record['completed'] is not False
                or record['process_exited'] is not False or record['quiet'] is not True
                or record['witness_verified'] is not False
                or record['source_sha256'] != hashes[CLIENT_SOURCE]
                or record['module_sha256'] is None
                or record['roundtrip_sha256'] != record['module_sha256']):
            raise FullError('invalid_result')
        # An error/partial/invalid terminal file is not the deliberate stall.
        absent(root / 'completed.json')
        client_marker(root / 'entered.json', nonce, 'entered')
        record.update(status='ok', failure_kind='none', timeout_verified=True)
    except FullError as error:
        record.update(status='failed', failure_kind=error.kind, witness_verified=False)
    return record

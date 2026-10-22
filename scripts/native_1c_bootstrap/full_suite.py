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


def empty_report(nonce: str, *, client_probe: bool = False, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False) -> dict:
    if not valid_nonce(nonce) or ((watchdog_check or client_dates or client_values or client_collections or client_numbers) and not client_probe):
        raise FullError('invalid_input')
    return {**({'client_probe': empty_client_report()} if client_probe else {}),
            **({'client_watchdog': empty_watchdog_report()} if watchdog_check else {}),
            **({'client_dates': empty_dates_report()} if client_dates else {}),
            **({'client_values': empty_values_report()} if client_values else {}),
            **({'client_collections': empty_collections_report()} if client_collections else {}),
            **({'client_numbers': empty_numbers_report()} if client_numbers else {}),
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


def validate_case_request(command: list[str], directory: Path, post_create: bool) -> None:
    """Bind the fixed post-create action to the reviewed source at launch time."""
    if (command.count('/C') != 1 or command.index('/C') + 1 >= len(command)
            or command[command.index('/C') + 1] != str(directory / 'request.json')):
        raise FullError('invalid_input')
    request = strict_json(secure_bytes(directory / 'request.json', 16_384))
    expected = {'module': str(directory / 'TestModule.epf'),
                'result': str(directory / 'result.json'), 'post_create': post_create}
    if (type(request) is not dict or set(request) != set(expected)
            or type(request['post_create']) is not bool or request != expected):
        raise FullError('invalid_input')


def run_suite(launcher, platform, launcher_epf: Path, root: Path,
              inputs: Path, nonce: str, *, client_probe: bool = False, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False) -> dict:
    report = empty_report(nonce, client_probe=client_probe, watchdog_check=watchdog_check, client_dates=client_dates, client_values=client_values, client_collections=client_collections, client_numbers=client_numbers)
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
        def case_process(command, case_directory, log, timeout):
            if len(command) > 1 and command[1] == 'ENTERPRISE':
                if case_directory != directory:
                    raise FullError('invalid_input')
                validate_case_request(command, directory, expected_post_create)
            run_process(command, case_directory, log, timeout)
        launcher.run_process = case_process
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
            expected_post_create = launcher.post_create_requested(source_data.decode('utf-8-sig'))
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
        if client_dates:
            report['client_dates'] = run_client_probe(
                platform, root / 'client-dates', inputs, nonce, report['input_sha256'],
                dates_output=root / 'dates.out')
            if report['client_dates']['status'] != 'ok':
                raise FullError(report['client_dates']['failure_kind'])
        if client_values:
            report['client_values'] = run_client_probe(
                platform, root / 'client-values', inputs, nonce, report['input_sha256'],
                values_output=root / 'values.out')
            if report['client_values']['status'] != 'ok':
                raise FullError(report['client_values']['failure_kind'])
        if client_collections:
            report['client_collections'] = run_client_probe(
                platform, root / 'client-collections', inputs, nonce, report['input_sha256'],
                collections_output=root / 'collections.out')
            if report['client_collections']['status'] != 'ok':
                raise FullError(report['client_collections']['failure_kind'])
        if client_numbers:
            report['client_numbers'] = run_client_probe(
                platform, root / 'client-numbers', inputs, nonce, report['input_sha256'],
                numbers_output=root / 'numbers.out')
            if report['client_numbers']['status'] != 'ok':
                raise FullError(report['client_numbers']['failure_kind'])
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


# Schemas 2/3 are stage-wire encodings only. Named evidence remains the internal
# representation, including all failure and process proof fields.
CLIENT_WIRE_RECORDS = ('client_probe', 'client_dates', 'client_values',
                       'client_collections', 'client_watchdog')
CLIENT_WIRE_V3_RECORDS = CLIENT_WIRE_RECORDS + ('client_numbers',)
CLIENT_WIRE_HASHES = ('source_sha256', 'module_sha256', 'roundtrip_sha256')
CLIENT_WIRE_PROOF = ('entered', 'completed', 'process_exited', 'quiet', 'witness_verified')
CLIENT_WIRE_DIAGNOSTICS = ('stage', 'reason', 'unexpected_count', 'zombie_count', 'classes')
CLIENT_WIRE_CLASSES = ('native', 'display', 'session_bus', 'shell', 'python', 'other', 'unreadable')


def decode_process_wire(value: object) -> dict:
    if (type(value) is not list or len(value) != 5
            or type(value[0]) is not str or value[0] not in {'not_checked', 'baseline', 'before_probe', 'after_exit'}
            or type(value[1]) is not str or value[1] not in {'none', 'unverified', 'native_not_quiet', 'unexpected_processes'}
            or any(type(count) is not int or not 0 <= count <= 256 for count in value[2:4])
            or type(value[4]) is not list or len(value[4]) != len(CLIENT_WIRE_CLASSES)
            or any(type(count) is not int or not 0 <= count <= 256 for count in value[4])
            or value[3] > value[2] or sum(value[4]) != value[2]
            or (value[1] != 'unexpected_processes' and value[2] != 0)):
        raise FullError('invalid_result')
    return {**dict(zip(CLIENT_WIRE_DIAGNOSTICS[:4], value[:4])),
            'classes': dict(zip(CLIENT_WIRE_CLASSES, value[4]))}


def decode_stage_wire(data: dict) -> dict:
    if type(data) is not dict or type(data.get('schema')) is not int or data['schema'] not in (1, 2, 3):
        raise FullError('invalid_result')
    if any(type(key) is str and key.startswith('client_') and key not in CLIENT_WIRE_V3_RECORDS for key in data):
        raise FullError('invalid_result')
    named = set(CLIENT_WIRE_HASHES + CLIENT_WIRE_PROOF)
    if data['schema'] == 1:
        if any(type(data.get(key)) is dict and ({'hashes', 'proof'} & set(data[key])
               or type(data[key].get('process_diagnostics')) is list)
               for key in CLIENT_WIRE_V3_RECORDS):
            raise FullError('invalid_result')
        return data
    if ((data['schema'] == 2 and ('client_collections' not in data or 'client_numbers' in data))
            or (data['schema'] == 3 and 'client_numbers' not in data)):
        raise FullError('invalid_result')
    try:
        size = len(json.dumps(data, separators=(',', ':'), allow_nan=False).encode())
    except (TypeError, ValueError):
        raise FullError('invalid_result') from None
    if size > MAX_STAGE_REPORT:
        raise FullError('export_failed')
    result = {**data, 'schema': 1}
    for key in CLIENT_WIRE_V3_RECORDS:
        if key not in data:
            continue
        record = data[key]
        if (type(record) is not dict or not {'hashes', 'proof'} <= set(record)
                or named & set(record)):
            raise FullError('invalid_result')
        if data['schema'] == 3:
            diagnostic = decode_process_wire(record.get('process_diagnostics'))
        elif type(record.get('process_diagnostics')) is not dict:
            raise FullError('invalid_result')
        hashes, proof = record['hashes'], record['proof']
        if (type(hashes) is not list or len(hashes) != 3
                or any(value is not None and (type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None) for value in hashes)
                or type(proof) is not list or len(proof) != 5
                or any(type(value) is not bool for value in proof)):
            raise FullError('invalid_result')
        result[key] = {**{name: value for name, value in record.items() if name not in {'hashes', 'proof'}},
                       **dict(zip(CLIENT_WIRE_HASHES, hashes)), **dict(zip(CLIENT_WIRE_PROOF, proof))}
        if data['schema'] == 3:
            result[key]['process_diagnostics'] = diagnostic
    return result


def encode_stage_wire(report: dict) -> dict:
    if type(report) is not dict or type(report.get('schema')) is not int or report['schema'] != 1:
        raise FullError('invalid_result')
    # The previous opt-in combinations retain their exact existing wire format.
    if 'client_collections' not in report and 'client_numbers' not in report:
        return decode_stage_wire(report)
    schema = 3 if 'client_numbers' in report else 2
    result = {**report, 'schema': schema}
    named = set(CLIENT_WIRE_HASHES + CLIENT_WIRE_PROOF)
    for key in CLIENT_WIRE_V3_RECORDS:
        if key not in report:
            continue
        record = report[key]
        if (type(record) is not dict or not named <= set(record)
                or {'hashes', 'proof'} & set(record)):
            raise FullError('invalid_result')
        result[key] = {**{name: value for name, value in record.items() if name not in named},
                       'hashes': [record[name] for name in CLIENT_WIRE_HASHES],
                       'proof': [record[name] for name in CLIENT_WIRE_PROOF]}
        if schema == 3:
            diagnostic = record.get('process_diagnostics')
            if (type(diagnostic) is not dict or set(diagnostic) != set(CLIENT_WIRE_DIAGNOSTICS)
                    or type(diagnostic['classes']) is not dict
                    or set(diagnostic['classes']) != set(CLIENT_WIRE_CLASSES)):
                raise FullError('invalid_result')
            result[key]['process_diagnostics'] = [
                *[diagnostic[name] for name in CLIENT_WIRE_DIAGNOSTICS[:4]],
                [diagnostic['classes'][name] for name in CLIENT_WIRE_CLASSES]]
    if decode_stage_wire(result) != report:
        raise FullError('invalid_result')
    return result


def write_report(path: Path, report: dict) -> None:
    report = encode_stage_wire(report)
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
    wire_report = {**report, 'stage3': encode_stage_wire(stage)}
    raw = json.dumps({'schema': WIRE_SCHEMA, 'nonce': nonce, 'report': wire_report,
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



def empty_dates_report() -> dict:
    return {**empty_client_report(), 'output_sha256': None, 'output_size': None,
            'message_count': None}

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


def session_bus_process(pid: int, parent: int, started: str | None = None,
                        *, require_executable: bool = True) -> tuple[int, str]:
    """Validate one explicitly launched direct child; never adopt by executable class."""
    if (type(pid) is not int or type(parent) is not int or pid <= 1 or parent <= 0
            or pid == os.getpid()):
        raise FullError('process_failed')
    try:
        directory = Path('/proc') / str(pid)
        raw = (directory / 'stat').read_text()
        fields = raw[raw.rindex(')') + 2:].split()
        uid_line = next(line for line in (directory / 'status').read_text().splitlines()
                        if line.startswith('Uid:'))
        uids = uid_line.split()[1:]
        if (fields[0] == 'Z' or int(fields[1]) != parent or len(uids) != 4
                or re.fullmatch(r'[0-9]{1,20}', fields[19]) is None
                or any(int(uid) != os.geteuid() for uid in uids)
                or (require_executable and str((directory / 'exe').readlink()) != '/usr/bin/dbus-daemon')
                or (started is not None and fields[19] != started)):
            raise FullError('process_failed')
        return pid, fields[19]
    except (OSError, ValueError, IndexError, StopIteration):
        raise FullError('process_failed') from None


def session_bus_paths(root: Path, nonce: str) -> tuple[Path, Path, str]:
    if not valid_nonce(nonce):
        raise FullError('invalid_input')
    directory = root / ('session-bus-' + nonce)
    address = 'unix:path=' + str(directory / 'bus')
    return directory, directory / 'owner.json', address


def prepare_session_bus(root: Path, nonce: str, pid: int, parent: int) -> None:
    """Bounded readiness for our nofork child, using only private fixed paths."""
    directory, owner, address = session_bus_paths(root, nonce)
    absent(owner)
    deadline = time.monotonic() + 5
    # Pin identity before exec; executable readiness may lag fork scheduling.
    # This never admits the pre-exec process to the baseline or owner record.
    identity = session_bus_process(pid, parent, require_executable=False)
    while True:
        session_bus_process(pid, parent, identity[1], require_executable=False)
        try:
            session_bus_process(pid, parent, identity[1])
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise FullError('process_failed')
            printed = secure_bytes(directory / 'address', 256).decode('ascii')
            socket = (directory / 'bus').lstat()
            if (re.fullmatch(re.escape(address) + r',guid=[0-9a-f]{32}\n', printed) is None
                    or not stat.S_ISSOCK(socket.st_mode) or socket.st_uid != os.geteuid()):
                raise FullError('process_failed')
            break
        except (OSError, UnicodeError, FullError):
            if time.monotonic() >= deadline:
                raise FullError('process_failed') from None
            time.sleep(0.05)
    with owner.open('x', encoding='utf-8') as stream:
        json.dump({'schema': 1, 'nonce': nonce, 'pid': pid, 'started': identity[1],
                   'parent': parent, 'socket_device': str(socket.st_dev),
                   'socket_inode': str(socket.st_ino)}, stream)


def session_bus_owner(root: Path, nonce: str) -> dict:
    directory, owner, address = session_bus_paths(root, nonce)
    value = strict_json(secure_bytes(owner, 1024))
    if (type(value) is not dict or set(value) != {
            'schema', 'nonce', 'pid', 'started', 'parent', 'socket_device', 'socket_inode'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or type(value['started']) is not str
            or re.fullmatch(r'[0-9]{1,20}', value['started']) is None
            or type(value['pid']) is not int or not 1 < value['pid'] <= 4194304
            or type(value['parent']) is not int or not 0 < value['parent'] <= 4194304
            or type(value['socket_device']) is not str
            or re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', value['socket_device']) is None
            or not 0 <= int(value['socket_device']) < 2**64
            or type(value['socket_inode']) is not str
            or re.fullmatch(r'[1-9][0-9]{0,19}', value['socket_inode']) is None
            or not 0 < int(value['socket_inode']) < 2**64):
        raise FullError('process_failed')
    return value


def require_session_bus(root: Path, nonce: str) -> tuple[int, str]:
    directory, owner, address = session_bus_paths(root, nonce)
    value = session_bus_owner(root, nonce)
    identity = session_bus_process(value['pid'], value['parent'], value['started'])
    try:
        info = directory.lstat()
        socket = (directory / 'bus').lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700 or not stat.S_ISSOCK(socket.st_mode)
                or socket.st_uid != os.geteuid()
                or (str(socket.st_dev), str(socket.st_ino)) != (value['socket_device'], value['socket_inode'])
                or os.environ.get('DBUS_SESSION_BUS_ADDRESS') != address):
            raise FullError('process_failed')
    except OSError:
        raise FullError('process_failed') from None
    return identity


def stop_session_bus(root: Path, nonce: str, pid: int, parent: int) -> None:
    """Pin our exact child with pidfd; bounded cleanup cannot signal a reused PID."""
    import select
    directory, owner, address = session_bus_paths(root, nonce)
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise FullError('process_failed')
    value = session_bus_owner(root, nonce)
    if value['pid'] != pid or value['parent'] != parent:
        raise FullError('process_failed')
    try:
        fd = os.pidfd_open(pid)
    except OSError:
        raise FullError('process_failed') from None
    try:
        session_bus_process(pid, parent, value['started'])
        poll = select.poll()
        poll.register(fd, select.POLLIN)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                signal.pidfd_send_signal(fd, sig)
            except OSError:
                raise FullError('process_failed') from None
            events = poll.poll(2000)
            if any(descriptor == fd and mask & select.POLLIN for descriptor, mask in events):
                return
        raise FullError('process_failed')
    finally:
        os.close(fd)


def read_client_process_baseline(nonce: str) -> set[tuple[int, str]]:
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
    return baseline


def client_process_baseline(nonce: str) -> set[tuple[int, str]]:
    baseline = read_client_process_baseline(nonce)
    bus = require_session_bus(Path('/tmp/onec-smoke'), nonce)
    if bus not in baseline:
        raise FullError('process_failed')
    current = client_process_snapshot()
    own = {identity for identity in current if identity[0] == os.getpid()}
    if len(own) != 1:
        raise FullError('process_failed')
    if not current <= baseline | own:
        raise ClientProcessError(unexpected_process_diagnostics(current - (baseline | own), 'baseline'))
    return baseline | own


def fail_client_process_checkpoint(suite: dict, watchdog_check: bool, diagnostics=None) -> None:
    """Keep a final teardown/census failure valid, finite and non-exportable."""
    suite.update(status='failed', failure_kind='process_failed')
    last = (suite['client_watchdog'] if watchdog_check else
            suite['client_numbers'] if 'client_numbers' in suite else
            suite['client_collections'] if 'client_collections' in suite else
            suite['client_values'] if 'client_values' in suite else
            suite['client_dates'] if 'client_dates' in suite else suite['client_probe'])
    if 'conversion_verified' in last:
        last['conversion_verified'] = False
    if 'output_sha256' in last:
        last.update(output_sha256=None, output_size=None, message_count=None)
    last.update(status='failed', failure_kind='process_failed', quiet=False, witness_verified=False)
    if watchdog_check:
        last['timeout_verified'] = False
    last['process_diagnostics'] = (diagnostics if diagnostics is not None else
        dict(empty_process_diagnostics(), stage='after_exit', reason='unverified'))


def final_client_process_census(nonce: str) -> None:
    """After owned bus teardown, reject late service activation before export."""
    baseline = read_client_process_baseline(nonce)
    value = session_bus_owner(Path('/tmp/onec-smoke'), nonce)
    current = client_process_snapshot()
    own = {identity for identity in current if identity[0] == os.getpid()}
    if len(own) != 1 or (value['pid'], value['started']) in current:
        raise FullError('process_failed')
    unexpected = current - (baseline | own)
    if unexpected:
        raise ClientProcessError(unexpected_process_diagnostics(unexpected, 'after_exit'))


def run_client_probe(platform, root: Path, inputs: Path, nonce: str,
                     hashes: dict, *, stall: bool = False, dates_output: Path | None = None,
                     values_output: Path | None = None, collections_output: Path | None = None,
                     numbers_output: Path | None = None) -> dict:
    """Fresh client-only EPF; stall is the explicitly requested negative checkpoint."""
    parity_output = (numbers_output if numbers_output is not None else
                     collections_output if collections_output is not None else
                     values_output if values_output is not None else dates_output)
    record = (empty_numbers_report() if numbers_output is not None else
              empty_collections_report() if collections_output is not None else
              empty_values_report() if values_output is not None else
              empty_dates_report() if dates_output is not None else empty_client_report())
    marker_reader = (client_numbers_marker if numbers_output is not None else
                     client_collections_marker if collections_output is not None else
                     client_values_marker if values_output is not None else
                     client_dates_marker if dates_output is not None else client_marker)
    record.update(status='failed', failure_kind='unexpected_failure')
    try:
        if (not valid_nonce(nonce) or type(stall) is not bool
                or (parity_output is not None and stall)
                or (sum(value is not None for value in (dates_output, values_output, collections_output, numbers_output)) > 1)
                or platform.timeout != 120
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
        if numbers_output is not None:
            numbers_source = secure_bytes(inputs / 'scenarios/numbers.bsl', MAX_OUTPUT)
            if digest(numbers_source) != hashes['integrational_tests/tests/numbers.bsl']:
                raise FullError('invalid_input')
            record['source_sha256'] = digest(numbers_source)
            module = client_numbers_module(numbers_source, source)
        elif collections_output is not None:
            collections_source = secure_bytes(inputs / 'scenarios/collections.bsl', MAX_OUTPUT)
            if digest(collections_source) != hashes['integrational_tests/tests/collections.bsl']:
                raise FullError('invalid_input')
            record['source_sha256'] = digest(collections_source)
            module = client_collections_module(collections_source, source)
        elif values_output is not None:
            values_source = secure_bytes(inputs / 'scenarios/values.bsl', MAX_OUTPUT)
            if digest(values_source) != hashes['integrational_tests/tests/values.bsl']:
                raise FullError('invalid_input')
            record['source_sha256'] = digest(values_source)
            module = client_values_module(values_source, source)
        elif dates_output is not None:
            dates_source = secure_bytes(inputs / 'scenarios/dates.bsl', MAX_OUTPUT)
            if digest(dates_source) != hashes['integrational_tests/tests/dates.bsl']:
                raise FullError('invalid_input')
            record['source_sha256'] = digest(dates_source)
            module = client_dates_module(dates_source, source)
        else:
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
                require_session_bus(Path('/tmp/onec-smoke'), nonce)
                record['process_diagnostics'].update(reason='native_not_quiet')
                record['quiet'] = native_processes_quiet(platform.executable)
                if record['quiet']:
                    record['process_diagnostics'].update(reason='none')
            # Diagnostic phase only. A timeout/nonzero exit never becomes success.
            for path, phase in ((entered, 'entered'), (completed, 'completed')):
                try:
                    marker_reader(path, nonce, phase)
                    record[phase] = True
                except FullError:
                    pass
        marker_reader(entered, nonce, 'entered')
        completion = marker_reader(completed, nonce, 'completed')
        if completed.stat().st_mtime_ns < entered.stat().st_mtime_ns:
            raise FullError('invalid_result')
        if not record['quiet']:
            raise FullError('process_failed')
        if secure_bytes(src / CLIENT_MODULE, MAX_OUTPUT) != module:
            raise FullError('module_mismatch')
        if parity_output is not None:
            client_output = serialize_messages(completion['values'])
            server_output = secure_bytes(parity_output, MAX_OUTPUT, allow_empty=True)
            if client_output != server_output:
                if collections_output is not None:
                    # Only finite metadata leaves the private comparison. The
                    # unchanged server messages must reproduce this exact output
                    # before ordinal diagnostics can be trusted. Diagnostics never
                    # relax the strict byte comparison or enable payload export.
                    try:
                        server_messages, _ = read_native_result(
                            collections_output.parent / 'collections-case/result.json')
                        record['mismatch'] = collections_mismatch(
                            completion['values'], server_messages, server_output)
                    except (FullError, OSError):
                        pass  # The original mismatch still fails closed.
                raise FullError('output_mismatch')
            if numbers_output is not None:
                server_messages, _ = read_native_result(numbers_output.parent / 'numbers-case/result.json')
                verify_numbers_conversion(completion['values'], server_messages, server_output)
                record['conversion_verified'] = True
            record.update(output_sha256=digest(client_output), output_size=len(client_output),
                          message_count=len(completion['values']))
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


# This is a deliberately source-specific adapter, not a general BSL rewriter.
CLIENT_DATES_SOURCE_SHA256 = '392761c5ce8f599d569400672b07590184f147c9e4d5cd3f07decee1cffb029e'
CLIENT_DATES_TEMPLATE_SHA256 = '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328'
CLIENT_DATES_MESSAGE_COUNT = 185


def client_dates_module(source: bytes, template: bytes) -> bytes:
    """Adapt only the pinned dates source into the pinned managed-client harness.

    Source statements retain their exact spelling/order. Only the six verified
    message-call identifiers change; helpers gain client directives and the
    original module body moves into a client procedure. No server trampoline,
    string conversion, date reference generation or expected values are added.
    """
    if (digest(source) != CLIENT_DATES_SOURCE_SHA256
            or digest(template) != CLIENT_DATES_TEMPLATE_SHA256):
        raise FullError('invalid_input')
    original = generated_module(source).decode('utf-8-sig')
    harness = generated_module(template).decode('utf-8-sig')
    lines = original.splitlines(keepends=True)
    # Pin declarations, body boundary and actual call sites, not text matches
    # inside expression strings or comments. The raw digest is checked above.
    sites = (6, 11, 13, 80, 131, 218)
    declarations = {2: 'Процедура НаблюдатьДату(Знач Метка, Знач Выражение)\n',
                    19: 'Функция ПроверитьКлючиДат()\n'}
    capture = 'ДатыКлиентЗахват'
    if (len(lines) != 219 or any(lines[i] != text for i, text in declarations.items())
            or lines[15] != 'КонецПроцедуры\n' or lines[28] != 'КонецФункции\n'
            or lines[30] != 'НаблюдатьДату("construct.parts", "Date(2024, 2, 29, 12, 34, 56)");\n'
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Сообщить\(', line)) != sites
            or any(name in original or name in harness for name in
                   (capture, 'ДатыКлиентСообщения', 'ДатыКлиентСимволы', 'ДатыКлиентВыполнить'))):
        raise FullError('invalid_input')
    adapted = lines.copy()
    for i in sites:
        adapted[i] = adapted[i].replace('Сообщить(', capture + '(', 1)
    for i in declarations:
        adapted[i] = '&НаКлиенте\n' + adapted[i]
    # Runtime inverse assertion is explicit, independent of Python -O.
    restored = adapted.copy()
    for i in declarations:
        restored[i] = restored[i].removeprefix('&НаКлиенте\n')
    for i in sites:
        restored[i] = restored[i].replace(capture + '(', 'Сообщить(', 1)
    if ''.join(restored) != original:
        raise FullError('invalid_input')
    fixed = re.search(r'&НаКлиенте\nФункция ВычислитьПробу\(\)\n.*?\nКонецФункции\n',
                      harness, flags=re.DOTALL)
    if fixed is None or harness.count('Функция ВычислитьПробу()') != 1:
        raise FullError('invalid_input')
    # Client-only, non-exported module variables are supported in form modules.
    # 4 UTF-8 bytes per character plus all 185 message LFs is conservative;
    # the receiving verifier enforces the exact serialized UTF-8 byte limit.
    budget = (MAX_OUTPUT - CLIENT_DATES_MESSAGE_COUNT) // 4
    variables = ('&НаКлиенте\nПерем ДатыКлиентСообщения;\n'
                 '&НаКлиенте\nПерем ДатыКлиентСимволы;\n\n')
    wrapper = f'''&НаКлиенте
Процедура ДатыКлиентЗахват(Знач Текст)
    Если ТипЗнч(Текст) <> Тип("Строка") Тогда
        ВызватьИсключение "client-dates-type";
    КонецЕсли;
    Если ДатыКлиентСообщения.Количество() >= {CLIENT_DATES_MESSAGE_COUNT}
        Или ДатыКлиентСимволы + СтрДлина(Текст) > {budget} Тогда
        ВызватьИсключение "client-dates-limit";
    КонецЕсли;
    ДатыКлиентСимволы = ДатыКлиентСимволы + СтрДлина(Текст);
    ДатыКлиентСообщения.Добавить(Текст);
КонецПроцедуры

'''
    wrapper += ''.join(adapted[:30])
    wrapper += '&НаКлиенте\nПроцедура ДатыКлиентВыполнить()\n'
    wrapper += ''.join(adapted[30:])
    wrapper += 'КонецПроцедуры\n\n'
    wrapper += '''&НаКлиенте
Функция ВычислитьПробу()
    ДатыКлиентСообщения = Новый Массив;
    ДатыКлиентСимволы = 0;
    ДатыКлиентВыполнить();
    Возврат ДатыКлиентСообщения;
КонецФункции
'''
    result = variables + harness[:fixed.start()] + wrapper + harness[fixed.end():]
    return generated_module(result.encode('utf-8'))


def client_dates_marker(path: Path, nonce: str, phase: str) -> dict:
    """Validate fresh dates evidence; preserve string/order semantics for parity.

    This validates shape, not date values. Only the downstream byte comparison
    with this run's independently captured server output establishes parity.
    """
    if not valid_nonce(nonce) or phase not in {'entered', 'completed'}:
        raise FullError('invalid_input')
    # Retain the existing private result envelope limit, including JSON escapes.
    value = strict_json(secure_bytes(path, MAX_RESULT), max_depth=3)
    expected_count = 0 if phase == 'entered' else CLIENT_DATES_MESSAGE_COUNT
    if (type(value) is not dict
            or set(value) != {'schema', 'nonce', 'phase', 'witness', 'values'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or value['phase'] != phase
            or value['witness'] != 'client' or type(value['values']) is not list
            or len(value['values']) != expected_count
            or any(type(item) is not str for item in value['values'])):
        raise FullError('invalid_result')
    try:
        if sum(len(item.encode('utf-8')) for item in value['values']) > MAX_OUTPUT:
            raise FullError('output_limit')
        serialize_messages(value['values'])
    except UnicodeError:
        raise FullError('invalid_result') from None
    return value
# This is a deliberately source-specific adapter, not a general BSL rewriter.
CLIENT_VALUES_SOURCE_SHA256 = 'dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12'
CLIENT_VALUES_TEMPLATE_SHA256 = '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328'
CLIENT_VALUES_MESSAGE_COUNT = 402


def empty_values_report() -> dict:
    return {**empty_client_report(), 'output_sha256': None, 'output_size': None,
            'message_count': None}


def client_values_module(source: bytes, template: bytes) -> bytes:
    """Wrap the complete pinned values source in the pinned managed-client form.

    All 40 helpers (39 previous and one fixed String projection) remain in their original order with client directives.
    Only the 22 verified message-call identifiers change, and the complete module
    body moves into a client procedure. Expressions, conversions and error paths
    stay byte-identical. No server trampoline or reference values are added.
    """
    if (digest(source) != CLIENT_VALUES_SOURCE_SHA256
            or digest(template) != CLIENT_VALUES_TEMPLATE_SHA256):
        raise FullError('invalid_input')
    original = generated_module(source).decode('utf-8-sig')
    harness = generated_module(template).decode('utf-8-sig')
    lines = original.splitlines(keepends=True)
    # Check exact declarations, helper endings, body boundary and call sites.
    # Raw hashes above also pin all expression strings and protected branches.
    declarations = {
        3: 'Процедура НаблюдатьNull(Знач Метка, Знач Выражение)\n',
        19: 'Функция ВложенныйNull(Знач Значение)\n',
        27: 'Функция ПоискNull(Знач Значение)\n',
        35: 'Функция КлючNull(Знач Значение)\n',
        49: 'Процедура НаблюдатьXML(Знач Метка, Знач Выражение)\n',
        64: 'Функция ПрочитатьДатуXML(Знач Текст)\n',
        71: 'Функция КругXML(Знач Значение)\n',
        80: 'Функция КодыXML(Знач Текст)\n',
        89: 'Функция УправляющиеXML()\n',
        96: 'Функция ГраницыXML()\n',
        102: 'Функция ОчисткаXML(Знач Текст, Знач Версия)\n',
        115: 'Функция ПолеКомпактногоДополнения(Знач Значение)\n',
        122: 'Функция ПоляКомпактногоДополнения(Знач Значение, Знач Путь)\n',
        143: 'Процедура НаблюдатьДополнениеТипов(Знач Метка, Знач Выражение)\n',
        158: 'Функция СодержитТипДополнения(Знач Описание, Знач ПроверяемыйТип)\n',
        163: 'Функция УмолчаниеТипаДополнения(Знач Описание)\n',
        169: 'Функция СвойстваТипаДополнения(Знач Описание)\n',
        174: 'Функция КоличествоМассиваДополнения(Знач Массив)\n',
        178: 'Функция КвалификаторыОписанияДополнения(Знач Описание)\n',
        199: 'Функция УмолчанияКвалификаторовДополнения(Знач Пустое, Знач Скалярное)\n',
        208: 'Функция ПолеКомпактныхТипов(Знач Значение)\n',
        215: 'Функция ПоляКомпактныхТипов(Знач Значение, Знач Путь)\n',
        236: 'Процедура НаблюдатьТипы(Знач Метка, Знач Выражение)\n',
        253: 'Функция СнимокТипов(Знач Значение)\n',
        288: 'Функция СвойстваЧислаТипов(Знач Значение)\n',
        295: 'Функция СвойстваДлиныТипов(Знач Значение)\n',
        300: 'Функция СвойстваДатыТипов(Знач Значение)\n',
        305: 'Функция СвойстваОписанияТипов(Знач Значение)\n',
        311: 'Функция МассивТиповПробы()\n',
        319: 'Функция НезависимостьТипов(Знач Значение)\n',
        327: 'Функция ПриведениеТипов(Знач Описание, Знач Значение)\n',
        337: 'Функция ПоляОбъектаТипов(Знач Значение)\n',
        349: 'Функция ЗаписьСвойстваТипов(Знач Значение, Знач Действие)\n',
        358: 'Процедура НаблюдатьСимволы(Знач Метка, Знач Выражение)\n',
        368: 'Функция ПроекцияСимвола(Знач Значение)\n',
        376: 'Функция КругСимвола(Знач Значение, Знач ЧерезXML)\n',
        387: 'Функция ЗаписьСимвола(Знач Пространство, Знач Поле)\n',
        403: 'Функция ПолучательСимволов(Знач Пространство)\n',
        407: 'Функция ЗаписьИндексаСимвола(Знач Пространство, Знач Поле)\n',
        426: 'Функция ПроекцияУмолчанияСтроки(Знач Итог)\n',
    }
    endings = {
        16: 'КонецПроцедуры\n',
        25: 'КонецФункции\n',
        33: 'КонецФункции\n',
        44: 'КонецФункции\n',
        62: 'КонецПроцедуры\n',
        69: 'КонецФункции\n',
        78: 'КонецФункции\n',
        87: 'КонецФункции\n',
        94: 'КонецФункции\n',
        100: 'КонецФункции\n',
        109: 'КонецФункции\n',
        120: 'КонецФункции\n',
        139: 'КонецФункции\n',
        156: 'КонецПроцедуры\n',
        161: 'КонецФункции\n',
        167: 'КонецФункции\n',
        172: 'КонецФункции\n',
        176: 'КонецФункции\n',
        197: 'КонецФункции\n',
        202: 'КонецФункции\n',
        213: 'КонецФункции\n',
        232: 'КонецФункции\n',
        249: 'КонецПроцедуры\n',
        286: 'КонецФункции\n',
        293: 'КонецФункции\n',
        298: 'КонецФункции\n',
        303: 'КонецФункции\n',
        309: 'КонецФункции\n',
        317: 'КонецФункции\n',
        325: 'КонецФункции\n',
        335: 'КонецФункции\n',
        346: 'КонецФункции\n',
        354: 'КонецФункции\n',
        366: 'КонецПроцедуры\n',
        374: 'КонецФункции\n',
        385: 'КонецФункции\n',
        401: 'КонецФункции\n',
        405: 'КонецФункции\n',
        421: 'КонецФункции\n',
        433: 'КонецФункции\n',
    }
    sites = {
        7: '        Сообщить("null." + Метка + ": [error]");\n',
        12: '        Сообщить("null." + Метка + ": [" + Запись + "]");\n',
        14: '        Сообщить("null." + Метка + ": [serialize-error]");\n',
        53: '        Сообщить("xml." + Метка + ": [error]");\n',
        58: '        Сообщить("xml." + Метка + ": [" + Запись + "]");\n',
        60: '        Сообщить("xml." + Метка + ": [serialize-error]");\n',
        147: '        Сообщить("types-extra." + Метка + ": [error]");\n',
        152: '        Сообщить("types-extra." + Метка + ": [" + Запись + "]");\n',
        154: '        Сообщить("types-extra." + Метка + ": [serialize-error]");\n',
        240: '        Сообщить("types." + Метка + ": [error]");\n',
        245: '        Сообщить("types." + Метка + ": [" + Запись + "]");\n',
        247: '        Сообщить("types." + Метка + ": [serialize-error]");\n',
        362: '        Сообщить("chars." + Метка + ": [" + Запись + "]");\n',
        364: '        Сообщить("chars." + Метка + ": [error]");\n',
        486: 'Сообщить("null.checkpoint.complete: [ok]");\n',
        565: 'Сообщить("xml.checkpoint.complete: [ok]");\n',
        702: 'Сообщить("types.checkpoint.complete: [ok]");\n',
        730: 'Сообщить("types-extra.checkpoint.complete: [ok]");\n',
        790: 'Сообщить("chars.checkpoint.complete: [ok]");\n',
        832: 'Сообщить("chars.index.checkpoint.complete: [ok]");\n',
        851: 'Сообщить("types-extra.fixed-default.checkpoint.complete: [ok]");\n',
        879: 'Сообщить("types-extra.service-filled.checkpoint.complete: [ok]");\n',
    }
    body_start = 437
    capture = 'ЗначенияКлиентЗахват'
    reserved = (capture, 'ЗначенияКлиентСообщения',
                'ЗначенияКлиентСимволы', 'ЗначенияКлиентВыполнить')
    if (len(lines) != 881
            or any(lines[i] != text for i, text in declarations.items())
            or any(lines[i] != text for i, text in endings.items())
            or any(lines[i] != text for i, text in sites.items())
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*(?:Процедура|Функция)\s', line)) != tuple(declarations)
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Конец(?:Процедуры|Функции)\b', line)) != tuple(endings)
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Сообщить\(', line)) != tuple(sites)
            or lines[body_start] != 'НаблюдатьNull("literal.upper", "NULL");\n'
            or lines[body_start - 1] != '// Значение, тип и настоящий прямой/обратный кодек.\n'
            or any(re.match(r'^\s*[&#]', line) for line in lines)
            or any(name.casefold() in text.casefold()
                   for name in reserved for text in (original, harness))):
        raise FullError('invalid_input')
    adapted = lines.copy()
    for i in sites:
        adapted[i] = adapted[i].replace('Сообщить(', capture + '(', 1)
    for i in declarations:
        adapted[i] = '&НаКлиенте\n' + adapted[i]
    # Inverse reconstruction is a runtime check, not disabled by Python -O.
    restored = adapted.copy()
    for i in declarations:
        restored[i] = restored[i].removeprefix('&НаКлиенте\n')
    for i in sites:
        restored[i] = restored[i].replace(capture + '(', 'Сообщить(', 1)
    if ''.join(restored) != original:
        raise FullError('invalid_input')
    fixed = re.search(r'&НаКлиенте\nФункция ВычислитьПробу\(\)\n.*?\nКонецФункции\n',
                      harness, flags=re.DOTALL)
    if fixed is None or harness.count('Функция ВычислитьПробу()') != 1:
        raise FullError('invalid_input')
    # Client-only, non-exported form variables. Four UTF-8 bytes per character
    # plus one LF per message conservatively bounds capture; the verifier also
    # enforces the exact serialized UTF-8 byte and private JSON-envelope caps.
    budget = (MAX_OUTPUT - CLIENT_VALUES_MESSAGE_COUNT) // 4
    variables = ('&НаКлиенте\nПерем ЗначенияКлиентСообщения;\n'
                 '&НаКлиенте\nПерем ЗначенияКлиентСимволы;\n\n')
    wrapper = f'''&НаКлиенте
Процедура ЗначенияКлиентЗахват(Знач Текст)
    Если ТипЗнч(Текст) <> Тип("Строка") Тогда
        ВызватьИсключение "client-values-type";
    КонецЕсли;
    Если ЗначенияКлиентСообщения.Количество() >= {CLIENT_VALUES_MESSAGE_COUNT}
        Или ЗначенияКлиентСимволы + СтрДлина(Текст) > {budget} Тогда
        ВызватьИсключение "client-values-limit";
    КонецЕсли;
    ЗначенияКлиентСимволы = ЗначенияКлиентСимволы + СтрДлина(Текст);
    ЗначенияКлиентСообщения.Добавить(Текст);
КонецПроцедуры

'''
    wrapper += ''.join(adapted[:body_start])
    wrapper += '&НаКлиенте\nПроцедура ЗначенияКлиентВыполнить()\n'
    wrapper += ''.join(adapted[body_start:])
    wrapper += 'КонецПроцедуры\n\n'
    wrapper += '''&НаКлиенте
Функция ВычислитьПробу()
    ЗначенияКлиентСообщения = Новый Массив;
    ЗначенияКлиентСимволы = 0;
    ЗначенияКлиентВыполнить();
    Возврат ЗначенияКлиентСообщения;
КонецФункции
'''
    result = variables + harness[:fixed.start()] + wrapper + harness[fixed.end():]
    return generated_module(result.encode('utf-8'))


def client_values_marker(path: Path, nonce: str, phase: str) -> dict:
    """Validate full values evidence without predicting or filtering its output.

    This checks shape, not values semantics. Only a downstream full-byte
    comparison with this run's independent native values.out proves parity.
    """
    if not valid_nonce(nonce) or phase not in {'entered', 'completed'}:
        raise FullError('invalid_input')
    value = strict_json(secure_bytes(path, MAX_RESULT), max_depth=3)
    expected_count = 0 if phase == 'entered' else CLIENT_VALUES_MESSAGE_COUNT
    if (type(value) is not dict
            or set(value) != {'schema', 'nonce', 'phase', 'witness', 'values'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or value['phase'] != phase
            or value['witness'] != 'client' or type(value['values']) is not list
            or len(value['values']) != expected_count
            or any(type(item) is not str for item in value['values'])):
        raise FullError('invalid_result')
    try:
        if sum(len(item.encode('utf-8')) for item in value['values']) > MAX_OUTPUT:
            raise FullError('output_limit')
        serialize_messages(value['values'])
    except UnicodeError:
        raise FullError('invalid_result') from None
    return value


# This is a deliberately source-specific adapter, not a general BSL rewriter.
CLIENT_COLLECTIONS_SOURCE_SHA256 = 'e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232'
CLIENT_COLLECTIONS_TEMPLATE_SHA256 = '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328'
CLIENT_COLLECTIONS_MESSAGE_COUNT = 841


def empty_collections_report() -> dict:
    return {**empty_client_report(), 'output_sha256': None, 'output_size': None,
            'message_count': None, 'mismatch': None}


def collections_mismatch(client: list[str], server: list[str], server_output: bytes) -> dict:
    """Bounded diagnostics for unequal full outputs; never raw native messages."""
    if (type(client) is not list or type(server) is not list
            or len(client) != CLIENT_COLLECTIONS_MESSAGE_COUNT
            or len(server) != CLIENT_COLLECTIONS_MESSAGE_COUNT
            or any(type(item) is not str for item in client + server)
            or type(server_output) is not bytes
            or serialize_messages(server) != server_output):
        raise FullError('invalid_result')
    client_output = serialize_messages(client)
    if client_output == server_output:
        raise FullError('invalid_result')
    differences = []
    first_client = first_server = None
    for ordinal, (client_message, server_message) in enumerate(zip(client, server), 1):
        left, right = serialize_messages([client_message]), serialize_messages([server_message])
        if left != right:
            differences.append(ordinal)
            if first_client is None:
                first_client, first_server = left, right
    if not differences:
        raise FullError('invalid_result')
    return {'count': len(differences), 'first': differences[0],
            'ordinals': differences[:16], 'client_sha256': digest(first_client),
            'server_sha256': digest(first_server), 'client_size': len(first_client),
            'server_size': len(first_server)}


def client_collections_module(source: bytes, template: bytes) -> bytes:
    """Wrap the complete pinned collections source in the pinned managed-client form.

    All 116 source helpers remain in their original order with client directives.
    Only the 16 verified message-call identifiers change, and the complete module
    body moves into a client procedure. Four explicit helper-local declarations
    preserve source-local bindings against the managed form's Object/Items names.
    Expressions, conversions and error paths stay byte-identical. No server
    trampoline or reference collections are added.
    """
    if (digest(source) != CLIENT_COLLECTIONS_SOURCE_SHA256
            or digest(template) != CLIENT_COLLECTIONS_TEMPLATE_SHA256):
        raise FullError('invalid_input')
    original = generated_module(source).decode('utf-8-sig')
    harness = generated_module(template).decode('utf-8-sig')
    lines = original.splitlines(keepends=True)
    # Check exact declarations, helper endings, body boundary and call sites.
    # Raw hashes above also pin all expression strings and protected branches.
    declarations = {
        7: 'Процедура ПроверитьСписокВключения(Знач Метка, Знач Список)\n',
        23: 'Процедура ПроверитьУдалениеЗаГраницей(Знач Метка)\n',
        56: 'Процедура ПроверитьЗаполнениеСвойств(Знач Метка)\n',
        88: 'Процедура ПоказатьСоставМассива(Знач Метка, Знач Массив)\n',
        97: 'Процедура ПроверитьЗаполненность(Знач Метка, Знач Значение)\n',
        106: 'Процедура Показать(Знач Метка, Знач Значение)\n',
        111: 'Процедура ПоказатьВнутреннее(Знач Метка, Знач Значение, Восстановлено = Неопределено)\n',
        141: 'Процедура ПоказатьВосстановленныеСсылки(Знач Метка, Знач Пара)\n',
        160: 'Процедура ПоказатьБулево(Знач Метка, Знач Значение)\n',
        165: 'Процедура ПоказатьВнутренниеСсылки(Знач Метка, Знач Первое, Знач ТакоеЖе)\n',
        181: 'Процедура ПолучитьПозиции(Знач Заказ, Результат)\n',
        185: 'Процедура ДобавитьПозицию(Знач Позиции)\n',
        192: 'Функция РезультатРавенства(Знач Левое, Знач Правое)\n',
        200: 'Процедура ПоказатьПоиск(Знач Метка, Знач Значения, Знач Искомое)\n',
        208: 'Функция ПрочитатьКлюч(Знач Словарь, Знач Ключ)\n',
        217: 'Процедура ИсследоватьФиксированное(Знач Метка, Знач Первое, Знач ТакоеЖе, Знач Другое)\n',
        281: 'Функция ЗначенияОперацийТаблицы(Знач Текст)\n',
        285: 'Функция СсылкаПослеОперации(Знач Таблица, Знач СтрокаТаблицы)\n',
        301: 'Функция СортировкаТаблицыПробы(Знач Набор, Знач Порядок, Знач Сравнение = "omitted")\n',
        354: 'Функция СверткаТаблицыПробы(Знач Набор, Знач Группы, Знач Суммы = "omitted")\n',
        434: 'Функция НаблюдениеУдаленнойСтроки(Знач Таблица, Знач Удаленная, Знач Первая)\n',
        456: 'Функция УдаленнаяПослеСверткиПробы(Знач Групп, Знач Действие)\n',
        477: 'Функция ПорядокИтоговСверткиПробы(Знач Сценарий)\n',
        504: 'Функция КомпактноеЗначениеТаблицы(Знач Значение)\n',
        527: 'Процедура ДобавитьПоляВыводаТаблицы(СтрокиВывода, Знач Путь, Знач Значение)\n',
        537: 'Функция КонструкторТаблицыПробы(Знач Объект)\n',
        541: 'Процедура НаблюдатьТаблицы(Знач Метка, Знач Выражение)\n',
        565: 'Функция НоваяТаблицаПробы()\n',
        579: 'Функция ПоляКолонкиПробы(Знач Колонка)\n',
        584: 'Функция ПоляСтрокиПробы(Знач СтрокаТаблицы)\n',
        592: 'Функция ПоляТаблицыПробы(Знач Таблица)\n',
        604: 'Функция ВидОбъектаТаблицы(Знач Объект)\n',
        628: 'Функция КодекТаблицыПробы(Знач Объект)\n',
        669: 'Функция ОбъектТаблицыПробы(Знач ИмяОбъекта)\n',
        684: 'Функция ЧтениеТаблицыПробы(Знач Выражение)\n',
        698: 'Функция ИзменениеТаблицыПробы(Знач Сценарий)\n',
        867: 'Функция ТипизированнаяТаблицаПробы(Знач Описание, Знач Значение)\n',
        880: 'Функция СвязиТаблицыПробы(Знач Сценарий)\n',
        970: 'Функция ТаблицаИндексовПробы()\n',
        981: 'Функция ПоляИндексаПробы(Знач Индекс)\n',
        987: 'Функция ПоляИндексовПробы(Знач Индексы)\n',
        993: 'Функция ПоискИндексовПробы(Знач Таблица, Знач Ссылка)\n',
        1006: 'Функция КонструкторИндексовПробы(Знач Вид)\n',
        1017: 'Функция КодекИндексовПробы(Знач Вид)\n',
        1063: 'Функция ОшибкиИндексовПробы(Знач Действие)\n',
        1095: 'Функция ИндексыТаблицыПробы(Знач Сценарий, Знач Список = "Key")\n',
        1219: 'Функция ДопТаблицаИндексов()\n',
        1229: 'Функция ДопИдентификаторыИндексов(Знач СтрокиТаблицы)\n',
        1235: 'Функция ДопПервыйИндексПоиска(Знач Таблица, Знач Вид = "key")\n',
        1245: 'Функция ДопПоискИндексов(Знач Таблица, Знач Вид = "edit")\n',
        1269: 'Функция ДопПорядокИндексов(Знач Вид)\n',
        1307: 'Функция ДопВыборИндекса()\n',
        1336: 'Функция ДопСоставКопииИндексов(Знач Таблица)\n',
        1351: 'Функция ДопКопииИндексов()\n',
        1384: 'Функция ДопУдаленныйИндекс(Знач Индексы, Знач Сохраненный)\n',
        1394: 'Функция ДопСвязиИндексов()\n',
        1430: 'Функция НовыйСписокПробы(Знач Вид = "base")\n',
        1439: 'Функция ПоляЭлементаСписка(Знач Элемент)\n',
        1447: 'Функция ПоляСпискаПробы(Знач Список)\n',
        1466: 'Функция ОтветСпискаПробы(Знач Ответ, Знач Сохраненный)\n',
        1476: 'Функция ДействиеСпискаПробы(Знач Команда, Знач Вид = "base")\n',
        1498: 'Функция СерияСпискаПробы(Знач Команды, Знач Вид = "base")\n',
        1506: 'Функция ИдентичностьСпискаПробы()\n',
        1536: 'Функция ПоискЗначенияСпискаПробы()\n',
        1579: 'Функция СвязиСпискаПробы(Знач Вид)\n',
        1618: 'Функция КопированиеСпискаПробы(Знач Вид)\n',
        1661: 'Функция ИдентификаторыСпискаПробы(Знач Список)\n',
        1682: 'Функция КодекСпискаПробы(Знач Вид)\n',
        1738: 'Функция ВозвращенныеЭлементыСпискаПробы()\n',
        1758: 'Функция ЧужойСдвигСпискаПробы()\n',
        1793: 'Функция ПорядокСортировкиСписка(Знач Список, Знач Исходные)\n',
        1814: 'Функция НаборСортировкиСписка(Знач Вид)\n',
        1861: 'Функция ДействиеСортировкиСписка(Знач Вид, Знач Команда)\n',
        1888: 'Функция СерияСортировкиСписка(Знач Вид, Знач Команды)\n',
        1896: 'Функция ТипНаправленияСортировкиПробы()\n',
        1916: 'Функция КодекНаправленияСортировкиПробы(Знач Направление, Знач СТипом = Ложь)\n',
        1943: 'Функция ПозицияСсылкиКопииСписка(Знач Список, Знач Элемент)\n',
        1954: 'Функция РазмерыКопииСписка(Знач Список, Знач Копия)\n',
        1961: 'Функция СнимокКопированияСписка(Знач Список)\n',
        1998: 'Функция ДобавлениеПослеКопииСписка(Знач Список, Знач Представление)\n',
        2010: 'Функция ИсторияКопированияСписка(Знач Вид)\n',
        2097: 'Функция РезультатТекстаСписка(Знач Значение)\n',
        2104: 'Функция СнимокТекстаСписка(Знач Список)\n',
        2124: 'Функция ОдинТекстСписка(Знач Значение, Знач Вид = "value")\n',
        2135: 'Функция ПустыеТекстыСписка()\n',
        2151: 'Функция СкалярныеТекстыСписка(Знач Вид)\n',
        2177: 'Функция СоставныеТекстыСписка()\n',
        2196: 'Функция ЗагруженныеТекстыСписка()\n',
        2209: 'Функция ЖивыеТекстыСписка()\n',
        2238: 'Функция ПоляКэшаСписка(Знач Список)\n',
        2252: 'Функция ПолеИнициализацииКэша(Знач Элемент, Знач Вид, Знач Значение)\n',
        2260: 'Функция ИнициализацияКэшаСписка(Знач Вид, Знач Чтение)\n',
        2283: 'Функция НачалоКэшаСписка()\n',
        2293: 'Функция ПоменятьПервыйКэшСписка(Знач Список, Знач Значение, Знач Представление)\n',
        2301: 'Функция ДействиеКэшаСписка(Знач Вид)\n',
        2342: 'Функция ИзмененияКэшаСписка(Знач Группа)\n',
        2352: 'Функция ПустойКэшСписка()\n',
        2371: 'Функция КопияКэшаСписка()\n',
        2405: 'Функция ПустойРезультатКэшаСписка(Знач Вид)\n',
        2424: 'Функция ПустыеРезультатыКэшаСписка()\n',
        2432: 'Функция КороткаяСортировкаКэшаСписка(Знач ПоПредставлению)\n',
        2454: 'Функция КороткиеСортировкиКэшаСписка()\n',
        2463: 'Процедура ЗаписатьСсылкуСписка(Поле, Знач Новое, Знач Журнал)\n',
        2469: 'Процедура ЗаписатьЗначениеСписка(Знач Поле, Знач Новое, Знач Журнал)\n',
        2475: 'Функция ЖиваяСсылкаСписка(Поле, Знач Элемент, Знач Журнал)\n',
        2482: 'Процедура ДвеСсылкиСписка(Первое, Второе, Знач Журнал)\n',
        2489: 'Процедура ОшибкаПослеСсылкиСписка(Поле, Знач Журнал)\n',
        2495: 'Функция ПолучательСсылкиСписка(Знач Список, Знач Журнал)\n',
        2500: 'Функция ИндексСсылкиСписка(Знач Журнал)\n',
        2505: 'Функция ПозднийАргументСписка(Знач Журнал)\n',
        2510: 'Процедура ПерестроитьСсылкуСписка(Поле, Знач Список, Знач Элемент, Знач Журнал)\n',
        2521: 'Функция ВозвратСсылкиСписка(Поле, Знач Журнал)\n',
        2527: 'Функция ПробаСсылкиСписка(Знач Случай)\n',
        2636: 'Функция ПараКлючейОписаний(Знач Вид)\n',
        2663: 'Функция РавенствоКлючейОписаний(Знач Вид)\n',
        2676: 'Функция ИсторияКлючейОписаний(Знач Вид, Знач Режим)\n',
    }
    endings = {
        19: 'КонецПроцедуры\n',
        51: 'КонецПроцедуры\n',
        85: 'КонецПроцедуры\n',
        94: 'КонецПроцедуры\n',
        104: 'КонецПроцедуры\n',
        108: 'КонецПроцедуры\n',
        137: 'КонецПроцедуры\n',
        158: 'КонецПроцедуры\n',
        162: 'КонецПроцедуры\n',
        179: 'КонецПроцедуры\n',
        183: 'КонецПроцедуры\n',
        188: 'КонецПроцедуры\n',
        198: 'КонецФункции\n',
        206: 'КонецПроцедуры\n',
        215: 'КонецФункции\n',
        274: 'КонецПроцедуры\n',
        283: 'КонецФункции\n',
        299: 'КонецФункции\n',
        352: 'КонецФункции\n',
        432: 'КонецФункции\n',
        454: 'КонецФункции\n',
        475: 'КонецФункции\n',
        496: 'КонецФункции\n',
        524: 'КонецФункции\n',
        535: 'КонецПроцедуры\n',
        539: 'КонецФункции\n',
        563: 'КонецПроцедуры\n',
        576: 'КонецФункции\n',
        582: 'КонецФункции\n',
        590: 'КонецФункции\n',
        602: 'КонецФункции\n',
        625: 'КонецФункции\n',
        667: 'КонецФункции\n',
        682: 'КонецФункции\n',
        694: 'КонецФункции\n',
        865: 'КонецФункции\n',
        878: 'КонецФункции\n',
        963: 'КонецФункции\n',
        979: 'КонецФункции\n',
        985: 'КонецФункции\n',
        991: 'КонецФункции\n',
        1003: 'КонецФункции\n',
        1015: 'КонецФункции\n',
        1060: 'КонецФункции\n',
        1093: 'КонецФункции\n',
        1214: 'КонецФункции\n',
        1227: 'КонецФункции\n',
        1233: 'КонецФункции\n',
        1243: 'КонецФункции\n',
        1267: 'КонецФункции\n',
        1305: 'КонецФункции\n',
        1334: 'КонецФункции\n',
        1349: 'КонецФункции\n',
        1382: 'КонецФункции\n',
        1392: 'КонецФункции\n',
        1425: 'КонецФункции\n',
        1437: 'КонецФункции\n',
        1445: 'КонецФункции\n',
        1464: 'КонецФункции\n',
        1473: 'КонецФункции\n',
        1496: 'КонецФункции\n',
        1504: 'КонецФункции\n',
        1534: 'КонецФункции\n',
        1577: 'КонецФункции\n',
        1616: 'КонецФункции\n',
        1659: 'КонецФункции\n',
        1680: 'КонецФункции\n',
        1734: 'КонецФункции\n',
        1756: 'КонецФункции\n',
        1788: 'КонецФункции\n',
        1812: 'КонецФункции\n',
        1859: 'КонецФункции\n',
        1886: 'КонецФункции\n',
        1894: 'КонецФункции\n',
        1914: 'КонецФункции\n',
        1937: 'КонецФункции\n',
        1952: 'КонецФункции\n',
        1959: 'КонецФункции\n',
        1996: 'КонецФункции\n',
        2008: 'КонецФункции\n',
        2091: 'КонецФункции\n',
        2102: 'КонецФункции\n',
        2122: 'КонецФункции\n',
        2133: 'КонецФункции\n',
        2149: 'КонецФункции\n',
        2175: 'КонецФункции\n',
        2194: 'КонецФункции\n',
        2207: 'КонецФункции\n',
        2233: 'КонецФункции\n',
        2250: 'КонецФункции\n',
        2258: 'КонецФункции\n',
        2281: 'КонецФункции\n',
        2291: 'КонецФункции\n',
        2299: 'КонецФункции\n',
        2340: 'КонецФункции\n',
        2350: 'КонецФункции\n',
        2369: 'КонецФункции\n',
        2401: 'КонецФункции\n',
        2422: 'КонецФункции\n',
        2430: 'КонецФункции\n',
        2452: 'КонецФункции\n',
        2459: 'КонецФункции\n',
        2467: 'КонецПроцедуры\n',
        2473: 'КонецПроцедуры\n',
        2480: 'КонецФункции\n',
        2487: 'КонецПроцедуры\n',
        2493: 'КонецПроцедуры\n',
        2498: 'КонецФункции\n',
        2503: 'КонецФункции\n',
        2508: 'КонецФункции\n',
        2519: 'КонецПроцедуры\n',
        2525: 'КонецФункции\n',
        2631: 'КонецФункции\n',
        2661: 'КонецФункции\n',
        2674: 'КонецФункции\n',
        2763: 'КонецФункции\n',
    }
    sites = {
        107: '    Сообщить(Метка + ": [" + Строка(Значение) + "]");\n',
        545: '        Сообщить("table." + Метка + ": [error]");\n',
        556: '            Сообщить(СтрСоединить(СтрокиВывода, Символ(10)));\n',
        558: '            Сообщить("table." + Метка + ": [" + КомпактноеЗначениеТаблицы(Результат) + "]");\n',
        561: '        Сообщить("table." + Метка + ": [serialize-error]");\n',
        3591: 'Сообщить("table.ops.checkpoint.complete: [ok]");\n',
        3629: 'Сообщить("table.indexes.checkpoint.complete: [ok]");\n',
        3679: 'Сообщить("table.list.checkpoint.complete: [ok]");\n',
        3709: 'Сообщить("table.list.sort.checkpoint.complete: [ok]");\n',
        3722: 'Сообщить("table.list.copy.checkpoint.complete: [ok]");\n',
        3733: 'Сообщить("table.list.string.checkpoint.complete: [ok]");\n',
        3741: 'Сообщить("table.list.string-cache.checkpoint.complete: [ok]");\n',
        3746: 'Сообщить("table.list.string-cache.final.complete: [ok]");\n',
        3769: 'Сообщить("table.list.reference.checkpoint.complete: [ok]");\n',
        3771: 'Сообщить("table.checkpoint.complete: [ok]");\n',
        3803: 'Сообщить("table.descriptor-key.checkpoint.complete: [ok]");\n',
    }
    regions = {
        3: '#Область ВспомогательныеПроцедуры\n',
        190: '#Region FixedCollectionProbes\n',
        276: '#EndRegion\n',
        277: '#КонецОбласти\n',
        2766: '#Область МассивыИСтруктуры\n',
        2925: '#КонецОбласти\n',
        2927: '#Область СоответствиеИТипы\n',
        2986: '#КонецОбласти\n',
        2988: '#Область СнимкиИОбратныеКопии\n',
        3061: '#КонецОбласти\n',
        3063: '#Область ВложенныеМассивы\n',
        3112: '#КонецОбласти\n',
        3114: '#Область РавенствоИсточникиИКлючи\n',
        3174: '#КонецОбласти\n',
        3177: '#Область ВнутренняяСериализация\n',
        3275: '#КонецОбласти\n',
    }
    body_start = 2766
    capture = 'КоллекцииКлиентЗахват'
    reserved = (capture, 'КоллекцииКлиентСообщения',
                'КоллекцииКлиентСимволы', 'КоллекцииКлиентВыполнить')
    if (len(lines) != 3820
            or any(lines[i] != text for i, text in declarations.items())
            or any(lines[i] != text for i, text in endings.items())
            or any(lines[i] != text for i, text in sites.items())
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*(?:Процедура|Функция)\s', line)) != tuple(declarations)
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Конец(?:Процедуры|Функции)\b', line)) != tuple(endings)
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Сообщить\(', line)) != tuple(sites)
            or lines[body_start] != '#Область МассивыИСтруктуры\n'
            or lines[body_start - 1] != '\n'
            or lines[body_start - 2] != '// End descriptor Map-key checkpoint helpers.\n'
            or lines[1] != 'Перем Выход;\n'
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Перем\s', line)) != (1,)
            or {i: line for i, line in enumerate(lines)
                if re.match(r'^\s*#', line)} != regions
            or any(re.match(r'^\s*&', line) for line in lines)
            or re.search(r'(?i)(?<!\w)Выход(?!\w)', harness) is not None
            or any(name.casefold() in text.casefold()
                   for name in reserved for text in (original, harness))):
        raise FullError('invalid_input')
    # ObjectModule implicit locals must remain locals in a managed FormModule:
    # bare Object binds its main attribute, and Items binds the form item tree.
    # These four source-pinned helpers have assignments, not parameters, for the
    # colliding names. Do not rename identifiers or alter dynamic expression text.
    local_declarations = {
        1006: '    Перем Объект;\n',   # КонструкторИндексовПробы
        1017: '    Перем Объект;\n',  # КодекИндексовПробы
        1447: '    Перем Элементы;\n',  # ПоляСпискаПробы
        1682: '    Перем Объект;\n',  # КодекСпискаПробы
    }
    adapted = lines.copy()
    adapted[1] = ''  # Relocated to the form-module declaration prefix, not a local.
    for i in sites:
        adapted[i] = adapted[i].replace('Сообщить(', capture + '(', 1)
    for i in declarations:
        adapted[i] = '&НаКлиенте\n' + adapted[i]
    for i, declaration in local_declarations.items():
        adapted[i] += declaration
    # Inverse reconstruction is a runtime check, not disabled by Python -O.
    restored = adapted.copy()
    restored[1] = lines[1]
    for i, declaration in local_declarations.items():
        restored[i] = restored[i].removesuffix(declaration)
    for i in declarations:
        restored[i] = restored[i].removeprefix('&НаКлиенте\n')
    for i in sites:
        restored[i] = restored[i].replace(capture + '(', 'Сообщить(', 1)
    if ''.join(restored) != original:
        raise FullError('invalid_input')
    fixed = re.search(r'&НаКлиенте\nФункция ВычислитьПробу\(\)\n.*?\nКонецФункции\n',
                      harness, flags=re.DOTALL)
    if fixed is None or harness.count('Функция ВычислитьПробу()') != 1:
        raise FullError('invalid_input')
    # Client-only, non-exported form variables. Four UTF-8 bytes per character
    # plus one LF per message conservatively bounds capture; the verifier also
    # enforces the exact serialized UTF-8 byte and private JSON-envelope caps.
    budget = (MAX_OUTPUT - CLIENT_COLLECTIONS_MESSAGE_COUNT) // 4
    variables = ('&НаКлиенте\nПерем Выход;\n'
                 '&НаКлиенте\nПерем КоллекцииКлиентСообщения;\n'
                 '&НаКлиенте\nПерем КоллекцииКлиентСимволы;\n\n')
    wrapper = f'''&НаКлиенте
Процедура КоллекцииКлиентЗахват(Знач Текст)
    Если ТипЗнч(Текст) <> Тип("Строка") Тогда
        ВызватьИсключение "client-collections-type";
    КонецЕсли;
    Если КоллекцииКлиентСообщения.Количество() >= {CLIENT_COLLECTIONS_MESSAGE_COUNT}
        Или КоллекцииКлиентСимволы + СтрДлина(Текст) > {budget} Тогда
        ВызватьИсключение "client-collections-limit";
    КонецЕсли;
    КоллекцииКлиентСимволы = КоллекцииКлиентСимволы + СтрДлина(Текст);
    КоллекцииКлиентСообщения.Добавить(Текст);
КонецПроцедуры

'''
    wrapper += ''.join(adapted[:body_start])
    wrapper += '&НаКлиенте\nПроцедура КоллекцииКлиентВыполнить()\n'
    wrapper += ''.join(adapted[body_start:])
    wrapper += 'КонецПроцедуры\n\n'
    wrapper += '''&НаКлиенте
Функция ВычислитьПробу()
    КоллекцииКлиентСообщения = Новый Массив;
    КоллекцииКлиентСимволы = 0;
    КоллекцииКлиентВыполнить();
    Возврат КоллекцииКлиентСообщения;
КонецФункции
'''
    result = variables + harness[:fixed.start()] + wrapper + harness[fixed.end():]
    return generated_module(result.encode('utf-8'))


def client_collections_marker(path: Path, nonce: str, phase: str) -> dict:
    """Validate full collections evidence without predicting or filtering its output.

    This checks shape, not collections semantics. Only a downstream full-byte
    comparison with this run's independent native collections.out proves parity.
    """
    if not valid_nonce(nonce) or phase not in {'entered', 'completed'}:
        raise FullError('invalid_input')
    value = strict_json(secure_bytes(path, MAX_RESULT), max_depth=3)
    expected_count = 0 if phase == 'entered' else CLIENT_COLLECTIONS_MESSAGE_COUNT
    if (type(value) is not dict
            or set(value) != {'schema', 'nonce', 'phase', 'witness', 'values'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or value['phase'] != phase
            or value['witness'] != 'client' or type(value['values']) is not list
            or len(value['values']) != expected_count
            or any(type(item) is not str for item in value['values'])):
        raise FullError('invalid_result')
    try:
        if sum(len(item.encode('utf-8')) for item in value['values']) > MAX_OUTPUT:
            raise FullError('output_limit')
        serialize_messages(value['values'])
    except UnicodeError:
        raise FullError('invalid_result') from None
    return value


# All four call sites and the sole non-string literal are pinned, not generalized.
CLIENT_NUMBERS_SOURCE_SHA256 = '65075fff9adc854a317c74821052a9f9afa2b064d5fbb55b21dbab1ecb87556d'
CLIENT_NUMBERS_TEMPLATE_SHA256 = CLIENT_VALUES_TEMPLATE_SHA256
CLIENT_NUMBERS_MESSAGE_COUNT = 421
CLIENT_NUMBERS_RAW_ORDINAL = 30  # Zero-based; source line 307, Number literal 1234.5.


def empty_numbers_report() -> dict:
    return {**empty_values_report(), 'conversion_verified': False}


def verify_numbers_conversion(client: list[str], server: list[str], output: bytes) -> None:
    """Calibrate only the pinned number against fresh native server Сообщить.

    Client native Строка output is measured, not client UI Сообщить. The original
    raw server call stays untouched. No historical or interpreter text is an oracle.
    """
    if (type(client) is not list or type(server) is not list
            or len(client) != CLIENT_NUMBERS_MESSAGE_COUNT
            or len(server) != CLIENT_NUMBERS_MESSAGE_COUNT
            or any(type(value) is not str for value in client + server)
            or serialize_messages(server) != output):
        raise FullError('invalid_result')
    for messages in (client, server):
        raw = messages[CLIENT_NUMBERS_RAW_ORDINAL]
        if (messages[27] != 'present.string: [' + raw + ']'
                or messages[28] != 'present.concat: [' + raw + ']'
                or messages[29] != 'present.direct.next:'
                or messages[31] != 'numbers.complete: [ok]'):
            raise FullError('output_mismatch')
    if client[CLIENT_NUMBERS_RAW_ORDINAL] != server[CLIENT_NUMBERS_RAW_ORDINAL]:
        raise FullError('output_mismatch')


def client_numbers_module(source: bytes, template: bytes) -> bytes:
    """Preserve the complete source and calibrate its sole raw numeric call.

    The 19 helpers retain their order/local scopes with client directives. All
    four message-call identifiers change; only source line 307 uses the distinct
    Number(1234.5)/ordinal-30 capture. Its native Строка conversion is checked
    against this run's raw server message, not asserted to measure client UI.
    The other three sites remain string-only. No original expression is changed.
    """
    if (digest(source) != CLIENT_NUMBERS_SOURCE_SHA256
            or digest(template) != CLIENT_NUMBERS_TEMPLATE_SHA256):
        raise FullError('invalid_input')
    original = generated_module(source).decode('utf-8-sig')
    harness = generated_module(template).decode('utf-8-sig')
    lines = original.splitlines(keepends=True)
    # Check exact declarations, helper endings, body boundary and call sites.
    # Raw hashes above also pin all expression strings and protected branches.
    declarations = {
        2: 'Процедура ПроверитьДвоичноеЧисло(Знач Метка, Знач Текст)\n',
        11: 'Процедура ПроверитьШестнадцатеричноеЧисло(Знач Метка, Знач Текст)\n',
        20: 'Процедура ПроверитьСдвигВлево(Знач Метка, Знач Значение, Знач Смещение)\n',
        29: 'Процедура ПроверитьПобитовыйКонтроль(Знач Метка)\n',
        45: 'Процедура ПоказатьКомпактнуюЗапись(Знач Метка, Знач Значения)\n',
        54: 'Процедура ПроверитьСмешанноеСравнение(Знач Метка, Знач Число, Знач Булево)\n',
        76: 'Процедура ПроверитьЧтениеПространства()\n',
        102: 'Процедура ПроверитьОкр(Знач Метка, Знач Значение, Знач Разрядность, Знач Режим)\n',
        110: 'Процедура ПроверитьОкрПоУмолчанию(Знач Метка, Знач Значение)\n',
        118: 'Процедура ПроверитьРежим(Знач Метка, Знач Значение)\n',
        141: 'Процедура ПроверитьЦел(Знач Метка, Знач Значение)\n',
        149: 'Процедура ПроверитьЭкстремумы(Знач Метка, Знач Левое, Знач Правое)\n',
        162: 'Процедура ПроверитьОдинЭкстремум(Знач Метка, Знач Значение)\n',
        177: 'Процедура Показать(Метка, Знач Значение)\n',
        182: 'Процедура ПоказатьВнутреннее(Знач Метка, Знач Значение)\n',
        199: 'Процедура ПоказатьБулево(Метка, Знач Значение)\n',
        208: 'Процедура ПоказатьЧтениеВнутреннего(Знач Метка, Знач Текст)\n',
        225: 'Процедура ПоказатьЧастное(Метка, Знач Числитель, Знач Знаменатель)\n',
        235: 'Процедура ПроверитьМатематику(Знач Метка, Знач Выражение)\n',
    }
    endings = {
        9: 'КонецПроцедуры\n',
        18: 'КонецПроцедуры\n',
        27: 'КонецПроцедуры\n',
        42: 'КонецПроцедуры\n',
        51: 'КонецПроцедуры\n',
        73: 'КонецПроцедуры\n',
        99: 'КонецПроцедуры\n',
        108: 'КонецПроцедуры\n',
        116: 'КонецПроцедуры\n',
        137: 'КонецПроцедуры\n',
        147: 'КонецПроцедуры\n',
        160: 'КонецПроцедуры\n',
        173: 'КонецПроцедуры\n',
        179: 'КонецПроцедуры\n',
        197: 'КонецПроцедуры\n',
        205: 'КонецПроцедуры\n',
        222: 'КонецПроцедуры\n',
        231: 'КонецПроцедуры\n',
        247: 'КонецПроцедуры\n',
    }
    sites = {
        178: '    Сообщить(Метка + ": [" + Строка(Значение) + "]");\n',
        304: 'Сообщить("present.concat: [" + 1234.5 + "]");\n',
        305: 'Сообщить("present.direct.next:");\n',
        306: 'Сообщить(1234.5);\n',
    }
    body_start = 251
    capture = 'ЧислаКлиентЗахват'
    reserved = (capture, 'ЧислаКлиентСообщения',
                'ЧислаКлиентСимволы', 'ЧислаКлиентВыполнить', 'ЧислаКлиентЧисло')
    if (len(lines) != 735
            or any(lines[i] != text for i, text in declarations.items())
            or any(lines[i] != text for i, text in endings.items())
            or any(lines[i] != text for i, text in sites.items())
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*(?:Процедура|Функция)\s', line)) != tuple(declarations)
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Конец(?:Процедуры|Функции)\b', line)) != tuple(endings)
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Сообщить\(', line)) != tuple(sites)
            or lines[body_start] != 'Треть = 1 / 3;\n'
            or lines[body_start - 1] != '// и фиксированное количество значащих цифр. Прямой вывод предшествует сложению.\n'
            or any(re.match(r'^\s*[&#]', line) for line in lines)
            or any(name.casefold() in text.casefold()
                   for name in reserved for text in (original, harness))):
        raise FullError('invalid_input')
    adapted = lines.copy()
    for i in sites:
        adapted[i] = adapted[i].replace('Сообщить(',
            ('ЧислаКлиентЧисло' if i == 306 else capture) + '(', 1)
    for i in declarations:
        adapted[i] = '&НаКлиенте\n' + adapted[i]
    # Inverse reconstruction is a runtime check, not disabled by Python -O.
    restored = adapted.copy()
    for i in declarations:
        restored[i] = restored[i].removeprefix('&НаКлиенте\n')
    for i in sites:
        restored[i] = restored[i].replace(
            ('ЧислаКлиентЧисло' if i == 306 else capture) + '(', 'Сообщить(', 1)
    if ''.join(restored) != original:
        raise FullError('invalid_input')
    fixed = re.search(r'&НаКлиенте\nФункция ВычислитьПробу\(\)\n.*?\nКонецФункции\n',
                      harness, flags=re.DOTALL)
    if fixed is None or harness.count('Функция ВычислитьПробу()') != 1:
        raise FullError('invalid_input')
    # Client-only, non-exported form variables. Four UTF-8 bytes per character
    # plus one LF per message conservatively bounds capture; the verifier also
    # enforces the exact serialized UTF-8 byte and private JSON-envelope caps.
    budget = (MAX_OUTPUT - CLIENT_NUMBERS_MESSAGE_COUNT) // 4
    variables = ('&НаКлиенте\nПерем ЧислаКлиентСообщения;\n'
                 '&НаКлиенте\nПерем ЧислаКлиентСимволы;\n\n')
    wrapper = f'''&НаКлиенте
Процедура ЧислаКлиентЧисло(Знач Значение)
    Если ТипЗнч(Значение) <> Тип("Число") Тогда
        ВызватьИсключение "client-numbers-type";
    КонецЕсли;
    Если Значение <> 1234.5 Или ЧислаКлиентСообщения.Количество() <> 30 Тогда
        ВызватьИсключение "client-numbers-conversion";
    КонецЕсли;
    ЧислаКлиентЗахват(Строка(Значение));
КонецПроцедуры

&НаКлиенте
Процедура ЧислаКлиентЗахват(Знач Текст)
    Если ТипЗнч(Текст) <> Тип("Строка") Тогда
        ВызватьИсключение "client-numbers-type";
    КонецЕсли;
    Если ЧислаКлиентСообщения.Количество() >= {CLIENT_NUMBERS_MESSAGE_COUNT}
        Или ЧислаКлиентСимволы + СтрДлина(Текст) > {budget} Тогда
        ВызватьИсключение "client-numbers-limit";
    КонецЕсли;
    ЧислаКлиентСимволы = ЧислаКлиентСимволы + СтрДлина(Текст);
    ЧислаКлиентСообщения.Добавить(Текст);
КонецПроцедуры

'''
    wrapper += ''.join(adapted[:body_start])
    wrapper += '&НаКлиенте\nПроцедура ЧислаКлиентВыполнить()\n'
    wrapper += ''.join(adapted[body_start:])
    wrapper += 'КонецПроцедуры\n\n'
    wrapper += '''&НаКлиенте
Функция ВычислитьПробу()
    ЧислаКлиентСообщения = Новый Массив;
    ЧислаКлиентСимволы = 0;
    ЧислаКлиентВыполнить();
    Возврат ЧислаКлиентСообщения;
КонецФункции
'''
    result = variables + harness[:fixed.start()] + wrapper + harness[fixed.end():]
    return generated_module(result.encode('utf-8'))


def client_numbers_marker(path: Path, nonce: str, phase: str) -> dict:
    """Validate full numbers evidence without predicting or filtering its output.

    This checks shape, not numbers semantics. Only a downstream full-byte
    comparison with this run's independent native numbers.out proves parity.
    """
    if not valid_nonce(nonce) or phase not in {'entered', 'completed'}:
        raise FullError('invalid_input')
    value = strict_json(secure_bytes(path, MAX_RESULT), max_depth=3)
    expected_count = 0 if phase == 'entered' else CLIENT_NUMBERS_MESSAGE_COUNT
    if (type(value) is not dict
            or set(value) != {'schema', 'nonce', 'phase', 'witness', 'values'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or value['phase'] != phase
            or value['witness'] != 'client' or type(value['values']) is not list
            or len(value['values']) != expected_count
            or any(type(item) is not str for item in value['values'])):
        raise FullError('invalid_result')
    try:
        if sum(len(item.encode('utf-8')) for item in value['values']) > MAX_OUTPUT:
            raise FullError('output_limit')
        serialize_messages(value['values'])
    except UnicodeError:
        raise FullError('invalid_result') from None
    return value

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
                 'process_failed', 'unexpected_failure', 'export_failed', 'unsupported_observation'}


class FullError(Exception):
    """Only a fixed, non-sensitive reason is allowed across the boundary."""

    def __init__(self, kind: str):
        self.kind = kind if kind in FAILURE_KINDS else 'unexpected_failure'
        super().__init__(self.kind)


def valid_nonce(nonce: object) -> bool:
    return type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}', nonce) is not None


def empty_report(nonce: str, *, client_probe: bool = False, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False, client_async: bool = False) -> dict:
    if not valid_nonce(nonce) or ((watchdog_check or client_dates or client_values or client_collections or client_numbers) and not client_probe):
        raise FullError('invalid_input')
    if type(client_async) is not bool or (client_async and (not client_probe or watchdog_check or client_dates or client_values or client_collections or client_numbers)):
        raise FullError('invalid_input')
    return {**({'client_async': empty_async_report()} if client_async else {}),
            **({'client_probe': empty_client_report()} if client_probe else {}),
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
              inputs: Path, nonce: str, *, client_probe: bool = False, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False, client_async: bool = False) -> dict:
    report = empty_report(nonce, client_probe=client_probe, watchdog_check=watchdog_check, client_dates=client_dates, client_values=client_values, client_collections=client_collections, client_numbers=client_numbers, **({"client_async": True} if client_async else {}))
    report.update(status='failed', failure_kind='unexpected_failure')
    async_deadline = None
    active = None
    old_reader, old_process, old_build = launcher.read_result, launcher.run_process, launcher.build_epf
    try:
        if client_async:
            async_deadline = read_async_deadline(nonce)
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
        if client_async:
            report['client_async'] = run_client_async(platform, root / 'client-async', inputs, nonce, report['input_sha256'], deadline=async_deadline)
            if report['client_async']['status'] != 'ok':
                raise FullError(report['client_async']['failure_kind'])
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
    if type(data) is dict and type(data.get('schema')) is int and data['schema'] == 4:
        if ('client_async' not in data or 'client_probe' not in data
                or any(key in data for key in ('client_dates','client_values','client_collections','client_numbers','client_watchdog'))
                or len(json.dumps(data,separators=(',',':'),allow_nan=False).encode()) > MAX_STAGE_REPORT):
            raise FullError('invalid_result')
        base = {key:value for key,value in data.items() if key != 'client_async'}
        base['schema'] = 1
        return {**decode_stage_wire(base),'client_async':decode_async_wire(data['client_async'])}
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
    if type(report) is dict and 'client_async' in report:
        if type(report.get('schema')) is not int or report['schema'] != 1:
            raise FullError('invalid_result')
        base = {key:value for key,value in report.items() if key != 'client_async'}
        result = {**encode_stage_wire(base),'schema':4,'client_async':encode_async_wire(report['client_async'])}
        if decode_stage_wire(result) != report:
            raise FullError('invalid_result')
        return result
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


def client_marker_diagnostics(path: Path, nonce: str) -> dict:
    """Finite failure metadata only; never actual strings, paths or error text."""
    result = {'phase': 'invalid', 'kind': 'none', 'ordinal': -1, 'error_stage': 0}
    try:
        value = strict_json(secure_bytes(path, 2048), max_depth=3)
    except (FullError, OSError):
        return result
    if (not valid_nonce(nonce) or type(value) is not dict
            or set(value) != {'schema', 'nonce', 'phase', 'witness', 'values'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['nonce'] != nonce or value['witness'] != 'client'
            or type(value['values']) is not list
            or value['phase'] not in ('error', 'completed')):
        return result
    values = value['values']
    if value['phase'] == 'error':
        if values == []:
            result['phase'] = 'error'
        return result
    result['phase'] = 'completed'
    # The four old client observations precede the fixed local error sentinel.
    if (len(values) == 6 and values[:4] == CLIENT_VALUES[:4]
            and all(type(a) is type(b) for a, b in zip(values[:4], CLIENT_VALUES[:4]))
            and values[4] == 'directive.runtime-error' and type(values[5]) is int
            and 1 <= values[5] <= 11):
        result.update(kind='runtime_error', ordinal=values[5] + 3, error_stage=values[5])
        return result
    for index, (actual, expected) in enumerate(zip(values, CLIENT_VALUES)):
        if type(actual) is not type(expected) or actual != expected:
            result.update(kind='type' if type(actual) is not type(expected) else 'value', ordinal=index)
            return result
    if len(values) != len(CLIENT_VALUES):
        result.update(kind='count', ordinal=min(len(values), len(CLIENT_VALUES)))
    return result


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
    if 'client_async' in suite and suite['client_async']['status'] != 'not_started':
        fail_async_process_checkpoint(suite['client_async'], diagnostics)
        return
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
        try:
            completion = marker_reader(completed, nonce, 'completed')
        except FullError as error:
            if error.kind == 'invalid_result' and parity_output is None and not stall:
                record['marker_diagnostics'] = client_marker_diagnostics(completed, nonce)
            raise
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


# Exact historical-adapter inverse only; the host executes the full strict witness.
CLIENT_DUAL_TEMPLATE_SHA256 = 'c991b9fbf808a59fad6edc10ad9768efe85bc3bd2da9d7b63c1daa5cdb118413'
CLIENT_DUAL_SHARED_SHA256 = 'b79c23abb756c3b3965e3a46ad7212e582db917ff319facc70a1efb18a470e14'
CLIENT_DUAL_PREFIX = b'// BEGIN bounded dual declarations\n&AtServer\nVar DualProbeServerState;\n\n// END bounded dual declarations\n'
CLIENT_DUAL_BLOCK = b'\n// BEGIN bounded dual witness\n&\xd0\x9d\xd0\xb0\xd0\x9a\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xb5\xd0\x9d\xd0\xb0\xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80\xd0\xb5\xd0\x91\xd0\xb5\xd0\xb7\xd0\x9a\xd0\xbe\xd0\xbd\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82\xd0\xb0\nProcedure DualProbeLeaf(ReferenceValue)\n    ReferenceValue = ReferenceValue + 1;\nEndProcedure\n\n&AtClientAtServerNoContext\nFunction DualProbeOperation(ReferenceValue, Val ContainerValue, Val Escape)\n    Var ProfileMask;\n    ReferenceValue = ReferenceValue + 10;\n    DualProbeLeaf(ReferenceValue);\n    ContainerValue[0] = ContainerValue[0] + 10;\n    If Escape Then\n        Raise "dual-directive-controlled-failure";\n    EndIf;\n    ProfileMask = 0;\n#If AtClient Then\n    ProfileMask = ProfileMask + 4;\n#EndIf\n#If AtServer Then\n    ProfileMask = ProfileMask + 8;\n#EndIf\n    Return New Structure("Container,Mask", ContainerValue, ProfileMask);\nEndFunction\n\n&AtClient\nFunction DualProbeFromClient()\n    Var Observations, ScalarValue, ContainerValue, OperationResult, Caught;\n    Observations = New Array;\n    ScalarValue = 1;\n    ContainerValue = New Array;\n    ContainerValue.Add(2);\n    OperationResult = DualProbeOperation(ScalarValue, ContainerValue, False);\n    Observations.Add(OperationResult.Mask);\n    OperationResult.Container[0] = OperationResult.Container[0] + 20;\n    Observations.Add(ContainerValue[0]);\n    ScalarValue = 6;\n    ContainerValue = New Array;\n    ContainerValue.Add(7);\n    Caught = False;\n    Try\n        DualProbeOperation(ScalarValue, ContainerValue, True);\n    Except\n        If Find(ErrorDescription(), "dual-directive-controlled-failure") > 0 Then\n            Caught = True;\n        Else\n            Raise;\n        EndIf;\n    EndTry;\n    If Not Caught Then\n        Raise "dual-directive-expected-exception-missing";\n    EndIf;\n    Observations.Add(ScalarValue);\n    Return Observations;\nEndFunction\n\n&AtServer\nFunction DualProbeFromServer()\n    Var Observations, ScalarValue, ContainerValue, OperationResult, Caught;\n    DualProbeServerState = 40;\n    Observations = New Array;\n    ScalarValue = 1;\n    ContainerValue = New Array;\n    ContainerValue.Add(2);\n    OperationResult = DualProbeOperation(ScalarValue, ContainerValue, False);\n    Observations.Add(OperationResult.Mask);\n    ScalarValue = 6;\n    ContainerValue = New Array;\n    ContainerValue.Add(7);\n    Caught = False;\n    Try\n        DualProbeOperation(ScalarValue, ContainerValue, True);\n    Except\n        If Find(ErrorDescription(), "dual-directive-controlled-failure") > 0 Then\n            Caught = True;\n        Else\n            Raise;\n        EndIf;\n    EndTry;\n    If Not Caught Then\n        Raise "dual-directive-expected-exception-missing";\n    EndIf;\n    Observations.Add(ScalarValue);\n    DualProbeServerState = DualProbeServerState + 1;\n    Observations.Add(DualProbeServerState);\n    Return Observations;\nEndFunction\n\n&AtServerNoContext\nFunction DualProbeFromServerNoContext()\n    Var Observations, ScalarValue, ContainerValue, OperationResult, Caught;\n    Observations = New Array;\n    ScalarValue = 1;\n    ContainerValue = New Array;\n    ContainerValue.Add(2);\n    OperationResult = DualProbeOperation(ScalarValue, ContainerValue, False);\n    Observations.Add(OperationResult.Mask);\n    OperationResult.Container[0] = OperationResult.Container[0] + 20;\n    Observations.Add(ContainerValue[0]);\n    ScalarValue = 6;\n    ContainerValue = New Array;\n    ContainerValue.Add(7);\n    Caught = False;\n    Try\n        DualProbeOperation(ScalarValue, ContainerValue, True);\n    Except\n        If Find(ErrorDescription(), "dual-directive-controlled-failure") > 0 Then\n            Caught = True;\n        Else\n            Raise;\n        EndIf;\n    EndTry;\n    If Not Caught Then\n        Raise "dual-directive-expected-exception-missing";\n    EndIf;\n    Observations.Add(ScalarValue);\n    Return Observations;\nEndFunction\n\n&AtClient\nFunction CollectDualDirectiveProbe() Export\n    Var Observations, Part, Item;\n    Observations = New Array;\n    Part = DualProbeFromClient();\n    For Each Item In Part Do\n        Observations.Add(Item);\n    EndDo;\n    Part = DualProbeFromServer();\n    For Each Item In Part Do\n        Observations.Add(Item);\n    EndDo;\n    Part = DualProbeFromServerNoContext();\n    For Each Item In Part Do\n        Observations.Add(Item);\n    EndDo;\n    Return Observations;\nEndFunction\n\n&AtClient\nFunction DualProbeEncode(Observations)\n    Var Encoded, Observation, Slot, Digits, Hundreds, Tens, Units;\n    If Observations.Count() <> 9 Then\n        Raise "dual-directive-invalid-count";\n    EndIf;\n    Encoded = "dual.v1:";\n    Digits = "0123456789";\n    Slot = 0;\n    For Each Observation In Observations Do\n        If TypeOf(Observation) <> Type("Number") Then\n            Raise "dual-directive-invalid-type";\n        EndIf;\n        If Observation < 0 Or Observation > 999 Or Int(Observation) <> Observation Then\n            Raise "dual-directive-invalid-range";\n        EndIf;\n        If (Slot = 0 Or Slot = 3 Or Slot = 6) And Observation > 15 Then\n            Raise "dual-directive-invalid-profile";\n        EndIf;\n        Hundreds = Int(Observation / 100);\n        Tens = Int(Observation / 10) - Hundreds * 10;\n        Units = Observation - Int(Observation / 10) * 10;\n        Encoded = Encoded + Mid(Digits, Hundreds + 1, 1)\n            + Mid(Digits, Tens + 1, 1) + Mid(Digits, Units + 1, 1);\n        Slot = Slot + 1;\n    EndDo;\n    Return Encoded;\nEndFunction\n\n&AtClient\nProcedure DualProbeAppend(RecordsOut)\n    RecordsOut.Add(DualProbeEncode(CollectDualDirectiveProbe()));\nEndProcedure\n'
CLIENT_DUAL_CALL = b'    DualProbeAppend(\xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f);\n'


def dual_shared_source(raw: bytes) -> bytes:
    """Restore strict134 only for the four frozen historical parity adapters."""
    tail = CLIENT_DUAL_BLOCK + CLIENT_NOCONTEXT_INITIALIZER
    if (digest(raw) != CLIENT_DUAL_TEMPLATE_SHA256
            or not raw.startswith(CLIENT_DUAL_PREFIX) or not raw.endswith(tail)
            or raw.count(CLIENT_DUAL_PREFIX) != 1 or raw.count(CLIENT_DUAL_BLOCK) != 1
            or raw.count(CLIENT_DUAL_CALL) != 1):
        raise FullError('source_changed')
    restored = (raw[len(CLIENT_DUAL_PREFIX):-len(tail)] + CLIENT_NOCONTEXT_INITIALIZER).replace(
        CLIENT_DUAL_CALL, b'', 1)
    if digest(restored) != CLIENT_DUAL_SHARED_SHA256:
        raise FullError('source_changed')
    return restored


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


# New mixed-context witness is removed only by this exact, hash-bound inverse.
# The four parity adapters retain their original pins and generated bytes.
CLIENT_DIRECTIVE_TEMPLATE_SHA256 = 'c991b9fbf808a59fad6edc10ad9768efe85bc3bd2da9d7b63c1daa5cdb118413'
CLIENT_LEGACY_TEMPLATE_SHA256 = '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328'


def client_parity_template(template: bytes) -> bytes:
    template = dual_shared_source(template)
    template = nocontext_shared_source(template)
    template = module_context_shared_source(template)
    if digest(template) != CLIENT_MODULE_SHARED_SHA256:
        raise FullError('invalid_input')
    marker = b"\n// BEGIN bounded directive witness\n"
    call = b'    \xd0\x94\xd0\xbb\xd1\x8f \xd0\x9a\xd0\xb0\xd0\xb6\xd0\xb4\xd0\xbe\xd0\xb3\xd0\xbe \xd0\x9d\xd0\xb0\xd0\xb1\xd0\xbb\xd1\x8e\xd0\xb4\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\x98\xd0\xb7 DirectiveWitnessValues() \xd0\xa6\xd0\xb8\xd0\xba\xd0\xbb\n        \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f.\xd0\x94\xd0\xbe\xd0\xb1\xd0\xb0\xd0\xb2\xd0\xb8\xd1\x82\xd1\x8c(\xd0\x9d\xd0\xb0\xd0\xb1\xd0\xbb\xd1\x8e\xd0\xb4\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5);\n    \xd0\x9a\xd0\xbe\xd0\xbd\xd0\xb5\xd1\x86\xd0\xa6\xd0\xb8\xd0\xba\xd0\xbb\xd0\xb0;\n'
    if template.count(marker) != 1 or template.count(call) != 1:
        raise FullError('invalid_input')
    copyback_call = b'    For Each CopybackValue In RunScalarCopybackProbe() Do\n        \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f.\xd0\x94\xd0\xbe\xd0\xb1\xd0\xb0\xd0\xb2\xd0\xb8\xd1\x82\xd1\x8c(CopybackValue);\n    EndDo;\n'
    if template.count(copyback_call) != 1:
        raise FullError('invalid_input')
    object_call = b'    For Each ObjectTransferValue In RunObjectTransferProbe() Do\n        \xd0\x97\xd0\xbd\xd0\xb0\xd1\x87\xd0\xb5\xd0\xbd\xd0\xb8\xd1\x8f.\xd0\x94\xd0\xbe\xd0\xb1\xd0\xb0\xd0\xb2\xd0\xb8\xd1\x82\xd1\x8c(ObjectTransferValue);\n    EndDo;\n'
    if template.count(object_call) != 1:
        raise FullError('invalid_input')
    restored = template.split(marker, 1)[0].replace(call, b'', 1).replace(copyback_call, b'', 1).replace(object_call, b'', 1)
    if digest(restored) != CLIENT_LEGACY_TEMPLATE_SHA256:
        raise FullError('invalid_input')
    return restored


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
    if digest(template) == CLIENT_DIRECTIVE_TEMPLATE_SHA256:
        template = client_parity_template(template)
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
    if digest(template) == CLIENT_DIRECTIVE_TEMPLATE_SHA256:
        template = client_parity_template(template)
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
CLIENT_COLLECTIONS_SOURCE_SHA256 = '42c1fedddb8a689f3ba2ca6a241b1d19d38c0bea4da8a29e5934b3082a43fdfb'
CLIENT_COLLECTIONS_TEMPLATE_SHA256 = '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328'
CLIENT_COLLECTIONS_MESSAGE_COUNT = 854


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

    All 118 source helpers remain in their original order with client directives.
    Only the 16 verified message-call identifiers change, and the complete module
    body moves into a client procedure. Four explicit helper-local declarations
    preserve source-local bindings against the managed form's Object/Items names.
    Expressions, conversions and error paths stay byte-identical. No server
    trampoline or reference collections are added.
    """
    if digest(template) == CLIENT_DIRECTIVE_TEMPLATE_SHA256:
        template = client_parity_template(template)
    if (digest(source) != CLIENT_COLLECTIONS_SOURCE_SHA256
            or digest(template) != CLIENT_COLLECTIONS_TEMPLATE_SHA256):
        raise FullError('invalid_input')
    original = generated_module(source).decode('utf-8-sig')
    harness = generated_module(template).decode('utf-8-sig')
    lines = original.splitlines(keepends=True)
    # Check exact declarations, helper endings, body boundary and call sites.
    # Raw hashes above also pin all expression strings and protected branches.
    declarations = {
        8: 'Процедура ПроверитьПозициюИсключения(Знач Позиция)\n',
        36: 'Процедура ПроверитьСписокИсключения(Знач Метка, Знач Наличие, Знач Список)\n',
        64: 'Процедура ПроверитьСписокВключения(Знач Метка, Знач Список)\n',
        80: 'Процедура ПроверитьУдалениеЗаГраницей(Знач Метка)\n',
        113: 'Процедура ПроверитьЗаполнениеСвойств(Знач Метка)\n',
        145: 'Процедура ПоказатьСоставМассива(Знач Метка, Знач Массив)\n',
        154: 'Процедура ПроверитьЗаполненность(Знач Метка, Знач Значение)\n',
        163: 'Процедура Показать(Знач Метка, Знач Значение)\n',
        168: 'Процедура ПоказатьВнутреннее(Знач Метка, Знач Значение, Восстановлено = Неопределено)\n',
        198: 'Процедура ПоказатьВосстановленныеСсылки(Знач Метка, Знач Пара)\n',
        217: 'Процедура ПоказатьБулево(Знач Метка, Знач Значение)\n',
        222: 'Процедура ПоказатьВнутренниеСсылки(Знач Метка, Знач Первое, Знач ТакоеЖе)\n',
        238: 'Процедура ПолучитьПозиции(Знач Заказ, Результат)\n',
        242: 'Процедура ДобавитьПозицию(Знач Позиции)\n',
        249: 'Функция РезультатРавенства(Знач Левое, Знач Правое)\n',
        257: 'Процедура ПоказатьПоиск(Знач Метка, Знач Значения, Знач Искомое)\n',
        265: 'Функция ПрочитатьКлюч(Знач Словарь, Знач Ключ)\n',
        274: 'Процедура ИсследоватьФиксированное(Знач Метка, Знач Первое, Знач ТакоеЖе, Знач Другое)\n',
        338: 'Функция ЗначенияОперацийТаблицы(Знач Текст)\n',
        342: 'Функция СсылкаПослеОперации(Знач Таблица, Знач СтрокаТаблицы)\n',
        358: 'Функция СортировкаТаблицыПробы(Знач Набор, Знач Порядок, Знач Сравнение = "omitted")\n',
        411: 'Функция СверткаТаблицыПробы(Знач Набор, Знач Группы, Знач Суммы = "omitted")\n',
        491: 'Функция НаблюдениеУдаленнойСтроки(Знач Таблица, Знач Удаленная, Знач Первая)\n',
        513: 'Функция УдаленнаяПослеСверткиПробы(Знач Групп, Знач Действие)\n',
        534: 'Функция ПорядокИтоговСверткиПробы(Знач Сценарий)\n',
        561: 'Функция КомпактноеЗначениеТаблицы(Знач Значение)\n',
        584: 'Процедура ДобавитьПоляВыводаТаблицы(СтрокиВывода, Знач Путь, Знач Значение)\n',
        594: 'Функция КонструкторТаблицыПробы(Знач Объект)\n',
        598: 'Процедура НаблюдатьТаблицы(Знач Метка, Знач Выражение)\n',
        622: 'Функция НоваяТаблицаПробы()\n',
        636: 'Функция ПоляКолонкиПробы(Знач Колонка)\n',
        641: 'Функция ПоляСтрокиПробы(Знач СтрокаТаблицы)\n',
        649: 'Функция ПоляТаблицыПробы(Знач Таблица)\n',
        661: 'Функция ВидОбъектаТаблицы(Знач Объект)\n',
        685: 'Функция КодекТаблицыПробы(Знач Объект)\n',
        726: 'Функция ОбъектТаблицыПробы(Знач ИмяОбъекта)\n',
        741: 'Функция ЧтениеТаблицыПробы(Знач Выражение)\n',
        755: 'Функция ИзменениеТаблицыПробы(Знач Сценарий)\n',
        924: 'Функция ТипизированнаяТаблицаПробы(Знач Описание, Знач Значение)\n',
        937: 'Функция СвязиТаблицыПробы(Знач Сценарий)\n',
        1027: 'Функция ТаблицаИндексовПробы()\n',
        1038: 'Функция ПоляИндексаПробы(Знач Индекс)\n',
        1044: 'Функция ПоляИндексовПробы(Знач Индексы)\n',
        1050: 'Функция ПоискИндексовПробы(Знач Таблица, Знач Ссылка)\n',
        1063: 'Функция КонструкторИндексовПробы(Знач Вид)\n',
        1074: 'Функция КодекИндексовПробы(Знач Вид)\n',
        1120: 'Функция ОшибкиИндексовПробы(Знач Действие)\n',
        1152: 'Функция ИндексыТаблицыПробы(Знач Сценарий, Знач Список = "Key")\n',
        1276: 'Функция ДопТаблицаИндексов()\n',
        1286: 'Функция ДопИдентификаторыИндексов(Знач СтрокиТаблицы)\n',
        1292: 'Функция ДопПервыйИндексПоиска(Знач Таблица, Знач Вид = "key")\n',
        1302: 'Функция ДопПоискИндексов(Знач Таблица, Знач Вид = "edit")\n',
        1326: 'Функция ДопПорядокИндексов(Знач Вид)\n',
        1364: 'Функция ДопВыборИндекса()\n',
        1393: 'Функция ДопСоставКопииИндексов(Знач Таблица)\n',
        1408: 'Функция ДопКопииИндексов()\n',
        1441: 'Функция ДопУдаленныйИндекс(Знач Индексы, Знач Сохраненный)\n',
        1451: 'Функция ДопСвязиИндексов()\n',
        1487: 'Функция НовыйСписокПробы(Знач Вид = "base")\n',
        1496: 'Функция ПоляЭлементаСписка(Знач Элемент)\n',
        1504: 'Функция ПоляСпискаПробы(Знач Список)\n',
        1523: 'Функция ОтветСпискаПробы(Знач Ответ, Знач Сохраненный)\n',
        1533: 'Функция ДействиеСпискаПробы(Знач Команда, Знач Вид = "base")\n',
        1555: 'Функция СерияСпискаПробы(Знач Команды, Знач Вид = "base")\n',
        1563: 'Функция ИдентичностьСпискаПробы()\n',
        1593: 'Функция ПоискЗначенияСпискаПробы()\n',
        1636: 'Функция СвязиСпискаПробы(Знач Вид)\n',
        1675: 'Функция КопированиеСпискаПробы(Знач Вид)\n',
        1718: 'Функция ИдентификаторыСпискаПробы(Знач Список)\n',
        1739: 'Функция КодекСпискаПробы(Знач Вид)\n',
        1795: 'Функция ВозвращенныеЭлементыСпискаПробы()\n',
        1815: 'Функция ЧужойСдвигСпискаПробы()\n',
        1850: 'Функция ПорядокСортировкиСписка(Знач Список, Знач Исходные)\n',
        1871: 'Функция НаборСортировкиСписка(Знач Вид)\n',
        1918: 'Функция ДействиеСортировкиСписка(Знач Вид, Знач Команда)\n',
        1945: 'Функция СерияСортировкиСписка(Знач Вид, Знач Команды)\n',
        1953: 'Функция ТипНаправленияСортировкиПробы()\n',
        1973: 'Функция КодекНаправленияСортировкиПробы(Знач Направление, Знач СТипом = Ложь)\n',
        2000: 'Функция ПозицияСсылкиКопииСписка(Знач Список, Знач Элемент)\n',
        2011: 'Функция РазмерыКопииСписка(Знач Список, Знач Копия)\n',
        2018: 'Функция СнимокКопированияСписка(Знач Список)\n',
        2055: 'Функция ДобавлениеПослеКопииСписка(Знач Список, Знач Представление)\n',
        2067: 'Функция ИсторияКопированияСписка(Знач Вид)\n',
        2154: 'Функция РезультатТекстаСписка(Знач Значение)\n',
        2161: 'Функция СнимокТекстаСписка(Знач Список)\n',
        2181: 'Функция ОдинТекстСписка(Знач Значение, Знач Вид = "value")\n',
        2192: 'Функция ПустыеТекстыСписка()\n',
        2208: 'Функция СкалярныеТекстыСписка(Знач Вид)\n',
        2234: 'Функция СоставныеТекстыСписка()\n',
        2253: 'Функция ЗагруженныеТекстыСписка()\n',
        2266: 'Функция ЖивыеТекстыСписка()\n',
        2295: 'Функция ПоляКэшаСписка(Знач Список)\n',
        2309: 'Функция ПолеИнициализацииКэша(Знач Элемент, Знач Вид, Знач Значение)\n',
        2317: 'Функция ИнициализацияКэшаСписка(Знач Вид, Знач Чтение)\n',
        2340: 'Функция НачалоКэшаСписка()\n',
        2350: 'Функция ПоменятьПервыйКэшСписка(Знач Список, Знач Значение, Знач Представление)\n',
        2358: 'Функция ДействиеКэшаСписка(Знач Вид)\n',
        2399: 'Функция ИзмененияКэшаСписка(Знач Группа)\n',
        2409: 'Функция ПустойКэшСписка()\n',
        2428: 'Функция КопияКэшаСписка()\n',
        2462: 'Функция ПустойРезультатКэшаСписка(Знач Вид)\n',
        2481: 'Функция ПустыеРезультатыКэшаСписка()\n',
        2489: 'Функция КороткаяСортировкаКэшаСписка(Знач ПоПредставлению)\n',
        2511: 'Функция КороткиеСортировкиКэшаСписка()\n',
        2520: 'Процедура ЗаписатьСсылкуСписка(Поле, Знач Новое, Знач Журнал)\n',
        2526: 'Процедура ЗаписатьЗначениеСписка(Знач Поле, Знач Новое, Знач Журнал)\n',
        2532: 'Функция ЖиваяСсылкаСписка(Поле, Знач Элемент, Знач Журнал)\n',
        2539: 'Процедура ДвеСсылкиСписка(Первое, Второе, Знач Журнал)\n',
        2546: 'Процедура ОшибкаПослеСсылкиСписка(Поле, Знач Журнал)\n',
        2552: 'Функция ПолучательСсылкиСписка(Знач Список, Знач Журнал)\n',
        2557: 'Функция ИндексСсылкиСписка(Знач Журнал)\n',
        2562: 'Функция ПозднийАргументСписка(Знач Журнал)\n',
        2567: 'Процедура ПерестроитьСсылкуСписка(Поле, Знач Список, Знач Элемент, Знач Журнал)\n',
        2578: 'Функция ВозвратСсылкиСписка(Поле, Знач Журнал)\n',
        2584: 'Функция ПробаСсылкиСписка(Знач Случай)\n',
        2693: 'Функция ПараКлючейОписаний(Знач Вид)\n',
        2720: 'Функция РавенствоКлючейОписаний(Знач Вид)\n',
        2733: 'Функция ИсторияКлючейОписаний(Знач Вид, Знач Режим)\n',
    }
    endings = {
        31: 'КонецПроцедуры\n',
        59: 'КонецПроцедуры\n',
        76: 'КонецПроцедуры\n',
        108: 'КонецПроцедуры\n',
        142: 'КонецПроцедуры\n',
        151: 'КонецПроцедуры\n',
        161: 'КонецПроцедуры\n',
        165: 'КонецПроцедуры\n',
        194: 'КонецПроцедуры\n',
        215: 'КонецПроцедуры\n',
        219: 'КонецПроцедуры\n',
        236: 'КонецПроцедуры\n',
        240: 'КонецПроцедуры\n',
        245: 'КонецПроцедуры\n',
        255: 'КонецФункции\n',
        263: 'КонецПроцедуры\n',
        272: 'КонецФункции\n',
        331: 'КонецПроцедуры\n',
        340: 'КонецФункции\n',
        356: 'КонецФункции\n',
        409: 'КонецФункции\n',
        489: 'КонецФункции\n',
        511: 'КонецФункции\n',
        532: 'КонецФункции\n',
        553: 'КонецФункции\n',
        581: 'КонецФункции\n',
        592: 'КонецПроцедуры\n',
        596: 'КонецФункции\n',
        620: 'КонецПроцедуры\n',
        633: 'КонецФункции\n',
        639: 'КонецФункции\n',
        647: 'КонецФункции\n',
        659: 'КонецФункции\n',
        682: 'КонецФункции\n',
        724: 'КонецФункции\n',
        739: 'КонецФункции\n',
        751: 'КонецФункции\n',
        922: 'КонецФункции\n',
        935: 'КонецФункции\n',
        1020: 'КонецФункции\n',
        1036: 'КонецФункции\n',
        1042: 'КонецФункции\n',
        1048: 'КонецФункции\n',
        1060: 'КонецФункции\n',
        1072: 'КонецФункции\n',
        1117: 'КонецФункции\n',
        1150: 'КонецФункции\n',
        1271: 'КонецФункции\n',
        1284: 'КонецФункции\n',
        1290: 'КонецФункции\n',
        1300: 'КонецФункции\n',
        1324: 'КонецФункции\n',
        1362: 'КонецФункции\n',
        1391: 'КонецФункции\n',
        1406: 'КонецФункции\n',
        1439: 'КонецФункции\n',
        1449: 'КонецФункции\n',
        1482: 'КонецФункции\n',
        1494: 'КонецФункции\n',
        1502: 'КонецФункции\n',
        1521: 'КонецФункции\n',
        1530: 'КонецФункции\n',
        1553: 'КонецФункции\n',
        1561: 'КонецФункции\n',
        1591: 'КонецФункции\n',
        1634: 'КонецФункции\n',
        1673: 'КонецФункции\n',
        1716: 'КонецФункции\n',
        1737: 'КонецФункции\n',
        1791: 'КонецФункции\n',
        1813: 'КонецФункции\n',
        1845: 'КонецФункции\n',
        1869: 'КонецФункции\n',
        1916: 'КонецФункции\n',
        1943: 'КонецФункции\n',
        1951: 'КонецФункции\n',
        1971: 'КонецФункции\n',
        1994: 'КонецФункции\n',
        2009: 'КонецФункции\n',
        2016: 'КонецФункции\n',
        2053: 'КонецФункции\n',
        2065: 'КонецФункции\n',
        2148: 'КонецФункции\n',
        2159: 'КонецФункции\n',
        2179: 'КонецФункции\n',
        2190: 'КонецФункции\n',
        2206: 'КонецФункции\n',
        2232: 'КонецФункции\n',
        2251: 'КонецФункции\n',
        2264: 'КонецФункции\n',
        2290: 'КонецФункции\n',
        2307: 'КонецФункции\n',
        2315: 'КонецФункции\n',
        2338: 'КонецФункции\n',
        2348: 'КонецФункции\n',
        2356: 'КонецФункции\n',
        2397: 'КонецФункции\n',
        2407: 'КонецФункции\n',
        2426: 'КонецФункции\n',
        2458: 'КонецФункции\n',
        2479: 'КонецФункции\n',
        2487: 'КонецФункции\n',
        2509: 'КонецФункции\n',
        2516: 'КонецФункции\n',
        2524: 'КонецПроцедуры\n',
        2530: 'КонецПроцедуры\n',
        2537: 'КонецФункции\n',
        2544: 'КонецПроцедуры\n',
        2550: 'КонецПроцедуры\n',
        2555: 'КонецФункции\n',
        2560: 'КонецФункции\n',
        2565: 'КонецФункции\n',
        2576: 'КонецПроцедуры\n',
        2582: 'КонецФункции\n',
        2688: 'КонецФункции\n',
        2718: 'КонецФункции\n',
        2731: 'КонецФункции\n',
        2820: 'КонецФункции\n',
    }
    sites = {
        164: '    Сообщить(Метка + ": [" + Строка(Значение) + "]");\n',
        602: '        Сообщить("table." + Метка + ": [error]");\n',
        613: '            Сообщить(СтрСоединить(СтрокиВывода, Символ(10)));\n',
        615: '            Сообщить("table." + Метка + ": [" + КомпактноеЗначениеТаблицы(Результат) + "]");\n',
        618: '        Сообщить("table." + Метка + ": [serialize-error]");\n',
        3648: 'Сообщить("table.ops.checkpoint.complete: [ok]");\n',
        3686: 'Сообщить("table.indexes.checkpoint.complete: [ok]");\n',
        3736: 'Сообщить("table.list.checkpoint.complete: [ok]");\n',
        3766: 'Сообщить("table.list.sort.checkpoint.complete: [ok]");\n',
        3779: 'Сообщить("table.list.copy.checkpoint.complete: [ok]");\n',
        3790: 'Сообщить("table.list.string.checkpoint.complete: [ok]");\n',
        3798: 'Сообщить("table.list.string-cache.checkpoint.complete: [ok]");\n',
        3803: 'Сообщить("table.list.string-cache.final.complete: [ok]");\n',
        3826: 'Сообщить("table.list.reference.checkpoint.complete: [ok]");\n',
        3828: 'Сообщить("table.checkpoint.complete: [ok]");\n',
        3860: 'Сообщить("table.descriptor-key.checkpoint.complete: [ok]");\n',
    }
    regions = {
        3: '#Область ВспомогательныеПроцедуры\n',
        247: '#Region FixedCollectionProbes\n',
        333: '#EndRegion\n',
        334: '#КонецОбласти\n',
        2823: '#Область МассивыИСтруктуры\n',
        2982: '#КонецОбласти\n',
        2984: '#Область СоответствиеИТипы\n',
        3043: '#КонецОбласти\n',
        3045: '#Область СнимкиИОбратныеКопии\n',
        3118: '#КонецОбласти\n',
        3120: '#Область ВложенныеМассивы\n',
        3169: '#КонецОбласти\n',
        3171: '#Область РавенствоИсточникиИКлючи\n',
        3231: '#КонецОбласти\n',
        3234: '#Область ВнутренняяСериализация\n',
        3332: '#КонецОбласти\n',
    }
    body_start = 2823
    capture = 'КоллекцииКлиентЗахват'
    reserved = (capture, 'КоллекцииКлиентСообщения',
                'КоллекцииКлиентСимволы', 'КоллекцииКлиентВыполнить')
    if (len(lines) != 3894
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
            or lines[9] != '    Перем Приемник, Источник, Статус, ЗначениеMissing, ЕстьMissing;\n'
            or tuple(i for i, line in enumerate(lines)
                     if re.match(r'^\s*Перем\s', line)) != (1, 9)
            or {i: line for i, line in enumerate(lines)
                if re.match(r'^\s*#', line)} != regions
            or any(re.match(r'^\s*&', line) for line in lines)
            or re.search(r'(?i)(?<!\w)Выход(?!\w)', harness) is not None
            or any(name.casefold() in text.casefold()
                   for name in reserved for text in (original, harness))):
        raise FullError('invalid_input')
    # Preserve exact new observer/setup text under a top-level-hash rebase too.
    exclude_blocks = (
        ('// Begin FillPropertyValues EXCLUDE source-order discriminator helpers.\n', '// End FillPropertyValues EXCLUDE source-order discriminator helpers.\n\n',
         '4b79c88f666e55e19a704a1258da7fde10fe7e1f8731290808a27bcc5ab0484e'),
        ('// Begin FillPropertyValues EXCLUDE checkpoint helpers.\n', '// End FillPropertyValues EXCLUDE checkpoint helpers.\n\n',
         'ba8891f93141eea9d2c799b21840031b1fa930ca6fb741022682599f89b22ea8'),
        ('// Begin FillPropertyValues EXCLUDE checkpoint observations.\n', '// End FillPropertyValues EXCLUDE checkpoint observations.\n',
         '789686567bbc3c47165c84aee9d617436f34b2295f59484068d8049a70fd906a'),
        ('// Begin FillPropertyValues EXCLUDE source-order discriminator observations.\n', '// End FillPropertyValues EXCLUDE source-order discriminator observations.\n',
         '7c10421d010312075ecaf0de592e2f17e04055c9d7ef47f1f797737324c3221c'),
    )
    for begin, finish, expected in exclude_blocks:
        if original.count(begin) != 1 or original.count(finish) != 1:
            raise FullError('invalid_input')
        content = begin + original.split(begin, 1)[1].split(finish, 1)[0] + finish
        if digest(content.encode('utf-8')) != expected:
            raise FullError('invalid_input')
    # ObjectModule implicit locals must remain locals in a managed FormModule:
    # bare Object binds its main attribute, and Items binds the form item tree.
    # These four source-pinned helpers have assignments, not parameters, for the
    # colliding names. Do not rename identifiers or alter dynamic expression text.
    local_declarations = {
        1063: '    Перем Объект;\n',   # КонструкторИндексовПробы
        1074: '    Перем Объект;\n',  # КодекИндексовПробы
        1504: '    Перем Элементы;\n',  # ПоляСпискаПробы
        1739: '    Перем Объект;\n',  # КодекСпискаПробы
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
    if digest(template) == CLIENT_DIRECTIVE_TEMPLATE_SHA256:
        template = client_parity_template(template)
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


def run_async_process(command: list[str], directory: Path, log: Path, timeout: float,
                *, require_clean_tree: bool = False) -> None:
    if os.name != 'posix' or type(timeout) not in (int, float) or not 0 < timeout <= 120:
        raise FullError('invalid_input')
    absent(log)
    with log.open('xb') as output:
        with subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                              stdout=output, stderr=subprocess.STDOUT,
                              start_new_session=True) as child:
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                error = FullError('timeout')
                try:
                    _stop_group(child)
                    error.async_process_stopped = True
                except Exception:
                    error.async_process_stopped = False
                raise error from None
            except BaseException as error:
                try:
                    _stop_group(child)
                    error.async_process_stopped = True
                except Exception:
                    error.async_process_stopped = False
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
                        error = FullError('process_failed')
                        try:
                            _stop_group(child)
                            error.async_process_stopped = True
                        except Exception:
                            error.async_process_stopped = False
                        raise error
                    time.sleep(0.02)
            else:
                _stop_group(child)
    if code:
        error = FullError('process_failed')
        error.async_process_stopped = True
        raise error
    if '/DumpResult' in command:
        result = Path(command[command.index('/DumpResult') + 1])
        try:
            data = secure_bytes(result, 128)
            value = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig').strip()
            if not re.fullmatch(r'[+-]?[0-9]+', value) or int(value) != 0:
                raise ValueError
        except (FullError, ValueError, UnicodeError) as cause:
            error = cause if isinstance(cause, FullError) else FullError('invalid_dump_result')
            error.async_process_stopped = True
            raise error from None



def read_async_deadline(nonce: str) -> float:
    value = strict_json(secure_bytes(Path('/tmp/onec-smoke/async-deadline.json'), 256))
    if (type(value) is not dict or set(value) != {'schema', 'nonce', 'deadline'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not valid_nonce(nonce) or value['nonce'] != nonce
            or type(value['deadline']) is not int
            or not time.monotonic() < value['deadline'] <= time.monotonic() + 2340):
        raise FullError('timeout')
    return value['deadline']

# Async-only private file continuity: same bytes in a replaced inode are not proof.
def async_file_snapshot(path: Path, limit: int, *, allow_empty=False):
    def signature(value):
        return (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
    before = path.lstat()
    data = secure_bytes(path, limit, allow_empty=allow_empty)
    after = path.lstat()
    if signature(before) != signature(after):
        raise FullError('stale_evidence')
    return signature(after), data


def async_require_snapshot(path, saved, limit, *, allow_empty=False):
    if async_file_snapshot(path, limit, allow_empty=allow_empty) != saved:
        raise FullError('stale_evidence')


def async_diagnostic_snapshot(path, limit, *, allow_empty=False):
    """A stable no-follow file observation, including securely observed absence."""
    def parents():
        result = []
        for parent in path.absolute().parents:
            value = parent.lstat()
            if not stat.S_ISDIR(value.st_mode):
                raise FullError('stale_evidence')
            result.append((value.st_dev, value.st_ino, value.st_mode))
        return result
    before = parents()
    try:
        result = async_file_snapshot(path, limit, allow_empty=allow_empty)
    except FileNotFoundError:
        try:
            descriptor = _open_no_follow(path)
        except FileNotFoundError:
            result = None
        else:
            os.close(descriptor)
            raise FullError('stale_evidence')
    if before != parents():
        raise FullError('stale_evidence')
    return result


def async_failure_observation(stage, case_id, nonce, *, stopped, marker_context=None,
                              log_context=None):
    """Lossy post-stop observations, never continuing proof or semantic diagnosis.

    No file is reread/rebased by the final emitter. observed_* is historical at
    this capture only; row proof remains zero and continuity remains null.
    """
    result = [stage, 0, 0, 0]
    if not stopped:
        return result
    retained = []
    marker_snaps = []
    if marker_context is not None:
        entered, completed, request, request_snap, previous = marker_context
        for index, (path, phase) in enumerate(((entered, 'entered'), (completed, 'completed')), 1):
            saved = None
            try:
                async_require_snapshot(request, request_snap, 2048)
                saved = async_diagnostic_snapshot(path, ASYNC_MAX_MARKER)
                if phase in previous and saved != previous[phase]:
                    raise FullError('stale_evidence')
                if saved is None:
                    result[index] = 1
                else:
                    if not async_diagnostic_after(saved, request_snap) or saved[1].startswith(b'\xef\xbb\xbf'):
                        raise FullError('stale_evidence')
                    validate_async_marker(strict_json(saved[1], max_depth=5), nonce, case_id, phase)
                    result[index] = 3
                retained.append((index, path, saved, ASYNC_MAX_MARKER, False))
            except Exception:
                result[index] = 2
            marker_snaps.append(saved)
        if result[2] == 3 and (result[1] != 3 or marker_snaps[1][0][5] < marker_snaps[0][0][5]):
            result[2] = 2
    if log_context is not None:
        paths, anchor_path, anchor_snap, anchor_limit = log_context
        try:
            from diagnostics import native_text, summarize_text
            async_require_snapshot(anchor_path, anchor_snap, anchor_limit)
            categories, entry_labels = set(), set()
            present = False
            for path in paths:
                saved = async_diagnostic_snapshot(path, MAX_OUTPUT, allow_empty=True)
                retained.append((3, path, saved, MAX_OUTPUT, True))
                if saved is None:
                    continue
                present = True
                if not async_diagnostic_after(saved, anchor_snap):
                    raise FullError('stale_evidence')
                text = native_text(saved[1])
                for line in text.splitlines():
                    if 'ASYNC-ENTRY-FAILURE:' in line:
                        if line not in ASYNC_ENTRY_LOG_MARKERS or stage < 3:
                            raise FullError('invalid_result')
                        entry_labels.add(ASYNC_ENTRY_LOG_MARKERS[line])
                category = summarize_text(text)['category']
                if category != 'unknown':
                    categories.add(category)
            specific = categories - {'runtime_error', 'startup_failed'}
            if len(entry_labels) > 1 or len(specific) > 1 or 'conflicting_evidence' in categories or (entry_labels and specific):
                result[3] = 12
            elif entry_labels:
                result[3] = next(iter(entry_labels))
            elif specific:
                result[3] = ASYNC_LOG_CATEGORIES.index(next(iter(specific)))
            elif categories:
                result[3] = 5 if 'runtime_error' in categories else 11
            else:
                result[3] = 3 if present else 1
        except Exception:
            result[3] = 2
    # Check all observations again after parsing/classifying the bounded files.
    # A late replacement cannot turn the first snapshot into accepted evidence.
    for index, path, saved, limit, allow_empty in retained:
        try:
            if async_diagnostic_snapshot(path, limit, allow_empty=allow_empty) != saved:
                raise FullError('stale_evidence')
        except Exception:
            result[index] = 2
    if marker_context is not None:
        try:
            async_require_snapshot(request, request_snap, 2048)
        except Exception:
            result[1:3] = [2, 2]
        if result[2] == 3 and result[1] != 3:
            result[2] = 2
    if log_context is not None:
        try:
            async_require_snapshot(anchor_path, anchor_snap, anchor_limit)
        except Exception:
            result[3] = 2
    return result


def async_diagnostic_after(saved, anchor):
    # Filesystem timestamps may be coarser than time.time_ns(). Compare only
    # against an earlier, securely retained current-case file on the same device.
    # Equal ticks are valid; exclusive paths and nonce/snapshots still bind runs.
    floor = max(anchor[0][5:7])
    return saved[0][0] == anchor[0][0] and all(value >= floor for value in saved[0][5:7])


def fail_async_process_checkpoint(record, diagnostics=None):
    # Only the last reached row is invalidated; no accepted aggregate survives.
    reached = [r for r in record['cases'] if r[1] != 0]
    row = reached[-1] if reached else record['cases'][0]
    index, module_hash = row[0], row[3]
    record['cases'][index] = [index,2,11,module_hash,0,[],[],[]]
    record.update(status='failed', failure_kind='process_failed', continuity_sha256=None,
                  failure_diagnostics=None, marker_validation_failure=None)
    record['process_diagnostics'] = diagnostics if diagnostics is not None else dict(empty_process_diagnostics(),stage='after_exit',reason='unverified')


def run_client_async(platform, root: Path, inputs: Path, nonce: str, hashes: dict, *, deadline: float) -> dict:
    record = empty_async_report()
    current = 0
    host_stage = 0
    process_stopped = False
    marker_context = log_context = None
    modules = [async_client_module(i) for i in range(8)]
    template_hash = digest(ASYNC_TEMPLATE.encode('utf-8'))
    module_hashes = [digest(module) for module in modules]
    retained = []
    def step(command, directory, log, anchor):
        nonlocal process_stopped, log_context
        process_stopped = False
        log_context = None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FullError('timeout')
        native_log = Path(command[command.index('/Out') + 1])
        absent(native_log, log)
        async_require_snapshot(*anchor)
        log_context = ((native_log, log), *anchor)
        try:
            run_async_process(command,directory,log,min(120,remaining),require_clean_tree=True)
        except Exception as error:
            process_stopped = getattr(error, 'async_process_stopped', False) is True
            raise
        process_stopped = True
        if '/DumpResult' in command:
            path = Path(command[command.index('/DumpResult')+1])
            saved = async_file_snapshot(path,128)
            data = saved[1]
            try:
                value = data.decode('utf-16' if data[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig').strip()
                if not re.fullmatch(r'[+-]?[0-9]+',value) or int(value) != 0:
                    raise ValueError
            except (ValueError,UnicodeError):
                raise FullError('invalid_dump_result') from None
            retained.append((path,saved,128,False))
    try:
        if (not valid_nonce(nonce) or type(deadline) not in (int,float)
                or not time.monotonic() < deadline <= time.monotonic()+2340
                or platform.timeout != 120 or platform.user != 'NativeSmoke' or platform.password is not None):
            raise FullError('invalid_input')
        absent(root)
        root.mkdir(mode=0o700)
        source_path = inputs / 'bootstrap/full_suite.py'
        source_snapshot = async_file_snapshot(source_path,MAX_OUTPUT)
        if digest(source_snapshot[1]) != hashes['scripts/native_1c_bootstrap/full_suite.py']:
            raise FullError('invalid_input')
        retained.append((source_path,source_snapshot,MAX_OUTPUT,False))
        record['template_sha256'] = template_hash
        for current,module in enumerate(modules):
            host_stage = 0
            process_stopped = False
            marker_context = log_context = None
            case = root / ('case-'+str(current))
            absent(case)
            case.mkdir(mode=0o700)
            record['process_diagnostics'].update(stage='baseline',reason='unverified')
            baseline = client_process_baseline(nonce)
            record['process_diagnostics'].update(stage='before_probe',reason='native_not_quiet')
            if not native_processes_quiet(platform.executable):
                raise FullError('process_failed')
            record['process_diagnostics'].update(reason='none')
            src = case / 'src'
            src.mkdir(mode=0o700)
            for relative in ('Launcher.xml','Launcher/Ext/ObjectModule.bsl','Launcher/Forms/Main.xml','Launcher/Forms/Main/Ext/Form.xml'):
                origin = inputs / 'launcher/launcher_1c' / relative
                snap = async_file_snapshot(origin,MAX_OUTPUT)
                if digest(snap[1]) != hashes['integrational_tests/launcher_1c/'+relative]:
                    raise FullError('invalid_input')
                retained.append((origin,snap,MAX_OUTPUT,False))
                destination = src / relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                with destination.open('xb') as stream: stream.write(snap[1])
                retained.append((destination,async_file_snapshot(destination,MAX_OUTPUT),MAX_OUTPUT,False))
            module_path = src / CLIENT_MODULE
            module_path.parent.mkdir(parents=True,exist_ok=True)
            with module_path.open('xb') as stream: stream.write(module)
            module_snap = async_file_snapshot(module_path,MAX_OUTPUT)
            retained.append((module_path,module_snap,MAX_OUTPUT,False))
            client_wiring(src)
            epf = case / 'AsyncClientProbe.epf'
            host_stage = 1
            step(platform.command('DESIGNER')+['/LoadExternalDataProcessorOrReportFromFiles',str(src/'Launcher.xml'),str(epf),'/Out',str(case/'build.log'),'/DumpResult',str(case/'build.result')],case,case/'build-console.log',(module_path,module_snap,MAX_OUTPUT))
            require_epf(epf)
            retained.append((epf,async_file_snapshot(epf,MAX_OUTPUT),MAX_OUTPUT,False))
            async_require_snapshot(module_path,module_snap,MAX_OUTPUT)
            host_stage = 2
            log_context = None
            dumped = case / 'roundtrip'
            dumped.mkdir(mode=0o700)
            step(platform.command('DESIGNER')+['/DumpExternalDataProcessorOrReportToFiles',str(dumped/'Launcher.xml'),str(epf),'/Out',str(case/'dump.log'),'/DumpResult',str(case/'dump.result')],case,case/'dump-console.log',(module_path,module_snap,MAX_OUTPUT))
            actual = generated_module(secure_bytes(dumped/CLIENT_MODULE,MAX_OUTPUT))
            if actual != module:
                raise FullError('module_mismatch')
            client_wiring(dumped)
            for relative in ('Launcher.xml','Launcher/Ext/ObjectModule.bsl','Launcher/Forms/Main.xml','Launcher/Forms/Main/Ext/Form.xml',CLIENT_MODULE):
                path = dumped/relative
                allow_empty = relative == 'Launcher/Ext/ObjectModule.bsl'
                retained.append((path,async_file_snapshot(path,MAX_OUTPUT,allow_empty=allow_empty),MAX_OUTPUT,allow_empty))
            host_stage = 0
            log_context = None
            entered,completed,request = case/'entered.json',case/'completed.json',case/'request.json'
            absent(entered,completed,request)
            expected = {'schema':1,'version':1,'nonce':nonce,'entered':str(entered),'completed':str(completed)}
            with request.open('x',encoding='utf-8') as stream: json.dump(expected,stream,sort_keys=True,separators=(',',':'))
            request_snap = async_file_snapshot(request,2048)
            if request_snap[1] != json.dumps(expected,sort_keys=True,separators=(',',':')).encode('utf-8') or strict_json(request_snap[1]) != expected or entered.parent != case or completed.parent != case:
                raise FullError('invalid_input')
            retained.append((request,request_snap,2048,False))
            host_stage = 5
            for path,saved,limit,allow_empty in retained:
                async_require_snapshot(path,saved,limit,allow_empty=allow_empty)
            host_stage = 3
            absent(entered, completed)
            marker_pins = {}
            marker_context = (entered, completed, request, request_snap, marker_pins)
            enterprise_error = None
            try:
                step(platform.command('ENTERPRISE')+['/RunModeManagedApplication','/VL','ru_RU','/Execute',str(epf),'/C',str(request),'/Out',str(case/'enterprise.log')],case,case/'enterprise-console.log',(request,request_snap,2048))
            except Exception as error:
                enterprise_error = error
                raise
            finally:
                try:
                    record['process_diagnostics'].update(stage='after_exit',reason='unverified')
                    survivors = client_process_snapshot()-baseline
                    if survivors:
                        record['process_diagnostics'] = unexpected_process_diagnostics(survivors,'after_exit')
                    else:
                        require_session_bus(Path('/tmp/onec-smoke'),nonce)
                        record['process_diagnostics'].update(reason='native_not_quiet')
                        if native_processes_quiet(platform.executable):
                            record['process_diagnostics'].update(reason='none')
                except Exception:
                    if enterprise_error is None:
                        raise
            if record['process_diagnostics']['reason'] != 'none':
                raise FullError('process_failed')
            host_stage = 4
            marker_pins['entered'] = False
            try:
                entered_snap = async_file_snapshot(entered,ASYNC_MAX_MARKER)
            except FileNotFoundError:
                marker_pins['entered'] = None
                raise
            marker_pins['entered'] = entered_snap
            marker_pins['completed'] = False
            try:
                completed_snap = async_file_snapshot(completed,ASYNC_MAX_MARKER)
            except FileNotFoundError:
                marker_pins['completed'] = None
                raise
            marker_pins['completed'] = completed_snap
            validate_async_marker(strict_json(entered_snap[1],max_depth=5),nonce,current,'entered')
            completion = validate_async_marker(strict_json(completed_snap[1],max_depth=5),nonce,current,'completed')
            if completed.stat().st_mtime_ns < entered.stat().st_mtime_ns:
                raise FullError('invalid_result')
            retained.extend(((entered,entered_snap,ASYNC_MAX_MARKER,False),(completed,completed_snap,ASYNC_MAX_MARKER,False)))
            if completion['status'] != 1:
                raise FullError(ASYNC_FAILURES[completion['failure']])
            record['cases'][current] = [current,1,0,module_hashes[current],63,completion['trace'],completion['values'],completion['errors']]
        host_stage = 5
        for path,saved,limit,allow_empty in retained:
            async_require_snapshot(path,saved,limit,allow_empty=allow_empty)
        record['continuity_sha256'] = write_async_continuity(root,inputs,nonce,retained)
        record.update(status='ok',failure_kind='none')
        validate_async_report(record,template_hash,module_hashes)
    except Exception as error:
        kind = error.kind if isinstance(error,FullError) else 'artifact_missing' if isinstance(error,OSError) else 'unexpected_failure'
        if kind not in ASYNC_FAILURES or kind in ('none','prerequisites_failed'):
            kind = 'unexpected_failure'
        if isinstance(error,ClientProcessError): record['process_diagnostics'] = error.diagnostics
        status = 3 if kind == 'unsupported_observation' else 2
        record['cases'][current] = [current,status,ASYNC_FAILURES.index(kind),module_hashes[current] if record['template_sha256'] else None,0,[],[],[]]
        record.update(status='inconclusive' if status == 3 else 'failed',failure_kind=kind,continuity_sha256=None)
        record['failure_diagnostics'] = async_failure_observation(
            host_stage, current, nonce, stopped=process_stopped,
            marker_context=marker_context, log_context=log_context)
        if kind == 'invalid_result':
            record['marker_validation_failure'] = observe_async_marker_validation_failure(
                host_stage,current,nonce,stopped=process_stopped,marker_context=marker_context)
    return record
# Client Async finite protocol v1. This code is embedded in trusted full_suite.py.
# Public rows stay compact in summary/provenance; descriptors never cross that boundary.
ASYNC_VERSION = 2
ASYNC_MAX_MARKER = 16_384
# Wire ordinals are independent of the legacy process diagnostic vocabulary.
# observed_* describes only the stable post-stop capture, not final continuity.
# Categories are append-only: 0-38 are unchanged; 39-43 localize request end.
# Category 26 retains the key helper-call stage; 27-30 are retired.
ASYNC_HOST_STAGES = ('prepare', 'build', 'roundtrip', 'enterprise', 'markers', 'continuity')
ASYNC_MARKER_STATES = ('not_checked', 'observed_absent', 'observed_invalid', 'observed_valid')
ASYNC_LOG_CATEGORIES = ('not_checked', 'observed_absent', 'observed_invalid', 'unknown',
    'compile_error', 'runtime_error', 'unsupported_api', 'permission_denied',
    'authentication_failed', 'license_unavailable', 'training_restriction',
    'startup_failed', 'conflicting_evidence', 'entry_request', 'entry_witness',
    'entry_initialize', 'entry_entered', 'entry_root', 'entry_request_open',
    'entry_request_object', 'entry_request_key', 'entry_request_value',
    'entry_request_end', 'entry_request_fields', 'entry_request_nonce', 'entry_request_paths',
    'entry_request_key_call', 'entry_request_key_read', 'entry_request_key_token',
    'entry_request_key_current', 'entry_request_key_property',
    'entry_request_key_read_first', 'entry_request_key_read_later',
    'entry_request_key_token_first', 'entry_request_key_token_later',
    'entry_request_key_current_first', 'entry_request_key_current_later',
    'entry_request_key_property_first', 'entry_request_key_property_later',
    'entry_request_end_call', 'entry_request_end_read', 'entry_request_end_token',
    'entry_request_end_trailing', 'entry_request_end_close')
ASYNC_ENTRY_LOG_MARKERS = {'ASYNC-ENTRY-FAILURE:' + name: index
                         for index, name in enumerate(('request', 'witness', 'initialize', 'entered', 'root',
                             'request_open', 'request_object', 'request_key', 'request_value',
                             'request_end', 'request_fields', 'request_nonce', 'request_paths',
                             'request_key_call', 'request_key_read', 'request_key_token',
                             'request_key_current', 'request_key_property',
                             'request_key_read_first', 'request_key_read_later',
                             'request_key_token_first', 'request_key_token_later',
                             'request_key_current_first', 'request_key_current_later',
                             'request_key_property_first', 'request_key_property_later',
                             'request_end_call', 'request_end_read', 'request_end_token',
                             'request_end_trailing', 'request_end_close'), 13)}
ASYNC_SLOTS = (4, 3, 5, 3, 4, 7, 3, 3)
ASYNC_STRINGS = ('7', '17', '11', '12', '21', '22', '31', '33')
ASYNC_FAILURES = ('none', 'prerequisites_failed', 'stale_evidence', 'invalid_input',
                  'invalid_result', 'invalid_dump_result', 'artifact_missing',
                  'output_mismatch', 'output_limit', 'module_mismatch', 'timeout',
                  'process_failed', 'unexpected_failure', 'export_failed',
                  'unsupported_observation')
ASYNC_PROOF_FLAGS = ('entered', 'completed', 'process_exited', 'quiet',
                     'witness_verified', 'roundtrip_module_equal')
ASYNC_REQUIRED = (
    (10,11,12,13,14,15,16,17,18),
    (10,11,12,13,14,15,16,17,25,26),
    (10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28),
    (10,13,16), (10,11,12,13,14,15,16,19),
    (10,11,12,13,14,15,16), (10,11,12),
    (10,11,12,13,14,15,16,17,18),
)
ASYNC_EDGES = (
    ((10,11),(11,12),(10,13),(13,14),(12,14),(14,15),(15,16),(16,17),(17,18)),
    ((10,11),(11,12),(12,25),(25,26),(26,13),(13,14),(14,17),(10,15),(15,16),(16,17)),
    ((10,11),(11,12),(12,25),(25,26),(26,13),(13,14),(14,22),(10,15),(15,16),(16,17),(17,18),(18,27),(27,28),(28,19),(19,20),(20,23),(16,21),(21,22),(22,23),(23,24)),
    ((10,11),(10,12),(11,13),(12,13),(13,14),(13,15),(14,16),(15,16),(16,17),(16,18)),
    ((10,11),(11,12),(12,13),(11,14),(14,16),(10,15),(15,16),(16,17),(16,18),(17,19),(18,19),(13,19)),
    ((10,11),(11,12),(12,13),(13,14),(14,16),(10,15),(15,16)),
    ((10,11),(11,12),(10,13),(12,14),(13,15),(15,16),(15,17),(12,16),(12,17),(16,18),(17,18),(18,19),(18,20),(12,19),(12,20)),
    ((10,11),(11,12),(12,13),(13,14),(14,15),(15,16),(16,17),(17,18)),
)


def _async_bad():
    raise FullError('invalid_result')


def _async_int(value, low=0, high=999999):
    return type(value) is int and low <= value <= high


def _async_hash(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _async_value(value):
    if type(value) is not list or len(value) != 2 or not _async_int(value[0], 0, 7):
        _async_bad()
    tag, payload = value
    if not _async_int(payload, -999999, 999999):
        _async_bad()
    if ((tag in (0,1,2,6) and payload != 0)
            or (tag == 3 and payload not in (0,1))
            or (tag == 5 and not 0 <= payload <= 7)
            or (tag == 7 and not 0 <= payload <= 2)):
        _async_bad()
    return tag


def _async_error(error):
    if (type(error) is not list or len(error) != 7
            or not _async_int(error[0], 0, 6)
            or any(not _async_int(v, 0, 4) for v in error[1:4])
            or any(not _async_int(v, 0, 3) for v in error[4:6])
            or not _async_hash(error[6])):
        _async_bad()


def validate_async_observation(case_id, trace, values, errors):
    """Exact inventory and logical DAG, deliberately not an Await scheduler."""
    if (not _async_int(case_id, 0, 7) or type(trace) is not list
            or not 5 <= len(trace) <= 24
            or any(not _async_int(v, 0, 28) for v in trace)
            or len(set(trace)) != len(trace) or trace[:2] != [0,1]
            or trace[-3:] != [2,3,4] or type(values) is not list
            or len(values) != ASYNC_SLOTS[case_id] or type(errors) is not list
            or len(errors) > 3):
        _async_bad()
    tags = [_async_value(value) for value in values]
    for error in errors:
        _async_error(error)
    allowed_errors = {3:{0:3,1:4,2:5}, 6:{0:0,1:1,2:2}, 7:{2:6}}.get(case_id, {})
    refs = []
    for slot, value in enumerate(values):
        if value[0] == 7:
            ordinal = value[1]
            if slot not in allowed_errors or ordinal >= len(errors) or errors[ordinal][0] != allowed_errors[slot]:
                _async_bad()
            refs.append(ordinal)
    if refs != list(range(len(errors))):
        _async_bad()
    required = set(ASYNC_REQUIRED[case_id]) | {0,1,2,3,4}
    skipped = set()
    if case_id == 3:
        required.update((12 if tags[0] == 7 else 11, 15 if tags[1] == 7 else 14, 18 if tags[2] == 7 else 17))
    elif case_id == 4:
        required.add(17 if tags[1] == 6 else 18)
        if tags[1] != 6:
            skipped.add(2)
    elif case_id == 6:
        if tags[0] == 7:
            required.add(14)
            skipped.update((1,2))
        else:
            required.update((13,15,18,17 if tags[1] == 7 else 16,20 if tags[2] == 7 else 19))
    elif case_id == 7 and tags[2] != 7:
        _async_bad()
    if any((tag == 0) != (slot in skipped) for slot, tag in enumerate(tags)):
        _async_bad()
    if set(trace) != required:
        _async_bad()
    positions = {event:index for index,event in enumerate(trace)}
    if any(a in required and b in required and positions[a] >= positions[b] for a,b in ASYNC_EDGES[case_id]):
        _async_bad()
    return {'trace':trace, 'values':values, 'errors':errors}


def _async_private_error(descriptor):
    """Hash exact bounded selected fields, never a recursive ErrorInfo object."""
    keys = {'schema','phase','description','code','additional','category','cause','module','line','source'}
    if (type(descriptor) is not dict or set(descriptor) != keys
            or not _async_int(descriptor['schema'],1,1) or not _async_int(descriptor['phase'],0,6)):
        _async_bad()
    fields = ('description','code','additional','category','cause','module','line','source')
    allowed = {'description':{0,1,2,3,4},'code':{0,1,2,3,4},'additional':{0,1,2,3,4},
               'category':{0,1,3,5},'cause':{0,1,5},'module':{0,2},'line':{0,1,3},'source':{0,2}}
    for name in fields:
        item = descriptor[name]
        if type(item) is not list or len(item) != 2 or not _async_int(item[0],0,5) or item[0] not in allowed[name]:
            _async_bad()
        tag,payload = item
        if tag in (0,1):
            if payload is not None:
                _async_bad()
        elif tag == 2:
            if type(payload) is not str or len(payload) > 512:
                _async_bad()
            try:
                if len(payload.encode('utf-8')) > 512:
                    _async_bad()
            except UnicodeError:
                _async_bad()
        elif tag == 3:
            if not _async_int(payload):
                _async_bad()
        elif tag == 4:
            if type(payload) is not bool:
                _async_bad()
        elif tag == 5 and (not _async_int(payload,0,1) or payload != (1 if name == 'category' else 0)):
            _async_bad()
    try:
        raw = json.dumps(descriptor, sort_keys=True, separators=(',',':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError,ValueError,UnicodeError):
        _async_bad()
    if len(raw) > 4096:
        _async_bad()
    public = [descriptor['phase']]
    for name,synthetic in zip(fields[:3], ('ASYNC-REJECT','ASYNC-CODE','ASYNC-DETAIL')):
        tag,payload = descriptor[name]
        public.append(4 if tag == 0 else 0 if tag == 1 else 1 if tag == 2 and payload == '' else 2 if tag == 2 and payload == synthetic else 3)
    tag,payload = descriptor['category']
    public.append(3 if tag == 0 else 0 if tag == 1 else 1 if tag == 3 and payload == 1 else 2)
    public.append({0:3,1:0,5:1}[descriptor['cause'][0]])
    public.append(hashlib.sha256(raw).hexdigest())
    return public


def client_async_marker(path, nonce, case_id, phase):
    if not valid_nonce(nonce) or not _async_int(case_id,0,7) or phase not in ('entered','completed'):
        raise FullError('invalid_input')
    raw = secure_bytes(path, ASYNC_MAX_MARKER)
    if raw.startswith(b'\xef\xbb\xbf'):
        _async_bad()
    value = strict_json(raw, max_depth=5)
    return validate_async_marker(value, nonce, case_id, phase)


def validate_async_marker(value, nonce, case_id, phase):
    fields = {'schema','nonce','case','phase','witness'}
    if phase == 'completed':
        fields |= {'status','failure','trace','values','errors'}
    if (not valid_nonce(nonce) or not _async_int(case_id,0,7) or phase not in ('entered','completed')
            or type(value) is not dict or set(value) != fields
            or not _async_int(value['schema'],1,1) or not _async_int(value['case'],case_id,case_id)
            or type(value['nonce']) is not str or value['nonce'] != nonce
            or type(value['phase']) is not str or value['phase'] != phase
            or type(value['witness']) is not str or value['witness'] != 'client'):
        _async_bad()
    if phase == 'entered':
        return value
    if not _async_int(value['status'],1,3) or not _async_int(value['failure'],0,14):
        _async_bad()
    if value['status'] != 1:
        if ((value['status'] == 2 and not 1 <= value['failure'] <= 13)
                or (value['status'] == 3 and value['failure'] != 14)
                or any(type(value[k]) is not list or value[k] != [] for k in ('trace','values','errors'))):
            _async_bad()
        return value
    if value['failure'] != 0 or type(value['errors']) is not list or len(value['errors']) > 3:
        _async_bad()
    public = [_async_private_error(error) for error in value['errors']]
    validate_async_observation(case_id, value['trace'], value['values'], public)
    return {**value,'errors':public}


# Failure-only validator sites. These ordinals are not semantic observations.
# The fourth tuple member is a site-specific locator; 31 means not applicable.
ASYNC_MARKER_VALIDATION_SITES = (
    'not_checked', 'json_encoding', 'json_depth', 'json_duplicate_key',
    'json_integer_width', 'json_float', 'json_constant', 'json_syntax',
    'envelope_shape', 'envelope_schema', 'completion_codes',
    'failure_completion_shape', 'success_failure_code', 'errors_shape',
    'descriptor_shape', 'descriptor_schema', 'descriptor_phase',
    'descriptor_pair', 'descriptor_tag', 'descriptor_null_payload',
    'descriptor_string_payload', 'descriptor_utf8_limit',
    'descriptor_integer_payload', 'descriptor_boolean_payload',
    'descriptor_enum_payload', 'descriptor_encoding', 'descriptor_budget',
    'observation_shape', 'event_type', 'event_duplicate', 'root_boundary',
    'value_pair', 'value_tag', 'value_payload', 'reference_phase',
    'reference_ordinal', 'reference_bijection', 'skipped_slot',
    'missing_event', 'extra_event', 'causal_edge', 'required_handler', 'unknown')


def async_marker_validation_failure(raw, nonce, case_id, phase):
    """Classify an already rejected bounded marker without changing acceptance.

    Exact validators remain the authority. Only fixed codes and bounded source
    locators can leave this function; no exception text or native payload does.
    Known identity disagreement is deliberately not diagnosable evidence.
    """
    if (type(raw) is not bytes or len(raw) > ASYNC_MAX_MARKER or not valid_nonce(nonce)
            or not _async_int(case_id,0,7) or phase not in ('entered','completed')): return None
    marker_phase = 0 if phase == 'entered' else 1
    def failure(site, descriptor=3, locator=31):
        return [marker_phase, site, descriptor, locator]
    try:
        value = strict_json(raw, max_depth=5)
    except FullError:
        # Match the original bounded JSON parser's order and reject vocabulary.
        # This second parse is diagnostic-only and can never grant acceptance.
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError:
            return failure(1)
        depth, quoted, escaped = 0, False, False
        for character in text:
            if quoted:
                if escaped: escaped = False
                elif character == '\\': escaped = True
                elif character == '"': quoted = False
            elif character == '"': quoted = True
            elif character in '[{':
                depth += 1
                if depth > 5: return failure(2)
            elif character in ']}':
                depth -= 1
                if depth < 0: return failure(7)
        site = 7
        def pairs(items):
            nonlocal site
            result = {}
            for key, item in items:
                if key in result:
                    site = 3
                    raise ValueError
                result[key] = item
            return result
        def number(token):
            nonlocal site
            if len(token) > 10:
                site = 4
                raise ValueError
            return int(token)
        def floating(token):
            nonlocal site
            site = 5
            raise ValueError
        def constant(token):
            nonlocal site
            site = 6
            raise ValueError
        try:
            json.loads(text, object_pairs_hook=pairs, parse_int=number,
                       parse_float=floating, parse_constant=constant)
        except (ValueError, UnicodeError, RecursionError):
            return failure(site)
        return failure(42)
    # Do not publish a diagnostic for a different invocation, case or context.
    if type(value) is dict and any(value.get(key) != expected or type(value.get(key)) is not type(expected)
            for key, expected in (('nonce', nonce), ('case', case_id),
                                  ('phase', phase), ('witness', 'client'))):
        return None
    try:
        validate_async_marker(value, nonce, case_id, phase)
    except FullError:
        pass
    else:
        return None
    fields = {'schema','nonce','case','phase','witness'}
    if phase == 'completed': fields |= {'status','failure','trace','values','errors'}
    if type(value) is not dict or set(value) != fields: return failure(8)
    if not _async_int(value['schema'],1,1): return failure(9)
    if phase == 'entered': return failure(42)
    if not _async_int(value['status'],1,3) or not _async_int(value['failure'],0,14): return failure(10)
    if value['status'] != 1: return failure(11)
    if value['failure'] != 0: return failure(12)
    if type(value['errors']) is not list or len(value['errors']) > 3: return failure(13)
    names = ('schema','phase','description','code','additional','category','cause','module','line','source')
    allowed = ({0,1,2,3,4},{0,1,2,3,4},{0,1,2,3,4},{0,1,3,5},{0,1,5},{0,2},{0,1,3},{0,2})
    public = []
    for ordinal, descriptor in enumerate(value['errors']):
        if type(descriptor) is not dict or set(descriptor) != set(names): return failure(14,ordinal)
        if not _async_int(descriptor['schema'],1,1): return failure(15,ordinal,0)
        if not _async_int(descriptor['phase'],0,6): return failure(16,ordinal,1)
        for locator, (name, tags) in enumerate(zip(names[2:],allowed),2):
            item = descriptor[name]
            if type(item) is not list or len(item) != 2: return failure(17,ordinal,locator)
            tag, payload = item
            if not _async_int(tag,0,5) or tag not in tags: return failure(18,ordinal,locator)
            if tag in (0,1):
                if payload is not None: return failure(19,ordinal,locator)
            elif tag == 2:
                if type(payload) is not str: return failure(20,ordinal,locator)
                try:
                    if len(payload) > 512 or len(payload.encode('utf-8')) > 512: return failure(21,ordinal,locator)
                except UnicodeError:
                    return failure(25,ordinal,locator)
            elif tag == 3:
                if not _async_int(payload): return failure(22,ordinal,locator)
            elif tag == 4:
                if type(payload) is not bool: return failure(23,ordinal,locator)
            elif not _async_int(payload,0,1) or payload != (1 if name == 'category' else 0):
                return failure(24,ordinal,locator)
        try:
            encoded = json.dumps(descriptor, sort_keys=True, separators=(',',':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (TypeError,ValueError,UnicodeError):
            return failure(25,ordinal)
        if len(encoded) > 4096: return failure(26,ordinal)
        public.append(_async_private_error(descriptor))
    trace, values = value['trace'], value['values']
    if (type(trace) is not list or not 5 <= len(trace) <= 24
            or type(values) is not list or len(values) != ASYNC_SLOTS[case_id]): return failure(27)
    if any(not _async_int(event,0,28) for event in trace): return failure(28)
    if len(set(trace)) != len(trace):
        return failure(29,locator=next(event for index,event in enumerate(trace) if event in trace[:index]))
    if trace[:2] != [0,1] or trace[-3:] != [2,3,4]: return failure(30)
    tags = []
    for slot, pair in enumerate(values):
        if type(pair) is not list or len(pair) != 2: return failure(31,locator=slot)
        tag,payload = pair
        if not _async_int(tag,0,7): return failure(32,locator=slot)
        if (not _async_int(payload,-999999,999999)
                or (tag in (0,1,2,6) and payload != 0)
                or (tag == 3 and payload not in (0,1))
                or (tag == 5 and not 0 <= payload <= 7)
                or (tag == 7 and not 0 <= payload <= 2)): return failure(33,locator=slot)
        tags.append(tag)
    allowed_errors = {3:{0:3,1:4,2:5},6:{0:0,1:1,2:2},7:{2:6}}.get(case_id,{})
    refs = []
    for slot, (tag, ordinal) in enumerate(values):
        if tag == 7:
            if slot not in allowed_errors or ordinal >= len(public): return failure(35,ordinal,slot)
            if public[ordinal][0] != allowed_errors[slot]: return failure(34,ordinal,slot)
            refs.append(ordinal)
    if refs != list(range(len(public))): return failure(36)
    required = set(ASYNC_REQUIRED[case_id]) | {0,1,2,3,4}
    skipped = set()
    if case_id == 3:
        required.update((12 if tags[0] == 7 else 11,15 if tags[1] == 7 else 14,18 if tags[2] == 7 else 17))
    elif case_id == 4:
        required.add(17 if tags[1] == 6 else 18)
        if tags[1] != 6: skipped.add(2)
    elif case_id == 6:
        if tags[0] == 7:
            required.add(14)
            skipped.update((1,2))
        else:
            required.update((13,15,18,17 if tags[1] == 7 else 16,20 if tags[2] == 7 else 19))
    elif case_id == 7 and tags[2] != 7: return failure(41,locator=2)
    for slot,tag in enumerate(tags):
        if (tag == 0) != (slot in skipped): return failure(37,locator=slot)
    if required - set(trace): return failure(38,locator=min(required-set(trace)))
    if set(trace) - required: return failure(39,locator=min(set(trace)-required))
    positions = {event:index for index,event in enumerate(trace)}
    for edge,(before,after) in enumerate(ASYNC_EDGES[case_id]):
        if before in required and after in required and positions[before] >= positions[after]:
            return failure(40,locator=edge)
    return failure(42)


def observe_async_marker_validation_failure(stage, case_id, nonce, *, stopped, marker_context):
    """A bounded failure hint tied to the original request and marker snapshots."""
    if stage != 4 or not stopped or marker_context is None: return None
    entered, completed, request, request_snap, previous = marker_context
    retained = []
    result = None
    try:
        async_require_snapshot(request,request_snap,2048)
        for path,phase in ((entered,'entered'),(completed,'completed')):
            saved = previous.get(phase)
            if type(saved) is not tuple or len(saved) != 2: return None
            if async_diagnostic_snapshot(path,ASYNC_MAX_MARKER) != saved: return None
            if not async_diagnostic_after(saved,request_snap): return None
            retained.append((path,saved))
        if retained[1][1][0][5] < retained[0][1][0][5]: return None
        for (path,saved),phase in zip(retained,('entered','completed')):
            try:
                value = strict_json(saved[1],max_depth=5)
                validate_async_marker(value,nonce,case_id,phase)
            except FullError:
                result = async_marker_validation_failure(saved[1],nonce,case_id,phase)
                break
        # No late replacement or changed request can retain a diagnostic hint.
        for path,saved in retained:
            if async_diagnostic_snapshot(path,ASYNC_MAX_MARKER) != saved: return None
        async_require_snapshot(request,request_snap,2048)
    except Exception:
        return None
    return result


def empty_async_report():
    return {'version':2,'status':'not_started','failure_kind':'prerequisites_failed',
            'template_sha256':None,'continuity_sha256':None,'process_diagnostics':empty_process_diagnostics(),
            'failure_diagnostics':None,'marker_validation_failure':None,
            'cases':[[i,0,1,None,0,[],[],[]] for i in range(8)]}


def _async_diagnostic(value):
    if (type(value) is not dict or set(value) != set(CLIENT_WIRE_DIAGNOSTICS)
            or type(value['classes']) is not dict or set(value['classes']) != set(CLIENT_WIRE_CLASSES)):
        _async_bad()
    wire = [value[name] for name in CLIENT_WIRE_DIAGNOSTICS[:4]] + [[value['classes'][name] for name in CLIENT_WIRE_CLASSES]]
    decode_process_wire(wire)
    return wire


def validate_async_marker_failure(record):
    value = record['marker_validation_failure']
    if value is None: return
    diagnostic = record.get('failure_diagnostics')
    if (record.get('status') != 'failed' or record.get('failure_kind') != 'invalid_result'
            or type(diagnostic) is not list or len(diagnostic) != 4 or diagnostic[0] != 4
            or type(value) is not list or len(value) != 4
            or not _async_int(value[0],0,1) or not _async_int(value[1],1,42)
            or not _async_int(value[2],0,3) or not _async_int(value[3],0,31)):
        _async_bad()
    phase,site,descriptor,locator = value
    if diagnostic[phase+1] != 2 or (phase == 1 and diagnostic[1] != 3): _async_bad()
    rows = record.get('cases')
    if type(rows) is not list or len(rows) != 8: _async_bad()
    failed = [i for i,row in enumerate(rows) if type(row) is list and len(row) == 8 and row[1:3] == [2,4]]
    if len(failed) != 1: _async_bad()
    case_id = failed[0]
    if phase == 0 and site not in (*range(1,10),42): _async_bad()
    if 14 <= site <= 26:
        if descriptor == 3: _async_bad()
        if site in (14,26): valid = locator == 31
        elif site == 15: valid = locator == 0
        elif site == 16: valid = locator == 1
        elif site == 25: valid = 2 <= locator <= 9 or locator == 31
        else: valid = 2 <= locator <= 9
    elif site in (34,35):
        valid = descriptor < 3 and locator < ASYNC_SLOTS[case_id]
    else:
        if descriptor != 3: _async_bad()
        if site in (29,38,39): valid = 0 <= locator <= 28
        elif site in (31,32,33,37): valid = locator < ASYNC_SLOTS[case_id]
        elif site == 40: valid = locator < len(ASYNC_EDGES[case_id])
        elif site == 41: valid = case_id == 7 and locator == 2
        else: valid = locator == 31
    if not valid: _async_bad()


def validate_async_failure_diagnostics(record):
    validate_async_marker_failure(record)
    value = record['failure_diagnostics']
    if value is None:
        return
    if (record.get('status') not in ('failed', 'inconclusive')
            or type(value) is not list or len(value) != 4
            or not _async_int(value[0], 0, 5)
            or any(not _async_int(item, 0, 3) for item in value[1:3])
            or not _async_int(value[3], 0, 43)
            or (value[0] < 3 and value[1:3] != [0, 0])
            or (value[0] == 0 and value[3] != 0)
            or (value[3] >= 13 and value[0] < 3)
            or (value[2] == 3 and value[1] != 3)):
        _async_bad()


def validate_async_report(record, template_hash, module_hashes):
    keys = {'version','status','failure_kind','template_sha256','continuity_sha256','process_diagnostics','failure_diagnostics','marker_validation_failure','cases'}
    if (not _async_hash(template_hash) or type(module_hashes) not in (list,tuple) or len(module_hashes) != 8
            or any(not _async_hash(h) for h in module_hashes) or type(record) is not dict or set(record) != keys
            or not _async_int(record['version'],2,2)
            or type(record['status']) is not str or record['status'] not in ('not_started','ok','failed','inconclusive')
            or type(record['failure_kind']) is not str or record['failure_kind'] not in ASYNC_FAILURES
            or (record['template_sha256'] is not None and (not _async_hash(record['template_sha256']) or record['template_sha256'] != template_hash))
            or type(record['cases']) is not list or len(record['cases']) != 8):
        _async_bad()
    if (not _async_hash(record['continuity_sha256']) if record['status'] == 'ok' else record['continuity_sha256'] is not None):
        _async_bad()
    _async_diagnostic(record['process_diagnostics'])
    validate_async_failure_diagnostics(record)
    stopped = False
    failed = None
    observed = 0
    for i,row in enumerate(record['cases']):
        if (type(row) is not list or len(row) != 8 or not _async_int(row[0],i,i)
                or not _async_int(row[1],0,3) or not _async_int(row[2],0,14)
                or not _async_int(row[4],0,63)
                or (row[3] is not None and (not _async_hash(row[3]) or row[3] != module_hashes[i]))):
            _async_bad()
        status,reason = row[1:3]
        if status == 1:
            if stopped or reason != 0 or row[3] != module_hashes[i] or row[4] != 63:
                _async_bad()
            validate_async_observation(i,*row[5:])
            observed += 1
        else:
            if row[4] != 0 or any(type(v) is not list or v != [] for v in row[5:]):
                _async_bad()
            if status == 0:
                if reason != 1 or row[3] is not None:
                    _async_bad()
            elif stopped or (status == 2 and not 1 <= reason <= 13) or (status == 3 and (reason != 14 or row[3] is None)):
                _async_bad()
            else:
                failed = row
            stopped = True
    diagnostic = record['process_diagnostics']
    if record['status'] == 'ok':
        if (observed != 8 or record['failure_kind'] != 'none' or record['template_sha256'] != template_hash
                or diagnostic['stage'] != 'after_exit' or diagnostic['reason'] != 'none'):
            _async_bad()
    elif record['status'] == 'not_started':
        if (observed or failed is not None or record['failure_kind'] != 'prerequisites_failed'
                or record['template_sha256'] is not None or diagnostic['stage'] != 'not_checked' or diagnostic['reason'] != 'none'):
            _async_bad()
    elif (failed is None or record['status'] != ('inconclusive' if failed[1] == 3 else 'failed')
            or record['failure_kind'] != ASYNC_FAILURES[failed[2]]
            or ((observed or failed[3] is not None) and record['template_sha256'] != template_hash)):
        _async_bad()
    return record


def encode_async_wire(record):
    if type(record) is not dict or not {'process_diagnostics', 'failure_diagnostics', 'marker_validation_failure'} <= set(record):
        _async_bad()
    validate_async_failure_diagnostics(record)
    return {**record,'process_diagnostics':_async_diagnostic(record['process_diagnostics'])}


def decode_async_wire(record):
    if type(record) is not dict or not {'process_diagnostics', 'failure_diagnostics', 'marker_validation_failure'} <= set(record):
        _async_bad()
    validate_async_failure_diagnostics(record)
    return {**record,'process_diagnostics':decode_process_wire(record['process_diagnostics'])}


def async_named_cases(record):
    """Inspection only. Never put these expanded objects in a public serializer."""
    return [dict(case_id=r[0],status=r[1],failure=r[2],module_sha256=r[3],roundtrip_sha256=r[3] if r[4] == 63 else None,
                 proof={name:bool(r[4] & (1 << i)) for i,name in enumerate(ASYNC_PROOF_FLAGS)},trace=r[5],values=r[6],errors=r[7]) for r in record['cases']]
# Fixed client-language measurement fixture. Native compilation/execution is a
# separate gate; offline source tests do not establish native behavior.
# Primary syntax references:
# https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Standards/Enhancements_to_1C_Enterprise_language_syntax_for_asynchronous_functions__synchronous_asynchrony/?language=en
# https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_8.3.23_Developer_Guide/Chapter_16._Operations_with_various_data_formats/16.2._JSON_operations/16.2.5._Stream_method/
# https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_8.3.23_Developer_Guide/Chapter_32._Debugging_and_testing_applications/32.3._Runtime_errors/32.3.3._Error_information/?language=en

ASYNC_TEMPLATE = '''// Fixed client async language measurement, never interpreter parity.
&НаКлиенте
Перем АсинхЗапрос, АсинхКонтекст, АсинхТрасса, АсинхЗначения, АсинхОшибки;
&НаКлиенте
Перем АсинхОжидания, АсинхЗавершено, АсинхНесовместимо, АсинхСбой;
&НаКлиенте
Перем АсинхВнутреннее, АсинхЛистЗначение, АсинхЗначениеУмолчания;

&НаКлиенте
Функция АсинхНомерСлучая()
    Возврат __ASYNC_CASE_ID__;
КонецФункции

&НаКлиенте
Функция АсинхКонтекстПробы()
#Если Клиент Тогда
    Возврат "client";
#Иначе
    ВызватьИсключение "ASYNC-NOT-CLIENT";
#КонецЕсли
КонецФункции

&НаКлиенте
Функция АсинхПара(Знач Тег, Знач Данные)
    Пара = Новый Массив;
    Пара.Добавить(Тег);
    Пара.Добавить(Данные);
    Возврат Пара;
КонецФункции

&НаКлиенте
Процедура АсинхНачатьТест(Знач ЧислоСлотов)
    Для Индекс = 1 По ЧислоСлотов Цикл
        АсинхЗначения.Добавить(АсинхПара(0, 0));
    КонецЦикла;
    АсинхСобытие(1);
КонецПроцедуры

&НаКлиенте
Процедура АсинхСобытие(Знач Код)
    Если АсинхЗавершено Или АсинхТрасса.Количество() >= 24
        Или АсинхТрасса.Найти(Код) <> Неопределено Тогда
        АсинхСбой = Истина;
        Возврат;
    КонецЕсли;
    АсинхТрасса.Добавить(Код);
КонецПроцедуры

&НаКлиенте
Процедура АсинхУдержать(Знач Обещание)
    // Every created function Promise is retained, including the root's test.
    // Failure cleanup consumes this finite registry before terminal output.
    Если ТипЗнч(Обещание) = Тип("Обещание") Тогда
        АсинхОжидания.Добавить(Обещание);
    КонецЕсли;
КонецПроцедуры

&НаКлиенте
Процедура АсинхСохранить(Знач Слот, Знач Данные)
    Вид = ТипЗнч(Данные);
    Если Вид = Тип("Неопределено") Тогда
        Пара = АсинхПара(1, 0);
    ИначеЕсли Вид = Тип("Null") Тогда
        Пара = АсинхПара(2, 0);
    ИначеЕсли Вид = Тип("Булево") Тогда
        Если Данные Тогда Код = 1; Иначе Код = 0; КонецЕсли;
        Пара = АсинхПара(3, Код);
    ИначеЕсли Вид = Тип("Число") Тогда
        Если Данные <> Цел(Данные) Или Данные < -999999 Или Данные > 999999 Тогда
            АсинхНесовместимо = Истина;
            Возврат;
        КонецЕсли;
        Пара = АсинхПара(4, Данные);
    ИначеЕсли Вид = Тип("Строка") Тогда
        // Exact equality only. No conversion or substring classification.
        Словарь = СтрРазделить("7,17,11,12,21,22,31,33", ",");
        Код = Словарь.Найти(Данные);
        Если Код = Неопределено Тогда
            АсинхНесовместимо = Истина;
            Возврат;
        КонецЕсли;
        Пара = АсинхПара(5, Код);
    ИначеЕсли Вид = Тип("Обещание") Тогда
        Пара = АсинхПара(6, 0);
    Иначе
        АсинхНесовместимо = Истина;
        Возврат;
    КонецЕсли;
    АсинхЗначения[Слот] = Пара;
КонецПроцедуры

&НаКлиенте
Функция АсинхПоле(Знач Данные, Знач Режим)
    // Modes: 0 diagnostic scalar, 1 source line, 2 cause, 3 source text.
    Вид = ТипЗнч(Данные);
    Если Вид = Тип("Неопределено") Тогда
        Если Режим = 3 Тогда
            АсинхНесовместимо = Истина;
            Возврат АсинхПара(0, Неопределено);
        КонецЕсли;
        Возврат АсинхПара(1, Неопределено);
    КонецЕсли;
    Если (Режим = 0 Или Режим = 3) И Вид = Тип("Строка") Тогда
        Если СтрДлина(Данные) > 512
            Или GetBinaryDataFromString(Данные, "UTF-8", Ложь).Size() > 512 Тогда
            АсинхНесовместимо = Истина;
            Возврат АсинхПара(0, Неопределено);
        КонецЕсли;
        Возврат АсинхПара(2, Данные);
    ИначеЕсли (Режим = 0 Или Режим = 1) И Вид = Тип("Число") Тогда
        Если Данные = Цел(Данные) И Данные >= 0 И Данные <= 999999 Тогда
            Возврат АсинхПара(3, Данные);
        КонецЕсли;
    ИначеЕсли Режим = 0 И Вид = Тип("Булево") Тогда
        Возврат АсинхПара(4, Данные);
    ИначеЕсли Режим = 2 И Вид = Тип("ИнформацияОбОшибке") Тогда
        Возврат АсинхПара(5, 0);
    КонецЕсли;
    АсинхНесовместимо = Истина;
    Возврат АсинхПара(0, Неопределено);
КонецФункции

&НаКлиенте
Процедура АсинхСохранитьОшибку(Знач Слот, Знач Фаза, Знач СохраненнаяОшибка)
    // Use only the originally saved ErrorInfo after guarded property failures.
    // Missing properties are unavailable, never invented Undefined values.
    Описание = АсинхПара(0, Неопределено);
    Код = АсинхПара(0, Неопределено);
    Дополнение = АсинхПара(0, Неопределено);
    Категория = АсинхПара(0, Неопределено);
    Причина = АсинхПара(0, Неопределено);
    Модуль = АсинхПара(0, Неопределено);
    СтрокаКода = АсинхПара(0, Неопределено);
    Исходник = АсинхПара(0, Неопределено);
    Если ТипЗнч(СохраненнаяОшибка) <> Тип("ИнформацияОбОшибке") Тогда
        АсинхНесовместимо = Истина;
        Возврат;
    КонецЕсли;
    Попытка Описание = АсинхПоле(СохраненнаяОшибка.Description, 0); Исключение КонецПопытки;
    Попытка Код = АсинхПоле(СохраненнаяОшибка.Code, 0); Исключение КонецПопытки;
    Попытка Дополнение = АсинхПоле(СохраненнаяОшибка.AdditionalInformation, 0); Исключение КонецПопытки;
    Попытка
        // Category membership is documented; ErrorInfo.Category is not.
        Если СохраненнаяОшибка.IsErrorOfCategory(ErrorCategory.ConfigurationError) Тогда
            Категория = АсинхПара(3, 1);
        Иначе
            Категория = АсинхПара(3, 2);
        КонецЕсли;
    Исключение КонецПопытки;
    Попытка Причина = АсинхПоле(СохраненнаяОшибка.Cause, 2); Исключение КонецПопытки;
    Попытка Модуль = АсинхПоле(СохраненнаяОшибка.ModuleName, 3); Исключение КонецПопытки;
    Попытка СтрокаКода = АсинхПоле(СохраненнаяОшибка.LineNumber, 1); Исключение КонецПопытки;
    Попытка Исходник = АсинхПоле(СохраненнаяОшибка.InitialString, 3); Исключение КонецПопытки;
    Дескриптор = Новый Структура("schema,phase,description,code,additional,category,cause,module,line,source",
        1, Фаза, Описание, Код, Дополнение, Категория, Причина, Модуль, СтрокаКода, Исходник);
    Если АсинхОшибки.Количество() >= 3 Тогда
        АсинхНесовместимо = Истина;
        Возврат;
    КонецЕсли;
    // Host hashes the complete canonical descriptor, requires <=4096 bytes,
    // and never puts these private fields into summary/provenance/artifacts.
    АсинхЗначения[Слот] = АсинхПара(7, АсинхОшибки.Количество());
    АсинхОшибки.Добавить(Дескриптор);
КонецПроцедуры

&AtClient
Procedure AsyncExpectToken(Reader, Val Token)
    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;
    If Reader.CurrentValueType <> Token Then Raise "ASYNC-REQUEST"; EndIf;
EndProcedure

&AtClient
Procedure AsyncExpectRequestKey(Reader, Val Token, ЭтапВхода, Val Index)
    If Index = 1 Then
        ЭтапВхода = "request_key_read_first";
    Else
        ЭтапВхода = "request_key_read_later";
    EndIf;
    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;
    If Index = 1 Then
        ЭтапВхода = "request_key_token_first";
    Else
        ЭтапВхода = "request_key_token_later";
    EndIf;
    If Reader.CurrentValueType <> Token Then Raise "ASYNC-REQUEST"; EndIf;
EndProcedure

&AtClient
Function AsyncReadRequest(ЭтапВхода)
    Var AsyncRequestKey, AsyncRequestEndToken;
    // Streaming grammar rejects nested values, duplicate keys and trailing data.
    ЭтапВхода = "request_open";
    Reader = New JSONReader;
    Reader.OpenFile(LaunchParameter);
    ЭтапВхода = "request_object";
    Request = New Structure;
    AsyncExpectToken(Reader, JSONValueType.ObjectStart);
    For Index = 1 To 5 Do
        ЭтапВхода = "request_key_call";
        AsyncExpectRequestKey(Reader, JSONValueType.PropertyName, ЭтапВхода, Index);
        If Index = 1 Then
            ЭтапВхода = "request_key_current_first";
        Else
            ЭтапВхода = "request_key_current_later";
        EndIf;
        AsyncRequestKey = Reader.CurrentValue;
        If Index = 1 Then
            ЭтапВхода = "request_key_property_first";
        Else
            ЭтапВхода = "request_key_property_later";
        EndIf;
        If Request.Property(AsyncRequestKey) Then Raise "ASYNC-REQUEST"; EndIf;
        ЭтапВхода = "request_value";
        If AsyncRequestKey = "schema" Or AsyncRequestKey = "version" Then
            AsyncExpectToken(Reader, JSONValueType.Number);
            If TypeOf(Reader.CurrentValue) <> Type("Number") Or Reader.CurrentValue <> 1 Then
                Raise "ASYNC-REQUEST";
            EndIf;
        ElsIf AsyncRequestKey = "nonce" Or AsyncRequestKey = "entered" Or AsyncRequestKey = "completed" Then
            AsyncExpectToken(Reader, JSONValueType.String);
        Else
            Raise "ASYNC-REQUEST";
        EndIf;
        Request.Insert(AsyncRequestKey, Reader.CurrentValue);
    EndDo;
    ЭтапВхода = "request_end_call";
    AsyncRequestEndToken = ТипЗначенияJSON.КонецОбъекта;
    ЭтапВхода = "request_end_read";
    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;
    ЭтапВхода = "request_end_token";
    If Reader.CurrentValueType <> AsyncRequestEndToken Then Raise "ASYNC-REQUEST"; EndIf;
    ЭтапВхода = "request_end_trailing";
    If Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;
    ЭтапВхода = "request_end_close";
    Reader.Close();
    ЭтапВхода = "request_fields";
    If Not Request.Property("schema") Or Not Request.Property("version")
        Or Not Request.Property("nonce") Or Not Request.Property("entered")
        Or Not Request.Property("completed") Then Raise "ASYNC-REQUEST"; EndIf;
    ЭтапВхода = "request_nonce";
    If StrLen(Request.nonce) <> 32 Then Raise "ASYNC-REQUEST"; EndIf;
    For Index = 1 To 32 Do
        If StrFind("0123456789abcdef", Mid(Request.nonce, Index, 1)) = 0 Then
            Raise "ASYNC-REQUEST";
        EndIf;
    EndDo;
    ЭтапВхода = "request_paths";
    If StrLen(Request.entered) = 0 Or StrLen(Request.entered) > 512
        Or StrLen(Request.completed) = 0 Or StrLen(Request.completed) > 512
        Or Request.entered = Request.completed Then Raise "ASYNC-REQUEST"; EndIf;
    Return Request;
EndFunction

&НаКлиенте
Процедура АсинхЗаписатьВход()
    Запись = Новый ЗаписьJSON;
    Запись.ОткрытьФайл(АсинхЗапрос.entered, "UTF-8", Ложь);
    ЗаписатьJSON(Запись, Новый Структура("schema,nonce,case,phase,witness",
        1, АсинхЗапрос.nonce, АсинхНомерСлучая(), "entered", АсинхКонтекст));
    Запись.Закрыть();
КонецПроцедуры

&НаКлиенте
Процедура АсинхЗаписатьЗавершение(Знач Статус, Знач Причина)
    Если АсинхЗавершено Тогда ВызватьИсключение "ASYNC-ONCE"; КонецЕсли;
    АсинхЗавершено = Истина;
    Если Статус <> 1 Тогда
        АсинхТрасса = Новый Массив;
        АсинхЗначения = Новый Массив;
        АсинхОшибки = Новый Массив;
    КонецЕсли;
    // OpenFile is not an atomic exclusive-create primitive. Fresh owned paths,
    // source review, this once guard and host identity checks provide the proof.
    Запись = Новый ЗаписьJSON;
    Запись.ОткрытьФайл(АсинхЗапрос.completed, "UTF-8", Ложь);
    ЗаписатьJSON(Запись, Новый Структура("schema,nonce,case,phase,witness,status,failure,trace,values,errors",
        1, АсинхЗапрос.nonce, АсинхНомерСлучая(), "completed", АсинхКонтекст,
        Статус, Причина, АсинхТрасса, АсинхЗначения, АсинхОшибки));
    Запись.Закрыть();
КонецПроцедуры

&НаКлиенте
Асинх Процедура АсинхКореньПробы()
    Попытка
        АсинхСобытие(0);
        Тест = АсинхТестПробы();
        АсинхУдержать(Тест);
        Результат = Ждать Тест;
        АсинхСобытие(3);
    Исключение
        АсинхСбой = Истина;
    КонецПопытки;
    Если АсинхСбой Или АсинхНесовместимо Тогда
        // No normal-path extra Await. On failure, every retained function,
        // including leaves/inner/test, is terminal before failure completion.
        Индекс = 0;
        Пока Индекс < АсинхОжидания.Количество() Цикл
            Попытка
                Отброшено = Ждать АсинхОжидания[Индекс];
            Исключение
                // Rejected Promise is terminal; no diagnostic publication.
            КонецПопытки;
            Индекс = Индекс + 1;
        КонецЦикла;
    КонецЕсли;
    Попытка
        Если АсинхСбой Тогда
            АсинхЗаписатьЗавершение(2, 12);
        ИначеЕсли АсинхНесовместимо Тогда
            АсинхЗаписатьЗавершение(3, 14);
        Иначе
            АсинхСобытие(4);
            Если АсинхСбой Тогда
                АсинхЗаписатьЗавершение(2, 12);
            Иначе
                АсинхЗаписатьЗавершение(1, 0);
            КонецЕсли;
        КонецЕсли;
    Исключение
        // Partial or missing marker cannot pass the external verifier.
    КонецПопытки;
    // The only application exit site is the owning Async root terminal path.
    ЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры

&НаКлиенте
Процедура ПриОткрытии(Отказ)
    ЭтапВхода = "request";
    Попытка
        АсинхЗапрос = AsyncReadRequest(ЭтапВхода);
        ЭтапВхода = "witness";
        АсинхКонтекст = АсинхКонтекстПробы();
        ЭтапВхода = "initialize";
        АсинхТрасса = Новый Массив;
        АсинхЗначения = Новый Массив;
        АсинхОшибки = Новый Массив;
        АсинхОжидания = Новый Массив;
        АсинхЗавершено = Ложь;
        АсинхНесовместимо = Ложь;
        АсинхСбой = Ложь;
        ЭтапВхода = "entered";
        АсинхЗаписатьВход();
        ЭтапВхода = "root";
        АсинхКореньПробы();
    Исключение
        // Finite private log witness only, never native semantic evidence.
        Сообщить("ASYNC-ENTRY-FAILURE:" + ЭтапВхода);
        // No completion and no early exit: external watchdog fails closed.
    КонецПопытки;
КонецПроцедуры

__ASYNC_CASE_SOURCE__
'''

ASYNC_CASE_SOURCES = (
    '''// Case 0: RU no-Await, repeated Await and implicit Undefined.
&НаКлиенте
Асинх Функция АсинхБезОжидания()
    АсинхСобытие(11);
    АсинхСобытие(12);
    Возврат 17;
КонецФункции
&НаКлиенте
Асинх Функция АсинхБезВозврата()
    АсинхСобытие(16);
    АсинхСобытие(17);
КонецФункции
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(4);
    АсинхСобытие(10);
    Обещание = АсинхБезОжидания();
    АсинхУдержать(Обещание);
    АсинхСобытие(13);
    АсинхСохранить(0, Обещание);
    Результат = Ждать Обещание;
    АсинхСобытие(14);
    АсинхСохранить(1, Результат);
    Повтор = Ждать Обещание;
    АсинхСобытие(15);
    АсинхСохранить(2, Повтор);
    Пустое = АсинхБезВозврата();
    АсинхУдержать(Пустое);
    РезультатПустого = Ждать Пустое;
    АсинхСобытие(18);
    АсинхСохранить(3, РезультатПустого);
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 1: settled leaf ordering, not a prescribed scheduler order.
&НаКлиенте
Асинх Функция АсинхЛист()
    АсинхСобытие(25);
    АсинхСобытие(26);
    Возврат 11;
КонецФункции
&НаКлиенте
Асинх Функция АсинхВетвь()
    АсинхСобытие(11);
    АсинхСобытие(12);
    Лист = АсинхЛист();
    АсинхУдержать(Лист);
    АсинхЛистЗначение = Ждать Лист;
    АсинхСобытие(13);
    АсинхСобытие(14);
    Возврат АсинхЛистЗначение + 1;
КонецФункции
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(3);
    АсинхСобытие(10);
    Обещание = АсинхВетвь();
    АсинхУдержать(Обещание);
    АсинхСобытие(15);
    АсинхСохранить(0, Обещание);
    АсинхСобытие(16);
    Результат = Ждать Обещание;
    АсинхСобытие(17);
    АсинхСохранить(1, АсинхЛистЗначение);
    АсинхСохранить(2, Результат);
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 2: both siblings and their leaves are retained and joined.
&НаКлиенте
Асинх Функция АсинхЛистА()
    АсинхСобытие(25);
    АсинхСобытие(26);
    Возврат 21;
КонецФункции
&НаКлиенте
Асинх Функция АсинхЛистБ()
    АсинхСобытие(27);
    АсинхСобытие(28);
    Возврат 22;
КонецФункции
&НаКлиенте
Асинх Функция АсинхВетвьА()
    АсинхСобытие(11);
    АсинхСобытие(12);
    Лист = АсинхЛистА();
    АсинхУдержать(Лист);
    Результат = Ждать Лист;
    АсинхСобытие(13);
    АсинхСобытие(14);
    Возврат Результат;
КонецФункции
&НаКлиенте
Асинх Функция АсинхВетвьБ()
    АсинхСобытие(17);
    АсинхСобытие(18);
    Лист = АсинхЛистБ();
    АсинхУдержать(Лист);
    Результат = Ждать Лист;
    АсинхСобытие(19);
    АсинхСобытие(20);
    Возврат Результат;
КонецФункции
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(5);
    АсинхСобытие(10);
    А = АсинхВетвьА();
    АсинхУдержать(А);
    АсинхСобытие(15);
    АсинхСохранить(0, А);
    АсинхСобытие(16);
    Б = АсинхВетвьБ();
    АсинхУдержать(Б);
    АсинхСобытие(21);
    АсинхСохранить(1, Б);
    Попытка
        ЗначениеА = Ждать А;
        АсинхСобытие(22);
        АсинхСохранить(2, ЗначениеА);
    Исключение
        АсинхСбой = Истина;
    КонецПопытки;
    Попытка
        ЗначениеБ = Ждать Б;
        АсинхСобытие(23);
        АсинхСохранить(3, ЗначениеБ);
    Исключение
        АсинхСбой = Истина;
    КонецПопытки;
    Попытка
        ПовторА = Ждать А;
        АсинхСобытие(24);
        АсинхСохранить(4, ПовторА);
    Исключение
        АсинхСбой = Истина;
    КонецПопытки;
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 3: each non-Promise operand gets a distinct terminal branch.
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(3);
    АсинхСобытие(10);
    Попытка
        Данные = Ждать 7;
        АсинхСобытие(11);
        АсинхСохранить(0, Данные);
    Исключение
        Ошибка = ИнформацияОбОшибке();
        АсинхСобытие(12);
        АсинхСохранитьОшибку(0, 3, Ошибка);
    КонецПопытки;
    АсинхСобытие(13);
    Попытка
        Данные = Ждать Неопределено;
        АсинхСобытие(14);
        АсинхСохранить(1, Данные);
    Исключение
        Ошибка = ИнформацияОбОшибке();
        АсинхСобытие(15);
        АсинхСохранитьОшибку(1, 4, Ошибка);
    КонецПопытки;
    АсинхСобытие(16);
    Попытка
        Данные = Ждать Null;
        АсинхСобытие(17);
        АсинхСохранить(2, Данные);
    Исключение
        Ошибка = ИнформацияОбОшибке();
        АсинхСобытие(18);
        АсинхСохранитьОшибку(2, 5, Ошибка);
    КонецПопытки;
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 4: at most one conditional unwrap; inner always joined explicitly.
&НаКлиенте
Асинх Функция АсинхВнутренняяФункция()
    АсинхСобытие(12);
    АсинхСобытие(13);
    Возврат 31;
КонецФункции
&НаКлиенте
Асинх Функция АсинхВнешняяФункция()
    АсинхСобытие(11);
    АсинхВнутреннее = АсинхВнутренняяФункция();
    АсинхУдержать(АсинхВнутреннее);
    АсинхСобытие(14);
    Возврат АсинхВнутреннее;
КонецФункции
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(4);
    АсинхСобытие(10);
    Внешнее = АсинхВнешняяФункция();
    АсинхУдержать(Внешнее);
    АсинхСобытие(15);
    АсинхСохранить(0, Внешнее);
    Первое = Ждать Внешнее;
    АсинхСобытие(16);
    АсинхСохранить(1, Первое);
    Если ТипЗнч(Первое) = Тип("Обещание") Тогда
        Второе = Ждать Первое;
        АсинхСобытие(17);
        АсинхСохранить(2, Второе);
    Иначе
        АсинхСобытие(18);
    КонецЕсли;
    ВнутреннийРезультат = Ждать АсинхВнутреннее;
    АсинхСобытие(19);
    АсинхСохранить(3, ВнутреннийРезультат);
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 5: separate implicit/explicit Val scalars and shared array alias.
&НаКлиенте
Асинх Функция АсинхПараметры(Первый, Знач Второй, Знач МассивДанных, ПоУмолчанию = 7)
    АсинхСобытие(11);
    Первый = 6;
    Второй = 8;
    АсинхСобытие(12);
    МассивДанных[0] = МассивДанных[0] + 1;
    АсинхСобытие(13);
    АсинхЗначениеУмолчания = ПоУмолчанию;
    АсинхСобытие(14);
    Возврат Первый + Второй + ПоУмолчанию;
КонецФункции
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(7);
    ПервыйФакт = 5;
    ВторойФакт = 4;
    МассивФакт = Новый Массив;
    МассивФакт.Добавить(9);
    АсинхСобытие(10);
    Обещание = АсинхПараметры(ПервыйФакт, ВторойФакт, МассивФакт);
    АсинхУдержать(Обещание);
    АсинхСобытие(15);
    АсинхСохранить(0, Обещание);
    Результат = Ждать Обещание;
    АсинхСобытие(16);
    АсинхСохранить(1, Результат);
    АсинхСохранить(2, ПервыйФакт);
    АсинхСохранить(3, ВторойФакт);
    АсинхСохранить(4, МассивФакт.Количество());
    АсинхСохранить(5, МассивФакт[0]);
    АсинхСохранить(6, АсинхЗначениеУмолчания);
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 6: call-side propagation remains distinct from rejected Await.
&НаКлиенте
Асинх Функция АсинхОтклонить()
    АсинхСобытие(11);
    АсинхСобытие(12);
    ВызватьИсключение("ASYNC-REJECT", КатегорияОшибки.ОшибкаКонфигурации,
        "ASYNC-CODE", "ASYNC-DETAIL", Неопределено);
КонецФункции
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(3);
    АсинхСобытие(10);
    ВызовВернулся = Ложь;
    Попытка
        Обещание = АсинхОтклонить();
        АсинхУдержать(Обещание);
        АсинхСобытие(13);
        АсинхСохранить(0, Обещание);
        ВызовВернулся = Истина;
    Исключение
        Ошибка = ИнформацияОбОшибке();
        АсинхСобытие(14);
        АсинхСохранитьОшибку(0, 0, Ошибка);
    КонецПопытки;
    Если ВызовВернулся Тогда
        АсинхСобытие(15);
        Попытка
            Результат = Ждать Обещание;
            АсинхСобытие(16);
            АсинхСохранить(1, Результат);
        Исключение
            Ошибка = ИнформацияОбОшибке();
            АсинхСобытие(17);
            АсинхСохранитьОшибку(1, 1, Ошибка);
        КонецПопытки;
        АсинхСобытие(18);
        Попытка
            Повтор = Ждать Обещание;
            АсинхСобытие(19);
            АсинхСохранить(2, Повтор);
        Исключение
            Ошибка = ИнформацияОбОшибке();
            АсинхСобытие(20);
            АсинхСохранитьОшибку(2, 2, Ошибка);
        КонецПопытки;
    КонецЕсли;
    АсинхСобытие(2);
КонецФункции
''',
    '''// Case 7: EN/mixed-case grammar, grouped nested Await argument/return.
&AtClient
AsYnC FuNcTiOn AsyncNestedLeaf()
    АсинхСобытие(11);
    АсинхСобытие(12);
    ReTuRn 32;
EnDfUnCtIoN
&AtClient
Function AsyncAddOne(Val Value)
    АсинхСобытие(13);
    Return Value + 1;
EndFunction
&AtClient
aSyNc fUnCtIoN AsyncEnglish()
    АсинхСобытие(10);
    Leaf = AsyncNestedLeaf();
    АсинхУдержать(Leaf);
    Return AsyncAddOne((aWaIt Leaf));
EndFunction
&AtClient
AsYnC PrOcEdUrE AsyncHandledProcedure()
    АсинхСобытие(15);
    Try
        Raise("ASYNC-REJECT", ErrorCategory.ConfigurationError,
            "ASYNC-CODE", "ASYNC-DETAIL", Undefined);
    Except
        SavedError = ErrorInfo();
        АсинхСобытие(16);
        АсинхСохранитьОшибку(2, 6, SavedError);
    EndTry;
    // Deliberately no suspension: terminal event is explicit, not inferred.
    АсинхСобытие(17);
EnDpRoCeDuRe
&НаКлиенте
Асинх Функция АсинхТестПробы()
    АсинхНачатьТест(3);
    Обещание = AsyncEnglish();
    АсинхУдержать(Обещание);
    АсинхСохранить(0, Обещание);
    Результат = Ждать Обещание;
    АсинхСобытие(14);
    АсинхСохранить(1, Результат);
    AsyncHandledProcedure();
    АсинхСобытие(18);
    АсинхСобытие(2);
КонецФункции
''',
)


ASYNC_FIXTURE_SHA256 = '83a6e22dbb4788498985e51e06ea610d2a9bc95702852da396cb6d7779bf1c5a'


def async_client_module(case_id: int) -> bytes:
    """Only trusted fixed literal sources, never request-controlled BSL."""
    if type(case_id) is not int or not 0 <= case_id < 8:
        raise FullError('invalid_input')
    if (type(ASYNC_TEMPLATE) is not str or type(ASYNC_CASE_SOURCES) is not tuple
            or len(ASYNC_CASE_SOURCES) != 8
            or ASYNC_TEMPLATE.count('__ASYNC_CASE_ID__') != 1
            or ASYNC_TEMPLATE.count('__ASYNC_CASE_SOURCE__') != 1
            or any(type(source) is not str or '__ASYNC_CASE_' in source
                   for source in ASYNC_CASE_SOURCES)):
        raise FullError('invalid_input')
    source_hash = hashlib.sha256(json.dumps(
        [ASYNC_TEMPLATE, ASYNC_CASE_SOURCES], ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    if source_hash != ASYNC_FIXTURE_SHA256:
        raise FullError('invalid_input')
    text = ASYNC_TEMPLATE.replace('__ASYNC_CASE_ID__', str(case_id))
    text = text.replace('__ASYNC_CASE_SOURCE__', ASYNC_CASE_SOURCES[case_id])
    return generated_module(text.encode('utf-8'))


def async_manifest_paths(root: Path, inputs: Path):
    metadata = ('Launcher.xml','Launcher/Ext/ObjectModule.bsl','Launcher/Forms/Main.xml','Launcher/Forms/Main/Ext/Form.xml')
    paths = {str(inputs/'bootstrap/full_suite.py'):(MAX_OUTPUT,False)}
    for name in metadata: paths[str(inputs/'launcher/launcher_1c'/name)]=(MAX_OUTPUT,False)
    for i in range(8):
        case=root/('case-'+str(i))
        for prefix in ('src','roundtrip'):
            for name in (*metadata,CLIENT_MODULE):
                paths[str(case/prefix/name)]=(MAX_OUTPUT,prefix=='roundtrip' and name=='Launcher/Ext/ObjectModule.bsl')
        paths[str(case/'build.result')]=(128,False)
        paths[str(case/'dump.result')]=(128,False)
        paths[str(case/'AsyncClientProbe.epf')]=(MAX_OUTPUT,False)
        paths[str(case/'request.json')]=(2048,False)
        paths[str(case/'entered.json')]=(ASYNC_MAX_MARKER,False)
        paths[str(case/'completed.json')]=(ASYNC_MAX_MARKER,False)
    return paths


def write_async_continuity(root: Path, inputs: Path, nonce: str, retained):
    expected=async_manifest_paths(root,inputs)
    entries={}
    for path,saved,limit,allow_empty in retained:
        name=str(path)
        if name not in expected or expected[name] != (limit,allow_empty):
            raise FullError('invalid_result')
        item=[list(map(str,saved[0])),digest(saved[1])]
        if name in entries and entries[name] != item:
            raise FullError('stale_evidence')
        entries[name]=item
    if set(entries) != set(expected): raise FullError('invalid_result')
    raw=json.dumps({'schema':1,'nonce':nonce,'files':entries},sort_keys=True,separators=(',',':')).encode()
    if len(raw)>65536: raise FullError('output_limit')
    with (root/'continuity.json').open('xb') as stream: stream.write(raw)
    return digest(raw)


def final_async_evidence_check(root: Path, inputs: Path, nonce: str, expected_sha256: str):
    manifest=root/'continuity.json'
    pinned=async_file_snapshot(manifest,65536)
    if not _async_hash(expected_sha256) or digest(pinned[1]) != expected_sha256:
        raise FullError('stale_evidence')
    value=strict_json(pinned[1],max_depth=5)
    expected=async_manifest_paths(root,inputs)
    if (type(value) is not dict or set(value)!={'schema','nonce','files'}
            or type(value['schema']) is not int or value['schema']!=1
            or value['nonce']!=nonce or not valid_nonce(nonce)
            or type(value['files']) is not dict or set(value['files'])!=set(expected)):
        raise FullError('invalid_result')
    for name,(limit,allow_empty) in expected.items():
        claim=value['files'][name]
        if (type(claim) is not list or len(claim)!=2 or type(claim[0]) is not list
                or len(claim[0])!=7 or any(type(n) is not str or re.fullmatch(r'(0|[1-9][0-9]{0,19})',n) is None for n in claim[0])
                or not _async_hash(claim[1])):
            raise FullError('invalid_result')
        current=async_file_snapshot(Path(name),limit,allow_empty=allow_empty)
        if list(map(str,current[0]))!=claim[0] or digest(current[1])!=claim[1]:
            raise FullError('stale_evidence')
    async_require_snapshot(manifest,pinned,65536)

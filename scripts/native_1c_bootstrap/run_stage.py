#!/usr/bin/env python3
"""Inside-container stage two. All native evidence and diagnostics stay in tmpfs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import uuid

from diagnostics import (bounded_exit_code, collect_diagnostics, empty_diagnostics,
                         collect_protection_observation, empty_protection_observation)
from inject_modules import DraftError, PROTOCOL, inject
from evidence_gates import (bounded_bytes, read_marker, require_epf,
                            require_marker_pair, require_reimported_modules, require_reimported_metadata,
                            require_zero_result)

ONEC = Path('/opt/1cv8t/x86_64/8.3.27.1508/1cv8t')
ROOT = Path('/tmp/onec-smoke')
INPUTS = Path('/smoke')
EXPECTED_VERSION = '8.3.27.1508'
EXPECTED_MESSAGES = ['native-smoke-v1', '42']
STAGES = {'inject', 'load', 'redump', 'bootstrap', 'named_designer', 'verify',
          'launcher_build', 'simple_epf', 'unknown'}
KINDS = {'none', 'timeout', 'process_failed', 'invalid_dump_result', 'artifact_missing',
         'metadata_rejected', 'module_mismatch', 'compile_error', 'permission_denied',
         'hook_missing', 'marker_invalid', 'version_mismatch', 'output_mismatch',
         'unexpected_failure', 'stale_evidence', 'unsupported_api'}
FLAGS = {'modules_reimported', 'bootstrap_verified', 'named_designer_verified',
         'named_user_verified', 'control_removed', 'launcher_built', 'simple_epf_passed',
         'security_change_attempted'}


class StageError(Exception):
    def __init__(self, kind: str, exit_code: int | None = None):
        self.kind = kind
        self.exit_code = bounded_exit_code(exit_code)


def empty_report() -> dict:
    return {'schema': 1, 'status': 'failed', 'failed_stage': 'inject',
            'failure_kind': 'unexpected_failure', 'actual_version': None,
            'version_source': 'not_measured', 'simple_output_sha256': None,
            'security_settings_state': 'not_attempted', 'diagnostics': empty_diagnostics(),
            'protection_observation': empty_protection_observation(),
            **{flag: False for flag in FLAGS}}


def absent(*paths: Path) -> None:
    if any(path.exists() or path.is_symlink() for path in paths):
        raise StageError('stale_evidence')


def process(command: list[str], directory: Path, console: Path, timeout: float = 120) -> None:
    absent(console)
    with console.open('xb') as log:
        with subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                              stdout=log, stderr=subprocess.STDOUT,
                              start_new_session=True) as child:
            try:
                code = child.wait(timeout=timeout)
            except BaseException as error:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                if isinstance(error, subprocess.TimeoutExpired):
                    raise StageError('timeout') from None
                raise
    if code != 0:
        raise StageError('process_failed', exit_code=code)


def command(mode: str, database: Path, user: str | None = None) -> list[str]:
    args = [str(ONEC), mode, '/F', str(database)]
    if user is not None:
        args += ['/N', user]
    return args + ['/AppAutoCheckVersion-', '/DisableStartupDialogs',
                   '/DisableStartupMessages', '/L', 'ru']


def batch(name: str, database: Path, evidence: Path, operation: list[str],
          user: str | None = None) -> None:
    result, log = evidence / (name + '.result'), evidence / (name + '.log')
    absent(result, log)
    process(command('DESIGNER', database, user) + operation +
            ['/Out', str(log), '/DumpResult', str(result)], evidence,
            evidence / (name + '-console.log'))
    try:
        require_zero_result(result, 0)
    except (DraftError, OSError):
        raise StageError('invalid_dump_result') from None


def enterprise(stage: str, database: Path, evidence: Path, manifest: dict,
               report: dict, user: str | None) -> None:
    control = evidence / 'control.json'
    markers = [evidence / (stage + '-' + hook + '.json') for hook in ('session', 'managed')]
    log = evidence / (stage + '.log')
    absent(control, log, *markers)
    token = manifest[stage + '_token']
    with control.open('x', encoding='utf-8') as target:
        json.dump({'protocol': PROTOCOL, 'run_id': manifest['run_id'],
                   'stage': stage, 'launch_token': token}, target)
    try:
        try:
            process(command('ENTERPRISE', database, user) +
                    ['/RunModeManagedApplication', '/C', token, '/Out', str(log)],
                    evidence, evidence / (stage + '-console.log'))
        except StageError as error:
            if error.kind != 'stale_evidence':
                observation = collect_protection_observation(evidence, stage, manifest)
                if observation['stage'] is not None:
                    report['protection_observation'] = observation
            raise
        observation = collect_protection_observation(evidence, stage, manifest)
        if observation['stage'] is not None:
            report['protection_observation'] = observation
        if not all(path.is_file() and not path.is_symlink() for path in markers):
            raise StageError('hook_missing')
        # Check the complete matching marker pair before exposing a numeric
        # SystemInfo value, even when that measured value is unexpected.
        try:
            marker = read_marker(markers[1])
            version = marker.get('actual_version')
            if type(version) is not str or not re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){3}', version):
                raise DraftError('Invalid numeric runtime version')
            require_marker_pair(evidence, stage, manifest['run_id'], manifest['user'],
                                returncode=0, expected_version=version)
        except (DraftError, OSError):
            raise StageError('marker_invalid') from None
        report['actual_version'] = version
        report['version_source'] = 'SystemInfo.AppVersion'
        if version != EXPECTED_VERSION:
            raise StageError('version_mismatch')
    finally:
        control.unlink(missing_ok=True)


def load_launcher():
    spec = importlib.util.spec_from_file_location('native_smoke_launcher', INPUTS / 'launcher/test_launcher.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def strict_simple_result(path: Path, output: Path) -> str:
    value = read_marker(path)
    if (set(value) != {'messages', 'error'} or type(value['messages']) is not list
            or any(type(item) is not str for item in value['messages'])
            or value['messages'] != EXPECTED_MESSAGES or value['error'] != ''):
        raise StageError('output_mismatch')
    expected = ''.join(item + '\n' for item in EXPECTED_MESSAGES).encode('utf-8')
    if bounded_bytes(output, 1024) != expected:
        raise StageError('output_mismatch')
    return hashlib.sha256(expected).hexdigest()


def run(*, full_nonce: str | None = None, client_probe: bool = False, watchdog_check: bool = False, client_dates: bool = False, client_values: bool = False, client_collections: bool = False, client_numbers: bool = False, client_async: bool = False, preprocessor_measurement: bool = False, tree_suite: bool = False, tree_profile: str = 'tree-v1') -> dict:
    if type(tree_profile) is not str or tree_profile not in ('tree-v1', 'tree-copy-v1') or (not tree_suite and tree_profile != 'tree-v1'):
        raise StageError("invalid_input")
    if type(tree_suite) is not bool:
        raise StageError("invalid_input")
    if tree_suite:
        import full_suite
        if (not full_suite.valid_nonce(full_nonce)
                or any(value is not False for value in (client_probe, watchdog_check, client_dates,
                    client_values, client_collections, client_numbers, client_async, preprocessor_measurement))):
            raise StageError("invalid_input")
    if (client_dates or client_values or client_collections or client_numbers) and (not client_probe or full_nonce is None):
        raise StageError("invalid_input")
    if type(preprocessor_measurement) is not bool or (preprocessor_measurement and (not client_probe or full_nonce is None)):
        raise ValueError("preprocessor mode")
    if type(client_async) is not bool or (client_async and (not client_probe or full_nonce is None or watchdog_check or client_dates or client_values or client_collections or client_numbers)):
        raise StageError("invalid_input")
    report = empty_report()
    stage = 'inject'
    evidence = ROOT / ('stage2-' + uuid.uuid4().hex)
    evidence.mkdir(mode=0o700)
    database = ROOT / 'db'
    user = 'NativeSmoke'
    manifest = None
    try:
        try:
            manifest = inject(ROOT / 'config', evidence / 'injected', run_id=uuid.uuid4().hex,
                              user=user, evidence=str(evidence))
        except (DraftError, OSError):
            raise StageError('metadata_rejected') from None
        stage = 'load'
        # Loading role metadata can itself change the disposable security state.
        report['security_change_attempted'] = True
        report['security_settings_state'] = 'unverified'
        batch(stage, database, evidence, ['/LoadConfigFromFiles', str(evidence / 'injected'), '/UpdateDBCfg'])
        stage = 'redump'
        redump = evidence / 'redump'
        redump.mkdir()
        batch(stage, database, evidence, ['/DumpConfigToFiles', str(redump), '-Format', 'Hierarchical'])
        try:
            require_reimported_metadata(evidence / 'injected', redump)
            require_reimported_modules(evidence / 'injected', redump)
        except (DraftError, OSError):
            raise StageError('module_mismatch') from None
        report['modules_reimported'] = True
        stage = 'bootstrap'
        enterprise(stage, database, evidence, manifest, report, None)
        report['bootstrap_verified'] = True
        report['security_settings_state'] = 'verified'
        stage = 'named_designer'
        named = evidence / 'named-designer'
        named.mkdir()
        batch(stage, database, evidence, ['/DumpConfigToFiles', str(named), '-Format', 'Hierarchical'], user)
        try:
            require_reimported_metadata(evidence / 'injected', named)
            require_reimported_modules(evidence / 'injected', named)
        except (DraftError, OSError):
            raise StageError('module_mismatch') from None
        report['named_designer_verified'] = True
        stage = 'verify'
        enterprise(stage, database, evidence, manifest, report, user)
        report['named_user_verified'] = True
        absent(evidence / 'control.json')
        report['control_removed'] = True
        stage = 'launcher_build'
        launcher = load_launcher()
        platform = launcher.Platform(ONEC, database, 120, user)
        launcher_epf = evidence / 'Launcher.epf'
        absent(launcher_epf, launcher_epf.with_suffix('.build-result.txt'))
        launcher_sources = evidence / 'launcher-src'
        absent(launcher_sources)
        shutil.copytree(INPUTS / 'launcher/launcher_1c', launcher_sources)
        launcher.build_epf(platform, launcher_sources / 'Launcher.xml', launcher_epf)
        require_zero_result(launcher_epf.with_suffix('.build-result.txt'), 0)
        require_epf(launcher_epf)
        report['launcher_built'] = True
        stage = 'simple_epf'
        case = evidence / 'simple-case'
        output = evidence / 'simple.out'
        absent(case, output)
        launcher.run_case(platform, INPUTS / 'bootstrap/simple_smoke.bsl', launcher_epf, case, output)
        require_zero_result(case / 'TestModule.build-result.txt', 0)
        require_epf(case / 'TestModule.epf')
        report['simple_output_sha256'] = strict_simple_result(case / 'result.json', output)
        report['simple_epf_passed'] = True
        report.update(status='ok', failed_stage=None, failure_kind='none')
    except Exception as error:
        fallback = error.kind if isinstance(error, StageError) else 'unexpected_failure'
        if isinstance(error, (DraftError, FileNotFoundError)):
            fallback = 'artifact_missing'
        # Existing launcher errors remain private; classify only known text and logs.
        if error.__class__.__name__ == 'LaunchError':
            fallback = 'timeout' if 'таймаут' in str(error).casefold() else 'process_failed'
        # Keep the primary orchestration failure authoritative. Diagnostics are
        # independent, lossy observations and cannot change any success gate.
        if fallback == 'stale_evidence':
            # Rejected pre-existing evidence cannot describe this process.
            diagnostics = empty_diagnostics()
        else:
            diagnostics = collect_diagnostics(evidence, stage, manifest,
                                              error.exit_code if isinstance(error, StageError) else None)
        report.update(failed_stage=stage, failure_kind=fallback, diagnostics=diagnostics)
    if tree_suite:
        import tree_suite as tree_lane
        suite = tree_lane.empty_report(full_nonce, profile=tree_profile)
        if report['status'] == 'ok' and all(report[flag] for flag in FLAGS):
            suite = tree_lane.run_suite(launcher, platform, launcher_epf,
                                       ROOT / ('stage3-' + full_nonce), INPUTS, full_nonce, profile=tree_profile)
        tree_lane.write_report(ROOT / 'stage3-report.json', suite, profile=tree_profile)
        return report
    if full_nonce is not None:
        # Stage two keeps its exact legacy schema. Stage three starts only after
        # every fresh bootstrap/security/version/simple-EPF gate has succeeded.
        import full_suite
        suite = full_suite.empty_report(full_nonce, client_probe=client_probe, watchdog_check=watchdog_check, client_dates=client_dates, client_values=client_values, client_collections=client_collections, client_numbers=client_numbers, **({"client_async": True} if client_async else {}), **({"preprocessor_measurement": True} if preprocessor_measurement else {}), preprocessor_runtime=client_probe and not preprocessor_measurement)
        if report['status'] == 'ok' and all(report[flag] for flag in FLAGS):
            suite = full_suite.run_suite(launcher, platform, launcher_epf,
                                        ROOT / ('stage3-' + full_nonce), INPUTS, full_nonce, client_probe=client_probe, watchdog_check=watchdog_check, client_dates=client_dates, client_values=client_values, client_collections=client_collections, client_numbers=client_numbers, **({"client_async": True} if client_async else {}), **({"preprocessor_measurement": True} if preprocessor_measurement else {}))
        full_suite.write_report(ROOT / 'stage3-report.json', suite)
    return report


def main(argv: list[str] | None = None) -> int:
    # Fixed full-mode arguments only; the nonce never selects an arbitrary path.
    arguments = [] if argv is None else argv
    full_nonce = None
    tree_suite = bool(arguments and arguments[0] in ('--tree-suite', '--tree-copy-suite'))
    tree_profile = 'tree-copy-v1' if arguments and arguments[0] == '--tree-copy-suite' else 'tree-v1'
    if tree_suite:
        import full_suite
        if len(arguments) != 3 or arguments[1] != '--invocation-nonce' or not full_suite.valid_nonce(arguments[2]):
            return 2
        arguments = ['--full-suite', *arguments[1:]]
    preprocessor_measurement = bool(arguments and arguments[-1] == "--client-preprocessor-measurement")
    if preprocessor_measurement:
        arguments = arguments[:-1]
    client_async = bool(arguments and arguments[-1] == "--client-async-measurement")
    if client_async:
        arguments = arguments[:-1]
    client_numbers = bool(arguments and arguments[-1] == "--client-numbers-parity")
    if client_numbers:
        arguments = arguments[:-1]
    client_collections = bool(arguments and arguments[-1] == "--client-collections-parity")
    if client_collections:
        arguments = arguments[:-1]
    client_values = bool(arguments and arguments[-1] == "--client-values-parity")
    if client_values:
        arguments = arguments[:-1]
    client_dates = bool(arguments and arguments[-1] == "--client-dates-parity")
    if client_dates:
        arguments = arguments[:-1]
    watchdog_check = bool(arguments and arguments[-1] == "--client-watchdog-check")
    if watchdog_check:
        arguments = arguments[:-1]
    client_probe = bool(arguments and arguments[-1] == "--client-probe")
    if (preprocessor_measurement or watchdog_check or client_dates or client_values or client_collections or client_numbers) and not client_probe:
        return 2
    if client_async and (not client_probe or watchdog_check or client_dates or client_values or client_collections or client_numbers):
        return 2
    if client_probe:
        arguments = arguments[:-1]
        if not arguments:
            return 2
    if arguments:
        import full_suite
        if (len(arguments) != 3 or arguments[:2] != ['--full-suite', '--invocation-nonce']
                or not full_suite.valid_nonce(arguments[2])):
            return 2
        full_nonce = arguments[2]
    # Only this bounded report is consumed by the shell. No tracebacks/raw errors.
    try:
        report = run() if full_nonce is None else run(full_nonce=full_nonce, **({"tree_suite": True, **({"tree_profile": tree_profile} if tree_profile != "tree-v1" else {})} if tree_suite else {}), client_probe=client_probe, watchdog_check=watchdog_check, client_dates=client_dates, **({"client_values": True} if client_values else {}), **({"client_collections": True} if client_collections else {}), **({"client_numbers": True} if client_numbers else {}), **({"client_async": True} if client_async else {}), **({"preprocessor_measurement": True} if preprocessor_measurement else {}))
    except Exception:
        report = empty_report()
        # An unexpected exception could follow a persisted user write. Never
        # downgrade uncertain mutation to "not_attempted" in the last-resort path.
        report.update(failed_stage="unknown", security_change_attempted=True,
                      security_settings_state="unverified")
    target = ROOT / 'stage2-report.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True)
    if full_nonce is not None:
        try:
            suite = full_suite.strict_json(full_suite.secure_bytes(
                ROOT / 'stage3-report.json', full_suite.MAX_STAGE_REPORT))
            if suite['status'] != 'ok':
                return 1
        except Exception:
            return 1
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

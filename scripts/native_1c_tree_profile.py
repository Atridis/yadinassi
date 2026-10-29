"""Independent, fail-closed host contract for the fixed tree-v1 measurement.

This profile never changes the ordinary six-scenario inventory or comparators.
"""
from __future__ import annotations
import base64
import contextlib
import binascii
import importlib.util
import json
import os
import shutil
import uuid
import types
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'tree-v1'
SCHEMA = 'native-1c-tree-v1'
STAGE_SCHEMA = 'native-1c-tree-stage-v1'
CASE = 'tree_fill_values'
SOURCE = 'integrational_tests/measurements/tree_fill_values.bsl'
SOURCE_SHA256 = '47ee0383ac5a9db0bf9d4132b78f0ca40eb46712b4152654feec776ce38e22df'
MAX_OUTPUT = 8192
MAX_TRANSPORT = 65536
MESSAGE_COUNT = 33


def sibling(name):
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location('tree_host_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FULL = sibling('native_1c_full_host')
CONTRACT = sibling('native_1c_tree_fill_contract')


class TreeError(ValueError):
    pass


def require(condition, reason='tree_report_invalid'):
    if not condition:
        raise TreeError(reason)


def validate_diagnostic(value):
    if value is None:
        return
    require(type(value) is dict and set(value) == {'site', 'case', 'category', 'calibration'})
    require(value['site'] in ('server', 'client'))
    require(value['case'] is None or type(value['case']) is int and 0 <= value['case'] <= 32)
    require(value['category'] in ('invalid_type', 'output_limit', 'encoding', 'record_count', 'calibration',
                                 'record_shape', 'probe_b', 'probe_p', 'probe_q', 'probe_r', 'payload_contract'))
    require(value['calibration'] is None or type(value['calibration']) is str and len(value['calibration']) == 1
            and value['calibration'] in '0123456789ABCDEFGHIJKLMNOPQR')
    category = value['category']
    require(not (category == 'calibration' and value['case'] != 0))
    require(not (category in ('record_shape', 'probe_b', 'probe_p', 'probe_q', 'probe_r', 'payload_contract')
                 and (type(value['case']) is not int or not 1 <= value['case'] <= 32)))
    require(not (category in ('invalid_type', 'output_limit', 'encoding', 'record_count') and value['case'] is not None))
    require(not (category != 'calibration' and value['calibration'] is not None))


def validate_envelope(raw, nonce, input_hashes, module_hashes, report_validator):
    """Accept successful native server/client evidence, never observer errors."""
    try:
        require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce))
        data = FULL.strict_json(raw, MAX_TRANSPORT)
        require(type(data) is dict and set(data) == {'schema', 'profile', 'nonce', 'report', 'outputs'})
        require((data['schema'], data['profile'], data['nonce']) == (SCHEMA, PROFILE, nonce))
        report = data['report']
        require(type(report) is dict)
        report_validator(json.dumps(report, separators=(',', ':')).encode(), bootstrap=True, full_suite=True)
        stage = report['stage3']
        require(type(stage) is dict and set(stage) == {
            'schema', 'profile', 'nonce', 'status', 'failure_kind', 'failed_case',
            'input_sha256', 'cases', 'client_tree', 'observation_diagnostic'})
        require((stage['schema'], stage['profile'], stage['nonce']) == (STAGE_SCHEMA, PROFILE, nonce))
        require(type(input_hashes) is dict and input_hashes.get(SOURCE) == SOURCE_SHA256)
        require(stage['input_sha256'] == input_hashes)
        diagnostic = stage['observation_diagnostic']
        validate_diagnostic(diagnostic)
        if diagnostic is not None:
            require(stage['status'] == 'failed' and stage['failure_kind'] == 'unsupported_observation')
            require(report['status'] == 'stage3_failed' and report['native_tests_completed'] is False)
            require(data['outputs'] == [])
            require(type(stage['cases']) is list and len(stage['cases']) == 1)
            witness = stage['cases'][0]
            require(type(witness) is dict and set(witness) == FULL.CASE_KEYS)
            require(witness['name'] == CASE and witness['source_sha256'] == SOURCE_SHA256)
            if diagnostic['site'] == 'server':
                require(stage['failed_case'] == CASE and witness['status'] == 'failed')
                require(all(witness[k] is None for k in ('module_sha256', 'output_sha256', 'output_size', 'message_count')))
                unstarted = stage['client_tree']
                require(type(unstarted) is dict and FULL.CLIENT_OUTPUT_KEYS <= set(unstarted))
                require(unstarted['status'] == 'not_started' and all(unstarted[k] is None for k in FULL.CLIENT_OUTPUT_KEYS))
                FULL.validate_client_probe({k: v for k, v in unstarted.items() if k not in FULL.CLIENT_OUTPUT_KEYS}, SOURCE_SHA256, module_hashes['client_tree'])
            else:
                require(stage['failed_case'] is None and witness['status'] == 'ok')
                require(witness['module_sha256'] == module_hashes[CASE])
                require(type(witness['message_count']) is int and witness['message_count'] == MESSAGE_COUNT)
                require(type(witness['output_size']) is int and 0 < witness['output_size'] <= MAX_OUTPUT)
                require(FULL.is_digest(witness['output_sha256']))
                client_failure = stage['client_tree']
                require(type(client_failure) is dict and set(client_failure) == FULL.CLIENT_FLAGS | FULL.CLIENT_HASHES | FULL.CLIENT_OUTPUT_KEYS | {'status', 'failure_kind', 'process_diagnostics'})
                require(client_failure['status'] == 'failed' and client_failure['failure_kind'] == 'unsupported_observation')
                require(client_failure['source_sha256'] == SOURCE_SHA256 and client_failure['module_sha256'] == module_hashes['client_tree'] and client_failure['roundtrip_sha256'] == module_hashes['client_tree'])
                require(all(type(client_failure[k]) is bool for k in FULL.CLIENT_FLAGS))
                require(client_failure['witness_verified'] is False and all(client_failure[k] is None for k in FULL.CLIENT_OUTPUT_KEYS))
                require(client_failure['entered'] is True and client_failure['process_exited'] is True
                        and client_failure['completed'] is False and client_failure['quiet'] is True)
                FULL.validate_process_diagnostics(client_failure['process_diagnostics'])
                require(client_failure['process_diagnostics']['stage'] == 'after_exit'
                        and client_failure['process_diagnostics']['reason'] == 'none')
            failure = TreeError('tree_observation_rejected')
            failure.observation_diagnostic = diagnostic.copy()
            raise failure
        if stage['status'] == 'failed' and diagnostic is None:
            require(report['status'] == 'stage3_failed' and report['native_tests_completed'] is False and data['outputs'] == [])
            require(type(stage['failure_kind']) is str and stage['failure_kind'] in FULL.FAILURES | {'unsupported_observation'} and stage['failure_kind'] not in ('none', 'unsupported_observation'))
            require(stage['failed_case'] in (None, CASE))
            require(type(stage['cases']) is list and len(stage['cases']) == 1)
            failed_case = stage['cases'][0]
            require(type(failed_case) is dict and set(failed_case) == FULL.CASE_KEYS and failed_case['name'] == CASE)
            require(failed_case['status'] in ('not_started', 'failed', 'ok'))
            require(failed_case['source_sha256'] in (None, SOURCE_SHA256) and failed_case['module_sha256'] in (None, module_hashes[CASE]))
            require(failed_case['output_sha256'] is None or FULL.is_digest(failed_case['output_sha256']))
            require(failed_case['output_size'] is None or type(failed_case['output_size']) is int and 0 < failed_case['output_size'] <= MAX_OUTPUT)
            require(failed_case['message_count'] is None or type(failed_case['message_count']) is int and failed_case['message_count'] == MESSAGE_COUNT)
            failed_client = stage['client_tree']
            require(type(failed_client) is dict and FULL.CLIENT_OUTPUT_KEYS <= set(failed_client))
            require(type(failed_client.get('failure_kind')) is str and failed_client['failure_kind'] in FULL.FAILURES | {'unsupported_observation'})
            base_client = {k: v for k, v in failed_client.items() if k not in FULL.CLIENT_OUTPUT_KEYS}
            if base_client['failure_kind'] == 'unsupported_observation':
                require(base_client['status'] == 'failed')
                base_client['failure_kind'] = 'invalid_result'
            FULL.validate_client_probe(base_client, SOURCE_SHA256, module_hashes['client_tree'])
            if failed_client['status'] == 'failed':
                require(failed_client['failure_kind'] == stage['failure_kind'])
            if failed_client['status'] == 'ok':
                require(failed_case['status'] == 'ok' and all(failed_client[k] == failed_case[k] and type(failed_client[k]) is type(failed_case[k]) for k in FULL.CLIENT_OUTPUT_KEYS))
            else:
                require(all(failed_client[k] is None for k in FULL.CLIENT_OUTPUT_KEYS))
            if stage['failed_case'] == CASE:
                require(failed_case['status'] == 'failed' and failed_client['status'] == 'not_started')
                require(all(failed_case[k] is None for k in ('module_sha256', 'output_sha256', 'output_size', 'message_count')))
            else:
                require(failed_case['status'] in ('not_started', 'ok'))
                if failed_case['status'] == 'not_started':
                    require(all(failed_case[k] is None for k in FULL.CASE_KEYS - {'name', 'status'}))
                    require(failed_client['status'] == 'not_started')
                else:
                    require(failed_case['source_sha256'] == SOURCE_SHA256 and failed_case['module_sha256'] == module_hashes[CASE])
                    require(FULL.is_digest(failed_case['output_sha256']) and type(failed_case['output_size']) is int
                            and 0 < failed_case['output_size'] <= MAX_OUTPUT and type(failed_case['message_count']) is int
                            and failed_case['message_count'] == MESSAGE_COUNT)
            process = FULL.validate_process_diagnostics(failed_client['process_diagnostics'])
            failure = TreeError('tree_native_evidence_rejected')
            failure.native_failure = {'stage': 'tree', 'reason': stage['failure_kind'],
                                      'case': 'tree_fill_values' if stage['failed_case'] == CASE else None,
                                      'process_stage': process['stage'], 'process_reason': process['reason']}
            raise failure
        require(report['status'] == 'ok' and report['native_tests_completed'] is True)
        require(stage['status'] == 'ok' and stage['failure_kind'] == 'none' and stage['failed_case'] is None)
        require(type(stage['cases']) is list and len(stage['cases']) == 1)
        case = stage['cases'][0]
        require(type(case) is dict and set(case) == FULL.CASE_KEYS)
        require(case['name'] == CASE and case['status'] == 'ok')
        require(case['source_sha256'] == SOURCE_SHA256 and case['module_sha256'] == module_hashes[CASE])
        require(type(case['message_count']) is int and case['message_count'] == MESSAGE_COUNT)
        require(type(case['output_size']) is int and 0 < case['output_size'] <= MAX_OUTPUT)
        require(FULL.is_digest(case['output_sha256']))
        client = stage['client_tree']
        require(type(client) is dict and FULL.CLIENT_OUTPUT_KEYS <= set(client))
        FULL.validate_client_probe({k: v for k, v in client.items() if k not in FULL.CLIENT_OUTPUT_KEYS},
                                   SOURCE_SHA256, module_hashes['client_tree'])
        require(client['status'] == 'ok')
        require(all(client[k] == case[k] and type(client[k]) is type(case[k]) for k in FULL.CLIENT_OUTPUT_KEYS))
        outputs = data['outputs']
        require(type(outputs) is list and len(outputs) == 1)
        output = outputs[0]
        require(type(output) is dict and set(output) == {'name', 'size', 'sha256', 'data_b64'})
        require(output['name'] == CASE + '.out' and type(output['size']) is int)
        require(output['size'] == case['output_size'] and output['sha256'] == case['output_sha256'])
        require(type(output['data_b64']) is str)
        payload = base64.b64decode(output['data_b64'], validate=True)
        require(base64.b64encode(payload).decode('ascii') == output['data_b64'])
        require(len(payload) == case['output_size'] and FULL.digest(payload) == case['output_sha256'])
        CONTRACT.validate_output(payload)
        return report, payload
    except TreeError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, RecursionError, FULL.FullError):
        raise TreeError('tree_native_evidence_rejected') from None


def compare_output(root, private, native, input_hashes, *, runner=FULL.bounded_child):
    """A valid measurement is distinct from exact interpreter compatibility."""
    CONTRACT.validate_output(native)
    source = root / SOURCE
    raw = FULL.read_regular(source, FULL.MAX_FILE, nonempty=True)
    require(FULL.digest(raw) == SOURCE_SHA256 == input_hashes[SOURCE], 'tree_source_changed')
    with tempfile.TemporaryDirectory(prefix='tree-cache-', dir=private) as cache:
        code, actual, stderr = runner([sys.executable, '-I', '-B', '-X', 'pycache_prefix=' + cache,
                                      '-c', FULL.EXECUTE_SCRIPT, str(root), str(source), FULL.LINUX_TARGET], root)
    valid = False
    if code == 0 and not stderr:
        try:
            CONTRACT.validate_output(actual)
            valid = True
        except ValueError:
            pass
    matched = valid and actual == native
    return {'schema': 'native-1c-tree-comparison-v1', 'profile': PROFILE,
            'status': 'matched' if matched else 'mismatched' if valid else 'invalid_interpreter_output',
            'acceptance_status': 'accepted' if matched else 'rejected',
            'native_sha256': FULL.digest(native), 'native_size': len(native),
            'interpreter_sha256': FULL.digest(actual), 'interpreter_size': len(actual)}


def staged_files(smoke):
    return {**smoke.STAGED_FILES,
            'scripts/native_1c_bootstrap/full_suite.py': 'bootstrap/full_suite.py',
            'scripts/native_1c_bootstrap/tree_suite.py': 'bootstrap/tree_suite.py',
            'scripts/native_1c_bootstrap/client_probe.bsl': 'bootstrap/client_probe.bsl',
            'scripts/native_1c_tree_fill_contract.py': 'bootstrap/native_1c_tree_fill_contract.py',
            SOURCE: 'scenarios/' + CASE + '.bsl'}


def stage_inputs(root, destination, smoke):
    files = staged_files(smoke)
    require(not destination.exists() and not destination.is_symlink(), 'tree_staging_exists')
    destination.mkdir(mode=0o700)
    hashes = {}
    for source, target in files.items():
        raw = FULL.read_regular(root / source, FULL.MAX_FILE, nonempty=True)
        hashes[source] = FULL.digest(raw)
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(0o444)
    require(hashes[SOURCE] == SOURCE_SHA256, 'tree_source_changed')
    validate_inputs(destination, hashes, smoke)
    return hashes


def validate_inputs(destination, hashes, smoke):
    files = staged_files(smoke)
    require(type(hashes) is dict and set(hashes) == set(files), 'tree_inventory_invalid')
    require(destination.is_dir() and not destination.is_symlink(), 'tree_inventory_invalid')
    directories = {parent.as_posix() for name in files.values() for parent in Path(name).parents
                   if parent.as_posix() != '.'}
    seen = set()
    for path in destination.rglob('*'):
        require(not path.is_symlink(), 'tree_inventory_invalid')
        rel = path.relative_to(destination).as_posix()
        if path.is_dir():
            require(rel in directories, 'tree_inventory_invalid')
        else:
            require(path.is_file() and rel in files.values(), 'tree_inventory_invalid')
            seen.add(rel)
    require(seen == set(files.values()), 'tree_inventory_invalid')
    for source, target in files.items():
        require(FULL.digest(FULL.read_regular(destination / target, FULL.MAX_FILE, nonempty=True)) == hashes[source],
                'tree_staged_source_changed')


def module_hashes(staged, hashes, smoke):
    validate_inputs(staged, hashes, smoke)
    names = ('inject_modules', 'evidence_gates', 'full_suite', 'tree_suite')
    sentinel = object()
    saved = {name: sys.modules.get(name, sentinel) for name in names}
    try:
        for name in names:
            path = staged / 'bootstrap' / (name + '.py')
            module = types.ModuleType(name)
            module.__file__ = str(path)
            sys.modules[name] = module
            exec(compile(FULL.read_regular(path, FULL.MAX_FILE, nonempty=True), str(path), 'exec'), module.__dict__)
        tree = sys.modules['tree_suite']
        require(tree.INPUT_FILES == staged_files(smoke), 'tree_inventory_invalid')
        source = FULL.read_regular(staged / ('scenarios/' + CASE + '.bsl'), FULL.MAX_FILE, nonempty=True)
        template = FULL.read_regular(staged / 'bootstrap/client_probe.bsl', FULL.MAX_FILE, nonempty=True)
        return {CASE: FULL.digest(FULL.generated_module(source)),
                'client_tree': FULL.digest(tree.client_module(source, template))}
    finally:
        for name, value in saved.items():
            if value is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def container_command(staged, hashes, name, nonce, smoke):
    validate_inputs(staged, hashes, smoke)
    require(re.fullmatch('onec-tree-[0-9a-f]{32}', name) and re.fullmatch('[0-9a-f]{32}', nonce))
    require(',' not in str(staged) and staged.is_absolute())
    return ['docker', 'run', '--name', name, '--hostname', 'onec-smoke',
            '--pull', 'never', '--platform', 'linux/amd64', '--network', 'none',
            '--user', '1000:1000', '--read-only', '--no-healthcheck', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--pids-limit', '256',
            '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
            '--ulimit', 'nofile=1024:1024', '--ulimit', 'fsize=67108864:67108864',
            '--ipc', 'private', '--shm-size', '128m', '--log-driver', 'none',
            '--stop-timeout', '10', '--init',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777',
            '--mount', f'type=bind,src={staged},dst=/smoke,readonly',
            '--workdir', '/tmp', '--entrypoint', '/usr/bin/env', smoke.IMAGE,
            '-i', 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME=/tmp/home', 'XDG_RUNTIME_DIR=/tmp/runtime', 'DISPLAY=:99',
            'LANG=ru_RU.UTF-8', 'LC_ALL=ru_RU.UTF-8', 'TZ=Etc/UTC',
            '/bin/bash', '--noprofile', '--norc', '/smoke/probe.sh',
            '--tree-suite', '--invocation-nonce', nonce]


@contextlib.contextmanager
def private_work(temp_root, state):
    manager = tempfile.TemporaryDirectory(prefix='onec-tree-', dir=temp_root)
    try:
        yield manager.name
    finally:
        prior = state['stage']
        state['stage'] = 'private_cleanup'
        manager.cleanup()
        state['stage'] = prior


def run(root, temp_root, *, export_native_outputs=False, failure_state=None):
    """Return only finite metadata after container and private-directory cleanup."""
    failure_state = {} if failure_state is None else failure_state
    failure_state['stage'] = 'credentials'
    smoke = sibling('native_1c_smoke')
    token, actor = os.environ.pop('GHCR_TOKEN', ''), os.environ.pop('GHCR_USER', '')
    require(token and re.fullmatch('[A-Za-z0-9-]{1,39}', actor), 'registry_credentials_missing')
    name, nonce = 'onec-tree-' + uuid.uuid4().hex, uuid.uuid4().hex
    failure_state['stage'] = 'provenance'
    provenance = FULL.repository_provenance(root)
    interpreter = FULL.interpreter_provenance(root)
    host_identity = {p: FULL.digest(FULL.read_regular(root / p, FULL.MAX_FILE, nonempty=True)) for p in ('scripts/native_1c_tree_profile.py', 'scripts/native_1c_tree_fill_contract.py', 'scripts/native_1c_smoke.py', 'scripts/native_1c_full_host.py')}
    goldens = FULL.windows_fingerprints(root)
    result = None
    with private_work(temp_root, failure_state) as directory:
        work = Path(directory).resolve()
        staged = work / 'staged'
        failure_state['stage'] = 'staging'
        hashes = stage_inputs(root, staged, smoke)
        failure_state['stage'] = 'adapter'
        modules = module_hashes(staged, hashes, smoke)
        failure_state['stage'] = 'preflight'
        FULL.verify_client_interpreter(root, staged / 'bootstrap/client_probe.bsl', hashes[FULL.CLIENT_SOURCE])
        auth = work / 'auth'
        auth.mkdir(mode=0o700)
        try:
            env = smoke.docker_environment(auth)
            failure_state['stage'] = 'registry_login'
            smoke.run_silent(['docker', 'login', 'ghcr.io', '--username', actor, '--password-stdin'], env, 60, token.encode())
            token = ''
            failure_state['stage'] = 'image_pull'
            smoke.run_silent(['docker', 'pull', '--platform', 'linux/amd64', smoke.IMAGE], env, 600)
        finally:
            token = ''
            shutil.rmtree(auth)
        clean = work / 'no-auth'
        clean.mkdir(mode=0o700)
        env = smoke.docker_environment(clean)
        failure_state['stage'] = 'image_inspect'
        code, image = smoke.bounded_run(['docker', 'image', 'inspect', '--format', '{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}', smoke.IMAGE], env, 30, 128)
        require(code == 0 and image.strip() == b'linux/amd64|0', 'unexpected_image_platform_or_volumes')
        try:
            failure_state['stage'] = 'container_run'
            code, raw = smoke.bounded_run(container_command(staged, hashes, name, nonce, smoke), env, smoke.FULL_MAX_RUNTIME, MAX_TRANSPORT)
            failure_state['stage'] = 'envelope'
            report, native = validate_envelope(raw, nonce, hashes, modules, smoke.validate_report)
            require(code == 0, 'tree_container_failed')
            del raw
        finally:
            primary_stage = failure_state['stage']
            failure_state['stage'] = 'container_cleanup'
            smoke.run_silent(['docker', 'rm', '--force', name], env, 30)
            cleanup_code, remaining = smoke.bounded_run(['docker', 'ps', '--all', '--filter', 'name=^/' + name + '$', '--format', '{{.Names}}'], env, 30, 128)
            require(cleanup_code == 0 and not remaining.strip(), 'container_cleanup_unverified')
            failure_state['stage'] = primary_stage
        require(all(FULL.digest(FULL.read_regular(root / p, FULL.MAX_FILE, nonempty=True)) == h for p, h in host_identity.items()), 'tree_host_changed')
        failure_state['stage'] = 'comparison'
        comparison = compare_output(root, work, native, hashes)
        failure_state['stage'] = 'final_provenance'
        validate_inputs(staged, hashes, smoke)
        require(all(FULL.digest(FULL.read_regular(root / p, FULL.MAX_FILE, nonempty=True)) == h for p, h in host_identity.items()), 'tree_host_changed')
        require(FULL.repository_provenance(root) == provenance and FULL.interpreter_provenance(root) == interpreter,
                'execution_provenance_changed')
        require(FULL.windows_fingerprints(root) == goldens, 'windows_goldens_changed')
        result = {'schema': 'native-1c-tree-host-v1', 'profile': PROFILE, 'nonce': nonce,
                  'image': smoke.IMAGE, 'platform': 'linux/amd64', 'configured_timezone': 'Etc/UTC',
                  'repository': provenance, 'interpreter': interpreter, 'host_source_sha256': host_identity, 'trusted_input_sha256': hashes,
                  'native_report': report, 'comparison': comparison, 'container_cleanup_verified': True,
                  'native_measurement_accepted': True, 'runtime_parity_accepted': comparison['acceptance_status'] == 'accepted'}
        retained = native if export_native_outputs else None
        del native
    failure_state['stage'] = 'private_cleanup'
    require(not Path(directory).exists(), 'private_cleanup_unverified')
    result['private_payloads_removed'] = True
    require(len(json.dumps(result, separators=(',', ':')).encode()) <= FULL.MAX_REPORT, 'tree_host_report_limit')
    if export_native_outputs:
        artifacts = {CASE + '.out': retained,
                     'provenance.json': (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()}
        result['native_artifact_sha256'] = {name: FULL.digest(data) for name, data in artifacts.items()}
        require(len(json.dumps(result, separators=(',', ':')).encode()) + 1 <= FULL.MAX_REPORT, 'tree_host_report_limit')
        failure_state['stage'] = 'artifact_export'
        export_artifact(root, artifacts)
    require(len(json.dumps(result, separators=(',', ':')).encode()) + 1 <= FULL.MAX_REPORT, 'tree_host_report_limit')
    return result


def export_artifact(root: Path, files: dict[str, bytes]) -> None:
    """Publish one complete directory atomically; Linux only, no replace fallback."""
    if (not sys.platform.startswith("linux") or list(files) != list((CASE + '.out', 'provenance.json'))
            or any(type(value) is not bytes for value in files.values())
            or any(len(files[name]) > MAX_OUTPUT for name in (CASE + '.out', 'provenance.json')[:-1])
            or sum(len(files[name]) for name in (CASE + '.out', 'provenance.json')[:-1]) > MAX_OUTPUT
            or not 0 < len(files["provenance.json"]) <= FULL.MAX_REPORT):
        raise FULL.FullError("native_artifact_export_invalid")
    root_fd = parent_fd = stage_fd = None
    staging = ".tree-outputs-" + uuid.uuid4().hex
    created = promoted = False
    failure = None
    cleanup_failed = False
    try:
        root_fd = FULL._artifact_directory(root)
        try:
            os.mkdir("native-smoke", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        parent_fd = os.open("native-smoke", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        # Early refusal is useful; the atomic rename below also closes the race.
        try:
            os.stat("tree-outputs", dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FULL.FullError("native_artifact_target_exists")
        os.mkdir(staging, mode=0o700, dir_fd=parent_fd)
        created = True
        stage_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        for name in (CASE + '.out', 'provenance.json'):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=stage_fd)
            with os.fdopen(fd, "wb") as stream:
                stream.write(files[name])
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o400)
        if set(os.listdir(stage_fd)) != set((CASE + '.out', 'provenance.json')):
            raise FULL.FullError("native_artifact_files_invalid")
        for name in (CASE + '.out', 'provenance.json'):
            if FULL.read_regular(root / "native-smoke" / staging / name, FULL.MAX_REPORT if name == "provenance.json" else MAX_OUTPUT) != files[name]:
                raise FULL.FullError("native_artifact_files_invalid")
        os.fsync(stage_fd)
        FULL._verify_artifact_directory(root, root_fd)
        FULL._verify_artifact_directory(root / "native-smoke", parent_fd)
        FULL._verify_artifact_directory(root / "native-smoke" / staging, stage_fd)
        FULL._rename_artifact_exclusive(parent_fd, staging, "tree-outputs")
        promoted = True
        # Actions opens visible paths later, not our descriptors. A swapped
        # ancestor or staging path must never produce the upload-ready signal.
        FULL._verify_artifact_directory(root, root_fd)
        FULL._verify_artifact_directory(root / "native-smoke", parent_fd)
        FULL._verify_artifact_directory(root / 'native-smoke/tree-outputs', stage_fd)
        if set(os.listdir(stage_fd)) != set((CASE + '.out', 'provenance.json')):
            raise FULL.FullError("native_artifact_files_invalid")
        for name in (CASE + '.out', 'provenance.json'):
            if FULL.read_regular(root / 'native-smoke/tree-outputs' / name, FULL.MAX_REPORT if name == "provenance.json" else MAX_OUTPUT) != files[name]:
                raise FULL.FullError("native_artifact_files_invalid")
        FULL._verify_artifact_directory(root / "native-smoke", parent_fd)
        FULL._verify_artifact_directory(root / 'native-smoke/tree-outputs', stage_fd)
    except OSError:
        failure = FULL.FullError("native_artifact_export_failed")
    except BaseException as error:
        failure = error
    finally:
        try:
            if failure is not None and created and stage_fd is not None:
                # Remove only our pinned directory's fixed files, never a
                # replacement directory reached through a changed visible path.
                for name in (CASE + '.out', 'provenance.json'):
                    try:
                        os.unlink(name, dir_fd=stage_fd)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        cleanup_failed = True
                try:
                    selected = "tree-outputs" if promoted else staging
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
            failure = FULL.FullError("native_artifact_cleanup_unverified")
        failure.cleanup_error = "native_artifact_cleanup_unverified"
    if failure is not None:
        raise failure from None


FAILURE_STAGES = ('credentials', 'provenance', 'staging', 'adapter', 'preflight', 'registry_login',
                  'image_pull', 'image_inspect', 'container_run', 'envelope', 'container_cleanup',
                  'comparison', 'final_provenance', 'private_cleanup', 'artifact_export')
FAILURE_REASONS = ('tree_native_evidence_rejected', 'tree_report_invalid', 'tree_observation_rejected',
                   'registry_credentials_missing', 'repository_identity_unverified', 'repository_commit_mismatch',
                   'repository_sources_unverified', 'tree_source_changed', 'tree_inventory_invalid',
                   'tree_staged_source_changed', 'docker_command_timeout', 'docker_command_unavailable',
                   'docker_command_failed', 'container_timeout', 'container_output_limit',
                   'container_cleanup_unverified', 'tree_container_failed', 'tree_host_changed',
                   'execution_provenance_changed', 'private_cleanup_unverified', 'unexpected_image_platform_or_volumes',
                   'tree_host_report_limit', 'native_artifact_export_failed', 'native_artifact_target_exists')


def failure_diagnostic(state, error):
    # Exact closed membership only. Unknown strings, including paths and secrets,
    # collapse to one token; never use repr/str output in the public record.
    stage = state.get('stage') if type(state) is dict else None
    stage = stage if type(stage) is str and stage in FAILURE_STAGES else 'unknown'
    reason = str(error)
    reason = reason if reason in FAILURE_REASONS else 'unexpected_failure'
    return {'stage': stage, 'reason': reason}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved-image', action='store_true', required=True)
    parser.add_argument('--export-native-outputs', action='store_true')
    args = parser.parse_args()
    parent = ROOT / 'native-smoke'
    require(not parent.is_symlink(), 'tree_artifact_parent_invalid')
    parent.mkdir(mode=0o700, exist_ok=True)
    require(not (parent / 'tree-report.json').exists(), 'tree_report_exists')
    failure_state = {'stage': 'credentials'}
    try:
        report = run(ROOT, Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())),
                     export_native_outputs=args.export_native_outputs, failure_state=failure_state)
    except Exception as error:
        report = {'schema': 'native-1c-tree-host-v1', 'profile': PROFILE,
                  'status': 'failed', 'native_measurement_accepted': False,
                  'runtime_parity_accepted': False,
                  'failure_diagnostic': failure_diagnostic(failure_state, error)}
        if isinstance(error, TreeError) and hasattr(error, 'native_failure'):
            value = error.native_failure
            require(type(value) is dict and set(value) == {'stage', 'reason', 'case', 'process_stage', 'process_reason'}
                    and value['stage'] == 'tree' and value['reason'] in FULL.FAILURES | {'unsupported_observation'}
                    and value['reason'] != 'none' and value['case'] in (None, CASE)
                    and value['process_stage'] in ('not_checked', 'baseline', 'before_probe', 'after_exit')
                    and value['process_reason'] in ('none', 'unverified', 'native_not_quiet', 'unexpected_processes'))
            report['native_failure'] = value
        if isinstance(error, TreeError) and hasattr(error, 'observation_diagnostic'):
            validate_diagnostic(error.observation_diagnostic)
            report['observation_diagnostic'] = error.observation_diagnostic
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode()
    require(len(raw) <= FULL.MAX_REPORT, 'tree_host_report_limit')
    with (parent / 'tree-report.json').open('xb') as stream:
        stream.write(raw)
    if report.get('native_artifact_sha256') and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('tree_outputs_ready=true\n')
    print('Native tree profile completed.' if report['runtime_parity_accepted'] else 'Native tree profile failed or differs.')
    return 0 if report['runtime_parity_accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

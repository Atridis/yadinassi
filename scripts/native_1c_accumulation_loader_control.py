"""One isolated declaration-only load/redump diagnostic; acceptance is always false."""
from __future__ import annotations
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
from accumulation_loader_control import contract, fixture

ROOT=Path(__file__).resolve().parents[1]
PROFILE = contract.PROFILE
SCHEMA = contract.SCHEMA
MAX_TRANSPORT = contract.MAX_TRANSPORT


def sibling(name):
    path=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location('accumulation_loader_control_host_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


FULL=sibling('native_1c_full_host')
SMOKE=sibling('native_1c_smoke')
DOCKER=sibling('native_1c_docker_lifecycle')


class LoaderControlError(ValueError):pass


def require(condition,reason='accumulation_loader_control_report_invalid'):
    if not condition:raise LoaderControlError(reason)


def staged_files(smoke=SMOKE):
    files = dict(smoke.STAGED_FILES)
    files.pop('scripts/native_1c_smoke_probe.sh')
    files['scripts/native_1c_accumulation_loader_control_probe.sh'] = 'probe.sh'
    files.update({'scripts/native_1c_bootstrap/full_suite.py':'bootstrap/full_suite.py',
        'scripts/native_1c_bootstrap/accumulation_loader_control_suite.py':'bootstrap/accumulation_loader_control_suite.py'})
    for name in ('__init__.py','route.py','fixture.py','observe.bsl','ObjectModule.bsl','Document.xml','AccumulationRegister.xml'):
        files['scripts/accumulation_register_behavior/'+name]='bootstrap/accumulation_register_behavior/'+name
    for name in ('__init__.py','route.py','fixture.py','packet.py','Catalog.xml','SOURCE.json',
                 'generated/setup.json','generated/Catalog.xml','generated/observe.bsl'):
        files['scripts/catalog_object_behavior/'+name]='bootstrap/catalog_object_behavior/'+name
    for name in ('__init__.py', 'contract.py', 'fixture.py'):
        files['scripts/accumulation_loader_control/' + name] = 'bootstrap/accumulation_loader_control/' + name
    return files


def manifest_bytes(smoke=SMOKE):
    raw=(json.dumps(staged_files(smoke),sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    require(len(raw)<=32768,'accumulation_loader_control_inventory_invalid')
    return raw


def stage_inputs(root, destination, smoke):
    files = staged_files(smoke)
    require(not destination.exists() and not destination.is_symlink(), 'accumulation_loader_control_staging_exists')
    # Only approved public source inputs are mounted here; the container runs
    # as UID 1000, which need not be the hosted runner's UID. Private work and
    # registry-auth directories remain 0700 and are never mounted.
    destination.mkdir(mode=0o755)
    destination.chmod(0o755)
    hashes = {}
    for source, target in files.items():
        raw = FULL.read_regular(root / source, FULL.MAX_FILE, nonempty=True)
        hashes[source] = FULL.digest(raw)
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
        # The mount is read-only; launcher copytree copies must remain editable.
        path.chmod(0o644)
    with (destination/contract.MANIFEST).open('xb') as stream:
        stream.write(manifest_bytes(smoke))
    (destination/contract.MANIFEST).chmod(0o644)
    for directory in destination.rglob('*'):
        if directory.is_dir():
            directory.chmod(0o755)
    validate_inputs(destination, hashes, smoke)
    return hashes


def validate_inputs(destination, hashes, smoke):
    files = staged_files(smoke)
    require(type(hashes) is dict and set(hashes) == set(files), 'accumulation_loader_control_inventory_invalid')
    require(destination.is_dir() and not destination.is_symlink(), 'accumulation_loader_control_inventory_invalid')
    directories = {parent.as_posix() for name in files.values() for parent in Path(name).parents
                   if parent.as_posix() != '.'}
    seen = set()
    for path in destination.rglob('*'):
        require(not path.is_symlink(), 'accumulation_loader_control_inventory_invalid')
        rel = path.relative_to(destination).as_posix()
        if path.is_dir():
            require(rel in directories, 'accumulation_loader_control_inventory_invalid')
        else:
            require(path.is_file() and rel in {*files.values(),contract.MANIFEST}, 'accumulation_loader_control_inventory_invalid')
            seen.add(rel)
    require(seen == {*files.values(),contract.MANIFEST}, 'accumulation_loader_control_inventory_invalid')
    require(FULL.read_regular(destination/contract.MANIFEST,32768,nonempty=True)==manifest_bytes(smoke),'accumulation_loader_control_inventory_invalid')
    for source, target in files.items():
        require(FULL.digest(FULL.read_regular(destination / target, FULL.MAX_FILE, nonempty=True)) == hashes[source],
                'accumulation_loader_control_staged_source_changed')


def container_command(staged, hashes, name, nonce, smoke):
    validate_inputs(staged, hashes, smoke)
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) and name == 'onec-accumulation-loader-control-' + nonce)
    require(',' not in str(staged) and staged.is_absolute())
    return ['docker', 'create', '--name', name, '--label', DOCKER.OWNER_LABEL + '=' + nonce,
            '--hostname', 'onec-smoke',
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
            '--accumulation-loader-control', '--invocation-nonce', nonce]


@contextlib.contextmanager
def private_work(temp_root, state):
    manager = tempfile.TemporaryDirectory(prefix='onec-accumulation-loader-control-', dir=temp_root)
    try:
        yield manager.name
    finally:
        prior = state['stage']
        state['stage'] = 'private_cleanup'
        manager.cleanup()
        state['stage'] = prior


def validate_envelope(raw, nonce, hashes, validator=SMOKE.validate_report):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_TRANSPORT)
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) is not None)
    require(type(hashes) is dict and set(hashes) == set(staged_files())
            and all(FULL.is_digest(value) for value in hashes.values()))
    try:
        value = FULL.strict_json(raw, MAX_TRANSPORT)
        require(type(value) is dict and set(value) == {'schema', 'profile', 'nonce', 'report', 'outputs'})
        require(value['schema'] == SCHEMA and value['profile'] == PROFILE and value['nonce'] == nonce)
        require(value['outputs'] == [])  # No raw/native payload export path exists.
        report = validator(json.dumps(value['report'], separators=(',', ':')).encode(), bootstrap=True, full_suite=True)
        stage = report.get('stage3')
        require(type(stage) is dict and set(stage) == contract.STAGE_KEYS)
        require(stage['schema'] == contract.STAGE_SCHEMA and stage['profile'] == PROFILE and stage['nonce'] == nonce)
        require(type(stage['status']) is str and stage['status'] in ('ok', 'failed'))
        require(type(stage['failure_kind']) is str and stage['failure_kind'] in FULL.FAILURES)
        require(type(stage['failure_phase']) is str and stage['failure_phase'] in contract.PHASES)
        require(all(type(stage[key]) is bool for key in contract.FLAGS))
        require(all(stage[key] is False for key in contract.ACCEPTANCE_FLAGS))
        require(report['native_tests_completed'] is False)
        require(type(stage['case_count']) is int and stage['case_count'] == contract.COUNT)
        require(type(stage['completed_case_count']) is int and stage['completed_case_count'] in (0, contract.COUNT))
        require(all(stage[key] is None or FULL.is_digest(stage[key]) for key in contract.HASH_FIELDS))
        require(type(stage['input_sha256']) is dict and stage['input_sha256'] in ({}, hashes))
        require(stage['configuration_validation'] == fixture.VALIDATION_MODE)
        require(fixture.valid_diagnostic(stage['redump_diagnostic']))
        FULL.validate_process_diagnostics(stage['process_diagnostics'])
        require(type(stage['install_diagnostics']) is list and len(stage['install_diagnostics']) <= 2)
        require(all(contract.valid_install_diagnostic(item) for item in stage['install_diagnostics']))
        require(not stage['load_completed'] or stage['entered'])
        require(not stage['redump_completed'] or stage['load_completed'])
        require(not stage['config_verified'] or stage['redump_completed'])
        require(not stage['source_verified'] or stage['config_verified'])
        require(not stage['completed'] or all(stage[key] for key in contract.FLAGS))
        if stage['status'] == 'ok':
            require(report['status'] == 'ok' and all(stage[key] for key in contract.FLAGS))
            require(stage['input_sha256'] == hashes and stage['failure_kind'] == 'none' and stage['failure_phase'] == 'final')
            require(stage['completed_case_count'] == contract.COUNT and all(FULL.is_digest(stage[key]) for key in contract.HASH_FIELDS))
            require(stage['install_diagnostics'] == [])
            require(stage['process_diagnostics']['stage'] == 'after_exit' and stage['process_diagnostics']['reason'] == 'none')
        else:
            require(report['status'] != 'ok' and stage['failure_kind'] != 'none')
            require(not stage['completed'] and stage['completed_case_count'] == 0)
        return report
    except LoaderControlError:
        raise
    except Exception:
        raise LoaderControlError('accumulation_loader_control_report_invalid') from None


def run(root, temp_root, *, failure_state=None):
    """Report only after source checks and both owned cleanup boundaries."""
    state = {} if failure_state is None else failure_state
    state['stage'] = 'credentials'
    token, actor = os.environ.pop('GHCR_TOKEN', ''), os.environ.pop('GHCR_USER', '')
    require(token and re.fullmatch('[A-Za-z0-9-]{1,39}', actor), 'registry_credentials_missing')
    nonce = uuid.uuid4().hex
    name = 'onec-accumulation-loader-control-' + nonce
    state['stage'] = 'provenance'
    provenance = FULL.repository_provenance(root)
    interpreter = FULL.interpreter_provenance(root)
    hosts = ('scripts/native_1c_accumulation_loader_control.py', 'scripts/native_1c_smoke.py',
             'scripts/native_1c_full_host.py', 'scripts/native_1c_docker_lifecycle.py')
    identity = {path: FULL.digest(FULL.read_regular(root / path, FULL.MAX_FILE, nonempty=True)) for path in hosts}
    goldens = FULL.windows_fingerprints(root)
    with private_work(temp_root, state) as directory:
        work = Path(directory).resolve()
        staged = work / 'staged'
        state['stage'] = 'staging'
        hashes = stage_inputs(root, staged, SMOKE)
        state['stage'] = 'adapter'
        fixture.declarations()
        auth = work / 'auth'
        auth.mkdir(mode=0o700)
        try:
            env = SMOKE.docker_environment(auth)
            state['stage'] = 'registry_login'
            SMOKE.run_silent(['docker', 'login', 'ghcr.io', '--username', actor, '--password-stdin'], env, 60, token.encode())
            token = ''
            state['stage'] = 'image_pull'
            SMOKE.run_silent(['docker', 'pull', '--platform', 'linux/amd64', SMOKE.IMAGE], env, 600)
        finally:
            token = ''
            shutil.rmtree(auth)
        clean = work / 'no-auth'
        clean.mkdir(mode=0o700)
        env = SMOKE.docker_environment(clean)
        code, raw = DOCKER.run_owned(container_command(staged, hashes, name, nonce, SMOKE), env,
            name=name, nonce=nonce, image=SMOKE.IMAGE, seconds=SMOKE.FULL_MAX_RUNTIME,
            output_limit=MAX_TRANSPORT, state=state)
        state['stage'] = 'envelope'
        report = validate_envelope(raw, nonce, hashes)
        del raw
        passed = report['status'] == 'ok' and report['stage3']['status'] == 'ok'
        if passed:
            require(code == 0, 'accumulation_loader_control_container_failed')
        state['stage'] = 'final_provenance'
        validate_inputs(staged, hashes, SMOKE)
        require(all(FULL.digest(FULL.read_regular(root / path, FULL.MAX_FILE, nonempty=True)) == digest
                    for path, digest in hashes.items()), 'accumulation_loader_control_source_changed')
        require(all(FULL.digest(FULL.read_regular(root / path, FULL.MAX_FILE, nonempty=True)) == digest
                    for path, digest in identity.items()), 'accumulation_loader_control_host_changed')
        require(FULL.repository_provenance(root) == provenance and FULL.interpreter_provenance(root) == interpreter,
                'execution_provenance_changed')
        require(FULL.windows_fingerprints(root) == goldens, 'windows_goldens_changed')
        result = dict(schema=contract.HOST_SCHEMA, profile=PROFILE, nonce=nonce,
            status='ok' if passed else 'failed', diagnostic_control_passed=passed,
            load_completed=report['stage3']['load_completed'], redump_verified=report['stage3']['config_verified'],
            case_count=contract.COUNT, completed_case_count=report['stage3']['completed_case_count'],
            image=SMOKE.IMAGE, platform='linux/amd64', configured_timezone='Etc/UTC',
            repository=provenance, interpreter=interpreter, host_source_sha256=identity,
            trusted_input_sha256=hashes, native_report=report, comparison=None,
            container_cleanup_verified=True, docker_cli_reap_verified=True,
            **{key: False for key in contract.ACCEPTANCE_FLAGS})
    state['stage'] = 'private_cleanup'
    require(not Path(directory).exists(), 'private_cleanup_unverified')
    result['private_payloads_removed'] = True
    require(len(json.dumps(result, separators=(',', ':')).encode()) + 1 <= FULL.MAX_REPORT,
            'accumulation_loader_control_host_report_limit')
    return result


FAILURE_STAGES = ('credentials', 'provenance', 'staging', 'adapter', 'registry_login', 'image_pull',
    'image_inspect', 'container_create', 'container_ownership', 'container_start', 'container_exit',
    'envelope', 'container_cleanup', 'final_provenance', 'private_cleanup')
FAILURE_REASONS = ('accumulation_loader_control_report_invalid', 'registry_credentials_missing',
    'accumulation_loader_control_source_changed', 'accumulation_loader_control_inventory_invalid',
    'accumulation_loader_control_staged_source_changed', 'docker_command_timeout', 'docker_command_unavailable',
    'docker_command_failed', 'container_timeout', 'container_output_limit', 'container_cleanup_unverified',
    'accumulation_loader_control_container_failed', 'accumulation_loader_control_host_changed',
    'execution_provenance_changed', 'private_cleanup_unverified', 'unexpected_image_platform_or_volumes',
    'accumulation_loader_control_host_report_limit', 'windows_goldens_changed', *DOCKER.FAILURE_CODES)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved-image', action='store_true', required=True)
    parser.parse_args()
    parent = ROOT / 'native-smoke'
    require(not parent.is_symlink())
    parent.mkdir(mode=0o700, exist_ok=True)
    target = parent / 'accumulation-loader-control.json'
    require(not target.exists() and not target.is_symlink())
    state = {'stage': 'credentials'}
    try:
        report = run(ROOT, Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())), failure_state=state)
    except Exception as error:
        reason = str(error)
        report = dict(schema=contract.HOST_SCHEMA, profile=PROFILE, status='failed',
            diagnostic_control_passed=False, load_completed=None, redump_verified=None,
            case_count=contract.COUNT, completed_case_count=0,
            failure_diagnostic=dict(stage=state['stage'] if state.get('stage') in FAILURE_STAGES else 'unknown',
                reason=reason if reason in FAILURE_REASONS else 'unexpected_failure'),
            **{key: False for key in contract.ACCEPTANCE_FLAGS})
        if isinstance(error, DOCKER.LifecycleError):
            report.update(docker_cli_reap_verified=error.cli_reap_verified,
                          container_cleanup_verified=error.container_cleanup_verified)
            if error.cleanup_error is not None:
                report['cleanup_error'] = error.cleanup_error
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode()
    require(len(raw) <= FULL.MAX_REPORT)
    with target.open('xb') as stream:
        stream.write(raw)
    passed = report['diagnostic_control_passed']
    print('Loader diagnostic passed; no semantic or runtime parity accepted.' if passed
          else 'Loader diagnostic failed; no semantic or runtime parity accepted.')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

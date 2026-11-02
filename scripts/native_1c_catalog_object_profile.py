"""One owned official-XML CatalogObject acquisition and isolated SQLite replay."""
from __future__ import annotations
import base64
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
from catalog_object_behavior import route, fixture
MAX_OUTPUT=route.MAX_OUTPUT
SOURCE_SHA256=fixture.ASSET_HASHES['generated/observe.bsl']

ROOT=Path(__file__).resolve().parents[1]
PROFILE='catalog-object-behavior-v1'
SCHEMA='native-1c-catalog-object-v1'
STAGE_SCHEMA='native-1c-catalog-object-stage-v1'
MAX_TRANSPORT=65536
SOURCE='scripts/catalog_object_behavior/generated/observe.bsl'
CASE='catalog-object'
ARTIFACT='catalog-object'


def sibling(name):
    path=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location('catalog_object_host_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


FULL=sibling('native_1c_full_host')
SMOKE=sibling('native_1c_smoke')


class CatalogObjectError(ValueError):pass


def require(condition,reason='catalog_object_report_invalid'):
    if not condition:raise CatalogObjectError(reason)


def staged_files(smoke=SMOKE):
    return {**smoke.STAGED_FILES,
            'scripts/native_1c_bootstrap/full_suite.py':'bootstrap/full_suite.py',
            'scripts/native_1c_bootstrap/catalog_object_suite.py':'bootstrap/catalog_object_suite.py',
            **{'scripts/catalog_object_behavior/'+name:'bootstrap/catalog_object_behavior/'+name
               for name in ('__init__.py','route.py','fixture.py','packet.py','Catalog.xml','SOURCE.json',
                            'generated/setup.json','generated/Catalog.xml','generated/observe.bsl')}}


def manifest_bytes(smoke=SMOKE):
    raw=(json.dumps(staged_files(smoke),sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    require(len(raw)<=32768,'catalog_object_inventory_invalid')
    return raw


def stage_inputs(root, destination, smoke):
    files = staged_files(smoke)
    require(not destination.exists() and not destination.is_symlink(), 'catalog_object_staging_exists')
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
    with (destination/'catalog-inputs.json').open('xb') as stream:
        stream.write(manifest_bytes(smoke))
    (destination/'catalog-inputs.json').chmod(0o644)
    for directory in destination.rglob('*'):
        if directory.is_dir():
            directory.chmod(0o755)
    require(hashes[SOURCE] == SOURCE_SHA256, 'catalog_object_source_changed')
    validate_inputs(destination, hashes, smoke)
    return hashes


def validate_inputs(destination, hashes, smoke):
    files = staged_files(smoke)
    require(type(hashes) is dict and set(hashes) == set(files), 'catalog_object_inventory_invalid')
    require(destination.is_dir() and not destination.is_symlink(), 'catalog_object_inventory_invalid')
    directories = {parent.as_posix() for name in files.values() for parent in Path(name).parents
                   if parent.as_posix() != '.'}
    seen = set()
    for path in destination.rglob('*'):
        require(not path.is_symlink(), 'catalog_object_inventory_invalid')
        rel = path.relative_to(destination).as_posix()
        if path.is_dir():
            require(rel in directories, 'catalog_object_inventory_invalid')
        else:
            require(path.is_file() and rel in {*files.values(),'catalog-inputs.json'}, 'catalog_object_inventory_invalid')
            seen.add(rel)
    require(seen == {*files.values(),'catalog-inputs.json'}, 'catalog_object_inventory_invalid')
    require(FULL.read_regular(destination/'catalog-inputs.json',32768,nonempty=True)==manifest_bytes(smoke),'catalog_object_inventory_invalid')
    for source, target in files.items():
        require(FULL.digest(FULL.read_regular(destination / target, FULL.MAX_FILE, nonempty=True)) == hashes[source],
                'catalog_object_staged_source_changed')


def container_command(staged, hashes, name, nonce, smoke):
    validate_inputs(staged, hashes, smoke)
    require(re.fullmatch('onec-catalog-object-[0-9a-f]{32}', name) and re.fullmatch('[0-9a-f]{32}', nonce))
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
            '--catalog-object-suite', '--invocation-nonce', nonce]


@contextlib.contextmanager
def private_work(temp_root, state):
    manager = tempfile.TemporaryDirectory(prefix='onec-catalog-object-', dir=temp_root)
    try:
        yield manager.name
    finally:
        prior = state['stage']
        state['stage'] = 'private_cleanup'
        manager.cleanup()
        state['stage'] = prior


def export_artifact(root: Path, files: dict[str, bytes]) -> None:
    """Publish one complete directory atomically; Linux only, no replace fallback."""
    if (not sys.platform.startswith("linux") or list(files) != list((CASE + '.out', 'provenance.json'))
            or any(type(value) is not bytes for value in files.values())
            or any(len(files[name]) > MAX_OUTPUT for name in (CASE + '.out', 'provenance.json')[:-1])
            or sum(len(files[name]) for name in (CASE + '.out', 'provenance.json')[:-1]) > MAX_OUTPUT
            or not 0 < len(files["provenance.json"]) <= FULL.MAX_REPORT):
        raise FULL.FullError("native_artifact_export_invalid")
    root_fd = parent_fd = stage_fd = None
    staging = '.' + ARTIFACT + '-outputs-' + uuid.uuid4().hex
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
            os.stat(ARTIFACT + '-outputs', dir_fd=parent_fd, follow_symlinks=False)
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
        FULL._rename_artifact_exclusive(parent_fd, staging, ARTIFACT + '-outputs')
        promoted = True
        # Actions opens visible paths later, not our descriptors. A swapped
        # ancestor or staging path must never produce the upload-ready signal.
        FULL._verify_artifact_directory(root, root_fd)
        FULL._verify_artifact_directory(root / "native-smoke", parent_fd)
        FULL._verify_artifact_directory(root / 'native-smoke' / (ARTIFACT + '-outputs'), stage_fd)
        if set(os.listdir(stage_fd)) != set((CASE + '.out', 'provenance.json')):
            raise FULL.FullError("native_artifact_files_invalid")
        for name in (CASE + '.out', 'provenance.json'):
            if FULL.read_regular(root / 'native-smoke' / (ARTIFACT + '-outputs') / name, FULL.MAX_REPORT if name == "provenance.json" else MAX_OUTPUT) != files[name]:
                raise FULL.FullError("native_artifact_files_invalid")
        FULL._verify_artifact_directory(root / "native-smoke", parent_fd)
        FULL._verify_artifact_directory(root / 'native-smoke' / (ARTIFACT + '-outputs'), stage_fd)
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
                    selected = ARTIFACT + '-outputs' if promoted else staging
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


PHASES=('prerequisites','inputs','install','build','redump','enterprise','markers','final')
FLAGS={'entered','completed','process_exited','quiet','witness_verified','config_verified'}
HASH_FIELDS={'source_sha256','module_sha256','module_verified_sha256','output_sha256'}
STAGE_KEYS=FLAGS|HASH_FIELDS|{'schema','profile','nonce','status','failure_kind','failure_phase',
    'input_sha256','output_size','record_count','process_diagnostics'}


def validate_envelope(raw,nonce,hashes,validator=SMOKE.validate_report):
    require(type(raw) is bytes and 0<len(raw)<=MAX_TRANSPORT)
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}',nonce) is not None)
    require(type(hashes) is dict and set(hashes)==set(staged_files()) and all(FULL.is_digest(v) for v in hashes.values()))
    try:
        value=FULL.strict_json(raw,MAX_TRANSPORT)
        require(type(value) is dict and set(value)=={'schema','profile','nonce','report','outputs'})
        require(value['schema']==SCHEMA and value['profile']==PROFILE and value['nonce']==nonce)
        report=validator(json.dumps(value['report'],separators=(',',':')).encode(),bootstrap=True,full_suite=True)
        stage=report.get('stage3')
        require(type(stage) is dict and set(stage)==STAGE_KEYS)
        require(stage['schema']==STAGE_SCHEMA and stage['profile']==PROFILE and stage['nonce']==nonce)
        require(type(stage['status']) is str and stage['status'] in ('ok','failed','not_started'))
        require(type(stage['failure_kind']) is str and stage['failure_kind'] in FULL.FAILURES|{'unsupported_observation'})
        require(type(stage['failure_phase']) is str and stage['failure_phase'] in PHASES)
        require(all(type(stage[k]) is bool for k in FLAGS))
        require(all(stage[k] is None or FULL.is_digest(stage[k]) for k in HASH_FIELDS))
        require(stage['output_size'] is None or type(stage['output_size']) is int and 0<stage['output_size']<=MAX_OUTPUT)
        require(stage['record_count'] is None or type(stage['record_count']) is int and stage['record_count']==24)
        FULL.validate_process_diagnostics(stage['process_diagnostics'])
        require(type(stage['input_sha256']) is dict and stage['input_sha256'] in ({},hashes))
        if stage['status']!='ok':
            require(report['native_tests_completed'] is False and value['outputs']==[])
            require(report['status']!='ok' and stage['failure_kind']!='none')
            error=CatalogObjectError('catalog_object_native_failed')
            error.validated_report=report
            error.native_failure={key:stage[key] for key in ('failure_kind','failure_phase','entered','completed','process_exited','quiet')}
            raise error
        require(stage['input_sha256']==hashes and stage['failure_kind']=='none' and stage['failure_phase']=='final')
        require(report['status']=='ok' and report['native_tests_completed'] is True and all(stage[k] for k in FLAGS))
        require(stage['source_sha256']==SOURCE_SHA256==hashes[SOURCE])
        module=FULL.digest(FULL.generated_module(route.program(fixture.load_saved()[0],nonce)))
        require(stage['module_sha256']==stage['module_verified_sha256']==module)
        require(stage['process_diagnostics']['stage']=='after_exit' and stage['process_diagnostics']['reason']=='none')
        require(type(value['outputs']) is list and len(value['outputs'])==1)
        item=value['outputs'][0]
        require(type(item) is dict and set(item)=={'name','size','sha256','data_b64'})
        require(item['name']=='catalog-object.out' and type(item['size']) is int and 0<item['size']<=MAX_OUTPUT)
        require(type(item['data_b64']) is str and len(item['data_b64'])<=4*((MAX_OUTPUT+2)//3))
        data=base64.b64decode(item['data_b64'],validate=True)
        require(base64.b64encode(data).decode()==item['data_b64'])
        require(len(data)==item['size']==stage['output_size'] and FULL.digest(data)==item['sha256']==stage['output_sha256'])
        parse_output(data)
        require(stage['record_count']==24)
        return report,data
    except CatalogObjectError:raise
    except Exception:raise CatalogObjectError('catalog_object_report_invalid') from None


def parse_output(raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT)
    values=FULL.strict_json(raw,MAX_OUTPUT)
    require(route.canonical(values)==raw)
    return values


EXECUTE_SCRIPT='''import sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'scripts'))
from catalog_object_behavior.replay import replay
from catalog_object_behavior.route import canonical
sys.stdout.buffer.write(canonical(replay()))
'''


def compare_output(root,private,native,hashes,runner=FULL.bounded_child):
    require(FULL.digest(FULL.read_regular(root/SOURCE,FULL.MAX_FILE,nonempty=True))==SOURCE_SHA256==hashes[SOURCE],'catalog_object_source_changed')
    parse_output(native)
    with tempfile.TemporaryDirectory(prefix='catalog-object-cache-',dir=private) as cache:
        code,actual,stderr=runner([sys.executable,'-I','-B','-X','pycache_prefix='+cache,'-c',EXECUTE_SCRIPT,str(root)],root)
    valid=False
    if code==0 and not stderr:
        try:parse_output(actual);valid=True
        except ValueError:pass
    matched=valid and actual==native
    return {'schema':'native-1c-catalog-object-comparison-v1','profile':PROFILE,
            'scope':'owned-catalog-object-logical-reference-model',
            'metadata_import_parity_claimed':False,
            'status':'matched' if matched else 'mismatched' if valid else 'invalid_interpreter_output',
            'acceptance_status':'accepted' if matched else 'rejected',
            'native_sha256':FULL.digest(native),'native_size':len(native),
            'interpreter_sha256':FULL.digest(actual),'interpreter_size':len(actual)}


def run(root,temp_root,*,export_native_outputs=False,failure_state=None):
    """Single authorized image; report only after both owned cleanup boundaries."""
    state={} if failure_state is None else failure_state
    state['stage']='credentials'
    token,actor=os.environ.pop('GHCR_TOKEN',''),os.environ.pop('GHCR_USER','')
    require(token and re.fullmatch('[A-Za-z0-9-]{1,39}',actor),'registry_credentials_missing')
    name,nonce='onec-catalog-object-'+uuid.uuid4().hex,uuid.uuid4().hex
    state['stage']='provenance'
    provenance=FULL.repository_provenance(root);interpreter=FULL.interpreter_provenance(root)
    hosts=('scripts/native_1c_catalog_object_profile.py','scripts/native_1c_smoke.py','scripts/native_1c_full_host.py','scripts/catalog_object_behavior/replay.py')
    identity={p:FULL.digest(FULL.read_regular(root/p,FULL.MAX_FILE,nonempty=True)) for p in hosts}
    goldens=FULL.windows_fingerprints(root)
    with private_work(temp_root,state) as directory:
        work=Path(directory).resolve();staged=work/'staged'
        state['stage']='staging';hashes=stage_inputs(root,staged,SMOKE)
        # The fixed source replay is bounded separately; no renderer code enters.
        state['stage']='adapter'
        require(len(route.program(fixture.load_saved()[0],nonce))<=8192,'catalog_object_source_changed')
        auth=work/'auth';auth.mkdir(mode=0o700)
        try:
            env=SMOKE.docker_environment(auth);state['stage']='registry_login'
            SMOKE.run_silent(['docker','login','ghcr.io','--username',actor,'--password-stdin'],env,60,token.encode())
            token='';state['stage']='image_pull'
            SMOKE.run_silent(['docker','pull','--platform','linux/amd64',SMOKE.IMAGE],env,600)
        finally:
            token='';shutil.rmtree(auth)
        clean=work/'no-auth';clean.mkdir(mode=0o700);env=SMOKE.docker_environment(clean)
        state['stage']='image_inspect'
        code,image=SMOKE.bounded_run(['docker','image','inspect','--format','{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}',SMOKE.IMAGE],env,30,128)
        require(code==0 and image.strip()==b'linux/amd64|0','unexpected_image_platform_or_volumes')
        native_failure=None
        try:
            state['stage']='container_run'
            code,raw=SMOKE.bounded_run(container_command(staged,hashes,name,nonce,SMOKE),env,SMOKE.FULL_MAX_RUNTIME,MAX_TRANSPORT)
            state['stage']='envelope'
            try:
                report,native=validate_envelope(raw,nonce,hashes)
            except CatalogObjectError as error:
                if not hasattr(error,'validated_report'):raise
                native_failure=error.native_failure
                report=error.validated_report
                native=None
            if native_failure is None:require(code==0,'catalog_object_container_failed')
            del raw
        finally:
            prior=state['stage'];state['stage']='container_cleanup'
            SMOKE.run_silent(['docker','rm','--force',name],env,30)
            code,remaining=SMOKE.bounded_run(['docker','ps','--all','--filter','name=^/'+name+'$','--format','{{.Names}}'],env,30,128)
            require(code==0 and not remaining.strip(),'container_cleanup_unverified');state['stage']=prior
        state['stage']='comparison'
        comparison=compare_output(root,work,native,hashes) if native_failure is None else None
        state['stage']='final_provenance';validate_inputs(staged,hashes,SMOKE)
        require(all(FULL.digest(FULL.read_regular(root/p,FULL.MAX_FILE,nonempty=True))==h for p,h in hashes.items()),'catalog_object_source_changed')
        require(all(FULL.digest(FULL.read_regular(root/p,FULL.MAX_FILE,nonempty=True))==h for p,h in identity.items()),'catalog_object_host_changed')
        require(FULL.repository_provenance(root)==provenance and FULL.interpreter_provenance(root)==interpreter,'execution_provenance_changed')
        require(FULL.windows_fingerprints(root)==goldens,'windows_goldens_changed')
        result={'schema':'native-1c-catalog-object-host-v1','profile':PROFILE,'nonce':nonce,
                'image':SMOKE.IMAGE,'platform':'linux/amd64','configured_timezone':'Etc/UTC',
                'repository':provenance,'interpreter':interpreter,'host_source_sha256':identity,
                'trusted_input_sha256':hashes,'native_report':report,'comparison':comparison,
                'container_cleanup_verified':True,'native_measurement_accepted':native_failure is None,
                'runtime_parity_accepted':native_failure is None and comparison['acceptance_status']=='accepted'}
        if native_failure is not None:
            result.update(status='failed',native_failure=native_failure,
                failure_diagnostic={'stage':'envelope','reason':'catalog_object_native_failed'})
        retained=native if export_native_outputs else None;del native
    state['stage']='private_cleanup';require(not Path(directory).exists(),'private_cleanup_unverified')
    result['private_payloads_removed']=True
    require(len(json.dumps(result,separators=(',',':')).encode())<=FULL.MAX_REPORT,'catalog_object_host_report_limit')
    if export_native_outputs and native_failure is None:
        artifacts={'catalog-object.out':retained,'provenance.json':(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()}
        result['native_artifact_sha256']={name:FULL.digest(data) for name,data in artifacts.items()}
        state['stage']='artifact_export';export_artifact(root,artifacts)
    require(len(json.dumps(result,separators=(',',':')).encode())+1<=FULL.MAX_REPORT,'catalog_object_host_report_limit')
    return result


FAILURE_STAGES=('credentials','provenance','staging','adapter','registry_login','image_pull','image_inspect',
                'container_run','envelope','container_cleanup','comparison','final_provenance','private_cleanup','artifact_export')
FAILURE_REASONS=('catalog_object_report_invalid','catalog_object_native_failed','registry_credentials_missing','catalog_object_source_changed',
    'catalog_object_inventory_invalid','catalog_object_staged_source_changed','docker_command_timeout','docker_command_unavailable',
    'docker_command_failed','container_timeout','container_output_limit','container_cleanup_unverified',
    'catalog_object_container_failed','catalog_object_host_changed','execution_provenance_changed','private_cleanup_unverified',
    'unexpected_image_platform_or_volumes','catalog_object_host_report_limit','native_artifact_export_failed',
    'native_artifact_target_exists','windows_goldens_changed')


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved-image',action='store_true',required=True)
    parser.add_argument('--export-native-outputs',action='store_true');args=parser.parse_args()
    parent=ROOT/'native-smoke';require(not parent.is_symlink(),'catalog_object_report_invalid');parent.mkdir(mode=0o700,exist_ok=True)
    target=parent/'catalog-object.json';require(not target.exists() and not target.is_symlink())
    state={'stage':'credentials'}
    try:report=run(ROOT,Path(os.environ.get('RUNNER_TEMP',tempfile.gettempdir())),export_native_outputs=args.export_native_outputs,failure_state=state)
    except Exception as error:
        reason=str(error)
        report={'schema':'native-1c-catalog-object-host-v1','profile':PROFILE,'status':'failed',
                'native_measurement_accepted':False,'runtime_parity_accepted':False,
                'failure_diagnostic':{'stage':state['stage'] if state.get('stage') in FAILURE_STAGES else 'unknown',
                                      'reason':reason if reason in FAILURE_REASONS else 'unexpected_failure'}}
        # Unverified cleanup or provenance failures deliberately retain no native evidence.
    raw=(json.dumps(report,sort_keys=True,separators=(',',':'))+'\n').encode()
    require(len(raw)<=FULL.MAX_REPORT)
    with target.open('xb') as stream:stream.write(raw)
    if report.get('native_artifact_sha256') and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as stream:stream.write('catalog_object_outputs_ready=true\n')
    accepted=report['runtime_parity_accepted']
    print('CatalogObject measurement accepted.' if accepted else 'CatalogObject measurement failed or differs.')
    return 0 if accepted else 1


if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Explicit closed Metadata public-runtime CLI; no caller database or source input.

Stdout is only the validated bounded JSON report. Native files remain in tmpfs.
The Docker confinement/auth/cleanup contract matches native_1c_db_oracle.py.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import uuid
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/native_1c_db_oracle'))
sys.path.insert(0,str(ROOT/'yadinassi/storage'))
import native_1c_smoke as smoke
import protocol
from protocol import require, IMAGE
from snapshots import OracleError
import metadata_catalog_runtime_inputs as inputs
import metadata_catalog_runtime_report as policy


def provenance():
    try: repository=smoke.FULL.repository_provenance(ROOT)
    except (smoke.FULL.FullError,OSError):raise OracleError('provenance_mismatch') from None
    return dict(commit=repository['commit'],tree=repository['tree'],sources=inputs.source_hashes(ROOT),
        image=IMAGE,platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')


def container_command(staged,name,nonce):
    require(type(name) is str and re.fullmatch('onec-db-oracle-[0-9a-f]{32}',name) is not None,'invalid_input')
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}',nonce) is not None,'invalid_input')
    require(staged.is_dir() and not staged.is_symlink() and ',' not in str(staged),'invalid_input')
    inputs.verify_inputs(staged,nonce)
    return ['docker','run','--name',name,'--hostname','onec-db-oracle',
        '--pull','never','--platform','linux/amd64','--network','none',
        '--user','1000:1000','--read-only','--no-healthcheck','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--pids-limit','256',
        '--memory','2g','--memory-swap','2g','--cpus','2',
        '--ulimit','nofile=1024:1024','--ulimit','fsize=67108864:67108864',
        '--ipc','private','--shm-size','128m','--log-driver','none','--stop-timeout','10','--init',
        '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777',
        '--mount',f'type=bind,src={staged.resolve()},dst=/oracle,readonly',
        '--workdir','/tmp','--entrypoint','/usr/bin/env',IMAGE,'-i',
        'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'HOME=/tmp/onec-db-oracle/home','TMPDIR=/tmp/onec-db-oracle/temp','XDG_RUNTIME_DIR=/tmp/runtime','DISPLAY=:99',
        'LANG=ru_RU.UTF-8','LC_ALL=ru_RU.UTF-8','TZ=Etc/UTC',
        'python3','-I','-S','-B','/oracle/metadata_catalog_runtime_run.py','--invocation-nonce',nonce]


def fail(report,kind,stage):
    value=report['lifecycle']
    value.pop('rejected_basename',None);value.pop('failure_context',None)
    if not (stage=='cleanup' and value['status']=='failed'):
        value.update(status='failed',failed_stage=stage,failure_kind=kind,accepted=False)
    entry=value['stages'][protocol.STAGES.index(stage)]
    entry['status']='failed'
    entry['checks']=({k:value['cleanup'][k] for k in protocol.CHECKS[stage]} if stage=='cleanup'
                     else {k:False for k in protocol.CHECKS[stage]})
    value['artifacts']=[]


def run_oracle(temp_root):
    # Scrub credential variables before git or any other subprocess.
    token=os.environ.pop('GHCR_TOKEN','');actor=os.environ.pop('GHCR_USER','')
    nonce=uuid.uuid4().hex;name='onec-db-oracle-'+uuid.uuid4().hex
    identity=provenance();report=policy.empty_report(nonce,identity.copy())
    work_name=None;attempted=False;removed=True;validated=False;primary=None
    try:
        with tempfile.TemporaryDirectory(prefix='onec-db-oracle-',dir=temp_root) as work_name:
            work=Path(work_name).resolve();staged=work/'inputs'
            inputs.stage_inputs(ROOT,staged,nonce,identity)
            require(bool(token) and re.fullmatch('[A-Za-z0-9-]{1,39}',actor) is not None,'registry_credentials_missing')
            auth=work/'auth';auth.mkdir(mode=0o700)
            try:
                smoke.run_silent(['docker','login','ghcr.io','--username',actor,'--password-stdin'],
                    smoke.docker_environment(auth),60,token.encode())
                token=''
                smoke.run_silent(['docker','pull','--platform','linux/amd64',IMAGE],smoke.docker_environment(auth),600)
            finally:
                token='';shutil.rmtree(auth)
            clean=work/'no-auth';clean.mkdir(mode=0o700);env=smoke.docker_environment(clean)
            code,raw=smoke.bounded_run(['docker','image','inspect','--format',
                '{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}',IMAGE],env,30,128)
            require(code==0 and raw.strip()==b'linux/amd64|0','container_unavailable')
            try:
                attempted=True;removed=False
                code,raw=smoke.bounded_run(container_command(staged,name,nonce),env,2400,policy.MAX_REPORT_BYTES)
                report=policy.validate_report(raw,nonce=nonce,provenance=identity)
                validated=True
                require((code==0)==(report['lifecycle']['status']=='ok'),'transport_invalid')
            finally:
                try:
                    smoke.run_silent(['docker','rm','--force',name],env,30)
                    code,raw=smoke.bounded_run(['docker','ps','--all','--filter',
                        'name=^/'+name+'$','--format','{{.Names}}'],env,30,128)
                    removed=code==0 and not raw.strip()
                except smoke.SmokeError:removed=False
            require(provenance()==identity,'provenance_mismatch')
    except OracleError as error:primary=error.kind
    except smoke.SmokeError as error:primary='timeout' if 'timeout' in str(error) else 'container_unavailable'
    except BaseException:primary='unexpected_failure'
    finally:token=''
    private_removed=work_name is not None and not Path(work_name).exists()
    if primary:
        if not validated:report=policy.empty_report(nonce,identity.copy())
        fail(report,primary,'cleanup' if validated else 'preflight')
    lifecycle=report['lifecycle']
    if not attempted or (removed and not validated):
        lifecycle['cleanup'].update(native_processes_stopped=True,raw_files_removed=True)
    lifecycle['cleanup'].update(container_removed=removed,private_staging_removed=private_removed)
    if not removed or not private_removed:fail(report,'cleanup_unverified','cleanup')
    elif not attempted or not validated:
        entry=lifecycle['stages'][-1];entry['status']='ok';entry['checks']={k:True for k in protocol.CHECKS['cleanup']}
    if not all(lifecycle['cleanup'].values()):
        lifecycle.pop('rejected_basename',None);lifecycle.pop('failure_context',None)
        report['states']=[];report['verdict']='not_established'
        report['runtime_readbacks']=[]
    lifecycle['accepted']=lifecycle['status']=='ok' and all(lifecycle['cleanup'].values())
    policy.validate_report(policy.encode_report(report),nonce=nonce,provenance=identity,final=True)
    return report


OUTPUT=Path('native-db-oracle/metadata-catalog-runtime.json')


def export_report(raw, root_identity):
    """One fixed exclusive descriptor-relative artifact, after validated cleanup."""
    require(type(raw) is bytes and len(raw)+1<=policy.MAX_REPORT_BYTES,'artifact_limit')
    require(os.open in os.supports_dir_fd and hasattr(os,'O_NOFOLLOW')
            and hasattr(os,'O_DIRECTORY'),'unsupported_platform_command')
    root_fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent_fd=None
    try:
        info=os.fstat(root_fd)
        require((info.st_dev,info.st_ino)==root_identity,'provenance_mismatch')
        try:os.mkdir(OUTPUT.parent.name,0o700,dir_fd=root_fd)
        except FileExistsError:pass
        parent_fd=os.open(OUTPUT.parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        parent_info=os.fstat(parent_fd)
        require(not os.listdir(parent_fd),'stale_evidence')
        target=os.open(OUTPUT.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent_fd)
        with os.fdopen(target,'wb') as stream:
            stream.write(raw+b'\n');stream.flush();os.fsync(stream.fileno())
            written=os.fstat(stream.fileno())
            require(stat.S_ISREG(written.st_mode) and written.st_nlink==1
                    and written.st_size==len(raw)+1,'transport_invalid')
        current=os.stat(OUTPUT.parent.name,dir_fd=root_fd,follow_symlinks=False)
        require((current.st_dev,current.st_ino)==(parent_info.st_dev,parent_info.st_ino),'provenance_mismatch')
    finally:
        if parent_fd is not None:os.close(parent_fd)
        os.close(root_fd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--run',action='store_true',required=True)
    parser.add_argument('--ci-report',action='store_true',help='Export only the fixed validated CI artifact')
    args=parser.parse_args(argv)
    try:
        root_stat=ROOT.stat();root_identity=(root_stat.st_dev,root_stat.st_ino)
        report=run_oracle(Path(tempfile.gettempdir()))
        raw=policy.encode_report(report)
        if args.ci_report:
            export_report(raw,root_identity)
            if 'GITHUB_OUTPUT' in os.environ:
                with open(os.environ['GITHUB_OUTPUT'],'a',encoding='ascii') as target:
                    target.write('report_ready=true\n')
        else:
            sys.stdout.buffer.write(raw+b'\n')
        return 0 if report['lifecycle']['accepted'] else 1
    except BaseException:
        # No native exception, credential or host path is ever printed.
        return 1


if __name__=='__main__':raise SystemExit(main())

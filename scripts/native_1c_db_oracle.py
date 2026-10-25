#!/usr/bin/env python3
"""Explicit, independent opt-in: synthetic file-DB oracle, finite observations only.

No caller-supplied database/config/dump and no legacy full-suite flags are accepted.
Native artifacts, logs and XML never leave the disposable container tmpfs.
"""
from __future__ import annotations

import argparse
import json
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
HELPERS=ROOT/'scripts/native_1c_db_oracle'
sys.path.insert(0,str(HELPERS))
sys.path.insert(0,str(ROOT/'yadinassi/storage'))
from protocol import (CHECKS, IMAGE, MAX_REPORT_BYTES, STAGES, decode,
    encode, require)
from comparison import empty_report, validate_report, discard_capture
from snapshots import OracleError
from inputs import inventory, source_hashes, stage_inputs, staged_hashes
import native_1c_smoke as smoke

MAX_RUNTIME=2400
OUTPUT=Path('native-db-oracle/report.json')


def provenance(*, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False):
    inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction)
    try:
        repository=smoke.FULL.repository_provenance(ROOT)
    except (smoke.FULL.FullError,OSError):
        raise OracleError('provenance_mismatch') from None
    return {'commit':repository['commit'],'tree':repository['tree'],
        'sources':source_hashes(ROOT,record_metadata=record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction),
        'image':IMAGE,'platform':'linux/amd64','actual_version':None,'locale':'ru_RU.UTF-8','timezone':'Etc/UTC'}


def container_command(staged,name,nonce, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False):
    require(type(name) is str and re.fullmatch('onec-db-oracle-[0-9a-f]{32}',name) is not None,'invalid_input')
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}',nonce) is not None,'invalid_input')
    require(staged.is_dir() and not staged.is_symlink() and ',' not in str(staged),'invalid_input')
    staged_hashes(staged,record_metadata=record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction)
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
        '/bin/bash','--noprofile','--norc','/oracle/probe.sh','--invocation-nonce',nonce] + (
        ['--params-dbnames-extraction'] if params_extraction else
        ['--params-transport-observation'] if params_transport else
        ['--record-reader-validation'] if record_reader else
        ['--record-metadata-observation'] if record_metadata else [])


def fail_report(report,kind,stage='preflight',*,preserve_primary=False,record_reader=False):
    require(type(record_reader) is bool,'invalid_input')
    report.pop('rejected_basename',None)
    report.pop('failure_context',None)
    # Cleanup has its own checks; do not erase a validated primary failure.
    preserve=(preserve_primary and stage=='cleanup' and kind=='cleanup_unverified'
              and report['status']=='failed' and report['failed_stage']!='cleanup')
    if not preserve:
        report.update(status='failed',failed_stage=stage,failure_kind=kind,accepted=False)
    entry=report['stages'][STAGES.index(stage)]
    entry['status']='failed'
    entry['checks']=({key:report['cleanup'][key] for key in CHECKS[stage]} if stage=='cleanup'
                     else {key:False for key in CHECKS[stage]})
    report['artifacts']=[]
    if report.get('schema') == 8:
        import params_extraction
        params_extraction.discard_capture(report,final=True)
    elif report.get('schema') == 7:
        import params_observation
        params_observation.discard_capture(report,final=True)
    elif record_reader:
        import record_validation
        record_validation.discard_capture(report,final=True)
    elif report.get('schema') == 5:
        import record_observation
        record_observation.discard_capture(report)
    else:
        discard_capture(report)


def run_oracle(temp_root, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False):
    inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction)
    options={'params_extraction':True} if params_extraction else {'params_transport':True} if params_transport else {'record_reader':True} if record_reader else {'record_metadata':True} if record_metadata else {}
    if params_extraction:
        import params_extraction as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif params_transport:
        import params_observation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif record_reader:
        import record_validation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif record_metadata:
        import record_observation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    else:
        make_report=empty_report; check_report=validate_report
    # Credentials are removed before git, Docker or any other external process.
    token=os.environ.pop('GHCR_TOKEN',''); actor=os.environ.pop('GHCR_USER','')
    nonce=uuid.uuid4().hex; name='onec-db-oracle-'+uuid.uuid4().hex
    identity=provenance(**options); report=make_report(nonce,identity.copy())
    work_name=None; attempted=False; container_removed=True; native_cleanup=False
    primary=None; validated=False
    try:
        with tempfile.TemporaryDirectory(prefix='onec-db-oracle-',dir=temp_root) as work_name:
            work=Path(work_name).resolve(); staged=work/'inputs'
            stage_inputs(ROOT,staged,nonce,identity,**options)
            require(bool(token) and re.fullmatch('[A-Za-z0-9-]{1,39}',actor) is not None,'registry_credentials_missing')
            auth=work/'auth'; auth.mkdir(mode=0o700)
            try:
                smoke.run_silent(['docker','login','ghcr.io','--username',actor,'--password-stdin'],
                    smoke.docker_environment(auth),60,token.encode())
                token=''
                smoke.run_silent(['docker','pull','--platform','linux/amd64',IMAGE],smoke.docker_environment(auth),600)
            finally:
                token=''; shutil.rmtree(auth)
            clean=work/'no-auth'; clean.mkdir(mode=0o700); env=smoke.docker_environment(clean)
            code,value=smoke.bounded_run(['docker','image','inspect','--format',
                '{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}',IMAGE],env,30,128)
            require(code==0 and value.strip()==b'linux/amd64|0','container_unavailable')
            try:
                attempted=True; container_removed=False
                code,raw=smoke.bounded_run(container_command(staged,name,nonce,**options),env,MAX_RUNTIME,MAX_REPORT_BYTES)
                report=check_report(raw,nonce=nonce,provenance=identity)
                validated=True
                require((code==0)==(report['status']=='ok'),'transport_invalid')
                native_cleanup=all(report['cleanup'][key] for key in ('native_processes_stopped','raw_files_removed'))
            finally:
                try:
                    smoke.run_silent(['docker','rm','--force',name],env,30)
                    code,value=smoke.bounded_run(['docker','ps','--all','--filter',
                        'name=^/'+name+'$','--format','{{.Names}}'],env,30,128)
                    container_removed=code==0 and not value.strip()
                except smoke.SmokeError:
                    container_removed=False
            require(provenance(**options)==identity,'provenance_mismatch')
    except OracleError as error:
        primary=error.kind
    except smoke.SmokeError as error:
        primary='timeout' if 'timeout' in str(error) else 'container_unavailable'
    except BaseException:
        primary='unexpected_failure'
    finally:
        token=''
    private_removed=work_name is not None and not Path(work_name).exists()
    if primary:
        if not validated: report=make_report(nonce,identity.copy())
        fail_report(report,primary,'cleanup' if validated else 'preflight',record_reader=record_reader)
    if not attempted or (container_removed and not validated):
        native_cleanup=True
        report['cleanup'].update(native_processes_stopped=True,raw_files_removed=True)
    report['cleanup'].update(container_removed=container_removed,private_staging_removed=private_removed)
    if not container_removed or not private_removed:
        fail_report(report,'cleanup_unverified','cleanup',preserve_primary=validated,record_reader=record_reader)
    elif not attempted or not validated:
        entry=report['stages'][-1]; entry['status']='ok'; entry['checks']={key:True for key in CHECKS['cleanup']}
    if not all(report['cleanup'].values()):
        report.pop('rejected_basename',None)
        report.pop('failure_context',None)
    report['accepted']=report['status']=='ok' and all(report['cleanup'].values())
    check_report(encode(report),nonce=nonce,provenance=identity,final=True)
    return report


def export_report(raw, root_identity):
    """Exclusive descriptor-relative publication after runtime cleanup/validation.

    No fallback to a path-following write: the real CI host is POSIX. Portable
    protocol/orchestration tests do not need to simulate an unsafe export path.
    """
    require(os.open in os.supports_dir_fd and hasattr(os,'O_NOFOLLOW')
            and hasattr(os,'O_DIRECTORY'),'unsupported_platform_command')
    require(type(raw) is bytes and len(raw)+1<=MAX_REPORT_BYTES,'artifact_limit')
    root_fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent_fd=None
    try:
        info=os.fstat(root_fd)
        require((info.st_dev,info.st_ino)==root_identity,'provenance_mismatch')
        try: os.mkdir(OUTPUT.parent.name,0o700,dir_fd=root_fd)
        except FileExistsError: pass
        parent_fd=os.open(OUTPUT.parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        parent_info=os.fstat(parent_fd)
        target=os.open(OUTPUT.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent_fd)
        with os.fdopen(target,'wb') as stream:
            stream.write(raw+b'\n'); stream.flush(); os.fsync(stream.fileno())
            written=os.fstat(stream.fileno())
            require(stat.S_ISREG(written.st_mode) and written.st_nlink==1
                    and written.st_size==len(raw)+1,'transport_invalid')
        current=os.stat(OUTPUT.parent.name,dir_fd=root_fd,follow_symlinks=False)
        require((current.st_dev,current.st_ino)==(parent_info.st_dev,parent_info.st_ino),'provenance_mismatch')
    finally:
        if parent_fd is not None: os.close(parent_fd)
        os.close(root_fd)


class Arguments(argparse.ArgumentParser):
    def error(self,message):
        # Do not echo untrusted input values or possible credentials into CI logs.
        self.exit(2,'File-DB oracle rejected: invalid_input\n')


def main(argv=None):
    parser=Arguments(description=__doc__,allow_abbrev=False)
    parser.add_argument('--execute-approved-image',action='store_true')
    parser.add_argument('--file-db-oracle',action='store_true')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--record-metadata-observation',action='store_true',
        help='explicit bounded baseline metadata/declaration observation; not record acceptance')
    modes.add_argument('--record-reader-validation',action='store_true',
        help='explicit bounded owned-record readback and validation')
    modes.add_argument('--params-transport-observation',action='store_true',
        help='finite PARAMS declaration capture, not DBNames extraction')
    modes.add_argument('--params-dbnames-extraction',action='store_true',
        help='finite owned PARAMS/DBNames extraction, without native byte equivalence')
    parser.add_argument('--output',default=str(OUTPUT))
    args=parser.parse_args(argv)
    if not args.execute_approved_image or not args.file_db_oracle or args.output!=str(OUTPUT):
        parser.error('invalid_input')
    output=ROOT/OUTPUT
    if output.exists() or output.is_symlink() or output.parent.is_symlink():
        parser.error('stale_evidence')
    try:
        root_info=ROOT.stat(); root_identity=(root_info.st_dev,root_info.st_ino)
        options=({'params_extraction':True} if args.params_dbnames_extraction else
                 {'params_transport':True} if args.params_transport_observation else
                 {'record_reader':True} if args.record_reader_validation else
                 {'record_metadata':True} if args.record_metadata_observation else {})
        report=run_oracle(Path(tempfile.gettempdir()),**options)
        raw=encode(report)
        export_report(raw,root_identity)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='ascii') as target:
                target.write('report_ready=true\n')
        print('File-DB oracle accepted.' if report['accepted'] else 'File-DB oracle failed; see finite report.')
        return 0 if report['accepted'] else 1
    except BaseException:
        print('File-DB oracle failed before validated report export.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())

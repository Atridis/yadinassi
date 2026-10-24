#!/usr/bin/env python3
"""Disposable, serialized native oracle. Never read a caller's database.

Every observation/export uses a throwaway clone of an already frozen snapshot.
The standalone reader examines only the closed, frozen post-audit clone.
No interpreter runtime or unrestricted native payload export is loaded.
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
# Staged as a standalone source-pinned standard-library module. Do not import
# yadinassi.__init__: native measurement must not load the Interpreter runtime.
from filedb import decode_header, InspectionStatus
from protocol import (ARTIFACTS, CHECKS, COMPARISONS, FAILURES, IMAGE, LANE, MAX_REPORT_BYTES,
    BASELINE_FAILURES, BASELINE_OPERATIONS, BOOTSTRAP_INVENTORY_FAILURES, DIAGNOSTIC_ENTRY_CLASSES,
    INVENTORY_PHASES, INVENTORY_REGIONS, INVENTORY_REASONS,
    SEED_FAILURE_CATEGORIES, SEED_FAILURES, SEED_OPERATIONS, STAGES, VERSION,
    decode, empty_report, encode, expected_logical, logical_from_marker,
    COMMAND_STAGES, CONTEXT_SITES, completion_marker, validate_failure_context,
    marker, require, validate_logical, validate_report)
from snapshots import (DatabaseEntryError, ENTRY_CLASSES, ENTRY_SHAPES, OracleError,
    MAX_FILE_BYTES, MAX_LIVE_BYTES, budget_check, clone_database,
    compare_files, compare_pair, diagnostic_entry_class, file_summary, freeze_database,
    valid_diagnostic_basename)
import contract
import comparison
import filedb_catalog
from inject_metadata import CRUD_USER, SETUP_USER, inject, promote_v2, verify_redump

ONEC = Path('/opt/1cv8t/x86_64/8.3.27.1508/1cv8t')
ROOT = Path('/tmp/onec-db-oracle')
INPUTS = Path('/oracle')
COMMAND_SECONDS = 120
WORK_SECONDS = 2340
MAX_LOG_BYTES = 1048576
MAX_LOG_TOTAL = 16777216
MAX_HOME_SOCKETS = 4


class SeedCommandError(OracleError):
    """Internal fixed launch context; only Controller may encode it publicly."""
    def __init__(self, kind, operation):
        require(type(operation) is str and operation in SEED_OPERATIONS
                and type(kind) is str and kind in SEED_FAILURE_CATEGORIES, 'invalid_input')
        super().__init__(kind)
        self.operation=operation


class SandboxInventoryError(OracleError):
    """Finite classification of an existing inventory rejection, never its path."""
    def __init__(self, region, reason):
        require(type(region) is str and region in INVENTORY_REGIONS
                and type(reason) is str and reason in INVENTORY_REASONS, 'invalid_input')
        super().__init__('invalid_input')
        self.region=region; self.reason=reason


class BootstrapInventoryError(SandboxInventoryError):
    def __init__(self, phase, region, reason):
        require(type(phase) is str and phase in INVENTORY_PHASES, 'invalid_input')
        super().__init__(region,reason)
        self.phase=phase


class BaselineInputError(OracleError):
    """Lexically scoped fixed operation and optional rejected root-entry shape."""
    def __init__(self, operation, entry_class=None, shape=None, *, basename=None):
        require(type(operation) is str and operation in BASELINE_OPERATIONS, 'invalid_input')
        require((entry_class is None and shape is None) or
                (type(entry_class) is str and entry_class in ENTRY_CLASSES
                 and type(shape) is str and shape in ENTRY_SHAPES), 'invalid_input')
        super().__init__('invalid_input')
        self.operation=operation; self.entry_class=entry_class; self.shape=shape
        if basename is not None:
            require(operation=='freeze' and shape=='owned_regular_zero'
                    and valid_diagnostic_basename(basename)
                    and entry_class in DIAGNOSTIC_ENTRY_CLASSES
                    and diagnostic_entry_class(basename)==entry_class, 'invalid_input')
            self.basename=basename


def inventory_region(relative):
    # Fixed controlled regions, not arbitrary native path components.
    def below(prefix): return relative.rstrip('/')==prefix or relative.startswith(prefix+'/')
    if below('onec-db-oracle/home'): return 'home'
    if below('onec-db-oracle/temp'): return 'tmp'
    if below('runtime') or below('.X11-unix'): return 'runtime'
    if below('onec-db-oracle'): return 'experiment'
    return 'tmp'


def inventory_io_reason(error):
    if error.errno in (errno.ENOENT, getattr(errno,'ESTALE',errno.ENOENT)): return 'race'
    if error.errno in (errno.EACCES,errno.EPERM): return 'access'
    return 'otherio'


def absent(*paths):
    require(not any(path.exists() or path.is_symlink() for path in paths), 'stale_evidence')


def regular_bytes(path, limit):
    try:
        info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0 < info.st_size <= limit, 'artifact_limit')
        fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            opened=os.fstat(stream.fileno())
            require((opened.st_dev,opened.st_ino)==(info.st_dev,info.st_ino),'stale_evidence')
            raw=stream.read(limit+1)
        require(0 < len(raw) <= limit,'artifact_limit')
        return raw
    except OSError:
        raise OracleError('artifact_missing') from None


def native_file_summary(path):
    summary=file_summary(path)
    require(summary['bytes']>0,'artifact_missing')
    return summary


def database_header_facts(raw, size):
    """Finite facts only; unknown versions and invalid geometry fail closed."""
    result = decode_header(raw, size, max_pages=MAX_FILE_BYTES // 4096,
                           max_file_bytes=MAX_FILE_BYTES)
    require(result.status is InspectionStatus.HEADER_LAYOUT_MATCH, 'invalid_header')
    header = result.header
    return {'status':'header_layout_match', 'version':list(header.version),
            'page_size':header.page_size, 'page_count':header.page_count}


def zero_result(path):
    raw=regular_bytes(path,128)
    try:
        value=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig').strip()
        require(re.fullmatch('[+-]?[0-9]+',value) is not None and int(value)==0,'invalid_dump_result')
    except UnicodeError:
        raise OracleError('invalid_dump_result') from None



def _checked_home_anchor(root_fd, expected=None):
    """Directory metadata only: fixed private HOME and its parent entry."""
    descriptors=[]
    try:
        if expected is not None:
            require(type(expected) is tuple and len(expected)==8
                    and all(type(value) is int and value>=0 for value in expected)
                    and expected[2:4]==expected[6:8]==(1000,1000), 'snapshot_changed')
        parent=root_fd; values=[]
        for name in ('onec-db-oracle','home'):
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            descriptors.append(child)
            opened=os.fstat(child); entry=os.stat(name,dir_fd=parent,follow_symlinks=False)
            require(stat.S_ISDIR(opened.st_mode) and stat.S_ISDIR(entry.st_mode)
                    and (opened.st_dev,opened.st_ino)==(entry.st_dev,entry.st_ino)
                    and (opened.st_uid,opened.st_gid)==(entry.st_uid,entry.st_gid)==(1000,1000),
                    'snapshot_changed')
            values.extend((opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid))
            parent=child
        actual=tuple(values)
        require(expected is None or actual==expected,'snapshot_changed')
        return actual
    except OSError:
        raise OracleError('snapshot_changed') from None
    finally:
        for descriptor in reversed(descriptors): os.close(descriptor)


def capture_home_anchor(root):
    # Called once, before native processes, never repinned after a replacement.
    try:
        descriptor=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: return _checked_home_anchor(descriptor)
        finally: os.close(descriptor)
    except OSError:
        raise OracleError('snapshot_changed') from None


def sandbox_bytes(root, reserve=0, *, home_anchor=None):
    """Account the same private tmpfs entries without changing admission policy.

    Error classifications contain fixed regions/reasons only. Disappearing entry
    stat/child-open races remain tolerated exactly as before; other existing
    rejections remain failures except the explicit pinned, owned HOME socket policy.
    """
    require(type(reserve) is int and 0 <= reserve <= MAX_LIVE_BYTES,'artifact_limit')
    sockets={'.X11-unix/X99','runtime/session-bus/bus'}
    total=0; entries=0; home_sockets=0
    def reject(relative,reason):
        raise SandboxInventoryError(inventory_region(relative),reason)
    def io(relative,action,*,missing=False):
        try: return action()
        except FileNotFoundError as error:
            if missing: return None
            raise SandboxInventoryError(inventory_region(relative),inventory_io_reason(error)) from None
        except OSError as error:
            raise SandboxInventoryError(inventory_region(relative),inventory_io_reason(error)) from None
    def links(relative,info):
        if info.st_nlink!=1: reject(relative,'hardlink' if info.st_nlink>1 else 'link_count')
    def walk(descriptor,prefix,depth):
        nonlocal total,entries,home_sockets
        require(depth<=16,'artifact_limit')
        try:
            with os.scandir(descriptor) as children:
                for entry in children:
                    entries+=1; require(entries<=4096,'artifact_limit')
                    relative=prefix+entry.name
                    info=io(relative,lambda: entry.stat(follow_symlinks=False),missing=True)
                    if info is None: continue
                    if stat.S_ISDIR(info.st_mode):
                        child=io(relative,lambda: os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor),missing=True)
                        if child is None: continue
                        try:
                            actual=io(relative,lambda: os.fstat(child))
                            require((actual.st_dev,actual.st_ino)==(info.st_dev,info.st_ino),'snapshot_changed')
                            if home_anchor is not None and relative in ('onec-db-oracle','onec-db-oracle/home'):
                                offset=0 if relative=='onec-db-oracle' else 4
                                require((actual.st_dev,actual.st_ino,actual.st_uid,actual.st_gid)==home_anchor[offset:offset+4],
                                        'snapshot_changed')
                            before=home_sockets
                            walk(child,relative+'/',depth+1)
                            if home_sockets>before:
                                # The new exception is valid only while this path still names the opened directory.
                                try: after=os.stat(entry.name,dir_fd=descriptor,follow_symlinks=False)
                                except OSError: raise OracleError('snapshot_changed') from None
                                require(stat.S_ISDIR(after.st_mode)
                                        and (after.st_dev,after.st_ino)==(actual.st_dev,actual.st_ino),'snapshot_changed')
                        finally: io(relative,lambda: os.close(child))
                    elif stat.S_ISSOCK(info.st_mode):
                        if relative in sockets:
                            links(relative,info)
                        elif home_anchor is not None and relative.startswith('onec-db-oracle/home/'):
                            if (info.st_uid,info.st_gid)!=(1000,1000): reject(relative,'unexpected_socket')
                            links(relative,info)
                            home_sockets+=1
                            require(home_sockets<=MAX_HOME_SOCKETS,'artifact_limit')
                        else: reject(relative,'unexpected_socket')
                    else:
                        if stat.S_ISLNK(info.st_mode): reject(relative,'symlink')
                        if not stat.S_ISREG(info.st_mode): reject(relative,'special')
                        links(relative,info)
                        require(0<=info.st_size<=MAX_FILE_BYTES,'artifact_limit')
                        total+=info.st_size
                        require(total+reserve<=MAX_LIVE_BYTES,'artifact_limit')
        except OSError as error:
            raise SandboxInventoryError(inventory_region(prefix),inventory_io_reason(error)) from None
    descriptor=io('',lambda: os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
    try:
        if home_anchor is not None: _checked_home_anchor(descriptor,home_anchor)
        walk(descriptor,'',0)
        if home_anchor is not None: _checked_home_anchor(descriptor,home_anchor)
    finally: io('',lambda: os.close(descriptor))
    return total


def process_snapshot():
    """PID + /proc starttime prevents accepting PID reuse as a live baseline."""
    result=set()
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            value=(path/'stat').read_text(encoding='ascii')
            # comm may contain spaces/parentheses; fields after its last ')' start at state.
            fields=value[value.rfind(')')+2:].split()
            require(len(fields)>=20,'snapshot_not_quiescent')
            result.add((int(path.name),fields[19]))
        except FileNotFoundError:
            continue
        except (OSError,UnicodeError,ValueError):
            raise OracleError('snapshot_not_quiescent') from None
    return result


def kill_identity(identity):
    pid,started=identity
    if identity not in process_snapshot():
        return
    require(pid not in (1,os.getpid()),'cleanup_unverified')
    try:
        fd=os.pidfd_open(pid)
        try:
            if identity in process_snapshot():
                signal.pidfd_send_signal(fd,signal.SIGKILL)
        finally:
            os.close(fd)
    except ProcessLookupError:
        pass


class Native:
    def __init__(self, nonce, provenance):
        self.nonce=nonce; self.provenance=provenance
        self.root=ROOT; self.artifacts=ROOT/'artifacts'; self.evidence=ROOT/'evidence'
        self.budget_base=Path('/tmp')
        self.deadline=time.monotonic()+WORK_SECONDS
        self.baseline=None; self.initial=None; self.services=[]; self.counter=0
        self.v1=ROOT/'metadata-v1'; self.v2=ROOT/'metadata-v2'
        self.stage='preflight'; self.seed_pending=None; self.seed_launched=None
        self.home_anchor=None; self.reader_attempted=False

    def begin_stage(self, stage):
        require(type(stage) is str and stage in STAGES, 'invalid_input')
        self.stage=stage
        # Never let an earlier seed launch relabel a later-stage failure.
        self.seed_pending=None; self.seed_launched=None

    @contextmanager
    def seed_command(self, operation):
        require(self.stage=='seed_v1' and type(operation) is str
                and operation in SEED_OPERATIONS and self.seed_pending is None, 'invalid_input')
        self.seed_pending=operation; self.seed_launched=None
        try:
            yield
        except BaseException as error:
            kind=error.kind if isinstance(error,OracleError) and error.kind in FAILURES else 'unexpected_failure'
            if self.stage=='seed_v1' and self.seed_launched==operation and kind in SEED_FAILURE_CATEGORIES:
                if operation=='bootstrap' and isinstance(error,BootstrapInventoryError): raise
                wrapped=SeedCommandError(kind,operation)
                if hasattr(error,'failure_context'):
                    wrapped.failure_context=error.failure_context
                    wrapped.failure_context_stage=getattr(error,'failure_context_stage',None)
                raise wrapped from None
            raise
        finally:
            self.seed_pending=None; self.seed_launched=None

    @contextmanager
    def command_context(self, operation):
        require(type(operation) is str and operation in COMMAND_STAGES, 'invalid_input')
        entered_stage=self.stage
        try:
            yield
        except BaseException as original:
            error=original if isinstance(original,OracleError) else OracleError('unexpected_failure')
            # No mutable pending operation survives a launch or stage transition.
            if self.stage==entered_stage and entered_stage in COMMAND_STAGES[operation]:
                context={'operation':operation,'site':getattr(error,'oracle_site','operation'),
                    'bsl_phase':getattr(error,'bsl_phase',None),
                    'region':error.region if isinstance(error,SandboxInventoryError) else None,
                    'reason':error.reason if isinstance(error,SandboxInventoryError) else None}
                if operation in ('snapshot_freeze','snapshot_clone') and isinstance(error,DatabaseEntryError):
                    context.update(entry_class=error.entry_class,entry_shape=error.shape)
                validate_failure_context(context,entered_stage)
                error.failure_context=context
                error.failure_context_stage=entered_stage
            else:
                error.__dict__.pop('failure_context',None)
                error.__dict__.pop('failure_context_stage',None)
            raise error from None

    def remaining(self):
        remaining=self.deadline-time.monotonic()
        require(remaining>0,'timeout')
        return remaining

    def budgets(self, reserve=0):
        sandbox_bytes(self.budget_base,reserve,home_anchor=self.home_anchor)
        logs=[p for p in self.root.rglob('*') if p.is_file() and p.suffix in ('.log','.result')]
        require(all(p.stat().st_size<=MAX_LOG_BYTES for p in logs)
                and sum(p.stat().st_size for p in logs)<=MAX_LOG_TOTAL,'artifact_limit')

    def monitor_budget(self, phase):
        require(type(phase) is str and phase in INVENTORY_PHASES, 'invalid_input')
        try:
            self.budgets()
        except SandboxInventoryError as error:
            if self.stage=='seed_v1' and self.seed_pending==self.seed_launched=='bootstrap':
                raise BootstrapInventoryError(phase,error.region,error.reason) from None
            raise

    def quiescent(self):
        return self.baseline is not None and process_snapshot()==self.baseline

    def process(self, args, label, *, native=True):
        site='prelaunch'
        try:
            self.remaining(); self.budgets()
            require(not native or self.quiescent(),'snapshot_not_quiescent')
            self.counter+=1
            console=self.evidence/f'{self.counter:03}-{label}-console.log'
            absent(console)
            with console.open('xb') as log:
                if self.seed_pending is not None:
                    require(native and self.stage=='seed_v1' and self.seed_pending in SEED_OPERATIONS, 'invalid_input')
                    # This is the launch boundary, not success or proof of an infobase.
                    self.seed_launched=self.seed_pending
                site='launch'
                child=subprocess.Popen(args,cwd=self.evidence,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=min(self.deadline,time.monotonic()+COMMAND_SECONDS)
                try:
                    site='poll'
                    while child.poll() is None:
                        require(time.monotonic()<deadline,'timeout')
                        if native: self.monitor_budget('poll')
                        time.sleep(.05)
                    site='exit'
                    code=child.wait()
                    require(code==0,'process_failed')
                finally:
                    if child.poll() is None:
                        try: os.killpg(child.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                        child.wait(timeout=5)
            # Marker, success exit and stable mtime do not certify quiescence.
            if native:
                # Allow --init to reap already-exiting helpers; never copy while they remain.
                site='settle'
                settle=min(self.deadline,time.monotonic()+5)
                while not self.quiescent():
                    require(time.monotonic()<settle,'snapshot_not_quiescent')
                    time.sleep(.02)
            site='post_exit'
            if native: self.monitor_budget('post_exit')
            else: self.budgets()
        except BaseException as original:
            error=original if isinstance(original,OracleError) else OracleError('unexpected_failure')
            error.oracle_site=site
            raise error from None

    def preflight(self):
        require(os.geteuid()==1000 and sys.version_info>=(3,10) and ONEC.is_file()
                and os.access(ONEC,os.X_OK),'unsupported_platform_command')
        require(hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'unsupported_platform_command')
        absent(self.root); self.root.mkdir(mode=0o700)
        self.artifacts.mkdir(mode=0o700); self.evidence.mkdir(mode=0o700)
        for directory in (self.root/'home',self.root/'temp',Path('/tmp/runtime')):
            absent(directory); directory.mkdir(mode=0o700)
        self.home_anchor=capture_home_anchor(self.budget_base)
        os.environ['HOME']=str(self.root/'home')
        os.environ['TMPDIR']=str(self.root/'temp')
        self.initial=process_snapshot()
        self.process(['ldd',str(ONEC)],'libraries',native=False)
        library_log=self.evidence/'001-libraries-console.log'
        require(b'not found' not in regular_bytes(library_log,65536),'unsupported_platform_command')
        xdir=Path('/tmp/.X11-unix'); xdir.mkdir(mode=0o1777,exist_ok=True)
        auth=Path('/tmp/runtime/xauth')
        self.process(['xauth','-f',str(auth),'add',':99','MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],'xauth',native=False)
        os.environ['XAUTHORITY']=str(auth)
        busdir=Path('/tmp/runtime/session-bus'); busdir.mkdir(mode=0o700)
        address='unix:path='+str(busdir/'bus')
        os.environ['DBUS_SESSION_BUS_ADDRESS']=address
        commands=[['Xtigervnc',':99','-geometry','1280x800','-depth','24','-rfbport','-1','-nolisten','tcp','-auth',str(auth)],
            ['/usr/bin/dbus-daemon','--session','--nofork','--nopidfile','--nosyslog','--address='+address]]
        for index,args in enumerate(commands):
            log=(self.evidence/f'service-{index}.log').open('xb')
            child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.services.append((child,log))
        deadline=min(self.deadline,time.monotonic()+10)
        while True:
            require(all(child.poll() is None for child,_ in self.services),'process_failed')
            result=subprocess.run(['xdpyinfo','-display',':99'],stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2,check=False)
            if result.returncode==0 and (busdir/'bus').is_socket():
                break
            require(time.monotonic()<deadline,'timeout'); time.sleep(.1)
        self.baseline=process_snapshot()

    def command(self, mode, database, user=SETUP_USER):
        self.remaining()
        require(database.parent==self.artifacts and not database.is_symlink(),'invalid_input')
        args=[str(ONEC),mode,'/F',str(database)]
        if user is not None:
            require(user in (SETUP_USER,CRUD_USER),'invalid_input'); args+=['/N',user]
        return args+['/AppAutoCheckVersion-','/DisableStartupDialogs','/DisableStartupMessages','/L','ru']

    def batch(self, database, operation, label, user=SETUP_USER):
        contexts={'dump-empty':'designer_dump_empty','seed-import':'designer_import',
            'producer-v2-import':'designer_import','seed-apply':'designer_apply',
            'producer-v2-apply':'designer_apply','apply-cf':'designer_apply','redump':'designer_redump',
            'export-cf_v1':'designer_export_cf','export-cf_v2':'designer_export_cf',
            'load-cf':'designer_load_cf','export-dt_updated':'designer_dump_dt','restore':'designer_restore_dt'}
        require(type(label) is str and label in contexts,'invalid_input')
        with self.command_context(contexts[label]):
            return self._batch(database,operation,label,user)

    def _batch(self, database, operation, label, user=SETUP_USER):
        result=self.evidence/f'{self.counter+1:03}-{label}.result'
        log=self.evidence/f'{self.counter+1:03}-{label}.log'
        absent(result,log)
        self.process(self.command('DESIGNER',database,user)+operation+['/Out',str(log),'/DumpResult',str(result)],label)
        zero_result(result)

    def physical_summary(self,path):
        # Census precedes the first database/artifact payload read, not just copying.
        require(self.quiescent(),'snapshot_not_quiescent')
        return native_file_summary(path)

    def create_db(self, name):
        with self.command_context('create_infobase'):
            return self._create_db(name)

    def _create_db(self, name):
        database=self.artifacts/name; absent(database)
        self.budgets(MAX_FILE_BYTES)
        result=self.evidence/f'{self.counter+1:03}-create.result'; log=self.evidence/f'{self.counter+1:03}-create.log'
        absent(result,log)
        self.process([str(ONEC),'CREATEINFOBASE',f'File="{database}";','/Lru',
            '/Out',str(log),'/DumpResult',str(result)],'create')
        zero_result(result); self.physical_summary(database/'1Cv8.1CD')
        return database

    def enterprise(self, database, operation, *, token=None):
        require(type(operation) is str and 'enterprise_'+operation in COMMAND_STAGES,'invalid_input')
        if operation == 'audit_contract':
            require(self.stage == 'baseline', 'invalid_input')
        with self.command_context('enterprise_'+operation):
            return self._enterprise(database,operation,token=token)

    def _enterprise(self, database, operation, *, token=None):
        token=secrets.token_hex(16) if token is None else token
        require(type(token) is str and re.fullmatch('[0-9a-f]{32}',token) is not None,'invalid_input')
        control=self.evidence/'control.json'; result=self.evidence/'result.json'
        completion=self.evidence/'completion.json'; pending=self.evidence/'completion.pending.json'
        absent(control,result,completion,pending)
        control.write_text(json.dumps({'schema':1,'nonce':self.nonce,'token':token,'operation':operation}),encoding='utf-8')
        user=None if operation=='bootstrap' else (SETUP_USER if operation in ('audit','audit_contract') else CRUD_USER)
        try:
            log=self.evidence/f'{self.counter+1:03}-{operation}.log'; absent(log)
            self.process(self.command('ENTERPRISE',database,user)+['/RunModeManagedApplication',
                '/C',token,'/Out',str(log)],operation)
            if operation == 'audit_contract':
                absent(pending)
            finished=completion_marker(regular_bytes(completion,4096),nonce=self.nonce,token=token,operation=operation)
            if finished['status']=='error':
                kind = ('artifact_limit' if operation == 'audit_contract' and finished['phase'] == 'contract_limit' else 'process_failed')
                error=OracleError(kind); error.oracle_site='result'; error.bsl_phase=finished['phase']
                raise error
            data=marker(regular_bytes(result,MAX_REPORT_BYTES),nonce=self.nonce,token=token,operation=operation,
                        contract_version=comparison.SCHEMA)
            self.provenance['actual_version']=data['actual_version']
            return data
        finally:
            control.unlink(missing_ok=True); result.unlink(missing_ok=True)
            completion.unlink(missing_ok=True); pending.unlink(missing_ok=True)

    def seed(self):
        with self.seed_command('create'):
            database=self.create_db('seed')
        native=self.root/'native-empty'; absent(native)
        with self.seed_command('dump_empty'):
            self.batch(database,['/DumpConfigToFiles',str(native),'-Format','Hierarchical'],'dump-empty',None)
        try:
            inject(native,self.v1,nonce=self.nonce,evidence=self.evidence)
            promote_v2(self.v1,self.v2)
        except (ValueError,OSError):
            raise OracleError('metadata_rejected') from None
        with self.seed_command('import'):
            self.batch(database,['/LoadConfigFromFiles',str(self.v1)],'seed-import',None)
        with self.seed_command('apply'):
            self.batch(database,['/UpdateDBCfg'],'seed-apply',None)
        with self.seed_command('redump'):
            self.redump(database,1,user=None)
        with self.seed_command('bootstrap'):
            self.enterprise(database,'bootstrap')
        return database

    def redump(self, database, version, user=SETUP_USER):
        target=self.root/f'redump-{self.counter+1:03}'; absent(target)
        self.batch(database,['/DumpConfigToFiles',str(target),'-Format','Hierarchical'],'redump',user)
        try:
            verify_redump(self.v1 if version==1 else self.v2,target,version=version)
        except (ValueError,OSError):
            raise OracleError('metadata_rejected') from None
        finally:
            if target.exists(): shutil.rmtree(target)

    def freeze(self, database, identifier):
        with self.command_context('snapshot_freeze'):
            target=self.artifacts/identifier
            self.budgets(self.physical_summary(database/'1Cv8.1CD')['bytes'])
            capture=(self.stage=='baseline' and identifier=='baseline'
                     and self.root==ROOT and self.artifacts==ROOT/'artifacts'
                     and database==self.artifacts/'seed'
                     and self.provenance['actual_version']==VERSION)
            summary=freeze_database(database,target,quiescent=self.quiescent,
                                    capture_source_name=capture,
                                    header_decoder=database_header_facts)
            self.budgets()
        # Removal has its own boundary; never relabel it as a freeze failure.
        self.remove(database)
        return summary

    def clone(self, identifier, label):
        with self.command_context('snapshot_clone'):
            target=self.artifacts/label
            self.budgets(self.physical_summary(self.artifacts/identifier/'1Cv8.1CD')['bytes'])
            clone_database(self.artifacts/identifier,target,budget_root=self.artifacts)
            self.budgets()
            return target

    def remove(self, path):
        with self.command_context('snapshot_remove'):
            require(self.quiescent(),'snapshot_not_quiescent')
            if path.exists():
                require(path.parent==self.artifacts and not path.is_symlink(),'invalid_input')
                path.chmod(0o700)
                shutil.rmtree(path)

    @contextmanager
    def temporary_clone(self, identifier, label):
        database=self.clone(identifier,label)
        try:
            yield database
        except BaseException:
            # Always attempt removal, but let the controller keep the primary
            # failure and its context before its independent global cleanup.
            try: self.remove(database)
            except BaseException: pass
            raise
        else:
            # A successful operation still fails if removal cannot be verified.
            self.remove(database)

    def discard(self,*identifiers):
        for identifier in identifiers: self.remove(self.artifacts/identifier)

    def observe(self, identifier, designer):
        with self.temporary_clone(identifier,'observer') as database:
            # Designer redump and runtime read are separate clone sessions. Neither touches frozen bytes.
            self.redump(database,designer)
            data=self.enterprise(database,'observe')
            return logical_from_marker(data,designer)

    def audit(self, identifier):
        with self.temporary_clone(identifier,'auditor') as database:
            self.enterprise(database,'audit')

    def audit_contract(self, identifier):
        require(self.stage == 'baseline' and identifier == 'baseline', 'invalid_input')
        with self.temporary_clone(identifier, 'auditor') as database:
            return self.enterprise(database, 'audit_contract')

    def compare_catalog(self, identifier):
        """One existing native audit; independent parser reads only its closed postimage."""
        require(self.stage == 'baseline' and identifier == 'baseline', 'invalid_input')
        with self.temporary_clone(identifier, 'auditor') as database:
            baseline = self.physical_summary(self.artifacts / identifier / '1Cv8.1CD')
            origin = self.physical_summary(database / '1Cv8.1CD')
            if origin != baseline:
                raise comparison.ComparisonFailure('io_or_change', 'origin_changed')
            # Pin the fresh token and fixed clone identity to the checked origin
            # before launch, not merely to the report's original baseline later.
            token = secrets.token_hex(16)
            origin = {**origin, 'clone': 'auditor', 'nonce': self.nonce, 'token': token}
            data = self.enterprise(database, 'audit_contract', token=token)
            frozen = self.artifacts / 'auditor_frozen'
            absent(frozen)
            try:
                with self.command_context('snapshot_freeze'):
                    self.budgets(self.physical_summary(database / '1Cv8.1CD')['bytes'])
                    postimage = freeze_database(database, frozen, quiescent=self.quiescent)
                    self.budgets()
                try:
                    from snapshots import inspect_frozen_catalog
                    self.reader_attempted = True
                    summary, catalog = inspect_frozen_catalog(frozen, quiescent=self.quiescent,
                        read_catalog=filedb_catalog.read_catalog, limits=filedb_catalog.CatalogLimits(),
                        before_read=self.remaining)
                except filedb_catalog.CatalogError as error:
                    raise comparison.reader_failure(error) from None
                except OracleError as error:
                    if error.kind in ('snapshot_changed', 'snapshot_not_quiescent', 'artifact_missing', 'invalid_input'):
                        raise comparison.ComparisonFailure('io_or_change', error.kind) from None
                    if error.kind == 'artifact_limit':
                        raise comparison.ComparisonFailure('resource_limit', 'projection_limit') from None
                    raise
                if summary != {key: postimage[key] for key in ('bytes', 'sha256')}:
                    raise comparison.ComparisonFailure('io_or_change', 'postimage_changed')
                # The complete parse above has never seen native names.
                try:
                    native, projected = comparison.project_catalog(catalog, data['storage_names'])
                except comparison.ComparisonFailure as error:
                    if type(error) is comparison.ComparisonFailure and (error.category, error.code) == ('name_mismatch', 'missing_table'):
                        raise comparison.missing_table_failure(catalog,
                            {'marker': data, 'origin': origin, 'postimage': summary},
                            nonce=self.nonce, provenance=self.provenance, baseline=baseline,
                            before_scan=self.remaining) from None
                    raise
                evidence = {'marker': data, 'origin': origin, 'postimage': summary, 'reader': projected}
            except BaseException:
                try: self.remove(frozen)
                except BaseException: pass
                raise
            else:
                self.remove(frozen)
                return evidence

    def mutate(self,database,operation):
        self.enterprise(database,operation)

    def compare(self,source,control,treatment):
        require(self.quiescent(),'snapshot_not_quiescent')
        return compare_files(*(self.artifacts/name/'1Cv8.1CD' for name in (source,control,treatment)))

    def compare_pair(self,source,treatment):
        require(self.quiescent(),'snapshot_not_quiescent')
        return compare_pair(*(self.artifacts/name/'1Cv8.1CD' for name in (source,treatment)))

    def export_configs(self):
        for version in (1,2):
            with self.temporary_clone('baseline','producer') as database:
                if version==2:
                    self.batch(database,['/LoadConfigFromFiles',str(self.v2)],'producer-v2-import')
                    self.batch(database,['/UpdateDBCfg'],'producer-v2-apply')
                    self.redump(database,2)
                self.export(database,'cf_v'+str(version),'/DumpCfg')

    def export(self,database,identifier,switch):
        suffix='.dt' if identifier=='dt_updated' else '.cf'
        target=self.artifacts/(identifier+suffix); absent(target)
        self.budgets(MAX_FILE_BYTES)
        self.batch(database,[switch,str(target)],'export-'+identifier)
        return self.physical_summary(target)

    def artifact(self,identifier):
        return self.physical_summary(self.artifacts/(identifier+('.dt' if identifier=='dt_updated' else '.cf')))

    def load_cf(self,database,version):
        self.batch(database,['/LoadCfg',str(self.artifacts/f'cf_v{version}.cf')],'load-cf')

    def apply(self,database):
        self.batch(database,['/UpdateDBCfg'],'apply-cf')

    def dump_dt(self):
        with self.temporary_clone('applied','dumper') as database:
            self.export(database,'dt_updated','/DumpIB')

    def restore(self):
        database=self.create_db('restore-target')
        self.batch(database,['/RestoreIB',str(self.artifacts/'dt_updated.dt')],'restore',None)
        # Deliberately no /UpdateDBCfg. Restored config must stand on its own.
        return database

    def cleanup(self):
        success=True
        try:
            if self.baseline is not None:
                for identity in process_snapshot()-self.baseline:
                    kill_identity(identity)
            for child,log in reversed(self.services):
                if child.poll() is None:
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                child.wait(timeout=5); log.close()
            if self.initial is not None:
                deadline=time.monotonic()+5
                while process_snapshot()!=self.initial and time.monotonic()<deadline:
                    for identity in process_snapshot()-self.initial:
                        kill_identity(identity)
                    time.sleep(.02)
                success=process_snapshot()==self.initial
        except BaseException:
            success=False
        removed=False
        try:
            if self.root.exists():
                for path in self.root.rglob('*'):
                    if path.is_dir() and not path.is_symlink(): path.chmod(0o700)
                shutil.rmtree(self.root)
            for directory in (Path('/tmp/runtime'),):
                if directory.exists(): shutil.rmtree(directory)
            removed=not self.root.exists()
        except OSError: pass
        return success,removed


class Controller:
    """Lifecycle orchestration, injectable only for offline tests, not a CLI backend."""
    def __init__(self, backend, report):
        self.backend=backend; self.report=report; self.stage='preflight'

    def done(self,stage):
        entry=self.report['stages'][STAGES.index(stage)]
        entry['status']='ok'; entry['checks']={key:True for key in CHECKS[stage]}

    def baseline_step(self,operation,callback,*args):
        # No mutable pending operation: only this call can receive a baseline label.
        if self.stage!='baseline': return callback(*args)
        require(type(operation) is str and operation in BASELINE_OPERATIONS, 'invalid_input')
        try:
            return callback(*args)
        except (SeedCommandError,BootstrapInventoryError,BaselineInputError):
            # A pre-wrapped or stale diagnostic is not a fresh baseline input error.
            raise
        except DatabaseEntryError as error:
            wrapped=BaselineInputError(operation,error.entry_class,error.shape,
                                       basename=getattr(error,'basename',None))
            if hasattr(error,'failure_context'):
                wrapped.failure_context=error.failure_context
                wrapped.failure_context_stage=getattr(error,'failure_context_stage',None)
            raise wrapped from None
        except OracleError as error:
            if error.kind=='invalid_input':
                wrapped=BaselineInputError(operation)
                if isinstance(error,SandboxInventoryError) and not hasattr(error,'failure_context'):
                    error.failure_context={'operation':'inventory','site':'scan','bsl_phase':None,
                        'region':error.region,'reason':error.reason}
                    error.failure_context_stage=self.stage
                if hasattr(error,'failure_context'):
                    wrapped.failure_context=error.failure_context
                    wrapped.failure_context_stage=getattr(error,'failure_context_stage',None)
                raise wrapped from None
            raise

    def snapshot(self,database,identifier):
        summary=self.baseline_step('freeze',self.backend.freeze,database,identifier)
        logical=self.baseline_step('observe',self.backend.observe,identifier,
                                   expected_logical(identifier)['designer_version'])
        validate_logical(logical,identifier)
        self.report['snapshots'].append({'id':identifier,'physical':summary,'logical':logical,
            'quiescent':True,'copy_verified':True})

    def paired(self,stage,operation):
        source,control,treatment=COMPARISONS[stage]
        for target,action in ((control,'observe'),(treatment,operation)):
            database=self.backend.clone(source,'writer')
            if stage=='load_cf': self.backend.load_cf(database,1 if target==control else 2)
            else: self.backend.mutate(database,action)
            self.snapshot(database,target)
        self.report['comparisons'].append({'id':stage,'kind':'matched_control','source':source,'control':control,'treatment':treatment,
            'physical':self.backend.compare(source,control,treatment)})
        self.backend.discard(control)

    def artifact(self,identifier):
        self.report['artifacts'].append({'id':identifier,'status':'ok','source':ARTIFACTS[identifier],
            'physical':self.backend.artifact(identifier)})

    def run(self):
        comparison_failure = None
        try:
            for stage in STAGES[:-1]:
                self.stage=stage
                self.backend.begin_stage(stage)
                if stage=='preflight': self.backend.preflight()
                elif stage=='seed_v1': database=self.backend.seed()
                elif stage=='baseline':
                    self.snapshot(database,'baseline')
                    if self.report['schema'] == comparison.SCHEMA:
                        data = self.baseline_step('audit', self.backend.compare_catalog, 'baseline')
                        self.report['storage_contract'] = comparison.bind_capture(data, self.report)
                        self.report['reader_validation'] = comparison.VERDICT
                    elif self.report['schema'] == contract.SCHEMA:
                        data = self.baseline_step('audit', self.backend.audit_contract, 'baseline')
                        self.report['storage_contract'] = contract.bind_capture(data, self.report)
                    else:
                        self.baseline_step('audit', self.backend.audit, 'baseline')
                elif stage in ('create','update','load_cf','delete'):
                    self.paired(stage,{'create':'create','update':'update','delete':'delete'}.get(stage,stage))
                    if stage=='update': self.backend.discard('created')
                    elif stage=='load_cf': self.backend.discard('updated')
                    elif stage=='delete': self.backend.discard('applied')
                elif stage=='apply_cf':
                    database=self.backend.clone('loaded','writer')
                    self.backend.apply(database)
                    self.snapshot(database,'applied')
                    self.report['comparisons'].append({'id':'apply_cf','kind':'observational',
                        'source':'loaded','control':None,'treatment':'applied',
                        'physical':self.backend.compare_pair('loaded','applied')})
                    self.backend.discard('loaded')
                elif stage=='export_cf':
                    self.backend.export_configs(); self.artifact('cf_v1'); self.artifact('cf_v2')
                    self.backend.discard('baseline')
                elif stage=='dump_dt': self.backend.dump_dt(); self.artifact('dt_updated')
                elif stage=='restore_dt': self.snapshot(self.backend.restore(),'restored')
                elif stage=='verify_restore':
                    self.backend.audit('restored')
                    validate_logical(self.backend.observe('deleted',2),'deleted')
                self.done(stage)
            self.report.update(status='ok',failed_stage=None,failure_kind='none')
        except BaseException as error:
            if type(error) is comparison.ComparisonFailure and self.stage == 'baseline':
                comparison_failure = error
            kind=error.kind if isinstance(error,OracleError) and error.kind in FAILURES else 'unexpected_failure'
            if type(error) is comparison.ComparisonFailure:
                kind = 'catalog_comparison_failed' if self.stage == 'baseline' else 'unexpected_failure'
            elif isinstance(error,BaselineInputError):
                kind=('baseline_' + error.operation + ('_invalid_input' if error.entry_class is None else
                    '_entry_' + error.entry_class + '_' + error.shape)) if self.stage=='baseline' else 'unexpected_failure'
            elif isinstance(error,BootstrapInventoryError):
                kind=('seed_bootstrap_inventory_' + error.phase + '_' + error.region + '_' + error.reason) if self.stage=='seed_v1' else 'unexpected_failure'
            elif isinstance(error,SeedCommandError):
                kind=('seed_' + error.operation + '_' + kind) if self.stage=='seed_v1' else 'unexpected_failure'
            if kind in SEED_FAILURES | BOOTSTRAP_INVENTORY_FAILURES and self.stage!='seed_v1': kind='unexpected_failure'
            if kind in BASELINE_FAILURES and self.stage!='baseline': kind='unexpected_failure'
            self.report.update(status='failed',failed_stage=self.stage,failure_kind=kind)
            context=(getattr(error,'failure_context',None)
                     if getattr(error,'failure_context_stage',None)==self.stage else None)
            if context is None and isinstance(error,SandboxInventoryError) and kind!='unexpected_failure':
                context={'operation':'inventory','site':'scan','bsl_phase':None,'region':error.region,'reason':error.reason}
            if context is not None:
                try:
                    validate_failure_context(context,self.stage)
                except OracleError:
                    pass  # A stale or forged context is never exported.
                else:
                    self.report['failure_context']=context

            if isinstance(error,BaselineInputError) and self.stage=='baseline' and hasattr(error,'basename'):
                self.report['rejected_basename']=error.basename
            self.report['stages'][STAGES.index(self.stage)]['status']='failed'
        finally:
            self.backend.begin_stage('cleanup')
            processes,files=self.backend.cleanup()
            self.report['cleanup'].update(native_processes_stopped=processes,raw_files_removed=files)
            entry=self.report['stages'][-1]
            entry['checks']={'native_processes_stopped':processes,'raw_files_removed':files}
            entry['status']='ok' if processes and files else 'failed'
            if not(processes and files) and self.report['status']=='ok':
                self.report.update(status='failed',failed_stage='cleanup',failure_kind='cleanup_unverified')
            if self.report['status']!='ok':
                self.report['artifacts']=[]
                contract.discard_capture(self.report)
                if self.report.get('reader_validation') == 'not_run' and getattr(self.backend, 'reader_attempted', False):
                    self.report['reader_validation'] = 'failed'
                comparison.discard_capture(self.report, comparison_failure)
            if not(processes and files) or self.report['status']=='ok':
                self.report.pop('rejected_basename',None)
                self.report.pop('failure_context',None)
        return self.report


def main():
    # No arbitrary paths, external DB/config/dump arguments, legacy flags or environment backend selection.
    if len(sys.argv)!=3 or sys.argv[1]!='--invocation-nonce' or re.fullmatch('[0-9a-f]{32}',sys.argv[2]) is None:
        return 2
    nonce=sys.argv[2]
    try:
        from inputs import verify_inputs
        provenance=verify_inputs(INPUTS,nonce)
        report=comparison.empty_report(nonce,provenance)
        report=Controller(Native(nonce,provenance),report).run()
        raw=encode(report)
        comparison.validate_report(raw,nonce=nonce,provenance=provenance)
        sys.stdout.buffer.write(raw+b'\n'); sys.stdout.buffer.flush()
        return 0 if report['status']=='ok' else 1
    except BaseException:
        # Never emit arbitrary native exceptions, paths or text, even on protocol failures.
        return 1


if __name__=='__main__':
    raise SystemExit(main())

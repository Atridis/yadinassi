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
    """Account private tmpfs entries with narrowly checked disappearance races.

    Error classifications contain fixed regions/reasons only. Disappearing entry
    stat/child-open races remain tolerated exactly as before; other existing
    rejections remain failures except pinned, owned HOME sockets and an owned
    HOME zero-link entry freshly confirmed absent from the same opened parent.
    """
    require(type(reserve) is int and 0 <= reserve <= MAX_LIVE_BYTES,'artifact_limit')
    sockets={'.X11-unix/X99','runtime/session-bus/bus'}
    total=0; entries=0; home_sockets=0; disappeared=0
    def reject(relative,reason):
        raise SandboxInventoryError(inventory_region(relative),reason)
    def io(relative,action,*,missing=False):
        try: return action()
        except FileNotFoundError as error:
            if missing: return None
            raise SandboxInventoryError(inventory_region(relative),inventory_io_reason(error)) from None
        except OSError as error:
            raise SandboxInventoryError(inventory_region(relative),inventory_io_reason(error)) from None
    def links(relative,info,descriptor,name):
        nonlocal disappeared
        if (info.st_nlink==0 and home_anchor is not None
                and relative.startswith('onec-db-oracle/home/')
                and (info.st_uid,info.st_gid)==(1000,1000)):
            # DirEntry.stat may cache the unlinked inode. Only a fresh lookup
            # relative to this still-open parent can establish disappearance.
            # Any present replacement (even an ordinary owned file) still fails.
            def fresh_entry():
                try: return os.stat(name,dir_fd=descriptor,follow_symlinks=False)
                except FileNotFoundError as error:
                    if error.errno==errno.ENOENT: return None
                    raise
            current=io(relative,fresh_entry)
            if current is None:
                disappeared+=1
                return False
        if info.st_nlink!=1: reject(relative,'hardlink' if info.st_nlink>1 else 'link_count')
        return True
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
                            before=(home_sockets,disappeared)
                            walk(child,relative+'/',depth+1)
                            if (home_sockets,disappeared)!=before:
                                # The new exception is valid only while this path still names the opened directory.
                                try: after=os.stat(entry.name,dir_fd=descriptor,follow_symlinks=False)
                                except OSError: raise OracleError('snapshot_changed') from None
                                require(stat.S_ISDIR(after.st_mode)
                                        and (after.st_dev,after.st_ino)==(actual.st_dev,actual.st_ino),'snapshot_changed')
                        finally: io(relative,lambda: os.close(child))
                    elif stat.S_ISSOCK(info.st_mode):
                        if relative in sockets:
                            if not links(relative,info,descriptor,entry.name): continue
                        elif home_anchor is not None and relative.startswith('onec-db-oracle/home/'):
                            if (info.st_uid,info.st_gid)!=(1000,1000): reject(relative,'unexpected_socket')
                            if not links(relative,info,descriptor,entry.name): continue
                            home_sockets+=1
                            require(home_sockets<=MAX_HOME_SOCKETS,'artifact_limit')
                        else: reject(relative,'unexpected_socket')
                    else:
                        if stat.S_ISLNK(info.st_mode): reject(relative,'symlink')
                        if not stat.S_ISREG(info.st_mode): reject(relative,'special')
                        if not links(relative,info,descriptor,entry.name): continue
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
    def __init__(self, nonce, provenance, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False, numeric_case=None, numeric_rows=False):
        require(type(record_metadata) is bool and type(record_reader) is bool
                and type(params_transport) is bool and type(params_extraction) is bool
                and type(dbnames_identity) is bool and type(config_transport) is bool and type(config_framing) is bool and type(config_marker_census) is bool and type(config_zero_marker_filename) is bool and type(config_entry_reference) is bool and type(config_blob_chain) is bool and type(config_content_decode) is bool and type(config_root_reference_projection) is bool and type(config_catalog_observation) is bool and type(config_catalog_name_binding) is bool and type(config_catalog_standard_binding) is bool and type(config_catalog_identity_binding) is bool and type(config_catalog_field_matrix) is bool and type(config_catalog_attribute_binding) is bool and type(catalog_readonly_binding) is bool
                and sum((record_metadata, record_reader, params_transport, params_extraction, dbnames_identity, config_transport, config_framing, config_marker_census, config_zero_marker_filename, config_entry_reference, config_blob_chain, config_content_decode, config_root_reference_projection, config_catalog_observation, config_catalog_name_binding, config_catalog_standard_binding, config_catalog_identity_binding, config_catalog_field_matrix, config_catalog_attribute_binding, catalog_readonly_binding, reference_case is not None, description_case is not None, numeric_case is not None)) <= 1, 'invalid_input')
        require(reference_case is None or type(reference_case) is str and reference_case in ('distinct_a','distinct_b'), 'invalid_input')
        require(type(reference_codec) is bool and (not reference_codec or reference_case is not None), 'invalid_input')
        require(type(reference_rows) is bool and (not reference_rows or reference_case is not None)
                and not (reference_rows and reference_codec), 'invalid_input')
        require(description_case is None or type(description_case) is str and description_case in ('description8','description17'), 'invalid_input')
        require(type(description_rows) is bool and (not description_rows or description_case is not None), 'invalid_input')
        require(type(params_slots) is bool and (not params_slots or description_case is not None)
                and not (params_slots and description_rows), 'invalid_input')
        require(numeric_case is None or type(numeric_case) is str and numeric_case in ('number3','number6'), 'invalid_input')
        require(type(numeric_rows) is bool and (not numeric_rows or numeric_case is not None),'invalid_input')
        self.numeric_rows = numeric_rows
        self.numeric_case = numeric_case
        self.params_slots = params_slots
        # Reuse the exact schema3 observer rendering, not its public typed reader.
        self.description_rows = description_rows or params_slots
        self.description_case = description_case
        self.description_policy = None
        self.description_witness = None
        if numeric_case is not None:
            if numeric_rows:
                import catalog_numeric_code_rows_policy as numeric_policy
            else:
                import catalog_numeric_code_policy as numeric_policy
            self.description_policy = numeric_policy
        elif description_case is not None:
            if params_slots:
                import params_slot_policy as description_policy
            elif description_rows:
                import catalog_description_rows as description_policy
            else:
                import catalog_description_policy as description_policy
            self.description_policy = description_policy
        self.reference_rows = reference_rows
        self.reference_codec = reference_codec
        self.reference_case = reference_case
        self.reference_witness = None
        self.reference_installation = None
        self.reference_module_sha256 = None
        self.observation = None
        if record_metadata or record_reader or params_transport or params_extraction or dbnames_identity or config_transport or config_framing or config_marker_census or config_zero_marker_filename or config_entry_reference or config_blob_chain or config_content_decode or config_root_reference_projection or config_catalog_observation or config_catalog_name_binding or config_catalog_standard_binding or config_catalog_identity_binding or config_catalog_field_matrix or config_catalog_attribute_binding or catalog_readonly_binding or reference_case is not None:
            import record_observation
            self.observation = record_observation
        self.params_policy = None
        if config_catalog_attribute_binding:
            import config_catalog_attribute_binding as selected
            self.params_policy = selected
        elif config_catalog_field_matrix:
            import config_catalog_field_matrix as selected
            self.params_policy = selected
        elif config_catalog_identity_binding:
            import config_catalog_identity_binding as selected
            self.params_policy = selected
        elif config_catalog_standard_binding:
            import config_catalog_standard_binding as selected
            self.params_policy = selected
        elif config_catalog_name_binding:
            import config_catalog_name_binding as selected
            self.params_policy = selected
        elif config_catalog_observation:
            import config_catalog_observation as selected
            self.params_policy = selected
        elif config_root_reference_projection:
            import config_root_reference_projection as selected
            self.params_policy = selected
        elif config_content_decode:
            import config_content_decode as selected
            self.params_policy = selected
        elif config_blob_chain:
            import config_blob_chain as selected
            self.params_policy = selected
        elif config_entry_reference:
            import config_entry_reference as selected
            self.params_policy = selected
        elif config_zero_marker_filename:
            import config_zero_marker_filename as selected
            self.params_policy = selected
        elif config_marker_census:
            import config_marker_census as selected
            self.params_policy = selected
        elif config_framing:
            import config_framing as selected
            self.params_policy = selected
        elif config_transport:
            import config_observation as selected
            self.params_policy = selected
        elif dbnames_identity:
            import dbnames_identity as identity_policy
            self.params_policy = identity_policy
        elif params_extraction:
            import params_extraction as extraction_policy
            self.params_policy = extraction_policy
        elif params_transport:
            import params_observation
            self.params_policy = params_observation
        self.catalog_binding = catalog_readonly_binding or reference_case is not None
        self.catalog_field_matrix = config_catalog_field_matrix or config_catalog_attribute_binding or catalog_readonly_binding or reference_case is not None
        self.identity_manifest = None; self.identity_baseline_verified = False
        self.record_policy = None; self.record_module = None
        self.record_pending = None; self.record_names = None; self.record_profile = None
        if reference_case is not None:
            if reference_rows:
                import catalog_reference_rows as binding_policy
            elif reference_codec:
                import catalog_reference_codec as binding_policy
            else:
                import catalog_reference_identity as binding_policy
            import catalog_binding_reader
            self.record_policy = binding_policy
            self.record_module = catalog_binding_reader
        elif catalog_readonly_binding:
            import catalog_readonly_binding as binding_policy
            import catalog_binding_reader
            self.record_policy = binding_policy
            self.record_module = catalog_binding_reader
        elif record_reader:
            import record_validation
            self.record_policy = record_validation
            self.record_module = record_validation.load_reader(Path(__file__).with_name('filedb_records.py'))
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

    def command_stages(self):
        # Do not import or admit the observation operation in the default lane.
        return ({**COMMAND_STAGES, 'enterprise_audit_record_metadata': ('baseline',)}
                if self.observation is not None else COMMAND_STAGES)

    def check_failure_context(self, value, stage):
        validator = (self.observation.validate_failure_context if self.observation is not None
                     else validate_failure_context)
        return validator(value, stage)

    @contextmanager
    def command_context(self, operation):
        commands = self.command_stages()
        require(type(operation) is str and operation in commands, 'invalid_input')
        entered_stage=self.stage
        try:
            yield
        except BaseException as original:
            error=original if isinstance(original,OracleError) else OracleError('unexpected_failure')
            # No mutable pending operation survives a launch or stage transition.
            if self.stage==entered_stage and entered_stage in commands[operation]:
                context={'operation':operation,'site':getattr(error,'oracle_site','operation'),
                    'bsl_phase':getattr(error,'bsl_phase',None),
                    'region':error.region if isinstance(error,SandboxInventoryError) else None,
                    'reason':error.reason if isinstance(error,SandboxInventoryError) else None}
                if operation in ('snapshot_freeze','snapshot_clone') and isinstance(error,DatabaseEntryError):
                    context.update(entry_class=error.entry_class,entry_shape=error.shape)
                self.check_failure_context(context,entered_stage)
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
        require(type(operation) is str and 'enterprise_'+operation in self.command_stages(),'invalid_input')
        if operation in ('audit_contract', 'audit_record_metadata'):
            require(self.stage == 'baseline', 'invalid_input')
        with self.command_context('enterprise_'+operation):
            return self._enterprise(database,operation,token=token)

    def _enterprise(self, database, operation, *, token=None):
        token=secrets.token_hex(16) if token is None else token
        require(type(token) is str and re.fullmatch('[0-9a-f]{32}',token) is not None,'invalid_input')
        control=self.evidence/'control.json'; result=self.evidence/'result.json'
        completion=self.evidence/'completion.json'; pending=self.evidence/'completion.pending.json'
        numeric_mode = getattr(self, 'numeric_case', None) is not None
        description_path = self.evidence / ('numeric-code-observation.json' if numeric_mode else 'description-observation.json')
        description_mode = numeric_mode or getattr(self, 'description_case', None) is not None
        if description_mode:
            absent(description_path)
            self.description_witness = None
        reference_path = self.evidence / 'reference-observation.json'
        reference_mode = getattr(self, 'reference_case', None) is not None
        if reference_mode:
            absent(reference_path)
            self.reference_witness = None
        reference_observation = None
        description_observation = None
        absent(control,result,completion,pending)
        control.write_text(json.dumps({'schema':1,'nonce':self.nonce,'token':token,'operation':operation}),encoding='utf-8')
        user=None if operation=='bootstrap' else (SETUP_USER if operation in ('audit','audit_contract','audit_record_metadata') else CRUD_USER)
        try:
            log=self.evidence/f'{self.counter+1:03}-{operation}.log'; absent(log)
            self.process(self.command('ENTERPRISE',database,user)+['/RunModeManagedApplication',
                '/C',token,'/Out',str(log)],operation)
            observed = operation == 'audit_record_metadata'
            require(not observed or self.observation is not None,'invalid_input')
            if operation in ('audit_contract','audit_record_metadata'):
                absent(pending)
            finish = self.observation.completion_marker if observed else completion_marker
            finished=finish(regular_bytes(completion,4096),nonce=self.nonce,token=token,operation=operation)
            if reference_mode and operation in ('create','update','delete','observe'):
                from catalog_reference_native import validate_witness, WITNESS_LIMIT
                if finished['status'] != 'error' or reference_path.exists():
                    raw_reference = regular_bytes(reference_path, WITNESS_LIMIT)
                    try:
                        witness = validate_witness(raw_reference, nonce=self.nonce, token=token,
                            case=self.reference_case, operation=operation)
                    except ValueError:
                        raise OracleError('invalid_marker') from None
                    if finished['status'] != 'error':
                        require(witness.status == 'ok', 'invalid_marker')
                        reference_observation = (witness, hashlib.sha256(raw_reference).hexdigest(), token)
            elif reference_mode:
                absent(reference_path)
            if description_mode and finished['status'] != 'error' and operation in ('create','update','observe'):
                if numeric_mode:
                    from catalog_numeric_code_measurement import validate_witness as validate_description, WITNESS_LIMIT
                    witness_options = {'case':self.numeric_case}
                else:
                    from catalog_description_measurement import validate_witness as validate_description, WITNESS_LIMIT
                    witness_options = {'case':self.description_case,'rows':getattr(self,'description_rows',False)}
                try:
                    description_observation = validate_description(regular_bytes(description_path, WITNESS_LIMIT),
                        nonce=self.nonce, token=token, operation=operation, **witness_options)
                except ValueError:
                    raise OracleError('invalid_marker') from None
            elif description_mode and finished['status'] != 'error':
                absent(description_path)
            if finished['status']=='error':
                kind = ('artifact_limit' if ((operation == 'audit_contract' and finished['phase'] == 'contract_limit')
                    or (observed and finished['phase'] == 'record_limit')) else 'process_failed')
                error=OracleError(kind); error.oracle_site='result'; error.bsl_phase=finished['phase']
                raise error
            if observed:
                data=self.observation.marker(regular_bytes(result,MAX_REPORT_BYTES),
                    nonce=self.nonce,token=token,operation=operation)
            else:
                marker_reader = self.description_policy.marker if numeric_mode else marker
                data=marker_reader(regular_bytes(result,MAX_REPORT_BYTES),nonce=self.nonce,token=token,operation=operation,
                            contract_version=comparison.SCHEMA)
            self.provenance['actual_version']=data['actual_version']
            if description_observation is not None:
                self.description_witness = description_observation
            if reference_observation is not None:
                self.reference_witness = reference_observation
                if operation == 'create':
                    require(witness.after_present and not witness.before_present, 'invalid_marker')
                    self.reference_installation = reference_observation
            return data
        finally:
            control.unlink(missing_ok=True); result.unlink(missing_ok=True)
            completion.unlink(missing_ok=True); pending.unlink(missing_ok=True)
            if reference_mode: reference_path.unlink(missing_ok=True)
            if description_mode: description_path.unlink(missing_ok=True)

    def seed(self):
        with self.seed_command('create'):
            database=self.create_db('seed')
        native=self.root/'native-empty'; absent(native)
        with self.seed_command('dump_empty'):
            self.batch(database,['/DumpConfigToFiles',str(native),'-Format','Hierarchical'],'dump-empty',None)
        try:
            inject(native,self.v1,nonce=self.nonce,evidence=self.evidence,
                   **({'description_rows': True} if getattr(self, 'description_rows', False) else {}),
                   **({'reference_case': self.reference_case} if getattr(self, 'reference_case', None) is not None else {}),
                   **({'catalog_field_matrix': True} if getattr(self, 'catalog_field_matrix', False) else {}),
                   **({'description_case': self.description_case} if getattr(self, 'description_case', None) is not None else {}),
                   **({'numeric_case': self.numeric_case} if getattr(self, 'numeric_case', None) is not None else {}))
            if getattr(self, 'reference_case', None) is not None:
                server = self.v1 / 'CommonModules/NativeOracleServer/Ext/Module.bsl'
                self.reference_module_sha256 = self.record_policy.canonical_module_sha256(regular_bytes(server,1048576))
            promote_v2(self.v1,self.v2,
                       **({'catalog_field_matrix': True} if getattr(self, 'catalog_field_matrix', False) else {}),
                   **({'description_case': self.description_case} if getattr(self, 'description_case', None) is not None else {}),
                   **({'numeric_case': self.numeric_case} if getattr(self, 'numeric_case', None) is not None else {}))
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
            expected = self.v1 if version == 1 else self.v2
            verify_redump(expected,target,version=version,
                          **({'catalog_field_matrix': True} if getattr(self, 'catalog_field_matrix', False) else {}),
                   **({'description_case': self.description_case} if getattr(self, 'description_case', None) is not None else {}),
                   **({'numeric_case': self.numeric_case} if getattr(self, 'numeric_case', None) is not None else {}))
            manifest_policy = (self.record_policy if getattr(self, 'catalog_binding', False)
                               else getattr(self, 'params_policy', None))
            if (manifest_policy is not None and manifest_policy.SCHEMA in (9, 27, 29, 31, 33, 35, 37, 39, 42, 45)
                    and version == 1 and self.stage in ('seed_v1', 'baseline')):
                manifest = manifest_policy.build_identity_manifest(
                    expected, target, nonce=self.nonce, version=version)
                if self.stage == 'seed_v1':
                    require(self.identity_manifest is None, 'metadata_rejected')
                    self.identity_manifest = manifest
                else:
                    require(self.identity_manifest is not None and manifest == self.identity_manifest,
                            'metadata_rejected')
                    self.identity_baseline_verified = True
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
        if getattr(self, 'description_policy', None) is not None and identifier in self.description_policy.TARGETS:
            return self.observe_record_state(identifier, designer)
        if self.record_policy is not None and identifier in self.record_policy.TARGETS:
            return self.observe_record_state(identifier, designer)
        with self.temporary_clone(identifier,'observer') as database:
            # Designer redump and runtime read are separate clone sessions. Neither touches frozen bytes.
            self.redump(database,designer)
            data=self.enterprise(database,'observe')
            return logical_from_marker(data,designer)

    def _clear_numeric_private_state(self):
        # A failed acquisition must not retain a private sidecar or its frozen
        # pending evidence in memory. Other profiles retain their old behavior.
        if getattr(self, 'numeric_case', None) is not None:
            self.description_witness = None
            self.record_pending = None

    def observe_record_state(self, identifier, designer):
        try:
            """Keep the existing redump/observe launch order; freeze only their clone."""
            policy = getattr(self, 'description_policy', None) or self.record_policy
            require(policy is not None and identifier in policy.TARGETS
                    and self.stage == policy.STAGES[identifier]
                    and designer == (expected_logical(identifier)['designer_version'] if (getattr(self, 'description_rows', False) or getattr(self, 'numeric_case', None) is not None) else 1)
                    and self.record_pending is None, 'invalid_input')
            frozen = self.artifacts / 'record_observer_frozen'
            absent(frozen)
            try:
                with self.temporary_clone(identifier, 'observer') as database:
                    expected = self.physical_summary(self.artifacts / identifier / '1Cv8.1CD')
                    origin = self.physical_summary(database / '1Cv8.1CD')
                    require(origin == expected, 'snapshot_changed')
                    origin = {key: origin[key] for key in ('bytes', 'sha256')}
                    token = secrets.token_hex(16)
                    self.redump(database, designer)
                    data = self.enterprise(database, 'observe', token=token)
                    logical = logical_from_marker(data, designer)
                    logical_validator = self.description_policy.validate_logical if getattr(self,'numeric_case',None) is not None else validate_logical
                    logical_validator(logical, identifier)
                    with self.command_context('snapshot_freeze'):
                        self.budgets(self.physical_summary(database / '1Cv8.1CD')['bytes'])
                        summary = freeze_database(database, frozen, quiescent=self.quiescent)
                        self.budgets()
                    evidence = {'snapshot': identifier, 'token': token, 'origin': origin,
                        'postimage': {key: summary[key] for key in ('bytes', 'sha256')}, 'logical': logical}
                    if getattr(self, 'description_policy', None) is not None:
                        require(self.description_witness is not None and self.description_witness.token == token, 'invalid_marker')
                        evidence['description'] = self.description_witness
                        self.description_witness = None
                    if getattr(self, 'reference_case', None) is not None:
                        require(self.reference_witness is not None and self.reference_witness[2] == token, 'invalid_marker')
                        evidence['reference'] = self.reference_witness
                        self.reference_witness = None
                # The writable observer has been removed before this pending evidence.
                # Baseline waits only until its already scheduled metadata auditor runs.
                self.record_pending = (identifier, frozen, evidence)
                return logical
            except BaseException:
                try: self.remove(frozen)
                except BaseException: pass
                raise
        except BaseException:
            if getattr(self, 'numeric_case', None) is not None:
                self.description_witness = None
                self.record_pending = None
            raise

    def compare_params_slot_state(self, identifier, report):
        policy = self.description_policy
        require(getattr(self, 'params_slots', False) and policy is not None
                and identifier in policy.TARGETS and self.record_pending is not None
                and self.record_pending[0] == identifier, 'invalid_input')
        _, frozen, evidence = self.record_pending
        try:
            expected = next(item for item in report['snapshots'] if item['id'] == identifier)
            require(evidence['origin'] == {key:expected['physical'][key] for key in ('bytes','sha256')}, 'snapshot_changed')
            from snapshots import inspect_frozen_catalog
            from params_slot_observer import observe
            self.reader_attempted = True
            measured, projection = inspect_frozen_catalog(frozen, quiescent=self.quiescent,
                read_catalog=observe, limits=filedb_catalog.CatalogLimits(), before_read=self.remaining)
            require(measured == evidence['postimage'], 'snapshot_changed')
            clean = {key:value for key,value in evidence.items() if key != 'description'}
            result = policy.bind_state(clean, report, projection)
        except BaseException:
            try: self.remove(frozen)
            except BaseException: pass
            self.record_pending = None
            raise
        else:
            self.remove(frozen)
            self.record_pending = None
            return result

    def compare_numeric_code_state(self, identifier, report):
        policy = self.description_policy
        require(getattr(self,'numeric_case',None) is not None and policy is not None
                and identifier in policy.TARGETS and self.record_pending is not None
                and self.record_pending[0] == identifier, 'invalid_input')
        _, frozen, evidence = self.record_pending
        try:
            expected = next(item for item in report['snapshots'] if item['id'] == identifier)
            require(evidence['origin'] == {key:expected['physical'][key] for key in ('bytes','sha256')}, 'snapshot_changed')
            witness = evidence['description']
            observation = None
            if identifier != 'baseline':
                from snapshots import inspect_frozen_catalog
                if getattr(self,'numeric_rows',False):
                    from catalog_numeric_code_rows_reader import read_numeric_code_rows as read_numeric_code
                else:
                    from catalog_numeric_code_physical import read_numeric_code
                self.reader_attempted = True
                def read_selected(read_at,size,*,limits):
                    return read_numeric_code(read_at,size,catalog_name='NativeOracleItems',limits=limits)
                measured, observation = inspect_frozen_catalog(frozen,quiescent=self.quiescent,
                    read_catalog=read_selected,limits=filedb_catalog.CatalogLimits(),before_read=self.remaining)
                require(measured == evidence['postimage'],'snapshot_changed')
            else:
                summary = self.physical_summary(frozen/'1Cv8.1CD')
                require({key:summary[key] for key in ('bytes','sha256')} == evidence['postimage'],'snapshot_changed')
            clean = {key:value for key,value in evidence.items() if key != 'description'}
            result = policy.bind_state(clean,report,observation,witness)
        except BaseException:
            try: self.remove(frozen)
            except BaseException: pass
            self.record_pending = None
            raise
        else:
            self.remove(frozen)
            self.record_pending = None
            return result

    def compare_description_state(self, identifier, report):
        if getattr(self,'numeric_case',None) is not None:
            return self.compare_numeric_code_state(identifier,report)
        if getattr(self, 'params_slots', False):
            return self.compare_params_slot_state(identifier, report)
        policy = self.description_policy
        require(policy is not None and identifier in policy.TARGETS
                and self.record_pending is not None and self.record_pending[0] == identifier, 'invalid_input')
        _, frozen, evidence = self.record_pending
        diagnostic_mode = getattr(self, 'description_rows', False)
        phase = 'postimage'
        try:
            expected = next(item for item in report['snapshots'] if item['id'] == identifier)
            require(evidence['origin'] == {key: expected['physical'][key] for key in ('bytes','sha256')}, 'snapshot_changed')
            witness = evidence['description']
            observation = None
            typed_uuid = None
            if identifier != 'baseline':
                from snapshots import inspect_frozen_catalog
                if getattr(self, 'description_rows', False):
                    from catalog_description_physical import read_description_rows as read_description
                else:
                    from catalog_description_physical import read_description
                self.reader_attempted = True
                reader_error = None
                failure_sentinel = object()
                def read_selected(read_at, size, *, limits):
                    nonlocal reader_error
                    try:
                        return read_description(read_at, size, catalog_name='NativeOracleItems', limits=limits)
                    except BaseException as error:
                        if not diagnostic_mode:
                            raise
                        # Keep the exact private exception, not text/attributes.
                        # Returning a unique sentinel lets the frozen boundary
                        # finish before we bind its measured digest to evidence.
                        reader_error = error
                        return failure_sentinel
                measured, observation = inspect_frozen_catalog(frozen, quiescent=self.quiescent,
                    read_catalog=read_selected, limits=filedb_catalog.CatalogLimits(), before_read=self.remaining)
                require(measured == evidence['postimage'], 'snapshot_changed')
                if diagnostic_mode and reader_error is not None:
                    require(observation is failure_sentinel, 'unexpected_failure')
                    phase = 'public_reader'
                    raise reader_error
                if getattr(self, 'description_rows', False):
                    observation, typed_uuid = observation
            else:
                summary = self.physical_summary(frozen / '1Cv8.1CD')
                require({key:summary[key] for key in ('bytes','sha256')} == evidence['postimage'], 'snapshot_changed')
            clean = {key:value for key,value in evidence.items() if key != 'description'}
            phase = 'comparison'
            result = policy.bind_state(identifier, clean, observation, witness, report,
                **({'typed_uuid':typed_uuid} if getattr(self, 'description_rows', False) else {}))
        except BaseException as error:
            removed = True
            try: self.remove(frozen)
            except BaseException: removed = False
            self.record_pending = None
            if diagnostic_mode and removed:
                raise policy.wrap_failure(error, snapshot=identifier, phase=phase) from None
            raise
        else:
            self.remove(frozen)
            self.record_pending = None
            return result

    def prepare_record_profile(self, evidence, report):
        if getattr(self, 'reference_case', None) is not None:
            expected = self.record_policy.rendered_module_sha256(self.nonce, self.reference_case)
            require(self.reference_module_sha256 == expected, 'provenance_mismatch')
        capture, self.record_names, self.record_profile = self.record_policy.begin_capture(
            evidence, report, self.record_module)
        return capture

    def compare_record_state(self, identifier, report):
        policy = self.record_policy
        require(policy is not None and identifier in policy.TARGETS
                and self.record_pending is not None and self.record_pending[0] == identifier
                and self.record_profile is not None, 'invalid_input')
        _, frozen, evidence = self.record_pending
        try:
            from snapshots import inspect_frozen_catalog
            expected = next(item for item in report['snapshots'] if item['id'] == identifier)
            require(evidence['origin'] == {key: expected['physical'][key] for key in ('bytes','sha256')},
                    'snapshot_changed')
            framings = []
            permutations = []
            codec_results = []
            projection_results = []
            for path, summary in ((self.artifacts / identifier, evidence['origin']),
                                  (frozen, evidence['postimage'])):
                def read_selected(read_at, size, *, limits):
                    if getattr(self, 'reference_rows', False):
                        return self.record_module.read_catalog_rows(read_at, size,
                            catalog_name=self.record_profile, limits=limits)
                    if getattr(self, 'catalog_binding', False):
                        return self.record_module.read_catalog_binding(read_at, size,
                            catalog_name=self.record_profile, limits=limits)
                    return self.record_module.read_records(read_at, size, profile=self.record_profile,
                        limits=self.record_module.RecordLimits(max_active_records=1), catalog_limits=limits)
                self.reader_attempted = True
                try:
                    measured, rows = inspect_frozen_catalog(path, quiescent=self.quiescent,
                        read_catalog=read_selected, limits=filedb_catalog.CatalogLimits(), before_read=self.remaining)
                except filedb_catalog.CatalogError as error:
                    raise policy.reader_failure(error) from None
                require(measured == summary, 'snapshot_changed')
                if getattr(self, 'reference_rows', False):
                    import catalog_reference_rows as projection_policy
                    typed_rows = rows
                    rows = projection_policy.admit_rows(typed_rows, self.record_module)
                framings.append(policy.compare_values(rows, identifier, self.record_names, self.record_module))
                if getattr(self, 'reference_case', None) is not None:
                    witness, witness_digest, witness_token = evidence['reference']
                    require(witness_token == evidence['token'], 'invalid_marker')
                    permutations.append(policy.measure_reference(rows, identifier, self.record_names, witness.actual_uuid or None))
                    if getattr(self, 'reference_codec', False) or getattr(self, 'reference_rows', False):
                        verdict = policy.verify_reference(rows, identifier, self.record_names, witness.actual_uuid or None)
                        if verdict != ('NN' if identifier == 'baseline' else 'TT'):
                            policy.fail('reference_bytes')
                        codec_results.append(verdict)
                    if getattr(self, 'reference_rows', False):
                        projection_results.append(projection_policy.verify_projection(
                            typed_rows, identifier, witness.actual_uuid or None))
                        del typed_rows
                # Do not retain either private catalog/row object beyond its own comparison.
                del rows
            clean_evidence = {key:value for key,value in evidence.items() if key != 'reference'}
            result = policy.bind_state(identifier, clean_evidence, report, *framings)
            if getattr(self, 'reference_codec', False) or getattr(self, 'reference_rows', False):
                require(len(codec_results) == 2, 'invalid_marker')
                result['codec'] = ''.join(codec_results)
            if getattr(self, 'reference_rows', False):
                require(len(projection_results) == 2, 'invalid_marker')
                result['projection'] = ''.join(projection_results)
            if getattr(self, 'reference_case', None) is not None:
                if len(permutations) != 2 or permutations[0] != permutations[1]:
                    policy.fail('reference_permutation')
                permutation = permutations[0]
                result['reference'] = {'witness_sha256': witness_digest,
                    'before': witness.before, 'after': witness.after,
                    'before_present': witness.before_present, 'after_present': witness.after_present,
                    'permutation': permutation,
                    'hypothesis_match': None if permutation is None else permutation == policy.TOOL1CD}
                policy._validate_reference(result['reference'], identifier)
                if identifier == 'created':
                    require(self.reference_installation is not None, 'invalid_marker')
                    installed, installed_digest, installed_token = self.reference_installation
                    require(installed.actual_uuid == witness.actual_uuid and installed_token != witness_token, 'invalid_marker')
                    report['record_readback']['installation'] = {'status':'succeeded',
                        'token':installed_token, 'witness_sha256':installed_digest}
                    self.reference_installation = None
                earlier = report['record_readback']['states']
                if identifier == 'updated' and earlier[1]['reference']['permutation'] != permutation:
                    policy.fail('reference_permutation')
        except BaseException:
            try: self.remove(frozen)
            except BaseException: pass
            self.record_pending = None
            raise
        else:
            self.remove(frozen)
            self.record_pending = None
            return result

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
                    native, projected = comparison.project_catalog_ascii_fields(catalog, data['storage_names'])
                except comparison.ComparisonFailure as error:
                    if type(error) is comparison.ComparisonFailure and (error.category, error.code) == ('name_mismatch', 'missing_table'):
                        raise comparison.missing_table_failure(catalog,
                            {'marker': data, 'origin': origin, 'postimage': summary},
                            nonce=self.nonce, provenance=self.provenance, baseline=baseline,
                            before_scan=self.remaining) from None
                    if type(error) is comparison.ComparisonFailure and (error.category, error.code) == ('name_mismatch', 'field_names_differ'):
                        raise comparison.field_names_ascii_fields_failure(catalog,
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

    def observe_record_metadata(self, identifier):
        """One baseline metadata call; a fixed owned reader on the frozen postimage."""
        params_policy = getattr(self, 'params_policy', None)
        policy = params_policy or self.observation
        require(policy is not None and self.stage == 'baseline' and identifier == 'baseline', 'invalid_input')
        if params_policy is not None and params_policy.SCHEMA in (9, 27, 29, 31, 33, 35):
            require(self.identity_baseline_verified and self.identity_manifest is not None,
                    'metadata_rejected')
        with self.temporary_clone(identifier, 'auditor') as database:
            baseline = self.physical_summary(self.artifacts / identifier / '1Cv8.1CD')
            origin = self.physical_summary(database / '1Cv8.1CD')
            if origin != baseline:
                raise policy.ObservationFailure('io_or_change', 'origin_changed')
            token = secrets.token_hex(16)
            origin = {'nonce': self.nonce, 'token': token, 'clone': 'auditor',
                      'bytes': origin['bytes'], 'sha256': origin['sha256']}
            data = self.enterprise(database, policy.OPERATION, token=token)
            frozen = self.artifacts / 'auditor_frozen'
            absent(frozen)
            try:
                with self.command_context('snapshot_freeze'):
                    # Reserve postimage while both baseline and writable clone exist.
                    self.budgets(self.physical_summary(database / '1Cv8.1CD')['bytes'])
                    postimage = freeze_database(database, frozen, quiescent=self.quiescent)
                    self.budgets()
                try:
                    from snapshots import inspect_frozen_catalog
                    self.reader_attempted = True
                    summary, catalog = inspect_frozen_catalog(frozen, quiescent=self.quiescent,
                        read_catalog=(policy.read_owned_projection if params_policy is not None and params_policy.SCHEMA in (25, 27, 29, 31, 33, 35)
                            else policy.read_projection if params_policy is not None else filedb_catalog.read_catalog),
                        limits=filedb_catalog.CatalogLimits(),
                        before_read=self.remaining)
                except filedb_catalog.CatalogError as error:
                    raise policy.reader_failure(error) from None
                except OracleError as error:
                    if error.kind in ('snapshot_changed', 'snapshot_not_quiescent', 'artifact_missing', 'invalid_input'):
                        raise policy.ObservationFailure('io_or_change', error.kind) from None
                    if error.kind == 'artifact_limit':
                        raise policy.ObservationFailure('resource_limit', 'projection_limit') from None
                    raise
                if summary != {key: postimage[key] for key in ('bytes', 'sha256')}:
                    raise policy.ObservationFailure('io_or_change', 'postimage_changed')
                # System-table selection is fixed and independent of native names.
                if params_policy is not None:
                    projected = catalog
                else:
                    _, projected = policy.project_catalog(catalog, data['record_metadata'])
                evidence = {'marker': data, 'origin': origin, 'postimage': summary, 'reader': projected}
                if getattr(self, 'catalog_binding', False):
                    require(self.identity_baseline_verified and self.identity_manifest is not None,
                            'metadata_rejected')
                    evidence['identity_manifest'] = self.identity_manifest
                if params_policy is not None and params_policy.SCHEMA in (9, 27, 29, 31, 33, 35):
                    require(self.identity_baseline_verified and self.identity_manifest is not None,
                            'metadata_rejected')
                    evidence['identity_manifest'] = self.identity_manifest
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
        self._clear_numeric_private_state()
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
        self.observation = None
        self.record_policy = None
        self.params_policy = None
        self.description_policy = None
        if report.get('schema') == 62:
            import catalog_numeric_code_rows_policy
            self.description_policy = catalog_numeric_code_rows_policy
        elif report.get('schema') == 59:
            import catalog_numeric_code_policy
            self.description_policy = catalog_numeric_code_policy
        elif report.get('schema') == 56:
            import params_slot_policy
            self.description_policy = params_slot_policy
        elif report.get('schema') == 53:
            import catalog_description_rows
            self.description_policy = catalog_description_rows
        elif report.get('schema') == 50:
            import catalog_description_policy
            self.description_policy = catalog_description_policy
        if report.get('schema') == 35:
            import config_catalog_attribute_binding
            self.params_policy = config_catalog_attribute_binding
        elif report.get('schema') == 33:
            import config_catalog_field_matrix
            self.params_policy = config_catalog_field_matrix
        elif report.get('schema') == 31:
            import config_catalog_identity_binding
            self.params_policy = config_catalog_identity_binding
        elif report.get('schema') == 29:
            import config_catalog_standard_binding
            self.params_policy = config_catalog_standard_binding
        elif report.get('schema') == 27:
            import config_catalog_name_binding
            self.params_policy = config_catalog_name_binding
        elif report.get('schema') == 25:
            import config_catalog_observation
            self.params_policy = config_catalog_observation
        elif report.get('schema') == 23:
            import config_root_reference_projection
            self.params_policy = config_root_reference_projection
        elif report.get('schema') == 17:
            import config_content_decode
            self.params_policy = config_content_decode
        elif report.get('schema') == 15:
            import config_blob_chain
            self.params_policy = config_blob_chain
        elif report.get('schema') == 14:
            import config_entry_reference
            self.params_policy = config_entry_reference
        elif report.get('schema') == 13:
            import config_zero_marker_filename
            self.params_policy = config_zero_marker_filename
        elif report.get('schema') == 12:
            import config_marker_census
            self.params_policy = config_marker_census
        elif report.get('schema') == 11:
            import config_framing
            self.params_policy = config_framing
        elif report.get('schema') == 10:
            import config_observation
            self.params_policy = config_observation
        elif report.get('schema') == 9:
            import dbnames_identity
            self.params_policy = dbnames_identity
        elif report.get('schema') == 8:
            import params_extraction
            self.params_policy = params_extraction
        elif report.get('schema') == 7:
            import params_observation
            self.params_policy = params_observation
        if report.get('schema') == 45:
            import catalog_reference_rows
            self.record_policy = catalog_reference_rows
        elif report.get('schema') == 42:
            import catalog_reference_codec
            self.record_policy = catalog_reference_codec
        elif report.get('schema') == 39:
            import catalog_reference_identity
            self.record_policy = catalog_reference_identity
        elif report.get('schema') == 37:
            import catalog_readonly_binding
            self.record_policy = catalog_readonly_binding
        elif report.get('schema') == 6:
            import record_validation
            self.record_policy = record_validation
        if report.get('schema') in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 23, 25, 27, 29, 31, 33, 35, 37, 39, 42, 45):
            import record_observation
            self.observation = record_observation

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
        logical_validator = self.description_policy.validate_logical if self.report.get('schema') in (59,62) else validate_logical
        logical_validator(logical,identifier)
        self.report['snapshots'].append({'id':identifier,'physical':summary,'logical':logical,
            'quiescent':True,'copy_verified':True})
        if self.description_policy is not None and identifier in self.description_policy.TARGETS:
            state = self.backend.compare_description_state(identifier, self.report)
            key = 'numeric_code_rows_measurement' if self.report['schema'] == 62 else 'numeric_code_measurement' if self.report['schema'] == 59 else 'params_slot_measurement' if self.report['schema'] == 56 else 'description_measurement'
            self.report[key]['states'].append(state)
        if self.record_policy is not None and identifier in ('created','updated'):
            state = self.backend.compare_record_state(identifier, self.report)
            self.report['record_readback']['states'].append(state)
            if identifier == 'updated':
                self.report['record_validation'] = self.record_policy.VERDICT

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
        observation_failure = None
        readback_failure = None
        params_failure = None
        description_failure = None
        try:
            for stage in STAGES[:-1]:
                self.stage=stage
                self.backend.begin_stage(stage)
                if stage=='preflight': self.backend.preflight()
                elif stage=='seed_v1': database=self.backend.seed()
                elif stage=='baseline':
                    self.snapshot(database,'baseline')
                    if self.params_policy is not None:
                        data = self.baseline_step('audit', self.backend.observe_record_metadata, 'baseline')
                        capture_key = ('config_catalog_attribute_binding' if self.report['schema'] == 35 else 'config_catalog_field_matrix' if self.report['schema'] == 33 else 'config_catalog_identity_binding' if self.report['schema'] == 31 else 'config_catalog_standard_binding' if self.report['schema'] == 29 else 'config_catalog_name_binding' if self.report['schema'] == 27 else 'config_catalog_observation' if self.report['schema'] == 25 else 'config_root_reference_projection' if self.report['schema'] == 23 else 'config_content_decode' if self.report['schema'] == 17 else 'config_blob_chain' if self.report['schema'] == 15 else 'config_entry_reference' if self.report['schema'] == 14 else 'config_zero_marker_filename' if self.report['schema'] == 13 else 'config_marker_census' if self.report['schema'] == 12 else 'config_framing' if self.report['schema'] == 11 else 'config_observation' if self.report['schema'] == 10 else 'dbnames_identity' if self.report['schema'] == 9 else
                            'params_extraction' if self.report['schema'] == 8 else 'params_observation')
                        validation_key = ('mapping_validation' if self.report['schema'] == 9 else
                            'extraction_validation' if self.report['schema'] == 8 else 'observation_validation')
                        self.report[capture_key] = self.params_policy.bind_capture(data, self.report)
                        self.report['reader_validation'] = self.report[validation_key] = self.params_policy.VERDICT
                        if self.report['schema'] in (17, 23, 25, 27, 29, 31, 33, 35):
                            self.report['decompression_validation'] = self.params_policy.DECOMPRESSION_VERDICT
                        if self.report['schema'] == 9:
                            self.report['extraction_validation'] = 'extraction_observed'
                    elif self.record_policy is not None:
                        data = self.baseline_step('audit', self.backend.observe_record_metadata, 'baseline')
                        capture = self.backend.prepare_record_profile(data, self.report)
                        self.report['record_readback'] = capture
                        self.report['reader_validation'] = comparison.VERDICT
                        self.report['metadata_validation'] = self.observation.METADATA_VERDICT
                        self.report['mapping_validation'] = self.record_policy.MAPPING_VERDICT
                        capture['states'].append(self.backend.compare_record_state('baseline', self.report))
                        self.report['layout_validation'] = self.record_policy.LAYOUT_VERDICT
                    elif self.observation is not None:
                        data = self.baseline_step('audit', self.backend.observe_record_metadata, 'baseline')
                        self.report['record_observation'] = self.observation.bind_capture(data, self.report)
                        self.report['reader_validation'] = comparison.VERDICT
                        self.report['metadata_validation'] = 'metadata_projection_captured'
                        self.report['layout_validation'] = 'declarations_only'
                    elif self.report['schema'] == comparison.SCHEMA:
                        comparison.require_ascii_field_policy(self.report)
                        data = self.baseline_step('audit', self.backend.compare_catalog, 'baseline')
                        self.report['storage_contract'] = comparison.bind_ascii_fields_capture(data, self.report)
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
                    logical_validator = self.description_policy.validate_logical if self.report.get('schema') in (59,62) else validate_logical
                    logical_validator(self.backend.observe('deleted',2),'deleted')
                self.done(stage)
            self.report.update(status='ok',failed_stage=None,failure_kind='none')
        except BaseException as error:
            if self.description_policy is not None and self.report.get('schema') == 53:
                if type(error) is self.description_policy.DiagnosticFailure:
                    description_failure = error.diagnostic
            if self.params_policy is not None and type(error) in (self.params_policy.ObservationFailure,
                    self.observation.ObservationFailure, comparison.ComparisonFailure) and self.stage == 'baseline':
                params_failure = self.params_policy.ObservationFailure(error.category, error.code)
            elif self.record_policy is not None and type(error) is self.record_policy.ReadbackFailure:
                readback_failure = error
            elif self.record_policy is not None and type(error) in (self.observation.ObservationFailure, comparison.ComparisonFailure) and self.stage == 'baseline':
                readback_failure = self.record_policy.ReadbackFailure(error.category, error.code)
            elif self.observation is not None and type(error) in (self.observation.ObservationFailure, comparison.ComparisonFailure) and self.stage == 'baseline':
                observation_failure = error
            elif type(error) is comparison.ComparisonFailure and self.stage == 'baseline':
                comparison_failure = error
            kind=error.kind if isinstance(error,OracleError) and error.kind in FAILURES else 'unexpected_failure'
            if params_failure is not None:
                kind = self.params_policy.FAILURE_KIND
            elif readback_failure is not None:
                kind = self.record_policy.FAILURE_KIND
            elif observation_failure is not None:
                kind = self.observation.FAILURE_KIND
            elif type(error) is comparison.ComparisonFailure:
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
                    (self.observation.validate_failure_context if self.observation is not None
                     else validate_failure_context)(context,self.stage)
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
                if self.description_policy is not None:
                    self.description_policy.discard_capture(self.report)
                    if description_failure is not None and processes and files:
                        self.description_policy.set_failure(self.report, description_failure)
                elif self.params_policy is not None:
                    if self.report.get('reader_validation') == 'not_run' and getattr(self.backend, 'reader_attempted', False):
                        self.report['reader_validation'] = 'failed'
                    self.params_policy.discard_capture(self.report, params_failure)
                elif self.record_policy is not None:
                    self.record_policy.discard_capture(self.report, readback_failure)
                elif self.observation is not None:
                    if self.report.get('reader_validation') == 'not_run' and getattr(self.backend, 'reader_attempted', False):
                        self.report['reader_validation'] = 'failed'
                    self.observation.discard_capture(self.report, observation_failure)
                else:
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
    if len(sys.argv) not in (3,4) or sys.argv[1]!='--invocation-nonce' or re.fullmatch('[0-9a-f]{32}',sys.argv[2]) is None:
        return 2
    flag = sys.argv[3] if len(sys.argv)==4 else None
    if flag not in (None, '--catalog-numeric-code-rows-3', '--catalog-numeric-code-rows-6', '--catalog-numeric-code-3', '--catalog-numeric-code-6', '--catalog-params-slots-8', '--catalog-params-slots-17', '--catalog-description-rows-8', '--catalog-description-rows-17', '--catalog-description-8', '--catalog-description-17', '--record-metadata-observation', '--record-reader-validation', '--params-transport-observation', '--params-dbnames-extraction', '--dbnames-identity-validation', '--config-transport-observation', '--config-framing-observation', '--config-slot-marker-observation', '--config-zero-marker-filename-observation', '--config-entry-reference-observation', '--config-blob-chain-observation', '--config-content-decode-observation', '--config-root-reference-projection-observation', '--config-catalog-reference-observation', '--config-catalog-name-binding', '--config-catalog-standard-binding', '--config-catalog-identity-binding', '--config-catalog-field-matrix', '--catalog-readonly-binding','--catalog-reference-distinct-a','--catalog-reference-distinct-b','--catalog-reference-codec-distinct-a','--catalog-reference-codec-distinct-b','--catalog-reference-rows-distinct-a','--catalog-reference-rows-distinct-b','--config-catalog-attribute-binding'): return 2
    numeric_rows = flag in ('--catalog-numeric-code-rows-3','--catalog-numeric-code-rows-6')
    numeric_case = {'--catalog-numeric-code-rows-3':'number3','--catalog-numeric-code-rows-6':'number6','--catalog-numeric-code-3':'number3','--catalog-numeric-code-6':'number6'}.get(flag)
    params_slots = flag in ('--catalog-params-slots-8','--catalog-params-slots-17')
    description_rows = flag in ('--catalog-description-rows-8','--catalog-description-rows-17')
    description_case = {'--catalog-params-slots-8':'description8','--catalog-params-slots-17':'description17','--catalog-description-8':'description8','--catalog-description-17':'description17',
        '--catalog-description-rows-8':'description8','--catalog-description-rows-17':'description17'}.get(flag)
    record_metadata = flag == '--record-metadata-observation'
    record_reader = flag == '--record-reader-validation'
    config_transport = flag == '--config-transport-observation'
    config_framing = flag == '--config-framing-observation'
    config_marker_census = flag == '--config-slot-marker-observation'
    config_zero_marker_filename = flag == '--config-zero-marker-filename-observation'
    config_entry_reference = flag == '--config-entry-reference-observation'
    config_blob_chain = flag == '--config-blob-chain-observation'
    config_content_decode = flag == '--config-content-decode-observation'
    reference_rows = flag in ('--catalog-reference-rows-distinct-a','--catalog-reference-rows-distinct-b')
    reference_codec = flag in ('--catalog-reference-codec-distinct-a','--catalog-reference-codec-distinct-b')
    reference_case = {'--catalog-reference-distinct-a':'distinct_a','--catalog-reference-distinct-b':'distinct_b',
        '--catalog-reference-codec-distinct-a':'distinct_a','--catalog-reference-codec-distinct-b':'distinct_b',
        '--catalog-reference-rows-distinct-a':'distinct_a','--catalog-reference-rows-distinct-b':'distinct_b'}.get(flag)
    catalog_readonly_binding = flag == '--catalog-readonly-binding'
    config_catalog_attribute_binding = flag == '--config-catalog-attribute-binding'
    config_catalog_field_matrix = flag == '--config-catalog-field-matrix'
    config_catalog_identity_binding = flag == '--config-catalog-identity-binding'
    config_catalog_standard_binding = flag == '--config-catalog-standard-binding'
    config_catalog_name_binding = flag == '--config-catalog-name-binding'
    config_catalog_observation = flag == '--config-catalog-reference-observation'
    config_root_reference_projection = flag == '--config-root-reference-projection-observation'
    params_transport = flag == '--params-transport-observation'
    params_extraction = flag == '--params-dbnames-extraction'
    dbnames_identity = flag == '--dbnames-identity-validation'
    nonce=sys.argv[2]
    try:
        from inputs import verify_inputs
        options=({'numeric_case':numeric_case,'numeric_rows':True} if numeric_rows else {'numeric_case':numeric_case} if numeric_case is not None else {'description_case':description_case,'params_slots':True} if params_slots else {'description_case':description_case,'description_rows':True} if description_rows else {'description_case':description_case} if description_case is not None else {'reference_case':reference_case, 'reference_rows':True} if reference_rows else {'reference_case':reference_case, 'reference_codec':True} if reference_codec else {'reference_case':reference_case} if reference_case is not None else {'catalog_readonly_binding':True} if catalog_readonly_binding else {'config_catalog_attribute_binding':True} if config_catalog_attribute_binding else {'config_catalog_field_matrix':True} if config_catalog_field_matrix else {'config_catalog_identity_binding':True} if config_catalog_identity_binding else {'config_catalog_standard_binding':True} if config_catalog_standard_binding else {'config_catalog_name_binding':True} if config_catalog_name_binding else {'config_catalog_observation':True} if config_catalog_observation else {'config_root_reference_projection':True} if config_root_reference_projection else {'config_content_decode':True} if config_content_decode else {'config_blob_chain':True} if config_blob_chain else {'config_entry_reference':True} if config_entry_reference else {'config_zero_marker_filename':True} if config_zero_marker_filename else {'config_marker_census':True} if config_marker_census else {'config_framing':True} if config_framing else {'config_transport':True} if config_transport else {'dbnames_identity':True} if dbnames_identity else {'params_extraction':True} if params_extraction else {'params_transport':True} if params_transport else {'record_reader':True} if record_reader else {'record_metadata':True} if record_metadata else {})
        provenance=verify_inputs(INPUTS,nonce,**options)
        selected=comparison
        if numeric_case is not None:
            if numeric_rows:
                import catalog_numeric_code_rows_policy as selected
            else:
                import catalog_numeric_code_policy as selected
            report=selected.empty_report(nonce,provenance,numeric_case=numeric_case)
        elif description_case is not None:
            if params_slots:
                import params_slot_policy as selected
            elif description_rows:
                import catalog_description_rows as selected
            else:
                import catalog_description_policy as selected
            report=selected.empty_report(nonce,provenance,description_case=description_case)
        elif reference_case is not None:
            if reference_rows:
                import catalog_reference_rows as selected
            elif reference_codec:
                import catalog_reference_codec as selected
            else:
                import catalog_reference_identity as selected
            report=selected.empty_report(nonce,provenance,reference_case=reference_case)
        elif catalog_readonly_binding:
            import catalog_readonly_binding as selected
            report=selected.empty_report(nonce,provenance)
        elif config_catalog_attribute_binding:
            import config_catalog_attribute_binding as selected
            report=selected.empty_report(nonce,provenance)
        elif config_catalog_field_matrix:
            import config_catalog_field_matrix as selected
            report=selected.empty_report(nonce,provenance)
        elif config_catalog_identity_binding:
            import config_catalog_identity_binding as selected
            report=selected.empty_report(nonce,provenance)
        elif config_catalog_standard_binding:
            import config_catalog_standard_binding as selected
            report=selected.empty_report(nonce,provenance)
        elif config_catalog_name_binding:
            import config_catalog_name_binding as selected
            report=selected.empty_report(nonce,provenance)
        elif config_catalog_observation:
            import config_catalog_observation as selected
            report=selected.empty_report(nonce,provenance)
        elif config_root_reference_projection:
            import config_root_reference_projection as selected
            report=selected.empty_report(nonce,provenance)
        elif config_content_decode:
            import config_content_decode as selected
            report=selected.empty_report(nonce,provenance)
        elif config_blob_chain:
            import config_blob_chain as selected
            report=selected.empty_report(nonce,provenance)
        elif config_entry_reference:
            import config_entry_reference as selected
            report=selected.empty_report(nonce,provenance)
        elif config_zero_marker_filename:
            import config_zero_marker_filename as selected
            report=selected.empty_report(nonce,provenance)
        elif config_marker_census:
            import config_marker_census as selected
            report=selected.empty_report(nonce,provenance)
        elif config_framing:
            import config_framing as selected
            report=selected.empty_report(nonce,provenance)
        elif config_transport:
            import config_observation as selected
            report=selected.empty_report(nonce,provenance)
        elif dbnames_identity:
            import dbnames_identity as selected
            report=selected.empty_report(nonce,provenance)
        elif params_extraction:
            import params_extraction as selected
            report=selected.empty_report(nonce,provenance)
        elif params_transport:
            import params_observation as selected
            report=selected.empty_report(nonce,provenance)
        elif record_reader:
            import record_validation as selected
            report=selected.empty_report(nonce,provenance)
        elif record_metadata:
            import record_observation as selected
            report=selected.empty_report(nonce,provenance)
        else:
            report=comparison.empty_report(nonce,provenance)
        report=Controller(Native(nonce,provenance,**options),report).run()
        raw=encode(report)
        selected.validate_report(raw,nonce=nonce,provenance=provenance)
        sys.stdout.buffer.write(raw+b'\n'); sys.stdout.buffer.flush()
        return 0 if report['status']=='ok' else 1
    except BaseException:
        # Never emit arbitrary native exceptions, paths or text, even on protocol failures.
        return 1


if __name__=='__main__':
    raise SystemExit(main())

"""Exact reviewed source manifest and bounded read-only staging checks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from protocol import IMAGE, decode, exact, require
from snapshots import OracleError

LEGACY_V3_SOURCE_FILES = {
    'yadinassi/storage/filedb.py':'filedb.py',
    'scripts/native_1c_db_oracle.py':'host.py',
    **{f'scripts/native_1c_db_oracle/{name}':name for name in (
        'probe.sh','run.py','contract.py','protocol.py','snapshots.py','inject_metadata.py','inputs.py',
        'metadata/Catalog.xml','metadata/CommonModule.xml','metadata/Role.xml',
        'metadata/SetupRights.xml','metadata/CRUDRights.xml',
        'modules/SessionModule.bsl','modules/ManagedApplicationModule.bsl','modules/NativeOracleServer.bsl')},
    'scripts/native_1c_bootstrap/inject_modules.py':'inject_modules.py',
}
# Historical v3 inventories remain exactly 18 entries; current v4 stages both
# the standalone parser and the versioned comparison orchestration.
SOURCE_FILES = {**LEGACY_V3_SOURCE_FILES,
    'yadinassi/storage/filedb_catalog.py': 'filedb_catalog.py',
    'scripts/native_1c_db_oracle/comparison.py': 'comparison.py'}
# The default inventory remains exactly 20 files. The explicit observation
# mode alone stages this additional module; old execution never imports it.
RECORD_SOURCE_FILES = {**SOURCE_FILES,
    'scripts/native_1c_db_oracle/record_observation.py': 'record_observation.py'}
RECORD_LANE = 'owned_record_metadata_observation_v1'
MAX_SOURCE=1048576


def inventory(record_metadata=False):
    require(type(record_metadata) is bool, 'invalid_input')
    return RECORD_SOURCE_FILES if record_metadata else SOURCE_FILES


def read_source(path):
    try:
        info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<info.st_size<=MAX_SOURCE,'invalid_input')
        fd=os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as stream:
            start=os.fstat(stream.fileno())
            require((start.st_dev,start.st_ino)==(info.st_dev,info.st_ino),'invalid_input')
            raw=stream.read(MAX_SOURCE+1); end=os.fstat(stream.fileno())
        require(0<len(raw)<=MAX_SOURCE and (start.st_size,start.st_mtime_ns,start.st_ctime_ns)==
            (end.st_size,end.st_mtime_ns,end.st_ctime_ns),'invalid_input')
        return raw
    except OSError:
        raise OracleError('invalid_input') from None


def source_hashes(root, *, record_metadata=False):
    require(root.is_dir() and not root.is_symlink(),'invalid_input')
    result={}
    for relative in inventory(record_metadata):
        path=root/relative
        require(not any(parent.is_symlink() for parent in path.parents if parent!=root),'invalid_input')
        result[relative]=hashlib.sha256(read_source(path)).hexdigest()
    return result


def staged_hashes(root, *, record_metadata=False):
    files=inventory(record_metadata)
    allowed=set(files.values()) | {'invocation.json'}
    directories={parent.as_posix() for name in allowed for parent in Path(name).parents if str(parent)!='.'}
    actual=set()
    for path in root.rglob('*'):
        relative=path.relative_to(root).as_posix()
        require(not path.is_symlink(),'invalid_input')
        if path.is_dir(): require(relative in directories,'invalid_input')
        else:
            require(relative in allowed,'invalid_input'); read_source(path); actual.add(relative)
    require(actual==allowed,'invalid_input')
    return {source:hashlib.sha256(read_source(root/target)).hexdigest() for source,target in files.items()}


def stage_inputs(root, destination, nonce, provenance, *, record_metadata=False):
    require(not destination.exists() and not destination.is_symlink(),'stale_evidence')
    destination.mkdir(mode=0o755)
    for source,target in inventory(record_metadata).items():
        path=destination/target; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(read_source(root/source)); path.chmod(0o444)
    invocation={'schema':1,'nonce':nonce,'provenance':provenance}
    if record_metadata:
        invocation.update(schema=2, lane=RECORD_LANE)
    (destination/'invocation.json').write_text(json.dumps(invocation,separators=(',',':')),encoding='ascii')
    (destination/'invocation.json').chmod(0o444)
    for path in destination.rglob('*'):
        if path.is_dir(): path.chmod(0o555)
    destination.chmod(0o555)
    require(staged_hashes(destination,record_metadata=record_metadata)==provenance['sources'],'provenance_mismatch')


def verify_inputs(root,nonce, *, record_metadata=False):
    require(root.is_dir() and not root.is_symlink(),'invalid_input')
    data=decode(read_source(root/'invocation.json'))
    inventory(record_metadata)
    exact(data,{'schema','nonce','provenance'} | ({'lane'} if record_metadata else set()))
    require(type(data['schema']) is int and data['schema']==(2 if record_metadata else 1)
            and data['nonce']==nonce,'provenance_mismatch')
    if record_metadata: require(data['lane']==RECORD_LANE,'provenance_mismatch')
    provenance=data['provenance']
    from protocol import validate_provenance
    validate_provenance(provenance,provenance)
    require(provenance['image']==IMAGE and provenance['platform']=='linux/amd64'
            and provenance['locale']=='ru_RU.UTF-8' and provenance['timezone']=='Etc/UTC'
            and provenance['actual_version'] is None,'provenance_mismatch')
    require(staged_hashes(root,record_metadata=record_metadata)==provenance['sources'],'provenance_mismatch')
    return provenance

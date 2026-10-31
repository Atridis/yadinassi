"""Independent exact source inventory; old lanes and inventories are unchanged."""
import hashlib
from pathlib import Path
import re
from inputs import CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES, read_source
from protocol import decode, encode, exact, require, validate_provenance, IMAGE

LANE = 'owned_metadata_catalog_applied_view_v1'
SOURCE_FILES = {**CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES,
    **{'scripts/native_1c_db_oracle/'+name:name for name in (
        'metadata_catalog_inputs.py', 'metadata_catalog_acquisition.py',
        'metadata_catalog_instrument.py', 'metadata_catalog_probe_contract.py',
        'metadata_catalog_run.py', 'metadata_catalog_report.py',
        'modules/MetadataCatalogProbe.bsl')},
    'scripts/native_1c_metadata_catalog_oracle.py':'metadata_host.py'}


def source_hashes(root):
    require(root.is_dir() and not root.is_symlink(), 'invalid_input')
    result={}
    for name in SOURCE_FILES:
        path=root/name
        require(not any(p.is_symlink() for p in path.parents if p != root), 'invalid_input')
        result[name]=hashlib.sha256(read_source(path)).hexdigest()
    return result


def staged_hashes(root):
    require(root.is_dir() and not root.is_symlink(), 'invalid_input')
    allowed=set(SOURCE_FILES.values()) | {'invocation.json'}
    directories={p.as_posix() for name in allowed for p in Path(name).parents if str(p)!='.'}
    actual=set()
    for path in root.rglob('*'):
        relative=path.relative_to(root).as_posix()
        require(not path.is_symlink(), 'invalid_input')
        if path.is_dir(): require(relative in directories, 'invalid_input')
        else:
            require(relative in allowed, 'invalid_input'); read_source(path); actual.add(relative)
    require(actual==allowed, 'invalid_input')
    return {name:hashlib.sha256(read_source(root/target)).hexdigest() for name,target in SOURCE_FILES.items()}


def verify_inputs(root, nonce):
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}',nonce) is not None, 'invalid_input')
    value=decode(read_source(root/'invocation.json'))
    exact(value, ('schema','lane','nonce','provenance'))
    require(type(value['schema']) is int and value['schema']==1
            and value['lane']==LANE and value['nonce']==nonce, 'provenance_mismatch')
    provenance=value['provenance'];validate_provenance(provenance,provenance)
    require(provenance['image']==IMAGE and provenance['platform']=='linux/amd64'
            and provenance['locale']=='ru_RU.UTF-8' and provenance['timezone']=='Etc/UTC'
            and provenance['actual_version'] is None
            and provenance['sources']==staged_hashes(root), 'provenance_mismatch')
    return provenance


def stage_inputs(root, destination, nonce, provenance):
    require(not destination.exists() and not destination.is_symlink(), 'stale_evidence')
    require(source_hashes(root)==provenance['sources'], 'provenance_mismatch')
    destination.mkdir(mode=0o755)
    for source,target in SOURCE_FILES.items():
        path=destination/target;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(read_source(root/source));path.chmod(0o444)
    (destination/'invocation.json').write_bytes(encode(dict(schema=1,lane=LANE,nonce=nonce,provenance=provenance)))
    (destination/'invocation.json').chmod(0o444)
    verify_inputs(destination,nonce)

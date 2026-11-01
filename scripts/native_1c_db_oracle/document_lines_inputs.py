"""Closed inventory layered on the reviewed isolated runtime/dependency bundle."""
import hashlib
import re
import sys
from pathlib import Path, PurePosixPath
import metadata_catalog_runtime_inputs as runtime
from protocol import decode, exact, require, validate_provenance, IMAGE

import document_read_inputs as reviewed
LANE = 'owned_document_lines_v1'
PREFIX='scripts/native_1c_db_oracle/'
LOCAL=('document_lines_fixture.py','document_lines_instrument.py','document_lines_run.py',
       'document_lines_inputs.py','document_lines_report.py','document_lines_readback.py',
       'document_lines_physical.py','document_lines_diagnostics.py')
PACKET=('__init__.py','lines_packet.py','schema_facts.json')
GENERATED=tuple(f'generated/repeat-{r}/{n}' for r,doc,cat in (
    (1,'D83c067c6','C1bb732a4'),(2,'De777997a','Cb27de61e'))
    for n in ('manifest.json',f'Documents/{doc}.xml',f'Catalogs/{cat}.xml',
        *(block+'.bsl' for block in ('identity','rows','find_total','selection')),
        *(f'{kind}-{state}.bsl' for kind in ('setup','witness') for state in ('initial','rewritten'))))
SOURCE_FILES={**reviewed.SOURCE_FILES,**{PREFIX+n:n for n in LOCAL},
    **{PREFIX+'document_lines_packet/'+n:'document_lines_packet/'+n for n in PACKET+GENERATED},
    'scripts/native_1c_document_lines_oracle.py':'document_lines_host.py'}


def source_hashes(root):
    manifest, _ = runtime._bundle(Path(root))
    return {name:hashlib.sha256(manifest if name == runtime.MANIFEST else runtime._read(Path(root)/name)).hexdigest()
            for name in SOURCE_FILES}


def staged_hashes(root):
    root = Path(root)
    raw, manifest = runtime._manifest(root)
    allowed = set(SOURCE_FILES.values()) | set(manifest['files']) | {'invocation.json'}
    directories = {p.as_posix() for name in allowed for p in PurePosixPath(name).parents if str(p) != '.'}
    require(len(directories) <= runtime.MAX_STAGE_DIRECTORIES, 'artifact_limit')
    actual = set()
    for path, directory in runtime._walk(root, max_files=len(allowed), max_directories=len(directories)):
        name = path.relative_to(root).as_posix()
        require(name in (directories if directory else allowed), 'invalid_input')
        if not directory: actual.add(name)
    require(actual == allowed, 'invalid_input')
    for name, info in manifest['files'].items():
        data = runtime._read(root/name)
        require(len(data) == info['bytes'] and hashlib.sha256(data).hexdigest() == info['sha256'], 'provenance_mismatch')
    return {name:hashlib.sha256(raw if name == runtime.MANIFEST else runtime._read(root/target)).hexdigest()
            for name, target in SOURCE_FILES.items()}


def verify_inputs(root, nonce):
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) is not None, 'invalid_input')
    value = decode(runtime._read(Path(root)/'invocation.json', 65536))
    exact(value, ('schema','lane','nonce','provenance'))
    require(type(value['schema']) is int and value['schema'] == 1 and value['lane'] == LANE and value['nonce'] == nonce, 'provenance_mismatch')
    p = value['provenance']; validate_provenance(p, p)
    require(p['image'] == IMAGE and p['platform'] == 'linux/amd64' and p['locale'] == 'ru_RU.UTF-8'
            and p['timezone'] == 'Etc/UTC' and p['actual_version'] is None and p['sources'] == staged_hashes(root), 'provenance_mismatch')
    return p


def stage_inputs(root, destination, nonce, provenance):
    root, destination = Path(root), Path(destination)
    require(not destination.exists() and not destination.is_symlink(), 'stale_evidence')
    manifest, bundled = runtime._bundle(root)
    sources = {target:manifest if source == runtime.MANIFEST else runtime._read(root/source)
               for source, target in SOURCE_FILES.items()}
    require({source:hashlib.sha256(sources[target]).hexdigest() for source,target in SOURCE_FILES.items()} == provenance['sources'], 'provenance_mismatch')
    require(not set(sources).intersection(bundled), 'invalid_input')
    destination.mkdir(mode=0o755)
    files = {**sources, **bundled, 'invocation.json':runtime._json(dict(schema=1,lane=LANE,nonce=nonce,provenance=provenance))}
    for name, data in files.items():
        path = destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o444)
    verify_inputs(destination, nonce)


def activate_runtime(root):
    root = Path(root).resolve()
    invocation = decode(runtime._read(root/'invocation.json', 65536))
    verify_inputs(root, invocation['nonce'])
    prefixes = ('yadinassi', *runtime.PACKAGES.values())
    require(not any(n == p or n.startswith(p+'.') for n in sys.modules for p in prefixes), 'provenance_mismatch')
    installed = {d.metadata['Name'].lower().replace('_','-'):d.version
                 for d in runtime.importlib.metadata.distributions(path=[str(root/'dependencies')])}
    require(installed == runtime.DEPENDENCIES, 'provenance_mismatch')
    sys.path[:0] = [str(root),str(root/'dependencies')]

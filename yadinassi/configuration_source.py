"""General Designer source admission, independent of executable/storage grants.

Unknown metadata and resources are preserved, not activated or silently mapped
onto an approximate schema. Import never compiles or executes BSL. Startup is a
separate operation, so an unused unsupported module cannot prevent admission.
"""
from dataclasses import dataclass
from hashlib import sha256
import io
import json
from pathlib import PurePosixPath
from uuid import UUID
import xml.etree.ElementTree as ET
import zipfile
import zlib

from .configuration_diagnostics import location
from .configuration_import import read_configuration_directory
from .configuration_xml import ConfigurationFile, MD

MAX_FILES = 50000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
_ARCHIVE_FORMAT = 'yadinassi.configuration-source.v1'
_MAX_MANIFEST_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    identity: UUID
    family: str
    name: str
    path: str


@dataclass(frozen=True, slots=True)
class SourceDiagnostic:
    code: str
    path: str
    detail: str


@dataclass(frozen=True, slots=True)
class ConfigurationSource:
    config_uuid: UUID
    name: str
    files: tuple[ConfigurationFile, ...]
    metadata: tuple[SourceMetadata, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    def report(self):
        families = {}
        for item in self.metadata:
            families[item.family] = families.get(item.family, 0) + 1
        return {'format': _ARCHIVE_FORMAT, 'name': self.name,
                'uuid': str(self.config_uuid), 'files': len(self.files),
                'bytes': sum(len(item.content) for item in self.files),
                'metadata_families': families, 'storage_activated': False,
                'source_sha256': source_digest(self),
                'diagnostics': [dict(code=d.code, path=d.path, detail=d.detail)
                                for d in self.diagnostics]}


def source_digest(source):
    """Unambiguous whole-source binding, including opaque and unused resources."""
    digest = sha256()
    for item in source.files:
        name = item.path.encode('utf-8')
        digest.update(len(name).to_bytes(8, 'big'))
        digest.update(name)
        digest.update(len(item.content).to_bytes(8, 'big'))
        digest.update(item.content)
    return digest.hexdigest()


def _path(path):
    if (type(path) is not str or not path or len(path) > 1024
            or '\\' in path or ':' in path or any(ord(c) < 32 for c in path)
            or any(part in ('', '.', '..') for part in path.split('/'))
            or len(path.split('/')) > 33):
        raise ValueError('unsafe configuration path')
    return path


def _xml(raw):
    text = raw.decode('utf-8-sig')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('DTD/entities forbidden')
    depth = count = 0
    root = None
    for event, element in ET.iterparse(io.StringIO(text), events=('start', 'end')):
        if event == 'start':
            if root is None:
                root = element
            depth += 1
            count += 1
            if depth > 128 or count > 250000:
                raise ValueError('XML structure bound')
        else:
            depth -= 1
    if root is None:
        raise ValueError('empty XML')
    return root


def _identity(obj):
    raw = obj.get('uuid', '')
    try:
        identity = UUID(raw)
    except (ValueError, AttributeError):
        raise ValueError('invalid metadata UUID') from None
    if not identity.int or str(identity) != raw.lower():
        raise ValueError('invalid metadata UUID')
    return identity


def _metadata(root, path):
    if root.tag != '{'+MD+'}MetaDataObject':
        return None
    if len(root) != 1 or not root[0].tag.startswith('{'+MD+'}'):
        raise ValueError('metadata object shape')
    obj = root[0]
    properties = obj.findall('{'+MD+'}Properties')
    names = properties[0].findall('{'+MD+'}Name') if len(properties) == 1 else []
    if (len(names) != 1 or len(names[0]) or not names[0].text
            or len(names[0].text) > 128 or not names[0].text.isidentifier()):
        raise ValueError('metadata name invalid')
    return SourceMetadata(_identity(obj), obj.tag.split('}', 1)[1], names[0].text, path)


def import_source(files):
    """Snapshot the full package; no family whitelist and no executable claims."""
    if type(files) is not dict or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('configuration file bound')
    if any(type(path) is not str for path in files):
        raise ValueError('unsafe configuration path')
    accepted = []; metadata = []; diagnostics = []
    paths = set(); identities = set(); names = set(); total = 0
    for path, raw in sorted(files.items()):
        with location(stage='read', file=path):
            _path(path)
            if path.casefold() in paths:
                raise ValueError('case-colliding paths')
            paths.add(path.casefold())
            if type(raw) is not bytes or len(raw) > MAX_FILE_BYTES:
                raise ValueError('file byte bound')
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ValueError('total byte bound')
            suffix = PurePosixPath(path).suffix.lower()
            kind = 'xml' if suffix == '.xml' else 'module' if suffix == '.bsl' else 'resource'
            if kind == 'xml':
                try:
                    root = _xml(raw)
                except (UnicodeError, ET.ParseError):
                    raise ValueError('malformed UTF-8 XML') from None
                item = _metadata(root, path)
                if item is not None:
                    if item.identity in identities:
                        raise ValueError('duplicate metadata UUID')
                    identities.add(item.identity)
                    # Nested forms legitimately reuse names under different owners.
                    key = (str(PurePosixPath(path).parent).casefold(), item.family, item.name.casefold())
                    if key in names:
                        raise ValueError('duplicate metadata name')
                    names.add(key)
                    metadata.append(item)
            # BSL encoding/syntax is deliberately checked by startup on demand.
            accepted.append(ConfigurationFile(path, raw, kind))
    config = next((item for item in metadata if item.path == 'Configuration.xml'), None)
    if config is None or config.family != 'Configuration':
        raise ValueError('missing Configuration.xml')
    # Describe the boundary once per family rather than emitting thousands of
    # misleading "errors" for objects that have merely been preserved.
    for family in sorted({item.family for item in metadata}):
        diagnostics.append(SourceDiagnostic('source_preserved', '', family))
    diagnostics.append(SourceDiagnostic('storage_not_activated', '',
        'Source admission does not grant database schemas or metadata behavior.'))
    return ConfigurationSource(config.identity, config.name, tuple(accepted),
                               tuple(metadata), tuple(diagnostics))


def load_source_directory(directory):
    return import_source(read_configuration_directory(directory, max_files=MAX_FILES,
        max_file_bytes=MAX_FILE_BYTES, max_total_bytes=MAX_TOTAL_BYTES, max_depth=32))


def save_source_archive(path, source):
    """Exclusive-create a portable source archive, never overwrite a database."""
    if type(source) is not ConfigurationSource:
        raise TypeError('ConfigurationSource required')
    # Revalidate callers' constructed values; metadata is derived, never trusted.
    canonical = import_source({item.path: item.content for item in source.files})
    if source != canonical:
        raise ValueError('source snapshot mismatch')
    manifest = {'format': _ARCHIVE_FORMAT,
                'files': {item.path: sha256(item.content).hexdigest() for item in source.files}}
    manifest_bytes = json.dumps(manifest, ensure_ascii=True, sort_keys=True).encode('utf-8')
    if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
        raise ValueError('manifest byte bound')
    with open(path, 'xb') as destination:
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', manifest_bytes)
            for item in source.files:
                archive.writestr('source/' + item.path, item.content)


def load_source_archive(path):
    """Read and verify bounded bytes without extraction or trusting stored grants."""
    try:
        return _load_source_archive(path)
    except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError,
            EOFError, zlib.error) as error:
        raise ValueError('invalid or unreadable configuration source archive') from error


def _load_source_archive(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not 2 <= len(entries) <= MAX_FILES + 1:
            raise ValueError('configuration file bound')
        if len({entry.filename for entry in entries}) != len(entries):
            raise ValueError('duplicate archive entry')
        if sum(entry.file_size for entry in entries) > MAX_TOTAL_BYTES + _MAX_MANIFEST_BYTES:
            raise ValueError('total byte bound')
        info = archive.getinfo('manifest.json')
        if info.file_size > _MAX_MANIFEST_BYTES:
            raise ValueError('manifest byte bound')
        manifest = json.loads(archive.read(info))
        if type(manifest) is not dict or manifest.get('format') != _ARCHIVE_FORMAT or type(manifest.get('files')) is not dict:
            raise ValueError('invalid source archive manifest')
        files = {}
        for entry in entries:
            if entry.filename == 'manifest.json':
                continue
            if not entry.filename.startswith('source/') or entry.file_size > MAX_FILE_BYTES:
                raise ValueError('invalid source archive entry')
            name = _path(entry.filename[len('source/'):])
            content = archive.read(entry)
            if manifest['files'].get(name) != sha256(content).hexdigest():
                raise ValueError('source checksum mismatch')
            files[name] = content
        if set(files) != set(manifest['files']):
            raise ValueError('source manifest mismatch')
        return import_source(files)

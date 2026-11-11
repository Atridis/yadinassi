"""Detached UI launch input, not an activation, migration or source grant.

Every result is assembled under one existing backend read lease. Plain legacy
profiles have no historical full-source digest: admission proves their current
canonical source and schemas, while the returned digest binds subsequent launch
handoffs to these exact bytes. No row data, VM, cursor or connection is retained.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from .catalog_backend import BackendError


@dataclass(frozen=True, slots=True)
class LaunchFile:
    path: str
    kind: str
    content: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class LaunchSnapshot:
    database_id: UUID
    configuration_generation: int
    profile: str
    route: str
    source_digest: str
    files: tuple[LaunchFile, ...]


PLAIN_PROFILE = 'plain-catalog-v1'


def _metadata(connection, backend, storage):
    if connection.execute("SELECT 1 FROM database_info WHERE typeof(database_uuid)!='text' OR length(database_uuid)!=36 OR typeof(configuration_uuid)!='text' OR length(configuration_uuid)!=36 OR typeof(generation)!='integer' OR generation<1 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(activated)!='integer' OR typeof(activation_issues)!='text' OR length(CAST(activation_issues AS BLOB))>65536 LIMIT 1").fetchone():
        raise BackendError('integrity')
    rows = connection.execute('SELECT singleton,database_uuid,configuration_uuid,generation,name,activated,activation_issues FROM database_info LIMIT 2').fetchall()
    if len(rows) != 1:
        raise BackendError('integrity')
    row = rows[0]
    if (row[0] != 1 or row[1] != str(backend.database_id)
            or row[3] != backend.configuration_generation or row[5] != 1
            or row[6] != storage._json(list(backend.activation_issues))):
        raise BackendError('schema_changed')
    return row


def _files(connection, storage):
    if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(CAST(path AS BLOB))>1024 OR typeof(kind)!='text' OR kind NOT IN ('xml','module') OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(CAST(sha256 AS BLOB))!=64 LIMIT 1").fetchone():
        raise BackendError('integrity')
    count, total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
    if not 1 <= count <= storage._MAX_FILES or total > storage._MAX_CONFIG_BYTES:
        raise BackendError('integrity')
    result = []
    for path, kind, content, digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file ORDER BY path'):
        if sha256(content).hexdigest() != digest:
            raise BackendError('integrity')
        result.append(LaunchFile(path, kind, content, digest))
    return tuple(result)


def _catalogs(connection, backend, storage):
    if connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(identity)!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone():
        raise BackendError('integrity')
    count, total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(definition AS BLOB))),0) FROM catalog_schema').fetchone()
    if count > 512 or total > storage._MAX_CONFIG_BYTES:
        raise BackendError('integrity')
    schemas = []
    for identity, name, definition in connection.execute('SELECT identity,name,definition FROM catalog_schema ORDER BY identity'):
        schema = storage._schema(definition,
            allow_numbering=backend.storage_version in (4, 6, 7, 8, 9, 10),
            allow_hierarchy=backend.storage_version == 10)
        if (identity, name) != (str(schema.identity), schema.name):
            raise BackendError('integrity')
        schemas.append(schema)
    return tuple(schemas)


def _same_schemas(left, right):
    # Canonical UUID ordering must not depend on source name/declaration order.
    return (len({s.identity for s in left}) == len(left)
        and len({s.identity for s in right}) == len(right)
        and tuple(sorted(left, key=lambda s: str(s.identity)))
            == tuple(sorted(right, key=lambda s: str(s.identity))))


def _admit(backend, connection, entries, metadata, catalogs, storage):
    from . import configuration_xml as xml
    from .errors import BSLError
    source = {f.path: f.content for f in entries}
    profile = storage._source_profile_for_issues(backend.activation_issues)
    version = backend.format_version
    try:
        if version == 15:
            from .configuration_inventory_application import (PROFILE, InventoryApplicationConfiguration,
                import_inventory_application)
            marker = connection.execute('SELECT singleton,profile,source_digest FROM inventory_profile LIMIT 2').fetchall()
            if len(marker) != 1 or marker[0][:2] != (1, PROFILE):
                raise BackendError('unsupported')
            config = import_inventory_application(source, inventory_runtime=PROFILE)
            if (type(config) is not InventoryApplicationConfiguration
                    or type(backend.accumulation_configuration) is not InventoryApplicationConfiguration
                    or config != backend.accumulation_configuration
                    or marker != [(1, PROFILE, config.source_digest)]
                    or not _same_schemas(config.catalogs, catalogs)
                    or not _same_schemas(config.documents, backend._document_schemas)):
                raise BackendError('schema_changed')
            identity, name = config.identity, config.name
            canonical_files = tuple((p, 'module' if p.endswith('.bsl') else 'xml', raw)
                                    for p, raw in config.files)
            profile, route = PROFILE, 'inventory'
        elif version == 13:
            from .configuration_posting_application import (PROFILE, PostingApplicationConfiguration,
                import_posting_application)
            marker = connection.execute('SELECT singleton,profile,source_digest FROM posting_profile LIMIT 2').fetchall()
            if len(marker) != 1 or marker[0][:2] != (1, PROFILE):
                raise BackendError('unsupported')
            config = import_posting_application(source, posting_runtime=PROFILE)
            if (type(config) is not PostingApplicationConfiguration
                    or type(backend.posting_configuration) is not PostingApplicationConfiguration
                    or config != backend.posting_configuration or catalogs
                    or marker != [(1, PROFILE, config.source_digest)]
                    or not _same_schemas(config.documents, backend._document_schemas)):
                raise BackendError('schema_changed')
            identity, name = config.identity, config.name
            canonical_files = tuple((p, 'module' if p.endswith('.bsl') else 'xml', raw)
                                    for p, raw in config.files)
            profile, route = PROFILE, 'posting'
        else:
            if version == 6:
                if profile not in (*storage._DEMO_SOURCE_ISSUES, storage.CATALOG_FORMS_PROFILE, storage.APPLICATION_PROFILE):
                    raise BackendError('unsupported')
                config, _ = xml._demo_configuration(source, profile)
                route = ('catalog-forms' if profile == storage.CATALOG_FORMS_PROFILE else
                         'application' if profile == storage.APPLICATION_PROFILE else 'catalog')
            elif version == 7:
                if profile == storage.DOCUMENT_FORMS_PROFILE:
                    from .configuration_document_profile import import_document_forms_configuration
                    config = import_document_forms_configuration(source)
                    route = 'documents'
                elif profile == storage.BUSINESS_PROFILE:
                    from .configuration_business_profile import import_business_configuration
                    config = import_business_configuration(source)
                    route = 'business'
                elif profile == storage.REFERENCE_PROFILE:
                    from .configuration_reference_profile import import_reference_configuration
                    config = import_reference_configuration(source)
                    route = 'references'
                else:
                    raise BackendError('unsupported')
            elif version in (1, 2, 3, 4, 10, 11, 12):
                if (backend.storage_version not in (1, 2, 3, 4, 10)
                        or backend.activation_issues or backend._document_schemas or backend._register_schemas):
                    raise BackendError('unsupported')
                numbering = 'decimal_v1' if any(s.numbering == 'decimal_v1' for s in catalogs) else 'explicit'
                config = xml.import_configuration(source, numbering_policy=numbering)
                if (config.activation_issues or config.documents or config.information_registers
                        or config.common_modules or config.module_runtime is not None):
                    raise BackendError('unsupported')
                # Ordinary canonical admission allows inert comment-only known
                # modules, but never executable BSL or another module grant.
                if any('\n'.join(line.split('//', 1)[0] for line in f.content.decode('utf-8-sig').splitlines()).strip()
                       for f in config.files if f.kind == 'module'):
                    raise BackendError('unsupported')
                profile, route = PLAIN_PROFILE, 'catalog'
            else:
                raise BackendError('unsupported')
            if (config.activation_issues != backend.activation_issues
                    or not _same_schemas(config.catalogs, catalogs)
                    or not _same_schemas(config.documents, backend._document_schemas)
                    or config.information_registers):
                raise BackendError('schema_changed')
            identity, name = config.config_uuid, config.name
            canonical_files = tuple((f.path, f.kind, f.content) for f in config.files)
        if (metadata[2], metadata[4]) != (str(identity), name):
            raise BackendError('schema_changed')
        if canonical_files != tuple((f.path, f.kind, f.content) for f in entries):
            raise BackendError('integrity')
    except BackendError:
        raise
    except (ValueError, TypeError, KeyError, BSLError):
        raise BackendError('integrity') from None
    return profile, route


def launch_snapshot(backend):
    from . import sqlite_catalog as storage
    from .database_transactions import current
    if type(backend) is not storage.SQLiteCatalogBackend:
        raise BackendError('unsupported')
    if backend._closed:
        raise BackendError('closed')
    # Do not borrow a transaction read lease, even from its current owner.
    # Foreign or pending owners are rejected by current() without adoption.
    if current(backend) is not None:
        raise BackendError('unsupported')
    if backend.format_version not in (1, 2, 3, 4, 6, 7, 10, 11, 12, 13, 15):
        raise BackendError('unsupported')
    view = backend.begin_read()
    try:
        connection = view._connection
        if connection.execute('PRAGMA application_id').fetchone()[0] != storage._APPLICATION_ID:
            raise BackendError('schema_changed')
        metadata = _metadata(connection, backend, storage)
        entries = _files(connection, storage)
        catalogs = _catalogs(connection, backend, storage)
        profile, route = _admit(backend, connection, entries, metadata, catalogs, storage)
        digest = sha256(storage._json([(f.path, f.kind, f.digest) for f in entries]).encode('utf-8')).hexdigest()
        result = LaunchSnapshot(backend.database_id, backend.configuration_generation,
            profile, route, digest, entries)
    finally:
        view.close()
    return result

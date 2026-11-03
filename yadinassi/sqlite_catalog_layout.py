"""SQLite v2 readable physical layout and persistent UUID/name registry.

Registry entries, rather than current metadata names, determine physical names.
"""
from uuid import UUID
import unicodedata

from .catalog_backend import BackendError

REGISTRY_DDL = (
    'CREATE TABLE catalog_storage_map(catalog_id TEXT PRIMARY KEY REFERENCES catalog_schema(identity), physical_name TEXT NOT NULL COLLATE NOCASE UNIQUE)',
    'CREATE TABLE catalog_field_storage_map(catalog_id TEXT NOT NULL REFERENCES catalog_storage_map(catalog_id), field_id TEXT NOT NULL, physical_name TEXT NOT NULL COLLATE NOCASE, PRIMARY KEY(catalog_id,field_id), UNIQUE(catalog_id,physical_name))',
)
MIGRATION_MARKER_DDL = 'CREATE TABLE migration_marker(singleton INTEGER PRIMARY KEY CHECK(singleton=1), migration_id TEXT NOT NULL, database_uuid TEXT NOT NULL, source_hash TEXT NOT NULL, layout_hash TEXT NOT NULL)'
_MAX_IDENTIFIER_BYTES = 1024
_RESERVED = frozenset(('database_info', 'configuration_file', 'catalog_schema', 'catalog_record', 'commit_receipt', 'catalog_storage_map', 'catalog_field_storage_map', 'migration_marker'))


def quote_identifier(name):
    if type(name) is not str or not name or any(unicodedata.category(ch).startswith('C') for ch in name):
        raise BackendError('invalid_input')
    try: size = len(name.encode('utf-8'))
    except UnicodeEncodeError: raise BackendError('invalid_input') from None
    if size > _MAX_IDENTIFIER_BYTES: raise BackendError('invalid_input')
    return '"' + name.replace('"', '""') + '"'


def _identity(value):
    if type(value) is not UUID or not value.int: raise BackendError('invalid_input')
    return value


def _key(name):
    quote_identifier(name)
    return unicodedata.normalize('NFC', unicodedata.normalize('NFC', name).casefold())


def _allocate(prefix, name, identity, used):
    _identity(identity)
    if type(name) is not str or not name: raise BackendError('invalid_input')
    if '\x00' in name: raise BackendError('invalid_input')
    normalized = unicodedata.normalize('NFC', name)
    base = prefix + ''.join('_' if unicodedata.category(ch).startswith('C') else ch for ch in normalized)
    quote_identifier(base)
    candidate = base
    if _key(candidate) in used:
        for length in (8, 12, 16, 24, 32):
            candidate = base + '_' + identity.hex[:length]
            quote_identifier(candidate)
            if _key(candidate) not in used: break
        else: raise BackendError('integrity')
    used.add(_key(candidate))
    return candidate


class Layout:
    """Immutable-by-convention snapshot; identifiers are unquoted strings."""
    def __init__(self, tables, fields):
        self._tables = dict(tables)
        self._fields = dict(fields)

    def table_name(self, catalog_id):
        try: return self._tables[_identity(catalog_id)]
        except KeyError: raise BackendError('integrity') from None

    def field_name(self, catalog_id, field_id):
        try: return self._fields[(_identity(catalog_id), _identity(field_id))]
        except KeyError: raise BackendError('integrity') from None


def build_layout(schemas, *, reserved_names=()):
    schemas = tuple(schemas)
    used = {_key(name) for name in _RESERVED}
    used.update(_key(name) for name in reserved_names)
    tables, fields = {}, {}
    for schema in sorted(schemas, key=lambda s: _identity(s.identity).hex):
        if schema.identity in tables: raise BackendError('integrity')
        tables[schema.identity] = _allocate('catalog_', schema.name, schema.identity, used)
        field_used = {_key(name) for name in ('record_id', 'revision', 'code', 'description', 'deletion_mark')}
        for field in sorted(schema.fields, key=lambda f: _identity(f.identity).hex):
            key = (schema.identity, field.identity)
            if key in fields: raise BackendError('integrity')
            fields[key] = _allocate('attr_', field.name, field.identity, field_used)
    return Layout(tables, fields)


def save_layout(connection, layout):
    for identity, name in sorted(layout._tables.items(), key=lambda item: item[0].hex):
        connection.execute('INSERT INTO catalog_storage_map(catalog_id,physical_name) VALUES(?,?)', (str(identity), name))
    for (catalog_id, field_id), name in sorted(layout._fields.items(), key=lambda item: (item[0][0].hex,item[0][1].hex)):
        connection.execute('INSERT INTO catalog_field_storage_map(catalog_id,field_id,physical_name) VALUES(?,?,?)', (str(catalog_id), str(field_id), name))


def load_layout(connection, schemas):
    schemas = tuple(schemas)
    expected_tables = {_identity(s.identity) for s in schemas}
    expected_fields = {(s.identity, _identity(f.identity)) for s in schemas for f in s.fields}
    if len(expected_tables) != len(schemas) or len(expected_fields) != sum(len(s.fields) for s in schemas): raise BackendError('integrity')
    # Bound registry data before materializing. Exact cardinality follows schema.
    if connection.execute("SELECT 1 FROM catalog_storage_map WHERE typeof(catalog_id)!='text' OR length(CAST(catalog_id AS BLOB))!=36 OR typeof(physical_name)!='text' OR length(CAST(physical_name AS BLOB))>? LIMIT 1", (_MAX_IDENTIFIER_BYTES,)).fetchone(): raise BackendError('integrity')
    if connection.execute("SELECT 1 FROM catalog_field_storage_map WHERE typeof(catalog_id)!='text' OR length(CAST(catalog_id AS BLOB))!=36 OR typeof(field_id)!='text' OR length(CAST(field_id AS BLOB))!=36 OR typeof(physical_name)!='text' OR length(CAST(physical_name AS BLOB))>? LIMIT 1", (_MAX_IDENTIFIER_BYTES,)).fetchone(): raise BackendError('integrity')
    if connection.execute('SELECT COUNT(*) FROM catalog_storage_map').fetchone()[0] != len(expected_tables) or connection.execute('SELECT COUNT(*) FROM catalog_field_storage_map').fetchone()[0] != len(expected_fields): raise BackendError('integrity')
    tables, fields = {}, {}
    used = {_key(name) for name in _RESERVED}
    try:
        for identity, name in connection.execute('SELECT catalog_id,physical_name FROM catalog_storage_map'):
            parsed = UUID(identity)
            if str(parsed) != identity or parsed not in expected_tables or not name.startswith('catalog_') or _key(name) in used: raise BackendError('integrity')
            used.add(_key(name)); tables[parsed] = name
        field_used = {catalog_id: {_key(name) for name in ('record_id','revision','code','description','deletion_mark')} for catalog_id in expected_tables}
        for catalog_id, field_id, name in connection.execute('SELECT catalog_id,field_id,physical_name FROM catalog_field_storage_map'):
            cat, field = UUID(catalog_id), UUID(field_id)
            key = (cat, field)
            if str(cat) != catalog_id or str(field) != field_id or key not in expected_fields or not name.startswith('attr_') or _key(name) in field_used[cat]: raise BackendError('integrity')
            field_used[cat].add(_key(name)); fields[key] = name
    except (ValueError, TypeError): raise BackendError('integrity') from None
    if set(tables) != expected_tables or set(fields) != expected_fields: raise BackendError('integrity')
    return Layout(tables, fields)


def catalog_ddl(schema, layout):
    fields = [
        'record_id TEXT PRIMARY KEY NOT NULL',
        'revision INTEGER NOT NULL CHECK(revision>0)',
        'code TEXT NOT NULL UNIQUE',
        'description TEXT NOT NULL',
        'deletion_mark INTEGER NOT NULL CHECK(deletion_mark IN(0,1))',
    ]
    for field in schema.fields:
        name = quote_identifier(layout.field_name(schema.identity, field.identity))
        if field.kind == 'catalog_ref':
            target = quote_identifier(layout.table_name(field.target_catalog_id))
            fields.append(f'{name} TEXT REFERENCES {target}(record_id) DEFERRABLE INITIALLY DEFERRED')
        elif field.kind == 'boolean':
            fields.append(f'{name} INTEGER NOT NULL CHECK({name} IN(0,1))')
        elif field.kind in ('string', 'number', 'datetime'):
            fields.append(f'{name} TEXT NOT NULL')
        else: raise BackendError('unsupported')
    return f'CREATE TABLE {quote_identifier(layout.table_name(schema.identity))}(' + ', '.join(fields) + ')'


def index_ddls(schema, layout):
    return ()


def encode_columns(encoded_values, schema):
    if type(encoded_values) not in (list, tuple) or len(encoded_values) != len(schema.fields):
        raise BackendError('integrity')
    result = []
    tags = {'string': 's', 'number': 'n', 'datetime': 'd', 'boolean': 'b', 'catalog_ref': 'r'}
    for value, field in zip(encoded_values, schema.fields):
        if type(value) is not list or len(value) != (3 if field.kind == 'catalog_ref' else 2) or value[0] != tags.get(field.kind):
            raise BackendError('integrity')
        if field.kind == 'catalog_ref':
            if value[1] != str(field.target_catalog_id) or type(value[2]) is not str:
                raise BackendError('integrity')
            try:
                identity = UUID(value[2])
                if str(identity) != value[2]: raise ValueError()
            except (ValueError, TypeError):
                raise BackendError('integrity') from None
            result.append(str(identity) if identity.int else None)
        elif field.kind == 'boolean':
            if type(value[1]) is not bool: raise BackendError('integrity')
            result.append(int(value[1]))
        else:
            if type(value[1]) is not str: raise BackendError('integrity')
            result.append(value[1])
    return tuple(result)


def decode_columns(columns, schema):
    if len(columns) != len(schema.fields): raise BackendError('integrity')
    result = []
    tags = {'string': 's', 'number': 'n', 'datetime': 'd'}
    for value, field in zip(columns, schema.fields):
        if field.kind == 'catalog_ref':
            if value is not None and type(value) is not str: raise BackendError('integrity')
            result.append(['r', str(field.target_catalog_id), value if value is not None else str(UUID(int=0))])
        elif field.kind == 'boolean':
            if type(value) is not int or value not in (0, 1): raise BackendError('integrity')
            result.append(['b', bool(value)])
        elif field.kind in tags:
            if type(value) is not str: raise BackendError('integrity')
            result.append([tags[field.kind], value])
        else:
            raise BackendError('unsupported')
    return result

"""UUID-addressed, persisted SQLite layouts for catalog tabular sections."""
from uuid import UUID, uuid5

from .catalog_backend import BackendError
from .sqlite_catalog_layout import (
    _MAX_IDENTIFIER_BYTES, _RESERVED, _allocate, _identity, _key,
    quote_identifier,
)

SECTION_REGISTRY_DDL = (
    'CREATE TABLE catalog_section_storage_map(catalog_id TEXT NOT NULL REFERENCES catalog_storage_map(catalog_id), section_id TEXT NOT NULL, physical_name TEXT NOT NULL COLLATE NOCASE UNIQUE, PRIMARY KEY(catalog_id,section_id))',
    'CREATE TABLE catalog_section_field_storage_map(catalog_id TEXT NOT NULL, section_id TEXT NOT NULL, field_id TEXT NOT NULL, physical_name TEXT NOT NULL COLLATE NOCASE, PRIMARY KEY(catalog_id,section_id,field_id), UNIQUE(catalog_id,section_id,physical_name), FOREIGN KEY(catalog_id,section_id) REFERENCES catalog_section_storage_map(catalog_id,section_id))',
)
_RESERVED_TABLES = _RESERVED | frozenset((
    'catalog_section_storage_map', 'catalog_section_field_storage_map',
))
_RESERVED_COLUMNS = ('owner_id', 'row_id', 'row_number')


class SectionLayout:
    """Immutable-by-convention physical names keyed only by metadata UUIDs."""
    def __init__(self, tables, fields):
        self._tables = dict(tables)
        self._fields = dict(fields)

    def table_name(self, catalog_id, section_id):
        try:
            return self._tables[(_identity(catalog_id), _identity(section_id))]
        except KeyError:
            raise BackendError('integrity') from None

    def field_name(self, catalog_id, section_id, field_id):
        try:
            return self._fields[(_identity(catalog_id), _identity(section_id), _identity(field_id))]
        except KeyError:
            raise BackendError('integrity') from None


def _expected(schemas):
    catalogs, tables, fields = set(), set(), set()
    for schema in schemas:
        cat = _identity(schema.identity)
        if cat in catalogs:
            raise BackendError('integrity')
        catalogs.add(cat)
        for section in schema.tabular_sections:
            key = (cat, _identity(section.identity))
            if key in tables:
                raise BackendError('integrity')
            tables.add(key)
            for field in section.fields:
                field_key = (*key, _identity(field.identity))
                if field_key in fields:
                    raise BackendError('integrity')
                fields.add(field_key)
    return tables, fields


def _used_table_names(catalog_layout):
    # Include every owner mapping, even owners without tabular sections.
    used = {_key(name) for name in _RESERVED_TABLES}
    for identity, name in catalog_layout._tables.items():
        _identity(identity)
        key = _key(name)
        if key in used:
            raise BackendError('integrity')
        used.add(key)
    return used


def build_section_layout(schemas, catalog_layout):
    schemas = tuple(schemas)
    _expected(schemas)
    used = _used_table_names(catalog_layout)
    tables, fields = {}, {}
    for schema in sorted(schemas, key=lambda s: s.identity.hex):
        catalog_layout.table_name(schema.identity)
        for section in sorted(schema.tabular_sections, key=lambda s: s.identity.hex):
            for name in (schema.name, section.name):
                if type(name) is not str or not name or '\x00' in name:
                    raise BackendError('invalid_input')
            key = (schema.identity, section.identity)
            # A section UUID may legitimately recur under a different owner.
            allocation_id = uuid5(schema.identity, section.identity.hex)
            tables[key] = _allocate('catalog_section_', schema.name + '_' + section.name, allocation_id, used)
            field_used = {_key(name) for name in _RESERVED_COLUMNS}
            for field in sorted(section.fields, key=lambda f: f.identity.hex):
                fields[(*key, field.identity)] = _allocate('attr_', field.name, field.identity, field_used)
    return SectionLayout(tables, fields)


def save_section_layout(connection, layout):
    for key, name in sorted(layout._tables.items()):
        connection.execute('INSERT INTO catalog_section_storage_map(catalog_id,section_id,physical_name) VALUES(?,?,?)', (*map(str, key), name))
    for key, name in sorted(layout._fields.items()):
        connection.execute('INSERT INTO catalog_section_field_storage_map(catalog_id,section_id,field_id,physical_name) VALUES(?,?,?,?)', (*map(str, key), name))


def load_section_layout(connection, schemas, catalog_layout):
    schemas = tuple(schemas)
    expected_tables, expected_fields = _expected(schemas)
    for schema in schemas:
        catalog_layout.table_name(schema.identity)
    # Preflight cardinality and byte sizes before materializing registry rows.
    registries = (
        ('catalog_section_storage_map', ('catalog_id', 'section_id'), expected_tables),
        ('catalog_section_field_storage_map', ('catalog_id', 'section_id', 'field_id'), expected_fields),
    )
    for registry, identities, expected in registries:
        if connection.execute(f'SELECT COUNT(*) FROM {registry}').fetchone()[0] != len(expected):
            raise BackendError('integrity')
        invalid = [f"typeof({column})!='text' OR length(CAST({column} AS BLOB))!=36" for column in identities]
        invalid.append("typeof(physical_name)!='text' OR length(CAST(physical_name AS BLOB))>?")
        if connection.execute(f'SELECT 1 FROM {registry} WHERE ' + ' OR '.join(invalid) + ' LIMIT 1', (_MAX_IDENTIFIER_BYTES,)).fetchone():
            raise BackendError('integrity')
    tables, fields = {}, {}
    used = _used_table_names(catalog_layout)
    field_used = {key: {_key(name) for name in _RESERVED_COLUMNS} for key in expected_tables}
    try:
        for cat, section, name in connection.execute('SELECT catalog_id,section_id,physical_name FROM catalog_section_storage_map'):
            key = (UUID(cat), UUID(section))
            if tuple(map(str, key)) != (cat, section) or key not in expected_tables or key in tables or not name.startswith('catalog_section_') or _key(name) in used:
                raise BackendError('integrity')
            used.add(_key(name))
            tables[key] = name
        for cat, section, field, name in connection.execute('SELECT catalog_id,section_id,field_id,physical_name FROM catalog_section_field_storage_map'):
            key = (UUID(cat), UUID(section), UUID(field))
            if tuple(map(str, key)) != (cat, section, field) or key not in expected_fields or key in fields or not name.startswith('attr_') or _key(name) in field_used[key[:2]]:
                raise BackendError('integrity')
            field_used[key[:2]].add(_key(name))
            fields[key] = name
    except (ValueError, TypeError):
        raise BackendError('integrity') from None
    if set(tables) != expected_tables or set(fields) != expected_fields:
        raise BackendError('integrity')
    return SectionLayout(tables, fields)


def section_ddl(catalog_schema, section_schema, catalog_layout, section_layout):
    owner = quote_identifier(catalog_layout.table_name(catalog_schema.identity))
    columns = [
        f'owner_id TEXT NOT NULL REFERENCES {owner}(record_id) DEFERRABLE INITIALLY DEFERRED',
        'row_id TEXT NOT NULL',
        'row_number INTEGER NOT NULL CHECK(row_number>0)',
    ]
    for field in section_schema.fields:
        name = quote_identifier(section_layout.field_name(catalog_schema.identity, section_schema.identity, field.identity))
        if field.kind == 'catalog_ref':
            target = quote_identifier(catalog_layout.table_name(field.target_catalog_id))
            columns.append(f'{name} TEXT REFERENCES {target}(record_id) DEFERRABLE INITIALLY DEFERRED')
        elif field.kind == 'boolean':
            columns.append(f'{name} INTEGER NOT NULL CHECK({name} IN(0,1))')
        elif field.kind in ('string', 'number', 'datetime'):
            columns.append(f'{name} TEXT NOT NULL')
        else:
            raise BackendError('unsupported')
    columns.extend(('PRIMARY KEY(owner_id,row_id)', 'UNIQUE(owner_id,row_number)'))
    table = quote_identifier(section_layout.table_name(catalog_schema.identity, section_schema.identity))
    return f'CREATE TABLE {table}(' + ', '.join(columns) + ')'

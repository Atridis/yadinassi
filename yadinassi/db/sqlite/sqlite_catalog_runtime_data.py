"""Open-time format-16 storage shape for ordinary catalog data operations.

This is not source authority or a row proof. A live data operation compares DB
identity, SQL schema and the reached catalog's metadata on its own transaction.
Unrelated configuration XML is not re-read by this lane. Editing the archive
does not activate any code; executable-source paths still admit independently.
"""
from copy import deepcopy
from itertools import zip_longest

from yadinassi.db.catalog.catalog_backend import BackendError


_DDL = ("SELECT CASE WHEN length(CAST(name AS BLOB))<=1024 "
        "AND length(CAST(tbl_name AS BLOB))<=1024 "
        "AND length(CAST(COALESCE(sql,'') AS BLOB))<=262144 THEN type END,"
        " CASE WHEN length(CAST(name AS BLOB))<=1024 THEN name END,"
        " CASE WHEN length(CAST(tbl_name AS BLOB))<=1024 THEN tbl_name END,"
        " CASE WHEN length(CAST(COALESCE(sql,'') AS BLOB))<=262144 THEN sql END"
        ",rootpage FROM sqlite_schema ORDER BY type,name LIMIT ?")
_INFO = ("SELECT database_uuid,generation,configuration_uuid,name,activated,activation_issues"
         " FROM database_info WHERE singleton=1 AND length(CAST(database_uuid AS BLOB))=36"
         " AND length(CAST(configuration_uuid AS BLOB))=36 AND length(CAST(name AS BLOB))<=512"
         " AND length(CAST(activation_issues AS BLOB))<=1024"
         " AND typeof(generation)='integer' AND typeof(activated)='integer'"
         " AND (SELECT application_id FROM pragma_application_id)=?"
         " AND (SELECT user_version FROM pragma_user_version)=16")
_SHAPE = ("SELECT 0,NULL,NULL,CASE WHEN length(CAST(physical_name AS BLOB))<=1024 THEN physical_name END"
          " FROM catalog_storage_map WHERE catalog_id=?1"
          " UNION ALL SELECT 1,NULL,CASE WHEN length(CAST(field_id AS BLOB))=36 THEN field_id END,"
          " CASE WHEN length(CAST(physical_name AS BLOB))<=1024 THEN physical_name END"
          " FROM catalog_field_storage_map WHERE catalog_id=?1"
          " UNION ALL SELECT 2,CASE WHEN length(CAST(section_id AS BLOB))=36 THEN section_id END,NULL,"
          " CASE WHEN length(CAST(physical_name AS BLOB))<=1024 THEN physical_name END"
          " FROM catalog_section_storage_map WHERE catalog_id=?1"
          " UNION ALL SELECT 3,CASE WHEN length(CAST(section_id AS BLOB))=36 THEN section_id END,"
          " CASE WHEN length(CAST(field_id AS BLOB))=36 THEN field_id END,"
          " CASE WHEN length(CAST(physical_name AS BLOB))<=1024 THEN physical_name END"
          " FROM catalog_section_field_storage_map WHERE catalog_id=?1 LIMIT ?2")


class CatalogRuntimeData:
    def __init__(self, backend, connection, application_id):
        from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration

        self.application_id = application_id
        self.config = backend.accumulation_configuration
        self.handlers = self.config.catalog_handlers if type(self.config) is MainDemoConfiguration else ()
        self.handler_ids = frozenset(identity.int for identity, _, _ in self.handlers)
        self.info = (str(backend.database_id), backend.configuration_generation,
                     str(self.config.identity), self.config.name, 1, '[]')
        self.ddl = tuple(connection.execute(_DDL, (4097,)))
        if len(self.ddl) > 4096 or any(row[0] is None for row in self.ddl):
            raise BackendError('unsupported')
        schemas, self.layout, self.sections, self.domain = deepcopy(
            (backend._schemas, backend._layout, backend._section_layout, backend._enum_domain))
        self.schemas = {schema.identity.int: schema for schema in schemas}
        self.rows = {identity: (name, definition) for identity, name, definition in backend._schema_snapshot}
        shapes = {identity: set() for identity in self.rows}
        for catalog, name in self.layout._tables.items():
            shapes[str(catalog)].add((0, None, None, name))
        for (catalog, field), name in self.layout._fields.items():
            shapes[str(catalog)].add((1, None, str(field), name))
        for (catalog, section), name in self.sections._tables.items():
            shapes[str(catalog)].add((2, str(section), None, name))
        for (catalog, section, field), name in self.sections._fields.items():
            shapes[str(catalog)].add((3, str(section), str(field), name))
        self.shapes = {identity: frozenset(shape) for identity, shape in shapes.items()}

    def allows_write(self, backend, identity):
        if (backend.accumulation_configuration is not self.config
                or getattr(self.config, 'catalog_handlers', self.handlers) is not self.handlers):
            raise BackendError('schema_changed')
        return identity.int not in self.handler_ids

    def check(self, connection):
        # Reading the live DB identity pins a deferred read transaction. In
        # DELETE journal mode the owner retains that snapshot through row I/O.
        if connection.execute(_INFO, (self.application_id,)).fetchone() != self.info:
            raise BackendError('schema_changed')
        cursor = connection.execute(_DDL, (len(self.ddl) + 1,))
        try:
            if any(stored != opened for stored, opened in zip_longest(cursor, self.ddl)):
                raise BackendError('schema_changed')
        finally:
            cursor.close()

    def catalog(self, connection, identity):
        schema = self.schemas.get(identity.int)
        if schema is None:
            raise BackendError('not_found')
        key = str(identity)
        if connection.execute(
                "SELECT name,definition FROM catalog_schema WHERE identity=? "
                "AND length(CAST(name AS BLOB))<=512 AND length(CAST(definition AS BLOB))<=262144",
                (key,)).fetchone() != self.rows[key]:
            raise BackendError('schema_changed')
        remaining = set(self.shapes[key])
        cursor = connection.execute(_SHAPE, (key, len(remaining) + 1))
        try:
            for row in cursor:
                if row not in remaining:
                    raise BackendError('schema_changed')
                remaining.remove(row)
        finally:
            cursor.close()
        if remaining:
            raise BackendError('schema_changed')
        return schema

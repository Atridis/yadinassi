"""Open-time format-16 catalog data descriptor, not executable-source authority.

An open backend uses its admitted schema and layout for ordinary record I/O.
File identity, transaction ownership, row validation, and revision checks still
apply. Changing schema/registry/identity via another connection requires
closing and reopening the backend. Raw, migration, and source lanes keep
their own admissions and never treat this descriptor as a validation proof.
"""
from copy import deepcopy
import sqlite3
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError


def authorize_write(_action, _first, _second, _database, source):
    # A lean writer does not re-admit all DDL. Never execute a trigger or view
    # program reached by its own SQL, including externally installed ones.
    return sqlite3.SQLITE_OK if source is None else sqlite3.SQLITE_DENY


class CatalogRuntimeData:
    def __init__(self, backend):
        from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration

        self.config = backend.accumulation_configuration
        self.handlers = self.config.catalog_handlers if type(self.config) is MainDemoConfiguration else ()
        self.handler_ids = frozenset(identity.int for identity, _, _ in self.handlers)
        self.identity = (UUID(int=backend.database_id.int), backend.configuration_generation)
        schemas, self.layout, self.sections, self.domain = deepcopy(
            (backend._schemas, backend._layout, backend._section_layout, backend._enum_domain))
        self.schemas = {schema.identity.int: schema for schema in schemas}
        # Prepared header layout/field descriptors, not any stored row proof.
        self.document_schemas = backend._document_schemas
        definitions = {row[0]:row for row in backend._document_snapshot}
        self.document_headers = {
            schema.identity.int:(schema,schema.name,schema.number_length,schema.fields,
                                 definitions[str(schema.identity)],
                                 {field.identity.int:deepcopy(field) for field in schema.fields})
            for schema in self.document_schemas}


    def allows_write(self, backend, identity):
        if (backend.accumulation_configuration is not self.config
                or getattr(self.config, 'catalog_handlers', self.handlers) is not self.handlers):
            raise BackendError('schema_changed')
        return identity.int not in self.handler_ids

    def document_header(self,backend,schema,identity,selected):
        from yadinassi.db.catalog.catalog_backend import FieldSchema
        from yadinassi.db.document.document_backend import DocumentSchema

        if (backend.accumulation_configuration is not self.config
                or backend._document_schemas is not self.document_schemas
                or type(schema) is not DocumentSchema or type(schema.identity) is not UUID
                or type(schema.identity.int) is not int or schema.identity.int!=identity.int):
            raise BackendError('schema_changed')
        header = self.document_headers.get(identity.int)
        if (header is None or header[0] is not schema or type(schema.number_length) is not int
                or schema.number_length!=header[2] or type(schema.name) is not str or schema.name!=header[1]
                or schema.fields is not header[3]):
            raise BackendError('schema_changed')
        if type(selected) is FieldSchema and type(selected.identity) is UUID and type(selected.identity.int) is int:
            from yadinassi.configuration.configuration_inventory_enums import _same
            admitted = header[5].get(selected.identity.int)
            if admitted is None or not _same(admitted,selected):
                raise BackendError('schema_changed')
            selected = admitted
        elif type(selected) is not str or selected not in ('number','date','deletion_mark','posted','ref'):
            raise BackendError('invalid_input')
        return (header[2],bool(header[3]),header[4]), selected

    def catalog(self, identity):
        schema = self.schemas.get(identity.int)
        if schema is None:
            raise BackendError('not_found')
        return schema

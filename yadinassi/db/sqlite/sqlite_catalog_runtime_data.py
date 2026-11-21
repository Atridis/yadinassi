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

    def allows_write(self, backend, identity):
        if (backend.accumulation_configuration is not self.config
                or getattr(self.config, 'catalog_handlers', self.handlers) is not self.handlers):
            raise BackendError('schema_changed')
        return identity.int not in self.handler_ids

    def catalog(self, identity):
        schema = self.schemas.get(identity.int)
        if schema is None:
            raise BackendError('not_found')
        return schema

"""Host-selected SQLite application database, separate from BSL object semantics."""
from .sqlite_catalog import SQLiteCatalogBackend
from .catalog_backend import BackendError


def require_database_context() -> str:
    raise ValueError('db required for further code execution')


class SQLiteDBContext:
    """A local SQLite file. Opening does not execute stored configuration code."""
    def __init__(self, path):
        self._backend = SQLiteCatalogBackend(path)
        self.path = self._backend.path

    @classmethod
    def create(cls, path, configuration, *, activate=True):
        result = object.__new__(cls)
        result._backend = SQLiteCatalogBackend.create(path, configuration, activate=activate)
        result.path = result._backend.path
        return result

    @classmethod
    def create_posting(cls, path, configuration):
        """Create a fresh source-granted recorder database, never migrate one."""
        result = object.__new__(cls)
        result._backend = SQLiteCatalogBackend.create_posting(path, configuration)
        result.path = result._backend.path
        return result

    @property
    def backend(self):
        return self._backend

    def require_active(self, *, tabular_sections=False):
        if type(tabular_sections) is not bool: raise BackendError('invalid_input')
        if self._backend.storage_version == 5 or not self._backend.activated:
            raise BackendError('unsupported')
        # Callers opt in explicitly. The BSL adapter and bounded reference-row
        # editor do so; other consumers retain the default refusal.
        if self._backend.capabilities().catalog_tabular_sections and not tabular_sections:
            raise BackendError('unsupported')

    def connection_string(self):
        # Host identity, not a claim of native connection-string syntax parity.
        return 'SQLite=' + self.path

    def close(self):
        self._backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

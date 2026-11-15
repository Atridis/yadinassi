"""Private main-demo catalog storage shape; no old-profile admission or file I/O.

Each public helper revalidates canonical source; the caller owns the SQLite transaction. These
helpers never connect, allocate a database, activate modules or commit changes.
"""
import sqlite3
from .catalog_backend import BackendError, CatalogSchema
from .enum_storage_values import EnumValueDomain


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def _require_config(config):
    from .configuration_main_demo import MainDemoConfiguration, canonical
    if (type(config) is not MainDemoConfiguration or type(config.profile) is not str
            or config.profile != 'main-demo-v1'):
        raise BackendError('unsupported')
    try:
        canonical(config)
    except (ValueError, TypeError, KeyError):
        raise BackendError('unsupported') from None


def _base_ddls():
    from .sqlite_inventory_enum_profile import DDL
    s = _storage()
    return (*(d for d in s._DDL if not d.startswith('CREATE TABLE catalog_record(')),
            *s.REGISTRY_DDL, s.MIGRATION_MARKER_DDL, *s.SECTION_REGISTRY_DDL,
            *s.DOCUMENT_DDL, s._SEQUENCE_DDL, *DDL)


def _catalog_shape(catalogs, domain):
    """Pure codec/layout validation, not a source or write capability."""
    s = _storage()
    if (type(domain) is not EnumValueDomain or type(catalogs) is not tuple
            or not 0 < len(catalogs) <= 512
            or any(type(c) is not CatalogSchema for c in catalogs)):
        raise BackendError('invalid_input')
    identities = set(); names = set(); total = 0; sections_count = 0
    for catalog in catalogs:
        raw = s._json(s._schema_data(catalog, enum_domain=domain))
        total += len(raw.encode('utf-8'))
        if (s._schema(raw, allow_numbering=True, enum_domain=domain) != catalog
                or catalog.hierarchy != 'none' or catalog.identity in identities
                or catalog.name.casefold() in names):
            raise BackendError('invalid_input')
        identities.add(catalog.identity); names.add(catalog.name.casefold())
        sections_count += len(catalog.tabular_sections)
        # The main-demo grant needs CatalogRef/scalar sections, not enum cells.
        if any(f.kind == 'enum_ref' for sec in catalog.tabular_sections for f in sec.fields):
            raise BackendError('unsupported')
    if total > s._MAX_CONFIG_BYTES or sections_count > s._MAX_DATABASE_SECTIONS:
        raise BackendError('unsupported')
    for catalog in catalogs:
        if any(f.target_catalog_id not in identities for f in s._all_fields(catalog)
               if f.kind == 'catalog_ref'):
            raise BackendError('invalid_input')
    reserved = tuple(ddl.split('(')[0].split()[-1] for ddl in _base_ddls())
    layout = s.build_layout(catalogs, reserved_names=reserved)
    sections = s.build_section_layout(catalogs, layout)
    # Construct every SQL declaration now, before the caller may allocate a file.
    for catalog in catalogs:
        s.catalog_ddl(catalog, layout, enum_domain=domain)
        for section in catalog.tabular_sections:
            s.section_ddl(catalog, section, layout, sections)
    return layout, sections


def preflight_catalog_sections(config, domain):
    _require_config(config)
    if type(domain) is not EnumValueDomain or domain != EnumValueDomain(domain.database_id, config.enumerations):
        raise BackendError('invalid_input')
    return _catalog_shape(config.catalogs, domain)


def catalog_section_ddls(config, domain, layout, sections):
    _require_config(config)
    s = _storage()
    return tuple(ddl for catalog in config.catalogs for ddl in (
        s.catalog_ddl(catalog, layout, enum_domain=domain),
        *(s.section_ddl(catalog, section, layout, sections)
          for section in catalog.tabular_sections)))


def create_catalog_tables(connection, config, domain):
    """Create physical catalog/section tables inside a caller-owned transaction.

    Schema rows, sequences and full-profile creation remain the caller's job.
    Failure rolls back this helper only; never commits the enclosing transaction.
    """
    _require_config(config)
    if type(connection) is not sqlite3.Connection or not connection.in_transaction:
        raise BackendError('invalid_input')
    layout, sections = preflight_catalog_sections(config, domain)
    declarations = catalog_section_ddls(config, domain, layout, sections)
    s = _storage()
    connection.execute('SAVEPOINT main_demo_catalog_tables')
    try:
        s.save_layout(connection, layout)
        s.save_section_layout(connection, sections)
        for ddl in declarations:
            connection.execute(ddl)
    except BaseException:
        connection.execute('ROLLBACK TO main_demo_catalog_tables')
        connection.execute('RELEASE main_demo_catalog_tables')
        raise
    connection.execute('RELEASE main_demo_catalog_tables')
    return layout, sections


def validate_main_demo_ddl(connection, config, domain):
    """Exact full format16 table vocabulary, including catalog section tables."""
    _require_config(config)
    preflight_catalog_sections(config, domain)
    s = _storage()
    layout = s.load_layout(connection, config.catalogs)
    sections = s.load_section_layout(connection, config.catalogs, layout)
    expected = {ddl.split('(')[0].split()[-1]: ddl for ddl in _base_ddls()}
    expected.update({layout.table_name(c.identity): s.catalog_ddl(c, layout, enum_domain=domain)
                     for c in config.catalogs})
    expected.update({sections.table_name(c.identity, sec.identity): s.section_ddl(c, sec, layout, sections)
                     for c in config.catalogs for sec in c.tabular_sections})
    if connection.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone():
        raise BackendError('unsupported')
    count, size = connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(name AS BLOB))+length(CAST(COALESCE(sql,'') AS BLOB))),0) FROM sqlite_master").fetchone()
    if count > 4096 or size > 64*1024*1024:
        raise BackendError('unsupported')
    actual = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7))!='sqlite_'"))
    if actual != expected or connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
        raise BackendError('integrity')
    from .sqlite_query_indexes import admit_query_indexes, read_index_bundle_ddls
    admit_query_indexes(connection, s.transaction_profile.profile_index_ddls(7, config.catalogs, layout),
                        read_index_bundle_ddls(7, config.catalogs, layout, format_version=16))

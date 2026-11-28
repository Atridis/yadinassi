"""Bounded lazy module handles for runtime dispatch, never invocation authority.

Keep each original import boundary lazy. Callers retrieve attributes at that
boundary, so live symbol replacement is not turned into a cached callable or
permission. No values, receivers, VMs, ASTs or authorization outcomes enter this
cache. Import failures are not cached. This is not a Python sandbox or support
for unloading/replacing entries in sys.modules during execution.
"""
from functools import lru_cache
from importlib import import_module

_MODULE_NAMES = {
    'accumulation_posting_values': 'yadinassi.db.registers.accumulation_posting_values',
    'catalog_types': 'yadinassi.db.catalog.catalog_types',
    'catalogs': 'yadinassi.db.catalog.catalogs',
    'common_templates': 'yadinassi.configuration.common_templates',
    'configuration_source_metadata': 'yadinassi.configuration.configuration_source_metadata',
    'database_transactions': 'yadinassi.db.database_transactions',
    'document_types': 'yadinassi.db.document.document_types',
    'documents': 'yadinassi.db.document.documents',
    'enum_types': 'yadinassi.db.metadata.enum_types',
    'enumerations': 'yadinassi.db.metadata.enumerations',
    'form_runtime': 'yadinassi.forms.form_runtime',
    'form_tables': 'yadinassi.forms.form_tables',
    'queries': 'yadinassi.db.query.queries',
    'reusable_values': 'yadinassi.application.reusable_values',
    'runtime': 'yadinassi.runtime',
    'source_catalog_runtime': 'yadinassi.db.catalog.source_catalog_runtime',
    'source_constant_managers': 'yadinassi.db.metadata.source_constant_managers',
    'source_constants_runtime': 'yadinassi.db.metadata.source_constants_runtime',
    'source_document_runtime': 'yadinassi.db.document.source_document_runtime',
    'source_document_sections': 'yadinassi.db.document.source_document_sections',
    'source_forms': 'yadinassi.forms.source_forms',
    'source_manager_modules': 'yadinassi.configuration.source_manager_modules',
    'source_metadata_properties': 'yadinassi.configuration.source_metadata_properties',
    'source_references': 'yadinassi.db.metadata.source_references',
    'temporary_storage': 'yadinassi.application.temporary_storage',
    'value_lists': 'yadinassi.collections.value_lists',
}


class _InitializingModule(Exception):
    def __init__(self, module):
        self.module = module


@lru_cache(maxsize=len(_MODULE_NAMES))
def _load_module(name):
    module = import_module(_MODULE_NAMES[name])
    # A recursive import can expose a partial module whose outer import later
    # fails. Return that handle to this caller, but never keep it in the cache.
    if getattr(getattr(module, '__spec__', None), '_initializing', False):
        raise _InitializingModule(module)
    return module


def runtime_module(name):
    # Validate before the cache hashes a key; only fixed source-authored names.
    if type(name) is not str or name not in _MODULE_NAMES:
        raise ValueError('unknown runtime dependency')
    try:
        return _load_module(name)
    except _InitializingModule as pending:
        return pending.module

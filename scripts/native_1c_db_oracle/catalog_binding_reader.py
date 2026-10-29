"""Production harness orchestration, no native/XML expectations in byte readers.

This deliberately remains an owned-profile harness integration, not a public
runtime Catalog manager. All returned metadata/values are private to the caller.
The native adapter must pin every staged source before importing this module.
"""
import importlib.util
from pathlib import Path
import sys
import types

import config_framing_reader as core
import config_catalog_name as name_parser
import filedb_catalog as catalog_module

_PACKAGE = '_owned_catalog_binding_storage'


def _same_file(module, path):
    return (type(module) is types.ModuleType and type(getattr(module, '__file__', None)) is str
            and Path(module.__file__).resolve() == path.resolve())


def _load_storage(*, project_rows=False):
    """Explicit exact-sibling loader; never import an installed yadinassi tree."""
    if type(project_rows) is not bool:
        raise ValueError('catalog binding profile mismatch')
    directory = Path(name_parser.__file__).resolve().parent
    if not _same_file(catalog_module, directory / 'filedb_catalog.py'):
        raise ValueError('catalog binding sibling mismatch')
    attribute_package = '_owned_catalog_attribute_storage'
    attribute_name = attribute_package + '.config_catalog_attributes'
    old_attribute = sys.modules.get(attribute_name)
    if old_attribute is not None and not _same_file(old_attribute, directory / 'config_catalog_attributes.py'):
        raise ValueError('catalog attribute sibling mismatch')
    old_name = sys.modules.get(attribute_package + '.config_catalog_name')
    if old_name is not None and old_name is not name_parser:
        raise ValueError('catalog identity alias mismatch')
    attribute_parser = core.load_catalog_attribute_projector()
    if (not _same_file(attribute_parser, directory / 'config_catalog_attributes.py')
            or sys.modules.get(attribute_package + '.config_catalog_name') is not name_parser):
        raise ValueError('catalog attribute alias mismatch')
    package = sys.modules.get(_PACKAGE)
    if package is None:
        package = types.ModuleType(_PACKAGE)
        package.__path__ = []
        sys.modules[_PACKAGE] = package
    elif type(package) is not types.ModuleType or getattr(package, '__path__', None) != []:
        raise ValueError('catalog binding package mismatch')
    for name, module in (('filedb_catalog', catalog_module), ('config_catalog_name', name_parser),
                         ('config_catalog_attributes', attribute_parser)):
        fullname = _PACKAGE + '.' + name
        old = sys.modules.get(fullname)
        if old is not None and old is not module:
            raise ValueError('catalog binding alias mismatch')
        sys.modules[fullname] = module
    loaded = {}
    for name in ('filedb_named_file', 'filedb_dbnames', 'filedb_records',
                 'config_catalog_binding', 'config_catalog_records',
                 'config_root_projection', 'config_catalog_references',
                 'config_catalog_transport', 'catalog_reader') + (('catalog_reference_uuid',) if project_rows else ()):
        fullname = _PACKAGE + '.' + name
        path = directory / (name + '.py')
        module = sys.modules.get(fullname)
        if module is not None:
            if (not _same_file(module, path) or module.__name__ != fullname
                    or module.__package__ != _PACKAGE):
                raise ValueError('catalog binding cached sibling mismatch')
        else:
            spec = importlib.util.spec_from_file_location(fullname, path)
            if spec is None or spec.loader is None:
                raise ValueError('catalog binding sibling unavailable')
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                del sys.modules[fullname]
                raise
        loaded[name] = module
    return loaded


def read_catalog_binding(read_at, file_size, *, catalog_name, limits=None):
    """Load source-pinned runtime siblings, then delegate without oracle inputs."""
    if type(catalog_name) is not str or not 1 <= len(catalog_name) <= 256:
        raise catalog_module.UnsupportedLayout('binding_catalog_selector')
    try:
        encoded_length = len(catalog_name.encode('utf-8'))
    except UnicodeEncodeError:
        raise catalog_module.UnsupportedLayout('binding_catalog_selector') from None
    if encoded_length > 1024 or any(ord(x) < 32 or ord(x) == 127 for x in catalog_name):
        raise catalog_module.UnsupportedLayout('binding_catalog_selector')
    if limits is not None and type(limits) is not catalog_module.CatalogLimits:
        raise catalog_module.InvalidStructure('binding_limits')
    try:
        runtime = _load_storage()['catalog_reader']
    except (ValueError, OSError, ImportError):
        raise catalog_module.InvalidStructure('binding_reader_sources') from None
    return runtime.read_catalog_binding(read_at, file_size,
        catalog_name=catalog_name, limits=limits)


def read_catalog_rows(read_at, file_size, *, catalog_name, limits=None):
    """Source-pinned opt-in runtime projection; never accepts native values."""
    try:
        runtime = _load_storage(project_rows=True)['catalog_reader']
    except (ValueError, OSError, ImportError):
        raise catalog_module.InvalidStructure('binding_reader_sources') from None
    return runtime.read_catalog_rows(read_at, file_size,
        catalog_name=catalog_name, limits=limits)


def _raw_rows_view(result):
    """Exact runtime result view; used only after the image digest is checked."""
    from uuid import UUID
    modules = _load_storage(project_rows=True)
    runtime, physical = modules['catalog_reader'], modules['filedb_records']
    if (type(result) is not runtime.CatalogRowsReadResult
            or type(result.records) is not physical.PhysicalRecords
            or type(result.rows) is not tuple or type(result.records.rows) is not tuple
            or len(result.rows) != len(result.records.rows) or len(result.rows) > 1
            or any(type(row) is not runtime.CatalogRow or type(row.reference_uuid) is not UUID
                   or row.physical_record is not record
                   for row, record in zip(result.rows, result.records.rows))):
        raise catalog_module.InvalidStructure('binding_typed_rows')
    return runtime.CatalogBindingReadResult(result.config_observation, result.identity,
        result.attributes, result.binding, result.records, result.usage)

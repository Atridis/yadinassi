"""Production harness orchestration, no native/XML expectations in byte readers.

This deliberately remains an owned-profile harness integration, not a public
runtime Catalog manager. All returned metadata/values are private to the caller.
The native adapter must pin every staged source before importing this module.
"""
from dataclasses import dataclass
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


def _load_storage():
    """Explicit exact-sibling loader; never import an installed yadinassi tree."""
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
                 'config_catalog_binding', 'config_catalog_records'):
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


@dataclass(frozen=True)
class CatalogBindingReadResult:
    config_observation: object
    identity: object
    attributes: object
    binding: object
    records: object
    usage: object


def read_catalog_binding(read_at, file_size, *, catalog_name, limits=None):
    """Read all CONFIG entries, PARAMS/DBNames, and one selected Catalog's rows.

    A catalog name is only a selector. It does not provide UUIDs, physical IDs,
    types, lengths, schema or expected values. Complete CONFIG traversal occurs
    before selection. Every subsequent phase uses the same lifetime budget and
    page-ownership graph; errors prevent partial result return and poison it.
    """
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
        modules = _load_storage()
    except (ValueError, OSError, ImportError):
        raise catalog_module.InvalidStructure('binding_reader_sources') from None
    named = modules['filedb_named_file']
    dbnames = modules['filedb_dbnames']
    compiler = modules['config_catalog_binding']
    row_reader = modules['config_catalog_records']
    row_types = modules['filedb_records']
    reader = catalog_module.CatalogReader(read_at, file_size, limits=limits)
    physical_catalog = reader.read_catalog()
    graph = catalog_module._CatalogBindingGraph(reader, physical_catalog)
    try:
        with graph.stage('config') as handle:
            observation = core._observe_catalog_attributes_from_graph(handle,
                profile=core.ConfigCatalogAttributeProfile(core.DECLARATIONS, '0', 0))
            # Complete projection is already bounded to 256 Catalogs. Reserve
            # additional retained result references/selector comparisons before
            # any collection scan, including failure paths.
            reader._budget.charge('output_bytes', 65536)
            reader._budget.charge('bytes_processed', 2048 * len(observation.private_fields))
            selected = None
            uuids = set()
            for key, identity, attributes in observation.private_fields:
                if key != identity.metadata_uuid or identity.metadata_uuid in uuids:
                    raise catalog_module.InvalidStructure('binding_catalog_identity')
                uuids.add(identity.metadata_uuid)
                if identity.name == catalog_name:
                    if selected is not None:
                        raise catalog_module.UnsupportedLayout('binding_catalog_ambiguous')
                    selected = (identity, attributes)
            if selected is None:
                raise catalog_module.UnsupportedLayout('binding_catalog_missing')
            identity, attributes = selected
        with graph.stage('params') as handle:
            extracted = named._read_dbnames_from_catalog(reader, physical_catalog,
                profile=named.DBNamesProfile(core.DECLARATIONS, '0', 0), _binding_handle=handle)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            parse_limits = dbnames.DBNamesParseLimits()
            reservation = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=parse_limits)
            reader._budget.charge('output_bytes', reservation.output_bytes)
            reader._budget.charge('bytes_processed', reservation.bytes_processed)
            # Each token consumes at least one input byte. Reserve the pure
            # parser's bounded token work before execution, including its first
            # over-limit event on failure; never refund unused reservation.
            reader._budget.charge('tokens', min(len(extracted.data), parse_limits.max_tokens + 1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=parse_limits)
            binding = compiler.compile_catalog_binding(identity, attributes, parsed,
                profile=compiler.CatalogBindingProfile(compiler.PROFILE_IDENTIFIER), budget=reader._budget)
            del parsed, extracted, reservation
        with graph.stage('records', binding=binding) as handle:
            rows = row_reader.read_bound_catalog_records(reader, physical_catalog, binding,
                handle=handle, limits=row_types.RecordLimits(max_active_records=1))
        return CatalogBindingReadResult(observation, identity, attributes, binding, rows, reader.usage)
    except BaseException as error:
        graph.failed = True
        if isinstance(error, dbnames.DBNamesParseResourceLimit):
            raise catalog_module.ResourceLimit('binding_dbnames_limits') from None
        if isinstance(error, dbnames.UnsupportedDBNamesProfile):
            raise catalog_module.UnsupportedLayout('binding_dbnames_profile') from None
        if isinstance(error, dbnames.DBNamesParseError):
            raise catalog_module.InvalidStructure('binding_dbnames_invalid') from None
        if isinstance(error, compiler.CatalogBindingError):
            raise catalog_module.UnsupportedLayout('binding_metadata_profile') from None
        if isinstance(error, ValueError):
            raise catalog_module.InvalidStructure('binding_graph_state') from None
        raise

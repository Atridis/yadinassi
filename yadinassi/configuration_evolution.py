"""Closed additive configuration delta. No SQL, activation or implicit migration.

Only exact canonical source packages may describe an update. Storage application
is a separate maintenance operation; constructing a delta grants no write access.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .catalog_backend import BackendError, CatalogSchema, FieldSchema
from .catalog_qualifiers import normalize_field
from .configuration_xml import ConfigurationImport, import_configuration


@dataclass(frozen=True, slots=True)
class CatalogAddition:
    schema: CatalogSchema
    appended: tuple[FieldSchema, ...]
    defaults: tuple
    new_catalog: bool


@dataclass(frozen=True, slots=True)
class ConfigurationDelta:
    source: ConfigurationImport
    target: ConfigurationImport
    catalogs: tuple[CatalogAddition, ...]


def canonical(configuration):
    """Reimport bytes, not caller-provided logical schemas or trusted flags."""
    if type(configuration) is not ConfigurationImport:
        raise BackendError('invalid_input')
    if configuration.activation_issues:
        raise BackendError('unsupported')
    try:
        policy = ('decimal_v1' if any(s.numbering == 'decimal_v1'
                  for s in (*configuration.catalogs, *configuration.documents)) else 'explicit')
        files = {f.path: f.content for f in configuration.files}
        if len(files) != len(configuration.files): raise ValueError()
        result = import_configuration(files, numbering_policy=policy,
                                      module_runtime=configuration.module_runtime)
    except (TypeError, ValueError, AttributeError):
        raise BackendError('invalid_input') from None
    if result != configuration: raise BackendError('integrity')
    return result


def default_value(field):
    """Only closed scalar defaults with exact metadata qualifier validation."""
    if type(field) is not FieldSchema: raise BackendError('invalid_input')
    values = {'string': '', 'number': Decimal(0), 'boolean': False,
              'datetime': datetime(1, 1, 1)}
    if field.kind not in values or field.target_catalog_id is not None:
        raise BackendError('unsupported')
    try: return normalize_field(values[field.kind], field)
    except (TypeError, ValueError): raise BackendError('unsupported') from None


def additive_delta(source, target):
    source, target = canonical(source), canonical(target)
    # Identity, activation, executable behavior and non-catalog schemas cannot
    # hitchhike on a scalar-storage update.
    if (source.config_uuid, source.name, source.modules, source.common_modules,
            source.module_runtime, source.documents, source.information_registers) != (
            target.config_uuid, target.name, target.modules, target.common_modules,
            target.module_runtime, target.documents, target.information_registers):
        raise BackendError('unsupported')
    before = {s.identity: s for s in source.catalogs}
    after = {s.identity: s for s in target.catalogs}
    if not before.keys() <= after.keys(): raise BackendError('unsupported')
    additions = []
    permitted = {'Configuration.xml', 'ConfigDumpInfo.xml'}
    for schema in target.catalogs:
        old = before.get(schema.identity)
        if old == schema: continue
        permitted.add('Catalogs/' + schema.name + '.xml')
        if old is None:
            if schema.tabular_sections or schema.hierarchy != 'none' or schema.numbering != 'explicit':
                raise BackendError('unsupported')
            fields = schema.fields
        else:
            if replace(schema, fields=old.fields) != old:
                raise BackendError('unsupported')
            if schema.fields[:len(old.fields)] != old.fields:
                raise BackendError('unsupported')
            fields = schema.fields[len(old.fields):]
            if not fields: raise BackendError('unsupported')
        additions.append(CatalogAddition(schema, fields,
                         tuple(default_value(f) for f in fields), old is None))
    old_files = {f.path: f.content for f in source.files}
    new_files = {f.path: f.content for f in target.files}
    for path in old_files.keys() | new_files.keys():
        if old_files.get(path) != new_files.get(path) and path not in permitted:
            raise BackendError('unsupported')
    if not additions or len(additions) > 512: raise BackendError('unsupported')
    return ConfigurationDelta(source, target, tuple(sorted(additions, key=lambda a: a.schema.identity.hex)))

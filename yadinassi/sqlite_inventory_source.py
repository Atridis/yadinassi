"""Operation-local full inventory source data from the current successful admit.

The prepared importer cache is not a proof. Only _begin can attach this record
from its actual admission result, after constructing and publishing that view.
Returned immutable configuration data is not transaction or row authority.
"""
from dataclasses import dataclass, fields
from uuid import UUID

from .accumulation_movements import AccumulationRegisterKind, AccumulationRegisterSchema
from .catalog_backend import BackendError, CatalogSchema, FieldSchema, TabularSectionSchema
from .document_backend import DocumentSchema
from .configuration_inventory_application import (
    InventoryApplicationConfiguration, InventoryCommandGrant, InventoryReportGrant,
    InventoryReportFilterGrant, PROFILE)

_UNSPECIFIED = object()

_RECORDS = (InventoryApplicationConfiguration, InventoryCommandGrant,
            InventoryReportGrant, InventoryReportFilterGrant, CatalogSchema,
            FieldSchema, TabularSectionSchema, DocumentSchema, AccumulationRegisterSchema)


def same_configuration_value(trusted, expected):
    """Closed immutable shape comparison, never caller equality/presentation hooks.

    Walk the already admitted graph on the left. No digest-only admission and
    no arbitrary dataclass or UUID subclass receives an equality callback.
    """
    kind = type(trusted)
    if kind is not type(expected):
        return False
    if kind in (str, bytes, int, bool, type(None)):
        return trusted == expected
    if kind is UUID:
        return type(trusted.int) is int and type(expected.int) is int and trusted.int == expected.int
    if kind is AccumulationRegisterKind:
        return trusted is expected
    if kind is tuple:
        return len(trusted) == len(expected) and all(
            same_configuration_value(a, b) for a, b in zip(trusted, expected))
    if kind in _RECORDS:
        return all(same_configuration_value(object.__getattribute__(trusted, f.name),
                                           object.__getattribute__(expected, f.name))
                   for f in fields(kind))
    return False


@dataclass(frozen=True, slots=True, eq=False)
class _SourceSnapshot:
    owner: object
    backend: object
    connection: object
    database_id: UUID
    generation: int
    configuration: InventoryApplicationConfiguration


def capture(view, admitted):
    """Private _begin seam; writer/receipt/core profiles intentionally get none."""
    if (view._operation_id is None and type(admitted) is InventoryApplicationConfiguration
            and type(admitted.profile) is str and admitted.profile == PROFILE):
        view._inventory_source = _SourceSnapshot(view, view._backend, view._connection,
            view.database_id, view.configuration_generation, admitted)


def read(view, *, expected=_UNSPECIFIED):
    from .sqlite_catalog import SQLiteCatalogBackend, _View
    if type(view) is not _View or type(view._backend) is not SQLiteCatalogBackend:
        raise BackendError('unsupported')
    view._require()
    backend = view._backend
    if backend._closed:
        raise BackendError('closed')
    record = view._inventory_source
    if (backend.format_version != 15 or view._operation_id is not None
            or type(record) is not _SourceSnapshot):
        raise BackendError('unsupported')
    if (backend._active is not view or record.owner is not view or record.backend is not backend
            or record.connection is not view._connection or view._connection is None
            or not view._connection.in_transaction
            or not same_configuration_value(record.database_id, view.database_id)
            or not same_configuration_value(record.generation, view.configuration_generation)
            or not same_configuration_value(record.database_id, backend.database_id)
            or not same_configuration_value(record.generation, backend.configuration_generation)):
        raise BackendError('schema_changed')
    if expected is not _UNSPECIFIED and not same_configuration_value(record.configuration, expected):
        raise BackendError('schema_changed')
    return record.configuration

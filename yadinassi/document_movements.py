"""Host-only recorder intent primitives; not an enabled BSL posting API.

No handler order, automatic movement write, or native posting semantics are
assumed here. A future admitted profile must supply recorder declarations.
"""
from dataclasses import dataclass
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from .catalog_backend import BackendError, FieldSchema
from .catalog_qualifiers import normalize_field
from .document_backend import DocumentKey

MAX_MOVEMENT_ROWS = 10000


@dataclass(frozen=True, slots=True)
class RecorderRegisterSchema:
    identity: UUID
    recorder_documents: tuple[UUID, ...]
    fields: tuple[FieldSchema, ...]


@dataclass(frozen=True, slots=True)
class RecorderMovementRow:
    line_number: int
    active: bool
    values: tuple


@dataclass(frozen=True, slots=True)
class RecorderReplacement:
    register_id: UUID
    recorder: DocumentKey
    rows: tuple[RecorderMovementRow, ...]
    expected_snapshot: str


def validate_replacement(schema, request, database_id):
    """Validate a complete recorder partition, never an arbitrary set filter.

    A replacement always carries an observed partition hash, including empty
    partitions. This host optimistic-lock contract is not native DataVersion.
    """
    if (type(schema) is not RecorderRegisterSchema or type(request) is not RecorderReplacement
            or type(database_id) is not UUID or not database_id.int):
        raise BackendError('invalid_input')
    if (type(schema.identity) is not UUID or not schema.identity.int
            or type(schema.recorder_documents) is not tuple
            or not 1 <= len(schema.recorder_documents) <= 256
            or any(type(v) is not UUID or not v.int for v in schema.recorder_documents)
            or len(set(schema.recorder_documents)) != len(schema.recorder_documents)
            or type(schema.fields) is not tuple or not 1 <= len(schema.fields) <= 64
            or any(type(f) is not FieldSchema for f in schema.fields)):
        raise BackendError('invalid_input')
    if (any(type(f.identity) is not UUID or not f.identity.int or type(f.name) is not str
            or not f.name for f in schema.fields)
            or len({f.identity for f in schema.fields}) != len(schema.fields)
            or len({f.name.casefold() for f in schema.fields}) != len(schema.fields)):
        raise BackendError('invalid_input')
    key = request.recorder
    if type(key) is not DocumentKey or any(type(v) is not UUID or not v.int
            for v in (key.database_id, key.document_id, key.record_id)):
        raise BackendError('invalid_input')
    if request.register_id != schema.identity or key.database_id != database_id:
        raise BackendError('conflict')
    if key.document_id not in schema.recorder_documents:
        raise BackendError('unsupported')
    if (type(request.expected_snapshot) is not str or len(request.expected_snapshot) != 64
            or any(c not in '0123456789abcdef' for c in request.expected_snapshot)
            or type(request.rows) is not tuple or len(request.rows) > MAX_MOVEMENT_ROWS):
        raise BackendError('invalid_input')
    scalar_types = {'string': str, 'number': Decimal, 'boolean': bool, 'datetime': datetime}
    if any(f.kind not in scalar_types or f.target_catalog_id is not None
           or (f.kind == 'boolean' and f.qualifiers != ())
           or (f.kind == 'datetime' and f.qualifiers != ('DateTime',))
           for f in schema.fields):
        raise BackendError('unsupported')
    for index, row in enumerate(request.rows, 1):
        if (type(row) is not RecorderMovementRow or type(row.line_number) is not int
                or row.line_number != index or type(row.active) is not bool
                or type(row.values) is not tuple or len(row.values) != len(schema.fields)):
            raise BackendError('invalid_input')
        for value, field in zip(row.values, schema.fields):
            if type(value) is not scalar_types[field.kind]:
                raise BackendError('invalid_input')
            if field.kind == 'datetime' and (value.tzinfo is not None or value.microsecond):
                raise BackendError('invalid_input')
        try:
            normalized = tuple(normalize_field(v, f) for v, f in zip(row.values, schema.fields))
        except (TypeError, ValueError):
            raise BackendError('invalid_input') from None
        if any(type(a) is not type(b) or a != b for a, b in zip(normalized, row.values)):
            raise BackendError('invalid_input')
    return request


def mutation_identity(request):
    """Disjoint recorder partitions may share a register within one UoW."""
    if type(request) is not RecorderReplacement or type(request.recorder) is not DocumentKey:
        raise BackendError('invalid_input')
    return ('recorder_movement', request.register_id, request.recorder)

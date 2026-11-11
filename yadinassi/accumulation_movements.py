"""Host accumulation occurrence storage contract and exact resource arithmetic.

An occurrence belongs to one recorder and line, not to a unique dimension key.
Direction is an exact enum, deliberately without Boolean/numeric coercion or a
signed-resource interpretation. Balance/Turnovers aggregation, native write
behavior, source grants and runtime binding are outside this storage contract.
The private resource arithmetic helper does not interpret movement directions.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from .catalog_backend import BackendError, FieldSchema
from .catalog_qualifiers import normalize_field
from .document_backend import DocumentKey

MAX_MOVEMENT_ROWS = 10000
MAX_FIELDS = 64
MAX_DIMENSIONS = 16
MAX_RECORDERS = 256


class AccumulationRegisterKind(Enum):
    BALANCE = 'balance'


class AccumulationDirection(Enum):
    RECEIPT = 'receipt'
    EXPENSE = 'expense'

    def __str__(self):
        raise ValueError('accumulation record type presentation is outside this profile')


@dataclass(frozen=True, slots=True)
class AccumulationRegisterSchema:
    identity: UUID
    name: str
    recorder_documents: tuple[UUID, ...]
    dimensions: tuple[FieldSchema, ...]
    resources: tuple[FieldSchema, ...]
    attributes: tuple[FieldSchema, ...] = ()
    kind: AccumulationRegisterKind = AccumulationRegisterKind.BALANCE

    @property
    def fields(self):
        return self.dimensions + self.resources + self.attributes


@dataclass(frozen=True, slots=True)
class AccumulationMovementRow:
    line_number: int
    period: datetime
    active: bool
    direction: AccumulationDirection
    dimensions: tuple
    resources: tuple[Decimal, ...]
    attributes: tuple = ()


@dataclass(frozen=True, slots=True)
class AccumulationReplacement:
    register_id: UUID
    recorder: DocumentKey
    rows: tuple[AccumulationMovementRow, ...]
    expected_snapshot: str


@dataclass(frozen=True, slots=True)
class AccumulationPartition:
    register_id: UUID
    recorder: DocumentKey
    revision: int
    rows: tuple[AccumulationMovementRow, ...]
    snapshot: str


@dataclass(frozen=True, slots=True)
class AccumulationOutcome:
    register_id: UUID
    recorder: DocumentKey
    revision: int
    snapshot: str
    row_count: int


_SCALAR_TYPES = {'string': str, 'number': Decimal, 'boolean': bool, 'datetime': datetime}
_RESERVED = {'period', 'период', 'recorder', 'регистратор', 'active', 'активность',
             'linenumber', 'номерстроки', 'recordtype', 'виддвижения',
             'direction', 'направление'}


def _uuid(value):
    if type(value) is not UUID or not value.int:
        raise BackendError('invalid_input')


def _date(value):
    if type(value) is not datetime or value.tzinfo is not None or value.microsecond:
        raise BackendError('invalid_input')


def validate_schema(schema):
    """Validate even empty replacements; unsupported qualifiers cannot hide."""
    if type(schema) is not AccumulationRegisterSchema:
        raise BackendError('invalid_input')
    _uuid(schema.identity)
    if (type(schema.name) is not str or not schema.name or len(schema.name) > 128
            or type(schema.recorder_documents) is not tuple
            or not 1 <= len(schema.recorder_documents) <= MAX_RECORDERS
            or any(type(v) is not UUID or not v.int for v in schema.recorder_documents)
            or len(set(schema.recorder_documents)) != len(schema.recorder_documents)
            or any(type(v) is not tuple for v in
                   (schema.dimensions, schema.resources, schema.attributes))
            or not 0 <= len(schema.dimensions) <= MAX_DIMENSIONS
            or not schema.resources or len(schema.fields) > MAX_FIELDS):
        raise BackendError('invalid_input')
    if type(schema.kind) is not AccumulationRegisterKind:
        raise BackendError('unsupported')
    identities = {schema.identity}
    names = _RESERVED.copy()
    try:
        schema.name.encode('utf-8')
        for field in schema.fields:
            if type(field) is not FieldSchema:
                raise BackendError('invalid_input')
            _uuid(field.identity)
            if (type(field.name) is not str or not field.name or len(field.name) > 128
                    or field.identity in identities or field.name.casefold() in names):
                raise BackendError('invalid_input')
            field.name.encode('utf-8')
            identities.add(field.identity)
            names.add(field.name.casefold())
            if (type(field.kind) is not str or field.kind not in _SCALAR_TYPES
                    or field.target_catalog_id is not None):
                raise BackendError('unsupported')
            q = field.qualifiers
            if type(q) is not tuple:
                raise BackendError('invalid_input')
            if field.kind == 'string' and (len(q) != 1 or type(q[0]) is not int
                                          or not 0 <= q[0] <= 65536):
                raise BackendError('invalid_input')
            if field.kind == 'number' and (len(q) != 3 or type(q[0]) is not int
                    or type(q[1]) is not int or not 1 <= q[0] <= 38
                    or not 0 <= q[1] <= q[0] or type(q[2]) is not str
                    or q[2] not in ('Any', 'Nonnegative')):
                raise BackendError('invalid_input')
            if field.kind == 'boolean' and q:
                raise BackendError('invalid_input')
            if field.kind == 'datetime' and (len(q) != 1 or type(q[0]) is not str
                                             or q[0] != 'DateTime'):
                raise BackendError('unsupported')
    except UnicodeError:
        raise BackendError('invalid_input') from None
    if any(field.kind != 'number' for field in schema.resources):
        raise BackendError('unsupported')
    return schema


def _sum_resource_vectors(schema, vectors, weights):
    """Exact host arithmetic, not Balance/Turnovers or a result-field schema.

    Accept bounded exact tuples of normalized resource tuples and caller-chosen
    exact int +1/-1 weights. Direction mapping, row selection and grouping are
    deliberately absent. Stored numeric qualifiers validate inputs only: an
    output may exceed their width or be negative for a Nonnegative resource.
    Results use each resource's declared scale and canonical positive zero;
    this representation does not assert native aggregate field qualifiers.
    Neither inputs nor the ambient Decimal context are modified.
    """
    validate_schema(schema)
    if (type(vectors) is not tuple or type(weights) is not tuple
            or len(vectors) > MAX_MOVEMENT_ROWS or len(weights) != len(vectors)):
        raise BackendError('invalid_input')
    totals = [0] * len(schema.resources)
    for vector, weight in zip(vectors, weights):
        if (type(vector) is not tuple or len(vector) != len(schema.resources)
                or type(weight) is not int or weight not in (-1, 1)):
            raise BackendError('invalid_input')
        for index, (value, field) in enumerate(zip(vector, schema.resources)):
            try:
                normalized = normalize_field(value, field)
            except (TypeError, ValueError):
                raise BackendError('invalid_input') from None
            if type(normalized) is not Decimal or normalized != value:
                raise BackendError('invalid_input')
            sign, digits, exponent = normalized.as_tuple()
            coefficient = 0
            for digit in digits:
                coefficient = coefficient * 10 + digit
            # Normalization bounds the coefficient and exponent before this
            # power, including extreme-exponent zero. Equality above refuses
            # any rounding/clamping instead of silently changing the input.
            coefficient *= 10 ** (exponent + field.qualifiers[1])
            totals[index] += weight * (-coefficient if sign else coefficient)
    result = []
    for total, field in zip(totals, schema.resources):
        # Both int conversion and tuple construction are exact: no Decimal
        # addition, multiplication, quantize, unary sign or context precision.
        sign, digits, _ = Decimal(total).as_tuple()
        result.append(Decimal((sign, digits, -field.qualifiers[1])))
    return tuple(result)


def validate_replacement(schema, request, database_id):
    """Strict whole-partition intent, with a host optimistic snapshot token.

    Rows use contiguous host line ordinals. Equal dimensions, periods and even
    entire scalar payloads are retained as separate occurrences. Neither rule
    asserts unmeasured native record-set duplicate or numbering behavior.
    """
    validate_schema(schema)
    _uuid(database_id)
    if type(request) is not AccumulationReplacement:
        raise BackendError('invalid_input')
    _uuid(request.register_id)
    key = request.recorder
    if type(key) is not DocumentKey:
        raise BackendError('invalid_input')
    for value in (key.database_id, key.document_id, key.record_id):
        _uuid(value)
    if request.register_id != schema.identity or key.database_id != database_id:
        raise BackendError('conflict')
    if key.document_id not in schema.recorder_documents:
        raise BackendError('unsupported')
    if (type(request.expected_snapshot) is not str or len(request.expected_snapshot) != 64
            or any(c not in '0123456789abcdef' for c in request.expected_snapshot)
            or type(request.rows) is not tuple or len(request.rows) > MAX_MOVEMENT_ROWS):
        raise BackendError('invalid_input')
    for index, row in enumerate(request.rows, 1):
        if (type(row) is not AccumulationMovementRow or type(row.line_number) is not int
                or row.line_number != index or type(row.active) is not bool
                or type(row.direction) is not AccumulationDirection):
            raise BackendError('invalid_input')
        _date(row.period)
        for values, fields in ((row.dimensions, schema.dimensions),
                               (row.resources, schema.resources),
                               (row.attributes, schema.attributes)):
            if type(values) is not tuple or len(values) != len(fields):
                raise BackendError('invalid_input')
            for value, field in zip(values, fields):
                if type(value) is not _SCALAR_TYPES[field.kind]:
                    raise BackendError('invalid_input')
                if field.kind == 'datetime':
                    _date(value)
                try:
                    normalized = normalize_field(value, field)
                except (TypeError, ValueError):
                    raise BackendError('invalid_input') from None
                if type(normalized) is not type(value) or normalized != value:
                    raise BackendError('invalid_input')
    return request


def mutation_identity(request):
    """Separate from information-register mutation and dimension key domains."""
    if type(request) is not AccumulationReplacement or type(request.recorder) is not DocumentKey:
        raise BackendError('invalid_input')
    for value in (request.register_id, request.recorder.database_id,
                  request.recorder.document_id, request.recorder.record_id):
        _uuid(value)
    return ('accumulation_movement', request.register_id, request.recorder)

"""Shared closed physical scalar declarations for admitted SQLite row schemas."""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError, FieldSchema
from .sqlite_catalog_layout import quote_identifier, encode_columns, decode_columns


def attribute_column(field):
    if type(field) is not FieldSchema or type(field.identity) is not UUID or not field.identity.int:
        raise BackendError('invalid_input')
    return 'attr_' + field.identity.hex


def bounded_value_sql(column, limit):
    # Never transfer an oversized physical value into Python. The invalid
    # BLOB sentinel is rejected by the existing typed decoder (unlike NULL,
    # which could be a valid EmptyRef here).
    return f"CASE WHEN length(CAST({column} AS BLOB))>{limit} THEN x'' ELSE {column} END"


def bounded_attribute_sql(column, field):
    if field.kind == 'string':
        limit = field.qualifiers[0] * 4
    elif field.kind in ('catalog_ref','enum_ref'):
        limit = 36
    else:
        limit = {'number':20,'boolean':1,'datetime':14}[field.kind]
    return bounded_value_sql(column,limit)


def attribute_definitions(fields, catalog_layout, *, enum_domain=None):
    """Exact scalar storage; references use SQL NULL for the empty reference."""
    definitions = []
    for field in fields:
        name = quote_identifier(attribute_column(field))
        if field.kind == 'enum_ref':
            from .sqlite_catalog import _enum_field
            _enum_field(field,enum_domain)
            declaration = 'TEXT NOT NULL'
        elif field.target_enum_id is not None:
            raise BackendError('unsupported')
        elif field.kind == 'catalog_ref':
            target = quote_identifier(catalog_layout.table_name(field.target_catalog_id))
            declaration = f'TEXT REFERENCES {target}(record_id) DEFERRABLE INITIALLY DEFERRED'
        elif field.kind == 'boolean':
            declaration = f'INTEGER NOT NULL CHECK({name} IN(0,1))'
        elif field.kind == 'number':
            declaration = number_definition(name,field)
        elif field.kind in ('string','datetime'):
            declaration = 'TEXT NOT NULL'
        else:
            raise BackendError('unsupported')
        definitions.append(name+' '+declaration)
    return tuple(definitions)

@dataclass(frozen=True,slots=True)
class PhysicalFields:
    """Reusable schema view for ports whose stored field order is a subset."""
    fields: tuple[FieldSchema,...]


_WIDE_BIAS = 1 << 127


def _number_domain(field):
    if (type(field) is not FieldSchema or type(field.kind) is not str or field.kind != 'number'
            or type(field.qualifiers) is not tuple or len(field.qualifiers) != 3):
        raise BackendError('invalid_input')
    precision, scale, sign = field.qualifiers
    if (type(precision) is not int or type(scale) is not int or not 1<=precision<=38
            or not 0<=scale<=precision or type(sign) is not str or sign not in ('Any','Nonnegative')):
        raise BackendError('invalid_input')
    return precision,scale,sign


def number_storage(field):
    return 'INTEGER' if _number_domain(field)[0] <= 18 else 'BLOB'


def number_definition(quoted_name, field):
    """Declaration suffix for a provider-owned, already quoted column name."""
    return f"{number_storage(field)} NOT NULL CHECK({number_check(quoted_name,field)})"


def number_check(column, field):
    """Validate the exact persisted coefficient, including externally damaged rows."""
    precision,_,sign = _number_domain(field)
    high = 10**precision-1
    low = 0 if sign == 'Nonnegative' else -high
    if precision <= 18:
        return (f"typeof({column})='integer' AND {column} BETWEEN {low} AND {high}")
    lo = (low+_WIDE_BIAS).to_bytes(16,'big').hex()
    hi = (high+_WIDE_BIAS).to_bytes(16,'big').hex()
    return (f"typeof({column})='blob' AND length({column})=16 AND {column} BETWEEN x'{lo}' AND x'{hi}'")


def encode_number(value, field):
    """Represent the exact scaled integer; no ambient Decimal arithmetic."""
    precision,scale,sign = _number_domain(field)
    if type(value) is not Decimal or not value.is_finite(): raise BackendError('invalid_input')
    negative,digits,exponent = value.as_tuple()
    if value.is_zero():
        integer = 0
    else:
        power = exponent + scale
        if power < 0:
            if -power >= len(digits) or any(digits[power:]): raise BackendError('invalid_input')
            digits = digits[:power]
            power = 0
        if len(digits)+power > precision or (negative and sign == 'Nonnegative'):
            raise BackendError('invalid_input')
        integer = 0
        for digit in digits: integer = integer*10+digit
        integer *= 10**power
        if negative: integer = -integer
    if precision <= 18: return integer
    return (integer+_WIDE_BIAS).to_bytes(16,'big')


def raw_number_coefficient(raw):
    if type(raw) is int: return raw
    if type(raw) is bytes and len(raw)==16: return int.from_bytes(raw,'big')-_WIDE_BIAS
    raise BackendError('integrity')


def decode_number(raw, field):
    precision,scale,sign = _number_domain(field)
    if type(raw) is not (int if precision<=18 else bytes): raise BackendError('integrity')
    integer = raw_number_coefficient(raw)
    if abs(integer) >= 10**precision or (integer<0 and sign=='Nonnegative'):
        raise BackendError('integrity')
    return Decimal((int(integer<0),tuple(int(digit) for digit in str(abs(integer))),-scale))


def encode_typed_columns(tagged_values, schema, *, enum_domain=None):
    raw = encode_columns(tagged_values,schema,enum_domain=enum_domain)
    return tuple(encode_number(Decimal(value),field) if field.kind=='number' else value
                 for field,value in zip(schema.fields,raw))


def decode_typed_columns(raw, schema, *, enum_domain=None):
    if len(raw)!=len(schema.fields): raise BackendError('integrity')
    values = tuple(format(decode_number(value,field),'f') if field.kind=='number' else value
                   for field,value in zip(schema.fields,raw))
    return decode_columns(values,schema,enum_domain=enum_domain)

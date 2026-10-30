"""Read one independently compiled Catalog through its active private graph.

Synthetic bounded NVC/BCD admission is not native acceptance of new layouts.
Opaque reference/version bytes remain private; no native or XML inputs exist.
"""
from decimal import Decimal
import re

from .config_catalog_binding import (CatalogBinding, BoundCatalogAttribute,
                                    BoundFieldPlacement, _uuid, _name, CatalogBindingError)
from .filedb_catalog import (CatalogReader, PhysicalCatalog, _BindingHandle,
                            _CatalogBindingGraph, InvalidStructure, ResourceLimit,
                            UnsupportedLayout)
from .filedb_records import (RecordLimits, PhysicalRecords, PhysicalRecord,
                            PhysicalValue, format_discriminator)

_PHYSICAL = re.compile(r'_(Reference|FLD)([1-9][0-9]{0,9})\Z', re.ASCII)


def _bad_binding():
    raise UnsupportedLayout('compiled_binding_invalid')


def _identifier(value, prefix):
    if type(value) is not str or len(value) > 20:
        _bad_binding()
    matched = _PHYSICAL.fullmatch(value)
    if matched is None or matched[1] != prefix or int(matched[2]) > 2147483647:
        _bad_binding()
    return int(matched[2])


def _validate_binding(binding, budget):
    """Reconstruct from retained logical facts, not caller-supplied placements.

    Frozen dataclasses can be manually constructed/replaced. This check prevents
    forged widths/offsets and declaration aliases from authorizing a data read;
    it does not certify that caller-owned metadata came from a particular file.
    """
    if type(binding) is not CatalogBinding:
        _bad_binding()
    budget.charge('output_bytes', 8192)
    budget.charge('bytes_processed', 8192)
    budget.charge('tokens', 128)
    if not _uuid(binding.metadata_uuid):
        _bad_binding()
    try:
        _name(binding.name)
    except CatalogBindingError:
        _bad_binding()
    if (type(binding.code_type) is not int or binding.code_type not in (0, 1)
            or type(binding.description_length) is not int or not 0 <= binding.description_length <= 2047
            or type(binding.code_length) is not int or not 1 <= binding.code_length <= (38 if binding.code_type == 0 else 2047)
            or type(binding.recordlock) is not str or binding.recordlock != '0'
            or type(binding.format_item) is not int or binding.format_item != 0
            or type(binding.attributes) is not tuple or len(binding.attributes) != 2):
        _bad_binding()
    a, b = binding.attributes
    for item in (a, b):
        if (type(item) is not BoundCatalogAttribute or not _uuid(item.metadata_uuid)
                or type(item.type_token) is not str or type(item.qualifiers) is not tuple
                or len(item.qualifiers) > 3 or any(type(q) is not int for q in item.qualifiers)):
            _bad_binding()
        try:
            _name(item.name)
        except CatalogBindingError:
            _bad_binding()
    if (len({binding.metadata_uuid, a.metadata_uuid, b.metadata_uuid}) != 3 or a.name == b.name
            or a.type_token != 'S' or b.type_token != 'N'
            or len(a.qualifiers) != 2 or a.qualifiers[1] != 1 or not 1 <= a.qualifiers[0] <= 2047
            or len(b.qualifiers) != 3 or b.qualifiers[2] != 0 or not 1 <= b.qualifiers[0] <= 38
            or not 0 <= b.qualifiers[1] <= b.qualifiers[0]):
        _bad_binding()
    ids = (_identifier(binding.table_name, 'Reference'), _identifier(a.physical_name, 'FLD'),
           _identifier(b.physical_name, 'FLD'))
    if len(set(ids)) != 3:
        _bad_binding()
    precision, scale, _ = b.qualifiers
    expected = (('_IDRREF', 'B', 0, 16, 0, 'CS'), ('_VERSION', 'RV', 0, 0, 0, 'CS'),
                ('_MARKED', 'L', 0, 0, 0, 'CS'), ('_PREDEFINEDID', 'B', 0, 16, 0, 'CS'),
                ('_CODE', 'N' if binding.code_type == 0 else 'NVC', 0, binding.code_length, 0, 'CS' if binding.code_type == 0 else 'CI'),
                (a.physical_name, 'NVC', 0, a.qualifiers[0], 0, 'CI'),
                (b.physical_name, 'N', 0, precision, scale, 'CS'))
    widths = (16, 16, 1, 16, (binding.code_length + 2) // 2 if binding.code_type == 0 else 2 + 2 * binding.code_length, 2 + 2 * a.qualifiers[0], (precision + 2) // 2)
    if binding.description_length:
        expected = expected[:5] + (('_DESCRIPTION', 'NVC', 0, binding.description_length, 0, 'CI'),) + expected[5:]
        widths = widths[:5] + (2 + 2 * binding.description_length,) + widths[5:]
    count = len(expected)
    size = 1 + sum(widths)
    if (size > 4096 or type(binding.record_size) is not int or binding.record_size != size
            or type(binding.declarations) is not tuple or len(binding.declarations) != count
            or type(binding.placements) is not tuple or len(binding.placements) != count):
        _bad_binding()
    for actual, wanted in zip(binding.declarations, expected):
        if (type(actual) is not tuple or len(actual) != 6
                or any(type(v) is not t for v, t in zip(actual, (str, str, int, int, int, str)))
                or actual != wanted):
            _bad_binding()
    offsets = [0] * count
    cursor = 1
    for index in (1, 0, *range(2, count)):
        offsets[index] = cursor
        cursor += widths[index]
    for i, place in enumerate(binding.placements):
        if (type(place) is not BoundFieldPlacement or type(place.offset) is not int
                or type(place.width) is not int or place.offset != offsets[i] or place.width != widths[i]
                or type(place.declaration) is not tuple or len(place.declaration) != 6
                or any(type(v) is not t for v, t in zip(place.declaration, (str, str, int, int, int, str)))
                or place.declaration != expected[i]):
            _bad_binding()


def _decode(raw, declaration):
    kind, precision, scale = declaration[1], declaration[3], declaration[4]
    if kind in ('B', 'RV'):
        return raw
    if kind == 'L':
        if raw not in (b'\0', b'\1'):
            raise UnsupportedLayout('boolean_encoding')
        return raw == b'\1'
    if kind == 'NVC':
        units = int.from_bytes(raw[:2], 'little')
        if units > precision:
            raise InvalidStructure('string_length')
        try:
            return raw[2:2 + 2 * units].decode('utf-16-le', errors='strict')
        except UnicodeDecodeError:
            raise UnsupportedLayout('string_encoding') from None
    # Sign 0/1 is conservative local admission. The upstream reader treats
    # any nonzero high nibble as positive; that is not a validity guarantee.
    sign = raw[0] >> 4
    if sign not in (0, 1):
        raise UnsupportedLayout('decimal_sign')
    digits = tuple((raw[(i + 1) // 2] >> (0 if i % 2 == 0 else 4)) & 15
                   for i in range(precision))
    if any(digit > 9 for digit in digits):
        raise UnsupportedLayout('decimal_digit')
    # Even precision has one trailing unused low nibble. Strict zero is an
    # explicit conservative admission, not a claim about every native encoding.
    if precision % 2 == 0 and raw[-1] & 15:
        raise UnsupportedLayout('decimal_padding')
    return Decimal((0 if sign else 1, digits, -scale))


def read_bound_catalog_records(reader, catalog, binding, *, handle, limits=None):
    """Consume the records stage of one CONFIG/PARAMS/records lifetime.

    All-or-nothing private result; failure poisons the graph. Old record APIs,
    profiles and admissions remain unchanged. Caller owns the consistent source.
    """
    if (type(reader) is not CatalogReader or type(catalog) is not PhysicalCatalog
            or reader._catalog is not catalog or type(handle) is not _BindingHandle
            or type(handle._graph) is not _CatalogBindingGraph
            or handle._graph.reader is not reader or handle._graph.catalog is not catalog
            or handle.role != 'records'):
        # Even a caught call-boundary error must not permit a second attempt on
        # this reader's owned graph. Never mutate a foreign supplied handle.
        graph = getattr(reader, '_binding_graph', None) if type(reader) is CatalogReader else None
        if type(graph) is _CatalogBindingGraph:
            graph.failed = True
        raise ValueError('records require their identical active binding graph')
    try:
        handle._check()
        if limits is not None and type(limits) is not RecordLimits:
            raise ValueError('limits must be RecordLimits')
        limits = limits if limits is not None else RecordLimits()
        if (limits.max_slots > 4096 or limits.max_active_records > 4096
                or limits.max_record_bytes > 4096 or limits.max_fields > 16):
            raise ValueError('bound record limits may only be lowered')
        _validate_binding(binding, reader._budget)
        if len(binding.declarations) > limits.max_fields:
            raise ResourceLimit('record_fields')
        if binding.record_size > limits.max_record_bytes:
            raise ResourceLimit('record_bytes')
        table = handle.table
        if table.name != binding.table_name:
            raise UnsupportedLayout('selected_table_count')
        discriminator = format_discriminator(table.format_item)
        if discriminator != 'integer_zero':
            raise UnsupportedLayout('format_' + discriminator)
        if table.recordlock != binding.recordlock:
            raise UnsupportedLayout('recordlock_mismatch')
        if (len(table.fields) != len(binding.declarations)
                or any(item.raw != expected for item, expected in zip(table.fields, binding.declarations))):
            raise UnsupportedLayout('declaration_mismatch')
        data = handle._open_table_data(table)
        length = data.info.logical_length
        if length % binding.record_size:
            raise InvalidStructure('record_file_length')
        slots = length // binding.record_size
        if slots > limits.max_slots:
            raise ResourceLimit('record_slots')
        if not slots:
            return PhysicalRecords(table, data.info, binding.record_size, 0, 'empty_zero_length', (), reader.usage)
        if data._read_range(0, 1) != b'\1':
            raise UnsupportedLayout('reserved_slot_marker')
        rows = []
        for slot in range(1, slots):
            raw = data._read_range(slot * binding.record_size, binding.record_size)
            if raw[0] != 0:
                raise UnsupportedLayout('nonreserved_free_slot')
            if len(rows) >= limits.max_active_records:
                raise ResourceLimit('active_records')
            reader._budget.charge('output_bytes', 2 * len(raw) + 128 + 128 * len(table.fields))
            reader._budget.charge('bytes_processed', 2 * len(raw))
            values = []
            for declaration, place in zip(table.fields, binding.placements):
                field_raw = raw[place.offset:place.offset + place.width]
                value = _decode(field_raw, place.declaration)
                if type(value) is str:
                    reader._budget.charge('output_bytes', len(value.encode('utf-8')))
                values.append(PhysicalValue(declaration, place.offset, place.width, field_raw, value))
            rows.append(PhysicalRecord(slot, raw, tuple(values)))
        return PhysicalRecords(table, data.info, binding.record_size, slots,
                               'empty_reserved' if slots == 1 else 'reserved_and_active', tuple(rows), reader.usage)
    except BaseException:
        handle._graph.failed = True
        raise

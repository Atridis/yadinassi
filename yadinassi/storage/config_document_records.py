"""Read only the native-measured all-active Document profile; fail closed."""
from .config_document_binding import DocumentBinding, PROFILE_IDENTIFIER, _layout
from .config_catalog_binding import CatalogBindingLimits, CatalogBindingError, BoundFieldPlacement
from .config_catalog_records import _decode
from .filedb_catalog import (CatalogReader, PhysicalCatalog, _BindingHandle,
    _CatalogBindingGraph, InvalidStructure, ResourceLimit, UnsupportedLayout)
from .filedb_records import (RecordLimits, PhysicalRecords, PhysicalRecord, PhysicalValue, format_discriminator)
import re

def _validate_binding(binding,budget):
    budget.charge('output_bytes',16384);budget.charge('bytes_processed',16384)
    if type(binding) is not DocumentBinding: raise UnsupportedLayout('document_binding')
    if (type(binding.profile_identifier) is not str or binding.profile_identifier!=PROFILE_IDENTIFIER
        or type(binding.table_name) is not str or re.fullmatch(r'_Document[1-9][0-9]{0,9}',binding.table_name) is None
        or int(binding.table_name[9:])>2147483647
        or type(binding.recordlock) is not str or binding.recordlock!='0'
        or type(binding.format_item) is not int or binding.format_item!=0
        or type(binding.record_size) is not int
        or type(binding.declarations) is not tuple or type(binding.placements) is not tuple):
        raise UnsupportedLayout('document_binding')
    try:ds,ps,size=_layout(binding,binding.attributes,CatalogBindingLimits())
    except CatalogBindingError: raise UnsupportedLayout('document_binding') from None
    if (binding.declarations!=ds or binding.placements!=ps or binding.record_size!=size
        or any(type(x) is not BoundFieldPlacement or type(x.offset) is not int or type(x.width) is not int
               or type(x.declaration) is not tuple or any(type(v) is not type(w) for v,w in zip(x.declaration,d))
               for x,d in zip(binding.placements,ds))
        or any(type(v) is not type(w) for d,e in zip(binding.declarations,ds) for v,w in zip(d,e))):
        raise UnsupportedLayout('document_binding')

def read_bound_document_records(reader, catalog, binding, *, handle, limits=None):
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
        RecordLimits.__post_init__(limits)
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
        # !todo Document deletion/free chains require dedicated native evidence.
        # Even a dangling reserved free head is not admitted as all-active.
        if data._read_range(1,4)!=b'\0'*4:
            raise UnsupportedLayout('document_free_head')
        rows = []
        for slot in range(1, slots):
            raw = data._read_range(slot * binding.record_size, binding.record_size)
            if raw[0] != 0:
                raise UnsupportedLayout('nonreserved_free_slot')
            # !todo Logical deletion on Documents needs a native witness.
            if raw[33] != 0:
                raise UnsupportedLayout('document_deletion_mark')
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

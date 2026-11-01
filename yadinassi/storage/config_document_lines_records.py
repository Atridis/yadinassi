"""Read the native-measured all-active Items profile; fail closed.

Run 41263661105/report 6977835f: both column orders and initial/rewritten
four active rows plus reserved slot, 605 bytes = 5 * 121. Owner raw16 joins
Document raw UUID, N5 LineNo defines order; key raw4 is opaque and NOT order.
Zero/reserved-only are structural empty cases, not additional native evidence.
"""
from .config_document_lines_binding import DocumentLinesBinding, PROFILE_IDENTIFIER, _layout
from .config_catalog_binding import CatalogBindingLimits, CatalogBindingError, BoundFieldPlacement
from .config_catalog_records import _decode
from .filedb_catalog import (CatalogReader, PhysicalCatalog, _BindingHandle,
    _CatalogBindingGraph, InvalidStructure, ResourceLimit, UnsupportedLayout)
from .filedb_records import (RecordLimits, PhysicalRecords, PhysicalRecord, PhysicalValue, format_discriminator)
import re

def _validate_binding(binding,budget):
    budget.charge('output_bytes',16384);budget.charge('bytes_processed',16384)
    if type(binding) is not DocumentLinesBinding: raise UnsupportedLayout('document_lines_binding')
    if (type(binding.profile_identifier) is not str or binding.profile_identifier!=PROFILE_IDENTIFIER
        or type(binding.table_name) is not str or re.fullmatch(r'_Document[1-9][0-9]{0,9}_VT[1-9][0-9]{0,9}',binding.table_name) is None
        or binding.table_name!='_Document'+str(binding.document_id)+'_VT'+str(binding.section_id)
        or type(binding.recordlock) is not str or binding.recordlock!='0'
        or type(binding.format_item) is not int or binding.format_item!=0
        or type(binding.record_size) is not int
        or type(binding.declarations) is not tuple or type(binding.placements) is not tuple):
        raise UnsupportedLayout('document_lines_binding')
    try:ds,ps,size=_layout(binding,binding.attributes,CatalogBindingLimits())
    except CatalogBindingError: raise UnsupportedLayout('document_lines_binding') from None
    if (binding.declarations!=ds or binding.placements!=ps or binding.record_size!=size
        or any(type(x) is not BoundFieldPlacement or type(x.offset) is not int or type(x.width) is not int
               or type(x.declaration) is not tuple or any(type(v) is not type(w) for v,w in zip(x.declaration,d))
               for x,d in zip(binding.placements,ds))
        or any(type(v) is not type(w) for d,e in zip(binding.declarations,ds) for v,w in zip(d,e))):
        raise UnsupportedLayout('document_lines_binding')

def read_bound_document_lines_records(reader, catalog, binding, *, handle, limits=None):
    """Consume the records stage of one CONFIG/PARAMS/Document/Items lifetime.

    All-or-nothing private result; failure poisons the graph. Old record APIs,
    profiles and admissions remain unchanged. Caller owns the consistent source.
    """
    if (type(reader) is not CatalogReader or type(catalog) is not PhysicalCatalog
            or reader._catalog is not catalog or type(handle) is not _BindingHandle
            or type(handle._graph) is not _CatalogBindingGraph
            or handle._graph.reader is not reader or handle._graph.catalog is not catalog
            or handle.role != 'document_lines'):
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
        # !todo Items deletion/free chains require dedicated native evidence.
        # Even a dangling reserved free head is not admitted as all-active.
        if data._read_range(1,4)!=b'\0'*4:
            raise UnsupportedLayout('document_lines_free_head')
        rows = [];owners={};keys=set()
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
            owner=values[0].value;key=values[1].value;line=values[2].value
            if owner==bytes(16):raise InvalidStructure('items_owner_zero')
            if (owner,key) in keys:raise InvalidStructure('items_key_duplicate')
            keys.add((owner,key))
            if line<1 or line>4096 or line!=int(line):raise UnsupportedLayout('items_line_number')
            number=int(line);seen=owners.setdefault(owner,set())
            if number in seen:raise InvalidStructure('items_line_duplicate')
            seen.add(number)
            rows.append(PhysicalRecord(slot, raw, tuple(values)))
        for seen in owners.values():
            if seen!=set(range(1,len(seen)+1)):raise UnsupportedLayout('items_line_gap')
        return PhysicalRecords(table, data.info, binding.record_size, slots,
                               'empty_reserved' if slots == 1 else 'reserved_and_active', tuple(rows), reader.usage)
    except BaseException:
        handle._graph.failed = True
        raise

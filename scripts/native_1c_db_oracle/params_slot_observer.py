"""Bounded PARAMS slot observations, not framing or runtime acceptance.

Offset-one u32LE links are one falsifiable hypothesis. Nonzero markers are not
asserted to be free, and unlinked markers are not automatically malformed.
"""
from __future__ import annotations

import hashlib
import json
import catalog_binding_reader as loader

MAX_SLOTS = 4096
RECIPE_ID = 'params_slot_offset1_u32le_census_v1'
RECIPE_DESCRIPTION = {
    'identifier': RECIPE_ID, 'profile': 'params_dbnames_8380_8192_v1',
    'candidate_stride': 301, 'max_slots': MAX_SLOTS,
    'links': 'reserved_and_nonzero_only_offset1_u32le_zero_sentinel',
    'markers': 'first_and_later_zero_one_other',
    'filenames': 'later_zero_only_strict_utf16le_fixed_ascii_DBNAMES_counts',
    'chain': 'bounded_head_traversal_terminated_out_of_range_cycle_zero_marker_target',
    'ownership': 'one_catalog_data_and_blob_mapping_no_blob_body',
    'runtime_support': 'not_claimed',
}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE_DESCRIPTION, sort_keys=True,
    separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def _class(marker):
    return 'zero' if marker == 0 else 'one' if marker == 1 else 'other'


def observe(read_at, file_size, *, limits=None):
    """Consume one private catalog graph; return only finite counts/classes.

Limits are the exact shared CatalogLimits type. No reader, raw bytes, indices,
names or intermediate result escapes, including on failure. No retry occurs.
"""
    c = loader.catalog_module
    n = loader._load_storage()['filedb_named_file']
    profile = n.DBNamesProfile(n.DBNAMES_DECLARATIONS, '0', 0)
    reader = c.CatalogReader(read_at, file_size, limits=limits)
    try:
        catalog = reader.read_catalog()
        selected = None
        for table in catalog.tables:
            if n._ascii_equal(table.name, 'PARAMS'):
                if selected is not None:
                    raise c.UnsupportedLayout('dbnames_table_ambiguous')
                selected = table
        if selected is None:
            raise c.UnsupportedLayout('dbnames_table_missing')
        if (type(selected.format_item) is not int or selected.format_item != 0
                or selected.recordlock != '0'
                or len(selected.fields) != len(profile.declarations)
                or any(item.raw != expected for item, expected in
                       zip(selected.fields, profile.declarations))):
            raise c.UnsupportedLayout('dbnames_profile_mismatch')
        data = reader._open_table_data(selected)
        blob = reader._open_table_blob(selected)
        stride = profile.record_size
        length = data.info.logical_length
        if length % stride:
            raise c.InvalidStructure('dbnames_record_length')
        if not length:
            raise c.UnsupportedLayout('params_slot_empty_data')
        slots = length // stride
        if slots > MAX_SLOTS:
            raise c.ResourceLimit('dbnames_slots')
        budget = reader._budget
        # Cumulative representation weights before arrays, decoded ints, visited
        # set and output allocation. Scalar raw reads/UTF16 copies add their own
        # charges through the shared named-file helpers. Not an exact heap bound.
        budget.charge('output_bytes', 8192 + 512 * slots)
        budget.charge('bytes_processed', 64 * slots)
        markers = [0] * slots
        links = [0] * slots
        counts = {'zero': 0, 'one': 0, 'other': 0}
        empty = nonempty = matches = 0
        for slot in range(slots):
            base = slot * stride
            marker = n._scalar(data, base, 1)[0]
            markers[slot] = marker
            if slot:
                counts[_class(marker)] += 1
            if not slot or marker:
                links[slot] = int.from_bytes(n._scalar(data, base + 1, 4), 'little')
            else:
                name = n._filename(data, base + profile.placements[0][0])
                if name:
                    nonempty += 1
                else:
                    empty += 1
                matches += int(n._ascii_equal(name, 'DBNAMES'))
        visited = set()
        current = links[0]
        outcome = 'terminated'
        while current:
            if current >= slots:
                outcome = 'out_of_range'
                break
            if current in visited:
                outcome = 'cycle'
                break
            if markers[current] == 0:
                outcome = 'zero_marker_target'
                break
            visited.add(current)
            current = links[current]
        return {
            'recipe_id': RECIPE_ID, 'recipe_sha256': RECIPE_SHA256,
            'data_logical_bytes': length, 'blob_logical_bytes': blob.info.logical_length,
            'candidate_stride': stride, 'candidate_slots': slots,
            'first_marker_class': _class(markers[0]),
            'later_zero_count': counts['zero'], 'later_one_count': counts['one'],
            'later_other_count': counts['other'], 'filename_zero_count': counts['zero'],
            'filename_empty_count': empty, 'filename_nonempty_count': nonempty,
            'dbnames_match_count': matches, 'chain_outcome': outcome,
            'linked_nonzero_count': len(visited),
            'unlinked_nonzero_count': counts['one'] + counts['other'] - len(visited),
            'runtime_support': 'not_claimed',
        }
    finally:
        # Even a captured private graph is consumed: no reuse after a partial
        # scan or mapping failure. Normal callers never receive this reader.
        reader._used = reader._table_opened = reader._table_blob_opened = True
        reader._dbnames_attempted = True

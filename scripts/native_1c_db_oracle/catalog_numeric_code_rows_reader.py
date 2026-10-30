"""One public typed read; bounded private view, never a second observer graph."""
import hashlib
import catalog_binding_reader as loader
from catalog_numeric_code_physical import NumericCodeObservation


def read_numeric_code_rows(read_at, file_size, *, catalog_name, limits=None):
    result = loader.read_catalog_rows(read_at, file_size, catalog_name=catalog_name, limits=limits)
    raw = loader._raw_rows_view(result)
    identity, attributes, binding = raw.identity, raw.attributes, raw.binding
    if (identity.code_type != 0 or binding.code_type != identity.code_type
            or binding.code_length != identity.code_length
            or identity.description_length != 8 or binding.description_length != 8
            or len(attributes.attributes) != 2
            or attributes.attributes[0].name != 'Payload'
            or attributes.attributes[0].type_token != 'S'
            or attributes.attributes[0].qualifiers not in ((32,1),(64,1))
            or attributes.attributes[1].name != 'Amount'
            or attributes.attributes[1].type_token != 'N'
            or attributes.attributes[1].qualifiers != (9,2,0)):
        raise loader.catalog_module.UnsupportedLayout('binding_metadata_profile')
    if len(raw.records.rows) != 1 or len(result.rows) != 1 or raw.records.slots != 2:
        raise loader.catalog_module.UnsupportedLayout('numeric_code_one_active_row')
    table = raw.records.table
    # All referenced objects already belong to the single completed public read.
    # This bounded report projection performs no I/O, metadata compilation or
    # record decoding, and neither expected values nor a case enter selection.
    return NumericCodeObservation('layout_observed', identity, attributes, table,
        hashlib.sha256(table.raw_descriptor).hexdigest(), binding.placements,
        binding.record_size, raw.records, raw.usage, result.rows[0].reference_uuid)

"""Single public typed read for a bounded zero-Code Catalog; no oracle graph."""
from dataclasses import dataclass
import hashlib
import catalog_binding_reader as loader
from catalog_zero_code_physical import ZeroCodeObservation


@dataclass(frozen=True)
class ZeroCodeRowsObservation:
    """Private projection identifying the public-reader acquisition path."""
    physical: ZeroCodeObservation


def read_zero_code_rows(read_at, file_size, *, catalog_name, limits=None):
    result = loader.read_catalog_rows(read_at, file_size, catalog_name=catalog_name, limits=limits)
    raw = loader._raw_rows_view(result)
    identity, attributes, binding = raw.identity, raw.attributes, raw.binding
    if (identity.code_type != 1 or binding.code_type != identity.code_type
            or identity.code_length != 0 or binding.code_length != 0
            or identity.description_length not in (0, 8)
            or binding.description_length != identity.description_length
            or len(attributes.attributes) != 2
            or attributes.attributes[0].name != 'Payload'
            or attributes.attributes[0].type_token != 'S'
            or attributes.attributes[0].qualifiers not in ((32, 1), (64, 1))
            or attributes.attributes[1].name != 'Amount'
            or attributes.attributes[1].type_token != 'N'
            or attributes.attributes[1].qualifiers != (9, 2, 0)):
        raise loader.catalog_module.UnsupportedLayout('binding_metadata_profile')
    if len(raw.records.rows) != 1 or len(result.rows) != 1 or raw.records.slots != 2:
        raise loader.catalog_module.UnsupportedLayout('zero_code_one_active_row')
    table = raw.records.table
    # No second read, metadata parse, binding compile or decoder invocation. All
    # fields are already admitted by the completed public lifetime and budget.
    observation = ZeroCodeObservation('layout_observed', identity, attributes,
        table, hashlib.sha256(table.raw_descriptor).hexdigest(), binding.placements,
        binding.record_size, raw.records, raw.usage, result.rows[0].reference_uuid)
    return ZeroCodeRowsObservation(observation)

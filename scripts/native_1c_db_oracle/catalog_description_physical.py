"""Private Description views: independent measurement and public typed adapter.

The sole layout hypothesis is the established seven fields plus one NVC
_DESCRIPTION immediately after _CODE. Widths come from CONFIG, not a case,
seed, XML manifest, native readback, or a search for a matching row value.
The standalone read_description retains a different valid descriptor as unresolved.
read_description_rows instead requires actual public runtime admission.
"""
from dataclasses import dataclass, replace
import hashlib

import catalog_binding_reader as loader


@dataclass(frozen=True)
class DescriptionObservation:
    status: str
    identity: object
    attributes: object
    table: object
    descriptor_sha256: str
    placements: tuple
    record_size: int
    records: object
    usage: object


def read_description(read_at, file_size, *, catalog_name, limits=None):
    """One frozen-source lifetime; returned descriptors/values are PRIVATE.

    Caller provides the same hardened immutable descriptor boundary as the
    established harness. This function does not open files or native sessions.
    Unresolved observations do not establish row validity or compatibility.
    """
    c = loader.catalog_module
    if (type(catalog_name) is not str or not 1 <= len(catalog_name) <= 256
            or any(ord(x) < 32 or ord(x) == 127 for x in catalog_name)):
        raise c.UnsupportedLayout('binding_catalog_selector')
    try:
        if len(catalog_name.encode('utf-8')) > 1024:
            raise c.UnsupportedLayout('binding_catalog_selector')
    except UnicodeEncodeError:
        raise c.UnsupportedLayout('binding_catalog_selector') from None
    modules = loader._load_storage()
    core, named, dbnames, compiler, rows = (modules[x] for x in (
        'config_catalog_transport', 'filedb_named_file', 'filedb_dbnames',
        'config_catalog_binding', 'config_catalog_records'))
    row_types = modules['filedb_records']
    reader = c.CatalogReader(read_at, file_size, limits=limits)
    catalog = reader.read_catalog()
    graph = c._CatalogBindingGraph(reader, catalog)
    try:
        with graph.stage('config') as handle:
            observation = core._observe_catalog_attributes_from_graph(handle,
                profile=core.ConfigCatalogAttributeProfile(core.DECLARATIONS, '0', 0))
            reader._budget.charge('output_bytes', 65536)
            reader._budget.charge('bytes_processed', 2048 * len(observation.private_fields))
            selected, uuids = None, set()
            for key, identity, attributes in observation.private_fields:
                if key != identity.metadata_uuid or key in uuids:
                    raise c.InvalidStructure('binding_catalog_identity')
                uuids.add(key)
                if identity.name == catalog_name:
                    if selected is not None:
                        raise c.UnsupportedLayout('binding_catalog_ambiguous')
                    selected = identity, attributes
            if selected is None:
                raise c.UnsupportedLayout('binding_catalog_missing')
            identity, attributes = selected
            # This is the observation grammar, NOT native property validity.
            if (type(identity.description_length) is not int
                    or not 0 <= identity.description_length <= 2047
                    or identity.code_length != 2 or identity.code_type != 1
                    or len(attributes.attributes) != 2):
                raise c.UnsupportedLayout('description_metadata_profile')
            a, b = attributes.attributes
            if (a.name != 'Payload' or a.type_token != 'S' or a.qualifiers not in ((32, 1), (64, 1))
                    or b.name != 'Amount' or b.type_token != 'N' or b.qualifiers != (9, 2, 0)):
                raise c.UnsupportedLayout('description_metadata_profile')
        with graph.stage('params') as handle:
            extracted = named._read_dbnames_from_catalog(reader, catalog,
                profile=named.DBNamesProfile(core.DECLARATIONS, '0', 0), _binding_handle=handle)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            parse_limits = dbnames.DBNamesParseLimits()
            reserve = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=parse_limits)
            reader._budget.charge('output_bytes', reserve.output_bytes)
            reader._budget.charge('bytes_processed', reserve.bytes_processed)
            reader._budget.charge('tokens', min(len(extracted.data), parse_limits.max_tokens + 1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=parse_limits)
            # Validate the unchanged subset and independent DBNames identity
            # join. This counterfactual is NEVER returned as a real binding.
            baseline = compiler.compile_catalog_binding(replace(identity, description_length=0),
                attributes, parsed, profile=compiler.CatalogBindingProfile(compiler.PROFILE_IDENTIFIER),
                budget=reader._budget)
        with graph.stage('records', binding=baseline) as handle:
            table = handle.table
            if len(table.fields) > 16:
                raise c.ResourceLimit('record_fields')
            if len({f.name for f in table.fields}) != len(table.fields):
                raise c.UnsupportedLayout('description_field_ambiguous')
            reader._budget.charge('bytes_processed', 2 * len(table.raw_descriptor) + 4096)
            reader._budget.charge('output_bytes', 4096)
            digest = hashlib.sha256(table.raw_descriptor).hexdigest()
            declarations = baseline.declarations
            widths = tuple(x.width for x in baseline.placements)
            if identity.description_length:
                declarations = declarations[:5] + (('_DESCRIPTION', 'NVC', 0,
                    identity.description_length, 0, 'CI'),) + declarations[5:]
                widths = widths[:5] + (2 + 2 * identity.description_length,) + widths[5:]
            # Opening only validates the table data header/ownership. No row
            # reads or length interpretation occur for an unresolved layout.
            data = handle._open_table_data(table)
            match = (type(table.format_item) is int and table.format_item == 0
                     and table.recordlock == '0'
                     and tuple(x.raw for x in table.fields) == declarations)
            if not match:
                result = DescriptionObservation('layout_unresolved', identity, attributes,
                    table, digest, (), 0, None, None)
            else:
                offsets, cursor = [0] * len(widths), 1
                for i in (1, 0, *range(2, len(widths))):
                    offsets[i], cursor = cursor, cursor + widths[i]
                if cursor > 4096:
                    raise c.ResourceLimit('record_bytes')
                placements = tuple(compiler.BoundFieldPlacement(d, offsets[i], widths[i])
                                   for i, d in enumerate(declarations))
                length = data.info.logical_length
                if length % cursor:
                    raise c.InvalidStructure('record_file_length')
                slots = length // cursor
                if slots > 2:
                    raise c.ResourceLimit('active_records')
                if slots != 2:
                    raise c.UnsupportedLayout('description_one_active_row')
                if data._read_range(0, 1) != b'\1':
                    raise c.UnsupportedLayout('reserved_slot_marker')
                raw = data._read_range(cursor, cursor)
                if raw[0] != 0:
                    raise c.UnsupportedLayout('nonreserved_free_slot')
                reader._budget.charge('bytes_processed', 2 * len(raw))
                reader._budget.charge('output_bytes', 2 * len(raw) + 128 + 128 * len(declarations))
                fields = []
                for field, place in zip(table.fields, placements):
                    field_raw = raw[place.offset:place.offset + place.width]
                    value = rows._decode(field_raw, place.declaration)
                    if type(value) is str:
                        reader._budget.charge('output_bytes', len(value.encode('utf-8')))
                    fields.append(row_types.PhysicalValue(field, place.offset, place.width, field_raw, value))
                record = row_types.PhysicalRecord(1, raw, tuple(fields))
                physical = row_types.PhysicalRecords(table, data.info, cursor, slots,
                    'reserved_and_active', (record,), reader.usage)
                result = DescriptionObservation('layout_observed', identity, attributes,
                    table, digest, placements, cursor, physical, None)
        return replace(result, usage=reader.usage)
    except BaseException:
        graph.failed = True
        raise


def public_observation(value):
    """Finite scalar/hash summary only; no names, descriptors or row strings.

    Called only on the private output above, never on untrusted report JSON.
    Native witness comparison and source/postimage bindings belong elsewhere.
    """
    if type(value) is not DescriptionObservation or value.status not in ('layout_observed', 'layout_unresolved'):
        raise ValueError('description_observation_invalid')
    out = dict(status=value.status, descriptor_sha256=value.descriptor_sha256,
               description_length=value.identity.description_length,
               payload_length=value.attributes.attributes[0].qualifiers[0],
               field_count=len(value.table.fields), record_size=value.record_size,
               active_count=0, active_count_known=False, description_ordinal=0, description_offset=0,
               description_width=0, used_utf16_units=0, unicode_scalars=0,
               trailing_spaces=0, utf16_count_matches=False,
               previous_ordinal=0, next_ordinal=0, previous_offset=0, next_offset=0,
               previous_displacement=0, next_displacement=0,
               description_type='unresolved' if value.status == 'layout_unresolved' else 'absent',
               value_sha256='0' * 64)
    if value.status == 'layout_observed':
        out['active_count'] = 1
        out['active_count_known'] = True
        if value.identity.description_length:
            f = value.records.rows[0].fields[5]
            units = int.from_bytes(f.raw[:2], 'little')
            encoded = f.value.encode('utf-16-le', errors='strict')
            out.update(description_ordinal=5, description_offset=f.offset,
                       description_width=f.width, used_utf16_units=units,
                       unicode_scalars=len(f.value), trailing_spaces=len(f.value)-len(f.value.rstrip(' ')),
                       utf16_count_matches=units == len(encoded)//2,
                       description_type='NVC', previous_ordinal=4, next_ordinal=6,
                       previous_offset=value.placements[4].offset,
                       next_offset=value.placements[6].offset,
                       next_displacement=f.width,
                       value_sha256=hashlib.sha256(encoded).hexdigest())
    return out


def read_description_rows(read_at, file_size, *, catalog_name, limits=None):
    """Public typed runtime API once; native witnesses never enter this call.

    The physical view and UUID belong to the same admitted record/owner graph.
    Creating the bounded report view does not open or re-read the database.
    """
    result = loader.read_catalog_rows(read_at, file_size, catalog_name=catalog_name, limits=limits)
    raw = loader._raw_rows_view(result)
    c = loader.catalog_module
    identity, attributes, binding = raw.identity, raw.attributes, raw.binding
    if (identity.code_type != 1 or identity.code_length != 2
            or binding.description_length != identity.description_length
            or len(attributes.attributes) != 2
            or attributes.attributes[0].name != 'Payload'
            or attributes.attributes[0].type_token != 'S'
            or attributes.attributes[0].qualifiers not in ((32,1),(64,1))
            or attributes.attributes[1].name != 'Amount'
            or attributes.attributes[1].type_token != 'N'
            or attributes.attributes[1].qualifiers != (9,2,0)):
        from catalog_description_rows import DescriptionAdapterError
        raise DescriptionAdapterError('metadata_profile')
    if len(raw.records.rows) != 1 or len(result.rows) != 1 or raw.records.slots != 2:
        from catalog_description_rows import DescriptionAdapterError
        raise DescriptionAdapterError('one_active_row')
    table = raw.records.table
    observation = DescriptionObservation('layout_observed', identity, attributes,
        table, hashlib.sha256(table.raw_descriptor).hexdigest(), binding.placements,
        binding.record_size, raw.records, raw.usage)
    return observation, result.rows[0].reference_uuid

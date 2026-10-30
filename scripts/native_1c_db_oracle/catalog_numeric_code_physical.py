"""Standalone numeric Code hypothesis; never production runtime admission.

CONFIG determines numeric precision. The local precision ceiling is an observer
resource grammar, not a statement of native CodeLength validity. Generic valid
layouts outside the sole N(precision,0) hypothesis remain unresolved, without
record reads. All descriptors, values and UUIDs in observations stay private.
"""
from dataclasses import dataclass, replace
import hashlib

import catalog_binding_reader as loader


@dataclass(frozen=True)
class NumericCodeObservation:
    status: str
    identity: object
    attributes: object
    table: object
    descriptor_sha256: str
    placements: tuple
    record_size: int
    records: object
    usage: object
    typed_uuid: object = None


def read_numeric_code(read_at, file_size, *, catalog_name, limits=None):
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
    modules = loader._load_storage(project_rows=True)
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
            if (type(identity.description_length) is not int or identity.description_length != 8
                    or type(identity.code_length) is not int or not 1 <= identity.code_length <= 38
                    or type(identity.code_type) is not int or identity.code_type != 0
                    or len(attributes.attributes) != 2):
                raise c.UnsupportedLayout('numeric_code_metadata_profile')
            a, b = attributes.attributes
            if (a.name != 'Payload' or a.type_token != 'S' or a.qualifiers not in ((32, 1), (64, 1))
                    or b.name != 'Amount' or b.type_token != 'N' or b.qualifiers != (9, 2, 0)):
                raise c.UnsupportedLayout('numeric_code_metadata_profile')
        with graph.stage('params') as handle:
            extracted = named._read_dbnames_from_catalog(reader, catalog,
                profile=named.DBNamesProfile(core.DECLARATIONS, '0', 0,
                    slot_policy='closed_marker1_chain_v1'), _binding_handle=handle)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            parse_limits = dbnames.DBNamesParseLimits()
            reserve = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=parse_limits)
            reader._budget.charge('output_bytes', reserve.output_bytes)
            reader._budget.charge('bytes_processed', reserve.bytes_processed)
            reader._budget.charge('tokens', min(len(extracted.data), parse_limits.max_tokens + 1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=parse_limits)
            # Validate the unchanged subset and independent DBNames identity
            # join. This counterfactual is NEVER returned as a real binding.
            baseline = compiler.compile_catalog_binding(replace(identity, code_type=1, code_length=2),
                attributes, parsed, profile=compiler.CatalogBindingProfile(compiler.PROFILE_IDENTIFIER),
                budget=reader._budget)
        with graph.stage('records', binding=baseline) as handle:
            table = handle.table
            if len(table.fields) > 16:
                raise c.ResourceLimit('record_fields')
            if len({f.name for f in table.fields}) != len(table.fields):
                raise c.UnsupportedLayout('numeric_code_field_ambiguous')
            reader._budget.charge('bytes_processed', 2 * len(table.raw_descriptor) + 4096)
            reader._budget.charge('output_bytes', 4096)
            digest = hashlib.sha256(table.raw_descriptor).hexdigest()
            declarations = (baseline.declarations[:4] +
                (('_CODE', 'N', 0, identity.code_length, 0, 'CS'),) + baseline.declarations[5:])
            widths = tuple(x.width for x in baseline.placements)
            widths = widths[:4] + ((identity.code_length + 2) // 2,) + widths[5:]
            # Opening only validates the table data header/ownership. No row
            # reads or length interpretation occur for an unresolved layout.
            data = handle._open_table_data(table)
            match = (type(table.format_item) is int and table.format_item == 0
                     and table.recordlock == '0'
                     and tuple(x.raw for x in table.fields) == declarations)
            if not match:
                result = NumericCodeObservation('layout_unresolved', identity, attributes,
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
                    raise c.UnsupportedLayout('numeric_code_one_active_row')
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
                # Exact descriptor/role admission above precedes UUID conversion.
                typed_uuid = modules['catalog_reference_uuid'].decode_catalog_reference_uuid(fields[0].raw)
                result = NumericCodeObservation('layout_observed', identity, attributes,
                    table, digest, placements, cursor, physical, None, typed_uuid)
        return replace(result, usage=reader.usage)
    except BaseException:
        graph.failed = True
        raise


def public_observation(value):
    """Finite projection of a PRIVATE observation, not an untrusted JSON parser.

    In particular, do not hash the low-entropy Code itself. Native comparison
    and same-postimage witness binding are performed outside this byte reader.
    """
    if type(value) is not NumericCodeObservation or value.status not in ('layout_observed', 'layout_unresolved'):
        raise ValueError('numeric_code_observation_invalid')
    out = dict(status=value.status, runtime_support='not_claimed', descriptor_sha256=value.descriptor_sha256,
               code_length=value.identity.code_length,
               description_length=value.identity.description_length,
               payload_length=value.attributes.attributes[0].qualifiers[0],
               field_count=len(value.table.fields), record_size=value.record_size,
               active_count=0, active_count_known=False, code_type='unresolved',
               code_ordinal=0, code_offset=0, code_width=0, code_precision=0, code_scale=0,
               digit_count=0, previous_ordinal=0, previous_offset=0,
               next_ordinal=0, next_offset=0, previous_displacement=0, next_displacement=0)
    if value.status == 'layout_observed':
        field = value.records.rows[0].fields[4]
        prior, following = value.placements[3], value.placements[5]
        out.update(active_count=1, active_count_known=True, code_type='N',
                   code_ordinal=4, code_offset=field.offset, code_width=field.width,
                   code_precision=field.declaration.raw[3], code_scale=field.declaration.raw[4],
                   digit_count=len(field.value.as_tuple().digits), previous_ordinal=3,
                   previous_offset=prior.offset, next_ordinal=5, next_offset=following.offset,
                   previous_displacement=field.offset-prior.offset,
                   next_displacement=following.offset-field.offset)
    return out

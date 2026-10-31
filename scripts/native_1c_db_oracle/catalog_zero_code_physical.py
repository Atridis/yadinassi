"""Standalone disabled Code hypothesis; never production runtime admission.

CONFIG determines optional Description placement. Generic valid
layouts outside the sole omitted_CODE hypothesis remain unresolved, without
record reads. All descriptors, values and UUIDs in observations stay private.
"""
from dataclasses import dataclass, replace
import hashlib

import catalog_binding_reader as loader


@dataclass(frozen=True)
class _TableSelection:
    table_name: str


@dataclass(frozen=True)
class ZeroCodeObservation:
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


def read_zero_code(read_at, file_size, *, catalog_name, limits=None):
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
            if (type(identity.description_length) is not int or not 0 <= identity.description_length <= 128
                    or type(identity.code_length) is not int or identity.code_length != 0
                    or type(identity.code_type) is not int or identity.code_type != 1
                    or len(attributes.attributes) != 2):
                raise c.UnsupportedLayout('zero_code_metadata_profile')
            a, b = attributes.attributes
            if (a.name != 'Payload' or a.type_token != 'S' or a.qualifiers not in ((32, 1), (64, 1))
                    or b.name != 'Amount' or b.type_token != 'N' or b.qualifiers != (9, 2, 0)):
                raise c.UnsupportedLayout('zero_code_metadata_profile')
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
            # Join only identities from independently parsed CONFIG/DBNames.
            # Never compile a counterfactual positive-code binding.
            reader._budget.charge('output_bytes', 8192)
            reader._budget.charge('bytes_processed', 4096 + 1024 * len(parsed.entries))
            reader._budget.charge('tokens', 64 + 8 * len(parsed.entries))
            targets = (identity.metadata_uuid, a.metadata_uuid, b.metadata_uuid)
            if len(set(targets)) != 3:
                raise c.UnsupportedLayout('zero_code_metadata_profile')
            selected = []
            for target, kind in zip(targets, ('Reference', 'Fld', 'Fld')):
                matches = [entry for entry in parsed.entries if entry.uuid == target]
                if len(matches) != 1 or matches[0].kind != kind or matches[0].id <= 0:
                    raise c.UnsupportedLayout('zero_code_dbnames_join')
                entry = matches[0]
                if sum(x.kind == kind and x.id == entry.id for x in parsed.entries) != 1:
                    raise c.UnsupportedLayout('zero_code_dbnames_join')
                selected.append(entry)
            if len({x.id for x in selected}) != 3:
                raise c.UnsupportedLayout('zero_code_dbnames_join')
            baseline = _TableSelection('_Reference' + str(selected[0].id))
            declarations = (('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
                ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'))
            widths = (16,16,1,16)
            if identity.description_length:
                declarations += (('_DESCRIPTION','NVC',0,identity.description_length,0,'CI'),)
                widths += (2 + 2 * identity.description_length,)
            declarations += (('_FLD'+str(selected[1].id),'NVC',0,a.qualifiers[0],0,'CI'),
                             ('_FLD'+str(selected[2].id),'N',0,9,2,'CS'))
            widths += (2 + 2*a.qualifiers[0],5)
        with graph.stage('records', binding=baseline) as handle:
            table = handle.table
            if len(table.fields) > 16:
                raise c.ResourceLimit('record_fields')
            if len({f.name for f in table.fields}) != len(table.fields):
                raise c.UnsupportedLayout('zero_code_field_ambiguous')
            reader._budget.charge('bytes_processed', 2 * len(table.raw_descriptor) + 4096)
            reader._budget.charge('output_bytes', 4096)
            digest = hashlib.sha256(table.raw_descriptor).hexdigest()
            # Opening only validates the table data header/ownership. No row
            # reads or length interpretation occur for an unresolved layout.
            data = handle._open_table_data(table)
            match = (type(table.format_item) is int and table.format_item == 0
                     and table.recordlock == '0'
                     and tuple(x.raw for x in table.fields) == declarations)
            if not match:
                result = ZeroCodeObservation('layout_unresolved', identity, attributes,
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
                    raise c.UnsupportedLayout('zero_code_one_active_row')
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
                result = ZeroCodeObservation('layout_observed', identity, attributes,
                    table, digest, placements, cursor, physical, None, typed_uuid)
        return replace(result, usage=reader.usage)
    except BaseException:
        graph.failed = True
        raise


def public_observation(value):
    """Counts/hash-only projection; private identities/descriptors never exported."""
    if type(value) is not ZeroCodeObservation or value.status not in ('layout_observed','layout_unresolved'):
        raise ValueError('zero_code_observation_invalid')
    present = value.status == 'layout_observed'
    return dict(status=value.status, runtime_support='not_claimed',
        descriptor_sha256=value.descriptor_sha256, code_length=value.identity.code_length,
        description_length=value.identity.description_length,
        payload_length=value.attributes.attributes[0].qualifiers[0],
        field_count=len(value.table.fields), record_size=value.record_size,
        code_field_count=sum(x.name == '_CODE' for x in value.table.fields),
        description_field_count=sum(x.name == '_DESCRIPTION' for x in value.table.fields),
        active_count=1 if present else 0, active_count_known=present,
        first_attribute_offset=value.placements[-2].offset if present else 0)

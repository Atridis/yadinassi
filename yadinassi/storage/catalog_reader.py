"""Runtime-only, read-only coordinator for a caller-owned frozen .1CD image.

The caller is responsible for providing a consistent offline source through read_at.
This API neither opens a live database nor creates a transaction or authentication
session. Admission includes the owned positive String/Number Code profiles and
the measured String CodeLength0 shapes (Description0/8, Payload32/64, Amount9,2).
Zero-code physical rows omit _CODE; no logical Code value is synthesized.
Only one active record is admitted. No BSL manager is exported yet.
"""
from dataclasses import dataclass
from uuid import UUID
from . import config_catalog_transport as core
from . import filedb_catalog as catalog_module
from . import filedb_named_file as named
from . import filedb_dbnames as dbnames
from . import config_catalog_binding as compiler
from . import config_catalog_records as row_reader
from . import filedb_records as row_types


@dataclass(frozen=True)
class CatalogBindingReadResult:
    config_observation: object
    identity: object
    attributes: object
    binding: object
    records: object
    usage: object


@dataclass(frozen=True)
class CatalogRow:
    """Private typed identity alongside the unchanged physical record."""
    physical_record: row_types.PhysicalRecord
    reference_uuid: UUID


@dataclass(frozen=True)
class CatalogRowsReadResult:
    config_observation: object
    identity: object
    attributes: object
    binding: object
    records: row_types.PhysicalRecords
    rows: tuple[CatalogRow, ...]
    usage: catalog_module.CatalogUsage


def read_catalog_rows(read_at, file_size, *, catalog_name, limits=None):
    """Opt in to UUID projection after complete Catalog/physical-row admission.

    Metadata identity is retained on the result, not inferred from UUID bytes.
    This is not a BSL reference, session, live reader or native acceptance claim.
    """
    return _read_catalog(read_at, file_size, catalog_name=catalog_name,
                         limits=limits, project_rows=True)


def read_catalog_binding(read_at, file_size, *, catalog_name, limits=None):
    """Read all CONFIG entries, PARAMS/DBNames, and one selected Catalog's rows.

    A catalog name is only a selector. It does not provide UUIDs, physical IDs,
    types, lengths, schema or expected values. Complete CONFIG traversal occurs
    before selection. Every subsequent phase uses the same lifetime budget and
    page-ownership graph; errors prevent partial result return and poison it.
    """
    return _read_catalog(read_at, file_size, catalog_name=catalog_name,
                         limits=limits, project_rows=False)


def _read_catalog(read_at, file_size, *, catalog_name, limits, project_rows):
    if type(catalog_name) is not str or not 1 <= len(catalog_name) <= 256:
        raise catalog_module.UnsupportedLayout('binding_catalog_selector')
    try:
        encoded_length = len(catalog_name.encode('utf-8'))
    except UnicodeEncodeError:
        raise catalog_module.UnsupportedLayout('binding_catalog_selector') from None
    if encoded_length > 1024 or any(ord(x) < 32 or ord(x) == 127 for x in catalog_name):
        raise catalog_module.UnsupportedLayout('binding_catalog_selector')
    if limits is not None and type(limits) is not catalog_module.CatalogLimits:
        raise catalog_module.InvalidStructure('binding_limits')
    reader = catalog_module.CatalogReader(read_at, file_size, limits=limits)
    physical_catalog = reader.read_catalog()
    graph = catalog_module._CatalogBindingGraph(reader, physical_catalog)
    try:
        with graph.stage('config') as handle:
            observation = core._observe_catalog_attributes_from_graph(handle,
                profile=core.ConfigCatalogAttributeProfile(core.DECLARATIONS, '0', 0))
            # Complete projection is already bounded to 256 Catalogs. Reserve
            # additional retained result references/selector comparisons before
            # any collection scan, including failure paths.
            reader._budget.charge('output_bytes', 65536)
            reader._budget.charge('bytes_processed', 2048 * len(observation.private_fields))
            selected = None
            uuids = set()
            for key, identity, attributes in observation.private_fields:
                if key != identity.metadata_uuid or identity.metadata_uuid in uuids:
                    raise catalog_module.InvalidStructure('binding_catalog_identity')
                uuids.add(identity.metadata_uuid)
                if identity.name == catalog_name:
                    if selected is not None:
                        raise catalog_module.UnsupportedLayout('binding_catalog_ambiguous')
                    selected = (identity, attributes)
            if selected is None:
                raise catalog_module.UnsupportedLayout('binding_catalog_missing')
            identity, attributes = selected
        with graph.stage('params') as handle:
            extracted = named._read_dbnames_from_catalog(reader, physical_catalog,
                profile=named.DBNamesProfile(core.DECLARATIONS, '0', 0,
                    slot_policy='closed_marker1_chain_v1'), _binding_handle=handle)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            parse_limits = dbnames.DBNamesParseLimits()
            reservation = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=parse_limits)
            reader._budget.charge('output_bytes', reservation.output_bytes)
            reader._budget.charge('bytes_processed', reservation.bytes_processed)
            # Each token consumes at least one input byte. Reserve the pure
            # parser's bounded token work before execution, including its first
            # over-limit event on failure; never refund unused reservation.
            reader._budget.charge('tokens', min(len(extracted.data), parse_limits.max_tokens + 1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=parse_limits)
            # Only the measured zero-code schema opts into physical field omission.
            # Exact primitive guards precede selection; the compiler independently
            # validates all qualifiers and rejects other zero/positive combinations.
            zero_code = (type(identity.code_type) is int and identity.code_type == 1
                         and type(identity.code_length) is int and identity.code_length == 0)
            profile_id = compiler.ZERO_PROFILE_IDENTIFIER if zero_code else compiler.NUMERIC_PROFILE_IDENTIFIER
            binding = compiler.compile_catalog_binding(identity, attributes, parsed,
                profile=compiler.CatalogBindingProfile(profile_id), budget=reader._budget)
            del parsed, extracted, reservation
        with graph.stage('records', binding=binding) as handle:
            rows = row_reader.read_bound_catalog_records(reader, physical_catalog, binding,
                handle=handle, limits=row_types.RecordLimits(max_active_records=1))
        if project_rows:
            # Reserve retained wrappers, UUIDs, tuple/result and bounded role
            # checks/conversion work on the SAME lifetime before construction.
            # Conservative accounting units, not Python allocator measurements.
            reader._budget.charge('output_bytes', 512 + 512 * len(rows.rows))
            reader._budget.charge('bytes_processed', 256 + 256 * len(rows.rows))
            typed = _project_rows(graph, identity, binding, rows)
            return CatalogRowsReadResult(observation, identity, attributes,
                                         binding, rows, typed, reader.usage)
        return CatalogBindingReadResult(observation, identity, attributes, binding, rows, reader.usage)
    except BaseException as error:
        graph.failed = True
        if isinstance(error, dbnames.DBNamesParseResourceLimit):
            raise catalog_module.ResourceLimit('binding_dbnames_limits') from None
        if isinstance(error, dbnames.UnsupportedDBNamesProfile):
            raise catalog_module.UnsupportedLayout('binding_dbnames_profile') from None
        if isinstance(error, dbnames.DBNamesParseError):
            raise catalog_module.InvalidStructure('binding_dbnames_invalid') from None
        if isinstance(error, compiler.CatalogBindingError):
            raise catalog_module.UnsupportedLayout('binding_metadata_profile') from None
        if isinstance(error, ValueError):
            raise catalog_module.InvalidStructure('binding_graph_state') from None
        raise



def _project_rows(graph, identity, binding, records):
    # Only the coordinator calls this after the records stage has completed.
    # Lazy import keeps the historical raw-only source-pinned adapter untouched.
    from .catalog_reference_uuid import decode_catalog_reference_uuid

    if (graph.failed or graph._next != 3 or graph._active is not None
            or graph.reader._binding_graph is not graph
            or binding.metadata_uuid != identity.metadata_uuid
            or binding.name != identity.name):
        raise catalog_module.InvalidStructure('binding_reference_identity')
    if (type(binding.code_type) is not int or binding.code_type not in (0, 1)
            or type(identity.code_type) is not int or binding.code_type != identity.code_type
            or type(binding.code_length) is not int or type(identity.code_length) is not int
            or binding.code_length != identity.code_length
            or type(binding.description_length) is not int or not 0 <= binding.description_length <= 2047
            or binding.description_length != identity.description_length):
        raise catalog_module.InvalidStructure('binding_reference_identity')
    zero_code = binding.code_length == 0
    if zero_code and (binding.code_type != 1 or binding.description_length not in (0, 8)):
        raise catalog_module.InvalidStructure('binding_reference_identity')
    field_count = (6 if zero_code else 7) + int(binding.description_length > 0)
    expected = ('_IDRREF', 'B', 0, 16, 0, 'CS')
    # Positive-code shapes have seven/eight declarations; zero-code has six/seven.
    # Check shape and unique role before indexing malformed private intermediate data.
    if (type(binding.placements) is not tuple or len(binding.placements) != field_count
            or any(type(p) is not compiler.BoundFieldPlacement
                   or type(p.declaration) is not tuple or len(p.declaration) != 6
                   for p in binding.placements)
            or sum(p.declaration[0] == '_IDRREF' for p in binding.placements) != 1):
        raise catalog_module.InvalidStructure('binding_reference_role')
    place = binding.placements[0]
    if place.declaration != expected:
        raise catalog_module.InvalidStructure('binding_reference_role')
    # Validate every role before invoking the codec, even if a future profile
    # admits more rows. Never reinterpret generic B16, RV or predefined bytes.
    for record in records.rows:
        if (type(record) is not row_types.PhysicalRecord
                or type(record.raw) is not bytes
                or type(record.fields) is not tuple or len(record.fields) != field_count
                or any(type(f) is not row_types.PhysicalValue
                       or type(f.declaration) is not catalog_module.PhysicalField
                       for f in record.fields)
                or sum(f.declaration.name == '_IDRREF' for f in record.fields) != 1):
            raise catalog_module.InvalidStructure('binding_reference_role')
        field = record.fields[0]
        if (field.declaration.raw != expected or field.offset != place.offset
                or field.width != 16 or type(field.raw) is not bytes
                or len(field.raw) != 16 or field.value != field.raw
                or record.raw[field.offset:field.offset + 16] != field.raw):
            raise catalog_module.InvalidStructure('binding_reference_role')
    return tuple(CatalogRow(record, decode_catalog_reference_uuid(record.fields[0].raw))
                 for record in records.rows)

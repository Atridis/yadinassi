"""Read-only Document coordinator on one CONFIG/PARAMS/records ownership graph."""
from dataclasses import dataclass, fields, replace
from uuid import UUID
from . import filedb_catalog as c
from . import config_catalog_transport as config
from . import filedb_named_file as named
from . import filedb_dbnames as dbnames
from . import config_document_binding as compiler
from . import config_document_records as records
from .config_document_metadata import DocumentConfigSnapshot
from .catalog_reference_uuid import decode_catalog_reference_uuid
from .filedb_records import RecordLimits


@dataclass(frozen=True)
class DocumentRow:
    physical_record: object
    reference_uuid: UUID


@dataclass(frozen=True)
class DocumentRowsReadResult:
    config_snapshot: DocumentConfigSnapshot
    identity: object
    attributes: object
    binding: object
    records: object
    rows: tuple[DocumentRow, ...]
    usage: object


def _reader(read_at, size, limits):
    if (type(size) is not int or size < 0
            or limits is not None and type(limits) is not c.CatalogLimits):
        raise c.InvalidStructure('document_input')
    defaults = c.CatalogLimits()
    if limits is not None and any(getattr(limits, f.name) > getattr(defaults, f.name)
                                  for f in fields(defaults)):
        raise c.InvalidStructure('document_limits')
    if size > 67108864:
        raise c.ResourceLimit('config_chain_image_bytes')
    reader = c.CatalogReader(read_at, size, limits=limits)
    catalog = reader.read_catalog()
    return reader, catalog, c._CatalogBindingGraph(reader, catalog)


def _snapshot(graph):
    with graph.stage('config') as handle:
        result = config._observe_catalog_attributes_from_graph(handle,
            profile=config.ConfigCatalogAttributeProfile(config.DECLARATIONS, '0', 0),
            linked=True, documents=True)
        all_fields = result.catalog_fields + result.document_fields
        budget = graph.reader._budget
        budget.charge('output_bytes', 512 + 4096*len(all_fields))
        budget.charge('bytes_processed', 4096*len(all_fields))
        metadata, reference_types = set(), {}
        for family in (result.catalog_fields, result.document_fields):
            names = set()
            for key, identity, attributes in family:
                if key != identity.metadata_uuid or key in metadata or identity.name.casefold() in names:
                    raise c.InvalidStructure('document_metadata_identity')
                metadata.add(key)
                names.add(identity.name.casefold())
                target = attributes.reference_type_uuid
                if target is None or target in reference_types:
                    raise c.InvalidStructure('document_reference_type_identity')
                reference_types[target] = key
        if metadata.intersection(reference_types):
            raise c.InvalidStructure('document_reference_type_identity')
        catalog_ids = {key for key, _, _ in result.catalog_fields}
        documents = []
        for key, identity, attributes in result.document_fields:
            bound = []
            for attribute in attributes.attributes:
                if attribute.type_token == '#':
                    target = reference_types.get(attribute.reference_type_uuid)
                    if target not in catalog_ids:
                        # !todo Composite/document-target fields require their own
                        # measured bindings, never treat arbitrary UUIDs as catalogs.
                        raise c.UnsupportedLayout('document_reference_target')
                    attribute = replace(attribute, reference_catalog_uuid=target)
                bound.append(attribute)
            documents.append((key, identity, replace(attributes, attributes=tuple(bound))))
        return DocumentConfigSnapshot(tuple(documents), result.catalog_fields)


def read_document_metadata(read_at, file_size, *, limits=None):
    _, _, graph = _reader(read_at, file_size, limits)
    try:
        return _snapshot(graph)
    except BaseException:
        graph.failed = True
        raise


def read_document_rows(read_at, file_size, *, document_name, limits=None):
    if (type(document_name) is not str or not 1 <= len(document_name) <= 256
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in document_name)):
        raise c.UnsupportedLayout('document_selector')
    reader, catalog, graph = _reader(read_at, file_size, limits)
    try:
        snapshot = _snapshot(graph)
        selected = [(identity, attributes) for _, identity, attributes in snapshot.document_fields
                    if identity.name == document_name]
        if len(selected) != 1:
            raise c.UnsupportedLayout('document_selector')
        identity, attributes = selected[0]
        with graph.stage('params') as handle:
            extracted = named._read_dbnames_from_catalog(reader, catalog,
                profile=named.DBNamesProfile(config.DECLARATIONS, '0', 0,
                    slot_policy='closed_marker1_chain_v1'), _binding_handle=handle)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            limits = dbnames.DBNamesParseLimits()
            reserve = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=limits)
            reader._budget.charge('output_bytes', reserve.output_bytes)
            reader._budget.charge('bytes_processed', reserve.bytes_processed)
            reader._budget.charge('tokens', min(len(extracted.data), limits.max_tokens+1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=limits)
            binding = compiler.compile_document_binding(identity, attributes, parsed, budget=reader._budget)
        with graph.stage('records', binding=binding) as handle:
            physical = records.read_bound_document_records(reader, catalog, binding,
                handle=handle, limits=RecordLimits(max_active_records=4096))
        reader._budget.charge('output_bytes', 512+512*len(physical.rows))
        reader._budget.charge('bytes_processed', 256+256*len(physical.rows))
        expected = ('_IDRREF', 'B', 0, 16, 0, 'CS')
        if binding.placements[0].declaration != expected:
            raise c.InvalidStructure('document_reference_role')
        rows = []
        for row in physical.rows:
            value = row.fields[0]
            if (value.declaration.raw != expected or value.offset != binding.placements[0].offset
                    or value.width != 16 or type(value.raw) is not bytes or len(value.raw) != 16
                    or value.value != value.raw or row.raw[value.offset:value.offset+16] != value.raw):
                raise c.InvalidStructure('document_reference_role')
            rows.append(DocumentRow(row, decode_catalog_reference_uuid(value.raw)))
        return DocumentRowsReadResult(snapshot, identity, attributes, binding, physical, tuple(rows), reader.usage)
    except BaseException as error:
        graph.failed = True
        if isinstance(error, dbnames.DBNamesParseResourceLimit):
            raise c.ResourceLimit('document_dbnames_limits') from None
        if isinstance(error, dbnames.UnsupportedDBNamesProfile):
            raise c.UnsupportedLayout('document_dbnames_profile') from None
        if isinstance(error, dbnames.DBNamesParseError):
            raise c.InvalidStructure('document_dbnames_invalid') from None
        if isinstance(error, compiler.CatalogBindingError):
            raise c.UnsupportedLayout('document_metadata_profile') from None
        if isinstance(error, ValueError):
            raise c.InvalidStructure('document_graph_state') from None
        raise

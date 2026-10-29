"""Runtime-only, read-only coordinator for a caller-owned frozen .1CD image.

The caller is responsible for providing a consistent offline source through read_at.
This API neither opens a live database nor creates a transaction or authentication
session. Current admission retains the owned String Code/Description0, String and
Number attribute profile and one active record. No BSL manager is exported yet.
"""
from dataclasses import dataclass
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


def read_catalog_binding(read_at, file_size, *, catalog_name, limits=None):
    """Read all CONFIG entries, PARAMS/DBNames, and one selected Catalog's rows.

    A catalog name is only a selector. It does not provide UUIDs, physical IDs,
    types, lengths, schema or expected values. Complete CONFIG traversal occurs
    before selection. Every subsequent phase uses the same lifetime budget and
    page-ownership graph; errors prevent partial result return and poison it.
    """
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
                profile=named.DBNamesProfile(core.DECLARATIONS, '0', 0), _binding_handle=handle)
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
            binding = compiler.compile_catalog_binding(identity, attributes, parsed,
                profile=compiler.CatalogBindingProfile(compiler.PROFILE_IDENTIFIER), budget=reader._budget)
            del parsed, extracted, reservation
        with graph.stage('records', binding=binding) as handle:
            rows = row_reader.read_bound_catalog_records(reader, physical_catalog, binding,
                handle=handle, limits=row_types.RecordLimits(max_active_records=1))
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


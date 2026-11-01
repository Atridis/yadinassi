"""Bounded read-only InformationRegister snapshot/keyed rows, one owned graph."""
from dataclasses import dataclass, replace
from . import filedb_catalog as c
from . import config_catalog_transport as config
from . import filedb_named_file as named
from . import filedb_dbnames as dbnames
from . import config_information_register_binding as compiler
from . import config_information_register_records as records
from .config_information_register_metadata import InformationRegisterConfigSnapshot
from .document_reader import _reader
from .filedb_records import RecordLimits


@dataclass(frozen=True)
class InformationRegisterRowsReadResult:
    config_snapshot: InformationRegisterConfigSnapshot
    identity: object
    binding: object
    records: object
    rows: tuple
    usage: object


def _snapshot(graph):
    with graph.stage('config') as handle:
        snapshot = config._observe_catalog_attributes_from_graph(handle,
            profile=config.ConfigCatalogAttributeProfile(config.DECLARATIONS, '0', 0),
            linked=True, information_registers=True)
        budget = graph.reader._budget
        total = len(snapshot.catalog_fields) + len(snapshot.register_fields)
        budget.charge('output_bytes', 512 + 8192 * total)
        budget.charge('bytes_processed', 8192 * total)
        used, names, targets = set(), set(), {}
        def unique(values):
            values = tuple(values)
            if len(set(values)) != len(values) or used.intersection(values):
                raise c.InvalidStructure('information_register_metadata_identity')
            used.update(values)
        for key, identity, attributes in snapshot.catalog_fields:
            if key != identity.metadata_uuid or identity.name.casefold() in names:
                raise c.InvalidStructure('information_register_metadata_identity')
            names.add(identity.name.casefold())
            if attributes.reference_type_uuid is None:
                raise c.InvalidStructure('information_register_reference_identity')
            unique((key, attributes.reference_type_uuid, *(a.metadata_uuid for a in attributes.attributes)))
            targets[attributes.reference_type_uuid] = key
        names = set(); registers = []
        for key, identity, dimensions, resources, attributes in snapshot.register_fields:
            if key != identity.metadata_uuid or identity.name.casefold() in names:
                raise c.InvalidStructure('information_register_metadata_identity')
            names.add(identity.name.casefold())
            all_fields = dimensions.attributes + resources.attributes + attributes.attributes
            unique((key, *(uid for family, type_uid, value_uid in identity.generated_types for uid in (type_uid, value_uid)),
                    *(a.metadata_uuid for a in all_fields)))
            if any(a.name.casefold() in ('next', 'следующий') for a in all_fields):
                raise c.InvalidStructure('information_register_field_name')
            bound = []
            for collection in (dimensions, resources, attributes):
                fields = []
                for attribute in collection.attributes:
                    if attribute.type_token == '#':
                        target = targets.get(attribute.reference_type_uuid)
                        if target is None:
                            raise c.UnsupportedLayout('information_register_reference_target')
                        attribute = replace(attribute, reference_catalog_uuid=target)
                    fields.append(attribute)
                bound.append(replace(collection, attributes=tuple(fields)))
            registers.append((key, identity, *bound))
        return InformationRegisterConfigSnapshot(tuple(registers), snapshot.catalog_fields)


def read_information_register_metadata(read_at, file_size, *, limits=None):
    _, _, graph = _reader(read_at, file_size, limits)
    try:
        return _snapshot(graph)
    except BaseException:
        graph.failed = True
        raise


def read_information_register_rows(read_at, file_size, *, register_name, limits=None):
    if (type(register_name) is not str or not 1 <= len(register_name) <= 256
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in register_name)):
        raise c.UnsupportedLayout('information_register_selector')
    reader, catalog, graph = _reader(read_at, file_size, limits)
    try:
        snapshot = _snapshot(graph)
        chosen = [row[1:] for row in snapshot.register_fields if row[1].name == register_name]
        if len(chosen) != 1: raise c.UnsupportedLayout('information_register_selector')
        identity, dimensions, resources, attributes = chosen[0]
        with graph.stage('params') as handle:
            extracted = named._read_dbnames_from_catalog(reader, catalog,
                profile=named.DBNamesProfile(config.DECLARATIONS, '0', 0,
                    slot_policy='closed_marker1_chain_v1'), _binding_handle=handle)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            parse_limits = dbnames.DBNamesParseLimits()
            reserve = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=parse_limits)
            reader._budget.charge('output_bytes', reserve.output_bytes)
            reader._budget.charge('bytes_processed', reserve.bytes_processed)
            reader._budget.charge('tokens', min(len(extracted.data), parse_limits.max_tokens + 1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=parse_limits)
            binding = compiler.compile_information_register_binding(identity, dimensions, resources,
                attributes, parsed, budget=reader._budget)
        with graph.stage('records', binding=binding) as handle:
            physical = records.read_bound_information_register_records(reader, catalog, binding,
                handle=handle, limits=RecordLimits(max_active_records=4096))
        return InformationRegisterRowsReadResult(snapshot, identity, binding, physical, physical.rows, reader.usage)
    except BaseException as error:
        graph.failed = True
        if isinstance(error, dbnames.DBNamesParseResourceLimit):
            raise c.ResourceLimit('information_register_dbnames_limits') from None
        if isinstance(error, dbnames.UnsupportedDBNamesProfile):
            raise c.UnsupportedLayout('information_register_dbnames_profile') from None
        if isinstance(error, dbnames.DBNamesParseError):
            raise c.InvalidStructure('information_register_dbnames_invalid') from None
        if isinstance(error, compiler.CatalogBindingError):
            raise c.UnsupportedLayout('information_register_metadata_profile') from None
        if isinstance(error, ValueError):
            raise c.InvalidStructure('information_register_graph_state') from None
        raise

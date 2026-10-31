"""Bounded metadata identities from a caller-owned, consistent offline CONFIG.

This coordinator admits the existing complete Catalog attribute profile but
exports identities only. It never opens PARAMS or catalog record files. Its
storage order is not a claim about native multi-Catalog numeric indexing.
CONFIG parsing alone does not establish applied state for arbitrary databases.
"""
from dataclasses import dataclass, fields

from . import config_catalog_transport as core
from . import filedb_catalog as catalog


@dataclass(frozen=True, slots=True)
class CatalogMetadataIdentity:
    metadata_uuid: str
    name: str


def read_catalog_metadata(read_at, file_size, *, limits=None):
    """Return a complete immutable tuple, or fail without partial identities.

    The closed storage/grammar/resource profile is the same as the measured
    CONFIG attribute projection. Empty or unrecognized profiles remain rejected;
    no metadata is guessed from physical table names or catalog record values.
    """
    if limits is not None and type(limits) is not catalog.CatalogLimits:
        raise catalog.InvalidStructure('metadata_limits')
    defaults = catalog.CatalogLimits()
    if limits is not None and any(getattr(limits, item.name) > getattr(defaults, item.name)
                                  for item in fields(defaults)):
        raise catalog.InvalidStructure('metadata_limits')
    # Reject an overlarge image before constructing any physical catalog graph.
    if type(file_size) is not int or file_size < 0:
        raise catalog.InvalidStructure('metadata_image_size')
    if file_size > 67108864:
        raise catalog.ResourceLimit('config_chain_image_bytes')
    reader = catalog.CatalogReader(read_at, file_size, limits=limits)
    physical = reader.read_catalog()
    graph = catalog._CatalogBindingGraph(reader, physical)
    try:
        with graph.stage('config') as handle:
            observation = core._observe_catalog_attributes_from_graph(handle,
                profile=core.ConfigCatalogAttributeProfile(core.DECLARATIONS, '0', 0))
            if (observation.catalog_declared_count != observation.catalog_resolved_count
                    or observation.catalog_resolved_count != observation.catalog_positive_count
                    or observation.catalog_positive_count != len(observation.private_fields)):
                raise catalog.InvalidStructure('metadata_incomplete')
            # Reserve all retained identity wrappers and folded comparison keys
            # before allocating them, in the same cumulative reader budget.
            reader._budget.charge('output_bytes', 512 + 4096 * len(observation.private_fields))
            reader._budget.charge('bytes_processed', 4096 * len(observation.private_fields))
            identities, uuids, names = [], set(), set()
            for key, identity, attributes in observation.private_fields:
                folded = identity.name.casefold()
                if (key != identity.metadata_uuid or key in uuids or folded in names):
                    raise catalog.InvalidStructure('metadata_identity_ambiguous')
                uuids.add(key)
                names.add(folded)
                identities.append(CatalogMetadataIdentity(key, identity.name))
            return tuple(identities)
    except BaseException:
        graph.failed = True
        raise

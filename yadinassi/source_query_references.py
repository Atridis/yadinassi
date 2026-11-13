"""Exact neutral source reference bindings, distinct from legacy record adapters.

This descriptor authorizes a detached typed identity, not a database read view.
The source query adapter must establish its own single owned record snapshot.
"""
from dataclasses import dataclass
from uuid import UUID
import weakref
from .catalog_types import BSLCatalogType, BSLCatalogReference


@dataclass(frozen=True, slots=True, eq=False)
class SourceBinding:
    value_type: object
    identity: tuple
    kind: str
    collection: object
    ownerapp: object

    def require_owner(self):
        from .source_catalog_store import SourceCatalogStore
        if type(self.ownerapp) is not weakref.ReferenceType:
            raise TypeError('Source reference binding requires an application owner')
        app = self.ownerapp()
        if app is None:
            raise ValueError('Source reference application is closed')
        app.require_open()
        if (type(self.kind) is not str or self.kind != 'catalog_ref' or type(self.value_type) is not BSLCatalogType
                or type(self.identity) is not tuple or len(self.identity) != 2
                or type(self.identity[1]) is not UUID
                or self.collection is not app.interpreter._catalogs
                or type(app.constant_store) is not SourceCatalogStore):
            raise TypeError('Invalid source reference binding ownership')
        entry, canonical, metadata = app.references.definition('Catalog', self.value_type.name)
        if (canonical is not self.value_type or canonical.family != 'ref'
                or self.identity[0] is not app.references.snapshot
                or canonical.snapshot is not self.identity[0]
                or entry.identity != self.identity[1]
                or canonical.metadata_uuid != self.identity[1]
                or metadata._root is not app.metadata or metadata._entry != entry):
            raise TypeError('Source reference binding requires canonical source metadata')
        definition = app.constant_store.catalog(entry.name)
        if definition.identity != entry.identity:
            raise TypeError('Source reference storage schema identity mismatch')
        if app.constant_store._closed:
            raise ValueError("Source reference database is closed")
        return app

    def require_context(self, catalogs, documents):
        if catalogs is not self.collection:
            raise TypeError('Source reference belongs to another interpreter snapshot')
        self.require_owner()

    def value(self, value):
        app = self.require_owner()
        metadata = app.references.definition('Catalog', self.value_type.name)[2]
        if (type(value) is not BSLCatalogReference or value.value_type is not self.value_type
                or type(value.reference_uuid) is not UUID or value.metadata is not metadata
                or value.read_member is not None or value.get_object is not None):
            raise TypeError('Source query cell requires exact neutral owned reference')
        return value


def make_binding(app, catalogs, name):
    entry, value_type, _ = app.references.definition('Catalog', name)
    binding = SourceBinding(value_type, (app.references.snapshot, entry.identity),
                            'catalog_ref', catalogs, weakref.ref(app))
    binding.require_owner()
    return binding

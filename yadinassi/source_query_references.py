"""Exact neutral source reference bindings, distinct from legacy record adapters.

This descriptor authorizes a detached typed identity, not a database read view.
The source query adapter must establish its own single owned record snapshot.
"""
from dataclasses import dataclass
from uuid import UUID
import weakref
from .catalog_types import BSLCatalogType, BSLCatalogReference
from .document_types import BSLDocumentType, BSLDocumentReference


@dataclass(frozen=True, slots=True, eq=False)
class SourceBinding:
    value_type: object
    identity: tuple
    kind: str
    collection: object
    ownerapp: object

    def require_owner(self):
        from .source_catalog_store import SourceCatalogStore
        from .source_document_store import SourceDocumentStore
        from .source_document_section_store import SourceDocumentSectionStore
        if type(self.ownerapp) is not weakref.ReferenceType:
            raise TypeError('Source reference binding requires an application owner')
        app = self.ownerapp()
        if app is None:
            raise ValueError('Source reference application is closed')
        app.require_open()
        if (type(self.kind) is not str or self.kind not in ('catalog_ref','document_ref') or type(self.value_type) is not (BSLCatalogType if self.kind=='catalog_ref' else BSLDocumentType)
                or type(self.identity) is not tuple or len(self.identity) != 2
                or type(self.identity[1]) is not UUID
                or self.collection is not app.interpreter._catalogs
                or type(app.constant_store) not in (SourceCatalogStore, SourceDocumentStore, SourceDocumentSectionStore)):
            raise TypeError('Invalid source reference binding ownership')
        family='Catalog' if self.kind=='catalog_ref' else 'Document'
        if family=='Document' and type(app.constant_store) not in (SourceDocumentStore, SourceDocumentSectionStore):
            raise ValueError('source Document query requires v5 scratch capability')
        entry, canonical, metadata = app.references.definition(family, self.value_type.name)
        if (canonical is not self.value_type or canonical.family != 'ref'
                or self.identity[0] is not app.references.snapshot
                or canonical.snapshot is not self.identity[0]
                or entry.identity != self.identity[1]
                or canonical.metadata_uuid != self.identity[1]
                or metadata._root is not app.metadata or metadata._entry != entry):
            raise TypeError('Source reference binding requires canonical source metadata')
        definition = (app.constant_store.catalog if family=='Catalog' else app.constant_store.document)(entry.name)
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
        family='Catalog' if self.kind=='catalog_ref' else 'Document'
        metadata = app.references.definition(family, self.value_type.name)[2]
        if (type(value) is not (BSLCatalogReference if self.kind=='catalog_ref' else BSLDocumentReference) or value.value_type is not self.value_type
                or type(value.reference_uuid) is not UUID or value.metadata is not metadata
                or value.read_member is not None or value.get_object is not None):
            raise TypeError('Source query cell requires exact neutral owned reference')
        return value


def make_binding(app, catalogs, name, family='Catalog'):
    if type(family) is not str or family not in ('Catalog','Document'):
        raise ValueError('unsupported source query reference family')
    entry, value_type, _ = app.references.definition(family, name)
    binding = SourceBinding(value_type, (app.references.snapshot, entry.identity),
                            'catalog_ref' if family=='Catalog' else 'document_ref', catalogs, weakref.ref(app))
    binding.require_owner()
    return binding


@dataclass(frozen=True, slots=True)
class SourcePackageScope:
    """Private capability for one translated package and its frozen source tables."""
    ownerapp: object
    collection: object
    statements: tuple
    tables: tuple

    def require_context(self, statements, catalogs):
        from .source_catalog_store import SourceCatalogStore
        from .source_document_store import SourceDocumentStore
        from .source_document_section_store import SourceDocumentSectionStore
        from .query_packages import _Table, _check_tables
        from . import query_parser as syntax
        if type(self.ownerapp) is not weakref.ReferenceType:
            raise TypeError('Invalid source package owner')
        app = self.ownerapp()
        if app is None:
            raise ValueError('Source package application is closed')
        app.require_open()
        if (statements is not self.statements or catalogs is not self.collection
                or catalogs is not app.interpreter._catalogs
                or type(app.constant_store) not in (SourceCatalogStore, SourceDocumentStore, SourceDocumentSectionStore) or app.constant_store._closed):
            raise TypeError('Source package requires its exact application context')
        if type(self.tables) is not tuple or len(self.tables)>16:
            raise ValueError('Source package table bound')
        tables = dict(self.tables)
        if len(tables)!=len(self.tables) or any(type(k) is not str or type(v) is not _Table for k,v in self.tables):
            raise TypeError('Invalid frozen source tables')
        _check_tables(tables)
        for node in syntax.walk_nodes(statements):
            if type(node) in (syntax.Select, syntax.Source) and node.derived is None:
                if node.section is not None or node.period_boundary is not None or not (node.external or node.temporary):
                    raise ValueError('Source package cannot acquire legacy database views')
        return tables

    def external_tables(self, statements, parameters, catalogs, documents):
        from . import query_parser as syntax
        from .query_sources import _snapshot
        frozen = self.require_context(statements, catalogs)
        result, budget = {}, [0,0]
        for node in syntax.walk_nodes(statements):
            if type(node) not in (syntax.Select, syntax.Source) or not node.external or node.derived is not None:
                continue
            key = node.catalog.casefold()
            if key in result:
                continue
            if key in frozen:
                if key in parameters:
                    raise ValueError('Private source table collides with user parameter')
                result[key] = frozen[key]
            else:
                if key not in parameters:
                    raise ValueError('External query parameter is not set')
                result[key] = _snapshot(parameters[key], budget, catalogs, documents)
        from .query_packages import _check_tables
        _check_tables(result)
        return result

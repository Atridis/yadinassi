"""Source-owned neutral catalog/document identities, without record activation."""
import weakref
from uuid import UUID
from .values import BSLObject, HostFunction
from .unique_identifiers import BSLUUID
from .catalog_types import BSLCatalogType, BSLCatalogReference
from .document_types import BSLDocumentType, BSLDocumentReference

_METHODS = {'emptyref':'empty', 'пустаяссылка':'empty', 'getref':'ref',
            'получитьссылку':'ref', 'metadata':'metadata', 'метаданные':'metadata'}
_FAMILIES = {'Catalog': ('Catalogs', BSLCatalogType, BSLCatalogReference),
             'Document': ('Documents', BSLDocumentType, BSLDocumentReference)}


class SourceReferences:
    def __init__(self, source, metadata):
        from .configuration_source_metadata import SourceMetadataObject
        self.source = source
        self.metadata = metadata
        self.snapshot = object()
        self.managers = {}
        for entry in source.metadata:
            if entry.family not in _FAMILIES:
                continue
            key = (entry.family, entry.name.casefold())
            if key in self.managers:
                raise ValueError('duplicate source reference identity')
            folder, cls, _ = _FAMILIES[entry.family]
            meta = SourceMetadataObject(metadata, entry)
            self.managers[key] = (entry, cls(entry.identity, entry.name, self.snapshot), meta)
        if len(self.managers) > 4096:
            raise ValueError('source reference type count bound')

    def definition(self, family, name):
        try:
            return self.managers[(family, name.casefold())]
        except KeyError:
            raise ValueError('Unknown source manager: ' + family + '.' + name) from None

    def ref(self, family, name, identity):
        entry, value_type, meta = self.definition(family, name)
        return _FAMILIES[family][2](value_type, identity, meta)


class SourceReferenceManager(BSLObject):
    def __init__(self, app, family, name):
        self._app = weakref.ref(app)
        self.family, self.name = family, name

    def authorize(self, caller):
        app = self._app()
        if app is None:
            raise ValueError('source manager belongs to a closed application')
        app.require_open()
        caller._require_family()
        if (caller._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler
                or caller.execution_context != 'server'
                or caller._scheduler._active_task is not None):
            raise ValueError('source managers require owning synchronous server context')
        app.references.definition(self.family, self.name)
        return app

    def module(self, caller):
        return self.authorize(caller).manager_module(self.family, self.name, caller)

    def member(self, caller, name):
        self.authorize(caller)
        if name.casefold() in _METHODS:
            return self.get_member(name)
        from .source_catalog_runtime import _MANAGER_METHODS
        if self.family == 'Catalog' and name.casefold() in _MANAGER_METHODS:
            return self.get_member(name)
        return self.module(caller).get_member(name)

    def get_member(self, name):
        from .source_catalog_runtime import _MANAGER_METHODS, SourceCatalogCall
        if self.family == 'Catalog' and name.casefold() in _MANAGER_METHODS:
            return HostFunction(name, SourceCatalogCall(self, _MANAGER_METHODS[name.casefold()]))
        operation = _METHODS.get(name.casefold())
        if operation is None:
            raise ValueError('source manager export requires interpreter access')
        return HostFunction(name, SourceReferenceCall(self, operation))


class SourceReferenceCall:
    def __init__(self, manager, operation):
        self.manager, self.operation = manager, operation

    def __call__(self, *args):
        raise ValueError('source reference methods require interpreter invocation')

    def invoke(self, caller, values):
        app = self.manager.authorize(caller)
        if self.operation == 'ref':
            if len(values) != 1 or type(values[0]) is not BSLUUID:
                raise TypeError('source GetRef requires one explicit UUID')
            identity = UUID(values[0].text)
        else:
            if values:
                raise TypeError('source EmptyRef/Metadata take no arguments')
            identity = UUID(int=0)
        if self.operation == 'metadata':
            return app.references.definition(self.manager.family, self.manager.name)[2]
        return app.references.ref(self.manager.family, self.manager.name, identity)

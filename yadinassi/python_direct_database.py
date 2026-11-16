"""Direct public catalog protocol over one host-selected database.

No arbitrary getattr, no backend access and no replacement for writer validation.
"""
from .experimental_naked_boundaries import BoundaryViolation
from .catalogs import BSLCatalogs, BSLCatalogManager, BSLCatalogObject
from .catalog_types import BSLCatalogReference
from .catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from .values import HostFunction
from .queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection

NAMES=('catalogs','справочники')

class CatalogBoundary:
    def _catalog_owner(self, value):
        self._check()
        root=self.vm._catalogs
        kind=type(value)
        if kind is BSLQuery: owner=value._catalogs
        elif kind in (BSLQueryResult, BSLQueryResultSelection):
            # Detached result data: these public methods cannot execute queries
            # or write. Returned references still require the current root.
            return
        elif kind is BSLCatalogs: owner=value
        elif kind is BSLCatalogManager: owner=value._catalogs
        elif kind is BSLCatalogObject: owner=value._manager._catalogs
        elif kind is BSLCatalogSection: owner=value._owner._manager._catalogs
        elif kind is BSLCatalogSectionRow: owner=value._section._owner._manager._catalogs
        elif kind is BSLCatalogReference:
            if value.value_type.snapshot is root._metadata:return
            owner=None
        else: owner=None
        if owner is not root:
            raise BoundaryViolation('unregistered or foreign database receiver')

    def resolve_service(self,name,*args,**kwargs):
        if name.casefold() in ('new:query','new:запрос'):
            self._check()
            function=self.vm.types.get(name.split(':',1)[1].casefold())
            if type(function) is not HostFunction:
                raise BoundaryViolation('query constructor requires canonical registration')
            return super().resolve_callable(function)
        return super().resolve_service(name,*args,**kwargs)

    def external_get(self,name):
        self._check()
        if name in NAMES:return self.vm._catalogs
        return super().external_get(name)

    def external_set(self,name,value):
        self._check()
        raise ValueError('catalog namespace is read-only')

    def get_member(self,value,name):
        self._catalog_owner(value)
        try:return value.get_member(name)
        finally:self._check()

    def resolve_set_member(self,value,name):
        self._catalog_owner(value)
        def write(new_value):
            self._catalog_owner(value)
            try:value.set_member(name,new_value)
            finally:self._check()
        return write

    def resolve_member(self,value,name):
        self._catalog_owner(value)
        if name=='__getitem__': function=lambda index:value.get_index(index)
        elif name=='__setitem__': function=lambda index,new:value.set_index(index,new)
        elif name=='__iter__':
            raise BoundaryViolation('direct database iterator not connected')
        else:
            function=value.get_method(name)
            if type(function) is not HostFunction:
                raise BoundaryViolation('database method requires canonical HostFunction')
        self._check()
        def invoke(*args):
            self._catalog_owner(value)
            try:return function(*args)
            finally:self._check()
        return invoke

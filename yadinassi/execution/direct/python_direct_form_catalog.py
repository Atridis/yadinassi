"""Catalog edit buffers on an explicitly owned replicated package server."""
from yadinassi.db.catalog.catalogs import BSLCatalogs, BSLCatalogManager, BSLCatalogObject
from yadinassi.db.catalog.catalog_types import BSLCatalogReference
from yadinassi.db.catalog.catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction
from .python_direct_database import CatalogBoundary
from .python_direct_forms import FormBoundary

NAMES = ('catalogs', 'справочники')
_WRITE = ('write', 'записать')
_FIND_CODE = ('findbycode', 'найтипокоду')
_METHODS = {
    id(BSLCatalogs): ('__getitem__',),
    id(BSLCatalogManager): ('createitem', 'создатьэлемент', *_FIND_CODE),
    id(BSLCatalogReference): ('isempty', 'пустая'),
    id(BSLCatalogObject): (*_WRITE, 'isnew', 'этоновый'),
    id(BSLCatalogSection): ('add', 'добавить'),
    id(BSLCatalogSectionRow): (),
}


class PackageCatalogBoundary(FormBoundary):
    def __init__(self, session, routine):
        super().__init__(session, routine)
        self._catalog_enrollment = session._catalog_server
        self._database_owner, self._backend, self._catalogs = self._catalog_enrollment

    def _check_effect(self):
        self._check()
        owner = self.owner
        if (self.session._catalog_server is not self._catalog_enrollment
                or self.database is not self._database_owner or self.app is not None
                or owner.execution_context != 'server' or not owner._has_module_context
                or owner._catalogs is not self._catalogs or type(self._catalogs) is not BSLCatalogs
                or self._catalogs._context is not self.database
                or self._catalogs._metadata is not owner._metadata._catalogs
                or self.database.backend is not self._backend
                or type(self._backend) is not SQLiteCatalogBackend or self._backend._closed):
            raise BoundaryViolation('package server database owner changed')

    def _catalog_owner(self, value, *, verify=True):
        self._check_effect()
        CatalogBoundary._catalog_owner(self, value, verify=False)

    def external_get(self, name):
        form = self.session.form
        if name in NAMES and name not in form._attributes and name not in form._tables:
            self._check_effect()
            return self._catalogs
        return super().external_get(name)

    def _inert_reference(self, value):
        if type(value) is not BSLCatalogReference or value.value_type.snapshot is not self._catalogs._metadata:
            raise BoundaryViolation('package catalog reference owner changed')
        # Keep the typed identity (including empty), but not the live
        # presentation, member, object-reader or metadata capabilities.
        return BSLCatalogReference(value.value_type,value.reference_uuid)

    def get_member(self, value, name):
        # The point lookup supplies only an emptiness witness, not an
        # independent live catalog-field reader through reference dot access.
        if type(value) is BSLCatalogReference:
            raise ValueError('Unsupported package catalog reference field: '+name)
        if id(type(value)) in _METHODS:
            if name.startswith('_'):
                raise BoundaryViolation('private package catalog member')
            result = CatalogBoundary.get_member(self, value, name)
            if type(result) is HostFunction:
                raise BoundaryViolation('package catalog methods cannot be captured')
            if type(result) is BSLCatalogReference:
                return self._inert_reference(result)
            return result
        return super().get_member(value, name)

    def resolve_member(self, value, name):
        methods = _METHODS.get(id(type(value)))
        if methods is not None:
            key = name.casefold()
            if key not in methods:
                raise ValueError('Unsupported package catalog method: '+name)
            method = CatalogBoundary.resolve_member(self, value, name)
            if type(value) is BSLCatalogManager and key in _FIND_CODE:
                return lambda code: self._inert_reference(method(code))
            return method
        return super().resolve_member(value, name)

    def resolve_member_call(self, value, name, *, require_value=False, omitted=()):
        if id(type(value)) in _METHODS:
            if name.startswith('_'):
                raise ValueError('Private package catalog method')
            if omitted or require_value and name.casefold() in _WRITE:
                raise TypeError('Unsupported package catalog call: '+name)
            return self.resolve_member(value, name)
        return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)

    def resolve_set_member(self, value, name):
        if (type(value) is BSLCatalogObject or type(value) is BSLCatalogSectionRow) and not name.startswith('_'):
            return CatalogBoundary.resolve_set_member(self,value,name)
        return super().resolve_set_member(value,name)

    def set_member(self, value, name, new_value):
        if type(value) is BSLCatalogObject or type(value) is BSLCatalogSectionRow:
            return self.resolve_set_member(value,name)(new_value)
        return super().set_member(value,name,new_value)

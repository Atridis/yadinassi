"""Lazy, read-only CONFIG metadata view; deliberately not catalog managers.

The admitted offline profile exposes names and lookup only. Attribute metadata,
iteration, configuration properties and multi-catalog numeric ordering are not
implemented. Loading a snapshot requires neither PARAMS nor any catalog row.
"""
from decimal import Decimal

from .database_context import FileDBContext, require_database_context
from .values import BSLObject, HostFunction, to_string


class _MetadataObject(BSLObject):
    def __str__(self) -> str:
        raise ValueError('metadata presentation is unsupported')


class BSLCatalogMetadata(_MetadataObject):
    def __init__(self, name: str, metadata_uuid=None):
        self._name = name
        self._metadata_uuid = metadata_uuid

    def get_member(self, name: str) -> object:
        key = name.casefold()
        if key in ('имя', 'name'):
            return self._name
        if key in ('полноеимя', 'fullname'):
            return HostFunction(name, self.full_name)
        return super().get_member(name)

    def full_name(self) -> str:
        # The measured English alias also returns the Russian metadata prefix.
        return 'Справочник.' + self._name


class BSLCatalogMetadataCollection(_MetadataObject):
    def __init__(self, context: FileDBContext | None):
        self._context = context
        self._items = None

    def _snapshot(self) -> dict[str, BSLCatalogMetadata]:
        if self._items is None:
            if self._context is None:
                require_database_context()
            entries = self._context.catalog_metadata()
            items = {}
            for entry in entries:
                key = entry.name.casefold()
                if key in items:
                    raise ValueError('ambiguous catalog metadata name')
                items[key] = BSLCatalogMetadata(entry.name, getattr(entry, "metadata_uuid", None))
            self._items = items
        return self._items

    def count(self) -> Decimal:
        return Decimal(len(self._snapshot()))

    def find(self, name: object) -> object:
        # Scalar String conversion, not a special case for a captured literal.
        # Other argument families remain outside this bounded API profile.
        if type(name) not in (str, Decimal):
            raise TypeError('metadata name requires String or Number')
        return self._snapshot().get(to_string(name).casefold())

    def get_member(self, name: str) -> object:
        if name.casefold() in ('count', 'количество', 'find', 'найти'):
            # Method/property collision precedence is not natively measured.
            # Calls dispatch via get_method; named index/Find stay available.
            raise ValueError('metadata method-name property access is unsupported')
        item = self._snapshot().get(name.casefold())
        if item is None:
            return super().get_member(name)
        return item

    def get_method(self, name: str) -> object:
        key = name.casefold()
        if key in ('count', 'количество'):
            return HostFunction(name, self.count)
        if key in ('find', 'найти'):
            return HostFunction(name, self.find)
        return super().get_member(name)

    def get_index(self, index: object) -> object:
        items = self._snapshot()
        if type(index) is str:
            item = items.get(index.casefold())
            if item is None:
                raise ValueError('catalog metadata name not found')
            return item
        if type(index) is not Decimal or not index.is_finite() or index != index.to_integral_value():
            raise TypeError('metadata index requires String or integer Number')
        if len(items) > 1:
            raise ValueError('multi-catalog numeric metadata ordering is unsupported')
        if index != 0 or not items:
            raise IndexError('catalog metadata index out of bounds')
        return next(iter(items.values()))

    def set_index(self, index: object, value: object) -> None:
        raise ValueError('catalog metadata is read-only')


class BSLMetadata(_MetadataObject):
    def __init__(self, context: FileDBContext | None):
        self._catalogs = BSLCatalogMetadataCollection(context)

    def get_member(self, name: str) -> object:
        if name.casefold() in ('catalogs', 'справочники'):
            return self._catalogs
        return super().get_member(name)

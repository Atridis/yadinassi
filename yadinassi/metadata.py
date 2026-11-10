"""Lazy logical configuration metadata, scoped to a backend generation.

The admitted graph describes the current logical schema, not arbitrary platform
metadata or Python objects. It is immutable and scoped to one runtime snapshot.
Unsupported families, presentation and transport remain closed.
"""
from decimal import Decimal

from .database_context import SQLiteDBContext, require_database_context
from .catalog_backend import CatalogSchema, BackendError
from uuid import UUID
from .values import BSLObject, HostFunction, to_string


class _MetadataObject(BSLObject):
    def __str__(self) -> str:
        raise ValueError('metadata presentation is unsupported')


class MetadataObjectCollection(_MetadataObject):
    """Immutable named metadata objects, ordered only by admitted source order."""
    _order_known = True

    def _snapshot(self):
        return self._items

    def _ordered(self):
        items = self._snapshot()
        if not self._order_known and len(items) > 1:
            raise ValueError('multi-object numeric metadata ordering is unsupported')
        return tuple(items.values())

    def count(self):
        return Decimal(len(self._snapshot()))

    def find(self, name):
        if type(name) is not str and type(name) is not Decimal:
            raise TypeError('metadata name requires String or Number')
        return self._snapshot().get(to_string(name).casefold())

    def get(self, index):
        items = self._ordered()
        if type(index) is not Decimal or not index.is_finite() or index != index.to_integral_value():
            raise TypeError('metadata index requires integer Number')
        if index < 0 or index >= len(items):
            raise IndexError('metadata index out of bounds')
        return items[int(index)]

    def index_of(self, item):
        return Decimal(next((i for i, candidate in enumerate(self._ordered()) if candidate is item), -1))

    def contains(self, item):
        return any(candidate is item for candidate in self._snapshot().values())

    def get_method(self, name):
        method = {'count':self.count, 'количество':self.count,
                  'find':self.find, 'найти':self.find, 'get':self.get, 'получить':self.get,
                  'indexof':self.index_of, 'индекс':self.index_of,
                  'contains':self.contains, 'содержит':self.contains}.get(name.casefold())
        return HostFunction(name, method) if method is not None else super().get_method(name)

    def get_member(self, name):
        if name.casefold() in ('count','количество','find','найти','get','получить',
                                'indexof','индекс','contains','содержит'):
            raise ValueError('metadata method-name property access is unsupported')
        item = self._snapshot().get(name.casefold())
        return super().get_member(name) if item is None else item

    def get_index(self, index):
        if type(index) is not str:
            return self.get(index)
        item = self._snapshot().get(index.casefold())
        if item is None: raise ValueError('metadata name not found')
        return item

    def set_index(self, index, value):
        raise ValueError('metadata is read-only')

    def __iter__(self):
        return iter(self._ordered())


class _DeclaredMetadataCollection(MetadataObjectCollection):
    def __init__(self, items):
        self._items = {item._name.casefold():item for item in items}
        if len(self._items) != len(items): raise ValueError('ambiguous metadata name')


class BSLAttributeMetadata(_MetadataObject):
    def __init__(self, owner, field, family='Реквизит'):
        self._owner, self._field, self._family = owner, field, family
        self._name = field.name
        self._description = None

    def full_name(self):
        return self._owner.full_name() + '.' + self._family + '.' + self._name

    def get_member(self, name):
        key = name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('synonym','синоним','comment','комментарий'): return ''
        if key in ('fullname','полноеимя'): return HostFunction(name, self.full_name)
        if key in ('type','тип'):
            if self._description is None:
                self._description = _field_description(self._field, self._owner._root)
            return self._description
        return super().get_member(name)


class BSLTabularSectionMetadata(_MetadataObject):
    def __init__(self, owner, schema):
        self._owner, self._schema, self._root = owner, schema, owner._root
        self._name = schema.name
        self._attributes = _DeclaredMetadataCollection(tuple(BSLAttributeMetadata(self, f) for f in schema.fields))
        self._standard = None

    def full_name(self):
        return self._owner.full_name() + '.ТабличнаяЧасть.' + self._name

    def get_member(self, name):
        key = name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('synonym','синоним','comment','комментарий'): return ''
        if key in ('fullname','полноеимя'): return HostFunction(name, self.full_name)
        if key in ('attributes','реквизиты'): return self._attributes
        if key in ('standardattributes','стандартныереквизиты'):
            if self._standard is None:
                self._standard = StandardAttributeDescriptions((('LineNumber','НомерСтроки', _scalar_description('number',(9,0,'Nonnegative'))),))
            return self._standard
        return super().get_member(name)


class StandardAttributeDescription(_MetadataObject):
    def __init__(self, name, description):
        self._name, self._description = name, description

    def get_member(self, name):
        key = name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('type','тип'): return self._description
        if key in ('synonym','синоним','comment','комментарий'): return ''
        # FullName and mutation are not part of StandardAttributeDescription.
        return super().get_member(name)


class StandardAttributeDescriptions(_MetadataObject):
    """Separate contract, NOT MetadataObjectCollection's Find/Get methods."""
    def __init__(self, fields):
        self._items = tuple(StandardAttributeDescription(ru, description) for en,ru,description in fields)
        self._names = {alias.casefold():item for (en,ru,_),item in zip(fields,self._items) for alias in (en,ru)}

    def get_method(self, name):
        if name.casefold() in ('count','количество'):
            return HostFunction(name, lambda:Decimal(len(self._items)))
        return super().get_method(name)

    def get_index(self, index):
        if type(index) is str:
            item = self._names.get(index.casefold())
            if item is None: raise ValueError('standard attribute not supported')
            return item
        if type(index) is not Decimal or not index.is_finite() or index != index.to_integral_value():
            raise TypeError('standard attribute index requires String or integer Number')
        if index < 0 or index >= len(self._items): raise IndexError('standard attribute index out of bounds')
        return self._items[int(index)]

    def set_index(self, index, value): raise ValueError('metadata is read-only')
    def __iter__(self): return iter(self._items)


def _scalar_description(kind, qualifiers=()):
    from .type_descriptions import BSLTypeDescription
    from .type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLAllowedSign, BSLAllowedLength, BSLDateFractions
    if kind == 'string':
        length = qualifiers[0] if qualifiers else 0
        allowed = qualifiers[1] if len(qualifiers) > 1 else 'Variable'
        return BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(length), BSLAllowedLength.FIXED if allowed == 'Fixed' else BSLAllowedLength.VARIABLE))
    if kind == 'number':
        digits, fraction, sign = qualifiers or (0,0,'Any')
        return BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(digits),Decimal(fraction),BSLAllowedSign.NONNEGATIVE if sign == 'Nonnegative' else BSLAllowedSign.ANY))
    if kind == 'datetime':
        part = (qualifiers or ('DateTime',))[0]
        return BSLTypeDescription('Date',None,None,BSLDateQualifiers({'Date':BSLDateFractions.DATE,'Time':BSLDateFractions.TIME,'DateTime':BSLDateFractions.DATE_TIME}[part]))
    if kind == 'boolean': return BSLTypeDescription('Boolean')
    raise ValueError('unsupported metadata field type')


def _field_description(field, root):
    if field.kind == 'catalog_ref':
        from .type_descriptions import _reference_description
        if root is None or root._catalog_managers is None: raise ValueError('metadata type requires runtime binding')
        return _reference_description(root._catalog_managers._manager_by_metadata_uuid(field.target_catalog_id)._value_type)
    return _scalar_description(field.kind, field.qualifiers)


class BSLCatalogMetadata(_MetadataObject):
    def __init__(self, name: str, metadata_uuid=None):
        self._name = name
        self._metadata_uuid = metadata_uuid
        self._root = None
        self._children = {}

    def get_member(self, name: str) -> object:
        key = name.casefold()
        if key in ('hierarchical','иерархический') and type(getattr(self,'_schema',None)) is CatalogSchema:
            return getattr(self._schema,'hierarchy','none')!='none'
        if key in ('имя', 'name'):
            return self._name
        if key in ('synonym','синоним','comment','комментарий'): return ''
        child = _child_collection(self, key)
        if child is not None: return child
        if key in ('полноеимя', 'fullname'):
            return HostFunction(name, self.full_name)
        return super().get_member(name)

    def full_name(self) -> str:
        # The measured English alias also returns the Russian metadata prefix.
        return 'Справочник.' + self._name


class BSLCatalogMetadataCollection(MetadataObjectCollection):
    _family = 'Catalog'
    _item_type = BSLCatalogMetadata
    _reader = 'begin_read'
    _entries = 'catalogs'

    def __init__(self, context, root=None):
        self._context, self._root = context, root
        self._items = None
        self._order_known = False

    def _snapshot(self):
        if self._items is None:
            if self._context is None: require_database_context()
            if self._root is not None and self._family != 'Catalog': self._root._catalogs._snapshot()
            reader = ('begin_query_read' if self._family != 'Catalog' and type(self._context) is SQLiteDBContext else self._reader)
            view = getattr(self._context.backend, reader)()
            try:
                entries = getattr(view,self._entries)()
                database, generation = view.database_id, view.configuration_generation
                items = {}
                for entry in entries:
                    key = entry.name.casefold()
                    if key in items: raise ValueError('ambiguous metadata name')
                    item = self._item_type(entry.name,str(entry.identity))
                    item._schema, item._root = entry,self._root
                    items[key] = item
                if self._root is not None:
                    self._root._accept_snapshot(database,generation)
            finally: view.close()
            self._database_id,self._generation = database,generation
            self._items = items
        return self._items

    def _ordered(self):
        items = self._snapshot()
        if len(items) <= 1: return tuple(items.values())
        if self._root is None or type(self._context) is not SQLiteDBContext:
            return super()._ordered()
        # Logical schema-only hosts remain valid for Count/Find/row operations.
        # Only an operation requiring source order loads the source-tree port.
        self._root._ensure_source_info()
        order = self._root._orders.get(self._family)
        keys = tuple(name.casefold() for name in order) if order is not None else ()
        if len(keys) != len(items) or set(keys) != set(items): raise BackendError('schema_changed')
        return tuple(items[key] for key in keys)


class BSLDocumentMetadata(BSLCatalogMetadata):
    def full_name(self):
        return 'Документ.' + self._name


class BSLDocumentMetadataCollection(BSLCatalogMetadataCollection):
    _family, _item_type = 'Document', BSLDocumentMetadata
    _reader, _entries = 'begin_document_read', 'documents'

    def __init__(self, context, catalogs, root=None):
        super().__init__(context,root)
        self._catalogs = catalogs
        self._config_snapshot = None


class BSLInformationRegisterMetadata(BSLCatalogMetadata):
    def get_member(self, name):
        if name.casefold() in ('periodicity','периодичность'): return self._schema.periodicity
        return super().get_member(name)
    def full_name(self):
        return 'РегистрСведений.' + self._name


class BSLInformationRegisterMetadataCollection(BSLDocumentMetadataCollection):
    _family, _item_type = 'InformationRegister', BSLInformationRegisterMetadata
    _reader, _entries = 'begin_register_read', 'registers'


class BSLMetadata(_MetadataObject):
    def __init__(self, context: SQLiteDBContext | None):
        self._catalogs = BSLCatalogMetadataCollection(context,self)
        self._documents = BSLDocumentMetadataCollection(context, self._catalogs,self)
        self._information_registers = BSLInformationRegisterMetadataCollection(context, self._catalogs,self)
        self._common_modules = None
        self._catalog_managers = self._document_managers = None
        self._configuration_name = None
        self._identity = None
        self._orders = {}

    def _accept_snapshot(self, database, generation, info=None):
        if self._identity is not None and self._identity != (database,generation):
            raise BackendError('schema_changed')
        if info is not None:
            name, orders = info
            self._configuration_name = name
            self._orders = dict(orders)
        self._identity = database,generation

    def _ensure_source_info(self):
        if self._orders: return
        context = self._catalogs._context
        if context is None: require_database_context()
        if type(context) is not SQLiteDBContext: raise ValueError('configuration source metadata unavailable')
        view = context.backend.begin_read()
        try:
            info = view.metadata_configuration()
            self._accept_snapshot(view.database_id,view.configuration_generation,info)
        finally: view.close()

    def find_by_type(self, kind):
        from .catalog_types import BSLCatalogType
        from .document_types import BSLDocumentType
        from .information_registers import BSLInformationRegisterType
        from .values import BSLType
        if type(kind) is BSLType: return None
        collection = (self._catalogs if type(kind) is BSLCatalogType else
                      self._documents if type(kind) is BSLDocumentType else
                      self._information_registers if type(kind) is BSLInformationRegisterType else None)
        if collection is None: raise TypeError('FindByType requires a supported Type value')
        if kind.snapshot is not collection: raise ValueError('metadata type belongs to another runtime snapshot')
        return next((item for item in collection._snapshot().values() if UUID(item._metadata_uuid) == kind.metadata_uuid), None)

    def find_by_full_name(self, name):
        if type(name) is not str: raise TypeError('FindByFullName requires String')
        if len(name) > 2048: raise ValueError('metadata path resource limit')
        parts = name.split('.')
        if len(parts) < 2 or len(parts) > 6 or len(parts) % 2: return None
        collection = {'catalog':self._catalogs,'справочник':self._catalogs,
                      'document':self._documents,'документ':self._documents,
                      'informationregister':self._information_registers,'регистрсведений':self._information_registers,
                      'commonmodule':self._common_modules,'общиймодуль':self._common_modules}.get(parts[0].casefold())
        if collection is None: return None
        item = collection.find(parts[1])
        aliases = {'attribute':'attributes','реквизит':'attributes','dimension':'dimensions','измерение':'dimensions',
                   'resource':'resources','ресурс':'resources','tabularsection':'tabularsections','табличнаячасть':'tabularsections'}
        for i in range(2,len(parts),2):
            if item is None: return None
            child = aliases.get(parts[i].casefold())
            if child is None: return None
            collection = _child_collection(item,child)
            if collection is None: return None
            item = collection.find(parts[i+1])
        return item

    def get_method(self, name):
        key = name.casefold()
        if key in ('findbytype','найтипотипу'): return HostFunction(name,self.find_by_type)
        if key in ('findbyfullname','найтипополномуимени'): return HostFunction(name,self.find_by_full_name)
        return super().get_method(name)


    def get_member(self, name: str) -> object:
        if name.casefold() in ('name','имя','synonym','синоним','comment','комментарий'):
            if self._configuration_name is None: self._ensure_source_info()
            if self._configuration_name is None: raise ValueError('configuration metadata unavailable')
            return self._configuration_name if name.casefold() in ('name','имя') else ''
        if name.casefold() in ('commonmodules', 'общиемодули') and self._common_modules is not None:
            return self._common_modules
        if name.casefold() in ('catalogs', 'справочники'):
            return self._catalogs
        if name.casefold() in ('documents', 'документы'):
            return self._documents
        if name.casefold() in ('informationregisters', 'регистрысведений'):
            return self._information_registers
        return super().get_member(name)


class BSLCommonModuleMetadata(_MetadataObject):
    def __init__(self, definition):
        self._definition = definition
        self._name = definition.name

    def get_member(self, name):
        key = name.casefold()
        d = self._definition
        if key in ('name', 'имя'): return d.name
        if key in ('synonym','синоним','comment','комментарий'): return ''
        if key in ('fullname','полноеимя'): return HostFunction(name,self.full_name)
        if key in ('global', 'глобальный'): return d.global_module
        if key in ('clientmanagedapplication', 'клиентуправляемоеприложение'): return d.client
        if key in ('server', 'сервер'): return d.server
        if key in ('servercall', 'вызовсервера'): return d.server_call
        if key in ('privileged', 'привилегированный'): return False
        return super().get_member(name)


    def full_name(self): return 'ОбщийМодуль.' + self._name


class BSLCommonModuleMetadataCollection(MetadataObjectCollection):
    """The explicit application's immutable registry, not arbitrary reflection."""
    def __init__(self, definitions):
        self._items = {d.name.casefold(): BSLCommonModuleMetadata(d) for d in definitions}


def _child_collection(owner, key):
    if type(owner) is BSLTabularSectionMetadata:
        if key in ('attributes','реквизиты'): return owner._attributes
        return None
    if not any(type(owner) is cls for cls in (BSLCatalogMetadata,BSLDocumentMetadata,BSLInformationRegisterMetadata)):
        return None
    schema = getattr(owner,'_schema',None)
    if schema is None: return None
    family = {'attributes':'attributes','реквизиты':'attributes','tabularsections':'sections','табличныечасти':'sections',
              'dimensions':'dimensions','измерения':'dimensions','resources':'resources','ресурсы':'resources',
              'standardattributes':'standard','стандартныереквизиты':'standard'}.get(key)
    if family is None: return None
    register = type(owner) is BSLInformationRegisterMetadata
    if (family in ('dimensions','resources') and not register) or (family == 'sections' and register): return None
    if family not in owner._children:
        if family == 'sections':
            result = _DeclaredMetadataCollection(tuple(BSLTabularSectionMetadata(owner,s) for s in schema.tabular_sections))
        elif family == 'standard': result = _standard_attributes(owner)
        else:
            fields = getattr(schema,family) if register else schema.fields
            label = {'attributes':'Реквизит','dimensions':'Измерение','resources':'Ресурс'}[family]
            result = _DeclaredMetadataCollection(tuple(BSLAttributeMetadata(owner,f,label) for f in fields))
        owner._children[family] = result
    return owner._children[family]


def _standard_attributes(owner):
    # This is the explicitly admitted record-field subset, not all native
    # standard metadata (recorder/posting/version/owner remain unsupported).
    schema, root = owner._schema, owner._root
    if type(owner) is BSLInformationRegisterMetadata:
        fields = (('Period','Период',_field_description(schema.period_field,root)),) if schema.periodic else ()
        return StandardAttributeDescriptions(fields)
    from .type_descriptions import _reference_description
    if root is None or root._catalog_managers is None: raise ValueError('metadata type requires runtime binding')
    managers = root._catalog_managers if type(owner) is BSLCatalogMetadata else root._document_managers
    reference = _reference_description(managers.get_index(owner._name)._value_type)
    fields = [('Ref','Ссылка',reference),('DeletionMark','ПометкаУдаления',_scalar_description('boolean'))]
    if type(owner) is BSLCatalogMetadata:
        fields += [('Code','Код',_scalar_description('string',(schema.code_length,'Variable'))),
                   ('Description','Наименование',_scalar_description('string',(schema.description_length,'Variable')))]
        if schema.hierarchy != 'none':
            fields += [('Parent','Родитель',reference),('IsFolder','ЭтоГруппа',_scalar_description('boolean'))]
    else:
        fields += [('Number','Номер',_scalar_description('string',(schema.number_length,'Variable'))),
                   ('Date','Дата',_scalar_description('datetime'))]
    return StandardAttributeDescriptions(tuple(fields))


def is_metadata_collection(value):
    return any(type(value) is cls for cls in (BSLCatalogMetadataCollection,BSLDocumentMetadataCollection,
        BSLInformationRegisterMetadataCollection,BSLCommonModuleMetadataCollection,_DeclaredMetadataCollection,StandardAttributeDescriptions))


def is_metadata_object(value):
    return is_metadata_collection(value) or any(type(value) is cls for cls in (
        BSLMetadata,BSLCatalogMetadata,BSLDocumentMetadata,BSLInformationRegisterMetadata,
        BSLCommonModuleMetadata,BSLAttributeMetadata,BSLTabularSectionMetadata,StandardAttributeDescription))

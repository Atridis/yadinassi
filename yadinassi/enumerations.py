"""Read-only application enum namespace. No SQL, network or source evaluator."""
from decimal import Decimal
from uuid import UUID
from .values import BSLObject, HostFunction
from .enum_types import BSLEnumType, BSLEnumReference
from .metadata import _MetadataObject, _DeclaredMetadataCollection


class EnumValueMetadata(_MetadataObject):
    def __init__(self, definition, owner):
        self._definition=definition;self._owner=owner;self._name=definition.name

    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('comment','комментарий'): return self._definition.comment
        return super().get_member(name)


class EnumMetadata(_MetadataObject):
    def __init__(self,definition):
        self._definition=definition;self._name=definition.name
        self._values=_DeclaredMetadataCollection(tuple(EnumValueMetadata(v,self) for v in definition.values))

    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('comment','комментарий'): return self._definition.comment
        if key in ('enumvalues','значенияперечисления'): return self._values
        return super().get_member(name)


class BSLEnumManager(BSLObject):
    def __init__(self,metadata,snapshot):
        self._metadata=metadata;definition=metadata._definition
        self._value_type=BSLEnumType(definition.identity,definition.name,snapshot)
        self._manager_type=BSLEnumType(definition.identity,definition.name,snapshot,'manager')
        self._values=tuple(BSLEnumReference(self._value_type,v.identity,metadata) for v in definition.values)
        self._named={v.name.casefold():r for v,r in zip(definition.values,self._values)}
        self._empty=BSLEnumReference(self._value_type,UUID(int=0),metadata)

    def count(self): return Decimal(len(self._values))

    def get(self,index):
        if type(index) is not Decimal or not index.is_finite() or index!=index.to_integral_value():
            raise TypeError('enumeration index requires integer Number')
        if index<0 or index>=len(self._values): raise IndexError('enumeration index out of bounds')
        return self._values[int(index)]

    def index_of(self,value):
        if type(value) is not BSLEnumReference or value.value_type!=self._value_type:
            raise TypeError('enumeration reference belongs to another type or application')
        return Decimal(next((i for i,v in enumerate(self._values) if v==value),-1))

    def get_member(self,name):
        key=name.casefold()
        if key in self._named: return self._named[key]
        return super().get_member(name)

    def get_method(self,name):
        fn={'count':self.count,'количество':self.count,'get':self.get,'получить':self.get,
            'indexof':self.index_of,'индекс':self.index_of,'emptyref':lambda:self._empty,
            'пустаяссылка':lambda:self._empty,'metadata':lambda:self._metadata,
            'метаданные':lambda:self._metadata}.get(name.casefold())
        return HostFunction(name,fn) if fn is not None else super().get_method(name)

    def get_index(self,index):
        if type(index) is str:
            if index.casefold() not in self._named: raise ValueError('enumeration value not found')
            return self._named[index.casefold()]
        return self.get(index)

    def set_index(self,index,value): raise ValueError('enumeration values are read-only')

    def __iter__(self): return iter(self._values)


class BSLEnumerations(BSLObject):
    def __init__(self,definitions):
        self.metadata=_DeclaredMetadataCollection(tuple(EnumMetadata(d) for d in definitions))
        self._managers={m._name.casefold():BSLEnumManager(m,self.metadata) for m in self.metadata}

    def get_member(self,name):
        value=self._managers.get(name.casefold())
        return super().get_member(name) if value is None else value

    def get_index(self,name):
        if type(name) is not str: raise TypeError('enumeration name requires String')
        return self.get_member(name)

    def set_index(self,name,value): raise ValueError('enumerations are read-only')

    def resolve_type(self,name):
        if type(name) is not str: return None
        prefix,sep,item=name.partition('.')
        family={'enumref':'ref','перечислениессылка':'ref','enummanager':'manager',
                'перечислениеменеджер':'manager'}.get(prefix.casefold())
        if not sep or family is None: return None
        manager=self.get_index(item)
        return manager._value_type if family=='ref' else manager._manager_type

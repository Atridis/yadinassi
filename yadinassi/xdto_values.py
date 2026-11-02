"""Bounded typed XDTO graph and metadata; not arbitrary schema/object execution."""
from decimal import Decimal
import base64
import re
from .file_io import _FileMethods, _methods, BSLBinaryData
from .values import NULL, BSLArray
from .dates import BSLDate
from .xml_values import xml_string, xml_value
from .values import BSLType

XS='http://www.w3.org/2001/XMLSchema'
MAX_NODES=10000
MAX_UNITS=4*1024*1024
MAX_TEXT=262144
MAX_DEPTH=32
MAX_TYPES=128
MAX_PROPERTIES=256
MAX_LIST=4096


def text(v):
    if type(v) is not str:raise TypeError('XDTO: ожидается Строка')
    if len(v)>MAX_TEXT:raise ValueError('XDTO: превышен предел строки')
    return v


def index(v,limit,*,end=False):
    if not (type(v) is int or type(v) is Decimal) or not 0<=v<=limit or v!=int(v):raise ValueError('XDTO: неверный индекс')
    i=int(v)
    if i==limit and not end:raise ValueError('XDTO: неверный индекс')
    return i


class _Readonly(_FileMethods):
    def set_member(self,name,value):raise ValueError('XDTO: свойство только для чтения')


class BSLXDTOPropertyCollection(_Readonly):
    _methods=_methods(('count',True,'Count Количество'),('get',True,'Get Получить'))
    def __init__(self,items):self._items=tuple(items)
    def __str__(self):return 'КоллекцияСвойствXDTO'
    def count(self):return Decimal(len(self._items))
    def get(self,key):
        if type(key) is str:return next((p for p in self._items if p._name==text(key)),None)
        return self._items[index(key,len(self._items))]
    def __getitem__(self,key):return self.get(key)
    def __iter__(self):return iter(self._items)


class BSLXDTOProperty(_Readonly):
    def __init__(self,owner,name,kind,uri,lower,upper,nillable,attribute=False):
        self._owner=owner;self._name=name;self._type=kind;self._uri=uri
        self._lower=lower;self._upper=upper;self._nil=nillable;self._attribute=attribute
    def __str__(self):return 'СвойствоXDTO'
    def get_member(self,name):
        key=name.casefold();pairs={
            'name':self._name,'имя':self._name,'localname':self._name,'локальноеимя':self._name,
            'namespaceuri':self._uri,'uriпространстваимен':self._uri,'type':self._type,'тип':self._type,
            'ownertype':self._owner,'типвладелец':self._owner,'ownerobject':None,'объектвладелец':None,
            'lowerbound':Decimal(self._lower),'нижняяграница':Decimal(self._lower),
            'upperbound':Decimal(self._upper),'верхняяграница':Decimal(self._upper),
            'nillable':self._nil,'возможнопустое':self._nil,'qualified':bool(self._uri),'квалифицированное':bool(self._uri),
            'defaultvalue':None,'значениепоумолчанию':None,'fixed':False,'фиксированное':False}
        if key in ('form','форма'):
            from .xdto_io import BSLXMLForm
            return BSLXMLForm.ATTRIBUTE if self._attribute else BSLXMLForm.ELEMENT
        if key in pairs:return pairs[key]
        return super().get_member(name)


class BSLXDTOValueType(_Readonly):
    _methods=_methods(('is_descendant',True,'IsDescendant ЭтоПотомок'),('validate',False,'Validate Проверить'))
    def __init__(self,factory,name,uri=XS):self._factory=factory;self._name=name;self._uri=uri
    def __str__(self):return 'ТипЗначенияXDTO'
    def is_descendant(self,other):return self is other
    def validate(self,value):
        if type(self) is BSLXDTOObjectType:
            if type(value) is not BSLXDTODataObject or value._type is not self:raise TypeError('XDTO: неверный тип объекта')
            value.validate()
        else:scalar(self,value)
    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'):return self._name
        if key in ('namespaceuri','uriпространстваимен'):return self._uri
        if key in ('basetype','базовыйтип'):return None
        return super().get_member(name)


class BSLXDTOObjectType(BSLXDTOValueType):
    def __init__(self,factory,name,uri):super().__init__(factory,name,uri);self._properties=BSLXDTOPropertyCollection(())
    def __str__(self):return 'ТипОбъектаXDTO'
    def get_member(self,name):
        if name.casefold() in ('properties','свойства'):return self._properties
        if name.casefold() in ('ordered','упорядоченный'):return True
        if name.casefold() in ('abstract','абстрактный','open','открытый','sequenced','последовательный','mixed','смешанный'):return False
        return super().get_member(name)


class BSLXDTOPackage(_Readonly):
    _methods=_methods(('count',True,'Count Количество'),('get',True,'Get Получить'))
    def __init__(self,uri,types,roots=()):self._uri=uri;self._types=tuple(types);self._roots=BSLXDTOPropertyCollection(roots);self._element_qualified=False;self._attribute_qualified=False
    def __str__(self):return 'ПакетXDTO'
    def count(self):return Decimal(len(self._types))
    def get(self,key):
        if type(key) is str:return next((t for t in self._types if t._name==text(key)),None)
        return self._types[index(key,len(self._types))]
    def __getitem__(self,key):return self.get(key)
    def __iter__(self):return iter(self._types)
    def get_member(self,name):
        if name.casefold() in ('namespaceuri','uriпространстваимен'):return self._uri
        if name.casefold() in ('rootproperties','корневыесвойства'):return self._roots
        if name.casefold() in ('elementformqualified','квалифицированнаяформаэлемента'):return self._element_qualified
        if name.casefold() in ('attributeformqualified','квалифицированнаяформаатрибута'):return self._attribute_qualified
        return super().get_member(name)


class BSLXDTOPackageCollection(BSLXDTOPropertyCollection):
    def __str__(self):return 'КоллекцияПакетовXDTO'
    def get(self,key):
        if type(key) is str:return next((p for p in self._items if p._uri==text(key)),None)
        return super().get(key)


def scalar(kind,value):
    """Closed conversions; no arbitrary host coercion or ambient decimal rounding."""
    name=kind._name
    if name=='string':
        value=text(value);return value,value
    if name=='boolean':
        if type(value) is str:
            token=text(value)
            if token not in ('true','false','1','0'):raise ValueError('XDTO: неверное Булево')
            value=token in ('true','1')
        if type(value) is not bool:raise TypeError('XDTO: ожидается Булево')
        return value,'true' if value else 'false'
    if name in ('decimal','integer','int','long'):
        if type(value) is str:
            if len(value)>256 or re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?',value) is None:raise ValueError('XDTO: неверное число')
            value=Decimal(value)
        if type(value) is int:
            if value.bit_length()>512:raise ValueError('XDTO: превышен предел числа')
            value=Decimal(value)
        if type(value) is not Decimal or not value.is_finite():raise TypeError('XDTO: ожидается конечное Число')
        # CPython Decimal size is only an admission guard before coefficient copy.
        if value.__sizeof__()>512:raise ValueError('XDTO: превышен предел числа')
        tup=value.as_tuple()
        if len(tup.digits)>128 or abs(tup.exponent)>128:raise ValueError('XDTO: превышен предел числа')
        if name!='decimal' and value!=value.to_integral_value():raise ValueError('XDTO: ожидается целое число')
        if name=='int' and not -(2**31)<=value<2**31:raise ValueError('XDTO: int вне диапазона')
        if name=='long' and not -(2**63)<=value<2**63:raise ValueError('XDTO: long вне диапазона')
        result=format(value,'f')
        if '.' in result:result=result.rstrip('0').rstrip('.')
        if value==0:result='0'
        return value,result
    if name in ('dateTime','date'):
        if type(value) is str:value=xml_value(BSLType.DATE,text(value))
        if type(value) is not BSLDate:raise TypeError('XDTO: ожидается Дата')
        result=xml_string(value);return value,result[:10] if name=='date' else result
    if name=='base64Binary':
        if type(value) is str:
            if len(value)>MAX_TEXT:raise ValueError('XDTO: превышен предел двоичных данных')
            try:value=BSLBinaryData.from_bytes(base64.b64decode(value,validate=True))
            except (ValueError,UnicodeError):raise ValueError('XDTO: неверный base64') from None
        if type(value) is not BSLBinaryData or len(value._data)>MAX_TEXT//2:raise ValueError('XDTO: неверные двоичные данные')
        return value,base64.b64encode(value._data).decode('ascii')
    raise ValueError('XDTO: неподдержанный скалярный тип')


class BSLXDTODataValue(_Readonly):
    _methods=_methods(('type',True,'Type Тип'),('factory',True,'Factory Фабрика'))
    def __init__(self,kind,value):
        native,lexical=scalar(kind,value);kind._factory._reserve(1,len(lexical))
        self._type=kind;self._value=native;self._lexical=lexical;self._factory=kind._factory
    def __str__(self):return 'ЗначениеXDTO'
    def type(self):return self._type
    def factory(self):return self._factory
    def get_member(self,name):
        if name.casefold() in ('value','значение'):return self._value
        if name.casefold() in ('lexicalvalue','лексическоезначение'):return self._lexical
        return super().get_member(name)


def _native(value):return value._value if type(value) is BSLXDTODataValue else value


def _prepare(prop,value,owner):
    if value is None or value is NULL:
        if not prop._nil:raise ValueError('XDTO: пустое значение не разрешено')
        return None
    if (type(value) is BSLXDTODataObject or type(value) is BSLXDTODataValue):
        if value._type is not prop._type:raise TypeError('XDTO: тип свойства не совпадает')
        if type(value) is BSLXDTODataObject:
            if value._owner is not None:raise ValueError('XDTO: объект уже принадлежит свойству')
            current=owner;depth=0
            while current is not None:
                if current is value:raise ValueError('XDTO: цикл владения')
                current=current._owner;depth+=1
                if depth>MAX_DEPTH:raise ValueError('XDTO: превышена глубина')
            # Check complete subtree before ownership changes.
            todo=[(value,depth)];seen=set()
            while todo:
                node,d=todo.pop()
                if d>MAX_DEPTH or id(node) in seen:raise ValueError('XDTO: неверное дерево')
                seen.add(id(node))
                for item in node._values.values():
                    for child in item._items if type(item) is BSLXDTOList else (item,):
                        if type(child) is BSLXDTODataObject:todo.append((child,d+1))
        return value
    if type(prop._type) is not BSLXDTOValueType:raise TypeError('XDTO: ожидается ОбъектXDTO')
    return BSLXDTODataValue(prop._type,value)


def _attach(value,owner,prop):
    if type(value) is BSLXDTODataObject:value._owner=owner;value._owning=prop


def _detach(value):
    if type(value) is BSLXDTODataObject:value._owner=None;value._owning=None


class BSLXDTOList(_Readonly):
    _methods=_methods(('count',True,'Count Количество'),('get',True,'Get Получить'),('get_xdto',True,'GetXDTO ПолучитьXDTO'),
        ('add',True,'Add Добавить'),('insert',True,'Insert Вставить'),('set',True,'Set Установить'),('delete',True,'Delete Удалить'),('clear',False,'Clear Очистить'))
    def __init__(self,owner,prop):self._owner=owner;self._prop=prop;self._items=[]
    def __str__(self):return 'СписокXDTO'
    def count(self):return Decimal(len(self._items))
    def get_xdto(self,i):return self._items[index(i,len(self._items))]
    def get(self,i):return _native(self.get_xdto(i))
    def __getitem__(self,i):return self.get(i)
    def __setitem__(self,i,v):self.set(i,v)
    def __iter__(self):return iter(tuple(_native(v) for v in self._items))
    def get_member(self,name):
        if name.casefold() in ('owningproperty','владеющеесвойство'):return self._prop
        if name.casefold() in ('owner','владелец'):return self._owner
        return super().get_member(name)
    def insert(self,i,value):
        i=index(i,len(self._items),end=True)
        cap=min(MAX_LIST,self._prop._upper if self._prop._upper>=0 else MAX_LIST)
        if len(self._items)>=cap:raise ValueError('XDTO: превышен размер списка')
        factory=self._owner._factory;previous=factory._nodes,factory._units
        try:
            v=_prepare(self._prop,value,self._owner);factory._reserve(1,0)
        except Exception:
            factory._nodes,factory._units=previous
            raise
        self._items.insert(i,v);_attach(v,self._owner,self._prop);return v
    def add(self,value):return self.insert(len(self._items),value)
    def set(self,i,value):
        i=index(i,len(self._items));old=self._items[i]
        if value is old:return old
        v=_prepare(self._prop,value,self._owner);_detach(old);self._items[i]=v;_attach(v,self._owner,self._prop);return v
    def delete(self,i=None):
        i=len(self._items)-1 if i is None else index(i,len(self._items))
        if i<0:raise ValueError('XDTO: список пуст')
        v=self._items.pop(i);_detach(v);return v
    def clear(self):
        for v in self._items:_detach(v)
        self._items.clear()


class BSLXDTODataObject(_FileMethods):
    _methods=_methods(('type',True,'Type Тип'),('factory',True,'Factory Фабрика'),('properties',True,'Properties Свойства'),
        ('owner',True,'Owner Владелец'),('owning_property',True,'OwningProperty ВладеющееСвойство'),
        ('get',True,'Get Получить'),('get_xdto',True,'GetXDTO ПолучитьXDTO'),('get_list',True,'GetList ПолучитьСписок'),
        ('set',False,'Set Установить'),('unset',False,'Unset Сбросить'),('is_set',True,'IsSet Установлено'),('validate',False,'Validate Проверить'))
    def __init__(self,kind):
        kind._factory._reserve(1,0);self._factory=kind._factory;self._type=kind
        self._owner=None;self._owning=None;self._values={}
    def __str__(self):return 'ОбъектXDTO'
    def type(self):return self._type
    def factory(self):return self._factory
    def properties(self):return self._type._properties
    def owner(self):return self._owner
    def owning_property(self):return self._owning
    def _property(self,key):
        if type(key) is BSLXDTOProperty:
            if key._owner is not self._type:raise ValueError('XDTO: чужое свойство')
            return key
        key=text(key)
        # !todo XPath expressions are not evaluated; only a direct property name.
        if any(c in key for c in '/[]@*'):raise ValueError('XDTO: XPath пока не поддерживается')
        p=self._type._properties.get(key)
        if p is None:raise ValueError('XDTO: неизвестное свойство')
        return p
    def get_xdto(self,key):
        p=self._property(key)
        if p._upper!=1:return self.get_list(p)
        return self._values.get(p._name)
    def get(self,key):return _native(self.get_xdto(key))
    def get_list(self,key):
        p=self._property(key)
        if p._upper==1:raise ValueError('XDTO: свойство не является списком')
        if p._name not in self._values:
            self._factory._reserve(1,0);self._values[p._name]=BSLXDTOList(self,p)
        return self._values[p._name]
    def set(self,key,value=None):
        p=self._property(key)
        if p._upper!=1:raise ValueError('XDTO: используйте методы списка')
        old=self._values.get(p._name)
        if value is old and p._name in self._values:return
        v=_prepare(p,value,self);self._values[p._name]=v;_detach(old);_attach(v,self,p)
    def unset(self,key):
        p=self._property(key);old=self._values.pop(p._name,None)
        if type(old) is BSLXDTOList:old.clear()
        else:_detach(old)
    def is_set(self,key):return self._property(key)._name in self._values
    def get_member(self,name):return self.get(name)
    def set_member(self,name,value):return self.set(name,value)
    def __getitem__(self,key):return self.get(key)
    def __setitem__(self,key,value):self.set(key,value)
    def validate(self):
        todo=[(self,0)];count=0
        while todo:
            obj,depth=todo.pop();count+=1
            if count>MAX_NODES or depth>MAX_DEPTH:raise ValueError('XDTO: превышен предел проверки')
            for prop in obj._type._properties:
                value=obj._values.get(prop._name)
                items=value._items if type(value) is BSLXDTOList else ([value] if prop._name in obj._values else [])
                if len(items)<prop._lower:raise ValueError('XDTO: обязательное свойство не установлено')
                for item in items:
                    if item is None and not prop._nil:raise ValueError('XDTO: пустое свойство')
                    if type(item) is BSLXDTODataObject:todo.append((item,depth+1))

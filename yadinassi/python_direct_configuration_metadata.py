"""Scope-issued, non-retainable readonly CommonModules metadata intermediates.

Tokens contain no owner, definition, source text or Python attribute payload.
Only this reader registry can interpret them; no host getter is delegated.
"""
from decimal import Decimal
from .configuration_modules import _DIRECT_COMMON_MODULE_METADATA_ABI
from .experimental_naked_boundaries import BoundaryViolation
from .values import to_string

ROOT_NAMES=('metadata','метаданные')
COLLECTION_NAMES=('commonmodules','общиемодули')
_FIELDS={alias:field for field,aliases in (
    ('name',('name','имя')),
    ('global_module',('global','глобальный')),
    ('client',('clientmanagedapplication','клиентуправляемоеприложение')),
    ('server',('server','сервер')),
    ('server_call',('servercall','вызовсервера')),
) for alias in aliases}
_EMPTY=('synonym','синоним','comment','комментарий')
_FALSE=('privileged','привилегированный')
SCALAR_FIELDS=tuple(_FIELDS)+_EMPTY+_FALSE
COUNT=('count','количество')
FIND=('find','найти')
GET=('get','получить')
FULLNAME=('fullname','полноеимя')
_METHODS=COUNT+FIND+GET+('indexof','индекс','contains','содержит')
CommonModuleDefinition,_GETATTRIBUTE,_STORAGE=_DIRECT_COMMON_MODULE_METADATA_ABI


class _Reader:
    __slots__=()


_TOKEN_TYPE=_Reader


def is_reader(value):return type(value) is _TOKEN_TYPE


def validate_definition(definition):
    if type(definition) is not CommonModuleDefinition:raise BoundaryViolation('foreign common-module definition')
    if (vars(CommonModuleDefinition).get('__getattribute__') is not _GETATTRIBUTE
            or any(vars(CommonModuleDefinition).get(name) is not descriptor for name,descriptor in _STORAGE)):
        raise BoundaryViolation('common-module metadata ABI changed')
    fields=tuple(descriptor.__get__(definition,CommonModuleDefinition) for _,descriptor in _STORAGE)
    if type(fields[0]) is not str or any(type(value) is not bool for value in fields[1:5]) or type(fields[5]) is not str:
        raise BoundaryViolation('invalid common-module metadata')
    return fields


class Readers:
    def __init__(self,scope):
        self.scope=scope
        self.definitions=tuple(scope.configuration.common_modules)
        self.snapshots=tuple(validate_definition(d) for d in self.definitions)
        self.issued={};self.cache={}

    def check(self,context):
        context._check()
        if context._command_scope is not self.scope:raise BoundaryViolation('foreign metadata scope')
        for definition,snapshot in zip(self.definitions,self.snapshots):
            if validate_definition(definition)!=snapshot:raise BoundaryViolation('common-module metadata changed')

    def issue(self,kind,index=None):
        key=(kind,index)
        if key not in self.cache:
            token=object.__new__(_TOKEN_TYPE);self.cache[key]=token;self.issued[id(token)]=(token,kind,index)
        return self.cache[key]

    def root(self,context):
        self.check(context);return self.issue('root')

    def record(self,context,value):
        self.check(context)
        record=self.issued.get(id(value))
        if not is_reader(value) or record is None or record[0] is not value:
            raise BoundaryViolation('unissued or stale metadata reader')
        return record[1:]

    def find(self,name):
        if type(name) is not str and type(name) is not Decimal:
            raise TypeError('metadata name requires String or Number')
        key=to_string(name).casefold()
        for index,snapshot in enumerate(self.snapshots):
            if snapshot[0].casefold()==key:return self.issue('item',index)
        return None

    def find_reader(self,name):
        result=self.find(name)
        return self.issue('missing') if result is None else result

    def at(self,index):
        if type(index) is str:
            result=self.find(index)
            if result is None:raise ValueError('metadata name not found')
            return result
        if type(index) is not Decimal or not index.is_finite() or index!=index.to_integral_value():
            raise TypeError('metadata index requires integer Number')
        if index<0 or index>=len(self.snapshots):raise IndexError('metadata index out of bounds')
        return self.issue('item',int(index))

    def get(self,context,value,name):
        kind,index=self.record(context,value)
        if type(name) is not str:raise BoundaryViolation('invalid metadata member name')
        key=name.casefold()
        if kind=='root' and key in COLLECTION_NAMES:return self.issue('collection')
        if kind=='collection':
            if key in _METHODS:raise ValueError('metadata method-name property access is unsupported')
            result=self.find(key)
            if result is not None:return result
        if kind=='item':
            if key in _FIELDS:return self.snapshots[index][next(i for i,(field,_) in enumerate(_STORAGE) if field==_FIELDS[key])]
            if key in _EMPTY:return ''
            if key in _FALSE:return False
        raise ValueError('Поле объекта не обнаружено: '+name)

    def method(self,context,value,name):
        kind,index=self.record(context,value)
        if type(name) is not str:raise BoundaryViolation('invalid metadata method name')
        key=name.casefold()
        if kind=='collection' and key in COUNT:operation=lambda:Decimal(len(self.snapshots));count=0
        elif kind=='collection' and key in FIND:operation=self.find_reader;count=1
        elif kind=='collection' and key in GET:operation=lambda value:self.at(value) if type(value) is not str else self.numeric_only();count=1
        elif kind=='collection' and key=='__getitem__':operation=self.at;count=1
        elif kind=='item' and key in FULLNAME:operation=lambda:'ОбщийМодуль.'+self.snapshots[index][0];count=0
        else:raise ValueError('Метод объекта не обнаружен: '+name)
        def invoke(*arguments):
            self.record(context,value)
            if len(arguments)!=count:raise TypeError('metadata argument count mismatch')
            return operation(*arguments)
        invoke.returns_value=True
        return invoke

    @staticmethod
    def numeric_only():raise TypeError('metadata index requires integer Number')

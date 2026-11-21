"""Source-only ValueStorage capture and canonical bounded restoration."""
from types import MethodType
from decimal import Decimal
from yadinassi.formats.storage import value_storage as storage
from yadinassi.formats.storage.value_storage import (BSLValueStorage, Snapshot, _DIRECT_VALUE_STORAGE_ABI,
    _DIRECT_VALUE_STORAGE_FROM_SNAPSHOT, _DIRECT_VALUE_STORAGE_FIELDS,
    _DIRECT_VALUE_STORAGE_FUNCTIONS, _DIRECT_VALUE_STORAGE_CLASSES, _DIRECT_VALUE_STORAGE_DYNAMIC_FIELDS,
    _DIRECT_VALUE_STORAGE_RECEIVER_BINDINGS, _DIRECT_VALUE_STORAGE_RECEIVER_CLASSES,
    _DIRECT_VALUE_STORAGE_TABLE_FUNCTIONS)
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

CONSTRUCTOR_NAMES=('valuestorage','хранилищезначения')
_GET=BSLValueStorage.get
_CAPTURE=storage.capture
_RESTORE=storage.restore


def owns(value):return type(value) is BSLValueStorage


def check_factories():
    for name,expected in _DIRECT_VALUE_STORAGE_TABLE_FUNCTIONS:
        if vars(storage._direct_table_snapshot).get(name) is not expected:
            raise BoundaryViolation('source ValueStorage table codec hook changed')
    for module,name,expected in _DIRECT_VALUE_STORAGE_RECEIVER_BINDINGS:
        if vars(module).get(name) is not expected:
            raise BoundaryViolation('source ValueStorage capture receiver changed')
    for cls,fields,mro in _DIRECT_VALUE_STORAGE_RECEIVER_CLASSES:
        current=vars(cls)
        if (cls.__mro__ is not mro or len(current)!=len(fields)
                or any(current.get(name) is not expected for name,expected in fields)):
            raise BoundaryViolation('source ValueStorage capture receiver hooks changed')
    if any(getattr(storage,name) is not cls for name,cls in _DIRECT_VALUE_STORAGE_CLASSES):
        raise BoundaryViolation('source ValueStorage class changed')
    for cls,name,expected in _DIRECT_VALUE_STORAGE_ABI:
        if getattr(cls,name) is not expected:
            raise BoundaryViolation('source ValueStorage hooks changed')
    if vars(BSLValueStorage).get('_from_snapshot') is not _DIRECT_VALUE_STORAGE_FROM_SNAPSHOT:
        raise BoundaryViolation('source ValueStorage factory changed')
    for cls,fields in _DIRECT_VALUE_STORAGE_DYNAMIC_FIELDS:
        if any(name in vars(base) for base in cls.__mro__ for name in fields):
            raise BoundaryViolation('source ValueStorage bookkeeping descriptor changed')
    for cls,name,descriptor in _DIRECT_VALUE_STORAGE_FIELDS:
        if vars(cls).get(name) is not descriptor:
            raise BoundaryViolation('source ValueStorage field descriptor changed')
    for name,expected in _DIRECT_VALUE_STORAGE_FUNCTIONS:
        if getattr(storage,name) is not expected:
            raise BoundaryViolation('source ValueStorage codec hook changed')


def _snapshot(value):
    if type(value) is not Snapshot:raise BoundaryViolation('source ValueStorage snapshot changed')
    root=object.__getattribute__(value,'_root')
    pending=[(root,0)];nodes=0
    # Validate immutable fields before the canonical tag decoder can compare
    # them. Decoder remains responsible for all semantic budgets and codecs.
    while pending:
        item,depth=pending.pop();nodes+=1
        if nodes>100000 or depth>3*storage.MAX_DEPTH+10:
            raise ValueError('source ValueStorage snapshot envelope exceeded')
        kind=type(item)
        if kind is tuple:
            if len(item)>100000-nodes-len(pending):raise ValueError('source ValueStorage snapshot envelope exceeded')
            pending.extend((child,depth+1) for child in item)
        elif item is not None and kind not in (str,bytes,int,bool,Decimal):
            raise BoundaryViolation('source ValueStorage private snapshot field changed')
    return value


def check(boundary,value):
    boundary._check();check_factories()
    if not owns(value):raise BoundaryViolation('source ValueStorage receiver changed')
    if any(name in vars(value) for cls,name,_ in _DIRECT_VALUE_STORAGE_ABI if cls is BSLValueStorage):
        raise BoundaryViolation('source ValueStorage instance hooks changed')
    return _snapshot(object.__getattribute__(value,'_snapshot'))


def _bound(boundary,value,*,require_value=False,argument_count=None,allow_references=False,validate=None):
    original=check(boundary,value)
    original_root=object.__getattribute__(original,'_root')
    def admit(count=None):
        if (check(boundary,value) is not original
                or object.__getattribute__(original,'_root') is not original_root):
            raise BoundaryViolation('source ValueStorage retained snapshot changed')
        if validate is not None:validate()
        if count is not None and count!=0:raise TypeError('ValueStorage.Get takes no arguments')
    admit(argument_count)
    def call(*values):
        admit(len(values))
        root=object.__getattribute__(original,'_root')
        if (type(root) is not tuple or not root or type(root[0]) is not str
                or root[0] not in ('undefined','null','boolean','number','string')):
            raise ValueError('source ValueStorage.Get currently supports scalar snapshots only')
        try:return _RESTORE(original)
        finally:admit()
    if allow_references:call.requires_reference=lambda index:False
    return call


def get(boundary,value,name):
    check(boundary,value)
    if type(name) is not str or name.casefold() not in ('get','получить'):
        raise ValueError('source ValueStorage member unavailable')
    return HostFunction(name,_GET.__get__(value,BSLValueStorage))


def resolve(boundary,value,name,**contract):
    get(boundary,value,name)
    return _bound(boundary,value,**contract)


def captured(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    if type(function) is not HostFunction or type(function.function) is not MethodType:return None
    callback=function.function;value=callback.__self__
    if not owns(value):return None
    if callback.__func__ is not _GET:raise BoundaryViolation('source ValueStorage method changed')
    def validate():
        if function.function is not callback or function.returns_value is not True or function.reference_parameters:
            raise BoundaryViolation('source ValueStorage saved method changed')
    return _bound(boundary,value,require_value=require_value,argument_count=argument_count,
        allow_references=allow_references,validate=validate)


def resolve_constructor(boundary,name,*,require_value=False,argument_count=None,allow_references=False,**unused):
    key=name[4:] if name.startswith('new:') else name
    if key not in CONSTRUCTOR_NAMES:raise ValueError('source ValueStorage constructor unavailable')
    factory=boundary.vm.types.get(key)
    def validate():
        boundary._check();check_factories()
        if (type(factory) is not HostFunction or factory.function is not BSLValueStorage
                or any(boundary.vm.types.get(alias) is not factory for alias in CONSTRUCTOR_NAMES)):
            raise BoundaryViolation('source ValueStorage constructor binding changed')
    validate()
    if argument_count is not None and argument_count!=1:raise TypeError('source ValueStorage requires one argument')
    def create(*values):
        validate()
        if len(values)!=1:raise TypeError('source ValueStorage requires one argument')
        snapshot=_CAPTURE(values[0],_source_direct=True,_source_no_nested_storage=True)
        validate();_snapshot(snapshot)
        result=BSLValueStorage._from_snapshot(snapshot)
        check(boundary,result)
        return result
    if allow_references:create.requires_reference=lambda index:False
    return create

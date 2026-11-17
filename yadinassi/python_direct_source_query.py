"""Finite source Query bridge; detached result data carries no storage grant."""
from types import MethodType
from weakref import ReferenceType
from .experimental_naked_boundaries import BoundaryViolation
from .source_constant_queries import SourceConstantQuery, SourceQueryCall
from .source_constants_runtime import SourceConstants
from .queries import BSLQueryResult, BSLQueryResultSelection
from .query_packages import BSLTempTablesManager
from .value_tables import BSLValueTable, BSLValueTableRow, BSLValueTableColumn, BSLValueTableColumnCollection
from .type_descriptions import BSLTypeDescription
from .values import HostFunction, BSLArray, BSLFixedArray

CONSTRUCTOR_NAMES=('query','запрос','temptablesmanager','менеджервременныхтаблиц',
                   'typedescription','описаниетипов','valuetable','таблицазначений')
_TYPES=(SourceConstantQuery,BSLQueryResult,BSLQueryResultSelection,BSLValueTable,
        BSLValueTableRow,BSLValueTableColumn,BSLValueTableColumnCollection,
        BSLTempTablesManager,BSLTypeDescription,BSLArray,BSLFixedArray)
_ITERABLE=(BSLValueTable,BSLValueTableRow,BSLValueTableColumnCollection,BSLArray,BSLFixedArray)


def supports(value):return type(value) in _TYPES


def owns(boundary,value):
    boundary._check();kind=type(value)
    if kind is SourceConstantQuery:
        if (type(value._source_owner) is not SourceConstants
                or value._source_owner._application() is not boundary.app
                or value._catalogs is not boundary.app.interpreter._catalogs):
            raise BoundaryViolation('foreign source query')
    elif kind is BSLTempTablesManager:
        source=getattr(value,'_source_owner',None)
        if (value._owner is not None and value._owner is not boundary.app.interpreter._catalogs._metadata
                or source is not None and (type(source) is not ReferenceType or source() is not boundary.app)):
            raise BoundaryViolation('foreign source temporary tables manager')
    elif kind in (BSLValueTableRow,BSLValueTableColumn,BSLValueTableColumnCollection):
        if type(value.table) is not BSLValueTable:raise BoundaryViolation('invalid detached table parent')
    elif kind is BSLQueryResultSelection:
        if type(value._result) is not BSLQueryResult:raise BoundaryViolation('invalid detached query result parent')
    elif kind not in _TYPES:return False
    return True


def _require(boundary,value):
    if not owns(boundary,value):raise BoundaryViolation('unsupported source query receiver')


def _public(name):
    if type(name) is not str or name.startswith('_'):raise BoundaryViolation('private source query member')


def resolve_constructor(boundary,name,*,require_value=True,argument_count=None,allow_references=False,**unused):
    from .configuration_source_runtime import _SourceInterpreter, _DIRECT_SOURCE_ABI
    from .runtime import Interpreter
    boundary._check();key=name.casefold().removeprefix('new:')
    if key not in CONSTRUCTOR_NAMES:raise BoundaryViolation('unknown source query constructor')
    factory=boundary.vm.types.get(key)
    captured=dict(_DIRECT_SOURCE_ABI)
    def validate():
        boundary._check()
        if boundary.vm.types.get(key) is not factory or type(factory) is not HostFunction:
            raise BoundaryViolation('source query constructor registration changed')
        impl=factory.function
        if key in ('query','запрос'):
            expected=captured.get('_new_query',_SourceInterpreter._new_query)
            valid=type(impl) is MethodType and impl.__self__ is boundary.vm and impl.__func__ is expected
        elif key in ('temptablesmanager','менеджервременныхтаблиц'):
            expected=captured.get('_new_temp_tables_manager',Interpreter._new_temp_tables_manager)
            valid=type(impl) is MethodType and impl.__self__ is boundary.vm and impl.__func__ is expected
        else:valid=impl is (BSLTypeDescription if key in ('typedescription','описаниетипов') else BSLValueTable)
        if not valid:raise BoundaryViolation('source query constructor implementation changed')
    validate()
    minimum,maximum=((0,1) if key in ('query','запрос') else
                     (0,7) if key in ('typedescription','описаниетипов') else (0,0))
    if argument_count is not None and not minimum<=argument_count<=maximum:
        raise TypeError('invalid source query constructor argument count')
    def construct(*values):
        validate()
        try:
            if key in ('typedescription','описаниетипов'):
                expected=captured.get('_new_type_description',Interpreter._new_type_description)
                return expected(boundary.vm,*values)
            return factory(*values)
        finally:boundary._check()
    bound=boundary.resolve_callable(HostFunction(name,construct),require_value=require_value,allow_references=allow_references)
    if key in ('typedescription','описаниетипов'):
        def omissions(current,positions,count):
            validate()
            if count>7:raise TypeError('invalid TypeDescription argument count')
            return current,{index:None for index in positions}
        bound.prepare_omissions=omissions
    return bound


def get_member(boundary,value,name):
    _require(boundary,value);_public(name)
    try:return value.get_member(name)
    finally:boundary._check()


def resolve_set_member(boundary,value,name):
    _require(boundary,value);_public(name)
    if type(value) not in (SourceConstantQuery,BSLValueTableRow,BSLValueTableColumn):
        raise ValueError('source query data member is read-only')
    def write(new_value):
        _require(boundary,value)
        if type(value) is SourceConstantQuery and name.casefold() in ('temptablesmanager','менеджервременныхтаблиц') and new_value is not None:
            if type(new_value) is not BSLTempTablesManager:raise TypeError('TempTablesManager required')
            _require(boundary,new_value)
        try:return value.set_member(name,new_value)
        finally:boundary._check()
    return write


def resolve_member(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False):
    _require(boundary,value)
    if name in ('__getitem__','__setitem__','__iter__'):
        if name=='__iter__':
            if type(value) not in _ITERABLE:raise ValueError('source query data is not iterable')
            return lambda:iterate(boundary,value)
        if type(value) not in _ITERABLE:
            raise ValueError('source query data is not indexable')
        def index(*args):
            _require(boundary,value)
            try:
                if type(value) in (BSLArray,BSLFixedArray):
                    return value.get(*args) if name=='__getitem__' else value.set(*args)
                return value.get_index(*args) if name=='__getitem__' else value.set_index(*args)
            finally:boundary._check()
        return index
    _public(name)
    function=value.get_method(name)
    if type(function) is not HostFunction:raise BoundaryViolation('invalid source query method')
    marker=function.function
    if type(marker) is SourceQueryCall:
        if type(value) is not SourceConstantQuery or marker.query is not value or type(marker.batch) is not bool:
            raise BoundaryViolation('invalid source query operation')
        if argument_count is not None and argument_count!=0:raise TypeError('Query.Execute takes no arguments')
    def call(*values):
        _require(boundary,value)
        if function.function is not marker:raise BoundaryViolation('source query method changed')
        try:
            if type(marker) is SourceQueryCall:return marker.invoke(boundary.vm,list(values))
            return function(*values)
        finally:boundary._check()
    wrapper=HostFunction(function.name,call,returns_value=function.returns_value,reference_parameters=function.reference_parameters)
    return boundary.resolve_callable(wrapper,require_value=require_value,allow_references=allow_references)


def iterate(boundary,value):
    _require(boundary,value)
    if type(value) not in _ITERABLE:raise ValueError('source query data is not iterable')
    for item in value:
        _require(boundary,value);yield item
    _require(boundary,value)

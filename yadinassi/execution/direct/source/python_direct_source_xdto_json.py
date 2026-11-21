"""Source-owned string-only JSON handles and transactional XDTO codecs."""
from types import MethodType
from weakref import WeakKeyDictionary
from . import python_direct_source_xdto as shared
from . import python_direct_source_xdto_objects as objects
from . import python_direct_source_xdto_local as local
from yadinassi.formats.json import json_processing as reader_module
writer_module=reader_module
from decimal import Decimal
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_READER=reader_module.BSLJSONReader;_WRITER=writer_module.BSLJSONWriter
_WRITE_SETTINGS=writer_module.BSLJSONWriterSettings
CONSTRUCTOR_NAMES=('jsonreader','чтениеjson','jsonwriter','записьjson')
_READ_NAMES=CONSTRUCTOR_NAMES[:2];_WRITE_NAMES=CONSTRUCTOR_NAMES[2:]
_RECORDS=WeakKeyDictionary();_COUNTS=WeakKeyDictionary()
_WRITER_DICT=writer_module._DIRECT_SOURCE_JSON_DICT

class _Handles(dict):
    def sanitize(self):
        # Use the original descriptor, not user-controlled fields, hashing,
        # __setattr__, or stream.close, before releasing retained writers.
        for value in dict.__iter__(self):
            if type(value) is _WRITER:_WRITER_DICT.__set__(value,{'_file':None})
    def __del__(self):self.sanitize()

_READ=shared.io.BSLXDTOFactory.read_json;_WRITE=shared.io.BSLXDTOFactory.write_json
_FACTORY_METHODS={'readjson':(_READ,2,True),'прочитатьjson':(_READ,2,True),
                  'writejson':(_WRITE,2,False),'записатьjson':(_WRITE,2,False)}
_ENUMS=(reader_module.BSLJSONValueType,reader_module.BSLJSONLineBreak)


def release_application(app):
    records=_RECORDS.pop(app,None)
    if records is not None:records.sanitize()
def owns(value):return type(value) is _READER or type(value) is _WRITER


def _hooks():
    local._host_hooks();shared._hooks()
    for module,name,value in reader_module._DIRECT_SOURCE_JSON_BINDINGS:
        if vars(module).get(name) is not value:raise BoundaryViolation('source JSON codec binding changed')
    for cls,mro,entries in reader_module._DIRECT_SOURCE_JSON_CLASSES+reader_module._DIRECT_SOURCE_JSON_STDLIB_CLASSES:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(entries) or any(current.get(k) is not v for k,v in entries):
            raise BoundaryViolation('source JSON class hooks changed')
    for name,maximum in zip(('MAX_TEXT','MAX_DEPTH'),reader_module._DIRECT_SOURCE_JSON_LIMITS):
        value=vars(reader_module).get(name)
        if type(value) is not int or not 0<value<=maximum:raise BoundaryViolation('source JSON quota changed')
    token,scalars,collections,encode_types,handler_types,skip,json,os,linesep=reader_module._DIRECT_SOURCE_JSON_CONSTANTS
    if (reader_module.T is not token or reader_module._JSON_SCALARS is not scalars
            or reader_module._JSON_COLLECTIONS is not collections or reader_module._JSON_TYPES is not encode_types
            or reader_module._JSON_HANDLER_TYPES is not handler_types or reader_module._SKIP_JSON_PROPERTY is not skip
            or reader_module.json is not json or reader_module.os is not os or os.linesep is not linesep):
        raise BoundaryViolation('source JSON codec constants changed')
    for module,name,value in reader_module._DIRECT_SOURCE_JSON_STDLIB:
        if vars(module).get(name) is not value:raise BoundaryViolation('source JSON parser/encoder hook changed')


def _boundary(boundary):
    from yadinassi.execution.direct.python_direct_source import SourceBoundary
    if type(boundary) is not SourceBoundary:raise BoundaryViolation('source JSON requires ordinary source boundary')
    _hooks();boundary._check();return boundary.app


def _fields(value):return shared._field_keys(value)


def _state(value):
    """Finite identity snapshot: exact containers/settings, never user protocols."""
    pending=[value];seen=set();result=[];budget=1000000
    while pending:
        item=pending.pop();kind=type(item)
        if item is None or kind is str or kind is bool or kind is int or kind is Decimal:continue
        if any(kind is cls for cls in _ENUMS):continue
        if id(item) in seen:continue
        seen.add(id(item))
        if kind is dict:
            if len(item)+1>budget:raise BoundaryViolation('source JSON state budget exceeded')
            if any(type(k) is not str for k in item):raise BoundaryViolation('source JSON state keys changed')
            entries=tuple(item.items())
        elif kind is list or kind is tuple:
            if len(item)+1>budget:raise BoundaryViolation("source JSON state budget exceeded")
            entries=tuple(enumerate(item))
        elif any(kind is cls for cls in (_READER,_WRITER,_WRITE_SETTINGS)):
            entries=tuple(_fields(item).items())
        else:raise BoundaryViolation('source JSON state contains foreign value')
        budget-=len(entries)+1
        if budget<0:raise BoundaryViolation('source JSON state budget exceeded')
        result.append((item,entries));pending.extend(v for _,v in entries)
    fields=_fields(value)
    if type(value) is _READER:
        if set(fields)!={'_source','_tokens','_position','_current'}:
            raise BoundaryViolation('source JSON reader instance hooks changed')
    if type(value) is _WRITER:
        if set(fields)!={'_active','_file','_filename','_encoding','_stream_encoding','_stream_add_bom','_settings','_parts','_stack','_root','_size'}:
            raise BoundaryViolation('source JSON writer instance hooks changed')
        if fields['_file'] is not None or fields['_filename'] is not None or fields['_stream_encoding'] is not None or fields['_stream_add_bom'] is not False:
            raise BoundaryViolation('source JSON file/stream capability forbidden')
    return tuple(result)


def _same(snapshot):
    for item,entries in snapshot:
        kind=type(item)
        if kind is dict:
            if any(type(k) is not str for k in item):raise BoundaryViolation('source JSON state keys changed')
            current=item
        elif kind is list or kind is tuple:
            if len(item)!=len(entries):raise BoundaryViolation("source JSON state changed")
            current=dict(enumerate(item))
        else:current=_fields(item)
        if len(current)!=len(entries) or any(current.get(k) is not v for k,v in entries):
            raise BoundaryViolation('source JSON handle state changed')


def _check(boundary,value):
    app=_boundary(boundary)
    if not owns(value):raise BoundaryViolation('source JSON receiver changed')
    records=_RECORDS.get(app);record=None if records is None else records.get(value)
    if record is None:raise BoundaryViolation('source JSON handle not created by this application')
    _state(value);_same(record)
    return records


def _save(boundary,value):_RECORDS.setdefault(boundary.app,_Handles())[value]=_state(value)


def resolve_constructor(boundary,name,*,argument_count=None,require_value=False,allow_references=False,**unused):
    app=_boundary(boundary);key=name[4:] if name.startswith('new:') else name
    aliases=_READ_NAMES if key in _READ_NAMES else _WRITE_NAMES if key in _WRITE_NAMES else ()
    if not aliases:raise ValueError('source JSON constructor unavailable')
    kind=_READER if aliases is _READ_NAMES else _WRITER
    registry=boundary.vm.types
    if type(registry) is not dict or any(type(k) is not str for k in registry):raise BoundaryViolation('source JSON constructors changed')
    function=registry.get(key)
    def check(count=None):
        if _boundary(boundary) is not app:raise BoundaryViolation('source JSON constructor owner changed')
        registry=boundary.vm.types
        if type(registry) is not dict or any(type(k) is not str for k in registry):raise BoundaryViolation('source JSON constructors changed')
        if type(function) is not HostFunction:raise BoundaryViolation('source JSON constructor changed')
        _fields(function)
        if (function.function is not kind or function.returns_value is not True
                or type(function.reference_parameters) is not frozenset or function.reference_parameters
                or any(registry.get(alias) is not function for alias in aliases)):
            raise BoundaryViolation('source JSON constructor binding changed')
        if count is not None and count!=0:raise TypeError('source JSON constructor takes no arguments')
        if _COUNTS.get(app,0)>=32:raise ValueError('source JSON handle creation limit exceeded')
    check(argument_count)
    def create(*args):
        check(len(args));value=kind();_state(value);_COUNTS[app]=_COUNTS.get(app,0)+1
        _save(boundary,value);return value
    if allow_references:create.requires_reference=lambda index:False
    return create


def _method(value,name):
    key=name.casefold()
    if key in ('setstring','установитьстроку'):
        return (_READER.set_string,1,False) if type(value) is _READER else (_WRITER.set_string,0,False)
    if key in ('close','закрыть'):
        return (_READER.close,0,False) if type(value) is _READER else (_WRITER.close,0,True)
    raise ValueError('source JSON method not integrated')


def get(boundary,value,name):
    _check(boundary,value);method,_,returns=_method(value,name)
    return HostFunction(name,method.__get__(value,type(value)),returns_value=returns)


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False,validate=None):
    _check(boundary,value);method,count,returns=_method(value,name)
    def check(arity=None):
        _check(boundary,value)
        if validate is not None:validate()
        if require_value and not returns:raise ValueError('source JSON procedure cannot be used as value')
        if arity is not None and arity!=count:raise TypeError('source JSON invalid method arity')
    check(argument_count)
    def call(*args):
        check(len(args))
        if method is _READER.set_string:
            if type(args[0]) is not str:raise TypeError('source JSON SetString requires String')
            if len(args[0].encode('utf-8'))>min(reader_module.MAX_TEXT,shared.io.MAX_SCHEMA_BYTES,shared.xdto_schema.MAX_SCHEMA_BYTES):
                raise ValueError('source JSON input exceeds byte limit')
        if method is _WRITER.close:
            candidate=_WRITER();candidate.__dict__=dict(vars(value))
            result=method(candidate,*args)
            _hooks();_state(candidate);check()
            value.__dict__=dict(vars(candidate))
        else:result=method(value,*args)
        _save(boundary,value);return result
    if allow_references:call.requires_reference=lambda index:False
    return call


def captured(boundary,function,**contract):
    if type(function) is not HostFunction:return None
    local._host_hooks();_fields(function);callback=function.function
    if type(callback) is not MethodType or not owns(callback.__self__):return None
    value=callback.__self__
    _hooks()
    if callback.__func__ is type(value).set_string:name='setstring'
    elif callback.__func__ is type(value).close:name='close'
    else:raise BoundaryViolation('source JSON saved method unavailable')
    def validate():
        _fields(function);_,_,returns=_method(value,name)
        if function.function is not callback or function.returns_value is not returns or type(function.reference_parameters) is not frozenset or function.reference_parameters:
            raise BoundaryViolation('source JSON saved method changed')
    return resolve(boundary,value,name,validate=validate,**contract)


def factory_method(boundary,factory,name):
    if name.casefold() not in _FACTORY_METHODS:return None
    _boundary(boundary);_,current=shared._owner(boundary)
    if current is not factory:raise BoundaryViolation('source JSON factory changed')
    method,_,returns=_FACTORY_METHODS[name.casefold()]
    return HostFunction(name,method.__get__(factory,shared._FACTORY),returns_value=returns)


def captured_factory(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    if type(function) is not HostFunction:return None
    local._host_hooks();_fields(function);callback=function.function
    if type(callback) is not MethodType or type(callback.__self__) is not shared._FACTORY:return None
    operation=callback.__func__
    if operation is not _READ and operation is not _WRITE:return None
    factory=callback.__self__;count=2;returns=operation is _READ
    def check(arity=None):
        _boundary(boundary);owner,current=objects.check_inventory(boundary);_fields(function)
        if set(_fields(current))!={'_nodes','_units','_types','_roots','_packages','_source_packages_loader'}:
            raise BoundaryViolation('source JSON factory instance hooks changed')
        if (current is not factory or function.function is not callback or function.returns_value is not returns
                or type(function.reference_parameters) is not frozenset or function.reference_parameters):
            raise BoundaryViolation('source JSON saved factory method changed')
        if arity is not None and arity!=count:raise TypeError('source JSON factory method arity')
        if require_value and not returns:raise ValueError('source JSON procedure cannot be used as value')
        return owner
    check(argument_count)
    def call(*args):
        owner=check(len(args));handle=args[0];_check(boundary,handle)
        if operation is _WRITE:
            if type(handle) is not _WRITER or handle._active is not True or handle._root or handle._stack or handle._parts or handle._size!=0:
                raise ValueError('source JSON WriteJSON requires empty active string writer')
            value=args[1]
            if objects.owns(value):objects._check(boundary,value)
            elif type(value) is shared._VALUE:shared.get(boundary,value,'Value')
            else:raise BoundaryViolation('source JSON value is not admitted')
            candidate=_WRITER();candidate.set_string()
            _WRITE(factory,candidate,value)
            _hooks();snapshot=_state(candidate);check()
            handle.__dict__=dict(vars(candidate));_save(boundary,handle)
            return None
        if type(handle) is not _READER or type(handle._source) is not str or handle._tokens is not None or handle._position!=-1:
            raise ValueError('source JSON ReadJSON requires unread string reader')
        kind=args[1]
        if type(kind) is objects._TYPE:objects.admit_type(factory,kind)
        else:shared._kind(factory,kind)
        # Canonical allocation observes io aliases. Refuse a tighter downstream
        # cap before it could publish a result beyond the source boundary.
        if shared.io.MAX_NODES>shared.values.MAX_NODES or shared.io.MAX_UNITS>shared.values.MAX_UNITS or shared.io.MAX_DEPTH>shared.values.MAX_DEPTH:
            raise ValueError('source JSON allocation quota aliases differ')
        candidate=_READER();candidate.set_string(handle._source)
        previous=(factory._nodes,factory._units);old_seal=shared._SEALS[boundary.app]
        committed=False
        try:
            result=_READ(factory,candidate,kind,_source_string_only=True)
            _hooks();_state(candidate);objects._budget(factory)
            staged=objects.stage_xml_result(boundary,factory,result)
            new_seal=shared._seal(owner,boundary.app,factory)
            boundary._check();_same(_RECORDS[boundary.app][handle])
            handle.__dict__=dict(vars(candidate));_save(boundary,handle)
            shared._SEALS[boundary.app]=new_seal;objects.publish_xml_result(boundary,staged)
            committed=True;return result
        finally:
            if not committed:
                factory._nodes,factory._units=previous
                shared._SEALS[boundary.app]=old_seal
    if allow_references:call.requires_reference=lambda index:False
    return call

# Definition-time canonical global codecs are not the owned factory methods.
# Their generic HostFunction path would bypass the handle/graph publication.
_GLOBAL_CODECS=tuple(value for module,name,value in reader_module._DIRECT_SOURCE_JSON_BINDINGS
    if module is reader_module and name in ('read_json','write_json'))


def reject_global_callable(value):
    if any(value is codec for codec in _GLOBAL_CODECS):
        raise BoundaryViolation('source JSON global codec requires owned XDTO factory method')
    if type(value) is not HostFunction:return
    local._host_hooks();_fields(value)
    if any(value.function is codec for codec in _GLOBAL_CODECS):
        raise BoundaryViolation('source JSON global codec requires owned XDTO factory method')


def guard_global_callable(boundary,value,bound):
    from functools import wraps
    reject_global_callable(value)
    @wraps(bound)
    def invoke(*args):
        boundary._check();reject_global_callable(value)
        return bound(*args)
    return invoke

"""Finite source TextDocument operations and binary Size, no generic object grant."""
from types import MethodType
from . import text_documents as text, file_io
from .text_documents import BSLTextDocument, _DIRECT_TEXT_DOCUMENT_ABI, _DIRECT_TEXT_HELPERS
from .file_io import BSLBinaryData, _DIRECT_SOURCE_BINARY_ABI, _DIRECT_SOURCE_BINARY_FROM_BYTES
from .experimental_naked_boundaries import BoundaryViolation
from .values import HostFunction

CONSTRUCTOR_NAMES=('textdocument','текстовыйдокумент')
_SPECS=(
    ('get_text',0,0,True,('gettext','получитьтекст')),
    ('line_count',0,0,True,('linecount','количествострок')),
    ('get_line',1,1,True,('getline','получитьстроку')),
    ('set_text',1,1,False,('settext','установитьтекст')),
    ('add_line',1,1,False,('addline','добавитьстроку')),
    ('insert_line',2,2,False,('insertline','вставитьстроку')),
    ('replace_line',2,2,False,('replaceline','заменитьстроку')),
    ('delete_line',1,1,False,('deleteline','удалитьстроку')),
    ('clear',0,0,False,('clear','очистить')),
    ('read',1,3,False,('read','прочитать')),
    ('write',1,3,False,('write','записать')),
)
_METHODS={alias:spec[:4] for spec in _SPECS for alias in spec[4]}
_TEXT_IMPL=dict(_DIRECT_TEXT_DOCUMENT_ABI)
_BINARY_IMPL=dict(_DIRECT_SOURCE_BINARY_ABI)


def owns(value):return type(value) in (BSLTextDocument,BSLBinaryData)


def check_factories():
    if text.BSLTextDocument is not BSLTextDocument or file_io.BSLBinaryData is not BSLBinaryData:
        raise BoundaryViolation('source resource class binding changed')
    for cls,abi in ((BSLTextDocument,_DIRECT_TEXT_DOCUMENT_ABI),(BSLBinaryData,_DIRECT_SOURCE_BINARY_ABI)):
        if any(getattr(cls,name) is not expected for name,expected in abi):
            raise BoundaryViolation('source resource hooks changed')
    for cls,fields in ((BSLTextDocument,('_text','_spans','_units')),(BSLBinaryData,('_data',))):
        if any(any(name in vars(base) for base in cls.__mro__) for name in fields):
            raise BoundaryViolation('source resource field descriptors changed')
    if vars(BSLBinaryData).get('from_bytes') is not _DIRECT_SOURCE_BINARY_FROM_BYTES:
        raise BoundaryViolation('source binary factory changed')
    if any(getattr(text,name) is not expected for name,expected in _DIRECT_TEXT_HELPERS):
        raise BoundaryViolation('source text helpers changed')


def check(boundary,value):
    boundary._check();check_factories()
    if type(value) is BSLTextDocument:
        if any(name in vars(value) for name,_ in _DIRECT_TEXT_DOCUMENT_ABI):
            raise BoundaryViolation('source text instance hooks changed')
        raw=value._text;spans=value._spans;units=value._units
        if type(raw) is not str or type(spans) is not list or type(units) is not int:
            raise BoundaryViolation('source text fields changed')
        if len(spans)>text._MAX_LINES or any(type(span) is not tuple or len(span)!=3
                or any(type(i) is not int for i in span) for span in spans):
            raise BoundaryViolation('source text spans changed')
        text._text(raw)
        if units!=text._units(raw) or spans!=text._spans(raw):
            raise BoundaryViolation('source text invariants changed')
    elif type(value) is BSLBinaryData:
        if any(name in vars(value) for name,_ in _DIRECT_SOURCE_BINARY_ABI):
            raise BoundaryViolation('source binary instance hooks changed')
        if type(value._data) is not bytes or len(value._data)>file_io.MAX_BYTES:
            raise BoundaryViolation('source binary data changed')
    else:raise BoundaryViolation('source resource receiver is not integrated')


def _spec(value,name):
    if type(name) is not str:raise TypeError('resource member requires String')
    if type(value) is BSLTextDocument:
        spec=_METHODS.get(name.casefold())
        if spec is not None:return spec
    elif type(value) is BSLBinaryData and name.casefold() in ('size','размер'):
        return ('size',0,0,True)
    raise ValueError('source resource member is not integrated: '+name)


def _bound(boundary,value,spec,*,require_value=False,argument_count=None,allow_references=False,validate=None):
    method,minimum,maximum,returns=spec
    implementation=(_TEXT_IMPL if type(value) is BSLTextDocument else _BINARY_IMPL)[method]
    def admit(count=None):
        check(boundary,value)
        if validate is not None:validate()
        if require_value and not returns:raise TypeError('Процедура не возвращает значение: '+method)
        if count is not None and not minimum<=count<=maximum:raise TypeError('resource method argument count')
    admit(argument_count)
    def call(*values):
        admit(len(values))
        try:return implementation(value,*values)
        finally:admit()
    if allow_references:call.requires_reference=lambda index:False
    return call


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False):
    check(boundary,value)
    return _bound(boundary,value,_spec(value,name),require_value=require_value,
        argument_count=argument_count,allow_references=allow_references)


def get(boundary,value,name):
    check(boundary,value);method,minimum,maximum,returns=_spec(value,name)
    implementation=(_TEXT_IMPL if type(value) is BSLTextDocument else _BINARY_IMPL)[method]
    return HostFunction(name,implementation.__get__(value,type(value)),returns_value=returns)


def captured(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    if type(function) is not HostFunction or type(function.function) is not MethodType:return None
    callback=function.function;value=callback.__self__
    if not owns(value):return None
    specs=_SPECS if type(value) is BSLTextDocument else (('size',0,0,True,('size',)),)
    impls=_TEXT_IMPL if type(value) is BSLTextDocument else _BINARY_IMPL
    spec=next((entry[:4] for entry in specs if callback.__func__ is impls[entry[0]]),None)
    if spec is None:raise BoundaryViolation('source resource saved method not integrated')
    def validate():
        if (function.function is not callback or function.returns_value is not spec[3]
                or function.reference_parameters):
            raise BoundaryViolation('source resource saved method changed')
    return _bound(boundary,value,spec,require_value=require_value,argument_count=argument_count,
        allow_references=allow_references,validate=validate)


def resolve_constructor(boundary,name,*,require_value=False,argument_count=None,allow_references=False,**unused):
    key=name[4:] if name.startswith('new:') else name
    if key not in CONSTRUCTOR_NAMES:raise ValueError('source resource constructor unavailable')
    factory=boundary.vm.types.get(key)
    def validate():
        boundary._check();check_factories()
        if (type(factory) is not HostFunction or factory.function is not BSLTextDocument
                or any(boundary.vm.types.get(alias) is not factory for alias in CONSTRUCTOR_NAMES)):
            raise BoundaryViolation('source text constructor binding changed')
    validate()
    if argument_count is not None and argument_count!=0:raise TypeError('TextDocument constructor takes no arguments')
    def create(*values):
        validate()
        if values:raise TypeError('TextDocument constructor takes no arguments')
        result=BSLTextDocument();check(boundary,result);return result
    if allow_references:create.requires_reference=lambda index:False
    return create

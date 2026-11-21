"""Finite, family-owned UserMessage protocol; no reflective host admission."""
from types import MethodType
from yadinassi.application.user_messages import BSLUserMessage, UserMessageContext
from yadinassi.types.values import HostFunction
from yadinassi.runtime import Interpreter
from yadinassi import runtime as _runtime
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.db.catalog.catalogs import BSLCatalogObject
from yadinassi.db.catalog.catalog_types import BSLCatalogReference

NAMES=('usermessage','сообщениепользователю')
CONSTRUCTOR_SERVICES=('new:usermessage','new:сообщениепользователю')
_INIT=BSLUserMessage.__init__
_PUBLISH=UserMessageContext.publish
_RESOLVE=UserMessageContext.resolve
_FACTORY=Interpreter._new_user_message
_GET=BSLUserMessage.get_member
_SET=BSLUserMessage.set_member
_METHODS={'message':BSLUserMessage.message,'сообщить':BSLUserMessage.message,
          'setdata':BSLUserMessage.set_data,'установитьданные':BSLUserMessage.set_data}
_PROPERTIES=frozenset(('text','текст','field','поле','datapath','путькданным',
                       'datakey','ключданных','targetid','идентификаторназначения'))
def owner(context,value):
    """Only the actual owner witness, not a scan of unrelated class metadata."""
    if type(value) is not BSLUserMessage:raise BoundaryViolation('foreign UserMessage receiver')
    host=context.vm.user_messages
    if type(host) is not UserMessageContext or vars(value).get('_context') is not host:
        raise BoundaryViolation('foreign UserMessage owner')
    return host


def method_owner(context,value,method):
    host=owner(context,value)
    name='message' if method is _METHODS['message'] else 'set_data'
    delivery='publish' if name=='message' else 'resolve'
    expected=_PUBLISH if name=='message' else _RESOLVE
    if (vars(BSLUserMessage).get(name) is not method or name in vars(value)
            or vars(UserMessageContext).get(delivery) is not expected or delivery in vars(host)):
        raise BoundaryViolation('UserMessage handler changed')
    return host


def constructor(context,name,**kwargs):
    if context._verify_context:context._check()
    key=name.casefold().split(':',1)[1]
    factory=context.vm.types.get(key)
    def valid():
        if vars(_runtime).get("BSLUserMessage") is not BSLUserMessage or vars(BSLUserMessage).get("__init__") is not _INIT:
            raise BoundaryViolation("UserMessage constructor implementation changed")
        if (type(factory) is not HostFunction or context.vm.types.get(key) is not factory
                or type(factory.function) is not MethodType
                or factory.function.__func__ is not _FACTORY
                or factory.function.__self__ is not context.vm
                or type(factory.reference_parameters) is not frozenset or factory.reference_parameters
                or factory.returns_value is not True):
            raise BoundaryViolation('UserMessage constructor registration changed')
    valid()
    def invoke(*args):
        context._before('call_value',key);valid()
        if args:raise TypeError('UserMessage constructor requires no arguments')
        try:
            result=_FACTORY(context.vm);owner(context,result);return result
        finally:
            if context._verify_context:context._check()
    return invoke


def get(context,value,name):
    key=name.casefold()
    context._before("get_member",key);owner(context,value)
    if key in _METHODS:return HostFunction(name,_METHODS[key].__get__(value,BSLUserMessage),returns_value=False)
    if key not in _PROPERTIES:raise ValueError('Свойство не найдено: '+name)
    try:return _GET(value,name)
    finally:
        if context._verify_context:context._check()


def setter(context,value,name):
    if context._verify_context:context._check()
    owner(context,value);key=name.casefold()
    if key not in _PROPERTIES:raise ValueError('Свойство не найдено: '+name)
    def write(new):
        context._before('set_member',key);owner(context,value)
        if key in ('datakey','ключданных') and type(new) is BSLCatalogReference:
            if context.vm.database_context is None:raise BoundaryViolation('UserMessage data key requires owned database')
            if not hasattr(context,'_catalog_owner'):raise BoundaryViolation('UserMessage catalog binding is not connected in this scope')
            context._catalog_owner(new)
        try:_SET(value,name,new)
        finally:
            if context._verify_context:context._check()
    return write


def resolve(context,value,name,*,require_value=False,omitted=(),operation='call_member',wrapper=None):
    if context._verify_context:context._check()
    owner(context,value);key=name.casefold();method=_METHODS.get(key)
    if method is None:raise ValueError('Метод не найден: '+name)
    if require_value:raise TypeError('Процедура не возвращает значение: '+name)
    if omitted:raise TypeError('UserMessage method argument omission is unsupported')
    delivers=method is _METHODS['message']
    def invoke(*args):
        context._before(operation,key);method_owner(context,value,method)
        if wrapper is not None and (type(wrapper.function) is not MethodType or wrapper.function.__self__ is not value
                or wrapper.function.__func__ is not method or wrapper.returns_value is not False
                or type(wrapper.reference_parameters) is not frozenset or wrapper.reference_parameters):
            raise BoundaryViolation('UserMessage captured method changed')
        count=0 if delivers else 1
        if len(args)!=count:raise TypeError('UserMessage method argument count')
        if count and type(args[0]) is BSLCatalogObject:
            if context.vm.database_context is None:raise BoundaryViolation('UserMessage data requires owned database')
            if not hasattr(context,'_catalog_owner'):raise BoundaryViolation('UserMessage catalog binding is not connected in this scope')
            context._catalog_owner(args[0])
        # Delivery calls an embedding-supplied sink/output even in plain mode.
        if delivers and not context._verify_context:context._check_effect()
        try:return method(value,*args)
        finally:
            if delivers or context._verify_context:context._check_effect()
    return invoke


def captured(context,value,**kwargs):
    if (type(value) is not HostFunction or type(value.function) is not MethodType
            or type(value.function.__self__) is not BSLUserMessage):return None
    receiver=value.function.__self__;name=value.name
    if type(name) is not str or _METHODS.get(name.casefold()) is not value.function.__func__:
        raise BoundaryViolation('UserMessage captured method changed')
    return resolve(context,receiver,name,require_value=kwargs.get('require_value',False),operation=kwargs.get('operation','call_value'),wrapper=value)

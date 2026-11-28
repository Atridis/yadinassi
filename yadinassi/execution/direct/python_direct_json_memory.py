"""Ordinary string JSON methods; resources and named callbacks stay separate."""

from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.formats.json.json_processing import (
    BSLJSONReader, BSLJSONWriter, JSON_LINE_BREAKS, BSLJSONLineBreak,
    _DIRECT_JSON_READ, _DIRECT_SOURCE_JSON_CLASSES, _DIRECT_SOURCE_JSON_DICT,
)


def _methods(cls, rows):
    return {name: (vars(cls)[method], returns)
            for method, returns, names in rows for name in names}


_READER = _methods(BSLJSONReader, (
    ('set_string', False, ('setstring', 'установитьстроку')),
    ('read', True, ('read', 'прочитать')),
    ('skip', True, ('skip', 'пропустить')),
    ('close', False, ('close', 'закрыть')),
))
_WRITER = _methods(BSLJSONWriter, (
    ('set_string', False, ('setstring', 'установитьстроку')),
    ('close', True, ('close', 'закрыть')),
    ('write_property_name', False, ('writepropertyname', 'записатьимясвойства')),
    ('write_start_object', False, ('writestartobject', 'записатьначалообъекта')),
    ('write_end_object', False, ('writeendobject', 'записатьконецобъекта')),
    ('write_start_array', False, ('writestartarray', 'записатьначаломассива')),
    ('write_end_array', False, ('writeendarray', 'записатьконецмассива')),
    ('write_value', False, ('writevalue', 'записатьзначение')),
))
_SINK_ACTIONS = (BSLJSONWriter.set_string, BSLJSONWriter.close)
_LINE_BREAKS = {name.casefold(): value for value in BSLJSONLineBreak for name in value.value}
_CURRENT = BSLJSONReader.get_member
_READER_PROPERTIES = ('currentvaluetype', 'типтекущегозначения', 'currentvalue', 'текущеезначение')
_GET_FIELDS = _DIRECT_SOURCE_JSON_DICT.__get__
_NOT_MEMORY = object()
_READ_CLASS, _READ, _READ_CODE, _READ_MRO, _READ_FIELDS, _READ_SEAL = _DIRECT_JSON_READ


def active(context):
    if context._verify_context or context.policy is not None or getattr(context, '_server_side', False):
        return False
    from yadinassi.runtime import Interpreter
    vm = context.vm
    return (type(vm) is Interpreter and vm.database_context is None
            and vm._configuration_runtime is None and vm._has_module_context
            and vm.execution_context == 'client')


def verify_metadata(value):
    """Keep the pre-argument function/procedure metadata check for JSON."""
    cls = type(value)
    for base, mro, entries in _DIRECT_SOURCE_JSON_CLASSES:
        if not any(base is ancestor for ancestor in cls.__mro__):
            continue
        current = vars(base)
        if (base.__mro__ is not mro or len(current) != len(entries)
                or any(current.get(key) is not expected for key, expected in entries)):
            raise BoundaryViolation('JSON method metadata ABI changed')
    fields = _GET_FIELDS(value, cls)
    if (any(type(key) is not str for key in fields)
            or any(key in vars(base) for key in fields for base in cls.__mro__)):
        raise BoundaryViolation('JSON method instance metadata changed')


def _verify_read(value):
    if _READ_CLASS.__mro__ is not _READ_MRO or _READ.__code__ is not _READ_CODE:
        raise BoundaryViolation('JSON method metadata ABI changed')
    for namespace, size, entries in _READ_SEAL:
        if len(namespace) != size or any(namespace.get(key) is not expected for key, expected in entries):
            raise BoundaryViolation('JSON method metadata ABI changed')
    fields = _GET_FIELDS(value, _READ_CLASS)
    if len(fields) != len(_READ_FIELDS) or any(type(key) is not str or key not in _READ_FIELDS for key in fields):
        verify_metadata(value)


def get(context,value,name):
    """One in-memory property read, not database provenance."""
    if value is JSON_LINE_BREAKS:
        context._check_effect()
        key = name.casefold()
        if key not in _LINE_BREAKS:
            raise ValueError('Поле объекта не обнаружено: '+name)
        return True, _LINE_BREAKS[key]
    if type(value) is BSLJSONReader and name.casefold() in _READER_PROPERTIES:
        context._check_effect()
        return True, _CURRENT(value,name)
    return False, None


def resolve(context,value,name,*,require_value=False,omitted=(),call_syntax=False):
    kind = type(value)
    if omitted or not active(context):
        return None
    if kind is BSLJSONWriter:
        fields = _GET_FIELDS(value, kind)
        if fields.get('_file', _NOT_MEMORY) is not None:
            return None
        methods = _WRITER
    else:
        methods = _READER
    method = methods.get(name.casefold())
    if method is None:
        return None
    function, returns = method
    if require_value:
        context._check_effect()
        if function is _READ:
            _verify_read(value)
        else:
            verify_metadata(value)
        if not returns:
            raise TypeError('Процедура не возвращает значение: '+name)

    # Canonical memory methods only. An actual effect during argument
    # evaluation cannot write to a closed activation.
    if function in _SINK_ACTIONS:
        def invoke(*args):
            context._check_effect()
            if _GET_FIELDS(value,kind).get('_file', _NOT_MEMORY) is not None:
                # An argument may have attached a stream after resolution.
                bound=context.resolve_json_resource(value,name,require_value,call_syntax)
                return bound(*args)
            return function(value,*args)
    elif function is _READ and require_value:
        def invoke(*args):
            context._check_effect()
            if _READ.__code__ is not _READ_CODE:
                raise BoundaryViolation('JSON method metadata ABI changed')
            return function(value,*args)
    else:
        def invoke(*args):
            context._check_effect()
            return function(value,*args)
    return invoke

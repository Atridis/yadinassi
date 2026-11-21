"""Synchronous JSON callbacks on the current or an explicitly imported direct module."""

from yadinassi.types.values import BSLObject, Reference
from yadinassi.formats.json.json_processing import (
    BSLJSONReader, BSLJSONWriter, encode_json_events, read_json_events, read_json,
    _DIRECT_SOURCE_JSON_DICT,
)
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_WRITE = BSLJSONWriter._write_encoded
_ACCESS = ('__getattribute__', '__getattr__', '__setattr__')
_READ_METHODS = ('read',)
_READ_FIELDS = ('_source', '_tokens', '_position', '_current')
_WRITE_METHODS = ('_write_encoded', '_append', '_prefix')
_WRITE_FIELDS = ('_active', '_parts', '_stack', '_root', '_size')


def _seal(cls, methods, data_fields):
    names = (*methods, *data_fields, *_ACCESS)
    codes = tuple((fn, fn.__code__) for name in methods for fn in (vars(cls)[name],))
    fields = tuple((vars(base), tuple((name, vars(base).get(name)) for name in names))
                   for base in (cls, BSLObject))
    return cls, cls.__mro__, (*methods, *_ACCESS), codes, fields


_READER = _seal(BSLJSONReader, _READ_METHODS, _READ_FIELDS)
_WRITER = _seal(BSLJSONWriter, _WRITE_METHODS, _WRITE_FIELDS)


def _receiver(value, info):
    cls, mro, reserved, methods, fields = info
    if type(value) is not cls:
        raise TypeError('JSON: ожидается канонический ЧтениеJSON или ЗаписьJSON')
    if (cls.__mro__ is not mro or any(fn.__code__ is not code for fn, code in methods)
            or any(namespace.get(name) is not expected
                   for namespace, pairs in fields for name, expected in pairs)):
        raise BoundaryViolation('canonical JSON handler receiver changed')
    state = _DIRECT_SOURCE_JSON_DICT.__get__(value, cls)
    if any(type(key) is not str for key in state) or any(name in state for name in reserved):
        raise BoundaryViolation('canonical JSON handler receiver changed')


def _drive(operation, callback):
    try:
        try:
            request = next(operation)
        except StopIteration as done:
            return done.value
        while True:
            result = callback(request)
            try:
                request = operation.send(result)
            except StopIteration as done:
                return done.value
    finally:
        operation.close()


def bind(context, key, service, original, implementation):
    is_read = implementation is read_json
    offset = 4 if is_read else 3

    def invoke(*values):
        handler = values[offset] if len(values) > offset else None
        target = values[offset + 1] if len(values) > offset + 1 else None
        if handler is None and target is None:
            return original(*values)
        context._before('call', key)
        context._check_effect()
        vm = context.vm
        from yadinassi.runtime import Interpreter, _Module
        from .python_direct_routines import RoutineModule, resolve
        if (type(vm) is not Interpreter or getattr(context, '_server_side', False)
                or vm.execution_context != 'client' or not vm._has_module_context
                or vm._configuration_runtime is not None or vm.database_context is not None
                or type(handler) is not str or not handler or target is None):
            raise TypeError('JSON: обработчик требует экспортной функции текущего модуля')
        name = handler.casefold()
        count = 3 if is_read else 4
        local = type(target) is _Module and target is vm._self_module
        if local:
            if target.interpreter is not vm:
                raise BoundaryViolation('canonical JSON handler module owner changed')
            registry = getattr(vm, '_direct_routine_modules', None)
            module = registry.get(name) if type(registry) is dict else None
            if type(module) is not RoutineModule or name not in module.local_function_exports:
                raise ValueError('JSON: обработчик не является экспортной функцией текущего модуля')
            _, minimum, maximum, references = module.signatures[name]
            if not minimum <= count <= maximum:
                raise TypeError('JSON: неверное число аргументов обработчика')
            routine = resolve(context, name, require_value=True, allow_references=True, argument_count=count)
            cancel_byref = 3 in references
        else:
            try:
                routine = context.resolve_callback_target(target, name, require_value=True,
                                                          argument_count=count, reusable=True)
            except (TypeError, ValueError) as error:
                raise ValueError('JSON: недопустимый обработчик: '+str(error)) from None
            cancel_byref = routine.requires_reference(3)
        extra = values[offset + 2] if len(values) > offset + 2 else None
        if not local and type(extra) is Reference:
            raise TypeError('JSON: дополнительные параметры обработчика должны быть значением')
        receiver = values[0]

        def check():
            context._check_effect()
            if (context._services.get(key) is not service or service.function is not implementation
                    or service.returns_value is not is_read or type(service.reference_parameters) is not frozenset
                    or service.reference_parameters):
                raise BoundaryViolation('canonical JSON handler binding changed')
            if local:
                if (vm._self_module is not target or vm._direct_routine_modules is not registry
                        or registry.get(name) is not module):
                    raise BoundaryViolation('canonical JSON handler binding changed')
            else:
                routine.check_binding()
            _receiver(receiver, _READER if is_read else _WRITER)

        def callback(request):
            check()
            try:
                if is_read:
                    return routine(request.property, request.value, extra)
                cancel = [False]
                ref = Reference(lambda: cancel[0], lambda value: cancel.__setitem__(0, value)) if cancel_byref else False
                return routine(request.property, request.value, extra, ref), cancel[0]
            finally:
                check()

        check()
        try:
            if is_read:
                properties, maximum = (tuple(values[7:]) + (None, None))[:2]
                return _drive(read_json_events(*values[:4], has_reviver=True,
                    reviver_properties=properties, maximum_nesting=maximum), callback)
            settings = values[2] if len(values) > 2 else None
            encoded = _drive(encode_json_events(values[1], settings, has_converter=True), callback)
            _WRITE(receiver, encoded)
        except PermissionError as error:
            raise BoundaryViolation(str(error)) from error
        finally:
            check()

    invoke.accepts_callback_module = True
    if hasattr(original, 'requires_reference'):
        invoke.requires_reference = original.requires_reference
    return invoke

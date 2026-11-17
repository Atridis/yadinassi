"""Bounded qualified source ServerCall: fresh contextual all-Val activation.

No reuse, defaults, copyback, async or NoContext admission. The origin seal is
scoped to the synchronous call, never an entry in the application registry.
"""
from contextvars import ContextVar
import xml.etree.ElementTree as ET

from .experimental_naked_boundaries import BoundaryViolation
from .values import Reference
from .python_direct_server import transfer, _LateNamedValue
from . import safe_mode, database_transactions

_ACTIVE = ContextVar('direct_source_server_activations', default=())


def check_activation(owner):
    """Validate an active fresh owner; return False for ordinary source owners."""
    for current, validate in reversed(_ACTIVE.get()):
        if current is owner:
            validate()
            return True
    if getattr(owner, '_direct_source_server_activation', False):
        raise BoundaryViolation('source ServerCall activation expired')
    return False


def resolve(parent, owner, routine, *, require_value=False,
            argument_count=None, allow_references=False):
    from .python_direct_source import check_owner, _preflight, invoke
    from .configuration_source_runtime import _SourceInterpreter
    from .configuration_xml import MD
    app = parent.app
    keys = tuple(key for key, child in app._instances.items() if child is owner)
    if (len(keys) != 1 or type(keys[0]) is not tuple or len(keys[0]) != 3
            or type(keys[0][0]) is not str or keys[0][1] != 'server'
            or keys[0][2] is not False):
        raise BoundaryViolation('direct source ServerCall requires a qualified common module')
    key = keys[0]
    definition = app.modules.get(key[0])
    if definition is None:
        raise BoundaryViolation('direct source ServerCall module is not current')
    metadata = app.files[definition.path]
    source_path = 'CommonModules/' + definition.name + '/Ext/Module.bsl'
    source = app.files[source_path]
    plan = _preflight(owner, routine)
    registry = owner.server_routines
    plans = owner._direct_source_plans
    bindings = owner._direct_source_host_bindings

    def host_bindings(current_owner, expected):
        if current_owner._direct_source_host_bindings is not expected:
            raise BoundaryViolation('source ServerCall host binding snapshot changed')
        for current, (original, entries) in zip((current_owner.functions, current_owner.types), expected):
            if current is not original or len(current) != len(entries):
                raise BoundaryViolation('modified source ServerCall host registrations are not integrated')
            for name, wrapper, function, spelling, references, returns_value in entries:
                if (current.get(name) is not wrapper or wrapper.function is not function
                        or wrapper.name is not spelling or wrapper.reference_parameters is not references
                        or wrapper.returns_value is not returns_value):
                    raise BoundaryViolation('modified source ServerCall host registrations are not integrated')

    def authority():
        check_owner(owner)
        host_bindings(owner, bindings)
        if (app.modules.get(key[0]) is not definition
                or app.files.get(definition.path) is not metadata
                or app.files.get(source_path) is not source
                or app._instances.get(key) is not owner
                or owner.server_routines is not registry
                or owner._direct_source_plans is not plans
                or registry.get(routine.name.casefold()) is not routine
                or _preflight(owner, routine) is not plan
                or not owner._self_module.ready or owner._logical_side != 'server'):
            raise BoundaryViolation('source ServerCall origin changed')
        if (routine.execution_context != 'server' or routine.is_async or routine.is_dual
                or not routine.module_context or not routine.exported
                or any(not p.by_value or p.default is not None for p in routine.parameters)
                or id(routine) in app._reuse_routines or owner.module_names
                or owner.variables):
            raise ValueError('direct source ServerCall supports contextual all-Val routines without defaults or reuse')

    def caller():
        parent._check()
        if parent.side != 'client' or parent.vm.execution_context != 'client':
            raise BoundaryViolation('source ServerCall requires the actual client caller')
        authority()
        selected = app.module(key[0], parent.vm)
        if selected is not owner._self_module:
            raise BoundaryViolation('source ServerCall module binding changed')
        properties = ET.fromstring(metadata)[0].find('{' + MD + '}Properties')
        flags = {element.tag.rsplit('}', 1)[-1]: element.text for element in properties}
        if (flags.get('ServerCall') != 'true' or flags.get('Server') != 'true'
                or flags.get('ClientManagedApplication') == 'true'
                or flags.get('ReturnValuesReuse', 'DontUse') != 'DontUse'):
            raise ValueError('direct source ServerCall requires a server-only DontUse module')
        safe_mode.require_transfer('cross-context or asynchronous calls')
        database_transactions.forbid_transfer(parent.vm._transaction_backend())

    caller()
    if require_value and not routine.is_function:
        raise TypeError('Процедура не возвращает значение: ' + routine.name)
    if argument_count is not None and argument_count != len(routine.parameters):
        raise TypeError('Неверное количество аргументов: ' + routine.name)

    def call(*arguments):
        caller()
        if len(arguments) != len(routine.parameters):
            raise TypeError('Неверное количество аргументов: ' + routine.name)
        values = []
        for value in arguments:
            if type(value) is _LateNamedValue:
                parent._check()
                value = value.reference.get()
                parent._check()
            values.append(value)
        caller()
        packet = transfer(values)
        caller()
        from .runtime import Interpreter
        from .configuration_source_runtime import _DIRECT_SOURCE_FACTORY_ABI
        if any(getattr(Interpreter, name) is not expected
               or (name != '__init__' and getattr(_SourceInterpreter, name) is not expected)
               for name, expected in _DIRECT_SOURCE_FACTORY_ABI):
            raise BoundaryViolation('source ServerCall base factory hooks changed')
        fresh = _SourceInterpreter(app, output=owner.output, encoding=owner.encoding,
            native_target=owner.native_target, compilation_profile=owner.compilation_profile,
            family_owner=app.interpreter)
        fresh._direct_source_server_activation = True
        fresh._logical_side = 'server'
        fresh._transaction_activation_allowed = False
        fresh._application_exports_enabled = owner._application_exports_enabled
        fresh.user_messages = owner.user_messages
        fresh.server_routines = registry.copy()
        fresh.routines = owner.routines.copy()
        fresh._direct_source_plans = plans.copy()
        fresh.module_names = set()
        fresh.variables = {}
        fresh._self_module.ready = True
        fresh_bindings = fresh._direct_source_host_bindings
        copied = tuple((mapping, tuple(mapping.items())) for mapping in
                       (fresh.routines, fresh.server_routines, fresh._direct_source_plans))
        token = None
        side_stack = fresh._context_stack
        module_stack = fresh._module_context_stack
        side_stack.append('server')
        module_stack.append(True)
        def active():
            authority()
            host_bindings(fresh, fresh_bindings)
            for current, (original, entries) in zip(
                    (fresh.routines, fresh.server_routines, fresh._direct_source_plans), copied):
                if current is not original or len(current) != len(entries):
                    raise BoundaryViolation('source ServerCall activation registry changed')
                if any(current.get(name) is not value for name, value in entries):
                    raise BoundaryViolation('source ServerCall activation declaration changed')
            if (fresh.application is not app or fresh._logical_side != 'server'
                    or fresh._transaction_activation_allowed is not False):
                raise BoundaryViolation('source ServerCall activation changed')
        try:
            token = _ACTIVE.set((*_ACTIVE.get(), (fresh, active)))
            with database_transactions.admission(False):
                result = invoke(fresh, routine, packet)
                active()
                outgoing = transfer([result])[0]
            return outgoing
        finally:
            if token is not None:
                _ACTIVE.reset(token)
            module_stack.pop()
            side_stack.pop()
            fresh.close()
            parent._check()

    def named(reference):
        caller()
        if type(reference) is not Reference:
            raise TypeError('named server value requires a source reference')
        return _LateNamedValue(reference)
    call.prepare_named_value = named
    if allow_references:
        call.requires_reference = lambda index: False
    return call

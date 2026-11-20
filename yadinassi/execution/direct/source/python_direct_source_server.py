"""Bounded source crossing: fresh contextual activation and named-slot copyback.

Immutable scalar-literal defaults for DontUse; scalar reuse without defaults.
Qualified named byref is DontUse-only and has no defaults. Session-owned
unqualified entries are zero-argument only. No async or NoContext. The origin seal is
scoped to the synchronous call, never an entry in the application registry.
"""
from contextvars import ContextVar
from decimal import Decimal
from yadinassi.configuration.source_instances import instance_keys
from yadinassi.syntax import ast
from yadinassi.execution.codegen.experimental_naked_collections import _OMITTED_REF, _Cell
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
import xml.etree.ElementTree as ET

from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import Reference
from yadinassi.execution.direct.python_direct_server import transfer, _LateNamedValue
from yadinassi.execution import safe_mode
from yadinassi.db import database_transactions

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


def resolve(parent, owner, routine, **contract):
    return _resolve(parent,owner,routine,session=False,**contract)


def resolve_session(parent,routine,**contract):
    """Actual-client host entry to its own declaration-only session owner."""
    from yadinassi.execution.direct.python_direct_source import SourceBoundary
    if type(parent) is not SourceBoundary:raise BoundaryViolation('source session crossing requires ordinary source boundary')
    return _resolve(parent,parent.vm,routine,session=True,**contract)


def _resolve(parent, owner, routine, *, session,require_value=False,
             argument_count=None, allow_references=False):
    from yadinassi.execution.direct.python_direct_source import check_owner, _preflight, invoke
    from yadinassi.configuration.configuration_source_runtime import _SourceInterpreter
    from yadinassi.configuration.configuration_xml import MD
    app = parent.app
    if type(app._reuse_routines) is not dict:
        raise BoundaryViolation('source ServerCall reuse registry changed')
    reuse_entry = app._reuse_routines.get(id(routine))
    if session:
        if (parent.vm is not app._session_owner or app._instances.get('<session>') is not owner):
            raise BoundaryViolation('source session crossing owner changed')
        key='<session>';definition=None;metadata=None
        source_path='Ext/SessionModule.bsl'
        source=app.files.get(source_path)
        if type(source) is not bytes:raise BoundaryViolation('source session module is unavailable')
    else:
        keys = instance_keys(app,owner)
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
    def session_maps():
        mappings=(owner.routines,owner.server_routines,owner._direct_source_plans)
        if any(type(mapping) is not dict for mapping in mappings):
            raise BoundaryViolation('source session crossing requires canonical registries')
        if any(type(name) is not str for mapping in mappings for name in mapping):
            raise BoundaryViolation('source session crossing registry names changed')
        return mappings
    if session:session_maps()
    plan = _preflight(owner, routine)
    registry = owner.server_routines
    plans = owner._direct_source_plans
    session_entries=tuple((mapping,tuple(mapping.items())) for mapping in session_maps()) if session else ()
    bindings = owner._direct_source_host_bindings
    default_table = plan._source_crossing_defaults
    defaults = default_table[routine.name.casefold()]
    references = frozenset(i for i,p in enumerate(routine.parameters) if not p.by_value)
    minimum = max((i + 1 for i, p in enumerate(routine.parameters)
                   if p.default is None), default=0)

    def default_values():
        if (plan._source_crossing_defaults is not default_table
                or default_table.get(routine.name.casefold()) is not defaults
                or len(defaults) != len(routine.parameters)):
            raise BoundaryViolation('source ServerCall default snapshot changed')
        for parameter, (saved_parameter, node, value) in zip(routine.parameters, defaults):
            if parameter is not saved_parameter or parameter.default is not node:
                raise BoundaryViolation('source ServerCall default binding changed')
            if node is not None:
                if type(node) is not ast.Literal or (value is not None and type(value) not in (str, bool, Decimal)):
                    raise ValueError('source ServerCall defaults require immutable scalar literals')
                if node.value is not value:
                    raise BoundaryViolation('source ServerCall default literal changed')


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
        if session:session_maps()
        # Validate exact AST/parameter types before reading mutable names,
        # lengths or defaults; those lookups must not invoke host callbacks.
        if _preflight(owner, routine) is not plan:
            raise BoundaryViolation('source ServerCall origin plan changed')
        default_values()
        host_bindings(owner, bindings)
        if session:
            for current,(original,entries) in zip(session_maps(),session_entries):
                if current is not original or len(current)!=len(entries) or any(current.get(name) is not value for name,value in entries):
                    raise BoundaryViolation('source session crossing declaration registry changed')
            if (parent.vm is not owner or app._session_owner is not owner
                    or routine.parameters or reuse_entry is not None):
                raise BoundaryViolation('source session crossing requires own zero-argument nonreusable routine')
        elif app.modules.get(key[0]) is not definition or app.files.get(definition.path) is not metadata:
            raise BoundaryViolation('source ServerCall module metadata changed')
        if (app.files.get(source_path) is not source
                or app._instances.get(key) is not owner
                or owner.server_routines is not registry
                or owner._direct_source_plans is not plans
                or registry.get(routine.name.casefold()) is not routine
                or not owner._self_module.ready or owner._logical_side != 'server'):
            raise BoundaryViolation('source ServerCall origin changed')
        if (routine.execution_context != 'server' or routine.is_async or routine.is_dual
                or not routine.module_context or (not session and not routine.exported)
                or owner.module_names
                or owner.variables):
            raise ValueError('direct source ServerCall supports contextual routines')
        if any(not p.by_value and p.default is not None for p in routine.parameters):
            raise ValueError('source ServerCall byref defaults are not integrated')
        if type(app._reuse_routines) is not dict or app._reuse_routines.get(id(routine)) is not reuse_entry:
            raise BoundaryViolation('source ServerCall reuse authority changed')
        if reuse_entry is not None and (type(reuse_entry) is not tuple or len(reuse_entry)!=5
                or reuse_entry[0] is not routine or reuse_entry[1] is not owner or reuse_entry[4] is not True
                or not routine.is_function or references or any(p.default is not None for p in routine.parameters)):
            raise BoundaryViolation('source ServerCall reuse requires scalar functions without defaults')

    def caller():
        parent._check()
        if parent.side != 'client' or parent.vm.execution_context != 'client':
            raise BoundaryViolation('source ServerCall requires the actual client caller')
        authority()
        if not session:
            selected = app.module(key[0], parent.vm)
            if selected is not owner._self_module:
                raise BoundaryViolation('source ServerCall module binding changed')
            properties = ET.fromstring(metadata)[0].find('{' + MD + '}Properties')
            flags = {element.tag.rsplit('}', 1)[-1]: element.text for element in properties}
            if (flags.get('ServerCall') != 'true' or flags.get('Server') != 'true'
                    or flags.get('ClientManagedApplication') == 'true'
                    or flags.get('ReturnValuesReuse', 'DontUse') != ('DontUse' if reuse_entry is None else reuse_entry[3])):
                raise ValueError('direct source ServerCall requires the admitted server-only module')
        safe_mode.require_transfer('cross-context or asynchronous calls')
        database_transactions.forbid_transfer(parent.vm._transaction_backend())

    caller()
    if require_value and not routine.is_function:
        raise TypeError('Процедура не возвращает значение: ' + routine.name)
    if argument_count is not None and not minimum <= argument_count <= len(routine.parameters):
        raise TypeError('Неверное количество аргументов: ' + routine.name)

    from .python_direct_source_reuse import prepare as prepare_reuse
    reuse = prepare_reuse(parent,owner,routine,caller,server=True) if reuse_entry is not None else None

    def call(*arguments):
        caller()
        if not minimum <= len(arguments) <= len(routine.parameters):
            raise TypeError('Неверное количество аргументов: ' + routine.name)
        values = [];outputs=[]
        for index in range(len(routine.parameters)):
            value = arguments[index] if index < len(arguments) else _OMITTED_REF
            if value is _OMITTED_REF:
                _, node, value = defaults[index]
                if node is None:
                    raise TypeError('Неверное количество аргументов: ' + routine.name)
            if index in references:
                if type(value) is _ForwardReference:value=value.reference
                if type(value) is not Reference or getattr(value,'_direct_name_sink',False) is not True:
                    raise TypeError('Межконтекстные параметры без Знач пока требуют имя переменной')
                outputs.append((index,value))
                caller()
                value=value.get()
                caller()
            if type(value) is _LateNamedValue:
                parent._check()
                value = value.reference.get()
                parent._check()
            values.append(value)
        caller()
        packet = transfer(values)
        for index,_ in outputs:packet[index]=_Cell(packet[index])
        cells=tuple((index,packet[index]) for index,_ in outputs)
        caller()
        def execute_packet():
            from yadinassi.runtime import Interpreter
            from yadinassi.configuration.configuration_source_runtime import _DIRECT_SOURCE_FACTORY_ABI
            if any(getattr(Interpreter, name) is not expected
                   or (name != '__init__' and getattr(_SourceInterpreter, name) is not expected)
                   for name, expected in _DIRECT_SOURCE_FACTORY_ABI):
                raise BoundaryViolation('source ServerCall base factory hooks changed')
            fresh = _SourceInterpreter(app, output=owner.output, encoding=owner.encoding,
                native_target=owner.native_target, compilation_profile=owner.compilation_profile,
                family_owner=app.interpreter)
            fresh._direct_source_server_activation = True
            fresh._logical_side = 'server'
            fresh._direct_source_scalar_reuse = reuse_entry is not None
            fresh._transaction_activation_allowed = False
            fresh._application_exports_enabled = False if session else owner._application_exports_enabled
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
                    if any(type(cell) is not _Cell or packet[index] is not cell
                           for index,cell in cells):
                        raise BoundaryViolation('source ServerCall output cells changed')
                    outgoing = transfer([result]+[cell.value for _,cell in cells])
                return outgoing
            finally:
                if token is not None:
                    _ACTIVE.reset(token)
                module_stack.pop()
                side_stack.pop()
                fresh.close()
                parent._check()
        if reuse is not None:
            return reuse(packet,lambda:execute_packet()[0])
        outgoing=execute_packet()
        caller()
        # Complete packet and caller validate before any ordered copy-out.
        # Repeated names intentionally receive the rightmost independent value.
        for (_,reference),value in zip(outputs,outgoing[1:]):
            caller()
            reference.set(value)
            caller()
        return outgoing[0]

    def named(reference):
        caller()
        if type(reference) is not Reference:
            raise TypeError('named server value requires a source reference')
        return _LateNamedValue(reference)
    def omissions(current, positions, count):
        caller()
        if (not minimum <= count <= len(defaults)
                or any(i >= len(defaults) or defaults[i][1] is None for i in positions)):
            raise TypeError('Неверное количество аргументов: ' + routine.name)
        return current, {i: _OMITTED_REF for i in positions}
    def shapes(named):
        caller()
        if type(named) is not tuple or any(type(item) is not bool for item in named):
            raise BoundaryViolation('source ServerCall argument shapes changed')
        if any(index>=len(named) or not named[index] for index in references):
            raise TypeError('Межконтекстные параметры без Знач пока требуют имя переменной')
    call.prepare_argument_shapes = shapes
    call.prepare_omissions = omissions
    call.prepare_named_value = named
    if allow_references:
        call.requires_reference = lambda index: index in references
    return call

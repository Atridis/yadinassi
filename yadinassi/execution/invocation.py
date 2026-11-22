"""Opt-in scalar NoContext InvocationPort; transport is supplied by the host.

Only trusted host setup binds names/signatures to opaque endpoint numbers. Wire
requests contain values, never BSL, procedure names, paths or Python handles.
This is not form-state synchronization, native RPC or a network server.
"""
from dataclasses import dataclass
from decimal import localcontext
from threading import Lock

from yadinassi.runtime import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.lexer import Token
from yadinassi.syntax.parser import parse
from .codegen.native_targets import target_context
from .codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.ui.protocol import (UIError, MAX_COUNTER, bounded_text, decode_line,
                          decode_value, encode_line, encode_value)

PROTOCOL = 'yadinassi-invocation/0'
MAX_CALLS = 4096
MAX_ENDPOINTS = 64
MAX_ARGUMENTS = 32
_REASONS = frozenset(('invalid_request', 'sequence', 'request_limit', 'busy',
                     'unknown_endpoint', 'invalid_arguments', 'server_error',
                     'result_unavailable'))


class InvocationError(ValueError):
    """Finite host diagnostic; a failed call never promises database rollback."""


def _identifier(value):
    if type(value) is not str or not value.isidentifier() or len(value) > 128:
        raise ValueError('invalid invocation identifier')
    return value


@dataclass(frozen=True)
class InvocationBinding:
    """Trusted host contract. All parameters are required and passed by value."""
    name: str
    endpoint: int
    parameters: tuple
    is_function: bool = True

    def __post_init__(self):
        _identifier(self.name)
        if type(self.endpoint) is not int or not 1 <= self.endpoint <= MAX_ENDPOINTS:
            raise ValueError('invalid invocation endpoint')
        if (type(self.parameters) is not tuple or len(self.parameters) > MAX_ARGUMENTS
                or type(self.is_function) is not bool):
            raise ValueError('invalid invocation signature')
        names = [_identifier(value).casefold() for value in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError('duplicate invocation parameter')


def _encode_scalar(value):
    # Reuse the measured context-value admission, then the bounded exact scalar
    # codec. Collections and CatalogRef remain outside this first wire profile.
    Interpreter._copy_context_packet([value])
    return encode_value(value)


def _decode_scalar(value):
    result = decode_value(value)
    _encode_scalar(result)
    return result


@dataclass(frozen=True, slots=True)
class _FormInvocation:
    port: object
    binding: InvocationBinding


class InvocationPort:
    """One serialized, host-owned byte exchange. No automatic retry or reconnect.

    An interrupted/malformed response locks this port. The host must reconcile
    possible server effects before establishing a new port; there is no reset
    or replay API. Transport timeouts/child ownership belong to the host adapter.
    """
    def __init__(self, exchange):
        if not callable(exchange): raise TypeError('byte exchange required')
        self._exchange = exchange
        self._gate = Lock()
        self._counter = 0
        self.uncertain = False

    def bind(self, interpreter, binding):
        if type(interpreter) is not Interpreter or type(binding) is not InvocationBinding:
            raise TypeError('plain Interpreter and InvocationBinding required')
        key=binding.name.casefold()
        ports=vars(interpreter).setdefault('_direct_invocation_ports',{})
        if (key in ports or key in interpreter.routines or key in interpreter.server_routines
                or key in interpreter.functions or key in getattr(interpreter,'_direct_routine_modules',{})):
            raise ValueError('invocation name already bound')
        ports[key]=(self,binding)

    def bind_form(self, session, binding):
        """Bind a scalar client call before a trusted local form session opens.

        Only explicit arguments/results cross this port. Form composition and
        contextful handlers remain local; no shared form object is transported.
        """
        from yadinassi.forms.form_runtime import FormSession
        if type(session) is not FormSession or type(binding) is not InvocationBinding:
            raise TypeError('FormSession and InvocationBinding required')
        if not session._gate.acquire(blocking=False):
            raise ValueError('form invocation binding requires an idle session')
        try:
            if session.state != 'created' or session.closed or session._busy:
                raise ValueError('form invocation binding must precede open')
            key = binding.name.casefold()
            if key in session.reserved_names or key in session.form._static:
                raise ValueError('form invocation name already bound')
            self._bind(session.interpreter, binding, _form_transport=True)
            # Later server-side composition cannot shadow the trusted alias with
            # a dynamic attribute. No renderer input can install this binding.
            session.reserved_names.add(key)
        finally:
            session._gate.release()

    def _bind(self, interpreter, binding, *, _form_transport=False):
        key = binding.name.casefold()
        if key in interpreter.routines or key in interpreter.server_routines or key in interpreter.functions:
            raise ValueError('invocation name already bound')
        token = Token('IDENT', binding.name, 1, 1, '<invocation>')
        routine = ast.Routine(token, binding.name,
            [ast.Parameter(token, parameter, True) for parameter in binding.parameters],
            binding.is_function, False, [], execution_context='server', module_context=False)
        interpreter.server_routines[key] = routine
        if _form_transport:
            invoke = _FormInvocation(self, binding)
        else:
            # Source-owned form replication already supplies a caller boundary.
            def invoke(values):
                return self.invoke(binding, values, output=interpreter.output)
        interpreter._invocation_bindings[key] = (routine, invoke)

    def invoke(self, binding, values, *, output=lambda message: None, _check_reply=None):
        if not self._gate.acquire(blocking=False): raise InvocationError('busy')
        exchange_started = False
        try:
            if self.uncertain: raise InvocationError('outcome_unknown')
            if self._counter >= MAX_CALLS: raise InvocationError('request_limit')
            if type(binding) is not InvocationBinding or type(values) not in (list, tuple) or len(values) != len(binding.parameters):
                raise InvocationError('invalid_arguments')
            request_id = self._counter + 1
            try:
                raw = encode_line({'protocol': PROTOCOL, 'id': request_id,
                    'endpoint': binding.endpoint, 'arguments': [_encode_scalar(value) for value in values]})
            except (UIError, TypeError, ValueError):
                raise InvocationError('invalid_arguments') from None
            self._counter = request_id
            try:
                exchange_started = True
                raw_reply = self._exchange(raw)
                if _check_reply is not None:
                    _check_reply()
                response = decode_line(raw_reply)
                if (type(response) is not dict or response.get('protocol') != PROTOCOL
                        or type(response.get('id')) is not int or response['id'] != request_id
                        or response.get('status') not in ('ok', 'error')):
                    raise ValueError('invalid response')
                success = response['status'] == 'ok'
                if set(response) != {'protocol', 'id', 'status', 'messages', 'value' if success else 'reason'}:
                    raise ValueError('invalid response')
                messages = response['messages']
                if type(messages) is not list or len(messages) > 64:
                    raise ValueError('invalid messages')
                for message in messages: bounded_text(message, 1024)
                if success:
                    result = _decode_scalar(response['value'])
                    if not binding.is_function and result is not None:
                        raise ValueError('procedure returned value')
                elif type(response['reason']) is not str or response['reason'] not in _REASONS:
                    raise ValueError('invalid error')
            except Exception:
                self.uncertain = True
                raise InvocationError('outcome_unknown') from None
            # Apply a fully admitted response before dependent client BSL resumes.
            try:
                for message in messages: output(message)
            except Exception:
                self.uncertain = True
                raise InvocationError('outcome_unknown') from None
            if not success:
                if response['reason'] == 'result_unavailable': self.uncertain = True
                raise InvocationError(response['reason'])
            return result
        except BaseException as error:
            # Cancellation can escape both transport and output delivery after
            # server effects. Preserve it, but never reopen a replayable port.
            if exchange_started and not isinstance(error, Exception):
                self.uncertain = True
            raise
        finally:
            self._gate.release()


def resolve_direct_invocation(context,key,entry,*,require_value=False,argument_count=None):
    from yadinassi.types.values import Reference
    from .direct.python_direct_server import _LateNamedValue
    vm=context.vm
    if vm.execution_context!='client' or getattr(context,'_server_side',False):
        raise ValueError('Удалённый вызов доступен только из логического клиента')
    if type(entry) is not tuple or len(entry)!=2:
        raise BoundaryViolation('invalid invocation binding')
    port,binding=entry
    if type(port) is not InvocationPort or type(binding) is not InvocationBinding or binding.name.casefold()!=key:
        raise BoundaryViolation('invalid invocation binding')
    if require_value and not binding.is_function:
        raise TypeError('Процедура не возвращает значение: '+binding.name)
    if argument_count!=len(binding.parameters):
        raise TypeError('Неверное количество аргументов: '+binding.name)
    def check():
        context._check_effect()
        if (vm.execution_context!='client'
                or getattr(vm,'_direct_invocation_ports',{}).get(key) is not entry):
            raise BoundaryViolation('invocation binding changed')
    def invoke(*arguments):
        check()
        values=[]
        for argument in arguments:
            if type(argument) is _LateNamedValue:
                try:argument=argument.reference.get()
                finally:check()
            values.append(argument)
        output=vm.output
        def guarded_output(message):
            check()
            output(message)
            check()
        try:return port.invoke(binding,values,output=guarded_output,_check_reply=check)
        finally:check()
    def named(reference):
        if type(reference) is not Reference:
            raise TypeError('named invocation value requires a source reference')
        return _LateNamedValue(reference)
    invoke.requires_reference=lambda index:False
    invoke.prepare_named_value=named
    return invoke


class InvocationServer:
    """Precompiled server-only module behind a bounded scalar request/reply port.

    Source and database context are trusted host inputs, never wire inputs. Every
    dispatch uses a fresh NoContext activation. BSL errors retain preceding
    effects; only a finite diagnostic and explicit messages cross back.
    """
    def __init__(self, source, endpoints, *, database_context=None, interpreter_factory=None):
        if type(endpoints) is not dict or not 1 <= len(endpoints) <= MAX_ENDPOINTS:
            raise ValueError('invalid endpoint inventory')
        from yadinassi.forms.form_program import admitted_program
        program = admitted_program(source, side='nocontext', label='<invocation-server>',
                                   compilation_profile='standalone')
        if not program or any(not isinstance(node, ast.Routine) or
                node.execution_context != 'server' or node.module_context or node.is_async or node.is_dual
                for node in program):
            raise ValueError('server module requires NoContext routines only')
        self._messages = []
        factory = Interpreter if interpreter_factory is None else interpreter_factory
        self._interpreter = factory(self._message, database_context=database_context)
        if type(self._interpreter) is not Interpreter:
            raise TypeError("plain interpreter factory required")
        self._interpreter.execute_program(program)
        declarations = {routine.name.casefold():routine for routine in program}
        self._direct_modules = self._interpreter._direct_routine_modules.copy()
        self._routines = {}
        bindings = []
        for endpoint, name in endpoints.items():
            key = _identifier(name).casefold()
            routine = declarations.get(key)
            module = self._direct_modules.get(key)
            if (routine is None or module is None or key not in module.nocontext_names
                    or any(not p.by_value or p.default is not None for p in routine.parameters)):
                raise ValueError('endpoint requires explicit by-value parameters')
            binding = InvocationBinding(routine.name, endpoint,
                tuple(p.name for p in routine.parameters), routine.is_function)
            self._routines[endpoint] = routine
            bindings.append(binding)
        self.bindings = tuple(bindings)
        self._gate = Lock()
        self._last_id = 0
        self._requests = 0

    @classmethod
    def from_handlers(cls, endpoints, *, message_scope):
        """Trusted host callbacks over the same closed scalar wire and no-replay gate."""
        if type(endpoints) is not dict or not 1 <= len(endpoints) <= MAX_ENDPOINTS or not callable(message_scope):
            raise ValueError('invalid endpoint inventory')
        result = object.__new__(cls)
        result._callbacks = {}
        result._routines = {}
        for endpoint, pair in endpoints.items():
            binding, callback = pair
            if type(binding) is not InvocationBinding or binding.endpoint != endpoint or not callable(callback):
                raise ValueError('invalid trusted endpoint')
            result._callbacks[endpoint] = callback
            result._routines[endpoint] = binding
        result.bindings = tuple(result._routines.values())
        result._message_scope = message_scope
        result._messages = []
        result._gate = Lock()
        result._last_id = 0
        result._requests = 0
        return result

    def _message(self, message):
        bounded_text(message, 1024)
        if len(self._messages) >= 64: raise ValueError('message limit')
        self._messages.append(message)

    def _reply(self, request_id, *, value=None, reason=None):
        response = {'protocol': PROTOCOL, 'id': request_id,
                    'status': 'ok' if reason is None else 'error', 'messages': list(self._messages)}
        try:
            if reason is None: response['value'] = _encode_scalar(value)
            else: response['reason'] = reason
            return encode_line(response)
        except (UIError, TypeError, ValueError):
            return encode_line({'protocol': PROTOCOL, 'id': request_id, 'status': 'error',
                                'messages': [], 'reason': 'result_unavailable'})

    def _invoke_endpoint(self, routine, values):
        from yadinassi.runtime import _DIRECT_EXECUTION_SCOPE_ABI
        from .direct.python_direct import make_boundary
        from .direct.python_direct_server import ServerBoundary
        from .execution_policy import compiled_ast_policy, execution_backend_policy

        activation = self._interpreter._new_server_activation(module_context=False)
        activation._direct_routine_modules = self._direct_modules.copy()
        parent = make_boundary(activation)
        parent._verify_context = True
        context = ServerBoundary(parent, module_context=False)
        with _DIRECT_EXECUTION_SCOPE_ABI(activation):
            activation._context_stack.append('server')
            activation._module_context_stack.append(False)
            try:
                context.enter()
                try:
                    with (target_context(activation.native_target),
                          execution_backend_policy(activation.execution_backend),
                          compiled_ast_policy(activation.compiled_ast_contract),
                          localcontext() as decimal_context):
                        decimal_context.prec = 38
                        call = context.resolve_service(routine.name, require_value=routine.is_function,
                                                       argument_count=len(values))
                        return call(*values)
                finally:
                    try:
                        context._check()
                    finally:
                        context.leave()
            finally:
                activation._module_context_stack.pop()
                activation._context_stack.pop()
                activation._scheduler.active_context.state.pop(activation._diagnostic_owner, None)

    def exchange(self, raw):
        if not self._gate.acquire(blocking=False):
            return encode_line({'protocol': PROTOCOL, 'id': None, 'status': 'error',
                                'messages': [], 'reason': 'busy'})
        request_id = None
        self._messages = []
        try:
            try:
                request = decode_line(raw)
                if (type(request) is not dict or set(request) != {'protocol', 'id', 'endpoint', 'arguments'}
                        or request['protocol'] != PROTOCOL or type(request['id']) is not int
                        or not 1 <= request['id'] <= MAX_COUNTER or type(request['endpoint']) is not int
                        or type(request['arguments']) is not list or len(request['arguments']) > MAX_ARGUMENTS):
                    raise ValueError('invalid request')
            except (UIError, TypeError, ValueError):
                return self._reply(None, reason='invalid_request')
            request_id = request['id']
            if request_id <= self._last_id: return self._reply(request_id, reason='sequence')
            if self._requests >= MAX_CALLS: return self._reply(request_id, reason='request_limit')
            self._last_id = request_id
            self._requests += 1
            routine = self._routines.get(request['endpoint'])
            if routine is None: return self._reply(request_id, reason='unknown_endpoint')
            try:
                if len(request['arguments']) != len(routine.parameters): raise ValueError('arity')
                values = [_decode_scalar(value) for value in request['arguments']]
            except (UIError, TypeError, ValueError):
                return self._reply(request_id, reason='invalid_arguments')
            if hasattr(self, '_callbacks'):
                try:
                    with self._message_scope(self._message):
                        result = self._callbacks[request['endpoint']](values)
                    return self._reply(request_id, value=result)
                except Exception:
                    return self._reply(request_id, reason='server_error')
            try:
                result = self._invoke_endpoint(routine, values)
                return self._reply(request_id, value=result)
            except (Exception, BoundaryViolation):
                return self._reply(request_id, reason='server_error')
        finally:
            self._gate.release()

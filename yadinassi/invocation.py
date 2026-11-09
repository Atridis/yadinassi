"""Opt-in scalar NoContext InvocationPort; transport is supplied by the host.

Only trusted host setup binds names/signatures to opaque endpoint numbers. Wire
requests contain values, never BSL, procedure names, paths or Python handles.
This is not form-state synchronization, native RPC or a network server.
"""
from dataclasses import dataclass
from decimal import localcontext
from threading import Lock

from .runtime import Interpreter
from .syntax import ast
from .syntax.lexer import Token
from .syntax.parser import parse
from .native_targets import target_context
from .ui.protocol import (UIError, MAX_COUNTER, bounded_text, decode_line,
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
        key = binding.name.casefold()
        if key in interpreter.routines or key in interpreter.server_routines or key in interpreter.functions:
            raise ValueError('invocation name already bound')
        token = Token('IDENT', binding.name, 1, 1, '<invocation>')
        routine = ast.Routine(token, binding.name,
            [ast.Parameter(token, parameter, True) for parameter in binding.parameters],
            binding.is_function, False, [], execution_context='server', module_context=False)
        interpreter.server_routines[key] = routine
        interpreter._invocation_bindings[key] = (routine,
            lambda values: self.invoke(binding, values, output=interpreter.output))

    def invoke(self, binding, values, *, output=lambda message: None):
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
                response = decode_line(self._exchange(raw))
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


class InvocationServer:
    """Precompiled server-only module behind a bounded scalar request/reply port.

    Source and database context are trusted host inputs, never wire inputs. Every
    dispatch uses a fresh NoContext activation. BSL errors retain preceding
    effects; only a finite diagnostic and explicit messages cross back.
    """
    def __init__(self, source, endpoints, *, database_context=None):
        bounded_text(source, 65536)
        if type(endpoints) is not dict or not 1 <= len(endpoints) <= MAX_ENDPOINTS:
            raise ValueError('invalid endpoint inventory')
        program = parse(source, '<invocation-server>')
        if not program or any(not isinstance(node, ast.Routine) or
                node.execution_context != 'server' or node.module_context or node.is_async or node.is_dual
                for node in program):
            raise ValueError('server module requires NoContext routines only')
        self._messages = []
        self._interpreter = Interpreter(self._message, database_context=database_context)
        self._interpreter.execute_program(program)
        self._routines = {}
        bindings = []
        for endpoint, name in endpoints.items():
            routine = self._interpreter.server_routines.get(_identifier(name).casefold())
            if routine is None or any(not p.by_value or p.default is not None for p in routine.parameters):
                raise ValueError('endpoint requires explicit by-value parameters')
            binding = InvocationBinding(routine.name, endpoint,
                tuple(p.name for p in routine.parameters), routine.is_function)
            self._routines[endpoint] = routine
            bindings.append(binding)
        self.bindings = tuple(bindings)
        self._gate = Lock()
        self._last_id = 0
        self._requests = 0

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
            activation = self._interpreter._new_server_activation(module_context=False)
            activation._context_stack.append('server')
            activation._module_context_stack.append(False)
            try:
                arguments = [ast.Literal(routine.token, value) for value in values]
                with target_context(activation.native_target), localcontext():
                    result = activation._scheduler.run_inline(activation.call_routine(
                        routine, arguments, activation, require_value=routine.is_function))
                return self._reply(request_id, value=result)
            except Exception:
                return self._reply(request_id, reason='server_error')
            finally:
                activation._module_context_stack.pop()
                activation._context_stack.pop()
                activation._scheduler.active_context.state.pop(activation._diagnostic_owner, None)
        finally:
            self._gate.release()

"""Opt-in replicated scalar and fixed-table forms with a host-owned byte transport.

Client and server have different modules, interpreters and form objects. Only a
closed state packet and prebound endpoint IDs cross the boundary. This is not a
network service, a persistence transaction or a native UI-event parity claim.
"""
from decimal import Decimal, localcontext
from threading import Lock

from .form_model import (BSLClientApplicationForm, BSLFormAttribute, BSLFormField,
    BSLFormButton, BSLFormCommand, BSLFormTable, BSLFormFieldView, MAX_ATTRIBUTES, MAX_ITEMS,
    MAX_COMMANDS, MAX_TOTAL_TEXT, MAX_ALLOCATED, name, scalar, text)
from .form_runtime import FormSession, MAX_SOURCE
from .invocation import (InvocationBinding, InvocationPort, InvocationError,
    MAX_CALLS, MAX_ENDPOINTS, _encode_scalar, _decode_scalar)
from .native_targets import target_context
from .syntax import ast
from .syntax.lexer import Token
from .syntax.parser import parse
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
    BSLDateQualifiers, BSLAllowedSign, BSLAllowedLength, BSLDateFractions)
from .ui.protocol import encode_line, decode_line, bounded_text, MAX_COUNTER, encode_value, decode_value
from .dates import BSLDate

from .form_table_replication import (pack_tables, unpack_tables, install_tables,
    capture_tables, capture_selections, table_delta, selection_delta,
    admit_table_delta, apply_table_delta)

from .form_references import is_reference, adjust, encode, decode, require_scope

PROTOCOL = 'yadinassi-form/1'
_REASONS = frozenset(('invalid_request', 'sequence', 'stale_revision', 'closed',
    'request_limit', 'unknown_endpoint', 'invalid_arguments', 'invalid_delta',
    'server_error', 'result_unavailable', 'busy'))



def _encode_form_scalar(value):
    """Local form-state profile admits the ordinary empty Date, not endpoints.

    Invocation arguments/results retain their measured generic transfer guard.
    No fractional Date or overflow boundary is added to either profile.
    """
    if type(value) is BSLDate and value.ticks == 0 and not value.boundary:
        return encode_value(value)
    return _encode_scalar(value)


def _decode_form_scalar(value):
    result = decode_value(value)
    _encode_form_scalar(result)
    return result

def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError('invalid form packet')


def _integer(value, low=0, high=MAX_COUNTER):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid form counter')
    return value


def _rows(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise ValueError('invalid form inventory')
    return value


def _row(value, size):
    if type(value) is not list or len(value) != size:
        raise ValueError('invalid form record')
    return value


def _booleans(values):
    if any(type(value) is not bool for value in values):
        raise ValueError('invalid form flags')


def _source(source, side):
    from .form_program import admitted_program
    program = admitted_program(source, side=side, label='<replicated-form>')
    if any(not isinstance(node, (ast.Routine, ast.Var)) or
           node.execution_context != side or
           isinstance(node, ast.Routine) and (node.is_async or node.is_dual)
           for node in program):
        raise ValueError('replicated form requires side-only declarations')


def _bindings(values, *, handlers=False):
    if type(values) is not tuple or len(values) > MAX_ENDPOINTS:
        raise ValueError('invalid form binding inventory')
    by_id = {}; by_name = {}
    for binding in values:
        if (type(binding) is not InvocationBinding or
                handlers and binding.is_function or
                binding.endpoint in by_id or binding.name.casefold() in by_name):
            raise ValueError('invalid or duplicate form binding')
        by_id[binding.endpoint] = binding
        by_name[binding.name.casefold()] = binding
    return by_id, by_name


def _stub(interpreter, binding, *, side):
    key = binding.name.casefold()
    if key in interpreter.routines or key in interpreter.server_routines or key in interpreter.functions:
        raise ValueError('form invocation name already bound')
    token = Token('IDENT', binding.name, 1, 1, '<form-signature>')
    routine = ast.Routine(token, binding.name,
        [ast.Parameter(token, parameter, True) for parameter in binding.parameters],
        binding.is_function, False, [], execution_context=side, module_context=True)
    (interpreter.routines if side == 'client' else interpreter.server_routines)[key] = routine
    return routine


def _handler_id(handler, handlers):
    if not handler:
        return 0
    binding = handlers.get(handler.casefold())
    if binding is None:
        raise ValueError('unbound client handler')
    return binding.endpoint


def _handler_name(endpoint, handlers, arity):
    _integer(endpoint, 0, MAX_ENDPOINTS)
    if endpoint == 0:
        return ''
    binding = handlers.get(endpoint)
    if binding is None or len(binding.parameters) != arity:
        raise ValueError('unbound client handler')
    return binding.name


def _appearance(item):
    return [item.name, item.title, item.visible, item.enabled, item.read_only]


def _object_identity(session, item):
    identity = getattr(item, '_replica_id', None)
    if identity is None:
        identity = getattr(session, '_replica_counter', 0) + 1
        _integer(identity, 1, MAX_ALLOCATED)
        session._replica_counter = identity
        item._replica_id = identity
    return identity


def _pack_state(session, handlers):
    form = session.form
    attributes = []
    for key, attribute in form._attributes.items():
        kind = attribute.value_type
        if is_reference(kind):
            require_scope(kind, session)
            attributes.append([attribute.name, "FormCatalogRef", [kind.target], attribute.title,
                key in form._static, encode(kind, form._data[key], _encode_form_scalar)])
            continue
        attributes.append([attribute.name, kind.types[0].value,
            [int(kind.number_qualifiers.digits), int(kind.number_qualifiers.fraction_digits),
             kind.number_qualifiers.allowed_sign.value, int(kind.string_qualifiers.length),
             kind.string_qualifiers.allowed_length.value, kind.date_qualifiers.date_fractions.value],
            attribute.title, key in form._static, _encode_form_scalar(form._data[key])])
    return {'attributes': attributes, 'tables': pack_tables(form), 'title': form.title,
        'items': [[item.name, 'button' if type(item) is BSLFormButton else 'table' if type(item) is BSLFormTable else 'field',
            item.title, item.visible, item.enabled, item.read_only,
            item.command_name if type(item) is BSLFormButton else item.data_path,
            0 if type(item) is BSLFormButton else _handler_id(item.action, handlers),
            item.view.value[0], _object_identity(session, item)] +
            ([item.current_row] if type(item) is BSLFormTable else [])
            for item in form.items._values.values()],
        'commands': [[command.name, command.title, _handler_id(command.action, handlers),
            _object_identity(session, command)]
            for command in form.commands._values.values()],
        'actions': {event: _handler_id(handler, handlers)
            for event, handler in form.actions.items() if event != 'oncreateatserver'},
        'allocated': session._allocated, 'lifecycle': session.state}


def _unpack_state(packet, session, handlers):
    # Scalar host preflight contexts predate the optional reference scope.
    # Reference packet branches still require an explicit enrolled scope.
    scope = getattr(session, 'reference_scope', None)
    checkpoint = None if scope is None else (scope.identity, dict(scope._client), dict(scope._client_values))
    try:
        return _unpack_state_candidate(packet, session, handlers)
    except BaseException:
        if checkpoint is not None:
            scope.identity, scope._client, scope._client_values = checkpoint
        raise


def _unpack_state_candidate(packet, session, handlers):
    """Validate an entire detached candidate before touching live client state."""
    _keys(packet, 'attributes tables title items commands actions allocated lifecycle')
    candidate = BSLClientApplicationForm(session)
    candidate.title = text(packet['title'], 1024)
    allocated = _integer(packet['allocated'], 0, MAX_ALLOCATED)
    if packet['lifecycle'] not in ('open', 'cancelled', 'closed', 'failed'):
        raise ValueError('invalid form lifecycle')
    for row in _rows(packet['attributes'], MAX_ATTRIBUTES):
        attr_name, kind, qualifiers, title, static, encoded = _row(row, 6)
        key = name(attr_name).casefold()
        if key in candidate._attributes or key in session.reserved_names:
            raise ValueError('duplicate or reserved form attribute')
        if kind == 'FormCatalogRef':
            if session.reference_scope is None or session.reference_scope.server:
                raise ValueError('explicit client reference scope required')
            target, = _row(qualifiers, 1)
            _integer(target, 1, 128)
            kind = session.reference_scope.descriptor(target)
            _booleans([static])
            attribute = BSLFormAttribute(attr_name, kind, title=title)
            value = decode(kind, encoded, _decode_form_scalar)
        else:
            q = _row(qualifiers, 6)
            for value, maximum in zip(q, (128, 128, 1, 65536, 1, 3)):
                _integer(value, 0, maximum)
            _booleans([static])
            kind = BSLTypeDescription(kind,
                BSLNumberQualifiers(Decimal(q[0]), Decimal(q[1]), BSLAllowedSign(q[2])),
                BSLStringQualifiers(Decimal(q[3]), BSLAllowedLength(q[4])),
                BSLDateQualifiers(BSLDateFractions(q[5])))
            attribute = BSLFormAttribute(attr_name, kind, title=title)
            value = scalar(_decode_form_scalar(encoded))
            if _encode_form_scalar(kind.adjust_value(value)) != encoded:
                raise ValueError('form value outside schema')
        candidate._attributes[key] = attribute
        candidate._data[key] = value
        if static:
            candidate._static.add(key)
    if sum(len(value) for value in candidate._data.values() if type(value) is str) > MAX_TOTAL_TEXT:
        raise ValueError('form text limit')
    unpack_tables(packet['tables'], candidate, session)
    identities = set()
    for row in _rows(packet['commands'], MAX_COMMANDS):
        command_name, title, action, identity = _row(row, 4)
        _integer(identity, 1, MAX_ALLOCATED)
        if identity in identities:
            raise ValueError('duplicate form identity')
        identities.add(identity)
        key = name(command_name).casefold()
        if key in candidate.commands._values:
            raise ValueError('duplicate form command')
        command = BSLFormCommand(candidate, command_name)
        command._replica_id = identity
        command.title = text(title, 1024)
        command.action = _handler_name(action, handlers, 1)
        candidate.commands._values[key] = command
    table_paths = set()
    for row in _rows(packet['items'], MAX_ITEMS):
        if type(row) is not list or len(row) not in (10, 11):
            raise ValueError('invalid form item record')
        is_table = row[1] == 'table'
        _row(row, 11 if is_table else 10)
        item_name, kind, title, visible, enabled, readonly, path, action, view, identity = row[:10]
        _integer(identity, 1, MAX_ALLOCATED)
        if identity in identities:
            raise ValueError('duplicate form identity')
        identities.add(identity)
        key = name(item_name).casefold()
        if key in candidate.items._values or kind not in ('field', 'button', 'table'):
            raise ValueError('invalid form item')
        _booleans([visible, enabled, readonly])
        item = (BSLFormButton if kind == 'button' else BSLFormTable if kind == 'table' else BSLFormField)(candidate, item_name)
        item._replica_id = identity
        item.title = text(title, 1024)
        item.visible, item.enabled, item.read_only = visible, enabled, readonly
        matches = [value for value in BSLFormFieldView if value.value[0] == view]
        if len(matches) != 1:
            raise ValueError('invalid field view')
        item.view = matches[0]
        text(path, 128)
        if path:
            name(path)
        if kind == 'button':
            if action != 0 or type(action) is not int or view != 'InputField':
                raise ValueError('invalid button')
            if path and path.casefold() not in candidate.commands._values:
                raise ValueError('unknown form command')
            item.command_name = path
        elif kind == 'table':
            key_path = name(path).casefold()
            if view != 'InputField' or key_path not in candidate._tables or key_path in table_paths:
                raise ValueError('unknown or duplicate table binding')
            table_paths.add(key_path)
            selected = row[10]
            if selected is not None and _integer(selected, 1, 4096) not in candidate._tables[key_path]._by_id:
                raise ValueError('removed table selection')
            item.data_path = path; item.current_row = selected
            item.action = _handler_name(action, handlers, 1)
        else:
            if path and path.casefold() not in candidate._attributes:
                raise ValueError('unknown form attribute')
            item.data_path = path
            item.action = _handler_name(action, handlers, 1)
        candidate.items._values[key] = item
    if type(packet['actions']) is not dict or len(packet['actions']) > 3:
        raise ValueError('invalid form lifecycle bindings')
    for event, endpoint in packet['actions'].items():
        if event not in ('onopen', 'beforeclose', 'onclose'):
            raise ValueError('invalid form lifecycle binding')
        candidate.actions[event] = _handler_name(endpoint, handlers, candidate.EVENTS[event][1])
    if allocated < len(candidate.items._values) + len(candidate.commands._values) + len(candidate._attributes) - len(candidate._static):
        raise ValueError('invalid form allocation ledger')
    return candidate, allocated, packet['lifecycle']


def _install_state(session, decoded):
    candidate, allocated, lifecycle = decoded
    form = session.form
    install_tables(form, candidate)
    # Existing event parameters/references continue to denote their local item.
    # Removed/retyped items are invalidated rather than silently kept usable.
    for destination, source in ((form.items, candidate.items), (form.commands, candidate.commands)):
        values = {}
        for key, new in source._values.items():
            old = destination._values.get(key)
            if old is not None and type(old) is type(new) and old._replica_id == new._replica_id:
                old.__dict__.update(new.__dict__)
                item = old
            else:
                item = new
            item._form = form
            values[key] = item
        for key, old in destination._values.items():
            if values.get(key) is not old:
                old._removed = True
        destination._values = values
    form._attributes, form._data, form._static = candidate._attributes, candidate._data, candidate._static
    form.title, form.actions = candidate.title, candidate.actions
    session._allocated = allocated
    return lifecycle


def _capture(form):
    return {'attributes': {key: encode(form._attributes[key].value_type, value, _encode_form_scalar) for key, value in form._data.items()},
            'tables': capture_tables(form), 'selections': capture_selections(form),
            'items': {key: _appearance(item) for key, item in form.items._values.items()},
            'title': form.title}


def _delta(form, baseline):
    current = _capture(form)
    if set(current['attributes']) != set(baseline['attributes']) or set(current['items']) != set(baseline['items']):
        raise ValueError('client cannot change form schema')
    return {'attributes': [[key, value] for key, value in current['attributes'].items()
            if value != baseline['attributes'][key]],
        'items': [value for key, value in current['items'].items() if value != baseline['items'][key]],
        'title': current['title'] if current['title'] != baseline['title'] else None,
        'cells': table_delta(current['tables'], baseline['tables']),
        'selections': selection_delta(current['selections'], baseline['selections'])}


def _admit_delta(form, packet):
    _keys(packet, 'attributes items title cells selections')
    data = form._data.copy(); seen = set()
    for row in _rows(packet['attributes'], MAX_ATTRIBUTES):
        attr_name, encoded = _row(row, 2)
        key = name(attr_name).casefold()
        if key not in form._attributes or key in seen or key in form._host_readonly:
            raise ValueError('invalid form delta attribute')
        seen.add(key)
        if is_reference(form._attributes[key].value_type):
            raise ValueError("reference deltas require server-owned choice")
        value = scalar(_decode_form_scalar(encoded))
        if _encode_form_scalar(form._attributes[key].value_type.adjust_value(value)) != encoded:
            raise ValueError('form delta outside schema')
        data[key] = value
    if sum(len(value) for value in data.values() if type(value) is str) > MAX_TOTAL_TEXT:
        raise ValueError('form text limit')
    items = []; seen = set()
    for row in _rows(packet['items'], MAX_ITEMS):
        item_name, title, visible, enabled, readonly = _row(row, 5)
        key = name(item_name).casefold()
        if key not in form.items._values or key in seen:
            raise ValueError('invalid form delta item')
        seen.add(key); text(title, 1024); _booleans([visible, enabled, readonly])
        items.append((form.items._values[key], title, visible, enabled, readonly))
    title = form.title if packet['title'] is None else text(packet['title'], 1024)
    tables = admit_table_delta(form, packet['cells'], packet['selections'], data)
    return data, items, title, tables


def _apply_delta(form, admitted):
    data, items, title, tables = admitted
    form._data, form.title = data, title
    apply_table_delta(form, tables)
    for item, item_title, visible, enabled, read_only in items:
        item.title, item.visible, item.enabled, item.read_only = item_title, visible, enabled, read_only


class ReplicatedFormServer:
    """One server-owned form. Lifecycle and endpoints are trusted host setup."""
    def __init__(self, source, endpoints, *, handlers, attributes=(), tables=(), initial_values=None,
                 bindings=None, database_context=None, server_bindings=(), interpreter_factory=None, reference_scope=None):
        _source(source, 'server')
        self._handlers, self._handler_names = _bindings(handlers, handlers=True)
        if type(endpoints) is not dict or len(endpoints) > MAX_ENDPOINTS:
            raise ValueError('invalid form endpoints')
        bindings = {} if bindings is None else bindings
        if type(bindings) is not dict or len(bindings) > 4:
            raise ValueError('invalid form lifecycle bindings')
        normalized = {}
        for event, handler in bindings.items():
            event = name(event).casefold()
            event = BSLClientApplicationForm.EVENT_NAMES.get(event, event)
            if event not in BSLClientApplicationForm.EVENTS or event in normalized:
                raise ValueError('invalid form lifecycle binding')
            normalized[event] = name(handler)
        self.session = FormSession(source, attributes=attributes, tables=tables, initial_values=initial_values,
            bindings={key: value for key, value in normalized.items() if key == 'oncreateatserver'},
            database_context=database_context, server_bindings=server_bindings, interpreter_factory=interpreter_factory, reference_scope=reference_scope)
        self.session._replica_handler_names = self._handler_names
        self.session._replica_handlers = self._handlers
        for binding in handlers:
            key = binding.name.casefold()
            if (key in self.session.reserved_names or key in self.session.form._attributes
                    or key in self.session.form._tables):
                raise ValueError('form handler name already bound')
            _stub(self.session.interpreter, binding, side='client')
            self.session.reserved_names.add(key)
        for event, handler in normalized.items():
            self.session._bind(handler, *self.session.form.EVENTS[event])
            self.session.form.actions[event] = handler
        self._routines = {}; self.bindings = []
        for endpoint, routine_name in endpoints.items():
            routine = self.session.interpreter.server_routines.get(name(routine_name).casefold())
            if (routine is None or not routine.module_context or
                    any(not parameter.by_value or parameter.default is not None for parameter in routine.parameters)):
                raise ValueError('form endpoint requires context and required Val parameters')
            binding = InvocationBinding(routine.name, endpoint,
                tuple(parameter.name for parameter in routine.parameters), routine.is_function)
            self._routines[endpoint] = routine
            self.bindings.append(binding)
        self.bindings = tuple(self.bindings)
        self._gate = Lock(); self._last_id = 0; self._sequence = 0; self._requests = 0

    def _reply(self, request_id, *, accepted=False, value=None, reason=None):
        session = self.session
        response = {'protocol': PROTOCOL, 'id': request_id,
            'status': 'ok' if reason is None else 'error', 'accepted': accepted,
            'revision': session.revision, 'sequence': self._sequence,
            'messages': list(session.messages) if accepted else [],
            'state': None}
        try:
            if accepted:
                response['state'] = _pack_state(session, self._handler_names)
            for message in response['messages']:
                bounded_text(message, 1024)
            response['value' if reason is None else 'reason'] = _encode_scalar(value) if reason is None else reason
            return encode_line(response)
        except Exception:
            return encode_line({'protocol': PROTOCOL, 'id': request_id, 'status': 'error',
                'accepted': accepted, 'revision': session.revision, 'sequence': self._sequence,
                'messages': [], 'state': None, 'reason': 'result_unavailable'})

    def exchange(self, raw):
        if not self._gate.acquire(blocking=False):
            return self._reply(None, reason='busy')
        request_id = None
        try:
            try:
                request = decode_line(raw)
                _keys(request, 'protocol id operation revision sequence endpoint arguments delta')
                request_id = _integer(request['id'], 1)
                _integer(request['revision']); _integer(request['sequence'], 1)
                _integer(request['endpoint'], 0, MAX_ENDPOINTS)
                if request['protocol'] != PROTOCOL or request['operation'] not in ('open', 'call', 'close', 'dispose'):
                    raise ValueError('invalid request')
                _rows(request['arguments'], 32)
            except Exception:
                return self._reply(request_id, reason='invalid_request')
            if request_id <= self._last_id or request['sequence'] != self._sequence + 1:
                return self._reply(request_id, reason='sequence')
            if self._requests >= MAX_CALLS:
                return self._reply(request_id, reason='request_limit')
            self._last_id = request_id; self._requests += 1
            session = self.session; operation = request['operation']
            if request['revision'] != session.revision:
                return self._reply(request_id, reason='stale_revision')
            if session.closed or operation != 'dispose' and (operation == 'open') != (session.state == 'created'):
                return self._reply(request_id, reason='closed')
            routine = None; admitted = None; values = []
            if operation == 'call':
                routine = self._routines.get(request['endpoint'])
                if routine is None:
                    return self._reply(request_id, reason='unknown_endpoint')
                try:
                    if len(request['arguments']) != len(routine.parameters):
                        raise ValueError('arity')
                    values = [_decode_scalar(value) for value in request['arguments']]
                except Exception:
                    return self._reply(request_id, reason='invalid_arguments')
            elif request['endpoint'] != 0 or request['arguments']:
                return self._reply(request_id, reason='invalid_arguments')
            try:
                if operation in ('open', 'dispose'):
                    if request['delta'] is not None:
                        raise ValueError('unexpected opening delta')
                else:
                    admitted = _admit_delta(session.form, request['delta'])
            except Exception:
                return self._reply(request_id, reason='invalid_delta')
            session._begin(session.revision)
            self._sequence += 1
            result = None; reason = None
            try:
                if admitted is not None:
                    _apply_delta(session.form, admitted)
                if operation == 'open':
                    created = session._event('oncreateatserver', [False, True])
                    if type(created[0]) is not bool or created[1] is not True:
                        raise ValueError('unsupported creation result')
                    session.closed = created[0]
                    session.state = 'cancelled' if session.closed else 'open'
                elif operation in ('close', 'dispose'):
                    session.closed = True; session.state = 'closed'
                else:
                    arguments = [ast.Literal(routine.token, value) for value in values]
                    with target_context(session.interpreter.native_target), localcontext():
                        result = session.interpreter._scheduler.run_inline(
                            session.interpreter.call_routine(routine, arguments,
                                session.interpreter, require_value=routine.is_function))
            except Exception:
                reason = 'server_error'
                if operation == 'open':
                    session.closed = True; session.state = 'failed'
            finally:
                session.revision += 1; session._busy = False; session._gate.release()
            return self._reply(request_id, accepted=True, value=result, reason=reason)
        finally:
            self._gate.release()


class ReplicatedFormSession(FormSession):
    """Logical client form; server responses are barriers inside client BSL calls.

    Form event revision, server revision, client sequence and request ID are
    separate counters. Unknown outcomes lock the channel; nothing is replayed.
    """
    def __init__(self, source, exchange, *, handlers, bindings=(), output=None, parameters=None, interpreter_factory=None, reference_scope=None):
        _source(source, 'client')
        if not callable(exchange):
            raise TypeError('byte exchange required')
        self._handlers, _ = _bindings(handlers, handlers=True)
        _bindings(bindings)
        super().__init__(source, output=output, parameters=parameters, interpreter_factory=interpreter_factory, reference_scope=reference_scope)
        for binding in handlers:
            routine = self._bind(binding.name, 'client', len(binding.parameters))
            if tuple(parameter.name.casefold() for parameter in routine.parameters) != tuple(value.casefold() for value in binding.parameters):
                raise ValueError('client handler signature mismatch')
        for binding in bindings:
            key = binding.name.casefold()
            if key in self.reserved_names:
                raise ValueError('form invocation name already bound')
            routine = _stub(self.interpreter, binding, side='server')
            self.interpreter._invocation_bindings[key] = (routine,
                lambda values, binding=binding: self._request('call', binding, values))
            self.reserved_names.add(key)
        self._exchange = exchange; self._transport_gate = Lock()
        self._request_id = 0; self.server_revision = 0; self.client_sequence = 0
        self.uncertain = False; self._baseline = None

    def bind_nocontext(self, port, binding):
        if type(port) is not InvocationPort or type(binding) is not InvocationBinding:
            raise TypeError('InvocationPort and InvocationBinding required')
        if not self._gate.acquire(blocking=False):
            raise ValueError('idle form required')
        try:
            key = binding.name.casefold()
            if self.state != 'created' or self._busy or key in self.reserved_names:
                raise ValueError('NoContext binding must precede open with an unused name')
            port._bind(self.interpreter, binding)
            self.reserved_names.add(key)
        finally:
            self._gate.release()

    def _request(self, operation, binding=None, values=()):
        if not self._transport_gate.acquire(blocking=False):
            raise InvocationError('busy')
        started = False
        try:
            if self.uncertain:
                raise InvocationError('outcome_unknown')
            if self._request_id >= MAX_CALLS:
                raise InvocationError('request_limit')
            request_id = self._request_id + 1
            raw = encode_line({'protocol': PROTOCOL, 'id': request_id,
                'operation': operation, 'revision': self.server_revision,
                'sequence': self.client_sequence + 1, 'endpoint': 0 if binding is None else binding.endpoint,
                'arguments': [_encode_scalar(value) for value in values],
                'delta': None if operation in ('open', 'dispose') else _delta(self.form, self._baseline)})
            self._request_id = request_id
            try:
                started = True
                response = decode_line(self._exchange(raw))
                if type(response) is not dict or response.get('status') not in ('ok', 'error'):
                    raise ValueError('invalid response')
                success = response['status'] == 'ok'
                _keys(response, 'protocol id status accepted revision sequence messages state ' + ('value' if success else 'reason'))
                if response['protocol'] != PROTOCOL or _integer(response['id'], 1) != request_id:
                    raise ValueError('invalid response identity')
                accepted = response['accepted']; _booleans([accepted])
                if (_integer(response['revision']) != self.server_revision + int(accepted) or
                        _integer(response['sequence']) != self.client_sequence + int(accepted)):
                    raise ValueError('invalid response revision')
                messages = _rows(response['messages'], 64)
                for message in messages:
                    bounded_text(message, 1024)
                if success:
                    if not accepted:
                        raise ValueError('unaccepted success')
                    result = _decode_scalar(response['value'])
                    if (binding is None or not binding.is_function) and result is not None:
                        raise ValueError('procedure returned value')
                elif type(response['reason']) is not str or response['reason'] not in _REASONS:
                    raise ValueError('invalid response reason')
                if accepted:
                    decoded = _unpack_state(response['state'], self, self._handlers)
                    lifecycle = decoded[2]
                    if operation == 'call' and lifecycle != 'open' or operation in ('close', 'dispose') and lifecycle != 'closed':
                        raise ValueError('invalid response lifecycle')
                elif response['state'] is not None or messages:
                    raise ValueError('rejected response contains effects')
            except Exception:
                self.uncertain = True
                raise InvocationError('outcome_unknown') from None
            if accepted:
                _install_state(self, decoded)
                self.server_revision = response['revision']; self.client_sequence = response['sequence']
                self._baseline = _capture(self.form)
                if operation == 'open':
                    self.state = lifecycle
                    self.closed = lifecycle != 'open'
            try:
                for message in messages:
                    self._record_message(message)
            except Exception:
                self.uncertain = True
                raise InvocationError('outcome_unknown') from None
            if not success:
                if response['reason'] in ('stale_revision', 'sequence', 'closed', 'result_unavailable'):
                    self.uncertain = True
                raise InvocationError(response['reason'])
            return result
        except BaseException as error:
            if started and not isinstance(error, Exception):
                self.uncertain = True
            raise
        finally:
            self._transport_gate.release()

    def open(self):
        if self.state != 'created':
            raise ValueError('form already opened')
        self._begin(0)
        try:
            self._request('open')
            if not self.closed:
                opened = self._event('onopen', [False])
                if type(opened[0]) is not bool:
                    raise ValueError('invalid opening cancellation')
                if opened[0]:
                    self._request('close')
                    self.closed = True; self.state = 'cancelled'
        except BaseException:
            # A known local opening failure must not strand a remote form. This
            # cleanup discards client edits and never reruns a BSL handler.
            # Unknown outcomes require host reconciliation, not automatic work.
            if not self.uncertain and self.server_revision and not self.closed:
                try:
                    self._request('dispose')
                except BaseException:
                    pass  # Preserve the original opening exception.
            self.closed = True; self.state = 'failed'
            raise
        finally:
            self.revision += 1; self._busy = False; self._gate.release()
        return self.snapshot()

    def dispatch(self, event, *, revision, control='', value=None, row=None, column=''):
        if self.uncertain:
            raise InvocationError('outcome_unknown')
        result = super().dispatch(event, revision=revision, control=control, value=value, row=row, column=column)
        if result.state == 'closed':
            # Closing remains local/cancelable; only an accepted close flushes
            # pending scalar state and releases the server-owned form.
            self._request('close')
        return result

    def dispose(self):
        """Host teardown without BSL callbacks or dirty-state flush.

        Useful after a known local lifecycle failure. An uncertain channel is
        never reused: its host must reconcile/tear down the server separately.
        """
        if not self._gate.acquire(blocking=False):
            raise InvocationError('busy')
        try:
            if self._busy:
                raise InvocationError('busy')
            self._busy = True
            self._request('dispose')
            self.closed = True
            if self.state != 'failed':
                self.state = 'closed'
            self.revision += 1
        finally:
            self._busy = False
            self._gate.release()
        return self.snapshot()

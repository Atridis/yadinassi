"""Explicit trusted XML configuration forms, with retained independent replicas.

OpenForm is client BSL infrastructure, not a browser procedure-name endpoint.
The browser receives opaque entry/session IDs and the existing closed form UI
contract. A failed transport locks the entire application without replay.
"""
import argparse
from collections import deque
from contextlib import nullcontext
import os
from pathlib import Path
import sys
from secrets import token_hex
from threading import Lock
import webbrowser

from ..configuration_forms import load_configuration_forms
from ..configuration_import import read_configuration_directory
from ..database_context import SQLiteDBContext
from ..invocation import InvocationPort, InvocationServer, _decode_scalar, _encode_scalar
from ..structures import BSLStructure, BSLFixedStructure
from ..values import HostFunction
from ..form_dialogs import (DIALOG_CAPABILITY, MAX_DIALOGS, MAX_DIALOG_TEXT, MAX_DIALOG_TITLE,
    QuestionDialogMode, DialogReturnCode, OwnedDialog, dialog_text)
from ..form_value_input import (INPUT_CAPABILITY, MAX_INPUTS, ScalarInputSpec,
    ValueListSelection, OwnedInput, scalar_descriptor)
from .form_app import FormController, FormProcess, PROTOCOL as FORM_PROTOCOL
from .local_app import LocalTransportError, LocalUIServer, _Handler
from .protocol import decode_line, encode_line, MAX_LINE_BYTES, MAX_COUNTER

PROTOCOL = 'yadinassi-configuration-app/3'
MAX_FORMS = 8
MAX_SESSIONS = 256
MAX_PARAMETERS = 32


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError('invalid application envelope')


def _parameters(values):
    """Snapshot a small scalar map; never admit a form/object/reference handle."""
    if values is None:
        values = {}
    if type(values) in (BSLStructure, BSLFixedStructure):
        values = {pair.key: pair.value for pair in values}
    if type(values) is not dict or len(values) > MAX_PARAMETERS:
        raise ValueError('scalar form parameters required')
    seen = set(); result = {}
    for key, value in values.items():
        if type(key) is not str or not key.isidentifier() or len(key) > 128 or key.casefold() in seen:
            raise ValueError('invalid form parameter')
        seen.add(key.casefold())
        result[key] = _decode_scalar(_encode_scalar(value))
    encode_line({key: _encode_scalar(value) for key, value in result.items()})
    return result


def load_application(root, *, catalog_objects=False, application_host=False, document_objects=False, business_application=False, reference_application=False, posting_application=False):
    if sum(bool(flag) for flag in (catalog_objects, application_host, document_objects, business_application, reference_application, posting_application)) > 1:
        raise ValueError('configuration source profiles cannot be combined implicitly')
    files = read_configuration_directory(root)
    if posting_application:
        from ..configuration_posting_application import import_posting_application, PROFILE
        imported = import_posting_application(files, posting_runtime=PROFILE)
        return load_configuration_forms(files, document_schemas=imported.documents, posting_application=True)
    if reference_application:
        from ..configuration_reference_profile import import_reference_configuration
        imported = import_reference_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs, document_schemas=imported.documents, reference_catalogs=imported.catalogs)
    if business_application:
        from ..configuration_business_profile import import_business_configuration
        imported = import_business_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs, document_schemas=imported.documents)
    if application_host:
        if catalog_objects:
            raise ValueError('application host is a separate explicit profile')
        from ..configuration_application_profile import import_application_configuration
        imported = import_application_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs)
    if document_objects:
        from ..configuration_document_profile import import_document_forms_configuration
        imported = import_document_forms_configuration(files)
        return load_configuration_forms(files, document_schemas=imported.documents)
    if catalog_objects:
        from ..configuration_xml import import_catalog_forms_configuration
        imported = import_catalog_forms_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs)
    return load_configuration_forms(files)


def _definitions(configuration):
    return {index: definition for index, (_, definition) in
            enumerate(sorted(configuration.forms.items()), 1)}


def _runtime(configuration, side, *, business_application=False, reference_application=False, **kwargs):
    from ..configuration_application_profile import import_application_configuration
    from ..configuration_runtime import ConfigurationApplication
    if reference_application:
        from ..configuration_reference_profile import import_reference_configuration
        imported = import_reference_configuration(dict(configuration.source_files))
    elif business_application:
        from ..configuration_business_profile import import_business_configuration
        imported = import_business_configuration(dict(configuration.source_files))
    else:
        imported = import_application_configuration(dict(configuration.source_files))
    return ConfigurationApplication(imported, side=side, **kwargs)


class ConfigurationBroker:
    """Server-process registry, bound to exactly one admitted configuration digest."""
    def __init__(self, configuration, database=None, *, bind_interpreter=None, application_host=False, business_application=False, reference_application=False, posting_application=False):
        self.configuration = configuration
        self.reference_application = reference_application
        self.posting_application = posting_application
        self.posting_configuration = None
        if posting_application:
            from ..configuration_posting_application import import_posting_application, PROFILE
            self.posting_configuration = import_posting_application(dict(configuration.source_files), posting_runtime=PROFILE)
        self.definitions = _definitions(configuration)
        self.database = database
        self.bind_interpreter = bind_interpreter
        self.sessions = {}
        self.allocated = 0
        self.ready = False
        self.objects = {}
        self.records = {}
        self.record_keys = {}
        self.projections = {}
        self.record_context = None
        self.application = None
        self.application_invocation = None
        if application_host or business_application or reference_application:
            if bind_interpreter is not None:
                raise ValueError('application owns its interpreter family')
            context = None if database is None else SQLiteDBContext(database)
            try:
                self.application = _runtime(configuration, 'server', business_application=business_application, reference_application=reference_application, database_context=context, output=lambda value: None)
                self.record_context = context
                if self.application.server_endpoints:
                    self.application_invocation = InvocationServer.from_handlers(
                        self.application.server_endpoints, message_scope=self.application.event_messages)
            except BaseException:
                if context is not None: context.close()
                raise

    def _catalog(self, entry):
        definition = self.definitions.get(entry) if type(entry) is int else None
        if definition is None or (definition.catalog_schema is None and definition.document_schema is None) or self.database is None:
            raise ValueError('declared object form and active database required')
        if self.record_context is None:
            self.record_context = SQLiteDBContext(self.database)
        context = self.record_context
        context.require_active(tabular_sections=True)
        if context.backend.export_configuration() != dict(self.configuration.source_files):
            raise ValueError('configuration/database source mismatch')
        document = definition.document_schema
        view = context.backend.begin_read() if document is None else context.backend.begin_document_read()
        try:
            if (definition.catalog_schema not in view.catalogs() if document is None
                    else document not in view.documents()):
                raise ValueError('configuration/database schema mismatch')
        finally:
            view.close()
        return definition, context

    def _projection_preflight(self, entry, listing):
        document = self.definitions[entry].document_schema is not None
        cards = listing if document else listing.cards
        needed = {(entry, card.key if document else card.reference) for card in cards} - self.record_keys.keys()
        if len(cards) > 256 or len(self.record_keys) + len(needed) > 4096:
            raise ValueError('catalog capability limit')

    def _records(self, entry):
        from .catalog_view import CatalogRepository
        definition, context = self._catalog(entry)
        document = definition.document_schema
        if document is None:
            repository = CatalogRepository(context.backend, own_backend=False)
            try: listing = repository.load(str(definition.catalog_schema.identity))
            finally: repository.close()
        else:
            from ..document_backend import DocumentSelection
            view = context.backend.begin_document_read()
            try: listing = view.select_documents(document.identity, DocumentSelection())
            finally: view.close()
        try:
            self._projection_preflight(entry, listing)
        except ValueError:
            return {'error': 'catalog_limit'}
        rows = []
        for card in (listing if document is not None else listing.cards):
            identity = (entry, card.key if document is not None else card.reference)
            key = self.record_keys.get(identity)
            if key is None:
                if len(self.record_keys) >= 4096:
                    return {'error': 'catalog_limit'}
                key = 'record-' + str(len(self.record_keys) + 1)
                self.record_keys[identity] = key
                self.records[key] = identity
            if document is None:
                rows.append({'key': key, 'code': card.values[0], 'description': card.values[1],
                             'deletionMark': card.values[2]})
            else:
                rows.append({'key': key, 'number': card.number, 'date': card.date.isoformat(sep=' '),
                             'deletionMark': card.deletion_mark, **({'posted': card.posted} if self.posting_application else {})})
        previous = self.projections.get(entry)
        version = 1 if previous is None else previous['version'] + (previous['rows'] != rows)
        result = {'entry': entry, 'version': version, 'rows': rows}
        encode_line(result)
        self.projections[entry] = result
        return result

    def exchange(self, request):
        _keys(request, 'operation session payload')
        operation, sid, payload = request['operation'], request['session'], request['payload']
        if type(sid) is not str:
            raise ValueError('invalid session')
        if operation == 'hello':
            _keys(payload, 'source')
            if sid or payload['source'] != self.configuration.source_sha256:
                raise ValueError('configuration source mismatch')
            if not self.ready and self.application is not None:
                self.application.start()
            self.ready = True
            return {'source': self.configuration.source_sha256}
        if not self.ready:
            raise ValueError('configuration handshake required')
        if operation == 'applicationInvoke':
            if sid or self.application_invocation is None:
                raise ValueError('application invocation is unavailable')
            return decode_line(self.application_invocation.exchange(encode_line(payload)))
        if operation == 'applicationStop':
            if sid or payload != {} or self.sessions or self.application is None:
                raise ValueError('application cannot stop with open forms')
            return {'closed': self.application.close()}
        if operation == 'catalog':
            _keys(payload, 'entry')
            if sid:
                raise ValueError('catalog operation has no form session')
            try:
                return self._records(payload['entry'])
            except Exception:
                return {'error': 'catalog_unavailable'}
        if operation == 'create':
            _keys(payload, 'entry parameters record')
            entry = payload['entry']
            if sid or type(entry) is not int or entry not in self.definitions:
                raise ValueError('unknown form entry')
            if type(payload['parameters']) is not dict:
                raise ValueError('invalid form parameters')
            values = _parameters({key: _decode_scalar(value) for key, value in payload['parameters'].items()})
            if len(self.sessions) >= MAX_FORMS or self.allocated >= MAX_SESSIONS:
                return {'error': 'capacity'}
            record = payload['record']
            definition = self.definitions[entry]
            reference = None
            if record is not None:
                if type(record) is not str or record not in self.records or self.records[record][0] != entry:
                    return {'error': 'invalid_record'}
                reference = self.records[record][1]
            if definition.catalog_schema is None and definition.document_schema is None and record is not None:
                return {'error': 'invalid_record'}
            if definition.catalog_schema is not None or definition.document_schema is not None:
                self._catalog(entry)
            self.allocated += 1
            sid = 'form-' + str(self.allocated)
            context = None if self.database is None else SQLiteDBContext(self.database)
            server = nocontext = None
            try:
                definition = self.definitions[entry]
                owned = None
                if definition.catalog_schema is not None:
                    from ..configuration_catalog import CatalogObjectSession
                    owned = CatalogObjectSession(context, definition.catalog_schema,
                        dict(self.configuration.source_files), reference=reference, reference_fields=self.reference_application)
                elif definition.document_schema is not None:
                    from ..configuration_document import DocumentObjectSession
                    if self.posting_application:
                        from ..configuration_posting_document import PostingDocumentSession
                        owned = PostingDocumentSession(context, definition.document_schema,
                            self.posting_configuration, definition.name, key=reference)
                    else:
                        owned = DocumentObjectSession(context, definition.document_schema,
                            dict(self.configuration.source_files), key=reference, reference_fields=self.reference_application)
                if owned is not None:
                    owned.projection_preflight = lambda listing, entry=entry: self._projection_preflight(entry, listing)
                server = definition.create_server(parameters=values, database_context=context, object_session=owned,
                    interpreter_factory=None if self.application is None else self.application.form_interpreter_factory)
                server._allow_host_sync = self.application is not None
                program = definition.program
                if program.nocontext_bindings:
                    nocontext = InvocationServer(program.nocontext, program.nocontext_endpoints,
                        database_context=context,
                        interpreter_factory=None if self.application is None else self.application.interpreter_factory)
                if self.bind_interpreter is not None:
                    self.bind_interpreter(server.session.interpreter)
                    if nocontext is not None:
                        self.bind_interpreter(nocontext._interpreter)
                self.sessions[sid] = (server, nocontext, context)
                if owned is not None:
                    self.objects[sid] = owned
                return {'session': sid, 'entry': entry}
            except BaseException:
                for vm in (None if server is None else server.session.interpreter,
                           None if nocontext is None else nocontext._interpreter):
                    if vm is not None:
                        vm.close()
                if context is not None:
                    context.close()
                raise
        if sid not in self.sessions:
            raise ValueError('retired session')
        server, nocontext, context = self.sessions[sid]
        if operation == 'posting':
            _keys(payload, 'action command receipt form')
            if not self.posting_application or sid not in self.objects:
                raise ValueError('explicit posting form required')
            definition = next(d for d in self.definitions.values() if d.name == self.objects[sid].form)
            binding = next((b for b in server.bindings if b.name == 'YadinassiPostingSync'), None)
            frame = payload['form']; action = payload['action']; owned = self.objects[sid]
            if (binding is None or type(frame) is not dict or frame.get('operation') != 'call'
                    or frame.get('endpoint') != binding.endpoint or action not in ('execute', 'recover', 'sync')):
                raise ValueError('unknown posting synchronization capability')
            if action == 'execute' and not any(g.form == definition.name and g.command == payload['command']
                    for g in self.posting_configuration.commands):
                raise ValueError('ungranted posting command')
            if action != 'execute' and payload['command'] is not None:
                raise ValueError('unexpected posting command')
            if action == 'recover' and (type(payload['receipt']) is not str or payload['receipt'] != owned.receipt_token):
                raise ValueError('wrong posting receipt capability')
            if action != 'recover' and payload['receipt'] is not None:
                raise ValueError('unexpected posting receipt')
            if action == 'recover':
                from ..configuration_posting_document import recover_posting_frame
                return recover_posting_frame(definition, server, owned, frame, payload['receipt'])
            # Synchronize typed buffers through the ordinary replica protocol.
            # The root effect cannot run until this dispatch returns successfully.
            response = decode_line(server.exchange(encode_line(frame)))
            if response.get('status') != 'ok' or response.get('accepted') is not True:
                return {'form': response, 'posting': None}
            from ..configuration_posting_document import dispatch_posting
            from ..form_replication import _pack_state
            state = dispatch_posting(definition, server, owned, action, payload['command'], payload['receipt'])
            response['state'] = _pack_state(server.session, server.session._replica_handler_names)
            encode_line(response)
            return {'form': response, 'posting': state}
        if operation == 'guardClose':
            if payload != {}:
                raise ValueError('invalid close guard')
            owned = self.objects.get(sid)
            dirty = (self.posting_application and owned is not None and
                next(d for d in self.definitions.values() if d.name == owned.form)._document_image(server.session) != owned.baseline)
            return {'allowed': not dirty and (owned is None or not (owned.pending_commit or owned.pending_refresh))
                    and (self.application is None or not self.application.interpreter.pending_promises)}
        if operation == 'reference':
            _keys(payload, 'action form')
            chooser = getattr(server, '_reference_choice', None)
            binding = next((b for b in server.bindings if b.name == 'YadinassiReferenceAction'), None)
            frame = payload['form']
            if (chooser is None or binding is None or type(payload['action']) is not dict
                    or type(frame) is not dict or frame.get('operation') != 'call'
                    or frame.get('endpoint') != binding.endpoint):
                raise ValueError('unknown reference capability')
            owned = self.objects.get(sid)
            owned.verify_source()
            chooser.pending = payload['action']
            try:
                response = decode_line(server.exchange(encode_line(frame)))
            finally:
                chooser.pending = None
            return {'form': response, 'choice': chooser.projection(),
                    'changed': chooser.changed_control, 'uncertain': chooser.uncertain}
        if operation == 'form':
            chooser = getattr(server, '_reference_choice', None)
            if chooser is not None and (chooser.active or chooser.uncertain):
                raise ValueError('finish owned reference selection before another form dispatch')
            if (payload.get('operation') in ('close', 'dispose') and self.application is not None
                    and self.application.interpreter.pending_promises):
                raise ValueError('application tasks must finish before releasing a form')
            owned = self.objects.get(sid)
            if owned is not None:
                owned.verify_source()
                if payload.get('operation') in ('close', 'dispose'):
                    owned.require_discardable()
            scope = (nullcontext() if self.application is None else
                     self.application.event_messages(server.session._record_message))
            with scope:
                response = decode_line(server.exchange(encode_line(payload)))
            if (self.posting_application and owned is not None and payload.get('operation') == 'open'
                    and response.get('status') == 'ok' and server.session.state == 'open'
                    and owned.object._revision is None):
                definition = next(d for d in self.definitions.values() if d.name == owned.form)
                owned.baseline = definition._document_image(server.session)
            return response
        if operation == 'invoke':
            if nocontext is None:
                raise ValueError('NoContext channel unavailable')
            scope = (nullcontext() if self.application is None else
                     self.application.event_messages(nocontext._message))
            with scope:
                return decode_line(nocontext.exchange(encode_line(payload)))
        if operation == 'retire':
            if payload != {}:
                raise ValueError('invalid retirement')
            if self.application is not None and self.application.interpreter.pending_promises:
                raise ValueError('application tasks must finish before releasing a form')
            owned = self.objects.get(sid)
            if self.posting_application and owned is not None: owned.close()
            del self.sessions[sid]
            self.objects.pop(sid, None)
            try:
                server.session.interpreter.close()
            finally:
                try:
                    if nocontext is not None:
                        nocontext._interpreter.close()
                finally:
                    if context is not None:
                        context.close()
            return {}
        raise ValueError('unknown application operation')

    def close(self):
        failure = None
        if self.application is not None:
            self.application.close(force=True)
        for sid in list(self.sessions):
            try:
                self.exchange({'operation': 'retire', 'session': sid, 'payload': {}})
            except Exception as error:
                failure = error
        if self.record_context is not None:
            self.record_context.close()
            self.record_context = None
        if self.application is not None:
            self.application.close(force=True)
        if failure is not None:
            raise failure


class ConfigurationProcess(FormProcess):
    def __init__(self, root, database=None, *, catalog_objects=False, application_host=False, document_objects=False, business_application=False, reference_application=False, posting_application=False):
        environment = dict(os.environ, PYTHONIOENCODING='utf-8')
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
        command = ([sys.executable, '--configuration-ui-runtime', str(Path(root).resolve())]
                   if getattr(sys, 'frozen', False) else
                   [sys.executable, '-m', 'yadinassi.ui.configuration_app', str(Path(root).resolve()), '--runtime'])
        if database is not None:
            command += ['--f', str(Path(database).resolve())]
        if catalog_objects:
            command += ['--catalog-objects']
        if application_host:
            command += ['--application-host']
        if business_application:
            command += ['--business-application']
        if reference_application:
            command += ['--reference-application']
        if posting_application:
            command += ['--posting-application']
        if document_objects:
            command += ['--document-objects']
        self._start(command, environment)


def serve_runtime(root, database=None, *, input_stream=None, output_stream=None, catalog_objects=False,
                  application_host=False, document_objects=False, business_application=False, reference_application=False, posting_application=False):
    broker = None
    try:
        broker = ConfigurationBroker(load_application(root, catalog_objects=catalog_objects,
            application_host=application_host, document_objects=document_objects, business_application=business_application, reference_application=reference_application, posting_application=posting_application), database, application_host=application_host, business_application=business_application, reference_application=reference_application, posting_application=posting_application)
        source = sys.stdin.buffer if input_stream is None else input_stream
        target = sys.stdout.buffer if output_stream is None else output_stream
        last_id = 0
        while True:
            raw = source.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return 0
            request = decode_line(raw)
            _keys(request, 'id operation session payload')
            if type(request['id']) is not int or not last_id < request['id'] <= MAX_COUNTER:
                return 1
            last_id = request['id']
            try:
                result = broker.exchange({key: request[key] for key in ('operation', 'session', 'payload')})
                error = None
            except Exception:
                result, error = None, 'operation_failed'
            target.write(encode_line({'id': request['id'], 'session': request['session'],
                                      'result': result, 'error': error})); target.flush()
    except Exception:
        return 1
    finally:
        if broker is not None:
            broker.close()


class ConfigurationController:
    """Several forms, one serialized application queue; no nested event dispatch."""
    def __init__(self, configuration, exchange, *, initial_form=None, bind_interpreter=None,
                 application_host=False, business_application=False, reference_application=False, posting_application=False):
        self.configuration = configuration
        self.reference_application = reference_application
        self.posting_application = posting_application
        self.posting_configuration = None
        if posting_application:
            from ..configuration_posting_application import import_posting_application, PROFILE
            self.posting_configuration = import_posting_application(dict(configuration.source_files), posting_runtime=PROFILE)
        self.definitions = _definitions(configuration)
        self.names = {definition.name.casefold(): entry for entry, definition in self.definitions.items()}
        self.initial_entry = None if initial_form is None else self._entry(initial_form)
        self.transport = exchange
        self.bind_interpreter = bind_interpreter
        self.sessions = {}
        self.issued = set()
        self.operations = {}
        self.pending = deque()
        self.owned_results = {}
        self.owner_children = {}
        self.dialogs = {}
        self.owner_dialogs = {}
        self._dialog_capability = False
        self.inputs = {}
        self.owner_inputs = {}
        self._input_capability = False
        self._close_requests = {}
        self._current_form_sid = None
        self._completion_owner = None
        self.counter = 0
        self.opened = self.closed = self.uncertain = False
        self.active = None
        self.catalog = None
        self.choice = None
        self._reference_action = None
        self._reference_changed = None
        self._posting_action = None
        self.posting_states = {}
        self.catalog_versions = {}
        self.gate = Lock()
        self.application = None
        self.application_messages = []
        self._dispatch_active = False
        if application_host or business_application or reference_application:
            if bind_interpreter is not None:
                raise ValueError('application owns its interpreter family')
            service = HostFunction('OpenForm', self._application_open_form, returns_value=False)
            query = HostFunction('ShowQueryBox', self._application_show_question, returns_value=False)
            warning = HostFunction('ShowMessageBox', self._application_show_warning, returns_value=False)
            value_input = HostFunction('ShowInputValue', self._application_show_input, returns_value=False)
            self.application = _runtime(configuration, 'client', business_application=business_application, reference_application=reference_application, output=self._application_message,
                host_services={'OpenForm': service, 'ОткрытьФорму': service,
                    'ShowQueryBox': query, 'ПоказатьВопрос': query,
                    'ShowMessageBox': warning, 'ПоказатьПредупреждение': warning,
                    'ShowInputValue': value_input, 'ПоказатьВводЗначения': value_input},
                value_selection_service=self._application_choose_item,
                server_exchange=lambda raw: encode_line(self._call('applicationInvoke', payload=decode_line(raw))))

    def _application_message(self, value):
        if type(value) is not str or len(value) > 4096 or len(self.application_messages) >= 64:
            raise ValueError('application message limit')
        self.application_messages.append(value)

    def _application_show_question(self, *arguments):
        if len(arguments) not in (3, 6):
            raise TypeError('ShowQueryBox requires three or six arguments')
        callback, text, mode = arguments[:3]
        title = ''
        if len(arguments) == 6:
            timeout, default, title = arguments[3:]
            if timeout is not None or default is not None:
                raise ValueError('question timeout/default button is unsupported')
        if type(mode) is not QuestionDialogMode:
            raise TypeError('exact QuestionDialogMode required')
        self._queue_dialog(callback, 'question', text, title, mode.value)

    def _application_show_warning(self, *arguments):
        if len(arguments) not in (2, 4):
            raise TypeError('ShowMessageBox requires two or four arguments')
        callback, text = arguments[:2]
        title = ''
        if len(arguments) == 4:
            timeout, title = arguments[2:]
            if timeout is not None:
                raise ValueError('warning timeout is unsupported')
        self._queue_dialog(callback, 'warning', text, title, ('dismiss',))

    def _input_owner(self, callback, caller=None):
        sid = self._current_form_sid
        controller = self.sessions.get(sid, (None, None))[0]
        session = None if controller is None else controller.session
        if (not self._input_capability or not self._dispatch_active or self.uncertain
                or self.application is None or self.application.state != 'running'
                or self.posting_application or self._completion_owner is not None or session is None
                or session.interpreter.execution_context != 'client'
                or not session._busy or session.state != 'open' or session._event_phase is not None
                or session._completion_active or session._owned_form_enrollment is None
                or self._owner_blocked(sid) or sid in self._close_requests or self.choice is not None):
            raise ValueError('input requires a negotiated live owner client event')
        if self.application.input_origin(caller) is not session.interpreter:
            raise ValueError('input origin is not the current owning form')
        if caller is not None and caller is not session.interpreter:
            # Same-context source CommonModules may delegate. Independent child,
            # server and retired VMs do not inherit the active form's authority.
            if not any(side == 'client' and module.interpreter is caller
                       for (_, side), module in self.application._modules.items()):
                raise ValueError('input caller is not the current form or its common module')
        _, target = session.interpreter.callback_target(callback)
        if target is not session.interpreter or callback.module is not session.form or callback._form_target is None:
            raise ValueError('input callback must target the current self-form')
        if len(self.owner_inputs) >= MAX_FORMS or len(self.inputs) >= MAX_INPUTS:
            raise ValueError('input capacity exhausted')
        return sid, session

    def _queue_input(self, sid, session, callback, kind, public, **values):
        ticket = token_hex(16)
        if (ticket in self.inputs or ticket in self.dialogs
                or any(ticket == record.ticket for record in (*self.owner_inputs.values(), *self.owner_dialogs.values()))):
            raise ValueError('input ticket collision')
        image = encode_line(public)
        if len(image) + sum(len(record.image) for record in self.owner_inputs.values()) > MAX_LINE_BYTES // 2:
            raise ValueError('pending input image budget exhausted')
        self.owner_inputs[sid] = OwnedInput(ticket, sid, callback, session._owned_form_enrollment,
            session.interpreter._family_owner._family_generation, kind, image, **values)

    def _application_show_input(self, *arguments):
        if not 2 <= len(arguments) <= 4:
            raise TypeError('ShowInputValue requires two to four arguments')
        callback, initial = arguments[:2]
        sid, session = self._input_owner(callback)
        prompt = arguments[2] if len(arguments) > 2 else None
        descriptor = arguments[3] if len(arguments) > 3 else None
        prompt = dialog_text('' if prompt is None else prompt, MAX_DIALOG_TEXT)
        spec = ScalarInputSpec.capture(scalar_descriptor(initial, descriptor), initial)
        self._queue_input(sid, session, callback, 'input',
            dict(spec.public(), kind='input', title='', text=prompt), spec=spec)

    def _application_choose_item(self, caller, source, *arguments):
        if not 1 <= len(arguments) <= 3:
            raise TypeError('ShowChooseItem requires one to three arguments')
        callback = arguments[0]
        sid, session = self._input_owner(callback, caller)
        title = arguments[1] if len(arguments) > 1 else None
        initial = arguments[2] if len(arguments) > 2 else None
        title = dialog_text('' if title is None else title, MAX_DIALOG_TITLE)
        selection = ValueListSelection.capture(source)
        try:
            public = dict(selection.public(), kind='choice', title=title, initial=selection.initial_choice(initial))
            self._queue_input(sid, session, callback, 'choice', public, selection=selection, source_lease=source)
        except BaseException:
            if selection.state == 'pending': selection.cancel()
            raise

    def _settle_input_event(self, sid, previous, success):
        record = self.owner_inputs.get(sid)
        if record is None or record is previous:
            return
        if not success:
            self.owner_inputs.pop(sid, None)
            record.finish('cancelled')
            return
        try:
            self.inputs[record.ticket] = record
            record.state = 'open'
        except BaseException:
            record.state = 'uncertain'
            self._lock()
            raise

    def _owner_blocked(self, sid):
        return sid in self.owner_children or sid in self.owner_dialogs or sid in self.owner_inputs

    def _owner_block_error(self, sid):
        return 'input_pending' if sid in self.owner_inputs else 'dialog_pending' if sid in self.owner_dialogs else 'owned_child_open'

    def _queue_dialog(self, callback, kind, text, title, choices):
        # No invisible requests in a legacy renderer and no application-start,
        # idle, server, closing or reentrant completion activation.
        sid = self._current_form_sid
        controller = self.sessions.get(sid, (None, None))[0]
        session = None if controller is None else controller.session
        if (not self._dialog_capability or not self._dispatch_active or self.uncertain
                or self.application is None or self.application.state != 'running'
                or self._completion_owner is not None or session is None
                or session.interpreter.execution_context != 'client'
                or not session._busy or session.state != 'open' or session._event_phase is not None
                or session._completion_active or session._owned_form_enrollment is None
                or self._owner_blocked(sid)
                or sid in self._close_requests or self.choice is not None):
            raise ValueError('dialog requires a negotiated live owner client event')
        _, target = session.interpreter.callback_target(callback, form_arity=2 if kind == 'question' else 1)
        if target is not session.interpreter or callback.module is not session.form or callback._form_target is None:
            raise ValueError('dialog callback must target the current self-form')
        text = dialog_text(text, MAX_DIALOG_TEXT)
        title = dialog_text(title, MAX_DIALOG_TITLE)
        if len(self.owner_dialogs) >= MAX_FORMS or len(self.dialogs) >= MAX_DIALOGS:
            raise ValueError('dialog capacity exhausted')
        ticket = token_hex(16)
        if ticket in self.dialogs or any(d.ticket == ticket for d in self.owner_dialogs.values()):
            raise ValueError('dialog ticket collision')
        self.owner_dialogs[sid] = OwnedDialog(ticket, sid, callback, session._owned_form_enrollment,
            session.interpreter._family_owner._family_generation, kind, title, text, choices)

    def _settle_dialog_event(self, sid, previous, success):
        record = self.owner_dialogs.get(sid)
        if record is None or record is previous:
            return
        if not success:
            self.owner_dialogs.pop(sid, None)
            record.finish('cancelled')
            return
        try:
            self.dialogs[record.ticket] = record
            record.state = 'open'
        except BaseException:
            record.state = 'uncertain'
            self._lock()
            raise

    def _application_open_form(self, *arguments):
        if len(arguments) not in (1, 2, 7):
            raise TypeError('OpenForm requires one/two unowned or seven owned arguments')
        name, parameters, owner, uniqueness, window, navigation, completion = (
            *arguments, *([None] * (7 - len(arguments))))
        if (not self._dispatch_active or self.uncertain or self.application is None
                or self.application.state not in ('starting', 'running') or self._completion_owner is not None
                or self._current_form_sid in self.owner_dialogs or self._current_form_sid in self.owner_inputs):
            raise ValueError('OpenForm requires an active application client event')
        if any(value is not None for value in (uniqueness, window, navigation)):
            raise ValueError('OpenForm window/uniqueness/navigation options are unsupported')
        entry, values = self._entry(name), _parameters(parameters)
        if len(self.sessions) + len(self.pending) >= MAX_FORMS or len(self.issued) + len(self.pending) >= MAX_SESSIONS:
            raise ValueError('form capacity exhausted')
        owned = None
        if len(arguments) == 7:
            from ..form_results import OwnedFormResult, freeze_result
            sid = self._current_form_sid
            controller = self.sessions.get(sid, (None, None))[0]
            session = None if controller is None else controller.session
            definition = self.definitions[entry]
            if (self.posting_application or session is None or owner is not session.form
                    or not session._busy or session.state != 'open' or session._event_phase is not None
                    or session._completion_active or sid in self.owner_children
                    or self.choice is not None
                    or not definition.name.startswith('CommonForm.')
                    or definition.catalog_schema is not None or definition.document_schema is not None):
                raise ValueError('owned CommonForm requires a live idle-owner client event')
            routine, target = session.interpreter.callback_target(completion)
            if target is not session.interpreter or completion.module is not owner or completion._form_target is None:
                raise ValueError('completion must target the owning self-form')
            owned = OwnedFormResult(sid, completion, session._owned_form_enrollment, freeze_result(None))
            self.owner_children[sid] = owned
        try:
            self.pending.append((entry, values, owned))
        except BaseException:
            if owned is not None: self.owner_children.pop(owned.owner, None)
            raise

    def _drop_pending_after(self, count):
        while len(self.pending) > count:
            _, _, owned = self.pending.pop()
            if owned is not None:
                owned.finish('opening_failed')
                if self.owner_children.get(owned.owner) is owned:
                    del self.owner_children[owned.owner]

    def _form_exchange(self, controller, request):
        queued_before = len(self.pending)
        scope = (nullcontext() if self.application is None else
                 self.application.event_messages(controller.session._record_message))
        previous = self._current_form_sid
        sid = next((sid for sid, (value, _) in self.sessions.items() if value is controller), None)
        previous_dialog = self.owner_dialogs.get(sid)
        previous_input = self.owner_inputs.get(sid)
        self._current_form_sid = sid
        # FormSession's trusted event entry executes its declared body directly;
        # nested BSL routines then extend this same task-local chain. No VM
        # fields, callback data or authority are copied into another activation.
        origin = (nullcontext() if self.application is None else
                  self.application.input_call(controller.session.interpreter,
                      controller.session.interpreter, True))
        try:
            with scope, origin:
                response = controller.exchange(request)
        except BaseException as exc:
            self._settle_dialog_event(sid, previous_dialog, False)
            self._settle_input_event(sid, previous_input, False)
            self._drop_pending_after(queued_before)
            self._close_requests.pop(sid, None)
            if not isinstance(exc, Exception):
                self._lock()
            raise
        finally:
            self._current_form_sid = previous
        if response['result']['error'] is not None:
            self._drop_pending_after(queued_before)
            self._close_requests.pop(sid, None)
        self._settle_dialog_event(sid, previous_dialog, response['result']['error'] is None)
        self._settle_input_event(sid, previous_input, response['result']['error'] is None)
        return response

    def idle_close(self):
        # Never discard an open form or retry an unknown request because its
        # renderer disappeared. Ordinary BeforeExit can still refuse a clean app.
        if not self.opened or self.sessions or self.uncertain or self.pending:
            return False
        return self.exchange({'jsonrpc':'2.0','id':1,'method':'application.close','params':{}})['result']['state']['kind'] == 'closed'

    def close(self):
        if self.application is not None:
            self.application.close(force=True)

    @staticmethod
    def _validate_choice(choice):
        if choice is None: return
        import re
        _keys(choice, 'ticket control row column title code rows error')
        if (type(choice['ticket']) is not str or not re.fullmatch('[0-9a-f]{32}', choice['ticket'])
                or type(choice['control']) is not str or len(choice['control']) > 128
                or choice['row'] is not None and (type(choice['row']) is not int or not 1 <= choice['row'] <= 4096)
                or choice['column'] is not None and (type(choice['column']) is not str or len(choice['column']) > 128)
                or type(choice['title']) is not str or len(choice['title']) > 1024
                or type(choice['code']) is not str or len(choice['code']) > 64
                or choice['error'] not in (None, 'too_many_matches')
                or type(choice['rows']) is not list or len(choice['rows']) > 32):
            raise ValueError('invalid bounded reference choice')
        tokens = set()
        for row in choice['rows']:
            _keys(row, 'choice code description')
            if (type(row['choice']) is not str or not re.fullmatch('[0-9a-f]{32}', row['choice'])
                    or row['choice'] in tokens or type(row['code']) is not str or len(row['code']) > 64
                    or type(row['description']) is not str or len(row['description']) > 1024):
                raise ValueError('invalid reference choice row')
            tokens.add(row['choice'])

    def _reference_request(self, params):
        _keys(params, 'session revision action')
        sid = params['session']
        if not self.reference_application or type(sid) is not str or sid not in self.sessions:
            raise ValueError('reference application session required')
        controller, entry = self.sessions[sid]
        if self.choice is not None and self.choice['session'] != sid:
            raise ValueError('finish another form reference selection')
        binding = next((b for b in self.definitions[entry].program.server_bindings
                        if b.name == 'YadinassiReferenceAction'), None)
        if binding is None or type(params['action']) is not dict:
            raise ValueError('reference form action required')
        if not controller._gate.acquire(blocking=False): raise ValueError('form busy')
        session = controller.session
        begun = False; error = None; queued_before = len(self.pending)
        try:
            session._begin(params['revision']); begun = True
            self._reference_changed = None
            self._reference_action = (sid, params['action'])
            scope = (nullcontext() if self.application is None else
                     self.application.event_messages(session._record_message))
            with scope:
                session._request('call', binding)
                changed = self._reference_changed
                if changed is not None:
                    item = session.form.items._values[changed['control'].casefold()]
                    if changed['row'] is not None:
                        # Match ordinary cell dispatch: CurrentData identifies
                        # the changed row, not the previously selected sibling.
                        item._table()._lookup_id(changed['row'])
                        item.current_row = changed['row']
                    if item.action: session._invoke(item.action, 'client', [item])
        except Exception:
            if session.uncertain or self.uncertain:
                self._lock(); error = 'outcome_unknown'
            else:
                error = 'reference_refused'
        finally:
            self._reference_action = None
            if begun:
                session.revision += 1; session._busy = False; session._gate.release()
            controller._gate.release()
        if error is not None:
            # Preserve the known applied value, but discard only opens queued
            # by the failed event, just like the ordinary form dispatch path.
            self._drop_pending_after(queued_before)
        return sid, {'jsonrpc':'2.0','id':1,'result':{
            'protocol':FORM_PROTOCOL, 'state':controller._snapshot(), 'error':error}}, error

    def _posting_command(self, entry, request, controller):
        if type(request) is not dict or request.get('method') != 'form.event': return None
        params = request.get('params', {})
        if params.get('event') != 'command': return None
        definition = self.definitions[entry]
        command = next((item[3] for item in definition.items if item[0] == params.get('control') and item[1] == 'Button'), None)
        if not any(g.form == definition.name and g.command == command for g in self.posting_configuration.commands):
            return None
        item = controller.session.form.items._values.get(params.get('control', '').casefold())
        declared = next(c for c in definition.commands if c[0] == command)
        live = controller.session.form.commands._values.get(command.casefold())
        if item is None or item.command_name != command or live is None or live.action != declared[2]:
            raise ValueError('posting source command binding changed')
        return command

    def _posting_sync(self, sid, action, command=None, receipt=None):
        controller, entry = self.sessions[sid]
        binding = next((b for b in self.definitions[entry].program.server_bindings
            if b.name == 'YadinassiPostingSync'), None)
        if binding is None or controller.session._busy:
            raise ValueError('posting barrier requires completed dispatch')
        self._posting_action = (sid, action, command, receipt)
        try:
            controller.session._request('call', binding)
            controller.session.revision += 1
        finally:
            self._posting_action = None

    def _entry(self, name):
        if type(name) is not str or len(name) > 256 or name.casefold() not in self.names:
            raise ValueError('unknown declared form')
        return self.names[name.casefold()]

    def _lock(self):
        self.uncertain = True
        self._drop_pending_after(0)
        for sid, record in tuple(self.owner_dialogs.items()):
            if record.state == 'queued':
                self.owner_dialogs.pop(sid, None)
                record.finish('cancelled')
            else:
                record.state = 'uncertain'
        for sid, record in tuple(self.owner_inputs.items()):
            if record.state == 'queued':
                self.owner_inputs.pop(sid, None)
                record.finish('cancelled')
            else:
                record.state = 'uncertain'
        for controller, _ in self.sessions.values():
            controller.session.uncertain = True

    def _call(self, operation, sid='', payload=None):
        if self.uncertain or self.counter >= MAX_COUNTER:
            raise LocalTransportError('unavailable')
        self.counter += 1
        try:
            response = decode_line(self.transport(encode_line({'id': self.counter, 'operation': operation,
                'session': sid, 'payload': {} if payload is None else payload})))
            _keys(response, 'id session result error')
            if (type(response['id']) is not int or response['id'] != self.counter or response['session'] != sid
                    or response['error'] not in (None, 'operation_failed')):
                raise ValueError('mismatched application response')
            if response['error'] is not None:
                # Creation may already have allocated resources. Never retry an
                # uncertain management operation or invent successful cleanup.
                raise ValueError('application operation failed')
            result = response['result']
            if type(result) is not dict:
                raise ValueError('invalid application result')
            if operation == 'hello':
                _keys(result, 'source')
                if result['source'] != self.configuration.source_sha256:
                    raise ValueError('configuration source mismatch')
            elif operation == 'create':
                if 'error' in result:
                    _keys(result, 'error')
                    if result['error'] not in ('capacity', 'invalid_record'):
                        raise ValueError('invalid capacity refusal')
                else:
                    _keys(result, 'session entry')
                    new = result['session']
                    if (type(new) is not str or not new.startswith('form-') or not new[5:].isdigit()
                            or len(new) > 12 or new in self.issued or type(result['entry']) is not int
                            or result['entry'] != payload['entry']):
                        raise ValueError('invalid new form identity')
            elif operation == 'catalog':
                if 'error' in result:
                    _keys(result, 'error')
                    if result['error'] not in ('catalog_limit', 'catalog_unavailable'):
                        raise ValueError('invalid catalog refusal')
                else:
                    _keys(result, 'entry version rows')
                    if (result['entry'] != payload['entry'] or type(result['entry']) is not int
                            or type(result['version']) is not int or result['version'] < 1
                            or result['version'] < self.catalog_versions.get(result['entry'], 0)
                            or type(result['rows']) is not list or len(result['rows']) > 256):
                        raise ValueError('invalid catalog projection')
                    seen = set()
                    document = self.definitions[result['entry']].document_schema
                    for row in result['rows']:
                        _keys(row, ('key number date deletionMark posted' if self.posting_application else 'key number date deletionMark') if document else 'key code description deletionMark')
                        if self.posting_application and type(row['posted']) is not bool: raise ValueError('invalid posted state')
                        key = row['key']
                        if (type(key) is not str or not key.startswith('record-') or not key[7:].isascii()
                                or not key[7:].isdigit() or len(key) > 12 or key in seen
                                or type(row['deletionMark']) is not bool):
                            raise ValueError('invalid object record')
                        if document:
                            from datetime import datetime
                            if (type(row['number']) is not str or len(row['number']) > document.number_length
                                    or type(row['date']) is not str or len(row['date']) != 19
                                    or datetime.fromisoformat(row['date']).isoformat(sep=' ') != row['date']):
                                raise ValueError('invalid document record')
                        elif (type(row['code']) is not str or len(row['code']) > 64
                                or type(row['description']) is not str or len(row['description']) > 1024):
                            raise ValueError('invalid catalog record')
                        seen.add(key)
                    self.catalog_versions[result['entry']] = result['version']
            elif operation == 'posting':
                _keys(result, 'form posting')
                state = result['posting']
                if state is not None:
                    import re
                    _keys(state, 'receipt state error posted')
                    if (state['receipt'] is not None and (type(state['receipt']) is not str or not re.fullmatch('[0-9a-f]{32}', state['receipt']))
                            or state['state'] not in ('new', 'unchanged', 'saved', 'committed', 'uncertain', 'rejected')
                            or state['error'] not in (None, 'refresh_required', 'outcome_unknown', 'operation_refused')
                            or (state['posted'] is not None if state['state'] in ('uncertain', 'committed')
                                else type(state['posted']) is not bool)):
                        raise ValueError('invalid posting result')
                    self.posting_states[sid] = dict(state, session=sid)
            elif operation == 'reference':
                _keys(result, 'form choice changed uncertain')
                if type(result['uncertain']) is not bool:
                    raise ValueError('invalid reference outcome')
                self._validate_choice(result['choice'])
                changed = result['changed']
                if changed is not None:
                    _keys(changed, 'control row column')
                    if type(changed['control']) is not str or len(changed['control']) > 128 or (changed['row'] is not None and (type(changed['row']) is not int or not 1 <= changed['row'] <= 4096)) or changed['column'] is not None and (type(changed['column']) is not str or len(changed['column']) > 128):
                        raise ValueError('invalid changed reference control')
                self.choice = None if result['choice'] is None else dict(result['choice'], session=sid)
                self._reference_changed = changed
                if result['uncertain']: self._lock()
            elif operation == 'guardClose':
                _keys(result, 'allowed')
                if type(result['allowed']) is not bool:
                    raise ValueError('invalid close guard response')
            elif operation == 'retire' and result != {}:
                raise ValueError('invalid retirement')
            return result
        except BaseException:
            self._lock()
            raise LocalTransportError('unavailable') from None

    def _bind(self, sid, interpreter):
        if self.application is not None:
            self.application.bind_interpreter(interpreter)
            session = interpreter._form_session
            session._owned_form_enrollment = object()
            session._allow_host_sync = True
            session._owned_close = lambda result: self._request_owned_close(sid, result)
            for key in ('showinputvalue', 'показатьвводзначения'):
                if key in interpreter.routines or key in interpreter.server_routines or key in interpreter.variables:
                    raise ValueError('reserved input service alias')
                session.reserved_names.add(key)
            for alias in ('Close', 'Закрыть'):
                key = alias.casefold()
                if (key in interpreter.routines or key in interpreter.server_routines
                        or key in interpreter.functions or key in self.application.reserved_form_names):
                    raise ValueError('reserved owned-form Close alias')
                interpreter.functions[key] = HostFunction(alias, session.request_close, returns_value=False)
                session.reserved_names.add(key)
            return
        def open_form(name, parameters=None):
            controller = self.sessions.get(sid, (None, None))[0]
            # The interpreter is bound before it opens, but the entry is retained
            # before OnOpen. No server or idle host call can enqueue client work.
            if (controller is None or not controller.session._busy or self.uncertain
                    or not interpreter._context_stack or interpreter._context_stack[-1] != 'client'):
                raise ValueError('OpenForm requires an active client form event')
            entry, values = self._entry(name), _parameters(parameters)
            if len(self.sessions) + len(self.pending) >= MAX_FORMS or len(self.issued) + len(self.pending) >= MAX_SESSIONS:
                raise ValueError('form capacity exhausted')
            self.pending.append((entry, values, None))
        for alias in ('OpenForm', 'ОткрытьФорму'):
            key = alias.casefold()
            if key in interpreter.routines or key in interpreter.server_routines or key in interpreter.functions:
                raise ValueError('reserved OpenForm alias')
            interpreter.functions[key] = HostFunction(alias, open_form, returns_value=False)
        if self.bind_interpreter is not None:
            self.bind_interpreter(interpreter)

    def _request_owned_close(self, sid, value):
        from ..form_results import freeze_result
        owned = self.owned_results.get(sid)
        controller = self.sessions.get(sid, (None, None))[0]
        if (owned is None or owned.state != 'open' or controller is None
                or sid != self._current_form_sid or self._owner_blocked(sid)
                or self.uncertain or self._completion_owner is not None or sid in self._close_requests):
            raise ValueError('owned child Close unavailable')
        self._close_requests[sid] = freeze_result(value)

    def _open(self, entry, parameters, record=None, *, owned=None):
        if len(self.sessions) >= MAX_FORMS or len(self.issued) >= MAX_SESSIONS:
            return None, None, 'capacity'
        result = self._call('create', payload={'entry': entry,
            'parameters': {key: _encode_scalar(value) for key, value in parameters.items()}, 'record': record})
        if result.get('error'):
            return None, None, result['error']
        sid = result['session']; self.issued.add(sid)
        definition = self.definitions[entry]
        controller = None
        queued_before = len(self.pending)
        try:
            def exchange(raw):
                if self._posting_action is not None:
                    owner, action, command, receipt = self._posting_action
                    if owner != sid: raise ValueError('posting action owner mismatch')
                    self._posting_action = None
                    result = self._call('posting', sid, {'action': action, 'command': command,
                        'receipt': receipt, 'form': decode_line(raw)})
                    return encode_line(result['form'])
                if self._reference_action is not None:
                    owner, action = self._reference_action
                    if owner != sid: raise ValueError('reference action owner mismatch')
                    self._reference_action = None
                    result = self._call('reference', sid, {'action': action, 'form': decode_line(raw)})
                    return encode_line(result['form'])
                return encode_line(self._call('form', sid, decode_line(raw)))
            reference_scope = None
            if definition.reference_targets:
                from ..form_references import FormReferenceScope
                reference_scope = FormReferenceScope(targets={i: n for i, _, n in definition.reference_targets})
            controller = FormController(definition.client_package(), exchange, parameters=parameters, reference_scope=reference_scope,
                bind_interpreter=lambda vm: self._bind(sid, vm),
                interpreter_factory=None if self.application is None else self.application.form_interpreter_factory)
            if self.posting_application:
                controller.session.form._host_readonly = frozenset((dict(definition.object_fields)["Posted"].casefold(),))
            self.sessions[sid] = (controller, entry)
            if owned is not None:
                owned.child = sid
                self.owned_results[sid] = owned
            if definition.program.nocontext_bindings:
                port = InvocationPort(lambda raw: encode_line(self._call('invoke', sid, decode_line(raw))))
                for binding in definition.program.nocontext_bindings:
                    controller.session.bind_nocontext(port, binding)
            form = self._form_exchange(controller, {'jsonrpc': '2.0', 'id': 1, 'method': 'form.hello',
                                        'params': {'protocol': FORM_PROTOCOL}})
            if controller.session.uncertain:
                self._lock()
            if form['result']['error'] or controller.session.closed:
                raise ValueError('form opening refused')
            if owned is not None: owned.state = 'open'
            self.active = sid
            return sid, form, None
        except Exception:
            self._drop_pending_after(queued_before)
            if controller is not None and controller.session.uncertain:
                self._lock()
            if not self.uncertain:
                self._call('retire', sid)
                self.sessions.pop(sid, None)
                if controller is not None:
                    controller.session.interpreter.close()
                if owned is not None:
                    owned.finish('opening_failed')
                    self.owner_children.pop(owned.owner, None)
            elif owned is not None:
                owned.state = 'uncertain'
            return None, None, 'open_failed'

    def _drain(self):
        error = None
        # Capacity bounds even OnOpen -> OpenForm recursion. Each admission has
        # a fresh identity and completed lifecycle before another form opens.
        while self.pending and not self.uncertain:
            entry, values, owned = self.pending.popleft()
            if owned is not None:
                parent = self.sessions.get(owned.owner, (None, None))[0]
                if (parent is None or parent.session.closed
                        or parent.session._owned_form_enrollment is not owned.enrollment):
                    owned.finish('owner_retired')
                    self.owner_children.pop(owned.owner, None)
                    error = 'retired_session'
                    continue
            try:
                _, _, failed = self._open(entry, values, owned=owned)
            except BaseException:
                if owned is not None:
                    owned.state = 'uncertain'
                    if owned.child is None:
                        self.owner_children.pop(owned.owner, None)
                raise
            if failed:
                if owned is not None and not self.uncertain:
                    owned.finish('opening_failed')
                    self.owner_children.pop(owned.owner, None)
                error = failed
        return error

    def _retire_completed_form(self, sid):
        """Retirement acknowledgement precedes every completion. Never retry."""
        controller, _ = self.sessions[sid]
        owned = self.owned_results.get(sid)
        self._call('retire', sid)
        del self.sessions[sid]
        self.posting_states.pop(sid, None)
        if self.active == sid:
            self.active = owned.owner if owned is not None and owned.owner in self.sessions else next(reversed(self.sessions), None)
        if owned is not None and owned.state == 'open':
            owned.state = 'retired'
        try:
            controller.session.interpreter.close()
        except BaseException:
            if owned is not None: owned.state = 'uncertain'
            if owned is not None: self.owner_children.pop(owned.owner, None)
            self._lock()
            raise
        return owned

    def _deliver_completed_form(self, owned, updates, *, dialog=False, typed=False):
        if owned is None or owned.state != 'retired' or self.uncertain:
            return None
        parent = self.sessions.get(owned.owner, (None, None))[0]
        owners = self.owner_inputs if typed else self.owner_dialogs if dialog else self.owner_children
        if (parent is None or parent.session.closed
                or parent.session._owned_form_enrollment is not owned.enrollment
                or (dialog or typed) and parent.session.interpreter._family_owner._family_generation != owned.generation):
            owned.finish('owner_retired')
            owners.pop(owned.owner, None)
            return 'retired_session'
        from ..form_results import result_value
        session = parent.session
        # Reserve delivery before any fallible work. Even a partial callback or
        # allocation failure is terminal, never an invitation to replay.
        owned.state = 'delivering'
        self._completion_owner = owned.owner
        previous = self._current_form_sid
        self._current_form_sid = owned.owner
        failed = False
        try:
            value = owned.result if dialog or typed else result_value(owned.result)
            with self.application.event_messages(session._record_message):
                session.synchronize_owned()
                try:
                    session.dispatch_completion(owned.callback, value, revision=session.revision,
                        result_argument=not dialog or owned.kind == 'question')
                except Exception:
                    failed = True
                if not session.uncertain:
                    # Pure replica admission, no BSL handler or implicit Write.
                    # Preserve local partial effects even when completion failed.
                    session.synchronize_owned()
            owned.state = 'uncertain' if session.uncertain or self.uncertain else 'failed' if failed else 'delivered'
        except BaseException as exc:
            if session.uncertain or not isinstance(exc, Exception):
                self._lock()
            owned.state = 'uncertain' if self.uncertain else 'failed'
            failed = True
            raise
        finally:
            self._completion_owner = None
            self._current_form_sid = previous
            if not (dialog or typed) or owned.state != 'uncertain':
                owners.pop(owned.owner, None)
            if owned.state in ('failed', 'delivered'):
                owned.finish(owned.state)
        if session.uncertain:
            self._lock()
        reply = self._form_exchange(parent, {'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
        if self.uncertain:
            reply['result']['error'] = 'outcome_unknown'
        elif failed:
            reply['result']['error'] = 'event_failed'
        updates.append({'session': owned.owner, 'form': reply})
        return 'outcome_unknown' if self.uncertain else 'completion_failed' if failed else None

    def _answer_dialog(self, params, updates):
        _keys(params, 'session ticket answer')
        sid, ticket, answer = params['session'], params['ticket'], params['answer']
        if (not self._dialog_capability or type(sid) is not str or type(ticket) is not str
                or len(ticket) != 32 or type(answer) is not str or len(answer) > 16):
            raise ValueError('invalid negotiated dialog answer')
        record = self.dialogs.get(ticket)
        error = None
        if record is None or record.owner != sid:
            error = 'dialog_refused'
        elif record.state != 'open':
            error = 'dialog_retired'
        elif answer not in record.choices:
            error = 'dialog_refused'
        elif (sid not in self.sessions or self.owner_dialogs.get(sid) is not record
                or self.sessions[sid][0].session._owned_form_enrollment is not record.enrollment
                or self.application.interpreter._family_generation != record.generation):
            record.finish('owner_retired')
            if self.owner_dialogs.get(sid) is record: self.owner_dialogs.pop(sid, None)
            error = 'retired_session'
        else:
            # Reserve this exact ticket before dispatch. The enum is a local
            # immutable value, never a browser-selected callback or BSL object.
            record.result = DialogReturnCode(answer) if record.kind == 'question' else None
            record.state = 'retired'
            try:
                error = self._deliver_completed_form(record, updates, dialog=True)
            except Exception:
                error = 'outcome_unknown' if self.uncertain else 'completion_failed'
            if not self.uncertain and self.catalog is not None:
                projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                projection_error = projection.get('error')
                self.catalog = None if projection_error else projection
                error = error or projection_error
        form = None
        if sid in self.sessions:
            form = self._form_exchange(self.sessions[sid][0], {
                'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
            if error == 'completion_failed': form['result']['error'] = 'event_failed'
            elif self.uncertain: form['result']['error'] = 'outcome_unknown'
        return sid, form, error

    def _answer_input(self, params, updates):
        action = params.get('action')
        if type(action) is not str or action not in ('accept', 'choose', 'cancel'):
            raise ValueError('invalid input action')
        _keys(params, 'session ticket action' + (' value' if action == 'accept' else ' choice' if action == 'choose' else ''))
        sid, ticket = params['session'], params['ticket']
        if (not self._input_capability or type(sid) is not str or type(ticket) is not str
                or len(ticket) != 32):
            raise ValueError('invalid negotiated input answer')
        record = self.inputs.get(ticket)
        error = None
        if record is None or record.owner != sid:
            error = 'input_refused'
        elif record.state != 'open':
            error = 'input_retired'
        elif (sid not in self.sessions or self.owner_inputs.get(sid) is not record
                or self.sessions[sid][0].session._owned_form_enrollment is not record.enrollment
                or self.application.interpreter._family_generation != record.generation):
            record.finish('owner_retired')
            if self.owner_inputs.get(sid) is record: self.owner_inputs.pop(sid, None)
            error = 'retired_session'
        elif action != 'cancel' and (action == 'accept') != (record.kind == 'input'):
            error = 'input_refused'
        else:
            try:
                if action == 'cancel':
                    value = None
                    if record.selection is not None: record.selection.cancel()
                elif action == 'accept':
                    value = record.spec.decode(params['value'])
                else:
                    value = record.selection.take(params['choice'])
                record.result = value
                record.state = 'retired'
            except (TypeError, ValueError):
                if record.selection is not None and record.selection.state == 'stale':
                    record.finish('stale')
                    self.owner_inputs.pop(sid, None)
                    error = 'input_stale'
                else:
                    error = 'input_refused'
            except BaseException:
                record.state = 'uncertain'
                self._lock()
                raise
            if error is None:
                try:
                    error = self._deliver_completed_form(record, updates, typed=True)
                except Exception:
                    error = 'outcome_unknown' if self.uncertain else 'completion_failed'
                if not self.uncertain and self.catalog is not None:
                    projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                    projection_error = projection.get('error')
                    self.catalog = None if projection_error else projection
                    error = error or projection_error
        form = None
        if sid in self.sessions:
            form = self._form_exchange(self.sessions[sid][0], {
                'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
            if error == 'completion_failed': form['result']['error'] = 'event_failed'
            elif self.uncertain: form['result']['error'] = 'outcome_unknown'
        return sid, form, error

    def _finish_owned_close(self, sid, form):
        controller = self.sessions[sid][0]
        raw = self._close_requests.pop(sid, None)
        if raw is None or form['result']['error'] is not None or controller.session.uncertain:
            return form, None
        if self._owner_blocked(sid):
            return form, self._owner_block_error(sid)
        if not self._call('guardClose', sid)['allowed']:
            return form, 'save_recovery_required'
        closed = self._form_exchange(controller, {'jsonrpc':'2.0','id':form['id'],
            'method':'form.event','params':{'event':'close','revision':controller.session.revision}})
        if closed['result']['error'] is None and controller.session.closed and not controller.session.uncertain:
            self.owned_results[sid].result = raw
        return closed, None

    def _state(self):
        return {'kind': 'closed' if self.closed else 'application', 'title': self.configuration.title,
                'entries': [{'id': entry, 'title': definition.title,
                             'kind': ('posting-document' if self.posting_application else 'document-object' if definition.document_schema is not None else
                                      'form' if definition.catalog_schema is None else 'catalog-object')} for entry, definition in self.definitions.items()],
                'sessions': [{'id': sid, 'entry': entry, 'title': controller.session.form.title or self.definitions[entry].title,
                              **({'owner': self.owned_results[sid].owner if sid in self.owned_results else None,
                                  'blocked': self._owner_blocked(sid)}
                                 if self.application is not None else {})}
                             for sid, (controller, entry) in self.sessions.items()],
                'active': self.active, 'uncertain': self.uncertain, 'catalog': self.catalog,
                **({'choice': self.choice} if self.reference_application else {}),
                **({'posting': list(self.posting_states.values())} if self.posting_application else {}),
                'lifecycle': 'forms' if self.application is None else self.application.state,
                'messages': list(self.application_messages),
                'exitWarning': '' if self.application is None else self.application.last_exit_warning}

    def exchange(self, request):
        if not self.gate.acquire(blocking=False):
            raise LocalTransportError('busy')
        self._dispatch_active = True
        try:
            _keys(request, 'jsonrpc id method params')
            if (request['jsonrpc'] != '2.0' or type(request['id']) is not int
                    or not 1 <= request['id'] <= MAX_COUNTER or type(request['params']) is not dict):
                raise ValueError('invalid renderer request')
            method, params = request['method'], request['params']
            error = None; sid = None; form = None
            updates = []; retained_before = set(self.sessions)
            if self.closed:
                error = 'closed'
            elif self.uncertain:
                error = 'outcome_unknown'
            elif method == 'application.hello':
                requested_dialogs = params.get('dialogCapability') == DIALOG_CAPABILITY
                requested_input = params.get('inputCapability') == INPUT_CAPABILITY
                expected = {'protocol': PROTOCOL, **({'dialogCapability': DIALOG_CAPABILITY} if requested_dialogs else {}),
                            **({'inputCapability': INPUT_CAPABILITY} if requested_input else {})}
                if params != expected:
                    raise ValueError('invalid application handshake')
                if self.opened and requested_dialogs != self._dialog_capability:
                    raise ValueError('dialog negotiation is immutable')
                if self.opened and requested_input != self._input_capability:
                    raise ValueError('input negotiation is immutable')
                if not self.opened:
                    self._dialog_capability = requested_dialogs
                    self._input_capability = requested_input
                    self.opened = True
                    self._call('hello', payload={'source': self.configuration.source_sha256})
                    if self.application is not None:
                        self.application_messages.clear()
                        try:
                            with self.application.event_messages(self._application_message):
                                started = self.application.start()
                            if not started:
                                self._drop_pending_after(0)
                                self._call('applicationStop')
                                self.closed = True
                                error = 'startup_cancelled'
                        except Exception:
                            self._drop_pending_after(0); self._lock(); error = 'startup_failed'
                    if self.initial_entry is not None and not self.closed and not self.uncertain:
                        sid, form, error = self._open(self.initial_entry, {})
            elif not self.opened:
                raise ValueError('application handshake required')
            elif method == 'application.catalog':
                _keys(params, 'entry')
                entry = params['entry']
                if type(entry) is not int or entry not in self.definitions or (self.definitions[entry].catalog_schema is None and self.definitions[entry].document_schema is None):
                    raise ValueError('unknown record entry')
                projected = self._call('catalog', payload={'entry': entry})
                error = projected.get('error')
                self.catalog = None if error else projected
            elif method in ('application.open', 'application.openRecord'):
                _keys(params, 'entry request record' if method.endswith('openRecord') else 'entry request')
                entry, token = params['entry'], params['request']
                if (type(entry) is not int or entry not in self.definitions or type(token) is not str
                        or not 1 <= len(token) <= 64 or not token.isascii()):
                    raise ValueError('invalid form open intent')
                record = params.get('record')
                if method.endswith('openRecord') and (
                        type(record) is not str or self.catalog is None or self.catalog['entry'] != entry
                        or not any(row['key'] == record for row in self.catalog['rows'])):
                    raise ValueError('record is not in the selected catalog projection')
                intent = (entry, record)
                if token in self.operations:
                    previous, sid, error = self.operations[token]
                    if previous != intent:
                        raise ValueError('open intent reused')
                    if sid is not None and sid not in self.sessions:
                        sid, error = None, 'retired_session'
                elif len(self.operations) >= MAX_SESSIONS:
                    error = 'capacity'
                else:
                    sid, form, error = self._open(entry, {}, record)
                    self.operations[token] = (intent, sid, error)
            elif method == 'application.reference':
                if self._owner_blocked(params.get('session')):
                    _keys(params, 'session revision action')
                    sid = params['session']
                    error = self._owner_block_error(sid)
                    form = self._form_exchange(self.sessions[sid][0], {
                        'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
                    form['result']['error'] = 'busy'
                else:
                    sid, form, error = self._reference_request(params)
                # OnChange may synchronously persist an object even if a later
                # callback statement fails. Reconcile, never replay that write.
                if not self.uncertain and self.catalog is not None:
                    projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                    projection_error = projection.get('error')
                    self.catalog = None if projection_error else projection
                    error = error or projection_error
            elif method == 'application.form':
                _keys(params, 'session request')
                sid = params['session']
                if type(sid) is not str or sid not in self.sessions:
                    error = 'retired_session'
                else:
                    controller, entry = self.sessions[sid]
                    nested_request = params['request']
                    owner_blocked = self._owner_blocked(sid) and (
                        type(nested_request) is not dict or nested_request.get('method') not in ('form.hello', 'form.snapshot'))
                    if (self.choice is not None and self.choice['session'] == sid
                            and (type(nested_request) is not dict or nested_request.get('method') not in ('form.hello', 'form.snapshot'))):
                        raise ValueError('finish reference selection first')
                    closing = (type(nested_request) is dict and nested_request.get('method') == 'form.event'
                               and type(nested_request.get('params')) is dict and nested_request['params'].get('event') == 'close')
                    if closing and self.posting_application and nested_request['params'].get('revision') == controller.session.revision:
                        self._posting_sync(sid, 'sync')
                        nested_request = dict(nested_request, params=dict(nested_request['params'], revision=controller.session.revision))
                    blocked = owner_blocked or (closing and ((self.application is not None
                                  and self.application.interpreter.pending_promises)
                               or ((self.definitions[entry].catalog_schema is not None or self.definitions[entry].document_schema is not None or self.application is not None)
                                  and not self._call('guardClose', sid)['allowed'])))
                    if blocked:
                        error = self._owner_block_error(sid) if owner_blocked else 'save_recovery_required'
                        form = self._form_exchange(controller, {'jsonrpc': '2.0', 'id': nested_request['id'],
                            'method': 'form.snapshot', 'params': {}})
                        form['result']['error'] = 'busy'
                    else:
                        form = self._form_exchange(controller, nested_request)
                        form, close_error = self._finish_owned_close(sid, form)
                        error = error or close_error
                        if self.posting_application and form['result']['error'] is None:
                            command = self._posting_command(entry, nested_request, controller)
                            if command is not None:
                                self._posting_sync(sid, 'execute', command)
                                form = self._form_exchange(controller, {'jsonrpc': '2.0', 'id': nested_request['id'],
                                    'method': 'form.snapshot', 'params': {}})
                    if controller.session.uncertain:
                        self._lock()
                    elif self.catalog is not None:
                        projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                        projection_error = projection.get('error')
                        self.catalog = None if projection_error else projection
                        error = error or projection_error
                    if not controller.session.uncertain and controller.session.closed:
                        owned = self._retire_completed_form(sid)
                        try:
                            completion_error = self._deliver_completed_form(owned, updates)
                            error = error or completion_error
                        except Exception:
                            error = 'outcome_unknown' if self.uncertain else 'completion_failed'
                            if owned is not None and owned.owner in self.sessions:
                                parent = self.sessions[owned.owner][0]
                                reply = self._form_exchange(parent, {'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
                                reply['result']['error'] = 'outcome_unknown' if parent.session.uncertain else 'event_failed'
                                updates.append({'session': owned.owner, 'form': reply})
                        if owned is not None and not self.uncertain and self.catalog is not None:
                            # A completion may explicitly Write before a later
                            # failure. Refresh lists, never repeat that handler.
                            projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                            projection_error = projection.get('error')
                            self.catalog = None if projection_error else projection
                            error = error or projection_error
            elif method == 'application.answerDialog':
                sid, form, error = self._answer_dialog(params, updates)
            elif method == 'application.answerInput':
                sid, form, error = self._answer_input(params, updates)
            elif method == 'application.recoverPosting':
                _keys(params, 'session receipt')
                sid = params['session']
                if not self.posting_application or sid not in self.sessions:
                    raise ValueError('posting session required')
                state = self.posting_states.get(sid)
                if state is None or params['receipt'] != state['receipt'] or state['receipt'] is None:
                    raise ValueError('posting receipt owner mismatch')
                self._posting_sync(sid, 'recover', receipt=params['receipt'])
                controller, entry = self.sessions[sid]
                form = self._form_exchange(controller, {'jsonrpc': '2.0', 'id': 1, 'method': 'form.snapshot', 'params': {}})
                if self.catalog is not None:
                    projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                    error = projection.get('error'); self.catalog = None if error else projection
            elif method == 'application.snapshot':
                if params:
                    raise ValueError('invalid snapshot request')
            elif method == 'application.close':
                if params:
                    raise ValueError('invalid shutdown request')
                if self.sessions:
                    error = 'forms_open'
                else:
                    if self.application is not None:
                        self.application_messages.clear()
                        with self.application.event_messages(self._application_message):
                            accepted = self.application.close()
                        if accepted:
                            if self._call('applicationStop') != {'closed': True}:
                                raise ValueError('server application did not stop')
                            self.closed = True
                        else:
                            error = 'exit_cancelled'
                    else:
                        self.closed = True
            else:
                raise ValueError('unknown application method')
            queued_error = self._drain()
            final_updates = []
            for update in updates:
                owner = update['session']
                if owner in self.sessions and owner in retained_before:
                    if owner == sid:
                        form = update['form']
                    else:
                        final_updates.append(update)
            result = {'protocol': PROTOCOL, 'state': self._state(), 'error': error or queued_error,
                      'session': sid, 'form': form,
                      **({'updates': final_updates} if self.application is not None else {}),
                      **({'dialogCapability': DIALOG_CAPABILITY,
                          'dialogs': [record.public() for record in self.owner_dialogs.values()
                                      if record.state in ('open', 'uncertain')]}
                         if self._dialog_capability else {}),
                      **({'inputCapability': INPUT_CAPABILITY,
                          'inputs': [record.public() for record in self.owner_inputs.values()
                                     if record.state in ('open', 'uncertain')]}
                         if self._input_capability else {})}
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
            try:
                encode_line(response)
            except Exception:
                self._lock()
                raise LocalTransportError('unavailable') from None
            return response
        finally:
            self._dispatch_active = False
            self.gate.release()


class ConfigurationHandler(_Handler):
    asset_directory = 'configuration'
    methods = ('application.hello', 'application.snapshot', 'application.open',
               'application.form', 'application.close', 'application.catalog', 'application.openRecord', 'application.reference',
               'application.recoverPosting', 'application.answerDialog', 'application.answerInput')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run trusted configuration-declared managed forms.')
    parser.add_argument('configuration', metavar='CONFIGURATION_DIRECTORY')
    parser.add_argument('--form', help='Declared form name to open initially')
    parser.add_argument('--f', help='Existing SQLite database, server process only')
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--catalog-objects', action='store_true', help='Explicit scalar catalog object forms profile')
    parser.add_argument('--document-objects', action='store_true', help='Explicit non-posting document Object forms with bounded sections')
    parser.add_argument('--posting-application', action='store_true', help='Explicit host posting command extension')
    parser.add_argument('--reference-application', action='store_true', help='Explicit typed catalog-reference application profile')
    parser.add_argument('--business-application', action='store_true', help='Explicit mixed catalog/document application profile')
    parser.add_argument('--application-host', action='store_true', help='Explicit application/CommonModules and declared forms profile')
    parser.add_argument('--browser-session', action='store_true', help='Single writer attachment, reconnect and safe idle lifetime')
    parser.add_argument('--runtime', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sum((args.catalog_objects, args.application_host, args.document_objects, args.business_application, args.reference_application, args.posting_application)) > 1:
        parser.error('choose one explicit configuration source profile')
    if (args.document_objects or args.business_application or args.reference_application or args.posting_application) and args.f is None:
        parser.error('document applications require --f with an existing explicitly created database')
    if args.runtime:
        return serve_runtime(args.configuration, args.f, catalog_objects=args.catalog_objects, application_host=args.application_host, document_objects=args.document_objects, business_application=args.business_application, reference_application=args.reference_application, posting_application=args.posting_application)
    process = server = controller = None
    try:
        configuration = load_application(args.configuration, catalog_objects=args.catalog_objects, application_host=args.application_host, document_objects=args.document_objects, business_application=args.business_application, reference_application=args.reference_application, posting_application=args.posting_application)
        process = ConfigurationProcess(args.configuration, args.f, catalog_objects=args.catalog_objects, application_host=args.application_host, document_objects=args.document_objects, business_application=args.business_application, reference_application=args.reference_application, posting_application=args.posting_application)
        controller = ConfigurationController(configuration, process.exchange, initial_form=args.form, application_host=args.application_host, business_application=args.business_application, reference_application=args.reference_application, posting_application=args.posting_application)
        server = LocalUIServer(controller, handler=ConfigurationHandler,
            browser_session=args.browser_session or args.application_host or args.document_objects or args.business_application or args.reference_application or args.posting_application, idle_close=controller.idle_close)
        print('Trusted configuration forms. Open this private per-launch URL:')
        print(server.launch_url, flush=True)
        if args.open_browser:
            webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Configuration forms unavailable.', file=sys.stderr)
        return 1
    finally:
        try:
            if server is not None:
                server.server_close()
        finally:
            if process is not None:
                process.close()
            if controller is not None:
                controller.close()


if __name__ == '__main__':
    raise SystemExit(main())

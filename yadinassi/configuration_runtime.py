"""Explicit, headless configuration application using the existing interpreter.

There is no source evaluator, scheduler, database writer or authority escalation
here. Metadata selects ordinary compiled module instances and existing calls.
"""
from contextlib import contextmanager
from decimal import localcontext
from .native_targets import target_context

from .configuration_modules import MODULE_RUNTIME, compile_module
from .configuration_xml import ConfigurationImport, import_configuration
from .errors import BSLError
from .metadata import BSLCommonModuleMetadataCollection
from .structures import BSLStructure
from .syntax import ast


_RESERVED = frozenset(('thisobject', 'этотобъект', 'metadata', 'метаданные',
    'enums', 'перечисления', 'catalogs', 'справочники', 'documents', 'документы', 'informationregisters',
    'регистрысведений', 'chars', 'символы', 'openform', 'открытьформу'))
_EVENTS = {
    'before_start': (('beforestart', 'передначаломработысистемы'), 1),
    'start': (('onstart', 'приначалеработысистемы'), 0),
    'before_exit': (('beforeexit', 'передзавершениемработысистемы'), 2),
    'exit': (('onexit', 'призавершенииработысистемы'), 0),
}


class ConfigurationApplication:
    """One explicit application/session lifetime, not a native GUI or server.

    Construction validates the whole configuration and compiles modules without
    executing application code. start() runs it once. Each application has an
    independent scheduler, module receivers and application state.
    """
    def __init__(self, configuration, *, output=print, database_context=None,
                 native_target='windows-8.3.27.2342', side=None, host_services=None,
                 server_exchange=None):
        from .runtime import Interpreter
        if type(configuration) is not ConfigurationImport or configuration.module_runtime != MODULE_RUNTIME:
            raise TypeError('an explicitly compiled configuration is required')
        if side not in (None, 'client', 'server'):
            raise ValueError('invalid application process side')
        if server_exchange is not None and (side != 'client' or not callable(server_exchange)):
            raise ValueError('server transport belongs to the client process')
        self.side = side
        self._output = output
        self._event_output = None
        self._event_sink = None
        self._server_exchange = server_exchange
        self.server_bindings = ()
        self.server_endpoints = {}
        sources = {entry.path: entry.content for entry in configuration.files}
        numbering = ('decimal_v1' if any(s.numbering == 'decimal_v1'
                     for s in (*configuration.catalogs, *configuration.documents)) else 'explicit')
        from .configuration_application_profile import (APPLICATION_SOURCE_ISSUE, import_application_configuration)
        from .configuration_business_profile import (BUSINESS_SOURCE_ISSUE, import_business_configuration)
        from .configuration_reference_profile import REFERENCE_SOURCE_ISSUE, import_reference_configuration
        references = (len(configuration.activation_issues) == 1 and
                      configuration.activation_issues[0].startswith(REFERENCE_SOURCE_ISSUE + ":"))
        business = (len(configuration.activation_issues) == 1 and
                    configuration.activation_issues[0].startswith(BUSINESS_SOURCE_ISSUE + ':'))
        composed = (len(configuration.activation_issues) == 1 and
                    configuration.activation_issues[0].startswith(APPLICATION_SOURCE_ISSUE + ':'))
        canonical = (import_reference_configuration(sources) if references else
                     import_business_configuration(sources) if business else
                     import_application_configuration(sources) if composed else
                     import_configuration(sources, numbering_policy=numbering, module_runtime=MODULE_RUNTIME))
        if configuration != canonical or (configuration.activation_issues and not (composed or business or references)):
            raise ValueError('configuration cannot be activated')
        if database_context is not None:
            database_context.require_active(tabular_sections=True)
            if references and tuple(database_context.backend.activation_issues) != configuration.activation_issues:
                raise ValueError('reference application requires its exact source grant')
            if database_context.backend.export_configuration() != sources:
                raise ValueError('configuration source does not match the database')
            view = database_context.backend.begin_read()
            try:
                if {x.identity: x for x in view.catalogs()} != {x.identity: x for x in configuration.catalogs}:
                    raise ValueError('configuration catalog schema does not match the database')
            finally:
                view.close()
            if configuration.documents:
                view = database_context.backend.begin_document_read()
                try:
                    if {x.identity: x for x in view.documents()} != {x.identity: x for x in configuration.documents}:
                        raise ValueError('configuration document schema does not match the database')
                finally:
                    view.close()
            if configuration.information_registers:
                view = database_context.backend.begin_register_read()
                try:
                    if {x.identity: x for x in view.registers()} != {x.identity: x for x in configuration.information_registers}:
                        raise ValueError('configuration information-register schema does not match the database')
                finally:
                    view.close()
        self.configuration = configuration
        self.state = 'prepared'
        self.last_exit_warning = ''
        self.interpreter = Interpreter(self._message, native_target=native_target,
                                       database_context=database_context)
        if side == 'server':
            self.interpreter._logical_side = 'server'
            self.interpreter._context_stack = ['server']
        from .values import HostFunction
        self._host_services = {}
        for name, function in (host_services or {}).items():
            if type(name) is not str or type(function) is not HostFunction:
                raise TypeError('named HostFunction services required')
            if side == 'server' and name.casefold() in ('openform', 'открытьформу'):
                raise ValueError('OpenForm is client-only')
            if name.casefold() in self.interpreter.functions:
                raise ValueError('host service conflicts with existing function')
            self.interpreter.functions[name.casefold()] = function
            self._host_services[name.casefold()] = function
        self._definitions = {m.name.casefold(): m for m in configuration.common_modules}
        self._modules = {}
        self._globals = {}
        self._global_names = set()
        self._metadata = BSLCommonModuleMetadataCollection(configuration.common_modules)
        self._program = compile_module(sources.get('Ext/ManagedApplicationModule.bsl', b''),
                                       'Ext/ManagedApplicationModule.bsl', 'client', common=False)
        self._events = {}
        self._common_routines = {}
        self._declared_routines = {id(n): n for n in self._program if type(n) is ast.Routine}
        self._preflight(sources)

    @classmethod
    def from_files(cls, files, *, numbering_policy='explicit', **kwargs):
        configuration = import_configuration(files, numbering_policy=numbering_policy,
                                              module_runtime=MODULE_RUNTIME)
        return cls(configuration, **kwargs)

    @classmethod
    def from_application_files(cls, files, **kwargs):
        from .configuration_application_profile import import_application_configuration
        return cls(import_application_configuration(files), **kwargs)

    @classmethod
    def from_reference_files(cls, files, **kwargs):
        from .configuration_reference_profile import import_reference_configuration
        return cls(import_reference_configuration(files), **kwargs)

    @classmethod
    def from_business_files(cls, files, **kwargs):
        from .configuration_business_profile import import_business_configuration
        return cls(import_business_configuration(files), **kwargs)

    @classmethod
    def from_database(cls, context, **kwargs):
        from .configuration_application_profile import APPLICATION_SOURCE_ISSUE
        from .configuration_business_profile import BUSINESS_SOURCE_ISSUE
        from .configuration_reference_profile import REFERENCE_SOURCE_ISSUE
        issues = context.backend.activation_issues
        if len(issues) == 1 and issues[0].startswith(REFERENCE_SOURCE_ISSUE + ":"):
            return cls.from_reference_files(context.backend.export_configuration(),
                                            database_context=context, **kwargs)
        if len(issues) == 1 and issues[0].startswith(BUSINESS_SOURCE_ISSUE + ":"):
            return cls.from_business_files(context.backend.export_configuration(),
                                           database_context=context, **kwargs)
        if len(issues) == 1 and issues[0].startswith(APPLICATION_SOURCE_ISSUE + ':'):
            return cls.from_application_files(context.backend.export_configuration(),
                                              database_context=context, **kwargs)
        return cls.from_files(context.backend.export_configuration(), numbering_policy='decimal_v1',
                              database_context=context, **kwargs)

    def _preflight(self, sources):
        root = self.interpreter
        reserved = set(root.functions) | set(root.types) | set(_RESERVED)
        module_names = set(self._definitions)
        app_names = set()
        app_routines = {}
        for node in self._program:
            if type(node) is ast.Routine:
                app_routines[node.name.casefold()] = node
                app_names.add(node.name.casefold())
            elif type(node) is ast.Var:
                app_names.update(name.casefold() for name in node.names)
        if module_names & (reserved | app_names):
            raise ValueError('configuration module name conflicts with global context')
        programs = {}
        export_owners = {}
        # Reserve all exports before executing any declaration or initializer.
        # Ambiguous native precedence is deliberately not guessed.
        for name, definition in self._definitions.items():
            for side, enabled in (('client', definition.client), ('server', definition.server)):
                if not enabled:
                    continue
                program = compile_module(sources[definition.path], definition.path, side, common=True)
                programs[name, side] = program
                if definition.global_module:
                    for routine in program:
                        if not routine.exported:
                            continue
                        key = routine.name.casefold()
                        if key in reserved or key in module_names or key in app_names:
                            raise ValueError('global common-module export conflicts with global context')
                        if key in export_owners and export_owners[key] != name:
                            raise ValueError('duplicate global common-module export')
                        export_owners[key] = name
                        self._global_names.add(key)
        for event, (aliases, count) in _EVENTS.items():
            selected = [app_routines[name] for name in aliases if name in app_routines]
            if len(selected) > 1:
                raise ValueError('ambiguous application event alias')
            if selected:
                routine = selected[0]
                if routine.is_function or routine.is_async or len(routine.parameters) != count:
                    raise ValueError('unsupported application event signature')
                if count and routine.parameters[0].by_value:
                    raise ValueError('application cancellation requires a reference parameter')
                self._events[event] = routine
        for (_, program_side), program in programs.items():
            if self.side is not None and program_side != self.side:
                continue
            for routine in program:
                self._common_routines[id(routine)] = routine
                self._declared_routines[id(routine)] = routine
        self.bind_interpreter(root)
        from .invocation import InvocationBinding, InvocationPort
        remote = []
        for name in sorted(self._definitions):
            definition = self._definitions[name]
            if definition.server_call:
                for routine in programs[name, 'server']:
                    if routine.exported:
                        if routine.is_async or any(not p.by_value or p.default is not None for p in routine.parameters):
                            if self.side is not None:
                                raise ValueError('remote common export requires explicit by-value scalar contract')
                        remote.append((name, routine))
        bindings = {(name, routine.name.casefold()): InvocationBinding(routine.name, index + 1,
                    tuple(p.name for p in routine.parameters), routine.is_function)
                    for index, (name, routine) in enumerate(remote)} if self.side is not None else {}
        self.server_bindings = tuple(bindings.values())
        port = InvocationPort(self._server_exchange) if self._server_exchange is not None else None
        for (name, side), program in programs.items():
            if self.side is not None and side != self.side:
                if not (self.side == 'client' and self._definitions[name].server_call):
                    continue
                if port is None:
                    raise ValueError('ServerCall requires a bound server transport')
                child = root._activation_interpreter()
                self.bind_interpreter(child)
                for routine in program:
                    if not routine.exported:
                        continue
                    binding = bindings[name, routine.name.casefold()]
                    port._bind(child, binding)
                    stub = child.server_routines[routine.name.casefold()]
                    stub.exported = True
                    self._common_routines[id(stub)] = stub
                    self._declared_routines[id(stub)] = stub
                child._self_module.ready = True
                self._modules[name, side] = child._self_module
                continue
            child = root._activation_interpreter()
            # Use the same family mechanisms as ordinary imported modules.
            child._diagnostic_owner = root._diagnostic_owner
            child.user_messages = root.user_messages
            child._inherit_host_bindings(root)
            child._handled_errors = root._handled_errors
            child._error_info_boundaries = root._error_info_boundaries
            child._execute_depth = root._execute_depth
            child._eval_depth = root._eval_depth
            self.bind_interpreter(child)
            if side == 'server':
                child._logical_side = 'server'
            child.execute_program(program)  # declarations only; validated above
            self._modules[name, side] = child._self_module
            if self._definitions[name].global_module:
                for routine in program:
                    if routine.exported:
                        self._globals[routine.name.casefold(), side] = (routine, child)
        if self.side == 'server':
            for name, routine in remote:
                binding = bindings[name, routine.name.casefold()]
                owner = self._modules[name, 'server'].interpreter
                self.server_endpoints[binding.endpoint] = (binding,
                    lambda values, routine=routine, owner=owner: self._invoke_remote(owner, routine, values))
        # Application exports are visible to the same logical client context.
        for key, routine in app_routines.items():
            if routine.exported:
                self._globals[key, 'client'] = (routine, root)
                self._global_names.add(key)

    def _message(self, value):
        (self._event_output or self._output)(value)

    @contextmanager
    def event_messages(self, output, sink=None):
        """Route only the active host event, never install a form context in modules."""
        if not callable(output) or sink is not None and not callable(sink):
            raise TypeError('message callbacks required')
        if self._event_output is not None:
            raise ValueError('application event already active')
        self._event_output = output
        self.interpreter.user_messages.set_sink(sink)
        try:
            yield
        finally:
            self.interpreter.user_messages.set_sink(None)
            self._event_output = None

    def interpreter_factory(self, output, **kwargs):
        from .runtime import Interpreter
        self.require_open()
        child = Interpreter(output, native_target=self.interpreter.native_target,
                            family_owner=self.interpreter, **kwargs)
        # Independently dispatched form/NoContext VMs are not transaction roots.
        # Dynamic admission carries this denial through reused common owners.
        child._transaction_activation_allowed = False
        child.functions.update(self._host_services)
        if self.side == 'server': child._logical_side = 'server'
        self.bind_interpreter(child)
        return child

    def form_interpreter_factory(self, session, output, **kwargs):
        from .form_runtime import _FormInterpreter
        self.require_open()
        child = _FormInterpreter(session, output, native_target=self.interpreter.native_target,
                                 family_owner=self.interpreter, **kwargs)
        # Independently dispatched form/NoContext VMs are not transaction roots.
        # Dynamic admission carries this denial through reused common owners.
        child._transaction_activation_allowed = False
        child.functions.update(self._host_services)
        if self.side == 'server': child._logical_side = 'server'
        self.bind_interpreter(child)
        return child

    def _invoke_remote(self, owner, routine, values):
        if self.side != 'server' or self.state != 'running':
            raise ValueError('server application is not running')
        arguments = [ast.Literal(routine.token, value) for value in values]
        with target_context(owner.native_target), localcontext():
            return owner._scheduler.run_inline(owner.call_routine(
                routine, arguments, owner, require_value=routine.is_function))

    def bind_interpreter(self, interpreter):
        """Host seam for application-owned modules, never a BSL method."""
        from .runtime import Interpreter
        if (not isinstance(interpreter, Interpreter)
                or interpreter._scheduler is not self.interpreter._scheduler
                or interpreter._family_owner is not self.interpreter):
            raise ValueError('configuration module must belong to this scheduler family')
        interpreter._require_family()
        interpreter._configuration_runtime = self
        from .enumerations import BSLEnumerations
        if interpreter._metadata._enumerations is None:
            interpreter._metadata._enumerations = BSLEnumerations(self.configuration.enumerations)
        interpreter._metadata._common_modules = self._metadata
        interpreter._metadata._configuration_name = self.configuration.name
        interpreter.user_messages._before_publish = self.check_messages

    def check_messages(self):
        self.require_open()
        if self.state == 'exiting':
            raise ValueError('messages are unavailable during application OnExit')

    def is_common_routine(self, routine):
        return self._common_routines.get(id(routine)) is routine

    @property
    def reserved_form_names(self):
        return frozenset(self._definitions) | frozenset(self._global_names) | frozenset(
            routine.name.casefold() for routine in self._events.values())

    def check_program(self, program):
        self.require_open()
        protected = set(self._definitions) | self._global_names
        protected.update(routine.name.casefold() for routine in self._events.values())
        for node in program:
            if type(node) is ast.Import:
                raise BSLError('file imports are unavailable in configured modules',
                               node.token.source, node.token.line, node.token.column)
            names = node.names if type(node) is ast.Var else (
                (node.name,) if type(node) is ast.Routine else ())
            if any(name.casefold() in protected for name in names):
                if self._declared_routines.get(id(node)) is not node:
                    raise BSLError('declaration conflicts with configuration context',
                                   node.token.source, node.token.line, node.token.column)

    def check_assignment(self, name, caller):
        if name in self._definitions and caller.locals is None:
            raise ValueError('common module names are read-only')

    def require_open(self):
        if self.state in ('closed', 'failed', 'cancelled'):
            raise ValueError('configuration application is not active')

    def resolve_module(self, name, caller):
        self.require_open()
        definition = self._definitions.get(name.casefold())
        if definition is None:
            return None
        if definition.global_module:
            raise ValueError('global common module has no named receiver')
        side = caller.execution_context
        if side == 'client' and not definition.client:
            if not definition.server_call:
                raise ValueError('common module is unavailable on the client')
            side = 'server'
        if side == 'server' and not definition.server:
            raise ValueError('client common module is unavailable on the server')
        return self._modules[name.casefold(), side]

    def resolve_global(self, name, caller):
        self.require_open()
        key = name.casefold()
        if key not in self._global_names:
            return None
        selected = self._globals.get((key, caller.execution_context))
        if selected is None:
            raise ValueError('global export is unavailable in this context')
        return selected

    def check_host_service(self, function, caller):
        self.require_open()
        if function.name.casefold() in ('openform', 'открытьформу'):
            if caller.execution_context != 'client' or self.side == 'server' or self.state not in ('starting', 'running'):
                raise ValueError('OpenForm requires an active client application event')

    def check_call(self, routine, caller):
        self.require_open()
        if self.state in ('before_exit', 'exiting') and (
                routine.is_async or routine.execution_context == 'server'):
            raise ValueError('server and asynchronous calls are unavailable during shutdown')

    def _invoke(self, event, values=()):
        routine = self._events.get(event)
        if routine is None:
            return
        arguments = [ast.Attribute(routine.token, ast.Literal(routine.token, obj), name)
                     for obj, name in values]
        call = ast.Call(routine.token, ast.Name(routine.token, routine.name), arguments)
        self.interpreter.execute_program([ast.ExpressionStatement(routine.token, call)])

    def start(self):
        if self.state != 'prepared':
            raise ValueError('configuration application can start only once')
        self.state = 'starting'
        try:
            if self.side == 'server':
                self.state = 'running'
                return True
            self.interpreter.execute_program(self._program)
            cancel = BSLStructure('Cancel', False)
            self._invoke('before_start', ((cancel, 'Cancel'),))
            if type(cancel.get_member('Cancel')) is not bool:
                raise TypeError('application cancellation requires Boolean')
            if cancel.get_member('Cancel'):
                self.state = 'cancelled'
                self.interpreter.close()
                return False
            self._invoke('start')
            self.interpreter.ensure_complete()
            self.state = 'running'
            return True
        except BaseException:
            self.state = 'failed'
            self.interpreter.close()
            raise

    def execute(self, text, source='<application command>'):
        if self.state != 'running':
            raise ValueError('configuration application must be running')
        return self.interpreter.execute(text, source)

    def close(self, *, force=False):
        if type(force) is not bool:
            raise TypeError('force requires Boolean')
        if self.state == 'closed':
            return True
        if force or self.state != 'running' or self.side == 'server':
            self.interpreter.close()
            self.state = 'closed'
            return True
        self.state = 'before_exit'
        try:
            values = BSLStructure('Cancel,Warning', False, '')
            self._invoke('before_exit', ((values, 'Cancel'), (values, 'Warning')))
            if type(values.get_member('Cancel')) is not bool or type(values.get_member('Warning')) is not str:
                raise TypeError('invalid application shutdown response')
            self.last_exit_warning = values.get_member('Warning')
            if values.get_member('Cancel'):
                self.state = 'running'
                return False
            self.state = 'exiting'
            self._invoke('exit')
            self.interpreter.ensure_complete()
            self.interpreter.close()
            self.state = 'closed'
            return True
        except BaseException:
            self.state = 'failed'
            self.interpreter.close()
            raise

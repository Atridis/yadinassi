"""Explicit, headless configuration application using the existing interpreter.

There is no source evaluator, scheduler, database writer or authority escalation
here. Metadata selects ordinary compiled module instances and existing calls.
"""
from .configuration_modules import MODULE_RUNTIME, compile_module
from .configuration_xml import ConfigurationImport, import_configuration
from .errors import BSLError
from .metadata import BSLCommonModuleMetadataCollection
from .structures import BSLStructure
from .syntax import ast


_RESERVED = frozenset(('thisobject', 'этотобъект', 'metadata', 'метаданные',
    'catalogs', 'справочники', 'documents', 'документы', 'informationregisters',
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
                 native_target='windows-8.3.27.2342'):
        from .runtime import Interpreter
        if type(configuration) is not ConfigurationImport or configuration.module_runtime != MODULE_RUNTIME:
            raise TypeError('an explicitly compiled configuration is required')
        sources = {entry.path: entry.content for entry in configuration.files}
        numbering = ('decimal_v1' if any(s.numbering == 'decimal_v1'
                     for s in (*configuration.catalogs, *configuration.documents)) else 'explicit')
        canonical = import_configuration(sources, numbering_policy=numbering,
                                         module_runtime=MODULE_RUNTIME)
        if configuration != canonical or configuration.activation_issues:
            raise ValueError('configuration cannot be activated')
        if database_context is not None:
            database_context.require_active(tabular_sections=True)
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
        self.configuration = configuration
        self.state = 'prepared'
        self.last_exit_warning = ''
        self.interpreter = Interpreter(output, native_target=native_target,
                                       database_context=database_context)
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
    def from_database(cls, context, **kwargs):
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
        for program in programs.values():
            for routine in program:
                self._common_routines[id(routine)] = routine
                self._declared_routines[id(routine)] = routine
        self.bind_interpreter(root)
        for (name, side), program in programs.items():
            child = root._activation_interpreter()
            # Use the same family mechanisms as ordinary imported modules.
            child._scheduler = root._scheduler
            child._diagnostic_owner = root._diagnostic_owner
            child.user_messages = root.user_messages
            child.functions = root.functions.copy()
            child.types = root.types.copy()
            child._handled_errors = root._handled_errors
            child._error_info_boundaries = root._error_info_boundaries
            child._execute_depth = root._execute_depth
            child._eval_depth = root._eval_depth
            self.bind_interpreter(child)
            child.execute_program(program)  # declarations only; validated above
            self._modules[name, side] = child._self_module
            if self._definitions[name].global_module:
                for routine in program:
                    if routine.exported:
                        self._globals[routine.name.casefold(), side] = (routine, child)
        # Application exports are visible to the same logical client context.
        for key, routine in app_routines.items():
            if routine.exported:
                self._globals[key, 'client'] = (routine, root)
                self._global_names.add(key)

    def bind_interpreter(self, interpreter):
        """Host seam for application-owned modules, never a BSL method."""
        from .runtime import Interpreter
        if not isinstance(interpreter, Interpreter) or interpreter._scheduler is not self.interpreter._scheduler:
            raise ValueError('configuration module must belong to this scheduler family')
        interpreter._configuration_runtime = self
        interpreter._metadata._common_modules = self._metadata
        interpreter.user_messages._before_publish = self.check_messages

    def check_messages(self):
        self.require_open()
        if self.state == 'exiting':
            raise ValueError('messages are unavailable during application OnExit')

    def is_common_routine(self, routine):
        return self._common_routines.get(id(routine)) is routine

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
        if force or self.state != 'running':
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

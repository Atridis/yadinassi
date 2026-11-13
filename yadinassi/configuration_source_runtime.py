"""Explicit experimental startup of admitted sources, without storage grants.

This is a source-host execution attempt, not an activation of arbitrary metadata.
Only reached modules are compiled. Unsupported platform services fail normally;
source admission and the existing database/profile path remain independent.
"""
from dataclasses import fields, is_dataclass
import xml.etree.ElementTree as ET

from .configuration_source import ConfigurationSource
from .configuration_xml import MD
from .errors import BSLRuntimeError
from .runtime import Interpreter
from .structures import BSLStructure
from .syntax import ast
from .syntax.parser import parse


class _SourceInterpreter(Interpreter):
    def __init__(self, application, *args, **kwargs):
        selected = kwargs.setdefault('compilation_profile', application.compilation_profile)
        if selected != application.compilation_profile:
            raise ValueError('source interpreter compilation profile mismatch')
        super().__init__(*args, output=kwargs.pop('output', application.output), **kwargs)
        self.application = application
        self._metadata._enumerations = application.enumerations
        self._source_reusable_runtime = application
        from .source_system_info import SourceSystemInfo
        self.register_type('SystemInfo', lambda: SourceSystemInfo(application), 'СистемнаяИнформация')
        from .source_host_session import SourceSessionCall
        self.register_function('GetCurrentInfoBaseSession', SourceSessionCall(application.host_session, True),
                               'ПолучитьТекущийСеансИнформационнойБазы')
        self.register_function('InfoBaseConnectionString', SourceSessionCall(application.host_session, 'connection'),
                               'СтрокаСоединенияИнформационнойБазы')
        self.register_function('CurrentRunMode', application.current_run_mode)
        self.register_function('ТекущийРежимЗапуска', application.current_run_mode)
        self.register_function('RefreshReusableValues', lambda: application.reusable_values.refresh(self))
        self.register_function('ОбновитьПовторноИспользуемыеЗначения', lambda: application.reusable_values.refresh(self))
        self.register_function('SetSafeMode', lambda enabled: application.safe_mode.set(enabled),
                               'УстановитьБезопасныйРежим', returns_value=False)
        self.register_function('SafeMode', lambda: application.safe_mode.get(), 'БезопасныйРежим')
        from .source_transactions import SourceTransactionCall
        for operation, english, russian in (
                ('begin', 'BeginTransaction', 'НачатьТранзакцию'),
                ('commit', 'CommitTransaction', 'ЗафиксироватьТранзакцию'),
                ('rollback', 'RollbackTransaction', 'ОтменитьТранзакцию'),
                ('active', 'TransactionActive', 'ТранзакцияАктивна')):
            self.register_function(english, SourceTransactionCall(application, operation),
                                   russian, returns_value=operation == 'active')


    def _activation_interpreter(self):
        # A logical ServerCall must retain the admitted source environment,
        # not silently fall back to a standalone Interpreter. The base call
        # engine still owns packet copying and side/transaction/safe-mode gates.
        self.application.require_open()
        return _SourceInterpreter(self.application, output=self.output,
            encoding=self.encoding, native_target=self.native_target,
            compilation_profile=self.compilation_profile,
            family_owner=self._family_owner)

    def execute_program(self, program):
        from .source_transactions import execution
        with execution(self.application), self.application.safe_mode.execution():
            return super().execute_program(program)


    def call(self, node, *, require_value):
        callee = self.ungroup(node.callee)
        if (isinstance(callee, ast.Name)
                and self._resolve_routine(callee.name) is None
                and callee.name.casefold() not in self.functions
                and not (self.locals is not None and callee.name.casefold() in self.locals)
                and not (self._has_module_context and callee.name.casefold() in self.variables
                         and (self.locals is None or callee.name.casefold() in self.module_names))
                and callee.name.casefold() not in self._client_routine_names):
            resolved = self.application.resolve_global(callee.name, self)
            if resolved is not None:
                routine, owner = resolved
                return (yield from self.call_routine(routine, node.arguments, owner,
                                                     require_value=require_value))
        return (yield from super().call(node, require_value=require_value))

    def known_table_receiver(self, node):
        from .source_extensions import SourceExtensions
        value = self.known_receiver(node)
        if type(value) is SourceExtensions:
            return value
        node = self.ungroup(node)
        if (isinstance(node, ast.Name)
                and node.name.casefold() in ('configurationextensions', 'расширенияконфигурации')
                and not (self.locals is not None and node.name.casefold() in self.locals)
                and not (self._has_module_context and node.name.casefold() in self.variables
                         and (self.locals is None or node.name.casefold() in self.module_names))):
            return self.application.extensions
        return super().known_table_receiver(node)

    def visit_Name(self, node):
        key = node.name.casefold()
        if ((self.locals is not None and key in self.locals)
                or (self._has_module_context and key in self.variables
                    and (self.locals is None or key in self.module_names))):
            return super().visit_Name(node)
        if key in ('xdtofactory', 'фабрикаxdto'):
            self.application.require_open()
            return self.application.xdto.factory
        if key in ('metadata', 'метаданные'):
            self.application.require_open()
            return self.application.metadata
        from .source_manager_modules import SourceManagers, MANAGER_NAMES
        if key in MANAGER_NAMES:
            self.application.require_open()
            return SourceManagers(self.application, MANAGER_NAMES[key])
        if key in ('configurationextensions', 'расширенияконфигурации'):
            self.application.require_open()
            return self.application.extensions
        if key in ('configurationextensionssource', 'источникрасширенийконфигурации'):
            from .source_extensions import SourceExtensionSources
            return SourceExtensionSources()
        if key in ('enums', 'перечисления'):
            self.application.require_open()
            return self.application.enumerations
        if key in ('constants', 'константы'):
            from .source_constants_runtime import SourceConstants
            return SourceConstants(self.application)
        if key in ('sessionparameters', 'параметрысеанса'):
            self.application.session_parameters._authorize(self)
            return self.application.session_parameters
        if key in self.application.modules:
            return self.application.module(key, self)
        from .source_application_exports import variable
        reference = variable(self, key)
        if reference is not None:
            return reference.get()
        return super().visit_Name(node)

    def set_variable(self, name, value):
        from .source_application_exports import variable
        reference = variable(self, name)
        if reference is not None:
            reference.set(value)
            return
        return super().set_variable(name, value)

    def argument(self, node):
        ungrouped = self.ungroup(node)
        if isinstance(ungrouped, ast.Name):
            from .source_application_exports import variable
            reference = variable(self, ungrouped.name)
            if reference is not None:
                return reference
        return (yield from super().argument(node))


def _walk(value):
    if isinstance(value, ast.Node):
        yield value
    if is_dataclass(value):
        for field in fields(value):
            yield from _walk(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk(item)


class SourceApplication:
    """One explicit source-only startup attempt; no implicit database or UI."""
    def __init__(self, source, *, output=print, compilation_profile='standalone', scratch_database=None, existing_scratch_database=None, compatibility_target=None):
        if type(source) is not ConfigurationSource:
            raise TypeError('admitted ConfigurationSource required')
        from .syntax.preprocessor import validate_compilation_profile
        compilation_profile = validate_compilation_profile(compilation_profile)
        from .source_system_info import validate_target
        self.compatibility_target = validate_target(compatibility_target)
        from .source_host_session import SourceHostSession
        self.host_session = SourceHostSession(self)
        self.source = source
        self.output = output
        self._compilation_profile = compilation_profile
        self.files = {item.path: item.content for item in source.files}
        from .configuration_source_metadata import SourceMetadataRoot
        self.metadata = SourceMetadataRoot(source)
        self.modules = {item.name.casefold(): item for item in source.metadata
                        if item.family == 'CommonModule'}
        from .configuration_source_enums import source_enum_definitions
        from .enumerations import BSLEnumerations
        enum_definitions, unsupported_enums, _ = source_enum_definitions(source)
        self.enumerations = BSLEnumerations(enum_definitions, unsupported=unsupported_enums)
        from .source_extensions import SourceExtensions
        self.extensions = SourceExtensions(self)
        from .source_xdto_packages import SourceXDTOPackages
        self.xdto = SourceXDTOPackages(self)
        self._instances = {}
        self._reuse_routines = {}
        self._global_exports = {}
        self.side = None
        self.state = 'prepared'
        self.interpreter = _SourceInterpreter(self, compilation_profile=compilation_profile)
        from .configuration_source_session import source_session_definitions
        from .session_parameters import BSLSessionParameters
        definitions, unsupported = source_session_definitions(source)
        self.session_parameters = BSLSessionParameters(self, definitions,
            source_family=self.interpreter, unsupported=unsupported)
        from .reusable_values import ApplicationReusableValues
        self.reusable_values = ApplicationReusableValues(self, source_family=self.interpreter)
        from .safe_mode import SourceSafeMode
        self.safe_mode = SourceSafeMode(self)
        self.constant_store = None
        if scratch_database is not None and existing_scratch_database is not None:
            raise ValueError('create and reopen scratch database are mutually exclusive')
        if scratch_database is not None or existing_scratch_database is not None:
            from .source_constant_store import SourceConstantStore
            try:
                self.constant_store = (SourceConstantStore.create(scratch_database, source)
                                       if scratch_database is not None else
                                       SourceConstantStore.reopen(existing_scratch_database, source))
            except BaseException:
                self.close()
                raise
        self._session_owner = None
        self._session_handler = None

    @property
    def compilation_profile(self):
        return self._compilation_profile

    def _program(self, path):
        program = parse(self.files.get(path, b'').decode('utf-8-sig'),
                        '<configuration:' + path + '>',
                        compilation_profile=self.compilation_profile)
        for node in _walk(program):
            if isinstance(node, ast.Import):
                raise BSLRuntimeError('Файловые импорты недоступны в загруженной конфигурации',
                                      node.token.source, node.token.line, node.token.column)
        return program

    def module(self, key, caller, *, global_call=False):
        self.require_open()
        caller._require_family()
        if (caller._family_owner is not self.interpreter
                or caller._scheduler is not self.interpreter._scheduler):
            raise ValueError('foreign source common-module caller')
        caller_side = caller.execution_context
        definition = self.modules[key]
        root = ET.fromstring(self.files[definition.path])
        properties_node = root[0].find('{' + MD + '}Properties')
        properties = {element.tag.rsplit('}', 1)[-1]: element.text
                      for element in properties_node}
        path = 'CommonModules/' + definition.name + '/Ext/Module.bsl'
        client = properties.get('ClientManagedApplication') == 'true'
        server = properties.get('Server') == 'true'
        crossing = (caller_side == 'client' and not client and server
                    and properties.get('ServerCall') == 'true' and not global_call)
        side = 'server' if crossing else caller_side
        # Cached receivers never bypass admission. Reusable cross-side results
        # need their own measured transport/cache contract; reject rather than
        # sharing mutable cached values across the packet boundary.
        if crossing and properties.get('ReturnValuesReuse', 'DontUse') != 'DontUse':
            raise ValueError('source ServerCall return-value reuse is not supported yet')
        if ((properties.get('Global') == 'true') != global_call
                or (global_call and properties.get('ReturnValuesReuse', 'DontUse') != 'DontUse')
                or properties.get('Privileged') == 'true'
                or properties.get('ClientManagedApplication' if side == 'client' else 'Server') != 'true'
                or properties.get('ReturnValuesReuse', 'DontUse') not in ('DontUse', 'DuringSession', 'DuringRequest')):
            raise ValueError('Режим общего модуля пока не поддержан при запуске источника: ' + definition.name)
        if path not in self.files:
            raise ValueError('Отсутствует исходный текст общего модуля: ' + path)
        instance_key = (key, side, global_call)
        if instance_key in self._instances:
            return self._instances[instance_key]._self_module
        child = _SourceInterpreter(self, family_owner=self.interpreter,
                                   compilation_profile=self.compilation_profile)
        try:
            from .configuration_modules import compile_module
            program = compile_module(self.files[path], path, side, common=True,
                                     compilation_profile=self.compilation_profile)
            child._logical_side = side
            child._application_exports_enabled = not global_call
            if any(not isinstance(node, ast.Routine) for node in program):
                raise ValueError('Общий модуль содержит неподдерживаемую инициализацию: ' + path)
            child.execute_program(program)
            reuse = properties.get('ReturnValuesReuse', 'DontUse')
            if reuse != 'DontUse':
                for routine in program:
                    if routine.is_async:
                        raise ValueError('Асинхронные повторно используемые модули пока не поддержаны')
                    self._reuse_routines[id(routine)] = (routine, child, definition.identity, reuse)
            from .values import BSLType
            child._self_module._platform_type = BSLType.COMMON_MODULE
            child._self_module.ready = True
            self._instances[instance_key] = child
            return child._self_module
        except BaseException:
            child.close()
            raise

    def resolve_global(self, name, caller):
        """Discover real exported routines, without executing unrelated modules."""
        self.require_open()
        side = caller.execution_context
        if side not in self._global_exports:
            from .configuration_modules import compile_module
            exports = {}
            for key, definition in self.modules.items():
                root = ET.fromstring(self.files[definition.path])
                properties = {element.tag.rsplit('}', 1)[-1]: element.text
                              for element in root[0].find('{' + MD + '}Properties')}
                if (properties.get('Global') != 'true'
                        or properties.get('ClientManagedApplication' if side == 'client' else 'Server') != 'true'):
                    continue
                path = 'CommonModules/' + definition.name + '/Ext/Module.bsl'
                if path not in self.files:
                    raise ValueError('Missing global module source: ' + path)
                program = compile_module(self.files[path], path, side, common=True,
                                     compilation_profile=self.compilation_profile)
                for routine in program:
                    if routine.exported:
                        exports.setdefault(routine.name.casefold(), []).append(key)
            self._global_exports[side] = exports
        candidates = self._global_exports[side].get(name.casefold(), [])
        if not candidates:
            from .source_application_exports import routine
            return routine(caller, name)
        if len(candidates) != 1:
            raise ValueError('Ambiguous global source routine: ' + name)
        receiver = self.module(candidates[0], caller, global_call=True)
        return receiver.routine(name), receiver.interpreter

    def require_manager_context(self, caller):
        """Source exports do not grant storage or client-side manager access."""
        self.require_open()
        caller._require_family()
        if (caller._family_owner is not self.interpreter
                or caller._scheduler is not self.interpreter._scheduler
                or caller.execution_context != 'server'
                or caller._scheduler._active_task is not None):
            raise ValueError('source manager modules require owning synchronous server context')

    def manager_module(self, family, name, caller):
        """Execute declared manager code, never synthesize storage operations."""
        self.require_manager_context(caller)
        definition = next((item for item in self.source.metadata
                           if item.family == family and item.name.casefold() == name.casefold()), None)
        if definition is None:
            raise ValueError('Unknown source manager: ' + family + '.' + name)
        key = ('manager', family, definition.name.casefold())
        if key in self._instances:
            return self._instances[key]._self_module
        path = definition.path[:-4] + '/Ext/ManagerModule.bsl'
        if path not in self.files:
            raise ValueError('Source manager module unavailable; storage operations are not activated: ' + path)
        from .configuration_modules import compile_module
        program = compile_module(self.files[path], path, 'server', common=False,
                                 compilation_profile=self.compilation_profile)
        if any(type(node) is not ast.Routine for node in program):
            raise ValueError('Source manager module initialization is not supported: ' + path)
        child = _SourceInterpreter(self, family_owner=self.interpreter,
                                   compilation_profile=self.compilation_profile)
        try:
            child._logical_side = 'server'
            child.execute_program(program)
            child._self_module.ready = True
            self._instances[key] = child
            return child._self_module
        except BaseException:
            child.close()
            raise

    @staticmethod
    def _event(owner, aliases, arguments=()):
        registry = owner.server_routines if owner.execution_context == 'server' else owner.routines
        routines = [registry[name] for name in aliases if name in registry]
        if not routines:
            return
        if len(routines) != 1:
            raise ValueError('Неоднозначный обработчик запуска: ' + '/'.join(aliases))
        routine = routines[0]
        if routine.is_function or routine.is_async or len(routine.parameters) > len(arguments):
            raise ValueError('Неподдерживаемая сигнатура обработчика: ' + routine.name)
        arguments = arguments[:len(routine.parameters)]
        if arguments and routine.parameters[0].by_value:
            raise ValueError('Параметр обработчика должен передаваться по ссылке: ' + routine.name)
        call = ast.Call(routine.token, ast.Name(routine.token, routine.name), list(arguments))
        owner.execute_program([ast.ExpressionStatement(routine.token, call)])

    def start(self):
        if self.state != 'prepared':
            raise ValueError('Повторный запуск приложения недопустим')
        self.state = 'starting'
        try:
            # A session initializer is not silently skipped. It needs the same
            # configuration services as the application and fails on actual use.
            session_path = 'Ext/SessionModule.bsl'
            if self.files.get(session_path, b'').strip():
                session = _SourceInterpreter(self, family_owner=self.interpreter,
                                             compilation_profile=self.compilation_profile)
                self._instances['<session>'] = session
                session._logical_side = 'server'
                from .configuration_modules import compile_session_module
                program, self._session_handler = compile_session_module(
                    self.files[session_path], compilation_profile=self.compilation_profile,
                    allow_omitted_parameters=True)
                self._session_owner = session
                session.execute_program(program)
                handlers = ('sessionparameterssetting', 'установкапараметровсеанса')
                selected = next((session.server_routines[name] for name in handlers if name in session.server_routines), None)
                if selected:
                    session._context_stack.append('server')
                    try:
                        self._event(session, handlers, (ast.Literal(selected.token, None),))
                    finally:
                        session._context_stack.pop()
            path = 'Ext/ManagedApplicationModule.bsl'
            if path not in self.files:
                raise ValueError('Нет модуля управляемого приложения: ' + path)
            self.interpreter.execute_program(self._program(path))
            cancel = BSLStructure('Cancel', False)
            aliases = ('beforestart', 'передначаломработысистемы')
            selected = next((self.interpreter.routines[name] for name in aliases if name in self.interpreter.routines), None)
            if selected:
                self._event(self.interpreter, aliases, (ast.Attribute(selected.token,
                            ast.Literal(selected.token, cancel), 'Cancel'),))
            if type(cancel.get_member('Cancel')) is not bool:
                raise ValueError('Отказ запуска должен быть булевым значением')
            if cancel.get_member('Cancel'):
                self.close()
                self.state = 'cancelled'
                return False
            self._event(self.interpreter, ('onstart', 'приначалеработысистемы'))
            self.interpreter.ensure_complete()
            self.state = 'running'
            return True
        except BaseException:
            self.close()
            self.state = 'failed'
            raise

    def is_scalar_server_reuse(self, routine):
        # No IPC/wire packet exists in this same-side, source-only host.
        return False

    def reusable_call(self, caller, owner, routine, qualified):
        entry = self._reuse_routines.get(id(routine))
        if not qualified or entry is None or not routine.is_function:
            return None
        if entry[0] is not routine or entry[1] is not owner:
            raise ValueError('source reusable routine owner mismatch')
        cache = self.reusable_values.cache(caller, entry[3])
        return cache, (str(entry[2]), routine.name.casefold(), caller.execution_context)

    def current_run_mode(self):
        """No managed/ordinary client is hosted by this headless source runner.

        This is the actual host context, not an emulated native client mode.
        The source host has no native ordinary/managed client mode, including when
        its optional supported-form renderer is attached.
        """
        self.require_open()
        return None

    def require_open(self):
        if self.state not in ('starting', 'running'):
            raise ValueError('source application is not running')

    def initialize_session_parameters(self, caller, names):
        self.session_parameters._authorize(caller)
        if self._session_handler is not None:
            routine = self._session_handler
            yield from caller.call_routine(routine, [ast.Literal(routine.token, names)][:len(routine.parameters)],
                                           self._session_owner, require_value=False)

    def close(self):
        if self.constant_store is not None:
            self.constant_store.close()
        self.session_parameters.close()
        self.reusable_values.close()
        self.interpreter.close()
        self.state = 'closed'

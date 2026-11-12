"""Explicit experimental startup of admitted sources, without storage grants.

This is a headless execution attempt, not an activation of arbitrary metadata.
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
    def __init__(self, application, **kwargs):
        super().__init__(output=application.output, **kwargs)
        self.application = application

    def visit_Name(self, node):
        key = node.name.casefold()
        # Do not expose empty standalone metadata as if it described this source.
        if key in {'metadata', 'метаданные', 'catalogs', 'справочники',
                   'documents', 'документы', 'informationregisters',
                   'регистрысведений', 'accumulationregisters', 'регистрынакопления',
                   'enums', 'перечисления'}:
            raise ValueError('Источник загружен, но сервис конфигурации пока не активирован: ' + node.name)
        if key in self.application.modules:
            return self.application.module(key, self)
        return super().visit_Name(node)


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
    def __init__(self, source, *, output=print, compilation_profile='standalone'):
        if type(source) is not ConfigurationSource:
            raise TypeError('admitted ConfigurationSource required')
        if compilation_profile != 'standalone':
            raise ValueError('Запуск общего источника пока поддерживает только standalone профиль компиляции')
        self.source = source
        self.output = output
        self.compilation_profile = compilation_profile
        self.files = {item.path: item.content for item in source.files}
        self.modules = {item.name.casefold(): item for item in source.metadata
                        if item.family == 'CommonModule'}
        self._instances = {}
        self.state = 'prepared'
        self.interpreter = _SourceInterpreter(self, compilation_profile=compilation_profile)

    def _program(self, path):
        program = parse(self.files.get(path, b'').decode('utf-8-sig'),
                        '<configuration:' + path + '>',
                        compilation_profile=self.compilation_profile)
        for node in _walk(program):
            if isinstance(node, ast.Import):
                raise BSLRuntimeError('Файловые импорты недоступны в загруженной конфигурации',
                                      node.token.source, node.token.line, node.token.column)
        return program

    def module(self, key, caller):
        side = caller.execution_context
        instance_key = (key, side)
        if instance_key in self._instances:
            return self._instances[instance_key]._self_module
        definition = self.modules[key]
        root = ET.fromstring(self.files[definition.path])
        properties_node = root[0].find('{' + MD + '}Properties')
        properties = {element.tag.rsplit('}', 1)[-1]: element.text
                      for element in properties_node}
        path = 'CommonModules/' + definition.name + '/Ext/Module.bsl'
        if (properties.get('Global') == 'true'
                or properties.get('Privileged') == 'true'
                or properties.get('ClientManagedApplication' if side == 'client' else 'Server') != 'true'
                or properties.get('ReturnValuesReuse', 'DontUse') != 'DontUse'):
            raise ValueError('Режим общего модуля пока не поддержан при запуске источника: ' + definition.name)
        if path not in self.files:
            raise ValueError('Отсутствует исходный текст общего модуля: ' + path)
        child = _SourceInterpreter(self, family_owner=self.interpreter,
                                   compilation_profile=self.compilation_profile)
        try:
            from .configuration_modules import compile_module
            program = compile_module(self.files[path], path, side, common=True)
            child._logical_side = side
            if any(not isinstance(node, ast.Routine) for node in program):
                raise ValueError('Общий модуль содержит неподдерживаемую инициализацию: ' + path)
            child.execute_program(program)
            child._self_module.ready = True
            self._instances[instance_key] = child
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
        if routine.is_function or routine.is_async or len(routine.parameters) != len(arguments):
            raise ValueError('Неподдерживаемая сигнатура обработчика: ' + routine.name)
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
                program, _ = compile_session_module(self.files[session_path])
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

    def close(self):
        self.interpreter.close()
        self.state = 'closed'

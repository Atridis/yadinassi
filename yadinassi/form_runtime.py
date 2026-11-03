"""Closed host-values entry for one bounded, headless managed-form session.

This is an internal host adapter, not a BSL global API or a renderer procedure
endpoint. The application supplies trusted source and event bindings at creation;
subsequent inputs select only a finite event on an admitted control identity.
Native form-context semantics remain provisional until source-bound acquisition.
"""
from dataclasses import dataclass
from threading import Lock
from decimal import localcontext
from .runtime import Interpreter, _Return
from .syntax import ast
from .syntax.parser import parse
from .values import Reference, HostFunction
from .native_targets import target_context
from .form_model import (BSLClientApplicationForm, BSLFormAttribute, BSLFormField,
                         BSLFormButton, BSLFormCommand, FORM_FIELD_VIEWS,
                         MAX_ATTRIBUTES, MAX_TOTAL_TEXT, name, scalar, text)

MAX_SOURCE = 65536
MAX_STEPS = 100000
MAX_EVENTS = 10000
MAX_HANDLERS = 128


class FormLimitError(RuntimeError):
    """Uncatchable host execution budget; not a native language assertion."""


@dataclass(frozen=True)
class FormActionResult:
    """Closed scalar patch from trusted application infrastructure, not BSL API."""
    values: tuple = ()


@dataclass(frozen=True)
class FormApplicationAction:
    """Sealed command/handler capability; callbacks never originate in renderer data."""
    command: str
    handler: str
    inputs: tuple
    outputs: tuple
    callback: object
    applied: object = None


@dataclass(frozen=True)
class FormSnapshot:
    revision: int
    state: str
    title: str
    attributes: tuple
    items: tuple
    commands: tuple
    item_views: tuple = ()


class _FormInterpreter(Interpreter):
    def __init__(self, session, *args, **kwargs):
        self._form_session = session
        super().__init__(*args, **kwargs)
        self.register_type('РеквизитФормы', self._make_attribute, 'FormAttribute')
        form = session.form
        for alias, method in [('ИзменитьРеквизиты','change_attributes'),('ChangeAttributes','change_attributes'),
                              ('ПолучитьРеквизиты','get_attributes'),('GetAttributes','get_attributes'),
                              ('УстановитьДействие','set_action'),('SetAction','set_action')]:
            self.functions[alias.casefold()] = HostFunction(alias, getattr(form,method), returns_value=method=='get_attributes')

    def _make_attribute(self, *args):
        self._form_session.form._check(True)
        value = BSLFormAttribute(*args)
        value._session = self._form_session
        return value

    def _activation_interpreter(self):
        return _FormInterpreter(self._form_session, self.output, encoding=self.encoding,
                                native_target=self.native_target, database_context=self.database_context,
                                compilation_profile=self.compilation_profile)

    def _visit(self, node):
        session = self._form_session
        session._steps += 1
        if session._steps > MAX_STEPS: raise FormLimitError('Форма: превышен предел исполнения события')
        return (yield from super()._visit(node))

    def visit_Name(self, node):
        key = node.name.casefold()
        if self.locals is not None and key in self.locals:
            return super().visit_Name(node)
        if key in ('видполяформы','formfieldtype'):
            return FORM_FIELD_VIEWS
        form = self._form_session.form
        if key in ('thisobject','этотобъект','items','элементы','commands','команды') or key in form._static:
            form._check()
            if key in ('thisobject','этотобъект'): return form
            if key in ('items','элементы'): return form.items
            if key in ('commands','команды'): return form.commands
            return form.get_member(node.name)
        return super().visit_Name(node)

    def visit_ForEach(self, node):
        from .form_model import BSLFormItems, BSLFormCommands
        collection = yield from self._visit(node.collection)
        if type(collection) in (BSLFormItems, BSLFormCommands):
            for item in collection:
                self.set_variable(node.name,item)
                if not (yield from self.iteration(node.body)): break
            return
        # Existing generic behavior without re-evaluating the collection.
        from .runtime import _COLLECTIONS, BSLRoundModes, BSLSearchDirections, BSLSortDirections
        if not isinstance(collection,_COLLECTIONS) and type(collection) not in (BSLRoundModes,BSLSearchDirections,BSLSortDirections):
            raise TypeError("Для Каждого: неподдерживаемая коллекция формы")
        for item in collection:
            self.set_variable(node.name,item)
            if not (yield from self.iteration(node.body)): break

    def set_variable(self, variable, value):
        key = variable.casefold(); form = self._form_session.form
        if key in form._static and not (self.locals is not None and key in self.locals):
            form.set_member(variable, value); return
        return super().set_variable(variable, value)

    def argument(self, node):
        ungrouped = self.ungroup(node); form = self._form_session.form
        if isinstance(ungrouped, ast.Name) and ungrouped.name.casefold() in form._static and not (self.locals is not None and ungrouped.name.casefold() in self.locals):
            # !todo Native form-attribute non-Val crossing/copyout needs its own proof.
            raise TypeError("Форма: передача реквизита без Знач пока не поддерживается")
        if (isinstance(ungrouped, ast.Attribute) and isinstance(ungrouped.object, ast.Name)
                and ungrouped.object.name.casefold() in ('thisobject','этотобъект','items','элементы','commands','команды')):
            receiver = yield from self.receiver(ungrouped.object)
            if receiver is form or receiver is form.items or receiver is form.commands:
                receiver.get_member(ungrouped.name)
                return Reference(lambda: receiver.get_member(ungrouped.name), lambda v: receiver.set_member(ungrouped.name,v))
        return (yield from super().argument(node))


class FormSession:
    """One trusted module and one form; no global registry, arbitrary eval or GUI.

    Events run synchronously in arrival order. Nested/reentrant dispatch rejects;
    the transport owns queuing, not a second concurrent interpreter execution.
    Exceptions retain completed BSL mutations and increment revision: clients
    must resynchronize, never assume a transaction rollback.
    """
    def __init__(self, source, *, attributes=(), initial_values=None, bindings=None, output=None, database_context=None, application_actions=()):
        text(source, MAX_SOURCE)
        if type(attributes) not in (tuple,list) or len(attributes)>MAX_ATTRIBUTES:
            raise ValueError('Форма: слишком много реквизитов')
        if bindings is None: bindings = {}
        if type(bindings) is not dict or len(bindings)>4: raise ValueError('Форма: неверные события')
        if initial_values is None: initial_values = {}
        if type(initial_values) is not dict or len(initial_values)>MAX_ATTRIBUTES: raise ValueError('Форма: неверные начальные данные')
        if type(application_actions) is not tuple or len(application_actions) > 64:
            raise ValueError('Форма: неверные действия приложения')
        self._application_actions = {}
        attribute_names = {a.name.casefold() for a in attributes if type(a) is BSLFormAttribute}
        for action in application_actions:
            if (type(action) is not FormApplicationAction or not callable(action.callback)
                    or action.applied is not None and not callable(action.applied)):
                raise TypeError('Форма: требуется связанное действие приложения')
            key = name(action.command).casefold(); name(action.handler)
            if key in self._application_actions:
                raise ValueError('Форма: повторное действие приложения')
            for members in (action.inputs, action.outputs):
                if type(members) is not tuple or len(members) > MAX_ATTRIBUTES:
                    raise ValueError('Форма: неверная схема действия приложения')
                keys = tuple(name(member).casefold() for member in members)
                if len(set(keys)) != len(keys) or not set(keys) <= attribute_names:
                    raise ValueError('Форма: неизвестные реквизиты действия приложения')
            self._application_actions[key] = action
        self._output = output; self._messages = []
        self.closed = False; self.state = 'created'; self.revision = 0
        self._busy = False; self._steps = 0; self._events = 0
        self._gate = Lock(); self._allocated = 0
        self.form = BSLClientApplicationForm(self)
        self.interpreter = _FormInterpreter(self, self._record_message, database_context=database_context)
        program = parse(source, '<form-module>', compilation_profile=self.interpreter.compilation_profile)
        if len(program)>MAX_HANDLERS*2 or any(not isinstance(node,(ast.Routine,ast.Var)) for node in program):
            raise ValueError('Форма: модуль допускает только объявления подпрограмм и переменных')
        if any(isinstance(n,ast.Routine) and n.is_async for n in program):
            raise ValueError('Форма: асинхронные обработчики пока не поддерживаются')
        self.reserved_names = {'thisobject','этотобъект','items','элементы','commands','команды','title','заголовок'}
        self.reserved_names.update(self.form._methods)
        self.reserved_names.update(n.name.casefold() for n in program if isinstance(n,ast.Routine))
        self.reserved_names.update(x.casefold() for n in program if isinstance(n,ast.Var) for x in n.names)
        self._busy = True
        try:
            self.interpreter.execute_program(program)
            for attr in attributes:
                if type(attr) is not BSLFormAttribute or attr.name.casefold() in self.reserved_names or attr.name.casefold() in self.form._attributes:
                    raise ValueError('Форма: неверный или повторный реквизит')
                key = attr.name.casefold()
                if sum(len(x) for x in self.form._data.values() if type(x) is str) + int(attr.value_type.string_qualifiers.length) > MAX_TOTAL_TEXT:
                    raise ValueError("Форма: превышен предел данных")
                self.form._attributes[key] = attr._copy()
                self.form._data[key] = scalar(attr.value_type.adjust_value())
                self.form._static.add(key)
            for key, value in initial_values.items():
                key = name(key)
                if key.casefold() not in self.form._static: raise ValueError("Форма: неизвестный начальный реквизит")
                self.form.set_member(key,value)
            for event, handler in bindings.items():
                event = name(event).casefold(); event = self.form.EVENT_NAMES.get(event,event)
                if event not in self.form.EVENTS: raise ValueError('Форма: неизвестное событие')
                self._bind(name(handler), *self.form.EVENTS[event]); self.form.actions[event] = handler
        finally: self._busy = False

    def _record_message(self, message):
        text(message,4096)
        if len(self._messages)>=64: raise FormLimitError('Форма: превышен предел сообщений')
        self._messages.append(message)
        if self._output is not None: self._output(message)

    @property
    def messages(self):
        return tuple(self._messages)

    def _bind(self, handler, side, arity):
        registry = self.interpreter.server_routines if side=='server' else self.interpreter.routines
        routine = registry.get(handler.casefold())
        if (routine is None or routine.is_function or routine.is_async or routine.is_dual or
                not routine.module_context or routine.execution_context != side or len(routine.parameters)!=arity):
            raise ValueError('Форма: обработчик отсутствует или имеет неподдерживаемую сигнатуру')
        return routine

    def _invoke(self, handler, side, arguments):
        routine = self._bind(handler, side, len(arguments))
        interpreter = (self.interpreter._new_server_activation() if side == 'server' else self.interpreter)
        # Host-created slots only, never renderer-selected name or generated AST.
        slots = list(arguments); bindings = {}
        for index, parameter in enumerate(routine.parameters):
            bindings[parameter.name.casefold()] = (slots[index] if parameter.by_value else
                Reference(lambda i=index: slots[i], lambda v,i=index: slots.__setitem__(i,v)))
        def execute():
            previous = interpreter.locals
            interpreter.locals = bindings
            interpreter._context_stack.append(side)
            interpreter._module_context_stack.append(True)
            try:
                try: yield from interpreter.block(routine.body)
                except _Return: pass
            finally:
                interpreter._module_context_stack.pop(); interpreter._context_stack.pop()
                interpreter.locals = previous
        with target_context(interpreter.native_target), localcontext():
            interpreter._scheduler.run_inline(execute())
        return slots

    def _application_action(self, command):
        action = self._application_actions.get(command.name.casefold())
        if action is None:
            return
        if command.action.casefold() != action.handler.casefold():
            raise ValueError('Форма: привязка действия приложения изменена')
        inputs = tuple((key, scalar(self.form.get_member(key))) for key in action.inputs)
        result = action.callback(inputs)
        if type(result) is not FormActionResult or type(result.values) is not tuple or len(result.values) > len(action.outputs):
            raise TypeError('Форма: неверный результат действия приложения')
        allowed = {key.casefold() for key in action.outputs}; changes = {}
        for pair in result.values:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError('Форма: неверный реквизит результата')
            key, value = pair; key = name(key).casefold()
            if key not in allowed or key in changes:
                raise ValueError('Форма: результат вне связанной схемы')
            attribute = self.form._attributes[key]
            changes[key] = scalar(attribute.value_type.adjust_value(scalar(value)))
        total = sum(len(value) for key, value in self.form._data.items()
                    if key not in changes and type(value) is str)
        total += sum(len(value) for value in changes.values() if type(value) is str)
        if total > MAX_TOTAL_TEXT:
            raise ValueError('Форма: превышен предел данных')
        # Shrink first so every intermediate text total also fits the validated
        # final bound. No handlers/observers run between these ordinary setters.
        def growth(pair):
            key, value = pair
            old = self.form.get_member(key)
            return (len(value) if type(value) is str else 0) - (len(old) if type(old) is str else 0)
        for key, value in sorted(changes.items(), key=growth):
            self.form.set_member(key, value)
        # This acknowledgement is fixed by trusted registration, not returned in
        # the patch or selected by the renderer. Failed patch => no adoption.
        if action.applied is not None:
            action.applied()

    def _event(self, event, arguments):
        handler = self.form.actions.get(event)
        return arguments if not handler else self._invoke(handler, self.form.EVENTS[event][0], arguments)

    def _begin(self, revision):
        if not self._gate.acquire(blocking=False): raise ValueError('Форма: обработчик уже исполняется')
        try:
            if self._busy or self.closed: raise ValueError('Форма: закрыта или обработчик уже исполняется')
            if type(revision) is not int or revision != self.revision: raise ValueError('Форма: устаревшая версия')
            if self._events >= MAX_EVENTS: raise FormLimitError('Форма: превышен предел событий')
            self._events += 1; self._steps = 0; self._messages = []; self._busy = True
        except BaseException:
            self._gate.release(); raise

    def open(self):
        if self.state != 'created': raise ValueError('Форма уже открывалась')
        self._begin(0)
        try:
            created = self._event('oncreateatserver', [False,True])
            if type(created[0]) is not bool: raise TypeError('Форма: Отказ должен быть Булево')
            if created[1] is not True: raise ValueError('Форма: отключение стандартного создания пока не поддерживается')
            if created[0]: self.closed = True; self.state = 'cancelled'
            else:
                opened = self._event('onopen', [False])
                if type(opened[0]) is not bool: raise TypeError('Форма: Отказ должен быть Булево')
                if opened[0]: self.closed = True; self.state = 'cancelled'
                else: self.state = 'open'
        except BaseException:
            self.closed = True; self.state = 'failed'; raise
        finally:
            self._busy = False; self.revision += 1; self._gate.release()
        return self.snapshot()

    def dispatch(self, event, *, revision, control='', value=None):
        if type(event) is not str or event not in ('change','command','close'):
            raise ValueError('Форма: недопустимое событие')
        if self.state != 'open': raise ValueError('Форма не открыта')
        if event != 'close': name(control)
        if event == 'change': scalar(value)
        self._begin(revision)
        try:
            item = command = None
            if event != 'close':
                item = self.form.items._values.get(control.casefold())
                expected = BSLFormField if event=='change' else BSLFormButton
                if type(item) is not expected or not item.visible or not item.enabled or item._removed:
                    raise ValueError('Форма: недоступный элемент')
                if event == 'change':
                    if item.read_only or not item.data_path: raise ValueError('Форма: поле недоступно для ввода')
                else:
                    command = self.form.commands._values.get(item.command_name.casefold())
                    if command is None or not command.action: raise ValueError('Форма: команда не привязана')
                    action = self._application_actions.get(command.name.casefold())
                    if action is not None and command.action.casefold() != action.handler.casefold():
                        raise ValueError('Форма: привязка действия приложения изменена')
        except BaseException:
            self._busy = False; self._gate.release(); raise
        try:
            if event=='close':
                result = self._event('beforeclose', [False,False,'',True])
                if type(result[0]) is not bool: raise TypeError('Форма: Отказ должен быть Булево')
                if result[3] is not True: raise ValueError('Форма: отключение стандартного закрытия пока не поддерживается')
                if not result[0]:
                    self._event('onclose', [False]); self.closed = True; self.state = 'closed'
            else:
                if event=='change':
                    self.form.set_member(item.data_path,value)
                    if item.action: self._invoke(item.action,'client',[item])
                else:
                    self._invoke(command.action,'client',[command])
                    self._application_action(command)
        finally:
            self.revision += 1; self._busy = False; self._gate.release()
        return self.snapshot()

    def snapshot(self):
        if self._busy: raise ValueError("Форма: снимок во время обработчика недоступен")
        form = self.form
        # Detached immutable scalar records, not Python/BSL object handles.
        items = tuple((x.name, 'button' if type(x) is BSLFormButton else 'field',x.title,
                       x.visible,x.enabled,x.read_only,
                       x.command_name if type(x) is BSLFormButton else x.data_path)
                      for x in form.items._values.values())
        commands = tuple((x.name,x.title) for x in form.commands._values.values())
        return FormSnapshot(self.revision,self.state,form.title,
                            tuple((a.name,form._data[k]) for k,a in form._attributes.items()),items,commands,
                            tuple((x.name,x.view.value[0]) for x in form.items._values.values()
                                  if type(x) is BSLFormField))

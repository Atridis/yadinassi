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
                         BSLFormButton, BSLFormTable, BSLFormGroup, BSLFormCommand, FORM_FIELD_VIEWS,
                         MAX_ATTRIBUTES, MAX_TOTAL_TEXT, name, scalar, text)

from .form_tables import (FormTableSchema, BSLFormDataCollection, MAX_TABLES,
                          validate_table_data, table_text_size)

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
class FormServerBinding:
    """Host-owned, zero-argument callback retained across fresh server activations.

    Only a scalar result can reach BSL. No callback or object is wire-selected.
    The trusted callback receives the owning session, never a renderer object.
    """
    name: str
    callback: object


@dataclass(frozen=True)
class FormSnapshot:
    revision: int
    state: str
    title: str
    attributes: tuple
    items: tuple
    commands: tuple
    item_views: tuple = ()
    tables: tuple = ()
    selections: tuple = ()


class _FormInterpreter(Interpreter):
    def _capture_form_callback(self, receiver):
        session = self._form_session
        enrollment = getattr(session, '_owned_form_enrollment', None)
        if receiver is not session.form or enrollment is None:
            return None
        session.form._check()
        if self is not session.interpreter or self.execution_context != 'client':
            raise ValueError('self-form callback requires its client context')
        from .callbacks import _FormCallbackTarget
        family = self._family_owner
        return _FormCallbackTarget(receiver, self, family, family._family_generation, enrollment)

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
        child = _FormInterpreter(self._form_session, self.output, encoding=self.encoding,
                                native_target=self.native_target, database_context=self.database_context,
                                compilation_profile=self.compilation_profile, family_owner=self._family_owner)
        enroll = getattr(self._form_session, '_reference_enroll_activation', None)
        if enroll is not None:
            enroll(child)
        return child

    def _visit(self, node):
        session = self._form_session
        session._steps += 1
        if session._steps > MAX_STEPS: raise FormLimitError('Форма: превышен предел исполнения события')
        return (yield from super()._visit(node))

    def visit_Name(self, node):
        key = node.name.casefold()
        if self.locals is not None and key in self.locals:
            return super().visit_Name(node)
        if key in ('parameters', 'параметры') and hasattr(self._form_session, '_parameters'):
            self._form_session.form._check()
            return self._form_session._parameters
        if key in ('видполяформы','formfieldtype'):
            return FORM_FIELD_VIEWS
        form = self._form_session.form
        if key in ('thisobject','этотобъект','items','элементы','commands','команды') or key in form._static or key in form._tables:
            form._check()
            if key in ('thisobject','этотобъект'): return form
            if key in ('items','элементы'): return form.items
            if key in ('commands','команды'): return form.commands
            return form.get_member(node.name)
        return super().visit_Name(node)

    def visit_Index(self, node):
        # Evaluate the receiver once. Keep the ordinary collection rules intact.
        from . import runtime
        value = yield from self._visit(node.object)
        from .source_manager_modules import SourceManagers
        if type(value) is SourceManagers:
            value.authorize(self)
            return value.member(self, (yield from self._visit(node.index)))
        if type(value) is BSLFormDataCollection:
            return value.get_index((yield from self._visit(node.index)))
        if type(value) in (runtime.BSLChars, runtime.BSLCatalogMetadataCollection,
                           runtime.BSLCatalogs, runtime.BSLDocumentMetadataCollection,
                           runtime.BSLDocuments):
            return value.get_index((yield from self._visit(node.index)))
        if not isinstance(value, runtime._COLLECTIONS):
            raise TypeError('Индексирование поддерживается только для коллекций')
        index = yield from self._visit(node.index)
        if isinstance(value, (runtime.BSLFixedMap, *runtime._TABLE_COLLECTIONS)):
            return value.get_index(index)
        return value.get(index)

    def visit_ForEach(self, node):
        from .form_model import BSLFormItems, BSLFormCommands
        collection = yield from self._visit(node.collection)
        if type(collection) in (BSLFormItems, BSLFormCommands, BSLFormDataCollection):
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
        if (key in form._static or key in form._tables) and not (self.locals is not None and key in self.locals):
            form.set_member(variable, value); return
        return super().set_variable(variable, value)

    def argument(self, node):
        ungrouped = self.ungroup(node); form = self._form_session.form
        if isinstance(ungrouped, ast.Name) and (ungrouped.name.casefold() in form._static or ungrouped.name.casefold() in form._tables) and not (self.locals is not None and ungrouped.name.casefold() in self.locals):
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
    def __init__(self, source, *, attributes=(), tables=(), initial_values=None, bindings=None, output=None, database_context=None, application_actions=(), server_bindings=(), parameters=None, interpreter_factory=None, reference_scope=None):
        if type(attributes) not in (tuple,list) or len(attributes)>MAX_ATTRIBUTES:
            raise ValueError('Форма: слишком много реквизитов')
        if type(tables) is not tuple or len(tables) > MAX_TABLES or any(type(t) is not FormTableSchema for t in tables):
            raise ValueError('Форма: неверные таблицы')
        if bindings is None: bindings = {}
        if type(bindings) is not dict or len(bindings)>4: raise ValueError('Форма: неверные события')
        if initial_values is None: initial_values = {}
        if type(initial_values) is not dict or len(initial_values)>MAX_ATTRIBUTES: raise ValueError('Форма: неверные начальные данные')
        if type(application_actions) is not tuple or len(application_actions) > 64:
            raise ValueError('Форма: неверные действия приложения')
        if (type(server_bindings) is not tuple or len(server_bindings) > 16 or
                any(type(binding) is not FormServerBinding or not callable(binding.callback)
                    for binding in server_bindings)):
            raise TypeError('trusted server bindings required')
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
        self._event_phase = None
        self._completion_active = False
        self._owned_form_enrollment = None
        self._owned_close = None
        self._busy = False; self._steps = 0; self._events = 0
        self._gate = Lock(); self._allocated = 0
        from .form_references import FormReferenceScope
        if reference_scope is not None and type(reference_scope) is not FormReferenceScope:
            raise TypeError("explicit form reference scope required")
        self.reference_scope = reference_scope
        if reference_scope is not None: reference_scope.attach(self)
        self.form = BSLClientApplicationForm(self)
        factory = _FormInterpreter if interpreter_factory is None else interpreter_factory
        from .form_program import FormSideProgram
        profile_options = ({'compilation_profile': source.compilation_profile}
                           if type(source) is FormSideProgram and source.compilation_profile != 'standalone' else {})
        self.interpreter = factory(self, self._record_message, database_context=database_context, **profile_options)
        if not isinstance(self.interpreter, _FormInterpreter) or self.interpreter._form_session is not self:
            raise TypeError("form interpreter factory returned an invalid interpreter")
        from .form_program import admitted_program
        program = admitted_program(source, compilation_profile=self.interpreter.compilation_profile)
        if len(program)>MAX_HANDLERS*2 or any(not isinstance(node,(ast.Routine,ast.Var)) for node in program):
            raise ValueError('Форма: модуль допускает только объявления подпрограмм и переменных')
        if any(isinstance(n,ast.Routine) and n.is_async for n in program):
            raise ValueError('Форма: асинхронные обработчики пока не поддерживаются')
        self.reserved_names = {'thisobject','этотобъект','items','элементы','commands','команды','title','заголовок','parameters','параметры','openform','открытьформу'}
        self.reserved_names.update(self.form._methods)
        if self.interpreter._configuration_runtime is not None:
            self.reserved_names.update(self.interpreter._configuration_runtime.reserved_form_names)
        self.reserved_names.update(n.name.casefold() for n in program if isinstance(n,ast.Routine))
        self.reserved_names.update(x.casefold() for n in program if isinstance(n,ast.Var) for x in n.names)
        for binding in server_bindings:
            key = name(binding.name).casefold()
            if (key in self.reserved_names or key in attribute_names or key in self.interpreter.functions
                    or key in {table.name.casefold() for table in tables}):
                raise ValueError('server binding name already bound')
            self.reserved_names.add(key)
            def make_callback(owned):
                def invoke():
                    self.form._check(True)
                    return scalar(owned.callback(self))
                return invoke
            self.interpreter.functions[key] = HostFunction(binding.name, make_callback(binding))
        self._busy = True
        try:
            self.interpreter.execute_program(program)
            for identity, schema in enumerate(tables, 1):
                key = schema.name.casefold()
                if key in self.reserved_names or key in self.form._tables:
                    raise ValueError('Форма: неверная или повторная таблица')
                self.form._tables[key] = BSLFormDataCollection(self.form, schema, identity)
            for attr in attributes:
                if type(attr) is not BSLFormAttribute or attr.name.casefold() in self.reserved_names or attr.name.casefold() in self.form._attributes or attr.name.casefold() in self.form._tables:
                    raise ValueError('Форма: неверный или повторный реквизит')
                key = attr.name.casefold()
                from .form_references import is_reference
                length = 0 if is_reference(attr.value_type) else int(attr.value_type.string_qualifiers.length)
                if sum(len(x) for x in self.form._data.values() if type(x) is str) + length > MAX_TOTAL_TEXT:
                    raise ValueError("Форма: превышен предел данных")
                self.form._attributes[key] = attr._copy()
                from .form_references import adjust, require_scope
                require_scope(attr.value_type, self)
                self.form._data[key] = adjust(attr.value_type)
                self.form._static.add(key)
            validate_table_data(self.form)
            for key, value in initial_values.items():
                key = name(key)
                if key.casefold() not in self.form._static: raise ValueError("Форма: неизвестный начальный реквизит")
                self.form.set_member(key,value)
            for event, handler in bindings.items():
                event = name(event).casefold(); event = self.form.EVENT_NAMES.get(event,event)
                if event not in self.form.EVENTS: raise ValueError('Форма: неизвестное событие')
                self._bind(name(handler), *self.form.EVENTS[event]); self.form.actions[event] = handler
        finally: self._busy = False
        if parameters is not None:
            from .configuration_forms import bind_parameters
            bind_parameters(self, parameters)

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
        if total + table_text_size(self.form) > MAX_TOTAL_TEXT:
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
        previous = self._event_phase
        self._event_phase = event
        try:
            return arguments if not handler else self._invoke(handler, self.form.EVENTS[event][0], arguments)
        finally:
            self._event_phase = previous

    def request_close(self, result=None):
        self.form._check()
        if (self._owned_close is None or self.interpreter.execution_context != 'client'
                or self._completion_active or self._event_phase is not None or self.state != 'open'):
            raise ValueError('Close(result) requires an active owned child command')
        self._owned_close(result)

    def dispatch_completion(self, description, result, *, revision, result_argument=True):
        """Trusted queued event. Never callable by a browser-selected handler."""
        if self._owned_form_enrollment is None or self.state != 'open':
            raise ValueError('owned live form required')
        if type(result_argument) is not bool:
            raise ValueError('explicit completion argument contract required')
        routine, owner = self.interpreter.callback_target(description, form_arity=2 if result_argument else 1)
        if owner is not self.interpreter or description.module is not self.form:
            raise ValueError('completion target differs from owner')
        self._begin(revision)
        self._completion_active = True
        try:
            with target_context(self.interpreter.native_target), localcontext():
                self.interpreter._scheduler.run_inline(
                    self.interpreter.dispatch_callback(description, result, routine.token,
                                                       result_argument=result_argument))
        finally:
            self._completion_active = False
            self.revision += 1; self._busy = False; self._gate.release()
        return self.snapshot()

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

    def dispatch(self, event, *, revision, control='', value=None, row=None, column=''):
        if type(event) is not str or event not in ('change','command','close','cell','select'):
            raise ValueError('Форма: недопустимое событие')
        if self.state != 'open': raise ValueError('Форма не открыта')
        if event != 'close': name(control)
        if event in ('change', 'cell'): scalar(value)
        if event in ('cell', 'select'):
            if row is not None and (type(row) is not int or not 1 <= row <= 4096):
                raise ValueError('ТаблицаФормы: неверный идентификатор строки')
            if event == 'cell':
                if row is None: raise ValueError('ТаблицаФормы: строка не выбрана')
                name(column)
        self._begin(revision)
        try:
            item = command = None
            if event != 'close':
                item = self.form.items._values.get(control.casefold())
                expected = BSLFormTable if event in ('cell', 'select') else BSLFormField if event=='change' else BSLFormButton
                from .form_layout import effective_state
                visible, enabled, readonly = effective_state(item) if type(item) is expected else (False, False, True)
                if type(item) is not expected or not visible or not enabled or item._removed:
                    raise ValueError('Форма: недоступный элемент')
                if event == 'change':
                    if readonly or not item.data_path: raise ValueError('Форма: поле недоступно для ввода')
                elif event in ('cell', 'select'):
                    table = item._table()
                    selected = None if row is None else table._lookup_id(row)
                    if event == 'cell':
                        col = next((c for c in table.schema.columns if c.name.casefold() == column.casefold()), None)
                        if readonly or col is None or col.read_only:
                            raise ValueError('ТаблицаФормы: ячейка недоступна для ввода')
                else:
                    if readonly and self.form._layout: raise ValueError('Форма: команда недоступна')
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
                elif event in ('cell', 'select'):
                    if event == 'cell': selected.set_member(column, value)
                    item.current_row = row
                    if event == 'cell' and item.action: self._invoke(item.action, 'client', [item])
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
        from .form_layout import effective_state
        items = tuple((x.name, 'button' if type(x) is BSLFormButton else 'table' if type(x) is BSLFormTable else 'group' if type(x) is BSLFormGroup else 'field',x.title,
                       *effective_state(x),
                       x.command_name if type(x) is BSLFormButton else x.data_path)
                      for x in form.items._values.values())
        commands = tuple((x.name,x.title) for x in form.commands._values.values())
        return FormSnapshot(self.revision,self.state,form.title,
                            tuple((a.name,form._data[k]) for k,a in form._attributes.items()),items,commands,
                            tuple((x.name,x.view.value[0]) for x in form.items._values.values()
                                  if type(x) is BSLFormField),
                            tuple(table._snapshot() for table in form._tables.values()),
                            tuple((x.name, x.current_row) for x in form.items._values.values()
                                  if type(x) is BSLFormTable))

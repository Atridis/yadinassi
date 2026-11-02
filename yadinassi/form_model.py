"""Bounded programmatic managed-form model; rendering is deliberately external.

Native semantics are provisional until the managed-form oracle is acquired.
!todo Nested form data/tables, standard persistence commands and layout are not
part of this first scalar slice. No network, file or database write capability.
"""
from decimal import Decimal
from enum import Enum
from .values import BSLObject, BSLArray, BSLType, NULL
from .dates import BSLDate
from .type_descriptions import BSLTypeDescription
from .file_io import _FileMethods, _methods

MAX_ATTRIBUTES = 128
MAX_ITEMS = 128
MAX_COMMANDS = 64
MAX_TEXT = 65536
MAX_NAME = 128
MAX_TOTAL_TEXT = 262144
MAX_ALLOCATED = 1024


def text(value, limit=MAX_TEXT):
    if type(value) is not str or len(value) > limit or '\x00' in value:
        raise ValueError('Форма: недопустимая строка или превышен предел')
    return value


def name(value):
    value = text(value, MAX_NAME)
    if not value or not value.isidentifier():
        raise ValueError('Форма: недопустимое имя')
    return value


def scalar(value):
    if value is None or value is NULL or type(value) in (bool, BSLDate):
        return value
    if type(value) is str:
        return text(value)
    if type(value) is Decimal:
        if not value.is_finite() or value.__sizeof__() > 2048:
            raise ValueError('Форма: превышен предел числа')
        parts = value.as_tuple()
        if len(parts.digits) > 128 or abs(parts.exponent) > 4096:
            raise ValueError('Форма: превышен предел числа')
        return value
    # !todo Scoped CatalogRef transport needs native form-context measurements.
    raise TypeError('Форма: поддерживаются только скалярные данные')


class BSLFormAttribute(BSLObject):
    def __init__(self, attribute_name, value_type, path='', title='', saved_data=False):
        self._session = None
        self.name = name(attribute_name)
        if type(value_type) is not BSLTypeDescription:
            raise TypeError('РеквизитФормы: требуется ОписаниеТипов')
        allowed = (BSLType.STRING, BSLType.NUMBER, BSLType.BOOLEAN, BSLType.DATE)
        if len(value_type.types) != 1 or value_type.types[0] not in allowed:
            raise ValueError('РеквизитФормы: пока поддерживается один скалярный тип')
        if (value_type.string_qualifiers.length > MAX_TEXT or
                value_type.number_qualifiers.digits > 128 or value_type.number_qualifiers.fraction_digits > 128):
            raise ValueError('РеквизитФормы: превышен предел квалификаторов')
        if text(path, MAX_NAME):
            raise ValueError('РеквизитФормы: вложенные реквизиты пока не поддерживаются')
        if type(saved_data) is not bool:
            raise TypeError('РеквизитФормы: ожидается Булево')
        if saved_data:
            raise ValueError('РеквизитФормы: сохраняемые данные/стандартная запись пока не поддерживаются')
        self.value_type, self.title, self.saved_data = value_type, text(title, 1024), saved_data

    def _copy(self, session=None):
        result = BSLFormAttribute(self.name,self.value_type,'',self.title,self.saved_data)
        result._session = session
        return result
    def _check(self):
        if self._session is not None: self._session.form._check(True)
    def set_member(self, member, value):
        self._check()
        values = [self.name,self.value_type,'',self.title,self.saved_data]
        indexes = {'name':0,'имя':0,'type':1,'тип':1,'path':2,'путь':2,
                   'title':3,'заголовок':3,'storeddata':4,'сохраняемыеданные':4}
        if member.casefold() not in indexes: return super().set_member(member,value)
        values[indexes[member.casefold()]] = value
        candidate = BSLFormAttribute(*values)
        self.name,self.value_type,self.title,self.saved_data = candidate.name,candidate.value_type,candidate.title,candidate.saved_data
    def get_member(self, member):
        self._check()
        fields = {'имя': self.name, 'name': self.name, 'тип': self.value_type,
                  'type': self.value_type, 'путь': '', 'path': '', 'заголовок': self.title,
                  'title': self.title, 'сохраняемыеданные': self.saved_data,
                  'storeddata': self.saved_data}
        if member.casefold() in fields: return fields[member.casefold()]
        return super().get_member(member)


class BSLFormFieldView(Enum):
    INPUT = ('InputField', 'ПолеВвода')
    CHECKBOX = ('CheckBoxField', 'ПолеФлажка')
    LABEL = ('LabelField', 'ПолеНадписи')


class _FieldViews(BSLObject):
    def get_member(self, member):
        for view in BSLFormFieldView:
            if member.casefold() in [v.casefold() for v in view.value]: return view
        return super().get_member(member)


FORM_FIELD_VIEWS = _FieldViews()


class _Owned(_FileMethods):
    def __init__(self, form): self._form, self._removed = form, False
    def _check(self, server=False):
        self._form._check(server)
        if self._removed: raise ValueError('Форма: объект удален')


class BSLFormCommand(_Owned):
    def __init__(self, form, command_name):
        super().__init__(form)
        self.name, self.title, self.action = command_name, '', ''
    def get_member(self, member):
        self._check()
        fields = {'name': self.name, 'имя': self.name, 'title': self.title,
                  'заголовок': self.title, 'action': self.action, 'действие': self.action}
        if member.casefold() in fields: return fields[member.casefold()]
        return super().get_member(member)
    def set_member(self, member, value):
        self._check(True)
        key = member.casefold()
        if key in ('action', 'действие'):
            self._form._bind(value, 'client', 1)
            self.action = value
        elif key in ('title', 'заголовок'): self.title = text(value, 1024)
        else: return super().set_member(member, value)


class BSLFormField(_Owned):
    _methods = _methods(('set_action', False, 'SetAction УстановитьДействие'), ('get_action', True, 'GetAction ПолучитьДействие'))
    def __init__(self, form, item_name):
        super().__init__(form)
        self.name, self.title, self.data_path = item_name, '', ''
        self.visible, self.enabled, self.read_only = True, True, False
        self.view = BSLFormFieldView.INPUT
        self.action = ''
    def set_action(self, event_name, handler):
        self._check(True)
        if text(event_name, MAX_NAME).casefold() not in ('onchange', 'приизменении'):
            raise ValueError('ПолеФормы: событие пока не поддерживается')
        # !todo Native handler Element argument convention is an acquisition gate.
        self._form._bind(handler, 'client', 1)
        self.action = handler
    def get_action(self, event_name):
        self._check(True)
        if text(event_name, MAX_NAME).casefold() not in ('onchange', 'приизменении'):
            raise ValueError('ПолеФормы: событие пока не поддерживается')
        return self.action
    def get_member(self, member):
        self._check()
        key = member.casefold()
        if key in ('datapath', 'путькданным'):
            self._check(True)
            return self.data_path
        fields = {'name': self.name, 'имя': self.name, 'title': self.title,
                  'заголовок': self.title, 'visible': self.visible, 'видимость': self.visible,
                  'enabled': self.enabled, 'доступность': self.enabled,
                  'readonly': self.read_only, 'толькопросмотр': self.read_only,
                  'type': self.view, 'вид': self.view}
        if key in fields: return fields[key]
        return super().get_member(member)
    def set_member(self, member, value):
        self._check()
        key = member.casefold()
        if key in ('datapath', 'путькданным'):
            self._check(True)
            if self.data_path: raise ValueError('ПолеФормы: ПутьКДанным уже задан')
            value = name(value)
            if value.casefold() not in self._form._attributes: raise ValueError('ПолеФормы: реквизит не найден')
            self.data_path = value
        elif key in ('title', 'заголовок'): self.title = text(value, 1024)
        elif key in ('visible', 'видимость', 'enabled', 'доступность', 'readonly', 'толькопросмотр'):
            if type(value) is not bool: raise TypeError('ПолеФормы: ожидается Булево')
            attr = {'visible':'visible','видимость':'visible','enabled':'enabled','доступность':'enabled','readonly':'read_only','толькопросмотр':'read_only'}[key]
            setattr(self, attr, value)
        elif key in ('type', 'вид'):
            if type(value) is not BSLFormFieldView: raise TypeError('ПолеФормы: ожидается ВидПоляФормы')
            if self.data_path: raise ValueError('ПолеФормы: изменение вида связанного поля пока не поддерживается')
            self.view = value
        else: return super().set_member(member, value)


class BSLFormButton(BSLFormField):
    _methods = {}
    def __init__(self, form, item_name):
        super().__init__(form, item_name)
        self.command_name = ''
    def get_member(self, member):
        if member.casefold() in ('commandname', 'имякоманды'):
            self._check(); return self.command_name
        return super().get_member(member)
    def set_member(self, member, value):
        if member.casefold() in ('commandname', 'имякоманды'):
            self._check(True); value = name(value)
            if value.casefold() not in self._form.commands._values: raise ValueError('КнопкаФормы: команда не найдена')
            self.command_name = value
        elif member.casefold() in ('datapath','путькданным','type','вид'):
            raise ValueError('КнопкаФормы: свойство не поддерживается')
        else: return super().set_member(member, value)


class BSLFormCollection(_Owned):
    _methods = _methods(('add', True, 'Add Добавить'), ('find', True, 'Find Найти'),
                        ('count', True, 'Count Количество'), ('delete', False, 'Delete Удалить'))
    def __init__(self, form, commands=False):
        super().__init__(form); self._values = {}; self._commands = commands
    def add(self, item_name, item_type=None, parent=None):
        self._check(True); item_name = name(item_name); key = item_name.casefold()
        limit = MAX_COMMANDS if self._commands else MAX_ITEMS
        if self._form._session._allocated >= MAX_ALLOCATED: raise ValueError("Форма: превышен предел созданных объектов")
        if key in self._values or len(self._values) >= limit: raise ValueError('Форма: повторное имя или превышен предел')
        if self._commands:
            if item_type is not None or parent is not None: raise TypeError('КомандыФормы: неверные параметры')
            item = BSLFormCommand(self._form, item_name)
        else:
            if parent is not None and parent is not self._form: raise ValueError('Форма: вложенные элементы пока не поддерживаются')
            if item_type is BSLType.FORM_FIELD: item = BSLFormField(self._form, item_name)
            elif item_type is BSLType.FORM_BUTTON: item = BSLFormButton(self._form, item_name)
            else: raise TypeError('Форма: поддерживаются ПолеФормы и КнопкаФормы')
        self._form._session._allocated += 1
        self._values[key] = item
        return item
    def find(self, item_name): self._check(); return self._values.get(name(item_name).casefold())
    def count(self): self._check(); return Decimal(len(self._values))
    def delete(self, item):
        self._check(True)
        if type(item) not in (BSLFormField, BSLFormButton, BSLFormCommand) or item._form is not self._form or self._values.get(item.name.casefold()) is not item:
            raise ValueError('Форма: чужой или удаленный объект')
        if self._commands and any(type(x) is BSLFormButton and x.command_name.casefold() == item.name.casefold() for x in self._form.items._values.values()):
            raise ValueError('Форма: команда используется кнопкой')
        del self._values[item.name.casefold()]; item._removed = True
    def get_member(self, member):
        self._check()
        if member.casefold() in self._values: return self._values[member.casefold()]
        return super().get_member(member)
    def __iter__(self): self._check(); return iter(tuple(self._values.values()))


class BSLFormItems(BSLFormCollection):
    pass


class BSLFormCommands(BSLFormCollection):
    def __init__(self, form): super().__init__(form, True)


class BSLClientApplicationForm(_Owned):
    _methods = _methods(('change_attributes', False, 'ChangeAttributes ИзменитьРеквизиты'),
                        ('get_attributes', True, 'GetAttributes ПолучитьРеквизиты'),
                        ('set_action', False, 'SetAction УстановитьДействие'))
    EVENTS = {'oncreateatserver': ('server', 2), 'onopen': ('client', 1),
              'beforeclose': ('client', 4), 'onclose': ('client', 1)}
    EVENT_NAMES = {'присозданиинасервере':'oncreateatserver','приоткрытии':'onopen',
                   'передзакрытием':'beforeclose','призакрытии':'onclose'}
    def __init__(self, session):
        self._session = session; self._attributes = {}; self._data = {}; self._static = set()
        self.items = BSLFormItems(self); self.commands = BSLFormCommands(self)
        self.actions = {}; self.title = ''
    def _check(self, server=False):
        if self._session.closed: raise ValueError('Форма закрыта')
        if not self._session._busy: raise ValueError('Форма: нет активного обработчика')
        if not self._session.interpreter._has_module_context: raise ValueError('Форма недоступна без контекста')
        if server and self._session.interpreter.execution_context != 'server': raise ValueError('Форма: операция доступна только на сервере')
    def _bind(self, handler, side, arity): return self._session._bind(name(handler), side, arity)
    def set_action(self, event_name, handler):
        self._check(True); event = text(event_name, MAX_NAME).casefold()
        event = self.EVENT_NAMES.get(event, event)
        if event not in self.EVENTS: raise ValueError('Форма: событие пока не поддерживается')
        self._bind(handler, *self.EVENTS[event]); self.actions[event] = handler
    def get_attributes(self, path=''):
        self._check(True)
        if text(path, MAX_NAME): raise ValueError('Форма: вложенные реквизиты пока не поддерживаются')
        result = BSLArray(); result.items = [a._copy(self._session) for a in self._attributes.values()]; return result
    def change_attributes(self, added=None, removed=None):
        self._check(True)
        for value in (added, removed):
            if value is not None and (type(value) is not BSLArray or len(value.items) > MAX_ATTRIBUTES): raise TypeError('Форма: ожидается ограниченный Массив')
        attrs = self._attributes.copy(); data = self._data.copy()
        for key in ([] if removed is None else removed.items):
            key = name(key).casefold()
            if key not in attrs or key in self._static: raise ValueError('Форма: реквизит нельзя удалить')
            if any(type(item) is BSLFormField and item.data_path.casefold() == key for item in self.items._values.values()): raise ValueError('Форма: реквизит связан с полем')
            del attrs[key]; del data[key]
        for attr in ([] if added is None else added.items):
            if type(attr) is not BSLFormAttribute: raise TypeError('Форма: требуется РеквизитФормы')
            key = attr.name.casefold()
            if key in attrs or key in self._session.reserved_names or len(attrs) >= MAX_ATTRIBUTES: raise ValueError('Форма: имя занято или превышен предел')
            default_length = int(attr.value_type.string_qualifiers.length)
            if sum(len(x) for x in data.values() if type(x) is str) + default_length > MAX_TOTAL_TEXT:
                raise ValueError("Форма: превышен предел данных")
            attrs[key] = attr._copy(); data[key] = scalar(attr.value_type.adjust_value())
        allocated = len([] if added is None else added.items)
        if self._session._allocated + allocated > MAX_ALLOCATED: raise ValueError("Форма: превышен предел созданных объектов")
        self._session._allocated += allocated
        self._attributes, self._data = attrs, data
    def get_member(self, member):
        self._check(); key = member.casefold()
        if key in self._data: return self._data[key]
        if key in ('items','элементы'): return self.items
        if key in ('commands','команды'): return self.commands
        if key in ('title','заголовок'): return self.title
        return _FileMethods.get_member(self, member)
    def set_member(self, member, value):
        self._check(); key = member.casefold()
        if key in self._attributes:
            scalar(value)
            value = scalar(self._attributes[key].value_type.adjust_value(value))
            total = sum(len(x) for k,x in self._data.items() if k != key and type(x) is str)
            if total + (len(value) if type(value) is str else 0) > MAX_TOTAL_TEXT: raise ValueError('Форма: превышен предел данных')
            self._data[key] = value
        elif key in ('title','заголовок'): self.title = text(value, 1024)
        else: return super().set_member(member, value)

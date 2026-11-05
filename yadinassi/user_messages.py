"""Structured user messages for a local host; no native GUI/dispatch claim.

The host owns delivery and any future UI navigation. Field/data paths are inert
strings here, never expressions to execute or paths to traverse automatically.
"""
from dataclasses import dataclass
from weakref import WeakKeyDictionary

from .catalog_types import BSLCatalogReference
from .unique_identifiers import BSLUUID
from .values import BSLObject, HostFunction

MAX_TEXT = 65536
MAX_PATH = 4096


def _text(value, maximum):
    if type(value) is not str:
        raise TypeError('СообщениеПользователю: ожидается Строка')
    if len(value) > maximum:
        raise ValueError('СообщениеПользователю: превышен предел строки Yadinassi')
    return value


def _key(value):
    if value is not None and type(value) is not BSLCatalogReference:
        raise TypeError('СообщениеПользователю: поддерживается ссылка справочника')
    return value


@dataclass(frozen=True, slots=True)
class UserMessageRecord:
    """Host-only property snapshot, not a wire DTO or navigation authority.

    data_key retains its existing runtime reference identity and callbacks. A UI
    adapter must resolve/validate its own database scope before exposing an ID.
    """
    text: str
    field: str
    data_path: str
    data_key: BSLCatalogReference | None
    target_id: BSLUUID | None


class UserMessageContext:
    """One logical execution family's delivery and instance-to-form bindings.

    bind_data/unbind_data are host APIs, not extra BSL globals. Bindings are weak
    and keyed by the actual detached object, not by its catalog reference.
    """
    def __init__(self, output, sink=None):
        if not callable(output) or sink is not None and not callable(sink):
            raise TypeError('UserMessage delivery requires a callable')
        self._output = output
        self._sink = sink
        self._paths = WeakKeyDictionary()

    def set_sink(self, sink):
        """Host-only delivery selection; None restores ordinary text output."""
        if sink is not None and not callable(sink):
            raise TypeError('UserMessage delivery requires a callable')
        self._sink = sink

    def bind_data(self, value, data_path):
        from .catalogs import BSLCatalogObject
        if type(value) is not BSLCatalogObject:
            raise TypeError('UserMessage binding requires a CatalogObject')
        data_path = _text(data_path, MAX_PATH)
        self._paths[value] = data_path

    def unbind_data(self, value):
        from .catalogs import BSLCatalogObject
        if type(value) is not BSLCatalogObject:
            raise TypeError('UserMessage binding requires a CatalogObject')
        self._paths.pop(value, None)

    def resolve(self, value):
        from .catalogs import BSLCatalogObject
        if type(value) is not BSLCatalogObject:
            raise TypeError('УстановитьДанные: поддерживается объект справочника')
        # Exact built-in receiver; this reads its detached buffer, not the DB.
        return _key(value.get_member('Ref')), self._paths.get(value, '')

    def publish(self, record):
        if self._sink is None:
            self._output(record.text)
        else:
            self._sink(record)


class BSLUserMessage(BSLObject):
    def __init__(self, context):
        if type(context) is not UserMessageContext:
            raise TypeError('UserMessage requires its host context')
        self._context = context
        self._text = ''
        self._field = ''
        self._data_path = ''
        self._data_key = None
        self._target_id = None

    def get_member(self, name):
        key = name.casefold()
        properties = {'text': '_text', 'текст': '_text',
                      'field': '_field', 'поле': '_field',
                      'datapath': '_data_path', 'путькданным': '_data_path',
                      'datakey': '_data_key', 'ключданных': '_data_key',
                      'targetid': '_target_id', 'идентификаторназначения': '_target_id'}
        if key in properties:
            return getattr(self, properties[key])
        if key in ('message', 'сообщить'):
            return HostFunction(name, self.message, returns_value=False)
        if key in ('setdata', 'установитьданные'):
            return HostFunction(name, self.set_data, returns_value=False)
        return super().get_member(name)

    def set_member(self, name, value):
        key = name.casefold()
        if key in ('text', 'текст'):
            self._text = _text(value, MAX_TEXT)
        elif key in ('field', 'поле'):
            self._field = _text(value, MAX_PATH)
        elif key in ('datapath', 'путькданным'):
            self._data_path = _text(value, MAX_PATH)
        elif key in ('datakey', 'ключданных'):
            self._data_key = _key(value)
        elif key in ('targetid', 'идентификаторназначения'):
            if value is not None and type(value) is not BSLUUID:
                raise TypeError('ИдентификаторНазначения: ожидается УникальныйИдентификатор')
            self._target_id = value
        else:
            super().set_member(name, value)

    def set_data(self, value):
        data_key, data_path = self._context.resolve(value)
        self._data_key, self._data_path = data_key, data_path

    def message(self):
        record = UserMessageRecord(self._text, self._field, self._data_path,
                                   self._data_key, self._target_id)
        self._context.publish(record)

    def __str__(self):
        raise TypeError('Строковое представление СообщениеПользователю пока не поддерживается')

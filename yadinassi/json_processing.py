"""Bounded JSON objects and collection conversion (no XDTO or callbacks)."""
from decimal import Decimal
from enum import Enum
import json
import os
import stat

from .values import BSLObject, HostFunction, BSLArray, BSLFixedArray
from .structures import BSLStructure, BSLFixedStructure
from .maps import BSLMap, BSLFixedMap

MAX_TEXT = 1_000_000
MAX_DEPTH = 128


def _text(value):
    if type(value) is not str:
        raise TypeError("JSON: ожидается Строка")
    if len(value) > MAX_TEXT:
        raise ValueError("JSON: превышен предел ресурсов Yadinassi")
    return value


def _open_regular(filename, encoding, *, writing=False):
    # Open nonblocking before inspecting the descriptor: reject devices/FIFOs
    # without hanging, and inspect the actual open file rather than a racy path.
    flags = (os.O_WRONLY | os.O_CREAT) if writing else os.O_RDONLY
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(filename, flags, 0o666)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("JSON: требуется обычный файл")
        if writing:
            # Validate the encoding before truncating an existing file.
            "".encode(encoding)
            os.ftruncate(fd, 0)
        stream = os.fdopen(fd, "w" if writing else "r", encoding=encoding, newline="")
        fd = None
        return stream
    finally:
        if fd is not None:
            os.close(fd)


class BSLJSONValueType(Enum):
    NONE = ("Ничего", "None")
    START_OBJECT = ("НачалоОбъекта", "ObjectStart")
    END_OBJECT = ("КонецОбъекта", "ObjectEnd")
    START_ARRAY = ("НачалоМассива", "ArrayStart")
    END_ARRAY = ("КонецМассива", "ArrayEnd")
    PROPERTY_NAME = ("ИмяСвойства", "PropertyName")
    STRING = ("Строка", "String")
    NUMBER = ("Число", "Number")
    BOOLEAN = ("Булево", "Boolean")
    NULL = ("Null", "Null")
    COMMENT = ("Комментарий", "Comment")

    def __str__(self):
        return self.value[0]


class BSLJSONValueTypes(BSLObject):
    def get_member(self, name):
        for item in BSLJSONValueType:
            if name.casefold() in tuple(n.casefold() for n in item.value):
                return item
        return super().get_member(name)


JSON_VALUE_TYPES = BSLJSONValueTypes()
T = BSLJSONValueType


class _Pairs(list):
    pass


def _load(text):
    # !todo Comment/non-standard JSON extensions and exact malformed-input
    # cursor locations require later native calibration; strict JSON is supported.
    def bad_constant(value):
        raise ValueError("JSON: недопустимое число")
    def parse_number(value):
        if len(value) > 4096:
            raise ValueError("JSON: превышен предел числа Yadinassi")
        number = Decimal(value)
        if not number.is_finite() or abs(number.adjusted()) > 4096:
            raise ValueError("JSON: превышен предел числа Yadinassi")
        return number
    try:
        return json.loads(text, parse_int=parse_number, parse_float=parse_number,
                          parse_constant=bad_constant, object_pairs_hook=_Pairs)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("JSON: некорректный документ") from error


def _tokens(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("JSON: превышена глубина Yadinassi")
    if type(value) is _Pairs:
        yield T.START_OBJECT, None
        for name, item in value:
            yield T.PROPERTY_NAME, name
            yield from _tokens(item, depth + 1)
        yield T.END_OBJECT, None
    elif type(value) is list:
        yield T.START_ARRAY, None
        for item in value:
            yield from _tokens(item, depth + 1)
        yield T.END_ARRAY, None
    else:
        kind = {str: T.STRING, Decimal: T.NUMBER, bool: T.BOOLEAN, type(None): T.NULL}[type(value)]
        yield kind, value


class BSLJSONReader(BSLObject):
    def __init__(self):
        self.close()

    def __str__(self):
        return "ЧтениеJSON"

    def set_string(self, value):
        self._source = _text(value)
        self._tokens = None
        self._position = -1
        self._current = (T.NONE, None)

    def open_file(self, filename, encoding="utf-8-sig"):
        filename = _text(filename)
        encoding = "UTF-8" if encoding is None else _text(encoding)
        code = encoding.casefold().replace("-", "")
        detect_utf16 = code == "utf16"
        if code in ("", "utf8", "utf8sig"):
            encoding = "utf-8-sig"
        elif code in ("utf16", "utf16le"):
            encoding = "utf-16-le"
        elif code == "utf16be":
            encoding = "utf-16-be"
        elif code in ("windows1251", "cp1251"):
            encoding = "cp1251"
        with _open_regular(filename, encoding) as stream:
            if detect_utf16 and stream.buffer.peek(2).startswith(b"\xfe\xff"):
                stream.reconfigure(encoding="utf-16-be")
            text = stream.read(MAX_TEXT + 1)
        if code in ("utf16", "utf16le", "utf16be") and text.startswith("\ufeff"):
            text = text[1:]
        self.set_string(text)

    def close(self):
        self._source = None
        self._tokens = None
        self._position = -1
        self._current = (T.NONE, None)

    def read(self):
        if self._source is None:
            raise ValueError("JSON: источник не открыт")
        if self._tokens is None:
            tokens = []
            for token in _tokens(_load(self._source)):
                if len(tokens) >= 100_000:
                    raise ValueError("JSON: превышен предел токенов Yadinassi")
                tokens.append(token)
            self._tokens = tokens
        self._position += 1
        if self._position >= len(self._tokens):
            self._current = (T.NONE, None)
            return False
        self._current = self._tokens[self._position]
        return True

    def skip(self):
        if self._current[0] in (T.START_OBJECT, T.START_ARRAY):
            depth = 1
            while depth and self.read():
                if self._current[0] in (T.START_OBJECT, T.START_ARRAY): depth += 1
                elif self._current[0] in (T.END_OBJECT, T.END_ARRAY): depth -= 1
        return self.read()

    def get_member(self, name):
        # !todo CurrentLine/CurrentPosition need source-offset tracking; neither
        # ordinary nor malformed-input positions are currently exposed.
        key = name.casefold()
        if key in ("типтекущегозначения", "currentvaluetype"):
            return None if self._current[0] is T.NONE else self._current[0]
        if key in ("текущеезначение", "currentvalue"):
            if self._current[0] in (T.NONE, T.START_OBJECT, T.END_OBJECT, T.START_ARRAY, T.END_ARRAY):
                raise ValueError("JSON: текущее значение недоступно")
            return self._current[1]
        methods = {"пропустить": (self.skip, True), "skip": (self.skip, True),
                   "установитьстроку": (self.set_string, False), "setstring": (self.set_string, False),
                   "открытьфайл": (self.open_file, False), "openfile": (self.open_file, False),
                   "закрыть": (self.close, False), "close": (self.close, False),
                   "прочитать": (self.read, True), "read": (self.read, True)}
        if key in methods:
            fn, returns = methods[key]
            return HostFunction(name, fn, returns_value=returns)
        return super().get_member(name)


def read_json(reader, read_to_map=False):
    # !todo Native date-name restoration, reviver callbacks and configurable
    # maximum nesting are not part of the current ordinary collection API.
    if type(reader) is not BSLJSONReader or type(read_to_map) is not bool:
        raise TypeError("ПрочитатьJSON: ожидаются ЧтениеJSON и Булево")
    if reader._current[0] is T.NONE and not reader.read():
        raise ValueError("JSON: ожидалось значение")

    def consume(depth):
        if depth > MAX_DEPTH:
            raise ValueError("JSON: превышена глубина Yadinassi")
        kind, value = reader._current
        if kind is T.START_OBJECT:
            result = BSLMap() if read_to_map else BSLStructure()
            while reader.read() and reader._current[0] is not T.END_OBJECT:
                if reader._current[0] is not T.PROPERTY_NAME:
                    raise ValueError("JSON: ожидалось имя свойства")
                key = reader._current[1]
                reader.read()
                result.insert(key, consume(depth + 1))
            return result
        if kind is T.START_ARRAY:
            result = BSLArray()
            while reader.read() and reader._current[0] is not T.END_ARRAY:
                result.add(consume(depth + 1))
            return result
        if kind in (T.STRING, T.NUMBER, T.BOOLEAN, T.NULL):
            return value
        raise ValueError("JSON: ожидалось значение")
    return consume(0)


def _quote(value):
    return json.dumps(_text(value), ensure_ascii=False).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _encode(value):
    parts, seen, size = [], set(), 0

    def append(text):
        nonlocal size
        size += len(text)
        if size > MAX_TEXT:
            raise ValueError("JSON: превышен предел ресурсов Yadinassi")
        parts.append(text)

    def encode(item, depth):
        if depth > MAX_DEPTH:
            raise ValueError("JSON: превышена глубина Yadinassi")
        kind = type(item)
        if item is None: append("null")
        elif kind is bool: append("true" if item else "false")
        elif kind is str: append(_quote(item))
        elif kind is Decimal:
            if not item.is_finite():
                raise ValueError("JSON: ожидается конечное число")
            if abs(item.adjusted()) > 4096 or len(item.as_tuple().digits) > 4096:
                raise ValueError("JSON: превышен предел числа Yadinassi")
            append(format(item, "f"))
        elif kind in (BSLArray, BSLFixedArray, BSLStructure, BSLFixedStructure, BSLMap, BSLFixedMap):
            if id(item) in seen:
                raise ValueError("JSON: циклическая коллекция")
            seen.add(id(item))
            try:
                array = kind in (BSLArray, BSLFixedArray)
                append("[" if array else "{")
                for index, child in enumerate(item):
                    if index: append(",")
                    if not array:
                        append(_quote(child.key))
                        append(":")
                        child = child.value
                    encode(child, depth + 1)
                append("]" if array else "}")
            finally:
                seen.remove(id(item))
        else:
            raise TypeError("ЗаписатьJSON: тип значения пока не поддерживается")
    encode(value, 0)
    return "".join(parts)


class BSLJSONLineBreak(Enum):
    AUTO = ("Авто", "Auto")
    NONE = ("Нет", "None")
    UNIX = ("Unix", "Unix")
    WINDOWS = ("Windows", "Windows")

    def __str__(self):
        return self.value[0]


class BSLJSONLineBreaks(BSLObject):
    def get_member(self, name):
        for item in BSLJSONLineBreak:
            if name.casefold() in tuple(n.casefold() for n in item.value):
                return item
        return super().get_member(name)


JSON_LINE_BREAKS = BSLJSONLineBreaks()


class BSLJSONWriterSettings(BSLObject):
    def __init__(self, new_lines=BSLJSONLineBreak.AUTO, padding_symbols=""):
        new_lines = BSLJSONLineBreak.AUTO if new_lines is None else new_lines
        padding_symbols = "" if padding_symbols is None else padding_symbols
        # !todo Add the advanced escape/quote constructor options after the
        # ordinary UTF-8/collection workflows have their native acceptance.
        if type(new_lines) is not BSLJSONLineBreak:
            raise TypeError("ПараметрыЗаписиJSON: ожидается ПереносСтрокJSON")
        self.new_lines = new_lines
        self.padding_symbols = _text(padding_symbols)

    def __str__(self):
        return "ПараметрыЗаписиJSON"

    def get_member(self, name):
        key = name.casefold()
        if key in ("переносстрок", "newlines"): return self.new_lines
        if key in ("символыотступа", "paddingsymbols"): return self.padding_symbols
        if key in ("использоватьдвойныекавычки", "usedoublequotes",
                   "экранироватьразделителистрок", "escapelineterminators"): return True
        if key in ("экранироватьугловыескобки", "escapeanglebrackets", "экранироватьамперсанд", "escapeampersand",
                   "экранироватьодинарныекавычки", "escapesinglequotes", "экранироватьслеш", "escapeslash"): return False
        return super().get_member(name)


def _layout(text, settings):
    if settings.new_lines is BSLJSONLineBreak.NONE:
        return text
    newline = "\r\n" if settings.new_lines is BSLJSONLineBreak.WINDOWS else (
        os.linesep if settings.new_lines is BSLJSONLineBreak.AUTO else "\n")
    def indent(depth):
        if len(settings.padding_symbols) * depth > MAX_TEXT:
            raise ValueError("JSON: превышен предел ресурсов Yadinassi")
        return settings.padding_symbols * depth
    result, size, depth, quoted, escaped = [], 0, 0, False, False
    for index, char in enumerate(text):
        part = char
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in "{[":
            depth += 1
            if index + 1 < len(text) and text[index + 1] not in "}]":
                part += newline + indent(depth)
        elif char in "}]":
            depth -= 1
            if index and text[index - 1] not in "{[":
                part = newline + indent(depth) + char
        elif char == ",": part += newline + indent(depth)
        elif char == ":": part += " "
        size += len(part)
        if size > MAX_TEXT:
            raise ValueError("JSON: превышен предел ресурсов Yadinassi")
        result.append(part)
    return "".join(result)


class BSLJSONWriter(BSLObject):
    def __init__(self):
        self._active = False
        self._file = None
        self._filename = None
        self._encoding = "utf-8"
        self._settings = BSLJSONWriterSettings()
        self._parts = []
        self._stack = []
        self._root = False
        self._size = 0

    def __str__(self):
        return "ЗаписьJSON"

    def set_string(self, settings=None):
        if settings is not None and type(settings) is not BSLJSONWriterSettings:
            raise TypeError("JSON: ожидаются ПараметрыЗаписиJSON")
        self._release_file()
        self.__init__()
        self._settings = settings if settings is not None else BSLJSONWriterSettings()
        self._active = True

    def open_file(self, filename, encoding="UTF-8", add_bom=False, settings=None):
        filename = _text(filename)
        encoding = "UTF-8" if encoding is None else _text(encoding)
        add_bom = False if add_bom is None else add_bom
        if type(add_bom) is not bool:
            raise TypeError("JSON: AddBOM должен иметь тип Булево")
        codec = encoding.casefold().replace("-", "")
        if codec in ("", "utf8"):
            encoding = "utf-8-sig" if add_bom else "utf-8"
        elif codec in ("utf16", "utf16le"):
            encoding = "utf-16" if add_bom else "utf-16-le"
        elif codec in ("windows1251", "cp1251"):
            encoding = "cp1251"
        else:
            raise ValueError("JSON: кодировка пока не поддерживается")
        if settings is not None and type(settings) is not BSLJSONWriterSettings:
            raise TypeError("JSON: ожидаются ПараметрыЗаписиJSON")
        stream = _open_regular(filename, encoding, writing=True)
        try:
            self.set_string(settings)
        except BaseException:
            stream.close()
            raise
        self._file = stream
        self._filename, self._encoding = filename, encoding

    def _release_file(self):
        stream = self._file
        self._file = None
        if stream is not None:
            stream.close()

    def __del__(self):
        stream = getattr(self, "_file", None)
        if stream is not None:
            stream.close()

    def _append(self, value):
        if self._size + len(value) > MAX_TEXT:
            raise ValueError("JSON: превышен предел ресурсов Yadinassi")
        self._parts.append(value)
        self._size += len(value)

    def _prefix(self):
        if not self._active:
            raise ValueError("JSON: приемник не открыт")
        if not self._stack:
            if self._root:
                raise ValueError("JSON: корневое значение уже записано")
            self._root = True
            return
        frame = self._stack[-1]
        if frame[0] == "object":
            if not frame[2]:
                raise ValueError("JSON: ожидалось имя свойства")
            frame[2] = False
        elif frame[1]:
            self._append(",")
        frame[1] += 1

    def write_property_name(self, name):
        name = _quote(name)
        if not self._active or not self._stack or self._stack[-1][0] != "object" or self._stack[-1][2]:
            raise ValueError("JSON: недопустимое состояние записи свойства")
        frame = self._stack[-1]
        self._append(("," if frame[1] else "") + name + ":")
        frame[2] = True

    def _start(self, kind):
        if len(self._stack) >= MAX_DEPTH:
            raise ValueError("JSON: превышена глубина Yadinassi")
        self._prefix()
        self._append("{" if kind == "object" else "[")
        self._stack.append([kind, 0, False])

    def _end(self, kind):
        if not self._active or not self._stack or self._stack[-1][0] != kind or self._stack[-1][2]:
            raise ValueError("JSON: недопустимое состояние конца контейнера")
        self._append("}" if kind == "object" else "]")
        self._stack.pop()

    def write_start_object(self): self._start("object")
    def write_end_object(self): self._end("object")
    def write_start_array(self): self._start("array")
    def write_end_array(self): self._end("array")

    def write_value(self, value, use_format_with_exponent=False):
        if type(value) not in (type(None), bool, str, Decimal):
            raise TypeError("ЗаписатьЗначение: ожидается примитивное значение JSON")
        if type(use_format_with_exponent) is not bool:
            raise TypeError("ЗаписатьЗначение: ожидается Булево")
        encoded = _encode(value)
        if type(value) is Decimal and use_format_with_exponent:
            encoded = format(value, "E").replace("E+", "E")
        self._write_encoded(encoded)

    def _write_encoded(self, value):
        if self._size + len(value) + 1 > MAX_TEXT:
            raise ValueError("JSON: превышен предел ресурсов Yadinassi")
        self._prefix()
        self._append(value)

    def close(self):
        if not self._active:
            raise ValueError("JSON: приемник не открыт")
        if self._stack:
            raise ValueError("JSON: незавершенный контейнер")
        text = _layout("".join(self._parts), self._settings)
        if self._file is not None:
            try:
                self._file.write(text)
            finally:
                self._release_file()
                self._active = False
            result = ""
        else:
            result = text
        self._active = False
        self._parts = []
        return result

    def get_member(self, name):
        if name.casefold() in ("параметры", "settings"):
            return self._settings
        methods = {
            "установитьстроку": self.set_string, "setstring": self.set_string,
            "открытьфайл": self.open_file, "openfile": self.open_file,
            "закрыть": self.close, "close": self.close,
            "записатьимясвойства": self.write_property_name, "writepropertyname": self.write_property_name,
            "записатьначалообъекта": self.write_start_object, "writestartobject": self.write_start_object,
            "записатьконецобъекта": self.write_end_object, "writeendobject": self.write_end_object,
            "записатьначаломассива": self.write_start_array, "writestartarray": self.write_start_array,
            "записатьконецмассива": self.write_end_array, "writeendarray": self.write_end_array,
            "записатьзначение": self.write_value, "writevalue": self.write_value,
        }
        key = name.casefold()
        if key in methods:
            return HostFunction(name, methods[key], returns_value=key in ("закрыть", "close"))
        return super().get_member(name)


def write_json(writer, value):
    # !todo Add native date serialization settings and conversion callbacks;
    # unsupported values must continue to fail rather than silently stringify.
    if type(writer) is not BSLJSONWriter:
        raise TypeError("ЗаписатьJSON: ожидается ЗаписьJSON")
    writer._write_encoded(_encode(value))

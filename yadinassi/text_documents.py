"""Bounded in-memory TextDocument, aligned with native run 40254792139.

The raw text retains its original CR/LF/CRLF delimiters. Line mutations use LF
for newly inserted text and leave untouched spans byte-for-byte unchanged.
No file operations, encoding/UI properties, codecs or cross-context transport.
"""

from decimal import Decimal
import re

from .values import BSLObject, HostFunction


# Explicit local resource limits, not inferred limits of the 1C platform.
_MAX_TEXT_UNITS = 1_000_000
_MAX_LINES = 100_000
_BREAK = re.compile(r"\r\n|\r|\n")


def _units(text):
    return len(text) + sum(ord(character) > 0xffff for character in text)


def _text(value):
    if type(value) is not str:
        raise TypeError("ТекстовыйДокумент: ожидается Строка без неявного преобразования")
    if len(value) > _MAX_TEXT_UNITS or _units(value) > _MAX_TEXT_UNITS:
        raise ValueError("ТекстовыйДокумент: превышен предел текста Yadinassi")
    # Native probes cover scalar Unicode, including an astral character and a
    # combining mark. Lone surrogate code units are outside this bounded slice.
    if any(0xd800 <= ord(character) <= 0xdfff for character in value):
        raise ValueError("ТекстовыйДокумент: отдельные суррогаты пока не поддерживаются")
    return value


def _line_text(value):
    value = _text(value)
    # SetText has measured CR/LF/CRLF handling. The line-mutator arguments only
    # establish empty/single lines and internal LF without a terminal break.
    # Do not silently invent normalization for their other delimiter forms.
    if "\r" in value or value.endswith("\n"):
        raise ValueError("ТекстовыйДокумент: CR и конечный LF в аргументе строки пока не поддерживаются")
    return value


def _index(value):
    # Compare bounded positions before int conversion; enormous exact Decimals
    # still have an immediate empty/no-op/append result without allocating ints.
    if (type(value) is not Decimal or not value.is_finite()
            or value != value.to_integral_value() or value < 0):
        raise TypeError("ТекстовыйДокумент: ожидается целый неотрицательный индекс")
    return value


def _spans(text):
    """(start, content_end, end_with_delimiter); no extra trailing empty line."""
    result = []
    start = 0
    for match in _BREAK.finditer(text):
        if len(result) >= _MAX_LINES:
            raise ValueError("ТекстовыйДокумент: превышен предел строк Yadinassi")
        result.append((start, match.start(), match.end()))
        start = match.end()
    if start < len(text):
        if len(result) >= _MAX_LINES:
            raise ValueError("ТекстовыйДокумент: превышен предел строк Yadinassi")
        result.append((start, len(text), len(text)))
    return result


class BSLTextDocument(BSLObject):
    def __init__(self):
        self._text = ""
        self._spans = []
        self._units = 0

    def __str__(self):
        # Object display is independently observed; it is not the type display.
        return "ТекстовыйДокумент"

    def get_text(self):
        return self._text

    def line_count(self):
        return Decimal(len(self._spans))

    def get_line(self, index):
        index = _index(index)
        if index == 0 or index > len(self._spans):
            return ""
        start, content_end, _ = self._spans[int(index) - 1]
        return self._text[start:content_end]

    def set_text(self, value):
        text = _text(value)
        spans = _spans(text)
        units = _units(text)
        # Commit only after every input/resource validation has succeeded.
        self._text, self._spans, self._units = text, spans, units

    def _replace(self, start, end, replacement):
        # A lone CR in an untouched left span must not silently combine with
        # a new/right-side LF and collapse an empty line. Native44 does not
        # establish that edit-boundary case, so reject it atomically.
        following_lf = (replacement.startswith("\n") or
                        (not replacement and self._text[end:end + 1] == "\n"))
        if start > 0 and self._text[start - 1] == "\r" and following_lf:
            raise ValueError("ТекстовыйДокумент: новый CRLF на границе изменения пока не поддерживается")
        units = self._units - _units(self._text[start:end]) + _units(replacement)
        if units > _MAX_TEXT_UNITS:
            raise ValueError("ТекстовыйДокумент: превышен предел текста Yadinassi")
        text = self._text[:start] + replacement + self._text[end:]
        spans = _spans(text)
        self._text, self._spans, self._units = text, spans, units

    def add_line(self, value):
        value = _line_text(value)
        separator = "\n" if self._text and not self._text.endswith(("\r", "\n")) else ""
        self._replace(len(self._text), len(self._text), separator + value + "\n")

    def insert_line(self, index, value):
        index, value = _index(index), _line_text(value)
        if index > len(self._spans):
            self.add_line(value)
            return
        position = 0 if index <= 1 else self._spans[int(index) - 1][0]
        self._replace(position, position, value + "\n")

    def replace_line(self, index, value):
        index, value = _index(index), _line_text(value)
        if index > len(self._spans):
            return
        if index == 0:
            start, end = 0, len(self._text)
        else:
            start, _, end = self._spans[int(index) - 1]
        self._replace(start, end, value + "\n")

    def delete_line(self, index):
        index = _index(index)
        if index == 0:
            self.clear()
        elif index <= len(self._spans):
            start, _, end = self._spans[int(index) - 1]
            self._replace(start, end, "")

    def clear(self):
        self._text, self._spans, self._units = "", [], 0

    def get_method(self, name):
        key = name.casefold()
        functions = {
            "gettext": self.get_text, "получитьтекст": self.get_text,
            "linecount": self.line_count, "количествострок": self.line_count,
            "getline": self.get_line, "получитьстроку": self.get_line,
        }
        procedures = {
            "settext": self.set_text, "установитьтекст": self.set_text,
            "addline": self.add_line, "добавитьстроку": self.add_line,
            "insertline": self.insert_line, "вставитьстроку": self.insert_line,
            "replaceline": self.replace_line, "заменитьстроку": self.replace_line,
            "deleteline": self.delete_line, "удалитьстроку": self.delete_line,
            "clear": self.clear, "очистить": self.clear,
        }
        if key in functions:
            return HostFunction(name, functions[key])
        if key in procedures:
            return HostFunction(name, procedures[key], returns_value=False)
        return super().get_method(name)

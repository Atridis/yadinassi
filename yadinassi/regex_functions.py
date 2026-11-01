"""Ordinary bounded regex search/result/replace API; native calibration pending.

!todo XDTO/XML serialization and unsupported regex extensions are not provided.
Matching currently uses Unicode scalar characters with UTF-16 public offsets;
the closed native acquisition must settle astral, flags and replacement details.
"""
from decimal import Decimal, ROUND_DOWN
import sys
from . import regex_parser as limits
from .regex_parser import Budget, Parser, checked_text
from .regex_vm import Program, run
from .search_directions import BSLSearchDirection
from .values import BSLObject, BSLArray, HostFunction
from .strings import _OMITTED


def _flag(value):
    if value is _OMITTED or value is None: return False
    if type(value) is not bool:
        raise TypeError('Регулярное выражение: ожидается булево значение')
    return value


def _integer(value, minimum, maximum, budget):
    # Never route unbounded strings through shared number()/host regex coercion.
    if type(value) is int:
        budget.tick()
        if value.bit_length() > 32 or not minimum <= value <= maximum:
            raise ValueError('Регулярное выражение: неверное числовое значение')
        return value
    if type(value) is not Decimal:
        raise TypeError('Регулярное выражение: ожидается число')
    # CPython Decimal.__sizeof__ includes its coefficient allocation. Bound that
    # before as_tuple(), which would otherwise allocate a tuple of every digit.
    if sys.implementation.name != 'cpython' or Decimal.__sizeof__ is object.__sizeof__:
        raise limits.RegexLimitError('Регулярное выражение: неподдержанное представление числа')
    if value.__sizeof__() > limits.MAX_DECIMAL_BYTES:
        raise limits.RegexLimitError('Регулярное выражение: слишком большое число')
    digits = value.as_tuple().digits
    if len(digits) > limits.MAX_DECIMAL_DIGITS:
        raise limits.RegexLimitError('Регулярное выражение: слишком большое число')
    budget.tick(len(digits) + 1)
    if not value.is_finite() or value < minimum or value >= maximum + 1:
        raise ValueError('Регулярное выражение: неверное числовое значение')
    return int(value.to_integral_value(rounding=ROUND_DOWN))


class BSLRegexGroup(BSLObject):
    def __init__(self, value, position, length):
        self._value, self._position, self._length = value, Decimal(position), Decimal(length)
    def get_member(self, name):
        key = name.casefold()
        if key in ('value', 'значение'): return self._value
        if key in ('startindex', 'начальнаяпозиция'): return self._position
        if key in ('length', 'длина'): return self._length
        return super().get_member(name)
    def __str__(self): return 'ГруппаРезультатаПоискаПоРегулярномуВыражению'


class BSLRegexResult(BSLRegexGroup):
    def __init__(self, value, position, length, groups):
        super().__init__(value, position, length)
        self._groups = tuple(groups)
    def get_groups(self):
        result = BSLArray(); result.items = list(self._groups)
        return result
    def get_method(self, name):
        if name.casefold() in ('getgroups', 'получитьгруппы'):
            return HostFunction(name, self.get_groups)
        return super().get_method(name)
    def __str__(self): return 'РезультатПоискаПоРегулярномуВыражению'


class Operation:
    def __init__(self, text, pattern, ignore, multiline):
        self.budget = Budget()
        self.text = checked_text(text, limits.MAX_TEXT, self.budget)
        node, groups = Parser(pattern, self.budget).parse()
        self.program = Program(node, groups, self.budget)
        self.ignore, self.multiline = _flag(ignore), _flag(multiline)
        # Bounded map avoids slicing/encoding prefixes repeatedly for each result.
        self.budget.tick(len(text) + 1)
        self.offsets = [0]
        for c in text: self.offsets.append(self.offsets[-1] + (2 if ord(c) > 0xffff else 1))

    def match(self, start, full=False):
        return run(self.program, self.text, start, self.budget, self.ignore, self.multiline, full)

    def matches(self, start=0):
        count = 0
        while start <= len(self.text):
            self.budget.tick()
            captures = self.match(start)
            if captures is None:
                start += 1; continue
            count += 1
            if count > limits.MAX_MATCHES:
                raise limits.RegexLimitError('Регулярное выражение: слишком много совпадений')
            yield captures
            start = captures[1] if captures[1] > start else start + 1

    def reverse_matches(self, end):
        count = 0
        while end >= 0:
            found = None
            for start in range(min(end, len(self.text)), -1, -1):
                self.budget.tick()
                captures = self.match(start)
                if captures is not None and captures[1] <= end:
                    found = captures; break
            if found is None: return
            count += 1
            if count > limits.MAX_MATCHES:
                raise limits.RegexLimitError('Регулярное выражение: слишком много совпадений')
            yield found
            end = found[0] if found[1] > found[0] else found[0] - 1

    def piece(self, start, end):
        if start is None or end is None:
            self.budget.result(objects=1)
            return '', 0, 0
        width = self.offsets[end] - self.offsets[start]
        self.budget.result(objects=1, output=width)
        return self.text[start:end], self.offsets[start] + 1, width

    def result(self, captures):
        if captures is None:
            self.budget.result(objects=1)
            return BSLRegexResult('', 0, 0, ())
        value, start, width = self.piece(captures[0], captures[1])
        groups = []
        for index in range(1, self.program.groups + 1):
            groups.append(BSLRegexGroup(*self.piece(captures[index * 2], captures[index * 2 + 1])))
        return BSLRegexResult(value, start, width, groups)

    def source_position(self, value, default, backward):
        if value is _OMITTED or value is None: return default
        position = _integer(value, 1, max(1, self.offsets[-1]), self.budget)
        target = position if backward else position - 1
        # !todo A start within a surrogate pair needs native calibration; reject
        # instead of silently moving the caller's requested UTF-16 position.
        for index, offset in enumerate(self.offsets):
            self.budget.tick()
            if offset == target: return index
        raise ValueError('Регулярное выражение: позиция внутри символа Unicode')


def str_like(text, pattern, ignore=_OMITTED, multiline=_OMITTED):
    op = Operation(text, pattern, ignore, multiline)
    return op.match(0, full=True) is not None


def str_find(text, pattern, direction=_OMITTED, start=_OMITTED, occurrence=_OMITTED,
             ignore=_OMITTED, multiline=_OMITTED):
    if direction is _OMITTED or direction is None: direction = BSLSearchDirection.FROM_BEGIN
    if type(direction) is not BSLSearchDirection:
        raise TypeError('Регулярное выражение: ожидается НаправлениеПоиска')
    op = Operation(text, pattern, ignore, multiline)
    backward = direction is BSLSearchDirection.FROM_END
    position = op.source_position(start, len(op.text) if backward else 0, backward)
    nth = 1 if occurrence is _OMITTED or occurrence is None else _integer(occurrence, 1, limits.MAX_MATCHES, op.budget)
    matches = op.reverse_matches(position) if backward else op.matches(position)
    for index, captures in enumerate(matches, 1):
        if index == nth: return op.result(captures)
    return op.result(None)


def str_find_all(text, pattern, ignore=_OMITTED, multiline=_OMITTED):
    op = Operation(text, pattern, ignore, multiline)
    result = BSLArray()
    for captures in op.matches(): result.items.append(op.result(captures))
    return result


def _replacement(value, group_count, budget):
    checked_text(value, limits.MAX_TEXT, budget)
    tokens = []; literal = []; index = 0
    while index < len(value):
        budget.tick(); c = value[index]; index += 1
        if c != '$' or index == len(value): literal.append(c); continue
        if value[index] == '$': literal.append('$'); index += 1; continue
        if not ('0' <= value[index] <= '9'): literal.append('$'); continue
        if literal: tokens.append(('literal', ''.join(literal))); literal = []
        group = 0
        while index < len(value) and '0' <= value[index] <= '9':
            budget.tick(); group = group * 10 + ord(value[index]) - 48; index += 1
            if group > group_count: raise ValueError('Регулярное выражение: неизвестная группа замены')
        tokens.append(('group', group))
    if literal: tokens.append(('literal', ''.join(literal)))
    budget.tick(len(value))
    return [(kind, item, len(item) + sum(ord(c) > 0xffff for c in item) if kind == 'literal' else 0)
            for kind, item in tokens]


def str_replace(text, pattern, replacement, ignore=_OMITTED, multiline=_OMITTED):
    op = Operation(text, pattern, ignore, multiline)
    tokens = _replacement(replacement, op.program.groups, op.budget)
    pieces = []; previous = 0
    def append_piece(value):
        if len(pieces) >= limits.MAX_OBJECTS:
            raise limits.RegexLimitError('Регулярное выражение: слишком много частей результата')
        pieces.append(value)
    def add_slice(start, end):
        if len(pieces) >= limits.MAX_OBJECTS:
            raise limits.RegexLimitError('Регулярное выражение: слишком много частей результата')
        width = op.offsets[end] - op.offsets[start]
        op.budget.result(output=width)
        append_piece(text[start:end])
    for captures in op.matches():
        add_slice(previous, captures[0])
        for kind, value, width in tokens:
            op.budget.tick()
            if kind == 'literal':
                op.budget.result(output=width); append_piece(value)
            else:
                begin, end = captures[value * 2:value * 2 + 2]
                if begin is not None and end is not None: add_slice(begin, end)
        previous = captures[1]
    add_slice(previous, len(text))
    return ''.join(pieces)


BUILTINS = (
    ('СтрПодобнаПоРегулярномуВыражению', str_like, 'StrLikeByRegularExpression'),
    ('СтрНайтиПоРегулярномуВыражению', str_find, 'StrFindByRegularExpression'),
    ('СтрНайтиВсеПоРегулярномуВыражению', str_find_all, 'StrFindAllByRegularExpression'),
    ('СтрЗаменитьПоРегулярномуВыражению', str_replace, 'StrReplaceByRegularExpression'),
)
FUNCTIONS = (str_like, str_find, str_find_all, str_replace)

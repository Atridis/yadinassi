"""Closed catalog SELECT grammar; this AST is never database SQL.

Field projections, bounded joins, grouping, aggregates and ordering are admitted. Bounds are implementation limits, not native platform limits.
!todo arithmetic expressions, packages, general functions and temporary tables.
"""
from dataclasses import dataclass
from decimal import Decimal
import re

MAX_TEXT = 65536
MAX_TOKENS = 2048
MAX_ROWS = 10000


@dataclass(frozen=True, slots=True)
class Field:
    parts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Aggregate:
    function: str
    field: Field | None
    distinct: bool = False


@dataclass(frozen=True, slots=True)
class Source:
    catalog: str
    alias: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class Join:
    source: Source
    kind: str
    predicate: object


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str


@dataclass(frozen=True, slots=True)
class Comparison:
    field: Field
    operator: str
    value: object


@dataclass(frozen=True, slots=True)
class Predicate:
    kind: str
    terms: tuple


@dataclass(frozen=True, slots=True)
class Projection:
    field: Field
    alias: str
    explicit_alias: bool = False


@dataclass(frozen=True, slots=True)
class Order:
    field: Field
    descending: bool


@dataclass(frozen=True, slots=True)
class Select:
    catalog: str
    source_alias: str
    projections: tuple[Projection, ...]
    predicate: Comparison | Predicate | None
    order: tuple[Order, ...]
    limit: int
    section: str | None = None
    joins: tuple[Join, ...] = ()
    groups: tuple[Field, ...] = ()
    having: Comparison | Predicate | None = None
    distinct: bool = False


_AGGREGATES = {'count':'count', 'количество':'count', 'sum':'sum', 'сумма':'sum',
               'avg':'avg', 'среднее':'avg', 'min':'min', 'минимум':'min',
               'max':'max', 'максимум':'max'}
_KEYWORDS = {
    'select':'select', 'выбрать':'select', 'top':'top', 'первые':'top',
    'from':'from', 'из':'from', 'as':'as', 'как':'as',
    'where':'where', 'где':'where', 'order':'order', 'упорядочить':'order',
    'by':'by', 'по':'by', 'asc':'asc', 'возр':'asc', 'desc':'desc', 'убыв':'desc',
    'and':'and', 'и':'and', 'or':'or', 'или':'or',
    'distinct':'distinct', 'различные':'distinct',
    'inner':'inner', 'внутреннее':'inner', 'left':'left', 'левое':'left',
    'outer':'outer', 'внешнее':'outer', 'join':'join', 'соединение':'join',
    'on':'on', 'group':'group', 'сгруппировать':'group',
    'having':'having', 'имеющие':'having',
    'is':'is', 'есть':'is', 'not':'not', 'не':'not', 'null':'null',
    'true':'true', 'истина':'true', 'false':'false', 'ложь':'false',
}
_TOKEN = re.compile(r'\s+|"(?:[^"\r\n]|"")*"|[0-9]+(?:\.[0-9]+)?|[^\W\d]\w*|<=|>=|<>|[&.,()=<>+*\-]', re.UNICODE)
_IDENTIFIER = re.compile(r'[^\W\d]\w*\Z', re.UNICODE)


def identifier(value):
    return type(value) is str and 0 < len(value) <= 128 and _IDENTIFIER.fullmatch(value) is not None


def _lex(text):
    if type(text) is not str:
        raise TypeError('Query text requires String')
    if not text or len(text) > MAX_TEXT:
        raise ValueError('Query text outside supported bounds')
    result = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None:
            raise ValueError('Unsupported query syntax')
        raw = match.group(); pos = match.end()
        if raw.isspace():
            continue
        if len(raw) > 4096:
            raise ValueError('Query token outside supported bounds')
        if raw.startswith('"'):
            token = ('string', raw[1:-1].replace('""', '"'))
        elif raw[0].isascii() and raw[0].isdigit():
            if len(raw) > 39 or sum(c.isdigit() for c in raw) > 38:
                raise ValueError('Query number outside supported bounds')
            token = ('number', raw)
        elif identifier(raw):
            token = (_KEYWORDS.get(raw.casefold(), 'name'), raw)
        else:
            token = (raw, raw)
        result.append(token)
        if len(result) > MAX_TOKENS:
            raise ValueError('Query token budget exceeded')
    return result + [('end', '')]


class _Parser:
    def __init__(self, text):
        self.tokens = _lex(text)
        self.position = 0
        self.comparisons = 0

    def peek(self):
        return self.tokens[self.position][0]

    def take(self, kind):
        if self.peek() != kind:
            raise ValueError('Unsupported query syntax')
        value = self.tokens[self.position][1]
        self.position += 1
        return value

    def accept(self, kind):
        if self.peek() != kind:
            return False
        self.position += 1
        return True

    def field(self):
        parts = [self.take('name')]
        if self.accept('.'):
            parts.append(self.take('name'))
        return Field(tuple(parts))

    def expression(self, *, aggregates=True):
        if (aggregates and self.peek() == 'name'
                and self.tokens[self.position][1].casefold() in _AGGREGATES
                and self.tokens[self.position + 1][0] == '('):
            function = _AGGREGATES[self.take('name').casefold()]
            self.take('(')
            distinct = self.accept('distinct')
            field = None if self.accept('*') else self.field()
            if field is None and (function != 'count' or distinct):
                raise ValueError('Only COUNT(*) admits a wildcard')
            self.take(')')
            return Aggregate(function, field, distinct)
        return self.field()

    def source(self):
        if self.take('name').casefold() not in ('catalog', 'справочник'):
            raise ValueError('Only catalog sources are supported')
        self.take('.')
        catalog = self.take('name')
        section = self.take('name') if self.accept('.') else None
        alias = self.take('name') if self.accept('as') else (section or catalog)
        return Source(catalog, alias, section)

    def scalar(self):
        if self.accept('&'):
            return Parameter(self.take('name'))
        if self.peek() == 'string':
            return self.take('string')
        if self.accept('true'):
            return True
        if self.accept('false'):
            return False
        sign = '-' if self.accept('-') else ''
        if not sign:
            self.accept('+')
        return Decimal(sign + self.take('number'))

    def condition(self, depth=0):
        if depth > 32:
            raise ValueError('Query predicate nesting limit exceeded')
        terms = [self.conjunction(depth)]
        while self.accept('or'):
            terms.append(self.conjunction(depth))
        return terms[0] if len(terms) == 1 else Predicate('or', tuple(terms))

    def conjunction(self, depth):
        terms = [self.atom(depth)]
        while self.accept('and'):
            terms.append(self.atom(depth))
        return terms[0] if len(terms) == 1 else Predicate('and', tuple(terms))

    def atom(self, depth):
        if self.accept('('):
            result = self.condition(depth + 1)
            self.take(')')
            return result
        field = self.expression()
        if self.accept('is'):
            negate = self.accept('not')
            self.take('null')
            return Comparison(field, 'is_not_null' if negate else 'is_null', None)
        operators = {'=':'eq', '<>':'ne', '<':'lt', '<=':'le', '>':'gt', '>=':'ge'}
        if self.peek() not in operators:
            raise ValueError('Unsupported query comparison')
        operator = operators[self.peek()]
        self.position += 1
        self.comparisons += 1
        if self.comparisons > 128:
            raise ValueError('Query predicate budget exceeded')
        return Comparison(field, operator, self.expression() if self.peek() == 'name' else self.scalar())

    def parse(self):
        self.take('select')
        distinct = self.accept('distinct')
        limit = MAX_ROWS
        if self.accept('top'):
            raw = self.take('number')
            if not raw.isascii() or not raw.isdigit() or len(raw) > 5:
                raise ValueError('TOP requires bounded integer')
            limit = int(raw)
            if not 1 <= limit <= MAX_ROWS:
                raise ValueError('TOP outside supported bounds')
        projections = []
        while True:
            field = self.expression()
            explicit = self.accept('as')
            alias = self.take('name') if explicit else (field.function if type(field) is Aggregate else field.parts[-1])
            projections.append(Projection(field, alias, explicit))
            if len(projections) > 128:
                raise ValueError('Query projection budget exceeded')
            if not self.accept(','):
                break
        if len({p.alias.casefold() for p in projections}) != len(projections):
            raise ValueError('Duplicate query output column')
        self.take('from')
        source = self.source()
        joins = []
        while self.peek() in ('inner', 'left', 'join'):
            kind = 'left' if self.accept('left') else 'inner'
            if kind == 'left': self.accept('outer')
            else: self.accept('inner')
            self.take('join')
            other = self.source()
            if not self.accept('on'): self.take('by')
            joins.append(Join(other, kind, self.condition()))
            if len(joins) > 7: raise ValueError('Query source budget exceeded')
        aliases = [source.alias.casefold()] + [j.source.alias.casefold() for j in joins]
        if len(set(aliases)) != len(aliases): raise ValueError('Duplicate query source alias')
        predicate = self.condition() if self.accept('where') else None
        groups = []
        if self.accept('group'):
            self.take('by')
            while True:
                groups.append(self.field())
                if len(groups) > 32: raise ValueError('Query grouping budget exceeded')
                if not self.accept(','): break
        having = self.condition() if self.accept('having') else None
        order = []
        if self.accept('order'):
            self.take('by')
            while True:
                field = self.expression()
                descending = self.accept('desc')
                if not descending:
                    self.accept('asc')
                order.append(Order(field, descending))
                if len(order) > 32:
                    raise ValueError('Query order budget exceeded')
                if not self.accept(','):
                    break
        self.take('end')
        return Select(source.catalog, source.alias, tuple(projections), predicate,
                      tuple(order), limit, source.section, tuple(joins), tuple(groups), having, distinct)


def parse_query(text):
    return _Parser(text).parse()

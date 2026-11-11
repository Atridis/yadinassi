"""Closed application SELECT grammar; this AST is never database SQL.

Field projections, bounded joins, grouping, aggregates and ordering are admitted. Bounds are implementation limits, not native platform limits.
Nested membership SELECTs are bounded and uncorrelated.
"""
from dataclasses import dataclass, replace
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
    field: object | None
    distinct: bool = False


@dataclass(frozen=True, slots=True)
class NullLiteral:
    pass


@dataclass(frozen=True, slots=True)
class Expression:
    operator: str
    arguments: tuple


@dataclass(frozen=True, slots=True)
class Source:
    catalog: str
    alias: str
    section: str | None = None
    temporary: bool = False
    external: bool = False
    family: str = 'catalog'
    period_boundary: object = None
    derived: object = None


@dataclass(frozen=True, slots=True)
class Destroy:
    name: str


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
    field: object
    operator: str
    value: object


@dataclass(frozen=True, slots=True)
class Membership:
    field: object
    values: object


@dataclass(frozen=True, slots=True)
class Hierarchy:
    field: object
    root: object


@dataclass(frozen=True, slots=True)
class Predicate:
    kind: str
    terms: tuple


@dataclass(frozen=True, slots=True)
class Projection:
    field: object
    alias: str
    explicit_alias: bool = False


@dataclass(frozen=True, slots=True)
class Order:
    field: object
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
    groups: tuple[object, ...] = ()
    having: Comparison | Predicate | None = None
    distinct: bool = False
    temporary: bool = False
    into: str | None = None
    external: bool = False
    family: str = 'catalog'
    period_boundary: object = None
    derived: object = None


@dataclass(frozen=True, slots=True)
class Union:
    arms: tuple[Select, ...]
    all: tuple[bool, ...]
    order: tuple[Order, ...]
    into: str | None = None


_AGGREGATES = {'count':'count', 'количество':'count', 'sum':'sum', 'сумма':'sum',
               'avg':'avg', 'среднее':'avg', 'min':'min', 'минимум':'min',
               'max':'max', 'максимум':'max'}
_KEYWORDS = {
    'union':'union', 'объединить':'union', 'all':'all', 'все':'all',
    'into':'into', 'поместить':'into', 'destroy':'destroy', 'уничтожить':'destroy',
    'select':'select', 'выбрать':'select', 'top':'top', 'первые':'top',
    'from':'from', 'из':'from', 'as':'as', 'как':'as',
    'where':'where', 'где':'where', 'order':'order', 'упорядочить':'order',
    'by':'by', 'по':'by', 'asc':'asc', 'возр':'asc', 'desc':'desc', 'убыв':'desc',
    'in':'in', 'в':'in', 'hierarchy':'hierarchy', 'иерархии':'hierarchy', 'between':'between', 'между':'between',
    'and':'and', 'и':'and', 'or':'or', 'или':'or',
    'distinct':'distinct', 'различные':'distinct',
    'inner':'inner', 'внутреннее':'inner', 'left':'left', 'левое':'left',
    'right':'right', 'правое':'right', 'full':'full', 'полное':'full',
    'outer':'outer', 'внешнее':'outer', 'join':'join', 'соединение':'join',
    'on':'on', 'group':'group', 'сгруппировать':'group',
    'having':'having', 'имеющие':'having',
    'case':'case', 'выбор':'case', 'when':'when', 'когда':'when',
    'then':'then', 'тогда':'then', 'else':'else', 'иначе':'else',
    'end':'case_end', 'конец':'case_end',
    'is':'is', 'есть':'is', 'not':'not', 'не':'not', 'null':'null',
    'true':'true', 'истина':'true', 'false':'false', 'ложь':'false',
}
_TOKEN = re.compile(r'\s+|"(?:[^"\r\n]|"")*"|[0-9]+(?:\.[0-9]+)?|[^\W\d]\w*|<=|>=|<>|[&.,;()=<>+*/\-]', re.UNICODE)
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
        self.expression_depth = 0
        self.subquery_depth = 0
        self.subquery_count = 0
        self.expression_heights = {}

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

    def expression_node(self, operator, arguments):
        def height(node):
            if type(node) is Expression: return self.expression_heights[id(node)][1]
            if type(node) is Aggregate: return 1 + height(node.field)
            if type(node) is Comparison: return max(height(node.field), height(node.value))
            if type(node) is Membership: return height(node.field)
            if type(node) is Hierarchy: return max(height(node.field),height(node.root))
            if type(node) is Predicate: return max(map(height, node.terms), default=0)
            if type(node) is tuple: return max(map(height, node), default=0)
            return 0
        depth = 1 + height(arguments)
        if depth > 32: raise ValueError('Query expression nesting limit exceeded')
        result = Expression(operator, arguments)
        self.expression_heights[id(result)] = (result, depth)
        return result

    def expression(self, *, aggregates=True, precedence=0):
        self.expression_depth += 1
        try:
            if self.expression_depth > 32:
                raise ValueError('Query expression nesting limit exceeded')
            if self.peek() in ('+', '-'):
                operator = self.peek(); self.position += 1
                operand = self.expression(aggregates=aggregates, precedence=3)
                left = ((operand.copy_negate() if operator == '-' else operand) if type(operand) is Decimal
                        else self.expression_node('unary' + operator, (operand,)))
            elif self.accept('('):
                left = self.expression(aggregates=aggregates)
                self.take(')')
            elif self.accept('case'):
                branches = []
                while self.accept('when'):
                    condition = self.condition()
                    self.take('then')
                    branches.append((condition, self.expression(aggregates=aggregates)))
                if not branches: raise ValueError('CASE requires WHEN')
                otherwise = self.expression(aggregates=aggregates) if self.accept('else') else None
                self.take('case_end')
                left = self.expression_node('case', (tuple(branches), otherwise))
            elif (self.peek() == 'name' and self.tokens[self.position + 1][0] == '('):
                function = self.take('name').casefold()
                self.take('(')
                if function in ('isnull', 'естьnull'):
                    first = self.expression(aggregates=aggregates)
                    self.take(',')
                    left = self.expression_node('coalesce', (first, self.expression(aggregates=aggregates)))
                elif aggregates and function in _AGGREGATES:
                    function = _AGGREGATES[function]
                    distinct = self.accept('distinct')
                    field = None if self.accept('*') else self.expression(aggregates=False)
                    if field is None and (function != 'count' or distinct):
                        raise ValueError('Only COUNT(*) admits a wildcard')
                    left = Aggregate(function, field, distinct)
                else: raise ValueError('Unsupported query function or nested aggregate')
                self.take(')')
            elif self.accept('null'):
                left = NullLiteral()
            elif self.peek() == 'name':
                left = self.field()
            else:
                left = self.scalar()
            priorities = {'+': 1, '-': 1, '*': 2, '/': 2}
            while self.peek() in priorities and priorities[self.peek()] > precedence:
                operator = self.peek(); self.position += 1
                right = self.expression(aggregates=aggregates, precedence=priorities[operator])
                left = self.expression_node(operator, (left, right))
            return left
        finally:
            self.expression_depth -= 1

    def source(self):
        if self.accept('('):
            self.subquery_depth += 1; self.subquery_count += 1
            if self.subquery_depth > 8 or self.subquery_count > 16:
                raise ValueError('Query subquery budget exceeded')
            try: derived = self.statement()
            finally: self.subquery_depth -= 1
            if derived.into is not None:
                raise ValueError('Derived source cannot create a temporary table')
            self.take(')'); self.take('as')
            alias = self.take('name')
            return Source(alias, alias, derived=derived)
        if self.accept('&'):
            name = self.take('name')
            alias = self.take('name') if self.accept('as') else name
            return Source(name, alias, external=True)
        family = self.take('name')
        if self.peek() != '.':
            alias = self.take('name') if self.accept('as') else family
            return Source(family, alias, temporary=True)
        if family.casefold() not in ('catalog', 'справочник', 'document', 'документ', 'informationregister', 'регистрсведений', 'accumulationregister', 'регистрнакопления'):
            raise ValueError('Unsupported query source family')
        self.take('.')
        catalog = self.take('name')
        section = self.take('name') if self.accept('.') else None
        source_family = ('document' if family.casefold() in ('document', 'документ') else
                         'accumulation_register' if family.casefold() in ('accumulationregister', 'регистрнакопления') else
                         'information_register' if family.casefold() in ('informationregister', 'регистрсведений') else 'catalog')
        boundary = None
        if source_family == 'information_register' and section is not None:
            names={'slicelast':'last','срезпоследних':'last','slicefirst':'first','срезпервых':'first'}
            if section.casefold() not in names: raise ValueError('Unsupported information-register virtual source')
            section=names[section.casefold()]
            self.take('('); self.take('&'); boundary=Parameter(self.take('name')); self.take(')')
        if source_family == 'accumulation_register' and section is not None:
            names = {'balance': 'balance', 'остатки': 'balance',
                     'turnovers': 'turnovers', 'обороты': 'turnovers'}
            if section.casefold() not in names:
                raise ValueError('Unsupported accumulation-register virtual source')
            section = names[section.casefold()]
            self.take('('); self.take('&'); start = Parameter(self.take('name'))
            boundary = (start,)
            if section == 'turnovers':
                self.take(','); self.take('&'); boundary += (Parameter(self.take('name')),)
            self.take(')')
        alias = self.take('name') if self.accept('as') else (section or catalog)
        return Source(catalog, alias, section, family=source_family, period_boundary=boundary)

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
        if depth > 32: raise ValueError('Query predicate nesting limit exceeded')
        if self.accept('not'):
            return Predicate('not', (self.atom(depth + 1),))
        if self.peek() == '(':
            # Decide from the matching close instead of recursively reparsing a
            # failed predicate as arithmetic. This bounds work for nested input.
            nesting, close = 0, None
            for position in range(self.position, len(self.tokens)):
                token = self.tokens[position][0]
                if token == '(': nesting += 1
                elif token == ')':
                    nesting -= 1
                    if nesting == 0:
                        close = position
                        break
            if close is None: raise ValueError('Unclosed query parenthesis')
            follows = self.tokens[close + 1][0]
            if follows not in ('=', '<>', '<', '<=', '>', '>=', 'is', 'in', 'not', 'between', '+', '-', '*', '/'):
                self.position += 1
                result = self.condition(depth + 1)
                self.take(')')
                return result
        field = self.expression()
        if self.accept('is'):
            negate = self.accept('not')
            self.take('null')
            return Comparison(field, 'is_not_null' if negate else 'is_null', None)
        negate = self.accept('not')
        if self.peek() in ('in', 'between'):
            operator = self.peek(); self.position += 1
            self.comparisons += 1
            if self.comparisons > 128: raise ValueError('Query predicate budget exceeded')
            if operator == 'between':
                lower = self.expression(); self.take('and'); upper = self.expression()
                result = Predicate('and', (Comparison(field, 'ge', lower), Comparison(field, 'le', upper)))
            elif self.accept('hierarchy'):
                self.take('('); root=self.expression(); self.take(')')
                result=Hierarchy(field,root)
                return Predicate('not',(result,)) if negate else result
            else:
                if self.peek() == '&':
                    self.take('&'); values = Parameter(self.take('name'))
                else:
                    self.take('(')
                    if self.peek() == 'select':
                        self.subquery_depth += 1; self.subquery_count += 1
                        if self.subquery_depth > 8 or self.subquery_count > 16:
                            raise ValueError('Query subquery budget exceeded')
                        try: values = self.statement()
                        finally: self.subquery_depth -= 1
                        if values.into is not None: raise ValueError('Membership subquery cannot create a temporary table')
                    else:
                        items = [self.expression()]
                        while self.accept(','):
                            items.append(self.expression())
                            if len(items) > 256: raise ValueError('Query IN list limit exceeded')
                        values = tuple(items)
                    self.take(')')
                result = Membership(field, values)
            return Predicate('not', (result,)) if negate else result
        if negate: raise ValueError('NOT after an expression requires IN or BETWEEN')
        operators = {'=':'eq', '<>':'ne', '<':'lt', '<=':'le', '>':'gt', '>=':'ge'}
        if self.peek() not in operators:
            raise ValueError('Unsupported query comparison')
        operator = operators[self.peek()]
        self.position += 1
        self.comparisons += 1
        if self.comparisons > 128:
            raise ValueError('Query predicate budget exceeded')
        return Comparison(field, operator, self.expression())

    def parse(self, *, complete=True):
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
            if explicit: alias = self.take('name')
            elif type(field) is Aggregate: alias = field.function
            elif type(field) is Field: alias = field.parts[-1]
            else: raise ValueError('Computed query projection requires AS alias')
            projections.append(Projection(field, alias, explicit))
            if len(projections) > 128:
                raise ValueError('Query projection budget exceeded')
            if not self.accept(','):
                break
        if len({p.alias.casefold() for p in projections}) != len(projections):
            raise ValueError('Duplicate query output column')
        into = self.take('name') if self.accept('into') else None
        self.take('from')
        source = self.source()
        joins = []
        while self.peek() in ('inner', 'left', 'right', 'full', 'join'):
            kind = self.peek() if self.peek() in ('left', 'right', 'full') else 'inner'
            if kind != 'inner': self.take(kind); self.accept('outer')
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
                groups.append(self.expression(aggregates=False))
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
        if complete: self.take('end')
        return Select(source.catalog, source.alias, tuple(projections), predicate,
                      tuple(order), limit, source.section, tuple(joins), tuple(groups), having, distinct, source.temporary, into, source.external, source.family, source.period_boundary, source.derived)


    def statement(self):
        first = self.parse(complete=False)
        if self.peek() != 'union': return first
        arms, modes = [first], []
        while self.accept('union'):
            if arms[-1].order:
                raise ValueError('UNION admits only one final output ORDER BY')
            modes.append(self.accept('all'))
            arm = self.parse(complete=False)
            if arm.into is not None:
                raise ValueError('UNION INTO belongs only to the first SELECT')
            arms.append(arm)
            if len(arms) > MAX_UNION_ARMS:
                raise ValueError('Query UNION arm limit exceeded')
        order = arms[-1].order
        arms[-1] = replace(arms[-1], order=())
        arms[0] = replace(arms[0], into=None)
        return Union(tuple(arms), tuple(modes), order, first.into)


def parse_query(text):
    parser = _Parser(text)
    result = parser.statement()
    parser.take('end')
    return result


MAX_STATEMENTS = 32
MAX_UNION_ARMS = 16


def parse_package(text):
    """Parse a complete bounded package, with one optional trailing semicolon."""
    parser = _Parser(text)
    statements = []
    while True:
        if parser.accept('destroy'):
            statement = Destroy(parser.take('name'))
        else:
            statement = parser.statement()
        statements.append(statement)
        if len(statements) > MAX_STATEMENTS:
            raise ValueError('Query package statement limit exceeded')
        if not parser.accept(';') or parser.peek() == 'end':
            break
    parser.take('end')
    return tuple(statements)


def walk_nodes(value):
    """Walk only closed grammar nodes, including nested membership sources."""
    from dataclasses import fields
    node_types = (Field, Aggregate, NullLiteral, Expression, Source, Destroy, Join,
                  Parameter, Comparison, Membership, Hierarchy, Predicate, Projection, Order, Select, Union)
    if type(value) is tuple:
        for item in value: yield from walk_nodes(item)
    elif type(value) in node_types:
        yield value
        for field in fields(value): yield from walk_nodes(getattr(value, field.name))


def selects(statements):
    return (node for node in walk_nodes(statements) if type(node) is Select)


def extended_filters(statement):
    return any(type(node) is Membership or (type(node) is Source and node.derived is not None)
               or (type(node) is Select and node.derived is not None)
               or (type(node) is Predicate and node.kind == 'not')
               for node in walk_nodes(statement))

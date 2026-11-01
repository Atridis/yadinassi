"""Bounded ordinary regex grammar. Unsupported extensions fail explicitly.

!todo Backreferences, lookaround, named groups, inline flags, Unicode properties,
atomic/possessive/conditional constructs are not implemented. Never delegate to re.
"""
MAX_PATTERN = 4096
MAX_TEXT = 65536
MAX_DEPTH = 32
MAX_GROUPS = 32
MAX_CODE = 2048
MAX_REPEAT = 1024
MAX_STATES = 4096
MAX_WORK = 2_000_000
MAX_MATCHES = 4096
MAX_OBJECTS = 8192
MAX_OUTPUT = 1_048_576
MAX_LOOPS = 128
MAX_DECIMAL_BYTES = 1024
MAX_DECIMAL_DIGITS = 128


class RegexLimitError(ValueError):
    pass


class Budget:
    def __init__(self):
        self.remaining = MAX_WORK
        self.objects = 0
        self.output = 0

    def tick(self, amount=1):
        if amount < 0 or amount > self.remaining:
            raise RegexLimitError('Регулярное выражение: превышен предел работы')
        self.remaining -= amount

    def result(self, objects=0, output=0):
        if self.objects + objects > MAX_OBJECTS or self.output + output > MAX_OUTPUT:
            raise RegexLimitError('Регулярное выражение: превышен предел результата')
        self.tick(objects + output)
        self.objects += objects
        self.output += output


def checked_text(value, maximum, budget):
    if type(value) is not str:
        raise TypeError('Регулярное выражение: ожидается строка')
    if len(value) > maximum:
        raise RegexLimitError('Регулярное выражение: слишком длинная строка')
    budget.tick(len(value))
    units = len(value) + sum(ord(c) > 0xffff for c in value)
    if units > maximum:
        raise RegexLimitError('Регулярное выражение: слишком длинная строка')
    return value


class Parser:
    def __init__(self, source, budget):
        self.source = checked_text(source, MAX_PATTERN, budget)
        self.i = 0
        self.groups = 0
        self.budget = budget

    def error(self):
        raise ValueError('Регулярное выражение: неверный или неподдержанный шаблон')

    def peek(self):
        return self.source[self.i] if self.i < len(self.source) else ''

    def take(self):
        self.budget.tick()
        if self.i == len(self.source): self.error()
        c = self.source[self.i]; self.i += 1
        return c

    def parse(self):
        node = self.alternation(0)
        if self.i != len(self.source): self.error()
        return node, self.groups

    def alternation(self, depth):
        if depth > MAX_DEPTH:
            raise RegexLimitError('Регулярное выражение: превышена глубина')
        choices = [self.sequence(depth)]
        while self.peek() == '|':
            self.take(); choices.append(self.sequence(depth))
        return ('alt', tuple(choices)) if len(choices) > 1 else choices[0]

    def sequence(self, depth):
        nodes = []
        while self.peek() and self.peek() not in ')|':
            node = self.atom(depth)
            c = self.peek()
            if c and c in '*+?{':
                self.take()
                if c == '*': lower, upper = 0, None
                elif c == '+': lower, upper = 1, None
                elif c == '?': lower, upper = 0, 1
                else:
                    lower = self.integer()
                    if self.peek() == ',':
                        self.take(); upper = self.integer() if self.peek().isascii() and self.peek().isdigit() else None
                    else: upper = lower
                    if self.take() != '}': self.error()
                    if upper is not None and lower > upper: self.error()
                lazy = self.peek() == '?'
                if lazy: self.take()
                if self.peek() and self.peek() in '*+?{': self.error()
                if node[0] == 'assert': self.error()
                node = ('repeat', node, lower, upper, lazy)
            nodes.append(node)
        return ('seq', tuple(nodes))

    def integer(self):
        if not (self.peek().isascii() and self.peek().isdigit()): self.error()
        value = 0
        while self.peek().isascii() and self.peek().isdigit():
            value = value * 10 + ord(self.take()) - 48
            if value > MAX_REPEAT:
                raise RegexLimitError('Регулярное выражение: слишком большой повтор')
        return value

    def atom(self, depth):
        c = self.take()
        if c == '(':
            group = None
            if self.peek() == '?':
                self.take()
                if self.take() != ':': self.error()
            else:
                self.groups += 1; group = self.groups
                if group > MAX_GROUPS:
                    raise RegexLimitError('Регулярное выражение: слишком много групп')
            node = self.alternation(depth + 1)
            if self.take() != ')': self.error()
            return ('group', group, node) if group is not None else node
        if c == '[': return self.character_class()
        if c == '.': return ('dot',)
        if c in '^$': return ('assert', c)
        if c == '\\': return self.escape(False)
        if c in '*+?{}]': self.error()
        return ('char', c)

    def escape(self, in_class):
        c = self.take()
        if c in 'dDsSwW': return ('category', c)
        if c in 'bB' and not in_class: return ('assert', c)
        if c == 'b' and in_class: return ('char', '\b')
        if c in 'nrtfv': return ('char', {'n':'\n','r':'\r','t':'\t','f':'\f','v':'\v'}[c])
        if c in 'xu':
            count = 2 if c == 'x' else 4
            if len(self.source) - self.i < count: self.error()
            digits = ''.join(self.take() for _ in range(count))
            if any(x not in '0123456789abcdefABCDEF' for x in digits): self.error()
            return ('char', chr(int(digits, 16)))
        if c.isalnum(): self.error()  # Includes unsupported backreferences/extensions.
        return ('char', c)

    def class_atom(self):
        c = self.take()
        if c == '\\': return self.escape(True)
        return ('char', c)

    def character_class(self):
        negate = self.peek() == '^'
        if negate: self.take()
        parts = []
        while self.peek() and (self.peek() != ']' or not parts):
            part = self.class_atom()
            if self.peek() == '-' and self.i + 1 < len(self.source) and self.source[self.i + 1] != ']':
                self.take(); end = self.class_atom()
                if part[0] != 'char' or end[0] != 'char' or ord(part[1]) > ord(end[1]): self.error()
                part = ('range', part[1], end[1])
            parts.append(part)
        if self.take() != ']' or not parts: self.error()
        return ('class', negate, tuple(parts))

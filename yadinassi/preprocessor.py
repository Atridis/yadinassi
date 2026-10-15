"""Conditional compilation for Yadinassi's standalone client profile."""

from dataclasses import dataclass
import re

from .errors import BSLError, IncompleteInput


DIRECTIVES = {
    "если": "if", "if": "if", "иначеесли": "elsif", "elsif": "elsif",
    "иначе": "else", "else": "else", "конецесли": "endif", "endif": "endif",
}
SYMBOLS = {
    "клиент": True, "client": True, "наклиенте": True, "atclient": True,
    "сервер": False, "server": False, "насервере": False, "atserver": False,
}
OPERATORS = {"и": "and", "and": "and", "или": "or", "or": "or",
             "не": "not", "not": "not"}


@dataclass
class _Branch:
    parent_active: bool
    matched: bool
    active: bool
    saw_else: bool = False


class ConditionalCompilation:
    def __init__(self, source: str):
        self.source = source
        self.stack: list[_Branch] = []

    @property
    def active(self) -> bool:
        return not self.stack or self.stack[-1].active

    def process(self, directive: str, line: int, column: int) -> bool:
        """Consume a conditional directive; return False for other # directives."""
        match = re.fullmatch(r"#\s*([^\W\d]\w*)(.*)", directive)
        if match is None or match.group(1).casefold() not in DIRECTIVES:
            return False
        kind = DIRECTIVES[match.group(1).casefold()]
        rest = match.group(2).strip()

        def fail(message: str) -> None:
            raise BSLError(message, self.source, line, column)

        if kind in ("if", "elsif"):
            condition = _Condition(rest, fail).parse()
        elif rest:
            fail("После #Иначе / #КонецЕсли не должно быть выражения")
        if kind == "if":
            parent = self.active
            self.stack.append(_Branch(parent, condition, parent and condition))
            return True
        if not self.stack:
            fail("Директива препроцессора не имеет соответствующей #Если")
        branch = self.stack[-1]
        if kind == "endif":
            self.stack.pop()
        elif branch.saw_else:
            fail("После #Иначе допустима только #КонецЕсли")
        elif kind == "else":
            branch.active = branch.parent_active and not branch.matched
            branch.matched = True
            branch.saw_else = True
        else:
            branch.active = branch.parent_active and not branch.matched and condition
            branch.matched = branch.matched or condition
        return True

    def finish(self, line: int, column: int) -> None:
        if self.stack:
            raise IncompleteInput("Не завершена #Если: ожидается #КонецЕсли",
                                  self.source, line, column)


class _Condition:
    def __init__(self, text, fail):
        self.fail = fail
        self.tokens = re.findall(r"[^\W\d]\w*|\S", text)
        self.pos = 0

    def accept(self, kind: str) -> bool:
        if self.pos < len(self.tokens):
            value = self.tokens[self.pos].casefold()
            if OPERATORS.get(value, value) == kind:
                self.pos += 1
                return True
        return False

    def parse(self) -> bool:
        value = self.disjunction()
        if not (self.accept("тогда") or self.accept("then")):
            self.fail("В условии препроцессора ожидается Тогда / Then")
        if self.pos != len(self.tokens):
            self.fail("Лишние символы после Тогда / Then")
        return value

    def disjunction(self) -> bool:
        value = self.conjunction()
        while self.accept("or"):
            right = self.conjunction()  # Always validate even an unselected operand.
            value = value or right
        return value

    def conjunction(self) -> bool:
        value = self.negation()
        while self.accept("and"):
            right = self.negation()
            value = value and right
        return value

    def negation(self) -> bool:
        negate = self.accept("not")
        value = self.atom()
        return not value if negate else value

    def atom(self) -> bool:
        if self.accept("("):
            value = self.disjunction()
            if not self.accept(")"):
                self.fail("В условии препроцессора ожидается ')'")
            return value
        if self.pos == len(self.tokens):
            self.fail("Ожидается символ клиентского или серверного контекста")
        name = self.tokens[self.pos]
        self.pos += 1
        if name.casefold() not in SYMBOLS:
            self.fail(f"Неподдерживаемый символ препроцессора: {name}")
        return SYMBOLS[name.casefold()]

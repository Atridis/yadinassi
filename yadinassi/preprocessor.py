"""Conditional compilation and source regions for the standalone client profile."""

from collections.abc import Collection
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
REGION_DIRECTIVES = {"область": "REGION", "region": "REGION",
                     "конецобласти": "ENDREGION", "endregion": "ENDREGION"}


@dataclass
class _Branch:
    parent_active: bool
    matched: bool
    active: bool
    saw_else: bool = False


class ConditionalCompilation:
    def __init__(self, source: str, execution_context: str = "client"):
        if execution_context not in {"client", "server"}:
            raise ValueError("Unknown execution context")
        self.source = source
        self.symbols = {name: value == (execution_context == "client")
                        for name, value in SYMBOLS.items()}
        self.stack: list[_Branch] = []

    @property
    def active(self) -> bool:
        return not self.stack or self.stack[-1].active

    def process(self, directive: str, line: int, column: int) -> str | None:
        """Consume a conditional directive and return its kind, or None."""
        match = re.fullmatch(r"#\s*([^\W\d]\w*)(.*)", directive)
        if match is None or match.group(1).casefold() not in DIRECTIVES:
            return None
        kind = DIRECTIVES[match.group(1).casefold()]
        rest = match.group(2).strip()

        def fail(message: str) -> None:
            raise BSLError(message, self.source, line, column)

        if kind in ("if", "elsif"):
            condition = _Condition(rest, fail, self.symbols).parse()
        elif rest:
            fail("После #Иначе / #КонецЕсли не должно быть выражения")
        if kind == "if":
            parent = self.active
            self.stack.append(_Branch(parent, condition, parent and condition))
            return kind
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
        return kind

    def finish(self, line: int, column: int) -> None:
        if self.stack:
            raise IncompleteInput("Не завершена #Если: ожидается #КонецЕсли",
                                  self.source, line, column)


@dataclass
class _Region:
    name: str
    line: int
    column: int
    conditional_depth: int


class SourceRegions:
    """Validate active region directives without creating runtime scopes."""

    def __init__(self, source: str):
        self.source = source
        self.stack: list[_Region] = []

    def process(self, directive: str, line: int, column: int,
                conditional_depth: int, keywords: Collection[str]) -> tuple[str, str] | None:
        match = re.fullmatch(r"#\s*([^\W\d]\w*)(.*)", directive)
        if match is None or match.group(1).casefold() not in REGION_DIRECTIVES:
            return None
        kind = REGION_DIRECTIVES[match.group(1).casefold()]
        name = match.group(2).strip()
        if kind == "REGION":
            if (not name or not (name[0].isalpha() or name[0] == "_")
                    or not all(char.isalnum() or char == "_" for char in name)
                    or name.casefold() in keywords):
                raise BSLError("После #Область ожидается имя-идентификатор",
                               self.source, line, column)
            self.stack.append(_Region(name, line, column, conditional_depth))
        else:
            if name:
                raise BSLError("После #КонецОбласти не должно быть имени или выражения",
                               self.source, line, column)
            if not self.stack:
                raise BSLError("#КонецОбласти не имеет соответствующей #Область",
                               self.source, line, column)
            if self.stack[-1].conditional_depth != conditional_depth:
                self.crossing(line, column)
            self.stack.pop()
        return kind, name

    def conditional_boundary(self, kind: str, previous_depth: int,
                             line: int, column: int) -> None:
        if (kind != "if" and self.stack
                and self.stack[-1].conditional_depth == previous_depth):
            self.crossing(line, column)

    def crossing(self, line: int, column: int) -> None:
        raise BSLError("Область пересекает границу условной компиляции",
                       self.source, line, column)

    def finish(self) -> None:
        if self.stack:
            region = self.stack[-1]
            raise IncompleteInput(
                f"Не завершена #Область {region.name}: ожидается #КонецОбласти",
                self.source, region.line, region.column)


class _Condition:
    def __init__(self, text, fail, symbols=SYMBOLS):
        self.symbols = symbols
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
        return self.symbols[name.casefold()]

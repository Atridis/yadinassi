"""Conditional compilation and source regions for the standalone client profile."""

from collections.abc import Collection
from dataclasses import dataclass
from types import MappingProxyType
import re

from .errors import BSLError, IncompleteInput


DIRECTIVES = {
    "если": "if", "if": "if", "иначеесли": "elsif", "elsif": "elsif",
    "иначе": "else", "else": "else", "конецесли": "endif", "endif": "endif",
}
COMPILATION_PROFILES = ("standalone",)
# These are standalone language policy, not a native platform mode or host OS.
# Site-dependent flags must not invert the constant-false application symbols.
_STANDALONE_FLAGS = MappingProxyType({
    "client": (True, False, True, False),
    "server": (False, True, False, True),
    "server_nocontext": (False, True, False, False),
    "dual_client": (True, False, False, False),
    "dual_server": (False, True, False, False),
})
_CONTEXT_ALIASES = (("client", "клиент"), ("server", "сервер"),
                    ("atclient", "наклиенте"), ("atserver", "насервере"))
_APPLICATION_SYMBOLS = (
    "thinclient", "тонкийклиент", "webclient", "вебклиент",
    "thickclientordinaryapplication", "толстыйклиентобычноеприложение",
    "thickclientmanagedapplication", "толстыйклиентуправляемоеприложение",
    "externalconnection", "внешнеесоединение",
)
_STANDALONE_SYMBOLS = MappingProxyType({
    site: MappingProxyType({
        **{alias: value for aliases, value in zip(_CONTEXT_ALIASES, flags)
           for alias in aliases},
        **dict.fromkeys(_APPLICATION_SYMBOLS, False),
    }) for site, flags in _STANDALONE_FLAGS.items()
})


def validate_compilation_profile(name: str) -> str:
    """Accept a closed identifier, never user defines or an inferred profile."""
    if type(name) is not str:
        raise TypeError("compilation_profile must be a string")
    if name not in COMPILATION_PROFILES:
        raise ValueError("Unsupported compilation_profile; expected 'standalone'")
    return name


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
    logical: bool = False


class ConditionalCompilation:
    def __init__(self, source: str, execution_context: str = "client", *,
                 compilation_profile: str = "standalone"):
        self._compilation_profile = validate_compilation_profile(compilation_profile)
        if execution_context not in _STANDALONE_SYMBOLS:
            raise ValueError("Unknown execution context")
        self.source = source
        self._symbols = _STANDALONE_SYMBOLS[execution_context]
        self.stack: list[_Branch] = []

    @property
    def compilation_profile(self) -> str:
        return self._compilation_profile

    @property
    def symbols(self):
        return self._symbols

    @property
    def active(self) -> bool:
        return not self.stack or self.stack[-1].active

    @property
    def logical_guard(self) -> bool:
        """An enclosing branch was selected with AtClient/AtServer symbols."""
        return any(branch.logical for branch in self.stack)

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
            expression = _Condition(rest, fail, self.symbols)
            condition = expression.parse()
            logical = expression.logical
        elif rest:
            fail("После #Иначе / #КонецЕсли не должно быть выражения")
        if kind == "if":
            parent = self.active
            self.stack.append(_Branch(parent, condition, parent and condition, logical=logical))
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
            branch.logical = branch.logical or logical
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
    def __init__(self, text, fail, symbols):
        self.symbols = symbols
        self.fail = fail
        self.tokens = re.findall(r"[^\W\d]\w*|\S", text)
        self.pos = 0
        self.logical = False

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
        if name.casefold() not in self.symbols:
            self.fail(f"Неподдерживаемый символ препроцессора: {name}")
        if name.casefold() in {"наклиенте", "atclient", "насервере", "atserver"}:
            self.logical = True
        return self.symbols[name.casefold()]

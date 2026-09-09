"""Unicode-aware lexer. Keyword aliases are centralized here."""

from dataclasses import dataclass
from decimal import Decimal

from .errors import BSLError, IncompleteInput


KEYWORDS: dict[str, str] = {}
for kind, aliases in {
    "IF": ("Если", "If"),
    "THEN": ("Тогда", "Then"),
    "ELSIF": ("ИначеЕсли", "ElsIf"),
    "ELSE": ("Иначе", "Else"),
    "ENDIF": ("КонецЕсли", "EndIf"),
    "FOR": ("Для", "For"),
    "EACH": ("Каждого", "Each"),
    "IN": ("Из", "In"),
    "TO": ("По", "To"),
    "DO": ("Цикл", "Do"),
    "ENDDO": ("КонецЦикла", "EndDo"),
    "WHILE": ("Пока", "While"),
    "BREAK": ("Прервать", "Break"),
    "CONTINUE": ("Продолжить", "Continue"),
    "NEW": ("Новый", "New"),
    "TRUE": ("Истина", "True"),
    "FALSE": ("Ложь", "False"),
    "UNDEFINED": ("Неопределено", "Undefined"),
    "AND": ("И", "And"),
    "OR": ("Или", "Or"),
    "NOT": ("Не", "Not"),
    "VAR": ("Перем", "Var"),
}.items():
    KEYWORDS.update((alias.casefold(), kind) for alias in aliases)


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int
    column: int
    source: str


class Lexer:
    def __init__(self, text: str, source: str = "<строка>"):
        self.text = text.removeprefix("\ufeff")
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1

    def peek(self, offset: int = 0) -> str:
        pos = self.pos + offset
        return self.text[pos] if pos < len(self.text) else ""

    def advance(self) -> str:
        char = self.text[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def tokens(self) -> list[Token]:
        result = []
        while self.peek():
            char = self.peek()
            if char.isspace():
                self.advance()
                continue
            if char == "/" and self.peek(1) == "/":
                while self.peek() and self.peek() != "\n":
                    self.advance()
                continue
            line, column = self.line, self.column
            if char.isalpha() or char == "_":
                start = self.pos
                while self.peek() and (self.peek().isalnum() or self.peek() == "_"):
                    self.advance()
                value = self.text[start:self.pos]
                kind = KEYWORDS.get(value.casefold(), "IDENT")
            elif char.isascii() and char.isdigit():
                start = self.pos
                while self.peek() and self.peek() in "0123456789":
                    self.advance()
                if self.peek() == "." and self.peek(1) and self.peek(1) in "0123456789":
                    self.advance()
                    while self.peek() and self.peek() in "0123456789":
                        self.advance()
                value = Decimal(self.text[start:self.pos])
                kind = "NUMBER"
            elif char == '"':
                value = self.string(line, column)
                kind = "STRING"
            else:
                pair = char + self.peek(1)
                if pair in ("<=", ">=", "<>"):
                    kind = value = self.advance() + self.advance()
                elif char in "+-*/%=<>()[];.,":
                    kind = value = self.advance()
                else:
                    raise BSLError(f"Неожиданный символ {char!r}", self.source, line, column)
            result.append(Token(kind, value, line, column, self.source))
        result.append(Token("EOF", None, self.line, self.column, self.source))
        return result

    def string(self, line: int, column: int) -> str:
        self.advance()
        chars = []
        while self.peek():
            char = self.advance()
            if char == '"':
                if self.peek() == '"':
                    self.advance()
                    chars.append('"')
                else:
                    return "".join(chars)
            elif char in "\r\n":
                if char == "\r" and self.peek() == "\n":
                    self.advance()
                while self.peek() and self.peek() in " \t":
                    self.advance()
                if not self.peek():
                    break
                if self.peek() != "|":
                    raise BSLError("Продолжение строки должно начинаться с '|'", self.source,
                                   self.line, self.column)
                self.advance()
                chars.append("\n")
            else:
                chars.append(char)
        raise IncompleteInput("Незавершенная строка", self.source, line, column)

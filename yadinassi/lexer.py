"""Unicode-aware lexer. Keyword aliases are centralized here."""

from dataclasses import dataclass
from decimal import Decimal
import re

from .errors import BSLError, IncompleteInput
from .dates import literal_date
from .preprocessor import ConditionalCompilation, SourceRegions


KEYWORDS: dict[str, str] = {}
for kind, aliases in {
    "ASYNC": ("Асинх", "Async"),
    "AWAIT": ("Ждать", "Await"),
    "EXECUTE": ("Выполнить", "Execute"),
    "GOTO": ("Перейти", "Goto"),
    "TRY": ("Попытка", "Try"),
    "EXCEPT": ("Исключение", "Except"),
    "ENDTRY": ("КонецПопытки", "EndTry"),
    "RAISE": ("ВызватьИсключение", "Raise"),
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
    "NULL": ("Null",),
    "UNDEFINED": ("Неопределено", "Undefined"),
    "AND": ("И", "And"),
    "OR": ("Или", "Or"),
    "NOT": ("Не", "Not"),
    "FUNCTION": ("Функция", "Function"),
    "ENDFUNCTION": ("КонецФункции", "EndFunction"),
    "PROCEDURE": ("Процедура", "Procedure"),
    "ENDPROCEDURE": ("КонецПроцедуры", "EndProcedure"),
    "RETURN": ("Возврат", "Return"),
    "EXPORT": ("Экспорт", "Export"),
    "VAR": ("Перем", "Var"),
    "VAL": ("Знач", "Val"),
}.items():
    KEYWORDS.update((alias.casefold(), kind) for alias in aliases)


EXECUTION_DIRECTIVES = {
    "наклиенте": "ATCLIENT", "atclient": "ATCLIENT",
    "насервере": "ATSERVER", "atserver": "ATSERVER",
    "насерверебезконтекста": "ATSERVERNOCONTEXT",
    "atservernocontext": "ATSERVERNOCONTEXT",
    "наклиентенасерверебезконтекста": "ATCLIENTATSERVERNOCONTEXT",
    "atclientatservernocontext": "ATCLIENTATSERVERNOCONTEXT",
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int
    column: int
    source: str
    source_line: str = ""


class Lexer:
    def __init__(self, text: str, source: str = "<строка>", *, allow_directives: bool = True,
                 execution_context: str = "client", server_declarations_only: bool = False):
        self.text = text.removeprefix("\ufeff")
        self.source = source
        self.source_lines = [line.removesuffix("\r") for line in self.text.split("\n")]
        self.allow_directives = allow_directives
        self.execution_context = execution_context
        self.server_declarations_only = server_declarations_only
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
        dual = self.execution_context in {"dual_client", "dual_server"}
        nocontext = self.execution_context == "server_nocontext" or dual
        declarations_only = self.server_declarations_only or nocontext
        selected_annotation = ("ATCLIENTATSERVERNOCONTEXT" if dual else
                               "ATSERVERNOCONTEXT" if nocontext else "ATSERVER")
        compilation = ConditionalCompilation(self.source, self.execution_context)
        capturing_server = False
        capturing_variable = False
        capturing_routine = False
        skipped_variable = False
        skipped_nocontext = False
        skipped_dual = False
        skipped_compilation = None
        skipped_conditional_depth = 0
        root_fragment = False
        root_depth = 0
        excluded_root_blocks = []
        client_compilation = ConditionalCompilation(self.source, "client")
        skipping_client = False
        skipped_depth = 0
        regions = SourceRegions(self.source)
        while self.peek():
            char = self.peek()
            # Only branches excluded from the default client root may initialize
            # a server activation. Never replay unguarded module statements.
            server_root = (self.server_declarations_only and not nocontext and compilation.active
                           and not client_compilation.active and compilation.logical_guard)
            # An excluded nested preprocessor branch does not terminate its
            # enclosing initializer. Runtime If/loop bodies may span it.
            root_ended = (root_depth > len(compilation.stack) or
                          root_depth > 0 and (
                              not compilation.stack[root_depth - 1].active or
                              client_compilation.stack[root_depth - 1].active))
            if root_fragment and (root_ended or (char == "&" and compilation.active)):
                result.append(Token("SERVERROOTEND", None, self.line, self.column, self.source))
                root_fragment = False
            if char.isspace():
                self.advance()
                continue
            source_active = (skipped_compilation.active
                             if skipping_client and skipped_nocontext else compilation.active)
            if not source_active and char != "#":
                # Excluded lines need not be valid BSL; no imports or annotations run.
                while self.peek() and self.peek() not in "\r\n":
                    self.advance()
                continue
            # The standalone entry point belongs only to the client. Additional
            # profiles select their annotated declarations, never a second
            # execution/parse of the root statement section.
            if (declarations_only and not capturing_server
                    and not skipping_client and char not in "#&"
                    and (not server_root or re.match(
                        r"(?:Async|Асинх|Procedure|Function|Процедура|Функция)\b", self.text[self.pos:], re.I))):
                # Track unannotated (therefore client) routine boundaries even
                # after another root statement on the same line. Quoted text
                # and comments cannot introduce declarations or directives.
                if char == "/" and self.peek(1) == "/":
                    while self.peek() and self.peek() not in "\r\n":
                        self.advance()
                elif char == '"':
                    try:
                        self.string(self.line, self.column)
                    except BSLError:
                        # Root text excluded from the client may deliberately
                        # be invalid BSL. It is never a server entry point.
                        pass
                elif char == "'":
                    self.advance()
                    while self.peek() and self.peek() not in "'\r\n":
                        self.advance()
                    if self.peek() == "'":
                        self.advance()
                elif char.isalpha() or char == "_":
                    start = self.pos
                    while self.peek() and (self.peek().isalnum() or self.peek() == "_"):
                        self.advance()
                    skipped_kind = KEYWORDS.get(self.text[start:self.pos].casefold())
                    if skipped_kind in {"ASYNC", "FUNCTION", "PROCEDURE"}:
                        skipping_client = True
                        skipped_depth = 0 if skipped_kind == "ASYNC" else 1
                        skipped_nocontext = skipped_dual = False
                    elif nocontext:
                        # Root statements are omitted, not flattened. A selected
                        # annotation inside an omitted If/loop/Try is still nested.
                        ending = {"IF": "ENDIF", "FOR": "ENDDO", "WHILE": "ENDDO",
                                  "TRY": "ENDTRY"}.get(skipped_kind)
                        if ending:
                            excluded_root_blocks.append(ending)
                        elif excluded_root_blocks and skipped_kind == excluded_root_blocks[-1]:
                            excluded_root_blocks.pop()
                else:
                    self.advance()
                continue
            if (server_root and not capturing_server and not skipping_client
                    and not root_fragment and char not in "#&"
                    and not (char == "/" and self.peek(1) == "/")):
                result.append(Token("SERVERROOTBEGIN", None, self.line, self.column, self.source))
                root_fragment = True
                root_depth = next(index + 1 for index, branch in enumerate(compilation.stack)
                                  if branch.active and not client_compilation.stack[index].active
                                  and any(parent.logical for parent in compilation.stack[:index + 1]))
            line, column = self.line, self.column
            if char == "/" and self.peek(1) == "/":
                start = self.pos
                standalone = not self.text[self.text.rfind("\n", 0, start) + 1:start].strip()
                while self.peek() and self.peek() not in "\r\n":
                    self.advance()
                directive = self.text[start + 2:self.pos].split("//", 1)[0].strip()
                if skipping_client:
                    continue
                if (declarations_only and standalone
                        and re.match(r"#\s*(?:Импорт|Import)\b", directive, re.IGNORECASE)):
                    if capturing_server:
                        raise BSLError("Импорт в серверной подпрограмме не поддерживается",
                                       self.source, line, column)
                    # Comment imports are a client-only extension. Preserve the
                    # historical ignored root contract; never load them here.
                    continue
                if standalone and re.match(r"#\s*(?:Импорт|Import)\b", directive, re.IGNORECASE):
                    if not self.allow_directives:
                        raise BSLError("Директивы недопустимы в вычисляемом выражении",
                                       self.source, line, column)
                    value = self.import_name(directive, line, column)
                    result.append(Token("IMPORT", value, line, column, self.source,
                                        self.source_lines[line - 1]))
                continue
            if char == "#":
                if not self.allow_directives:
                    raise BSLError("Директивы недопустимы в вычисляемом выражении",
                                   self.source, line, column)
                # A directive owns its line; comments and strings are lexed separately.
                if self.text[self.text.rfind("\n", 0, self.pos) + 1:self.pos].strip():
                    raise BSLError("Директива должна начинать строку",
                                   self.source, line, column)
                start = self.pos
                while self.peek() and self.peek() not in "\r\n":
                    self.advance()
                directive = self.text[start:self.pos].split("//", 1)[0].strip()
                previous_depth = len(compilation.stack)
                client_compilation.process(directive, line, column)
                if conditional := compilation.process(directive, line, column):
                    if (skipping_client and skipped_nocontext and
                            (conditional == "if" or previous_depth > skipped_conditional_depth)):
                        # A skipped NoContext body still uses its own logical
                        # selection for structural boundaries. Outer guards only
                        # select the declaration; they are not part of its body.
                        skipped_compilation.process(directive, line, column)
                    regions.conditional_boundary(conditional, previous_depth, line, column)
                    continue
                if not compilation.active:
                    continue
                if skipping_client or (declarations_only and not capturing_server and not root_fragment):
                    # Root regions and other root-only directives do not belong
                    # to the server declaration fragment. Conditional nesting
                    # was still processed above to select the right sources.
                    continue
                if region := regions.process(directive, line, column,
                                             len(compilation.stack), KEYWORDS.keys()):
                    kind, value = region
                    result.append(Token(kind, value, line, column, self.source,
                                        self.source_lines[line - 1]))
                    continue
                if re.match(r"#\s*(?:Импорт|Import)\b", directive, re.IGNORECASE):
                    raise BSLError("Директива #Импорт не поддерживается; используйте "
                                   "комментарий // #Импорт на отдельной строке",
                                   self.source, line, column)
                raise BSLError(f"Директива препроцессора не поддерживается: {directive}",
                               self.source, line, column)
            elif char == "&":
                if not self.allow_directives:
                    raise BSLError("Директивы недопустимы в вычисляемом выражении",
                                   self.source, line, column)
                if self.text[self.text.rfind("\n", 0, self.pos) + 1:self.pos].strip():
                    raise BSLError("Директива исполнения должна начинать строку",
                                   self.source, line, column)
                start = self.pos
                while self.peek() and self.peek() not in "\r\n":
                    self.advance()
                directive = self.text[start:self.pos].split("//", 1)[0].strip()
                match = re.fullmatch(r"&([^\W\d]\w*)", directive)
                if match is None:
                    raise BSLError("Ожидается директива исполнения на отдельной строке",
                                   self.source, line, column)
                name = match.group(1).casefold()
                if skipping_client:
                    if skipped_dual and skipped_depth == 0:
                        raise BSLError("После директивы исполнения ожидается объявление процедуры или функции",
                                       self.source, line, column)
                    continue
                kind = EXECUTION_DIRECTIVES.get(name)
                if kind is None:
                    raise BSLError(f"Директива {directive} не поддерживается: "
                                   "доступны &НаКлиенте / &AtClient, &НаСервере / &AtServer, "
                                   "&НаСервереБезКонтекста / &AtServerNoContext "
                                   "и &НаКлиентеНаСервереБезКонтекста / &AtClientAtServerNoContext",
                                   self.source, line, column)
                if not capturing_server and (
                        declarations_only and kind != selected_annotation or
                        not declarations_only and kind in {"ATSERVERNOCONTEXT", "ATCLIENTATSERVERNOCONTEXT"}):
                    # Each NoContext body belongs solely to its independent
                    # compilation. Other passes must not parse or import it.
                    skipping_client = True
                    skipped_depth = 0
                    skipped_dual = kind == "ATCLIENTATSERVERNOCONTEXT"
                    skipped_nocontext = kind == "ATSERVERNOCONTEXT" or skipped_dual
                    if skipped_nocontext:
                        skipped_profile = "server_nocontext"
                        if skipped_dual:
                            side = "client" if self.execution_context in {"client", "dual_client"} else "server"
                            skipped_profile = "dual_" + side
                        skipped_compilation = ConditionalCompilation(self.source, skipped_profile)
                        skipped_conditional_depth = len(compilation.stack)
                    if not declarations_only:
                        # Retain a declaration skeleton in the client parse so
                        # nested placement is rejected without lexing its body.
                        result.append(Token(kind, directive, line, column, self.source,
                                            self.source_lines[line - 1]))
                    continue
                if nocontext and excluded_root_blocks:
                    raise BSLError("Директива исполнения допустима только перед подпрограммой уровня модуля",
                                   self.source, line, column)
                value = directive
                if declarations_only:
                    capturing_server = True
            elif char.isalpha() or char == "_":
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
            elif char == "'":
                self.advance()
                start = self.pos
                while self.peek() and self.peek() not in "'\r\n":
                    self.advance()
                if not self.peek():
                    raise IncompleteInput("Незавершенный литерал даты", self.source, line, column)
                if self.peek() != "'":
                    raise BSLError("Перенос строки в литерале даты не поддерживается", self.source, line, column)
                text = self.text[start:self.pos]
                self.advance()
                try:
                    value = literal_date(text)
                except (ValueError, TypeError, OverflowError) as error:
                    raise BSLError(str(error), self.source, line, column) from None
                kind = "DATE"
            elif char == '"':
                value = self.string(line, column)
                kind = "STRING"
            else:
                pair = char + self.peek(1)
                if pair in ("<=", ">=", "<>"):
                    kind = value = self.advance() + self.advance()
                elif char in "+-*/%=<>()[];.,?~:":
                    kind = value = self.advance()
                else:
                    if skipping_client:
                        self.advance()
                        continue
                    raise BSLError(f"Неожиданный символ {char!r}", self.source, line, column)
            if skipping_client:
                if skipped_depth == 0 and skipped_dual and kind == "ASYNC":
                    # Explicit project boundary, including declarations present
                    # only under ordinary logical-client/server guards.
                    raise BSLError("Асинх для двойной подпрограммы без контекста пока не поддерживается",
                                   self.source, line, column)
                if skipped_depth == 0 and kind == "VAR":
                    if skipped_nocontext:
                        raise BSLError("Директива без контекста недопустима для переменной",
                                       self.source, line, column)
                    skipped_variable = True
                if skipped_variable:
                    if kind == ";":
                        skipping_client = skipped_variable = False
                    continue
                if skipped_depth == 0 and kind not in {"ASYNC", "FUNCTION", "PROCEDURE"}:
                    raise BSLError("После директивы исполнения ожидается объявление процедуры или функции",
                                   self.source, line, column)
                if kind in {"FUNCTION", "PROCEDURE"}:
                    if skipped_depth == 0 and skipped_nocontext and not declarations_only:
                        result.append(Token(kind, value, line, column, self.source,
                                            self.source_lines[line - 1]))
                    skipped_depth += 1
                elif kind in {"ENDFUNCTION", "ENDPROCEDURE"}:
                    skipped_depth -= 1
                    if skipped_depth == 0:
                        skipping_client = False
                        if skipped_nocontext and not declarations_only:
                            result.append(Token(kind, value, line, column, self.source,
                                                self.source_lines[line - 1]))
                continue
            result.append(Token(kind, value, line, column, self.source,
                                        self.source_lines[line - 1]))
            if declarations_only and capturing_server and kind in {"FUNCTION", "PROCEDURE"}:
                capturing_routine = True
            if declarations_only and capturing_server and not capturing_routine and kind == "VAR":
                capturing_variable = True
            if capturing_variable and kind == ";":
                capturing_server = capturing_variable = False
            if declarations_only and kind in {"ENDFUNCTION", "ENDPROCEDURE"}:
                capturing_server = capturing_routine = False
        if root_fragment:
            result.append(Token("SERVERROOTEND", None, self.line, self.column, self.source))
        compilation.finish(self.line, self.column)
        if skipping_client:
            raise IncompleteInput("Не завершена подпрограмма",
                                  self.source, self.line, self.column)
        regions.finish()
        result.append(Token("EOF", None, self.line, self.column, self.source))
        return result

    def import_name(self, directive: str, line: int, column: int) -> str:
        match = re.fullmatch(r"#\s*(?:Импорт|Import)\s+(\w+(?:\.\w+)*)\s*", directive,
                             re.IGNORECASE)
        if match is None:
            raise BSLError("Ожидается // #Импорт ИмяМодуля.bsl или "
                           "// #Импорт Каталог; пути с разделителями не поддерживаются",
                           self.source, line, column)
        value = match.group(1)
        parts = value[:-4] if value.casefold().endswith(".bsl") else value
        for part in parts.split("."):
            if not (part[0].isalpha() or part[0] == "_"):
                raise BSLError("Каждая часть имени импорта должна быть идентификатором",
                               self.source, line, column)
            if part.casefold() in KEYWORDS:
                raise BSLError("Имя модуля или каталога не может быть ключевым словом",
                               self.source, line, column)
        return value

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

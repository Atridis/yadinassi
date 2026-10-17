"""Recursive-descent statements and precedence-climbing expressions."""

from . import ast
from .errors import BSLError, IncompleteInput
from .lexer import Lexer, Token


PRECEDENCE = {
    "OR": 1, "AND": 2,
    "=": 3, "<>": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5, "%": 5,
}
class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
        self.loop_depth = 0
        self.handler_depth = 0
        self.routine_kind: str | None = None
        self.parameter_names: set[str] = set()

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def accept(self, kind: str) -> Token | None:
        if self.current.kind == kind:
            token = self.current
            self.pos += 1
            return token
        return None

    def fail(self, message: str) -> None:
        token = self.current
        error = IncompleteInput if token.kind == "EOF" else BSLError
        raise error(message, token.source, token.line, token.column)

    def expect(self, kind: str) -> Token:
        token = self.accept(kind)
        if token is None:
            self.fail(f"Ожидается {kind}, получено {self.current.value!r}")
        return token

    def parse(self) -> list[ast.Node]:
        statements = []
        routines = set()
        regions = []
        while self.current.kind != "EOF":
            self.region_directives(regions)
            if self.current.kind == "EOF":
                break
            if self.accept(";"):
                continue
            if token := self.accept("IMPORT"):
                statements.append(ast.Import(token, token.value))
                continue
            if self.accept("ATCLIENT"):
                if self.current.kind not in ("FUNCTION", "PROCEDURE"):
                    self.fail("После &НаКлиенте ожидается объявление процедуры или функции")
            if self.current.kind in ("FUNCTION", "PROCEDURE"):
                token = self.current
                kind = token.kind
                self.pos += 1
                name = self.expect("IDENT").value
                if name.casefold() in routines:
                    self.fail(f"Повторное объявление процедуры или функции: {name}")
                routines.add(name.casefold())
                self.expect("(")
                parameters = self.parameters()
                exported = bool(self.accept("EXPORT"))
                self.routine_kind = kind
                self.parameter_names = {parameter.name.casefold() for parameter in parameters}
                try:
                    body = self.block({"END" + kind})
                    self.expect("END" + kind)
                finally:
                    self.routine_kind = None
                    self.parameter_names = set()
                statements.append(ast.Routine(token, name, parameters, kind == "FUNCTION", exported, body))
                # Routine brackets are not statements and need no semicolon.
                continue
            statements.append(self.statement())
            separated = self.accept(";") or isinstance(statements[-1], ast.Label)
            self.region_directives(regions)
            if not separated and self.current.kind != "EOF":
                self.fail("Ожидается ';' между операторами")
        self.expect("EOF")
        validate_labels(statements)
        return statements

    def parameters(self) -> list[ast.Parameter]:
        parameters = []
        names = set()
        if self.accept(")"):
            return parameters
        while True:
            by_value = bool(self.accept("VAL"))
            token = self.expect("IDENT")
            name = token.value
            if name.casefold() in names:
                self.fail(f"Повторное объявление параметра: {name}")
            names.add(name.casefold())
            default = self.parameter_default() if self.accept("=") else None
            parameters.append(ast.Parameter(token, name, by_value, default))
            if not self.accept(","):
                self.expect(")")
                return parameters

    def parameter_default(self) -> ast.Node:
        # BSL defaults are constants, not arbitrary expressions or Python defaults.
        token = self.current
        if token.kind in ("+", "-"):
            self.pos += 1
            value = self.expect("NUMBER")
            default = ast.Unary(token, token.kind, ast.Literal(value, value.value))
        elif token.kind in ("NUMBER", "STRING", "TRUE", "FALSE", "UNDEFINED"):
            default = self.primary()
        else:
            self.fail("Ожидается литерал значения параметра по умолчанию")
        if self.current.kind not in (",", ")"):
            self.fail("Значение параметра по умолчанию должно быть литералом")
        return default

    def block(self, endings: set[str]) -> list[ast.Node]:
        statements = []
        regions = []
        while True:
            self.region_directives(regions)
            if self.current.kind in endings:
                break
            if self.current.kind == "EOF":
                self.fail("Не завершен блок: ожидается " + "/".join(sorted(endings)))
            if self.accept(";"):
                continue
            statements.append(self.statement())
            separated = self.accept(";") or isinstance(statements[-1], ast.Label)
            self.region_directives(regions)
            if not separated and self.current.kind not in endings:
                self.fail("Ожидается ';' между операторами")
        if regions:
            self.fail("Область пересекает границу синтаксической конструкции")
        return statements

    def region_directives(self, regions: list[Token]) -> None:
        # Regions share the surrounding statement list and its variable/routine scope.
        # Each block owns its nesting, so a region cannot cross a routine or branch.
        while self.current.kind in {"REGION", "ENDREGION"}:
            if self.current.kind == "REGION":
                regions.append(self.current)
            elif not regions:
                self.fail("Область пересекает границу синтаксической конструкции")
            else:
                regions.pop()
            self.pos += 1

    def statement(self) -> ast.Node:
        token = self.current
        if self.accept("~"):
            name = self.expect("IDENT").value
            self.expect(":")
            return ast.Label(token, name)
        if self.accept("GOTO"):
            self.expect("~")
            return ast.Goto(token, self.expect("IDENT").value)
        if token.kind == "ATCLIENT":
            self.fail("Директива исполнения допустима только перед подпрограммой уровня модуля")
        if token.kind == "IMPORT":
            self.fail("Импорт допустим только на уровне модуля")
        if token.kind in ("FUNCTION", "PROCEDURE"):
            self.fail("Процедуры и функции допустимы только на уровне модуля")
        if self.accept("RETURN"):
            if self.routine_kind is None:
                self.fail("Возврат допустим только внутри процедуры или функции")
            empty = self.current.kind in {";", "ENDPROCEDURE", "ENDFUNCTION", "ENDIF", "ELSE", "ELSIF", "ENDDO", "EXCEPT", "ENDTRY", "ENDREGION"}
            if self.routine_kind == "PROCEDURE" and not empty:
                self.fail("Процедура не может возвращать значение")
            return ast.Return(token, None if empty else self.expression())
        if self.accept("TRY"):
            body = self.block({"EXCEPT"})
            self.expect("EXCEPT")
            self.handler_depth += 1
            try:
                handler = self.block({"ENDTRY"})
                self.expect("ENDTRY")
            finally:
                self.handler_depth -= 1
            return ast.Try(token, body, handler)
        if self.accept("RAISE"):
            empty = self.current.kind in {
                ";", "EOF", "ENDPROCEDURE", "ENDFUNCTION", "ENDIF", "ELSE",
                "ELSIF", "ENDDO", "EXCEPT", "ENDTRY", "ENDREGION",
            }
            if empty and not self.handler_depth:
                self.fail("ВызватьИсключение без выражения допустимо только внутри Исключение")
            return ast.Raise(token, None if empty else self.expression())
        if self.accept("IF"):
            branches = []
            while True:
                condition = self.expression()
                self.expect("THEN")
                branches.append((condition, self.block({"ELSIF", "ELSE", "ENDIF"})))
                if not self.accept("ELSIF"):
                    break
            otherwise = self.block({"ENDIF"}) if self.accept("ELSE") else []
            self.expect("ENDIF")
            return ast.If(token, branches, otherwise)
        if self.accept("FOR"):
            if self.accept("EACH"):
                name = self.expect("IDENT").value
                self.expect("IN")
                collection = self.expression()
                return ast.ForEach(token, name, collection, self.loop_body())
            name = self.expect("IDENT").value
            self.expect("=")
            start = self.expression()
            self.expect("TO")
            end = self.expression()
            return ast.For(token, name, start, end, self.loop_body())
        if self.accept("WHILE"):
            condition = self.expression()
            return ast.While(token, condition, self.loop_body())
        if token.kind in ("BREAK", "CONTINUE"):
            if not self.loop_depth:
                self.fail("Прервать/Продолжить допустимы только внутри цикла")
            self.pos += 1
            return ast.Break(token) if token.kind == "BREAK" else ast.Continue(token)
        if self.accept("VAR"):
            names = [self.expect("IDENT").value]
            while self.accept(","):
                names.append(self.expect("IDENT").value)
            for name in names:
                if name.casefold() in self.parameter_names:
                    self.fail(f"Переменная уже объявлена как параметр: {name}")
            return ast.Var(token, names)
        # Assignment is a statement, while '=' in an expression is comparison.
        if token.kind == "IDENT":
            start = self.pos
            target = self.postfix(self.primary())
            if self.accept("="):
                if not isinstance(target, (ast.Name, ast.Index, ast.Attribute)):
                    self.fail("Недопустимая цель присваивания")
                return ast.Assign(token, target, self.expression())
            self.pos = start
        return ast.ExpressionStatement(token, self.expression())

    def loop_body(self) -> list[ast.Node]:
        self.expect("DO")
        self.loop_depth += 1
        try:
            body = self.block({"ENDDO"})
            self.expect("ENDDO")
            return body
        finally:
            self.loop_depth -= 1

    def expression(self, minimum: int = 1) -> ast.Node:
        token = self.current
        if token.kind in ("+", "-", "NOT"):
            self.pos += 1
            # NOT binds less tightly than comparisons, but more tightly than AND.
            left = ast.Unary(token, token.kind, self.expression(3 if token.kind == "NOT" else 6))
        else:
            left = self.postfix(self.primary())
        while PRECEDENCE.get(self.current.kind, 0) >= minimum:
            token = self.current
            self.pos += 1
            right = self.expression(PRECEDENCE[token.kind] + 1)
            left = ast.Binary(token, left, token.kind, right)
        return left

    def primary(self) -> ast.Node:
        token = self.current
        if token.kind in ("NUMBER", "STRING", "TRUE", "FALSE", "UNDEFINED"):
            self.pos += 1
            value = {"TRUE": True, "FALSE": False, "UNDEFINED": None}.get(token.kind, token.value)
            return ast.Literal(token, value)
        if self.accept("IDENT"):
            return ast.Name(token, token.value)
        if self.accept("REGION"):
            # EDT admits a complete expression as a region's contents, including
            # an optional trailing semicolon. The region adds no runtime node.
            value = self.expression()
            self.accept(";")
            self.expect("ENDREGION")
            return value
        if self.accept("?"):
            self.expect("(")
            condition = self.expression()
            self.expect(",")
            when_true = self.expression()
            self.expect(",")
            when_false = self.expression()
            self.expect(")")
            return ast.Conditional(token, condition, when_true, when_false)
        if self.accept("("):
            value = self.expression()
            self.expect(")")
            return ast.Group(token, value)
        if self.accept("NEW"):
            name = self.expect("IDENT").value
            arguments = self.arguments() if self.accept("(") else []
            return ast.New(token, name, arguments)
        self.fail(f"Ожидается выражение, получено {token.value!r}")

    def postfix(self, value: ast.Node) -> ast.Node:
        while True:
            if token := self.accept("("):
                value = ast.Call(token, value, self.arguments())
            elif token := self.accept("."):
                value = ast.Attribute(token, value, self.expect("IDENT").value)
            elif token := self.accept("["):
                index = self.expression()
                self.expect("]")
                value = ast.Index(token, value, index)
            else:
                return value

    def arguments(self) -> list[ast.Node]:
        arguments = []
        if self.accept(")"):
            return arguments
        while True:
            if self.current.kind == ",":
                arguments.append(ast.OmittedArgument(self.current))
            else:
                arguments.append(self.expression())
            if not self.accept(","):
                break
            if self.current.kind == ")":
                self.fail("Запятая в конце списка аргументов пока не поддерживается; "
                          "опустите конечные необязательные параметры без запятой")
        self.expect(")")
        return arguments


def validate_labels(statements: list[ast.Node]) -> None:
    """Resolve one routine/module at a time, before any execution side effects.

    The current interpreter supports jumping within an active statement list or
    outward to an ancestor list. Entering an inactive block is deliberately an
    explicit implementation boundary, not an asserted restriction of native BSL.
    """
    labels: dict[str, tuple[ast.Label, tuple[int, ...]]] = {}
    jumps: list[tuple[ast.Goto, tuple[int, ...]]] = []

    def fail(node: ast.Node, message: str) -> None:
        token = node.token
        raise BSLError(message, token.source, token.line, token.column)

    def collect(body: list[ast.Node], parents: tuple[int, ...]) -> None:
        path = (*parents, id(body))
        for node in body:
            if isinstance(node, ast.Label):
                name = node.name.casefold()
                if name in labels:
                    fail(node, f"Повторное объявление метки: {node.name}")
                labels[name] = (node, path)
            elif isinstance(node, ast.Goto):
                jumps.append((node, path))
            elif isinstance(node, ast.Routine):
                validate_labels(node.body)
            elif isinstance(node, ast.If):
                for _, branch in node.branches:
                    collect(branch, path)
                collect(node.otherwise, path)
            elif isinstance(node, (ast.For, ast.ForEach, ast.While)):
                collect(node.body, path)
            elif isinstance(node, ast.Try):
                collect(node.body, path)
                collect(node.handler, path)

    collect(statements, ())
    for node, path in jumps:
        target = labels.get(node.name.casefold())
        if target is None:
            fail(node, f"Метка не определена: {node.name}")
        target_path = target[1]
        if path[:len(target_path)] != target_path:
            fail(node, f"Переход внутрь другого блока пока не поддерживается: {node.name}")


def parse(text: str, source: str = "<строка>") -> list[ast.Node]:
    return Parser(Lexer(text, source).tokens()).parse()

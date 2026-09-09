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
        statements = self.block({"EOF"})
        self.expect("EOF")
        return statements

    def block(self, endings: set[str]) -> list[ast.Node]:
        statements = []
        while self.current.kind not in endings:
            if self.current.kind == "EOF":
                self.fail("Не завершен блок: ожидается " + "/".join(sorted(endings)))
            if self.accept(";"):
                continue
            statements.append(self.statement())
            if not self.accept(";") and self.current.kind not in endings:
                self.fail("Ожидается ';' между операторами")
        return statements

    def statement(self) -> ast.Node:
        token = self.current
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
            return ast.Var(token, names)
        # Assignment is a statement, while '=' in an expression is comparison.
        if token.kind == "IDENT":
            start = self.pos
            target = self.postfix(self.primary())
            if self.accept("="):
                if not isinstance(target, (ast.Name, ast.Index)):
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
        if self.accept("("):
            value = self.expression()
            self.expect(")")
            return value
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
        if not self.accept(")"):
            arguments.append(self.expression())
            while self.accept(","):
                arguments.append(self.expression())
            self.expect(")")
        return arguments


def parse(text: str, source: str = "<строка>") -> list[ast.Node]:
    return Parser(Lexer(text, source).tokens()).parse()

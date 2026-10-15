"""Tree-walking interpreter with persistent state and injectable builtins."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Callable

from . import ast
from .errors import BSLError
from .parser import parse
from .values import (
    BSLArray, BSLObject, HostFunction, boolean, equal, number, require_number, to_string,
)


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Return(Exception):
    def __init__(self, value: object):
        self.value = value


@dataclass
class _Reference:
    """A caller-owned storage location, captured before entering the callee."""

    get: Callable[[], object]
    set: Callable[[object], None]


class Interpreter:
    def __init__(self, output: Callable[[str], None] = print):
        self.variables: dict[str, object] = {}
        self.functions: dict[str, HostFunction] = {}
        self.routines: dict[str, ast.Routine] = {}
        self.module_names: set[str] = set()
        self.locals: dict[str, object] | None = None
        self.types: dict[str, HostFunction] = {}
        self.output = output
        self.register_function("Сообщить", self._message, "Message")
        self.register_function("Строка", to_string, "String")
        self.register_function("Число", number, "Number")
        self.register_function("Булево", boolean, "Boolean")
        self.register_function("СтрДлина", self._string_length, "StrLen")
        self.register_type("Массив", BSLArray, "Array")

    def register_function(self, name: str, function: Callable, *aliases: str) -> None:
        wrapper = HostFunction(name, function)
        for alias in (name, *aliases):
            self.functions[alias.casefold()] = wrapper

    def register_type(self, name: str, factory: Callable, *aliases: str) -> None:
        wrapper = HostFunction(name, factory)
        for alias in (name, *aliases):
            self.types[alias.casefold()] = wrapper

    def _message(self, value: object) -> None:
        self.output(to_string(value))

    @staticmethod
    def _string_length(value: object) -> Decimal:
        if not isinstance(value, str):
            raise TypeError("СтрДлина ожидает строку")
        return Decimal(len(value))

    def execute(self, text: str, source: str = "<строка>") -> object:
        return self.execute_program(parse(text, source))

    def execute_program(self, program: list[ast.Node]) -> object:
        # Keep decimal arithmetic independent of the embedding application's context.
        with localcontext() as context:
            context.prec = 38
            # Register module declarations before executing any module statements.
            for node in program:
                if isinstance(node, ast.Routine):
                    self.routines[node.name.casefold()] = node
                elif isinstance(node, ast.Var):
                    for name in node.names:
                        self.module_names.add(name.casefold())
                        self.variables.setdefault(name.casefold(), None)
            return self.block(program)

    def block(self, statements: list[ast.Node]) -> object:
        result = None
        for statement in statements:
            result = self.visit(statement)
        return result

    def visit(self, node: ast.Node) -> object:
        try:
            handler = getattr(self, f"visit_{type(node).__name__}")
            return handler(node)
        except BSLError:
            raise
        except (ArithmeticError, ValueError, TypeError, IndexError, RecursionError) as error:
            message = str(error) or type(error).__name__
            if isinstance(error, ZeroDivisionError):
                message = "Деление на ноль"
            token = node.token
            raise BSLError(message, token.source, token.line, token.column) from None

    def visit_Literal(self, node: ast.Literal) -> object:
        return node.value

    def visit_Name(self, node: ast.Name) -> object:
        name = node.name.casefold()
        if self.locals is not None and name in self.locals:
            value = self.locals[name]
            return value.get() if isinstance(value, _Reference) else value
        if name in self.variables and (self.locals is None or name in self.module_names):
            return self.variables[name]
        if name in self.routines:
            raise TypeError(f"Процедуру или функцию необходимо вызвать: {node.name}")
        if name in self.functions:
            return self.functions[name]
        raise ValueError(f"Переменная или функция не определена: {node.name}")

    def visit_Group(self, node: ast.Group) -> object:
        return self.visit(node.expression)

    def visit_Unary(self, node: ast.Unary) -> object:
        value = self.visit(node.operand)
        if node.operator == "NOT":
            return not boolean(value)
        value = require_number(value)
        return value if node.operator == "+" else -value

    def visit_Binary(self, node: ast.Binary) -> object:
        left = self.visit(node.left)
        operator = node.operator
        if operator == "AND":
            return boolean(left) and boolean(self.visit(node.right))
        if operator == "OR":
            return boolean(left) or boolean(self.visit(node.right))
        right = self.visit(node.right)
        if operator == "=":
            return equal(left, right)
        if operator == "<>":
            return not equal(left, right)
        if operator in ("<", "<=", ">", ">="):
            if type(left) is not type(right) or not isinstance(left, (Decimal, str, bool)):
                raise TypeError("Значения несовместимы для сравнения")
            if operator == "<":
                return left < right
            if operator == "<=":
                return left <= right
            if operator == ">":
                return left > right
            return left >= right
        if operator == "+" and isinstance(left, str):
            return left + to_string(right)
        left, right = require_number(left), require_number(right)
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            if right == 0:
                raise ZeroDivisionError
            return left / right
        if operator == "%":
            if right == 0:
                raise ZeroDivisionError
            return left % right
        raise ValueError(f"Неизвестный оператор: {operator}")

    def visit_Conditional(self, node: ast.Conditional) -> object:
        branch = node.when_true if boolean(self.visit(node.condition)) else node.when_false
        return self.visit(branch)

    def visit_Attribute(self, node: ast.Attribute) -> object:
        value = self.visit(node.object)
        if not isinstance(value, BSLObject):
            raise TypeError("Значение не имеет методов или свойств")
        return value.get_member(node.name)

    def visit_Index(self, node: ast.Index) -> object:
        value = self.visit(node.object)
        if not isinstance(value, BSLArray):
            raise TypeError("Индексирование поддерживается только для массива")
        return value.get(self.visit(node.index))

    def visit_Call(self, node: ast.Call) -> object:
        return self.call(node, require_value=True)

    def call(self, node: ast.Call, *, require_value: bool) -> object:
        callee = self.ungroup(node.callee)
        routine = (self.routines.get(callee.name.casefold())
                   if isinstance(callee, ast.Name) else None)
        if routine is not None:
            function = routine
            if require_value and not function.is_function:
                raise TypeError(f"Процедура не возвращает значение: {function.name}")
            if len(node.arguments) != len(function.parameters):
                raise TypeError(f"{function.name} ожидает {len(function.parameters)} аргументов, "
                                f"получено {len(node.arguments)}")
            # Bind left to right in the caller's frame. Val snapshots the value,
            # while ordinary parameters keep a live alias to assignable storage.
            bindings = {}
            for parameter, argument in zip(function.parameters, node.arguments):
                bindings[parameter.name.casefold()] = (
                    self.visit(argument) if parameter.by_value else self.argument(argument)
                )
            previous = self.locals
            self.locals = bindings
            try:
                self.block(function.body)
            except _Return as returned:
                return returned.value
            finally:
                self.locals = previous
            return None
        function = self.visit(node.callee)
        if not isinstance(function, HostFunction):
            raise TypeError("Значение не является функцией")
        return function(*(self.visit(argument) for argument in node.arguments))

    def argument(self, node: ast.Node) -> object:
        if isinstance(node, ast.Name):
            name = node.name.casefold()
            if self.locals is not None and name in self.locals:
                scope = self.locals
            elif name in self.variables and (self.locals is None or name in self.module_names):
                scope = self.variables
            else:
                return self.visit(node)
            if isinstance(scope[name], _Reference):
                return scope[name]
            return _Reference(lambda: scope[name], lambda value: scope.__setitem__(name, value))
        target = self.ungroup(node)
        if isinstance(target, (ast.Name, ast.Index, ast.Attribute)):
            raise TypeError("Передача свойства, элемента массива или переменной в скобках "
                            "по ссылке пока не поддерживается; используйте Знач/Val "
                            "или отдельную переменную")
        # Literals and computed expressions have no caller storage to rebind.
        return self.visit(node)

    @staticmethod
    def ungroup(node: ast.Node) -> ast.Node:
        while isinstance(node, ast.Group):
            node = node.expression
        return node

    def visit_New(self, node: ast.New) -> object:
        factory = self.types.get(node.name.casefold())
        if factory is None:
            raise ValueError(f"Тип не определен: {node.name}")
        return factory(*(self.visit(argument) for argument in node.arguments))

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.target, ast.Name):
            self.set_variable(node.target.name, self.visit(node.value))
        else:
            value = self.visit(node.target.object)
            if not isinstance(value, BSLArray):
                raise TypeError("Индексирование поддерживается только для массива")
            index = self.visit(node.target.index)
            value.set(index, self.visit(node.value))

    def set_variable(self, name: str, value: object) -> None:
        name = name.casefold()
        if self.locals is None or (name in self.module_names and name not in self.locals):
            self.variables[name] = value
        elif isinstance(self.locals.get(name), _Reference):
            self.locals[name].set(value)
        else:
            self.locals[name] = value

    def visit_Routine(self, node: ast.Routine) -> None:
        # Declarations are registered by execute_program, never executed in place.
        pass

    def visit_Return(self, node: ast.Return) -> None:
        raise _Return(self.visit(node.value) if node.value is not None else None)

    def visit_ExpressionStatement(self, node: ast.ExpressionStatement) -> object:
        expression = self.ungroup(node.expression)
        if isinstance(expression, ast.Call):
            # A procedure is allowed only when its result is discarded.
            return self.call(expression, require_value=False)
        return self.visit(node.expression)

    def visit_Var(self, node: ast.Var) -> None:
        for name in node.names:
            (self.variables if self.locals is None else self.locals).setdefault(name.casefold(), None)

    def visit_If(self, node: ast.If) -> None:
        for condition, body in node.branches:
            if boolean(self.visit(condition)):
                self.block(body)
                return
        self.block(node.otherwise)

    def iteration(self, body: list[ast.Node]) -> bool:
        try:
            self.block(body)
        except _Continue:
            pass
        except _Break:
            return False
        return True

    def visit_For(self, node: ast.For) -> None:
        start = require_number(self.visit(node.start))
        end = require_number(self.visit(node.end))
        name = node.name.casefold()
        self.set_variable(name, start)
        while require_number(self.visit_Name(ast.Name(node.token, name))) <= end:
            if not self.iteration(node.body):
                break
            self.set_variable(name, require_number(self.visit_Name(ast.Name(node.token, name))) + Decimal(1))

    def visit_ForEach(self, node: ast.ForEach) -> None:
        collection = self.visit(node.collection)
        if not isinstance(collection, BSLArray):
            raise TypeError("Для Каждого ожидает массив")
        for item in collection:
            self.set_variable(node.name, item)
            if not self.iteration(node.body):
                break

    def visit_While(self, node: ast.While) -> None:
        while boolean(self.visit(node.condition)):
            if not self.iteration(node.body):
                break

    def visit_Break(self, node: ast.Break) -> None:
        raise _Break

    def visit_Continue(self, node: ast.Continue) -> None:
        raise _Continue

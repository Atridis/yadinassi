"""Tree-walking interpreter with persistent state and injectable builtins."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Callable

from . import ast
from .errors import BSLError
from .parser import parse
from .lexer import KEYWORDS
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


class _Module:
    """Only exported BSL routines are callable; no Python member reflection."""

    def __init__(self, interpreter: "Interpreter", path: Path):
        self.interpreter = interpreter
        self.path = path

    def routine(self, name: str) -> ast.Routine:
        routine = self.interpreter.routines.get(name.casefold())
        if routine is None or not routine.exported:
            raise ValueError(f"Экспортная процедура или функция не найдена: {name}")
        return routine


class _Namespace:
    """A directory's explicitly imported children, never arbitrary Python members."""

    def __init__(self, path: Path):
        self.path = path
        self.members: dict[str, _Module | _Namespace] = {}


class Interpreter:
    def __init__(self, output: Callable[[str], None] = print, *, encoding: str = "utf-8-sig"):
        self.variables: dict[str, object] = {}
        self.functions: dict[str, HostFunction] = {}
        self.routines: dict[str, ast.Routine] = {}
        self.module_names: set[str] = set()
        self.locals: dict[str, object] | None = None
        self.types: dict[str, HostFunction] = {}
        self.output = output
        self.encoding = encoding
        self.imports: dict[str, _Module | _Namespace] = {}
        self._module_cache: dict[Path, _Module] = {}
        self._loading: list[Path] = []
        self.register_function("Сообщить", self._message, "Message")
        self.register_function("Строка", to_string, "String")
        self.register_function("Число", number, "Number")
        self.register_function("Булево", boolean, "Boolean")
        self.register_function("СтрДлина", self._string_length, "StrLen")
        self.register_type("Массив", BSLArray, "Array")

    @property
    def execution_context(self) -> str:
        """Standalone root code, routines and imports run in the client context only."""
        return "client"

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
        # A diagnostic source label need not name a readable filesystem path.
        if not any(isinstance(node, ast.Import) for node in program):
            return self._execute_program(program)
        source = program[0].token.source if program else "<строка>"
        path = None if source.startswith("<") else Path(source).resolve()
        if path is None:
            return self._execute_program(program)
        self._loading.append(path)
        try:
            return self._execute_program(program)
        finally:
            self._loading.pop()

    def _execute_program(self, program: list[ast.Node]) -> object:
        # Keep decimal arithmetic independent of the embedding application's context.
        with localcontext() as context:
            context.prec = 38
            # Reserve import names before any module initialization effects.
            names = set(self.imports)
            names.update(node.filename.split(".")[0].casefold()
                         for node in program if isinstance(node, ast.Import))
            for node in program:
                declared = ([node.name] if isinstance(node, ast.Routine) else
                            node.names if isinstance(node, ast.Var) else [])
                if any(name.casefold() in names for name in declared):
                    token = node.token
                    raise BSLError("Имя импорта конфликтует с объявлением", token.source,
                                   token.line, token.column)
            # Register module declarations before executing any module statements.
            for node in program:
                if isinstance(node, ast.Routine):
                    self.routines[node.name.casefold()] = node
                elif isinstance(node, ast.Var):
                    for name in node.names:
                        self.module_names.add(name.casefold())
                        self.variables.setdefault(name.casefold(), None)
            for node in program:
                if isinstance(node, ast.Import):
                    self.visit(node)
            return self.block([node for node in program if not isinstance(node, ast.Import)])

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
        if name in self.imports:
            raise TypeError(f"Имя модуля допустимо только при вызове его подпрограммы: {node.name}")
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
        owner = self
        if isinstance(callee, ast.Attribute):
            module = self.import_receiver(callee.object)
            if module is not None:
                if not isinstance(module, _Module):
                    raise TypeError("Пространство каталога не содержит вызываемых подпрограмм")
                owner = module.interpreter
                routine = module.routine(callee.name)
        if routine is not None:
            return self.call_routine(routine, node.arguments, owner, require_value=require_value)
        self.reject_host_omissions(node.arguments)
        function = self.visit(node.callee)
        if not isinstance(function, HostFunction):
            raise TypeError("Значение не является функцией")
        return function(*(self.visit(argument) for argument in node.arguments))

    def import_receiver(self, node: ast.Node) -> _Module | _Namespace | None:
        """Resolve only explicit namespace syntax; ordinary values keep normal dispatch."""
        node = self.ungroup(node)
        if isinstance(node, ast.Name):
            name = node.name.casefold()
            if self.locals is not None and name in self.locals:
                return None
            return self.imports.get(name)
        if isinstance(node, ast.Attribute):
            parent = self.import_receiver(node.object)
            if parent is None:
                return None
            if not isinstance(parent, _Namespace):
                raise TypeError("Вложенное имя допустимо только для пространства каталога")
            child = parent.members.get(node.name.casefold())
            if child is None:
                raise ValueError(f"Импортированное имя не найдено: {node.name}")
            return child
        return None

    def call_routine(self, function: ast.Routine, arguments: list[ast.Node],
                     owner: "Interpreter", *, require_value: bool) -> object:
        if function.execution_context != owner.execution_context:
            raise ValueError("Подпрограмма требует неподдерживаемый контекст исполнения")
        if require_value and not function.is_function:
            raise TypeError(f"Процедура не возвращает значение: {function.name}")
        required = max((index + 1 for index, parameter in enumerate(function.parameters)
                        if parameter.default is None), default=0)
        if not required <= len(arguments) <= len(function.parameters):
            raise TypeError(f"{function.name} ожидает {len(function.parameters)} аргументов, "
                            f"получено {len(arguments)}")
        # Bind left to right in the caller's frame. Val snapshots the value,
        # while ordinary parameters keep a live alias to assignable storage.
        bindings = {}
        for index, parameter in enumerate(function.parameters):
            argument = arguments[index] if index < len(arguments) else None
            if argument is None or isinstance(argument, ast.OmittedArgument):
                value = self.visit(parameter.default) if parameter.default is not None else None
            else:
                value = self.visit(argument) if parameter.by_value else self.argument(argument)
            bindings[parameter.name.casefold()] = value
        previous = owner.locals
        owner.locals = bindings
        try:
            owner.block(function.body)
        except _Return as returned:
            return returned.value
        finally:
            owner.locals = previous
        return None

    @staticmethod
    def reject_host_omissions(arguments: list[ast.Node]) -> None:
        if any(isinstance(argument, ast.OmittedArgument) for argument in arguments):
            raise TypeError("Пропуск аргументов встроенных функций, методов и конструкторов "
                            "пока не поддерживается")

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
        self.reject_host_omissions(node.arguments)
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
        if name in self.imports and self.locals is None:
            raise ValueError(f"Нельзя присвоить значение имени импорта: {name}")
        if self.locals is None or (name in self.module_names and name not in self.locals):
            self.variables[name] = value
        elif isinstance(self.locals.get(name), _Reference):
            self.locals[name].set(value)
        else:
            self.locals[name] = value

    def visit_Import(self, node: ast.Import) -> None:
        name = node.filename.split(".")[0].casefold()
        if name in self.variables or name in self.routines or name in self.functions:
            raise ValueError(f"Имя импорта уже занято: {name}")
        if node.token.source.startswith("<"):
            raise ValueError("Для импорта нужен путь исходного файла; "
                             "импорт из команды и консоли пока не поддерживается")
        is_file = node.filename.casefold().endswith(".bsl")
        parts = (node.filename[:-4] if is_file else node.filename).split(".")
        relative = (Path(*parts[:-1], parts[-1] + node.filename[-4:])
                    if is_file else Path(*parts))
        path = Path(node.token.source).parent / relative
        try:
            base = Path(node.token.source).resolve().parent
            path = (base / relative).resolve()
            directories = [(base / Path(*parts[:index + 1])).resolve()
                           for index in range(len(parts) - int(is_file))]
            children = []
            if not is_file:
                for child in sorted(path.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
                    if child.suffix.casefold() != ".bsl" or not child.is_file():
                        continue
                    stem = child.stem
                    if (not stem or not (stem[0].isalpha() or stem[0] == "_")
                            or not all(char.isalnum() or char == "_" for char in stem)
                            or stem.casefold() in KEYWORDS):
                        raise ValueError(f"Имя модуля должно быть идентификатором: {child.name}")
                    children.append((stem, child.resolve()))
        except (OSError, RuntimeError) as error:
            raise ValueError(f"Не удалось прочитать путь импорта {path}: {error}") from None
        # Stage every namespace and check every collision before loading any code.
        members = self.imports
        pending = []
        for index, part in enumerate(parts):
            key = part.casefold()
            module_leaf = is_file and index == len(parts) - 1
            target = path if module_leaf else directories[index]
            existing = members.get(key)
            if existing is not None:
                self._check_import_binding(existing, target, module_leaf, part)
            elif not module_leaf:
                existing = _Namespace(target)
                pending.append((members, key, existing))
            if not module_leaf:
                members = existing.members
        if is_file:
            children = [(parts[-1], path)]
        seen = set()
        for name, target in children:
            key = name.casefold()
            if key in seen:
                raise ValueError(f"Имя импорта конфликтует с другим файлом: {name}")
            seen.add(key)
            if key in members:
                self._check_import_binding(members[key], target, True, name)
        loaded = [(name.casefold(), self._load_module(target)) for name, target in children]
        for parent, key, namespace in pending:
            parent[key] = namespace
        members.update(loaded)

    @staticmethod
    def _check_import_binding(existing: _Module | _Namespace, path: Path,
                              is_module: bool, name: str) -> None:
        if isinstance(existing, _Module) != is_module or existing.path != path:
            raise ValueError(f"Имя импорта уже занято другим модулем или каталогом: {name}")

    def _load_module(self, path: Path) -> _Module:
        if path in self._loading:
            chain = " -> ".join(str(item) for item in [*self._loading, path])
            raise ValueError(f"Циклический импорт: {chain}")
        module = self._module_cache.get(path)
        if module is None:
            try:
                text = path.read_text(encoding=self.encoding)
            except (OSError, UnicodeError, LookupError) as error:
                raise ValueError(f"Не удалось прочитать модуль {path}: {error}") from None
            child = Interpreter(self.output, encoding=self.encoding)
            child.functions = self.functions.copy()
            child.types = self.types.copy()
            child._module_cache = self._module_cache
            child._loading = self._loading
            child.execute(text, str(path))
            module = _Module(child, path)
            self._module_cache[path] = module
        return module

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
        if self.locals is None and any(name.casefold() in self.imports for name in node.names):
            raise ValueError("Имя импорта конфликтует с объявлением")
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

"""Tree-walking interpreter with persistent state and injectable builtins."""

from decimal import Decimal, localcontext
from pathlib import Path
from typing import Callable

from . import ast, bits, clocks, date_time_conversions, dates, elementary, numbers, serialization, strings, type_values, value_checks, xml_values
from .round_modes import BSLRoundModes, ROUND_MODES
from .search_directions import BSLSearchDirections, SEARCH_DIRECTIONS
from .sort_directions import BSLSortDirections, SORT_DIRECTIONS
from .xml_processing import XML_STRING_PROCESSING
from .type_descriptions import BSLTypeDescription
from .value_tables import (BSLValueTable, BSLValueTableColumnCollection,
                           BSLValueTableColumn, BSLValueTableRow,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .value_lists import BSLValueList, BSLValueListItem
from .type_qualifiers import (
    ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)
from .errors import BSLError, BSLRuntimeError
from .collation import string_key
from .parser import parse, parse_expression, parse_fragment, validate_labels
from .lexer import KEYWORDS
from .maps import BSLFixedMap, BSLMap
from .native_targets import WINDOWS_8_3_27_2342, target_context, validate_native_target
from .structures import BSLFixedStructure, BSLStructure, fill_property_values
from .values import (
    BSLArray, BSLFixedArray, BSLObject, BSLType, HostFunction, Reference as _Reference,
    boolean, divide, equal, number, require_number, to_string,
)


_COLLECTIONS = (BSLArray, BSLFixedArray, BSLStructure, BSLFixedStructure,
                BSLMap, BSLFixedMap, BSLValueTable, BSLValueTableColumnCollection,
                BSLValueTableRow, BSLCollectionIndexes, BSLCollectionIndex, BSLValueList)
_TABLE_COLLECTIONS = (BSLValueTable, BSLValueTableColumnCollection, BSLValueTableRow,
                      BSLCollectionIndexes, BSLCollectionIndex, BSLValueList)


# Explicit Yadinassi resource limits, not asserted native language limits.
EVAL_MAX_SOURCE = 65536
EVAL_MAX_DEPTH = 16
EXECUTE_MAX_SOURCE = 65536
EXECUTE_MAX_DEPTH = 16


def _eval_marker(value: object) -> object:
    # The interpreter supplies the current module/frame at the call site.
    raise TypeError("Вычислить требует контекст интерпретатора")


class _Goto(Exception):
    def __init__(self, node: ast.Goto):
        self.node = node
        self.name = node.name.casefold()


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Return(Exception):
    def __init__(self, value: object):
        self.value = value


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
    def __init__(self, output: Callable[[str], None] = print, *, encoding: str = "utf-8-sig",
                 native_target: str = WINDOWS_8_3_27_2342):
        self._native_target = validate_native_target(native_target)
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
        # Imports share this dynamic handler stack, independent of variable frames.
        self._handled_errors: list[BSLRuntimeError | None] = []
        self._execute_depth = [0]
        self._eval_depth = [0]  # Shared by imported modules, like the handler stack.
        self.register_function("Вычислить", _eval_marker, "Eval")
        self.register_function("Сообщить", self._message, "Message")
        self.register_function("Строка", to_string, "String")
        self.register_function("Число", number, "Number")
        self.register_function("Булево", boolean, "Boolean")
        self.register_function("ЗаполнитьЗначенияСвойств", fill_property_values,
                               "FillPropertyValues", returns_value=False)
        self.register_function("ЗначениеЗаполнено", value_checks.value_is_filled, "ValueIsFilled")
        self.register_function("Тип", type_values.type_by_name, "Type")
        self.register_function("ТипЗнч", type_values.type_of, "TypeOf")
        self.register_function("ЗначениеВСтрокуВнутр", serialization.value_to_string_internal,
                               "ValueToStringInternal")
        self.register_function("ЗначениеИзСтрокиВнутр", serialization.value_from_string_internal,
                               "ValueFromStringInternal")
        for name, function, alias in (*strings.BUILTINS, *numbers.BUILTINS,
                                      *xml_values.BUILTINS, *bits.BUILTINS, *elementary.BUILTINS,
                                      *dates.BUILTINS, *clocks.BUILTINS,
                                      *date_time_conversions.BUILTINS):
            self.register_function(name, function, alias)
        self.register_function("ОписаниеОшибки", self._error_description, "ErrorDescription")
        self.register_type("Массив", BSLArray, "Array")
        self.register_type("Структура", BSLStructure, "Structure")
        self.register_type("Соответствие", BSLMap, "Map")
        self.register_type("ФиксированныйМассив", BSLFixedArray, "FixedArray")
        self.register_type("ФиксированнаяСтруктура", BSLFixedStructure, "FixedStructure")
        self.register_type("ФиксированноеСоответствие", BSLFixedMap, "FixedMap")

        self.register_type("ТаблицаЗначений", BSLValueTable, "ValueTable")
        self.register_type("СписокЗначений", BSLValueList, "ValueList")
        self.register_type("ОписаниеТипов", BSLTypeDescription, "TypeDescription")
        self.register_type("КвалификаторыЧисла", BSLNumberQualifiers, "NumberQualifiers")
        self.register_type("КвалификаторыСтроки", BSLStringQualifiers, "StringQualifiers")
        self.register_type("КвалификаторыДаты", BSLDateQualifiers, "DateQualifiers")
        self.register_type("КвалификаторыДвоичныхДанных", BSLBinaryDataQualifiers, "BinaryDataQualifiers")

    @property
    def native_target(self) -> str:
        """The explicitly selected native checkpoint, shared by this VM's imports."""
        return self._native_target

    @property
    def execution_context(self) -> str:
        """Standalone root code, routines and imports run in the client context only."""
        return "client"

    def register_function(self, name: str, function: Callable, *aliases: str,
                          returns_value: bool = True) -> None:
        wrapper = HostFunction(name, function, returns_value=returns_value)
        for alias in (name, *aliases):
            self.functions[alias.casefold()] = wrapper

    def register_type(self, name: str, factory: Callable, *aliases: str) -> None:
        wrapper = HostFunction(name, factory)
        for alias in (name, *aliases):
            self.types[alias.casefold()] = wrapper

    def _message(self, value: object) -> None:
        self.output(to_string(value))

    def _error_description(self) -> str:
        return (str(self._handled_errors[-1])
                if self._handled_errors and self._handled_errors[-1] is not None else "")

    def _evaluate(self, argument: ast.Node) -> object:
        value = self.visit(argument)
        # Native evidence covers a Number argument 12. Other non-string values
        # are deliberately rejected; do not call arbitrary Python __str__ hooks.
        if type(value) is str:
            text = value
        elif type(value) is Decimal and value.is_finite():
            text = to_string(value)
        else:
            raise TypeError("Вычислить: ожидается строка или конечное число")
        if len(text) > EVAL_MAX_SOURCE:
            raise ValueError("Вычислить: превышен предел текста Yadinassi (65536 символов)")
        if self._eval_depth[0] >= EVAL_MAX_DEPTH:
            raise ValueError("Вычислить: превышен предел вложенности Yadinassi (16)")
        self._eval_depth[0] += 1
        try:
            # Parse and consume the entire input before executing even its first call.
            try:
                expression = parse_expression(text)
            except BSLError as error:
                raise BSLRuntimeError(error.message, error.source, error.line, error.column) from None
            return self.visit(expression)
        except RecursionError:
            raise ValueError("Вычислить: превышен предел глубины выражения Yadinassi") from None
        finally:
            self._eval_depth[0] -= 1

    def visit_Execute(self, node: ast.Execute) -> None:
        value = self.visit(node.expression)
        # Native checkpoint accepts Undefined as an empty fragment, not Number.
        if value is None:
            value = ""
        if type(value) is not str:
            raise TypeError("Выполнить: ожидается строка или Неопределено")
        if len(value) > EXECUTE_MAX_SOURCE:
            raise ValueError("Выполнить: превышен предел текста Yadinassi (65536 символов)")
        if self._execute_depth[0] >= EXECUTE_MAX_DEPTH:
            raise ValueError("Выполнить: превышен предел вложенности Yadinassi (16)")
        self._execute_depth[0] += 1
        previous = self.locals
        try:
            try:
                program = parse_fragment(value)
            except BSLError as error:
                raise BSLRuntimeError(error.message, error.source, error.line, error.column) from None
            # Existing bindings are live references, including reference parameters.
            # Newly assigned names belong only to this fragment. A nested fragment
            # may see them, but does not leak its own new names back to this one.
            scope = self.variables if previous is None else previous
            self.locals = {
                name: item if isinstance(item, _Reference) else _Reference(
                    lambda name=name: scope[name],
                    lambda value, name=name: scope.__setitem__(name, value))
                for name, item in scope.items()
            }
            self.block(program)
        except RecursionError:
            raise ValueError("Выполнить: превышен предел глубины фрагмента Yadinassi") from None
        finally:
            self.locals = previous
            self._execute_depth[0] -= 1

    def execute(self, text: str, source: str = "<строка>") -> object:
        return self.execute_program(parse(text, source))

    def execute_program(self, program: list[ast.Node]) -> object:
        with target_context(self.native_target):
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
        # Also validate callers supplying an AST directly. No import or declaration
        # effects may precede label resolution.
        validate_labels(program)
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
        labels = {node.name.casefold(): index for index, node in enumerate(statements)
                  if isinstance(node, ast.Label)}
        position = 0
        while position < len(statements):
            try:
                result = self.visit(statements[position])
            except _Goto as jump:
                if jump.name not in labels:
                    raise
                position = labels[jump.name]
            else:
                position += 1
        return result

    def visit(self, node: ast.Node) -> object:
        try:
            handler = getattr(self, f"visit_{type(node).__name__}")
            return handler(node)
        except BSLError:
            raise
        except (ArithmeticError, ValueError, TypeError, IndexError, RecursionError) as error:
            message = str(error) or type(error).__name__
            if isinstance(error, RecursionError) and self._eval_depth[0]:
                message = "Вычислить: превышен предел глубины выражения Yadinassi"
            if isinstance(error, ZeroDivisionError):
                message = "Деление на ноль"
            token = node.token
            raise BSLRuntimeError(message, token.source, token.line, token.column) from None

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
        if name in ("допустимыйзнак", "allowedsign"):
            return ALLOWED_SIGNS
        if name in ("допустимаядлина", "allowedlength"):
            return ALLOWED_LENGTHS
        if name in ("частидаты", "datefractions"):
            return DATE_FRACTIONS
        if name in ("режимокругления", "roundmode"):
            return ROUND_MODES
        if name in ("обработкастрокиxml", "xmlstringprocessing"):
            return XML_STRING_PROCESSING
        if name in ("направлениепоиска", "searchdirection"):
            return SEARCH_DIRECTIONS
        if name in ("направлениесортировки", "sortdirection"):
            return SORT_DIRECTIONS
        raise ValueError(f"Переменная или функция не определена: {node.name}")

    def visit_Group(self, node: ast.Group) -> object:
        return self.visit(node.expression)

    def visit_Unary(self, node: ast.Unary) -> object:
        value = self.visit(node.operand)
        if node.operator == "NOT":
            return not boolean(value)
        value = require_number(value)
        return value if node.operator == "+" else value.copy_negate()

    def visit_Binary(self, node: ast.Binary) -> object:
        left = self.visit(node.left)
        operator = node.operator
        if operator == "AND":
            return boolean(left) and boolean(self.visit(node.right))
        if operator == "OR":
            return boolean(left) or boolean(self.visit(node.right))
        right = self.visit(node.right)
        if operator in ("=", "<>", "<", "<=", ">", ">="):
            if type(left) is dates.BSLDate:
                left.require_known()
            if type(right) is dates.BSLDate:
                right.require_known()
        if (operator in ("=", "<>", "<", "<=", ">", ">=")
                and ((type(left) is Decimal and type(right) is bool)
                     or (type(left) is bool and type(right) is Decimal))):
            # BSL operator comparisons convert Boolean to Number (0 or 1).
            # Keep this separate from typed collection lookup equality.
            left = Decimal(1 if left else 0) if type(left) is bool else left
            right = Decimal(1 if right else 0) if type(right) is bool else right
        if operator == "=":
            return equal(left, right)
        if operator == "<>":
            return not equal(left, right)
        if operator in ("<", "<=", ">", ">="):
            if type(left) is dates.BSLDate and type(right) is dates.BSLDate:
                left, right = Decimal(left.ticks), Decimal(right.ticks)
            if type(left) is not type(right) or not isinstance(left, (Decimal, str, bool)):
                raise TypeError("Значения несовместимы для сравнения")
            if isinstance(left, str):
                left, right = string_key(left), string_key(right)
            if operator == "<":
                return left < right
            if operator == "<=":
                return left <= right
            if operator == ">":
                return left > right
            return left >= right
        if operator == "+" and isinstance(left, str):
            return strings.concatenate(left, to_string(right))
        if type(left) is dates.BSLDate and operator in ("+", "-"):
            if operator == "-" and type(right) is dates.BSLDate:
                return dates.date_difference(left, right)
            if type(right) is not Decimal:
                raise TypeError("Арифметика даты: ожидается число секунд")
            return dates.shift_date(left, right if operator == "+" else right.copy_negate())
        left, right = require_number(left), require_number(right)
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            return divide(left, right)
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
        if not isinstance(value, _COLLECTIONS):
            raise TypeError("Индексирование поддерживается только для коллекций")
        index = self.visit(node.index)
        if isinstance(value, (BSLFixedMap, *_TABLE_COLLECTIONS)):
            return value.get_index(index)
        return value.get(index)

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
        # Existing host calls reject omitted arguments before receiver effects.
        # Native table/list methods need optional holes; admit them only for a known
        # exact built-in receiver (a variable or its Columns property). We never
        # execute a factory merely to discover whether it allows omissions.
        table_receiver = None
        table_optional = None
        if (isinstance(callee, ast.Attribute)
                and any(isinstance(a, ast.OmittedArgument) for a in node.arguments)):
            table_receiver = self.known_table_receiver(callee.object)
            table_optional = self.table_optional_arguments(table_receiver, callee.name)
        registered = (self.functions.get(callee.name.casefold())
                      if isinstance(callee, ast.Name) else None)
        if table_optional is None and (registered is None or
                (registered.function is not fill_property_values
                 and registered.function is not strings.str_find)):
            self.reject_host_omissions(node.arguments)
        if isinstance(callee, ast.Attribute):
            receiver = table_receiver if table_optional is not None else self.visit(callee.object)
            if not isinstance(receiver, BSLObject):
                raise TypeError("Значение не имеет методов или свойств")
            function = receiver.get_method(callee.name)
        else:
            function = self.visit(node.callee)
        if not isinstance(function, HostFunction):
            raise TypeError("Значение не является функцией")
        if function.function is fill_property_values:
            if not 2 <= len(node.arguments) <= 4:
                raise TypeError("ЗаполнитьЗначенияСвойств ожидает от 2 до 4 аргументов")
            self.reject_host_omissions(node.arguments[:2])
        elif function.function is strings.str_find:
            if not 2 <= len(node.arguments) <= 5:
                raise TypeError("СтрНайти ожидает от 2 до 5 аргументов")
            self.reject_host_omissions(node.arguments[:2])
        elif table_optional is not None:
            self.reject_host_omissions([argument for index, argument in enumerate(node.arguments)
                                       if index not in table_optional])
        else:
            self.reject_host_omissions(node.arguments)
        if require_value and not function.returns_value:
            raise TypeError(f"Процедура не возвращает значение: {function.name}")
        if function.function is _eval_marker:
            if len(node.arguments) != 1:
                raise TypeError("Вычислить ожидает 1 аргумент")
            return self._evaluate(node.arguments[0])
        if function.function is strings.str_find:
            return function(*(strings._OMITTED if isinstance(argument, ast.OmittedArgument)
                              else self.visit(argument) for argument in node.arguments))
        if table_optional is not None:
            defaults = None
            if type(table_receiver) is BSLValueTableColumnCollection:
                defaults = ("", None, "", Decimal(0))
                if callee.name.casefold() in {"insert", "вставить"}:
                    defaults = (None,) + defaults
            elif type(table_receiver) is BSLValueList:
                defaults = (None, "", False)
                if callee.name.casefold() in {"insert", "вставить"}:
                    defaults = (None,) + defaults
            return function(*((defaults[index] if defaults is not None else None)
                              if isinstance(argument, ast.OmittedArgument) else self.visit(argument)
                              for index, argument in enumerate(node.arguments)))
        if function.function is fill_property_values:
            return function(*(None if isinstance(argument, ast.OmittedArgument)
                              else self.visit(argument) for argument in node.arguments))
        return function(*(self.argument(argument) if index in function.reference_parameters
                          else self.visit(argument)
                          for index, argument in enumerate(node.arguments)))

    def known_table_receiver(self, node: ast.Node) -> object:
        """Read only explicit built-in receiver storage; never invoke factories."""
        node = self.ungroup(node)
        if isinstance(node, ast.Name):
            value = self.visit_Name(node)
            return value if type(value) in (BSLValueTable, BSLValueTableColumnCollection, BSLValueList) else None
        if isinstance(node, ast.Attribute) and node.name.casefold() in {"колонки", "columns"}:
            parent = self.known_table_receiver(node.object)
            if type(parent) is BSLValueTable:
                return parent.columns
        return None

    @staticmethod
    def table_optional_arguments(receiver: object, name: str) -> frozenset[int] | None:
        key = name.casefold()
        if type(receiver) is BSLValueList:
            if key in {"add", "добавить"}:
                return frozenset(range(3))
            if key in {"insert", "вставить"}:
                return frozenset(range(1, 4))
        if type(receiver) is BSLValueTableColumnCollection:
            if key in {"add", "добавить"}:
                return frozenset(range(4))
            if key in {"insert", "вставить"}:
                return frozenset(range(1, 5))
        if type(receiver) is BSLValueTable:
            if key in {"copy", "скопировать"}:
                return frozenset({0, 1})
            if key in {"copycolumns", "скопироватьколонки"}:
                return frozenset({0})
            if key in {"fillvalues", "заполнитьзначения"}:
                return frozenset({1})
        return None

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
        validate_labels(function.body)
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
        node = self.ungroup(node)
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
        if isinstance(node, ast.Attribute):
            owner = self.visit(node.object)
            if type(owner) is BSLValueListItem:
                # Native PR74: a field is live storage, not a copy-out temporary.
                # Resolve the item once; its existing setters retain conversion,
                # identity and string-cache behavior, including after deletion.
                owner.reference_get_member(node.name)
                return _Reference(lambda: owner.reference_get_member(node.name),
                                  lambda value: owner.reference_set_member(node.name, value))
            if not isinstance(owner, (BSLStructure, BSLFixedStructure, BSLValueTableRow, BSLValueTableColumn)):
                raise TypeError("Передача свойства по ссылке поддерживается только для структуры, строки или колонки таблицы")
            # Bind the receiver once and validate existence before entering the
            # callee. Fixed properties remain readable; their setter rejects an
            # actual assignment inside the callee, not the argument itself.
            owner.get_member(node.name)
            return _Reference(lambda: owner.get_member(node.name),
                              lambda value: owner.set_member(node.name, value))
        if isinstance(node, ast.Index):
            owner = self.visit(node.object)
            if not isinstance(owner, _COLLECTIONS):
                raise TypeError("Индексирование поддерживается только для коллекций")
            index = self.visit(node.index)
            getter = owner.get_index if isinstance(owner, (BSLFixedMap, *_TABLE_COLLECTIONS)) else owner.get
            # Native PR47: bad array indices / absent structure properties fail
            # before entry; a mutable map's missing key is a valid output slot.
            getter(index)
            setter = owner.set_index if isinstance(owner, _TABLE_COLLECTIONS) else owner.set
            return _Reference(lambda: getter(index), lambda value: setter(index, value))
        # Literals and computed expressions have no caller storage to rebind.
        return self.visit(node)

    @staticmethod
    def ungroup(node: ast.Node) -> ast.Node:
        while isinstance(node, ast.Group):
            node = node.expression
        return node

    def visit_New(self, node: ast.New) -> object:
        factory = self.types.get(node.name.casefold())
        if factory is not None and factory.function is BSLTypeDescription:
            # The observed descriptor overloads use positional qualifier holes.
            # Other host constructors retain their explicit omission rejection.
            return factory(*(None if isinstance(argument, ast.OmittedArgument)
                             else self.visit(argument) for argument in node.arguments))
        self.reject_host_omissions(node.arguments)
        if factory is None:
            raise ValueError(f"Тип не определен: {node.name}")
        return factory(*(self.visit(argument) for argument in node.arguments))

    def visit_DynamicNew(self, node: ast.DynamicNew) -> object:
        # Expressions follow the same left-to-right evaluation as host calls.
        # EDT root_New explicitly says to ignore a non-array second value.
        value_type = self.visit(node.type_expression)
        parameters = self.visit(node.parameters) if node.parameters is not None else None
        if type(value_type) is BSLType:
            name = value_type.value
        elif type(value_type) is str:
            name = value_type
        else:
            raise TypeError("Новый: ожидается имя типа или значение Тип")
        factory = self.types.get(name.casefold())
        if factory is None:
            raise ValueError(f"Тип не определен или не имеет конструктора: {name}")
        # No reflection, conversion, or arbitrary host iterable expansion.
        arguments = tuple(parameters.items) if type(parameters) is BSLArray else ()
        return factory(*arguments)

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.target, ast.Name):
            self.set_variable(node.target.name, self.visit(node.value))
        else:
            value = self.visit(node.target.object)
            if isinstance(node.target, ast.Attribute):
                if not isinstance(value, BSLObject):
                    raise TypeError("Значение не имеет методов или свойств")
                value.set_member(node.target.name, self.visit(node.value))
            else:
                if not isinstance(value, _COLLECTIONS):
                    raise TypeError("Индексирование поддерживается только для коллекций")
                index = self.visit(node.target.index)
                setter = value.set_index if isinstance(value, _TABLE_COLLECTIONS) else value.set
                setter(index, self.visit(node.value))

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
            child = Interpreter(self.output, encoding=self.encoding,
                                native_target=self.native_target)
            child.functions = self.functions.copy()
            child.types = self.types.copy()
            child._module_cache = self._module_cache
            child._loading = self._loading
            child._handled_errors = self._handled_errors
            child._eval_depth = self._eval_depth
            child._execute_depth = self._execute_depth
            child.execute(text, str(path))
            module = _Module(child, path)
            self._module_cache[path] = module
        return module

    def visit_Label(self, node: ast.Label) -> None:
        pass

    def visit_Goto(self, node: ast.Goto) -> None:
        raise _Goto(node)

    def visit_Routine(self, node: ast.Routine) -> None:
        # Declarations are registered by execute_program, never executed in place.
        pass

    def visit_Try(self, node: ast.Try) -> None:
        try:
            self.block(node.body)
        except BSLRuntimeError as error:
            # 1C discards parent diagnostic information on entering a nested handler.
            # Keep frames for reliable unwinding, but never revive their stale errors.
            for index in range(len(self._handled_errors)):
                self._handled_errors[index] = None
            self._handled_errors.append(error)
            try:
                self.block(node.handler)
            finally:
                self._handled_errors.pop()

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.value is None:
            if not self._handled_errors:
                # Protect callers constructing ASTs directly, as well as the parser.
                raise ValueError("Нет активного исключения для повторного вызова")
            error = self._handled_errors[-1]
            if error is None:
                raise ValueError("Повторный вызов исключения после вложенного обработчика "
                                 "пока не поддерживается; используйте явное сообщение")
            raise error
        message = to_string(self.visit(node.value))
        token = node.token
        raise BSLRuntimeError(message, token.source, token.line, token.column)

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
        if (not isinstance(collection, _COLLECTIONS)
                and type(collection) is not BSLRoundModes
                and type(collection) is not BSLSearchDirections
                and type(collection) is not BSLSortDirections):
            raise TypeError("Для Каждого ожидает массив, структуру, соответствие или поддержанное пространство системного перечисления")
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

"""Tree-walking interpreter with persistent state and injectable builtins."""

from decimal import Decimal, localcontext
from types import GeneratorType

from . import file_io
from .file_io import BSLFile, BSLTextReader, BSLTextWriter, BSLBinaryData, TEXT_ENCODINGS
from .text_documents import BSLTextDocument
from .json_processing import BSLJSONReader, BSLJSONWriter, JSON_VALUE_TYPES, JSON_LINE_BREAKS, BSLJSONWriterSettings, read_json, write_json
from .unique_identifiers import BSLUUID
from .async_runtime import Scheduler, Promise, AwaitRequest, SchedulerLimitError
from pathlib import Path
from typing import Callable

from .syntax import ast
from .numeric import bits, elementary, numbers
from . import clocks, date_time_conversions, dates, formatting, serialization, strings, type_values, value_checks, xml_values
from .chars import BSLChars, CHARS
from .metadata import BSLMetadata, BSLCatalogMetadataCollection
from .catalogs import BSLCatalogs
from .catalog_types import BSLCatalogType
from .database_context import FileDBContext, require_database_context
from .numeric.round_modes import BSLRoundModes, ROUND_MODES
from .search_directions import BSLSearchDirections, SEARCH_DIRECTIONS
from .sort_directions import BSLSortDirections, SORT_DIRECTIONS
from .xml_processing import XML_STRING_PROCESSING
from .type_descriptions import BSLTypeDescription
from .value_trees import (BSLValueTree, BSLValueTreeColumnCollection, BSLValueTreeColumn,
                          BSLValueTreeRow, BSLValueTreeRowCollection)
from .value_tables import (BSLValueTable, BSLValueTableColumnCollection,
                           BSLValueTableColumn, BSLValueTableRow,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .value_lists import BSLValueList, BSLValueListItem
from .type_qualifiers import (
    ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)
from .errors import BSLError, BSLRuntimeError
from .error_info import (BSLErrorInfo, BSLErrorCategory, ERROR_CATEGORIES,
                         FORBIDDEN_RAISE_CATEGORIES, empty_error_info)
from .collation import string_key
from .syntax.parser import parse, parse_expression, parse_fragment, validate_labels, validate_async
from .syntax.lexer import KEYWORDS
from .syntax.preprocessor import validate_compilation_profile
from .maps import BSLFixedMap, BSLMap
from .native_targets import WINDOWS_8_3_27_2342, target_context, validate_native_target
from .structures import BSLFixedStructure, BSLStructure, fill_property_values
from .values import (
    BSLArray, BSLFixedArray, BSLObject, BSLType, HostFunction, NULL, Reference as _Reference,
    boolean, divide, equal, number, require_number, to_string,
)


_COLLECTIONS = (BSLArray, BSLFixedArray, BSLStructure, BSLFixedStructure,
                BSLMap, BSLFixedMap, BSLValueTable, BSLValueTableColumnCollection,
                BSLValueTableRow, BSLCollectionIndexes, BSLCollectionIndex, BSLValueList,
                BSLValueTreeColumnCollection, BSLValueTreeRow, BSLValueTreeRowCollection)
_TABLE_COLLECTIONS = (BSLValueTable, BSLValueTableColumnCollection, BSLValueTableRow,
                      BSLCollectionIndexes, BSLCollectionIndex, BSLValueList,
                      BSLValueTreeColumnCollection, BSLValueTreeRow, BSLValueTreeRowCollection)


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


class _VariableReference(_Reference):
    """Named dictionary storage, preserving its provenance through forwarding."""


class _Module:
    """A stable, explicit public module receiver, never a platform/Python object."""

    def __init__(self, interpreter: "Interpreter", path: Path | None = None):
        self.interpreter = interpreter
        self.path = path
        self.ready = False

    def __str__(self) -> str:
        raise TypeError("Строковое представление объекта модуля пока не поддерживается")

    def __repr__(self) -> str:
        return "<module receiver>"

    def get_member(self, name: str) -> object:
        key = name.casefold()
        if not self.ready or key not in self.interpreter.exported_variables:
            raise ValueError(f"Поле объекта не обнаружено: {name}")
        return self.interpreter.variables[key]

    def set_member(self, name: str, value: object) -> None:
        key = name.casefold()
        if not self.ready or key not in self.interpreter.exported_variables:
            raise ValueError(f"Поле объекта не обнаружено: {name}")
        self.interpreter.variables[key] = value

    def routine(self, name: str) -> ast.Routine:
        routine = (self.interpreter.routines.get(name.casefold()) or
                   self.interpreter.server_routines.get(name.casefold()))
        if not self.ready or routine is None or not routine.exported:
            raise ValueError(f"Метод объекта не обнаружен: {name}")
        if routine.is_dual:
            # Native form-module Export does not expose dual NoContext through
            # ThisObject. This bounded standalone slice also excludes imported
            # and stored module receivers; it does not define a general native
            # common-module export policy.
            raise ValueError("Двухконтекстная подпрограмма через объект модуля пока не поддерживается")
        return routine


class _Namespace:
    """A directory's explicitly imported children, never arbitrary Python members."""

    def __init__(self, path: Path):
        self.path = path
        self.members: dict[str, _Module | _Namespace] = {}


class Interpreter:
    def __init__(self, output: Callable[[str], None] = print, *, encoding: str = "utf-8-sig",
                 native_target: str = WINDOWS_8_3_27_2342,
                 database_context: FileDBContext | None = None,
                 compilation_profile: str = "standalone"):
        self._compilation_profile = validate_compilation_profile(compilation_profile)
        self._native_target = validate_native_target(native_target)
        self._database_context = database_context
        self._metadata = BSLMetadata(database_context)
        self._catalogs = BSLCatalogs(self._metadata._catalogs, database_context)
        self._scheduler = Scheduler(self._native_target)
        self._diagnostic_owner = self
        self.variables: dict[str, object] = {}
        self.functions: dict[str, HostFunction] = {}
        self.routines: dict[str, ast.Routine] = {}
        self.server_routines: dict[str, ast.Routine] = {}
        self.server_module_names: set[str] = set()
        self.server_initializers: list[ast.ServerInitializer] = []
        self._logical_side = "client"
        self._context_stack = ["client"]
        self._module_context_stack = [True]
        self._client_routine_names: set[str] = set()
        # Family tombstones survive a missing side, including detached servers,
        # so an unavailable variant can never fall through to a host function.
        self._dual_routine_names: set[str] = set()
        self.module_names: set[str] = set()
        self.exported_variables: set[str] = set()
        self._self_module = _Module(self)
        self.locals: dict[str, object] | None = None
        self.types: dict[str, HostFunction] = {}
        self.output = output
        self.encoding = encoding
        self.imports: dict[str, _Module | _Namespace] = {}
        self._module_cache: dict[Path, _Module] = {}
        self._loading: list[Path] = []
        # Imports share this dynamic handler stack, independent of variable frames.
        self._handled_errors: list[BSLRuntimeError | None] = []
        self._error_info_boundaries: list[int] = []
        self._execute_depth = [0]
        self._eval_depth = [0]  # Shared by imported modules, like the handler stack.
        self.register_function("Вычислить", _eval_marker, "Eval")
        self.register_function("Сообщить", self._message, "Message")
        self.register_function("Строка", to_string, "String")
        self.register_function("Число", number, "Number")
        self.register_function("Булево", boolean, "Boolean")
        # Bind only immutable startup data, never the interpreter's client frame.
        connection_string = (database_context.connection_string if database_context is not None
                             else require_database_context)
        self.register_function("СтрокаСоединенияИнформационнойБазы", connection_string,
                               "InfoBaseConnectionString")
        self.register_function("ЗаполнитьЗначенияСвойств", fill_property_values,
                               "FillPropertyValues", returns_value=False)
        self.register_function("ЗначениеЗаполнено", value_checks.value_is_filled, "ValueIsFilled")
        self.register_function("Тип", self._catalogs.type_by_name, "Type")
        self.register_function("ТипЗнч", type_values.type_of, "TypeOf")
        self.register_function("ЗначениеВСтрокуВнутр", serialization.value_to_string_internal,
                               "ValueToStringInternal")
        self.register_function("ЗначениеИзСтрокиВнутр", serialization.value_from_string_internal,
                               "ValueFromStringInternal")
        for name, function, alias in (*strings.BUILTINS, *formatting.BUILTINS, *numbers.BUILTINS,
                                      *xml_values.BUILTINS, *bits.BUILTINS, *elementary.BUILTINS,
                                      *dates.BUILTINS, *clocks.BUILTINS,
                                      *date_time_conversions.BUILTINS):
            self.register_function(name, function, alias)
        self.register_function("ОписаниеОшибки", self._error_description, "ErrorDescription")
        self.register_function("ИнформацияОбОшибке", self._error_info, "ErrorInfo")
        self.register_type("ПараметрыЗаписиJSON", BSLJSONWriterSettings, "JSONWriterSettings")
        self.register_type("ЧтениеJSON", BSLJSONReader, "JSONReader")
        self.register_type("ЗаписьJSON", BSLJSONWriter, "JSONWriter")
        self.register_function("ПрочитатьJSON", read_json, "ReadJSON")
        self.register_function("ЗаписатьJSON", write_json, "WriteJSON", returns_value=False)
        for ru, factory, en in (("Файл", BSLFile, "File"),
                                ("ЧтениеТекста", BSLTextReader, "TextReader"),
                                ("ЗаписьТекста", BSLTextWriter, "TextWriter"),
                                ("ДвоичныеДанные", BSLBinaryData, "BinaryData")):
            self.register_type(ru, factory, en)
        for ru, function, en, returns_value in file_io.FUNCTIONS:
            self.register_function(ru, function, en, returns_value=returns_value)
        self.register_type("ТекстовыйДокумент", BSLTextDocument, "TextDocument")
        self.register_type("УникальныйИдентификатор", BSLUUID, "UUID")
        self.register_type("Массив", BSLArray, "Array")
        self.register_type("Структура", BSLStructure, "Structure")
        self.register_type("Соответствие", BSLMap, "Map")
        self.register_type("ФиксированныйМассив", BSLFixedArray, "FixedArray")
        self.register_type("ФиксированнаяСтруктура", BSLFixedStructure, "FixedStructure")
        self.register_type("ФиксированноеСоответствие", BSLFixedMap, "FixedMap")

        self.register_type("ТаблицаЗначений", BSLValueTable, "ValueTable")
        self.register_type("ДеревоЗначений", BSLValueTree, "ValueTree")
        self.register_type("СписокЗначений", BSLValueList, "ValueList")
        self.register_type("ОписаниеТипов", BSLTypeDescription, "TypeDescription")
        self.register_type("КвалификаторыЧисла", BSLNumberQualifiers, "NumberQualifiers")
        self.register_type("КвалификаторыСтроки", BSLStringQualifiers, "StringQualifiers")
        self.register_type("КвалификаторыДаты", BSLDateQualifiers, "DateQualifiers")
        self.register_type("КвалификаторыДвоичныхДанных", BSLBinaryDataQualifiers, "BinaryDataQualifiers")

    @property
    def database_context(self) -> FileDBContext | None:
        return self._database_context

    @property
    def locals(self):
        return self._scheduler.active_context.locals.get(self)

    @locals.setter
    def locals(self, value):
        if value is None:
            self._scheduler.active_context.locals.pop(self, None)
        else:
            self._scheduler.active_context.locals[self] = value

    @property
    def _context_stack(self):
        return self._scheduler.active_context.context_stack

    @_context_stack.setter
    def _context_stack(self, value):
        self._scheduler.active_context.context_stack = value

    @property
    def _module_context_stack(self):
        return self._scheduler.active_context.module_context_stack

    @_module_context_stack.setter
    def _module_context_stack(self, value):
        self._scheduler.active_context.module_context_stack = value

    @property
    def _has_module_context(self) -> bool:
        """Task-local module capability, independent of logical server execution."""
        return self._module_context_stack[-1]

    def _diagnostics(self):
        return self._scheduler.active_context.state.setdefault(self._diagnostic_owner, {})

    @property
    def _handled_errors(self):
        return self._diagnostics().setdefault("_handled_errors", [])

    @_handled_errors.setter
    def _handled_errors(self, value):
        self._diagnostics()["_handled_errors"] = value

    @property
    def _error_info_boundaries(self):
        return self._diagnostics().setdefault("_error_info_boundaries", [])

    @_error_info_boundaries.setter
    def _error_info_boundaries(self, value):
        self._diagnostics()["_error_info_boundaries"] = value

    @property
    def _eval_depth(self):
        return self._diagnostics().setdefault("_eval_depth", [0])

    @_eval_depth.setter
    def _eval_depth(self, value):
        self._diagnostics()["_eval_depth"] = value

    @property
    def _execute_depth(self):
        return self._diagnostics().setdefault("_execute_depth", [0])

    @_execute_depth.setter
    def _execute_depth(self, value):
        self._diagnostics()["_execute_depth"] = value

    def _pump_async(self, *, max_steps=100_000):
        try:
            self._scheduler.run_until_idle(max_steps=max_steps)
        except SchedulerLimitError as error:
            raise BSLRuntimeError("Превышен предел асинхронных возобновлений Yadinassi",
                                  "<async>", 1, 1) from error

    def run_until_idle(self, *, max_steps=100_000):
        """Resume queued language work; unresolved host promises remain pending."""
        before = len(self._scheduler.procedure_errors)
        self._pump_async(max_steps=max_steps)
        if len(self._scheduler.procedure_errors) > before:
            raise self._scheduler.procedure_errors[before]

    def ensure_complete(self):
        """Reject silent process success while language tasks remain blocked."""
        if self.pending_promises:
            raise BSLRuntimeError("Остались незавершенные асинхронные задания",
                                  "<async>", 1, 1)

    def close(self):
        """Release suspended frames explicitly at the embedding lifecycle boundary."""
        self._scheduler.reset()

    @property
    def pending_promises(self):
        return self._scheduler.pending

    def visit(self, node: ast.Node) -> object:
        """Synchronous embedding boundary; language evaluation uses _visit."""
        return self._scheduler.run_inline(self._visit(node))

    @property
    def compilation_profile(self) -> str:
        """Immutable source-compilation policy, independent of native_target."""
        return self._compilation_profile

    @property
    def native_target(self) -> str:
        """The explicitly selected native checkpoint, shared by this VM's imports."""
        return self._native_target

    @property
    def execution_context(self) -> str:
        """Current logical side; standalone entry points always start as client."""
        return self._context_stack[-1]

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

    def _error_info(self) -> BSLErrorInfo:
        boundary = self._error_info_boundaries[-1] if self._error_info_boundaries else 0
        if len(self._handled_errors) <= boundary or self._handled_errors[-1] is None:
            return empty_error_info()
        error = self._handled_errors[-1]
        if error.info is None:
            error.info = BSLErrorInfo(error.message, module_name=error.source,
                                      line_number=error.line, initial_string=error.source_line)
        return error.info

    def _evaluate(self, argument: ast.Node) -> object:
        value = (yield from self._visit(argument))
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
        # Native Eval does not inherit the enclosing ErrorInfo context. A handler
        # entered by evaluated code can still establish its own diagnostic frame.
        self._error_info_boundaries.append(len(self._handled_errors))
        try:
            # Parse and consume the entire input before executing even its first call.
            try:
                expression = parse_expression(text)
            except BSLError as error:
                raise BSLRuntimeError(error.message, error.source, error.line, error.column) from None
            return (yield from self._visit(expression))
        except RecursionError:
            raise ValueError("Вычислить: превышен предел глубины выражения Yadinassi") from None
        finally:
            self._error_info_boundaries.pop()
            self._eval_depth[0] -= 1

    def visit_Execute(self, node: ast.Execute) -> None:
        value = (yield from self._visit(node.expression))
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
                name: item if isinstance(item, _Reference) else _VariableReference(
                    lambda name=name: scope[name],
                    lambda value, name=name: scope.__setitem__(name, value))
                for name, item in scope.items()
            }
            (yield from self.block(program))
        except RecursionError:
            raise ValueError("Выполнить: превышен предел глубины фрагмента Yadinassi") from None
        finally:
            self.locals = previous
            self._execute_depth[0] -= 1

    def execute(self, text: str, source: str = "<строка>") -> object:
        return self.execute_program(parse(text, source, compilation_profile=self.compilation_profile))

    def execute_program(self, program: list[ast.Node]) -> object:
        """Execute already-compiled AST; this does not select source branches."""
        outermost = not self._scheduler.is_active
        procedure_errors = len(self._scheduler.procedure_errors)
        with target_context(self.native_target):
            # A diagnostic source label need not name a readable filesystem path.
            if not any(isinstance(node, ast.Import) for node in program):
                result = self._scheduler.run_inline(self._execute_program(program))
            else:
                source = program[0].token.source if program else "<строка>"
                path = None if source.startswith("<") else Path(source).resolve()
                if path is None:
                    result = self._scheduler.run_inline(self._execute_program(program))
                else:
                    self._loading.append(path)
                    try:
                        result = self._scheduler.run_inline(self._execute_program(program))
                    finally:
                        self._loading.pop()
            # Native public fields and routines become available only after the
            # first successful whole module initialization. Later REPL executions
            # keep the same receiver, storage and public availability.
            self._self_module.ready = True
            if outermost:
                self._pump_async()
                if len(self._scheduler.procedure_errors) > procedure_errors:
                    raise self._scheduler.procedure_errors[procedure_errors]
            return result

    def _execute_program(self, program: list[ast.Node]) -> object:
        # Also validate callers supplying an AST directly. No import or declaration
        # effects may precede label resolution.
        validate_labels(program)
        validate_async(program)
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
        routine_groups: dict[str, list[ast.Routine]] = {}
        for node in program:
            if isinstance(node, ast.Routine):
                if not self._valid_routine_context(node):
                    token = node.token
                    raise BSLError("Подпрограмма требует неподдерживаемый контекст исполнения",
                                   token.source, token.line, token.column)
                routine_groups.setdefault(node.name.casefold(), []).append(node)
        for group in routine_groups.values():
            first = group[0]
            if len(group) > 1 and (not all(node.is_dual for node in group)
                    or len(group) > 2
                    or len({node.execution_context for node in group}) != len(group)
                    or len({(node.token.source, node.token.line, node.token.column,
                             node.token.kind) for node in group}) != 1):
                token = first.token
                raise BSLError("Одноименные подпрограммы разных объявлений в одном модуле пока не поддерживаются",
                               token.source, token.line, token.column)
        # Preflight the whole incoming program before publishing any replacement.
        # A declaration family replaces both old sides and its availability marker
        # atomically, even when preprocessing retained only one new dual variant.
        routines = self.routines.copy()
        server_routines = self.server_routines.copy()
        dual_names = self._dual_routine_names.copy()
        for key, group in routine_groups.items():
            routines.pop(key, None)
            server_routines.pop(key, None)
            dual_names.discard(key)
            if group[0].is_dual:
                dual_names.add(key)
            for node in group:
                registry = server_routines if node.execution_context == "server" else routines
                registry[key] = node
        self.routines, self.server_routines = routines, server_routines
        self._dual_routine_names = dual_names
        # Register side-local storage before any module statement executes.
        for node in program:
            if isinstance(node, ast.ServerInitializer):
                self.server_initializers.append(node)
            elif isinstance(node, ast.Var):
                if node.execution_context == "server":
                    self.server_module_names.update(name.casefold() for name in node.names)
                    continue
                self.exported_variables.update(name.casefold() for name in node.exported_names)
                for name in node.names:
                    self.module_names.add(name.casefold())
                    self.variables.setdefault(name.casefold(), None)
        for node in program:
            if isinstance(node, ast.Import):
                yield from self._visit(node)
        return (yield from self.block([node for node in program
            if not isinstance(node, (ast.Import, ast.ServerInitializer))
            and not (isinstance(node, ast.Var) and node.execution_context == "server")]))

    def block(self, statements: list[ast.Node]) -> object:
        result = None
        labels = {node.name.casefold(): index for index, node in enumerate(statements)
                  if isinstance(node, ast.Label)}
        position = 0
        while position < len(statements):
            try:
                result = (yield from self._visit(statements[position]))
            except _Goto as jump:
                if jump.name not in labels:
                    raise
                position = labels[jump.name]
            else:
                position += 1
        return result

    def _visit(self, node: ast.Node) -> object:
        try:
            handler = getattr(self, f"visit_{type(node).__name__}")
            result = handler(node)
            if isinstance(result, GeneratorType):
                return (yield from result)
            return result
        except BSLError:
            raise
        except (ArithmeticError, ValueError, TypeError, IndexError, RecursionError) as error:
            message = str(error) or type(error).__name__
            if isinstance(error, RecursionError) and self._eval_depth[0]:
                message = "Вычислить: превышен предел глубины выражения Yadinassi"
            if isinstance(error, ZeroDivisionError):
                message = "Деление на ноль"
            token = node.token
            raise BSLRuntimeError(message, token.source, token.line, token.column,
                                  source_line=token.source_line) from None

    def visit_Literal(self, node: ast.Literal) -> object:
        return node.value

    def visit_Name(self, node: ast.Name) -> object:
        name = node.name.casefold()
        if self.locals is not None and name in self.locals:
            value = self.locals[name]
            return value.get() if isinstance(value, _Reference) else value
        if self._has_module_context and name in self.variables and (self.locals is None or name in self.module_names):
            return self.variables[name]
        if name in self.imports:
            raise TypeError(f"Имя модуля допустимо только при вызове его подпрограммы: {node.name}")
        if name in self.routines or name in self.server_routines or name in self._dual_routine_names:
            raise TypeError(f"Процедуру или функцию необходимо вызвать: {node.name}")
        if name in self.functions:
            return self.functions[name]
        if name in ("thisobject", "этотобъект"):
            if not self._has_module_context:
                raise ValueError("Объект модуля недоступен в подпрограмме без контекста")
            return self._self_module
        if name in ("справочники", "catalogs"):
            return self._catalogs
        if name in ("метаданные", "metadata"):
            return self._metadata
        if name in ("символы", "chars"):
            return CHARS
        if name in ("допустимыйзнак", "allowedsign"):
            return ALLOWED_SIGNS
        if name in ("допустимаядлина", "allowedlength"):
            return ALLOWED_LENGTHS
        if name in ("частидаты", "datefractions"):
            return DATE_FRACTIONS
        if name in ("режимокругления", "roundmode"):
            return ROUND_MODES
        if name in ("переносстрокjson", "jsonlinebreak"):
            return JSON_LINE_BREAKS
        if name in ("кодировкатекста", "textencoding"):
            return TEXT_ENCODINGS
        if name in ("типзначенияjson", "jsonvaluetype"):
            return JSON_VALUE_TYPES
        if name in ("обработкастрокиxml", "xmlstringprocessing"):
            return XML_STRING_PROCESSING
        if name in ("направлениепоиска", "searchdirection"):
            return SEARCH_DIRECTIONS
        if name in ("категорияошибки", "errorcategory"):
            return ERROR_CATEGORIES
        if name in ("направлениесортировки", "sortdirection"):
            return SORT_DIRECTIONS
        raise ValueError(f"Переменная или функция не определена: {node.name}")

    def visit_Group(self, node: ast.Group) -> object:
        return (yield from self._visit(node.expression))

    def visit_Unary(self, node: ast.Unary) -> object:
        value = (yield from self._visit(node.operand))
        if node.operator == "NOT":
            return not boolean(value)
        value = require_number(value)
        return value if node.operator == "+" else value.copy_negate()

    def visit_Binary(self, node: ast.Binary) -> object:
        left = (yield from self._visit(node.left))
        operator = node.operator
        if operator == "AND":
            return boolean(left) and boolean((yield from self._visit(node.right)))
        if operator == "OR":
            return boolean(left) or boolean((yield from self._visit(node.right)))
        right = (yield from self._visit(node.right))
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
        branch = node.when_true if boolean((yield from self._visit(node.condition))) else node.when_false
        return (yield from self._visit(branch))

    def visit_Attribute(self, node: ast.Attribute) -> object:
        value = (yield from self.receiver(node.object))
        if type(value) is _Module:
            self._require_module_storage_context()
            return value.get_member(node.name)
        if not isinstance(value, BSLObject):
            raise TypeError("Значение не имеет методов или свойств")
        return value.get_member(node.name)

    def visit_Index(self, node: ast.Index) -> object:
        value = (yield from self._visit(node.object))
        if type(value) in (BSLChars, BSLCatalogMetadataCollection, BSLCatalogs):
            return value.get_index((yield from self._visit(node.index)))
        if not isinstance(value, _COLLECTIONS):
            raise TypeError("Индексирование поддерживается только для коллекций")
        index = (yield from self._visit(node.index))
        if isinstance(value, (BSLFixedMap, *_TABLE_COLLECTIONS)):
            return value.get_index(index)
        return value.get(index)

    def visit_Call(self, node: ast.Call) -> object:
        return (yield from self.call(node, require_value=True))

    @staticmethod
    def _valid_routine_context(function: ast.Routine) -> bool:
        return (function.execution_context in {"client", "server"}
                and type(function.module_context) is bool
                and type(function.is_dual) is bool
                and type(function.is_async) is bool
                and (not function.is_dual or
                     (not function.module_context and not function.is_async))
                and (function.execution_context != "client" or
                     function.module_context or function.is_dual))

    def _resolve_routine(self, name: str) -> ast.Routine | None:
        key = name.casefold()
        candidates = (self.routines.get(key), self.server_routines.get(key))
        if key in self._dual_routine_names or any(
                node is not None and node.is_dual for node in candidates):
            # Detached servers store their server routines in .routines. Select
            # by declaration metadata, never by the dictionary's historical name.
            for node in candidates:
                if node is not None and node.is_dual and node.execution_context == self.execution_context:
                    return node
            raise ValueError(f"Двухконтекстная подпрограмма недоступна на стороне {self.execution_context}: {name}")
        return candidates[0] or candidates[1]

    def call(self, node: ast.Call, *, require_value: bool) -> object:
        callee = self.ungroup(node.callee)
        routine = self._resolve_routine(callee.name) if isinstance(callee, ast.Name) else None
        if (isinstance(callee, ast.Name) and routine is None
                and callee.name.casefold() in self._client_routine_names):
            raise ValueError("Вызов клиентской подпрограммы с сервера недопустим")
        owner = self
        has_omissions = any(isinstance(a, ast.OmittedArgument) for a in node.arguments)
        known_receiver = None
        if isinstance(callee, ast.Attribute):
            module = self.import_receiver(callee.object)
            if module is not None:
                if type(module) is not _Module:
                    raise TypeError("Пространство каталога не содержит вызываемых подпрограмм")
                owner = module.interpreter
                routine = module.routine(callee.name)
            elif has_omissions:
                # Classify only stored receivers. Calling a factory to discover
                # optional arguments would violate the host side-effect guard.
                known_receiver = self.known_table_receiver(callee.object)
                if type(known_receiver) is _Module:
                    owner = known_receiver.interpreter
                    routine = known_receiver.routine(callee.name)
        if routine is not None:
            return (yield from self.call_routine(routine, node.arguments, owner, require_value=require_value))
        # Existing host calls reject omitted arguments before receiver effects.
        # Native table/list methods need optional holes; admit them only for a known
        # exact built-in receiver (a variable or its Columns property). We never
        # execute a factory merely to discover whether it allows omissions.
        table_receiver = None
        table_optional = None
        if isinstance(callee, ast.Attribute) and has_omissions:
            table_receiver = known_receiver
            table_optional = self.table_optional_arguments(table_receiver, callee.name)
        registered = (self.functions.get(callee.name.casefold())
                      if isinstance(callee, ast.Name) else None)
        if table_optional is None and (registered is None or
                (registered.function is not fill_property_values
                 and registered.function is not strings.str_find
                 and not any(registered.function is fn for fn in (file_io.binary_from_string, file_io.string_from_binary, file_io.find_files)))):
            self.reject_host_omissions(node.arguments)
        if isinstance(callee, ast.Attribute):
            receiver = table_receiver if table_optional is not None else (yield from self.receiver(callee.object))
            if type(receiver) is _Module:
                return (yield from self.call_routine(receiver.routine(callee.name), node.arguments,
                                         receiver.interpreter, require_value=require_value))
            if not isinstance(receiver, BSLObject):
                raise TypeError("Значение не имеет методов или свойств")
            function = receiver.get_method(callee.name)
        else:
            function = (yield from self._visit(node.callee))
        if not isinstance(function, HostFunction):
            raise TypeError("Значение не является функцией")
        if any(function.function is fn for fn in (file_io.binary_from_string, file_io.string_from_binary, file_io.find_files)):
            self.reject_host_omissions(node.arguments[:1])
        elif function.function is fill_property_values:
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
            return (yield from self._evaluate(node.arguments[0]))
        defaults = None
        if table_optional is not None:
            if type(table_receiver) in (BSLValueTableColumnCollection, BSLValueTreeColumnCollection):
                defaults = ("", None, "", Decimal(0))
                if callee.name.casefold() in {"insert", "вставить"}:
                    defaults = (None,) + defaults
            elif type(table_receiver) is BSLValueList:
                defaults = (None, "", False)
                if callee.name.casefold() in {"insert", "вставить"}:
                    defaults = (None,) + defaults
        values = []
        for index, argument in enumerate(node.arguments):
            if isinstance(argument, ast.OmittedArgument):
                value = (strings._OMITTED if function.function is strings.str_find else
                         defaults[index] if defaults is not None else None)
            elif index in function.reference_parameters:
                value = (yield from self.argument(argument))
            else:
                value = (yield from self._visit(argument))
            values.append(value)
        return function(*values)

    def known_receiver(self, node: ast.Node) -> object:
        """Read explicit receiver storage only, never factories or arbitrary fields."""
        node = self.ungroup(node)
        imported = self.import_receiver(node)
        if imported is not None:
            return imported
        if isinstance(node, ast.Name):
            return self.visit_Name(node)
        if isinstance(node, ast.Attribute):
            parent = self.known_receiver(node.object)
            if type(parent) is _Module:
                self._require_module_storage_context()
                return parent.get_member(node.name)
            if type(parent) in (BSLValueTable, BSLValueTree) and node.name.casefold() in {"колонки", "columns"}:
                return parent.columns
        return None

    def known_table_receiver(self, node: ast.Node) -> object:
        # Stored module receivers also allow BSL routine omissions. Keep this
        # classifier as the single existing hook for known optional receivers.
        value = self.known_receiver(node)
        return value if type(value) in (_Module, BSLValueTable, BSLValueTableColumnCollection,
                                       BSLValueList, BSLValueTreeColumnCollection, BSLJSONReader, BSLJSONWriter,
                                       BSLTextReader, BSLTextWriter) else None

    def receiver(self, node: ast.Node) -> object:
        """Use one explicit import-or-value receiver route for all member access."""
        imported = self.import_receiver(node)
        return imported if imported is not None else (yield from self._visit(node))

    def _require_module_storage_context(self) -> None:
        # A supplied module receiver cannot restore missing module capability.
        # Guard source-level access, not _Module's low-level getters: an explicit
        # field reference already bound by the caller keeps ordinary semantics.
        if not self._has_module_context:
            raise ValueError("Хранилище модуля недоступно в подпрограмме без контекста")

    @staticmethod
    def table_optional_arguments(receiver: object, name: str) -> frozenset[int] | None:
        key = name.casefold()
        if type(receiver) in (BSLTextReader, BSLTextWriter):
            if key in {"open", "открыть"}: return frozenset({1, 2, 3, 4})
            if key in {"read", "прочитать", "readline", "прочитатьстроку"}: return frozenset({0})
            if key in {"writeline", "записатьстроку"}: return frozenset({1})
        if type(receiver) is BSLJSONWriter:
            if key in {"openfile", "открытьфайл"}:
                return frozenset({1, 2, 3})
            if key in {"setstring", "установитьстроку"}:
                return frozenset({0})
        if type(receiver) is BSLJSONReader and key in {"openfile", "открытьфайл"}:
            return frozenset({1})
        if type(receiver) is BSLValueList:
            if key in {"add", "добавить"}:
                return frozenset(range(3))
            if key in {"insert", "вставить"}:
                return frozenset(range(1, 4))
        if type(receiver) in (BSLValueTableColumnCollection, BSLValueTreeColumnCollection):
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
            if type(parent) is _Module:
                # A module field is an ordinary value, not another namespace.
                # Leave its evaluation to the shared explicit receiver route.
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
        if function.is_async and function.execution_context != "client":
            raise ValueError("Асинхронные подпрограммы допустимы только на клиенте")
        if not self._valid_routine_context(function):
            raise ValueError("Подпрограмма требует неподдерживаемый контекст исполнения")
        caller_side = self.execution_context
        if function.is_dual and function.execution_context != caller_side:
            raise ValueError(f"Двухконтекстная подпрограмма недоступна на стороне {caller_side}: {function.name}")
        if caller_side == "server" and function.execution_context == "client":
            raise ValueError("Вызов клиентской подпрограммы с сервера недопустим")
        if not self._has_module_context and function.module_context:
            raise ValueError("Подпрограмма без контекста не может вызывать контекстную подпрограмму")
        crossing = caller_side == "client" and function.execution_context == "server"
        if require_value and not function.is_function:
            raise TypeError(f"Процедура не возвращает значение: {function.name}")
        required = max((index + 1 for index, parameter in enumerate(function.parameters)
                        if parameter.default is None), default=0)
        if not required <= len(arguments) <= len(function.parameters):
            raise TypeError(f"{function.name} ожидает {len(function.parameters)} аргументов, "
                            f"получено {len(arguments)}")
        validate_labels(function.body)
        if crossing:
            # The measured copy-in/copy-out slice covers named variable actuals.
            # Reject properties, indexes, expressions and omitted non-Val slots
            # before evaluating even an earlier, otherwise supported argument.
            for index, parameter in enumerate(function.parameters):
                if not parameter.by_value and (index >= len(arguments) or
                        not isinstance(self.ungroup(arguments[index]), ast.Name)):
                    raise TypeError("Межконтекстные параметры без Знач пока требуют имя переменной")
        # Evaluate expression actuals once, left to right. At a measured crossing,
        # named actual storage (including Val) is read after all actual effects.
        # Same-side argument semantics remain unchanged.
        bindings = {}
        copyback: list[tuple[str, _VariableReference]] = []
        late_inputs: dict[str, _VariableReference] = {}
        for index, parameter in enumerate(function.parameters):
            argument = arguments[index] if index < len(arguments) else None
            if argument is None or isinstance(argument, ast.OmittedArgument):
                value = (yield from self._visit(parameter.default)) if parameter.default is not None else None
            else:
                if crossing and isinstance(self.ungroup(argument), ast.Name):
                    value = (yield from self.argument(argument))
                else:
                    value = (yield from self._visit(argument)) if parameter.by_value or function.is_async else (yield from self.argument(argument))
            name = parameter.name.casefold()
            if crossing and not parameter.by_value:
                # A named caller formal may itself alias a property/index.
                # Only dictionary variable storage has a safe copy-out setter;
                # do not let forwarding widen the supported sink boundary.
                if not isinstance(value, _VariableReference):
                    raise TypeError("Межконтекстные параметры без Знач пока требуют имя переменной")
                copyback.append((name, value))
            if crossing and isinstance(value, _Reference):
                if not isinstance(value, _VariableReference):
                    raise TypeError("Межконтекстная передача ссылок на свойства пока не поддерживается")
                late_inputs[name] = value
            bindings[name] = value
        if crossing:
            # Native 8.3.27.1508: names remain storage, expression results remain
            # values/handles. Clone the complete packet only after actual effects.
            for name, reference in late_inputs.items():
                bindings[name] = reference.get()
            names = list(bindings)
            copied = self._copy_context_packet([bindings[name] for name in names])
            bindings = dict(zip(names, copied))
            owner = (owner._new_server_activation() if function.module_context else
                     owner._new_server_activation(module_context=False))
        if function.is_async:
            promise = self._scheduler.start(owner._async_body(function, bindings),
                                            procedure=not function.is_function)
            return promise if function.is_function else None
        previous = owner.locals
        # Fresh server module initialization precedes formal parameter storage.
        # One cleanup boundary encloses BOTH initializer and routine execution.
        owner.locals = None if crossing else bindings
        owner._context_stack.append(function.execution_context)
        owner._module_context_stack.append(function.module_context)
        try:
            if crossing:
                for initializer in owner.server_initializers:
                    yield from owner.block(initializer.body)
                owner.locals = bindings
            result = None
            try:
                (yield from owner.block(function.body))
            except _Return as returned:
                result = returned.value
            if crossing:
                # Validate the entire outgoing packet before touching caller
                # storage. Escaping errors never reach this normal-return path.
                packet = self._copy_context_packet(
                    [result] + [bindings[name] for name, _ in copyback])
                result = packet[0]
                # Every output/result gets an independent per-occurrence copy.
                # Publish only after the whole packet validates and allocates.
                for (_, reference), value in zip(copyback, packet[1:]):
                    reference.set(value)
            return result
        finally:
            owner._module_context_stack.pop()
            owner._context_stack.pop()
            owner.locals = previous
            if crossing:
                self._scheduler.active_context.state.pop(owner._diagnostic_owner, None)

    def _async_body(self, function: ast.Routine, bindings: dict):
        previous = self.locals
        self.locals = bindings
        self._context_stack.append("client")
        self._module_context_stack.append(True)
        try:
            try:
                yield from self.block(function.body)
            except _Return as returned:
                return returned.value
            return None
        finally:
            self._module_context_stack.pop()
            self._context_stack.pop()
            self.locals = previous

    def visit_Await(self, node: ast.Await):
        value = yield from self._visit(node.operand)
        # Even settled promises suspend in the measured client profile.
        # Scalar operands also resume as themselves; no synchronous unwrap.
        return (yield AwaitRequest(value))

    @staticmethod
    def _copy_context_packet(values: list[object]) -> list[object]:
        """Measured acyclic Array/Structure transport, not generic deepcopy.

        Shared children are copied per occurrence, not memoized. Date/Null leaves
        follow the bounded native transfer capture. Resource limits, excluded
        Date representations and unsupported/cyclic graph rejection are local
        safety policy, not additional claims about native serialization limits.
        """
        remaining = 10_000
        active: set[int] = set()

        def copy(value: object, depth: int) -> object:
            nonlocal remaining
            remaining -= 1
            if remaining < 0 or depth > 64:
                raise ValueError("Межконтекстная передача: превышен предел размера или глубины")
            if value is None or value is NULL or type(value) in (str, bool, Decimal):
                return value
            if type(value) is dates.BSLDate:
                # Only known interior whole-second Dates are in this transfer
                # envelope. Do not infer fractions/endpoints from the capture,
                # or round them through the lossy internal/XML serializers.
                if (value.boundary or value.ticks % dates.TICKS_PER_SECOND or
                        not 0 < value.ticks < dates.MAX_TICKS):
                    raise ValueError("Межконтекстная передача: дробные и граничные даты пока не поддерживаются")
                return value  # Frozen value; only mutable containers need copies.
            if type(value) not in (BSLArray, BSLStructure):
                raise TypeError("Межконтекстная передача поддерживает скаляры, Массив и Структуру")
            identity = id(value)
            if identity in active:
                raise ValueError("Межконтекстная передача циклических коллекций пока не поддерживается")
            active.add(identity)
            try:
                if type(value) is BSLArray:
                    result = BSLArray()
                    result.items = [copy(item, depth + 1) for item in value.items]
                else:
                    result = BSLStructure()
                    for key, (name, item) in value._items.items():
                        result._items[key] = (name, copy(item, depth + 1))
                return result
            finally:
                active.remove(identity)

        return [copy(value, 0) for value in values]

    def _new_server_activation(self, *, module_context: bool = True) -> "Interpreter":
        """Fresh logical server call, not a real server or a form context."""
        server = Interpreter(self.output, encoding=self.encoding, native_target=self.native_target,
                             database_context=self.database_context,
                             compilation_profile=self.compilation_profile)
        server._scheduler = self._scheduler
        server._logical_side = "server"
        server._context_stack = self._context_stack
        server.routines = self.server_routines.copy()
        server.module_names = self.server_module_names.copy() if module_context else set()
        server.variables = dict.fromkeys(server.module_names)
        server.server_initializers = self.server_initializers.copy() if module_context else []
        server._client_routine_names = set(self.routines)
        server._dual_routine_names = self._dual_routine_names.copy()
        # Keep server-bound core helpers. Copy registered host functions while
        # rebinding this interpreter's methods, never retaining client frames.
        for name, function in self.functions.items():
            callback = function.function
            # Imports may carry core callbacks bound to an ancestor module.
            # Match exact implementation identities, not the current owner or
            # a user callback's name, so client diagnostic frames never leak.
            core_helpers = {Interpreter._message, Interpreter._error_description,
                            Interpreter._error_info}
            if getattr(callback, "__func__", None) in core_helpers:
                callback = getattr(server, callback.__name__)
            server.functions[name] = HostFunction(function.name, callback,
                                                  reference_parameters=function.reference_parameters,
                                                  returns_value=function.returns_value)
        server.types = self.types.copy()
        # Imports and the public module receiver remain unsupported server-side.
        # Side-local variables above never alias client storage.
        server._self_module.ready = False
        return server

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
            elif self._has_module_context and name in self.variables and (self.locals is None or name in self.module_names):
                scope = self.variables
            else:
                return (yield from self._visit(node))
            if isinstance(scope[name], _Reference):
                return scope[name]
            return _VariableReference(lambda: scope[name], lambda value: scope.__setitem__(name, value))
        if isinstance(node, ast.Attribute):
            owner = (yield from self.receiver(node.object))
            if type(owner) is _Module:
                self._require_module_storage_context()
                owner.get_member(node.name)
                return _Reference(lambda: owner.get_member(node.name),
                                  lambda value: owner.set_member(node.name, value))
            if type(owner) is BSLValueListItem:
                # Native PR74: a field is live storage, not a copy-out temporary.
                # Resolve the item once; its existing setters retain conversion,
                # identity and string-cache behavior, including after deletion.
                owner.reference_get_member(node.name)
                return _Reference(lambda: owner.reference_get_member(node.name),
                                  lambda value: owner.reference_set_member(node.name, value))
            if not isinstance(owner, (BSLStructure, BSLFixedStructure, BSLValueTableRow, BSLValueTableColumn, BSLValueTreeRow, BSLValueTreeColumn)):
                raise TypeError("Передача свойства по ссылке поддерживается только для структуры, строки или колонки таблицы")
            # Bind the receiver once and validate existence before entering the
            # callee. Fixed properties remain readable; their setter rejects an
            # actual assignment inside the callee, not the argument itself.
            owner.get_member(node.name)
            return _Reference(lambda: owner.get_member(node.name),
                              lambda value: owner.set_member(node.name, value))
        if isinstance(node, ast.Index):
            owner = (yield from self._visit(node.object))
            if type(owner) in (BSLCatalogMetadataCollection, BSLCatalogs):
                index = (yield from self._visit(node.index))
                owner.get_index(index)
                return _Reference(lambda: owner.get_index(index),
                                  lambda value: owner.set_index(index, value))
            if not isinstance(owner, _COLLECTIONS):
                raise TypeError("Индексирование поддерживается только для коллекций")
            index = (yield from self._visit(node.index))
            getter = owner.get_index if isinstance(owner, (BSLFixedMap, *_TABLE_COLLECTIONS)) else owner.get
            # Native PR47: bad array indices / absent structure properties fail
            # before entry; a mutable map's missing key is a valid output slot.
            getter(index)
            setter = owner.set_index if isinstance(owner, _TABLE_COLLECTIONS) else owner.set
            return _Reference(lambda: getter(index), lambda value: setter(index, value))
        # Literals and computed expressions have no caller storage to rebind.
        return (yield from self._visit(node))

    @staticmethod
    def ungroup(node: ast.Node) -> ast.Node:
        while isinstance(node, ast.Group):
            node = node.expression
        return node

    def visit_New(self, node: ast.New) -> object:
        factory = self.types.get(node.name.casefold())
        if factory is not None and (factory.function is BSLTypeDescription
                                    or factory.function is BSLJSONWriterSettings
                                    or factory.function is BSLTextReader
                                    or factory.function is BSLTextWriter):
            if factory.function is BSLTextReader or factory.function is BSLTextWriter:
                self.reject_host_omissions(node.arguments[:1])
            # The observed descriptor overloads use positional qualifier holes.
            # Other host constructors retain their explicit omission rejection.
            values = []
            for argument in node.arguments:
                values.append(None if isinstance(argument, ast.OmittedArgument) else (yield from self._visit(argument)))
            return factory(*values)
        self.reject_host_omissions(node.arguments)
        if factory is None:
            raise ValueError(f"Тип не определен: {node.name}")
        values = []
        for argument in node.arguments:
            values.append((yield from self._visit(argument)))
        return factory(*values)

    def visit_DynamicNew(self, node: ast.DynamicNew) -> object:
        # Expressions follow the same left-to-right evaluation as host calls.
        # EDT root_New explicitly says to ignore a non-array second value.
        value_type = (yield from self._visit(node.type_expression))
        parameters = (yield from self._visit(node.parameters)) if node.parameters is not None else None
        if type(value_type) is BSLCatalogType:
            raise ValueError("catalog reference type construction is unsupported")
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
            self.set_variable(node.target.name, (yield from self._visit(node.value)))
        else:
            value = (yield from self.receiver(node.target.object))
            if isinstance(node.target, ast.Attribute):
                if type(value) is _Module:
                    self._require_module_storage_context()
                if type(value) is not _Module and not isinstance(value, BSLObject):
                    raise TypeError("Значение не имеет методов или свойств")
                value.set_member(node.target.name, (yield from self._visit(node.value)))
            else:
                if type(value) in (BSLChars, BSLCatalogMetadataCollection, BSLCatalogs):
                    value.set_index((yield from self._visit(node.target.index)), (yield from self._visit(node.value)))
                    return
                if not isinstance(value, _COLLECTIONS):
                    raise TypeError("Индексирование поддерживается только для коллекций")
                index = (yield from self._visit(node.target.index))
                setter = value.set_index if isinstance(value, _TABLE_COLLECTIONS) else value.set
                setter(index, (yield from self._visit(node.value)))

    def set_variable(self, name: str, value: object) -> None:
        name = name.casefold()
        if (name in ("thisobject", "этотобъект")
                and not (self.locals is not None and name in self.locals)
                and not (self._has_module_context and name in self.variables
                         and (self.locals is None or name in self.module_names))):
            raise ValueError(f"Нельзя присвоить значение свойству только для чтения: {name}")
        if name in self.imports and self.locals is None:
            raise ValueError(f"Нельзя присвоить значение имени импорта: {name}")
        if self.locals is None or (self._has_module_context and name in self.module_names and name not in self.locals):
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
                                native_target=self.native_target,
                                database_context=self.database_context,
                                compilation_profile=self.compilation_profile)
            child._scheduler = self._scheduler
            child._diagnostic_owner = self._diagnostic_owner
            child.functions = self.functions.copy()
            child.types = self.types.copy()
            child._context_stack = self._context_stack
            child._module_cache = self._module_cache
            child._loading = self._loading
            child._handled_errors = self._handled_errors
            child._error_info_boundaries = self._error_info_boundaries
            child._eval_depth = self._eval_depth
            child._execute_depth = self._execute_depth
            child._self_module.path = path
            child.execute(text, str(path))
            module = child._self_module
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
            (yield from self.block(node.body))
        except BSLRuntimeError as error:
            # 1C discards parent diagnostic information on entering a nested handler.
            # Keep frames for reliable unwinding, but never revive their stale errors.
            for index in range(len(self._handled_errors)):
                self._handled_errors[index] = None
            self._handled_errors.append(error)
            try:
                (yield from self.block(node.handler))
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
        message = to_string((yield from self._visit(node.value)))
        arguments = node.optional_arguments or []
        if len(arguments) > 4:
            raise TypeError("ВызватьИсключение ожидает не более 5 аргументов")
        values = []
        for argument in arguments:
            values.append(None if isinstance(argument, ast.OmittedArgument) else (yield from self._visit(argument)))
        values.extend([None] * (4 - len(values)))
        category, code, additional, cause = values
        if category is not None:
            if type(category) is not BSLErrorCategory:
                raise TypeError("Ожидается значение КатегорияОшибки")
            if category in FORBIDDEN_RAISE_CATEGORIES:
                # A rejected category is a runtime validation error, not an
                # explicitly raised script exception. Native exposes its cause.
                message = "Недопустимая категория ВызватьИсключение"
                cause_info = BSLErrorInfo(message, categories=frozenset({
                    BSLErrorCategory.ALL_ERRORS}))
                token = node.token
                info = BSLErrorInfo(message, cause=cause_info, module_name=token.source,
                                    line_number=token.line, initial_string=token.source_line)
                raise BSLRuntimeError(message, token.source, token.line, token.column, info=info)
        if code is not None and type(code) is not str:
            raise TypeError("Код ошибки должен быть строкой")
        if additional is not None and type(additional) is not str:
            raise TypeError("Дополнительная информация должна быть строкой")
        if cause is not None and type(cause) is not BSLErrorInfo:
            raise TypeError("Причина должна иметь тип ИнформацияОбОшибке")
        categories = {BSLErrorCategory.ALL_ERRORS, BSLErrorCategory.SCRIPT_RUNTIME_ERROR,
                      BSLErrorCategory.EXCEPTION_RAISED_FROM_SCRIPT}
        if category is not None:
            categories.add(category)
        if cause is not None and cause._empty:
            # Empty diagnostic values contribute OtherError but do not produce
            # a visible Cause node, as measured by the five-argument checkpoint.
            categories.update(cause.categories)
            cause = None
        token = node.token
        info = BSLErrorInfo(message, code or "", additional or "", cause,
                            frozenset(categories), token.source, token.line, token.source_line)
        raise BSLRuntimeError(message, token.source, token.line, token.column, info=info)

    def visit_Return(self, node: ast.Return) -> None:
        raise _Return((yield from self._visit(node.value)) if node.value is not None else None)

    def visit_ExpressionStatement(self, node: ast.ExpressionStatement) -> object:
        expression = self.ungroup(node.expression)
        if isinstance(expression, ast.Call):
            # A procedure is allowed only when its result is discarded.
            return (yield from self.call(expression, require_value=False))
        return (yield from self._visit(node.expression))

    def visit_Var(self, node: ast.Var) -> None:
        if self.locals is None and any(name.casefold() in self.imports for name in node.names):
            raise ValueError("Имя импорта конфликтует с объявлением")
        for name in node.names:
            (self.variables if self.locals is None else self.locals).setdefault(name.casefold(), None)

    def visit_If(self, node: ast.If) -> None:
        for condition, body in node.branches:
            if boolean((yield from self._visit(condition))):
                (yield from self.block(body))
                return
        (yield from self.block(node.otherwise))

    def iteration(self, body: list[ast.Node]) -> bool:
        try:
            (yield from self.block(body))
        except _Continue:
            pass
        except _Break:
            return False
        return True

    def visit_For(self, node: ast.For) -> None:
        start = require_number((yield from self._visit(node.start)))
        end = require_number((yield from self._visit(node.end)))
        name = node.name.casefold()
        self.set_variable(name, start)
        while require_number(self.visit_Name(ast.Name(node.token, name))) <= end:
            if not (yield from self.iteration(node.body)):
                break
            self.set_variable(name, require_number(self.visit_Name(ast.Name(node.token, name))) + Decimal(1))

    def visit_ForEach(self, node: ast.ForEach) -> None:
        collection = (yield from self._visit(node.collection))
        if (not isinstance(collection, _COLLECTIONS)
                and type(collection) is not BSLRoundModes
                and type(collection) is not BSLSearchDirections
                and type(collection) is not BSLSortDirections):
            raise TypeError("Для Каждого ожидает массив, структуру, соответствие или поддержанное пространство системного перечисления")
        for item in collection:
            self.set_variable(node.name, item)
            if not (yield from self.iteration(node.body)):
                break

    def visit_While(self, node: ast.While) -> None:
        while boolean((yield from self._visit(node.condition))):
            if not (yield from self.iteration(node.body)):
                break

    def visit_Break(self, node: ast.Break) -> None:
        raise _Break

    def visit_Continue(self, node: ast.Continue) -> None:
        raise _Continue

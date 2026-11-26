from weakref import WeakValueDictionary
from threading import RLock
from contextlib import contextmanager
from .http.http_security import (BSLOpenSSLSecureConnection, BSLFileCertificationAuthorityCertificates,
                            BSLOSCertificationAuthorityCertificates, BSLInternetProxy)
from .http.http_client import BSLHTTPConnection, BSLHTTPRequest
from .formats.xml.xdto_io import BSLXDTOFactory, create_xdto_factory
from .formats.xml.dom_nodes import BSLDOMDocument
from .formats.xml.dom_xpath import BSLDOMNamespaceResolver
from .formats.xml.dom_io import BSLDOMBuilder, BSLDOMWriter
from .streams.data_hashing import BSLDataHashing
from .streams.data_io import BSLDataReader, BSLDataWriter
from .streams.zip_archives import BSLZipFileReader, BSLZipFileWriter
"""Direct runtime state, canonical services and live ownership boundaries."""

from decimal import Decimal
from types import MethodType

from .streams import file_io
from .formats.xml.xml_io import (BSLXMLReader, BSLXMLReaderSettings, BSLXMLNodeType, BSLXMLSpace,
                     BSLXMLValidationType, BSLXMLNamespaceContext, XML_NODE_TYPES, XML_SPACES, XML_VALIDATION_TYPES)
from .formats.xml.xml_writer import BSLXMLWriter, BSLXMLWriterSettings
from .streams import binary_streams
from .streams.binary_streams import BSLBinaryDataBuffer, BSLMemoryStream, BSLFileStream
from .streams.file_io import BSLFile, BSLTextReader, BSLTextWriter, BSLBinaryData
from .streams.text_documents import BSLTextDocument
from .application.user_messages import BSLUserMessage, UserMessageContext
from .formats.storage.value_storage import BSLValueStorage
from .streams.data_compression import BSLDeflation
from .formats.json.json_dates import (BSLJSONSerializerSettings, JSON_DATE_FORMATS, JSON_DATE_WRITING_VARIANTS,
                         read_json_date, write_json_date)
from .formats.json.json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings, read_json, write_json
from .types.unique_identifiers import BSLUUID
from .application.async_runtime import Scheduler, SchedulerLimitError
from .application.callbacks import BSLCallbackDescription, callback_description_marker, run_callback_marker
from pathlib import Path
from typing import Callable

from .syntax import ast
from .numeric import bits, elementary, numbers
from .formats.regex import regex_functions
from yadinassi.temporal import clocks, date_time_conversions, dates, period_presentation
from yadinassi.text import formatting, number_in_words, strings
from yadinassi.formats.storage import serialization
from yadinassi.types import type_values, value_checks
from yadinassi.formats.xml import xml_values
from .configuration.metadata import BSLMetadata
from .db.catalog.catalogs import BSLCatalogs
from .db.query.queries import BSLQuery
from .db.query.query_packages import BSLTempTablesManager
from .db.document.documents import BSLDocuments
from .db.registers.information_registers import BSLInformationRegisters
from .db.database_context import SQLiteDBContext, require_database_context
from .types.type_descriptions import BSLTypeDescription
from .collections.value_trees import (BSLValueTree, BSLValueTreeColumnCollection, BSLValueTreeColumn,
                          BSLValueTreeRow, BSLValueTreeRowCollection)
from .collections.value_tables import (BSLValueTable, BSLValueTableColumnCollection,
                           BSLValueTableColumn, BSLValueTableRow,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .collections.value_lists import BSLValueList
from .types.type_qualifiers import (
    ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)
from .types.errors import BSLRuntimeError
from .types.error_info import (BSLErrorInfo, BSLErrorCategory, ERROR_CATEGORIES,
                         FORBIDDEN_RAISE_CATEGORIES, empty_error_info)
from .syntax.parser import (parse, parse_expression, parse_fragment, validate_labels, validate_async,
                            prepare_control_flow, PreparedBlock)
from .syntax.lexer import KEYWORDS
from .syntax.preprocessor import validate_compilation_profile
from .collections.maps import BSLFixedMap, BSLMap
from .execution.codegen.native_targets import WINDOWS_8_3_27_2342, validate_native_target
from .collections.structures import BSLFixedStructure, BSLStructure, fill_property_values
from .types.values import (
    BSLArray, BSLFixedArray, BSLObject, BSLType, HostFunction, InterpreterCall, NULL, Reference as _Reference,
    boolean, divide, equal, number, require_number, to_string,
)


# Explicit Yadinassi resource limits, not asserted native language limits.
EVAL_MAX_SOURCE = 65536
EVAL_MAX_DEPTH = 16
EXECUTE_MAX_SOURCE = 65536
EXECUTE_MAX_DEPTH = 16


def _eval_marker(value: object) -> object:
    # The interpreter supplies the current module/frame at the call site.
    raise TypeError("Вычислить требует контекст интерпретатора")




class _VariableReference(_Reference):
    """Named dictionary storage, preserving its provenance through forwarding."""


class _Module:
    """A stable, explicit public module receiver, never a platform/Python object."""

    def __init__(self, interpreter: "Interpreter", path: Path | None = None):
        self.interpreter = interpreter
        self.path = path
        self.ready = False
        self._platform_type = None

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
        metadata = (routine
                    if self.ready and routine is not None else None)
        if not self.ready or metadata is None or not metadata.exported:
            raise ValueError(f"Метод объекта не обнаружен: {name}")
        if metadata.is_dual:
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
                 database_context: SQLiteDBContext | None = None,
                 compilation_profile: str = "standalone",
                 user_message_sink: Callable | None = None,
                 family_owner: "Interpreter | None" = None,
                 execution_backend: str | None = None,
                 allow_extensions: bool | None = None):
        if execution_backend is not None and (type(execution_backend) is not str or execution_backend != 'python-direct'):
            raise ValueError("unsupported execution backend")
        inherited_extensions = family_owner.allow_extensions if isinstance(family_owner, Interpreter) else False
        if allow_extensions is None:
            allow_extensions = inherited_extensions
        if type(allow_extensions) is not bool:
            raise TypeError('allow_extensions must be bool')
        if isinstance(family_owner, Interpreter) and allow_extensions != inherited_extensions:
            raise ValueError('interpreter family cannot change extension policy')
        self._allow_extensions = allow_extensions
        self._compilation_profile = validate_compilation_profile(compilation_profile)
        self._native_target = validate_native_target(native_target)
        if database_context is not None:
            database_context.require_active(tabular_sections=True)
        self._database_context = database_context
        self._xdto_factory = BSLXDTOFactory()
        if family_owner is not None:
            if not isinstance(family_owner, Interpreter) or family_owner.native_target != self._native_target:
                raise ValueError('compatible interpreter family owner required')
            if family_owner._family_owner is not family_owner:
                raise ValueError('root interpreter family owner required')
            if family_owner._family_closed:
                raise ValueError('interpreter family is closed')
        self._family_owner = self if family_owner is None else family_owner
        self._family_closed = False
        self._family_released = False
        self._family_generation = 0 if family_owner is None else family_owner._family_generation
        if family_owner is None:
            self._direct_execution_lock = RLock()
            self._direct_executions = 0
            self._direct_cancelling = False
            self._schema_scopes = WeakValueDictionary()
        self._bind_schema_scope()
        self._scheduler = (Scheduler(self._native_target) if family_owner is None
                           else family_owner._scheduler)
        self._diagnostic_owner = self
        self.variables: dict[str, object] = {}
        self.functions: dict[str, HostFunction] = {}
        self.routines: dict[str, ast.Routine] = {}
        self.server_routines: dict[str, ast.Routine] = {}
        # Host-installed InvocationPort stubs contain signatures, never server bodies.
        self._invocation_bindings: dict[str, tuple] = {}
        self.server_module_names: set[str] = set()
        self.server_initializers: list[ast.ServerInitializer] = []
        self._logical_side = "client"
        if family_owner is None:
            self._context_stack = ["client"]
            self._module_context_stack = [True]
        # Family tombstones survive a missing side, including detached servers,
        # so an unavailable variant can never fall through to a host function.
        self._dual_routine_names: set[str] = set()
        self.module_names: set[str] = set()
        self.exported_variables: set[str] = set()
        self._self_module = _Module(self)
        self.locals: dict[str, object] | None = None
        self.types: dict[str, HostFunction] = {}
        self.output = output
        self.user_messages = UserMessageContext(output, user_message_sink)
        self.encoding = encoding
        self.imports: dict[str, _Module | _Namespace] = {}
        self._configuration_runtime = None
        self._module_cache: dict[Path, _Module] = {}
        self._loading: list[Path] = []
        # Imports share this dynamic handler stack, independent of variable frames.
        self._handled_errors: list[BSLRuntimeError | None] = []
        self._error_info_boundaries: list[int] = []
        self._execute_depth = [0]
        register_function = self._register_function
        register_type = self._register_type
        from .configuration.common_templates import get_common_template_marker
        register_function('ПолучитьОбщийМакет',get_common_template_marker,'GetCommonTemplate')
        from .application.reusable_values import refresh_reusable_marker
        register_function('ОбновитьПовторноИспользуемыеЗначения',refresh_reusable_marker,'RefreshReusableValues',returns_value=False)
        self._eval_depth = [0]  # Shared by imported modules, like the handler stack.
        from .application import temporary_storage
        register_function('ПоместитьВоВременноеХранилище',temporary_storage.put_marker,'PutToTempStorage')
        register_function('ПолучитьИзВременногоХранилища',temporary_storage.get_marker,'GetFromTempStorage')
        register_function('УдалитьИзВременногоХранилища',temporary_storage.delete_marker,'DeleteFromTempStorage',returns_value=False)
        register_function('ЭтоАдресВременногоХранилища',temporary_storage.recognize_marker,'IsTempStorageURL')
        register_function("Вычислить", _eval_marker, "Eval")
        register_function("ВыполнитьОбработкуОповещения", run_callback_marker, "RunCallback")
        register_type("ОписаниеОповещения", callback_description_marker, "CallbackDescription")
        register_function("Сообщить", self._message, "Message")
        register_function("Строка", to_string, "String")
        register_function("Число", number, "Number")
        register_function("Булево", boolean, "Boolean")
        # Bind only immutable startup data, never the interpreter's client frame.
        connection_string = (database_context.connection_string if database_context is not None
                             else require_database_context)
        register_function("НачатьТранзакцию", self._begin_transaction, "BeginTransaction", returns_value=False)
        register_function("ЗафиксироватьТранзакцию", self._commit_transaction, "CommitTransaction", returns_value=False)
        register_function("ОтменитьТранзакцию", self._rollback_transaction, "RollbackTransaction", returns_value=False)
        register_function("ТранзакцияАктивна", self._transaction_active, "TransactionActive")
        register_function("СтрокаСоединенияИнформационнойБазы", connection_string,
                               "InfoBaseConnectionString")
        register_function("ЗаполнитьЗначенияСвойств", fill_property_values,
                               "FillPropertyValues", returns_value=False)
        register_function("ЗначениеЗаполнено", value_checks.value_is_filled, "ValueIsFilled")
        register_function("Тип", self._type_by_name, "Type")
        register_function("ТипЗнч", type_values.type_of, "TypeOf")
        register_function("ЗначениеВСтрокуВнутр", serialization.value_to_string_internal,
                               "ValueToStringInternal")
        register_function("ЗначениеИзСтрокиВнутр", serialization.value_from_string_internal,
                               "ValueFromStringInternal")
        for name, function, alias in (*regex_functions.BUILTINS, *strings.BUILTINS, *formatting.BUILTINS, *number_in_words.BUILTINS, *period_presentation.BUILTINS, *numbers.BUILTINS,
                                      *xml_values.BUILTINS, *bits.BUILTINS, *elementary.BUILTINS,
                                      *dates.BUILTINS, *clocks.BUILTINS,
                                      *date_time_conversions.BUILTINS):
            register_function(name, function, alias)
        register_function("ОписаниеОшибки", self._error_description, "ErrorDescription")
        register_function("ИнформацияОбОшибке", self._error_info, "ErrorInfo")
        register_type("ПараметрыЗаписиJSON", BSLJSONWriterSettings, "JSONWriterSettings")
        register_type("НастройкиСериализацииJSON", BSLJSONSerializerSettings, "JSONSerializerSettings")
        register_function("ПрочитатьДатуJSON", read_json_date, "ReadJSONDate")
        register_function("ЗаписатьДатуJSON", write_json_date, "WriteJSONDate")
        register_type("ЧтениеXML", BSLXMLReader, "XMLReader")
        register_type("ЗаписьXML", BSLXMLWriter, "XMLWriter")
        register_type("ПараметрыЧтенияXML", BSLXMLReaderSettings, "XMLReaderSettings")
        register_type("ПараметрыЗаписиXML", BSLXMLWriterSettings, "XMLWriterSettings")
        register_type("ФабрикаXDTO", BSLXDTOFactory, "XDTOFactory")
        register_function("СоздатьФабрикуXDTO", create_xdto_factory, "CreateXDTOFactory")
        register_type("Разыменователь пространств имен DOM XPath", BSLDOMNamespaceResolver, "DOMNamespaceResolver")
        register_type("ДокументDOM", BSLDOMDocument, "DOMDocument")
        register_type("ПостроительDOM", BSLDOMBuilder, "DOMBuilder")
        register_type("ЗаписьDOM", BSLDOMWriter, "DOMWriter")
        register_type("ЗащищенноеСоединениеOpenSSL", BSLOpenSSLSecureConnection, "OpenSSLSecureConnection")
        register_type("СертификатыУдостоверяющихЦентровФайл", BSLFileCertificationAuthorityCertificates, "FileCertificationAuthorityCertificates")
        register_type("СертификатыУдостоверяющихЦентровОС", BSLOSCertificationAuthorityCertificates, "OSCertificationAuthorityCertificates")
        register_type("ИнтернетПрокси", BSLInternetProxy, "InternetProxy")
        register_type("HTTPСоединение", BSLHTTPConnection, "HTTPConnection")
        register_type("HTTPЗапрос", BSLHTTPRequest, "HTTPRequest")
        register_type("ХешированиеДанных", BSLDataHashing, "DataHashing")
        register_type("ЧтениеДанных", BSLDataReader, "DataReader")
        register_type("ЗаписьДанных", BSLDataWriter, "DataWriter")
        register_type("ЧтениеZipФайла", BSLZipFileReader, "ZipFileReader")
        register_type("ЗаписьZipФайла", BSLZipFileWriter, "ZipFileWriter")
        register_type("ЧтениеJSON", BSLJSONReader, "JSONReader")
        register_type("ЗаписьJSON", BSLJSONWriter, "JSONWriter")
        register_function("ПрочитатьJSON", read_json, "ReadJSON")
        register_function("ЗаписатьJSON", write_json, "WriteJSON", returns_value=False)
        for ru, factory, en in (("Файл", BSLFile, "File"),
                                ("ЧтениеТекста", BSLTextReader, "TextReader"),
                                ("ЗаписьТекста", BSLTextWriter, "TextWriter"),
                                ("ДвоичныеДанные", BSLBinaryData, "BinaryData")):
            register_type(ru, factory, en)
        for ru, factory, en in (("БуферДвоичныхДанных", BSLBinaryDataBuffer, "BinaryDataBuffer"),
                                ("ПотокВПамяти", BSLMemoryStream, "MemoryStream"),
                                ("ФайловыйПоток", BSLFileStream, "FileStream")):
            register_type(ru, factory, en)
        for ru, function, en in binary_streams.FUNCTIONS:
            register_function(ru, function, en)
        for ru, function, en, returns_value in file_io.FUNCTIONS:
            register_function(ru, function, en, returns_value=returns_value)
        register_type("ТекстовыйДокумент", BSLTextDocument, "TextDocument")
        register_type("СообщениеПользователю", self._new_user_message, "UserMessage")
        register_type("ХранилищеЗначения", BSLValueStorage, "ValueStorage")
        register_type("СжатиеДанных", BSLDeflation, "Deflation")
        register_type("УникальныйИдентификатор", BSLUUID, "UUID")
        register_type("Массив", BSLArray, "Array")
        register_type("Структура", BSLStructure, "Structure")
        register_type("Соответствие", BSLMap, "Map")
        register_type("ФиксированныйМассив", BSLFixedArray, "FixedArray")
        register_type("ФиксированнаяСтруктура", BSLFixedStructure, "FixedStructure")
        register_type("ФиксированноеСоответствие", BSLFixedMap, "FixedMap")

        register_type("МенеджерВременныхТаблиц", self._new_temp_tables_manager, "TempTablesManager")
        register_type("Запрос", self._new_query, "Query")
        register_type("ТаблицаЗначений", BSLValueTable, "ValueTable")
        register_type("ДеревоЗначений", BSLValueTree, "ValueTree")
        register_type("СписокЗначений", BSLValueList, "ValueList")
        register_type("ОписаниеТипов", BSLTypeDescription, "TypeDescription")
        register_type("КвалификаторыЧисла", BSLNumberQualifiers, "NumberQualifiers")
        register_type("КвалификаторыСтроки", BSLStringQualifiers, "StringQualifiers")
        register_type("КвалификаторыДаты", BSLDateQualifiers, "DateQualifiers")
        register_type("КвалификаторыДвоичныхДанных", BSLBinaryDataQualifiers, "BinaryDataQualifiers")

        if not self.allow_extensions:
            self._builtin_functions = self._binding_snapshot(self.functions)
            self._builtin_types = self._binding_snapshot(self.types)

    @staticmethod
    def _binding_snapshot(registry):
        return {key: (value, value.function, value.name, value.reference_parameters, value.returns_value)
                for key, value in registry.items()}

    @property
    def allow_extensions(self) -> bool:
        """Allow custom host registrations and extension-aware code generation."""
        return self._allow_extensions

    @property
    def database_context(self) -> SQLiteDBContext | None:
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
        if self._scheduler.is_active:
            # A rejected nested pump is not a host boundary and must not consume
            # the enclosing execution's procedure failures.
            self._pump_async(max_steps=max_steps)
            return
        try:
            self._pump_async(max_steps=max_steps)
        finally:
            # Preserve pump/host failure precedence, but never keep the batch
            # as traceback-bearing history for a later execution.
            error = self._scheduler.take_procedure_error()
        if error is not None:
            raise error

    def ensure_complete(self):
        """Reject silent process success while language tasks remain blocked."""
        if self.pending_promises:
            raise BSLRuntimeError("Остались незавершенные асинхронные задания",
                                  "<async>", 1, 1)

    def _bind_schema_scope(self):
        # Types/metadata belong to one family generation, not to individual
        # routine interpreters. Managers stay VM-local (notably document code).
        scopes = self._family_owner._schema_scopes
        metadata = scopes.get(id(self.database_context))
        self._metadata = BSLMetadata(self.database_context) if metadata is None else metadata
        scopes[id(self.database_context)] = self._metadata
        self._catalogs = BSLCatalogs(self._metadata._catalogs, self.database_context)
        self._documents = BSLDocuments(self._metadata._documents, self.database_context, self._catalogs)
        self._documents._interpreter = self
        self._information_registers = BSLInformationRegisters(
            self._metadata._information_registers, self.database_context, self._catalogs, self._documents)
        if metadata is None:
            self._metadata._bind_managers(self._catalogs, self._documents)
            from .configuration.demos.inventory_enum_runtime import bind as bind_storage_enums
            bind_storage_enums(self,self._metadata)

    @contextmanager
    def _direct_execution_scope(self):
        """Account for synchronous direct execution without driving the scheduler."""
        root=self._family_owner
        with root._direct_execution_lock:
            if root._direct_cancelling:
                raise RuntimeError('Cannot execute while scheduler cancellation is active')
            root._direct_executions+=1
        try:yield
        finally:
            with root._direct_execution_lock:root._direct_executions-=1

    def cancel_pending(self):
        """Cancel current cooperative work without retiring the module family."""
        if self._family_owner is not self or self._family_closed:
            raise ValueError('active root interpreter required')
        with self._direct_execution_lock:
            if self._direct_executions or self._direct_cancelling:
                raise RuntimeError('Cannot reset an active scheduler')
            self._direct_cancelling=True
        try:self._scheduler.reset()
        finally:
            with self._direct_execution_lock:self._direct_cancelling=False

    def close(self):
        """Release suspended frames explicitly at the embedding lifecycle boundary."""
        if self._family_owner is not self and self._scheduler.pending:
            raise ValueError('cannot release a child while family tasks are pending')
        if self._family_owner is not self:
            self._family_released = True
        if self._family_owner is self:
            self._scheduler.reset()
            self._family_closed = True
            self._family_generation += 1

    def _require_family(self):
        if self._family_owner is self:
            # A standalone embedding historically may execute again after reset.
            # Its old children stay fenced by generation; application lifecycle
            # remains independently guarded by ConfigurationApplication.
            if self._family_closed:
                self._schema_scopes.clear()
                self._bind_schema_scope()
            self._family_closed = False
        elif (self._family_released or self._family_owner._family_closed
                or self._family_generation != self._family_owner._family_generation):
            raise ValueError("interpreter family member is closed")

    @property
    def pending_promises(self):
        return self._scheduler.pending

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
        if not self.allow_extensions:
            raise ValueError('register_function requires allow_extensions=True')
        Interpreter._register_function(self, name, function, *aliases, returns_value=returns_value)
        self.functions[name.casefold()]._public_number_arguments = True

    def _register_function(self, name, function, *aliases, returns_value=True):
        wrapper = HostFunction(name, function, returns_value=returns_value)
        for alias in (name, *aliases):
            self.functions[alias.casefold()] = wrapper

    def register_type(self, name: str, factory: Callable, *aliases: str) -> None:
        if not self.allow_extensions:
            raise ValueError('register_type requires allow_extensions=True')
        Interpreter._register_type(self, name, factory, *aliases)
        self.types[name.casefold()]._python_extension_factory = True

    def _register_type(self, name, factory, *aliases):
        wrapper = HostFunction(name, factory)
        for alias in (name, *aliases):
            self.types[alias.casefold()] = wrapper

    def _register_platform_function(self, name, function, *aliases, returns_value=True):
        """Install an application-owned service without enabling Python extensions."""
        Interpreter._register_function(self, name, function, *aliases, returns_value=returns_value)
        if not self.allow_extensions:
            self._record_platform_binding(self.functions, self._builtin_functions, name, aliases)

    def _register_platform_type(self, name, factory, *aliases):
        """Install an application-owned factory without enabling Python extensions."""
        Interpreter._register_type(self, name, factory, *aliases)
        if not self.allow_extensions:
            self._record_platform_binding(self.types, self._builtin_types, name, aliases)

    @staticmethod
    def _record_platform_binding(registry, snapshot, name, aliases):
        # Never resnapshot the whole registry: unrelated host mutations do not
        # become canonical as a side effect of installing one platform binding.
        wrapper = registry[name.casefold()]
        binding = (wrapper, wrapper.function, wrapper.name, wrapper.reference_parameters, wrapper.returns_value)
        for alias in (name, *aliases):
            snapshot[alias.casefold()] = binding

    def _new_type_description(self, *values):
        # Resolve only one application-owned enum type name. Mixed/reference
        # unions and all qualifiers still pass through the descriptor's closed
        # admission; do not turn arbitrary names into host type lookups.
        if values and type(values[0]) is str and len(values[0]) <= 4096:
            token = values[0].strip()
            prefix, separator, _ = token.partition('.')
            if (separator and ',' not in token and prefix.casefold() in
                    ('enumref', 'перечислениессылка', 'enummanager', 'перечислениеменеджер')):
                self._require_family()
                if self._metadata._enumerations is None:
                    raise ValueError('enumeration types require an active configuration application')
                kind = self._metadata._enumerations.resolve_type(token)
                source = BSLArray()
                source.items.append(kind)
                values = (source, *values[1:])
        return BSLTypeDescription(*values)

    def _type_by_name(self, name):
        if self._metadata._enumerations is not None:
            value = self._metadata._enumerations.resolve_type(name)
            if value is not None: return value
        return self._information_registers.type_by_name(name)

    def _new_query(self, text=""):
        return BSLQuery(self._catalogs, text, self._documents, self._information_registers)

    def _new_temp_tables_manager(self):
        return BSLTempTablesManager(self._catalogs._metadata)

    def _inherit_host_bindings(self, parent):
        """Copy host registrations, rebinding only exact VM-owned core helpers.

        Each activation owns its metadata/catalog snapshot. Copying a parent's
        bound Type or Query factory crosses that boundary even with the same DB.
        Explicit host overrides remain untouched; names alone grant no rebinding.
        """
        # Plain children already have their own canonical registrations.
        if not self.allow_extensions:
            return
        core_helpers = (Interpreter._message, Interpreter._error_description,
                        Interpreter._error_info, Interpreter._type_by_name,
                        Interpreter._new_query, Interpreter._new_temp_tables_manager,
                        Interpreter._new_user_message, Interpreter._begin_transaction,
                        Interpreter._commit_transaction, Interpreter._rollback_transaction,
                        Interpreter._transaction_active)
        wrappers = {}

        def copy_registry(registry):
            result = {}
            for name, wrapper in registry.items():
                identity = id(wrapper)
                if identity not in wrappers:
                    callback = wrapper.function
                    if type(callback) is MethodType:
                        for helper in core_helpers:
                            if callback.__func__ is helper:
                                callback = helper.__get__(self, type(self))
                                break
                    wrappers[identity] = (wrapper if callback is wrapper.function else HostFunction(
                        wrapper.name, callback,
                        reference_parameters=wrapper.reference_parameters,
                        returns_value=wrapper.returns_value))
                result[name] = wrappers[identity]
            return result

        self.functions = copy_registry(parent.functions)
        self.types = copy_registry(parent.types)

    def _new_user_message(self):
        return BSLUserMessage(self.user_messages)

    def _message(self, value: object) -> None:
        if self._configuration_runtime is not None and self._configuration_runtime.state == "exiting":
            raise ValueError("Messages are unavailable during application OnExit")
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

    def _transaction_backend(self):
        return None if self.database_context is None else self.database_context.backend

    def _transaction_active(self):
        from .db.database_transactions import active
        if (not getattr(self, '_transaction_activation_allowed', True)
                or self._scheduler._active_task is not None or self._scheduler.pending):
            raise ValueError('Transaction status requires an authorized synchronous activation')
        return active(self._transaction_backend())

    def _begin_transaction(self):
        from .db.database_transactions import begin
        if (not getattr(self, '_transaction_activation_allowed', True)
                or self._scheduler._active_task is not None or self._scheduler.pending):
            raise ValueError('Transactions require synchronous execution without pending tasks')
        begin(self._transaction_backend())

    def _commit_transaction(self):
        if not getattr(self, '_transaction_activation_allowed', True):
            raise ValueError('Transaction control is unavailable in this activation')
        from .db.database_transactions import commit
        commit(self._transaction_backend())

    def _rollback_transaction(self):
        if not getattr(self, '_transaction_activation_allowed', True):
            raise ValueError('Transaction control is unavailable in this activation')
        from .db.database_transactions import rollback
        rollback(self._transaction_backend())

    @property
    def execution_backend(self):
        return 'python-direct'

    def prepare(self, text: str, source: str = "<строка>"):
        """Compile a reusable owned module snapshot for python-direct only."""
        from .execution.direct.python_direct import prepare_module, _reject
        if type(self) is not Interpreter:
            _reject('specialized Interpreter contexts are not integrated')
        return prepare_module(self, parse(text, source, compilation_profile=self.compilation_profile),
                              source_text=text, source_name=source)

    def prepare_program(self, program: list[ast.Node]):
        """Snapshot and compile an AST; later caller edits do not affect it."""
        from .execution.direct.python_direct import prepare_module
        return prepare_module(self, program)

    def execute_prepared(self, prepared):
        """Run an explicit prepared snapshot with current namespace/services."""
        from .execution.direct.python_direct import execute_prepared
        return execute_prepared(self, prepared)

    def execute(self, text: str, source: str = "<строка>") -> object:
        from .execution.direct.python_direct import execute
        return execute(self, parse(text, source, compilation_profile=self.compilation_profile),
                       source_text=text, source_name=source)

    def execute_program(self, program: list[ast.Node]) -> object:
        """Compile and execute the supplied AST through the direct compiler only."""
        from .execution.direct.python_direct import execute, _snapshot
        return execute(self, _snapshot(program, supplied=True))


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

    def _require_callback_context(self):
        if self.execution_context != "client":
            raise ValueError("ОписаниеОповещения поддерживается только на клиенте")
        self._require_module_storage_context()

    def _callback_module(self, value):
        # Strings select already imported modules only. Never import code, read
        # arbitrary paths or expose Python attributes on behalf of a callback.
        if type(value) is str:
            parts = value.split(".")
            receiver = self.imports.get(parts[0].casefold())
            if receiver is None and len(parts) == 1 and self._configuration_runtime is not None:
                receiver = self._configuration_runtime.resolve_module(parts[0], self)
            for part in parts[1:]:
                receiver = (receiver.members.get(part.casefold())
                            if type(receiver) is _Namespace else None)
            if type(receiver) is not _Module:
                raise ValueError(f"Модуль оповещения не импортирован: {value}")
            value = receiver
        if value is not None and type(value) is not _Module:
            raise TypeError("ОписаниеОповещения: ожидается объект импортированного модуля")
        if value is not None and value.interpreter._scheduler is not self._scheduler:
            raise ValueError("ОписаниеОповещения: модуль другого интерпретатора")
        return value

    def _new_callback(self, values):
        self._require_callback_context()
        if len(values) > 5:
            raise TypeError("ОписаниеОповещения ожидает от 0 до 5 аргументов")
        name, module, additional, error_name, error_module = [*values, *([None] * (5 - len(values)))]
        if name is not None and type(name) is not str:
            raise TypeError("ОписаниеОповещения: имя процедуры должно быть строкой")
        # This family implements direct completion dispatch, not an async
        # operation/error-dialog protocol. Never silently discard a handler.
        if error_name is not None or error_module is not None:
            raise ValueError("Обработчик ошибки ОписаниеОповещения пока не поддерживается")
        target = self._capture_form_callback(module)
        if target is not None:
            return BSLCallbackDescription(name, module, additional, _form_target=target)
        return BSLCallbackDescription(name, self._callback_module(module), additional)

    def _capture_form_callback(self, receiver):
        # Only the owned form interpreter overrides this closed enrollment seam.
        return None

    def callback_target(self, description, *, form_arity=2):
        """Validate a value capability without executing or creating source."""
        if type(form_arity) is not int or form_arity not in (1, 2):
            raise ValueError('unsupported sealed form callback arity')
        self._require_callback_context()
        if type(description) is not BSLCallbackDescription:
            raise TypeError('ВыполнитьОбработкуОповещения: ожидается ОписаниеОповещения')
        from .application.callbacks import _FormCallbackTarget
        target = description._form_target
        if target is not None:
            if type(target) is not _FormCallbackTarget or description.module is not target.receiver:
                raise ValueError('invalid form callback capability')
            owner = target.require(self)
            if type(description.procedure_name) is not str or not description.procedure_name:
                raise ValueError('callback procedure required')
            routine = owner.routines.get(description.procedure_name.casefold())
            metadata = routine
            if (metadata is None or not metadata.exported or metadata.is_function or metadata.is_async
                    or metadata.is_dual or not metadata.module_context or metadata.execution_context != 'client'
                    or len(metadata.parameters) != form_arity):
                raise ValueError('form completion requires an exported synchronous client procedure with the granted arity')
            return routine, owner
        module = self._callback_module(description.module)
        if module is None or not description.procedure_name:
            raise ValueError('ОписаниеОповещения: не заданы имя процедуры и модуль')
        routine = module.routine(description.procedure_name)
        if routine.execution_context != 'client':
            raise ValueError('Обработчик оповещения должен выполняться на клиенте')
        return routine, module.interpreter

    def _require_module_storage_context(self) -> None:
        # A supplied module receiver cannot restore missing module capability.
        # Guard source-level access, not _Module's low-level getters: an explicit
        # field reference already bound by the caller keeps ordinary semantics.
        if not self._has_module_context:
            raise ValueError("Хранилище модуля недоступно в подпрограмме без контекста")


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

    def _activation_interpreter(self):
        """Internal specialization seam; ordinary modules retain their behavior."""
        return Interpreter(self.output, encoding=self.encoding, native_target=self.native_target,
                           database_context=self.database_context,
                           compilation_profile=self.compilation_profile,
                           family_owner=self._family_owner)

    def _new_server_activation(self, *, module_context: bool = True) -> "Interpreter":
        """Fresh logical server call, not a real server or a form context."""
        server = self._activation_interpreter()
        server._transaction_activation_allowed = False
        server.user_messages = self.user_messages
        server._scheduler = self._scheduler
        if self._configuration_runtime is not None:
            self._configuration_runtime.bind_interpreter(server)
        server._logical_side = "server"
        server._context_stack = self._context_stack
        server.routines = self.server_routines.copy()
        server._invocation_bindings = self._invocation_bindings.copy()
        server.module_names = self.server_module_names.copy() if module_context else set()
        server.variables = dict.fromkeys(server.module_names)
        server.server_initializers = self.server_initializers.copy() if module_context else []
        server._dual_routine_names = self._dual_routine_names.copy()
        server._inherit_host_bindings(self)
        # Imports and the public module receiver remain unsupported server-side.
        # Side-local variables above never alias client storage.
        server._self_module.ready = False
        return server

    @staticmethod
    def ungroup(node: ast.Node) -> ast.Node:
        while isinstance(node, ast.Group):
            node = node.expression
        return node

    def set_variable(self, name: str, value: object) -> None:
        name = name.casefold()
        if self._configuration_runtime is not None:
            self._configuration_runtime.check_assignment(name, self)
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

    def semantic_import(self, node: ast.Import) -> None:
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
                                compilation_profile=self.compilation_profile,
                                family_owner=self._family_owner)
            child.user_messages = self.user_messages
            child._scheduler = self._scheduler
            if self._configuration_runtime is not None:
                self._configuration_runtime.bind_interpreter(child)
            child._diagnostic_owner = self._diagnostic_owner
            child._inherit_host_bindings(self)
            child._context_stack = self._context_stack
            child._module_cache = self._module_cache
            child._loading = self._loading
            child._handled_errors = self._handled_errors
            child._error_info_boundaries = self._error_info_boundaries
            child._eval_depth = self._eval_depth
            child._execute_depth = self._execute_depth
            child._self_module.path = path
            from .execution.direct.python_direct_imports import loading_child
            with loading_child(self,child,path):
                child.execute(text,str(path))
                module=child._self_module
                self._module_cache[path]=module
        return module


# Keep the actual storage hook sealed for standalone execution.
_DIRECT_SET_VARIABLE = Interpreter.set_variable
# Definition-time identities: a lazy direct-import adapter must not bless hooks
# installed before its first import.
_DIRECT_IMPORT_LOADER_ABI = tuple((name,vars(Interpreter)[name]) for name in
    ('semantic_import','_load_module','_check_import_binding','_inherit_host_bindings'))
_DIRECT_IMPORT_RECEIVER_ABI = tuple((cls,tuple(vars(cls).items()),cls.__mro__)
                                   for cls in (_Module,_Namespace))


# Capture canonical diagnostic identity before trusted host class overrides.
_DIRECT_ERROR_DESCRIPTION_ABI = Interpreter._error_description
_DIRECT_ERROR_INFO_ABI = Interpreter._error_info
_DIRECT_QUERY_FACTORY_ABI = Interpreter._new_query
_DIRECT_TEMP_TABLE_FACTORY_ABI = Interpreter._new_temp_tables_manager
_DIRECT_TYPE_NAME_ABI = Interpreter._type_by_name
_DIRECT_TRANSACTION_ABI = (Interpreter._begin_transaction, Interpreter._commit_transaction, Interpreter._rollback_transaction, Interpreter._transaction_active)

# Definition-time Message identity for the finite direct configuration command lane.
_DIRECT_CONFIGURATION_MESSAGE_ABI = Interpreter._message
_DIRECT_MESSAGE_CODE = Interpreter._message.__code__

# Definition-time execute lease; instance/class rebinding cannot replace it.
_DIRECT_EXECUTION_SCOPE_ABI = Interpreter._direct_execution_scope

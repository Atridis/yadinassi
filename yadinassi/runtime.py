from .execution.runtime_dependencies import runtime_module as _runtime_module
from functools import lru_cache
from weakref import WeakValueDictionary
from threading import RLock
from contextlib import nullcontext, contextmanager
from .http.http_security import (BSLOpenSSLSecureConnection, BSLFileCertificationAuthorityCertificates,
                            BSLOSCertificationAuthorityCertificates, BSLInternetProxy)
from .http.http_client import BSLHTTPConnection, BSLHTTPRequest, BSLHTTPResponse, BYTE_ORDER_MARK_USE
from .formats.xml.xdto_values import (BSLXDTODataObject, BSLXDTODataValue, BSLXDTOList, BSLXDTOValueType, BSLXDTOObjectType, BSLXDTOProperty, BSLXDTOPropertyCollection, BSLXDTOPackage, BSLXDTOPackageCollection)
from .formats.xml.xdto_io import BSLXDTOFactory, BSLXMLForm, XML_FORMS, create_xdto_factory
from .formats.xml.dom_nodes import (BSLDOMDocument, BSLDOMElement, BSLDOMAttribute, BSLDOMText, BSLDOMCDATASection, BSLDOMComment, BSLDOMProcessingInstruction, BSLDOMDocumentFragment, BSLDOMNodeList, BSLDOMElementList, BSLDOMAttributeMap, BSLDOMNodeType, DOM_NODE_TYPES)
from .formats.xml.dom_xpath import BSLDOMNamespaceResolver
from .formats.xml.dom_io import BSLDOMBuilder, BSLDOMWriter
from .streams.data_hashing import BSLDataHashing, HASH_FUNCTIONS
from .streams.data_io import BSLDataReader, BSLDataWriter
from .streams import zip_archives
from .streams.zip_archives import BSLZipFileReader, BSLZipFileWriter, BSLZipFileEntries
"""Direct runtime state, canonical services and live ownership boundaries."""

from decimal import Decimal, localcontext
from types import GeneratorType, MethodType

from .streams import file_io
from .formats.xml.xml_io import (BSLXMLReader, BSLXMLReaderSettings, BSLXMLNodeType, BSLXMLSpace,
                     BSLXMLValidationType, BSLXMLNamespaceContext, XML_NODE_TYPES, XML_SPACES, XML_VALIDATION_TYPES)
from .formats.xml.xml_writer import BSLXMLWriter, BSLXMLWriterSettings
from .streams import binary_streams
from .streams.binary_streams import BSLBinaryDataBuffer, BSLMemoryStream, BSLFileStream
from .streams.file_io import BSLFile, BSLTextReader, BSLTextWriter, BSLBinaryData, TEXT_ENCODINGS
from .streams.text_documents import BSLTextDocument
from .application.user_messages import BSLUserMessage, UserMessageContext
from .formats.storage.value_storage import BSLValueStorage
from .streams.data_compression import BSLDeflation
from .formats.json import json_processing
from .formats.json.json_dates import (BSLJSONSerializerSettings, JSON_DATE_FORMATS, JSON_DATE_WRITING_VARIANTS,
                         read_json_date, write_json_date)
from .formats.json.json_processing import BSLJSONReader, BSLJSONWriter, JSON_VALUE_TYPES, JSON_LINE_BREAKS, BSLJSONWriterSettings, read_json, write_json
from .types.unique_identifiers import BSLUUID
from .application.async_runtime import Scheduler, Promise, AwaitRequest, SchedulerLimitError
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
from .text.chars import BSLChars, CHARS
from .configuration.metadata import BSLCommonModuleMetadataCollection, BSLMetadata, BSLCatalogMetadataCollection, BSLDocumentMetadataCollection, is_metadata_collection, is_metadata_object
from .db.catalog.catalogs import BSLCatalogs
from .db.metadata.enumerations import BSLEnumerations, BSLEnumManager
from .application.session_parameters import BSLSessionParameters
from .db.catalog.catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from .db.query.queries import BSLQuery
from .db.query.query_packages import BSLTempTablesManager
from .db.document.documents import BSLDocuments, BSLDocumentObject
from .db.registers.information_registers import BSLInformationRegisters, BSLInformationRegisterType, BSLInformationRegisterRecordSet
from .db.document.document_types import BSLDocumentType
from .db.document.document_lines import BSLDocumentLines, BSLDocumentLinesType, BSLDocumentLine, BSLDocumentSectionType
from .db.catalog.catalog_types import BSLCatalogType
from .db.database_context import SQLiteDBContext, require_database_context
from .numeric.round_modes import BSLRoundModes, ROUND_MODES
from .collections.search_directions import BSLSearchDirections, SEARCH_DIRECTIONS
from .collections.sort_directions import BSLSortDirections, SORT_DIRECTIONS
from .formats.xml.xml_processing import XML_STRING_PROCESSING
from .types.type_descriptions import BSLTypeDescription
from .collections.value_trees import (BSLValueTree, BSLValueTreeColumnCollection, BSLValueTreeColumn,
                          BSLValueTreeRow, BSLValueTreeRowCollection)
from .collections.value_tables import (BSLValueTable, BSLValueTableColumnCollection,
                           BSLValueTableColumn, BSLValueTableRow,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .collections.value_lists import BSLValueList, BSLValueListItem
from .types.type_qualifiers import (
    ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)
from .types.errors import BSLError, BSLRuntimeError
from .types.error_info import (BSLErrorInfo, BSLErrorCategory, ERROR_CATEGORIES,
                         FORBIDDEN_RAISE_CATEGORIES, empty_error_info)
from .text.collation import string_key
from .syntax.parser import (parse, parse_expression, parse_fragment, validate_labels, validate_async,
                            prepare_control_flow, PreparedBlock)
from .syntax.lexer import KEYWORDS
from .syntax.preprocessor import validate_compilation_profile
from .collections.maps import BSLFixedMap, BSLMap
from .execution.codegen.native_targets import WINDOWS_8_3_27_2342, target_context, validate_native_target
from .collections.structures import BSLFixedStructure, BSLStructure, fill_property_values
from .types.values import (
    BSLArray, BSLFixedArray, BSLObject, BSLType, HostFunction, InterpreterCall, NULL, Reference as _Reference,
    boolean, divide, equal, number, require_number, to_string,
)


_COLLECTIONS = (BSLInformationRegisterRecordSet, BSLDocumentLine, BSLCatalogSection, BSLCatalogSectionRow, BSLXDTOList, BSLXDTOPropertyCollection, BSLXDTOPackage, BSLXDTOPackageCollection, BSLDOMNodeList, BSLDOMElementList, BSLDOMAttributeMap, BSLDocumentLines, BSLZipFileEntries, BSLBinaryDataBuffer, BSLArray, BSLFixedArray, BSLStructure, BSLFixedStructure,
                BSLMap, BSLFixedMap, BSLValueTable, BSLValueTableColumnCollection,
                BSLValueTableRow, BSLCollectionIndexes, BSLCollectionIndex, BSLValueList,
                BSLValueTreeColumnCollection, BSLValueTreeRow, BSLValueTreeRowCollection)
_TABLE_COLLECTIONS = (BSLInformationRegisterRecordSet, BSLDocumentLine, BSLCatalogSection, BSLCatalogSectionRow, BSLDocumentLines, BSLValueTable, BSLValueTableColumnCollection, BSLValueTableRow,
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


_CONTROL_FLOW_PLANS = object()


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
        metadata = (self.interpreter._routine_execution_metadata(routine)
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
                 compiled_ast_contract: str | None = None,
                 compiled_plain_routines: bool | None = None,
                 allow_extensions: bool | None = None):
        from .execution.execution_policy import current_backend, BACKENDS, current_ast_contract, AST_CONTRACTS
        if execution_backend is None:
            execution_backend = (family_owner.execution_backend if isinstance(family_owner, Interpreter)
                                 else current_backend())
        if type(execution_backend) is not str or execution_backend not in BACKENDS:
            raise ValueError("unsupported execution backend")
        if (isinstance(family_owner, Interpreter)
                and family_owner.execution_backend == 'compiled-strict'
                and execution_backend != 'compiled-strict'):
            raise ValueError('strict interpreter family cannot silently change backend')
        if compiled_ast_contract is None:
            compiled_ast_contract = (family_owner.compiled_ast_contract
                                     if isinstance(family_owner, Interpreter) else current_ast_contract())
        if type(compiled_ast_contract) is not str or compiled_ast_contract not in AST_CONTRACTS:
            raise ValueError('unsupported compiled AST contract')
        if (isinstance(family_owner, Interpreter)
                and family_owner.compiled_ast_contract != compiled_ast_contract):
            raise ValueError('interpreter family cannot silently change AST contract')
        self._compiled_ast_contract = compiled_ast_contract
        if compiled_plain_routines is None:
            compiled_plain_routines = (family_owner.compiled_plain_routines
                                       if isinstance(family_owner, Interpreter) else False)
        if type(compiled_plain_routines) is not bool:
            raise ValueError('compiled_plain_routines must be bool')
        self._compiled_plain_routines = compiled_plain_routines
        inherited_extensions = family_owner.allow_extensions if isinstance(family_owner, Interpreter) else False
        if allow_extensions is None:
            allow_extensions = inherited_extensions
        if type(allow_extensions) is not bool:
            raise TypeError('allow_extensions must be bool')
        if isinstance(family_owner, Interpreter) and allow_extensions != inherited_extensions:
            raise ValueError('interpreter family cannot change extension policy')
        self._allow_extensions = allow_extensions
        self._compiled_engine = None
        self._execution_backend = execution_backend
        self._hybrid_stats = {"compiled": 0, "fallback": 0, "compile_seconds": 0.0}
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
        self._scheduler = (Scheduler(self._native_target, execution_backend=self.execution_backend, compiled_ast_contract=self.compiled_ast_contract) if family_owner is None
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
            self._metadata._catalog_managers = self._catalogs
            self._metadata._document_managers = self._documents
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

    def visit(self, node: ast.Node) -> object:
        from .execution.direct.python_direct import _reject
        _reject("visit is a retired execution entrypoint; use execute or prepare")

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

    def _register_function(self, name, function, *aliases, returns_value=True):
        wrapper = HostFunction(name, function, returns_value=returns_value)
        for alias in (name, *aliases):
            self.functions[alias.casefold()] = wrapper

    def register_type(self, name: str, factory: Callable, *aliases: str) -> None:
        if not self.allow_extensions:
            raise ValueError('register_type requires allow_extensions=True')
        Interpreter._register_type(self, name, factory, *aliases)

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

    def _evaluate(self, argument: ast.Node, *, _evaluation=None) -> object:
        from .execution.direct.python_direct import _reject
        _reject("_evaluate is a retired execution entrypoint; use execute or prepare")

    def semantic_execute(self, node: ast.Execute, *, _evaluation=None) -> None:
        from .execution.direct.python_direct import _reject
        _reject("semantic_execute is a retired execution entrypoint; use execute or prepare")

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

    def _compiled(self):
        from .execution.direct.python_direct import _reject
        _reject("_compiled is a retired execution entrypoint; use execute or prepare")

    def _admit_compiled_node(self, node):
        from .execution.direct.python_direct import _reject
        _reject("_admit_compiled_node is a retired execution entrypoint; use execute or prepare")

    @property
    def compiled_plain_routines(self):
        return self._compiled_plain_routines

    @property
    def compiled_ast_contract(self):
        return self._compiled_ast_contract

    @property
    def compiled_backend_stats(self):
        return {} if self._compiled_engine is None else dict(self._compiled_engine.stats)

    @property
    def execution_backend(self):
        return self._execution_backend

    @property
    def execution_backend_stats(self):
        return dict(self._hybrid_stats)

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
        from .execution.direct.python_direct import execute
        return execute(self, program)

    def _execute_program_boundary(self, program, outermost):
        from .execution.direct.python_direct import _reject
        _reject("_execute_program_boundary is a retired execution entrypoint; use execute or prepare")

    def _execute_program(self, program: list[ast.Node], *, module_entry=False) -> object:
        # Also validate callers supplying an AST directly. No import or declaration
        # effects may precede label resolution.
        from .execution.direct.python_direct import _reject
        _reject("_execute_program is a retired execution entrypoint; use execute or prepare")

    def _planned_module_block(self, statements, *, enabled=False):
        from .execution.direct.python_direct import _reject
        _reject("_planned_module_block is a retired execution entrypoint; use execute or prepare")


    def _planned_routine_block(self, function):
        from .execution.direct.python_direct import _reject
        _reject("_planned_routine_block is a retired execution entrypoint; use execute or prepare")

    def block(self, statements: list[ast.Node]) -> object:
        from .execution.direct.python_direct import _reject
        _reject("block is a retired execution entrypoint; use execute or prepare")

    def compiled_before(self, node):
        """Strict node ABI; reference context subclasses preserve their original wrappers."""
        return None

    def compiled_after(self, node, value):
        """Context-owned post-node policy; failures belong to the parent boundary."""
        return value

    def compiled_exception(self, node, error):
        if isinstance(error, BSLError) or not isinstance(error,
                (ArithmeticError, ValueError, TypeError, IndexError, RecursionError)):
            return error
        if error is self._scheduler.active_context.host_failure:
            return error
        message = str(error) or type(error).__name__
        if isinstance(error, RecursionError) and self._eval_depth[0]:
            message = "Вычислить: превышен предел глубины выражения Yadinassi"
        if isinstance(error, ZeroDivisionError):
            message = "Деление на ноль"
        token = node.token
        return BSLRuntimeError(message, token.source, token.line, token.column,
                               source_line=token.source_line)

    def _visit(self, node: ast.Node) -> object:
        # Select this frame's path on entry. Runtime backend selection is fixed
        # at construction; private mutation during a yield is not a mode API.
        from .execution.direct.python_direct import _reject
        _reject("_visit is a retired execution entrypoint; use execute or prepare")


    def semantic_name(self, node: ast.Name) -> object:
        name = node.name.casefold()
        if self.locals is not None and name in self.locals:
            value = self.locals[name]
            return value.get() if isinstance(value, _Reference) else value
        if self._has_module_context and name in self.variables and (self.locals is None or name in self.module_names):
            return self.variables[name]
        if self._configuration_runtime is not None:
            module = self._configuration_runtime.resolve_module(name, self)
            if module is not None:
                return module
        if name in self.imports:
            raise TypeError(f"Имя модуля допустимо только при вызове его подпрограммы: {node.name}")
        if name in self.routines or name in self.server_routines or name in self._dual_routine_names:
            raise TypeError(f"Процедуру или функцию необходимо вызвать: {node.name}")
        if name in self.functions:
            return self.functions[name]
        if name in ('sessionparameters','параметрысеанса'):
            if self._configuration_runtime is None:
                raise ValueError('session parameters require an explicit configuration application')
            parameters=self._configuration_runtime.session_parameters
            parameters._authorize(self)
            return parameters
        if name in ("thisobject", "этотобъект"):
            if not self._has_module_context:
                raise ValueError("Объект модуля недоступен в подпрограмме без контекста")
            return self._self_module
        if name in ("регистрысведений", "informationregisters"):
            return self._information_registers
        if name in ("accumulationrecordtype", "виддвижениянакопления"):
            posting = self._documents.posting_runtime()
            if posting is None or not posting.accumulation:
                raise ValueError("accumulation posting profile required")
            from .db.registers.accumulation_posting_values import ACCUMULATION_RECORD_TYPES
            return ACCUMULATION_RECORD_TYPES
        if name in ("documentwritemode", "режимзаписидокумента"):
            if self._documents.posting_runtime() is None: raise ValueError("posting profile required")
            from .db.document.document_posting_values import DOCUMENT_WRITE_MODES
            return DOCUMENT_WRITE_MODES
        if name in ("enums", "перечисления"):
            if self._metadata._enumerations is None: raise ValueError("enumerations require an active configuration application")
            return self._metadata._enumerations
        if name in ("документы", "documents"):
            return self._documents
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
        if name in ('questiondialogmode', 'режимдиалогавопрос'):
            from .forms.form_dialogs import QUESTION_DIALOG_MODES
            return QUESTION_DIALOG_MODES
        if name in ('dialogreturncode', 'кодвозвратадиалога'):
            from .forms.form_dialogs import DIALOG_RETURN_CODES
            return DIALOG_RETURN_CODES
        if name in ("форматдатыjson", "jsondateformat"):
            return JSON_DATE_FORMATS
        if name in ("вариантзаписидатыjson", "jsondatewritingvariant"):
            return JSON_DATE_WRITING_VARIANTS
        if name in ("переносстрокjson", "jsonlinebreak"):
            return JSON_LINE_BREAKS
        if name in ("кодировкатекста", "textencoding"):
            return TEXT_ENCODINGS
        for ru, en, namespace in zip_archives.NAMESPACES:
            if name in (ru.casefold(), en.casefold()): return namespace
        if name in ("фабрикаxdto", "xdtofactory"): return self._xdto_factory
        if name in ("формаxml", "xmlform"): return XML_FORMS
        if name in ("типузлаdom", "domnodetype"): return DOM_NODE_TYPES
        if name in ("использованиеbyteordermark", "byteordermarkuse"): return BYTE_ORDER_MARK_USE
        if name in ("хешфункция", "hashfunction"): return HASH_FUNCTIONS
        if name in ("порядокбайтов", "byteorder"): return binary_streams.BYTE_ORDERS
        if name in ("режимоткрытияфайла", "fileopenmode"): return binary_streams.FILE_OPEN_MODES
        if name in ("доступкфайлу", "fileaccess"): return binary_streams.FILE_ACCESSES
        if name in ("позициявпотоке", "positioninstream"): return binary_streams.POSITIONS_IN_STREAM
        if name in ("типузлаxml", "xmlnodetype"): return XML_NODE_TYPES
        if name in ("пробельныесимволыxml", "xmlspace"): return XML_SPACES
        if name in ("типпроверкиxml", "xmlvalidationtype"): return XML_VALIDATION_TYPES
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





    def semantic_attribute(self, node: ast.Attribute) -> object:
        value = (yield from self.receiver(node.object))
        _dependency = _runtime_module('source_document_sections')
        SourceDocumentSection = _dependency.SourceDocumentSection
        SourceDocumentRow = _dependency.SourceDocumentRow
        if type(value) in (SourceDocumentSection, SourceDocumentRow):
            return value.property_read(self,node.name)
        _dependency = _runtime_module('source_document_runtime')
        is_document_reference = _dependency.is_source_reference
        document_member = _dependency.reference_member
        SourceDocumentObject = _dependency.SourceDocumentObject
        SourceDocumentSelection = _dependency.SourceDocumentSelection
        if is_document_reference(value):
            return document_member(self,value,node.name)
        if type(value) in (SourceDocumentObject, SourceDocumentSelection):
            return value.property_read(self,node.name)
        _dependency = _runtime_module('source_catalog_runtime')
        is_source_reference = _dependency.is_source_reference
        reference_member = _dependency.reference_member
        if is_source_reference(value):
            return reference_member(self,value,node.name)
        SourceManagers = _runtime_module('source_manager_modules').SourceManagers
        if type(value) is SourceManagers:
            return value.member(self, node.name)
        _dependency = _runtime_module('source_catalog_runtime')
        SourceCatalogObject = _dependency.SourceCatalogObject
        SourceCatalogSelection = _dependency.SourceCatalogSelection
        if type(value) in (SourceCatalogObject, SourceCatalogSelection):
            return value.property_read(self, node.name)
        SourceReferenceManager = _runtime_module('source_references').SourceReferenceManager
        if type(value) is SourceReferenceManager:
            return value.member(self, node.name)
        SourceConstantValueManager = _runtime_module('source_constant_managers').SourceConstantValueManager
        if type(value) is SourceConstantValueManager:
            return value.property_read(self, node.name)
        _dependency = _runtime_module('source_constants_runtime')
        SourceConstants = _dependency.SourceConstants
        SourceConstantSet = _dependency.SourceConstantSet
        if type(value) is SourceConstantSet:
            if node.name.casefold() in ('read', 'прочитать', 'write', 'записать'):
                return value.get_member(node.name)
            return value.read_property(self, node.name)
        if type(value) is SourceConstants:
            return value.member(self, node.name)
        if type(value) is BSLSessionParameters:
            return (yield from value.read(self,node.name))
        if type(value) is _Module:
            self._require_module_storage_context()
            return value.get_member(node.name)
        if not isinstance(value, BSLObject):
            raise TypeError("Значение не имеет методов или свойств")
        return value.get_member(node.name)

    def semantic_index(self, node: ast.Index) -> object:
        value = (yield from self._visit(node.object))
        SourceDocumentSection = _runtime_module('source_document_sections').SourceDocumentSection
        if type(value) is SourceDocumentSection:
            return value.get_index(self,(yield from self._visit(node.index)))
        SourceManagers = _runtime_module('source_manager_modules').SourceManagers
        if type(value) is SourceManagers:
            value.authorize(self)
            return value.member(self, (yield from self._visit(node.index)))
        SourceConstants = _runtime_module('source_constants_runtime').SourceConstants
        if type(value) is SourceConstants:
            return value.member(self, (yield from self._visit(node.index)))
        SourcePropertyDomain = _runtime_module('source_metadata_properties').SourcePropertyDomain
        if type(value) is SourcePropertyDomain:
            return value.get_index((yield from self._visit(node.index)))
        if type(value) is BSLSessionParameters:
            value._authorize(self)
            index=(yield from self._visit(node.index))
            return (yield from value.read(self,index))
        if (type(value) is BSLCommonModuleMetadataCollection
                or any(type(value) is cls for cls in (BSLChars, BSLCatalogs, BSLDocuments))
                or is_metadata_collection(value) or type(value) is BSLEnumerations or type(value) is BSLEnumManager):
            return value.get_index((yield from self._visit(node.index)))
        if not isinstance(value, _COLLECTIONS):
            raise TypeError("Индексирование поддерживается только для коллекций")
        index = (yield from self._visit(node.index))
        if isinstance(value, (BSLFixedMap, *_TABLE_COLLECTIONS)):
            return value.get_index(index)
        return value.get(index)


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

    def _routine_execution_metadata(self, routine):
        """Read frozen semantics, retaining original handles in authority registries."""
        if routine is None or self._execution_backend != 'compiled-strict':
            return routine
        engine = self._compiled()
        if not engine.OWNED_SNAPSHOT:
            return routine
        self._admit_compiled_node(routine)
        return engine.execution_view(routine)

    def _resolve_routine(self, name: str) -> ast.Routine | None:
        key = name.casefold()
        candidates = (self.routines.get(key), self.server_routines.get(key))
        metadata = tuple(self._routine_execution_metadata(node) for node in candidates)
        if key in self._dual_routine_names or any(
                node is not None and node.is_dual for node in metadata):
            # Detached servers store their server routines in .routines. Select
            # by declaration metadata, never by the dictionary's historical name.
            for original, node in zip(candidates, metadata):
                if node is not None and node.is_dual and node.execution_context == self.execution_context:
                    return original
            raise ValueError(f"Двухконтекстная подпрограмма недоступна на стороне {self.execution_context}: {name}")
        return candidates[0] or candidates[1]

    def call(self, node: ast.Call, *, require_value: bool, _evaluation=None) -> object:
        from .execution.direct.python_direct import _reject
        _reject("call is a retired execution entrypoint; use execute or prepare")

    def _convert_json(self, node, *, writing, _evaluation=None):
        evaluate = self._visit if _evaluation is None else _evaluation.evaluate
        required, maximum, module_index = (2, 6, 4) if writing else (1, 9, 5)
        if not required <= len(node.arguments) <= maximum:
            raise TypeError(f"JSON: ожидается от {required} до {maximum} аргументов")
        self.reject_host_omissions(node.arguments[:required])
        values = []
        for index, argument in enumerate(node.arguments):
            if isinstance(argument, ast.OmittedArgument):
                value = None
            elif index == module_index:
                receiver = self.import_receiver(argument)
                value = receiver if receiver is not None else (yield from evaluate(argument))
            else:
                value = yield from evaluate(argument)
            values.append(value)
        values += [None] * (maximum - len(values))
        name, module, additional = values[module_index - 1:module_index + 2]
        handler = None
        if name is not None or module is not None:
            if type(name) is not str or not name or module is None:
                raise TypeError("JSON: требуются имя функции и ее модуль")
            self._require_module_storage_context()
            module = self._callback_module(module)
            routine = module.routine(name)
            metadata = module.interpreter._routine_execution_metadata(routine)
            if not metadata.is_function or metadata.is_async or not metadata.module_context:
                raise TypeError("JSON: обработчик должен быть обычной контекстной функцией")
            if metadata.execution_context != self.execution_context:
                raise ValueError("JSON: обработчик должен выполняться в текущем контексте")
            # Validate arity before consuming a reader or invoking any handler.
            count = 4 if writing else 3
            required_parameters = max((i + 1 for i, p in enumerate(metadata.parameters)
                                       if p.default is None), default=0)
            if not required_parameters <= count <= len(metadata.parameters):
                raise TypeError(f"JSON: обработчик должен принимать {count} параметра")
            handler = routine, module.interpreter
        if writing:
            writer, value, settings = values[:3]
            if type(writer) is not BSLJSONWriter:
                raise TypeError("ЗаписатьJSON: ожидается ЗаписьJSON")
            if not writer._active:
                raise ValueError("JSON: приемник не открыт")
            operation = json_processing.encode_json_events(value, settings, has_converter=handler is not None)
        else:
            operation = json_processing.read_json_events(*values[:4], has_reviver=handler is not None,
                reviver_properties=values[7], maximum_nesting=values[8])
        response = None
        try:
            while True:
                try:
                    request = operation.send(response)
                except StopIteration as done:
                    result = done.value
                    break
                if handler is None:
                    raise TypeError("JSON: обработчик не задан")
                routine, owner = handler
                arguments = [ast.Literal(node.token, request.property),
                             ast.Literal(node.token, request.value),
                             ast.Literal(node.token, additional)]
                if writing:
                    # A real temporary property supplies ordinary by-reference
                    # semantics (including Val), without caller-frame injection.
                    cancel = BSLStructure("Cancel", False)
                    arguments.append(ast.Attribute(node.token, ast.Literal(node.token, cancel), "Cancel"))
                result = yield from self.call_routine(routine, arguments, owner, require_value=True)
                response = (result, cancel.get_member("Cancel")) if writing else result
        finally:
            operation.close()
        if writing:
            # Conversion finishes before this value changes the writer state.
            writer._write_encoded(result)
            return None
        return result

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
            metadata = owner._routine_execution_metadata(routine)
            if (metadata is None or not metadata.exported or metadata.is_function or metadata.is_async
                    or metadata.is_dual or not metadata.module_context or metadata.execution_context != 'client'
                    or len(metadata.parameters) != form_arity):
                raise ValueError('form completion requires an exported synchronous client procedure with the granted arity')
            return routine, owner
        module = self._callback_module(description.module)
        if module is None or not description.procedure_name:
            raise ValueError('ОписаниеОповещения: не заданы имя процедуры и модуль')
        routine = module.routine(description.procedure_name)
        if module.interpreter._routine_execution_metadata(routine).execution_context != 'client':
            raise ValueError('Обработчик оповещения должен выполняться на клиенте')
        return routine, module.interpreter

    def dispatch_callback(self, description, result, token, *, result_argument=True):
        """Shared value-based dispatch; host callers still own event admission."""
        if type(result_argument) is not bool:
            raise ValueError('explicit callback argument contract required')
        routine, owner = self.callback_target(description, form_arity=2 if result_argument else 1)
        if not result_argument and description._form_target is None:
            raise ValueError('one-argument completion requires a sealed form target')
        if description._form_target is not None:
            if not owner._form_session._busy or owner._form_session.interpreter is not self:
                raise ValueError('form callback requires its owning trusted event')
        values = ([result] if result_argument else []) + [description.additional_parameters]
        arguments = [ast.Literal(token, value) for value in values]
        return (yield from self.call_routine(routine, arguments, owner, require_value=False))

    def _run_callback(self, node, *, _evaluation=None):
        evaluate = self._visit if _evaluation is None else _evaluation.evaluate
        self._require_callback_context()
        if not 1 <= len(node.arguments) <= 2:
            raise TypeError("ВыполнитьОбработкуОповещения ожидает от 1 до 2 аргументов")
        self.reject_host_omissions(node.arguments[:1])
        description = yield from evaluate(node.arguments[0])
        result = None
        if len(node.arguments) == 2 and not isinstance(node.arguments[1], ast.OmittedArgument):
            result = yield from evaluate(node.arguments[1])
        return (yield from self.dispatch_callback(description, result, node.token))

    def known_receiver(self, node: ast.Node) -> object:
        """Read explicit receiver storage only, never factories or arbitrary fields."""
        node = self.ungroup(node)
        imported = self.import_receiver(node)
        if imported is not None:
            return imported
        if isinstance(node, ast.Name):
            return (self.semantic_name(node) if self.execution_backend == 'compiled-strict'
                    else self.visit_Name(node))
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
                                       BSLTextReader, BSLTextWriter, BSLTextDocument, BSLXMLReader, BSLXMLWriter,
                                       BSLDataReader, BSLDataWriter, BSLDataHashing, BSLHTTPRequest, BSLHTTPResponse, BSLHTTPConnection, BSLInternetProxy) else None

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
        from .configuration.source_extensions import SourceExtensions
        if type(receiver) is SourceExtensions and key in ('get', 'получить'):
            return frozenset({0, 1})
        if type(receiver) is BSLTextDocument and key in {"read", "прочитать", "write", "записать"}:
            return frozenset({1, 2})
        if type(receiver) is BSLInternetProxy and key in {"set", "установить"}: return frozenset({2, 3, 4, 5})
        if type(receiver) is BSLHTTPRequest and key in {"setbodyfromstring", "установитьтелоизстроки"}: return frozenset({1, 2})
        if type(receiver) is BSLHTTPResponse and key in {"getbodyasstring", "получитьтелокакстроку"}: return frozenset({0})
        if type(receiver) is BSLHTTPConnection:
            if key in {"get", "получить", "post", "отправитьдляобработки"}: return frozenset({1})
            if key in {"callhttpmethod", "вызватьhttpметод"}: return frozenset({2})
        if type(receiver) is BSLDataHashing and key in {"append", "добавить"}:
            return frozenset({1})
        if type(receiver) is BSLDataReader:
            if key in {"read", "прочитать", "readint16", "прочитатьцелое16", "readint32", "прочитатьцелое32", "readint64", "прочитатьцелое64"}: return frozenset({0})
            if key in {"readchars", "прочитатьсимволы", "readline", "прочитатьстроку", "split", "разделить"}: return frozenset({0, 1})
            if key in {"readto", "прочитатьдо", "skipto", "пропуститьдо", "copyto", "копироватьв"}: return frozenset({1})
        if type(receiver) is BSLDataWriter:
            if key in {"writeint16", "записатьцелое16", "writeint32", "записатьцелое32", "writeint64", "записатьцелое64", "writechars", "записатьсимволы"}: return frozenset({1})
            if key in {"writeline", "записатьстроку"}: return frozenset({1, 2})
        if type(receiver) is BSLXMLReader:
            if key in {"openfile", "открытьфайл", "openstream", "открытьпоток"}: return frozenset({1, 2, 3})
            if key in {"setstring", "установитьстроку"}: return frozenset({1, 2})
            if key in {"movetocontent", "перейтиксодержимому"}: return frozenset({0})
        if type(receiver) is BSLXMLWriter:
            if key in {"openfile", "открытьфайл", "openstream", "открытьпоток"}: return frozenset({1, 2})
            if key in {"setstring", "установитьстроку"}: return frozenset({0})
        if type(receiver) in (BSLTextReader, BSLTextWriter):
            if key in {"open", "открыть"}: return frozenset({1, 2, 3, 4})
            if key in {"read", "прочитать", "readline", "прочитатьстроку"}: return frozenset({0})
            if key in {"writeline", "записатьстроку"}: return frozenset({1})
        if type(receiver) is BSLJSONWriter:
            if key in {"openfile", "открытьфайл", "openstream", "открытьпоток"}:
                return frozenset({1, 2, 3})
            if key in {"setstring", "установитьстроку"}:
                return frozenset({0})
        if type(receiver) is BSLJSONReader and key in {"openfile", "открытьфайл", "openstream", "открытьпоток"}:
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
            imported = self.imports.get(name)
            if imported is not None or self._configuration_runtime is None:
                return imported
            return self._configuration_runtime.resolve_module(name, self)
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
                     owner: "Interpreter", *, require_value: bool, qualified: bool = False, _evaluation=None) -> object:
        from .execution.direct.python_direct import _reject
        _reject("call_routine is a retired execution entrypoint; use execute or prepare")





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
        server._client_routine_names = set(self.routines)
        server._dual_routine_names = self._dual_routine_names.copy()
        server._inherit_host_bindings(self)
        # Imports and the public module receiver remain unsupported server-side.
        # Side-local variables above never alias client storage.
        server._self_module.ready = False
        return server

    @staticmethod
    def reject_host_omissions(arguments: list[ast.Node]) -> None:
        if any(isinstance(argument, ast.OmittedArgument) for argument in arguments):
            raise TypeError("Пропуск аргументов встроенных функций, методов и конструкторов "
                            "пока не поддерживается")

    def _invocation_argument(self, node, *, _evaluation=None):
        return (yield from self.argument(node) if _evaluation is None else _evaluation.argument(node))

    def argument(self, node: ast.Node, *, _evaluation=None) -> object:
        evaluate = self._visit if _evaluation is None else _evaluation.evaluate
        receiver = self.receiver if _evaluation is None else _evaluation.receiver
        node = self.ungroup(node)
        if isinstance(node, ast.Name):
            name = node.name.casefold()
            if self.locals is not None and name in self.locals:
                scope = self.locals
            elif self._has_module_context and name in self.variables and (self.locals is None or name in self.module_names):
                scope = self.variables
            else:
                return (yield from evaluate(node))
            if isinstance(scope[name], _Reference):
                return scope[name]
            return _VariableReference(lambda: scope[name], lambda value: scope.__setitem__(name, value))
        if isinstance(node, ast.Attribute):
            owner = (yield from receiver(node.object))
            _dependency = _runtime_module('source_document_sections')
            SourceDocumentSection = _dependency.SourceDocumentSection
            SourceDocumentRow = _dependency.SourceDocumentRow
            if type(owner) in (SourceDocumentSection, SourceDocumentRow):
                owner.property_read(self,node.name)
                return _Reference(lambda:owner.property_read(self,node.name), lambda value:owner.property_write(self,node.name,value))
            _dependency = _runtime_module('source_document_runtime')
            is_document_reference = _dependency.is_source_reference
            document_member = _dependency.reference_member
            readonly_document = _dependency.readonly_reference
            SourceDocumentObject = _dependency.SourceDocumentObject
            SourceDocumentSelection = _dependency.SourceDocumentSelection
            if is_document_reference(owner):
                captured=document_member(self,owner,node.name)
                return _Reference(lambda:captured, lambda value:readonly_document(self,owner,node.name,value))
            if type(owner) in (SourceDocumentObject,SourceDocumentSelection):
                owner.property_read(self,node.name)
                return _Reference(lambda:owner.property_read(self,node.name), lambda value:owner.property_write(self,node.name,value))
            _dependency = _runtime_module('source_catalog_runtime')
            is_source_reference = _dependency.is_source_reference
            reference_member = _dependency.reference_member
            readonly_reference = _dependency.readonly_reference
            if is_source_reference(owner):
                captured=reference_member(self,owner,node.name)
                return _Reference(lambda:captured, lambda value:readonly_reference(self,owner,node.name,value))
            _dependency = _runtime_module('source_catalog_runtime')
            SourceCatalogObject = _dependency.SourceCatalogObject
            SourceCatalogSelection = _dependency.SourceCatalogSelection
            if type(owner) in (SourceCatalogObject, SourceCatalogSelection):
                owner.property_read(self, node.name)
                return _Reference(lambda: owner.property_read(self, node.name),
                                  lambda value: owner.property_write(self, node.name, value))
            SourceConstantValueManager = _runtime_module('source_constant_managers').SourceConstantValueManager
            if type(owner) is SourceConstantValueManager:
                owner.property_read(self, node.name)
                return _Reference(lambda: owner.property_read(self, node.name),
                                  lambda value: owner.property_write(self, node.name, value))
            if type(owner) is _Module:
                self._require_module_storage_context()
                owner.get_member(node.name)
                return _Reference(lambda: owner.get_member(node.name),
                                  lambda value: owner.set_member(node.name, value))
            if is_metadata_object(owner):
                # Reading a metadata lvalue through an ordinary BSL parameter
                # is allowed; mutation still reaches its read-only setter.
                owner.get_member(node.name)
                return _Reference(lambda: owner.get_member(node.name),
                                  lambda value: owner.set_member(node.name, value))
            if (type(owner) is BSLDocumentObject and node.name.casefold() in ('ref','ссылка')
                    and owner._manager._documents.posting_runtime() is not None):
                # Native14 observer passes the read-only document Ref to local
                # helpers. Preserve the actual property; assignment remains
                # rejected by the object's setter, never a writable temporary.
                owner.get_member(node.name)
                return _Reference(lambda:owner.get_member(node.name),
                                  lambda value:owner.set_member(node.name,value))
            if type(owner) is BSLValueListItem:
                # Native PR74: a field is live storage, not a copy-out temporary.
                # Resolve the item once; its existing setters retain conversion,
                # identity and string-cache behavior, including after deletion.
                owner.reference_get_member(node.name)
                return _Reference(lambda: owner.reference_get_member(node.name),
                                  lambda value: owner.reference_set_member(node.name, value))
            BSLQueryResultSelection = _runtime_module('queries').BSLQueryResultSelection
            BSLAccumulationRow = _runtime_module('accumulation_posting_values').BSLAccumulationRow
            key = node.name.casefold()
            observed_readonly = (
                type(owner) is BSLQueryResultSelection and any(
                    column.name.casefold() == key for column in owner._result._columns)
                or type(owner) is BSLNumberQualifiers and key in
                    ('digits', 'разрядность', 'fractiondigits', 'разрядностьдробнойчасти')
                or type(owner) is BSLAccumulationRow and key in ('linenumber', 'номерстроки'))
            if observed_readonly:
                # Native accumulation16 calls scalar helpers with these actuals.
                # Capture once; this closed reader admission grants no mutable
                # query cursor/qualifier/occurrence property reference.
                captured = owner.get_member(node.name)
                def readonly(value):
                    raise ValueError('Observed read-only property argument cannot be assigned')
                return _Reference(lambda: captured, readonly)
            if not isinstance(owner, (BSLStructure, BSLFixedStructure, BSLValueTableRow, BSLValueTableColumn, BSLValueTreeRow, BSLValueTreeColumn)):
                raise TypeError("Передача свойства по ссылке поддерживается только для структуры, строки или колонки таблицы")
            # Bind the receiver once and validate existence before entering the
            # callee. Fixed properties remain readable; their setter rejects an
            # actual assignment inside the callee, not the argument itself.
            owner.get_member(node.name)
            return _Reference(lambda: owner.get_member(node.name),
                              lambda value: owner.set_member(node.name, value))
        if isinstance(node, ast.Index):
            owner = (yield from evaluate(node.object))
            if is_metadata_collection(owner) or type(owner) in (BSLCatalogs, BSLDocuments, BSLEnumerations, BSLEnumManager):
                index = (yield from evaluate(node.index))
                owner.get_index(index)
                return _Reference(lambda: owner.get_index(index),
                                  lambda value: owner.set_index(index, value))
            if not isinstance(owner, _COLLECTIONS):
                raise TypeError("Индексирование поддерживается только для коллекций")
            index = (yield from evaluate(node.index))
            getter = owner.get_index if isinstance(owner, (BSLFixedMap, *_TABLE_COLLECTIONS)) else owner.get
            # Native PR47: bad array indices / absent structure properties fail
            # before entry; a mutable map's missing key is a valid output slot.
            getter(index)
            setter = owner.set_index if isinstance(owner, _TABLE_COLLECTIONS) else owner.set
            return _Reference(lambda: getter(index), lambda value: setter(index, value))
        # Literals and computed expressions have no caller storage to rebind.
        return (yield from evaluate(node))

    @staticmethod
    def ungroup(node: ast.Node) -> ast.Node:
        while isinstance(node, ast.Group):
            node = node.expression
        return node

    def semantic_new(self, node: ast.New, *, _evaluation=None) -> object:
        evaluate = self._visit if _evaluation is None else _evaluation.evaluate
        receiver = self.receiver if _evaluation is None else _evaluation.receiver
        factory = self.types.get(node.name.casefold())
        if factory is not None and factory.function is callback_description_marker:
            self._require_callback_context()
            if len(node.arguments) > 5:
                raise TypeError("ОписаниеОповещения ожидает от 0 до 5 аргументов")
            values = []
            for index, argument in enumerate(node.arguments):
                if isinstance(argument, ast.OmittedArgument):
                    value = None
                elif index in (1, 4):
                    value = yield from receiver(argument)
                else:
                    value = yield from evaluate(argument)
                values.append(value)
            return self._new_callback(values)
        if factory is not None and (factory.function is BSLTypeDescription
                                    or factory.function is BSLXMLReaderSettings
                                    or factory.function is BSLXMLWriterSettings
                                    or factory.function is BSLJSONWriterSettings
                                    or factory.function is BSLValueStorage
                                    or factory.function is BSLTextReader
                                    or factory.function is BSLTextWriter
                                    or factory.function is BSLDataReader
                                    or factory.function is BSLDataWriter
                                    or factory.function is BSLOpenSSLSecureConnection
                                    or factory.function is BSLFileCertificationAuthorityCertificates
                                    or factory.function is BSLHTTPConnection
                                    or factory.function is BSLHTTPRequest):
            if (factory.function is BSLValueStorage
                    or factory.function is BSLTextReader or factory.function is BSLTextWriter
                    or factory.function is BSLDataReader or factory.function is BSLDataWriter
                    or factory.function is BSLFileCertificationAuthorityCertificates
                    or factory.function is BSLHTTPConnection or factory.function is BSLHTTPRequest):
                self.reject_host_omissions(node.arguments[:1])
            # The observed descriptor overloads use positional qualifier holes.
            # Other host constructors retain their explicit omission rejection.
            values = []
            for argument in node.arguments:
                values.append(None if isinstance(argument, ast.OmittedArgument) else (yield from evaluate(argument)))
            if factory.function is BSLTypeDescription:
                return self._new_type_description(*values)
            return factory(*values)
        self.reject_host_omissions(node.arguments)
        if factory is None:
            raise ValueError(f"Тип не определен: {node.name}")
        values = []
        for argument in node.arguments:
            values.append((yield from evaluate(argument)))
        return factory(*values)

    def semantic_dynamic_new(self, node: ast.DynamicNew, *, _evaluation=None) -> object:
        evaluate = self._visit if _evaluation is None else _evaluation.evaluate
        # Expressions follow the same left-to-right evaluation as host calls.
        # EDT root_New explicitly says to ignore a non-array second value.
        value_type = (yield from evaluate(node.type_expression))
        parameters = (yield from evaluate(node.parameters)) if node.parameters is not None else None
        if (type(value_type) is BSLCatalogType or type(value_type) is BSLDocumentType or (type(value_type) is BSLDocumentLinesType or type(value_type) is BSLDocumentSectionType) or type(value_type) is BSLInformationRegisterType):
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
        if factory.function is callback_description_marker:
            return self._new_callback(arguments)
        if factory.function is BSLTypeDescription:
            return self._new_type_description(*arguments)
        return factory(*arguments)

    def semantic_assign(self, node: ast.Assign) -> None:
        if isinstance(node.target, ast.Name):
            self.set_variable(node.target.name, (yield from self._visit(node.value)))
        else:
            value = (yield from self.receiver(node.target.object))
            _dependency = _runtime_module('source_document_sections')
            SourceDocumentSection = _dependency.SourceDocumentSection
            SourceDocumentRow = _dependency.SourceDocumentRow
            if type(value) in (SourceDocumentSection, SourceDocumentRow):
                if not isinstance(node.target,ast.Attribute):
                    raise ValueError("source document section replacement unsupported")
                value.property_write(self,node.target.name,(yield from self._visit(node.value)))
                return
            _dependency = _runtime_module('source_document_runtime')
            is_document_reference = _dependency.is_source_reference
            SourceDocumentObject = _dependency.SourceDocumentObject
            if is_document_reference(value):
                raise ValueError('source document reference fields are readonly; use GetObject().Write()')
            if type(value) is SourceDocumentObject:
                if not isinstance(node.target,ast.Attribute):
                    raise ValueError('source document object indexing unsupported')
                value.property_write(self,node.target.name,(yield from self._visit(node.value)))
                return
            _dependency = _runtime_module('source_catalog_runtime')
            is_source_reference = _dependency.is_source_reference
            readonly_reference = _dependency.readonly_reference
            if is_source_reference(value):
                raise ValueError('source reference fields are readonly; use GetObject().Write()')
            SourceCatalogObject = _runtime_module('source_catalog_runtime').SourceCatalogObject
            if type(value) is SourceCatalogObject:
                if not isinstance(node.target, ast.Attribute):
                    raise ValueError("source catalog object indexing unsupported")
                value.property_write(self, node.target.name, (yield from self._visit(node.value)))
                return
            SourceConstantValueManager = _runtime_module('source_constant_managers').SourceConstantValueManager
            if type(value) is SourceConstantValueManager:
                if not isinstance(node.target, ast.Attribute):
                    raise ValueError('unsupported value manager indexing')
                value.property_write(self, node.target.name, (yield from self._visit(node.value)))
                return
            SourceConstantSet = _runtime_module('source_constants_runtime').SourceConstantSet
            if type(value) is SourceConstantSet:
                if not isinstance(node.target, ast.Attribute):
                    raise ValueError('constant set indexing unsupported')
                value.write_property(self, node.target.name, (yield from self._visit(node.value)))
                return
            if type(value) is BSLSessionParameters:
                value._authorize(self)
                name=node.target.name if isinstance(node.target,ast.Attribute) else (yield from self._visit(node.target.index))
                value.write(self,name,(yield from self._visit(node.value)))
                return
            if isinstance(node.target, ast.Attribute):
                if type(value) is _Module:
                    self._require_module_storage_context()
                if type(value) is not _Module and not isinstance(value, BSLObject):
                    raise TypeError("Значение не имеет методов или свойств")
                value.set_member(node.target.name, (yield from self._visit(node.value)))
            else:
                if is_metadata_collection(value) or any(type(value) is cls for cls in (BSLChars, BSLCatalogs, BSLDocuments, BSLEnumerations, BSLEnumManager)):
                    value.set_index((yield from self._visit(node.target.index)), (yield from self._visit(node.value)))
                    return
                if not isinstance(value, _COLLECTIONS):
                    raise TypeError("Индексирование поддерживается только для коллекций")
                index = (yield from self._visit(node.target.index))
                setter = value.set_index if isinstance(value, _TABLE_COLLECTIONS) else value.set
                setter(index, (yield from self._visit(node.value)))

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
            child = Interpreter(self.output, execution_backend=self.execution_backend, encoding=self.encoding,
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
            if self.execution_backend == 'python-direct':
                from .execution.direct.python_direct_imports import loading_child
                with loading_child(self,child,path):
                    child.execute(text,str(path))
                    module=child._self_module
                    self._module_cache[path]=module
            else:
                child.execute(text, str(path))
                module = child._self_module
                self._module_cache[path] = module
        return module





    def semantic_raise(self, node: ast.Raise, *, _evaluation=None) -> None:
        evaluate = self._visit if _evaluation is None else _evaluation.evaluate
        if node.value is None:
            if not self._handled_errors:
                # Protect callers constructing ASTs directly, as well as the parser.
                raise ValueError("Нет активного исключения для повторного вызова")
            error = self._handled_errors[-1]
            if error is None:
                raise ValueError("Повторный вызов исключения после вложенного обработчика "
                                 "пока не поддерживается; используйте явное сообщение")
            raise error
        message = to_string((yield from evaluate(node.value)))
        arguments = node.optional_arguments or []
        if len(arguments) > 4:
            raise TypeError("ВызватьИсключение ожидает не более 5 аргументов")
        values = []
        for argument in arguments:
            values.append(None if isinstance(argument, ast.OmittedArgument) else (yield from evaluate(argument)))
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







    def compiled_iterable(self, collection):
        from .db.document.source_document_sections import SourceDocumentSection
        if type(collection) is SourceDocumentSection:
            return collection.iterate(self)
        from .db.metadata.source_constants_runtime import SourceConstants
        if type(collection) is SourceConstants:
            members = collection.members(self)
            collection = BSLArray()
            collection.items = list(members)
        if (not isinstance(collection, _COLLECTIONS)
                and type(collection) is not BSLRoundModes
                and type(collection) is not BSLSearchDirections
                and type(collection) is not BSLSortDirections
                and not is_metadata_collection(collection)
                and type(collection) is not BSLEnumManager):
            raise TypeError("Для Каждого ожидает массив, структуру, соответствие или поддержанное пространство системного перечисления")
        return collection





    # Independent dispatch names share implementations, not forwarding frames.
    # Legacy hooks are visit_*; compiled adapters resolve semantic_* directly.
    visit_Name = semantic_name
    visit_Attribute = semantic_attribute
    visit_Index = semantic_index
    visit_Assign = semantic_assign
    visit_New = semantic_new
    visit_DynamicNew = semantic_dynamic_new
    visit_Import = semantic_import
    visit_Raise = semantic_raise
    visit_Execute = semantic_execute


# Definition-time direct admission guard; no visitor evaluator is retained.
_DIRECT_VISITOR_ABI = Interpreter._visit


def unary_value(operator, value):
    if operator == "NOT":
        return not boolean(value)
    value = require_number(value)
    return value if operator == "+" else value.copy_negate()

def binary_values(operator, left, right):
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

# Capture built-in policy hooks at definition time, before any embedding code can
# patch the class and before the optional compiler is lazily imported.
_COMPILED_BASE_ABI_NAMES = ('compiled_before', 'compiled_after', 'compiled_exception',
                            'semantic_name', 'semantic_assign', 'set_variable')
_COMPILED_BASE_ABI = tuple(getattr(Interpreter, name) for name in _COMPILED_BASE_ABI_NAMES)
# Definition-time identities: a lazy direct-import adapter must not bless hooks
# installed before its first import.
_DIRECT_IMPORT_LOADER_ABI = tuple((name,vars(Interpreter)[name]) for name in
    ('semantic_import','_load_module','_check_import_binding','_inherit_host_bindings'))
_DIRECT_IMPORT_RECEIVER_ABI = tuple((cls,tuple(vars(cls).items()),cls.__mro__)
                                   for cls in (_Module,_Namespace))


@lru_cache(maxsize=1)
def _source_call_dispatch_types():
    """Lazy immutable identities only; no caller, receiver or authority is cached.

    Kept after argument evaluation at the call site to preserve import timing and
    avoid runtime/configuration-source circular imports during module loading.
    Failed imports do not populate functools.lru_cache.
    """
    from .db.catalog.source_catalog_runtime import SourceCatalogCall
    from .db.document.source_document_sections import SourceDocumentSectionCall
    from .db.document.source_document_runtime import SourceDocumentCall
    from .db.metadata.source_references import SourceReferenceCall
    from .db.metadata.source_constants_runtime import ConstantCall, ConstantSetCall
    from .db.query.source_constant_queries import SourceQueryCall
    from .configuration.source_extensions import ExtensionCall
    from .application.source_host_session import SourceSessionCall
    from .db.source_transactions import SourceTransactionCall
    from .db.metadata.source_constant_managers import ValueManagerCall, write_values
    return (SourceCatalogCall, SourceDocumentSectionCall, SourceDocumentCall,
            SourceReferenceCall, ConstantCall, ConstantSetCall, SourceQueryCall,
            ExtensionCall, SourceSessionCall, SourceTransactionCall,
            ValueManagerCall, write_values)

_PLAIN_BLOCK_ABI = Interpreter.block

_PLAIN_SCOPE_ABI = (Interpreter.locals, Interpreter._context_stack, Interpreter._module_context_stack)

from .application.async_runtime import ExecutionContext as _PlainExecutionContext
_PLAIN_STORAGE_ABI = tuple((cls, vars(cls).get('__dict__'), cls.__mro__)
                           for cls in (Interpreter, Scheduler, _PlainExecutionContext))

# Capture canonical diagnostic identity before trusted host class overrides.
_DIRECT_ERROR_DESCRIPTION_ABI = Interpreter._error_description
_DIRECT_ERROR_INFO_ABI = Interpreter._error_info
_DIRECT_QUERY_FACTORY_ABI = Interpreter._new_query
_DIRECT_TRANSACTION_ABI = (Interpreter._begin_transaction, Interpreter._commit_transaction, Interpreter._rollback_transaction, Interpreter._transaction_active)

# Definition-time Message identity for the finite direct configuration command lane.
_DIRECT_CONFIGURATION_MESSAGE_ABI = Interpreter._message

# Definition-time execute lease; instance/class rebinding cannot replace it.
_DIRECT_EXECUTION_SCOPE_ABI = Interpreter._direct_execution_scope

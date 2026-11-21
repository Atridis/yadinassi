"""Finite canonical constructors for direct JSON, regex and HTTP/file protocols."""
from yadinassi.formats.xml.dom_io import BSLDOMBuilder, BSLDOMWriter
from yadinassi.formats.xml.dom_nodes import BSLDOMDocument
from yadinassi.formats.xml.dom_xpath import BSLDOMNamespaceResolver
from yadinassi.formats.xml.xml_io import BSLXMLReader, BSLXMLReaderSettings
from yadinassi.formats.xml.xml_writer import BSLXMLWriter, BSLXMLWriterSettings
from yadinassi.streams.file_io import (
    BSLFile, BSLBinaryData, BSLTextReader, BSLTextWriter, binary_from_string, find_files, temp_file_name,
    create_directory, copy_file, move_file, delete_files,
)
from yadinassi.streams.text_documents import BSLTextDocument
from .source import python_direct_source_resources as text_resources
from yadinassi.formats.storage.value_storage import BSLValueStorage
from yadinassi.streams.data_compression import BSLDeflation
from yadinassi.http.http_client import BSLHTTPConnection, BSLHTTPRequest
from yadinassi.streams.binary_streams import BSLBinaryDataBuffer, BSLMemoryStream, BSLFileStream
from yadinassi.streams.data_io import BSLDataReader, BSLDataWriter
from yadinassi.streams.data_hashing import BSLDataHashing
from yadinassi.formats.json.json_dates import BSLJSONSerializerSettings
from yadinassi.formats.json.json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings, read_json, write_json
from yadinassi.types.values import HostFunction, BSLFixedArray, _DIRECT_TO_STRING_ABI
from yadinassi.db.query.query_packages import BSLTempTablesManager, TEMP_TABLE_MANAGER_NAMES
from yadinassi.collections.structures import BSLFixedStructure
from yadinassi.collections.maps import BSLFixedMap
from . import python_direct_fixed as fixed
from .python_direct_plain_array import PlainArray
from .python_direct_plain_map import PlainMap
from yadinassi.collections.plain_value_list import PlainValueList, PlainValueListItem
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.collections.value_lists import BSLValueList
from yadinassi.types.type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers
from yadinassi.formats.regex import regex_functions
from yadinassi.text import strings
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation, _SCALAR_TYPE_IDS

from yadinassi.execution.codegen.experimental_naked_collections import _DIRECT_MAP_ENTRY_TYPE as _CanonicalMapEntry, _TypedMap as _DirectMapType
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure as _DirectStructureType
from yadinassi.types.type_values import _DIRECT_TYPE_OF_ABI
from yadinassi.formats.storage.serialization import _DIRECT_VALUE_TO_STRING_ABI, _direct_value_to_string_internal
from yadinassi.runtime import _eval_marker
from . import python_direct_user_messages as user_messages
from yadinassi.application.callbacks import callback_description_marker
from yadinassi.application.direct_callbacks import CallbackDescription as _CallbackDescription, construct as _new_callback, read as _callback_read

_FILE_EFFECTS = frozenset(map(id, (
    find_files, temp_file_name, create_directory, copy_file, move_file, delete_files,
)))

_FILE_CONSTRUCTORS = (BSLBinaryData, BSLFileStream)
_FILE_OR_BORROWED_STREAM_CONSTRUCTORS = (BSLTextReader, BSLTextWriter, BSLDataReader, BSLDataWriter)
_STREAM_CONSTRUCTORS = (*_FILE_CONSTRUCTORS, *_FILE_OR_BORROWED_STREAM_CONSTRUCTORS, BSLMemoryStream)
_STREAM_CONSTRUCTOR_COUNTS = {
    BSLTextReader: (0,5), BSLTextWriter: (0,5), BSLMemoryStream: (0,1),
    BSLFileStream: (2,4), BSLDataReader: (1,5), BSLDataWriter: (1,7),
}


_REGEX_IMPLEMENTATIONS=tuple(regex_functions.FUNCTIONS)
_REGEX_IDENTITIES=frozenset(map(id,_REGEX_IMPLEMENTATIONS))

CONSTRUCTORS = {
    alias: factory for aliases,factory in (
        (user_messages.NAMES,user_messages._FACTORY),
        (('callbackdescription','описаниеоповещения'),callback_description_marker),
        (('fixedmap','фиксированноесоответствие'),BSLFixedMap),
        (('fixedarray','фиксированныймассив'),BSLFixedArray),
        (('fixedstructure','фиксированнаяструктура'),BSLFixedStructure),
        (('valuelist','списокзначений'),BSLValueList),
        (('valuelistitem','элементсписказначений'),None),
        (('valuetable','таблицазначений'),BSLValueTable),
        (('valuetablerow','строкатаблицызначений'),None),
        (('valuetablecolumn','колонкатаблицызначений'),None),
        (('valuetablecolumncollection','коллекцияколоноктаблицызначений'),None),
        (('typedescription','описаниетипов'),BSLTypeDescription),
        (TEMP_TABLE_MANAGER_NAMES,BSLTempTablesManager),
        (('numberqualifiers','квалификаторычисла'),BSLNumberQualifiers),
        (('stringqualifiers','квалификаторыстроки'),BSLStringQualifiers),
        (('datequalifiers','квалификаторыдаты'),BSLDateQualifiers),
        (('binarydataqualifiers','квалификаторыдвоичныхданных'),BSLBinaryDataQualifiers),
        (('textdocument','текстовыйдокумент'),BSLTextDocument),
        (('file','файл'),BSLFile),
        (('binarydata','двоичныеданные'),BSLBinaryData),
        (('binarydatabuffer','буфердвоичныхданных'),BSLBinaryDataBuffer),
        (('httpconnection','httpсоединение'),BSLHTTPConnection),
        (('httprequest','httpзапрос'),BSLHTTPRequest),
        (('dombuilder','построительdom'),BSLDOMBuilder),
        (('domwriter','записьdom'),BSLDOMWriter),
        (('domdocument','документdom'),BSLDOMDocument),
        (('domnamespaceresolver','разыменователь пространств имен dom xpath'),BSLDOMNamespaceResolver),
        (('xmlreader','чтениеxml'),BSLXMLReader),
        (('xmlwriter','записьxml'),BSLXMLWriter),
        (('xmlreadersettings','параметрычтенияxml'),BSLXMLReaderSettings),
        (('xmlwritersettings','параметрызаписиxml'),BSLXMLWriterSettings),
        (('jsonreader','чтениеjson'),BSLJSONReader),
        (('jsonwriter','записьjson'),BSLJSONWriter),
        (('jsonwritersettings','параметрызаписиjson'),BSLJSONWriterSettings),
        (('collectionindexes','индексыколлекции'),None),
        (('collectionindex','индексколлекции'),None),
        (('searchdirection','направлениепоиска'),None),
        (('resultofsearchbyregularexpression','результатпоискапорегулярномувыражению'),None),
        (('resultofsearchbyregularexpressiongroup','группарезультатапоискапорегулярномувыражению'),None),
    ) for alias in aliases
}

# Source/NoContext/Forms consume CONSTRUCTORS plus their own declarations.
# They do not inherit ordinary stream, compression or unrestricted Get contracts.
ORDINARY_CONSTRUCTORS = {
    **CONSTRUCTORS,
    'textreader': BSLTextReader, 'чтениетекста': BSLTextReader,
    'textwriter': BSLTextWriter, 'записьтекста': BSLTextWriter,
    'memorystream': BSLMemoryStream, 'потоквпамяти': BSLMemoryStream,
    'filestream': BSLFileStream, 'файловыйпоток': BSLFileStream,
    'datareader': BSLDataReader, 'чтениеданных': BSLDataReader,
    'datawriter': BSLDataWriter, 'записьданных': BSLDataWriter,
    'readdataresult': None, 'результатчтенияданных': None,
    'datahashing': BSLDataHashing, 'хешированиеданных': BSLDataHashing,
    'hashfunction': None, 'хешфункция': None,
    'jsonserializersettings': BSLJSONSerializerSettings,
    'настройкисериализацииjson': BSLJSONSerializerSettings,
    'valuestorage': BSLValueStorage, 'хранилищезначения': BSLValueStorage,
    'deflation': BSLDeflation, 'сжатиеданных': BSLDeflation,
}
OPTIONAL_STREAM_CONSTRUCTORS = frozenset(
    name for name,value in ORDINARY_CONSTRUCTORS.items() if value in _STREAM_CONSTRUCTOR_COUNTS)


def _string_callable(context,function,*,name=None,require_value=False,allow_references=False,**unused):
    if type(function) is not HostFunction or function.function is not _DIRECT_TO_STRING_ABI:return None
    if context._verify_context:context._check()
    context._validate_host_function(function,require_value,allow_references)
    key=name if name is not None else function.name.casefold()
    def stringify(value):
        context._before('call' if name is not None else 'call_value',key)
        foreign_presentation=False
        try:
            if function.function is not _DIRECT_TO_STRING_ABI:
                raise BoundaryViolation('String implementation changed during argument evaluation')
            kind=type(value)
            if kind is fixed.PlainFixedMap:return 'ФиксированноеСоответствие'
            if kind is _CallbackDescription:return 'ОписаниеОповещения'
            if kind is list:return 'Массив'
            if kind is _DirectStructureType:return 'Структура'
            if kind is _DirectMapType:return 'Соответствие'
            if kind is _CanonicalMapEntry:return 'КлючИЗначение'
            # Preserve the existing canonical service for all other values.
            # Non-scalar presentation may invoke an embedding value's __str__.
            foreign_presentation=id(kind) not in _SCALAR_TYPE_IDS
            if foreign_presentation and not context._verify_context:context._check_effect()
            return _DIRECT_TO_STRING_ABI(value)
        except PermissionError as error:raise BoundaryViolation(str(error)) from error
        finally:
            if foreign_presentation or context._verify_context:context._check_effect()
    if allow_references:stringify.requires_reference=lambda index:index in function.reference_parameters
    return stringify


def builtin_binding(value, entry):
    return (entry is not None and type(value) is HostFunction and value is entry[0]
            and value.function is entry[1] and value.name is entry[2]
            and value.reference_parameters is entry[3] and value.returns_value is entry[4])


class ServicesBoundary:
    def _check_extension_binding(self, key):
        if not getattr(self,'_restrict_python_extensions',False):
            return
        vm=self.vm
        if self._services is not vm.functions:
            raise BoundaryViolation('host registry changed during plain BSL execution')
        if key.startswith('new:'):
            key=key[4:]
            registry,snapshot=vm.types,vm._builtin_types
        else:
            registry,snapshot=vm.functions,vm._builtin_functions
        if key in registry and not builtin_binding(registry[key],snapshot.get(key)):
            raise BoundaryViolation('custom host registry entries require allow_extensions=True')

    def _before(self,operation,name):
        if operation=='call':self._check_extension_binding(name)
        return super()._before(operation,name)

    def get_member(self,value,name):
        if type(value) is user_messages.BSLUserMessage:return user_messages.get(self,value,name)
        if type(value) is fixed.PlainFixedMap:return fixed.get(self,value,name)
        if type(value) is _CallbackDescription:
            if self._verify_context:self._check()
            return _callback_read(value,name)
        if value is None:
            if self._verify_context:self._check()
            raise ValueError('Значение не является значением объектного типа')
        from .python_direct_error_info import owns, read
        if owns(value):return read(self,value,name)
        if type(value) is BSLTextDocument:return text_resources.get(self,value,name)
        return super().get_member(value,name)

    def resolve_member(self,value,name):
        if type(value) is user_messages.BSLUserMessage:return user_messages.resolve(self,value,name)
        if type(value) is fixed.PlainFixedMap:return fixed.resolve(self,value,name)
        if value is None:
            if self._verify_context:self._check()
            raise ValueError('Значение не является значением объектного типа')
        from .python_direct_error_info import owns,resolve_query
        if owns(value):return resolve_query(self,value,name)
        if type(value) is BSLTextDocument:return text_resources.resolve(self,value,name)
        return super().resolve_member(value,name)

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if omitted and type(value) is PlainValueList:
            from .python_direct_import_collections import bind_optional_list
            if not self._verify_context:return bind_optional_list(value,name.casefold(),omitted)
            self._check_effect()
            function=bind_optional_list(value,name.casefold(),omitted)
            def invoke(*arguments):
                self._check_effect()
                try:return function(*arguments)
                finally:self._check_effect()
            return invoke
        if type(value) is BSLValueStorage:
            from yadinassi.runtime import Interpreter
            if type(self.vm) is Interpreter:
                from .python_direct_value_storage import resolve_get
                return resolve_get(self,value,name,omitted=omitted)
        if type(value) is user_messages.BSLUserMessage:return user_messages.resolve(self,value,name,require_value=require_value,omitted=omitted)
        if type(value) is fixed.PlainFixedMap:
            if omitted:raise TypeError('FixedMap method argument omission is unsupported')
            return fixed.resolve(self,value,name,require_value=require_value)
        if value is None:
            if self._verify_context:self._check()
            raise ValueError('Значение не является значением объектного типа')
        from .python_direct_error_info import owns,resolve_query
        if owns(value):return resolve_query(self,value,name,require_value=require_value,omitted=omitted)
        if type(value) is not BSLTextDocument:
            return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        text_resources.check(self,value)
        if omitted and (name.casefold() not in ('read','прочитать','write','записать')
                or any(index not in (1,2) for index in omitted)):
            raise TypeError('TextDocument method required argument omitted')
        bound=text_resources.resolve(self,value,name,require_value=require_value)
        if not omitted:return bound
        def invoke(*arguments):
            values=list(arguments)
            for index in omitted:values[index]=None
            return bound(*values)
        return invoke

    def resolve_set_member(self, value, name):
        if type(value) is user_messages.BSLUserMessage:return user_messages.setter(self,value,name)
        if type(value) is fixed.PlainFixedMap:
            if self._verify_context:self._check()
            def readonly_fixed_map(new_value):
                if self._verify_context:self._check()
                raise ValueError('Фиксированная коллекция недоступна для записи')
            return readonly_fixed_map
        if type(value) is BSLTextDocument:
            text_resources.check(self,value)
            def unsupported(new_value):
                text_resources.check(self,value)
                raise ValueError('TextDocument property is not integrated: '+name)
            return unsupported
        # Iterator pairs are direct scalar containers, not database receivers.
        # Resolve before the RHS, but report readonly only after evaluating it.
        # Exact identity admits no protocol, subclass, or payload authority.
        from .python_direct_error_info import owns
        if type(value) is not _CanonicalMapEntry and not owns(value):
            return super().resolve_set_member(value, name)
        if self._verify_context:self._check()
        def readonly(new_value):
            if self._verify_context:self._check()
            raise ValueError('Свойство недоступно для записи: '+name)
        return readonly

    def resolve_callable(self,value,*,require_value=False,allow_references=False,_extension_value=False):
        if (type(value) is user_messages.HostFunction and type(value.function) is user_messages.MethodType
                and type(value.function.__self__) is user_messages.BSLUserMessage):
            return user_messages.captured(self,value,require_value=require_value,allow_references=allow_references)
        bound=_string_callable(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        if type(value) is HostFunction and value.function is _DIRECT_VALUE_TO_STRING_ABI:
            if self._verify_context:self._check()
            self._validate_host_function(value,require_value,allow_references)
            def serialize_pair(argument):
                self._before('call_value',value.name.casefold())
                try:
                    if value.function is not _DIRECT_VALUE_TO_STRING_ABI:
                        raise BoundaryViolation('serialization implementation changed during argument evaluation')
                    # Only native representations with a finite captured codec.
                    if type(argument) is _CanonicalMapEntry or type(argument) is PlainValueList:
                        return _direct_value_to_string_internal(argument)
                    return _DIRECT_VALUE_TO_STRING_ABI(argument)
                except PermissionError as error:raise BoundaryViolation(str(error)) from error
                finally:
                    if self._verify_context:self._check()
            if allow_references:serialize_pair.requires_reference=lambda index:index in value.reference_parameters
            return serialize_pair
        from .python_direct_fill import resolve_fill
        bound=resolve_fill(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        # Only exact canonical TextDocument methods, not arbitrary host objects.
        from types import MethodType
        if (type(value) is HostFunction and type(value.function) is MethodType
                and type(value.function.__self__) is BSLTextDocument):
            return text_resources.captured(self,value,require_value=require_value,allow_references=allow_references)
        from yadinassi.application.temporary_storage import SourceTemporaryCall
        from yadinassi.configuration.common_templates import SourceTemplateCall
        if type(value) is HostFunction and type(value.function) is SourceTemporaryCall:
            raise ValueError('temporary storage belongs to another or closed source application')
        if type(value) is HostFunction and type(value.function) is SourceTemplateCall:
            raise ValueError('foreign or inactive source common template owner')
        return super().resolve_callable(value,require_value=require_value,allow_references=allow_references,_extension_value=_extension_value)

    def resolve_optional_service(self,name,*args,**kwargs):
        bound=super().resolve_optional_service(name,*args,**kwargs)
        from yadinassi.runtime import Interpreter
        key=name.casefold()
        vm=getattr(self,'vm',None)
        # This adapter is for the ordinary direct registry, not source-owned
        # services or persisted BSL routines that may shadow its names.
        if type(vm) is not Interpreter or key in getattr(vm,'_direct_routine_modules',{}):
            return bound
        if key.startswith('new:') and key[4:] in OPTIONAL_STREAM_CONSTRUCTORS:
            required,maximum=_STREAM_CONSTRUCTOR_COUNTS[ORDINARY_CONSTRUCTORS[key[4:]]]
            def prepare_omissions(bound,positions,count):
                if not required<=count<=maximum or any(not required<=index<count for index in positions):
                    from yadinassi.execution.codegen.experimental_naked_collections import _host_omission_error
                    _host_omission_error()
                return bound,dict.fromkeys(positions,None)
            bound.prepare_omissions=prepare_omissions
            return bound
        if key in ('new:jsonwritersettings','new:параметрызаписиjson'):
            factory=vm.types.get(key[4:])
            if type(factory) is HostFunction and factory.function is BSLJSONWriterSettings:
                def prepare_omissions(bound,positions,count):
                    if self._verify_context:self._check()
                    if not 1<=count<=2 or any(not 0<=i<count for i in positions):
                        raise TypeError('ПараметрыЗаписиJSON ожидает от 0 до 2 аргументов')
                    def invoke(*values):
                        self._before('call_value',factory.name.casefold())
                        try:
                            if (vm.types.get(key[4:]) is not factory
                                    or factory.function is not BSLJSONWriterSettings):
                                raise BoundaryViolation('canonical JSON constructor changed at call boundary')
                            return BSLJSONWriterSettings(*values)
                        except PermissionError as error:raise BoundaryViolation(str(error)) from error
                        finally:
                            if self._verify_context:self._check()
                    return invoke,dict.fromkeys(positions,None)
                bound.prepare_omissions=prepare_omissions
            return bound
        function=self._services.get(key)
        if type(function) is not HostFunction:return bound
        implementation=function.function
        if implementation is read_json or implementation is write_json:
            returns_value=implementation is read_json
            required,maximum=(1,9) if returns_value else (2,6)
            def prepare_omissions(bound,positions,count):
                from yadinassi.execution.codegen.experimental_naked_collections import _host_omission_error
                if not required<=count<=maximum or any(not required<=i<count for i in positions):
                    _host_omission_error()
                def invoke(*values):
                    if (function.function is not implementation or function.returns_value is not returns_value
                            or type(function.reference_parameters) is not frozenset
                            or function.reference_parameters):
                        raise BoundaryViolation('canonical JSON service changed during argument evaluation')
                    return bound(*values)
                invoke.requires_reference=bound.requires_reference
                return invoke,dict.fromkeys(positions,None)
            bound.prepare_omissions=prepare_omissions
            return bound
        if implementation is not binary_from_string and implementation is not find_files:
            return bound

        external=implementation is find_files

        def canonical():
            return (function.function is implementation and function.returns_value is True
                    and type(function.reference_parameters) is frozenset and not function.reference_parameters)

        def prepare_omissions(bound,positions,count):
            from yadinassi.execution.codegen.experimental_naked_collections import _host_omission_error
            if self._verify_context:self._check()
            if not canonical() or not 1<=count<=3 or any(not 1<=index<count for index in positions):
                _host_omission_error()

            def invoke(*arguments):
                self._before('call',key)
                try:
                    if not canonical():
                        raise BoundaryViolation('optional file service implementation changed during argument evaluation')
                    # FindFiles still crosses a filesystem boundary with omitted arguments.
                    if external and not self._verify_context:self._check_effect()
                    return implementation(*arguments)
                except PermissionError as error:raise BoundaryViolation(str(error)) from error
                finally:
                    if external or self._verify_context:self._check_effect()

            invoke.requires_reference=lambda index:False
            return invoke,{index:None for index in positions}

        bound.prepare_omissions=prepare_omissions
        return bound

    def resolve_service(self,name,*args,**kwargs):
        key=name.casefold()
        self._check_extension_binding(key)
        if key.startswith('new:') and key[4:] in user_messages.NAMES:
            return user_messages.constructor(self,key,**kwargs)
        from yadinassi.application.temporary_storage import SourceTemporaryCall
        from yadinassi.configuration.common_templates import SourceTemplateCall
        function=self._services.get(key)
        if key in ('readjson','прочитатьjson','writejson','записатьjson'):
            count=kwargs.get('argument_count')
            if count is not None and type(function) is HostFunction:
                implementation=function.function
                if ((implementation is read_json and 5<=count<=9)
                        or (implementation is write_json and 4<=count<=6)):
                    from .python_direct_json_handlers import bind
                    original=super().resolve_service(name,*args,**kwargs)
                    return bind(self,key,function,original,implementation)
        if (type(function) is user_messages.HostFunction and type(function.function) is user_messages.MethodType
                and type(function.function.__self__) is user_messages.BSLUserMessage):
            return user_messages.captured(self,function,operation='call',**kwargs)
        from .python_direct_fill import resolve_fill
        bound=resolve_fill(self,function,name=key,**kwargs)
        if bound is not None:return bound
        if type(function) is HostFunction and type(function.function) is SourceTemporaryCall:
            raise ValueError('temporary storage belongs to another or closed source application')
        if type(function) is HostFunction and type(function.function) is SourceTemplateCall:
            raise ValueError('foreign or inactive source common template owner')
        if key.startswith('new:') and key[4:] in text_resources.CONSTRUCTOR_NAMES:
            return text_resources.resolve_constructor(self,key,**kwargs)
        if key.startswith('new:') and key[4:] in ORDINARY_CONSTRUCTORS:
            if self._verify_context:self._check()
            expected=ORDINARY_CONSTRUCTORS[key[4:]]
            if expected is None:
                raise ValueError('Тип не определен: '+name[4:])
            factory=self.vm.types.get(key[4:])
            if expected is BSLTempTablesManager:
                # The factory binds this interpreter's catalog metadata to the
                # manager, just like the owning Query constructor.
                if type(factory) is not HostFunction:
                    raise BoundaryViolation('temporary tables constructor requires registered factory')
                return super().resolve_callable(factory)
            if factory is None and expected in (BSLDOMBuilder,BSLDOMWriter,BSLDOMDocument,
                    BSLDOMNamespaceResolver,BSLXMLReader,BSLXMLReaderSettings,BSLXMLWriter,
                    BSLXMLWriterSettings,BSLBinaryDataBuffer,BSLDataHashing):
                raise ValueError('Тип не определен: '+name[4:])
            if type(factory) is not HostFunction or factory.function is not expected:
                raise BoundaryViolation('direct constructor requires canonical registration: '+key[4:])
            if expected is BSLValueStorage or expected is BSLDeflation:
                from yadinassi.runtime import Interpreter
                if type(self.vm) is not Interpreter:
                    raise BoundaryViolation('direct ValueStorage/Deflation requires an ordinary interpreter')
                from .python_direct_value_storage import constructor
                return constructor(self,key[4:],factory,**kwargs)
            bound=super().resolve_callable(factory)
            if expected in (BSLDOMBuilder,BSLDOMWriter,BSLDOMDocument,BSLDOMNamespaceResolver,BSLXMLReader,BSLXMLWriter,BSLXMLReaderSettings,BSLXMLWriterSettings,BSLHTTPConnection,BSLHTTPRequest,BSLFile,BSLBinaryDataBuffer,BSLDataHashing,BSLJSONSerializerSettings,*_STREAM_CONSTRUCTORS,BSLValueList,BSLValueTable,BSLTypeDescription,BSLNumberQualifiers,BSLStringQualifiers,BSLDateQualifiers,BSLBinaryDataQualifiers):
                original=bound
                def guarded(*values):
                    external = (not self._verify_context and (expected in _FILE_CONSTRUCTORS
                                or (expected in _FILE_OR_BORROWED_STREAM_CONSTRUCTORS
                                    and values and values[0] is not None)))
                    if self._verify_context or external:self._check_effect()
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical constructor changed during argument evaluation')
                    try:return original(*values)
                    finally:
                        if external:self._check_effect()
                bound=guarded
            if expected in fixed.FACTORIES:
                factory_name=factory.name.casefold()
                def fixed_constructor(*values):
                    if self._verify_context:self._check()
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical fixed constructor changed during argument evaluation')
                    self._before('call_value',factory_name)
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical fixed constructor changed at policy boundary')
                    try:return fixed.construct(expected,values)
                    except PermissionError as error:raise BoundaryViolation(str(error)) from error
                    finally:
                        if self._verify_context:self._check()
                bound=fixed_constructor
            if expected is callback_description_marker:
                def callback_constructor(*values):
                    if self._verify_context:self._check()
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical callback constructor changed')
                    self._before('call_value',factory.name.casefold())
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical callback constructor changed at policy boundary')
                    try:return _new_callback(*values)
                    finally:
                        if self._verify_context:self._check()
                def prepare_omissions(bound,positions,count):
                    if self._verify_context:self._check()
                    if count>5:raise TypeError('ОписаниеОповещения ожидает от 0 до 5 аргументов')
                    return bound,{index:None for index in positions}
                callback_constructor.prepare_omissions=prepare_omissions
                bound=callback_constructor
            if expected in (BSLTypeDescription,BSLXMLReaderSettings,BSLXMLWriterSettings):
                def prepare_omissions(bound,positions,count):
                    if self._verify_context:self._check()
                    return bound,{index:None for index in positions}
                bound.prepare_omissions=prepare_omissions
            if expected in (BSLHTTPConnection,BSLHTTPRequest):
                limit=8 if expected is BSLHTTPConnection else 2
                def prepare_omissions(bound,positions,count):
                    if self._verify_context:self._check()
                    if count>limit or any(index<1 or index>=limit for index in positions):
                        raise TypeError('HTTP constructor argument omission is not supported')
                    return bound,{index:None for index in positions}
                bound.prepare_omissions=prepare_omissions
            return bound
        function=self._services.get(key)
        if type(function) is HostFunction and function.function is _DIRECT_TYPE_OF_ABI:
            def direct_type_of(value):
                if function.function is not _DIRECT_TYPE_OF_ABI:
                    raise BoundaryViolation('TypeOf implementation changed during argument evaluation')
                from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
                from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap
                from yadinassi.types.values import BSLType
                kind=type(value)
                if kind is list or kind is PlainArray:return BSLType.ARRAY
                if kind is PlainMap:return BSLType.MAP
                if kind is PlainValueList:return BSLType.VALUE_LIST
                if kind is PlainValueListItem:return BSLType.VALUE_LIST_ITEM
                if kind is fixed.PlainFixedMap:return BSLType.FIXED_MAP
                if kind is _CallbackDescription:return BSLType.CALLBACK_DESCRIPTION
                if kind is _DirectStructure:return BSLType.STRUCTURE
                if kind is _TypedMap:return BSLType.MAP
                if kind is _CanonicalMapEntry:return BSLType.KEY_AND_VALUE
                return _DIRECT_TYPE_OF_ABI(value)
            if self._verify_context:self._check()
            self._validate_host_function(function,kwargs.get('require_value',False),kwargs.get('allow_references',False))
            def invoke(*arguments):
                self._before('call',key)
                try:return direct_type_of(*arguments)
                except PermissionError as error:raise BoundaryViolation(str(error)) from error
                finally:
                    if self._verify_context:self._check()
            if kwargs.get('allow_references',False):invoke.requires_reference=lambda index:index in function.reference_parameters
            return invoke
        if (not self._verify_context and type(function) is HostFunction
                and id(function.function) in _FILE_EFFECTS):
            operation=function.function
            original=super().resolve_service(name,*args,**kwargs)
            def file_effect(*values):
                self._check_effect()
                if function.function is not operation:
                    raise BoundaryViolation('file service changed during argument evaluation')
                try:return original(*values)
                finally:self._check_effect()
            if kwargs.get('allow_references',False):
                file_effect.requires_reference=original.requires_reference
            return file_effect
        bound=_string_callable(self,function,name=key,**kwargs)
        if bound is not None:return bound
        if type(function) is HostFunction and function.function is _DIRECT_VALUE_TO_STRING_ABI:
            if self._verify_context:self._check()
            self._validate_host_function(function,kwargs.get('require_value',False),kwargs.get('allow_references',False))
            def serialize(value):
                self._before('call',key)
                try:
                    if function.function is not _DIRECT_VALUE_TO_STRING_ABI:
                        raise BoundaryViolation('serialization implementation changed during argument evaluation')
                    return _direct_value_to_string_internal(value)
                except PermissionError as error:raise BoundaryViolation(str(error)) from error
                finally:
                    if self._verify_context:self._check()
            if kwargs.get('allow_references',False):serialize.requires_reference=lambda index:index in function.reference_parameters
            return serialize
        bound=super().resolve_service(name,*args,**kwargs)
        function=self._services.get(key)
        if type(function) is HostFunction and function.function is _eval_marker:
            if kwargs.get('argument_count') is not None and kwargs['argument_count']!=1:
                raise TypeError('Вычислить ожидает 1 аргумент')
            from .python_direct_eval import eval_capability
            bound.bind_eval=eval_capability(self,function,key)
        # Only canonical search implementations opt in, never a matching name.
        function=self._services.get(key)
        if type(function) is HostFunction and (function.function is strings._DIRECT_STR_FIND_ABI or id(function.function) in _REGEX_IDENTITIES):
            implementation=function.function
            required=3 if implementation is regex_functions.str_replace else 2
            maximum=5 if implementation is strings._DIRECT_STR_FIND_ABI else 7 if implementation is regex_functions.str_find else 5 if required==3 else 4
            count=kwargs.get('argument_count')
            if count is not None and not required<=count<=maximum:
                raise TypeError('Регулярное выражение: неверное количество аргументов')
            def prepare_omissions(bound,positions,count):
                from yadinassi.execution.codegen.experimental_naked_collections import _host_omission_error
                if self._verify_context:self._check()
                implementation=function.function
                if implementation is not strings._DIRECT_STR_FIND_ABI and id(implementation) not in _REGEX_IDENTITIES:
                    _host_omission_error()
                required=3 if implementation is regex_functions.str_replace else 2
                maximum=5 if implementation is strings._DIRECT_STR_FIND_ABI else 7 if implementation is regex_functions.str_find else 5 if required==3 else 4
                if not required<=count<=maximum:
                    raise TypeError('Регулярное выражение: неверное количество аргументов')
                if any(index<required for index in positions):_host_omission_error()
                def guarded(*arguments):
                    if self._verify_context:self._check()
                    if function.function is not implementation:
                        raise BoundaryViolation('regex implementation changed during argument evaluation')
                    return bound(*arguments)
                guarded.requires_reference=bound.requires_reference
                return guarded,{index:strings._OMITTED for index in positions}
            bound.prepare_omissions=prepare_omissions
        return bound

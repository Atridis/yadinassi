"""Finite canonical constructors for direct JSON, regex and HTTP/file protocols."""
from .file_io import BSLFile, BSLBinaryData
from .text_documents import BSLTextDocument
from . import python_direct_source_resources as text_resources
from .http_client import BSLHTTPConnection, BSLHTTPRequest
from .binary_streams import BSLBinaryDataBuffer
from .json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings
from .values import HostFunction, BSLFixedArray, _DIRECT_TO_STRING_ABI
from .structures import BSLFixedStructure
from .maps import BSLFixedMap
from . import python_direct_fixed as fixed
from .type_descriptions import BSLTypeDescription
from .value_tables import BSLValueTable
from .value_lists import BSLValueList
from .type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers
from . import regex_functions, strings
from .experimental_naked_boundaries import BoundaryViolation

from .experimental_naked_collections import _DIRECT_MAP_ENTRY_TYPE as _CanonicalMapEntry, _TypedMap as _DirectMapType
from .experimental_naked_structure import _DirectStructure as _DirectStructureType
from .type_values import _DIRECT_TYPE_OF_ABI
from .serialization import _DIRECT_VALUE_TO_STRING_ABI, _direct_value_to_string_internal
from .runtime import _eval_marker

_REGEX_IMPLEMENTATIONS=tuple(regex_functions.FUNCTIONS)
_REGEX_IDENTITIES=frozenset(map(id,_REGEX_IMPLEMENTATIONS))

CONSTRUCTORS = {
    alias: factory for aliases,factory in (
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

def _string_callable(context,function,*,name=None,require_value=False,allow_references=False,**unused):
    if type(function) is not HostFunction or function.function is not _DIRECT_TO_STRING_ABI:return None
    context._check()
    context._validate_host_function(function,require_value,allow_references)
    key=name if name is not None else function.name.casefold()
    def stringify(value):
        context._before('call' if name is not None else 'call_value',key)
        try:
            if function.function is not _DIRECT_TO_STRING_ABI:
                raise BoundaryViolation('String implementation changed during argument evaluation')
            kind=type(value)
            if kind is list:return 'Массив'
            if kind is _DirectStructureType:return 'Структура'
            if kind is _DirectMapType:return 'Соответствие'
            # Preserve the existing canonical service for all other values.
            # This adds no new host-object admission or payload traversal.
            return _DIRECT_TO_STRING_ABI(value)
        except PermissionError as error:raise BoundaryViolation(str(error)) from error
        finally:context._check()
    if allow_references:stringify.requires_reference=lambda index:index in function.reference_parameters
    return stringify


class ServicesBoundary:
    def get_member(self,value,name):
        if value is None:
            self._check();raise ValueError('Значение не является значением объектного типа')
        from .python_direct_error_info import owns, read
        if owns(value):return read(self,value,name)
        if type(value) is BSLTextDocument:return text_resources.get(self,value,name)
        return super().get_member(value,name)

    def resolve_member(self,value,name):
        if value is None:
            self._check();raise ValueError('Значение не является значением объектного типа')
        from .python_direct_error_info import owns,resolve_query
        if owns(value):return resolve_query(self,value,name)
        if type(value) is BSLTextDocument:return text_resources.resolve(self,value,name)
        return super().resolve_member(value,name)

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if value is None:
            self._check();raise ValueError('Значение не является значением объектного типа')
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
        self._check()
        def readonly(new_value):
            self._check()
            raise ValueError('Свойство недоступно для записи: '+name)
        return readonly

    def resolve_callable(self,value,*,require_value=False,allow_references=False):
        bound=_string_callable(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        from .python_direct_fill import resolve_fill
        bound=resolve_fill(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        # Only exact canonical TextDocument methods, not arbitrary host objects.
        from types import MethodType
        if (type(value) is HostFunction and type(value.function) is MethodType
                and type(value.function.__self__) is BSLTextDocument):
            return text_resources.captured(self,value,require_value=require_value,allow_references=allow_references)
        from .temporary_storage import SourceTemporaryCall
        from .common_templates import SourceTemplateCall
        if type(value) is HostFunction and type(value.function) is SourceTemporaryCall:
            raise ValueError('temporary storage belongs to another or closed source application')
        if type(value) is HostFunction and type(value.function) is SourceTemplateCall:
            raise ValueError('foreign or inactive source common template owner')
        return super().resolve_callable(value,require_value=require_value,allow_references=allow_references)

    def resolve_service(self,name,*args,**kwargs):
        key=name.casefold()
        from .temporary_storage import SourceTemporaryCall
        from .common_templates import SourceTemplateCall
        function=self._services.get(key)
        from .python_direct_fill import resolve_fill
        bound=resolve_fill(self,function,name=key,**kwargs)
        if bound is not None:return bound
        if type(function) is HostFunction and type(function.function) is SourceTemporaryCall:
            raise ValueError('temporary storage belongs to another or closed source application')
        if type(function) is HostFunction and type(function.function) is SourceTemplateCall:
            raise ValueError('foreign or inactive source common template owner')
        if key.startswith('new:') and key[4:] in text_resources.CONSTRUCTOR_NAMES:
            return text_resources.resolve_constructor(self,key,**kwargs)
        if key.startswith('new:') and key[4:] in CONSTRUCTORS:
            self._check()
            expected=CONSTRUCTORS[key[4:]]
            if expected is None:
                raise ValueError('Тип не определен: '+name[4:])
            factory=self.vm.types.get(key[4:])
            if type(factory) is not HostFunction or factory.function is not expected:
                raise BoundaryViolation('direct constructor requires canonical registration: '+key[4:])
            bound=super().resolve_callable(factory)
            if expected in (BSLHTTPConnection,BSLHTTPRequest,BSLFile,BSLBinaryData,BSLBinaryDataBuffer,BSLValueList,BSLValueTable,BSLTypeDescription,BSLNumberQualifiers,BSLStringQualifiers,BSLDateQualifiers,BSLBinaryDataQualifiers):
                original=bound
                def guarded(*values):
                    self._check()
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical constructor changed during argument evaluation')
                    return original(*values)
                bound=guarded
            if expected in fixed.FACTORIES:
                factory_name=factory.name.casefold()
                def fixed_constructor(*values):
                    self._check()
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical fixed constructor changed during argument evaluation')
                    self._before('call_value',factory_name)
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical fixed constructor changed at policy boundary')
                    try:return fixed.construct(expected,values)
                    except PermissionError as error:raise BoundaryViolation(str(error)) from error
                    finally:self._check()
                bound=fixed_constructor
            if expected is BSLTypeDescription:
                def prepare_omissions(bound,positions,count):
                    self._check()
                    return bound,{index:None for index in positions}
                bound.prepare_omissions=prepare_omissions
            if expected in (BSLHTTPConnection,BSLHTTPRequest):
                limit=8 if expected is BSLHTTPConnection else 2
                def prepare_omissions(bound,positions,count):
                    self._check()
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
                from .experimental_naked_structure import _DirectStructure
                from .experimental_naked_collections import _TypedMap
                from .values import BSLType
                kind=type(value)
                if kind is list:return BSLType.ARRAY
                if kind is _DirectStructure:return BSLType.STRUCTURE
                if kind is _TypedMap:return BSLType.MAP
                if kind is _CanonicalMapEntry:return BSLType.KEY_AND_VALUE
                return _DIRECT_TYPE_OF_ABI(value)
            self._check()
            self._validate_host_function(function,kwargs.get('require_value',False),kwargs.get('allow_references',False))
            def invoke(*arguments):
                self._before('call',key)
                try:return direct_type_of(*arguments)
                except PermissionError as error:raise BoundaryViolation(str(error)) from error
                finally:self._check()
            if kwargs.get('allow_references',False):invoke.requires_reference=lambda index:index in function.reference_parameters
            return invoke
        bound=_string_callable(self,function,name=key,**kwargs)
        if bound is not None:return bound
        if type(function) is HostFunction and function.function is _DIRECT_VALUE_TO_STRING_ABI:
            self._check()
            self._validate_host_function(function,kwargs.get('require_value',False),kwargs.get('allow_references',False))
            def serialize(value):
                self._before('call',key)
                try:
                    if function.function is not _DIRECT_VALUE_TO_STRING_ABI:
                        raise BoundaryViolation('serialization implementation changed during argument evaluation')
                    return _direct_value_to_string_internal(value)
                except PermissionError as error:raise BoundaryViolation(str(error)) from error
                finally:self._check()
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
                from .experimental_naked_collections import _host_omission_error
                self._check()
                implementation=function.function
                if implementation is not strings._DIRECT_STR_FIND_ABI and id(implementation) not in _REGEX_IDENTITIES:
                    _host_omission_error()
                required=3 if implementation is regex_functions.str_replace else 2
                maximum=5 if implementation is strings._DIRECT_STR_FIND_ABI else 7 if implementation is regex_functions.str_find else 5 if required==3 else 4
                if not required<=count<=maximum:
                    raise TypeError('Регулярное выражение: неверное количество аргументов')
                if any(index<required for index in positions):_host_omission_error()
                def guarded(*arguments):
                    self._check()
                    if function.function is not implementation:
                        raise BoundaryViolation('regex implementation changed during argument evaluation')
                    return bound(*arguments)
                guarded.requires_reference=bound.requires_reference
                return guarded,{index:strings._OMITTED for index in positions}
            bound.prepare_omissions=prepare_omissions
        return bound

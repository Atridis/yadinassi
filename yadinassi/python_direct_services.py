"""Finite canonical constructors for direct JSON, regex and HTTP/file protocols."""
from .file_io import BSLFile, BSLBinaryData
from .http_client import BSLHTTPConnection, BSLHTTPRequest
from .binary_streams import BSLBinaryDataBuffer
from .json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings
from .values import HostFunction
from .type_descriptions import BSLTypeDescription
from .value_tables import BSLValueTable
from .type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers
from . import regex_functions, strings
from .experimental_naked_boundaries import BoundaryViolation

CONSTRUCTORS = {
    alias: factory for aliases,factory in (
        (('valuetable','таблицазначений'),BSLValueTable),
        (('typedescription','описаниетипов'),BSLTypeDescription),
        (('numberqualifiers','квалификаторычисла'),BSLNumberQualifiers),
        (('stringqualifiers','квалификаторыстроки'),BSLStringQualifiers),
        (('datequalifiers','квалификаторыдаты'),BSLDateQualifiers),
        (('binarydataqualifiers','квалификаторыдвоичныхданных'),BSLBinaryDataQualifiers),
        (('file','файл'),BSLFile),
        (('binarydata','двоичныеданные'),BSLBinaryData),
        (('binarydatabuffer','буфердвоичныхданных'),BSLBinaryDataBuffer),
        (('httpconnection','httpсоединение'),BSLHTTPConnection),
        (('httprequest','httpзапрос'),BSLHTTPRequest),
        (('jsonreader','чтениеjson'),BSLJSONReader),
        (('jsonwriter','записьjson'),BSLJSONWriter),
        (('jsonwritersettings','параметрызаписиjson'),BSLJSONWriterSettings),
        (('searchdirection','направлениепоиска'),None),
        (('resultofsearchbyregularexpression','результатпоискапорегулярномувыражению'),None),
        (('resultofsearchbyregularexpressiongroup','группарезультатапоискапорегулярномувыражению'),None),
    ) for alias in aliases
}

class ServicesBoundary:
    def resolve_service(self,name,*args,**kwargs):
        key=name.casefold()
        if key.startswith('new:') and key[4:] in CONSTRUCTORS:
            self._check()
            expected=CONSTRUCTORS[key[4:]]
            if expected is None:
                raise ValueError('Тип не определен: '+name[4:])
            factory=self.vm.types.get(key[4:])
            if type(factory) is not HostFunction or factory.function is not expected:
                raise BoundaryViolation('direct constructor requires canonical registration: '+key[4:])
            bound=super().resolve_callable(factory)
            if expected in (BSLHTTPConnection,BSLHTTPRequest,BSLFile,BSLBinaryData,BSLBinaryDataBuffer,BSLValueTable,BSLTypeDescription,BSLNumberQualifiers,BSLStringQualifiers,BSLDateQualifiers,BSLBinaryDataQualifiers):
                original=bound
                def guarded(*values):
                    self._check()
                    if factory.function is not expected:
                        raise BoundaryViolation('canonical constructor changed during argument evaluation')
                    return original(*values)
                bound=guarded
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
        from .type_values import _DIRECT_TYPE_OF_ABI
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
        from .serialization import _DIRECT_VALUE_TO_STRING_ABI, _direct_value_to_string_internal
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
        from .runtime import _eval_marker
        function=self._services.get(key)
        if type(function) is HostFunction and function.function is _eval_marker:
            if kwargs.get('argument_count') is not None and kwargs['argument_count']!=1:
                raise TypeError('Вычислить ожидает 1 аргумент')
            from .python_direct_eval import eval_capability
            bound.bind_eval=eval_capability(self,function,key)
        # Only canonical search implementations opt in, never a matching name.
        function=self._services.get(key)
        if type(function) is HostFunction and (function.function is strings._DIRECT_STR_FIND_ABI or any(function.function is item for item in regex_functions.FUNCTIONS)):
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
                if implementation is not strings._DIRECT_STR_FIND_ABI and not any(implementation is item for item in regex_functions.FUNCTIONS):
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

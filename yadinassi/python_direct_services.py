"""Finite canonical constructors for direct JSON and regex interoperability."""
from .json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings
from .values import HostFunction
from . import regex_functions, strings
from .experimental_naked_boundaries import BoundaryViolation

CONSTRUCTORS = {
    alias: factory for aliases,factory in (
        (('jsonreader','чтениеjson'),BSLJSONReader),
        (('jsonwriter','записьjson'),BSLJSONWriter),
        (('jsonwritersettings','параметрызаписиjson'),BSLJSONWriterSettings),
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
            return super().resolve_callable(factory)
        bound=super().resolve_service(name,*args,**kwargs)
        # Only canonical regex implementations opt in, never a matching name.
        function=self._services.get(key)
        if type(function) is HostFunction and any(function.function is item for item in regex_functions.FUNCTIONS):
            implementation=function.function
            required=3 if implementation is regex_functions.str_replace else 2
            maximum=7 if implementation is regex_functions.str_find else 5 if required==3 else 4
            count=kwargs.get('argument_count')
            if count is not None and not required<=count<=maximum:
                raise TypeError('Регулярное выражение: неверное количество аргументов')
            def prepare_omissions(bound,positions,count):
                from .experimental_naked_collections import _host_omission_error
                self._check()
                implementation=function.function
                if not any(implementation is item for item in regex_functions.FUNCTIONS):
                    _host_omission_error()
                required=3 if implementation is regex_functions.str_replace else 2
                maximum=7 if implementation is regex_functions.str_find else 5 if required==3 else 4
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

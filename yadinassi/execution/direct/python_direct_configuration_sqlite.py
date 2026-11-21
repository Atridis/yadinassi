"""SQL reads and detached catalog buffers inside an owned client common routine."""
from types import MethodType

from yadinassi.db.catalog.catalogs import BSLCatalogs, BSLCatalogManager, BSLCatalogObject
from yadinassi.db.catalog.catalog_types import BSLCatalogReference
from yadinassi.db.query.queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection
from yadinassi.db.query.query_packages import BSLTempTablesManager, TEMP_TABLE_MANAGER_NAMES
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.runtime import _DIRECT_QUERY_FACTORY_ABI, _DIRECT_TEMP_TABLE_FACTORY_ABI, _DIRECT_TYPE_NAME_ABI
from yadinassi.types.type_values import _DIRECT_TYPE_OF_ABI
from yadinassi.types.values import HostFunction
from .python_direct_configuration import ConfigurationBoundary, check_owner
from . import python_direct_configuration_enums as enums
from .python_direct_database import CatalogBoundary
from .python_direct_fill import resolve_fill

NAMES = ('catalogs','справочники')
_QUERY = ('query','запрос')
CONSTRUCTORS = _QUERY + TEMP_TABLE_MANAGER_NAMES

_READERS = frozenset(map(id, (BSLCatalogs, BSLCatalogManager, BSLCatalogObject,
    BSLCatalogReference, BSLQuery, BSLQueryResult, BSLQueryResultSelection, BSLTempTablesManager)))
# No persistence call is exposed on the editable in-memory catalog buffer.
_METHODS = {
    BSLCatalogs: ('__getitem__',),
    BSLCatalogManager: ('findbycode','найтипокоду','findbydescription','найтипонаименованию',
                       'emptyref','пустаяссылка','createitem','создатьэлемент'),
    BSLCatalogReference: ('getobject','получитьобъект','isempty','пустая'),
    BSLCatalogObject: ('isnew','этоновый','__getitem__'),
    BSLQuery: ('setparameter','установитьпараметр','execute','выполнить',
               'executebatch','выполнитьпакет'),
    BSLQueryResult: ('select','выбрать','isempty','пустой'),
    BSLQueryResultSelection: ('next','следующий'),
    BSLTempTablesManager: ('close','закрыть'),
}


class SQLiteClientRoutine(ConfigurationBoundary, CatalogBoundary):
    def __init__(self, app, owner, routine):
        super().__init__(app, owner, routine)
        self.vm = owner
        self._database_grant = app._client_sqlite
        self._catalogs = owner._catalogs
        self._plan=owner._direct_configuration_plan
        self._routine_key=routine.name.casefold()
        # The command still checks the complete admitted scope at its normal
        # boundaries. Receiver operations use only the live database owner.
        self._verify_context = False

    def _check_effect(self):
        self._check_lease()
        scope = self._command_scope
        scope.check_origin()
        check_owner(self.app,self.owner,allow_database=True)
        if (self.app._client_sqlite is not self._database_grant
                or self.app.state != scope.expected_state or self.owner.execution_context != 'client'
                or self.owner._direct_configuration_plan is not self._plan
                or type(self.owner.routines) is not dict or self.owner.routines.get(self._routine_key) is not self.routine
                or self.owner._catalogs is not self._catalogs
                or type(self._catalogs) is not BSLCatalogs
                or self._catalogs._context is not self._database_grant[0]
                or self._catalogs._metadata is not self.owner._metadata._catalogs):
            raise BoundaryViolation('client configuration SQLite activation changed')

    def _catalog_owner(self,value,*,verify=True):
        if id(type(value)) not in _READERS:
            raise BoundaryViolation('unsupported client configuration database receiver')
        return super()._catalog_owner(value,verify=verify)

    def external_get(self,name):
        if name.casefold() in NAMES:
            self._check_effect()
            return self._catalogs
        return super().external_get(name)

    def get_member(self,value,name):
        if id(type(value)) in _READERS:
            if name.startswith('_'):raise BoundaryViolation('private configuration database member')
            result=CatalogBoundary.get_member(self,value,name)
            if type(result) is HostFunction:
                raise BoundaryViolation('captured configuration database methods are not connected')
            return result
        return super().get_member(value,name)

    def resolve_member(self,value,name):
        if id(type(value)) in _READERS:
            if name.casefold() not in _METHODS[type(value)]:
                raise BoundaryViolation('configuration database method not connected: '+name)
            return CatalogBoundary.resolve_member(self,value,name)
        return super().resolve_member(value,name)

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if id(type(value)) in _READERS:
            if omitted:raise TypeError('configuration database methods do not accept omitted arguments')
            if require_value and name.casefold() in ('setparameter','установитьпараметр','close','закрыть'):
                raise TypeError('Процедура не возвращает значение: '+name)
            return self.resolve_member(value,name)
        return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)

    def resolve_set_member(self,value,name):
        if type(value) is BSLCatalogObject and not name.startswith('_'):
            return CatalogBoundary.resolve_set_member(self,value,name)
        if type(value) is BSLQuery and name.casefold() in ('text','текст','temptablesmanager','менеджервременныхтаблиц'):
            return CatalogBoundary.resolve_set_member(self,value,name)
        return BoundaryContext.resolve_set_member(self,value,name)

    reference_member=BoundaryContext.reference_member
    reference_index=BoundaryContext.reference_index

    def resolve_service(self,name,*args,**kwargs):
        key=name.casefold()
        if key.startswith('new:') and key[4:] in CONSTRUCTORS:
            key=key[4:]
            expected=_DIRECT_QUERY_FACTORY_ABI if key in _QUERY else _DIRECT_TEMP_TABLE_FACTORY_ABI
            return self._binding(self.owner.types,key,expected)
        name_type=key in ('type','тип')
        if name_type or key in ('typeof','типзнч'):
            bind=self._binding(self._services,key,_DIRECT_TYPE_NAME_ABI if name_type else _DIRECT_TYPE_OF_ABI,
                               receiver=not name_type)
            if not self.app.configuration.enumerations:return bind
            enum=super().resolve_service(name,*args,**kwargs)
            def select(value):
                if name_type and type(value) is str:
                    prefix,sep,_=value.partition('.')
                    if sep and prefix.casefold() in ('enumref','перечислениессылка',
                                                     'enummanager','перечислениеменеджер'):
                        return enum(value)
                elif not name_type and (enums.transfer_value(value) or type(value) is enums.bridge.BSLEnumManager):
                    return enum(value)
                return bind(value)
            select.requires_reference=lambda index:False
            return select
        if key in ('fillpropertyvalues','заполнитьзначениясвойств'):
            bound=resolve_fill(self,self._services.get(key),name=key,**kwargs)
            if bound is not None:return bound
        return super().resolve_service(name,*args,**kwargs)

    def _binding(self,registry,key,expected,*,receiver=False):
        self._check_effect()
        function=registry.get(key)
        if type(function) is not HostFunction:
            raise BoundaryViolation('configuration database service requires canonical binding')
        implementation=function.function
        if receiver:
            valid=implementation is expected
        else:
            valid=(type(implementation) is MethodType and implementation.__self__ is self.owner
                   and implementation.__func__ is expected)
        if not valid:
            raise BoundaryViolation('configuration database service requires owning binding')

        def invoke(*args):
            self._before('call',key)
            self._check_effect()
            if (registry.get(key) is not function or function.function is not implementation
                    or function.returns_value is not True or type(function.reference_parameters) is not frozenset
                    or function.reference_parameters):
                raise BoundaryViolation('configuration database service binding changed')
            if receiver:
                if len(args)!=1:raise TypeError('TypeOf requires one argument')
                if id(type(args[0])) in _READERS:self._catalog_owner(args[0],verify=False)
                elif not self._command_scope.literal(args[0]):raise TypeError('unsupported TypeOf value')
            return implementation(*args)
        invoke.requires_reference=lambda index:False
        return invoke

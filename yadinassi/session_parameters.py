"""Application-owned scalar state. No database, ACL or privilege-mode grant."""
from decimal import Decimal
import weakref
from .values import BSLObject, BSLArray, HostFunction
from .metadata import _MetadataObject, _DeclaredMetadataCollection, _scalar_description
from .dates import BSLDate
from .catalog_qualifiers import validate_string, normalize_number

_UNSET=object()


class BSLSessionParameterMetadata(_MetadataObject):
    def __init__(self,definition):
        self._name=definition.name
        self._description=_scalar_description(definition.kind,definition.qualifiers)

    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('type','тип'): return self._description
        if key in ('fullname','полноеимя'):
            return HostFunction(name,lambda:'ПараметрСеанса.'+self._name)
        return super().get_member(name)


class BSLSessionParameters(BSLObject):
    def __init__(self, application, definitions):
        self._application=weakref.ref(application)
        self._definitions={d.name.casefold():d for d in definitions}
        self.metadata=_DeclaredMetadataCollection(tuple(BSLSessionParameterMetadata(d) for d in definitions))
        self._values={name:_UNSET for name in self._definitions}
        self._initializing=set()
        self._closed=False

    def _authorize(self, caller):
        app=self._application()
        if (self._closed or app is None or caller._configuration_runtime is not app
                or caller._scheduler is not app.interpreter._scheduler):
            raise ValueError('session parameters belong to another or closed application')
        app.require_open()
        caller._require_family()
        if app.state not in ('starting','running') or caller.execution_context!='server':
            raise ValueError('session parameters require an active server application context')
        return app

    def _key(self, name):
        if type(name) is not str or not 1<=len(name)<=128:
            raise TypeError('session parameter name requires String')
        key=name.casefold()
        if key not in self._definitions: raise ValueError('unknown session parameter')
        return key

    def read(self, caller, name):
        app=self._authorize(caller);key=self._key(name)
        if self._values[key] is _UNSET:
            if key in self._initializing or len(self._initializing)>=16:
                raise ValueError('recursive session parameter initialization')
            self._initializing.add(key)
            try:
                names=BSLArray();names.items.append(self._definitions[key].name)
                yield from app.initialize_session_parameters(caller,names)
            finally:
                self._initializing.discard(key)
        self._authorize(caller)
        if self._values[key] is _UNSET:
            raise ValueError('session parameter value is not set')
        return self._values[key]

    def write(self, caller, name, value):
        self._authorize(caller);key=self._key(name);definition=self._definitions[key]
        if definition.kind=='boolean':
            valid=type(value) is bool
        elif definition.kind=='string':
            validate_string(value,definition.qualifiers[0]);valid=True
        elif definition.kind=='number':
            valid=type(value) is Decimal and value.is_finite()
            if valid: valid=normalize_number(value,definition.qualifiers)==value
        else:
            valid=type(value) is BSLDate
            if valid:value.require_known()
        if not valid: raise TypeError('unsupported session parameter assignment')
        self._values[key]=value

    def close(self):
        self._closed=True
        self._values.clear()
        self._initializing.clear()

    def get_member(self,name):
        raise ValueError('session parameter access requires the executing interpreter')

    def set_member(self,name,value):
        raise ValueError('session parameter assignment requires the executing interpreter')

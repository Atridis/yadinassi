"""Application-owned scalar state. No database, ACL or privilege-mode grant."""
from decimal import Decimal
import weakref
from .values import BSLObject, BSLArray, HostFunction
from .metadata import _MetadataObject, _DeclaredMetadataCollection, _scalar_description
from .dates import BSLDate
from .catalog_qualifiers import validate_string, normalize_number

_UNSET=object()
_SOURCE_STRING_MAX_UNITS=1048576


class BSLSessionParameterMetadata(_MetadataObject):
    def __init__(self,definition):
        self._name=definition.name
        if definition.kind == 'uuid':
            from .type_descriptions import BSLTypeDescription
            self._description = BSLTypeDescription('UUID')
        else:
            self._description=(_scalar_description(definition.kind, definition.qualifiers)
                               if definition.kind in ('boolean','string','number','datetime') else None)

    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'): return self._name
        if key in ('type','тип'):
            if self._description is None:
                raise ValueError('unsupported metadata field type: source session description')
            return self._description
        if key in ('fullname','полноеимя'):
            return HostFunction(name,lambda:'ПараметрСеанса.'+self._name)
        return super().get_member(name)


class BSLSessionParameters(BSLObject):
    def __init__(self, application, definitions, *, source_family=None, unsupported=None):
        self._application=weakref.ref(application)
        # A source-only host binds a family explicitly, without granting the
        # unrelated database/template/transport capabilities of ConfigurationApplication.
        self._source_family = weakref.ref(source_family) if source_family is not None else None
        self._unsupported = dict(unsupported or {})
        self._definitions={d.name.casefold():d for d in definitions}
        self.metadata=_DeclaredMetadataCollection(tuple(BSLSessionParameterMetadata(d) for d in definitions))
        self._values={name:_UNSET for name in self._definitions}
        self._initializing=set()
        self._closed=False

    def _authorize(self, caller):
        app=self._application()
        source_owned = (self._source_family is not None
                        and self._source_family() is caller._family_owner
                        and getattr(caller, 'application', None) is app)
        if (self._closed or app is None
                or (caller._configuration_runtime is not app and not source_owned)
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
        if key in self._unsupported:
            raise ValueError('unsupported session parameter type: ' + name + ': ' + self._unsupported[key])
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
        value = self._validate_value(definition.kind, definition.qualifiers, value)
        if self._source_family is not None:
            from .source_session_values import validate_session_value
            validate_session_value(value)
        self._values[key]=value

    def _validate_value(self, kind, qualifiers, value):
        if kind=='source_union':
            if self._source_family is None:
                raise ValueError('composite session types require source host')
            for alternative, limits in qualifiers:
                try:
                    return self._validate_value(alternative, limits, value)
                except (TypeError, ValueError):
                    pass
            raise TypeError('value does not match any declared source session type')
        if kind=='boolean':
            valid=type(value) is bool
        elif kind=='string':
            if qualifiers[0] == 0:
                if self._source_family is None:
                    raise ValueError('unbounded session strings require source host')
                if type(value) is not str:
                    raise TypeError('session String required')
                if len(value) > _SOURCE_STRING_MAX_UNITS or len(value.encode('utf-16-le')) > 2 * _SOURCE_STRING_MAX_UNITS:
                    raise ValueError('source session String resource limit')
            else:
                validate_string(value,qualifiers[0])
            valid=True
        elif kind=='number':
            valid=type(value) is Decimal and value.is_finite()
            if valid: valid=normalize_number(value,qualifiers)==value
        elif kind=='fixed_map':
            from .maps import BSLFixedMap
            valid=type(value) is BSLFixedMap
        elif kind=='fixed_structure':
            from .structures import BSLFixedStructure
            valid=type(value) is BSLFixedStructure
        elif kind=='datetime':
            valid=type(value) is BSLDate
            if valid:value.require_known()
        elif kind in ('uuid', 'value_storage', 'type_description', 'fixed_array'):
            if self._source_family is None:
                raise ValueError('extended session types require source host')
            from .unique_identifiers import BSLUUID
            from .value_storage import BSLValueStorage
            from .type_descriptions import BSLTypeDescription
            from .values import BSLFixedArray
            valid=type(value) is {'uuid':BSLUUID, 'value_storage':BSLValueStorage,
                                  'type_description':BSLTypeDescription, 'fixed_array':BSLFixedArray}[kind]
        else:
            raise ValueError('unsupported session parameter type')
        if not valid: raise TypeError('unsupported session parameter assignment')
        return value

    def close(self):
        self._closed=True
        self._values.clear()
        self._initializing.clear()

    def get_member(self,name):
        raise ValueError('session parameter access requires the executing interpreter')

    def set_member(self,name,value):
        raise ValueError('session parameter assignment requires the executing interpreter')

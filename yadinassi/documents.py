"""Read-only measured Document managers, cards and chronological selections.

Native 41256261065; no posting/write API. Unsupported layouts fail in storage.
"""
from uuid import UUID
from .values import BSLObject, HostFunction
from .unique_identifiers import BSLUUID
from .dates import BSLDate, _date_from_datetime
from .document_types import BSLDocumentType, BSLDocumentReference
from .catalogs import _bound_card, _bound_value

_ZERO = UUID(int=0)
_OMITTED = object()
_ALIASES = {'номер':'number','дата':'date','проведен':'posted','ссылка':'ref',
            'пометкаудаления':'deletionmark'}
_RESERVED = frozenset((*_ALIASES, *_ALIASES.values()))


def _field(fields, name):
    key = name.casefold()
    key = _ALIASES.get(key, key)
    if key not in fields:
        raise ValueError('document field not found: '+name)
    return fields[key]


class BSLDocuments(BSLObject):
    def __init__(self, metadata, context, catalogs):
        self._metadata, self._context, self._catalogs = metadata, context, catalogs
        self._managers = {}

    def get_member(self, name):
        return self.get_index(name)

    def get_index(self, name):
        if type(name) is not str:
            raise TypeError('document name requires String')
        item = self._metadata._snapshot().get(name.casefold())
        if item is None:
            raise ValueError('document name not found')
        key = item._name.casefold()
        if key not in self._managers:
            self._managers[key] = BSLDocumentManager(self, item)
        return self._managers[key]

    def set_index(self, name, value):
        raise ValueError('document managers are read-only')

    def type_by_name(self, name):
        if type(name) is str:
            prefix, separator, item = name.partition('.')
            families = {'документссылка':'_value_type','documentref':'_value_type',
                        'документменеджер':'_manager_type','documentmanager':'_manager_type',
                        'документвыборка':'_selection_type','documentselection':'_selection_type'}
            if separator and prefix.casefold() in families:
                return getattr(self.get_index(item), families[prefix.casefold()])
        return self._catalogs.type_by_name(name)

    def __str__(self):
        raise ValueError('document managers presentation is unsupported')


class BSLDocumentManager(BSLObject):
    def __init__(self, documents, metadata):
        self._documents, self._metadata = documents, metadata
        self._catalogs = documents._catalogs
        for family, key in (('ref','_value_type'),('manager','_manager_type'),('selection','_selection_type')):
            setattr(self,key,BSLDocumentType(UUID(metadata._metadata_uuid),metadata._name,documents._metadata,family))

    def _ref(self, uuid):
        return BSLDocumentReference(self._value_type, uuid, self._metadata, self._read_member)

    def empty_ref(self):
        return self._ref(_ZERO)

    def get_ref(self, uuid=_OMITTED):
        if uuid is _OMITTED or uuid is None:
            uuid = BSLUUID()
        if type(uuid) is not BSLUUID:
            raise TypeError('GetRef requires UUID')
        return self._ref(UUID(uuid.text))

    def _rows(self):
        result = self._documents._context.document_rows(self._metadata._name)
        if (result.identity.name != self._metadata._name or
                UUID(result.identity.metadata_uuid) != self._value_type.metadata_uuid or
                result.config_snapshot != self._documents._metadata._config_snapshot):
            raise ValueError('document metadata identity changed')
        refs = [row.reference_uuid for row in result.rows]
        if len(set(refs)) != len(refs) or _ZERO in refs:
            raise ValueError('invalid document row identities')
        return result

    def _attributes(self, result):
        attributes = result.binding.attributes
        if type(attributes) is not tuple or len(attributes) > 10:
            raise ValueError('document attributes exceed bounded profile')
        names = set()
        for attribute in attributes:
            key = attribute.name.casefold()
            if key in _RESERVED or key in names:
                raise ValueError('ambiguous document field name')
            names.add(key)
        return attributes

    def _fields(self, result, row):
        physical = {field.declaration.name:field.value for field in row.physical_record.fields}
        logical = {'number':physical['_NUMBER'], 'date':_date_from_datetime(physical['_DATE_TIME']),
                   'posted':physical['_POSTED'], 'deletionmark':physical['_MARKED'],
                   'ref':self._ref(row.reference_uuid)}
        for attribute in self._attributes(result):
            logical[attribute.name.casefold()] = _bound_card(attribute).project(
                _bound_value(attribute, physical[attribute.physical_name]), self._catalogs)
        return logical

    def _default_fields(self, result, ref=None):
        logical = {'number':'','date':BSLDate(0),'posted':False,'deletionmark':False,'ref':ref}
        for attribute in self._attributes(result):
            logical[attribute.name.casefold()] = _bound_card(attribute).default(self._catalogs)
        return logical

    def _read_member(self, ref, name):
        result = self._rows()
        for row in result.rows:
            if row.reference_uuid == ref.reference_uuid:
                return _field(self._fields(result,row),name)
        return _field(self._default_fields(result,ref),name)

    def find_by_number(self, number, date=_OMITTED):
        if type(number) is not str:
            raise TypeError('document number requires String')
        if date is not _OMITTED and date is not None:
            if type(date) is not BSLDate:
                raise TypeError('document lookup date requires Date')
            date.require_known()
        # Nonperiodical numbering: the validated optional date does not narrow.
        # !todo Other numbering/collation profiles require native evidence.
        if number and (len(number) > 8 or not number.isascii() or not number.isalnum()):
            raise ValueError('document number lookup normalization is unsupported')
        result = self._rows()
        numbered = [(self._fields(result,row)['number'], row) for row in result.rows]
        # The physical CI declaration is not permission to guess Unicode/case or
        # padding rules. Digit-only stored numbers make ASCII missing probes safe.
        if any(type(key) is not str or not 1 <= len(key) <= 8 or
               not key.isascii() or not key.isdigit() for key,_ in numbered):
            raise ValueError('document number lookup collation is unsupported')
        matches = [row for key,row in numbered if key == number]
        if len(matches)>1:
            raise ValueError('ambiguous document number lookup')
        return self._ref(matches[0].reference_uuid) if matches else self.empty_ref()

    def select(self, start=_OMITTED, end=_OMITTED):
        bounds=[]
        for value in (start,end):
            if value is _OMITTED or value is None:
                bounds.append(None)
            else:
                if type(value) is not BSLDate:
                    raise TypeError('document selection bounds require Date')
                value.require_known()
                bounds.append(value.ticks or None)
        return BSLDocumentSelection(self,self._rows(),*bounds)

    def get_member(self, name):
        methods={'emptyref':self.empty_ref,'пустаяссылка':self.empty_ref,
                 'getref':self.get_ref,'получитьссылку':self.get_ref,
                 'select':self.select,'выбрать':self.select,
                 'findbynumber':self.find_by_number,'найтипономеру':self.find_by_number}
        method=methods.get(name.casefold())
        return HostFunction(name,method) if method else super().get_member(name)

    def __str__(self):
        raise ValueError('document manager presentation is unsupported')


class BSLDocumentSelection(BSLObject):
    def __init__(self, manager, result, start, end):
        self._manager,self._result=manager,result
        self._selection_type=manager._selection_type
        dated=[(manager._fields(result,row)['date'].ticks,row) for row in result.rows]
        # !todo Equal-date document ordering needs its own native witness.
        if len({date for date,_ in dated}) != len(dated):
            raise ValueError('equal-date document ordering is unsupported')
        self._rows=tuple(row for date,row in sorted(dated,key=lambda item:item[0])
                         if (start is None or date>=start) and (end is None or date<=end))
        self._position=-1
        self._next_position=0

    def next(self):
        if self._next_position>=len(self._rows):
            return False
        self._position=self._next_position
        self._next_position+=1
        return True

    def get_method(self,name):
        if name.casefold() in ('next','следующий'):
            return HostFunction(name,self.next)
        return super().get_method(name)

    def get_member(self,name):
        if self._position<0:
            _field(self._manager._default_fields(self._result),name)
            return None
        return _field(self._manager._fields(self._result,self._rows[self._position]),name)

    def __str__(self):
        raise ValueError('document selection presentation is unsupported')

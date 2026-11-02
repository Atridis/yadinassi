"""Measured read-only independent InformationRegisters Get/Select/Next.

Native41353896285; no record-set/manager mutation, query engine or live session.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID
from .values import BSLObject, HostFunction
from .structures import BSLStructure
from .catalogs import _bound_card, _bound_value
from .catalog_types import BSLCatalogReference

_OMITTED = object()


@dataclass(frozen=True, slots=True, eq=False)
class BSLInformationRegisterType(BSLObject):
    metadata_uuid: UUID
    type_uuid: UUID
    name: str
    snapshot: object = field(repr=False)
    family: str

    def __post_init__(self):
        if (type(self.metadata_uuid) is not UUID or not self.metadata_uuid.int
                or type(self.type_uuid) is not UUID or not self.type_uuid.int
                or type(self.name) is not str or not 1 <= len(self.name) <= 256
                or type(self.family) is not str or self.family not in ('Manager', 'Selection')):
            raise ValueError('invalid information-register type')

    def __eq__(self, other):
        return (type(other) is BSLInformationRegisterType and self.snapshot is other.snapshot
                and self.metadata_uuid == other.metadata_uuid and self.type_uuid == other.type_uuid
                and self.family == other.family)

    def __hash__(self):
        return hash((id(self.snapshot), self.metadata_uuid, self.type_uuid, self.family))

    def __str__(self):
        return ('Регистр сведений менеджер: ' if self.family == 'Manager'
                else 'Регистр сведений выборка: ') + self.name


class BSLInformationRegisters(BSLObject):
    def __init__(self, metadata, context, catalogs, documents):
        self._metadata, self._context = metadata, context
        self._catalogs, self._documents = catalogs, documents
        self._managers = {}

    def get_member(self, name):
        return self.get_index(name)

    def get_index(self, name):
        if type(name) is not str: raise TypeError('information-register name requires String')
        item = self._metadata._snapshot().get(name.casefold())
        if item is None: raise ValueError('information-register name not found')
        if item._metadata_uuid not in self._managers:
            self._managers[item._metadata_uuid] = BSLInformationRegisterManager(self, item)
        return self._managers[item._metadata_uuid]

    def type_by_name(self, name):
        if type(name) is str:
            prefix, separator, item = name.partition('.')
            families = {'informationregistermanager': '_manager_type', 'регистрсведенийменеджер': '_manager_type',
                        'informationregisterselection': '_selection_type', 'регистрсведенийвыборка': '_selection_type'}
            if separator and prefix.casefold() in families:
                return getattr(self.get_index(item), families[prefix.casefold()])
        return self._documents.type_by_name(name)

    def __str__(self):
        raise ValueError('information-register namespace presentation is unsupported')


class BSLInformationRegisterManager(BSLObject):
    def __init__(self, registers, metadata):
        self._registers, self._metadata = registers, metadata
        snapshot = registers._metadata._config_snapshot
        definition = next(row[1] for row in snapshot.register_fields if row[0] == metadata._metadata_uuid)
        generated = {family: uid for family, uid, _ in definition.generated_types}
        self._manager_type = BSLInformationRegisterType(UUID(metadata._metadata_uuid), UUID(generated['Manager']),
            metadata._name, registers._metadata, 'Manager')
        self._selection_type = BSLInformationRegisterType(UUID(metadata._metadata_uuid), UUID(generated['Selection']),
            metadata._name, registers._metadata, 'Selection')

    def _rows(self):
        result = self._registers._context.information_register_rows(self._metadata._name)
        if (result.config_snapshot != self._registers._metadata._config_snapshot
                or result.identity.metadata_uuid != self._metadata._metadata_uuid
                or result.identity.name != self._metadata._name):
            raise ValueError('information-register metadata identity changed')
        return result

    def _fields(self, result, row):
        return {attribute.name.casefold(): _bound_card(attribute).project(
                    _bound_value(attribute, value.value), self._registers._catalogs)
                for attribute, value in zip(result.binding.attributes, row.fields)}

    def _key(self, structure, dimensions):
        if type(structure) is not BSLStructure:
            raise TypeError('information-register key requires Structure')
        wanted = {attribute.name.casefold() for attribute in dimensions}
        if set(structure._items) != wanted:
            raise ValueError('complete bounded information-register key required')
        values = {}
        for attribute in dimensions:
            value = structure.get(attribute.name)
            if attribute.type_token == '#':
                expected = self._registers._catalogs._manager_by_metadata_uuid(UUID(attribute.reference_catalog_uuid))._value_type
                if type(value) is not BSLCatalogReference or value.value_type != expected:
                    raise TypeError('information-register key reference belongs to another type/snapshot')
            else:
                if (type(value) is not Decimal or not value.is_finite()
                        or value != value.to_integral_value() or not 0 <= value <= 999999999):
                    # !todo Negative/fractional dimension normalization and index
                    # ordering need a native key witness, not Number coercion.
                    raise ValueError('information-register numeric key profile unsupported')
            values[attribute.name.casefold()] = value
        return values

    def get(self, key):
        result = self._rows()
        dimensions = result.binding.attributes[:result.binding.dimension_count]
        wanted = self._key(key, dimensions)
        matches = [row for row in result.rows if all(self._fields(result, row)[name] == value for name, value in wanted.items())]
        if len(matches) > 1: raise ValueError('duplicate information-register key')
        resources = result.binding.attributes[result.binding.dimension_count:
            result.binding.dimension_count + result.binding.resource_count]
        found = self._fields(result, matches[0]) if matches else None
        answer = BSLStructure()
        for attribute in resources:
            answer.insert(attribute.name, found[attribute.name.casefold()] if found is not None
                          else _bound_card(attribute).default(self._registers._catalogs))
        return answer

    def select(self, selection=_OMITTED, order=_OMITTED):
        result = self._rows()
        dimensions = result.binding.attributes[:result.binding.dimension_count]
        reference = tuple(attribute for attribute in dimensions if attribute.type_token == '#')
        wanted = {} if selection is _OMITTED else self._key(selection, reference)
        reverse = False
        if order is not _OMITTED:
            if type(order) is not str or order.casefold() not in ('asc', 'desc'):
                raise ValueError('information-register selection order unsupported')
            reverse = order.casefold() == 'desc'
        selected = [row for row in result.rows if all(self._fields(result, row)[name] == value for name, value in wanted.items())]
        def key(row):
            values = []
            for attribute, value in zip(dimensions, row.fields):
                if attribute.type_token == '#': values.append(value.raw)
                else:
                    if value.value < 0:
                        raise ValueError('negative information-register dimension ordering unsupported')
                    values.append(value.value)
            return tuple(values)
        # Actual raw composite dimensions, not slot/insertion/UUID presentation:
        # native reversed field order changes overall ordering in repeat2.
        return BSLInformationRegisterSelection(self, result, tuple(sorted(selected, key=key, reverse=reverse)))

    def get_member(self, name):
        method = {'get': self.get, 'получить': self.get,
                  'select': self.select, 'выбрать': self.select}.get(name.casefold())
        return HostFunction(name, method) if method else super().get_member(name)

    def __str__(self):
        raise ValueError('information-register manager presentation is unsupported')


class BSLInformationRegisterSelection(BSLObject):
    def __init__(self, manager, result, rows):
        self._manager, self._result, self._rows = manager, result, rows
        self._selection_type = manager._selection_type
        self._position = -1
        self._next_position = 0

    def next(self):
        if self._next_position >= len(self._rows): return False
        self._position = self._next_position
        self._next_position += 1
        return True

    def get_method(self, name):
        if name.casefold() in ('next', 'следующий'): return HostFunction(name, self.next)
        return super().get_method(name)

    def get_member(self, name):
        key = name.casefold()
        names = {attribute.name.casefold() for attribute in self._result.binding.attributes}
        if key not in names: return super().get_member(name)
        if self._position < 0: return None
        return self._manager._fields(self._result, self._rows[self._position])[key]

    def __str__(self):
        raise ValueError('information-register selection presentation is unsupported')

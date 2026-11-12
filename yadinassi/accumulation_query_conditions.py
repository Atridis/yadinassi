"""Closed explicit virtual-table dimension conditions, not SQL pushdown.

Bindings retain schema field and record identities only. They perform no reads,
coercion, existence lookup or callback execution. Source rows are validated and
charged in full by the owner before this selector can exclude a movement.
"""
from dataclasses import dataclass
from decimal import Decimal
from types import MethodType
from uuid import UUID

from . import query_parser as syntax
from .accumulation_movements import MAX_DIMENSIONS
from .catalog_types import BSLCatalogReference, BSLCatalogType
from .catalogs import BSLCatalogManager
from .dates import BSLDate
from .enum_types import BSLEnumReference
from .values import NULL

MAX_LIST_MEMBERS = 256


def _issued_method(value, issuer, function):
    # Never use equality on an externally supplied callable. Identity checks
    # on exact bound-method components neither invoke it nor its __eq__.
    return (type(value) is MethodType and value.__self__ is issuer
            and value.__func__ is function)


@dataclass(frozen=True, slots=True)
class DimensionCondition:
    terms: tuple

    def matches(self, values):
        return all(values[field].reference_uuid == record for field, record in self.terms)


def bind_condition(manager, source, parameters, *, typed=False, budget=None):
    node = source.virtual_condition
    if node is None:
        return DimensionCondition(())
    if source.section not in ('balance', 'turnovers', 'balance_and_turnovers'):
        raise ValueError('Dimension conditions require an accumulation virtual source')
    if typed:
        return _bind_typed(manager, node, parameters, budget if budget is not None else [0, 0])
    terms = []

    def bind(node, depth=0):
        if depth > 16:
            raise ValueError('Virtual dimension condition nesting limit exceeded')
        if type(node) is syntax.Predicate:
            if node.kind != 'and' or type(node.terms) is not tuple or not node.terms:
                raise ValueError('Virtual dimension conditions support only AND')
            for part in node.terms:
                bind(part, depth + 1)
            return
        if (type(node) is not syntax.Comparison or node.operator != 'eq'
                or type(node.field) is not syntax.Field or len(node.field.parts) != 1
                or type(node.value) is not syntax.Parameter):
            raise ValueError('Virtual dimension conditions require Dimension = &Parameter')
        fields = [field for field in manager._schema.dimensions
                  if field.name.casefold() == node.field.parts[0].casefold()]
        if len(fields) != 1 or fields[0].kind != 'catalog_ref':
            raise ValueError('Virtual condition requires a declared CatalogRef dimension')
        field = fields[0]
        key = node.value.name.casefold()
        if key not in parameters:
            raise ValueError('Query parameter is not set')
        value = parameters[key]
        if (type(value) is not BSLCatalogReference
                or value.value_type.snapshot is not manager._catalogs._metadata
                or value.value_type.metadata_uuid != field.target_catalog_id):
            raise TypeError('Virtual dimension reference requires same database family and catalog')
        issuer = manager._catalogs._manager_by_metadata_uuid(field.target_catalog_id)
        if (type(issuer) is not BSLCatalogManager
                or value.value_type is not issuer._value_type
                or value.metadata is not issuer._metadata
                or not _issued_method(value.read_member, issuer, BSLCatalogManager._read_member)
                or not _issued_method(value.get_object, issuer, BSLCatalogManager._get_object)):
            raise TypeError('Virtual dimension condition requires an owned catalog reference')
        terms.append((field.identity, value.reference_uuid))
        if len(terms) > MAX_DIMENSIONS:
            raise ValueError('Virtual dimension condition term limit exceeded')

    bind(node)
    return DimensionCondition(tuple(terms))


def _typed_key(value):
    """Only validated scalar/owned row values; never user hash/equality hooks.

    Native typed12 case1 establishes canonical/caseless spelling and trailing
    ASCII space for this selector. Do not change global UCA, residual WHERE or
    legacy dimension grouping, or claim arbitrary regional collation parity.
    """
    if value is NULL:
        return ('null',)
    if type(value) is str:
        from .collation import caseless_string_key
        return ('string', caseless_string_key(value.rstrip(' ')))
    if type(value) is Decimal:
        return ('number', value)
    if type(value) is bool:
        return ('boolean', value)
    if type(value) is BSLDate:
        return ('datetime', value.ticks)
    if type(value) is BSLCatalogReference:
        return ('catalog_ref', value.value_type.metadata_uuid.int, value.reference_uuid.int)
    if type(value) is BSLEnumReference:
        return ('enum_ref', value.value_type.metadata_uuid.int, value.reference_uuid.int)
    raise TypeError('Unsupported virtual dimension value')


@dataclass(frozen=True, slots=True)
class TypedDimensionCondition:
    terms: tuple
    binding: object

    def require_live(self):
        # Revalidate the retained canonical issuer inside the caller's lexical
        # data view, including an empty scan with no enum decoder invocation.
        # No manager discovery, alternate connection or authority is added.
        from .enum_storage_binding import EnumStorageBinding
        if type(self.binding) is not EnumStorageBinding:
            raise TypeError('Invalid typed virtual condition binding')
        EnumStorageBinding._live(self.binding)

    def matches(self, values):
        # At most 16 bounded O(1) memberships per fully decoded source row.
        # Only primitive immutable keys are hashed, not reference objects.
        return all(_typed_key(values[field]) in keys for field, keys in self.terms)


def _owned_catalog(manager, value, field):
    if (type(value.value_type) is not BSLCatalogType
            or type(value.reference_uuid) is not UUID
            or value.value_type.snapshot is not manager._catalogs._metadata):
        raise TypeError('Virtual dimension reference requires the same database family')
    issuer = manager._catalogs._manager_by_metadata_uuid(value.value_type.metadata_uuid)
    if (type(issuer) is not BSLCatalogManager
            or value.value_type is not issuer._value_type
            or value.metadata is not issuer._metadata
            or not _issued_method(value.read_member, issuer, BSLCatalogManager._read_member)
            or not _issued_method(value.get_object, issuer, BSLCatalogManager._get_object)):
        raise TypeError('Virtual dimension condition requires an owned catalog reference')
    # This remains a strict host boundary, not inferred from wrong-enum native
    # observations. No existence lookup or assignment-to-empty conversion.
    if field.kind == 'catalog_ref' and value.value_type.metadata_uuid != field.target_catalog_id:
        raise TypeError('Virtual dimension reference requires the declared catalog')


def _bind_typed(manager, node, parameters, budget):
    from .inventory_enum_runtime import query_binding
    from .queries import _parameter_value, _MAX_CELLS, _MAX_RESULT_TEXT
    from .relational_queries import _ParameterList
    binding = query_binding(manager._catalogs)
    if binding is None:
        raise ValueError('Typed virtual predicates require the enum inventory profile')
    terms = []

    def bind(part, depth=0):
        if depth > 16:
            raise ValueError('Virtual dimension condition nesting limit exceeded')
        if type(part) is syntax.Predicate:
            if part.kind != 'and' or type(part.terms) is not tuple or not part.terms:
                raise ValueError('Virtual dimension conditions support only AND')
            for child in part.terms:
                bind(child, depth + 1)
            return
        member = type(part) is syntax.VirtualMembership
        if not member and (type(part) is not syntax.Comparison or part.operator != 'eq'):
            raise ValueError('Virtual condition requires equality or parameter-array IN')
        parameter = part.values if member else part.value
        if (type(part.field) is not syntax.Field or len(part.field.parts) != 1
                or type(parameter) is not syntax.Parameter):
            raise ValueError('Virtual condition requires Dimension and parameter')
        fields = [f for f in manager._schema.dimensions
                  if f.name.casefold() == part.field.parts[0].casefold()]
        if len(fields) != 1 or fields[0].kind not in (
                'string', 'number', 'boolean', 'datetime', 'catalog_ref', 'enum_ref'):
            raise ValueError('Virtual condition requires a declared typed dimension')
        field = fields[0]
        name = parameter.name.casefold()
        if name not in parameters:
            raise ValueError('Query parameter is not set')
        value = parameters[name]
        if member:
            if type(value) is not _ParameterList or type(value.values) is not tuple:
                raise TypeError('Virtual IN requires an Array or FixedArray parameter')
            values = value.values
            if len(values) > MAX_LIST_MEMBERS:
                raise ValueError('Virtual IN parameter member limit exceeded')
        else:
            values = (value,)
        # Charge each use, including repeated parameters and duplicates, before
        # collation/deduplication. The plan shares this across virtual sources;
        # snapshotting a caller buffer once is not a free key-compilation pass.
        budget[0] += len(values)
        budget[1] += sum(len(value) for value in values if type(value) is str)
        if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
            raise ValueError('Virtual condition binding resource limit exceeded')
        keys = set()
        for value in values:
            if value is NULL:
                continue  # NULL never equals a typed empty reference.
            _parameter_value(value)  # Query bounds, not storage qualifiers.
            if type(value) is BSLEnumReference:
                # Validate canonical issuer even a wrong-enum/nonmatching
                # member; never use assigned(), equality or a caller hook.
                key = binding.owned_key(value)
                owned = ('enum_ref', key.enum_id.int, key.value_id.int)
            else:
                if type(value) is BSLCatalogReference:
                    _owned_catalog(manager, value, field)
                owned = _typed_key(value)
            # Case10 measures Number <- String and same-owned other Enum.
            # Do not generalize to arbitrary cross-kind comparisons.
            if owned[0] != field.kind and not (field.kind == 'number' and type(value) is str):
                raise TypeError('Virtual dimension parameter type is outside the measured profile')
            keys.add(owned)
        terms.append((field.identity, frozenset(keys)))
        if len(terms) > MAX_DIMENSIONS:
            raise ValueError('Virtual dimension condition term limit exceeded')

    bind(node)  # Never short-circuit binding of empty/nonmatching earlier terms.
    return TypedDimensionCondition(tuple(terms), binding)

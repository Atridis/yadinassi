"""Closed explicit virtual-table dimension conditions, not SQL pushdown.

Bindings retain schema field and record identities only. They perform no reads,
coercion, existence lookup or callback execution. Source rows are validated and
charged in full by the owner before this selector can exclude a movement.
"""
from dataclasses import dataclass
from types import MethodType

from . import query_parser as syntax
from .accumulation_movements import MAX_DIMENSIONS
from .catalog_types import BSLCatalogReference
from .catalogs import BSLCatalogManager


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


def bind_condition(manager, source, parameters):
    node = source.virtual_condition
    if node is None:
        return DimensionCondition(())
    if source.section not in ('balance', 'turnovers', 'balance_and_turnovers'):
        raise ValueError('Dimension conditions require an accumulation virtual source')
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

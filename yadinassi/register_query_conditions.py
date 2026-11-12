"""Bounded explicit pre-slice filters for independent information registers.

This uses the existing relational casefold_v1 host policy. It does not infer
WHERE pushdown, normalize assignment values, or claim native query parity.
"""
from dataclasses import dataclass
from types import MethodType
from uuid import UUID

from . import query_parser as syntax
from .catalog_types import BSLCatalogReference, BSLCatalogType
from .catalogs import BSLCatalogManager


def _reference(manager, field, value):
    if (type(value) is not BSLCatalogReference or type(value.value_type) is not BSLCatalogType
            or type(value.reference_uuid) is not UUID
            or value.value_type.snapshot is not manager._catalogs._metadata
            or value.value_type.metadata_uuid != field.target_catalog_id):
        raise TypeError('Slice condition requires an owned reference of the declared catalog')
    issuer = manager._catalogs._manager_by_metadata_uuid(field.target_catalog_id)
    if (type(issuer) is not BSLCatalogManager or value.value_type is not issuer._value_type
            or value.metadata is not issuer._metadata):
        raise TypeError('Slice condition requires a canonical catalog reference')
    for callback, function in ((value.read_member, BSLCatalogManager._read_member),
                               (value.get_object, BSLCatalogManager._get_object)):
        if (type(callback) is not MethodType or callback.__self__ is not issuer
                or callback.__func__ is not function):
            raise TypeError('Slice condition requires an issued catalog reference')


@dataclass(frozen=True, slots=True)
class SliceCondition:
    terms: tuple
    references: tuple

    def require_current(self, manager):
        manager._catalogs._metadata._snapshot()
        for field, value in self.references:
            _reference(manager, field, value)

    def matches(self, values):
        from .relational_queries import _key
        return all(_key(values[field]) in keys for field, keys in self.terms)


def bind_condition(manager, node, parameters, budget):
    from .queries import _parameter_value, _MAX_CELLS, _MAX_RESULT_TEXT
    from .relational_queries import _ParameterList, _key
    terms, references = [], []

    def visit(part, depth=0):
        if depth > 16:
            raise ValueError('Slice condition nesting limit exceeded')
        if type(part) is syntax.Predicate:
            if part.kind != 'and' or type(part.terms) is not tuple or not part.terms:
                raise ValueError('Slice conditions support only AND')
            for child in part.terms:
                visit(child, depth + 1)
            return
        member = type(part) is syntax.VirtualMembership
        if not member and (type(part) is not syntax.Comparison or part.operator != 'eq'):
            raise ValueError('Slice conditions require field equality or IN (&Array)')
        parameter = part.values if member else part.value
        if type(part.field) is not syntax.Field or len(part.field.parts) != 1 or type(parameter) is not syntax.Parameter:
            raise ValueError('Slice conditions require unqualified fields and parameters')
        field_name = part.field.parts[0].casefold()
        if manager._schema.periodic and field_name == 'период': field_name = 'period'
        fields = [f for f in manager._schema.fields if f.name.casefold() == field_name]
        if len(fields) != 1:
            raise ValueError('Unknown slice condition field')
        field = fields[0]
        if field.kind not in ('string', 'number', 'boolean', 'datetime', 'catalog_ref'):
            raise TypeError('Unsupported slice condition field type')
        name = parameter.name.casefold()
        if name not in parameters:
            raise ValueError('Query parameter is not set')
        value = parameters[name]
        if member:
            if type(value) is not _ParameterList:
                raise TypeError('Slice IN requires Array or FixedArray')
            values = value.values
            if len(values) > 256:
                raise ValueError('Slice condition member limit exceeded')
        else:
            values = (value,)
        keys = []
        for value in values:
            _parameter_value(value)
            manager._stored(field, value)  # Exact type, never assignment coercion.
            if field.kind == 'catalog_ref':
                _reference(manager, field, value)
                references.append((field, value))
            budget[0] += 1
            budget[1] += len(value) if type(value) is str else 0
            if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                raise ValueError('Slice condition parameter resource limit exceeded')
            keys.append(_key(value))
        terms.append((field.identity, frozenset(keys)))
        if len(terms) > 16:
            raise ValueError('Slice condition term limit exceeded')

    if node is not None:
        visit(node)
    return SliceCondition(tuple(terms), tuple(references))

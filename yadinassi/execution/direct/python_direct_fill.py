"""Direct FillPropertyValues for structures and mixed detached table/tree rows."""
from yadinassi.collections.structures import _DIRECT_FILL_STRUCTURE_ABI
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure, structure_key
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction

_FILL, _STRUCTURE, _FIXED, _STATE, _COPY = _DIRECT_FILL_STRUCTURE_ABI


def _storage(value, role):
    kind=type(value)
    if kind is _DirectStructure:
        items=value
    elif kind is _STRUCTURE or kind is _FIXED:
        items=dict.get(_STATE.__get__(value,kind),'_items')
        if type(items) is not dict:
            raise BoundaryViolation('invalid canonical structure storage')
    else:
        raise TypeError('ЗаполнитьЗначенияСвойств: '+role+' должен быть структурой')
    # No arbitrary hashing, equality, attribute or payload protocols. Malformed
    # storage is distinct from lazily validated user selection tokens.
    for key,entry in dict.items(items):
        if (type(key) is not str or type(entry) is not tuple or len(entry)!=2
                or type(entry[0]) is not str or structure_key(entry[0])!=key):
            raise BoundaryViolation('invalid canonical structure entry')
    return items


def fill(target,source,properties=None,exclude=None):
    # Preserve the already-registered canonical host contract when no direct
    # storage participates. This is not a conversion or retry: direct storage
    # never reaches database adapters or the runtime evaluator.
    target_direct = type(target) is _DirectStructure
    source_direct = type(source) is _DirectStructure
    if not target_direct and not source_direct:
        if not ((type(target) is _STRUCTURE or type(target) is _FIXED)
                and (type(source) is _STRUCTURE or type(source) is _FIXED)):
            return _FILL(target,source,properties,exclude)
    elif target_direct != source_direct:
        other = source if target_direct else target
        if type(other) is not _STRUCTURE and type(other) is not _FIXED:
            from yadinassi.collections.plain_value_table_runtime import BSLValueTableRow
            from yadinassi.collections.value_trees import BSLValueTreeRow
            other_kind = type(other)
            if other_kind is BSLValueTableRow or other_kind is BSLValueTreeRow:
                from yadinassi.collections.property_transfer import fill_structure_row
                return fill_structure_row(target, source, properties, exclude)
    target_items=_storage(target,'приемник')
    source_items=_storage(source,'источник')
    return _COPY(target_items,source_items,properties,exclude,
        target_fixed=type(target) is _FIXED,source_mutable=type(source) is not _FIXED)


def resolve_fill(context,function,*,name=None,require_value=False,allow_references=False,argument_count=None):
    if type(function) is not HostFunction or function.function is not _FILL:return None
    context._check()
    if argument_count is not None and not 2<=argument_count<=4:
        raise TypeError('ЗаполнитьЗначенияСвойств ожидает от 2 до 4 аргументов')
    context._validate_host_function(function,require_value,allow_references)
    def invoke(*args):
        context._check()
        if function.function is not _FILL:raise BoundaryViolation('fill implementation changed during argument evaluation')
        context._before('call' if name is not None else 'call_value',name or function.name.casefold())
        try:
            if function.function is not _FILL:raise BoundaryViolation('fill implementation changed at policy boundary')
            return fill(*args)
        except PermissionError as error:raise BoundaryViolation(str(error)) from error
        finally:context._check()
    if allow_references:invoke.requires_reference=lambda index:index in function.reference_parameters
    def prepare_omissions(bound,positions,count):
        context._check()
        if not 2<=count<=4:raise TypeError('ЗаполнитьЗначенияСвойств ожидает от 2 до 4 аргументов')
        if any(index<2 for index in positions):
            from yadinassi.execution.codegen.experimental_naked_collections import _host_omission_error
            _host_omission_error()
        return bound,{index:None for index in positions}
    invoke.prepare_omissions=prepare_omissions
    return invoke

"""Second/Independent temporal reads measured in native41380811903.

No posting, record manager, totals, recorder position or user-database writes.
"""
from decimal import Decimal
from .dates import BSLDate, _date_from_datetime, TICKS_PER_SECOND
from .structures import BSLStructure
from .value_tables import BSLValueTable
from .type_descriptions import BSLTypeDescription
from .information_registers import _OMITTED, BSLInformationRegisterSelection
from .catalogs import _bound_card


def _require(result):
    if result.identity.periodicity != 5 or result.identity.write_mode != 0:
        raise ValueError('Second independent register required')


def _date(value):
    if type(value) is not BSLDate:
        raise TypeError('temporal register boundary requires Date')
    value.require_known()
    if value.ticks % TICKS_PER_SECOND:
        # !todo Subsecond, Boundary and PointInTime normalization not measured.
        raise ValueError('whole-second register boundary required')
    return value.ticks


def _period(row):
    return _date_from_datetime(row.fields[0].value)


def _dimensions(result):
    return result.binding.attributes[:result.binding.dimension_count]


def _dimension_key(result,row):
    values=[]
    for attribute,value in zip(_dimensions(result),row.fields[1:]):
        if attribute.type_token == '#':values.append(value.raw)
        else:
            if value.value < 0:raise ValueError('negative dimension ordering unsupported')
            values.append(value.value)
    return tuple(values)


def _filter(manager,result,selection,*,full=False):
    dimensions=_dimensions(result)
    if selection is _OMITTED and not full:return {}
    if type(selection) is BSLStructure and not selection._items and not full:return {}
    if not full:
        names=set(selection._items) if type(selection) is BSLStructure else set()
        if names == {a.name.casefold() for a in dimensions if a.type_token=='#'}:
            dimensions=tuple(a for a in dimensions if a.type_token=='#')
    return manager._key(selection,dimensions)


def _matched(manager,result,wanted):
    return [row for row in result.rows if all(manager._fields(result,row)[name]==value for name,value in wanted.items())]


def _resource_structure(manager,result,row):
    resources=result.binding.attributes[result.binding.dimension_count:result.binding.dimension_count+result.binding.resource_count]
    values=manager._fields(result,row) if row is not None else None
    answer=BSLStructure()
    for attribute in resources:
        answer.insert(attribute.name,values[attribute.name.casefold()] if values is not None
                      else _bound_card(attribute).default(manager._registers._catalogs))
    return answer


def get_edge(manager,boundary,key,*,last):
    result=manager._rows();_require(result);tick=_date(boundary)
    wanted=_filter(manager,result,key,full=True)
    selected=[r for r in _matched(manager,result,wanted)
              if (_period(r).ticks<=tick if last else _period(r).ticks>=tick)]
    row=(max if last else min)(selected,key=lambda r:_period(r).ticks) if selected else None
    return _resource_structure(manager,result,row)


def select(manager,start=_OMITTED,end=_OMITTED,selection=_OMITTED,order=_OMITTED):
    result=manager._rows();_require(result)
    low=None if start is _OMITTED else _date(start);high=None if end is _OMITTED else _date(end)
    # Select admits one indexed reference filter only, not the slice full key.
    reference=tuple(a for a in _dimensions(result) if a.type_token=='#')
    wanted={} if selection is _OMITTED else manager._key(selection,reference)
    reverse=False
    if order is not _OMITTED:
        if type(order) is not str or order.casefold() not in ('asc','desc'):
            raise ValueError('periodic register order unsupported')
        reverse=order.casefold()=='desc'
    rows=[r for r in _matched(manager,result,wanted)
          if (low is None or _period(r).ticks>=low) and (high is None or _period(r).ticks<=high)]
    return BSLInformationRegisterSelection(manager,result,tuple(sorted(rows,
        key=lambda r:(_period(r).ticks,*_dimension_key(result,r)),reverse=reverse)))


def slice_edge(manager,boundary,selection=_OMITTED,*,last):
    result=manager._rows();_require(result);tick=_date(boundary)
    wanted=_filter(manager,result,selection)
    groups={}
    for row in _matched(manager,result,wanted):
        period=_period(row).ticks
        if not (period<=tick if last else period>=tick):continue
        key=_dimension_key(result,row);previous=groups.get(key)
        if previous is None or (period>_period(previous).ticks if last else period<_period(previous).ticks):
            groups[key]=row
    # !todo Date column descriptor remains provisional until final native probe.
    table=BSLValueTable();table.columns.add('Период',BSLTypeDescription('Date'))
    for attribute in result.binding.attributes:table.columns.add(attribute.name)
    # !todo Slice row ordering beyond measured raw key profile requires evidence.
    for row in groups.values():
        item=table.add();item.set_member('Период',_period(row));values=manager._fields(result,row)
        for attribute in result.binding.attributes:item.set_member(attribute.name,values[attribute.name.casefold()])
    table._bounded_slice_read = True
    return table

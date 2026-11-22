"""Narrow allocation limits for direct native lists, not VM execution wrappers.

The units match values.BSLArray: slots plus non-root nested Array objects for
construction, and the existing Insert growth bound. Compare Decimal sizes before
int conversion so enormous exponents cannot materialize enormous Python integers.
"""
from decimal import Decimal
from yadinassi.types import values
from yadinassi.execution.direct.python_direct_plain_array import PlainArray


def array_widths(dimensions=(), *, max_slots=None, max_dimensions=None):
    sizes=tuple(dimensions) or (Decimal(0),)
    limit=values._MAX_ARRAY_CONSTRUCTION if max_slots is None else max_slots
    dimension_limit=values._MAX_ARRAY_DIMENSIONS if max_dimensions is None else max_dimensions
    if len(sizes)>dimension_limit:
        raise ValueError('Массив: превышен предел измерений Yadinassi (64)')
    # Validate all dimensions before any allocation or integer materialization.
    for size in sizes:
        if type(size) is not Decimal:raise TypeError('Ожидается число')
        if not size.is_finite() or size!=size.to_integral_value():raise ValueError('Ожидается целое число')
        if size<0:raise ValueError('Размер массива не может быть отрицательным')
        if len(sizes)>1 and size==0:raise ValueError('Размеры многомерного массива должны быть положительными')
    widths=[];parents=1;cost=0
    for depth,size in enumerate(sizes):
        if depth:cost+=parents
        remaining=limit-cost
        if parents and (remaining<0 or size>remaining//parents):
            raise ValueError('Массив: превышен предел ресурсов Yadinassi (1000000 элементов и вложенных массивов)')
        width=int(size) if parents else 0
        widths.append(width);parents*=width;cost+=parents
    return tuple(widths)


def bounded_array(*dimensions, max_slots=None, max_dimensions=None):
    if not dimensions:
        # Zero slots and no child arrays are statically known. Keep live limits,
        # but do not run Decimal/shape traversal to prove the empty allocation.
        slots=values._MAX_ARRAY_CONSTRUCTION if max_slots is None else max_slots
        dims=values._MAX_ARRAY_DIMENSIONS if max_dimensions is None else max_dimensions
        if slots<0 or dims<1:raise ValueError('Массив: превышен предел ресурсов Yadinassi')
        return []
    if len(dimensions)==1 and type(dimensions[0]) is values.BSLFixedArray:
        return _copy_fixed_array(dimensions[0],max_slots,max_dimensions)
    widths=array_widths(dimensions,max_slots=max_slots,max_dimensions=max_dimensions)
    def create(depth):
        if depth==len(widths)-1:return [None]*widths[depth]
        return [create(depth+1) for _ in range(widths[depth])]
    return create(0)


def bounded_insert(array,index,value=None,*,max_growth=None):
    if type(array) is not list and type(array) is not PlainArray:raise TypeError('Ожидается массив')
    if type(index) is not Decimal:raise TypeError('Ожидается число')
    if not index.is_finite() or index!=index.to_integral_value():raise ValueError('Ожидается целое число')
    if index<0:raise IndexError('Индекс массива вне границ')
    limit=values._MAX_INSERT_GROWTH if max_growth is None else max_growth
    length=list.__len__(array)
    if index>=length+limit:
        raise ValueError('Вставить: превышен предел роста массива Yadinassi (1000000 элементов)')
    offset=int(index)
    if offset<length:list.insert(array,offset,value)
    else:
        # Prepare the full tail before publishing any mutation, as the VM does.
        tail=[None]*(offset-length);tail.append(value);list.extend(array,tail)


def _copy_fixed_array(source,max_slots,max_dimensions):
    """Preflight exact fixed snapshots before allocating native mutable arrays."""
    limit=values._MAX_ARRAY_CONSTRUCTION if max_slots is None else max_slots
    depth_limit=values._MAX_ARRAY_DIMENSIONS if max_dimensions is None else max_dimensions
    active=set();cost=0
    def check(array,depth):
        nonlocal cost
        if depth>depth_limit:raise ValueError('Массив: превышен предел измерений Yadinassi')
        items=object.__getattribute__(array,'items')
        if type(items) is not tuple:raise TypeError('Некорректный фиксированный массив')
        identity=id(array)
        if identity in active:raise ValueError('Циклический фиксированный массив не поддерживается')
        cost+=len(items)+(depth>1)
        if cost>limit:raise ValueError('Массив: превышен предел ресурсов Yadinassi')
        active.add(identity)
        try:
            for item in items:
                if type(item) is values.BSLFixedArray:check(item,depth+1)
                elif any(base is values.BSLFixedArray for base in type.__getattribute__(type(item),'__mro__')):
                    raise TypeError('Подкласс фиксированного массива не поддерживается')
        finally:active.remove(identity)
    try:check(source,1)
    finally:del check
    def copy(array):
        return [copy(item) if type(item) is values.BSLFixedArray else item
                for item in object.__getattribute__(array,'items')]
    try:return copy(source)
    finally:del copy

"""Read-only scalar fields of an exact canonical diagnostic snapshot."""
from yadinassi.types.error_info import _DIRECT_SNAPSHOT_ABI, _DIRECT_CATEGORY_ABI, _DIRECT_CATEGORY_SETS
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from decimal import Decimal
from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI

_HostFunction=_DIRECT_COLLECTION_CLASS_ABI[3][0]

BSLErrorInfo,_STATE,_CATEGORIES,_EMPTY_CATEGORIES=_DIRECT_SNAPSHOT_ABI
_ALL,_OTHER,_COMPILE,_RUNTIME,_RAISED,_CONFIGURATION=_DIRECT_CATEGORY_ABI
_QUERY_NAMES=('iserrorofcategory','являетсяошибкойкатегории')

_FIELDS={alias:field for field,aliases in (
    ('description',('description','описание')),
    ('code',('code','код')),
    ('additional_information',('additionalinformation','дополнительнаяинформация')),
    ('cause',('cause','причина')),
    ('module_name',('modulename','имямодуля')),
    ('line_number',('linenumber','номерстроки')),
    ('initial_string',('initialstring','исходнаястрока')),
) for alias in aliases}

def owns(value):return type(value) is BSLErrorInfo

def read(context,value,name):
    context._check()
    if name.casefold() in _QUERY_NAMES:
        return _HostFunction(name,_CategoryQuery(value))
    field=_FIELDS.get(name.casefold())
    if field is None:raise ValueError('Свойство не найдено: '+name)
    state=_STATE.__get__(value,BSLErrorInfo)
    result=dict.get(state,field)
    expected=int if field=='line_number' else str
    if field=='cause':
        if result is not None and type(result) is not BSLErrorInfo:
            raise BoundaryViolation('invalid canonical error cause')
    elif type(result) is not expected or (field=='line_number' and result<0):
        raise BoundaryViolation('invalid canonical error field')
    return Decimal(result) if field=='line_number' else result


def snapshot(description='',*,module_name='',line_number=0,initial_string='',empty=False,
             code='',additional_information='',cause=None,categories=None):
    if (type(description) is not str or type(module_name) is not str or
            type(line_number) is not int or line_number<0 or type(initial_string) is not str):
        raise BoundaryViolation('invalid direct diagnostic fields')
    value=object.__new__(BSLErrorInfo)
    state=_STATE.__get__(value,BSLErrorInfo)
    dict.update(state,description=description,code=code,additional_information=additional_information,cause=cause,
        categories=(_EMPTY_CATEGORIES if empty else _CATEGORIES) if categories is None else categories,module_name=module_name,
        line_number=line_number,initial_string=initial_string,_empty=empty)
    return value


def _category(value):
    if not any(value is member for member in _DIRECT_CATEGORY_ABI):
        raise TypeError('Ожидается значение КатегорияОшибки')
    return value


def _chain(value):
    """Finite raw canonical state; never invoke a diagnostic's Python hooks."""
    seen=set()
    while value is not None:
        if type(value) is not BSLErrorInfo or id(value) in seen or len(seen)>=1024:
            raise BoundaryViolation('invalid or excessive canonical error cause chain')
        seen.add(id(value))
        state=_STATE.__get__(value,BSLErrorInfo)
        categories=dict.get(state,'categories')
        if (type(categories) is not frozenset or
                any(not any(member is known for known in _DIRECT_CATEGORY_ABI) for member in categories)):
            raise BoundaryViolation('invalid canonical error categories')
        if type(dict.get(state,'_empty')) is not bool:
            raise BoundaryViolation('invalid canonical empty error flag')
        for field in ('description','code','additional_information','module_name','initial_string'):
            if type(dict.get(state,field)) is not str:
                raise BoundaryViolation('invalid canonical error field')
        line=dict.get(state,'line_number')
        if type(line) is not int or line<0:raise BoundaryViolation('invalid canonical error line')
        yield state
        value=dict.get(state,'cause')


class _CategoryQuery:
    __slots__=('value',)
    def __init__(self,value):self.value=value
    def __call__(self,category):
        category=_category(category)
        result=False
        for state in _chain(self.value):
            result=result or any(member is category for member in dict.get(state,'categories'))
        return result


def resolve_query(context,value,name,*,require_value=False,omitted=()):
    context._check()
    if name.casefold() not in _QUERY_NAMES:raise ValueError('Метод не найден: '+name)
    if omitted:raise TypeError('Ожидается значение КатегорияОшибки')
    return context.resolve_callable(_HostFunction(name,_CategoryQuery(value)),require_value=require_value)


def raise_arity_error(description):
    raise TypeError('ВызватьИсключение ожидает не более 5 аргументов')


def raise_error(context,description,arguments,source,line,column,source_line):
    """Called after ordered source evaluations; constructs no interpreter frame."""
    context._check()
    if len(arguments)>4:raise TypeError('ВызватьИсключение ожидает не более 5 аргументов')
    category,code,additional,cause=arguments+(None,)*(4-len(arguments))
    from yadinassi.types.errors import BSLRuntimeError
    if category is not None:
        _category(category)
        if category is not _CONFIGURATION:
            message='Недопустимая категория ВызватьИсключение'
            reason=snapshot(message,categories=_DIRECT_CATEGORY_SETS[1])
            info=snapshot(message,cause=reason,module_name=source,line_number=line,initial_string=source_line)
            raise BSLRuntimeError(message,source,line,column,info=info,source_line=source_line)
    if code is not None and type(code) is not str:raise TypeError('Код ошибки должен быть строкой')
    if additional is not None and type(additional) is not str:
        raise TypeError('Дополнительная информация должна быть строкой')
    if cause is not None and type(cause) is not BSLErrorInfo:
        raise TypeError('Причина должна иметь тип ИнформацияОбОшибке')
    categories=(_ALL,_RUNTIME,_RAISED)+(() if category is None else (category,))
    if cause is not None:
        states=list(_chain(cause))
        if dict.get(states[0],'_empty'):
            categories+=tuple(dict.get(states[0],'categories'));cause=None
    mask=sum(1 << index for index,member in enumerate(_DIRECT_CATEGORY_ABI)
        if any(member is category for category in categories))
    info=snapshot(description,code=code or '',additional_information=additional or '',cause=cause,
        categories=_DIRECT_CATEGORY_SETS[mask],module_name=source,line_number=line,initial_string=source_line)
    raise BSLRuntimeError(description,source,line,column,info=info,source_line=source_line)

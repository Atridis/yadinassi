"""Conservative receiver facts plus one admission at a real origin boundary."""
from dataclasses import dataclass
from decimal import Decimal
from yadinassi.syntax import ast
from weakref import ref


@dataclass(frozen=True, slots=True)
class Entry:
    kind: str
    aliases: tuple
    receiver: type
    method: str
    result: str | None
    effect: str


class _OpaqueLocal(Exception):
    pass


def analyze(program, *, database, local_slots=None):
    lexical=local_slots is not None
    entries = _TABLE_ENTRIES + (_QUERY_ENTRIES if database else ())
    methods = {(item.kind, name): item for item in entries for name in item.aliases}
    calls, origins = {}, set()
    constructed=executed=False

    def expression(node, facts):
        nonlocal constructed,executed
        kind = type(node)
        if kind is ast.Group:return expression(node.expression,facts)
        if kind is ast.Name:
            fact=facts.get(node.name.casefold())
            if lexical and fact is None:raise _OpaqueLocal
            return fact, lexical
        if kind is ast.Literal:
            if not lexical:return None,False
            if (type(node.value) is str or type(node.value) is Decimal or type(node.value) is bool
                    or type(node.value) is int or node.value is None):
                return 'scalar',True
            raise _OpaqueLocal
        if kind is ast.New:
            if lexical:
                if constructed or any(expression(arg,facts)[0]!='scalar' for arg in node.arguments):
                    raise _OpaqueLocal
                constructed=True
            facts.clear()
            name=node.name.casefold()
            if database and name in ('query','запрос'):return 'query', False
            if not node.arguments and name in ('valuetable','таблицазначений'):
                origins.add(id(node))
                return 'table', True
            if lexical:raise _OpaqueLocal
            return None, False
        if kind is ast.Call and type(node.callee) is ast.Attribute and not node.arguments:
            receiver, fresh = expression(node.callee.object,facts)
            entry = methods.get((receiver,node.callee.name.casefold()))
            if entry is not None:
                if lexical and entry.effect=='database':
                    if executed:raise _OpaqueLocal
                    executed=True
                calls[id(node)] = entry,fresh
                if entry.effect=='database':facts.clear()
                return entry.result or ('scalar' if lexical else None),fresh or entry.effect=='database'
        # Opaque calls, dynamic expressions, and unmodeled state effects
        # cannot propagate a capability, even when they happen to return it.
        if lexical:raise _OpaqueLocal
        facts.clear()
        return None, False

    def statements(block, facts):
        for node in block:
            kind = type(node)
            if kind is ast.Assign and type(node.target) is ast.Name:
                result,_=expression(node.value,facts)
                # A named result is a type hint, but un-published old storage
                # may retain Python objects. Detached methods need a fresh
                # result in the same expression, not merely the same type.
                if result:facts[node.target.name.casefold()]=result
                else:facts.clear()
            elif kind is ast.ExpressionStatement:
                expression(node.expression,facts)
            elif kind in (ast.For,ast.While,ast.ForEach):
                statements(node.body,{})
                facts.clear()
            elif kind is ast.If:
                for _,body in node.branches:statements(body,{})
                statements(node.otherwise,{})
                facts.clear()
            else:facts.clear()
    if lexical:
        # Only an uninterrupted prefix of unboxed routine-local storage is
        # eligible. It contains no previous opaque value whose release could
        # invoke Python, and no alias can escape to a mutable host slot.
        facts={}
        try:
            for node in program:
                kind=type(node)
                if kind is ast.Assign and type(node.target) is ast.Name and node.target.name.casefold() in local_slots:
                    facts[node.target.name.casefold()]=expression(node.value,facts)[0]
                elif kind is ast.ExpressionStatement:
                    expression(node.expression,facts)
                elif kind is ast.Var and all(name.casefold() in local_slots for name in node.names):
                    for name in node.names:facts.setdefault(name.casefold(),'scalar')
                elif kind is ast.Return:
                    if node.value is not None:expression(node.value,facts)
                    break
                else:
                    break
        except _OpaqueLocal:
            pass
    else:
        statements(program,{})
    return calls,origins


def _plain_abi(kind,methods):
    if kind.__getattribute__ is not object.__getattribute__ or hasattr(kind,'__getattr__'):
        return False
    for _,name,fn,code in methods:
        if getattr(kind,name) is not fn or fn.__code__ is not code:return False
    return True


def _query_selection_abi():
    return (_query_module.BSLQueryResultSelection is BSLQueryResultSelection
            and _plain_abi(BSLQueryResultSelection,_SELECTION_CONSTRUCTOR_METHODS))


def _rows(result):
    rows=type(result._rows)
    return rows is tuple or rows is list


def generic_call(context,value,spelling,require_value):
    # A retained or re-entrant generic call can invoke arbitrary Python.
    # Regardless of what it returns, it cannot arm the enclosing origin.
    try:
        return context.resolve_member_call(value,spelling,require_value=require_value)()
    finally:
        context._known_methods_live=0
        context._known_method_origin=None


def execute(context,value,spelling,require_value):
    # A generic Execute never certifies the next detached operation.
    context._known_methods_live=0
    context._known_method_origin=None
    if (not context._known_method_db or type(value) is not BSLQuery or context.policy is not None
            or not _plain_abi(BSLQuery,_QUERY_EXECUTE_METHODS)
            or 'execute' in vars(value) or 'get_method' in vars(value)):
        return generic_call(context,value,spelling,require_value)
    context._check_effect()
    if value._catalogs is not context.vm._catalogs:
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        raise BoundaryViolation('unregistered or foreign database receiver')
    try:
        result=_QUERY_EXECUTE_METHODS[0][2](value)
    finally:
        context._check_effect()
    if (type(result) is BSLQueryResult and _query_selection_abi()
            and _plain_abi(BSLQueryResult,_RESULT_METHODS)
            and 'select' not in vars(result) and 'get_method' not in vars(result)
            and _rows(result)):
        context._known_methods_live=1
        context._known_method_origin=ref(result)
    return result



def detached_after_publication(context,value,kind):
    # Named slots preserve their original publication. A rare Python finalizer
    # may change the receiver or selected dispatch, so use the live origin and
    # the one applicable method pair rather than a full context audit.
    origin=context._known_method_origin
    if origin is None or context.policy is not None:return False
    result=origin()
    if kind=='query-selection':
        return (context._known_methods_live==1 and result is not None and type(value) is BSLQueryResultSelection
                and _plain_abi(BSLQueryResultSelection,_SELECTION_METHODS)
                and 'next' not in vars(value) and 'get_method' not in vars(value)
                and value._result is result and type(value._exhausted) is bool and type(value._position) is int
                and BSLQueryResult.__getattribute__ is object.__getattribute__ and _rows(result))
    if kind=='table':
        return (context._known_methods_live==2 and value is result and _table(value))
    return (context._known_methods_live==1 and value is result
            and _plain_abi(BSLQueryResult,_RESULT_METHODS) and _query_selection_abi()
            and 'select' not in vars(value) and 'get_method' not in vars(value) and _rows(result))


def _table(value):
    return (type(value) is BSLValueTable and _plain_abi(BSLValueTable,_TABLE_METHODS)
            and 'count' not in vars(value) and 'get_method' not in vars(value) and type(value.rows) is list)


def construct_table(context,value):
    # The existing constructor path already checked the live exact factory.
    context._known_methods_live=0
    context._known_method_origin=None
    if context._known_method_local and context.policy is None and _table(value):
        context._known_methods_live=2
        context._known_method_origin=ref(value)
    return value


from yadinassi.db.query import queries as _query_module
from yadinassi.db.query.queries import BSLQuery,BSLQueryResult,BSLQueryResultSelection,_DIRECT_METHODS
from yadinassi.collections.value_tables import BSLValueTable,_DIRECT_REGION_ABI,_DIRECT_REGION_FUNCTIONS

_QUERY_ENTRIES = (
    Entry('query',('execute','выполнить'),BSLQuery,'execute','query-result','database'),
    Entry('query-result',('select','выбрать'),BSLQueryResult,'select','query-selection','detached'),
    Entry('query-selection',('next','следующий'),BSLQueryResultSelection,'next',None,'detached'),
)
_TABLE_ENTRIES=(Entry('table',('count','количество'),BSLValueTable,'count',None,'detached'),)
_QUERY_EXECUTE_METHODS,_QUERY_DETACHED_METHODS=_DIRECT_METHODS
_RESULT_METHODS,_SELECTION_CONSTRUCTOR_METHODS=(
    tuple(entry for entry in _QUERY_DETACHED_METHODS if entry[0] is kind)
    for kind in (BSLQueryResult,BSLQueryResultSelection))
_SELECTION_METHODS=tuple(entry for entry in _SELECTION_CONSTRUCTOR_METHODS if entry[1]!='__init__')
_TABLE_METHODS=tuple((kind,name,fn,next(code for saved,code,*_ in _DIRECT_REGION_FUNCTIONS if saved is fn))
    for kind,_,attrs in _DIRECT_REGION_ABI if kind is BSLValueTable
    for name,fn in attrs if name in ('count','get_method'))

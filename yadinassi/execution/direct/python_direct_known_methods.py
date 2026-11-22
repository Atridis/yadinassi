"""Conservative receiver facts plus one admission at a real origin boundary."""
from dataclasses import dataclass
from decimal import Decimal
from yadinassi.syntax import ast
from weakref import ref
from .python_direct_static_module import ordered_if


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


_RETURNED = object()
_MAX_LOOP_PROBES = 8


def _common_facts(left, right):
    return {name: kind for name, kind in left.items() if right.get(name) == kind}


def analyze(program, *, database, local_slots=None):
    lexical=local_slots is not None
    entries = _TABLE_ENTRIES + (_QUERY_ENTRIES if database else ())
    methods = {(item.kind, name): item for item in entries for name in item.aliases}
    calls, origins, selection_reads, selection_adds = {}, set(), set(), set()
    loop_probes = {}
    # The lexical phase distinguishes kinds, not individual objects. Keep
    # the existing single-origin rule across the whole routine, including
    # mutually exclusive arms; never relicense an earlier alias.
    constructed=executed=False
    record=True
    loop_depth=0

    def expression(node, facts):
        nonlocal constructed,executed
        kind = type(node)
        if kind is ast.Group:return expression(node.expression,facts)
        if kind is ast.Name:
            fact=facts.get(node.name.casefold())
            if lexical and fact is None:raise _OpaqueLocal
            return fact, lexical
        if kind is ast.Literal:
            if (type(node.value) is str or type(node.value) is Decimal or type(node.value) is bool
                    or type(node.value) is int or node.value is None):
                return 'scalar',lexical
            if lexical:raise _OpaqueLocal
            facts.clear()
            return None,False
        if kind is ast.Unary and node.operator in ('NOT','+','-'):
            operand,_=expression(node.operand,facts)
            if operand != 'scalar':
                if lexical:raise _OpaqueLocal
                facts.clear()
                return None,False
            return 'scalar',False
        if kind is ast.Binary and node.operator in ('AND','OR','=','<>','<','<=','>','>=','+','-','*','/','%'):
            left,_=expression(node.left,facts)
            if lexical and left != 'scalar' and not (node.operator=='+' and left=='selection-value'):
                raise _OpaqueLocal
            if node.operator in ('AND','OR'):
                reached=facts.copy()
                right,_=expression(node.right,reached)
                common=_common_facts(facts,reached)
                facts.clear()
                facts.update(common)
            else:
                right,_=expression(node.right,facts)
            if (node.operator=='+'
                    and 'selection-value' in (left,right)
                    and left in ('scalar','selection-value') and right in ('scalar','selection-value')):
                # A detached projection's value domain is not a receiver fact.
                # Keep the cursor's provenance through this expression only
                # with a live exact-operand guard at the eventual addition.
                if record:selection_adds.add(id(node))
                return 'scalar',False
            if left != 'scalar' or right != 'scalar':
                if lexical:raise _OpaqueLocal
                facts.clear()
                return None,False
            return 'scalar',False
        if kind is ast.Conditional:
            condition,_=expression(node.condition,facts)
            if lexical and condition != 'scalar':raise _OpaqueLocal
            true_facts,false_facts=facts.copy(),facts.copy()
            left,left_fresh=expression(node.when_true,true_facts)
            right,right_fresh=expression(node.when_false,false_facts)
            facts.clear()
            facts.update(_common_facts(true_facts,false_facts))
            if left==right:return left,left_fresh and right_fresh
            if lexical:raise _OpaqueLocal
            return None,False
        if kind is ast.New:
            # Probes cannot carry a new origin around a backedge. Existing
            # module body calls still get their guarded, intra-run lowering
            # when actually recorded. A lexical phase is single-origin.
            if loop_depth and (lexical or not record):
                if lexical:raise _OpaqueLocal
                facts.clear()
                return None,False
            if lexical:
                if constructed or any(expression(arg,facts)[0]!='scalar' for arg in node.arguments):
                    raise _OpaqueLocal
                constructed=True
            facts.clear()
            name=node.name.casefold()
            if database and name in ('query','запрос'):return 'query', False
            if not node.arguments and name in ('valuetable','таблицазначений'):
                if record:origins.add(id(node))
                return 'table', True
            if lexical:raise _OpaqueLocal
            return None, False
        if database and kind is ast.Attribute:
            owner=node.object
            while type(owner) is ast.Group:owner=owner.expression
            # Only a tracked local/standalone name; do not walk or infer the
            # effects of arbitrary dereference chains.
            if type(owner) is ast.Name and facts.get(owner.name.casefold())=='query-selection':
                if record:selection_reads.add(id(node))
                # An admitted selection read doesn't execute SQL or mutate the
                # cursor. The value itself may be a ref, NULL, a method, etc.
                # Never use it as a scalar or a new receiver fact.
                return 'selection-value', False
        if kind is ast.Call and type(node.callee) is ast.Attribute and not node.arguments:
            receiver, fresh = expression(node.callee.object,facts)
            entry = methods.get((receiver,node.callee.name.casefold()))
            if entry is not None:
                if entry.effect=='database':
                    if loop_depth and (lexical or not record):
                        if lexical:raise _OpaqueLocal
                        facts.clear()
                        return None,False
                    if lexical:
                        if executed:raise _OpaqueLocal
                        executed=True
                if record:calls[id(node)] = entry,fresh
                if entry.effect=='database':facts.clear()
                return entry.result or 'scalar',fresh or entry.effect=='database'
        # Opaque calls, dynamic expressions, and unmodeled state effects
        # cannot propagate a capability, even when they happen to return it.
        if lexical:raise _OpaqueLocal
        facts.clear()
        return None, False

    def loop(node, incoming):
        nonlocal record,loop_depth
        counted=type(node) is ast.For
        counter=None
        if counted:
            # Bounds are evaluated once, before the start value replaces the
            # counter's old value. An opaque bound can invalidate the origin.
            start,_=expression(node.start,incoming)
            end,_=expression(node.end,incoming)
            counter=node.name.casefold()
            if lexical and (counter not in local_slots or start!='scalar' or end!='scalar'):
                return None
            if start!='scalar' or end!='scalar':incoming.clear()
            else:incoming[counter]='scalar'

        def pass_at(header):
            body_facts=header.copy()
            if not counted:
                condition,_=expression(node.condition,body_facts)
                if lexical and condition!='scalar':return None
            exit_facts=body_facts.copy()
            continued,broken=[],[]
            fallthrough=statements(node.body,body_facts,(continued,broken))
            if fallthrough is None:return None
            if fallthrough is not _RETURNED:continued.append(fallthrough)
            if counted:
                # The actual increment can invoke unknown code if the
                # iteration variable was rebound to an opaque value.
                continued=[path if path.get(counter)=='scalar' else {} for path in continued]
            return exit_facts,continued,broken

        header=incoming.copy()
        previous_record=record
        loop_depth+=1
        try:
            try:
                # Speculative visits cannot publish call sites: the first
                # iteration may know a receiver that a backedge invalidates.
                record=False
                probes=loop_probes.setdefault(id(node),{})
                while True:
                    # Outer probes revisit nested loops with the same headers.
                    # Bound distinct headers per syntax node as well: uncommon
                    # deeper refinements can safely use ordinary dispatch.
                    key=frozenset(header.items())
                    if key not in probes:
                        if len(probes)>=_MAX_LOOP_PROBES:return None
                        probes[key]=pass_at(header)
                    paths=probes[key]
                    if paths is None:return None
                    refined=header
                    for edge in paths[1]:refined=_common_facts(refined,edge)
                    if refined==header:break
                    header=refined
            finally:record=previous_record
            if record:
                # Record only stabilized call sites; intra-loop origins may
                # lower local operations but do not alter the proven exits.
                pass_at(header)
            exit_facts,_,broken=paths
            for edge in broken:exit_facts=_common_facts(exit_facts,edge)
            # A caller may mutate its outgoing facts; never expose the memo.
            return exit_facts if broken else exit_facts.copy()
        finally:loop_depth-=1

    def statements(block, facts, loop_edges=None):
        # None is an opaque fallthrough, not an empty set of proven facts:
        # the lexical proof may not restart after an unknown effect.
        try:
            for node in block:
                kind=type(node)
                if kind is ast.Assign and type(node.target) is ast.Name:
                    name=node.target.name.casefold()
                    if lexical and name not in local_slots:raise _OpaqueLocal
                    result,_=expression(node.value,facts)
                    # A module name is only a hint, not a fresh detached
                    # result: publication of old host storage may run Python.
                    if result is not None:facts[name]=result
                    else:facts.clear()
                elif kind is ast.ExpressionStatement:
                    expression(node.expression,facts)
                elif kind is ast.Var and lexical and all(name.casefold() in local_slots for name in node.names):
                    for name in node.names:facts.setdefault(name.casefold(),'scalar')
                elif kind is ast.Return:
                    if node.value is not None:
                        try:expression(node.value,facts)
                        except _OpaqueLocal:pass
                    # Even an opaque return expression cannot fall through
                    # to the lexical suffix (it returns a value or raises).
                    return _RETURNED
                elif kind is ast.If:
                    exits=[]
                    for condition,body,live_test,live_body,literal in ordered_if(node,literal_reachability=True):
                        if live_test and literal is None:
                            result,_=expression(condition,facts)
                            if lexical and result != 'scalar':raise _OpaqueLocal
                        # The next ElseIf sees only this condition's
                        # fallthrough, never the preceding Then body.
                        if live_body:
                            exits.append(statements(body,facts.copy(),loop_edges))
                    live=[exit_facts for exit_facts in exits if exit_facts is not _RETURNED]
                    if not live:return _RETURNED
                    if any(exit_facts is None for exit_facts in live):return None
                    facts=live[0]
                    for incoming in live[1:]:facts=_common_facts(facts,incoming)
                elif kind is ast.For or kind is ast.While:
                    following=loop(node,facts)
                    if following is None:
                        if lexical:return None
                        facts.clear()
                    else:facts=following
                elif loop_edges is not None and kind in (ast.Break,ast.Continue):
                    loop_edges[int(kind is ast.Break)].append(facts.copy())
                    return _RETURNED
                elif lexical:raise _OpaqueLocal
                else:
                    if kind is ast.ForEach:statements(node.body,{})
                    facts.clear()
        except _OpaqueLocal:
            return None
        return facts

    statements(program,{})
    return calls,origins,selection_reads,selection_adds


def _plain_abi(kind,methods):
    if kind.__getattribute__ is not object.__getattribute__ or hasattr(kind,'__getattr__'):
        return False
    # These protocol entries were captured on the exact defining class.
    # getattr(kind, name) would invoke a replacement descriptor even when
    # this guard is preparing to decline that replacement.
    attributes=vars(kind)
    for _,name,fn,code in methods:
        if attributes.get(name) is not fn or fn.__code__ is not code:return False
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


_CLOSED_ADD_TYPES=frozenset(map(id,(str,Decimal,bool,int,type(None))))


def selection_add(context, operation, left, right):
    # An opaque operand may run Python while adding. Revoke before that
    # callback (not after it), and do not let its result rearm this origin.
    if id(type(left)) in _CLOSED_ADD_TYPES and id(type(right)) in _CLOSED_ADD_TYPES:
        return operation(left,right)
    context._known_methods_live=0
    context._known_method_origin=None
    try:return operation(left,right)
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


def selection_read_protocol(context,value):
    """An overridden member read can execute unknown Python; retire the proof."""
    origin=context._known_method_origin
    if (origin is not None and context.policy is None and type(value) is BSLQueryResultSelection
            and _plain_abi(BSLQueryResultSelection,_SELECTION_READ_METHODS)
            and vars(BSLObject).get('get_member') is _BASE_MEMBER
            and _BASE_MEMBER.__code__ is _BASE_MEMBER_CODE):
        state=vars(value)
        if 'get_member' not in state and 'get_method' not in state and 'next' not in state:
            # Inspect the canonical instance storage, not the actual field
            # read: the generated read below must remain the only operation.
            result=state.get('_result')
            if (result is origin() and type(result) is BSLQueryResult
                    and BSLQueryResult.__getattribute__ is object.__getattribute__
                    and not hasattr(BSLQueryResult,'__getattr__')
                    and type(state.get('_position')) is int):
                detached=vars(result)
                if type(detached.get('_columns')) is tuple and type(detached.get('_rows')) in (tuple,list):
                    return True
    context._known_methods_live=0
    context._known_method_origin=None
    return False


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
from yadinassi.db.query.queries import (BSLQuery,BSLQueryResult,BSLQueryResultSelection,
    _DIRECT_METHODS,_DIRECT_SELECTION_MEMBER,_DIRECT_SELECTION_BASE_MEMBER)
from yadinassi.types.values import BSLObject
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
_SELECTION_READ_METHODS=(*_SELECTION_METHODS,(BSLQueryResultSelection,'get_member',*_DIRECT_SELECTION_MEMBER))
_BASE_MEMBER,_BASE_MEMBER_CODE=_DIRECT_SELECTION_BASE_MEMBER
_TABLE_METHODS=tuple((kind,name,fn,next(code for saved,code,*_ in _DIRECT_REGION_FUNCTIONS if saved is fn))
    for kind,_,attrs in _DIRECT_REGION_ABI if kind is BSLValueTable
    for name,fn in attrs if name in ('count','get_method'))

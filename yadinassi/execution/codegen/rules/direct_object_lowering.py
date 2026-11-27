"""Object and namespace behavior outside the ordinary Python value lane."""
from yadinassi.syntax import ast as b
from yadinassi.types.values import NULL
from ..direct_python_ast import _node, attr, call, literal, name
from .direct_reference_lowering import SELF_NAMES
import ast as p


def standalone_metadata_read(emit, key):
    # Without a DB, only a *read* of an unbound Metadata alias gets the
    # detached namespace. Ordinary assignments and local declarations win.
    bound = p.Compare(left=literal(key), ops=[p.In()], comparators=[name('_S')])
    return p.IfExp(test=bound, body=emit.var(key), orelse=emit.read_external(key))


def index(self,x):
    receiver,key=self.expr(x.object),self.expr(x.index)
    target=x.object
    while type(target) is b.Group:target=target.expression
    null_literal=type(target) is b.Literal and target.value is NULL
    if null_literal or self.meter_loops or self.source_dispatch or self.configuration_dispatch:
        return _node(call(call('_OwnedIndex',name('_C'),receiver),key),x.token)
    return _node(call('_ReadBracket',name('_C'),receiver,key),x.token)


def index_assignment(emit, target, value):
    receiver, key = emit.expr(target.object), emit.expr(target.index)
    if emit.meter_loops or emit.source_dispatch or emit.configuration_dispatch:
        return [p.Expr(value=call('_OwnedSetIndex',name('_C'),value,receiver,key))]
    # Evaluate receiver, key and RHS before validating the target.
    return [p.Expr(value=call('_WriteBracket',name('_C'),receiver,key,value))]


def field(emit, node):
    receiver = call('_PropertyReceiver', name('_C'), emit.expr(node.object))
    return p.Subscript(value=receiver, slice=literal(node.name), ctx=p.Load())


def field_assignment(emit, node, value):
    # Bind the receiver before evaluating RHS, as for other BSL lvalues.
    slot = emit.temp()
    receiver = call('_PropertyReceiver', name('_C'), emit.expr(node.object), write=literal(True), key=literal(node.name))
    target = p.Subscript(value=name(slot), slice=literal(node.name), ctx=p.Store())
    return [p.Assign(targets=[name(slot, True)], value=receiver),
            p.Assign(targets=[target], value=value)]


_ALIASES = {
    'количество': 'count', 'вграница': 'ubound', 'добавить': 'add',
    'очистить': 'clear', 'получить': 'get', 'установить': 'set',
    'получитьгруппы': 'getgroups',
    'привестизначение': 'adjustvalue', 'скопироватьколонки': 'copycolumns',
    'содержиттип': 'containstype',
    'удалитьнедопустимыесимволыxml': 'deletedisallowedxmlcharacters',
    'заполнитьзначения': 'fillvalues', 'загрузитьколонку': 'loadcolumn', 'свернуть': 'groupby',
    'установитьстроку': 'setstring', 'закрыть': 'close',
    'записатьначаломассива': 'writestartarray', 'записатьконецмассива': 'writeendarray',
    'записатьзначение': 'writevalue', 'прочитать': 'read', 'пропустить': 'skip',
    'записатьначалообъекта': 'writestartobject', 'записатьконецобъекта': 'writeendobject',
    'записатьимясвойства': 'writepropertyname',
    'индекс': 'indexof', 'найтипоидентификатору': 'findbyid',
    'найтипозначению': 'findbyvalue', 'получитьидентификатор': 'getid',
    'скопировать': 'copy', 'выгрузитьзначения': 'unloadvalues',
    'загрузитьзначения': 'loadvalues', 'сдвинуть': 'move',
    'заполнитьпометки': 'fillchecks', 'сортироватьпозначению': 'sortbyvalue',
    'сортироватьпопредставлению': 'sortbypresentation', 'владелец': 'owner', 'типы': 'types',
    'вставить': 'insert', 'удалить': 'delete', 'найти': 'find', 'найтистроки': 'findrows', 'выгрузитьколонку': 'unloadcolumn', 'итог': 'total', 'сортировать': 'sort', 'свойство': 'property',
}


def member_call(self, x, c, want_value):
    omitted = self.omissions(x.arguments)
    root = c.object
    while type(root) is b.Group:
        root = root.expression
    if (self.current_module and not self.owned and type(root) is b.Name
            and root.name.casefold() in SELF_NAMES
            and root.name.casefold() not in self.locals
            and root.name.casefold() not in self.module_declarations):
        options = {'require_value': literal(want_value), 'argument_count': literal(len(x.arguments))}
        if omitted:
            options['local_omissions'] = literal(True)
        bound = call(attr(name('_C'), 'resolve_public_module_call'), self.expr(root), literal(c.name), **options)
        return self.bound_call(bound, x.arguments, omitted, references=True)
    qualifier = root
    while type(qualifier) in (b.Group, b.Attribute):
        qualifier = qualifier.expression if type(qualifier) is b.Group else qualifier.object
    if self.source_dispatch and type(qualifier) is b.Name and self.external(qualifier.name.casefold()):
        bound = call(attr(name('_C'), 'resolve_source_member'), self.expr(c.object), literal(c.name),
                     require_value=literal(want_value), argument_count=literal(len(x.arguments)),
                     allow_references=literal(True))
        return self.bound_call(bound, x.arguments, omitted, references=True, crossing=True, shapes=True)
    folded = c.name.casefold()
    operation = _ALIASES.get(folded, folded)
    prefix = '_bsl_value_' if want_value else '_bsl_proc_'
    if omitted:
        from .direct_value_list_omissions import lower_omissions
        return lower_omissions(self, root, x.arguments, omitted, prefix, operation)
    receiver = self.expr(c.object)
    property_output = operation == 'property' and len(x.arguments) == 2
    if property_output:
        slot = self.temp()
        receiver = p.NamedExpr(target=name(slot, True), value=receiver)
    bound = attr(receiver, prefix + operation)
    if property_output:
        native = call('_OwnsPropertyOutput', name(slot))
        return call(bound, self.expr(x.arguments[0]), self.actual_address(x.arguments[1], native))
    return call(bound, *(self.expr(arg) for arg in x.arguments))

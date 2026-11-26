"""Non-native BSL control-flow rules: named transfers and controlled loops."""
import ast as p
from . import direct_goto, direct_text_addition
from ..direct_python_ast import _node, attr, call, literal, name
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported, _nodes
from yadinassi.syntax import ast as b


def block(self,nodes):
    if self.goto_labels and any(id(n) in self.goto_labels for n in nodes):
        return self.goto_block(nodes)
    if self.has_jumps and any(type(n) is b.Goto for n in nodes):
        prefix,cycle=direct_goto.linear_path(nodes)
        result=[stmt for n in prefix for stmt in self.stmt(n)]
        if cycle is not None:
            direct_goto.check_cycle(cycle,self.routines,PythonDirectUnsupported)
            loop=p.While(test=self.loop_condition(literal(True)),
                         body=[stmt for n in cycle for stmt in self.stmt(n)] or [p.Pass()],
                         orelse=[])
            result.append(_node(loop,nodes[0].token))
        return result
    result = []
    strings = set()
    for n in nodes:
        emitted = self.stmt(n)
        if type(n) is b.Assign:
            direct_text_addition.apply(emitted, strings)
        else:
            strings.clear()
        result.extend(emitted)
    return result


def loop_iterable(emit, value):
    if emit.meter_loops:
        return call('_Metered',name('_C'),value)
    # An inline native Array needs no admission or iterable conversion.
    if isinstance(value,p.List) or (isinstance(value,p.Call)
            and isinstance(value.func,p.Name) and value.func.id=='_Array'):
        return value
    helper = '_OwnedIterable' if emit.source_dispatch else '_BSLIterable'
    return call(helper,name('_C'),value)


def loop_condition(self,test):
    if self.meter_loops:
        boundary=call(attr(name('_C'),'checkpoint'))
        return p.Subscript(value=p.Tuple(elts=[boundary,test],ctx=p.Load()),slice=literal(1),ctx=p.Load())
    return test


def jump(self,target):
    return p.Raise(exc=call('_GotoTransfer',literal(target)),cause=literal(None))


def loop_control(self,continuing):
    if not self.loop:
        raise PythonDirectUnsupported(('Continue' if continuing else 'Break')+' outside a loop')
    if self.dispatch and self.dispatch[-1][0]==len(self.loop):
        target=-2 if continuing else -3
        self.dispatch[-1][1].add(target)
        return [self.jump(target)]
    if continuing:
        from copy import deepcopy
        prefix=[] if self.loop[-1] is None else [deepcopy(self.loop[-1])]
        return [*prefix,p.Continue()]
    return [p.Break()]


def goto_block(self,nodes):
    pc,caught=self.temp(),self.temp()
    segments=[(-1,[])]
    for node in nodes:
        destination=self.goto_labels.get(id(node))
        if destination is not None:segments.append((destination,[]))
        else:segments[-1][1].append(node)
    def assign(value):
        return p.Assign(targets=[name(pc,True)],value=value)
    def is_at(target):
        return p.Compare(left=name(pc),ops=[p.Eq()],comparators=[literal(target)])
    controls=set()
    self.dispatch.append((len(self.loop),controls))
    try:
        cases=[]
        for i,(target,body) in enumerate(segments):
            following=segments[i+1][0] if i+1<len(segments) else -4
            cases.append(p.match_case(pattern=p.MatchValue(value=literal(target)),guard=None,
                                      body=[assign(literal(following)),*[s for n in body for s in self.stmt(n)]]))
    finally:
        self.dispatch.pop()
    accepted=tuple(k for k,_ in segments[1:])+tuple(sorted(controls))
    destination=attr(name(caught),'target')
    handler=p.If(test=p.Compare(left=destination,ops=[p.In()],comparators=[literal(accepted)]),
                 body=[assign(destination)],orelse=[p.Raise(exc=None,cause=None)])
    attempt=p.Try(body=[p.Match(subject=name(pc),cases=cases)],
                  handlers=[p.ExceptHandler(type=name('_GotoTransfer'),name=caught,body=[handler])],
                  orelse=[],finalbody=[])
    active=p.Compare(left=name(pc),ops=[p.GtE()],comparators=[literal(-1)])
    result=[assign(literal(-1)),p.While(test=self.loop_condition(active),body=[attempt],orelse=[])]
    for target in sorted(controls):
        result.append(p.If(test=is_at(target),body=self.loop_control(target==-2),orelse=[]))
    return [_node(stmt,nodes[0].token) for stmt in result]

def advance_for_counter(value):
    # Python bool is an int subclass; a BSL For step requires a number.
    if type(value) is bool:
        raise TypeError('Ожидается число')
    return value + 1


def _counter_value_can_be_boolean(value):
    while type(value) is b.Group:
        value = value.expression
    if type(value) is b.Literal:
        return type(value.value) is bool
    if type(value) is b.Unary:
        return value.operator == 'NOT'
    if type(value) is b.Binary:
        return value.operator not in ('+', '-', '*', '/', '%')
    return True


def for_counter(loop, key, *, read, assign, target=None):
    # Normal induction does not need an adapter. Only an explicit assignment
    # in this loop can trigger this rule; handling ByRef/host mutation belongs
    # to those separate operations, not to every loop's increment.
    for item in _nodes(loop.body):
        if (type(item) is b.Assign and type(item.target) is b.Name
                and item.target.name.casefold() == key
                and _counter_value_can_be_boolean(item.value)):
            return assign(call('_AdvanceFor', read))
    if target is not None:
        return p.AugAssign(target=target, op=p.Add(), value=literal(1))
    return assign(p.BinOp(left=read, op=p.Add(), right=literal(1)))

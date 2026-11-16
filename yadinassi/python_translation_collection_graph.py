"""Conservative preparation-time cycle exclusion for unpublished fresh graphs.

Monotone points-to sets never forget aliases after rebinding. Reads may return
anything reachable from their owner, including its implicit multidimensional
children. Allocation sites abstract repeated allocations; false positives decline
optimization before effects rather than retaining cycles while GC is suspended.
"""
from dataclasses import fields
from .syntax import ast
from .owned_syntax import syntax_kind


class _AnalysisBudget(Exception):pass

def acyclic(statements):
    try:return _acyclic(statements)
    except _AnalysisBudget:return False

def _acyclic(statements):
    nodes=[];pending=list(statements);seen=set()
    while pending:
        node=pending.pop()
        if id(node) in seen:continue
        if isinstance(node,ast.Node):
            seen.add(id(node));nodes.append(node)
            if len(nodes)>10000:return False
            for field in fields(node):
                if field.name!='token':pending.append(getattr(node,field.name))
        elif isinstance(node,(tuple,list)):seen.add(id(node));pending.extend(node)
    points={};edges={id(node):set() for node in nodes if syntax_kind(node) is ast.New}
    changed=False;too_deep=False;entries=0
    def reachable(owners):
        result=set(owners);queue=list(owners)
        while queue:
            for target in edges.get(queue.pop(),()):
                if target not in result:result.add(target);queue.append(target)
        return result
    def refs(node,depth=0):
        nonlocal too_deep
        if depth>128:too_deep=True;return set()
        kind=syntax_kind(node)
        if kind is ast.Name:return points.get(node.name.casefold(),set())
        if kind is ast.New:return {id(node)}
        if kind is ast.Group:return refs(node.expression,depth+1)
        if kind in (ast.Index,ast.Attribute):return reachable(refs(node.object,depth+1))
        if kind is ast.Conditional:return refs(node.when_true,depth+1)|refs(node.when_false,depth+1)
        if kind is ast.Call and syntax_kind(node.callee) is ast.Attribute:
            if node.callee.name.casefold() in ('get','получить'):
                return reachable(refs(node.callee.object,depth+1))
        return set()  # Admitted literals/operators/other methods return scalars.
    def add(target,values):
        nonlocal changed,entries,too_deep
        extra=values-target
        if entries+len(extra)>100000:raise _AnalysisBudget
        target.update(extra);entries+=len(extra);changed|=bool(extra)
    for _ in range(64):
        changed=False
        for node in nodes:
            if too_deep:return False
            kind=syntax_kind(node)
            if kind is ast.Assign:
                if syntax_kind(node.target) is ast.Name:
                    add(points.setdefault(node.target.name.casefold(),set()),refs(node.value))
                elif syntax_kind(node.target) in (ast.Index,ast.Attribute):
                    for owner in refs(node.target.object):
                        add(edges[owner],refs(node.value))
                        if syntax_kind(node.target) is ast.Index:add(edges[owner],refs(node.target.index))
            elif kind is ast.ForEach:
                add(points.setdefault(node.name.casefold(),set()),reachable(refs(node.collection)))
            elif kind is ast.Call and syntax_kind(node.callee) is ast.Attribute:
                if node.callee.name.casefold() in ('add','добавить','insert','вставить','set','установить'):
                    for owner in refs(node.callee.object):
                        for argument in node.arguments:add(edges[owner],refs(argument))
            elif kind is ast.New and node.name.casefold() in ('structure','структура'):
                for argument in node.arguments[1:]:add(edges[id(node)],refs(argument))
        if too_deep:return False
        if not changed:break
    else:return False  # Bounded optional analysis, never accept an incomplete proof.
    degree={key:0 for key in edges}
    for targets in edges.values():
        for key in targets:degree[key]+=1
    ready=[key for key,count in degree.items() if not count];visited=0
    while ready:
        key=ready.pop();visited+=1
        for target in edges[key]:
            degree[target]-=1
            if not degree[target]:ready.append(target)
    return visited==len(edges)

"""Small construction utilities shared by the single Python emitter."""
import ast as p


def _node(n, token):
    if 'lineno' in n._attributes:
        n.lineno=n.end_lineno=token.line
        n.col_offset=max(0,token.column-1)
        n.end_col_offset=n.col_offset+1
    return n


def name(value, store=False):
    return p.Name(id=value, ctx=p.Store() if store else p.Load())


def call(target, *args, **kwargs):
    if isinstance(target,str):
        target=name(target)
    return p.Call(func=target, args=list(args),
                  keywords=[p.keyword(arg=k,value=v) for k,v in kwargs.items()])


def attr(target,key):
    return p.Attribute(value=target, attr=key, ctx=p.Load())


def literal(value):
    return p.Constant(value=value)


def arguments(names):
    return p.arguments(posonlyargs=[],args=[p.arg(arg=k) for k in names],vararg=None,
                       kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])

"""AST instrumentation used only for budgeted catalog preparation."""
import ast as p

from ..direct_python_ast import attr, call, literal, name


def _step():
    return call(attr(name('_C'), 'preparation_step'))


def expression(value):
    # A step is charged before evaluating the expression, then the value
    # budget is checked without repeating the expression.
    sequenced = p.Subscript(
        value=p.Tuple(elts=[_step(), value], ctx=p.Load()),
        slice=literal(1), ctx=p.Load(),
    )
    return call(attr(name('_C'), 'preparation_value'), sequenced)


def statements(body):
    return [p.Expr(value=_step()), *body]

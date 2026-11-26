"""BSL string-left + in straight-line assignments, not a generic + fallback."""
import ast as p

from ..direct_python_ast import call


def apply(statements, strings):
    """Keep only explicit string assignments until control or effects intervene."""
    if len(statements) != 1 or type(statements[0]) is not p.Assign:
        strings.clear()
        return
    assignment = statements[0]
    if len(assignment.targets) != 1 or type(assignment.targets[0]) is not p.Name:
        strings.clear()
        return
    target = assignment.targets[0].id
    value = assignment.value
    if type(value) is p.Constant:
        is_string = type(value.value) is str
    elif type(value) is p.Name:
        is_string = value.id in strings
    elif (type(value) is p.BinOp and type(value.op) is p.Add
          and type(value.left) is p.Name and value.left.id in strings
          and type(value.right) in (p.Constant, p.Name)):
        assignment.value = p.copy_location(call('_String', value.left, value.right), value)
        is_string = True
    else:
        # No facts survive arbitrary Python operators, imports, or calls.
        strings.clear()
        return
    if is_string:
        strings.add(target)
    else:
        strings.discard(target)

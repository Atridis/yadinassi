"""Straight-line string-left addition; no dynamic operator fallback."""
import ast as p

from yadinassi.text.strings import _WHITESPACE
from ..direct_python_ast import call


_TEXT = object()


def _intrinsic(node, name):
    return type(node) is p.Call and type(node.func) is p.Name and node.func.id == name


def _field_is_text(node, facts):
    if type(node) is not p.Subscript or not _intrinsic(node.value, '_PropertyReceiver'):
        return False
    receiver = node.value.args[1]
    if type(receiver) is not p.Name:
        return False
    fields = facts.get(receiver.id)
    return type(fields) is frozenset and node.slice.value.casefold() in fields


def apply(statements, facts):
    """Track names and fresh literal Structure fields within one block only."""
    if len(statements) != 1 or type(statements[0]) is not p.Assign:
        facts.clear()
        return
    assignment = statements[0]
    if len(assignment.targets) != 1 or type(assignment.targets[0]) is not p.Name:
        facts.clear()
        return
    target = assignment.targets[0].id
    value = assignment.value

    if type(value) is p.Constant:
        fact = _TEXT if type(value.value) is str else None
    elif type(value) is p.Name:
        fact = facts.get(value.id)
    elif (_intrinsic(value, '_Structure') and value.args
          and type(value.args[0]) is p.Constant and type(value.args[0].value) is str
          and all(type(item) is p.Constant for item in value.args[1:])):
        keys = (part.strip(_WHITESPACE) for part in value.args[0].value.split(','))
        fields = {
            key.casefold(): i + 1 < len(value.args) and type(value.args[i + 1].value) is str
            for i, key in enumerate(key for key in keys if key)
        }
        fact = frozenset(key for key, is_text in fields.items() if is_text)
    elif type(value) is p.BinOp and type(value.op) is p.Add:
        left, right = value.left, value.right
        simple_right = type(right) in (p.Constant, p.Name)
        if (_field_is_text(left, facts)
                or simple_right and type(left) is p.Name and facts.get(left.id) is _TEXT):
            assignment.value = p.copy_location(call('_String', left, right), value)
            if not simple_right:
                facts.clear()  # The RHS may have effects after the left read.
            fact = _TEXT
        else:
            facts.clear()
            return
    else:
        facts.clear()
        return

    if fact is None:
        facts.pop(target, None)
    else:
        facts[target] = fact

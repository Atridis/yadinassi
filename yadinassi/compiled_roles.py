"""Whole-unit AST role checks at admission, never an execution dispatcher.

The parser normally guarantees these roles. Embedders can construct AST objects
directly, so recognizing a node class alone must not authorize its use anywhere.
Standalone expression research helpers keep their separate delayed-error contract.
"""
from .syntax import ast
from .owned_syntax import syntax_kind

EXPRESSION_KINDS = (ast.Literal, ast.Name, ast.Group, ast.Unary, ast.Binary,
                    ast.Conditional, ast.Attribute, ast.Index, ast.Call, ast.New,
                    ast.DynamicNew, ast.Await)


def validate_node_roles(node, kind, reject):
    def expression(value, *, optional=False, omitted=False):
        if optional and value is None:
            return
        actual = syntax_kind(value)
        if omitted and actual is ast.OmittedArgument:
            return
        if not any(actual is expected for expected in EXPRESSION_KINDS):
            reject(node, 'expression operand has invalid AST role')

    if kind is ast.Group:
        expression(node.expression)
    elif kind is ast.Unary or kind is ast.Await:
        expression(node.operand)
    elif kind is ast.Binary:
        expression(node.left); expression(node.right)
    elif kind is ast.Conditional:
        expression(node.condition); expression(node.when_true); expression(node.when_false)
    elif kind is ast.Attribute:
        expression(node.object)
    elif kind is ast.Index:
        expression(node.object); expression(node.index)
    elif kind is ast.Call or kind is ast.New:
        if kind is ast.Call:
            expression(node.callee)
        for argument in node.arguments:
            expression(argument, omitted=True)
    elif kind is ast.DynamicNew:
        expression(node.type_expression); expression(node.parameters, optional=True)
    elif kind is ast.Assign:
        target = syntax_kind(node.target)
        if not any(target is expected for expected in (ast.Name, ast.Attribute, ast.Index)):
            reject(node, 'assignment target has invalid AST role')
        expression(node.value)
    elif kind is ast.ExpressionStatement:
        expression(node.expression)
    elif kind is ast.If:
        for test, _ in node.branches:
            expression(test)
    elif kind is ast.For:
        expression(node.start); expression(node.end)
    elif kind is ast.ForEach:
        expression(node.collection)
    elif kind is ast.While:
        expression(node.condition)
    elif kind is ast.Return or kind is ast.Raise:
        expression(node.value, optional=True)
        if kind is ast.Raise and node.optional_arguments is not None:
            for argument in node.optional_arguments:
                expression(argument, omitted=True)
    elif kind is ast.Execute:
        expression(node.expression)
    elif kind is ast.Parameter:
        expression(node.default, optional=True)
    elif kind is ast.Routine:
        for parameter in node.parameters:
            if syntax_kind(parameter) is not ast.Parameter:
                reject(node, 'routine parameter has invalid AST role')

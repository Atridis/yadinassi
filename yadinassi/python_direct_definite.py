"""Compile-time scalar islands for live module dictionary reads.

Never caches values or defers stores. Unknown operations terminate the proof;
loop proofs require a callback-free scalar body, including every branch.
"""
from decimal import Decimal
from .syntax import ast


def definite_module_reads(program):
    safe = set()

    def scalar(node, known, record):
        kind = type(node)
        if kind is ast.Literal:
            return type(node.value) in (type(None), bool, Decimal, str, int, float)
        if kind is ast.Name:
            found = node.name.casefold() in known
            if found and record:
                safe.add(id(node))
            return found
        if kind is ast.Group:
            return scalar(node.expression, known, record)
        if kind is ast.Unary:
            return scalar(node.operand, known, record)
        if kind is ast.Binary:
            # Both sides must be pure, even for short-circuit operators.
            left = scalar(node.left, known, record)
            right = scalar(node.right, known if left else set(), record)
            return left and right
        if kind is ast.Conditional:
            return (scalar(node.condition, known, record)
                    and scalar(node.when_true, known, record)
                    and scalar(node.when_false, known, record))
        return False

    def block(nodes, incoming, record):
        known = set(incoming)
        pure = True
        for node in nodes:
            kind = type(node)
            if kind is ast.Routine:
                # Routine bodies execute later, potentially after arbitrary hosts.
                continue
            if kind is ast.Assign and type(node.target) is ast.Name:
                ok = scalar(node.value, known, record)
                if not ok:
                    known.clear()
                    pure = False
                else:
                    known.add(node.target.name.casefold())
            elif kind is ast.Var:
                # setdefault can retain an unknown incoming host value.
                pass
            elif kind is ast.ExpressionStatement:
                if not scalar(node.expression, known, record):
                    known.clear(); pure = False
            elif kind is ast.If:
                outputs = []
                conditions_pure = all(scalar(c, known, False) for c, _ in node.branches)
                if not conditions_pure:
                    known.clear(); pure = False
                for condition, body in node.branches:
                    scalar(condition, known, record)
                    result, branch_pure = block(body, known, record)
                    outputs.append(result); pure &= branch_pure
                result, branch_pure = block(node.otherwise or [], known, record)
                outputs.append(result); pure &= branch_pure
                known = set.intersection(*outputs)
            elif kind in (ast.For, ast.While):
                seed = set(known)
                if kind is ast.For:
                    loop_pure = scalar(node.start, seed, False) and scalar(node.end, seed, False)
                    seed.add(node.name.casefold())
                else:
                    loop_pure = scalar(node.condition, seed, False)
                _, body_pure = block(node.body, seed, False)
                loop_pure &= body_pure
                if loop_pure:
                    if record and kind is ast.For: safe.add(id(node))
                    if kind is ast.For:
                        scalar(node.start, known, record); scalar(node.end, known, record)
                    else:
                        scalar(node.condition, seed, record)
                    block(node.body, seed, record)
                    # Zero iterations must not introduce body assignments.
                    if kind is ast.For: known.add(node.name.casefold())
                else:
                    # No entry facts cross a possibly mutating backedge.
                    block(node.body, set(), record)
                    known.clear(); pure = False
            else:
                # Includes break/continue/try, host calls and reference operations.
                known.clear(); pure = False
        return known, pure

    block(program, set(), True)
    return frozenset(safe)

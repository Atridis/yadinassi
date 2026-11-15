"""Explicit compatibility oracle for historical fail-closed mutable AST tests.

These are not snapshot tests. Snapshot/version behavior has separate regressions.
"""
from functools import wraps
from yadinassi.execution_policy import compiled_ast_policy

def mutable_compiled_contract(test):
    @wraps(test)
    def run(*args, **kwargs):
        with compiled_ast_policy('mutable'):
            return test(*args, **kwargs)
    return run

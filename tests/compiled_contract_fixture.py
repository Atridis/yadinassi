"""Explicit compatibility oracle for historical fail-closed mutable AST tests.

These are not snapshot tests. Snapshot/version behavior has separate regressions.
"""
from functools import wraps
from unittest.mock import patch
from yadinassi.compiled_backend import Engine
from yadinassi.execution_policy import compiled_ast_policy

def mutable_compiled_contract(test):
    @wraps(test)
    def run(*args, **kwargs):
        with compiled_ast_policy('mutable'), patch.object(Engine, 'FORCE_PYTHON_TRANSLATION', False):
            return test(*args, **kwargs)
    return run


def legacy_compiler_fixture(cls):
    """Select the optional legacy compiler explicitly, not translated coverage.

    Applied only to tests of its plan cache, counters, eligibility and adapter
    boundaries. All original assertions remain; default Python translation has
    separate end-to-end context, security and differential coverage.
    """
    original = cls.setUp
    @wraps(original)
    def set_up(self):
        selection = patch.object(Engine, 'FORCE_PYTHON_TRANSLATION', False)
        selection.start()
        self.addCleanup(selection.stop)
        original(self)
    cls.setUp = set_up
    cls.compiler_coverage_scope = 'legacy-optional-compiler-only'
    return cls

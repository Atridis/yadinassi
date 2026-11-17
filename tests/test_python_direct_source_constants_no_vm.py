"""Run the complete existing constant lifecycle contracts with VM entry points poisoned."""
import unittest
from unittest.mock import patch
import test_source_constant_handlers as handlers
import test_source_constant_module_lifecycle as lifecycle
from yadinassi.runtime import Interpreter


class NoVM:
    def setUp(self):
        super().setUp()
        for name in ('_execute_program', 'call_routine'):
            poison = patch.object(Interpreter, name, side_effect=AssertionError('legacy '+name))
            poison.start()
            self.addCleanup(poison.stop)


class DirectConstantHandlersNoVM(NoVM, handlers.SourceConstantHandlerTests):
    pass


class DirectConstantLifecycleNoVM(NoVM, lifecycle.SourceConstantModuleLifecycleTests):
    pass


if __name__ == '__main__':
    unittest.main()

"""Run the complete existing constant lifecycle contracts with VM entry points poisoned."""
import unittest
import test_source_constant_handlers as handlers
import test_source_constant_module_lifecycle as lifecycle


class NoVM:
    def setUp(self):
        super().setUp()


class DirectConstantHandlersNoVM(NoVM, handlers.SourceConstantHandlerTests):
    pass


class DirectConstantLifecycleNoVM(NoVM, lifecycle.SourceConstantModuleLifecycleTests):
    pass


if __name__ == '__main__':
    unittest.main()

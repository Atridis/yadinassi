"""Native scalar ServerCall reuse observations without VM execution."""
from contextlib import ExitStack
from unittest.mock import patch
import test_source_server_reuse as replay
from yadinassi.runtime import Interpreter


class SourceServerReuseNoVM(replay.SourceServerReuseTests):
    def setUp(self):
        stack=ExitStack();self.addCleanup(stack.close)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            stack.enter_context(patch.object(Interpreter,name,side_effect=AssertionError('VM forbidden')))

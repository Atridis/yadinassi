"""Native scalar ServerCall reuse observations without VM execution."""
from contextlib import ExitStack
import test_source_server_reuse as replay


class SourceServerReuseNoVM(replay.SourceServerReuseTests):
    def setUp(self):
        stack=ExitStack();self.addCleanup(stack.close)

"""Real owning posting semantics replace synthetic deleted semantic hooks."""
import unittest

class DirectPostingSemantics(unittest.TestCase):
    def test_builtin_field_collision(self):
        from test_python_direct_posting_names import PostingNamesTests
        case=PostingNamesTests('test_number_call_keeps_field_read_and_ignores_parent_override')
        self.addCleanup(case.doCleanups)
        case.setUp()
        try:case.test_number_call_keeps_field_read_and_ignores_parent_override()
        finally:case.tearDown()

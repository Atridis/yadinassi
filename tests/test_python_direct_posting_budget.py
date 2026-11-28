"""Generated posting loop budgets abort native atomic writes without VM dispatch."""
import unittest
from unittest.mock import patch
from yadinassi.db.document.document_posting import PostingLimitError
from yadinassi.db.database_transactions import current,_registered
import test_document_posting_runtime as fixture

class DirectPostingBudgetTests(unittest.TestCase):
    def test_recorder_budget_uncatchable_atomic_and_no_vm(self):
        owner=fixture.PostingRuntimeTests();owner.setUp();self.addCleanup(owner.doCleanups)
        owner.make('Procedure Posting(Cancel,Mode) Try While True Do EndDo; Except EndTry; EndProcedure')
        obj=owner.new(3)
        with patch('yadinassi.db.document.document_posting.MAX_STEPS',50):
            with self.assertRaises(PostingLimitError):owner.post()
        self.assertTrue(obj.is_new())
        self.assertEqual(owner.rows(obj),())
        self.assertIsNone(obj._posting_active)
        self.assertIsNone(obj._pending_write)
        self.assertIsNone(current(owner.backend))
        self.assertIsNone(_registered(owner.backend))

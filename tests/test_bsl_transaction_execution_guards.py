"""Explicit ownership must not leak into legacy logical or no-DB execution."""
from contextvars import Context
from decimal import Decimal
from unittest.mock import Mock
import unittest
import test_bsl_transactions as fixtures
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.database_transactions import execution, begin, rollback, current


class TransactionExecutionGuardTests(unittest.TestCase):
    setUp = fixtures.BSLTransactionsTests.setUp

    def test_mock_missing_owner_is_not_created_or_treated_as_pending(self):
        backend=Mock()
        self.assertIsNone(current(backend))
        self.assertNotIn('_bsl_transaction',backend._mock_children)

    def test_explicit_forged_owner_is_refused(self):
        self.backend._bsl_transaction=Mock()
        try:
            with self.assertRaises(BackendError): current(self.backend)
        finally: self.backend._bsl_transaction=None

    def test_logical_backend_cannot_begin_explicit_sqlite_transaction(self):
        backend=Mock()
        with execution(backend):
            with self.assertRaises(BackendError): begin(backend)
        backend.begin_unit_of_work.assert_not_called()
        self.assertNotIn('_bsl_transaction',backend.__dict__)

    def test_nested_no_database_execution_allowed_without_explicit_transaction(self):
        with execution(self.backend):
            self.assertEqual(Interpreter().execute('20+22'),Decimal(42))

    def test_nested_no_database_execution_refused_while_transaction_active(self):
        with execution(self.backend):
            begin(self.backend)
            with self.assertRaises(BackendError): Interpreter().execute('20+22')
            rollback(self.backend)

    def test_different_logical_execution_allowed_without_explicit_transaction(self):
        with execution(self.backend):
            with execution(Mock()): pass

    def test_different_execution_cannot_start_foreign_backend_transaction(self):
        with execution(Mock()):
            with execution(self.backend):
                with self.assertRaises(BackendError): begin(self.backend)
        self.assertIsNone(self.backend._active)

    def test_foreign_context_cannot_observe_active_owner(self):
        with execution(self.backend):
            begin(self.backend)
            with self.assertRaises(BackendError): Context().run(current,self.backend)
            rollback(self.backend)

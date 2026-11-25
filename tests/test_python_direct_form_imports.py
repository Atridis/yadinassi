"""Hoisted module imports retain live form policy and budget checks."""
import dis
from contextvars import ContextVar
import unittest
from unittest.mock import patch
from yadinassi.forms.form_runtime import FormSession, FormLimitError
from yadinassi.execution.direct.python_direct_forms import FormBoundary
from yadinassi.execution.direct.python_direct_configuration import check_owner
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution import safe_mode
from yadinassi.db import source_transactions, database_transactions


class DirectFormImportTests(unittest.TestCase):
    def boundary(self):
        session=FormSession('Procedure Event() EndProcedure')
        session._begin(session.revision)
        def cleanup():
            session._busy=False
            session._gate.release()
        self.addCleanup(cleanup)
        boundary=FormBoundary(session,session.interpreter.routines['event'])
        boundary.enter()
        self.addCleanup(boundary.leave)
        return session,boundary

    def test_hot_methods_have_no_import_bytecode(self):
        for method in (FormBoundary._check,FormBoundary.checkpoint,check_owner):
            self.assertFalse(any(op.opname.startswith('IMPORT_') for op in dis.get_instructions(method)))

    def test_current_module_context_attributes_are_observed(self):
        session,boundary=self.boundary()
        for module,name in ((safe_mode,'_CURRENT'),(source_transactions,'_current'),(database_transactions,'_execution')):
            with self.subTest(module=module.__name__),patch.object(module,name,ContextVar('denied',default=object())):
                with self.assertRaisesRegex(BoundaryViolation,'restricted form'):boundary.checkpoint()
                self.assertEqual(session._steps,0)
        boundary.checkpoint()
        self.assertEqual(session._steps,1)

    def test_budget_is_read_live_not_frozen_at_module_import(self):
        session,boundary=self.boundary()
        boundary.checkpoint()
        with patch('yadinassi.forms.form_runtime.MAX_STEPS',1):
            with self.assertRaises(FormLimitError):boundary.checkpoint()
        self.assertEqual(session._steps,2)

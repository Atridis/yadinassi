"""Narrow DB form opt-in does not grant configuration or transaction authority."""
from contextvars import ContextVar
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_python_direct_bound_forms as fixtures
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.forms.form_runtime import FormSession
from yadinassi.execution.direct.python_direct_forms import FormBoundary, check_form_owner
from yadinassi.execution.direct.python_direct_configuration import check_owner
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution import safe_mode
from yadinassi.db import source_transactions, database_transactions
from sqlite_test_templates import copy_main_demo

class DatabaseFormAdmissionTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.BoundFormTests()
        self.addCleanup(fixture.doCleanups)
        _,self.app=fixture.setup_apps()
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        path=Path(folder.name)/'db.sqlite'
        copy_main_demo(path)
        self.db=SQLiteDBContext(path)
        self.addCleanup(self.db.close)
        self.output=[]
        self.session=FormSession('Procedure Event() Message("effect"); EndProcedure',
            interpreter_factory=self.app.form_interpreter_factory,
            database_context=self.db,output=self.output.append)
        self.vm=self.session.interpreter
        self.session._begin(0)
        self.addCleanup(self.release)
        self.boundary=FormBoundary(self.session,self.vm.routines['event'])
        self.boundary.enter();self.addCleanup(self.boundary.leave)
    def release(self):
        self.session._busy=False;self.session._gate.release()
    def test_only_form_opt_in_general_configuration_still_denied(self):
        check_form_owner(self.app,self.vm)
        with self.assertRaisesRegex(BoundaryViolation,'database execution'):
            check_owner(self.app,self.vm)
    def test_non_sqlite_and_subclass_rejected_before_event(self):
        class Derived(SQLiteDBContext):pass
        for database in (object(),object.__new__(Derived)):
            with self.subTest(kind=type(database)),patch.object(self.vm,'_database_context',database):
                with self.assertRaisesRegex(BoundaryViolation,'host-selected SQLite'):
                    self.session._invoke('Event','client',[])
        self.assertEqual(self.output,[])
    def test_bound_service_rejects_changed_database_before_effect(self):
        call=self.boundary.resolve_service('Message')
        with patch.object(self.vm,'_database_context',None):
            with self.assertRaisesRegex(BoundaryViolation,'database owner changed'):call('bad')
        self.assertEqual(self.output,[])
        self.boundary._check()
    def test_database_opt_in_retains_all_restricted_context_denials(self):
        for module,name in ((safe_mode,'_CURRENT'),(source_transactions,'_current'),(database_transactions,'_execution')):
            with self.subTest(name=name),patch.object(module,name,ContextVar('blocked',default=object())):
                with self.assertRaisesRegex(BoundaryViolation,'restricted'):
                    self.session._invoke('Event','client',[])
        self.assertEqual(self.output,[])
    def test_closed_application_denied_with_database(self):
        self.app.close(force=True)
        with self.assertRaises((BoundaryViolation,ValueError)):
            self.session._invoke('Event','client',[])
        self.assertEqual(self.output,[])

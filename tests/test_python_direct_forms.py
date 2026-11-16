"""Actual demo import/event slice; full application and DB execution remain unsupported."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.configuration_app import load_application

ROOT=Path(__file__).resolve().parents[1]/'examples/demo'

class DirectFormTests(unittest.TestCase):
    def test_real_demo_import_database_reopen_and_created_without_vm_dispatch(self):
        files={p.relative_to(ROOT).as_posix():p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')), patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            config=import_main_demo_configuration(files,profile=PROFILE)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'demo.sqlite'
                SQLiteDBContext.create_main_demo(path,config).close()
                with SQLiteDBContext(path) as reopened:
                    self.assertEqual(len(reopened.backend.accumulation_configuration.catalogs),3)
                before=path.read_bytes()
                app=load_application(ROOT,main_demo_application=True)
                server=app.forms['commonform.demowelcome'].create_server()
                session=server.session
                session._begin(session.revision)
                try:
                    self.assertEqual(session._event('oncreateatserver',[False,True]),[False,True])
                    self.assertEqual(session.form.get_member('Greeting'),'Справочники, документы и регистр накопления работают в одной базе')
                finally:
                    session._busy=False
                    session._gate.release()
                self.assertEqual(path.read_bytes(),before)

    def test_event_transaction_service_rejected_before_effect(self):
        from yadinassi.form_runtime import FormSession
        source='&AtServer\nProcedure Created(Cancel, StandardProcessing) BeginTransaction(); EndProcedure'
        session=FormSession(source,bindings={'OnCreateAtServer':'Created'})
        with patch('yadinassi.database_transactions.begin',side_effect=AssertionError('transaction effect')) as begin:
            with self.assertRaises(Exception):session.open()
            begin.assert_not_called()
        self.assertFalse(session._busy)
        self.assertEqual(session.interpreter.execution_context,'client')

    def test_loop_budget_and_closed_interpreter_reject(self):
        from yadinassi.form_runtime import FormSession, FormLimitError
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        source='&AtServer\nProcedure Created(Cancel, StandardProcessing) While True Do EndDo; EndProcedure'
        session=FormSession(source,bindings={'OnCreateAtServer':'Created'})
        with patch('yadinassi.form_runtime.MAX_STEPS',5):
            with self.assertRaises(FormLimitError):session.open()
        self.assertFalse(session._busy)
        session=FormSession('&AtServer\nProcedure Created(Cancel, StandardProcessing) EndProcedure',bindings={'OnCreateAtServer':'Created'})
        session.interpreter.close()
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertFalse(session._busy)

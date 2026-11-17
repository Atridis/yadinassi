"""Exact source form boundary admission and revocation without legacy dispatch."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from test_source_forms import files
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_forms import SourceFormController
from yadinassi.python_direct_source_forms import SourceFormBoundary,check_source_session
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.runtime import Interpreter
from yadinassi import source_transactions


class DirectSourceFormSecurity(unittest.TestCase):
    def controller(self):
        app=SourceApplication(import_source(files()));self.addCleanup(app.close)
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('legacy program')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            app.start();controller=SourceFormController(app,'CommonForm.Main')
        return app,controller

    @contextmanager
    def boundary(self,app,session):
        vm=session.interpreter;routine=vm.server_routines['created'];busy=session._busy
        session._busy=True;vm._context_stack.append('server');vm._module_context_stack.append(True)
        with app.safe_mode.execution(),source_transactions.execution(app):
            boundary=SourceFormBoundary(session,routine)
            try:
                boundary.enter();yield boundary
            finally:
                boundary.leave();vm._module_context_stack.pop();vm._context_stack.pop();session._busy=busy

    def test_source_attribute_reference_revoked_with_event(self):
        app,controller=self.controller();session=controller.server.session
        with self.boundary(app,session) as boundary:
            reference=boundary.reference_member(session.form,'Greeting')
            reference.set('owned');self.assertEqual(reference.get(),'owned')
        with self.assertRaises(BoundaryViolation):reference.get()

    def test_changed_nonentry_routine_signature_rejected(self):
        app,controller=self.controller();session=controller.server.session
        routine=session.interpreter.server_routines['updateatserver'];original=routine.is_function
        with self.boundary(app,session) as boundary:
            routine.is_function=not original
            try:
                with self.assertRaisesRegex(BoundaryViolation,'declaration'):boundary._check()
            finally:routine.is_function=original

    def test_close_procedure_as_value_rejected_before_close(self):
        app,controller=self.controller();session=controller.server.session
        with self.boundary(app,session) as boundary:
            with patch.object(session,'request_close',side_effect=AssertionError('unexpected close')):
                with self.assertRaises(TypeError):
                    boundary.resolve_source_member(session.form,'Close',require_value=True)
            boundary._check()

    def test_declaration_constructor_rechecked_after_argument_mutation(self):
        from yadinassi.values import HostFunction
        for mutation in ('function','registry'):
            with self.subTest(mutation=mutation):
                app,controller=self.controller();session=controller.server.session;effects=[]
                with self.boundary(app,session) as boundary:
                    factory=session.interpreter.types['typedescription'];original=factory.function
                    bound=boundary.resolve_service('new:typedescription',require_value=True)
                    replacement=HostFunction('TypeDescription',lambda *args:effects.append('called'))
                    if mutation=='function':factory.function=replacement.function
                    else:session.interpreter.types['typedescription']=replacement
                    try:
                        with self.assertRaisesRegex(BoundaryViolation,'constructor registration'):bound('String')
                    finally:
                        factory.function=original;session.interpreter.types['typedescription']=factory
                self.assertEqual(effects,[])

    def test_source_session_cannot_gain_database_or_foreign_form(self):
        app,controller=self.controller();session=controller.server.session
        with app.safe_mode.execution():
            original=session.interpreter.database_context;session.interpreter._database_context=object()
            try:
                with self.assertRaisesRegex(BoundaryViolation,'scope'):check_source_session(session)
            finally:session.interpreter._database_context=original
        with self.boundary(app,session) as boundary:
            original=session.form;session.form=controller.client.session.form
            try:
                with self.assertRaises(BoundaryViolation):boundary._check()
            finally:session.form=original


if __name__=='__main__':unittest.main()

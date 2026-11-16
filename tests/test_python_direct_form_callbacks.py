import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.form_runtime import FormSession
from yadinassi.callbacks import BSLCallbackDescription
from yadinassi.experimental_naked_boundaries import BoundaryViolation

SOURCE='''Var Observed;
Procedure Make() Capture(New CallbackDescription("Done",ThisObject));EndProcedure
Procedure Done(Result,Additional) Export Observed=Result;EndProcedure
'''
class DirectCallbackTests(unittest.TestCase):
    def make(self,source=SOURCE):
        session=FormSession(source);session._owned_form_enrollment=object();session.open();return session
    def capture(self,session):
        descriptions=[];session.interpreter.register_function('Capture',descriptions.append)
        session._begin(session.revision)
        try:session._invoke('Make','client',[])
        finally:session.revision+=1;session._busy=False;session._gate.release()
        return descriptions[0]
    def test_capability_capture_and_direct_completion(self):
        session=self.make()
        with patch.object(Interpreter,'dispatch_callback',side_effect=AssertionError('legacy callback')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')),patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')):
            callback=self.capture(session)
            self.assertIs(type(callback),BSLCallbackDescription)
            session.dispatch_completion(callback,'result',revision=session.revision)
        self.assertEqual(session.interpreter.variables['observed'],'result')
        self.assertFalse(session._busy);self.assertFalse(session._completion_active)
    def test_stale_enrollment_and_closed_owner_deny(self):
        session=self.make();callback=self.capture(session)
        session._owned_form_enrollment=object()
        with self.assertRaises(ValueError):session.dispatch_completion(callback,1,revision=session.revision)
        session=self.make();callback=self.capture(session);session.interpreter.close()
        with self.assertRaises((ValueError,BoundaryViolation)):session.dispatch_completion(callback,1,revision=session.revision)
    def test_nonexported_callback_denied_before_execution(self):
        session=self.make(SOURCE.replace(' Export',''));callback=self.capture(session)
        with self.assertRaises(ValueError):session.dispatch_completion(callback,1,revision=session.revision)
        self.assertIsNone(session.interpreter.variables['observed'])
    def test_constructor_requires_owned_self_form(self):
        session=FormSession(SOURCE);session.open()
        with self.assertRaises(BoundaryViolation):self.capture(session)
    def test_completion_failure_cleans_event(self):
        session=self.make(SOURCE.replace('Observed=Result','Observed=Result;x=1/0'));callback=self.capture(session)
        with self.assertRaises(Exception):session.dispatch_completion(callback,'partial',revision=session.revision)
        self.assertEqual(session.interpreter.variables['observed'],'partial')
        self.assertFalse(session._busy);self.assertFalse(session._completion_active)
    def test_validated_schema_names_refresh_without_body_or_value_recompile(self):
        from yadinassi.form_model import BSLFormAttribute
        from yadinassi.type_descriptions import BSLTypeDescription
        session=FormSession('Procedure Event() Capture(Field);EndProcedure')
        values=[];session.interpreter.register_function('Capture',values.append)
        # Mirrors the already-validated replica schema installation, not source.
        session.form._attributes['field']=BSLFormAttribute('Field',BSLTypeDescription('String'))
        session.form._static.add('field');session.form._data['field']='first'
        session.open();old=session._direct_handlers
        session._begin(session.revision)
        try:
            session._invoke('Event','client',[])
            current=session._direct_handlers
            self.assertIsNot(current,old)
            session.form._data['field']='second'
            session._invoke('Event','client',[])
            self.assertIs(session._direct_handlers,current)
        finally:session._busy=False;session._gate.release()
        self.assertEqual(values,['first','second'])
    def test_close_only_uses_existing_owned_command_admission(self):
        session=self.make('Procedure CloseIt() ThisObject.Close("result");EndProcedure')
        results=[];session._owned_close=results.append
        session._begin(session.revision)
        try:session._invoke('CloseIt','client',[])
        finally:session._busy=False;session._gate.release()
        self.assertEqual(results,['result'])

"""Form references keep their authority rules under generated operand evaluation."""
import unittest
from yadinassi.execution.execution_policy import execution_backend_policy
from yadinassi.forms.form_runtime import FormSession
from yadinassi.forms.form_model import BSLFormAttribute
from yadinassi.types.type_descriptions import BSLTypeDescription
import test_configuration_app as config_tests

class TranslatedFormArgumentsTests(unittest.TestCase):
    def modes(self):
        return ('python-direct',)
    def open_form(self, body, *, backend):
        source='''&AtClient
Procedure Change(Value)
 Value = "changed";
EndProcedure
&AtClient
Procedure Open(Cancel)
'''+body+'\nEndProcedure'
        with execution_backend_policy(backend):
            session=FormSession(source,attributes=(BSLFormAttribute('Name',BSLTypeDescription('String')),),bindings={'OnOpen':'Open'})
            result=session.open()
            self.addCleanup(lambda: session.dispatch('close',revision=session.revision) if not session.closed else None)
            self.assertEqual(session.interpreter.execution_backend, 'python-direct')
            return session,result
    def test_local_scalar_reference(self):
        for backend in self.modes():
            with self.subTest(backend=backend):
                session,result=self.open_form('Local="before";Change(Local);ThisObject.Name=Local;',backend=backend)
                self.assertEqual(session.form._data['name'],'changed')
    def test_local_shadow_keeps_form_attribute_unchanged(self):
        for backend in self.modes():
            with self.subTest(backend=backend):
                session,result=self.open_form('Var Name;Name="local";Change(Name);',backend=backend)
                self.assertEqual(session.form._data['name'],'')
    def test_explicit_form_attribute_reference(self):
        for backend in self.modes():
            with self.subTest(backend=backend):
                session,result=self.open_form('Change(ThisObject.Name);',backend=backend)
                self.assertEqual(session.form._data['name'],'changed')
    def test_implicit_form_attribute_byref_still_rejected(self):
        for backend in self.modes():
            with self.subTest(backend=backend):
                with self.assertRaisesRegex(Exception,'передача реквизита без Знач'):
                    self.open_form('Change(Name);',backend=backend)
    def test_configuration_context_nocontext_sequence_direct(self):
        with execution_backend_policy('python-direct'):
            test=config_tests.ConfigurationApplicationTests('test_client_and_context_nocontext_sequences_are_independent')
            result=unittest.TestResult();test.run(result)
            self.assertEqual(result.testsRun,1)
            self.assertEqual(result.errors,[])
            self.assertEqual(result.failures,[])

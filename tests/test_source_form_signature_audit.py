"""Static binder-shaped diagnostics are not execution or native parity proof."""
import unittest
from unittest.mock import patch
from test_source_forms import FORM,CODE
import test_source_form_projection as projection_tests
from yadinassi.source_form_handler_audit import audit_handler_names
from yadinassi.form_program import compile_form_module

class SourceSignatureAuditTests(unittest.TestCase):
    controller=projection_tests.SourceFormProjectionTests.controller
    def audit(self, code=CODE, raw=FORM):
        return audit_handler_names(raw,compile_form_module(code.decode()))

    def test_valid_contracts_and_reference_counts(self):
        result=self.audit();self.assertEqual(result['signature_issues'],[])
        self.assertEqual(result['signature_references'],2)

    def test_wrong_command_side_arity_and_function_have_static_diagnostics(self):
        cases=[b'&AtServer\nProcedure Go(Command)\nEndProcedure',b'&AtClient\nProcedure Go()\nEndProcedure',b'&AtClient\nFunction Go(Command)\nReturn 1;\nEndFunction',b'&AtServerNoContext\nProcedure Go(Val Command)\nEndProcedure']
        for code in cases:
            with self.subTest(code=code):
                result=self.audit(code);self.assertEqual(len(result['signature_issues']),1)
                self.assertIn('requires client procedure(1)',result['signature_issues'][0])
                self.assertNotIn('Go',result['missing'])

    def test_server_lifecycle_contract_and_russian_alias(self):
        raw=FORM.replace(b'OnCreateAtServer','ПриСозданииНаСервере'.encode())
        self.assertEqual(self.audit(raw=raw)['signature_issues'],[])
        wrong=CODE.replace(b'Created(Cancel, StandardProcessing)',b'Created(Cancel)')
        self.assertIn('requires server procedure(2)',self.audit(wrong,raw)['signature_issues'][0])

    def test_field_change_checks_client_single_argument(self):
        raw=FORM.replace(b'</LabelField>',b'<Events><Event name="OnChange">UpdateAtServer</Event></Events></LabelField>')
        result=self.audit(raw=raw)
        self.assertEqual(result['signature_references'],3)
        self.assertIn('Item.GreetingLabel.onchange',result['signature_issues'][0])

    def test_shared_name_checked_per_distinct_event_contract(self):
        raw=FORM.replace(b'</Events></Form>',b'<Event name="OnOpen">Created</Event></Events></Form>')
        result=self.audit(raw=raw)
        self.assertEqual(len(result['signature_issues']),1)
        self.assertIn('Form.onopen',result['signature_issues'][0])

    def test_defaults_and_reference_parameters_not_overrestricted(self):
        code=CODE.replace(b'Go(Command)',b'Go(Command = Undefined)')
        self.assertEqual(self.audit(code)['signature_issues'],[])

    def test_no_runtime_and_duplicate_event_alias_fails_closed(self):
        with patch('yadinassi.runtime.Interpreter.__init__',side_effect=AssertionError('no runtime')):
            self.assertEqual(self.audit()['status'],'names-checked')
        raw=FORM.replace(b'</Events></Form>','<Event name="ПриСозданииНаСервере">Created</Event></Events></Form>'.encode())
        self.assertEqual(self.audit(raw=raw)['status'],'unavailable')

    def test_signature_issue_list_bounded(self):
        commands=b''.join(('<Command name="C%d" id="%d"><Action>Wrong</Action></Command>'%(i,i+1)).encode() for i in range(25))
        raw=FORM[:FORM.index(b'<Commands>')]+b'<Commands>'+commands+b'</Commands></Form>'
        result=self.audit(b'&AtClient\nProcedure Wrong()\nEndProcedure',raw)
        self.assertEqual(len(result['signature_issues']),16);self.assertEqual(result['omitted_signature_issues'],9)

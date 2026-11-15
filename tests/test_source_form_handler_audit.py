import unittest
from unittest.mock import patch
import test_source_workspace as workspace_tests
from test_source_workspace import request
from test_source_forms import files, FORM, CODE

class SourceHandlerAuditTests(unittest.TestCase):
    workspace=workspace_tests.SourceWorkspaceTests.workspace
    def check(self, source=None):
        w=self.workspace(source or files())
        return w,w.exchange(request('preflight',name='CommonForm.Main'))['result']['state']['module_preflight']

    def test_declared_names_are_not_runtime_or_context_proof(self):
        with patch('yadinassi.configuration_forms.FormDefinition.create_server',side_effect=AssertionError('no runtime')):
            w,p=self.check()
        self.assertEqual(p['handler_names']['status'],'names-checked')
        self.assertEqual(p['handler_names']['missing'],[])
        self.assertGreater(p['handler_names']['referenced'],0)
        self.assertFalse(p['bindings_checked']);self.assertFalse(p['runtime_checked']);self.assertFalse(w.open_forms)

    def test_missing_name_reported_while_compilation_stays_successful(self):
        source=files(b'&AtClient\nProcedure Other()\nEndProcedure')
        _,p=self.check(source)
        self.assertEqual(p['status'],'compiled');self.assertTrue(p['handler_names']['missing'])
        self.assertFalse(p['bindings_checked'])

    def test_variables_are_not_routines_and_case_insensitive_routines_match(self):
        source=files(CODE.lower());_,p=self.check(source)
        self.assertEqual(p['handler_names']['missing'],[])
        source=files(b'&AtClient\nVar Go;');_,p=self.check(source)
        self.assertTrue(p['handler_names']['missing'])

    def test_missing_and_invalid_xml_do_not_relabel_compilation(self):
        for xml in (None,b'<Unsupported/>'):
            source=files()
            if xml is None:del source['CommonForms/Main/Ext/Form.xml']
            else:source['CommonForms/Main/Ext/Form.xml']=xml
            _,p=self.check(source)
            self.assertEqual(p['status'],'compiled');self.assertEqual(p['handler_names']['status'],'unavailable')
            self.assertTrue(p['handler_names']['error'])

    def test_removed_unknown_events_are_not_admitted(self):
        source=files();source['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'<Events>',b'<Events><Event name="UnknownEvent">ForeignHandler</Event>',1)
        _,p=self.check(source)
        self.assertNotIn('ForeignHandler',p['handler_names']['missing'])

    def test_nested_snapshot_cannot_mutate_saved_evidence(self):
        w,p=self.check(files(b''));before=list(p['handler_names']['missing'])
        p['handler_names']['missing'].append('injected')
        self.assertEqual(w.snapshot()['state']['module_preflight']['handler_names']['missing'],before)

    def test_failed_compilation_has_no_name_claim(self):
        _,p=self.check(files(b'Procedure Invalid('))
        self.assertEqual(p['status'],'unavailable');self.assertIsNone(p['handler_names'])

    def test_missing_list_is_bounded_and_malformed_reference_is_not_checked(self):
        from yadinassi.source_form_handler_audit import audit_handler_names
        from yadinassi.form_program import compile_form_module
        program=compile_form_module('')
        commands=b''.join(('<Command name="C%d" id="%d"><Action>Missing%d</Action></Command>'%(i,i+1,i)).encode() for i in range(25))
        raw=FORM[:FORM.index(b'<Commands>')]+b'<Commands>'+commands+b'</Commands></Form>'
        result=audit_handler_names(raw,program)
        self.assertEqual(result['status'],'names-checked');self.assertEqual(len(result['missing']),16)
        self.assertGreaterEqual(result['omitted_missing'],9)
        bad=raw.replace(b'<Action>',b'<Action extra="1">',1)
        self.assertEqual(audit_handler_names(bad,program)['status'],'unavailable')

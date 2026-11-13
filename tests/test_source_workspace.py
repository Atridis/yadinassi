import unittest
from threading import Event, Thread
from unittest.mock import patch
from test_source_forms import files, FORM, request as form_request
from test_source_metadata import xml
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.ui.source_workspace import SourceWorkspace


def request(method='snapshot', **params):
    return {'jsonrpc':'2.0','id':1,'method':'workspace.'+method,'params':params}


class SourceWorkspaceTests(unittest.TestCase):
    def workspace(self, mapping=None):
        app=SourceApplication(import_source(files() if mapping is None else mapping))
        self.addCleanup(app.close);app.start();return SourceWorkspace(app)

    def test_inventory_and_open_roundtrip(self):
        w=self.workspace(); self.assertEqual(w.snapshot()['state']['forms'],['CommonForm.Main'])
        state=w.exchange(request('open',name='CommonForm.Main'))['result']['state']
        self.assertTrue(state['active']);self.assertIsNone(state['error'])
        result=w.exchange(request('form',generation=1,request=form_request()))['result']
        self.assertEqual(result['result']['state']['kind'],'form')

    def test_repeated_open_keeps_current_form(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));first=w.form
        state=w.exchange(request('open',name='CommonForm.Main'))['result']['state']
        self.assertIs(w.form,first);self.assertEqual(state['generation'],1);self.assertIsNone(state['error'])

    def test_stale_generation_refused(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'))
        with self.assertRaisesRegex(ValueError,'stale'):w.exchange(request('form',generation=0,request=form_request()))

    def test_unlisted_form_refused(self):
        w=self.workspace()
        with self.assertRaisesRegex(ValueError,'declared'):w.exchange(request('open',name='CommonForm.Nope'))

    def test_unsupported_form_reports_error_without_killing_workspace(self):
        mapping=files();mapping['CommonForms/Main/Ext/Form.xml']=b'<Unsupported/>'
        w=self.workspace(mapping);state=w.exchange(request('open',name='CommonForm.Main'))['result']['state']
        self.assertIsNotNone(state['error']);self.assertFalse(state['active']);w.application.require_open()
        self.assertEqual(w.exchange(request())['result']['state']['kind'],'workspace')

    def test_close_with_active_form_refused(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'))
        state=w.exchange(request('close'))['result']['state'];self.assertEqual(state['kind'],'workspace');self.assertIsNotNone(state['error'])

    def test_close_empty_workspace(self):
        w=self.workspace();self.assertEqual(w.exchange(request('close'))['result']['state']['kind'],'closed')
        with self.assertRaisesRegex(ValueError,'closed'):w.exchange(request('open',name='CommonForm.Main'))

    def test_close_form_then_reopen_does_not_close_application(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));w.form.exchange(form_request())
        reply=w.form.exchange(form_request('event',event='close',revision=w.form.client.session.revision))
        self.assertEqual(reply['result']['state']['kind'],'closed');w.application.require_open()
        state=w.exchange(request('open',name='CommonForm.Main'))['result']['state'];self.assertEqual(state['generation'],2)

    def test_concurrent_open_and_close_are_rejected_during_form_creation(self):
        w=self.workspace();entered=Event();release=Event();errors=[]
        from yadinassi.source_forms import SourceFormController
        def create(*args, **kwargs):
            entered.set()
            if not release.wait(5):raise RuntimeError('test timeout')
            return SourceFormController(*args, **kwargs)
        def opening():
            try:w.exchange(request('open',name='CommonForm.Main'))
            except Exception as error:errors.append(error)
        with patch('yadinassi.ui.source_workspace.SourceFormController',side_effect=create):
            worker=Thread(target=opening);worker.start()
            try:
                self.assertTrue(entered.wait(5))
                for command in (request('open',name='CommonForm.Main'),request('close'),request('form',generation=0,request=form_request())):
                    with self.assertRaisesRegex(ValueError,'busy'):w.exchange(command)
            finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,[]);self.assertEqual(w.generation,1)

    def test_large_unicode_inventory_is_byte_bounded_and_searchable(self):
        from yadinassi.ui.protocol import encode_line, MAX_LINE_BYTES
        w=self.workspace();w.forms=tuple('Catalog.'+'Я'*128+'.Form.'+'Ю'*120+str(i) for i in range(512))
        state=w.exchange(request())['result']['state']
        self.assertGreater(state['omitted_forms'],0)
        self.assertLess(len(encode_line(w.exchange(request()))),MAX_LINE_BYTES)
        state=w.exchange(request('search',query='511'))['result']['state']
        self.assertEqual(state['forms'],[w.forms[-1]]);self.assertEqual(state['omitted_forms'],0)

    def test_search_filters_without_compiling_forms(self):
        w=self.workspace()
        self.assertEqual(w.exchange(request('search',query='none'))['result']['state']['forms'],[])
        self.assertEqual(w.exchange(request('search',query='MAIN'))['result']['state']['forms'],['CommonForm.Main'])
        self.assertIsNone(w.form)

    def many_forms(self, count=2):
        mapping=files()
        for i in range(1,count):
            name='Other'+str(i)
            mapping['Configuration.xml']=mapping['Configuration.xml'].replace(b'</ChildObjects>',('<CommonForm>'+name+'</CommonForm></ChildObjects>').encode())
            mapping['CommonForms/'+name+'.xml']=xml('CommonForm',name,properties='<FormType>Managed</FormType>')
            mapping['CommonForms/'+name+'/Ext/Form.xml']=FORM
            mapping['CommonForms/'+name+'/Ext/Form/Module.bsl']=mapping['CommonForms/Main/Ext/Form/Module.bsl']
        return mapping

    def test_two_forms_preserve_independent_state_when_switching(self):
        w=self.workspace(self.many_forms());w.exchange(request('open',name='CommonForm.Main'));first=w.form
        first.exchange(form_request());first.exchange(form_request('event',event='command',revision=first.client.session.revision,control='GoButton'))
        w.exchange(request('open',name='CommonForm.Other1'));second=w.form;second.exchange(form_request())
        self.assertEqual(dict(second.client.session.snapshot().attributes)['Greeting'],'Demo')
        w.exchange(request('select',generation=1));self.assertIs(w.form,first)
        self.assertEqual(dict(first.client.session.snapshot().attributes)['Greeting'],'updated')
        self.assertEqual(len(w.snapshot()['state']['open_forms']),2)

    def test_hidden_form_events_are_not_retargeted(self):
        w=self.workspace(self.many_forms());w.exchange(request('open',name='CommonForm.Main'));w.exchange(request('open',name='CommonForm.Other1'))
        with self.assertRaisesRegex(ValueError,'stale'):w.exchange(request('form',generation=1,request=form_request()))
        w.exchange(request('select',generation=1));self.assertIsNotNone(w.exchange(request('form',generation=1,request=form_request())))

    def test_search_while_form_open_preserves_form(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));first=w.form
        state=w.exchange(request('search',query='missing'))['result']['state']
        self.assertEqual(state['forms'],[]);self.assertIs(w.form,first);self.assertTrue(state['active'])

    def test_close_selected_does_not_allow_closing_other_live_form(self):
        w=self.workspace(self.many_forms());w.exchange(request('open',name='CommonForm.Main'));w.exchange(request('open',name='CommonForm.Other1'))
        w.form.exchange(form_request());w.form.exchange(form_request('event',event='close',revision=w.form.client.session.revision))
        state=w.exchange(request('close'))['result']['state'];self.assertEqual(state['kind'],'workspace');self.assertTrue(state['any_active'])

    def test_open_limit_does_not_discard_any_live_form(self):
        w=self.workspace(self.many_forms(9))
        for name in w.forms[:8]:w.exchange(request('open',name=name))
        before=dict(w.open_forms);state=w.exchange(request('open',name=w.forms[8]))['result']['state']
        self.assertIn('предел',state['error']);self.assertEqual(w.open_forms,before)

    def test_closed_slot_pruned_and_never_reuses_identity(self):
        w=self.workspace(self.many_forms());w.exchange(request('open',name='CommonForm.Main'))
        w.form.exchange(form_request());w.form.exchange(form_request('event',event='close',revision=w.form.client.session.revision))
        w.exchange(request('open',name='CommonForm.Other1'))
        self.assertEqual(list(w.open_forms),[2])
        with self.assertRaisesRegex(ValueError,'unknown'):w.exchange(request('select',generation=1))

    def test_unknown_selection_and_boolean_identity_refused(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'))
        for key in (True,0,2,'1'):
            with self.assertRaisesRegex(ValueError,'unknown'):w.exchange(request('select',generation=key))

    def test_failed_second_open_preserves_first_form(self):
        mapping=self.many_forms();mapping['CommonForms/Other1/Ext/Form.xml']=b'<Broken/>'
        w=self.workspace(mapping);w.exchange(request('open',name='CommonForm.Main'));first=w.form
        state=w.exchange(request('open',name='CommonForm.Other1'))['result']['state']
        self.assertIsNotNone(state['error']);self.assertIs(w.form,first);self.assertEqual(len(w.open_forms),1)

"""Deferred navigation is committed after a successful user change, never replayed."""
import unittest
import test_source_workspace as workspace_tests
from test_source_workspace import request, form_request
from test_source_forms import FORM

class SourceChangeNavigationTests(unittest.TestCase):
    workspace=workspace_tests.SourceWorkspaceTests.workspace
    many_forms=workspace_tests.SourceWorkspaceTests.many_forms
    def setup_workspace(self,body='OpenForm("CommonForm.Other1",New Structure("Greeting",Greeting));',side='AtClient'):
        mapping=self.many_forms()
        mapping['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'LabelField',b'InputField').replace(b'<DataPath>Greeting</DataPath>',b'<DataPath>Greeting</DataPath><Events><Event name="OnChange">Changed</Event></Events>')
        code='&AtServer\nProcedure Created(Cancel,StandardProcessing)\nGreeting="parent";\nEndProcedure\n&AtClient\nProcedure Go(Command)\nEndProcedure\n&AtClient\nProcedure Changed(Item)\n'
        code+=body if side=='AtClient' else 'ServerChanged();'
        code+='\nEndProcedure'
        if side!='AtClient':code+='\n&AtServer\nProcedure ServerChanged()\n'+body+'\nEndProcedure'
        mapping['CommonForms/Main/Ext/Form/Module.bsl']=code.encode()
        mapping['CommonForms/Other1/Ext/Form/Module.bsl']=b'&AtServer\nProcedure Created(Cancel,StandardProcessing)\nGreeting=Parameters.Greeting;\nEndProcedure\n&AtClient\nProcedure Go(Command)\nEndProcedure'
        w=self.workspace(mapping);w.exchange(request('open',name='CommonForm.Main'));w.exchange(request('form',generation=1,request=form_request()))
        return w
    def change(self,w,**overrides):
        values={'event':'change','revision':w.open_forms[1][1].client.session.revision,'control':'GreetingLabel','value':{'type':'String','value':'edited'}};values.update(overrides)
        return w.exchange(request('form',generation=1,request=form_request('event',**values)))

    def test_child_parameters_capture_changed_value_and_parent_remains(self):
        w=self.setup_workspace('p=New Structure("Greeting",Greeting);OpenForm("CommonForm.Other1",p);p.Greeting="later";')
        reply=self.change(w);self.assertIsNone(reply['result']['result']['error']);self.assertEqual(w.selected,'CommonForm.Other1');self.assertEqual(w.generation,2)
        w.exchange(request('form',generation=2,request=form_request()));self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'edited')
        w.exchange(request('select',generation=1));self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'edited')

    def test_failure_discards_intent_and_snapshot_never_replays(self):
        w=self.setup_workspace('OpenForm("CommonForm.Other1");Raise "stop";')
        reply=self.change(w);self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(w.generation,1);self.assertEqual(len(w.open_forms),1);self.assertEqual(w.pending_navigation,[])
        for _ in range(2):w.exchange(request());w.exchange(request('form',generation=1,request=form_request('snapshot')))
        self.assertEqual(len(w.open_forms),1)

    def test_stale_revision_or_invalid_control_cannot_open(self):
        for overrides in ({'revision':999},{'control':'Absent'},{'value':{'type':'Unknown','value':'3'}}):
            w=self.setup_workspace()
            with self.subTest(overrides=overrides):
                try:reply=self.change(w,**overrides)
                except ValueError:pass
                else:self.assertIsNotNone(reply['result']['result']['error'])
                self.assertEqual(len(w.open_forms),1);self.assertEqual(w.pending_navigation,[])

    def test_repeated_wire_event_cannot_duplicate_child(self):
        w=self.setup_workspace();revision=w.form.client.session.revision;self.change(w)
        with self.assertRaisesRegex(ValueError,'stale'):self.change(w,revision=revision)
        w.exchange(request('select',generation=1));reply=self.change(w,revision=revision)
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),2)

    def test_server_and_capacity_keep_parent_without_open(self):
        for server in (True,False):
            w=self.setup_workspace(side='AtServer' if server else 'AtClient')
            if not server:w.navigation_total=256
            reply=self.change(w);self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1);self.assertEqual(w.generation,1)

    def test_client_onopen_does_not_acquire_change_event_scope(self):
        mapping=self.many_forms()
        mapping['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'</Events>',b'<Event name="OnOpen">Opened</Event></Events>')
        mapping['CommonForms/Main/Ext/Form/Module.bsl']+=b'\n&AtClient\nProcedure Opened(Cancel)\nOpenForm("CommonForm.Other1");\nEndProcedure'
        w=self.workspace(mapping);w.exchange(request('open',name='CommonForm.Main'))
        reply=w.exchange(request('form',generation=1,request=form_request()))
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1);self.assertEqual(w.pending_navigation,[])

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

    def test_object_inventory_filters_declared_metadata_without_compiling(self):
        w=self.workspace()
        state=w.exchange(request('objects',query='helpers',family='CommonModule'))['result']['state']
        self.assertEqual(state['objects'],['CommonModule.Helpers']);self.assertIsNone(w.form)
        detail=w.exchange(request('inspect',name='CommonModule.Helpers'))['result']['state']['object_detail']
        self.assertEqual(detail['execution'],'metadata_only');self.assertFalse(detail['storage_granted'])
        self.assertEqual(detail['forms'],[]);self.assertEqual(detail['source_path'],'CommonModules/Helpers.xml')

    def test_object_common_form_can_open_despite_unrelated_form_search(self):
        w=self.workspace();w.exchange(request('search',query='missing'))
        detail=w.exchange(request('inspect',name='CommonForm.Main'))['result']['state']['object_detail']
        self.assertEqual(detail['forms'],['CommonForm.Main'])
        self.assertTrue(w.exchange(request('open',name='CommonForm.Main'))['result']['state']['active'])

    def test_object_inspection_requires_visible_identity_and_known_family(self):
        w=self.workspace();w.exchange(request('objects',query='Helpers',family=''))
        for name in ('CommonForm.Main','missing'):
            with self.assertRaisesRegex(ValueError,'visible'):w.exchange(request('inspect',name=name))
        for query,family in [('x'*129,''),('', 'Arbitrary'),(None,'')]:
            with self.assertRaisesRegex(ValueError,'search'):w.exchange(request('objects',query=query,family=family))

    def test_object_navigation_keeps_open_form_state(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));first=w.form
        w.exchange(request('objects',query='Helpers',family='CommonModule'));w.exchange(request('inspect',name='CommonModule.Helpers'))
        self.assertIs(w.form,first);self.assertEqual(w.generation,1)

    def test_catalog_owned_form_association_uses_exact_owner(self):
        mapping=files();mapping['Configuration.xml']=mapping['Configuration.xml'].replace(b'</ChildObjects>',b'<Catalog>Items</Catalog><Catalog>ItemsOther</Catalog></ChildObjects>')
        for name in ('Items','ItemsOther'):
            mapping['Catalogs/'+name+'.xml']=xml('Catalog',name,children='<Form>Main</Form>')
            from uuid import uuid5, NAMESPACE_URL
            raw=xml('Form','Main',properties='<FormType>Managed</FormType>')
            mapping['Catalogs/'+name+'/Forms/Main.xml']=raw.replace(str(uuid5(NAMESPACE_URL,'Form/Main')).encode(),str(uuid5(NAMESPACE_URL,name+'/Form/Main')).encode())
            mapping['Catalogs/'+name+'/Forms/Main/Ext/Form.xml']=FORM
            mapping['Catalogs/'+name+'/Forms/Main/Ext/Form/Module.bsl']=mapping['CommonForms/Main/Ext/Form/Module.bsl']
        w=self.workspace(mapping)
        detail=w.exchange(request('inspect',name='Catalog.Items'))['result']['state']['object_detail']
        self.assertEqual(detail['forms'],['Catalog.Items.Form.Main'])
        w.exchange(request('search',query='none'));self.assertTrue(w.exchange(request('open',name=detail['forms'][0]))['result']['state']['active'])

    def test_object_inventory_utf8_budget_and_search_all_names(self):
        from types import SimpleNamespace
        from yadinassi.ui.protocol import encode_line,MAX_LINE_BYTES
        w=self.workspace();w.objects={'Catalog.'+'Я'*120+str(i):SimpleNamespace(family='Catalog',path='Catalogs/Item.xml') for i in range(500)};w.object_families=['Catalog']
        state=w.snapshot()['state'];self.assertGreater(state['omitted_objects'],0)
        self.assertLess(len(encode_line(w.exchange(request()))),MAX_LINE_BYTES)
        state=w.exchange(request('objects',query='499',family='Catalog'))['result']['state']
        self.assertEqual(len(state['objects']),1);self.assertEqual(state['omitted_objects'],0)

    def test_family_inventory_is_byte_bounded(self):
        from types import SimpleNamespace
        from yadinassi.ui.protocol import encode_line,MAX_LINE_BYTES
        app=SimpleNamespace(require_open=lambda:None,constant_store=None,source=SimpleNamespace(name='Demo'))
        app.metadata=SimpleNamespace(_inventory={str(i)+'.xml':SimpleNamespace(path=str(i)+'.xml',family='Future'+'Я'*100+str(i),name='Entry') for i in range(2000)})
        w=SourceWorkspace(app);self.assertGreater(w.snapshot()['state']['omitted_families'],0)
        self.assertLess(len(encode_line(w.exchange(request()))),MAX_LINE_BYTES)

    def test_ambiguous_logical_metadata_identity_fails_explicitly(self):
        from types import SimpleNamespace
        app=SimpleNamespace(require_open=lambda:None,constant_store=None)
        app.metadata=SimpleNamespace(_inventory={p:SimpleNamespace(path=p,family='CommonForm',name='Same') for p in ('CommonForms/Same.xml','Other/Same.xml')})
        with self.assertRaisesRegex(ValueError,'ambiguous metadata full name'):
            SourceWorkspace(app)
        app.metadata._inventory['Other/Same.xml'].name='same'
        with self.assertRaisesRegex(ValueError,'ambiguous metadata full name'):
            SourceWorkspace(app)

    def navigation_workspace(self, command='OpenForm("CommonForm.Other1", New Structure("Greeting", "from-parent"));', side='AtClient'):
        mapping=self.many_forms()
        mapping['CommonForms/Main/Ext/Form/Module.bsl']=('&AtServer\nProcedure Created(Cancel, StandardProcessing)\n Greeting="parent";\nEndProcedure\n&'+side+'\nProcedure Go(Command)\n'+command+'\nEndProcedure').encode()
        if side == 'AtServer':
            mapping['CommonForms/Main/Ext/Form/Module.bsl']=('&AtServer\nProcedure Created(Cancel, StandardProcessing)\nEndProcedure\n&AtServer\nProcedure ServerGo()\n'+command+'\nEndProcedure\n&AtClient\nProcedure Go(Command)\nServerGo();\nEndProcedure').encode()
        mapping['CommonForms/Other1/Ext/Form/Module.bsl']=b'&AtServer\nProcedure Created(Cancel, StandardProcessing)\n Greeting=Parameters.Greeting;\nEndProcedure\n&AtClient\nProcedure Go(Command)\n Greeting="child";\nEndProcedure'
        return self.workspace(mapping)

    def invoke_navigation(self,w):
        w.exchange(request('open',name='CommonForm.Main'))
        w.exchange(request('form',generation=w.generation,request=form_request()))
        return w.exchange(request('form',generation=w.generation,request=form_request('event',event='command',revision=w.form.client.session.revision,control='GoButton')))

    def test_bsl_openform_creates_child_with_typed_parameters(self):
        w=self.navigation_workspace();reply=self.invoke_navigation(w)
        self.assertIsNone(reply['result']['result']['error']);self.assertEqual(w.selected,'CommonForm.Other1');self.assertEqual(len(w.open_forms),2)
        w.exchange(request('form',generation=w.generation,request=form_request()))
        self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'from-parent')
        w.exchange(request('select',generation=1));self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'parent')

    def test_russian_openform_alias(self):
        w=self.navigation_workspace('ОткрытьФорму("CommonForm.Other1", Новый Структура("Greeting", "ru"));');self.invoke_navigation(w)
        w.exchange(request('form',generation=w.generation,request=form_request()))
        self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'ru')

    def test_navigation_parameters_are_snapshotted_before_later_mutation(self):
        w=self.navigation_workspace('p=New Structure("Greeting","before"); OpenForm("CommonForm.Other1",p); p.Greeting="after";');self.invoke_navigation(w)
        w.exchange(request('form',generation=w.generation,request=form_request()))
        self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'before')

    def test_failed_handler_discards_deferred_navigation(self):
        w=self.navigation_workspace('OpenForm("CommonForm.Other1"); Raise "stop";');reply=self.invoke_navigation(w)
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1);self.assertEqual(w.pending_navigation,[])
        w.exchange(request());self.assertEqual(len(w.open_forms),1)

    def test_undeclared_target_and_unsupported_owner_arguments_fail(self):
        for command in ('OpenForm("CommonForm.Missing");','OpenForm("CommonForm.Other1",Undefined,ThisObject);','OpenForm("CommonForm.Other1",New Array);'):
            with self.subTest(command=command):
                w=self.navigation_workspace(command);reply=self.invoke_navigation(w)
                self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1)

    def test_server_handler_cannot_enqueue_client_navigation(self):
        w=self.navigation_workspace('OpenForm("CommonForm.Other1");',side='AtServer');reply=self.invoke_navigation(w)
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1)

    def test_navigation_capacity_does_not_discard_open_forms(self):
        w=self.navigation_workspace();w.navigation_total=256;reply=self.invoke_navigation(w)
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1)

    def test_idle_or_hidden_navigation_callback_refused(self):
        w=self.navigation_workspace();w.exchange(request('open',name='CommonForm.Main'));interpreter=w.form.client.session.interpreter
        with self.assertRaisesRegex(ValueError,'active client'):interpreter._open_source_form('CommonForm.Other1')
        w.exchange(request('open',name='CommonForm.Other1'))
        with self.assertRaisesRegex(ValueError,'inactive'):w._request_navigation(1,'CommonForm.Main')

    def test_broken_target_keeps_original_form_and_visible_diagnostic(self):
        mapping=self.many_forms();mapping['CommonForms/Other1/Ext/Form.xml']=b'<Broken/>'
        mapping['CommonForms/Main/Ext/Form/Module.bsl']=b'&AtServer\nProcedure Created(Cancel,StandardProcessing)\nEndProcedure\n&AtClient\nProcedure Go(Command)\nOpenForm("CommonForm.Other1");\nEndProcedure'
        w=self.workspace(mapping);self.invoke_navigation(w)
        self.assertEqual(w.selected,'CommonForm.Main');self.assertIn('OpenForm CommonForm.Other1',w.exchange(request())['result']['state']['error']);self.assertEqual(len(w.open_forms),1)

    def test_onchange_navigation_is_explicit_error_not_stale_generation(self):
        mapping=self.many_forms()
        mapping['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'LabelField',b'InputField').replace(b'<DataPath>Greeting</DataPath>',b'<DataPath>Greeting</DataPath><Events><Event name="OnChange">Changed</Event></Events>')
        mapping['CommonForms/Main/Ext/Form/Module.bsl']+=b'\n&AtClient\nProcedure Changed(Item)\nOpenForm("CommonForm.Other1");\nEndProcedure'
        w=self.workspace(mapping);w.exchange(request('open',name='CommonForm.Main'));w.exchange(request('form',generation=1,request=form_request()))
        reply=w.exchange(request('form',generation=1,request=form_request('event',event='change',revision=w.form.client.session.revision,control='GreetingLabel',value={'type':'String','value':'edit'})))
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(w.generation,1);self.assertEqual(len(w.open_forms),1)

class SourceStartupNavigationTests(unittest.TestCase):
    def app(self, code, form_code=None):
        mapping=files() if form_code is None else files(form_code)
        mapping['Ext/ManagedApplicationModule.bsl']=code.encode()
        app=SourceApplication(import_source(mapping));self.addCleanup(app.close)
        return app

    def test_onstart_opens_actual_form_with_copied_parameters(self):
        app=self.app('''Procedure OnStart()
 P = New Structure("Text", "startup");
 OpenForm("CommonForm.Main", P);
 P.Text = "changed";
EndProcedure''', b'''&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = Parameters.Text;
EndProcedure
&AtClient
Procedure Go(Command)
EndProcedure''')
        w=SourceWorkspace.start(app)
        self.assertEqual(w.selected,'CommonForm.Main')
        self.assertIsNone(w.form.exchange(form_request())['result']['error'])
        self.assertEqual(dict(w.form.client.session.snapshot().attributes)['Greeting'],'startup')
        for _ in range(2):w.exchange(request())
        self.assertEqual(len(w.open_forms),1)
        with self.assertRaisesRegex(ValueError,'fresh'):SourceWorkspace.start(app)

    def test_cancel_discards_pending_and_never_constructs_form(self):
        app=self.app('''Procedure BeforeStart(Cancel)
 OpenForm("CommonForm.Main"); Cancel = True;
EndProcedure''')
        with patch('yadinassi.ui.source_workspace.SourceFormController') as create:
            self.assertIsNone(SourceWorkspace.start(app));create.assert_not_called()
        self.assertEqual(app.state,'cancelled')

    def test_exception_discards_pending_and_never_constructs_form(self):
        app=self.app('''Procedure OnStart()
 OpenForm("CommonForm.Main"); Raise "startup failed";
EndProcedure''')
        with patch('yadinassi.ui.source_workspace.SourceFormController') as create:
            with self.assertRaises(Exception):SourceWorkspace.start(app)
            create.assert_not_called()
        self.assertEqual(app.state,'failed')

    def test_unknown_form_is_visible_error_without_destroying_session(self):
        w=SourceWorkspace.start(self.app('OpenForm("CommonForm.Absent");'))
        self.assertIn('declared source form',w.error)
        self.assertEqual(w.open_forms,{})
        w.application.require_open()
        w.exchange(request('open',name='CommonForm.Main'))
        self.assertEqual(w.selected,'CommonForm.Main')

    def test_startup_queue_is_bounded(self):
        app=self.app('For I = 1 To 9 Do OpenForm("CommonForm.Main"); EndDo;')
        with patch('yadinassi.ui.source_workspace.SourceFormController') as create:
            with self.assertRaises(Exception):SourceWorkspace.start(app)
            create.assert_not_called()
        self.assertEqual(app.state,'failed')

    def test_startup_capability_does_not_survive_start(self):
        app=self.app('');SourceWorkspace.start(app)
        with self.assertRaises(Exception):app.interpreter.execute('OpenForm("CommonForm.Main");')

    def test_invalid_parameters_do_not_open_any_forms(self):
        app=self.app('OpenForm("CommonForm.Main", New Array);')
        with patch('yadinassi.ui.source_workspace.SourceFormController') as create:
            with self.assertRaises(Exception):SourceWorkspace.start(app)
            create.assert_not_called()
        self.assertEqual(app.state,'failed')

    def test_headless_startup_does_not_gain_openform(self):
        app=self.app('OpenForm("CommonForm.Main");')
        with self.assertRaises(Exception):app.start()
        self.assertEqual(app.state,'failed')

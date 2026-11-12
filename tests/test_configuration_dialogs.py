"""Negotiated host dialogs using real BSL/replicas. No synthetic native claims."""
from decimal import Decimal
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from test_configuration_form_results import HostFixture
from configuration_form_results_fixture import OWNER_MODULE, OPEN
from configuration_dialog_fixture import sources, QUESTION, WARNING
from yadinassi import Interpreter, BSLError
from yadinassi.configuration_application_profile import import_application_configuration
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.form_dialogs import DIALOG_CAPABILITY, DialogReturnCode, QuestionDialogMode
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, PROTOCOL
from yadinassi.ui.protocol import encode_line, decode_line
from yadinassi.values import BSLType


class DialogFixture(HostFixture):
    def host(self, files=None, *, negotiated=True, business=False):
        files=sources() if files is None else files
        database=None
        if business:
            from yadinassi.configuration_business_profile import import_business_configuration
            from yadinassi.sqlite_catalog import SQLiteCatalogBackend
            temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
            database=Path(temporary.name)/'dialogs.sqlite'
            SQLiteCatalogBackend.create_business_application(database,files).close()
            imported=import_business_configuration(files)
            configuration=load_configuration_forms(files,catalog_schemas=imported.catalogs,document_schemas=imported.documents)
            flags={'business_application':True}
        else:
            imported=import_application_configuration(files)
            configuration=load_configuration_forms(files,catalog_schemas=imported.catalogs)
            flags={'application_host':True}
        broker=ConfigurationBroker(configuration,database,**flags); self.addCleanup(broker.close)
        packets=[]
        def pipe(raw):
            q=decode_line(raw); packets.append(q)
            result=broker.exchange({k:q[k] for k in ('operation','session','payload')})
            return encode_line({'id':q['id'],'session':q['session'],'result':result,'error':None})
        app=ConfigurationController(configuration,pipe,**flags); self.addCleanup(app.close)
        self.rpc(app,'hello',protocol=PROTOCOL,**({'dialogCapability':DIALOG_CAPABILITY} if negotiated else {}))
        return broker,app,packets

    def pending(self, files=None):
        broker,app,packets=self.host(files)
        owner=self.open(app)
        response=self.event(app,owner)
        self.assertIsNone(response['error'],response)
        self.assertIsNone(response['form']['result']['error'],response)
        self.assertEqual(len(response['dialogs']),1,response)
        return broker,app,packets,owner,response['dialogs'][0]

    def answer(self, app, owner, dialog, answer='yes'):
        return self.rpc(app,'answerDialog',session=owner,ticket=dialog['ticket'],answer=answer)

    def refused(self, files, *, negotiated=True):
        _,app,_=self.host(files,negotiated=negotiated); owner=self.open(app)
        r=self.event(app,owner)
        self.assertIsNotNone(r['form']['result']['error'],r)
        self.assertFalse(app.owner_dialogs); self.assertFalse(app.dialogs)
        return app,owner,r


class DialogHostTests(DialogFixture,unittest.TestCase):
    def test_explicit_capability_is_echoed_on_every_response(self):
        _,app,_=self.host()
        for method,params in (('hello',{'protocol':PROTOCOL,'dialogCapability':DIALOG_CAPABILITY}),('snapshot',{})):
            r=self.rpc(app,method,**params)
            self.assertEqual(r['dialogCapability'],DIALOG_CAPABILITY); self.assertEqual(r['dialogs'],[])
        owner=self.open(app); self.assertIsNotNone(owner)
        self.assertEqual(self.rpc(app,'snapshot')['dialogs'],[])

    def test_legacy_family_has_no_new_fields_or_invisible_queue(self):
        app,_,r=self.refused(sources(),negotiated=False)
        self.assertNotIn('dialogs',r); self.assertNotIn('dialogCapability',r)
        self.assertNotIn('dialogs',self.rpc(app,'snapshot'))

    def test_negotiation_cannot_change_after_first_hello(self):
        for negotiated in (False,True):
            with self.subTest(negotiated=negotiated):
                _,app,_=self.host(negotiated=negotiated)
                with self.assertRaises(ValueError):
                    self.rpc(app,'hello',protocol=PROTOCOL,**({} if negotiated else {'dialogCapability':DIALOG_CAPABILITY}))

    def test_unknown_capability_does_not_negotiate(self):
        _,app,_=self.host()
        with self.assertRaises(ValueError): self.rpc(app,'hello',protocol=PROTOCOL,dialogCapability='future/9')
        self.assertTrue(app._dialog_capability)

    def test_forms_only_can_echo_capability_without_acquiring_dialog_authority(self):
        from test_configuration_forms import sources as legacy_sources
        configuration=load_configuration_forms(legacy_sources())
        broker=ConfigurationBroker(configuration); self.addCleanup(broker.close)
        def pipe(raw):
            q=decode_line(raw)
            return encode_line({'id':q['id'],'session':q['session'],'error':None,
                'result':broker.exchange({k:q[k] for k in ('operation','session','payload')})})
        app=ConfigurationController(configuration,pipe); self.addCleanup(app.close)
        result=self.rpc(app,'hello',protocol=PROTOCOL,dialogCapability=DIALOG_CAPABILITY)
        self.assertEqual(result['dialogs'],[]); self.assertEqual(result['dialogCapability'],DIALOG_CAPABILITY)
        self.assertNotIn('updates',result)
        owner=self.open(app); descriptor=self.rpc(app,'snapshot')['state']['sessions'][0]
        self.assertEqual(set(descriptor),{'id','entry','title'})
        with self.assertRaises(ValueError): app._application_show_warning(None,'no authority')
        self.assertEqual(app.owner_dialogs,{})

    def test_nonblocking_command_publishes_closed_plain_descriptor(self):
        _,app,packets,owner,d=self.pending()
        self.assertEqual(self.greeting(app,owner),'waiting')
        self.assertEqual(set(d),{'ticket','owner','kind','title','text','choices'})
        self.assertRegex(d['ticket'],'^[0-9a-f]{32}$'); self.assertEqual(d['owner'],owner)
        self.assertEqual((d['kind'],d['text'],d['title']),('question','Continue?',''))
        self.assertEqual(d['choices'],['yes','no','cancel'])
        self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.assertFalse(any(p['payload'].get('operation')=='sync' for p in packets))
        self.assertNotIn('Completed',encode_line(d).decode())

    def test_question_result_is_typed_and_additional_identity_is_retained(self):
        broker,app,_,owner,d=self.pending(); extra=self.extra(app,owner)
        callback=app.dialogs[d['ticket']].callback
        self.assertIs(callback.module,app.sessions[owner][0].session.form)
        self.assertIs(callback.additional_parameters,extra)
        r=self.answer(app,owner,d)
        self.assertIsNone(r['error'],r); self.assertEqual(r['session'],owner); self.assertEqual(r['updates'],[])
        self.assertEqual(r['dialogs'],[]); self.assertEqual(self.greeting(app,owner),'yes')
        self.assertEqual(broker.sessions[owner][0].session.form._data['greeting'],'yes')
        self.assertIs(app.sessions[owner][0].session.interpreter.variables['seen'],DialogReturnCode.YES)
        self.assertIs(self.extra(app,owner),extra); self.assertEqual(extra.get('Calls'),1)

    def test_all_question_modes_admit_only_their_typed_answers(self):
        for mode,choices in [('OK',['ok']),('OKCancel',['ok','cancel']),('YesNo',['yes','no']),('YesNoCancel',['yes','no','cancel'])]:
            for answer in choices:
                with self.subTest(mode=mode,answer=answer):
                    _,app,_,owner,d=self.pending(sources(showing=QUESTION.replace('YesNoCancel',mode)))
                    self.assertEqual(d['choices'],choices)
                    self.assertIsNone(self.answer(app,owner,d,answer)['error'])
                    self.assertIs(app.sessions[owner][0].session.interpreter.variables['seen'],DialogReturnCode(answer))

    def test_warning_dispatches_exactly_one_additional_argument(self):
        _,app,_,owner,d=self.pending(sources(warning=True)); extra=self.extra(app,owner)
        self.assertEqual((d['kind'],d['choices']),('warning',['dismiss']))
        r=self.answer(app,owner,d,'dismiss')
        self.assertIsNone(r['error'],r); self.assertEqual(self.greeting(app,owner),'dismissed')
        self.assertEqual(extra.get('Calls'),1)

    def test_question_and_warning_title_overloads(self):
        for warning,showing in [(False,'ShowQueryBox(Callback,"plain <tag>",QuestionDialogMode.YesNo,Undefined,Undefined,"A title");'),
                                 (True,'ShowMessageBox(Callback,"plain <tag>",Undefined,"A title");')]:
            with self.subTest(warning=warning):
                _,_,_,_,d=self.pending(sources(warning=warning,showing=showing))
                self.assertEqual((d['text'],d['title']),('plain <tag>','A title'))

    def test_russian_calls_and_enum_aliases(self):
        for warning,showing in [(False,'ПоказатьВопрос(Callback,"Вопрос",РежимДиалогаВопрос.ДаНет);'),
                                 (True,'ПоказатьПредупреждение(Callback,"Сообщение");')]:
            with self.subTest(warning=warning):
                _,app,_,owner,d=self.pending(sources(warning=warning,showing=showing))
                self.assertIsNone(self.answer(app,owner,d,'dismiss' if warning else 'yes')['error'])

    def test_nonexistent_english_aliases_are_not_invented(self):
        for showing in (QUESTION.replace('ShowQueryBox','ShowQuestion'),WARNING.replace('ShowMessageBox','ShowWarning')):
            with self.subTest(showing=showing): self.refused(sources(showing=showing))

    def test_explicit_unsupported_timeout_default_and_extra_slots_fail(self):
        bad=['ShowQueryBox(Callback,"x",QuestionDialogMode.OK,1,Undefined,"t");',
             'ShowQueryBox(Callback,"x",QuestionDialogMode.OK,Undefined,DialogReturnCode.OK,"t");',
             'ShowQueryBox(Callback,"x",QuestionDialogMode.OK,Undefined);',
             'ShowQueryBox(Callback,"x",QuestionDialogMode.OK,Undefined,Undefined,"t",Undefined);',
             'ShowMessageBox(Callback,"x",1,"t");','ShowMessageBox(Callback,"x",Undefined);']
        for showing in bad:
            with self.subTest(showing=showing): self.refused(sources(showing=showing))

    def test_omitted_slots_are_not_implicitly_accepted(self):
        self.refused(sources(showing='ShowQueryBox(Callback,"x",QuestionDialogMode.OK,,,"title");'))

    def test_mode_is_exact_enum_not_string_number_or_return_code(self):
        for mode in ('"YesNo"','1','DialogReturnCode.Yes','Undefined'):
            with self.subTest(mode=mode): self.refused(sources(showing=QUESTION.replace('QuestionDialogMode.YesNoCancel',mode)))

    def test_callback_is_required_and_kind_arity_is_closed(self):
        for files in (sources(showing=QUESTION.replace('Callback,','Undefined,')),
                      sources(warning=True,showing=QUESTION),sources(showing=WARNING)):
            self.refused(files)

    def test_unknown_and_wrong_owner_ticket_do_not_consume(self):
        _,app,_,owner,d=self.pending(); sibling=self.open(app,token='sibling')
        self.assertEqual(self.answer(app,sibling,d)['error'],'dialog_refused')
        self.assertEqual(self.answer(app,owner,dict(d,ticket='f'*32))['error'],'dialog_refused')
        self.assertEqual(app.dialogs[d['ticket']].state,'open')
        self.assertIsNone(self.answer(app,owner,d)['error'])

    def test_inadmissible_choice_does_not_consume_question_or_warning(self):
        for warning,answer in ((False,'dismiss'),(True,'ok')):
            with self.subTest(warning=warning):
                _,app,_,owner,d=self.pending(sources(warning=warning))
                self.assertEqual(self.answer(app,owner,d,answer)['error'],'dialog_refused')
                self.assertEqual(self.extra(app,owner).get('Calls'),0)
                self.assertEqual(app.dialogs[d['ticket']].state,'open')

    def test_repeated_or_changed_late_answer_never_replays(self):
        _,app,packets,owner,d=self.pending(); self.answer(app,owner,d); count=len(packets)
        for answer in ('yes','no','cancel'):
            self.assertEqual(self.answer(app,owner,d,answer)['error'],'dialog_retired')
        self.assertEqual(len(packets),count); self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_owner_business_close_and_reference_paused_snapshot_allowed(self):
        _,app,packets,owner,d=self.pending(); count=len(packets)
        for event in ('command','close'):
            self.assertEqual(self.event(app,owner,event=event)['error'],'dialog_pending')
        r=self.rpc(app,'reference',session=owner,revision=app.sessions[owner][0].session.revision,action={})
        self.assertEqual(r['error'],'dialog_pending'); self.assertEqual(r['session'],owner)
        r=self.rpc(app,'form',session=owner,request={'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
        self.assertIsNone(r['form']['result']['error']); self.assertEqual(len(packets),count)
        self.assertTrue(next(s for s in r['state']['sessions'] if s['id']==owner)['blocked'])

    def test_sibling_is_not_authority_locked_by_another_owner_dialog(self):
        _,app,_,owner,d=self.pending(); sibling=self.open(app,token='sibling')
        r=self.event(app,sibling)
        self.assertIsNone(r['form']['result']['error']); self.assertEqual(len(r['dialogs']),2)
        self.assertNotEqual(r['dialogs'][0]['ticket'],r['dialogs'][1]['ticket'])
        self.assertEqual(self.extra(app,owner).get('Calls'),0)

    def test_failed_event_discards_unpublished_dialog(self):
        self.refused(sources(suffix='Raise "after queue";'))

    def test_second_dialog_same_event_drops_first(self):
        self.refused(sources(showing=QUESTION+'\n'+QUESTION))

    def test_openform_after_dialog_is_rejected_without_hidden_work(self):
        app,_,_=self.refused(sources(suffix='OpenForm("CommonForm.Details");'))
        self.assertFalse(app.pending); self.assertEqual(len(app.sessions),1)

    def test_owned_child_open_prevents_dialog_queue(self):
        app,_,_=self.refused(sources(showing=OPEN+'\n'+QUESTION))
        self.assertFalse(app.pending); self.assertFalse(app.owner_children)

    def test_completion_reentrancy_is_explicitly_refused(self):
        for ending in (QUESTION,'OpenForm("CommonForm.Details");','ThisObject.Close();'):
            with self.subTest(ending=ending):
                _,app,_,owner,d=self.pending(sources(completion='Extra.Calls=Extra.Calls+1; '+ending))
                r=self.answer(app,owner,d)
                self.assertEqual(r['error'],'completion_failed'); self.assertEqual(r['dialogs'],[])
                self.assertEqual(self.extra(app,owner).get('Calls'),1); self.assertFalse(app.pending)

    def test_callback_partial_mutation_then_error_is_authoritative_not_rolled_back(self):
        broker,app,_,owner,d=self.pending(sources(completion='Greeting="partial"; Extra.Calls=Extra.Calls+1; Raise "failed";'))
        r=self.answer(app,owner,d)
        self.assertEqual(r['error'],'completion_failed'); self.assertEqual(r['form']['result']['error'],'event_failed')
        self.assertEqual(self.greeting(app,owner),'partial')
        self.assertEqual(broker.sessions[owner][0].session.form._data['greeting'],'partial')
        self.assertEqual(app.dialogs[d['ticket']].state,'failed')
        self.assertEqual(self.answer(app,owner,d)['error'],'dialog_retired')

    def test_retired_enrollment_does_not_deliver(self):
        _,app,_,owner,d=self.pending(); app.sessions[owner][0].session._owned_form_enrollment=object()
        self.assertEqual(self.answer(app,owner,d)['error'],'retired_session')
        self.assertEqual(self.extra(app,owner).get('Calls'),0); self.assertEqual(app.owner_dialogs,{})

    def test_changed_family_generation_does_not_deliver(self):
        _,app,_,owner,d=self.pending(); root=app.application.interpreter; generation=root._family_generation
        root._family_generation+=1
        try:
            self.assertEqual(self.answer(app,owner,d)['error'],'retired_session')
            self.assertEqual(self.extra(app,owner).get('Calls'),0)
        finally: root._family_generation=generation

    def test_terminal_tombstone_releases_callback_and_additional(self):
        _,app,_,owner,d=self.pending(); vm=app.sessions[owner][0].session.interpreter
        cbref=weakref.ref(app.dialogs[d['ticket']].callback); extra=weakref.ref(self.extra(app,owner))
        self.answer(app,owner,d); record=app.dialogs[d['ticket']]
        self.assertEqual((record.callback,record.enrollment,record.result),(None,None,None))
        vm.variables['callback']=None; vm.variables['extra']=None; gc.collect()
        self.assertIsNone(cbref()); self.assertIsNone(extra())

    def test_capacity_refuses_before_publication_or_handler(self):
        with patch('yadinassi.ui.configuration_app.MAX_DIALOGS',0): self.refused(sources())

    def test_ticket_collision_does_not_replace_existing_receipt(self):
        _,app,_,owner,d=self.pending(); sibling=self.open(app,token='sibling')
        with patch('yadinassi.ui.configuration_app.token_hex',return_value=d['ticket']):
            r=self.event(app,sibling)
        self.assertIsNotNone(r['form']['result']['error']); self.assertEqual(len(app.dialogs),1)
        self.assertEqual(app.dialogs[d['ticket']].owner,owner)

    def test_text_title_and_control_character_budgets(self):
        for showing in (QUESTION.replace('Continue?','x'*4097),
                        'ShowQueryBox(Callback,"x",QuestionDialogMode.OK,Undefined,Undefined,"'+'t'*257+'");',
                        QUESTION.replace('"Continue?"', '"bad" + Char(0) + "text"')):
            with self.subTest(length=len(showing)): self.refused(sources(showing=showing))

    def test_missing_negotiation_rejects_answer_endpoint(self):
        _,app,_=self.host(negotiated=False); owner=self.open(app)
        with self.assertRaises(ValueError): self.rpc(app,'answerDialog',session=owner,ticket='0'*32,answer='yes')

    def test_unknown_sync_before_callback_retains_envelope_without_replay(self):
        _,app,packets,owner,d=self.pending(); transport=app.transport
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='form' and q['payload'].get('operation')=='sync': raise OSError('lost reply')
            return reply
        app.transport=lost
        r=self.answer(app,owner,d)
        self.assertEqual(r['error'],'outcome_unknown'); self.assertTrue(app.uncertain)
        self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.assertEqual(app.dialogs[d['ticket']].state,'uncertain'); self.assertIsNotNone(app.dialogs[d['ticket']].callback)
        count=len(packets); self.answer(app,owner,d); self.assertEqual(len(packets),count)

    def test_unknown_sync_after_callback_keeps_one_partial_effect(self):
        _,app,_,owner,d=self.pending(); transport=app.transport; syncs=[]
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='form' and q['payload'].get('operation')=='sync':
                syncs.append(q)
                if len(syncs)==2: raise OSError('lost after callback')
            return reply
        app.transport=lost
        r=self.answer(app,owner,d)
        self.assertEqual(r['error'],'outcome_unknown'); self.assertEqual(self.extra(app,owner).get('Calls'),1)
        self.assertEqual(self.greeting(app,owner),'yes'); self.assertIn(owner,app.owner_dialogs)

    def test_caught_unknown_server_call_during_callback_cannot_become_known_failed(self):
        files=sources(completion='Extra.Calls=Extra.Calls+1; Try Service.Add(4); Except EndTry; Greeting="after unknown";')
        _,app,_,owner,d=self.pending(files); transport=app.transport
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='applicationInvoke': raise OSError('lost server result')
            return reply
        app.transport=lost
        r=self.answer(app,owner,d)
        self.assertEqual(r['error'],'outcome_unknown'); self.assertEqual(app.dialogs[d['ticket']].state,'uncertain')
        self.assertIsNotNone(app.dialogs[d['ticket']].callback); self.assertIn(owner,app.owner_dialogs)
        self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_interruption_locks_and_keeps_envelope(self):
        _,app,_,owner,d=self.pending(); session=app.sessions[owner][0].session
        with patch.object(session,'dispatch_completion',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.answer(app,owner,d)
        self.assertTrue(app.uncertain); self.assertEqual(app.dialogs[d['ticket']].state,'uncertain')
        self.assertFalse(app.gate.locked()); self.assertFalse(session._gate.locked())

    def test_application_start_cannot_create_ownerless_dialog(self):
        files=sources(); files['Ext/ManagedApplicationModule.bsl']=b'Procedure OnStart() ShowMessageBox(Undefined,"no owner"); EndProcedure'
        _,app,_=self.host(files)
        self.assertFalse(app.owner_dialogs); self.assertFalse(app.dialogs); self.assertTrue(app.uncertain)

    def test_source_dialog_common_module_delegation_preserves_owner(self):
        files=sources(showing='Tools.Ask(Callback);')
        files['CommonModules/Tools/Ext/Module.bsl']+=b'\nProcedure Ask(Val Completion) Export ShowQueryBox(Completion,"via common",QuestionDialogMode.YesNo); EndProcedure'
        _,app,_,owner,d=self.pending(files)
        self.assertEqual(d['text'],'via common'); self.assertIsNone(self.answer(app,owner,d)['error'])

    def test_server_activation_cannot_invoke_client_dialog_service(self):
        files=sources(showing='ServerAsk();')
        files[OWNER_MODULE]+=b'\n&AtServer\nProcedure ServerAsk() ShowMessageBox(Undefined,"server"); EndProcedure'
        self.refused(files)


class DialogBusinessTests(DialogFixture,unittest.TestCase):
    def business_source(self,kind,*,save=False,fail=False):
        from configuration_form_results_fixture import business_sources
        files=business_sources(kind,save=save,fail=fail)
        prefix='Catalogs/Items/Forms/Card' if kind=='catalog' else 'Documents/Orders/Forms/Card'
        key=prefix+'/Ext/Form/Module.bsl'; field='Description' if kind=='catalog' else 'Number'
        files[key]=files[key].replace(OPEN.encode(),QUESTION.encode()).replace(
            ('Object.'+field+'=String(Result);').encode(),
            ('If Result=DialogReturnCode.Yes Then Object.'+field+'="approved"; EndIf;').encode())
        return files

    def test_catalog_and_document_owner_callbacks_do_not_implicitly_write(self):
        for kind in ('catalog','document'):
            with self.subTest(kind=kind):
                broker,app,_=self.host(self.business_source(kind),business=True)
                name='Catalog.Items.Form.Card' if kind=='catalog' else 'Document.Orders.Form.Card'
                owner=self.open(app,name); r=self.event(app,owner,'ChooseButton')
                self.assertIsNone(r['form']['result']['error'],r)
                d=r['dialogs'][0]; r=self.answer(app,owner,d)
                self.assertIsNone(r['error'],r); self.assertIsNone(broker.objects[owner].object._revision)
                definition=app.definitions[app.sessions[owner][1]]
                slot=dict(definition.object_fields)['Description' if kind=='catalog' else 'Number'].casefold()
                self.assertEqual(app.sessions[owner][0].session.form._data[slot],'approved')
                self.assertEqual(broker.sessions[owner][0].session.form._data[slot],'approved')

    def test_explicit_document_write_then_callback_error_is_not_replayed(self):
        broker,app,packets=self.host(self.business_source('document',save=True,fail=True),business=True)
        owner=self.open(app,'Document.Orders.Form.Card')
        self.rpc(app,'catalog',entry=app.sessions[owner][1])
        d=self.event(app,owner,'ChooseButton')['dialogs'][0]
        r=self.answer(app,owner,d)
        self.assertEqual(r['error'],'completion_failed')
        self.assertEqual([row['number'] for row in r['state']['catalog']['rows']],['approved'])
        self.assertIsNotNone(broker.objects[owner].object._revision)
        count=len(packets); self.answer(app,owner,d); self.assertEqual(len(packets),count)


class DialogExampleTests(DialogFixture,unittest.TestCase):
    def files(self):
        root=Path(__file__).resolve().parents[1]/'examples/configuration-dialogs'
        return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_authored_example_yes_and_warning_use_distinct_callback_arities(self):
        _,app,_=self.host(self.files()); owner=app.active
        question=self.event(app,owner,'QuestionButton')['dialogs'][0]
        r=self.answer(app,owner,question)
        self.assertIsNone(r['error'],r); self.assertEqual(self.greeting(app,owner),'Approved value')
        self.assertEqual(app.sessions[owner][0].session.form._data['completioncount'],1)
        warning=self.event(app,owner,'WarningButton')['dialogs'][0]
        r=self.answer(app,owner,warning,'dismiss')
        self.assertIsNone(r['error'],r); self.assertEqual(self.greeting(app,owner),'Approved value')
        self.assertEqual(app.sessions[owner][0].session.form._data['completioncount'],2)
        self.assertEqual(app.sessions[owner][0].session.form._data['lastanswer'],'Warning dismissed')

    def test_authored_example_cancel_preserves_draft_and_owned_form_flow(self):
        _,app,_=self.host(self.files()); owner=app.active
        d=self.event(app,owner,'QuestionButton')['dialogs'][0]
        self.answer(app,owner,d,'cancel')
        self.assertEqual(self.greeting(app,owner),'Editable owner draft')
        r=self.event(app,owner,'DetailsButton'); self.assertIsNone(r['error'],r)
        child=app.active; self.assertNotEqual(child,owner)
        self.event(app,child,'AcceptButton')
        self.assertEqual(app.sessions[owner][0].session.form._data['lastanswer'],'Owned form closed')
        self.assertFalse(app.owner_children); self.assertFalse(app.owner_dialogs)


class DialogValueTests(unittest.TestCase):
    def test_typeof_bilingual_identity_and_readonly_members(self):
        vm=Interpreter(output=lambda value:None); self.addCleanup(vm.close)
        for expression,kind in [('QuestionDialogMode.OK',BSLType.QUESTION_DIALOG_MODE),
                                ('РежимДиалогаВопрос.ДаНет',BSLType.QUESTION_DIALOG_MODE),
                                ('DialogReturnCode.Yes',BSLType.DIALOG_RETURN_CODE),
                                ('КодВозвратаДиалога.Отмена',BSLType.DIALOG_RETURN_CODE)]:
            self.assertIs(vm.execute('TypeOf('+expression+')'),kind)
        self.assertIs(vm.execute('DialogReturnCode.Yes'),vm.execute('КодВозвратаДиалога.Да'))
        with self.assertRaises(BSLError): vm.execute('DialogReturnCode.Yes=1;')

    def test_types_have_no_invented_internal_codecs(self):
        from yadinassi import serialization
        vm=Interpreter(output=lambda value:None); self.addCleanup(vm.close)
        for kind,expression in [(BSLType.QUESTION_DIALOG_MODE,'QuestionDialogMode.OK'),(BSLType.DIALOG_RETURN_CODE,'DialogReturnCode.OK')]:
            self.assertIn(kind,serialization._UNSUPPORTED_CODEC_TYPES); self.assertNotIn(kind,serialization._TYPE_IDS)
            with self.assertRaises(BSLError): vm.execute('ValueToStringInternal('+expression+');')
        for expression in ('QuestionDialogMode', 'DialogReturnCode', 'QuestionDialogMode.OK', 'DialogReturnCode.Yes'):
            with self.assertRaises(BSLError): vm.execute('String('+expression+');')

    def test_enum_is_not_a_scalar_form_or_invocation_packet(self):
        from yadinassi.invocation import _encode_scalar
        for value in (QuestionDialogMode.OK,DialogReturnCode.OK):
            with self.assertRaises((TypeError,ValueError)): _encode_scalar(value)

    def test_warning_does_not_change_public_runcallback_two_argument_contract(self):
        vm=Interpreter(output=lambda value:None); self.addCleanup(vm.close)
        vm.execute('Procedure One(Extra) Export EndProcedure\nC=New CallbackDescription("One",ThisObject);')
        with self.assertRaises(BSLError): vm.execute('RunCallback(C);')


if __name__=='__main__': unittest.main()

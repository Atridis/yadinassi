"""Real interpreter/replica owned lifecycle, not simulated/native window parity."""
from decimal import Decimal
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from configuration_form_results_fixture import sources, OPEN, OWNER_MODULE, CHILD_MODULE
from yadinassi.configuration_application_profile import import_application_configuration
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.form_results import freeze_result, result_value
from yadinassi.dates import date
from yadinassi.values import NULL
from yadinassi.structures import BSLStructure, BSLFixedStructure
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, PROTOCOL
from yadinassi.ui.local_app import LocalTransportError
from yadinassi.ui.protocol import decode_line, encode_line


class HostFixture:
    def host(self, files=None, *, business=False, family=True):
        files = sources() if files is None else files
        database = None
        if business:
            from yadinassi.configuration_business_profile import import_business_configuration
            from yadinassi.sqlite_catalog import SQLiteCatalogBackend
            temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
            database = Path(temporary.name)/'owned.sqlite'
            SQLiteCatalogBackend.create_business_application(database, files).close()
            imported = import_business_configuration(files)
            configuration = load_configuration_forms(files, catalog_schemas=imported.catalogs,
                                                     document_schemas=imported.documents)
            flags = {'business_application': True}
        else:
            imported = import_application_configuration(files)
            configuration = load_configuration_forms(files, catalog_schemas=imported.catalogs)
            flags = {'application_host': family}
        broker = ConfigurationBroker(configuration, database, **flags)
        self.addCleanup(broker.close)
        packets = []
        def pipe(raw):
            request = decode_line(raw); packets.append(request)
            result = broker.exchange({k: request[k] for k in ('operation', 'session', 'payload')})
            return encode_line({'id': request['id'], 'session': request['session'], 'result': result, 'error': None})
        app = ConfigurationController(configuration, pipe, **flags)
        self.addCleanup(app.close)
        self.rpc(app, 'hello', protocol=PROTOCOL)
        return broker, app, packets

    def rpc(self, app, method, **params):
        return app.exchange({'jsonrpc':'2.0', 'id':1, 'method':'application.'+method, 'params':params})['result']

    def open(self, app, name='CommonForm.Welcome', token='owner'):
        r = self.rpc(app, 'open', entry=app.names[name.casefold()], request=token)
        self.assertIsNone(r['error'], r)
        return r['session']

    def event(self, app, sid, control='DetailsButton', event='command', **extra):
        params = {'event':event, 'revision':app.sessions[sid][0].session.revision, **extra}
        if event != 'close': params['control'] = control
        return self.rpc(app, 'form', session=sid, request={
            'jsonrpc':'2.0','id':1,'method':'form.event','params':params})

    def pair(self, files=None):
        broker, app, packets = self.host(files)
        owner = self.open(app)
        r = self.event(app, owner)
        self.assertIsNone(r['form']['result']['error'], r)
        self.assertIsNone(r['error'], r)
        child = app.active
        self.assertNotEqual(owner, child)
        return broker, app, packets, owner, child

    def extra(self, app, owner):
        return app.sessions[owner][0].session.interpreter.variables['extra']

    def greeting(self, app, owner):
        return app.sessions[owner][0].session.form._data['greeting']

    def assert_open_refused(self, files):
        _, app, _ = self.host(files)
        owner = self.open(app)
        result = self.event(app, owner)
        self.assertIsNotNone(result['form']['result']['error'])
        self.assertEqual(list(app.sessions), [owner])
        self.assertFalse(app.pending)
        self.assertFalse(app.owner_children)
        return app, owner


class OwnedFormHostTests(HostFixture, unittest.TestCase):
    def test_family_capability_present_on_hello_and_empty_snapshot(self):
        _, app, _ = self.host()
        for method, params in (('hello', {'protocol':PROTOCOL}), ('snapshot', {})):
            r = self.rpc(app, method, **params)
            self.assertEqual(r['updates'], [])
            self.assertEqual(r['state']['sessions'], [])

    def test_legacy_response_remains_without_family_wire_capability(self):
        from test_configuration_forms import sources as legacy_sources
        configuration = load_configuration_forms(legacy_sources())
        broker = ConfigurationBroker(configuration); self.addCleanup(broker.close)
        def pipe(raw):
            q=decode_line(raw)
            return encode_line({'id':q['id'],'session':q['session'],'error':None,
                'result':broker.exchange({k:q[k] for k in ('operation','session','payload')})})
        app=ConfigurationController(configuration,pipe); self.addCleanup(app.close)
        self.assertNotIn('updates',self.rpc(app,'hello',protocol=PROTOCOL))
        sid=self.open(app)
        self.assertNotIn('owner',self.rpc(app,'snapshot')['state']['sessions'][0])
        self.assertEqual(sid, app.active)

    def test_owner_graph_and_callback_module_identity(self):
        _, app, _, owner, child = self.pair()
        states = {r['id']:r for r in self.rpc(app,'snapshot')['state']['sessions']}
        self.assertEqual(set(states[owner]), {'id','entry','title','owner','blocked'})
        self.assertIsNone(states[owner]['owner']); self.assertTrue(states[owner]['blocked'])
        self.assertEqual(states[child]['owner'],owner); self.assertFalse(states[child]['blocked'])
        description=app.owned_results[child].callback
        self.assertIs(description.get_member('Module'),app.sessions[owner][0].session.form)
        self.assertIs(description.get_member('AdditionalParameters'),self.extra(app,owner))

    def test_close_result_runs_once_after_remote_close_and_retire(self):
        _, app, packets, owner, child = self.pair()
        extra=self.extra(app,owner)
        before=len(packets)
        r=self.event(app,child,'AcceptButton')
        self.assertIsNone(r['error']); self.assertNotIn(child,app.sessions)
        self.assertEqual(self.greeting(app,owner),'chosen'); self.assertEqual(extra.get('Calls'),Decimal(1))
        operations=[(p['operation'],p['session'],p['payload'].get('operation')) for p in packets[before:]]
        retire=operations.index(('retire',child,None))
        self.assertLess(operations.index(('form',child,'close')),retire)
        self.assertTrue(all(n>retire for n,v in enumerate(operations) if v==('form',owner,'sync')))
        self.assertEqual(sum(v==('form',owner,'sync') for v in operations),2)
        self.assertEqual(r['session'],child); self.assertEqual(r['state']['active'],owner)
        self.assertEqual([u['session'] for u in r['updates']],[owner])
        self.assertEqual(r['updates'][0]['form']['id'],1)
        self.assertEqual(r['updates'][0]['form']['result']['state']['revision'],app.sessions[owner][0].session.revision)

    def test_plain_close_delivers_undefined(self):
        _, app, _, owner, child=self.pair(sources(completion='If Result=Undefined Then Greeting="empty"; EndIf; Extra.Calls=Extra.Calls+1;'))
        self.event(app,child,event='close')
        self.assertEqual(self.greeting(app,owner),'empty'); self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_thisobject_close_uses_same_lifecycle(self):
        _, app, _, owner, child=self.pair(sources(accept='ThisObject.Close("method");'))
        self.event(app,child,'AcceptButton'); self.assertEqual(self.greeting(app,owner),'method')

    def test_structure_result_detached_at_request_and_additional_shared(self):
        files=sources(accept='R=New Structure("Text", "first"); Close(R); R.Text="later";',
                      completion='Greeting=Result.Text; Extra.Calls=Extra.Calls+1;')
        _, app, _, owner, child=self.pair(files); extra=self.extra(app,owner)
        self.event(app,child,'AcceptButton')
        self.assertEqual(self.greeting(app,owner),'first'); self.assertIs(extra,self.extra(app,owner))
        self.assertEqual(extra.get('Calls'),1)

    def test_repeated_child_request_does_not_repeat_completion(self):
        _, app, packets, owner, child=self.pair()
        self.event(app,child,'AcceptButton'); count=len(packets)
        r=self.rpc(app,'form',session=child,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{'event':'close','revision':1}})
        self.assertEqual(r['error'],'retired_session'); self.assertEqual(r['updates'],[])
        self.assertEqual(len(packets),count); self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_live_child_blocks_owner_business_and_close_but_not_snapshot(self):
        _, app, packets, owner, child=self.pair(); count=len(packets)
        for event in ('command','close'):
            r=self.event(app,owner,event=event)
            self.assertEqual(r['error'],'owned_child_open')
            self.assertEqual(r['form']['result']['error'],'busy')
        r=self.rpc(app,'form',session=owner,request={'jsonrpc':'2.0','id':1,'method':'form.snapshot','params':{}})
        self.assertIsNone(r['form']['result']['error']); self.assertEqual(len(packets),count)
        self.assertIn(child,app.sessions)

    def test_second_owned_open_in_same_event_discards_both_pending_intents(self):
        self.assert_open_refused(sources(opening=OPEN+'\n'+OPEN))

    def test_blocked_reference_reply_preserves_owner_and_authoritative_snapshot(self):
        _, app, _, owner, child=self.pair()
        r=self.rpc(app,'reference',session=owner,revision=app.sessions[owner][0].session.revision,action={})
        self.assertEqual(r['error'],'owned_child_open'); self.assertEqual(r['session'],owner)
        self.assertEqual(r['form']['id'],1); self.assertEqual(r['form']['result']['error'],'busy')
        self.assertIn(child,app.sessions)

    def test_failed_owner_event_does_not_open_child(self):
        self.assert_open_refused(sources(opening=OPEN+'\nRaise "after queue";'))

    def test_unsupported_open_options_are_not_ignored(self):
        for index in range(3):
            options=['Undefined']*3; options[index]='True'
            opening='OpenForm("CommonForm.Details",Undefined,ThisObject,'+','.join(options)+',Callback);'
            with self.subTest(index=index): self.assert_open_refused(sources(opening=opening))

    def test_eighth_argument_and_omitted_option_rejected(self):
        for opening in (OPEN.replace('Callback);','Callback,Undefined);'),OPEN.replace('Undefined, Undefined, Undefined',', Undefined, Undefined')):
            with self.subTest(opening=opening): self.assert_open_refused(sources(opening=opening))

    def test_partial_positional_options_and_empty_owned_call_are_rejected(self):
        for count in (3,4,5,6,7):
            opening='OpenForm("CommonForm.Details",'+','.join(['Undefined']*(count-1))+');'
            with self.subTest(count=count): self.assert_open_refused(sources(opening=opening))

    def test_owner_and_completion_are_both_required(self):
        for opening in (OPEN.replace('ThisObject,','Undefined,'),OPEN.replace('Callback);','Undefined);')):
            with self.subTest(opening=opening): self.assert_open_refused(sources(opening=opening))

    def test_undeclared_or_nonform_target_rejected(self):
        for target in ('CommonForm.Missing','Catalog.Items.Form.Card'):
            with self.subTest(target=target): self.assert_open_refused(sources(opening=OPEN.replace('CommonForm.Details',target)))

    def test_invalid_completion_routines_fail_before_open(self):
        for change in ('private','arity','function','server'):
            files=sources()
            old=b'&AtClient\nProcedure Completed(Result, Extra) Export'
            new={'private':b'&AtClient\nProcedure Completed(Result, Extra)',
                 'arity':b'&AtClient\nProcedure Completed(Result) Export',
                 'function':b'&AtClient\nFunction Completed(Result, Extra) Export',
                 'server':b'&AtServer\nProcedure Completed(Result, Extra) Export'}[change]
            files[OWNER_MODULE]=files[OWNER_MODULE].replace(old,new)
            if change=='function':
                prefix,suffix=files[OWNER_MODULE].rsplit(b'EndProcedure',1)
                files[OWNER_MODULE]=prefix+b'EndFunction'+suffix
            with self.subTest(change=change): self.assert_open_refused(files)

    def test_ordinary_object_is_not_callback_module(self):
        files=sources(); files[OWNER_MODULE]=files[OWNER_MODULE].replace(b'"Completed", ThisObject, Extra',b'"Completed", Extra, Extra')
        self.assert_open_refused(files)

    def test_close_on_unowned_form_rejected_without_retirement(self):
        _, app, _=self.host(); child=self.open(app,'CommonForm.Details')
        r=self.event(app,child,'AcceptButton')
        self.assertIsNotNone(r['form']['result']['error']); self.assertIn(child,app.sessions)

    def test_failed_child_handler_discards_close_intent(self):
        _, app, _, owner, child=self.pair(sources(accept='Close("first"); Raise "later";'))
        r=self.event(app,child,'AcceptButton')
        self.assertIsNotNone(r['form']['result']['error']); self.assertIn(child,app.sessions)
        self.assertFalse(app._close_requests); self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.event(app,child,event='close'); self.assertEqual(self.extra(app,owner).get('Calls'),1)
        self.assertNotEqual(self.greeting(app,owner),'first')

    def test_invalid_result_does_not_queue_close_or_complete(self):
        _, app, _, owner, child=self.pair(sources(accept='Close(New Structure("Nested", New Structure));'))
        r=self.event(app,child,'AcceptButton')
        self.assertIsNotNone(r['form']['result']['error']); self.assertIn(child,app.sessions)
        self.assertFalse(app._close_requests); self.assertEqual(self.extra(app,owner).get('Calls'),0)

    def test_stale_child_revision_does_not_dispatch_close(self):
        _, app, packets, owner, child=self.pair(); count=len(packets)
        r=self.rpc(app,'form',session=child,request={'jsonrpc':'2.0','id':1,'method':'form.event',
            'params':{'event':'command','control':'AcceptButton','revision':0}})
        self.assertEqual(r['form']['result']['error'],'stale_revision'); self.assertIn(child,app.sessions)
        self.assertEqual(len(packets),count); self.assertEqual(self.extra(app,owner).get('Calls'),0)

    def test_double_close_in_handler_drops_first_request(self):
        _, app, _, owner, child=self.pair(sources(accept='Close("first"); Close("second");'))
        r=self.event(app,child,'AcceptButton')
        self.assertIsNotNone(r['form']['result']['error']); self.assertIn(child,app.sessions)
        self.assertEqual(self.extra(app,owner).get('Calls'),0); self.assertFalse(app._close_requests)

    def test_before_close_refusal_keeps_child_and_does_not_cache_result(self):
        files=sources(child_events='<Event name="BeforeClose">Closing</Event>',
            child_handlers='Var Refused;\n&AtClient\nProcedure Closing(Cancel,Quitting,Warning,Standard)\n If Refused=Undefined Then Cancel=True; Refused=True; EndIf;\nEndProcedure')
        _, app, _, owner, child=self.pair(files)
        self.event(app,child,'AcceptButton')
        self.assertIn(child,app.sessions); self.assertIn(owner,app.owner_children)
        self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.event(app,child,event='close')
        self.assertNotIn(child,app.sessions); self.assertNotEqual(self.greeting(app,owner),'chosen')
        self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_cancelled_child_open_unlocks_without_completion(self):
        files=sources(child_events='<Event name="OnOpen">Opened</Event>',
                      child_handlers='&AtClient\nProcedure Opened(Cancel) Cancel=True; EndProcedure')
        _, app, _=self.host(files); owner=self.open(app)
        r=self.event(app,owner)
        self.assertEqual(r['error'],'open_failed'); self.assertEqual(list(app.sessions),[owner])
        self.assertFalse(app.owner_children); self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.assertTrue(all(v.state=='opening_failed' and v.callback is None for v in app.owned_results.values()))

    def test_failed_child_open_does_not_complete(self):
        files=sources(child_events='<Event name="OnOpen">Opened</Event>',
                      child_handlers='&AtClient\nProcedure Opened(Cancel) Raise "opening"; EndProcedure')
        _, app, _=self.host(files); owner=self.open(app)
        self.assertEqual(self.event(app,owner)['error'],'open_failed')
        self.assertEqual(self.extra(app,owner).get('Calls'),0); self.assertFalse(app.owner_children)

    def test_programmatic_close_during_open_is_explicitly_refused(self):
        files=sources(child_events='<Event name="OnOpen">Opened</Event>',
                      child_handlers='&AtClient\nProcedure Opened(Cancel) Close("too early"); EndProcedure')
        _, app, _=self.host(files); owner=self.open(app)
        self.assertEqual(self.event(app,owner)['error'],'open_failed'); self.assertEqual(self.extra(app,owner).get('Calls'),0)

    def test_callback_partial_error_preserves_client_and_server_snapshot(self):
        files=sources(completion='Greeting="partial"; Extra.Calls=Extra.Calls+1; Message("before failure"); Raise "completion";')
        broker, app, _, owner, child=self.pair(files)
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'completion_failed'); self.assertNotIn(child,app.sessions)
        self.assertEqual(r['updates'][0]['form']['result']['error'],'event_failed')
        self.assertEqual(self.greeting(app,owner),'partial')
        self.assertEqual(broker.sessions[owner][0].session.form._data['greeting'],'partial')
        self.assertEqual(r['updates'][0]['form']['result']['state']['messages'],['before failure'])
        self.assertEqual(self.extra(app,owner).get('Calls'),1)
        self.assertEqual(app.owned_results[child].state,'failed'); self.assertIsNone(app.owned_results[child].callback)

    def test_reentrant_open_in_completion_is_rejected_after_partial_effect(self):
        _, app, _, owner, child=self.pair(sources(completion='Extra.Calls=Extra.Calls+1; OpenForm("CommonForm.Details");'))
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'completion_failed'); self.assertEqual(list(app.sessions),[owner])
        self.assertFalse(app.pending); self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_reentrant_close_in_completion_is_rejected(self):
        _, app, _, owner, child=self.pair(sources(completion='Extra.Calls=Extra.Calls+1; ThisObject.Close("nested");'))
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'completion_failed'); self.assertIn(owner,app.sessions)
        self.assertFalse(app._close_requests)

    def test_terminal_tombstone_drops_heavy_owner_capabilities(self):
        _, app, _, owner, child=self.pair()
        vm=app.sessions[owner][0].session.interpreter
        callback_ref=weakref.ref(app.owned_results[child].callback)
        extra_ref=weakref.ref(self.extra(app,owner))
        self.event(app,child,'AcceptButton')
        record=app.owned_results[child]
        self.assertEqual(record.state,'delivered')
        self.assertEqual((record.callback,record.enrollment,record.result),(None,None,None))
        # Source-level module variables legitimately own both values until BSL
        # releases them. The ledger must not extend that ownership. Full family
        # VM lifetime is an independent runtime contract, not this tombstone.
        vm.variables['callback']=None; vm.variables['extra']=None
        gc.collect()
        self.assertIsNone(callback_ref()); self.assertIsNone(extra_ref())
        self.event(app,owner,event='close'); self.assertIn(child,app.owned_results)

    def test_replaced_owner_enrollment_never_receives_callback(self):
        _, app, _, owner, child=self.pair(); extra=self.extra(app,owner)
        app.sessions[owner][0].session._owned_form_enrollment=object()
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'retired_session'); self.assertEqual(extra.get('Calls'),0)
        self.assertEqual(app.owned_results[child].state,'owner_retired'); self.assertIsNone(app.owned_results[child].callback)

    def test_generation_change_invalidates_sealed_target(self):
        _, app, _, owner, child=self.pair()
        vm=app.sessions[owner][0].session.interpreter; callback=app.owned_results[child].callback
        generation=vm._family_owner._family_generation
        vm._family_owner._family_generation+=1
        try:
            with self.assertRaisesRegex(ValueError,'retired or foreign'): vm.callback_target(callback)
        finally: vm._family_owner._family_generation=generation

    def test_foreign_family_cannot_dispatch_self_form_callback(self):
        _, app, _, owner, child=self.pair(); _, foreign, _=self.host()
        second=self.open(foreign)
        with self.assertRaisesRegex(ValueError,'retired or foreign'):
            foreign.sessions[second][0].session.interpreter.callback_target(app.owned_results[child].callback)

    def test_idle_form_callback_cannot_bypass_event_gate(self):
        _, app, _, owner, child=self.pair(); vm=app.sessions[owner][0].session.interpreter
        routine=vm.routines['completed']
        with self.assertRaisesRegex(ValueError,'trusted event'):
            vm._scheduler.run_inline(vm.dispatch_callback(app.owned_results[child].callback,'idle',routine.token))
        self.assertEqual(self.extra(app,owner).get('Calls'),0)

    def test_nested_owner_chain_closes_leaf_then_parent_once(self):
        files=sources(accept='If Callback=Undefined Then Callback=New CallbackDescription("ChildDone",ThisObject); '+OPEN+' Else Close("done"); EndIf;',
            child_handlers='Var Callback;\n&AtClient\nProcedure ChildDone(Result,Extra) Export MessageText="leaf completed"; EndProcedure')
        _, app, _, owner, child=self.pair(files)
        self.event(app,child,'AcceptButton'); leaf=app.active
        self.assertNotEqual(leaf,child)
        self.assertEqual(self.event(app,child,event='close')['error'],'owned_child_open')
        r=self.event(app,leaf,event='close')
        self.assertEqual([u['session'] for u in r['updates']],[child])
        self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.event(app,child,'AcceptButton'); self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_known_sync_no_handler_and_no_callback_payload_on_wire(self):
        _, app, packets, owner, child=self.pair()
        self.event(app,child,'AcceptButton')
        sync=[p['payload'] for p in packets if p['operation']=='form' and p['payload'].get('operation')=='sync']
        self.assertEqual(len(sync),2)
        for q in sync:
            self.assertEqual(q['endpoint'],0); self.assertEqual(q['arguments'],[])
            self.assertNotIn('Completed',encode_line(q).decode()); self.assertNotIn('CallbackDescription',encode_line(q).decode())

    def test_sync_rejects_unenrolled_server_before_delta(self):
        broker, app, _, owner, child=self.pair()
        server=broker.sessions[owner][0]; server._allow_host_sync=False
        revision=server.session.revision
        with self.assertRaises(Exception): app.sessions[owner][0].session.synchronize_owned()
        self.assertEqual(server.session.revision,revision)

    def test_transport_loss_after_retire_is_not_replayed(self):
        broker, app, packets, owner, child=self.pair(); transport=app.transport
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='retire' and q['session']==child: raise OSError('lost retirement reply')
            return reply
        app.transport=lost
        with self.assertRaises(LocalTransportError): self.event(app,child,'AcceptButton')
        self.assertNotIn(child,broker.sessions); self.assertIn(child,app.sessions)
        self.assertTrue(app.uncertain); self.assertEqual(self.extra(app,owner).get('Calls'),0)
        count=len(packets); self.assertEqual(self.rpc(app,'snapshot')['error'],'outcome_unknown')
        self.assertEqual(len(packets),count); self.assertIsNotNone(app.owned_results[child].callback)

    def test_unknown_close_never_retires_or_delivers(self):
        broker, app, packets, owner, child=self.pair(); transport=app.transport
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='form' and q['session']==child and q['payload'].get('operation')=='close': raise OSError('lost close')
            return reply
        app.transport=lost
        self.event(app,child,'AcceptButton')
        self.assertTrue(app.uncertain); self.assertIn(child,app.sessions); self.assertIn(child,broker.sessions)
        self.assertFalse(any(p['operation']=='retire' and p['session']==child for p in packets))
        self.assertEqual(self.extra(app,owner).get('Calls'),0)

    def test_unknown_sync_before_callback_locks_without_delivery(self):
        _, app, packets, owner, child=self.pair(); transport=app.transport
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='form' and q['session']==owner and q['payload'].get('operation')=='sync': raise OSError('lost sync')
            return reply
        app.transport=lost
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'outcome_unknown'); self.assertTrue(app.uncertain)
        self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.assertEqual(app.owned_results[child].state,'uncertain')
        self.assertIsNotNone(app.owned_results[child].callback)
        count=len(packets); self.rpc(app,'snapshot'); self.assertEqual(len(packets),count)

    def test_unknown_sync_after_callback_retains_one_mutation(self):
        _, app, _, owner, child=self.pair(); transport=app.transport; syncs=[]
        def lost(raw):
            q=decode_line(raw); reply=transport(raw)
            if q['operation']=='form' and q['session']==owner and q['payload'].get('operation')=='sync':
                syncs.append(q)
                if len(syncs)==2: raise OSError('lost final sync')
            return reply
        app.transport=lost
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'outcome_unknown'); self.assertEqual(self.extra(app,owner).get('Calls'),1)
        self.assertEqual(self.greeting(app,owner),'chosen'); self.assertEqual(app.owned_results[child].state,'uncertain')

    def test_callback_interruption_marks_terminal_unknown_and_releases_gates(self):
        _, app, _, owner, child=self.pair(); session=app.sessions[owner][0].session
        with patch.object(session,'dispatch_completion',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.event(app,child,'AcceptButton')
        self.assertTrue(app.uncertain); self.assertFalse(app.gate.locked()); self.assertFalse(session._gate.locked())
        self.assertEqual(app.owned_results[child].state,'uncertain')

    def test_retire_cleanup_interruption_does_not_deliver(self):
        _, app, _, owner, child=self.pair(); vm=app.sessions[child][0].session.interpreter
        with patch.object(vm,'close',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.event(app,child,'AcceptButton')
        self.assertTrue(app.uncertain); self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.assertEqual(app.owned_results[child].state,'uncertain')


class OwnedResultCodecTests(unittest.TestCase):
    def test_scalar_roundtrips(self):
        for value in (None,NULL,True,False,Decimal('123.4500'),'Кириллица',date('20240229123042')):
            with self.subTest(value=value): self.assertEqual(result_value(freeze_result(value)),value)

    def test_fixed_structure_returns_detached_structure(self):
        source=BSLStructure('A,B',Decimal(1),'b'); fixed=BSLFixedStructure(source)
        raw=freeze_result(fixed); source.set('A',Decimal(2))
        result=result_value(raw)
        self.assertIs(type(result),BSLStructure); self.assertEqual(result.get('A'),Decimal(1))

    def test_nested_or_capability_values_refused(self):
        from yadinassi.callbacks import BSLCallbackDescription
        for value in ([],{},object(),BSLCallbackDescription(),BSLStructure('Nested',BSLStructure())):
            with self.subTest(value=type(value).__name__),self.assertRaises((TypeError,ValueError)):
                freeze_result(value)

    def test_field_and_encoded_byte_limits(self):
        value=BSLStructure()
        for n in range(33): value.insert('F'+str(n),None)
        with self.assertRaisesRegex(ValueError,'field limit'): freeze_result(value)
        for n in range(33): value.set('F'+str(n),'x'*4096)
        value._items.pop('f32')
        with self.assertRaises(ValueError): freeze_result(value)


class OwnedFormExampleTests(HostFixture, unittest.TestCase):
    def files(self):
        root=Path(__file__).resolve().parents[1]/'examples/configuration-form-results'
        return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_authored_example_opens_and_completes_real_form_lifecycle(self):
        _,app,_=self.host(self.files()); owner=app.active
        self.assertIsNotNone(owner)
        self.event(app,owner); child=app.active
        r=self.event(app,child,'AcceptButton')
        self.assertIsNone(r['error'],r); self.assertEqual(self.greeting(app,owner),'A chosen value')
        self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_authored_example_beforeclose_refusal_then_plain_close(self):
        from yadinassi.ui.protocol import encode_value
        _,app,_=self.host(self.files()); owner=app.active
        self.event(app,owner); child=app.active
        self.event(app,child,'KeepOpenCheck',event='change',value=encode_value(True))
        self.event(app,child,'AcceptButton')
        self.assertIn(child,app.sessions); self.assertEqual(self.extra(app,owner).get('Calls'),0)
        self.event(app,child,'KeepOpenCheck',event='change',value=encode_value(False))
        self.event(app,child,event='close')
        self.assertEqual(self.greeting(app,owner),'Closed without a selection')
        self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_authored_example_plain_close_is_explicit_undefined(self):
        _,app,_=self.host(self.files()); owner=app.active
        self.event(app,owner); self.event(app,app.active,event='close')
        self.assertEqual(self.greeting(app,owner),'Closed without a selection')


class OwnedBusinessFormTests(HostFixture, unittest.TestCase):
    def business_pair(self, kind, *, save=False, fail=False):
        from configuration_form_results_fixture import business_sources
        broker,app,packets=self.host(business_sources(kind,save=save,fail=fail),business=True)
        name='Catalog.Items.Form.Card' if kind=='catalog' else 'Document.Orders.Form.Card'
        owner=self.open(app,name)
        r=self.event(app,owner,'ChooseButton')
        self.assertIsNone(r['form']['result']['error'],r); self.assertIsNone(r['error'],r)
        self.assertNotEqual(app.active,owner)
        return broker,app,packets,owner,app.active

    def assert_business_completion(self, kind):
        broker,app,_,owner,child=self.business_pair(kind)
        r=self.event(app,child,'AcceptButton')
        self.assertIsNone(r['error'],r)
        entry=app.sessions[owner][1]; definition=app.definitions[entry]
        field='Description' if kind=='catalog' else 'Number'
        slot=dict(definition.object_fields)[field].casefold()
        self.assertEqual(app.sessions[owner][0].session.form._data[slot],'chosen')
        self.assertEqual(broker.sessions[owner][0].session.form._data[slot],'chosen')
        self.assertIsNone(broker.objects[owner].object._revision)
        self.assertEqual(self.extra(app,owner).get('Calls'),1)
        self.assertEqual([u['session'] for u in r['updates']],[owner])
        # The historical nonposting profile guards unresolved save outcomes,
        # not arbitrary dirty data. Do not silently import posting's policy.
        owned=broker.objects[owner]
        owned.pending_commit=True
        try:
            self.assertEqual(self.event(app,owner,event='close')['error'],'save_recovery_required')
            self.assertEqual(app.sessions[owner][0].session.form._data[slot],'chosen')
        finally:
            owned.pending_commit=False
        self.assertIsNone(self.event(app,owner,event='close')['error'])

    def test_catalog_owner_is_updated_without_implicit_write(self):
        self.assert_business_completion('catalog')

    def test_document_owner_is_updated_without_implicit_write(self):
        self.assert_business_completion('document')

    def test_catalog_explicit_callback_write_refreshes_visible_list(self):
        broker,app,_,owner,child=self.business_pair('catalog',save=True)
        self.rpc(app,'catalog',entry=app.sessions[owner][1])
        r=self.event(app,child,'AcceptButton')
        self.assertIsNone(r['error'],r)
        self.assertEqual([row['description'] for row in r['state']['catalog']['rows']],['chosen'])
        self.assertIsNotNone(broker.objects[owner].object._revision)

    def test_document_write_then_callback_error_keeps_committed_effect(self):
        broker,app,packets,owner,child=self.business_pair('document',save=True,fail=True)
        self.rpc(app,'catalog',entry=app.sessions[owner][1])
        r=self.event(app,child,'AcceptButton')
        self.assertEqual(r['error'],'completion_failed')
        self.assertEqual([row['number'] for row in r['state']['catalog']['rows']],['chosen'])
        self.assertIsNotNone(broker.objects[owner].object._revision)
        count=len(packets); self.rpc(app,'snapshot'); self.assertEqual(len(packets),count)
        self.assertEqual(self.extra(app,owner).get('Calls'),1)

    def test_owned_target_must_be_commonform_even_in_business_profile(self):
        from configuration_form_results_fixture import business_sources
        files=business_sources()
        key='Catalogs/Items/Forms/Card/Ext/Form/Module.bsl'
        files[key]=files[key].replace(b'CommonForm.Details',b'Document.Orders.Form.Card')
        _,app,_=self.host(files,business=True); owner=self.open(app,'Catalog.Items.Form.Card')
        r=self.event(app,owner,'ChooseButton')
        self.assertIsNotNone(r['form']['result']['error']); self.assertEqual(list(app.sessions),[owner])
        self.assertFalse(app.owner_children)

    def test_dedicated_posting_host_does_not_enroll_form_results(self):
        from test_configuration_posting_app import files, EXAMPLE
        from yadinassi.configuration_posting_application import import_posting_application, PROFILE
        from yadinassi.sqlite_catalog import SQLiteCatalogBackend
        from yadinassi.ui.configuration_app import load_application
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        path=Path(temporary.name)/'posting.sqlite'
        SQLiteCatalogBackend.create_posting(path,import_posting_application(files(),posting_runtime=PROFILE)).close()
        configuration=load_application(EXAMPLE,posting_application=True)
        broker=ConfigurationBroker(configuration,path,posting_application=True); self.addCleanup(broker.close)
        def pipe(raw):
            q=decode_line(raw)
            return encode_line({'id':q['id'],'session':q['session'],'error':None,
                'result':broker.exchange({k:q[k] for k in ('operation','session','payload')})})
        app=ConfigurationController(configuration,pipe,posting_application=True); self.addCleanup(app.close)
        self.assertNotIn('updates',self.rpc(app,'hello',protocol=PROTOCOL))
        sid=self.rpc(app,'open',entry=next(iter(app.definitions)),request='posting')['session']
        session=app.sessions[sid][0].session
        self.assertIsNone(session._owned_form_enrollment); self.assertFalse(session._allow_host_sync)
        self.assertIsNone(session._owned_close)
        with self.assertRaises(ValueError): session.request_close('not enrolled')
        self.assertFalse(app.owner_children)


if __name__=='__main__': unittest.main()

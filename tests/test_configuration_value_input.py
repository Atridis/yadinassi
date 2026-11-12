"""Real application/interpreter integration; no fabricated native dialog results."""
from decimal import Decimal
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from test_configuration_form_results import HostFixture
from configuration_form_results_fixture import OWNER_MODULE, OPEN, CHILD_MODULE, business_sources
from configuration_dialog_fixture import sources as dialog_sources, QUESTION, WARNING
from yadinassi import Interpreter, BSLError
from yadinassi.configuration_application_profile import import_application_configuration
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.form_dialogs import DIALOG_CAPABILITY
from yadinassi.form_value_input import INPUT_CAPABILITY
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, PROTOCOL
from yadinassi.ui.form_app import PROTOCOL as FORM_PROTOCOL
from yadinassi.ui.protocol import encode_line, decode_line, encode_value
from yadinassi.value_lists import BSLValueList
from yadinassi.values import HostFunction

INPUT = 'ShowInputValue(Callback, 1, "Quantity");'
PREPARE = 'Options=New ValueList; Options.Add("same","First"); InitialItem=Options.Add("same","Second");'
CHOOSE = PREPARE + ' Options.ShowChooseItem(Callback,"Pick",InitialItem);'
COMPLETE = 'Extra.Calls=Extra.Calls+1; Seen=Result; If Result=Undefined Then Greeting="cancelled"; Else Greeting="accepted"; EndIf;'


def sources(*, showing=INPUT, completion=COMPLETE, suffix='Greeting="waiting";'):
    files = dialog_sources(showing=showing, completion=completion, suffix=suffix)
    files[OWNER_MODULE] = files[OWNER_MODULE].replace(b'Var Extra, Callback, Seen;',
        b'Var Extra, Callback, Seen, Options, InitialItem;')
    return files


class InputFixture(HostFixture):
    def host(self, files=None, *, negotiated=True, dialogs=True, business=False, family=True):
        files = sources() if files is None else files
        database = None
        if business:
            from yadinassi.configuration_business_profile import import_business_configuration
            from yadinassi.sqlite_catalog import SQLiteCatalogBackend
            temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
            database = Path(temporary.name)/'inputs.sqlite'
            SQLiteCatalogBackend.create_business_application(database, files).close()
            imported = import_business_configuration(files)
            configuration = load_configuration_forms(files, catalog_schemas=imported.catalogs, document_schemas=imported.documents)
            flags = {'business_application':True}
        else:
            imported = import_application_configuration(files)
            configuration = load_configuration_forms(files, catalog_schemas=imported.catalogs)
            flags = {'application_host':family}
        broker = ConfigurationBroker(configuration, database, **flags); self.addCleanup(broker.close)
        packets = []
        def pipe(raw):
            q = decode_line(raw); packets.append(q)
            result = broker.exchange({key:q[key] for key in ('operation','session','payload')})
            return encode_line({'id':q['id'],'session':q['session'],'result':result,'error':None})
        app = ConfigurationController(configuration, pipe, **flags); self.addCleanup(app.close)
        self.rpc(app, 'hello', protocol=PROTOCOL,
                 **({'inputCapability':INPUT_CAPABILITY} if negotiated else {}),
                 **({'dialogCapability':DIALOG_CAPABILITY} if dialogs else {}))
        return broker, app, packets

    def pending(self, files=None):
        broker, app, packets = self.host(files)
        owner = self.open(app)
        result = self.event(app, owner)
        self.assertIsNone(result['error'], result)
        self.assertIsNone(result['form']['result']['error'], result)
        self.assertEqual(len(result['inputs']), 1, result)
        return broker, app, packets, owner, result['inputs'][0]

    def answer(self, app, owner, descriptor, *, action='accept', value=Decimal(2), choice=None):
        fields = {'value':encode_value(value)} if action == 'accept' else {'choice':choice} if action == 'choose' else {}
        return self.rpc(app, 'answerInput', session=owner, ticket=descriptor['ticket'], action=action, **fields)

    def refused(self, files, *, negotiated=True):
        _, app, _ = self.host(files, negotiated=negotiated)
        owner = self.open(app); result = self.event(app, owner)
        self.assertIsNotNone(result['form']['result']['error'], result)
        self.assertFalse(app.owner_inputs); self.assertFalse(app.inputs)
        return app, owner, result


class InputHostTests(InputFixture, unittest.TestCase):
    def test_negotiation_echo_is_separate_and_immutable(self):
        for dialogs in (False, True):
            _, app, _ = self.host(dialogs=dialogs)
            result = self.rpc(app, 'snapshot')
            self.assertEqual(result['inputCapability'], INPUT_CAPABILITY); self.assertEqual(result['inputs'], [])
            self.assertEqual('dialogCapability' in result, dialogs)
            with self.assertRaises(ValueError):
                self.rpc(app, 'hello', protocol=PROTOCOL, **({'dialogCapability':DIALOG_CAPABILITY} if dialogs else {}))
            with self.assertRaises(ValueError): self.rpc(app, 'hello', protocol=PROTOCOL, inputCapability='unknown/9')

    def test_legacy_client_has_no_new_fields_and_no_invisible_input(self):
        for showing in (INPUT, CHOOSE):
            app, owner, result = self.refused(sources(showing=showing), negotiated=False)
            self.assertNotIn('inputCapability', result); self.assertNotIn('inputs', result)
            with self.assertRaises(ValueError): self.answer(app, owner, {'ticket':'0'*32})

    def test_forms_only_negotiates_empty_capability_without_authority(self):
        _, app, _ = self.host(family=False)
        result = self.rpc(app, 'snapshot')
        self.assertEqual(result['inputs'], []); self.assertNotIn('updates', result)
        with self.assertRaises(ValueError): app._application_show_input(None, 'x')
        self.assertFalse(app.owner_inputs)

    def test_nonblocking_scalar_has_exact_public_descriptor(self):
        _, app, _, owner, descriptor = self.pending()
        self.assertEqual(set(descriptor), {'ticket','owner','kind','title','text','value','editor'})
        self.assertEqual(descriptor['owner'], owner); self.assertEqual(descriptor['kind'], 'input')
        self.assertEqual(descriptor['value'], encode_value(Decimal(1)))
        self.assertEqual(descriptor['editor'], {'kind':'number','digits':0,'scale':0,'nonnegative':False})
        self.assertEqual(self.greeting(app, owner), 'waiting'); self.assertEqual(self.extra(app, owner).get('Calls'), 0)
        self.assertNotIn('Completed', encode_line(descriptor).decode())

    def test_scalar_result_additional_parameters_and_owner_identity(self):
        broker, app, _, owner, descriptor = self.pending(); extra = self.extra(app, owner)
        result = self.answer(app, owner, descriptor, value=Decimal('12.300'))
        self.assertIsNone(result['error'], result); self.assertEqual(result['session'], owner)
        self.assertEqual(result['updates'], []); self.assertEqual(result['inputs'], [])
        self.assertEqual(str(app.sessions[owner][0].session.interpreter.variables['seen']), '12.300')
        self.assertIs(self.extra(app, owner), extra); self.assertEqual(extra.get('Calls'), 1)
        self.assertEqual(broker.sessions[owner][0].session.form._data['greeting'], 'accepted')

    def test_four_scalar_kinds_and_russian_alias(self):
        from yadinassi.dates import date
        for initial, value in [('"before"','after'), ('False',True), ('1',Decimal('3.50')),
                               ('Date(2024,1,2)',date(Decimal(2024),Decimal(1),Decimal(3)))]:
            with self.subTest(initial=initial):
                _, app, _, owner, descriptor = self.pending(sources(showing='ПоказатьВводЗначения(Callback,'+initial+');'))
                self.assertIsNone(self.answer(app, owner, descriptor, value=value)['error'])
                self.assertEqual(app.sessions[owner][0].session.interpreter.variables['seen'], value)

    def test_undefined_requires_explicit_single_scalar_type(self):
        self.refused(sources(showing='ShowInputValue(Callback,Undefined);'))
        for descriptor in ('Type("String")','New TypeDescription("String")'):
            _, app, _, owner, prompt = self.pending(sources(showing='ShowInputValue(Callback,Undefined,Undefined,'+descriptor+');'))
            self.assertEqual(prompt['value'], encode_value('')); self.assertEqual(prompt['text'], '')
            self.assertIsNone(self.answer(app, owner, prompt, value='chosen')['error'])

    def test_explicit_type_cannot_coerce_initial_or_admit_union_reference(self):
        for showing in ('ShowInputValue(Callback,1,"",Type("String"));',
                        'ShowInputValue(Callback,Undefined,"",New TypeDescription("String,Number"));',
                        'ShowInputValue(Callback,New Structure);',
                        'ShowInputValue(Callback,Undefined,"",Type("UUID"));'):
            with self.subTest(showing=showing): self.refused(sources(showing=showing))

    def test_qualifier_validation_refuses_rounding_without_consuming(self):
        showing = 'ShowInputValue(Callback,1,"",New TypeDescription("Number",New NumberQualifiers(5,2)));'
        _, app, _, owner, descriptor = self.pending(sources(showing=showing))
        for value in (Decimal('1.234'), Decimal('1000'), '1.25'):
            result = self.answer(app, owner, descriptor, value=value)
            self.assertEqual(result['error'], 'input_refused'); self.assertEqual(len(result['inputs']), 1)
            self.assertEqual(self.extra(app, owner).get('Calls'), 0)
        self.assertIsNone(self.answer(app, owner, descriptor, value=Decimal('1.25'))['error'])

    def test_cancel_is_undefined_not_empty_string_or_zero(self):
        for showing in (INPUT, CHOOSE):
            _, app, _, owner, descriptor = self.pending(sources(showing=showing))
            result = self.answer(app, owner, descriptor, action='cancel')
            self.assertIsNone(result['error']); self.assertIsNone(app.sessions[owner][0].session.interpreter.variables['seen'])
            self.assertEqual(self.extra(app, owner).get('Calls'), 1); self.assertEqual(self.greeting(app, owner), 'cancelled')

    def test_bad_answer_shape_and_wrong_kind_never_consume(self):
        _, app, _, owner, descriptor = self.pending()
        self.assertEqual(self.answer(app, owner, descriptor, action='choose', choice='0'*32)['error'], 'input_refused')
        for fields in ({'action':'accept'}, {'action':'cancel','value':encode_value('')},
                       {'action':'accept','value':{'type':'Number','value':1},'callback':'Completed'}):
            with self.assertRaises(ValueError): self.rpc(app, 'answerInput', session=owner, ticket=descriptor['ticket'], **fields)
        self.assertEqual(app.inputs[descriptor['ticket']].state, 'open')
        self.assertEqual(self.extra(app, owner).get('Calls'), 0)

    def test_unknown_wrong_owner_and_repeated_answers_never_retarget(self):
        _, app, packets, owner, descriptor = self.pending(); sibling = self.open(app, token='sibling')
        self.assertEqual(self.answer(app, sibling, descriptor)['error'], 'input_refused')
        self.assertEqual(self.answer(app, owner, {'ticket':'f'*32})['error'], 'input_refused')
        self.answer(app, owner, descriptor); count = len(packets)
        for action in ('accept','cancel'):
            self.assertEqual(self.answer(app, owner, descriptor, action=action)['error'], 'input_retired')
        self.assertEqual(len(packets), count); self.assertEqual(self.extra(app, owner).get('Calls'), 1)

    def test_owner_business_close_and_reference_paused_reads_allowed(self):
        _, app, packets, owner, descriptor = self.pending(); count = len(packets)
        for event in ('command','close'):
            self.assertEqual(self.event(app, owner, event=event)['error'], 'input_pending')
        response = self.rpc(app, 'reference', session=owner, revision=app.sessions[owner][0].session.revision, action={})
        self.assertEqual(response['session'], owner); self.assertEqual(response['error'], 'input_pending')
        for method in ('form.hello','form.snapshot'):
            params = {'protocol':FORM_PROTOCOL} if method == 'form.hello' else {}
            response = self.rpc(app, 'form', session=owner, request={'jsonrpc':'2.0','id':1,'method':method,'params':params})
            self.assertTrue(next(s for s in response['state']['sessions'] if s['id']==owner)['blocked'])
        self.assertEqual(len(packets), count)

    def test_sibling_retains_independent_interaction_and_draft(self):
        _, app, _, owner, first = self.pending(); sibling = self.open(app, token='sibling')
        second = self.event(app, sibling)['inputs'][1]
        result = self.answer(app, owner, first)
        self.assertEqual([item['ticket'] for item in result['inputs']], [second['ticket']])
        self.assertEqual(self.extra(app, sibling).get('Calls'), 0); self.assertEqual(self.greeting(app, sibling), 'waiting')

    def test_children_questions_and_inputs_share_one_owner_occupancy(self):
        for showing in (INPUT+INPUT, INPUT+QUESTION, QUESTION+INPUT, INPUT+WARNING,
                        OPEN+INPUT, INPUT+OPEN, CHOOSE+INPUT, INPUT+CHOOSE):
            with self.subTest(showing=showing):
                app, _, _ = self.refused(sources(showing=showing))
                self.assertFalse(app.owner_dialogs); self.assertFalse(app.pending); self.assertFalse(app.owner_children)

    def test_failed_or_interrupted_opening_drops_unpublished_input(self):
        self.refused(sources(suffix='Raise "after enqueue";'))
        _, app, _ = self.host(); owner = self.open(app)
        with patch.object(app, '_queue_input', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.event(app, owner)
        self.assertTrue(app.uncertain); self.assertFalse(app.owner_inputs)

    def test_callback_reentrancy_is_refused_but_partial_effect_is_kept(self):
        for ending in (INPUT, CHOOSE, QUESTION, 'OpenForm("CommonForm.Details");', 'ThisObject.Close();'):
            _, app, _, owner, descriptor = self.pending(sources(completion='Extra.Calls=Extra.Calls+1; Greeting="partial"; '+ending))
            result = self.answer(app, owner, descriptor)
            self.assertEqual(result['error'], 'completion_failed'); self.assertEqual(result['inputs'], [])
            self.assertEqual(self.extra(app, owner).get('Calls'), 1); self.assertEqual(self.greeting(app, owner), 'partial')
            self.assertEqual(result['form']['result']['error'], 'event_failed')
            self.assertEqual(self.answer(app, owner, descriptor)['error'], 'input_retired')

    def test_known_failure_and_success_release_callback_capabilities(self):
        for completion in (COMPLETE, 'Extra.Calls=Extra.Calls+1; Raise "failed";'):
            _, app, _, owner, descriptor = self.pending(sources(completion=completion))
            receipt = app.inputs[descriptor['ticket']]
            callback_ref = weakref.ref(receipt.callback); vm = app.sessions[owner][0].session.interpreter
            vm.variables['callback'] = None
            self.answer(app, owner, descriptor); gc.collect()
            self.assertIsNone(callback_ref()); self.assertIsNone(receipt.callback); self.assertIsNone(receipt.enrollment)
            self.assertIsNone(receipt.result); self.assertIsNone(receipt.spec); self.assertEqual(receipt.image, b'')

    def test_retired_enrollment_and_generation_refuse_terminally(self):
        for change in ('enrollment','generation'):
            _, app, _, owner, descriptor = self.pending()
            if change == 'enrollment': app.sessions[owner][0].session._owned_form_enrollment = object()
            else: app.inputs[descriptor['ticket']].generation -= 1
            self.assertEqual(self.answer(app, owner, descriptor)['error'], 'retired_session')
            self.assertEqual(app.inputs[descriptor['ticket']].state, 'owner_retired')
            self.assertEqual(self.extra(app, owner).get('Calls'), 0)

    def test_unknown_sync_before_or_after_callback_locks_without_replay(self):
        for target in (1, 2):
            _, app, packets, owner, descriptor = self.pending(); transport = app.transport; syncs = []
            def lost(raw):
                q = decode_line(raw); reply = transport(raw)
                if q['operation']=='form' and q['payload'].get('operation')=='sync':
                    syncs.append(q)
                    if len(syncs)==target: raise OSError('lost sync reply')
                return reply
            app.transport = lost
            result = self.answer(app, owner, descriptor)
            self.assertEqual(result['error'], 'outcome_unknown'); self.assertTrue(app.uncertain)
            self.assertEqual(self.extra(app, owner).get('Calls'), target-1)
            self.assertEqual(app.inputs[descriptor['ticket']].state, 'uncertain')
            self.assertIsNotNone(app.inputs[descriptor['ticket']].callback)
            count = len(packets); self.answer(app, owner, descriptor); self.assertEqual(len(packets), count)

    def test_caught_unknown_server_call_does_not_unlock_failed_completion(self):
        _, app, _, owner, descriptor = self.pending(sources(completion='Extra.Calls=Extra.Calls+1; Try Service.Add(4); Except EndTry;'))
        transport = app.transport
        def lost(raw):
            q = decode_line(raw); reply = transport(raw)
            if q['operation']=='applicationInvoke': raise OSError('lost server result')
            return reply
        app.transport = lost
        self.assertEqual(self.answer(app, owner, descriptor)['error'], 'outcome_unknown')
        self.assertIn(owner, app.owner_inputs); self.assertEqual(self.extra(app, owner).get('Calls'), 1)

    def test_completion_interruption_retains_envelope_and_unlocks_gates(self):
        _, app, _, owner, descriptor = self.pending(); session = app.sessions[owner][0].session
        with patch.object(session, 'dispatch_completion', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.answer(app, owner, descriptor)
        self.assertTrue(app.uncertain); self.assertEqual(app.inputs[descriptor['ticket']].state, 'uncertain')
        self.assertFalse(app.gate.locked()); self.assertFalse(session._gate.locked())

    def test_ticket_budget_and_collision_refuse_before_publication(self):
        _, app, _, owner, descriptor = self.pending(); sibling = self.open(app, token='sibling')
        with patch('yadinassi.ui.configuration_app.token_hex', return_value=descriptor['ticket']):
            self.assertIsNotNone(self.event(app, sibling)['form']['result']['error'])
        self.assertEqual(len(app.inputs), 1)
        with patch('yadinassi.ui.configuration_app.MAX_INPUTS', 1):
            self.assertIsNotNone(self.event(app, sibling)['form']['result']['error'])
        self.assertEqual(app.inputs[descriptor['ticket']].owner, owner)

    def test_plain_text_limits_arity_and_omitted_slots_fail_closed(self):
        for showing in ('ShowInputValue(Callback);', 'ShowInputValue(Callback,1,"",Type("Number"),1);',
                        'ShowInputValue(Callback,1,,Type("Number"));',
                        'ShowInputValue(Callback,1,"'+'x'*4097+'");',
                        'ShowInputValue(Callback,1,"bad"+Char(0));', PREPARE+'Options.ShowChooseItem(Callback,1);',
                        PREPARE+'Options.ShowChooseItem(Callback,"",InitialItem,1);'):
            with self.subTest(length=len(showing)): self.refused(sources(showing=showing))

    def test_callback_must_be_current_owner_and_two_argument_client_procedure(self):
        wrong_arity = sources()
        wrong_arity[OWNER_MODULE] = wrong_arity[OWNER_MODULE].replace(b'Procedure Completed(Result, Extra)', b'Procedure Completed(Extra)')
        for files in (sources(showing=INPUT.replace('Callback,','Undefined,')), wrong_arity):
            self.refused(files)

    def test_application_start_and_server_context_cannot_enqueue(self):
        files = sources(); files['Ext/ManagedApplicationModule.bsl'] = b'Procedure OnStart() ShowInputValue(Undefined,1); EndProcedure'
        _, app, _ = self.host(files); self.assertTrue(app.uncertain); self.assertFalse(app.owner_inputs)
        for call in ('ShowInputValue(Undefined,1);','Values=New ValueList; Values.ShowChooseItem(Undefined);'):
            files = sources(showing='ServerAsk();')
            files[OWNER_MODULE] += ('\n&AtServer\nProcedure ServerAsk() '+call+' EndProcedure').encode()
            self.refused(files)

    def test_same_context_common_modules_preserve_callback_and_item_owner(self):
        for choosing in (False, True):
            showing = PREPARE+'Tools.Ask(Options,Callback);' if choosing else 'Tools.Ask(Callback);'
            body = ('Procedure Ask(Val Values, Val Completion) Export Values.ShowChooseItem(Completion,"via common"); EndProcedure'
                    if choosing else 'Procedure Ask(Val Completion) Export ShowInputValue(Completion,1,"via common"); EndProcedure')
            files = sources(showing=showing); files['CommonModules/Tools/Ext/Module.bsl'] += ('\n'+body).encode()
            _, app, _, owner, descriptor = self.pending(files)
            if choosing:
                original = app.sessions[owner][0].session.interpreter.variables['options'].items[1]
                self.assertIsNone(self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][1]['choice'])['error'])
                self.assertIs(app.sessions[owner][0].session.interpreter.variables['seen'], original)
            else: self.assertIsNone(self.answer(app, owner, descriptor)['error'])

    def test_marker_has_no_ambient_or_direct_callable_authority(self):
        source = BSLValueList(); source.add('x')
        for alias in ('ShowChooseItem','ПоказатьВыборЭлемента'):
            with self.assertRaises(ValueError): source.get_method(alias)(None)
        with self.assertRaises(BSLError): Interpreter().execute('Values=New ValueList; Values.ShowChooseItem(Undefined);')

    def test_independent_client_child_cannot_borrow_active_owner_marker(self):
        _, app, _ = self.host(sources(showing=CHOOSE)); owner = self.open(app)
        child = app.application.interpreter_factory(lambda value: None)
        self.addCleanup(child.close)
        original = app.application.dispatch_value_selection
        def wrong_caller(caller, source, arguments):
            return original(child, source, arguments)
        with patch.object(app.application, 'dispatch_value_selection', side_effect=wrong_caller):
            result = self.event(app, owner)
        self.assertIsNotNone(result['form']['result']['error']); self.assertFalse(app.inputs)

    def test_child_cannot_launder_origin_through_reused_common_module(self):
        for choosing in (False, True):
            files = sources(showing=PREPARE+'InjectChild();')
            command = 'Values.ShowChooseItem(Completion);' if choosing else 'ShowInputValue(Completion,1);'
            files['CommonModules/Tools/Ext/Module.bsl'] += ('\nProcedure Ask(Val Values, Val Completion) Export '+command+' EndProcedure').encode()
            _, app, _ = self.host(files); owner = self.open(app)
            child = app.application.interpreter_factory(lambda value: None); self.addCleanup(child.close)
            vm = app.sessions[owner][0].session.interpreter
            def inject():
                child.variables.update({'options':vm.variables['options'], 'completion':vm.variables['callback']})
                child.execute('Tools.Ask(Options,Completion);')
            vm.functions['injectchild'] = HostFunction('InjectChild', inject, returns_value=False)
            result = self.event(app, owner)
            self.assertIsNotNone(result['form']['result']['error']); self.assertFalse(app.inputs)
            self.assertNotIn(app.application._input_call_key, vm._scheduler.active_context.state)

    def test_async_common_task_does_not_inherit_form_origin(self):
        for choosing in (False, True):
            files = sources(showing=PREPARE+'Tools.Later(Options,Callback);')
            command = 'Values.ShowChooseItem(Completion);' if choosing else 'ShowInputValue(Completion,1);'
            files['CommonModules/Tools/Ext/Module.bsl'] += ('''
Async Procedure Later(Val Values, Val Completion) Export Ask(Values,Completion); EndProcedure
Procedure Ask(Val Values, Val Completion) '''+command+' EndProcedure').encode()
            _, app, _ = self.host(files); owner = self.open(app)
            self.event(app, owner)
            self.assertFalse(app.inputs); self.assertFalse(app.owner_inputs)
            self.assertEqual(self.extra(app, owner).get('Calls'), 0)

    def test_call_chain_finally_restores_after_caught_failure_and_sibling(self):
        files = sources(showing='Try Tools.Fail(); Except EndTry; '+INPUT)
        files['CommonModules/Tools/Ext/Module.bsl'] += b'\nProcedure Fail() Export Raise "expected"; EndProcedure'
        _, app, _, owner, descriptor = self.pending(files)
        scheduler = app.application.interpreter._scheduler
        self.assertNotIn(app.application._input_call_key, scheduler.active_context.state)
        self.assertIsNone(self.answer(app, owner, descriptor)['error'])
        self.assertNotIn(app.application._input_call_key, scheduler.active_context.state)
        sibling = self.open(app, token='sibling'); result = self.event(app, sibling)
        self.assertIsNone(result['form']['result']['error'])
        self.assertEqual(result['inputs'][0]['owner'], sibling)
        self.assertNotIn(app.application._input_call_key, scheduler.active_context.state)

    def test_foreign_family_callback_cannot_be_enqueued_by_active_form(self):
        _, foreign, _, foreign_owner, _ = self.pending()
        callback = foreign.sessions[foreign_owner][0].session.interpreter.variables['callback']
        _, app, _ = self.host(sources(showing='BorrowCallback(); '+INPUT)); owner = self.open(app)
        vm = app.sessions[owner][0].session.interpreter
        def borrow(): vm.variables['callback'] = callback
        vm.functions['borrowcallback'] = HostFunction('BorrowCallback', borrow, returns_value=False)
        result = self.event(app, owner)
        self.assertIsNotNone(result['form']['result']['error']); self.assertFalse(app.inputs)
        self.assertEqual(self.extra(foreign, foreign_owner).get('Calls'), 0)

    def test_form_and_global_source_alias_collisions_are_refused(self):
        for alias in ('ShowInputValue','ПоказатьВводЗначения'):
            files = sources(); files[OWNER_MODULE] += ('\n&AtClient\nProcedure '+alias+'() EndProcedure').encode()
            _, app, _ = self.host(files)
            result = self.rpc(app, 'open', entry=app.names['commonform.welcome'], request='owner')
            self.assertIsNotNone(result['error']); self.assertFalse(app.owner_inputs)
            files = sources(); files['Ext/ManagedApplicationModule.bsl'] = ('Procedure '+alias+'() EndProcedure').encode()
            with self.assertRaises(ValueError): self.host(files)
            files = sources()
            files['CommonModules/Tools.xml'] = files['CommonModules/Tools.xml'].replace(b'<Global>false</Global>', b'<Global>true</Global>')
            files['CommonModules/Tools/Ext/Module.bsl'] += ('\nProcedure '+alias+'() Export EndProcedure').encode()
            with self.assertRaises(ValueError): self.host(files)


class SelectionHostTests(InputFixture, unittest.TestCase):
    def test_choice_snapshot_and_initial_item_use_only_opaque_tokens(self):
        _, app, _, owner, descriptor = self.pending(sources(showing=CHOOSE))
        self.assertEqual(set(descriptor), {'ticket','owner','kind','title','choices','initial'})
        self.assertEqual(descriptor['initial'], descriptor['choices'][1]['choice'])
        self.assertEqual([x['presentation'] for x in descriptor['choices']], ['First','Second'])
        self.assertNotEqual(descriptor['choices'][0]['choice'], descriptor['choices'][1]['choice'])
        self.assertEqual(self.extra(app, owner).get('Calls'), 0)

    def test_selected_result_is_original_item_and_callback_mutates_same_list(self):
        completion = 'Seen=Result; Result.Value="chosen"; Extra.Calls=Extra.Calls+1; Greeting=String(Result.GetID());'
        _, app, _, owner, descriptor = self.pending(sources(showing=CHOOSE, completion=completion))
        options = app.sessions[owner][0].session.interpreter.variables['options']; original = options.items[1]
        result = self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][1]['choice'])
        self.assertIsNone(result['error'], result)
        self.assertIs(app.sessions[owner][0].session.interpreter.variables['seen'], original)
        self.assertEqual(original.value, 'chosen'); self.assertEqual(self.greeting(app, owner), '1')

    def test_optional_title_initial_and_russian_list_alias(self):
        _, app, _, owner, descriptor = self.pending(sources(showing=PREPARE+'Options.ПоказатьВыборЭлемента(Callback);'))
        self.assertEqual(descriptor['title'], ''); self.assertIsNone(descriptor['initial'])
        self.assertIsNone(self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][0]['choice'])['error'])

    def test_initial_item_is_exact_member_not_index_value_or_foreign(self):
        for expression in ('0','"same"','Other.Get(0)'):
            self.refused(sources(showing=PREPARE+'Other=New ValueList; Other.Add("same"); Options.ShowChooseItem(Callback,"",'+expression+');'))

    def test_invalid_token_and_accept_action_do_not_consume_choice(self):
        _, app, _, owner, descriptor = self.pending(sources(showing=CHOOSE))
        for token in ('0','f'*32,None,0):
            self.assertEqual(self.answer(app, owner, descriptor, action='choose', choice=token)['error'], 'input_refused')
        self.assertEqual(self.answer(app, owner, descriptor)['error'], 'input_refused')
        self.assertEqual(app.inputs[descriptor['ticket']].state, 'open')
        self.assertEqual(self.extra(app, owner).get('Calls'), 0)

    def test_mutated_list_is_terminally_stale_without_completion(self):
        for field in ('value','presentation','check','delete','reorder'):
            _, app, _, owner, descriptor = self.pending(sources(showing=CHOOSE))
            options = app.sessions[owner][0].session.interpreter.variables['options']
            if field == 'delete': options.delete(Decimal(0))
            elif field == 'reorder': options.move(Decimal(0),Decimal(1))
            else: setattr(options.items[0], field, True if field=='check' else 'changed')
            result = self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][1]['choice'])
            self.assertEqual(result['error'], 'input_stale'); self.assertEqual(result['inputs'], [])
            self.assertEqual(self.extra(app, owner).get('Calls'), 0)
            receipt = app.inputs[descriptor['ticket']]
            self.assertEqual(receipt.state, 'stale'); self.assertIsNone(receipt.selection); self.assertIsNone(receipt.source_lease)
            self.assertEqual(self.answer(app, owner, descriptor, action='cancel')['error'], 'input_retired')

    def test_source_drift_after_enqueue_keeps_snapshot_but_never_accepts(self):
        _, app, _, owner, descriptor = self.pending(sources(showing=CHOOSE, suffix='Options.Get(0).Value="changed";'))
        self.assertEqual(descriptor['choices'][0]['value'], encode_value('same'))
        self.assertEqual(self.rpc(app, 'snapshot')['inputs'][0], descriptor)
        result = self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][0]['choice'])
        self.assertEqual(result['error'], 'input_stale'); self.assertEqual(self.extra(app, owner).get('Calls'), 0)

    def test_empty_selection_only_cancels(self):
        _, app, _, owner, descriptor = self.pending(sources(showing='Options=New ValueList; Options.ShowChooseItem(Callback);'))
        self.assertEqual(descriptor['choices'], []); self.assertIsNone(descriptor['initial'])
        self.assertEqual(self.answer(app, owner, descriptor, action='choose', choice='0'*32)['error'], 'input_refused')
        self.assertIsNone(self.answer(app, owner, descriptor, action='cancel')['error'])

    def test_local_list_source_is_held_through_callback_then_released(self):
        files = sources(showing='AskLocal(Callback);', completion='Greeting=String(Result.GetID()); Extra.Calls=Extra.Calls+1;')
        files[OWNER_MODULE] += b'\n&AtClient\nProcedure AskLocal(Val Completion) Values=New ValueList; Values.Add("x"); Values.ShowChooseItem(Completion); EndProcedure'
        _, app, _, owner, descriptor = self.pending(files)
        receipt = app.inputs[descriptor['ticket']]; reference = weakref.ref(receipt.source_lease)
        self.assertIsNone(self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][0]['choice'])['error'])
        self.assertEqual(self.greeting(app, owner), '0'); gc.collect()
        self.assertIsNone(reference()); self.assertIsNone(receipt.source_lease)

    def test_unknown_selection_completion_retains_exact_item_and_source(self):
        _, app, _, owner, descriptor = self.pending(sources(showing=CHOOSE)); session = app.sessions[owner][0].session
        receipt = app.inputs[descriptor['ticket']]; original = receipt.source_lease.items[1]
        with patch.object(session, 'dispatch_completion', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.answer(app, owner, descriptor, action='choose', choice=descriptor['choices'][1]['choice'])
        self.assertEqual(receipt.state, 'uncertain'); self.assertIs(receipt.result, original)
        self.assertIsNotNone(receipt.source_lease); self.assertEqual(receipt.selection.state, 'consumed')


class InputBusinessTests(InputFixture, unittest.TestCase):
    def business_source(self, kind, *, save=False, fail=False):
        files = business_sources(kind, save=save, fail=fail)
        prefix = 'Catalogs/Items/Forms/Card' if kind=='catalog' else 'Documents/Orders/Forms/Card'
        key = prefix+'/Ext/Form/Module.bsl'
        files[key] = files[key].replace(OPEN.encode(), b'ShowInputValue(Callback,"initial","Value");')
        return files

    def test_catalog_and_document_inputs_do_not_implicitly_write(self):
        for kind in ('catalog','document'):
            broker, app, _ = self.host(self.business_source(kind), business=True)
            owner = self.open(app, 'Catalog.Items.Form.Card' if kind=='catalog' else 'Document.Orders.Form.Card')
            descriptor = self.event(app, owner, 'ChooseButton')['inputs'][0]
            self.assertIsNone(self.answer(app, owner, descriptor, value='chosen')['error'])
            self.assertIsNone(broker.objects[owner].object._revision)
            definition = app.definitions[app.sessions[owner][1]]
            slot = dict(definition.object_fields)['Description' if kind=='catalog' else 'Number'].casefold()
            self.assertEqual(app.sessions[owner][0].session.form._data[slot], 'chosen')
            self.assertEqual(broker.sessions[owner][0].session.form._data[slot], 'chosen')

    def test_explicit_write_then_callback_error_keeps_commit_without_replay(self):
        broker, app, packets = self.host(self.business_source('document', save=True, fail=True), business=True)
        owner = self.open(app, 'Document.Orders.Form.Card')
        self.rpc(app, 'catalog', entry=app.sessions[owner][1])
        descriptor = self.event(app, owner, 'ChooseButton')['inputs'][0]
        result = self.answer(app, owner, descriptor, value='chosen')
        self.assertEqual(result['error'], 'completion_failed')
        self.assertEqual([row['number'] for row in result['state']['catalog']['rows']], ['chosen'])
        self.assertIsNotNone(broker.objects[owner].object._revision)
        count = len(packets); self.answer(app, owner, descriptor); self.assertEqual(len(packets), count)

    def test_completion_cannot_become_a_root_transaction(self):
        files = self.business_source('document')
        key = 'Documents/Orders/Forms/Card/Ext/Form/Module.bsl'
        files[key] = files[key].replace(b'Object.Number=String(Result);', b'Object.Number=String(Result); BeginTransaction();')
        broker, app, _ = self.host(files, business=True); owner = self.open(app, 'Document.Orders.Form.Card')
        descriptor = self.event(app, owner, 'ChooseButton')['inputs'][0]
        result = self.answer(app, owner, descriptor, value='partial')
        self.assertEqual(result['error'], 'completion_failed'); self.assertIsNone(broker.objects[owner].object._revision)
        self.assertEqual(app.inputs[descriptor['ticket']].state, 'failed')


if __name__ == '__main__':
    unittest.main()

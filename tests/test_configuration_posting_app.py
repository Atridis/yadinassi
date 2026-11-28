"""Explicit posting host application, typed replicas and no write replay."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.configuration.configuration_posting_application import import_posting_application, PROFILE
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, ConfigurationProcess, load_application, PROTOCOL, main
from yadinassi.ui.protocol import encode_line, decode_line, encode_value

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/configuration-posting-application'


def files():
    return {p.relative_to(EXAMPLE).as_posix(): p.read_bytes() for p in EXAMPLE.rglob('*') if p.is_file()}


class PostingApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)/'posting.sqlite'
        self.configuration = import_posting_application(files(), posting_runtime=PROFILE)
        SQLiteCatalogBackend.create_posting(self.path, self.configuration).close()
        forms = load_application(EXAMPLE, posting_application=True)
        self.broker = ConfigurationBroker(forms, self.path, posting_application=True)
        self.addCleanup(self.broker.close)
        def exchange(raw):
            request = decode_line(raw)
            result = self.broker.exchange({k: request[k] for k in ('operation', 'session', 'payload')})
            return encode_line({'id': request['id'], 'session': request['session'], 'result': result, 'error': None})
        self.app = ConfigurationController(forms, exchange, posting_application=True)
        self.addCleanup(self.app.close)
        self.rpc('hello', protocol=PROTOCOL)

    def rpc(self, method, **params):
        return self.app.exchange({'jsonrpc':'2.0', 'id':1, 'method':'application.'+method, 'params':params})['result']

    def open(self, request='one', record=None):
        response = self.rpc('open' if record is None else 'openRecord', entry=1, request=request,
            **({} if record is None else {'record':record}))
        self.assertIsNone(response['error'], response)
        self.assertIsNotNone(response['session'], response)
        return response['session']

    def event(self, sid, event='command', **values):
        if event in ('change','cell'): values['value'] = encode_value(values['value'])
        response = self.rpc('form', session=sid, request={'jsonrpc':'2.0','id':1,'method':'form.event',
            'params':{'event':event,'revision':self.app.sessions[sid][0].session.revision,**values}})
        self.assertIsNone(response['error'], response)
        self.assertIsNone(response['form']['result']['error'], response)
        return response

    def read(self):
        backend = SQLiteCatalogBackend(self.path)
        try:
            from yadinassi.db.document.document_backend import DocumentSelection
            view = backend.begin_document_read()
            try: cards = view.select_documents(self.configuration.documents[0].identity, DocumentSelection())
            finally: view.close()
            rows = [backend.read_recorder(self.configuration.registers[0].identity, card.key).rows for card in cards]
            return cards, rows
        finally: backend.close()

    def test_new_oncreate_defaults_are_clean(self):
        sid = self.open()
        self.event(sid, 'close')
        self.assertNotIn(sid, self.app.sessions)

    def test_reopened_projection_changes_remain_dirty(self):
        sid = self.open(); self.event(sid, control='WriteButton')
        self.rpc('catalog', entry=1)
        record = self.app._state()['catalog']['rows'][0]['key']
        other = self.open('reopen', record)
        owned = self.broker.objects[other]
        definition = self.broker.definitions[1]
        server = self.broker.sessions[other][0]
        slot = dict(definition.object_fields)['Note'].casefold()
        server.session.form._data[slot] = 'creation-side modification'
        self.assertNotEqual(definition._document_image(server.session), owned.baseline)
        self.assertFalse(self.broker.exchange({'operation':'guardClose','session':other,'payload':{}})['allowed'])

    def test_dynamic_control_flags_survive_sync_and_recovery(self):
        sid = self.open(); owned = self.broker.objects[sid]
        client = self.app.sessions[sid][0].session
        item = client.form.items._values['noteinput']
        item.visible, item.enabled, item.read_only = False, False, True
        self.app._posting_sync(sid, 'sync')
        item = client.form.items._values['noteinput']
        self.assertEqual((item.visible,item.enabled,item.read_only),(False,False,True))
        with patch.object(owned, '_refresh', side_effect=ValueError('projection fault')):
            state = self.event(sid, control='PostButton')['state']['posting'][0]
        self.assertIsNone(state['posted'])
        response = self.rpc('refreshPosting',session=sid)
        self.assertTrue(response['state']['posting'][0]['posted'])
        item = client.form.items._values['noteinput']
        self.assertEqual((item.visible,item.enabled,item.read_only),(False,False,True))

    def test_operation_id_allocation_failure_does_not_lock_form(self):
        sid = self.open(); owned = self.broker.objects[sid]
        with patch('yadinassi.configuration.configuration_posting_document.uuid4', side_effect=MemoryError):
            with self.assertRaises(MemoryError): owned.execute('Post', owned.image())
        self.assertFalse(owned._saving); self.assertFalse(owned.pending_commit)
        self.assertEqual(self.read(),((),[]))

    def test_unknown_discard_does_not_dispatch_or_replay_and_reopen_is_only_a_read(self):
        from types import SimpleNamespace
        sid = self.open(); owned = self.broker.objects[sid]; server = self.broker.sessions[sid][0]
        execute = owned.operations.execute
        def lose_outcome(*args, **kwargs):
            self.assertEqual(execute(*args, **kwargs).state, 'committed')
            return SimpleNamespace(state='uncertain', accepted=False)
        with patch.object(owned.operations, 'execute', side_effect=lose_outcome):
            state = self.event(sid, control='PostButton')['state']['posting'][0]
        self.assertEqual((state['state'], state['error'], state['posted']), ('uncertain', 'outcome_unknown', None))
        self.assertTrue(owned.pending_commit)
        self.assertNotIn('receipt', state)
        saved_revision = self.read()[0][0].revision
        with patch.object(server, 'exchange', side_effect=AssertionError('no BSL dispatch')), \
             patch.object(owned.operations, 'execute', side_effect=AssertionError('no replay')), \
             patch.object(owned, '_refresh', side_effect=AssertionError('no attribution from record read')):
            with self.assertRaisesRegex(ValueError, 'known commit'):
                self.rpc('refreshPosting', session=sid)
            controller = self.app.sessions[sid][0]
            blocked = self.rpc('form', session=sid, request={
                'jsonrpc':'2.0', 'id':1, 'method':'form.event',
                'params':{'event':'command','revision':controller.session.revision,'control':'PostButton'}})
            self.assertEqual(blocked['error'], 'save_recovery_required')
            discarded = self.rpc('discardPosting', session=sid)
        self.assertIsNone(discarded['form'])
        self.assertEqual(discarded['state']['posting'], [])
        self.assertNotIn(sid, self.broker.sessions)
        self.assertEqual(self.read()[0][0].revision, saved_revision)
        record = self.rpc('catalog', entry=1)['state']['catalog']['rows'][0]['key']
        other = self.open('after-discard', record)
        self.assertTrue(self.broker.objects[other].object.get_member('Posted'))
        self.assertEqual(self.broker.objects[other].save_state, 'unchanged')
        self.assertEqual(self.read()[0][0].revision, saved_revision)

    def test_posted_bsl_assignment_is_denied_on_both_sides(self):
        sid = self.open(); slot = dict(self.broker.definitions[1].object_fields)['Posted']
        for session in (self.app.sessions[sid][0].session,self.broker.sessions[sid][0].session):
            session._busy = True
            try:
                with self.assertRaises(Exception):session.interpreter.execute(slot+' = True;')
                self.assertFalse(session.form._data[slot.casefold()])
            finally:session._busy = False

    def test_posted_reference_copyout_is_denied_on_both_sides(self):
        sid = self.open(); slot = dict(self.broker.definitions[1].object_fields)['Posted']
        for session in (self.app.sessions[sid][0].session,self.broker.sessions[sid][0].session):
            session._busy = True
            try:
                with self.assertRaises(Exception):
                    session.interpreter.execute('Procedure Mutate(X) X = True; EndProcedure Mutate(ThisObject.'+slot+');')
                self.assertFalse(session.form._data[slot.casefold()])
            finally:session._busy = False

    def test_posted_replica_delta_is_denied(self):
        from yadinassi.forms.form_replication import _admit_delta
        sid = self.open(); server = self.broker.sessions[sid][0]
        slot = dict(self.broker.definitions[1].object_fields)['Posted']
        with self.assertRaises(ValueError):
            _admit_delta(server.session.form,{'attributes':[[slot,encode_value(True)]],
                'items':[],'title':None,'cells':[],'selections':[]})

    def test_write_post_undo_and_posted_projection(self):
        self.rpc('catalog', entry=1); sid = self.open()
        self.event(sid, control='NewLineButton')
        self.event(sid, control='WriteButton')
        cards, rows = self.read(); self.assertFalse(cards[0].posted); self.assertFalse(rows[0])
        posted = self.event(sid, control='PostButton')
        cards, rows = self.read(); self.assertTrue(cards[0].posted); self.assertEqual(len(rows[0]),1)
        self.assertTrue(posted['state']['catalog']['rows'][0]['posted'])
        unposted = self.event(sid, control='UndoButton')
        cards, rows = self.read(); self.assertFalse(cards[0].posted); self.assertFalse(rows[0])
        self.assertFalse(unposted['state']['catalog']['rows'][0]['posted'])

    def test_sibling_draft_is_preserved(self):
        one, two = self.open(), self.open('two')
        self.event(two,'change',control='NoteInput',value='Keep sibling')
        before = self.app.sessions[two][0]._snapshot()
        self.event(one,control='PostButton')
        self.assertEqual(self.app.sessions[two][0]._snapshot(),before)

    def test_stale_duplicate_click_does_not_repeat_root_write(self):
        sid = self.open(); revision = self.app.sessions[sid][0].session.revision
        self.event(sid,control='WriteButton')
        before = self.read()[0][0].revision
        response = self.rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
            'event':'command','revision':revision,'control':'WriteButton'}})
        self.assertEqual(response['form']['result']['error'],'stale_revision')
        self.assertEqual(self.read()[0][0].revision,before)

    def test_dirty_close_refused_and_saved_close_allowed(self):
        sid = self.open();self.event(sid,'change',control='NoteInput',value='Unsaved')
        response = self.rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
            'event':'close','revision':self.app.sessions[sid][0].session.revision}})
        self.assertEqual(response['error'],'save_recovery_required');self.assertIn(sid,self.app.sessions)
        self.event(sid,control='WriteButton');self.event(sid,'close')
        self.assertNotIn(sid,self.app.sessions)

    def test_cancelled_post_is_atomic_and_not_saved(self):
        sid = self.open();self.event(sid,control='NewLineButton')
        self.event(sid,'change',control='NoteInput',value='cancel')
        response = self.event(sid,control='PostButton')
        self.assertEqual(response['state']['posting'][0]['state'],'rejected')
        self.assertEqual(self.read(),((),[]))

    def test_committed_refresh_failure_locks_then_only_refreshes(self):
        sid = self.open();owned = self.broker.objects[sid]
        with patch.object(owned,'_refresh',side_effect=ValueError('projection fault')):
            response = self.event(sid,control='PostButton')
        state = response['state']['posting'][0]
        self.assertEqual(state['state'],'committed');self.assertTrue(owned.pending_refresh)
        self.assertTrue(self.read()[0][0].posted)
        with patch.object(owned.operations.backend,'begin_unit_of_work',side_effect=AssertionError('no replay')):
            recovered = self.rpc('refreshPosting',session=sid)
        self.assertEqual(recovered['state']['posting'][0]['state'],'saved')
        self.assertFalse(owned.pending_refresh)

    def test_known_commit_uses_normal_read_even_without_a_receipt_acceptance_flag(self):
        from types import SimpleNamespace
        sid = self.open(); owned = self.broker.objects[sid]
        execute = owned.operations.execute
        def known_commit(*args, **kwargs):
            self.assertEqual(execute(*args, **kwargs).state, 'committed')
            return SimpleNamespace(state='committed', accepted=False)
        with patch.object(owned.operations, 'execute', side_effect=known_commit):
            state = self.event(sid, control='PostButton')['state']['posting'][0]
        self.assertEqual(state, {'session':sid, 'state':'saved', 'error':None, 'posted':True})
        self.assertFalse(owned.pending_commit)
        self.assertFalse(owned.pending_refresh)

    def test_result_never_exposes_business_operation_id_or_key(self):
        from uuid import uuid4
        sid = self.open()
        identifier = uuid4()
        with patch('yadinassi.configuration.configuration_posting_document.uuid4', return_value=identifier):
            result = self.event(sid, control='WriteButton')
        owned = self.broker.objects[sid]
        text = repr(result)
        self.assertNotIn(str(identifier), text)
        self.assertNotIn(str(owned.object._key.record_id), text)
        self.assertNotIn(str(owned.object._key.database_id), text)
        self.assertNotIn('receipt', result['state']['posting'][0])

    def test_posting_recovery_actions_require_matching_state_and_owner(self):
        one, two = self.open(), self.open('two')
        owned = self.broker.objects[one]
        with patch.object(owned, '_refresh', side_effect=ValueError('projection fault')):
            self.event(one, control='WriteButton')
        with self.assertRaisesRegex(ValueError, 'known commit'):
            self.rpc('refreshPosting', session=two)
        with self.assertRaisesRegex(ValueError, 'unknown posting draft'):
            self.rpc('discardPosting', session=one)
        self.assertIn(one, self.app.sessions)
        self.rpc('refreshPosting', session=one)

    def test_posted_control_is_authoritative_readonly(self):
        sid = self.open()
        response = self.rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
            'event':'change','revision':self.app.sessions[sid][0].session.revision,'control':'PostedLabel','value':encode_value(True)}})
        self.assertEqual(response['form']['result']['error'],'event_failed')
        self.assertEqual(self.read(),((),[]))

    def test_plain_form_write_cannot_enter_root(self):
        sid = self.open();owned = self.broker.objects[sid]
        with self.assertRaises(BackendError):owned.save(owned.image())
        self.assertEqual(self.read(),((),[]))

    def test_effect_runs_only_after_server_dispatch_exits(self):
        sid = self.open();owned=self.broker.objects[sid];server=self.broker.sessions[sid][0]
        original=owned.operations.execute
        def execute(*args,**kwargs):
            self.assertFalse(server.session._busy)
            self.assertTrue(server._gate.acquire(blocking=False));server._gate.release()
            return original(*args,**kwargs)
        with patch.object(owned.operations,'execute',side_effect=execute):self.event(sid,control='PostButton')

    def test_child_transaction_control_remains_denied(self):
        sid=self.open();server=self.broker.sessions[sid][0]
        from yadinassi.types.errors import BSLError
        with self.assertRaises((BSLError,ValueError,BackendError)):
            server.session.interpreter.execute('BeginTransaction();')
        self.assertEqual(self.read(),((),[]))

    def test_empty_handler_not_called_from_browser_name(self):
        sid=self.open()
        with self.assertRaises(ValueError):
            self.rpc('post',session=sid,handler='Posting',mode='Post')
        self.assertEqual(self.read(),((),[]))

    def test_default_and_combined_profiles_refused(self):
        for flags in ({},{'document_objects':True},{'posting_application':True,'business_application':True}):
            with self.assertRaises(ValueError):load_application(EXAMPLE,**flags)

    def test_cli_requires_explicit_database(self):
        with patch('sys.stderr'),self.assertRaises(SystemExit) as raised:main([str(EXAMPLE),'--posting-application'])
        self.assertEqual(raised.exception.code,2)

    def test_reopen_preserves_posted_and_sections(self):
        sid=self.open();self.rpc('catalog',entry=1);self.event(sid,control='NewLineButton')
        response=self.event(sid,control='PostButton');record=response['state']['catalog']['rows'][0]['key']
        closed=self.event(sid,'close')
        with self.assertRaisesRegex(ValueError, 'record is not in the selected catalog projection'):
            self.open('stale-reopened',record)
        other=self.open('reopened',closed['state']['catalog']['rows'][0]['key'])
        owned=self.broker.objects[other]
        self.assertTrue(owned.object.get_member('Posted'));self.assertEqual(len(owned.image().sections[0][1]),1)

    def test_real_process_flag_and_root_command(self):
        process=ConfigurationProcess(EXAMPLE,self.path,posting_application=True)
        try:
            app=ConfigurationController(load_application(EXAMPLE,posting_application=True),process.exchange,posting_application=True)
            def call(method,params):return app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
            call('hello',{'protocol':PROTOCOL})
            sid=call('open',{'entry':1,'request':'owned-child'})['session']
            result=call('form',{'session':sid,'request':{'jsonrpc':'2.0','id':1,'method':'form.event','params':{
                'event':'command','revision':app.sessions[sid][0].session.revision,'control':'PostButton'}}})
            self.assertEqual(result['state']['posting'][0]['state'],'saved')
            self.assertTrue(self.read()[0][0].posted)
            app.close()
        finally:process.close()

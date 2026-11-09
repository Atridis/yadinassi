"""Bounded workspace routing and real SQLite retained editor regressions."""
from pathlib import Path
import tempfile
import unittest
from yadinassi.database_context import SQLiteDBContext
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.ui.orders_workspace import OrdersBroker, WorkspaceController, WorkspaceProcess, PROTOCOL
from yadinassi.ui.protocol import decode_line, encode_line
from test_order_workbench import seed

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'orders.sqlite'
        context = SQLiteDBContext.create(self.path, load_configuration_directory(ROOT / 'examples/forms/order-intake/configuration'))
        seed(context); seed(context, 'O002', 'Second order', 1); context.close()
        self.broker = OrdersBroker(ROOT / 'examples/forms', self.path)
        self.addCleanup(self.broker.close)
        self.controller = WorkspaceController(ROOT / 'examples/forms', self.pipe)
        self.counter = 0
        self.hello = self.rpc('hello', {'protocol': PROTOCOL})

    def pipe(self, raw):
        packet = decode_line(raw)
        result = self.broker.exchange({k: packet[k] for k in ('operation', 'session', 'payload')})
        return encode_line({'id': packet['id'], 'session': packet['session'], 'result': result, 'error': None})

    def rpc(self, method, params):
        self.counter += 1
        return self.controller.exchange({'jsonrpc': '2.0', 'id': self.counter,
            'method': 'workspace.' + method, 'params': params})['result']

    def open(self, row=1, token=None):
        return self.rpc('open', {'revision': self.controller.list_state['revision'],
            'row': row, 'request': token or str(self.counter)})

    def form(self, sid, event=None, **values):
        controller = self.controller.sessions[sid][0]
        request = {'jsonrpc': '2.0', 'id': self.counter + 1,
            'method': 'form.snapshot' if event is None else 'form.event',
            'params': {} if event is None else {'event': event, 'revision': controller.session.revision, **values}}
        return self.rpc('form', {'session': sid, 'request': request})

    def test_list_identity_not_backend_identity(self):
        self.assertEqual(len(self.hello['state']['orders']), 2)
        self.assertEqual(set(self.hello['state']['orders'][0]), {'id', 'code', 'description', 'total'})
        result = self.open()
        self.assertIsNone(result['error'])
        state = result['form']['result']['state']
        self.assertFalse(next(i for i in state['items'] if i['name'] == 'OrdersTable')['visible'])
        self.assertEqual(next(i for i in state['items'] if i['name'] == 'FieldCode')['value']['value'], 'O001')

    def test_duplicate_open_and_retired_id(self):
        opened = self.open(token='same'); sid = opened['session']
        self.assertEqual(self.open(token='same')['session'], sid)
        self.assertEqual(len(self.controller.sessions), 1)
        closed = self.form(sid, 'close')
        self.assertEqual(closed['state']['kind'], 'workspace')
        self.assertEqual(self.open(token='same')['error'], 'retired_session')
        self.assertNotEqual(self.open()['session'], sid)

    def test_capacity_and_stale_selection(self):
        for _ in range(4):
            self.assertIsNone(self.open()['error'])
        self.assertEqual(self.open()['error'], 'capacity')
        self.assertEqual(len(self.broker.sessions), 4)
        self.rpc('list', {'code': ''})
        self.assertEqual(self.rpc('open', {'revision': 1, 'row': 1, 'request': 'stale'})['error'], 'capacity')

    def test_stale_selection_refuses_without_new_context(self):
        self.rpc('list', {'code': ''})
        self.assertEqual(self.rpc('open', {'revision': 1, 'row': 1, 'request': 'stale'})['error'], 'stale_list')
        self.assertEqual(self.broker.sessions, {})

    def test_independent_dirty_close_and_shutdown(self):
        a = self.open()['session']; b = self.open(row=2)['session']
        changed = self.form(a, 'change', control='FieldDescription', value={'type': 'String', 'value': 'Draft A'})
        self.assertTrue(changed['form']['result']['state']['dirty'])
        self.form(b, 'close')
        self.assertIn(a, self.controller.sessions)
        self.assertNotIn(b, self.controller.sessions)
        self.form(a, 'close')
        self.assertIn(a, self.controller.sessions)
        self.assertEqual(self.rpc('close', {})['error'], 'forms_open')
        self.form(a, 'command', control='DiscardButton')
        self.form(a, 'close')
        self.assertEqual(self.rpc('close', {})['state']['kind'], 'closed')

    def test_intake_trusted_dirty_policy(self):
        opened = self.open(row=None); sid = opened['session']
        self.assertIs(opened['form']['result']['state']['dirty'], False)
        changed = self.form(sid, 'change', control='FieldDescription', value={'type': 'String', 'value': 'New draft'})
        self.assertIs(changed['form']['result']['state']['dirty'], True)
        self.form(sid, 'close')
        self.assertIn(sid, self.controller.sessions)

    def test_same_record_editors_conflict(self):
        a = self.open()['session']; b = self.open()['session']
        for sid, description in [(a, 'First write'), (b, 'Second draft')]:
            self.form(sid, 'change', control='FieldDescription', value={'type': 'String', 'value': description})
        saved = self.form(a, 'command', control='SaveOrderButton')
        self.assertFalse(saved['form']['result']['state']['dirty'])
        conflict = self.form(b, 'command', control='SaveOrderButton')['form']['result']['state']
        self.assertTrue(conflict['dirty'])
        status = next(i for i in conflict['items'] if i['name'] == 'FieldStatus')['value']['value']
        self.assertIn('conflict', status)

    def test_malformed_shared_pipe_locks_all_forms(self):
        a = self.open()['session']; b = self.open()['session']
        self.controller.transport = lambda raw: b'{}\n'
        response = self.form(a, 'command', control='SaveOrderButton')
        self.assertTrue(response['state']['uncertain'])
        self.assertTrue(self.controller.sessions[b][0].session.uncertain)
        self.assertEqual(self.open()['error'], 'outcome_unknown')

    def test_real_owned_process(self):
        process = WorkspaceProcess(ROOT / 'examples/forms', self.path)
        self.addCleanup(process.close)
        self.controller = WorkspaceController(ROOT / 'examples/forms', process.exchange)
        self.rpc('hello', {'protocol': PROTOCOL})
        self.assertIsNone(self.open()['error'])

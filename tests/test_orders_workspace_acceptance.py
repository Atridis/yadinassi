"""Additional bounded workspace lifecycle and projection acceptance cases."""
import unittest
from unittest import mock
from decimal import Decimal
import test_orders_workspace as base
from test_order_workbench import seed
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.local_app import LocalTransportError
from yadinassi.ui.protocol import encode_value, decode_line, encode_line


class WorkspaceAcceptanceTests(unittest.TestCase):
    setUp = base.WorkspaceTests.setUp
    pipe = base.WorkspaceTests.pipe
    rpc = base.WorkspaceTests.rpc
    open = base.WorkspaceTests.open
    form = base.WorkspaceTests.form

    def change(self, sid, name, value):
        return self.form(sid, 'change', control='Field' + name, value=encode_value(value))

    def test_create_refresh_edit_independent_reopen(self):
        sid = self.open(row=None)['session']
        self.change(sid, 'Code', 'O003'); self.change(sid, 'Description', 'New order')
        self.form(sid, 'command', control='AddLineButton')
        for column, value in [('Description', 'Line'), ('Quantity', Decimal('2')), ('Price', Decimal('3.25'))]:
            self.form(sid, 'cell', control='LinesTable', row=1, column=column, value=encode_value(value))
        saved = self.form(sid, 'command', control='SaveOrderButton')
        self.assertFalse(saved['form']['result']['state']['dirty'])
        self.form(sid, 'close')
        refreshed = self.rpc('list', {'code': 'O003'})
        self.assertEqual(refreshed['state']['orders'][0]['total'], encode_value(Decimal('6.50')))
        editor = self.open()['session']
        self.change(editor, 'Description', 'Edited same order')
        self.form(editor, 'command', control='SaveOrderButton')
        self.form(editor, 'close')
        reopened = self.open()['form']['result']['state']
        description = next(i for i in reopened['items'] if i['name'] == 'FieldDescription')['value']['value']
        self.assertEqual(description, 'Edited same order')

    def test_discard_new_order_preserves_other_editor(self):
        editor = self.open()['session']; intake = self.open(row=None)['session']
        self.change(intake, 'Description', 'Abandoned')
        self.assertIsNone(self.rpc('discard', {'session': intake})['error'])
        self.assertIn(editor, self.controller.sessions)
        self.assertNotIn(intake, self.broker.sessions)
        self.assertEqual(self.rpc('discard', {'session': editor})['error'], 'discard_refused')

    def test_intake_attempted_save_cannot_be_abandoned(self):
        sid = self.open(row=None)['session']
        self.broker.sessions[sid][0].session.form._data['saveattempted'] = True
        self.assertEqual(self.rpc('discard', {'session': sid})['error'], 'discard_refused')
        self.assertIn(sid, self.controller.sessions)

    def test_oversized_record_open_cleanup_keeps_existing_form(self):
        context = SQLiteDBContext(self.path)
        try:
            seed(context, 'O003', 'Oversized', 33)
        finally:
            context.close()
        first = self.open()['session']
        self.rpc('list', {'code': 'O003'})
        result = self.open()
        self.assertEqual(result['error'], 'open_failed')
        self.assertEqual(list(self.controller.sessions), [first])
        self.assertEqual(list(self.broker.sessions), [first])
        self.rpc('list', {'code': 'O002'})
        self.assertEqual(self.open()['session'], 'form-3')

    def test_partial_client_open_failure_cleans_child_context(self):
        first = self.open()['session']
        with mock.patch('yadinassi.ui.orders_workspace.FormController', side_effect=ValueError('bad package')):
            self.assertEqual(self.open()['error'], 'open_failed')
        self.assertEqual(list(self.broker.sessions), [first])
        original = self.controller.transport
        def refused(raw):
            packet = decode_line(raw)
            if packet['operation'] == 'create':
                return encode_line({'id': packet['id'], 'session': packet['session'],
                                    'result': None, 'error': 'operation_failed'})
            return original(raw)
        self.controller.transport = refused
        self.assertEqual(self.open()['error'], 'operation_failed')
        self.assertFalse(self.controller.uncertain)
        self.assertFalse(self.controller.sessions[first][0].session.uncertain)

    def test_identical_row_control_and_revision_are_session_scoped(self):
        a = self.open()['session']; b = self.open()['session']
        self.assertEqual(self.controller.sessions[a][0].session.revision, self.controller.sessions[b][0].session.revision)
        self.form(a, 'cell', control='LinesTable', row=1, column='Description', value=encode_value('Only A'))
        a_rows = next(i for i in self.form(a)['form']['result']['state']['items'] if i['name'] == 'LinesTable')['rows']
        b_rows = next(i for i in self.form(b)['form']['result']['state']['items'] if i['name'] == 'LinesTable')['rows']
        self.assertEqual(a_rows[0]['values'][0]['value'], 'Only A')
        self.assertEqual(b_rows[0]['values'][0]['value'], 'Line 1')

    def test_open_token_cannot_be_retargeted(self):
        self.open(token='immutable')
        with self.assertRaises(ValueError):
            self.open(row=2, token='immutable')
        self.assertEqual(len(self.broker.sessions), 1)

    def test_malformed_open_replica_locks_existing_forms(self):
        existing = self.open()['session']
        original = self.broker.exchange
        def exchange(packet):
            if packet['operation'] == 'form' and packet['session'] != existing:
                return {'malformed': True}
            return original(packet)
        with mock.patch.object(self.broker, 'exchange', side_effect=exchange):
            response = self.open(row=2)
        self.assertEqual(response['error'], 'open_failed')
        self.assertTrue(response['state']['uncertain'])
        self.assertTrue(self.controller.sessions[existing][0].session.uncertain)
        self.assertEqual(self.rpc('close', {})['error'], 'outcome_unknown')

    def fail_management(self, operation):
        original = self.controller.transport
        def failed(raw):
            packet = decode_line(raw)
            if packet['operation'] == operation:
                return encode_line({'id': packet['id'], 'session': packet['session'],
                                    'result': None, 'error': 'operation_failed'})
            return original(raw)
        self.controller.transport = failed

    def test_failed_retirement_locks_all_retained_forms(self):
        a = self.open()['session']; b = self.open(row=2)['session']
        self.fail_management('retire')
        with self.assertRaises(LocalTransportError):
            self.form(a, 'close')
        self.assertTrue(self.controller.uncertain)
        self.assertEqual(set(self.controller.sessions), {a, b})
        self.assertTrue(all(controller.session.uncertain for controller, _ in self.controller.sessions.values()))
        self.assertEqual(self.open()['error'], 'outcome_unknown')

    def test_failed_abandon_locks_and_retains_intake(self):
        sid = self.open(row=None)['session']
        self.fail_management('abandon')
        with self.assertRaises(LocalTransportError):
            self.rpc('discard', {'session': sid})
        self.assertTrue(self.controller.uncertain)
        self.assertIn(sid, self.controller.sessions)
        self.assertTrue(self.controller.sessions[sid][0].session.uncertain)

    def test_failed_partial_open_cleanup_locks_existing_forms(self):
        sid = self.open()['session']
        self.fail_management('retire')
        with mock.patch('yadinassi.ui.orders_workspace.FormController', side_effect=ValueError('bad package')):
            with self.assertRaises(LocalTransportError):
                self.open(row=2)
        self.assertTrue(self.controller.uncertain)
        self.assertTrue(self.controller.sessions[sid][0].session.uncertain)
        self.assertEqual(len(self.broker.sessions), 2)

"""Existing Orders vertical slice: real SQLite, owned child process and fault recovery."""
from decimal import Decimal
from pathlib import Path
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError, CatalogDraft, TabularRow, TabularSectionRows
from yadinassi.database_context import SQLiteDBContext
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.form_replication import ReplicatedFormServer
from yadinassi.form_runtime import FormServerBinding
from yadinassi.ui.form_app import FormController, FormProcess, create_server
from yadinassi.ui.form_package import load_client, load_server
from yadinassi.ui.order_workbench import OrdersWorkbenchSession
from yadinassi.ui.protocol import encode_line
from test_form_table_app import state, event, item, scalar, table, row_values, IntakeHelpers

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/forms/order-editor'
CONFIGURATION = ROOT / 'examples/forms/order-intake/configuration'


def seed(context, code='O001', description='First order', count=2):
    vm = Interpreter(database_context=context)
    try:
        manager = vm._catalogs.get_index('Orders')
        obj = manager.create_item()
        obj.set_member('Code', code); obj.set_member('Description', description)
        obj.set_member('Total', Decimal(count) * Decimal('2.50'))
        for index in range(count):
            row = obj.get_member('Lines').add()
            for name, value in [('ItemDescription', 'Line ' + str(index + 1)),
                                ('Quantity', Decimal('1')), ('Price', Decimal('2.50')),
                                ('Amount', Decimal('2.50'))]:
                row.set_member(name, value)
        obj.write()
        return obj._key
    finally:
        vm.close()


def pair(context):
    package = load_server(EXAMPLE)
    application = OrdersWorkbenchSession(context)
    server = ReplicatedFormServer(package.source, package.endpoints,
        handlers=package.handlers, attributes=package.attributes, tables=package.tables,
        initial_values=package.initial_values, bindings=package.lifecycle,
        database_context=context, server_bindings=application.bindings())
    return FormController(load_client(EXAMPLE), server.exchange), server, application


class WorkbenchHelpers(IntakeHelpers):
    def open_order(self, controller, code='O001'):
        current = state(controller, 'snapshot')
        row = next(row for row in item(current, 'OrdersTable')['rows'] if row['values'][0]['value'] == code)
        self.good(event(controller, 'select', 'OrdersTable', row=row['id']))
        return self.good(event(controller, control='OpenOrderButton'))

    def description(self, controller, value):
        return self.good(event(controller, 'change', 'FieldDescription', value=scalar(value)))

    def status(self, result):
        return item(result, 'FieldStatus')['value']['value']


class OrdersWorkbenchTests(WorkbenchHelpers, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'orders.sqlite'
        self.context = SQLiteDBContext.create(self.path, load_configuration_directory(CONFIGURATION))
        self.addCleanup(self.context.close)
        self.key = seed(self.context)
        self.other = seed(self.context, 'O002', 'Second order', 1)
        self.controller, self.server, self.application = pair(self.context)
        self.opened = self.good(state(self.controller))

    def test_closed_trusted_package_and_complete_projection(self):
        self.assertEqual(load_server(EXAMPLE).application, 'orders-workbench/1')
        self.assertEqual(load_client(EXAMPLE).discard_commands, (('Discard', 'DiscardCommand'),))
        self.assertEqual(self.opened['state']['discardCommands'], ['DiscardButton'])
        self.assertFalse(self.opened['state']['dirty'])
        self.assertTrue(item(self.opened, 'OrdersTable')['readOnly'])
        self.assertTrue(table(self.opened)['readOnly'])
        loaded = self.open_order(self.controller)
        self.assertEqual(len(table(loaded)['rows']), 2)
        self.assertEqual(item(loaded, 'FieldDescription')['value']['value'], 'First order')
        self.assertFalse(table(loaded)['readOnly'])
        self.assertEqual(self.application.object._key, self.key)
        raw = encode_line(loaded)
        for private in (str(self.key.record_id).encode(), str(self.path).encode(), b'Workbench', b'Procedure'):
            self.assertNotIn(private, raw)
        self.assertIsNone(self.controller.session.interpreter.database_context)

    def test_save_same_record_then_continue_and_unchanged_save_never_writes(self):
        loaded = self.open_order(self.controller)
        old_revision = self.application.object._revision
        line_ids = tuple(r._identity for r in self.application.object._sections['lines']._rows)
        self.description(self.controller, 'Changed once')
        self.good(self.cell(self.controller, table(loaded)['rows'][0]['id'], 'Price', Decimal('4.25')))
        saved = self.good(event(self.controller))
        self.assertFalse(saved['state']['dirty']); self.assertFalse(table(saved)['readOnly'])
        self.assertNotEqual(self.application.object._revision, old_revision)
        self.assertEqual(self.application.object._key, self.key)
        self.assertEqual(tuple(r._identity for r in self.application.object._sections['lines']._rows), line_ids)
        with mock.patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('no second write')) as writes:
            result = self.good(event(self.controller))
            self.assertIn('No changes', self.status(result)); writes.assert_not_called()
        self.description(self.controller, 'Changed twice')
        self.good(event(self.controller))
        header, rows, count = self.readback(self.path)
        self.assertEqual(header, ('O001', 'Changed twice', Decimal('6.75')))
        self.assertEqual(rows[0][2], Decimal('4.25')); self.assertEqual(count, Decimal(2))

    def test_editable_code_never_becomes_target_identity(self):
        self.open_order(self.controller)
        self.good(event(self.controller, 'change', 'FieldCode', value=scalar('RENAMED')))
        self.description(self.controller, 'Same identity')
        self.good(event(self.controller))
        self.assertEqual(self.application.object._key, self.key)
        with SQLiteDBContext(self.path) as context:
            vm = Interpreter(database_context=context)
            try:
                self.assertEqual(vm.execute('Catalogs.Orders.FindByCode("RENAMED").GetObject().Description'), 'Same identity')
                self.assertTrue(vm.execute('Catalogs.Orders.FindByCode("O001").IsEmpty()'))
            finally: vm.close()

    def test_two_writers_conflict_keeps_edits_then_explicit_reload(self):
        self.open_order(self.controller)
        with SQLiteDBContext(self.path) as other_context:
            second, _, _ = pair(other_context); self.good(state(second)); self.open_order(second)
            self.description(second, 'Concurrent winner'); self.good(event(second))
        self.description(self.controller, 'Keep this draft')
        failed = self.good(event(self.controller))
        self.assertIn('conflict', self.status(failed))
        self.assertEqual(item(failed, 'FieldDescription')['value']['value'], 'Keep this draft')
        self.assertTrue(failed['state']['dirty']); self.assertFalse(table(failed)['readOnly'])
        failed_again = self.good(event(self.controller))
        self.assertIn('conflict', self.status(failed_again))
        reloaded = self.good(event(self.controller, control='DiscardButton'))
        self.assertEqual(item(reloaded, 'FieldDescription')['value']['value'], 'Concurrent winner')
        self.assertFalse(reloaded['state']['dirty'])

    def test_business_validation_remains_recoverable(self):
        loaded = self.open_order(self.controller)
        row = table(loaded)['rows'][0]['id']
        for bad in (Decimal('0'), Decimal('0.001'), Decimal('1000001')):
            self.good(self.cell(self.controller, row, 'Quantity', bad))
            with mock.patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('invalid')):
                failed = event(self.controller)
            self.assertEqual(failed['error'], 'event_failed'); self.assertTrue(failed['state']['dirty'])
            self.assertFalse(table(failed)['readOnly'])
        self.good(self.cell(self.controller, row, 'Quantity', Decimal('2')))
        self.good(event(self.controller))
        self.assertEqual(self.readback(self.path)[0][2], Decimal('7.50'))

    def test_duplicate_code_rejection_does_not_retarget_or_lock(self):
        self.open_order(self.controller)
        self.good(event(self.controller, 'change', 'FieldCode', value=scalar('O002')))
        result = self.good(event(self.controller))
        self.assertIn('rejected', self.status(result)); self.assertEqual(self.application.object._key, self.key)
        self.assertFalse(table(result)['readOnly']); self.assertTrue(result['state']['dirty'])
        self.good(event(self.controller, control='DiscardButton'))
        self.assertEqual(self.readback(self.path)[0][0], 'O001')

    def test_dirty_close_and_switch_require_discard_with_fresh_row_ids(self):
        loaded = self.open_order(self.controller)
        old = table(loaded)['rows'][0]['id']
        self.description(self.controller, 'Unsaved')
        closed = self.good(event(self.controller, 'close'))
        self.assertEqual(closed['state']['kind'], 'form')
        blocked = self.open_order(self.controller, 'O002')
        self.assertIn('Unsaved changes', self.status(blocked)); self.assertEqual(self.application.object._key, self.key)
        self.good(event(self.controller, control='DiscardButton'))
        switched = self.open_order(self.controller, 'O002')
        self.assertEqual(len(table(switched)['rows']), 1)
        self.assertGreater(table(switched)['rows'][0]['id'], old)
        self.assertEqual(self.cell(self.controller, old, 'Price', Decimal('9'))['error'], 'event_failed')
        self.assertFalse(state(self.controller, 'snapshot')['state']['dirty'])
        self.assertEqual(self.good(event(self.controller, 'close'))['state']['kind'], 'closed')

    def test_failed_complete_load_preserves_previous_record_and_oversize_is_never_truncated(self):
        loaded = self.open_order(self.controller)
        baseline = self.application.baseline; obj = self.application.object
        seed(self.context, 'TOOBIG', 'Too many lines', 33)
        self.good(event(self.controller, control='SearchOrdersButton'))
        failed = self.open_order(self.controller, 'TOOBIG')
        self.assertIn('complete order', self.status(failed))
        self.assertEqual(table(failed)['rows'], table(loaded)['rows'])
        self.assertIs(self.application.object, obj); self.assertEqual(self.application.baseline, baseline)
        self.assertEqual(len(table(failed)['rows']), 2)

    def test_failed_reload_preserves_server_edits_and_selected_object(self):
        self.open_order(self.controller); self.description(self.controller, 'Still mine')
        obj = self.application.object
        with mock.patch.object(self.application, '_fresh', side_effect=BackendError('busy')):
            result = self.good(event(self.controller, control='DiscardButton'))
        self.assertIn('Reload failed', self.status(result))
        self.assertEqual(item(result, 'FieldDescription')['value']['value'], 'Still mine')
        self.assertIs(self.application.object, obj); self.assertTrue(result['state']['dirty'])

    def test_bounded_exact_search_issues_new_row_identities_and_closes_read_views(self):
        self.good(event(self.controller, 'change', 'FieldSearchCode', value=scalar('O002')))
        first = self.good(event(self.controller, control='SearchOrdersButton'))
        row = item(first, 'OrdersTable')['rows'][0]
        self.assertEqual(len(item(first, 'OrdersTable')['rows']), 1)
        second = self.good(event(self.controller, control='SearchOrdersButton'))
        self.assertGreater(item(second, 'OrdersTable')['rows'][0]['id'], row['id'])
        self.assertEqual(event(self.controller, 'select', 'OrdersTable', row=row['id'])['error'], 'event_failed')
        # An external writer can complete while the form remains open.
        with SQLiteDBContext(self.path) as independent:
            seed(independent, 'O003', 'No held read view', 1)

    def test_healthy_channel_uncertain_commit_locks_and_resolves_exact_intent_once(self):
        from yadinassi.sqlite_catalog import _View
        self.open_order(self.controller); self.description(self.controller, 'Committed exact intent')
        commit = _View.commit; calls = []
        def lost(tx):
            calls.append(tx); commit(tx); raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', lost):
            failed = self.good(event(self.controller))
        self.assertFalse(failed['state']['uncertain']); self.assertTrue(self.application.pending_commit)
        self.assertTrue(table(failed)['readOnly']); self.assertFalse(item(failed, 'DiscardButton')['enabled'])
        intent = self.application.object._pending_write
        self.assertEqual(event(self.controller, control='DiscardButton')['error'], 'event_failed')
        with mock.patch.object(self.context.backend, 'resolve_write', side_effect=BackendError('busy')):
            self.good(event(self.controller, control='ResolveButton'))
        self.assertIs(self.application.object._pending_write, intent)
        self.assertTrue(self.application.pending_commit)
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('never duplicate')):
            resolved = self.good(event(self.controller, control='ResolveButton'))
        self.assertFalse(self.application.pending_commit); self.assertFalse(resolved['state']['dirty'])
        self.assertFalse(table(resolved)['readOnly']); self.assertEqual(len(calls), 1)
        self.assertEqual(self.readback(self.path)[0][1], 'Committed exact intent')

    def test_confirmed_commit_failed_refresh_only_refreshes_without_writing(self):
        self.open_order(self.controller); self.description(self.controller, 'Known committed')
        with mock.patch.object(self.application, '_fresh', side_effect=BackendError('busy')):
            failed = self.good(event(self.controller))
        self.assertTrue(self.application.pending_refresh); self.assertFalse(self.application.pending_commit)
        self.assertIn('saved, but refresh failed', self.status(failed))
        self.assertEqual(item(failed, 'ResolveButton')['title'], 'Refresh saved record')
        self.assertFalse(item(failed, 'SaveOrderButton')['enabled'])
        with mock.patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('refresh only')):
            refreshed = self.good(event(self.controller, control='ResolveButton'))
        self.assertFalse(self.application.pending_refresh); self.assertFalse(refreshed['state']['dirty'])
        self.assertEqual(item(refreshed, 'FieldDescription')['value']['value'], 'Known committed')

    def test_postcommit_projection_rejection_retains_refresh_obligation(self):
        self.open_order(self.controller); self.description(self.controller, 'Committed')
        original = self.application._preflight
        with mock.patch.object(self.application, '_preflight', side_effect=ValueError('oversized projection')):
            failed = self.good(event(self.controller))
        self.assertTrue(self.application.pending_refresh); self.assertTrue(failed['state']['dirty'])
        self.assertEqual(self.readback(self.path)[0][1], 'Committed')
        with mock.patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('refresh only')):
            self.good(event(self.controller, control='ResolveButton'))
        self.assertFalse(self.application.pending_refresh)

    def test_discard_policy_live_handler_change_fails_closed(self):
        self.controller.session.form.commands._values['discard'].action = 'SaveCommand'
        with self.assertRaises(Exception):
            state(self.controller, 'snapshot')
        self.assertTrue(self.controller.session.uncertain)

    def test_host_binding_inventory_rejects_collisions_and_non_scalar_returns(self):
        package = load_server(EXAMPLE)
        for name in ('Create', 'Code', 'Lines', 'Message', 'WorkbenchSave'):
            bindings = self.application.bindings() + (FormServerBinding(name, lambda session: None),)
            with self.subTest(name=name), self.assertRaises(ValueError):
                ReplicatedFormServer(package.source, package.endpoints, handlers=package.handlers,
                    attributes=package.attributes, tables=package.tables, server_bindings=bindings)
        bad = FormServerBinding('ReturnObject', lambda session: object())
        server = ReplicatedFormServer('&AtServer\nProcedure Create(Cancel, StandardProcessing) ReturnObject(); EndProcedure', {},
            handlers=(), bindings={'OnCreateAtServer': 'Create'}, server_bindings=(bad,))
        from yadinassi.form_replication import ReplicatedFormSession
        client = ReplicatedFormSession('', server.exchange, handlers=())
        with self.assertRaises(Exception): client.open()
        self.assertFalse(client.uncertain)

    def test_manifest_rejects_arbitrary_application_and_unbound_discard_policy(self):
        directory = Path(self.temp.name) / 'package'; shutil.copytree(EXAMPLE, directory)
        for file, field, value in [('server.json', 'application', 'arbitrary.module'),
                                   ('client.json', 'discardCommands', [{'command': 'SaveOrder', 'handler': 'Unknown'}])]:
            path = directory / file; original = path.read_text(); data = json.loads(original)
            data[field] = value; path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): (load_server if file.startswith('server') else load_client)(directory)
            path.write_text(original)


class OrdersWorkbenchProcessTests(WorkbenchHelpers, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'orders.sqlite'
        with SQLiteDBContext.create(self.path, load_configuration_directory(CONFIGURATION)) as context:
            self.key = seed(context); seed(context, 'O002', 'Second order', 1)
        self.process = FormProcess(EXAMPLE, self.path); self.addCleanup(self.process.close)
        self.controller = FormController(load_client(EXAMPLE), self.process.exchange)
        self.good(state(self.controller))

    def test_real_child_edit_add_delete_recalculate_save_twice_and_reopen(self):
        self.assertNotEqual(self.process.child.pid, os.getpid())
        loaded = self.open_order(self.controller)
        first, second = [r['id'] for r in table(loaded)['rows']]
        self.good(self.cell(self.controller, first, 'Price', Decimal('2.35')))
        self.good(event(self.controller, 'select', 'LinesTable', row=second))
        self.good(event(self.controller, control='DeleteLineButton'))
        self.line(self.controller, 'New service', '2', '3.10')
        self.good(event(self.controller, control='RecalculateButton'))
        saved = self.good(event(self.controller))
        self.assertEqual(Decimal(item(saved, 'FieldTotal')['value']['value']), Decimal('8.55'))
        self.description(self.controller, 'Continued editing')
        self.good(event(self.controller)); self.good(event(self.controller))
        self.assertEqual(self.good(event(self.controller, 'close'))['state']['kind'], 'closed')
        self.process.close()
        header, rows, count = self.readback(self.path)
        self.assertEqual(header, ('O001', 'Continued editing', Decimal('8.55')))
        self.assertEqual(rows, (('Line 1', Decimal('1'), Decimal('2.35'), Decimal('2.35')),
                                ('New service', Decimal('2'), Decimal('3.10'), Decimal('6.20'))))
        self.assertEqual(count, Decimal(2))
        fresh = FormProcess(EXAMPLE, self.path); self.addCleanup(fresh.close)
        controller = FormController(load_client(EXAMPLE), fresh.exchange); self.good(state(controller))
        self.assertEqual(item(self.open_order(controller), 'FieldDescription')['value']['value'], 'Continued editing')

    def test_lost_response_after_commit_is_terminal_without_replay(self):
        self.open_order(self.controller); self.description(self.controller, 'Durable despite lost response')
        original = self.controller.session._exchange; calls = []
        def lost(raw): calls.append(raw); original(raw); raise OSError('private transport fault')
        self.controller.session._exchange = lost
        failed = event(self.controller)
        self.assertEqual(failed['error'], 'outcome_unknown'); self.assertTrue(failed['state']['uncertain'])
        for control in ('SaveOrderButton', 'ResolveButton', 'DiscardButton'):
            self.assertEqual(event(self.controller, control=control)['error'], 'outcome_unknown')
        self.assertTrue(state(self.controller, 'snapshot')['state']['uncertain']); self.assertEqual(len(calls), 1)
        self.assertNotIn(b'private transport', encode_line(failed))
        self.process.close()
        self.assertEqual(self.readback(self.path)[0][1], 'Durable despite lost response')

    def test_process_discard_and_close_persist_nothing(self):
        loaded = self.open_order(self.controller)
        self.description(self.controller, 'Abandoned')
        self.good(self.cell(self.controller, table(loaded)['rows'][0]['id'], 'Price', Decimal('99')))
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'form')
        discarded = self.good(event(self.controller, control='DiscardButton'))
        self.assertFalse(discarded['state']['dirty'])
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'closed')
        self.process.close()
        self.assertEqual(self.readback(self.path)[0], ('O001', 'First order', Decimal('5.00')))

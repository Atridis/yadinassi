"""Opt-in typed-reference order workflow, ownership, faults and SQLite readback."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError, CatalogKey
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.form_app import PROTOCOL as FORM_PROTOCOL
from yadinassi.ui.form_package import load_server
from yadinassi.ui.reference_orders import OwnedChoice, APPLY_CHOICE_ENDPOINT
from yadinassi.ui.reference_orders_workspace import (
    ReferenceOrdersBroker, ReferenceWorkspaceController, ReferenceWorkspaceProcess, PROTOCOL)
from yadinassi.ui.protocol import decode_line, encode_line

ROOT = Path(__file__).resolve().parents[1]
FORMS = ROOT / 'examples/forms'
CONFIGURATION = FORMS / 'reference-order/configuration'


def seed_references(context, *, orders=True):
    vm = Interpreter(database_context=context)
    try:
        refs = {}
        for catalog, code, description, price in (
                ('Customers', 'C001', 'Shared display', None), ('Customers', 'C002', 'Shared display', None),
                ('Products', 'P001', 'Shared product', Decimal('2.50')),
                ('Products', 'P002', 'Shared product', Decimal('4.25'))):
            manager = vm._catalogs.get_index(catalog)
            obj = manager.create_item()
            obj.set_member('Code', code); obj.set_member('Description', description)
            if price is not None:
                obj.set_member('UnitPrice', price)
            obj.write(); refs[code] = obj._key
        if orders:
            manager = vm._catalogs.get_index('Orders')
            order = manager.create_item()
            for name, value in (('Code', 'O001'), ('Description', 'First order'), ('Total', Decimal('2.50')),
                    ('Customer', vm._catalogs.get_index('Customers')._ref(refs['C001'].record_id))):
                order.set_member(name, value)
            row = order.get_member('Lines').add()
            for name, value in (('Product', vm._catalogs.get_index('Products')._ref(refs['P001'].record_id)),
                    ('ItemDescription', 'Original description'), ('Quantity', Decimal('1')),
                    ('Price', Decimal('2.50')), ('Amount', Decimal('2.50'))):
                row.set_member(name, value)
            order.write(); refs['O001'] = order._key
        return refs
    finally:
        vm.close()


def item(result, name):
    return next(i for i in result['form']['result']['state']['items'] if i['name'] == name)


class ReferenceOrdersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'references.sqlite'
        with SQLiteDBContext.create(self.path, load_configuration_directory(CONFIGURATION)) as context:
            self.refs = seed_references(context)
        self.broker = ReferenceOrdersBroker(FORMS, self.path)
        self.addCleanup(self.broker.close)
        self.controller = ReferenceWorkspaceController(FORMS, self.pipe)
        self.counter = 0
        self.hello = self.rpc('hello', {'protocol': PROTOCOL})

    def pipe(self, raw):
        packet = decode_line(raw)
        try:
            result = self.broker.exchange({k: packet[k] for k in ('operation', 'session', 'payload')})
            error = None
        except Exception:
            result, error = None, 'operation_failed'
        return encode_line({'id': packet['id'], 'session': packet['session'], 'result': result, 'error': error})

    def rpc(self, method, params):
        self.counter += 1
        return self.controller.exchange({'jsonrpc': '2.0', 'id': self.counter,
            'method': 'workspace.' + method, 'params': params})['result']

    def open(self, row=1, token=None):
        result = self.rpc('open', {'revision': self.controller.list_state['revision'], 'row': row,
            'request': token or str(self.counter)})
        self.assertIsNone(result['error'], result)
        return result

    def form(self, sid, event=None, **values):
        controller = self.controller.sessions[sid][0]
        request = {'jsonrpc': '2.0', 'id': self.counter + 1,
            'method': 'form.snapshot' if event is None else 'form.event',
            'params': {} if event is None else {'event': event, 'revision': controller.session.revision, **values}}
        return self.rpc('form', {'session': sid, 'request': request})

    def command(self, sid, name):
        return self.form(sid, 'command', control=name + 'Button')

    def change(self, sid, name, value):
        return self.form(sid, 'change', control='Field' + name, value={'type': 'String', 'value': value})

    def choice(self, owner, target='Customer'):
        if target == 'Product':
            state = self.form(owner)
            row = item(state, 'LinesTable')['rows'][0]['id']
            self.form(owner, 'select', control='LinesTable', row=row)
        result = self.command(owner, 'Choose' + target)
        child = next(row['id'] for row in result['state']['sessions'] if row['kind'] == 'choice')
        mounted = self.rpc('form', {'session': child, 'request': {'jsonrpc': '2.0', 'id': 1,
            'method': 'form.hello', 'params': {'protocol': FORM_PROTOCOL}}})
        self.assertIsNone(mounted['form']['result']['error'], mounted)
        return child

    def select(self, child, code):
        state = self.form(child)
        row = next(r['id'] for r in item(state, 'ChoicesTable')['rows'] if r['values'][0]['value'] == code)
        self.form(child, 'select', control='ChoicesTable', row=row)
        return self.command(child, 'Choose')

    def read_order(self, code='O001'):
        with SQLiteDBContext(self.path) as context:
            vm = Interpreter(database_context=context)
            try:
                manager = vm._catalogs.get_index('Orders')
                ref = vm.execute('Catalogs.Orders.FindByCode("' + code + '")')
                obj = manager._get_object(ref)
                return obj._key, tuple(manager._stored(field, obj.get_member(field.name)) for field in manager._schema.fields), obj._sections['lines']._stored_rows().rows, obj._revision
            finally:
                vm.close()

    def mutate_catalog(self, code, catalog, field, value):
        with SQLiteDBContext(self.path) as context:
            vm = Interpreter(database_context=context)
            try:
                obj = vm.execute('Catalogs.' + catalog + '.FindByCode("' + code + '").GetObject()')
                obj.set_member(field, value); obj.write()
            finally:
                vm.close()

    def test_exact_wire_shape_has_only_scalar_presentation_and_opaque_ids(self):
        self.assertEqual(set(self.hello), {'protocol', 'state', 'error', 'session', 'form'})
        self.assertEqual(set(self.hello['state']), {'kind', 'revision', 'orders', 'truncated', 'sessions', 'uncertain'})
        opened = self.open(); owner = opened['session']; child = self.choice(owner)
        state = self.form(child)
        self.assertEqual(state['state']['sessions'], [
            {'id': owner, 'kind': 'order', 'owner': None}, {'id': child, 'kind': 'choice', 'owner': owner}])
        raw = encode_line(state)
        for secret in [str(self.path), 'CatalogKey', 'ReferenceApplyChoice', 'ApplyChoice', 'Procedure'] + [str(k.record_id) for k in self.refs.values()]:
            self.assertNotIn(secret.encode(), raw)

    def test_selectors_require_owned_broker_and_existing_packages_stay_valid(self):
        for package in ('reference-order', 'catalog-choice'):
            with self.assertRaisesRegex(ValueError, 'workspace broker'):
                load_server(FORMS / package)
            self.assertIsNotNone(load_server(FORMS / package, owned_choices=True).application)
        self.assertEqual(load_server(FORMS / 'order-editor').application, 'orders-workbench/1')
        self.assertIsNone(load_server(FORMS / 'order-intake').application)

    def test_customer_choice_uses_exact_key_despite_duplicate_display(self):
        owner = self.open()['session']; child = self.choice(owner)
        closed = self.select(child, 'C002')
        self.assertEqual(closed['form']['result']['state']['kind'], 'closed')
        self.assertEqual(len(closed['state']['sessions']), 1)
        self.assertEqual(self.broker.applications[owner].customer, self.refs['C002'])
        self.assertTrue(self.form(owner)['form']['result']['state']['dirty'])
        self.command(owner, 'SaveOrder')
        self.assertEqual(self.read_order()[1][0], self.refs['C002'])

    def test_product_choice_is_bound_to_exact_selected_live_row(self):
        owner = self.open()['session']; added = self.command(owner, 'AddLine')
        second = item(added, 'LinesTable')['currentRow']
        selected = self.command(owner, 'ChooseProduct')
        child = selected['state']['sessions'][1]['id']
        self.rpc('form', {'session': child, 'request': {'jsonrpc': '2.0', 'id': 1, 'method': 'form.hello', 'params': {'protocol': FORM_PROTOCOL}}})
        self.select(child, 'P002')
        application = self.broker.applications[owner]
        self.assertEqual(application.products[second], self.refs['P002'])
        state = self.form(owner)
        rows = item(state, 'LinesTable')['rows']
        self.assertEqual(rows[0]['values'][3]['value'], '2.50')
        self.assertEqual(rows[1]['values'][3]['value'], '4.25')
        self.command(owner, 'SaveOrder')
        saved = self.read_order()
        self.assertEqual([r.values[0] for r in saved[2]], [self.refs['P001'], self.refs['P002']])
        self.assertEqual(saved[1][1], Decimal('6.75'))

    def test_product_choice_after_highest_row_deleted_keeps_allocation_high_water(self):
        owner = self.open(row=None)['session']
        first = item(self.command(owner, 'AddLine'), 'LinesTable')['currentRow']
        deleted = item(self.command(owner, 'AddLine'), 'LinesTable')['currentRow']
        self.assertGreater(deleted, first)
        self.command(owner, 'DeleteLine')
        closed = self.select(self.choice(owner, 'Product'), 'P002')
        self.assertFalse(closed['state']['uncertain'])
        self.assertEqual(closed['form']['result']['state']['kind'], 'closed')
        app = self.broker.applications[owner]
        self.assertEqual(app.products[first], self.refs['P002'])
        resumed = self.form(owner)
        self.assertIn('Selection applied', item(resumed, 'FieldStatus')['value']['value'])
        self.assertEqual(item(resumed, 'LinesTable')['rows'][0]['values'][3]['value'], '4.25')
        next_id = item(self.command(owner, 'AddLine'), 'LinesTable')['currentRow']
        self.assertGreater(next_id, deleted)

    def test_projection_preflight_still_rejects_retired_row_identity_reuse(self):
        owner = self.open(row=None)['session']
        self.command(owner, 'AddLine')
        deleted = item(self.command(owner, 'AddLine'), 'LinesTable')['currentRow']
        self.command(owner, 'DeleteLine')
        app = self.broker.applications[owner]
        session = self.broker.sessions[owner][0].session
        table = session.form._tables['lines']
        before = table._snapshot()
        live_values = before.rows[0][1]
        with self.assertRaisesRegex(ValueError, 'removed row identity reused'):
            app._preflight(session, {}, {'lines': before.rows + ((deleted, live_values),)})
        self.assertEqual(table._snapshot(), before)
        self.assertEqual(table._allocated, deleted)

    def test_cancel_and_ordinary_close_preserve_reference_and_do_not_write(self):
        owner = self.open()['session']; before = self.read_order()
        for event in ('cancel', 'close'):
            child = self.choice(owner)
            with mock.patch('yadinassi.sqlite_catalog.SQLiteCatalogBackend.begin_write', side_effect=AssertionError('no write')):
                closed = self.command(child, 'Cancel') if event == 'cancel' else self.form(child, 'close')
            self.assertEqual(closed['form']['result']['state']['kind'], 'closed')
            self.assertEqual(self.broker.applications[owner].customer, self.refs['C001'])
            self.assertFalse(self.form(owner)['form']['result']['state']['dirty'])
        self.assertEqual(self.read_order(), before)

    def test_owner_is_blocked_for_changes_close_save_and_new_selection(self):
        owner = self.open()['session']; child = self.choice(owner)
        for event, fields in [('change', {'control': 'FieldDescription', 'value': {'type': 'String', 'value': 'injected'}}),
                ('close', {}), ('command', {'control': 'SaveOrderButton'}),
                ('command', {'control': 'ChooseCustomerButton'})]:
            response = self.form(owner, event, **fields)
            self.assertEqual(response['error'], 'owner_blocked')
            self.assertIn(child, self.controller.sessions)
        self.assertEqual(item(self.form(owner), 'FieldDescription')['value']['value'], 'First order')

    def test_server_rejects_raw_owner_call_or_delta_during_choice(self):
        owner = self.open()['session']; self.choice(owner)
        base = {'protocol': 'yadinassi-form/1', 'id': 99, 'operation': 'call', 'revision': 1,
                'sequence': 2, 'endpoint': 4, 'arguments': [], 'delta': None}
        with self.assertRaises(ValueError):
            self.broker.exchange({'operation': 'form', 'session': owner, 'payload': base})
        with self.assertRaises(ValueError):
            self.broker.exchange({'operation': 'form', 'session': owner, 'payload': dict(base, endpoint=APPLY_CHOICE_ENDPOINT)})

    def test_one_owner_capacity_and_idempotent_open_retired_session(self):
        opened = self.open(token='same'); owner = opened['session']
        self.assertEqual(self.open(token='same')['session'], owner)
        self.assertEqual(self.rpc('open', {'revision': 1, 'row': None, 'request': 'second'})['error'], 'capacity')
        self.form(owner, 'close')
        self.assertEqual(self.rpc('open', {'revision': 1, 'row': 1, 'request': 'same'})['error'], 'retired_session')
        self.assertNotEqual(self.open()['session'], owner)

    def test_failed_owner_client_creation_retires_remote_without_replay(self):
        with mock.patch('yadinassi.ui.reference_orders_workspace.FormController', side_effect=ValueError('bad client')):
            result = self.rpc('open', {'revision': 1, 'row': 1, 'request': 'bad'})
        self.assertEqual(result['error'], 'open_failed')
        self.assertFalse(result['state']['uncertain'])
        self.assertEqual(self.broker.sessions, {})
        self.assertEqual(self.controller.sessions, {})
        self.assertEqual(self.open()['session'], 'form-2')

    def test_failed_child_registration_locks_owner_without_replaying_choice(self):
        owner = self.open()['session']
        with mock.patch('yadinassi.ui.reference_orders_workspace.FormController', side_effect=ValueError('bad client')):
            result = self.command(owner, 'ChooseCustomer')
        self.assertTrue(result['state']['uncertain'])
        self.assertEqual(len(self.broker.sessions), 2)
        count = self.controller.counter
        self.assertEqual(self.form(owner)['error'], 'outcome_unknown')
        self.assertEqual(self.controller.counter, count)

    def test_lifetime_choice_capacity_is_known_without_allocating_or_locking(self):
        self.broker.allocated = 254
        owner = self.open()['session']
        app = self.broker.applications[owner]
        self.assertEqual(app.choice_limit, 1)
        self.command(self.choice(owner), 'Cancel')
        result = self.command(owner, 'ChooseCustomer')
        self.assertFalse(result['state']['uncertain'])
        self.assertEqual(len(result['state']['sessions']), 1)
        self.assertIn('Selection limit reached', item(result, 'FieldStatus')['value']['value'])
        self.assertIsNone(app.active_choice)

    def test_stale_list_revision_and_bool_row_are_rejected(self):
        self.rpc('list', {'code': ''})
        self.assertEqual(self.rpc('open', {'revision': 1, 'row': 1, 'request': 'stale'})['error'], 'stale_list')
        with self.assertRaises(ValueError):
            self.rpc('open', {'revision': 2, 'row': True, 'request': 'bool'})
        self.assertEqual(self.broker.sessions, {})

    def test_search_replaces_mapping_and_old_row_is_not_selectable(self):
        owner = self.open()['session']; child = self.choice(owner)
        old = item(self.form(child), 'ChoicesTable')['rows'][0]['id']
        self.change(child, 'SearchCode', 'C002'); result = self.command(child, 'SearchChoices')
        self.assertEqual(len(item(result, 'ChoicesTable')['rows']), 1)
        stale = self.form(child, 'select', control='ChoicesTable', row=old)
        self.assertEqual(stale['form']['result']['error'], 'event_failed')
        refused = self.command(child, 'Choose')
        self.assertIn(child, self.controller.sessions)
        self.assertIn('Select a record', item(refused, 'FieldStatus')['value']['value'])

    def test_deleted_choice_is_rechecked_and_refused_without_owner_mutation(self):
        owner = self.open()['session']; child = self.choice(owner)
        self.mutate_catalog('C002', 'Customers', 'DeletionMark', True)
        refused = self.select(child, 'C002')
        self.assertIn('no longer available', item(refused, 'FieldStatus')['value']['value'])
        self.assertIn(child, self.controller.sessions)
        self.assertEqual(self.broker.applications[owner].customer, self.refs['C001'])

    def test_typed_result_rechecked_at_apply_and_wrong_catalog_cannot_inject(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[child]
        app.finished, app.result = True, self.refs['P002']
        self.form(child)
        self.assertEqual(self.broker.applications[owner].customer, self.refs['C001'])
        self.assertIn('could not be applied', item(self.form(owner), 'FieldStatus')['value']['value'])

    def test_wrong_database_key_cannot_inject(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[child]
        app.finished, app.result = True, replace(self.refs['C002'], database_id=uuid4())
        self.form(child)
        self.assertEqual(self.broker.applications[owner].customer, self.refs['C001'])

    def test_capability_is_identity_based_and_one_shot(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[owner]; ticket = app.active_choice
        with self.assertRaises(ValueError):
            app.stage_result(replace(ticket), self.refs['C002'])
        with self.assertRaises(TypeError):
            app.stage_result(ticket, {'record': str(self.refs['C002'].record_id)})
        self.command(child, 'Cancel')
        with self.assertRaises(ValueError):
            app.stage_result(ticket, self.refs['C002'])
        self.assertEqual(self.rpc('form', {'session': child, 'request': {}})['error'], 'retired_session')

    def test_stale_generation_result_is_retired_without_reference_change(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[owner]; app.generation += 1
        self.select(child, 'C002')
        self.assertEqual(app.customer, self.refs['C001'])
        self.assertIsNone(app.active_choice)

    def test_deleted_owner_row_result_cannot_retarget_neighbor(self):
        owner = self.open()['session']; child = self.choice(owner, 'Product')
        app = self.broker.applications[owner]; row = app.active_choice.row
        table = self.broker.sessions[owner][0].session.form._tables['lines']
        table._replace_rows((), table._allocated)
        self.select(child, 'P002')
        self.assertEqual(app.products[row], self.refs['P001'])
        self.assertIsNone(app.active_choice)

    def test_apply_preflight_failure_keeps_old_reference_and_no_false_mutation(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[owner]
        with mock.patch.object(app, '_preflight', side_effect=ValueError('projection rejected')):
            closed = self.select(child, 'C002')
        self.assertFalse(closed['state']['uncertain'])
        self.assertEqual(app.customer, self.refs['C001'])
        self.assertFalse(self.form(owner)['form']['result']['state']['dirty'])

    def test_apply_install_fault_locks_workspace_and_never_claims_old_reference_kept(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[owner]; install = app._install
        def broken(session, prepared):
            install(session, prepared)
            raise RuntimeError('fault after installation')
        with mock.patch.object(app, '_install', side_effect=broken):
            failed = self.select(child, 'C002')
        self.assertTrue(failed['state']['uncertain'])
        self.assertIn(child, self.controller.sessions)
        self.assertNotIn('previous reference were kept', self.broker.sessions[owner][0].session.form._data['status'])
        self.assertTrue(all(c.session.uncertain for c, _ in self.controller.sessions.values()))

    def test_postinstall_lock_fault_is_uncertain_not_replayed(self):
        owner = self.open()['session']; child = self.choice(owner)
        app = self.broker.applications[owner]
        with mock.patch.object(app, '_locked', side_effect=RuntimeError('postcommit lock')):
            failed = self.select(child, 'C002')
        self.assertTrue(failed['state']['uncertain'])
        self.assertEqual(app.customer, self.refs['C002'])
        calls = self.controller.counter
        self.assertEqual(self.rpc('list', {'code': ''})['error'], 'outcome_unknown')
        self.assertEqual(self.controller.counter, calls)

    def test_lost_transport_locks_owner_child_and_has_no_automatic_replay(self):
        owner = self.open()['session']; child = self.choice(owner)
        self.controller.transport = lambda raw: b'{}\n'
        failed = self.command(child, 'Cancel')
        self.assertTrue(failed['state']['uncertain'])
        self.assertEqual(len(self.controller.sessions), 2)
        counter = self.controller.counter
        self.assertEqual(self.rpc('close', {})['error'], 'outcome_unknown')
        self.assertEqual(self.controller.counter, counter)

    def test_uncertain_child_retirement_keeps_both_sessions_locked(self):
        owner = self.open()['session']; child = self.choice(owner)
        original = self.broker.exchange
        def fail(packet):
            if packet['operation'] == 'retire':
                original(packet)
                raise RuntimeError('lost cleanup acknowledgement')
            return original(packet)
        with mock.patch.object(self.broker, 'exchange', side_effect=fail):
            failed = self.command(child, 'Cancel')
        self.assertTrue(failed['state']['uncertain'])
        self.assertIn(child, self.controller.sessions)
        self.assertNotIn(child, self.broker.sessions)

    def test_save_same_identity_and_unchanged_save_never_writes_twice(self):
        owner = self.open()['session']; app = self.broker.applications[owner]
        self.change(owner, 'Code', 'RENAMED'); self.change(owner, 'Description', 'Edited')
        self.command(owner, 'SaveOrder')
        saved = self.read_order('RENAMED')
        self.assertEqual(saved[0], self.refs['O001'])
        with mock.patch.object(app.context.backend, 'begin_write', side_effect=AssertionError('duplicate')) as writes:
            result = self.command(owner, 'SaveOrder')
        writes.assert_not_called()
        self.assertFalse(result['form']['result']['state']['dirty'])
        self.assertIn('No changes', item(result, 'FieldStatus')['value']['value'])

    def test_create_save_reopen_preserves_exact_header_and_line_reference_keys(self):
        owner = self.open(row=None)['session']
        self.change(owner, 'Code', 'NEW'); self.change(owner, 'Description', 'New reference order')
        self.select(self.choice(owner), 'C002')
        self.command(owner, 'AddLine'); self.select(self.choice(owner, 'Product'), 'P002')
        saved = self.command(owner, 'SaveOrder')
        self.assertFalse(saved['form']['result']['state']['dirty'])
        record = self.read_order('NEW')
        self.assertEqual(record[1][0], self.refs['C002']); self.assertEqual(record[2][0].values[0], self.refs['P002'])
        self.form(owner, 'close'); listing = self.rpc('list', {'code': 'NEW'})
        reopened = self.open(row=listing['state']['orders'][0]['id'])
        app = self.broker.applications[reopened['session']]
        self.assertEqual(app.object._key, record[0]); self.assertEqual(app.customer, self.refs['C002'])
        self.assertEqual(tuple(app.products.values()), (self.refs['P002'],))

    def test_new_order_discard_has_no_write_and_can_close(self):
        owner = self.open(row=None)['session']; self.change(owner, 'Description', 'Draft')
        self.assertEqual(self.form(owner, 'close')['form']['result']['state']['kind'], 'form')
        app = self.broker.applications[owner]
        with mock.patch.object(app.context.backend, 'begin_write', side_effect=AssertionError('no write')):
            discarded = self.command(owner, 'Discard')
        self.assertFalse(discarded['form']['result']['state']['dirty'])
        self.assertEqual(self.form(owner, 'close')['form']['result']['state']['kind'], 'closed')

    def test_save_rechecks_deleted_references_without_retargeting(self):
        owner = self.open()['session']; self.change(owner, 'Description', 'Draft')
        self.mutate_catalog('P001', 'Products', 'DeletionMark', True)
        result = self.command(owner, 'SaveOrder')
        self.assertTrue(result['form']['result']['state']['dirty'])
        self.assertIn('live product', item(result, 'FieldStatus')['value']['value'])
        self.assertEqual(self.broker.applications[owner].object._key, self.refs['O001'])

    def test_concurrent_writer_conflict_preserves_draft_and_reload_adopts_winner(self):
        owner = self.open()['session']; self.change(owner, 'Description', 'My draft')
        self.mutate_catalog('O001', 'Orders', 'Description', 'Concurrent winner')
        result = self.command(owner, 'SaveOrder')
        self.assertIn('conflict', item(result, 'FieldStatus')['value']['value'])
        self.assertEqual(item(result, 'FieldDescription')['value']['value'], 'My draft')
        result = self.command(owner, 'Discard')
        self.assertEqual(item(result, 'FieldDescription')['value']['value'], 'Concurrent winner')
        self.assertFalse(result['form']['result']['state']['dirty'])

    def test_known_commit_failed_refresh_resolves_without_another_write(self):
        owner = self.open()['session']; app = self.broker.applications[owner]
        self.change(owner, 'Description', 'Known committed')
        with mock.patch.object(app, '_fresh', side_effect=BackendError('busy')):
            self.command(owner, 'SaveOrder')
        self.assertTrue(app.pending_refresh)
        with mock.patch.object(app.context.backend, 'begin_write', side_effect=AssertionError('refresh only')):
            result = self.command(owner, 'Resolve')
        self.assertFalse(app.pending_refresh); self.assertFalse(result['form']['result']['state']['dirty'])
        self.assertEqual(app.customer, self.refs['C001'])

    def test_uncertain_commit_resolves_exact_retained_receipt_and_keys(self):
        from yadinassi.sqlite_catalog import _View
        owner = self.open()['session']; app = self.broker.applications[owner]
        self.select(self.choice(owner), 'C002'); self.change(owner, 'Description', 'Retained intent')
        commit = _View.commit
        def lost(tx):
            commit(tx); raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', lost):
            self.command(owner, 'SaveOrder')
        self.assertTrue(app.pending_commit)
        intent = app.object._pending_write
        self.assertIsNotNone(intent)
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('never duplicate')):
            result = self.command(owner, 'Resolve')
        self.assertFalse(app.pending_commit); self.assertFalse(result['form']['result']['state']['dirty'])
        self.assertEqual(self.read_order()[1][0], self.refs['C002'])

    def test_absent_receipt_retries_only_retained_reference_intent(self):
        from yadinassi.sqlite_catalog import _View
        owner = self.open()['session']; app = self.broker.applications[owner]
        self.select(self.choice(owner), 'C002')
        with mock.patch.object(_View, 'commit', side_effect=BackendError('uncertain_commit')):
            self.command(owner, 'SaveOrder')
        draft, expected, operation = app.object._pending_write
        self.assertEqual(draft.key, self.refs['O001'])
        with mock.patch.object(app.context.backend, 'begin_write', wraps=app.context.backend.begin_write) as writes:
            self.command(owner, 'Resolve')
        self.assertEqual(writes.call_args_list, [mock.call(operation)])
        self.assertEqual(self.read_order()[1][0], self.refs['C002'])

    def test_product_choice_without_selected_row_does_not_allocate_child(self):
        owner = self.open()['session']; result = self.command(owner, 'ChooseProduct')
        self.assertEqual(len(result['state']['sessions']), 1)
        self.assertIn('Select an order line', item(result, 'FieldStatus')['value']['value'])

    def test_workspace_close_requires_explicit_owner_and_child_close(self):
        owner = self.open()['session']; child = self.choice(owner)
        self.assertEqual(self.rpc('close', {})['error'], 'forms_open')
        self.form(child, 'close'); self.form(owner, 'close')
        self.assertEqual(self.rpc('close', {})['state']['kind'], 'closed')

    def test_real_owned_process_choice_save_and_readback(self):
        process = ReferenceWorkspaceProcess(FORMS, self.path); self.addCleanup(process.close)
        self.assertNotEqual(process.child.pid, os.getpid())
        self.controller = ReferenceWorkspaceController(FORMS, process.exchange)
        self.rpc('hello', {'protocol': PROTOCOL})
        owner = self.open()['session']; self.select(self.choice(owner), 'C002')
        self.command(owner, 'SaveOrder')
        self.assertEqual(self.read_order()[1][0], self.refs['C002'])

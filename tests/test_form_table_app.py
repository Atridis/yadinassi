"""Real fixed-table form intake and SQLite, not native managed-form evidence."""
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.database_context import SQLiteDBContext
from yadinassi.form_replication import ReplicatedFormServer
from yadinassi.ui.form_app import FormController, FormProcess, PROTOCOL
from yadinassi.ui.form_package import load_client, load_server
from yadinassi.ui.protocol import encode_line

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/forms/order-intake'


def request(method='hello', **params):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'form.' + method,
            'params': {'protocol': PROTOCOL} if method == 'hello' else params}


def state(controller, method='hello', **params):
    return controller.exchange(request(method, **params))['result']


def event(controller, event='command', control='SaveOrderButton', **params):
    args = {'event': event, 'revision': controller.session.revision, **params}
    if event != 'close':
        args['control'] = control
    return state(controller, 'event', **args)


def item(result, name):
    return next(value for value in result['state']['items'] if value['name'] == name)


def scalar(value):
    return {'type': 'Number', 'value': str(value)} if isinstance(value, Decimal) else {
        'type': 'String', 'value': value}


def table(result):
    return item(result, 'LinesTable')


def row_values(result, row_id):
    grid = table(result)
    row = next(row for row in grid['rows'] if row['id'] == row_id)
    return {column['name']: value for column, value in zip(grid['columns'], row['values'])}


def pair(context):
    package = load_server(EXAMPLE)
    server = ReplicatedFormServer(package.source, package.endpoints,
        handlers=package.handlers, attributes=package.attributes, tables=package.tables,
        initial_values=package.initial_values, bindings=package.lifecycle,
        database_context=context)
    return FormController(load_client(EXAMPLE), server.exchange), server


class IntakeHelpers:
    def good(self, result):
        self.assertIsNone(result['error'], result)
        return result

    def header(self, controller, code='O001', description='Owned order'):
        for name, value in [('Code', code), ('Description', description)]:
            self.good(event(controller, 'change', 'Field' + name, value=scalar(value)))

    def cell(self, controller, row, column, value):
        return event(controller, 'cell', 'LinesTable', row=row, column=column,
                     value=scalar(value))

    def line(self, controller, description='First line', quantity='1.25', price='2.35'):
        added = self.good(event(controller, control='AddLineButton'))
        row = table(added)['currentRow']
        self.assertIs(type(row), int)
        for column, value in [('Description', description),
                              ('Quantity', Decimal(quantity)), ('Price', Decimal(price))]:
            self.good(self.cell(controller, row, column, value))
        return row

    def form_values(self, controller):
        return dict(controller.session.snapshot().attributes)

    def assert_locked(self, result):
        for name in ('FieldCode', 'FieldDescription', 'LinesTable'):
            self.assertTrue(item(result, name)['readOnly'])
        for name in ('AddLineButton', 'DeleteLineButton', 'RecalculateButton', 'SaveOrderButton'):
            self.assertFalse(item(result, name)['enabled'])

    def readback(self, path, code='O001'):
        """A fresh database context, not the form's database/interpreter/object."""
        with SQLiteDBContext(path) as context:
            vm = Interpreter(database_context=context)
            try:
                vm.execute('O=Catalogs.Orders.FindByCode("' + code + '").GetObject();')
                header = tuple(vm.execute('O.' + name) for name in ('Code', 'Description', 'Total'))
                count = int(vm.execute('O.Lines.Count()'))
                rows = tuple(tuple(vm.execute('O.Lines.Get(' + str(index) + ').' + column)
                                   for column in ('ItemDescription', 'Quantity', 'Price', 'Amount'))
                             for index in range(count))
                vm.execute('N=0; S=Catalogs.Orders.Select(); While S.Next() Do N=N+1; EndDo;')
                return header, rows, vm.execute('N')
            finally:
                vm.close()


class FormTablePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        shutil.copytree(EXAMPLE, self.directory, dirs_exist_ok=True)

    def edit(self, change):
        path = self.directory / 'server.json'
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def test_four_file_v1_package_and_frozen_server_schema(self):
        client, server = load_client(self.directory), load_server(self.directory)
        self.assertEqual(server.endpoints, {1: 'AddLine', 2: 'DeleteLine',
                                           3: 'Recalculate', 4: 'SaveOrder'})
        self.assertEqual([b.name for b in client.bindings],
                         ['RemoteAdd', 'RemoteDelete', 'RemoteRecalculate', 'RemoteSave'])
        self.assertNotIn('&AtServer', client.source)
        self.assertNotIn('&AtClient', server.source)
        self.assertEqual(len(server.tables), 1)
        schema = server.tables[0]
        self.assertEqual(schema.name, 'Lines')
        self.assertEqual([c.name for c in schema.columns],
                         ['Description', 'Quantity', 'Price', 'Amount'])
        self.assertEqual([c.read_only for c in schema.columns], [False, False, False, True])
        self.assertEqual(schema.columns[1].value_type.number_qualifiers.digits, Decimal(0))
        with self.assertRaises(AttributeError):
            schema.name = 'Changed'

    def test_authored_configuration_has_exact_header_and_storage_columns(self):
        configuration = load_configuration_directory(self.directory / 'configuration')
        self.assertEqual(configuration.activation_issues, ())
        self.assertEqual(len(configuration.catalogs), 1)
        orders = configuration.catalogs[0]
        self.assertEqual(orders.name, 'Orders')
        self.assertEqual([f.name for f in orders.fields], ['Total'])
        self.assertEqual(orders.fields[0].qualifiers, (18, 2, 'Any'))
        self.assertEqual([s.name for s in orders.tabular_sections], ['Lines'])
        fields = orders.tabular_sections[0].fields
        self.assertEqual([f.name for f in fields], ['ItemDescription', 'Quantity', 'Price', 'Amount'])
        self.assertEqual(fields[0].qualifiers, (128,))
        self.assertEqual([f.qualifiers for f in fields[1:]], [(18, 2, 'Any')] * 3)

    def test_client_never_needs_server_files_or_configuration(self):
        for name in ('server.json', 'server.bsl'):
            (self.directory / name).unlink()
        shutil.rmtree(self.directory / 'configuration')
        self.assertEqual(len(load_client(self.directory).bindings), 4)

    def test_server_never_needs_client_files(self):
        for name in ('client.json', 'client.bsl'):
            (self.directory / name).unlink()
        self.assertEqual(len(load_server(self.directory).tables), 1)

    def test_closed_table_manifest_rejects_unknown_types_flags_and_shapes(self):
        original = (self.directory / 'server.json').read_text()
        changes = [
            lambda x: x['tables'][0].update(rows=[]),
            lambda x: x['tables'][0]['columns'][0].update(type='CatalogRef'),
            lambda x: x['tables'][0]['columns'][0].update(readOnly=1),
            lambda x: x['tables'][0]['columns'][0].update(qualifiers={'length': 8}),
            lambda x: x['tables'][0]['columns'][0].pop('title'),
            lambda x: x.update(tables={}),
            lambda x: x.update(protocol='yadinassi-form-app/0'),
        ]
        for change in changes:
            (self.directory / 'server.json').write_text(original)
            self.edit(change)
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                load_server(self.directory)

    def test_case_insensitive_schema_namespace_and_inventory_limits(self):
        original = (self.directory / 'server.json').read_text()
        changes = [
            lambda x: x['tables'].append(x['tables'][0]),
            lambda x: x['tables'][0].update(name='cOdE'),
            lambda x: x['tables'][0]['columns'].append(dict(x['tables'][0]['columns'][0], name='description')),
            lambda x: x['tables'][0].update(columns=[dict(x['tables'][0]['columns'][0], name='C' + str(i)) for i in range(9)]),
            lambda x: x.update(tables=[dict(x['tables'][0], name='T' + str(i)) for i in range(5)]),
        ]
        for change in changes:
            (self.directory / 'server.json').write_text(original)
            self.edit(change)
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                load_server(self.directory)


class FormTableControllerTests(IntakeHelpers, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'orders.sqlite'
        self.context = SQLiteDBContext.create(self.path,
            load_configuration_directory(EXAMPLE / 'configuration'))
        self.addCleanup(self.context.close)
        self.controller, self.server = pair(self.context)
        self.opened = self.good(state(self.controller))

    def test_bootstrap_projects_closed_table_without_private_source(self):
        grid = table(self.opened)
        self.assertEqual(set(grid), {'name', 'kind', 'title', 'visible', 'enabled',
                                    'readOnly', 'controlId', 'tableId', 'columns', 'rows', 'currentRow'})
        self.assertEqual(grid['kind'], 'table')
        self.assertGreater(grid['tableId'], 0)
        self.assertGreater(grid['controlId'], 0)
        self.assertEqual(grid['rows'], [])
        self.assertIsNone(grid['currentRow'])
        self.assertEqual(len(grid['columns']), 4)
        self.assertTrue(grid['columns'][3]['readOnly'])
        raw = encode_line(self.opened)
        for private in (b'Procedure', b'endpoint', b'client.bsl', b'server.bsl', b'orders.sqlite'):
            self.assertNotIn(private, raw)
        self.assertIsNone(self.controller.session.interpreter.database_context)

    def test_cell_change_is_local_dirty_and_recalculate_crosses_barrier(self):
        first = self.line(self.controller)
        before = self.server.session.snapshot()
        sequence = self.controller.session.client_sequence
        changed = self.good(self.cell(self.controller, first, 'Price', Decimal('3.10')))
        self.assertEqual(self.server.session.snapshot(), before)
        self.assertEqual(self.controller.session.client_sequence, sequence)
        self.assertTrue(self.form_values(self.controller)['Dirty'])
        self.assertEqual(row_values(changed, first)['Price'], scalar(Decimal('3.10')))
        result = self.good(event(self.controller, control='RecalculateButton'))
        self.assertEqual(row_values(result, first)['Amount'], scalar(Decimal('3.88')))
        self.assertEqual(item(result, 'FieldTotal')['value'], scalar(Decimal('3.88')))
        self.assertTrue(self.form_values(self.controller)['Dirty'])
        self.assertGreater(self.controller.session.client_sequence, sequence)

    def test_add_select_edit_delete_and_monotonic_ordered_identities(self):
        first = self.line(self.controller, 'Keep first')
        middle = self.line(self.controller, 'Remove middle')
        last = self.line(self.controller, 'Keep last')
        self.assertLess(first, middle)
        self.assertLess(middle, last)
        selected = self.good(event(self.controller, 'select', 'LinesTable', row=first))
        self.assertEqual(table(selected)['currentRow'], first)
        edited = self.good(self.cell(self.controller, middle, 'Price', Decimal('9')))
        self.assertEqual(table(edited)['currentRow'], middle)
        deleted = self.good(event(self.controller, control='DeleteLineButton'))
        self.assertEqual([r['id'] for r in table(deleted)['rows']], [first, last])
        self.assertIsNone(table(deleted)['currentRow'])
        fourth = self.line(self.controller, 'Appended')
        self.assertGreater(fourth, last)
        failed = self.cell(self.controller, middle, 'Price', Decimal('1'))
        self.assertEqual(failed['error'], 'event_failed')
        self.assertEqual([r['id'] for r in table(failed)['rows']], [first, last, fourth])

    def test_selection_without_change_does_not_mark_clean_form_dirty(self):
        self.good(event(self.controller, 'select', 'LinesTable', row=None))
        self.assertFalse(self.form_values(self.controller)['Dirty'])
        first = self.line(self.controller, 'First')
        self.line(self.controller, 'Second')
        calculated = self.good(event(self.controller, control='RecalculateButton'))
        selected = self.good(event(self.controller, 'select', 'LinesTable', row=first))
        self.assertEqual(table(selected)['currentRow'], first)
        # Changed would replace this status with the local unsaved-changes text.
        self.assertEqual(item(selected, 'FieldStatus')['value'],
                         item(calculated, 'FieldStatus')['value'])

    def test_delete_without_selection_is_recoverable_and_preserves_rows(self):
        first = self.line(self.controller)
        self.good(event(self.controller, 'select', 'LinesTable', row=None))
        result = event(self.controller, control='DeleteLineButton')
        self.assertEqual(result['error'], 'event_failed')
        self.assertEqual([r['id'] for r in table(result)['rows']], [first])
        self.assertIn('Select a line', item(result, 'FieldStatus')['value']['value'])
        self.assertTrue(item(result, 'DeleteLineButton')['enabled'])

    def test_readonly_column_unknown_row_column_and_wrong_control_reject(self):
        first = self.line(self.controller)
        for control, row, column in [('LinesTable', first, 'Amount'),
                ('LinesTable', first + 100, 'Price'), ('LinesTable', first, 'Missing'),
                ('FieldCode', first, 'Price')]:
            result = event(self.controller, 'cell', control, row=row, column=column,
                           value=scalar(Decimal('999')))
            self.assertEqual(result['error'], 'event_failed')
        self.assertEqual(row_values(result, first)['Amount'], scalar(Decimal('0')))
        self.assertEqual(event(self.controller, 'select', 'LinesTable', row=first + 100)['error'], 'event_failed')

    def test_exact_event_admission_rejects_boolean_ids_and_extra_capabilities(self):
        first = self.line(self.controller)
        cases = [dict(row=True, column='Price', value=scalar(Decimal('1'))),
                 dict(row=first, column='Price', value={'type': 'Number', 'value': 1.2}),
                 dict(row=first, column='Price', value=scalar(Decimal('1')), endpoint=4),
                 dict(row=first, column='Price', value=scalar(Decimal('1')), tableId=1)]
        before = self.controller.session.client_sequence
        for params in cases:
            with self.subTest(params=params), self.assertRaises(ValueError):
                event(self.controller, 'cell', 'LinesTable', **params)
        self.assertEqual(self.controller.session.client_sequence, before)

    def test_stale_structural_command_and_repeat_hello_never_replay(self):
        revision = self.controller.session.revision
        added = self.good(event(self.controller, control='AddLineButton'))
        sequence = self.controller.session.client_sequence
        duplicate = state(self.controller, 'event', event='command', revision=revision,
                          control='AddLineButton')
        self.assertEqual(duplicate['error'], 'stale_revision')
        self.assertEqual(table(duplicate)['rows'], table(added)['rows'])
        self.assertEqual(table(state(self.controller))['rows'], table(added)['rows'])
        self.assertEqual(self.controller.session.client_sequence, sequence)

    def test_validation_before_write_lock_allows_fixing_inputs(self):
        self.header(self.controller)
        empty = event(self.controller)
        self.assertEqual(empty['error'], 'event_failed')
        first = self.line(self.controller)
        bad_values = [('Description', ' '), ('Description', 'x' * 129),
                      ('Quantity', Decimal('0')), ('Quantity', Decimal('-1')),
                      ('Quantity', Decimal('0.001')), ('Quantity', Decimal('1000001')),
                      ('Price', Decimal('-1')), ('Price', Decimal('0.001')),
                      ('Price', Decimal('1000001'))]
        defaults = {'Description': 'First line', 'Quantity': Decimal('1.25'), 'Price': Decimal('2.35')}
        with mock.patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('unexpected write')) as writes:
            for column, bad in bad_values:
                self.good(self.cell(self.controller, first, column, bad))
                result = event(self.controller)
                self.assertEqual(result['error'], 'event_failed')
                self.assertFalse(self.form_values(self.controller)['SaveAttempted'])
                self.assertFalse(table(result)['readOnly'])
                self.assertTrue(item(result, 'SaveOrderButton')['enabled'])
                self.good(self.cell(self.controller, first, column, defaults[column]))
            writes.assert_not_called()
        saved = self.good(event(self.controller))
        self.assert_locked(saved)
        self.assertTrue(self.form_values(self.controller)['Saved'])
        self.assertFalse(self.form_values(self.controller)['Dirty'])

    def test_header_validation_and_duplicate_code_are_recoverable(self):
        self.line(self.controller)
        for code, description in [('', 'Order'), (' ', 'Order'), ('123456789', 'Order'),
                                  ('O001', ''), ('O001', ' '), ('O001', 'x' * 65)]:
            self.header(self.controller, code, description)
            result = event(self.controller)
            self.assertEqual(result['error'], 'event_failed')
            self.assertFalse(self.form_values(self.controller)['SaveAttempted'])
        vm = Interpreter(database_context=self.context)
        vm.execute('O=Catalogs.Orders.CreateItem(); O.Code="EXISTS"; O.Write();')
        vm.close()
        self.header(self.controller, 'EXISTS')
        result = event(self.controller)
        self.assertEqual(result['error'], 'event_failed')
        self.assertIn('already exists', item(result, 'FieldStatus')['value']['value'])
        self.assertFalse(self.form_values(self.controller)['SaveAttempted'])
        self.header(self.controller, 'O001')
        self.good(event(self.controller))

    def test_failed_recalculation_keeps_previous_totals_and_close_cancels(self):
        first = self.line(self.controller)
        previous = self.good(event(self.controller, control='RecalculateButton'))
        self.good(self.cell(self.controller, first, 'Price', Decimal('-1')))
        failed = event(self.controller, control='RecalculateButton')
        self.assertEqual(failed['error'], 'event_failed')
        self.assertEqual(item(failed, 'FieldTotal')['value'], item(previous, 'FieldTotal')['value'])
        self.assertEqual(row_values(failed, first)['Amount'], row_values(previous, first)['Amount'])
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'form')
        self.assertFalse(self.server.session.closed)

    def test_known_write_failure_locks_save_and_editing_without_retry(self):
        self.header(self.controller)
        first = self.line(self.controller)
        with mock.patch.object(self.context.backend, 'begin_write', side_effect=BackendError('storage_error')) as writes:
            failed = event(self.controller)
            self.assertEqual(failed['error'], 'event_failed')
            self.assertFalse(failed['state']['uncertain'])
            self.assert_locked(failed)
            self.assertTrue(self.form_values(self.controller)['SaveAttempted'])
            self.assertFalse(self.form_values(self.controller)['Saved'])
            self.assertEqual(event(self.controller)['error'], 'event_failed')
            self.assertEqual(self.cell(self.controller, first, 'Price', Decimal('8'))['error'], 'event_failed')
            self.assertEqual(event(self.controller, 'change', 'FieldCode', value=scalar('O002'))['error'], 'event_failed')
            self.assertEqual(event(self.controller, 'close')['state']['kind'], 'form')
            writes.assert_called_once()

    def test_known_error_after_actual_sql_commit_retains_lock_and_single_record(self):
        self.header(self.controller)
        self.line(self.controller)
        original = self.context.backend.begin_write
        commits = []

        class LostCommitResult:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def execute(self, sql, *args):
                result = self.connection.execute(sql, *args)
                if sql == 'COMMIT':
                    commits.append(sql)
                    raise sqlite3.OperationalError('private fault after committed order')
                return result

        def begin(operation):
            view = original(operation)
            view._connection = LostCommitResult(view._connection)
            return view

        with mock.patch.object(self.context.backend, 'begin_write', side_effect=begin):
            failed = event(self.controller)
        self.assertEqual(failed['error'], 'event_failed')
        self.assertFalse(failed['state']['uncertain'])
        self.assert_locked(failed)
        self.assertTrue(self.form_values(self.controller)['SaveAttempted'])
        self.assertFalse(self.form_values(self.controller)['Saved'])
        sequence = self.controller.session.client_sequence
        self.assertEqual(event(self.controller)['error'], 'event_failed')
        self.assertEqual(self.controller.session.client_sequence, sequence)
        self.assertEqual(commits, ['COMMIT'])
        self.assertNotIn(b'private fault', encode_line(failed))
        self.context.close()
        header, rows, count = self.readback(self.path)
        self.assertEqual(header, ('O001', 'Owned order', Decimal('2.94')))
        self.assertEqual(rows, (('First line', Decimal('1.25'), Decimal('2.35'), Decimal('2.94')),))
        self.assertEqual(count, Decimal(1))


class FormTableProcessTests(IntakeHelpers, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'orders.sqlite'
        with SQLiteDBContext.create(self.path,
                load_configuration_directory(EXAMPLE / 'configuration')):
            pass
        self.process = FormProcess(EXAMPLE, self.path)
        self.addCleanup(self.process.close)
        self.controller = FormController(load_client(EXAMPLE), self.process.exchange)
        self.good(state(self.controller))

    def test_real_child_edit_select_delete_recalculate_save_close_reopen_exact_order(self):
        self.assertNotEqual(self.process.child.pid, os.getpid())
        self.assertIsNone(self.controller.session.interpreter.database_context)
        self.header(self.controller)
        first = self.line(self.controller, 'Cable', '1.25', '2.30')
        removed = self.line(self.controller, 'Remove me', '9', '9')
        last = self.line(self.controller, 'Service', '2', '3.10')
        self.good(event(self.controller, 'select', 'LinesTable', row=removed))
        deleted = self.good(event(self.controller, control='DeleteLineButton'))
        self.assertEqual([r['id'] for r in table(deleted)['rows']], [first, last])
        calculated = self.good(event(self.controller, control='RecalculateButton'))
        self.assertEqual(Decimal(item(calculated, 'FieldTotal')['value']['value']), Decimal('9.08'))
        self.good(self.cell(self.controller, first, 'Price', Decimal('2.35')))
        # Save must recalculate from the final edit, not trust the displayed old total.
        saved = self.good(event(self.controller))
        self.assertEqual(Decimal(item(saved, 'FieldTotal')['value']['value']), Decimal('9.14'))
        self.assert_locked(saved)
        self.assertTrue(self.form_values(self.controller)['Saved'])
        self.assertFalse(self.form_values(self.controller)['Dirty'])
        counter = self.process.counter
        self.assertEqual(event(self.controller)['error'], 'event_failed')
        self.assertEqual(self.process.counter, counter)
        closed = self.good(event(self.controller, 'close'))
        self.assertEqual(closed['state']['kind'], 'closed')
        self.process.close()
        self.assertIsNotNone(self.process.child.poll())
        self.assertFalse(self.process._worker.is_alive())
        header, rows, count = self.readback(self.path)
        self.assertEqual(header, ('O001', 'Owned order', Decimal('9.14')))
        self.assertEqual(rows, (('Cable', Decimal('1.25'), Decimal('2.35'), Decimal('2.94')),
                                ('Service', Decimal('2'), Decimal('3.10'), Decimal('6.20'))))
        self.assertEqual(count, Decimal(1))

    def test_lost_response_after_real_child_save_locks_without_replay_or_duplicate(self):
        self.header(self.controller)
        self.line(self.controller)
        original = self.controller.session._exchange
        calls = []

        def lost(raw):
            calls.append(raw)
            original(raw)
            raise OSError('private response disappeared after real commit')

        self.controller.session._exchange = lost
        failed = event(self.controller)
        self.assertEqual(failed['error'], 'outcome_unknown')
        self.assertTrue(failed['state']['uncertain'])
        self.assertEqual(event(self.controller)['error'], 'outcome_unknown')
        self.assertTrue(state(self.controller, 'snapshot')['state']['uncertain'])
        self.assertEqual(len(calls), 1)
        self.assertNotIn(b'private response', encode_line(failed))
        self.process.close()
        header, rows, count = self.readback(self.path)
        self.assertEqual(header, ('O001', 'Owned order', Decimal('2.94')))
        self.assertEqual(rows, (('First line', Decimal('1.25'), Decimal('2.35'), Decimal('2.94')),))
        self.assertEqual(count, Decimal(1))

    def test_unsaved_close_cancels_and_host_teardown_leaves_no_record(self):
        self.header(self.controller)
        self.line(self.controller)
        closed = self.good(event(self.controller, 'close'))
        self.assertEqual(closed['state']['kind'], 'form')
        self.assertIsNone(self.process.child.poll())
        self.process.close()
        with SQLiteDBContext(self.path) as context:
            vm = Interpreter(database_context=context)
            try:
                self.assertTrue(vm.execute('Catalogs.Orders.FindByCode("O001").IsEmpty()'))
                vm.execute('S=Catalogs.Orders.Select();')
                self.assertFalse(vm.execute('S.Next()'))
            finally:
                vm.close()

    def test_untouched_empty_form_can_close_without_writing(self):
        closed = self.good(event(self.controller, 'close'))
        self.assertEqual(closed['state']['kind'], 'closed')
        self.process.close()
        with SQLiteDBContext(self.path) as context:
            vm = Interpreter(database_context=context)
            try:
                vm.execute('S=Catalogs.Orders.Select();')
                self.assertFalse(vm.execute('S.Next()'))
            finally:
                vm.close()

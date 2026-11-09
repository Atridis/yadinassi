"""Host byte-isolation and closed table-replica contracts, not native parity."""
from copy import deepcopy
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import BSLError
from yadinassi.dates import BSLDate
from yadinassi.form_model import BSLFormAttribute
from yadinassi.form_replication import (PROTOCOL, ReplicatedFormServer,
                                        ReplicatedFormSession)
from yadinassi.form_tables import FormTableColumn, FormTableSchema
from yadinassi.invocation import InvocationBinding, InvocationPort, InvocationServer
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.ui.protocol import decode_line, encode_line, encode_value

SCHEMA = FormTableSchema('Lines', (
    FormTableColumn('Label', BSLTypeDescription('String'), 'Description'),
    FormTableColumn('Qty', BSLTypeDescription('Number'), 'Quantity'),
    FormTableColumn('Amount', BSLTypeDescription('Number'), 'Amount', True)), 'Lines')
HANDLERS = (InvocationBinding('Changed', 1, ('Element',), False),
            InvocationBinding('RunCommand', 2, ('Command',), False))
REMOTE = InvocationBinding('RemoteWork', 1, ('Action',))
SERVER = '''&AtServer
Procedure Create(Cancel, StandardProcessing)
    T = Items.Add("Grid", Type("FormTable")); T.DataPath = "Lines";
    T.SetAction("OnChange", "Changed");
    R = Lines.Add(); R.Label = "first"; R.Qty = 2; R.Amount = 4;
    R = Lines.Add(); R.Label = "second"; R.Qty = 3; R.Amount = 6;
    F = Items.Add("StatusField", Type("FormField")); F.DataPath = "Status";
    C = Commands.Add("Run"); C.Action = "RunCommand";
    B = Items.Add("RunButton", Type("FormButton")); B.CommandName = "Run";
    // extra-create
EndProcedure
&AtServer
Function Work(Val Action)
    Calls = Calls + 1;
    If Action = "delete" Then
        Lines.Delete(Items.Grid.CurrentData);
    ElsIf Action = "fail" Then
        R = Lines.Get(0); R.Label = "known effect";
        R = Lines.Add(); R.Label = "added before error";
        Raise "private detail";
    Else
        Total = 0;
        For Each R In Lines Do R.Amount = R.Qty * 2; Total = Total + R.Amount; EndDo;
    EndIf;
    // extra-work
    Return Calls;
EndFunction
'''
COMMAND = 'Result = RemoteWork("sum"); Status = "after:" + String(Total);'
CLIENT = '''&AtClient
Procedure Changed(Element)
    Status = "edited";
EndProcedure
&AtClient
Procedure RunCommand(Command)
    %s
EndProcedure
''' % COMMAND


def attributes():
    return tuple(BSLFormAttribute(name, BSLTypeDescription(kind)) for name, kind in
                 (('Status', 'String'), ('Total', 'Number'), ('Calls', 'Number')))


def scalar_delta():
    return {'attributes': [], 'items': [], 'title': None, 'cells': [], 'selections': []}


class ReplicatedTableTests(unittest.TestCase):
    def pair(self, *, server_source=SERVER, client_source=CLIENT, tables=(SCHEMA,), exchange=None):
        server = ReplicatedFormServer(server_source, {1: 'Work'}, handlers=HANDLERS,
            attributes=attributes(), tables=tables, bindings={'OnCreateAtServer': 'Create'})
        requests = []; replies = []
        def transport(raw):
            self.assertIs(type(raw), bytes); requests.append(raw)
            reply = server.exchange(raw) if exchange is None else exchange(server, raw)
            self.assertIs(type(reply), bytes); replies.append(reply)
            return reply
        client = ReplicatedFormSession(client_source, transport, handlers=HANDLERS, bindings=(REMOTE,))
        return client, server, requests, replies

    def command(self, client):
        return client.dispatch('command', revision=client.revision, control='RunButton')

    def cell(self, client, row=1, column='Qty', value=Decimal('4.125')):
        return client.dispatch('cell', revision=client.revision, control='Grid', row=row, column=column, value=value)

    def request(self, server, delta, *, action='sum', revision=None):
        return {'protocol': PROTOCOL, 'id': server._last_id + 1, 'operation': 'call',
                'revision': server.session.revision if revision is None else revision,
                'sequence': server._sequence + 1, 'endpoint': 1,
                'arguments': [encode_value(action)], 'delta': delta}

    def reject_delta(self, server, delta, *, reason='invalid_delta', revision=None):
        before = server.session.snapshot()
        reply = decode_line(server.exchange(encode_line(self.request(server, delta, revision=revision))))
        self.assertFalse(reply['accepted']); self.assertEqual(reply['reason'], reason)
        self.assertEqual(server.session.snapshot(), before)
        return reply

    def tampered_call(self, mutate, *, client_source=CLIENT, server_source=SERVER):
        def exchange(server, raw):
            frame = decode_line(server.exchange(raw))
            if decode_line(raw)['operation'] == 'call': mutate(frame)
            return encode_line(frame)
        client, server, requests, replies = self.pair(exchange=exchange,
            client_source=client_source, server_source=server_source)
        client.open()
        before = client.snapshot()
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertTrue(client.uncertain)
        after = client.snapshot()
        self.assertEqual((after.tables, after.attributes, after.items, after.selections),
                         (before.tables, before.attributes, before.items, before.selections))
        return client, server, requests, replies

    def test_bootstrap_copies_schema_rows_and_controls_over_bytes(self):
        client, server, requests, replies = self.pair(); snapshot = client.open()
        self.assertEqual(snapshot.tables, server.session.snapshot().tables)
        self.assertEqual(snapshot.tables[0].columns, (('Label', 'Description', 'String', False),
            ('Qty', 'Quantity', 'Number', False), ('Amount', 'Amount', 'Number', True)))
        self.assertIsNot(client.form._tables['lines'], server.session.form._tables['lines'])
        self.assertIsNot(client.form._tables['lines']._rows[0], server.session.form._tables['lines']._rows[0])
        self.assertIsNot(client.form.items._values['grid'], server.session.form.items._values['grid'])
        self.assertEqual(decode_line(requests[0])['protocol'], 'yadinassi-form/1')
        state = decode_line(replies[0])['state']; self.assertEqual(state['tables'][0]['allocated'], 2)
        for raw in requests + replies:
            for forbidden in (b'&AtServer', b'EndFunction', b'__dict__', b'0x'):
                self.assertNotIn(forbidden, raw)

    def test_cell_edit_is_local_until_barrier_and_return_uses_flushed_value(self):
        client, server, requests, replies = self.pair(); before = client.open()
        edited = self.cell(client)
        self.assertEqual(len(requests), 1)
        self.assertEqual(server.session.snapshot().tables[0].rows[0][1][1], Decimal(2))
        after = self.command(client)
        self.assertEqual(after.tables[0].rows[0][1][2], Decimal('8.250'))
        self.assertEqual(dict(after.attributes)['Total'], Decimal('14.250'))
        self.assertEqual(dict(after.attributes)['Status'], 'after:14,25')
        delta = decode_line(requests[-1])['delta']
        self.assertEqual(delta['cells'], [[1, 1, 1, {'type': 'Number', 'value': '4.125'}]])
        self.assertEqual(len(delta['selections']), 1)
        self.assertEqual(before.tables[0].rows[0][1][1], Decimal(2))
        self.assertEqual(edited.tables[0].rows[0][1][2], Decimal(4))

    def test_selection_flushes_before_server_delete_and_no_fallback_selected(self):
        client, server, requests, replies = self.pair(client_source=CLIENT.replace(COMMAND, 'Result = RemoteWork("delete");'))
        client.open(); client.dispatch('select', revision=client.revision, control='Grid', row=2)
        self.assertIsNone(server.session.form.items._values['grid'].current_row)
        after = self.command(client)
        self.assertEqual([r[0] for r in after.tables[0].rows], [1])
        self.assertEqual(after.selections, (('Grid', None),))
        self.assertEqual(server.session.snapshot().selections, (('Grid', None),))
        self.assertEqual(decode_line(requests[-1])['delta']['selections'][0][-1], 2)

    def test_surviving_handles_remain_identical_and_removed_handle_invalidates(self):
        client, server, requests, replies = self.pair(); client.open()
        table = client.form._tables['lines']; row = table._rows[0]; grid = client.form.items._values['grid']
        self.cell(client); self.command(client)
        self.assertIs(client.form._tables['lines'], table)
        self.assertIs(table._rows[0], row); self.assertIs(client.form.items._values['grid'], grid)
        self.assertEqual(row._data['amount'], Decimal('8.250'))
        server_source = SERVER.replace('// extra-work', 'Lines.Delete(Lines.Get(0));')
        deleting, _, _, _ = self.pair(server_source=server_source); deleting.open()
        old = deleting.form._tables['lines']._rows[0]
        self.command(deleting)
        self.assertTrue(old._removed)
        self.assertNotIn(old._row_id, deleting.form._tables['lines']._by_id)

    def test_client_add_delete_and_clear_never_reach_transport(self):
        for statement in ('Lines.Add();', 'Lines.Delete(Lines.Get(0));', 'Lines.Clear();'):
            with self.subTest(statement=statement):
                client, server, requests, replies = self.pair(client_source=CLIENT.replace(COMMAND, statement))
                before = client.open()
                with self.assertRaises((BSLError, ValueError)): self.command(client)
                self.assertEqual(len(requests), 1)
                self.assertEqual(client.snapshot().tables, before.tables)
                self.assertFalse(client.uncertain)

    def test_trusted_client_can_change_readonly_cell_before_remote_call(self):
        source = CLIENT.replace(COMMAND, 'R = Lines.Get(0); R.Amount = 123; Result = RemoteWork("noop");')
        server_source = SERVER.replace('For Each R In Lines Do R.Amount = R.Qty * 2; Total = Total + R.Amount; EndDo;',
                                       'For Each R In Lines Do Total = Total + R.Amount; EndDo;')
        client, server, requests, replies = self.pair(client_source=source, server_source=server_source)
        client.open(); result = self.command(client)
        self.assertEqual(dict(result.attributes)['Total'], Decimal(129))
        self.assertEqual(decode_line(requests[-1])['delta']['cells'][0][2], 2)

    def test_schema_drift_never_partially_installs_scalar_or_table_state(self):
        def change_name(frame): frame['state']['tables'][0]['columns'][0][0] = 'Renamed'
        def change_type(frame): frame['state']['tables'][0]['columns'][1][1] = 'String'
        def change_qualifier(frame): frame['state']['tables'][0]['columns'][0][2][3] = 128
        def change_readonly(frame): frame['state']['tables'][0]['columns'][0][4] = True
        def change_title(frame): frame['state']['tables'][0]['title'] = 'Changed'
        def remove_table(frame): frame['state']['tables'] = []
        for mutate in (change_name, change_type, change_qualifier, change_readonly, change_title, remove_table):
            with self.subTest(mutation=mutate.__name__): self.tampered_call(mutate)

    def test_duplicate_invalid_and_unallocated_response_row_ids_are_atomic(self):
        def duplicate(frame): frame['state']['tables'][0]['rows'][1][0] = 1
        def boolean(frame): frame['state']['tables'][0]['rows'][0][0] = True
        def negative(frame): frame['state']['tables'][0]['rows'][0][0] = -1
        def unallocated(frame): frame['state']['tables'][0]['rows'][0][0] = 3
        def decreasing(frame): frame['state']['tables'][0]['allocated'] = 1
        for mutate in (duplicate, boolean, negative, unallocated, decreasing):
            with self.subTest(mutation=mutate.__name__): self.tampered_call(mutate)

    def test_bad_response_cell_shape_or_scalar_tag_is_atomic(self):
        def short(frame): frame['state']['tables'][0]['rows'][1][1].pop()
        def wrong_type(frame): frame['state']['tables'][0]['rows'][1][1][1] = encode_value('invalid')
        def hostile_tag(frame): frame['state']['tables'][0]['rows'][1][1][0] = {'type': 'HostObject', 'value': 'no'}
        def extra_key(frame): frame['state']['tables'][0]['surprise'] = True
        for mutate in (short, wrong_type, hostile_tag, extra_key):
            with self.subTest(mutation=mutate.__name__): self.tampered_call(mutate)

    def test_removed_row_identity_cannot_be_resurrected(self):
        calls = 0
        def exchange(server, raw):
            nonlocal calls
            frame = decode_line(server.exchange(raw))
            if decode_line(raw)['operation'] == 'call':
                calls += 1
                if calls == 2:
                    table = frame['state']['tables'][0]
                    table['rows'].append([1, [encode_value('resurrected'), encode_value(Decimal(1)), encode_value(Decimal(2))]])
            return encode_line(frame)
        source = SERVER.replace('// extra-work', 'If Calls = 1 Then Lines.Delete(Lines.Get(0)); EndIf;')
        client, server, requests, replies = self.pair(server_source=source, exchange=exchange)
        client.open(); self.command(client); before = client.snapshot()
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertTrue(client.uncertain)
        self.assertEqual(client.snapshot().tables, before.tables)
        self.assertEqual([r[0] for r in before.tables[0].rows], [2])

    def test_table_schema_cannot_appear_after_empty_bootstrap(self):
        scalar_server = '''&AtServer
Procedure Create(Cancel, StandardProcessing)
 C = Commands.Add("Run"); C.Action = "RunCommand";
 B = Items.Add("RunButton", Type("FormButton")); B.CommandName = "Run";
EndProcedure
&AtServer
Function Work(Val Action)
 Calls = Calls + 1; Return Calls;
EndFunction
'''
        template_client, _, _, template_replies = self.pair(); template_client.open()
        injected = decode_line(template_replies[0])['state']['tables']
        def exchange(server, raw):
            reply = decode_line(server.exchange(raw))
            if decode_line(raw)['operation'] == 'call': reply['state']['tables'] = deepcopy(injected)
            return encode_line(reply)
        client, server, requests, replies = self.pair(server_source=scalar_server, tables=(), exchange=exchange)
        client.open(); before = client.snapshot()
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertTrue(client.uncertain)
        self.assertEqual(client.snapshot().tables, before.tables)
        self.assertEqual(dict(client.snapshot().attributes)['Calls'], Decimal(0))

    def test_duplicate_and_unknown_response_table_selection_rejected(self):
        def removed(frame):
            next(i for i in frame['state']['items'] if i[1] == 'table')[10] = 999
        def wrong_row_type(frame):
            next(i for i in frame['state']['items'] if i[1] == 'table')[10] = True
        def duplicate_control(frame):
            rows = frame['state']['items']; original = next(i for i in rows if i[1] == 'table')
            duplicate = deepcopy(original); duplicate[0] = 'OtherGrid'; duplicate[9] = 900
            rows.append(duplicate); frame['state']['allocated'] = 900
        for mutate in (removed, wrong_row_type, duplicate_control):
            with self.subTest(mutation=mutate.__name__): self.tampered_call(mutate)

    def test_duplicate_delta_cells_do_not_apply_prior_scalar_or_cell(self):
        client, server, requests, replies = self.pair(); client.open()
        delta = scalar_delta(); delta['attributes'] = [['status', encode_value('must not apply')]]
        cell = [1, 1, 0, encode_value('changed')]; delta['cells'] = [cell, cell]
        self.reject_delta(server, delta)

    def test_unknown_removed_and_out_of_range_delta_cells_are_atomic(self):
        client, server, requests, replies = self.pair(); client.open()
        for cell in ([2, 1, 0, encode_value('x')], [1, 99, 0, encode_value('x')],
                     [1, 1, 3, encode_value('x')], [1, True, 0, encode_value('x')],
                     [1, 1, 1, encode_value('not number')]):
            with self.subTest(cell=cell):
                delta = scalar_delta(); delta['attributes'] = [['status', encode_value('must not apply')]]
                delta['cells'] = [[1, 1, 0, encode_value('earlier')], cell]
                self.reject_delta(server, delta)

    def test_invalid_delta_selection_prevents_all_other_changes(self):
        client, server, requests, replies = self.pair(); client.open()
        identity = client.form.items._values['grid']._replica_id
        for selections in ([[identity, 1, 999]], [[identity, 2, 1]],
                           [[identity, 1, 1], [identity, 1, 2]], [[999, 1, 1]]):
            with self.subTest(selections=selections):
                delta = scalar_delta(); delta['cells'] = [[1, 1, 0, encode_value('must not apply')]]
                delta['selections'] = selections; self.reject_delta(server, delta)

    def test_delta_cannot_change_schema_or_row_inventory(self):
        client, server, requests, replies = self.pair(); client.open()
        for key, value in (('tables', []), ('rows', []), ('schema', {})):
            with self.subTest(key=key):
                delta = scalar_delta(); delta[key] = value
                self.reject_delta(server, delta)

    def test_stale_server_revision_rejects_before_any_delta(self):
        client, server, requests, replies = self.pair(); client.open()
        delta = scalar_delta(); delta['cells'] = [[1, 1, 0, encode_value('must not apply')]]
        self.reject_delta(server, delta, reason='stale_revision', revision=0)

    def test_aggregate_delta_budget_prevents_scalar_cell_and_handler_effects(self):
        client, server, requests, replies = self.pair(); client.open()
        delta = scalar_delta(); delta['attributes'] = [['status', encode_value('must not apply')]]
        delta['cells'] = [[1, 1, 0, encode_value('x' * 500)]]
        with patch('yadinassi.form_tables.MAX_TABLE_DATA_BYTES', 500): self.reject_delta(server, delta)

    def test_valid_multitable_delta_can_grow_then_shrink_atomically(self):
        other = FormTableSchema('Other', (FormTableColumn('Label', BSLTypeDescription('String')),))
        source = SERVER.replace('// extra-create', 'R = Lines.Get(0); R.Label = "'+('a' * 8000)+'"; R = Other.Add();')
        client, server, requests, replies = self.pair(server_source=source, tables=(SCHEMA, other)); client.open()
        delta = scalar_delta(); delta['cells'] = [[2, 1, 0, encode_value('b' * 8000)], [1, 1, 0, encode_value('')]]
        with patch('yadinassi.form_tables.MAX_TABLE_DATA_BYTES', 9000):
            response = decode_line(server.exchange(encode_line(self.request(server, delta))))
        self.assertTrue(response['accepted']); self.assertEqual(response['status'], 'ok')
        snapshots = server.session.snapshot().tables
        self.assertEqual(snapshots[0].rows[0][1][0], '')
        self.assertEqual(snapshots[1].rows[0][1][0], 'b' * 8000)

    def test_known_server_error_applies_completed_rows_before_client_catch(self):
        source = CLIENT.replace(COMMAND, 'Try Result = RemoteWork("fail"); Except Status = Lines.Get(0).Label; EndTry;')
        client, server, requests, replies = self.pair(client_source=source); client.open()
        snap = self.command(client)
        self.assertEqual(snap.tables[0].rows[0][1][0], 'known effect')
        self.assertEqual(snap.tables[0].rows[-1][1][0], 'added before error')
        self.assertEqual(dict(snap.attributes)['Status'], 'known effect')
        response = decode_line(replies[-1]); self.assertEqual(response['reason'], 'server_error')
        self.assertTrue(response['accepted']); self.assertNotIn(b'private detail', replies[-1])
        self.assertFalse(client.uncertain)

    def test_unknown_reply_locks_without_replaying_committed_row_changes(self):
        def exchange(server, raw):
            reply = server.exchange(raw)
            if decode_line(raw)['operation'] == 'call': raise OSError('response lost')
            return reply
        source = SERVER.replace('// extra-work', 'R = Lines.Add(); R.Label = "one effect";')
        client, server, requests, replies = self.pair(server_source=source, exchange=exchange); client.open()
        before = client.snapshot()
        for _ in range(2):
            with self.assertRaisesRegex((BSLError, ValueError), 'outcome_unknown'): self.command(client)
        self.assertTrue(client.uncertain); self.assertEqual(len(requests), 2)
        self.assertEqual(client.snapshot().tables, before.tables)
        self.assertEqual(len(server.session.snapshot().tables[0].rows), 3)
        self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(1))

    def test_close_flushes_pending_cells_and_selection(self):
        client, server, requests, replies = self.pair(); client.open()
        self.cell(client, row=2, column='Label', value='unsaved edit')
        closed = client.dispatch('close', revision=client.revision)
        self.assertEqual(closed.state, 'closed')
        self.assertEqual(server.session.snapshot().tables[0].rows[1][1][0], 'unsaved edit')
        self.assertEqual(server.session.snapshot().selections, (('Grid', 2),))
        self.assertEqual([decode_line(r)['operation'] for r in requests], ['open', 'close'])

    def test_nocontext_call_keeps_pending_table_cells_local(self):
        source = CLIENT.replace(COMMAND, 'Calls = Detached(3);')
        client, server, requests, replies = self.pair(client_source=source)
        detached = InvocationServer('&AtServerNoContext\nFunction Triple(Val X) Return X * 3; EndFunction', {1: 'Triple'})
        scalar_frames = []
        def exchange(raw): scalar_frames.append(decode_line(raw)); return detached.exchange(raw)
        client.bind_nocontext(InvocationPort(exchange), InvocationBinding('Detached', 1, ('X',)))
        client.open(); self.cell(client); snap = self.command(client)
        self.assertEqual(dict(snap.attributes)['Calls'], Decimal(9))
        self.assertEqual(len(requests), 1)
        self.assertEqual(server.session.snapshot().tables[0].rows[0][1][1], Decimal(2))
        self.assertEqual(set(scalar_frames[0]), {'protocol', 'id', 'endpoint', 'arguments'})

    def test_live_row_cannot_escape_as_scalar_endpoint_result(self):
        source = SERVER.replace('Return Calls;', 'Return Lines.Get(0);')
        client, server, requests, replies = self.pair(server_source=source); client.open()
        before = client.snapshot()
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertFalse(client.uncertain)
        self.assertEqual(decode_line(replies[-1])['reason'], 'server_error')
        self.assertEqual(client.snapshot().tables, before.tables)
        self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(1))
        self.assertEqual(dict(client.snapshot().attributes)['Calls'], Decimal(1))
        self.assertNotIn(b'BSLFormDataCollectionItem', replies[-1])

    def test_date_default_and_fractional_ticks_roundtrip_without_invocation_widening(self):
        from yadinassi.invocation import _encode_scalar
        temporal = FormTableSchema('Temporal', (FormTableColumn('When', BSLTypeDescription('Date')),))
        source = SERVER.replace('// extra-create', 'R = Temporal.Add();')
        client, server, requests, replies = self.pair(server_source=source, tables=(SCHEMA, temporal))
        opened = client.open()
        self.assertEqual(opened.tables[1].rows[0][1][0], BSLDate(0))
        self.assertEqual(decode_line(replies[0])['state']['tables'][1]['rows'][0][1][0],
                         {'type': 'Date', 'ticks': '0'})
        # Trusted host installs a scalar cell; browser Date editing stays a
        # separate display-only contract. Exercise both delta and full reply.
        fractional = BSLDate(123456789)
        client.form._tables['temporal']._replace_rows(((1, (fractional,)),), 1)
        roundtrip = self.command(client)
        self.assertEqual(roundtrip.tables[1].rows[0][1][0], fractional)
        self.assertEqual(server.session.snapshot().tables[1].rows[0][1][0], fractional)
        self.assertIn([2, 1, 0, {'type': 'Date', 'ticks': '123456789'}],
                      decode_line(requests[-1])['delta']['cells'])
        for value in (BSLDate(0), fractional):
            with self.assertRaises((TypeError, ValueError)): _encode_scalar(value)

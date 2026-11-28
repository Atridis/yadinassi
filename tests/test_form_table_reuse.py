"""Versioned table reuse in trusted form hosts; scalar effects still cross."""
from decimal import Decimal
import sys
import unittest
from unittest.mock import patch

from yadinassi import BSLError
from yadinassi.execution.invocation import InvocationError
from yadinassi.forms import form_replication as replica, form_table_replication as tables, form_tables as model
from yadinassi.ui.protocol import decode_line, encode_line, encode_value

import test_form_table_replication as fixtures


class FormTableReuseTests(unittest.TestCase):
    def pair(self, source, command='Result=RemoteWork("sum");', *, transform=None):
        requests, replies = [], []
        server = replica.ReplicatedFormServer(source, {1: 'Work'}, handlers=fixtures.HANDLERS,
            tables=(fixtures.SCHEMA,), attributes=fixtures.attributes(),
            bindings={'OnCreateAtServer': 'Create'})
        self.addCleanup(server.session.interpreter.close)

        def exchange(raw):
            request = decode_line(raw)
            requests.append(request)
            if transform is None:
                reply = decode_line(server.exchange(raw))
            else:
                reply = transform(client, server, request)
            replies.append(reply)
            return encode_line(reply)

        client = replica.ReplicatedFormSession(fixtures.CLIENT.replace(fixtures.COMMAND, command),
            exchange, handlers=fixtures.HANDLERS, bindings=(fixtures.REMOTE,), reuse_tables=True)
        self.addCleanup(client.interpreter.close)
        return client, server, requests, replies

    def command(self, client):
        return client.dispatch('command', revision=client.revision, control='RunButton')

    @staticmethod
    def scalar_server(body):
        start = fixtures.SERVER.split('&AtServer\nFunction Work', 1)[0]
        return start + '&AtServer\nFunction Work(Val Action)\n' + body + '\nEndFunction\n'

    def test_ten_unchanged_round_trips_do_not_pack_install_or_validate_tables(self):
        body = 'Calls=Calls+1; Return Calls;'
        command = 'X=0; For I=1 To 10 Do X=X+RemoteWork("sum"); EndDo; Total=X;'
        client, server, requests, replies = self.pair(self.scalar_server(body), command)
        client.open()
        table = client.form._tables['lines']; row = table._rows[0]
        generation = replies[0]['table_generation']
        self.assertIsNotNone(generation)
        self.assertIsInstance(replies[0]['state']['tables'], list)
        watched = {fn.__code__ for fn in (tables.pack_tables, tables.install_tables,
            model.BSLFormDataCollection._replace_rows, model.validate_table_data)}
        reached = []

        def profile(frame, event, _):
            if event == 'call' and frame.f_code in watched:
                reached.append(frame.f_code.co_name)

        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            snapshot = self.command(client)
        finally:
            sys.setprofile(previous)
        self.assertEqual(reached, [])
        self.assertEqual(dict(snapshot.attributes)['Total'], Decimal(55))
        self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(10))
        self.assertEqual([frame['sequence'] for frame in requests], list(range(1, 12)))
        self.assertEqual([frame['table_generation'] for frame in requests[1:]], [generation] * 10)
        self.assertEqual([frame['state']['tables'] for frame in replies[1:]], [None] * 10)
        self.assertIs(client.form._tables['lines'], table)
        self.assertIs(table._rows[0], row)

    def test_cell_delta_and_server_structure_change_publish_fresh_full_image(self):
        body = ('If Action = "delete" Then Lines.Delete(Lines.Get(1));'
                'ElsIf Action = "add" Then R=Lines.Add(); R.Qty=9; EndIf; Return 1;')
        client, server, requests, replies = self.pair(self.scalar_server(body))
        client.open()
        table = client.form._tables['lines']; first, second = table._rows
        old_generation = replies[0]['table_generation']
        client.dispatch('cell', revision=client.revision, control='Grid', row=1,
                        column='Qty', value=Decimal(5))
        self.command(client)
        self.assertIsNone(requests[-1]['table_generation'])
        self.assertEqual(requests[-1]['delta']['cells'], [[1, 1, 1, encode_value(Decimal(5))]])
        self.assertIsNotNone(replies[-1]['state']['tables'])
        self.assertNotEqual(replies[-1]['table_generation'], old_generation)
        self.assertEqual(first._data['qty'], Decimal(5))
        self.command(client)
        self.assertIsNone(replies[-1]['state']['tables'])

        client._request('call', fixtures.REMOTE, ('delete',))
        self.assertTrue(second._removed)
        self.assertEqual(replies[-1]['state']['tables'][0]['allocated'], 2)
        client._request('call', fixtures.REMOTE, ('add',))
        self.assertEqual([row._row_id for row in table._rows], [1, 3])
        self.assertIs(table._rows[0], first)
        self.assertEqual(client.snapshot().tables, server.session.snapshot().tables)
        self.command(client)
        self.assertIsNone(replies[-1]['state']['tables'])

    def test_server_cell_write_and_clear_invalidate_the_same_table_image(self):
        body = ('If Action = "edit" Then R=Lines.Get(0); R.Qty=21;'
                'ElsIf Action = "clear" Then Lines.Clear(); EndIf; Return 1;')
        client, server, requests, replies = self.pair(self.scalar_server(body))
        client.open()
        table = client.form._tables['lines']
        row = table._rows[0]
        generation = replies[-1]['table_generation']
        for action in ('edit', 'clear'):
            client._request('call', fixtures.REMOTE, (action,))
            self.assertEqual(requests[-1]['table_generation'], generation)
            self.assertIsNotNone(replies[-1]['state']['tables'])
            self.assertNotEqual(replies[-1]['table_generation'], generation)
            generation = replies[-1]['table_generation']
            self.assertEqual(client.snapshot().tables, server.session.snapshot().tables)
            if action == 'edit':
                self.assertIs(table._rows[0], row)
                self.assertEqual(row._data['qty'], Decimal(21))
            self.command(client)
            self.assertIsNone(replies[-1]['state']['tables'])
        self.assertTrue(row._removed)
        self.assertEqual(table._rows, [])

    def test_unknown_generation_resends_full_without_replaying_endpoint(self):
        def stale_ack(_client, server, request):
            if request['operation'] == 'call':
                request = {**request, 'table_generation': '0' * 96}
            return decode_line(server.exchange(encode_line(request)))

        client, server, _, replies = self.pair(self.scalar_server('Calls=Calls+1;Return Calls;'),
                                               transform=stale_ack)
        client.open(); self.command(client)
        self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(1))
        self.assertIsNotNone(replies[-1]['state']['tables'])
        self.assertNotEqual(replies[0]['table_generation'], replies[-1]['table_generation'])

    def test_known_error_still_installs_effects_when_table_changed(self):
        client, _, _, replies = self.pair(self.scalar_server(
            'R=Lines.Get(0);R.Label="effect";Raise "private";'))
        client.open()
        with self.assertRaises(BSLError):
            self.command(client)
        self.assertFalse(client.uncertain)
        self.assertEqual(replies[-1]['reason'], 'server_error')
        self.assertIsNotNone(replies[-1]['state']['tables'])
        self.assertEqual(client.form._tables['lines']._rows[0]._data['label'], 'effect')

    def test_tampered_table_generation_or_candidate_leaves_client_unmodified(self):
        for boundary in ('generation', 'full_image', 'selection', 'inventory'):
            with self.subTest(boundary=boundary):
                def mutate(_client, server, request):
                    if request['operation'] == 'call' and boundary == 'full_image':
                        request = {**request, 'table_generation': None}
                    reply = decode_line(server.exchange(encode_line(request)))
                    if request['operation'] == 'call':
                        if boundary == 'generation':
                            reply['table_generation'] = '0' * 96
                        elif boundary == 'full_image':
                            reply['state']['tables'][0]['rows'][0][1][0] = encode_value('changed')
                        elif boundary == 'selection':
                            next(row for row in reply['state']['items'] if row[1] == 'table')[10] = 999
                        else:
                            reply['state']['attributes'][0][0] = 'Lines'
                    return reply

                client, server, _, _ = self.pair(self.scalar_server('Calls=Calls+1;Return Calls;'),
                                                  transform=mutate)
                before = client.open()
                with self.assertRaises(BSLError):
                    self.command(client)
                self.assertTrue(client.uncertain)
                self.assertEqual(client.server_revision, 1)
                self.assertEqual(client.client_sequence, 1)
                self.assertEqual(client.snapshot().tables, before.tables)
                self.assertEqual(client.snapshot().attributes, before.attributes)
                with self.assertRaises(InvocationError):
                    self.command(client)
                self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(1))

    def test_live_client_mutation_during_exchange_cannot_acknowledge_stale_rows(self):
        def mutate(client, server, request):
            reply = decode_line(server.exchange(encode_line(request)))
            if request['operation'] == 'call':
                client.form._tables['lines']._rows[0].set_member('Qty', Decimal(123))
            return reply

        client, _, _, replies = self.pair(self.scalar_server('Return 1;'), transform=mutate)
        client.open()
        with self.assertRaises(BSLError):
            self.command(client)
        self.assertIsNone(replies[-1]['state']['tables'])
        self.assertTrue(client.uncertain)
        self.assertEqual(client.server_revision, 1)
        self.assertEqual(client.form._tables['lines']._rows[0]._data['qty'], Decimal(123))

    def test_reuse_preserves_aggregate_text_and_validates_empty_delta_shape(self):
        client, server, _, replies = self.pair(self.scalar_server('Calls=Calls+1;Return Calls;'))
        client.open()
        generation = replies[0]['table_generation']
        def request(inventory, attributes):
            delta = fixtures.scalar_delta()
            delta.update(cells=inventory, attributes=attributes)
            frame = fixtures.ReplicatedTableTests().request(server, delta)
            frame.update(protocol=replica.TABLE_PROTOCOL, table_generation=generation)
            return decode_line(server.exchange(encode_line(frame)))

        with patch.object(tables, 'MAX_TOTAL_TEXT', 11):
            over = request([], [['status', encode_value('x')]])
        self.assertFalse(over['accepted']); self.assertEqual(over['reason'], 'invalid_delta')
        bad = request(None, [])
        self.assertFalse(bad['accepted']); self.assertEqual(bad['reason'], 'invalid_delta')
        self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(0))

    def test_accepted_open_pins_protocol_without_consuming_invalid_switch(self):
        profiles = (replica.PROTOCOL, replica.TABLE_PROTOCOL)
        for established, alternate in (profiles, profiles[::-1]):
            with self.subTest(established=established):
                _, server, _, _ = self.pair(self.scalar_server('Calls=Calls+1; Return Calls;'))

                def exchange(protocol, operation='call', *, delta=None, wrong=False):
                    frame = fixtures.ReplicatedTableTests().request(server, delta)
                    frame.update(protocol=protocol, operation=operation)
                    if operation == 'open':
                        frame.update(endpoint=0, arguments=[])
                    if wrong:
                        frame.update(revision=0, endpoint=2)
                    if protocol == replica.TABLE_PROTOCOL:
                        frame['table_generation'] = None
                    return decode_line(server.exchange(encode_line(frame)))

                invalid_open = exchange(alternate, 'open', delta={})
                self.assertEqual(invalid_open['reason'], 'invalid_delta')
                self.assertIsNone(server._replica_protocol)
                self.assertTrue(exchange(established, 'open')['accepted'])
                last_id = server._last_id
                rejected = exchange(alternate, delta=fixtures.scalar_delta(), wrong=True)
                self.assertFalse(rejected['accepted'])
                self.assertEqual(rejected['reason'], 'invalid_request')
                self.assertEqual(server._last_id, last_id)
                self.assertEqual(server.session.revision, 1)
                self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(0))
                self.assertEqual(exchange(established, 'open')['reason'], 'closed')
                self.assertTrue(exchange(established, delta=fixtures.scalar_delta())['accepted'])
                self.assertEqual(dict(server.session.snapshot().attributes)['Calls'], Decimal(1))

    def test_owned_stdio_child_uses_same_compact_grammar(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from yadinassi.ui.form_app import FormController, FormProcess
        from yadinassi.ui.form_package import TABLE_PACKAGE_PROTOCOL, load_client
        from test_form_app import event, state

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        def binding(item):
            return {'name': item.name, 'endpoint': item.endpoint,
                    'parameters': list(item.parameters), 'isFunction': item.is_function}
        handlers = [binding(item) for item in fixtures.HANDLERS]
        client = {'protocol': TABLE_PACKAGE_PROTOCOL, 'handlers': handlers,
                  'bindings': [binding(fixtures.REMOTE)]}
        server = {'protocol': TABLE_PACKAGE_PROTOCOL, 'handlers': handlers,
                  'endpoints': [{'endpoint': 1, 'routine': 'Work'}],
                  'lifecycle': {'OnCreateAtServer': 'Create'},
                  'attributes': [{'name': name, 'type': kind, 'title': name,
                                  'value': encode_value(value)}
                    for name, kind, value in (('Status','String',''), ('Total','Number',Decimal(0)),
                                               ('Calls','Number',Decimal(0)))],
                  'tables': [{'name': 'Lines', 'title': 'Lines', 'columns': [
                    {'name': col.name, 'type': kind, 'title': col.title, 'readOnly': col.read_only}
                    for col, kind in zip(fixtures.SCHEMA.columns, ('String','Number','Number'))]}]}
        for filename, value in (('client.json', client), ('server.json', server)):
            (root / filename).write_text(json.dumps(value), encoding='utf-8')
        (root / 'client.bsl').write_text(fixtures.CLIENT.replace(
            fixtures.COMMAND, 'Total=RemoteWork("sum")+RemoteWork("sum");'), encoding='utf-8')
        (root / 'server.bsl').write_text(self.scalar_server('Return 1;'), encoding='utf-8')
        process = FormProcess(root)
        self.addCleanup(process.close)
        replies = []

        def capture(raw):
            response = process.exchange(raw)
            replies.append(decode_line(response))
            return response

        controller = FormController(load_client(root), capture, reuse_tables=True)
        self.addCleanup(controller.session.interpreter.close)
        self.assertIsNone(state(controller)['error'])
        self.assertIsNone(event(controller)['error'])
        self.assertEqual(process.counter, 3)
        self.assertEqual(dict(controller.session.snapshot().attributes)['Total'], 2)
        self.assertEqual([reply['protocol'] for reply in replies], [replica.TABLE_PROTOCOL] * 3)
        self.assertEqual([reply['state']['tables'] is None for reply in replies], [False, True, True])

    def test_configuration_process_enrolls_owned_document_table_automatically(self):
        from test_configuration_document_app import DocumentApplicationTests

        application = DocumentApplicationTests()
        self.addCleanup(application.doCleanups)
        application.setUp()
        exchange = application.app.transport
        responses = []

        def capture(raw):
            request = decode_line(raw)
            response = exchange(raw)
            if request['operation'] == 'form':
                responses.append(decode_line(response)['result'])
            return response

        application.app.transport = capture
        identity = application.open()
        application.event(identity, 'close')
        self.assertEqual([reply['protocol'] for reply in responses], [replica.TABLE_PROTOCOL] * 2)
        self.assertIsInstance(responses[0]['state']['tables'], list)
        self.assertIsNone(responses[1]['state']['tables'])
        self.assertEqual(responses[0]['table_generation'], responses[1]['table_generation'])
        self.assertEqual(responses[1]['state']['lifecycle'], 'closed')

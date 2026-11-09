"""Detached form copies over bytes. Synthetic host evidence, not native 1C parity."""
from asyncio import CancelledError
from decimal import Decimal
import os
from pathlib import Path
import subprocess
from queue import Queue, Empty
from threading import Thread
import sys
import unittest

from yadinassi import BSLError
from yadinassi.form_model import BSLFormAttribute
from yadinassi.form_replication import ReplicatedFormServer, ReplicatedFormSession
from yadinassi.invocation import InvocationBinding, InvocationPort, InvocationServer
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.ui.protocol import decode_line, encode_line

ROOT = Path(__file__).resolve().parents[1]
HANDLERS = (
    InvocationBinding('Opened', 1, ('Cancel',), False),
    InvocationBinding('Changed', 2, ('Element',), False),
    InvocationBinding('CalculateCommand', 3, ('Command',), False),
)
REMOTE = InvocationBinding('RemoteCalculate', 1, ('Bonus',))
SERVER = '''&AtServer
Procedure Create(Cancel, StandardProcessing)
    A = New Array;
    A.Add(New FormAttribute("Dynamic", New TypeDescription("String")));
    ChangeAttributes(A);
    ThisObject.Dynamic = "server-created";
    F = Items.Add("PriceField", Type("FormField"));
    F.DataPath = "Price";
    F.SetAction("OnChange", "Changed");
    C = Commands.Add("Calculate");
    C.Action = "CalculateCommand";
    B = Items.Add("CalculateButton", Type("FormButton"));
    B.CommandName = "Calculate";
EndProcedure
&AtServer
Function Calculate(Val Bonus)
    ThisObject.Result = ThisObject.Price * ThisObject.Quantity + Bonus;
    ThisObject.Status = ThisObject.Status + ":server";
    Items.PriceField.Title = "calculated";
    ThisObject.Dynamic = ThisObject.Dynamic + ":roundtrip";
    Message("server total");
    Return ThisObject.Result;
EndFunction
'''
COMMAND = '''Returned = RemoteCalculate(0.70);
ThisObject.Status = ThisObject.Status + ":client:" + String(ThisObject.Result);
Message(Items.PriceField.Title + ":" + String(Returned));'''
CLIENT = '''&AtClient
Procedure Opened(Cancel)
    ThisObject.Status = "opened";
EndProcedure
&AtClient
Procedure Changed(Element)
    ThisObject.Status = "edited";
    Items.PriceField.Title = "client edited";
EndProcedure
&AtClient
Procedure CalculateCommand(Command)
    %s
EndProcedure
''' % COMMAND


def make_server(source=SERVER, *, handlers=HANDLERS, lifecycle=None):
    return ReplicatedFormServer(source, {1: 'Calculate'}, handlers=handlers,
        attributes=tuple(BSLFormAttribute(name, BSLTypeDescription(kind)) for name, kind in (
            ('Price', 'Number'), ('Quantity', 'Number'), ('Result', 'Number'), ('Status', 'String'))),
        initial_values={'Price': Decimal('20.10'), 'Quantity': Decimal(3)},
        bindings=({'OnCreateAtServer': 'Create', 'OnOpen': 'Opened'} if lifecycle is None else lifecycle))


class ReplicatedFormFlowTests(unittest.TestCase):
    def pair(self, *, client_source=CLIENT, server_source=SERVER, exchange=None,
             handlers=HANDLERS, lifecycle=None, sink=None):
        server = make_server(server_source, handlers=handlers, lifecycle=lifecycle)
        requests, replies, output = [], [], []
        def transport(raw):
            self.assertIs(type(raw), bytes)
            requests.append(raw)
            response = server.exchange(raw) if exchange is None else exchange(server, raw)
            self.assertIs(type(response), bytes)
            replies.append(response)
            return response
        def record(message):
            output.append(message)
            if sink is not None: sink(message)
        client = ReplicatedFormSession(client_source, transport, handlers=handlers,
                                       bindings=(REMOTE,), output=record)
        return client, server, requests, replies, output

    def command(self, client, revision=None):
        return client.dispatch('command', revision=client.revision if revision is None else revision,
                               control='CalculateButton')

    def test_bootstrap_composition_dynamic_schema_and_client_open(self):
        client, server, requests, replies, output = self.pair()
        first = client.open()
        self.assertEqual(first.state, 'open')
        self.assertEqual(dict(first.attributes)['Dynamic'], 'server-created')
        self.assertEqual(dict(first.attributes)['Status'], 'opened')
        self.assertEqual({item[0] for item in first.items}, {'PriceField', 'CalculateButton'})
        self.assertEqual(first.commands, (('Calculate', ''),))
        self.assertEqual(len(requests), 1)
        self.assertFalse(client.uncertain)

    def test_dirty_field_and_appearance_roundtrip_before_client_continuation(self):
        client, server, requests, replies, output = self.pair()
        first = client.open()
        edited = client.dispatch('change', revision=first.revision, control='PriceField', value=Decimal(7))
        self.assertEqual(len(requests), 1)
        result = self.command(client)
        self.assertEqual(dict(result.attributes)['Result'], Decimal('21.70'))
        self.assertEqual(dict(result.attributes)['Status'], 'edited:server:client:21,7')
        self.assertEqual(next(x for x in result.items if x[0] == 'PriceField')[2], 'calculated')
        self.assertEqual(output, ['server total', 'calculated:21,7'])
        self.assertEqual(client.messages, tuple(output))
        self.assertEqual(dict(edited.attributes)['Result'], Decimal(0))
        self.assertEqual(dict(first.attributes)['Price'], Decimal('20.10'))

    def test_repeated_calls_keep_separate_ui_and_server_counters(self):
        client, server, requests, replies, output = self.pair(); client.open()
        before = client.server_revision
        client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(2))
        self.assertEqual(client.server_revision, before)
        self.command(client)
        one = client.server_revision
        self.command(client)
        self.assertGreater(client.server_revision, one)
        self.assertEqual(dict(client.snapshot().attributes)['Dynamic'], 'server-created:roundtrip:roundtrip')
        self.assertEqual(len(requests), 3)
        self.assertEqual(len({decode_line(raw)['id'] for raw in requests}), 3)

    def test_stale_click_never_reaches_transport(self):
        client, server, requests, replies, output = self.pair(); client.open()
        revision = client.revision
        self.command(client)
        with self.assertRaises(ValueError): self.command(client, revision)
        self.assertEqual(len(requests), 2)

    def test_nocontext_transfers_only_arguments_without_form_flush(self):
        source = CLIENT.replace(COMMAND, 'ThisObject.Result = Detached(4);')
        client, server, requests, replies, output = self.pair(client_source=source)
        detached = InvocationServer('&AtServerNoContext\nFunction Twice(Val X) Return X * 2; EndFunction', {1: 'Twice'})
        frames = []
        def exchange(raw):
            frames.append(decode_line(raw))
            return detached.exchange(raw)
        client.bind_nocontext(InvocationPort(exchange), InvocationBinding('Detached', 1, ('X',)))
        client.open()
        revision, sequence = client.server_revision, client.client_sequence
        client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(9))
        result = self.command(client)
        self.assertEqual(dict(result.attributes)['Result'], Decimal(8))
        self.assertEqual(len(requests), 1)
        self.assertEqual((client.server_revision, client.client_sequence), (revision, sequence))
        self.assertEqual(set(frames[0]), {'protocol', 'id', 'endpoint', 'arguments'})

    def test_server_error_applies_completed_mutations_before_catch(self):
        source = CLIENT.replace(COMMAND, '''Try RemoteCalculate(0.70); Except
ThisObject.Status = ThisObject.Status + ":caught:" + String(ThisObject.Result);
EndTry;''')
        failing = SERVER.replace('Return ThisObject.Result;', 'Raise "private server detail";')
        client, server, requests, replies, output = self.pair(client_source=source, server_source=failing)
        client.open(); result = self.command(client)
        self.assertEqual(dict(result.attributes)['Result'], Decimal(61))
        self.assertEqual(dict(result.attributes)['Status'], 'opened:server:caught:61')
        self.assertIn('server_error', replies[-1].decode())
        self.assertNotIn('private server detail', replies[-1].decode())
        self.assertFalse(client.uncertain)
        self.command(client)
        self.assertEqual(len(requests), 3)

    def test_wire_has_no_server_or_client_bodies_or_python_handles(self):
        client, server, requests, replies, output = self.pair(); client.open(); self.command(client)
        for raw in requests + replies:
            text = raw.decode('utf-8')
            for forbidden in ('&AtServer', '&AtClient', 'EndProcedure', 'EndFunction', '0x', '__dict__'):
                self.assertNotIn(forbidden, text)
        self.assertNotIn(b'RemoteCalculate', requests[-1])
        self.assertNotIn(b'Calculate', requests[-1])

    def test_lost_reply_locks_session_without_replaying_server_effect(self):
        calls = 0
        def lose(server, raw):
            nonlocal calls
            calls += 1
            result = server.exchange(raw)
            if calls > 1: raise OSError('lost response')
            return result
        client, server, requests, replies, output = self.pair(exchange=lose); client.open()
        with self.assertRaisesRegex((BSLError, ValueError), 'outcome_unknown'): self.command(client)
        self.assertTrue(client.uncertain)
        with self.assertRaisesRegex((BSLError, ValueError), 'outcome_unknown'): self.command(client)
        self.assertEqual(len(requests), 2)

    def test_malformed_reply_locks_session_without_retry(self):
        calls = 0
        def malformed(server, raw):
            nonlocal calls
            calls += 1
            good = server.exchange(raw)
            return good if calls == 1 else b'{"broken":true}\n'
        client, server, requests, replies, output = self.pair(exchange=malformed); client.open()
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertTrue(client.uncertain)
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertEqual(len(requests), 2)

    def test_mismatched_response_id_is_not_applied(self):
        calls = 0
        def tamper(server, raw):
            nonlocal calls
            calls += 1
            frame = decode_line(server.exchange(raw))
            if calls > 1: frame['id'] += 1
            return encode_line(frame)
        client, server, requests, replies, output = self.pair(exchange=tamper); client.open()
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertTrue(client.uncertain)
        self.assertEqual(dict(client.snapshot().attributes)['Result'], Decimal(0))

    def test_replayed_request_rejected_without_second_server_execution(self):
        client, server, requests, replies, output = self.pair(); client.open(); self.command(client)
        try:
            response = decode_line(server.exchange(requests[-1]))
        except ValueError:
            pass
        else:
            self.assertEqual(response['status'], 'error')
        result = self.command(client)
        self.assertEqual(dict(result.attributes)['Dynamic'], 'server-created:roundtrip:roundtrip')

    def test_renderer_cannot_select_server_endpoint_or_handler(self):
        client, server, requests, replies, output = self.pair(); client.open()
        for event, control in (('Calculate', ''), ('command', 'Calculate'), ('command', 'RemoteCalculate')):
            with self.subTest(event=event, control=control), self.assertRaises(ValueError):
                client.dispatch(event, revision=client.revision, control=control)
        self.assertEqual(len(requests), 1)

    def test_separate_process_retains_server_form_across_multiple_calls(self):
        child = '''import sys
from test_form_replication import make_server
server = make_server()
for raw in sys.stdin.buffer:
    sys.stdout.buffer.write(server.exchange(raw))
    sys.stdout.buffer.flush()
'''
        env = {**os.environ, 'PYTHONPATH': os.pathsep.join((str(ROOT), str(ROOT / 'tests'), os.environ.get('PYTHONPATH', ''))),
               'PYTHONIOENCODING': 'utf-8'}
        with subprocess.Popen([sys.executable, '-c', child], cwd=ROOT, env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                def exchange(raw):
                    process.stdin.write(raw); process.stdin.flush()
                    result = Queue()
                    def read(): result.put(process.stdout.readline(131073))
                    reader = Thread(target=read, daemon=True)
                    reader.start()
                    try: return result.get(timeout=10)
                    except Empty: raise TimeoutError('replicated server response timeout') from None
                client = ReplicatedFormSession(CLIENT, exchange, handlers=HANDLERS, bindings=(REMOTE,))
                client.open(); self.command(client)
                client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(4))
                result = self.command(client)
                self.assertEqual(dict(result.attributes)['Result'], Decimal('12.70'))
                self.assertEqual(dict(result.attributes)['Dynamic'], 'server-created:roundtrip:roundtrip')
            finally:
                process.stdin.close()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode('utf-8', 'replace'))

    def test_client_source_cannot_embed_server_routine_body(self):
        with self.assertRaises(ValueError):
            self.pair(client_source=CLIENT + '\n&AtServer\nFunction Secret(Val X) Return X; EndFunction')

    def test_dirty_delta_carries_edits_and_appearance_not_schema(self):
        client, server, requests, replies, output = self.pair(); client.open()
        client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(7))
        self.command(client)
        frame = decode_line(requests[-1])
        self.assertEqual(frame['arguments'], [{'type': 'Number', 'value': '0.70'}])
        self.assertEqual(set(frame['delta']), {'attributes', 'items', 'title'})
        self.assertEqual(dict(frame['delta']['attributes'])['price'], {'type': 'Number', 'value': '7'})
        self.assertEqual(next(item for item in frame['delta']['items'] if item[0] == 'PriceField')[1], 'client edited')

    def test_distinct_forms_controls_and_source_bodies(self):
        client, server, requests, replies, output = self.pair(); client.open()
        self.assertIsNot(client.form, server.session.form)
        self.assertIsNot(client.form.items._values['pricefield'], server.session.form.items._values['pricefield'])
        self.assertNotIn('calculate', client.interpreter.server_routines)
        self.assertEqual(client.interpreter.server_routines['remotecalculate'].body, [])
        self.assertEqual(server.session.interpreter.routines['opened'].body, [])
        client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(8))
        self.assertEqual(dict(server.session.snapshot().attributes)['Price'], Decimal('20.10'))
        self.assertEqual(next(item for item in server.session.snapshot().items if item[0] == 'PriceField')[2], '')
        self.command(client)
        self.assertEqual(dict(server.session.snapshot().attributes)['Price'], Decimal(8))

    def test_stale_server_revision_rejected_before_delta_application(self):
        client, server, requests, replies, output = self.pair(); client.open(); self.command(client)
        frame = decode_line(requests[-1])
        frame['id'] += 1
        frame['sequence'] += 1
        frame['delta']['attributes'] = [['Price', {'type': 'Number', 'value': '999'}]]
        before = server.session.snapshot()
        response = decode_line(server.exchange(encode_line(frame)))
        self.assertEqual(response['status'], 'error')
        self.assertFalse(response['accepted'])
        self.assertEqual(server.session.snapshot(), before)

    def test_wrong_client_sequence_rejected_before_server_execution(self):
        client, server, requests, replies, output = self.pair(); client.open(); self.command(client)
        frame = decode_line(requests[-1])
        frame['id'] += 1
        frame['revision'] = client.server_revision
        frame['sequence'] += 10
        before = server.session.snapshot()
        response = decode_line(server.exchange(encode_line(frame)))
        self.assertEqual(response['status'], 'error')
        self.assertFalse(response['accepted'])
        self.assertEqual(server.session.snapshot(), before)

    def test_unknown_delta_member_rejected_atomically(self):
        client, server, requests, replies, output = self.pair(); client.open(); self.command(client)
        frame = decode_line(requests[-1])
        frame['id'] += 1
        frame['revision'] = client.server_revision
        frame['sequence'] += 1
        frame['delta']['attributes'] = [['Price', {'type': 'Number', 'value': '999'}],
                                        ['UnknownAttribute', {'type': 'String', 'value': 'injected'}]]
        before = server.session.snapshot()
        response = decode_line(server.exchange(encode_line(frame)))
        self.assertEqual(response['status'], 'error')
        self.assertFalse(response['accepted'])
        self.assertEqual(server.session.snapshot(), before)

    def test_exchange_cannot_reenter_client_event_or_snapshot(self):
        def exchange(server, raw):
            if decode_line(raw)['operation'] == 'call':
                with self.assertRaises(ValueError): self.command(client)
                with self.assertRaises(ValueError): client.snapshot()
            return server.exchange(raw)
        client, server, requests, replies, output = self.pair(exchange=exchange); client.open()
        self.assertEqual(dict(self.command(client).attributes)['Result'], Decimal(61))
        self.assertFalse(client.uncertain)

    def test_close_flushes_dirty_client_state_and_closes_server(self):
        client, server, requests, replies, output = self.pair(); client.open()
        client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(8))
        self.assertEqual(dict(server.session.snapshot().attributes)['Price'], Decimal('20.10'))
        closed = client.dispatch('close', revision=client.revision)
        self.assertEqual(closed.state, 'closed')
        self.assertEqual(server.session.state, 'closed')
        self.assertTrue(server.session.closed)
        self.assertEqual(dict(server.session.snapshot().attributes)['Price'], Decimal(8))
        self.assertEqual(dict(server.session.snapshot().attributes)['Status'], 'edited')
        self.assertEqual([decode_line(raw)['operation'] for raw in requests], ['open', 'close'])
        with self.assertRaises(ValueError): self.command(client)
        self.assertEqual(len(requests), 2)

        with self.subTest(teardown="host dispose bypasses close callbacks and dirty flush"):
            handlers = HANDLERS + (InvocationBinding('Closed', 4, ('Exit',), False),)
            source = CLIENT + '''&AtClient
Procedure Closed(Exit)
    Raise "close callback must not run";
EndProcedure'''
            client, server, requests, replies, output = self.pair(client_source=source, handlers=handlers,
                lifecycle={'OnCreateAtServer': 'Create', 'OnOpen': 'Opened', 'OnClose': 'Closed'})
            client.open()
            client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(8))
            result = client.dispose()
            self.assertEqual(result.state, 'closed')
            self.assertEqual(server.session.state, 'closed')
            self.assertEqual(dict(server.session.snapshot().attributes)['Price'], Decimal('20.10'))
            self.assertEqual([decode_line(raw)['operation'] for raw in requests], ['open', 'dispose'])
            frame = decode_line(requests[-1])
            self.assertEqual((frame['endpoint'], frame['arguments'], frame['delta']), (0, [], None))

        with self.subTest(teardown="host dispose after known local close failure"):
            client, server, requests, replies, output = self.pair(client_source=source, handlers=handlers,
                lifecycle={'OnCreateAtServer': 'Create', 'OnOpen': 'Opened', 'OnClose': 'Closed'})
            client.open()
            with self.assertRaisesRegex(BSLError, 'close callback must not run'):
                client.dispatch('close', revision=client.revision)
            self.assertEqual(len(requests), 1)
            self.assertFalse(client.uncertain)
            client.dispose()
            self.assertEqual(server.session.state, 'closed')
            self.assertEqual(client.state, 'closed')
            self.assertEqual([decode_line(raw)['operation'] for raw in requests], ['open', 'dispose'])

    def test_cancelled_close_stays_open_without_transport(self):
        handlers = HANDLERS + (InvocationBinding('Before', 4,
            ('Cancel', 'Exit', 'MessageText', 'StandardProcessing'), False),)
        source = CLIENT + '''&AtClient
Procedure Before(Cancel, Exit, MessageText, StandardProcessing)
    Cancel = True;
    ThisObject.Status = "stayed";
EndProcedure'''
        client, server, requests, replies, output = self.pair(client_source=source, handlers=handlers,
            lifecycle={'OnCreateAtServer': 'Create', 'OnOpen': 'Opened', 'BeforeClose': 'Before'})
        client.open(); revision, sequence = client.server_revision, client.client_sequence
        result = client.dispatch('close', revision=client.revision)
        self.assertEqual(result.state, 'open')
        self.assertFalse(client.closed)
        self.assertEqual(server.session.state, 'open')
        self.assertEqual(dict(result.attributes)['Status'], 'stayed')
        self.assertEqual(len(requests), 1)
        self.assertEqual((client.server_revision, client.client_sequence), (revision, sequence))

    def test_cancelled_server_create_never_runs_client_open(self):
        source = SERVER.replace('    A = New Array;', '    Cancel = True;\n    A = New Array;')
        client, server, requests, replies, output = self.pair(server_source=source)
        result = client.open()
        self.assertEqual(result.state, 'cancelled')
        self.assertEqual(server.session.state, 'cancelled')
        self.assertTrue(client.closed)
        self.assertEqual(dict(result.attributes)['Status'], '')
        self.assertEqual(dict(result.attributes)['Dynamic'], 'server-created')
        self.assertEqual(len(requests), 1)
        with self.assertRaises(ValueError): self.command(client)
        self.assertEqual(len(requests), 1)

    def test_client_open_contextful_call_finishes_before_first_snapshot(self):
        source = CLIENT.replace('ThisObject.Status = "opened";', '''ThisObject.Status = "opening";
    RemoteCalculate(0.70);
    ThisObject.Status = ThisObject.Status + ":ready:" + String(ThisObject.Result);''')
        client, server, requests, replies, output = self.pair(client_source=source)
        result = client.open()
        self.assertEqual(result.revision, 1)
        self.assertEqual(dict(result.attributes)['Result'], Decimal(61))
        self.assertEqual(dict(result.attributes)['Status'], 'opening:server:ready:61')
        self.assertEqual([decode_line(raw)['operation'] for raw in requests], ['open', 'call'])
        self.assertEqual(client.server_revision, 2)
        self.assertEqual(output, ['server total'])

        with self.subTest(opening="known local failure disposes server and preserves exception"):
            source = CLIENT.replace('ThisObject.Status = "opened";',
                'ThisObject.Status = "unsent open edit"; Raise "original opening failure";')
            client, server, requests, replies, output = self.pair(client_source=source)
            with self.assertRaisesRegex(BSLError, 'original opening failure'):
                client.open()
            self.assertEqual(client.state, 'failed')
            self.assertTrue(client.closed)
            self.assertFalse(client.uncertain)
            self.assertEqual(server.session.state, 'closed')
            self.assertEqual(dict(server.session.snapshot().attributes)['Status'], '')
            self.assertEqual([decode_line(raw)['operation'] for raw in requests], ['open', 'dispose'])
            self.assertIsNone(decode_line(requests[-1])['delta'])

        with self.subTest(opening="unknown outcome neither cleans up nor permits host dispose"):
            source = CLIENT.replace('ThisObject.Status = "opened";', 'RemoteCalculate(0.70);')
            def lose(server, raw):
                response = server.exchange(raw)
                if decode_line(raw)['operation'] == 'call': raise OSError('lost opening reply')
                return response
            client, server, requests, replies, output = self.pair(client_source=source, exchange=lose)
            with self.assertRaisesRegex((BSLError, ValueError), 'outcome_unknown'):
                client.open()
            self.assertEqual(client.state, 'failed')
            self.assertTrue(client.uncertain)
            self.assertEqual(server.session.state, 'open')
            with self.assertRaisesRegex(ValueError, 'outcome_unknown'):
                client.dispose()
            self.assertEqual([decode_line(raw)['operation'] for raw in requests], ['open', 'call'])

    def test_held_field_parameter_survives_server_barrier(self):
        source = CLIENT.replace('Items.PriceField.Title = "client edited";', '''RemoteCalculate(0.70);
    ThisObject.Status = Element.Title;
    Element.Title = "continued through held field";''')
        client, server, requests, replies, output = self.pair(client_source=source); client.open()
        original = client.form.items._values['pricefield']
        result = client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(4))
        self.assertEqual(dict(result.attributes)['Result'], Decimal('12.70'))
        self.assertEqual(dict(result.attributes)['Status'], 'calculated')
        self.assertIs(client.form.items._values['pricefield'], original)
        self.assertEqual(next(item for item in result.items if item[0] == 'PriceField')[2],
                         'continued through held field')
        self.assertEqual(len(requests), 2)

        with self.subTest(replacement="same name and type, new identity"):
            replacing = SERVER.replace('    Return ThisObject.Result;', '''    Items.Delete(Items.PriceField);
    F = Items.Add("PriceField", Type("FormField"));
    F.DataPath = "Price";
    F.Title = "replacement";
    Return ThisObject.Result;''')
            source = CLIENT.replace('Items.PriceField.Title = "client edited";', '''RemoteCalculate(0.70);
    Try
        Element.Title = "must not affect replacement";
        ThisObject.Status = "old reference survived";
    Except
        ThisObject.Status = "old reference invalidated";
    EndTry;''')
            client, server, requests, replies, output = self.pair(client_source=source, server_source=replacing)
            client.open(); original = client.form.items._values['pricefield']
            result = client.dispatch('change', revision=client.revision, control='PriceField', value=Decimal(4))
            self.assertIsNot(client.form.items._values['pricefield'], original)
            self.assertTrue(original._removed)
            self.assertEqual(dict(result.attributes)['Status'], 'old reference invalidated')
            self.assertEqual(next(item for item in result.items if item[0] == 'PriceField')[2], 'replacement')
            self.assertEqual(len(requests), 2)

    def test_server_endpoint_adds_dynamic_composition_before_client_continuation(self):
        source = SERVER.replace('    Return ThisObject.Result;', '''    A = New Array;
    A.Add(New FormAttribute("Extra", New TypeDescription("String")));
    ChangeAttributes(A);
    ThisObject.Extra = "added at server";
    F = Items.Add("ExtraField", Type("FormField"));
    F.DataPath = "Extra";
    F.Title = "new field";
    Return ThisObject.Result;''')
        client_source = CLIENT.replace(COMMAND, '''RemoteCalculate(0.70);
ThisObject.Status = ThisObject.Extra + ":" + Items.ExtraField.Title;''')
        client, server, requests, replies, output = self.pair(client_source=client_source, server_source=source)
        first = client.open(); result = self.command(client)
        self.assertNotIn('Extra', dict(first.attributes))
        self.assertEqual(dict(result.attributes)['Extra'], 'added at server')
        self.assertEqual(dict(result.attributes)['Status'], 'added at server:new field')
        self.assertIn('ExtraField', {item[0] for item in result.items})
        self.assertIsNot(client.form.items._values['extrafield'], server.session.form.items._values['extrafield'])
        self.assertEqual(len(requests), 2)

    def test_malformed_full_state_is_rejected_without_partial_installation(self):
        def tamper(server, raw):
            response = decode_line(server.exchange(raw))
            if decode_line(raw)['operation'] == 'call':
                response['state']['title'] = 'must not install'
                response['state']['items'][-1][6] = 'MissingCommand'
            return encode_line(response)
        client, server, requests, replies, output = self.pair(exchange=tamper); client.open()
        before = client.snapshot()
        with self.assertRaisesRegex((BSLError, ValueError), 'outcome_unknown'): self.command(client)
        after = client.snapshot()
        self.assertEqual((after.title, after.attributes, after.items, after.commands),
                         (before.title, before.attributes, before.items, before.commands))
        self.assertEqual(dict(server.session.snapshot().attributes)['Result'], Decimal(61))
        self.assertEqual(client.messages, ())
        self.assertTrue(client.uncertain)
        with self.assertRaises(ValueError): self.command(client)
        self.assertEqual(len(requests), 2)

    def test_output_failure_locks_after_server_state_barrier(self):
        def fail_output(message): raise RuntimeError('host output failed')
        client, server, requests, replies, output = self.pair(sink=fail_output); client.open()
        with self.assertRaisesRegex((BSLError, ValueError), 'outcome_unknown'): self.command(client)
        self.assertEqual(dict(client.snapshot().attributes)['Result'], Decimal(61))
        self.assertEqual(dict(client.snapshot().attributes)['Status'], 'opened:server')
        self.assertEqual(client.messages, ('server total',))
        self.assertEqual(output, ['server total'])
        self.assertTrue(client.uncertain)
        self.assertFalse(client._busy)
        with self.assertRaises(ValueError): self.command(client)
        self.assertEqual(len(requests), 2)

    def test_transport_cancellation_propagates_and_locks_without_replay(self):
        cancellation = CancelledError()
        def cancel(server, raw):
            response = server.exchange(raw)
            if decode_line(raw)['operation'] == 'call': raise cancellation
            return response
        client, server, requests, replies, output = self.pair(exchange=cancel); client.open()
        with self.assertRaises(CancelledError) as caught: self.command(client)
        self.assertIs(caught.exception, cancellation)
        self.assertTrue(client.uncertain)
        self.assertFalse(client._busy)
        self.assertEqual(dict(server.session.snapshot().attributes)['Result'], Decimal(61))
        self.assertEqual(dict(client.snapshot().attributes)['Result'], Decimal(0))
        with self.assertRaises(ValueError): self.command(client)
        self.assertEqual(len(requests), 2)

    def test_nonscalar_contextful_argument_rejected_before_transport(self):
        source = CLIENT.replace(COMMAND, 'RemoteCalculate(ThisObject);')
        client, server, requests, replies, output = self.pair(client_source=source); client.open()
        revision, sequence = client.server_revision, client.client_sequence
        with self.assertRaises((BSLError, ValueError)): self.command(client)
        self.assertFalse(client.uncertain)
        self.assertEqual(len(requests), 1)
        self.assertEqual((client.server_revision, client.client_sequence), (revision, sequence))
        self.assertEqual(dict(server.session.snapshot().attributes)['Result'], Decimal(0))

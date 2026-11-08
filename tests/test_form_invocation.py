"""Scalar remote results inside serialized local form events, not form replication."""
from asyncio import CancelledError
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.form_model import BSLFormAttribute
from yadinassi.form_runtime import FormSession
from yadinassi.invocation import InvocationBinding, InvocationPort, InvocationServer
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.ui.protocol import decode_line

ROOT = Path(__file__).resolve().parents[1]
SERVER = '''&AtServerNoContext
Function Calculate(Val Price, Val Quantity)
    Message("server total");
    Return Price * Quantity;
EndFunction'''
COMMAND = '''ThisObject.Result = RemoteTotal(ThisObject.Price, ThisObject.Quantity) + 0.70;
Message("client result " + String(ThisObject.Result));'''
SOURCE = '''&AtServer
Procedure Create(Cancel, StandardProcessing)
    F = Items.Add("PriceField", Type("FormField"));
    F.DataPath = "Price";
    C = Commands.Add("Calculate");
    C.Action = "CalculateCommand";
    B = Items.Add("CalculateButton", Type("FormButton"));
    B.CommandName = "Calculate";
EndProcedure
&AtClient
Procedure CalculateCommand(Command)
    %s
EndProcedure
''' % COMMAND
BINDING = InvocationBinding('RemoteTotal', 1, ('Price', 'Quantity'))


def form(source=SOURCE, *, output=None):
    return FormSession(source, attributes=tuple(
        BSLFormAttribute(key, BSLTypeDescription(kind)) for key, kind in
        [('Price', 'Number'), ('Quantity', 'Number'), ('Result', 'Number'), ('Status', 'String')]),
        initial_values={'Price': Decimal('20.10'), 'Quantity': Decimal(3)},
        bindings={'OnCreateAtServer': 'Create'}, output=output)


class FormInvocationTests(unittest.TestCase):
    def setup_form(self, *, source=SOURCE, exchange=None, server_source=SERVER, output=None):
        session = form(source, output=output)
        server = InvocationServer(server_source, {1: 'Calculate'})
        requests = []
        def transport(raw):
            requests.append(raw)
            return server.exchange(raw) if exchange is None else exchange(server, raw)
        port = InvocationPort(transport)
        port.bind_form(session, BINDING)
        return session, port, server, requests

    def command(self, session, revision=None):
        return session.dispatch('command', revision=session.revision if revision is None else revision,
                                control='CalculateButton')

    def test_command_applies_remote_result_before_snapshot_and_client_continuation(self):
        messages = []
        session, port, server, requests = self.setup_form(output=messages.append)
        initial = session.open()
        result = self.command(session)
        self.assertEqual(dict(result.attributes)['Result'], Decimal(61))
        self.assertEqual(dict(initial.attributes)['Result'], Decimal(0))
        self.assertEqual(result.revision, 2)
        self.assertEqual(messages, ['server total', 'client result 61'])
        self.assertEqual(session.messages, tuple(messages))
        self.assertFalse(port.uncertain)
        self.assertEqual(session.interpreter.server_routines['remotetotal'].body, [])
        self.assertNotIn('calculate', session.interpreter.server_routines)
        self.assertTrue(server._interpreter.server_routines['calculate'].body)
        frame = decode_line(requests[0])
        self.assertEqual(frame['arguments'], [{'type': 'Number', 'value': '20.10'},
                                             {'type': 'Number', 'value': '3'}])
        self.assertEqual(set(frame), {'protocol', 'id', 'endpoint', 'arguments'})
        self.assertNotIn(b'Calculate', requests[0])

    def test_real_separate_process_calculates_form_result_without_client_server_body(self):
        child = '''import sys
from yadinassi.invocation import InvocationServer
server = InvocationServer(%r, {1: 'Calculate'})
sys.stdout.buffer.write(server.exchange(sys.stdin.buffer.readline(131073)))
''' % SERVER
        requests = []
        def exchange(raw):
            requests.append(raw)
            result = subprocess.run([sys.executable, '-c', child], input=raw, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=10, cwd=ROOT,
                env={**os.environ, 'PYTHONPATH': os.pathsep.join([str(ROOT), os.environ.get('PYTHONPATH', '')]),
                     'PYTHONIOENCODING': 'utf-8'})
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            return result.stdout
        session = form(); port = InvocationPort(exchange); port.bind_form(session, BINDING)
        session.open()
        self.assertEqual(dict(self.command(session).attributes)['Result'], Decimal(61))
        self.assertEqual(session.messages, ('server total', 'client result 61'))
        self.assertEqual(session.interpreter.server_routines['remotetotal'].body, [])
        self.assertEqual(len(requests), 1)

    def test_edits_and_repeated_commands_use_current_values_and_reject_stale_click(self):
        session, port, server, requests = self.setup_form(); session.open()
        self.command(session, revision=1)
        with self.assertRaises(ValueError): self.command(session, revision=1)
        self.assertEqual(len(requests), 1)
        session.dispatch('change', revision=2, control='PriceField', value=Decimal(7))
        result = self.command(session, revision=3)
        self.assertEqual(dict(result.attributes)['Result'], Decimal('21.70'))
        self.assertEqual([decode_line(raw)['id'] for raw in requests], [1, 2])
        self.assertFalse(port.uncertain)

    def test_catchable_server_error_preserves_client_state_and_server_messages(self):
        source = SOURCE.replace(COMMAND, '''ThisObject.Status = "before";
Try
    ThisObject.Result = RemoteTotal(ThisObject.Price, ThisObject.Quantity);
Except
    ThisObject.Status = "caught";
EndTry;''')
        failing = SERVER.replace('Return Price * Quantity;', 'Raise "private server detail";')
        session, port, server, requests = self.setup_form(source=source, server_source=failing)
        session.open(); result = self.command(session)
        self.assertEqual(dict(result.attributes)['Status'], 'caught')
        self.assertEqual(dict(result.attributes)['Result'], Decimal(0))
        self.assertEqual(session.messages, ('server total',))
        self.assertFalse(port.uncertain)
        self.assertEqual(result.revision, 2)

    def test_lost_response_retains_prior_state_and_blocks_retry_but_allows_close(self):
        def lose(server, raw):
            server.exchange(raw)
            raise OSError('lost')
        source = SOURCE.replace(COMMAND, 'ThisObject.Status = "started";\n' + COMMAND)
        session, port, server, requests = self.setup_form(source=source, exchange=lose)
        session.open()
        with self.assertRaisesRegex(BSLError, 'outcome_unknown'): self.command(session)
        self.assertEqual(dict(session.snapshot().attributes)['Status'], 'started')
        self.assertEqual(dict(session.snapshot().attributes)['Result'], Decimal(0))
        self.assertEqual(session.revision, 2)
        with self.assertRaisesRegex(BSLError, 'outcome_unknown'): self.command(session)
        self.assertEqual(len(requests), 1)
        self.assertTrue(port.uncertain)
        self.assertFalse(session._busy)
        self.assertEqual(session.dispatch('close', revision=3).state, 'closed')

    def test_cancellation_releases_form_gate_but_never_replays_remote_effect(self):
        for cancellation in (KeyboardInterrupt(), CancelledError()):
            with self.subTest(cancellation=type(cancellation).__name__):
                def cancel(server, raw):
                    server.exchange(raw)
                    raise cancellation
                session, port, server, requests = self.setup_form(exchange=cancel)
                session.open()
                with self.assertRaises(type(cancellation)) as raised: self.command(session)
                self.assertIs(raised.exception, cancellation)
                self.assertTrue(port.uncertain)
                self.assertFalse(session._busy)
                self.assertEqual(session.snapshot().revision, 2)
                with self.assertRaisesRegex(BSLError, 'outcome_unknown'): self.command(session)
                self.assertEqual(len(requests), 1)

    def test_output_cancellation_keeps_partial_message_but_no_result_or_retry(self):
        cancellation = CancelledError()
        def output(message): raise cancellation
        session, port, server, requests = self.setup_form(output=output); session.open()
        with self.assertRaises(CancelledError) as raised: self.command(session)
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(session.messages, ('server total',))
        self.assertEqual(dict(session.snapshot().attributes)['Result'], Decimal(0))
        self.assertTrue(port.uncertain)
        with self.assertRaisesRegex(BSLError, 'outcome_unknown'): self.command(session)
        self.assertEqual(len(requests), 1)

    def test_exchange_cannot_reenter_event_snapshot_or_binding(self):
        def exchange(server, raw):
            with self.assertRaises(ValueError): self.command(session)
            with self.assertRaises(ValueError): session.snapshot()
            with self.assertRaises(ValueError): port.bind_form(session, InvocationBinding('Later', 1, ('P', 'Q')))
            return server.exchange(raw)
        session, port, server, requests = self.setup_form(exchange=exchange); session.open()
        self.assertEqual(dict(self.command(session).attributes)['Result'], Decimal(61))
        self.assertEqual(len(requests), 1)
        self.assertNotIn('later', session.interpreter.server_routines)

    def test_binding_rejects_collisions_without_partial_registration(self):
        session = form('Var ModuleValue;\n' + SOURCE); port = InvocationPort(lambda raw: raw)
        for name in ('Price', 'PRICE', 'ModuleValue', 'Create', 'CalculateCommand', 'Items', 'Title', 'Message', 'ChangeAttributes'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                port.bind_form(session, InvocationBinding(name, 1, ()))
        self.assertEqual(session.interpreter._invocation_bindings, {})
        port.bind_form(session, BINDING)
        with self.assertRaises(ValueError): port.bind_form(session, BINDING)
        self.assertEqual(set(session.interpreter._invocation_bindings), {'remotetotal'})

    def test_only_exact_form_and_binding_types_are_accepted(self):
        class FormSubclass(FormSession): pass
        class BindingSubclass(InvocationBinding): pass
        port = InvocationPort(lambda raw: raw)
        for target in (Interpreter(), object(), FormSubclass('')):
            with self.assertRaises(TypeError): port.bind_form(target, BINDING)
        session = form()
        with self.assertRaises(TypeError): port.bind_form(session, BindingSubclass('Remote', 1, ()))
        with self.assertRaises(TypeError): port.bind(session.interpreter, BINDING)
        self.assertEqual(session.interpreter._invocation_bindings, {})

    def test_binding_requires_idle_created_session_and_does_not_unlock_foreign_gate(self):
        session = form(); port = InvocationPort(lambda raw: raw)
        session._gate.acquire()
        try:
            with self.assertRaises(ValueError): port.bind_form(session, BINDING)
            self.assertTrue(session._gate.locked())
        finally: session._gate.release()
        session.open()
        with self.assertRaises(ValueError): port.bind_form(session, BINDING)
        session.dispatch('close', revision=1)
        with self.assertRaises(ValueError): port.bind_form(session, BINDING)
        self.assertEqual(session.interpreter._invocation_bindings, {})
        self.assertFalse(session._gate.locked())

    def test_dynamic_attribute_cannot_shadow_bound_alias(self):
        source = SOURCE.replace('F = Items.Add', '''A = New Array;
A.Add(New FormAttribute("RemoteTotal", New TypeDescription("Number")));
Try ChangeAttributes(A); Except EndTry;
F = Items.Add''')
        session, port, server, requests = self.setup_form(source=source); session.open()
        self.assertNotIn('remotetotal', session.form._attributes)
        self.assertEqual(dict(self.command(session).attributes)['Result'], Decimal(61))

    def test_local_server_cannot_dispatch_remote_alias_or_evaluate_its_arguments(self):
        source = SOURCE.replace('F = Items.Add', 'RemoteTotal(Effect(), 3);\nF = Items.Add') + '''
&AtServer
Function Effect() Message("must not run"); Return 2; EndFunction'''
        session, port, server, requests = self.setup_form(source=source)
        with self.assertRaises(BSLError): session.open()
        self.assertEqual(session.messages, ())
        self.assertEqual(requests, [])
        self.assertEqual(session.state, 'failed')
        self.assertFalse(port.uncertain)

    def test_form_objects_and_bare_static_attribute_references_do_not_cross(self):
        for argument in ('ThisObject', 'Items', 'Price'):
            with self.subTest(argument=argument):
                source = SOURCE.replace('RemoteTotal(ThisObject.Price,', 'RemoteTotal(' + argument + ',')
                session, port, server, requests = self.setup_form(source=source); session.open()
                with self.assertRaises(BSLError): self.command(session)
                self.assertEqual(requests, [])
                self.assertFalse(port.uncertain)
                self.assertEqual(dict(session.snapshot().attributes)['Result'], Decimal(0))

    def test_client_open_can_resume_with_remote_value_before_first_snapshot(self):
        source = SOURCE + '''&AtClient
Procedure Open(Cancel)
    ThisObject.Result = RemoteTotal(ThisObject.Price, ThisObject.Quantity);
EndProcedure'''
        session = FormSession(source, attributes=tuple(BSLFormAttribute(key, BSLTypeDescription('Number'))
            for key in ('Price', 'Quantity', 'Result')), initial_values={'Price': Decimal(4), 'Quantity': Decimal(5)},
            bindings={'OnCreateAtServer': 'Create', 'OnOpen': 'Open'})
        server = InvocationServer(SERVER, {1: 'Calculate'}); port = InvocationPort(server.exchange)
        port.bind_form(session, BINDING)
        first = session.open()
        self.assertEqual(dict(first.attributes)['Result'], Decimal(20))
        self.assertEqual(first.revision, 1)
        self.assertEqual(session.messages, ('server total',))

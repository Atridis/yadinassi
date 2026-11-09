"""Scalar client/server calls, including a real process boundary; no network/1C."""
from asyncio import CancelledError
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from yadinassi import BSLError, Interpreter
from yadinassi.dates import BSLDate, TICKS_PER_SECOND
from yadinassi.invocation import (InvocationBinding, InvocationError,
    InvocationPort, InvocationServer, MAX_CALLS, PROTOCOL)
from yadinassi.ui.protocol import decode_line, encode_line
from yadinassi.values import BSLArray, NULL

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''&AtServerNoContext
Function Total(Val Price, Val Quantity)
    Message("server total");
    Return Price * Quantity;
EndFunction
&AtServerNoContext
Function Echo(Val Value)
    Return Value;
EndFunction
&AtServerNoContext
Procedure Announce(Val Text)
    Message(Text);
EndProcedure
&AtServerNoContext
Function Fail(Val Text)
    Message("before error");
    Raise Text;
EndFunction
'''


class InvocationPortTests(unittest.TestCase):
    def setup_port(self, exchange=None):
        server = InvocationServer(SOURCE, {1: 'Total', 2: 'Echo', 3: 'Announce', 4: 'Fail'})
        seen = []
        def transport(raw):
            seen.append(raw)
            return server.exchange(raw) if exchange is None else exchange(server, raw)
        messages = []
        client = Interpreter(messages.append)
        port = InvocationPort(transport)
        for binding in server.bindings: port.bind(client, binding)
        return client, server, port, seen, messages

    def test_client_expression_resumes_after_server_result_and_messages(self):
        client, server, port, seen, messages = self.setup_port()
        client.execute('Message(Total(10.25, 2) + 0.50);')
        self.assertEqual(messages, ['server total', '21'])
        self.assertEqual(client.execution_context, 'client')
        self.assertTrue(client._has_module_context)
        self.assertFalse(port.uncertain)
        self.assertEqual(len(seen), 1)
        self.assertEqual(decode_line(seen[0]), {'protocol': PROTOCOL, 'id': 1,
            'endpoint': 1, 'arguments': [{'type': 'Number', 'value': '10.25'}, {'type': 'Number', 'value': '2'}]})
        self.assertEqual(client.server_routines['total'].body, [])
        self.assertTrue(server._interpreter.server_routines['total'].body)

    def test_by_value_arguments_keep_existing_left_to_right_late_name_reads(self):
        client, unused, port, seen, messages = self.setup_port()
        client.execute('''Function Change(X)
X=7; Return 2;
EndFunction
X=3; Message(Total(X,Change(X))); Message(X);''')
        self.assertEqual(messages, ['server total', '14', '7'])
        self.assertEqual(decode_line(seen[0])['arguments'][0]['value'], '7')

    def test_scalar_codec_preserves_decimal_date_null_and_unicode(self):
        client, unused, port, unused_seen, unused_messages = self.setup_port()
        binding = InvocationBinding('Echo', 2, ('Value',))
        values = [None, NULL, True, False, '', 'Привет\n世界', Decimal('-0.00'),
                  Decimal('123456789012345678901234567890.123456789'), BSLDate(12345*TICKS_PER_SECOND)]
        for value in values:
            with self.subTest(value=value):
                result = port.invoke(binding, [value])
                self.assertIs(type(result), type(value))
                if isinstance(value, Decimal): self.assertEqual(result.as_tuple(), value.as_tuple())
                else: self.assertEqual(result, value)

    def test_procedure_is_callable_only_without_result(self):
        client, unused, port, seen, messages = self.setup_port()
        client.execute('Announce("hello");')
        self.assertEqual(messages, ['hello'])
        with self.assertRaises(BSLError): client.execute('X=Announce("no");')
        self.assertEqual(len(seen), 1)

    def test_unsupported_inputs_reject_before_transport_and_next_valid_call_works(self):
        client, unused, port, seen, messages = self.setup_port()
        binding = InvocationBinding('Echo', 2, ('Value',))
        for value in [BSLArray(), object(), BSLDate(1), Decimal('NaN'), 'x'*8193]:
            with self.subTest(value=type(value)):
                with self.assertRaisesRegex(InvocationError, 'invalid_arguments'):
                    port.invoke(binding, [value])
        self.assertEqual(seen, [])
        self.assertFalse(port.uncertain)
        self.assertEqual(client.execute('Echo(42)'), Decimal(42))
        self.assertEqual(decode_line(seen[0])['id'], 1)

    def test_arity_rejects_before_argument_effects(self):
        client, unused, port, seen, messages = self.setup_port()
        client.execute('Function Effect() Message("effect"); Return 1; EndFunction')
        with self.assertRaises(BSLError): client.execute('Total(Effect())')
        self.assertEqual(seen, [])
        self.assertEqual(messages, [])

    def test_server_errors_are_catchable_finite_and_do_not_discard_prior_messages(self):
        client, unused, port, seen, messages = self.setup_port()
        client.variables['text'] = '/private/server/path'
        client.execute('Try Fail(Text); Except Message(ErrorDescription()); EndTry; Message(Echo(8));')
        self.assertEqual(messages[0], 'before error')
        self.assertIn('server_error', messages[1])
        self.assertNotIn('/private/server/path', messages[1])
        self.assertEqual(messages[2], '8')
        self.assertFalse(port.uncertain)
        self.assertEqual(len(seen), 2)

    def test_lost_reply_never_replays_and_locks_even_when_bsl_catches_failure(self):
        dispatched = []
        def lose(server, raw):
            dispatched.append(server.exchange(raw))
            raise OSError('/private/transport')
        client, unused, port, seen, messages = self.setup_port(lose)
        client.execute('Try Total(3,4); Except Message("caught"); EndTry;')
        with self.assertRaises(BSLError): client.execute('Total(3,4)')
        self.assertTrue(port.uncertain)
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(messages, ['caught'])

    def test_malformed_or_wrong_id_response_locks_without_publishing_messages(self):
        alters = [lambda r: {**r, 'id': True}, lambda r: {**r, 'id': r['id']+1},
                  lambda r: {**r, 'extra': 1}, lambda r: {**r, 'value': {'type':'Number', 'value':'NaN'}},
                  lambda r: {**r, 'messages': ['admitted', 5]}, lambda r: {**r, 'status':'unexpected'}]
        for alter in alters:
            with self.subTest(alter=alter):
                def exchange(server, raw): return encode_line(alter(decode_line(server.exchange(raw))))
                client, unused, port, seen, messages = self.setup_port(exchange)
                with self.assertRaisesRegex(BSLError, 'outcome_unknown'): client.execute('Total(1,2)')
                self.assertTrue(port.uncertain)
                self.assertEqual(messages, [])

    def test_server_unsupported_result_has_explicit_uncertain_outcome(self):
        server = InvocationServer('&AtServerNoContext\nFunction NewValue() Return New Array; EndFunction', {1:'NewValue'})
        client = Interpreter()
        port = InvocationPort(server.exchange)
        port.bind(client, server.bindings[0])
        with self.assertRaisesRegex(BSLError, 'result_unavailable'): client.execute('NewValue()')
        self.assertTrue(port.uncertain)

    def test_message_delivery_failure_does_not_retry_server(self):
        client, unused, port, seen, unused_messages = self.setup_port()
        with self.assertRaisesRegex(InvocationError, 'outcome_unknown'):
            port.invoke(InvocationBinding('Total',1,('Price','Quantity')), [Decimal(2),Decimal(3)],
                output=mock.Mock(side_effect=RuntimeError('delivery failed')))
        self.assertEqual(len(seen), 1)
        self.assertTrue(port.uncertain)

    def test_cancellation_after_server_effect_locks_port_and_propagates_unchanged(self):
        for kind in (KeyboardInterrupt, CancelledError, SystemExit, GeneratorExit):
            with self.subTest(cancellation=kind):
                cancellation = kind('cancelled')
                completed = []
                def exchange(server, raw):
                    completed.append(server.exchange(raw))
                    raise cancellation
                client, server, port, seen, messages = self.setup_port(exchange)
                binding = InvocationBinding('Total', 1, ('Price', 'Quantity'))
                with self.assertRaises(kind) as raised:
                    port.invoke(binding, [Decimal(2), Decimal(3)])
                self.assertIs(raised.exception, cancellation)
                self.assertEqual(decode_line(completed[0])['value'], {'type': 'Number', 'value': '6'})
                self.assertTrue(port.uncertain)
                self.assertFalse(port._gate.locked())
                with self.assertRaisesRegex(InvocationError, '^outcome_unknown$'):
                    port.invoke(binding, [Decimal(2), Decimal(3)])
                self.assertEqual(len(seen), 1)
                self.assertEqual(server._requests, 1)
                self.assertEqual(messages, [])

    def test_cancellation_during_output_locks_port_without_repeating_delivery(self):
        for kind in (KeyboardInterrupt, CancelledError, SystemExit, GeneratorExit):
            with self.subTest(cancellation=kind):
                cancellation = kind('cancelled')
                client, server, port, seen, messages = self.setup_port()
                binding = InvocationBinding('Total', 1, ('Price', 'Quantity'))
                def output(message):
                    messages.append(message)
                    raise cancellation
                with self.assertRaises(kind) as raised:
                    port.invoke(binding, [Decimal(2), Decimal(3)], output=output)
                self.assertIs(raised.exception, cancellation)
                self.assertTrue(port.uncertain)
                self.assertFalse(port._gate.locked())
                with self.assertRaisesRegex(InvocationError, '^outcome_unknown$'):
                    port.invoke(binding, [Decimal(2), Decimal(3)], output=output)
                self.assertEqual(len(seen), 1)
                self.assertEqual(server._requests, 1)
                self.assertEqual(messages, ['server total'])

    def test_cancellation_before_exchange_does_not_poison_an_unsent_call(self):
        for kind in (KeyboardInterrupt, CancelledError):
            with self.subTest(cancellation=kind):
                cancellation = kind('cancelled')
                client, server, port, seen, messages = self.setup_port()
                binding = InvocationBinding('Echo', 2, ('Value',))
                with mock.patch('yadinassi.invocation._encode_scalar', side_effect=cancellation):
                    with self.assertRaises(kind) as raised:
                        port.invoke(binding, [Decimal(7)])
                self.assertIs(raised.exception, cancellation)
                self.assertFalse(port.uncertain)
                self.assertFalse(port._gate.locked())
                self.assertEqual(seen, [])
                self.assertEqual(port.invoke(binding, [Decimal(7)]), Decimal(7))
                self.assertEqual(decode_line(seen[0])['id'], 1)

    def test_reentrant_call_is_rejected_without_poisoning_outer_result(self):
        attempts=[]
        def exchange(server, raw):
            try: port.invoke(server.bindings[1], [Decimal(99)])
            except InvocationError as error: attempts.append(str(error))
            return server.exchange(raw)
        client, unused, port, seen, messages = self.setup_port(exchange)
        self.assertEqual(client.execute('Echo(7)'), Decimal(7))
        self.assertEqual(attempts, ['busy'])
        self.assertFalse(port.uncertain)
        self.assertEqual(len(seen), 1)

    def test_remote_stub_cannot_be_called_from_local_server_before_argument_effects(self):
        client, unused, port, seen, messages = self.setup_port()
        client.execute('''&AtServerNoContext
Function Effect() Message("effect"); Return 1; EndFunction
&AtServerNoContext
Function LocalServer() Return Echo(Effect()); EndFunction''')
        with self.assertRaisesRegex(BSLError, 'логического клиента'): client.execute('LocalServer()')
        self.assertEqual(seen, [])
        self.assertEqual(messages, [])

    def test_existing_local_direct_calls_still_work_without_port(self):
        messages=[]
        client=Interpreter(messages.append)
        client.execute(SOURCE)
        self.assertEqual(client.execute('Total(2,3)'), Decimal(6))
        self.assertEqual(messages, ['server total'])

    def test_client_binding_is_host_only_and_cannot_replace_an_existing_name(self):
        client, unused, port, seen, messages = self.setup_port()
        for binding in [InvocationBinding('Echo', 2, ('Value',)), InvocationBinding('Message',1,())]:
            with self.assertRaises(ValueError): port.bind(client,binding)
        with self.assertRaises(TypeError): port.bind(object(),InvocationBinding('Allowed',1,()))
        self.assertEqual(seen, [])

    def test_binding_rejects_noncanonical_or_executable_descriptors(self):
        for args in [('X; Message(1)',1,()), ('X',True,()), ('X',65,()), ('X',1,['a']),
                     ('X',1,('a','A')), ('X',1,('a)',)), ('X',1,tuple('p'+str(n) for n in range(33)))]:
            with self.subTest(args=args), self.assertRaises(ValueError): InvocationBinding(*args)

    def test_client_request_limit_is_local_and_does_not_dispatch(self):
        client, unused, port, seen, messages = self.setup_port()
        port._counter=MAX_CALLS
        with self.assertRaisesRegex(BSLError,'request_limit'): client.execute('Echo(1)')
        self.assertEqual(seen, [])
        self.assertFalse(port.uncertain)

    def test_real_separate_process_returns_result_without_loading_server_body_on_client(self):
        child = '''import sys
from yadinassi.invocation import InvocationServer
server=InvocationServer("&AtServerNoContext\\nFunction Calculate(Val X) Return X * 3; EndFunction", {1:"Calculate"})
sys.stdout.buffer.write(server.exchange(sys.stdin.buffer.readline(131073)))
'''
        transmissions=[]
        def exchange(raw):
            transmissions.append(raw)
            completed=subprocess.run([sys.executable,'-c',child],input=raw,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,timeout=10,cwd=ROOT,
                env={**os.environ,'PYTHONPATH':os.pathsep.join([str(ROOT),os.environ.get('PYTHONPATH','')]),
                     'PYTHONIOENCODING':'utf-8'})
            self.assertEqual(completed.returncode,0,completed.stderr.decode('utf-8','replace'))
            return completed.stdout
        messages=[]
        client=Interpreter(messages.append)
        port=InvocationPort(exchange)
        port.bind(client,InvocationBinding('ServerTotal',1,('Price',)))
        client.execute('Message(ServerTotal(20.10)+0.70);')
        self.assertEqual(messages,['61'])
        self.assertEqual(client.server_routines['servertotal'].body,[])
        self.assertNotIn('calculate',client.server_routines)
        self.assertEqual(set(decode_line(transmissions[0])),{'protocol','id','endpoint','arguments'})
        self.assertNotIn(b'Calculate',transmissions[0])


class InvocationServerTests(unittest.TestCase):
    def setUp(self):
        self.server=InvocationServer(SOURCE,{1:'Total',2:'Echo'})

    def request(self,**changes):
        request={'protocol':PROTOCOL,'id':1,'endpoint':2,'arguments':[{'type':'String','value':'hello'}]}
        request.update(changes)
        return decode_line(self.server.exchange(encode_line(request)))

    def test_replay_does_not_repeat_server_effects(self):
        args=[{'type':'Number','value':'1'},{'type':'Number','value':'2'}]
        first=self.request(endpoint=1,arguments=args)
        repeated=self.request(endpoint=1,arguments=args)
        self.assertEqual(first['messages'],['server total'])
        self.assertEqual(repeated['reason'],'sequence')
        self.assertEqual(repeated['messages'],[])
        self.assertEqual(self.request(id=2)['status'],'ok')

    def test_request_envelope_rejects_extra_fields_bool_ids_and_duplicate_json(self):
        for changes in [{'id':True},{'endpoint':'Echo'},{'source':'Message(1)'},{'path':'database.sqlite'},
                        {'protocol':'other'},{'arguments':{}},{'endpoint':True}]:
            with self.subTest(changes=changes): self.assertEqual(self.request(**changes)['reason'],'invalid_request')
        self.assertEqual(decode_line(self.server.exchange(b'{"id":1,"id":2}'))['reason'],'invalid_request')
        self.assertEqual(self.server._requests,0)

    def test_unknown_endpoint_and_invalid_arguments_are_not_dispatched(self):
        self.assertEqual(self.request(endpoint=64)['reason'],'unknown_endpoint')
        self.assertEqual(self.request(id=2,arguments=[])['reason'],'invalid_arguments')
        self.assertEqual(self.request(id=3,arguments=[{'type':'CatalogRef','catalog':'11111111-1111-4111-8111-111111111111',
            'record':'22222222-2222-4222-8222-222222222222'}])['reason'],'invalid_arguments')
        self.assertEqual(self.server._messages,[])
        self.assertEqual(self.request(id=4)['value'],{'type':'String','value':'hello'})

    def test_module_admission_never_executes_root_or_accepts_contextful_export(self):
        for source in ['Message("root");\n'+SOURCE, '&AtServer\nFunction X() Return 1; EndFunction',
                       '&AtClient\nFunction X() Return 1; EndFunction',
                       '&AtServerNoContext\nFunction X(Value) Return Value; EndFunction',
                       '&AtServerNoContext\nFunction X(Val Value=1) Return Value; EndFunction']:
            with self.subTest(source=source),self.assertRaises(ValueError): InvocationServer(source,{1:'X'})

    def test_nested_server_helpers_are_local_and_no_client_variables_leak(self):
        server=InvocationServer('''&AtServerNoContext
Function Inner(Val X) Return X+1; EndFunction
&AtServerNoContext
Function Outer(Val X) Return Inner(X); EndFunction
&AtServerNoContext
Function ReadClient() Return Secret; EndFunction''',{1:'Outer',2:'ReadClient'})
        client=Interpreter();port=InvocationPort(server.exchange)
        for binding in server.bindings: port.bind(client,binding)
        client.execute('Secret=123;')
        self.assertEqual(client.execute('Outer(2)'),Decimal(3))
        with self.assertRaisesRegex(BSLError,'server_error'): client.execute('ReadClient()')
        self.assertEqual(client.execute('Secret'),Decimal(123))

    def test_server_busy_and_request_limits_never_run_an_endpoint(self):
        self.server._gate.acquire()
        try: self.assertEqual(self.request()['reason'],'busy')
        finally: self.server._gate.release()
        self.server._requests=MAX_CALLS
        self.assertEqual(self.request()['reason'],'request_limit')
        self.assertEqual(self.server._messages,[])

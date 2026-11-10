"""Configuration XML -> independent BSL -> OpenForm -> retained UI sessions."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest import mock
from scripts import entrypoint

from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.ui.configuration_app import (ConfigurationBroker, ConfigurationController,
    ConfigurationProcess, PROTOCOL, load_application, serve_runtime, _parameters)
from yadinassi.ui.local_app import LocalTransportError
from yadinassi.ui.protocol import decode_line, encode_line
from yadinassi.structures import BSLStructure
from test_configuration_forms import sources

ROOT = Path(__file__).resolve().parents[1] / 'examples/configuration-forms'


class ConfigurationApplicationTests(unittest.TestCase):
    def setup_app(self, app='welcome', *, files=None, initial_form=None):
        configuration = load_configuration_forms(sources(app) if files is None else files)
        broker = ConfigurationBroker(configuration); self.addCleanup(broker.close)
        def pipe(raw):
            request = decode_line(raw)
            result = broker.exchange({key: request[key] for key in ('operation', 'session', 'payload')})
            return encode_line({'id': request['id'], 'session': request['session'], 'result': result, 'error': None})
        controller = ConfigurationController(configuration, pipe, initial_form=initial_form)
        return broker, controller

    def rpc(self, controller, method, **params):
        return controller.exchange({'jsonrpc': '2.0', 'id': 1, 'method': 'application.'+method, 'params': params})['result']

    def open(self, controller, name='CommonForm.Welcome', token='one'):
        self.rpc(controller, 'hello', protocol=PROTOCOL)
        return self.rpc(controller, 'open', entry=controller.names[name.casefold()], request=token)

    def event(self, controller, sid, event='command', control='DetailsButton', revision=None):
        session = controller.sessions[sid][0].session
        params = {'event': event, 'revision': session.revision if revision is None else revision}
        if event != 'close': params['control'] = control
        return self.rpc(controller, 'form', session=sid, request={
            'jsonrpc': '2.0', 'id': 1, 'method': 'form.event', 'params': params})

    def test_openform_command_opens_declared_child_with_parameter_copy(self):
        broker, app = self.setup_app()
        parent = self.open(app)['session']
        result = self.event(app, parent)
        self.assertIsNone(result['error'])
        self.assertEqual(len(app.sessions), 2)
        child = app.sessions[result['state']['active']][0].session
        self.assertEqual(child.form._data['messagetext'], 'Hello from a configuration form')
        self.assertEqual(len(broker.sessions), 2)
        self.assertIsNot(child.form, broker.sessions[result['state']['active']][0].session.form)

    def test_reattach_does_not_reexecute_open_or_allocate(self):
        broker, app = self.setup_app(initial_form='CommonForm.Welcome')
        first = self.rpc(app, 'hello', protocol=PROTOCOL)
        second = self.rpc(app, 'hello', protocol=PROTOCOL)
        self.assertEqual(len(broker.sessions), 1)
        self.assertEqual(first['state'], second['state'])
        self.assertIsNone(second['form'])

    def test_duplicate_open_token_and_retired_identity_never_reopen(self):
        broker, app = self.setup_app()
        first = self.open(app)
        self.assertEqual(self.open(app)['session'], first['session'])
        self.event(app, first['session'], 'close')
        self.assertEqual(self.open(app)['error'], 'retired_session')
        self.assertEqual(broker.allocated, 1)
        self.assertNotEqual(self.open(app, token='two')['session'], first['session'])

    def test_second_configuration_runs_server_nocontext_and_sync(self):
        broker, app = self.setup_app('counter')
        sid = self.open(app, 'CommonForm.Counter')['session']
        for _ in range(3):
            result = self.event(app, sid, control='IncrementButton')
            self.assertIsNone(result['form']['result']['error'])
        self.assertEqual(str(app.sessions[sid][0].session.form._data['count']), '3')
        self.assertEqual(str(broker.sessions[sid][0].session.form._data['count']), '3')

    def test_client_and_context_nocontext_sequences_are_independent(self):
        files = sources('counter')
        module = 'CommonForms/Counter/Ext/Form/Module.bsl'
        files[module] = files[module].replace(b'IncrementAtServer();', b'LocalCount = Count;\n Count = AddOne(LocalCount);\n IncrementAtServer();')
        _, app = self.setup_app(files=files)
        sid = self.open(app, 'CommonForm.Counter')['session']
        for _ in range(2):
            self.assertIsNone(self.event(app, sid, control='IncrementButton')['form']['result']['error'])
        self.assertEqual(str(app.sessions[sid][0].session.form._data['count']), '4')

    def test_renderer_cannot_choose_source_name_or_parameters(self):
        _, app = self.setup_app()
        self.rpc(app, 'hello', protocol=PROTOCOL)
        for params in ({'entry': 'CommonForm.Welcome', 'request': 'x'},
                       {'entry': 1, 'request': 'x', 'parameters': {}},
                       {'entry': 1, 'request': 'x', 'source': 'code'}):
            with self.assertRaises(ValueError): self.rpc(app, 'open', **params)

    def test_closed_form_removes_only_owned_session(self):
        broker, app = self.setup_app()
        one = self.open(app)['session']; two = self.open(app, token='two')['session']
        self.event(app, one, 'close')
        self.assertEqual(list(app.sessions), [two])
        self.assertEqual(list(broker.sessions), [two])
        self.assertEqual(self.rpc(app, 'close')['error'], 'forms_open')
        self.event(app, two, 'close')
        self.assertEqual(self.rpc(app, 'close')['state']['kind'], 'closed')

    def test_capacity_and_independent_forms(self):
        broker, app = self.setup_app()
        for index in range(8): self.assertIsNone(self.open(app, token=str(index))['error'])
        self.assertEqual(self.open(app, token='last')['error'], 'capacity')
        self.assertEqual(broker.allocated, 8)

    def test_failed_open_drops_child_intents_and_closes_allocated_session(self):
        files = sources()
        key = 'CommonForms/Welcome/Ext/Form.xml'
        files[key] = files[key].replace(b'</Events>', b'<Event name="OnOpen">Opened</Event></Events>')
        files['CommonForms/Welcome/Ext/Form/Module.bsl'] += b'\n&AtClient\nProcedure Opened(Cancel)\nOpenForm("CommonForm.Details");\nCancel = True;\nEndProcedure'
        broker, app = self.setup_app(files=files)
        result = self.open(app)
        self.assertEqual(result['error'], 'open_failed')
        self.assertEqual(app.sessions, {})
        self.assertEqual(broker.sessions, {})
        self.assertFalse(app.pending)
        self.assertEqual(broker.allocated, 1)

    def test_stale_command_does_not_open_child_twice(self):
        _, app = self.setup_app()
        sid = self.open(app)['session']; revision = app.sessions[sid][0].session.revision
        self.event(app, sid, revision=revision)
        result = self.event(app, sid, revision=revision)
        self.assertEqual(result['form']['result']['error'], 'stale_revision')
        self.assertEqual(len(app.sessions), 2)

    def test_bad_transport_locks_all_and_never_replays(self):
        _, app = self.setup_app(); sid = self.open(app)['session']
        calls = []
        def lost(raw): calls.append(raw); raise OSError('lost')
        app.transport = lost
        with self.assertRaises(LocalTransportError): self.event(app, sid)
        self.assertTrue(app.uncertain)
        self.assertTrue(self.rpc(app, 'snapshot')['state']['uncertain'])
        self.assertEqual(len(calls), 1)

    def test_source_change_between_processes_refuses_before_creation(self):
        broker, app = self.setup_app()
        other = load_configuration_forms(sources('counter'))
        app.configuration = other
        with self.assertRaises(LocalTransportError): self.rpc(app, 'hello', protocol=PROTOCOL)
        self.assertEqual(broker.allocated, 0)
        self.assertTrue(app.uncertain)

    def test_bounded_scalar_parameters_reject_handles(self):
        self.assertEqual(_parameters(BSLStructure('Message', 'hello')), {'Message': 'hello'})
        for params in ({'Value': BSLStructure()}, {'A': 1, 'a': 2}, {'Bad-Key': None}, {'K'+str(i): None for i in range(33)}):
            with self.assertRaises((TypeError, ValueError)): _parameters(params)

    def test_directory_loader_matches_exact_digest(self):
        self.assertEqual(load_application(ROOT/'welcome').source_sha256, load_configuration_forms(sources()).source_sha256)

    def test_stdio_duplicate_management_id_not_reexecuted(self):
        configuration = load_application(ROOT/'counter')
        hello = {'id': 1, 'operation': 'hello', 'session': '', 'payload': {'source': configuration.source_sha256}}
        create = {'id': 2, 'operation': 'create', 'session': '', 'payload': {'entry': 1, 'parameters': {}}}
        output = BytesIO()
        self.assertEqual(serve_runtime(ROOT/'counter', input_stream=BytesIO(encode_line(hello)+encode_line(create)+encode_line(create)), output_stream=output), 1)
        self.assertEqual(len(output.getvalue().splitlines()), 2)

    def test_real_owned_child_process(self):
        process = ConfigurationProcess(ROOT/'counter'); self.addCleanup(process.close)
        app = ConfigurationController(load_application(ROOT/'counter'), process.exchange)
        sid = self.open(app, 'CommonForm.Counter')['session']
        self.assertIsNone(self.event(app, sid, control='IncrementButton')['form']['result']['error'])
        self.assertEqual(str(app.sessions[sid][0].session.form._data['count']), '1')
        self.event(app, sid, 'close')
        self.assertEqual(self.rpc(app, 'close')['state']['kind'], 'closed')

    def test_frozen_configuration_route_is_explicit_and_first_argument_only(self):
        with mock.patch.object(entrypoint.configuration_app, 'main', return_value=6) as app, mock.patch.object(entrypoint, 'cli_main', return_value=9):
            self.assertEqual(entrypoint.main(['--configuration-ui', 'owned']), 6)
            app.assert_called_with(['owned'])
            self.assertEqual(entrypoint.main(['--configuration-ui-runtime', 'owned']), 6)
            app.assert_called_with(['--runtime', 'owned'])
            self.assertEqual(entrypoint.main(['-c', '--configuration-ui']), 9)

    def test_frozen_child_reuses_executable_without_python_mode(self):
        with mock.patch.object(ConfigurationProcess, '_start') as start, mock.patch.object(sys, 'frozen', True, create=True):
            ConfigurationProcess(ROOT/'counter', ROOT/'existing.sqlite')
            command, env = start.call_args.args
            self.assertEqual(command, [sys.executable, '--configuration-ui-runtime', str((ROOT/'counter').resolve()), '--f', str((ROOT/'existing.sqlite').resolve())])
            self.assertEqual(env['PYTHONIOENCODING'], 'utf-8')

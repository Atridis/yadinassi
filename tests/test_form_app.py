"""Runnable replicated forms: owned packages, processes, HTTP and SQLite only."""
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
import http.client
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Thread
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.database_context import SQLiteDBContext
from yadinassi.form_replication import ReplicatedFormServer
from yadinassi.ui.form_app import (FormController, FormHandler, FormProcess,
    PROTOCOL, main, serve_runtime)
from yadinassi.ui.form_package import load_client, load_server
from yadinassi.ui.local_app import LocalUIServer, LocalTransportError
from yadinassi.ui.protocol import encode_line, decode_line, MAX_LINE_BYTES
from yadinassi import launcher as entrypoint

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/forms/estimate'
PRODUCT = ROOT / 'examples/forms/product-intake'


def request(method='hello', **params):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'form.' + method,
            'params': {'protocol': PROTOCOL} if method == 'hello' else params}


def pair(directory=EXAMPLE):
    package = load_server(directory)
    server = ReplicatedFormServer(package.source, package.endpoints, handlers=package.handlers,
        attributes=package.attributes, initial_values=package.initial_values, bindings=package.lifecycle)
    return FormController(load_client(directory), server.exchange), server


def state(controller, method='hello', **params):
    return controller.exchange(request(method, **params))['result']


def event(controller, event='command', control='RunButton', **params):
    args = {'event': event, 'revision': controller.session.revision, **params}
    if event != 'close': args['control'] = control
    return state(controller, 'event', **args)


class FormPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        shutil.copytree(EXAMPLE, self.directory, dirs_exist_ok=True)

    def edit(self, side, callback):
        path = self.directory / (side + '.json')
        data = json.loads(path.read_text()); callback(data)
        path.write_text(json.dumps(data))

    def test_example_loads_separate_sources_and_signatures(self):
        client, server = load_client(self.directory), load_server(self.directory)
        self.assertNotIn('&AtServer', client.source)
        self.assertNotIn('&AtClient', server.source)
        self.assertEqual(client.bindings[0].name, 'RemoteRun')
        self.assertEqual(server.endpoints, {1: 'Run'})
        self.assertEqual(server.initial_values['Price'], Decimal('20.10'))

    def test_client_does_not_read_server_files(self):
        (self.directory / 'server.json').unlink(); (self.directory / 'server.bsl').unlink()
        self.assertTrue(load_client(self.directory).source)

    def test_server_does_not_read_client_files(self):
        (self.directory / 'client.json').unlink(); (self.directory / 'client.bsl').unlink()
        self.assertTrue(load_server(self.directory).source)

    def test_unknown_keys_and_versions_reject(self):
        self.edit('client', lambda x: x.update(path='/private/server'))
        with self.assertRaises(ValueError): load_client(self.directory)
        self.edit('server', lambda x: x.update(protocol='future'))
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_duplicate_json_and_non_utf8_reject(self):
        (self.directory / 'client.json').write_bytes(b'{"protocol":1,"protocol":2}')
        with self.assertRaises(ValueError): load_client(self.directory)
        (self.directory / 'server.bsl').write_bytes(b'\xff')
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_source_and_manifest_limits(self):
        (self.directory / 'client.bsl').write_bytes(b'x' * 65537)
        with self.assertRaises(ValueError): load_client(self.directory)
        (self.directory / 'server.json').write_bytes(b' ' * (MAX_LINE_BYTES + 1))
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_duplicate_bindings_and_attribute_names_reject(self):
        self.edit('client', lambda x: x['handlers'].append(x['handlers'][0]))
        with self.assertRaises(ValueError): load_client(self.directory)
        self.edit('server', lambda x: x['attributes'].append(x['attributes'][0]))
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_hostile_endpoint_and_scalar_shapes_reject(self):
        self.edit('server', lambda x: x['endpoints'][0].update(endpoint=True))
        with self.assertRaises(ValueError): load_server(self.directory)
        self.edit('client', lambda x: x['bindings'][0].update(parameters=['A', 'a']))
        with self.assertRaises(ValueError): load_client(self.directory)

    def test_handler_functions_and_unsupported_attribute_types_reject(self):
        self.edit('client', lambda x: x['handlers'][0].update(isFunction=True))
        with self.assertRaises(ValueError): load_client(self.directory)
        self.edit('server', lambda x: x['attributes'][0].update(type='CatalogRef'))
        with self.assertRaises(ValueError): load_server(self.directory)


class FormControllerTests(unittest.TestCase):
    def setUp(self): self.controller, self.server = pair()

    def test_bootstrap_projection_exposes_no_source_signatures_or_paths(self):
        result = state(self.controller)
        self.assertEqual(result['error'], None)
        self.assertEqual(result['state']['kind'], 'form')
        self.assertEqual(len(result['state']['items']), 5)
        raw = encode_line(result)
        for private in (b'Procedure', b'endpoint', b'client.bsl', b'database', b'Create(Cancel'):
            self.assertNotIn(private, raw)
        self.assertEqual(result['state']['items'][0]['value'], {'type':'Number','value':'20.10'})

    def test_edit_command_barrier_and_client_continuation(self):
        state(self.controller)
        result = event(self.controller, 'change', 'FieldPrice', value={'type':'Number','value':'7.25'})
        self.assertEqual(self.server.session.form._data['price'], Decimal('20.10'))
        result = event(self.controller)
        self.assertEqual(self.server.session.form._data['price'], Decimal('7.25'))
        total = next(x for x in result['state']['items'] if x['name'] == 'FieldTotal')
        self.assertEqual(total['value'], {'type':'Number','value':'21.75'})
        self.assertEqual(result['state']['messages'], ['Calculated on the server'])

    def test_repeat_hello_and_snapshot_do_not_reopen_or_repeat_commands(self):
        first = state(self.controller); sequence = self.controller.session.client_sequence
        self.assertEqual(state(self.controller), first)
        self.assertEqual(state(self.controller, 'snapshot'), first)
        self.assertEqual(self.controller.session.client_sequence, sequence)

    def test_duplicate_or_stale_command_does_not_cross_transport(self):
        state(self.controller); revision = self.controller.session.revision
        event(self.controller); sequence = self.controller.session.client_sequence
        result = state(self.controller, 'event', event='command', revision=revision, control='RunButton')
        self.assertEqual(result['error'], 'stale_revision')
        self.assertEqual(self.controller.session.client_sequence, sequence)

    def test_close_cancellation_then_success(self):
        state(self.controller)
        event(self.controller, 'change', 'FieldPrice', value={'type':'Number','value':'3'})
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'form')
        event(self.controller)
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'closed')
        self.assertTrue(self.server.session.closed)

    def test_renderer_cannot_select_routine_or_package(self):
        state(self.controller)
        for fields in ({'routine':'Run'}, {'endpoint':1}, {'database':'private'}, {'source':'Message(1)'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                state(self.controller, 'event', event='command', revision=1, control='RunButton', **fields)
        self.assertEqual(self.controller.session.client_sequence, 1)

    def test_hidden_readonly_or_wrong_kind_controls_cannot_mutate(self):
        state(self.controller)
        for control in ('Dirty', 'FieldTotal', 'RunButton', 'Missing'):
            result = event(self.controller, 'change', control, value={'type':'Number','value':'9'})
            self.assertEqual(result['error'], 'event_failed')
        self.assertEqual(self.server.session.form._data['total'], Decimal(0))

    def test_lost_response_locks_without_automatic_replay(self):
        state(self.controller)
        original = self.controller.session._exchange; calls=[]
        def lost(raw):
            calls.append(raw); original(raw); raise OSError('private transport details')
        self.controller.session._exchange = lost
        result = event(self.controller)
        self.assertEqual(result['error'], 'outcome_unknown')
        self.assertTrue(result['state']['uncertain'])
        self.assertEqual(event(self.controller)['error'], 'outcome_unknown')
        self.assertTrue(state(self.controller, 'snapshot')['state']['uncertain'])
        self.assertEqual(len(calls), 1)

    def test_server_error_keeps_authoritative_state_and_finite_reason(self):
        state(self.controller)
        original = self.server._routines[1]
        from yadinassi.syntax.parser import parse
        self.server._routines[1] = parse('&AtServer\nProcedure Run() ThisObject.Status="partial"; Raise "private"; EndProcedure')[0]
        result = event(self.controller)
        self.assertEqual(result['error'], 'event_failed')
        self.assertFalse(result['state']['uncertain'])
        self.assertIn({'type':'String','value':'partial'}, [x['value'] for x in result['state']['items']])
        self.assertNotIn(b'private', encode_line(result))
        self.server._routines[1] = original
        self.assertIsNone(event(self.controller)['error'])

    def test_failed_open_is_not_retried_on_reattach(self):
        calls=[]
        def failed(raw): calls.append(raw); return b'broken\n'
        controller=FormController(load_client(EXAMPLE), failed)
        result=state(controller)
        self.assertEqual(result['error'], 'outcome_unknown')
        state(controller); state(controller, 'snapshot')
        self.assertEqual(len(calls),1)

    def test_concurrent_exchange_and_prehello_snapshot_reject(self):
        with self.assertRaises(ValueError): state(self.controller,'snapshot')
        self.controller._gate.acquire()
        try:
            with self.assertRaises(LocalTransportError): state(self.controller)
        finally: self.controller._gate.release()

    def test_exact_request_and_value_admission(self):
        state(self.controller)
        for request_value in (True, 1.2, '1'):
            with self.assertRaises(ValueError):
                state(self.controller,'event',event='close',revision=request_value)
        with self.assertRaises(ValueError):
            event(self.controller,'change','FieldPrice',value={'type':'Number','value':1.2})


class FormProcessTests(unittest.TestCase):
    def process(self, directory=EXAMPLE, database=None):
        value = FormProcess(directory, database); self.addCleanup(value.close); return value

    def test_actual_separate_process_calculation_and_owned_cleanup(self):
        process=self.process(); controller=FormController(load_client(EXAMPLE),process.exchange)
        state(controller); result=event(controller)
        self.assertIsNone(result['error'])
        self.assertIsNone(controller.session.interpreter.database_context)
        self.assertEqual(next(x for x in result['state']['items'] if x['name']=='FieldTotal')['value']['value'],'60.30')
        event(controller,'close'); process.close()
        self.assertIsNotNone(process.child.poll())
        self.assertFalse(process._worker.is_alive())

    def test_sqlite_write_happens_only_in_server_and_survives_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.sqlite'
            config=load_configuration_directory(PRODUCT/'configuration')
            context=SQLiteDBContext.create(path,config); context.close()
            process=self.process(PRODUCT,path)
            controller=FormController(load_client(PRODUCT),process.exchange); state(controller)
            for field,value in [('Code',{'type':'String','value':'P001'}),('Description',{'type':'String','value':'Owned product'}),('Amount',{'type':'Number','value':'12.75'})]:
                self.assertIsNone(event(controller,'change','Field'+field,value=value)['error'])
            result=event(controller); self.assertIsNone(result['error'])
            self.assertFalse(next(x for x in result['state']['items'] if x['name']=='RunButton')['enabled'])
            self.assertIsNone(controller.session.interpreter.database_context)
            event(controller,'close'); process.close()
            context=SQLiteDBContext(path)
            try:
                vm=Interpreter(database_context=context)
                self.assertEqual(vm.execute('Catalogs.Products.FindByCode("P001").Amount'),Decimal('12.75'))
            finally: context.close()

    def test_missing_database_is_not_created_or_disclosed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'missing-private.sqlite'
            process=self.process(PRODUCT,path)
            result=state(FormController(load_client(PRODUCT),process.exchange))
            self.assertEqual(result['error'],'outcome_unknown')
            self.assertFalse(path.exists())
            self.assertNotIn(b'missing-private',encode_line(result))
            process.close()

    def test_child_loss_never_restarts_process_or_replays(self):
        process=self.process(); controller=FormController(load_client(EXAMPLE),process.exchange)
        state(controller); process.child.terminate(); process.child.wait(timeout=5)
        result=event(controller)
        self.assertEqual(result['error'],'outcome_unknown')
        counter=process.counter
        self.assertEqual(event(controller)['error'],'outcome_unknown')
        self.assertEqual(process.counter,counter)

    def test_deadline_failure_is_finite_and_transport_is_locked(self):
        process=self.process()
        with mock.patch.object(process._replies,'get',side_effect=__import__('queue').Empty):
            with self.assertRaises(LocalTransportError): process.exchange(b'{}\n')
        self.assertTrue(process.failed)
        counter=process.counter
        with self.assertRaises(LocalTransportError): process.exchange(b'{}\n')
        self.assertEqual(process.counter,counter)

    def test_runtime_truncated_and_oversized_frames_stop_without_dispatch(self):
        for raw in (b'{}',b'x'*(MAX_LINE_BYTES+1)):
            output=io.BytesIO()
            self.assertEqual(serve_runtime(EXAMPLE,input_stream=io.BytesIO(raw),output_stream=output),1)
            self.assertEqual(output.getvalue(),b'')
        self.assertEqual(serve_runtime(EXAMPLE,input_stream=io.BytesIO(),output_stream=io.BytesIO()),0)

    def test_frozen_route_and_process_selection_are_explicit(self):
        with mock.patch.object(entrypoint.form_app,'main',return_value=6) as app, mock.patch.object(entrypoint,'cli_main',return_value=9):
            self.assertEqual(entrypoint.main(['--form-ui','owned']),6)
            app.assert_called_with(['owned'])
            self.assertEqual(entrypoint.main(['--form-ui-runtime','owned']),6)
            app.assert_called_with(['--runtime','owned'])
            self.assertEqual(entrypoint.main(['-c','--form-ui']),9)
        with mock.patch.object(FormProcess,'_start') as start, mock.patch.object(sys,'frozen',True,create=True):
            FormProcess('owned','data.sqlite')
            command=start.call_args.args[0]
            self.assertEqual(command[:2],[sys.executable,'--form-ui-runtime'])
            self.assertIn('--f',command)

    def test_launcher_failure_is_finite_and_plain_mode_is_unchanged(self):
        output=io.StringIO()
        with redirect_stderr(output), mock.patch('yadinassi.ui.form_app.load_client',side_effect=OSError('/private/path')):
            self.assertEqual(main(['private-package']),1)
        self.assertEqual(output.getvalue(),'Local form application unavailable.\n')


class FormHTTPTests(unittest.TestCase):
    def setUp(self):
        self.controller,self.runtime=pair()
        self.server=LocalUIServer(self.controller,'a'*43,handler=FormHandler)
        self.thread=Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def http(self, method='POST', path='/rpc', body=None, headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        values={'Host':self.server.authority,'Origin':self.server.origin,'Content-Type':'application/x-ndjson','X-Yadinassi-Session':self.server.token}
        values.update(headers or {})
        try:
            conn.request(method,path,body=encode_line(request()) if body is None else body,headers=values)
            response=conn.getresponse();return response.status,dict(response.getheaders()),response.read()
        finally:conn.close()

    def test_loopback_hello_and_readonly_reattach(self):
        code,headers,raw=self.http()
        self.assertEqual(code,200);self.assertEqual(decode_line(raw)['result']['state']['kind'],'form')
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.http()[2],raw)
        self.assertEqual(self.controller.session.client_sequence,1)

    def test_wrong_origin_token_host_and_other_protocol_reject(self):
        for headers in ({'Host':'other.invalid'},{'Origin':'https://evil.invalid'},{'X-Yadinassi-Session':'b'*43}):
            self.assertEqual(self.http(headers=headers)[0],403)
        bad=request();bad['method']='editor.hello'
        self.assertEqual(self.http(body=encode_line(bad))[0],400)
        self.assertFalse(self.controller._opened)

    def test_static_routes_cannot_read_packages_databases_or_traversal(self):
        for path in ('/server.bsl','/server.json','/client.bsl','/owned.sqlite','/../server.bsl','/app.js?x=1'):
            self.assertEqual(self.http('GET',path)[0],404)
        code,headers,raw=self.http('GET','/')
        self.assertEqual(code,200);self.assertIn(b'<html',raw)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])

    def test_extra_event_keys_reject_before_mutation(self):
        self.http()
        bad=request('event',event='command',revision=1,control='RunButton',endpoint=1)
        self.assertEqual(self.http(body=encode_line(bad))[0],503)
        self.assertEqual(self.controller.session.client_sequence,1)

    def test_accepted_close_still_shuts_down_after_lost_http_response(self):
        self.http()
        original = FormHandler._reply
        def lost(handler, status, body=b'', kind='text/plain'):
            if status == 200:
                raise BrokenPipeError('owned lost response')
            return original(handler, status, body, kind)
        with mock.patch.object(FormHandler, '_reply', lost):
            with self.assertRaises(http.client.RemoteDisconnected):
                self.http(body=encode_line(request('event', event='close', revision=1)))
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(self.runtime.session.closed)

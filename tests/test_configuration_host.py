"""Application module + side-partitioned CommonModules + retained form host."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, PropertyMock

from test_configuration_application_profile import application_sources
from configuration_runtime_fixture import module_files, SERVER
from yadinassi.configuration_application_profile import import_application_configuration
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.ui.configuration_app import (ConfigurationBroker, ConfigurationController,
    ConfigurationProcess, load_application, PROTOCOL)
from yadinassi.ui.protocol import decode_line, encode_line


def host_files(application=None):
    files = application_sources(catalog=False)
    files['CommonModules/Tools/Ext/Module.bsl'] += b'\nProcedure Show() Export OpenForm("CommonForm.Details"); EndProcedure'
    extra = module_files([('Service', 'Function Add(Val X) Export Message("server result"); Return X + 1; EndFunction', SERVER)])
    files.update({k:v for k,v in extra.items() if k.startswith('CommonModules/')})
    files['Configuration.xml'] = files['Configuration.xml'].replace(b'</ChildObjects>', b'<CommonModule>Service</CommonModule></ChildObjects>')
    if application is not None: files['Ext/ManagedApplicationModule.bsl'] = application.encode()
    return files


class ConfigurationHostTests(unittest.TestCase):
    def setup_host(self, files=None, initial_form=None):
        files = host_files() if files is None else files
        imported = import_application_configuration(files)
        configuration = load_configuration_forms(files, catalog_schemas=imported.catalogs)
        broker = ConfigurationBroker(configuration, application_host=True)
        self.addCleanup(broker.close)
        packets = []
        def pipe(raw):
            request = decode_line(raw); packets.append(request)
            result = broker.exchange({k:request[k] for k in ('operation','session','payload')})
            return encode_line({'id':request['id'],'session':request['session'],'result':result,'error':None})
        controller = ConfigurationController(configuration, pipe, initial_form=initial_form, application_host=True)
        self.addCleanup(controller.close)
        return broker, controller, packets

    def rpc(self, app, method, **params):
        return app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']

    def hello(self, app): return self.rpc(app, 'hello', protocol=PROTOCOL)

    def open(self, app, token='one'):
        self.hello(app)
        return self.rpc(app, 'open', entry=app.names['commonform.welcome'], request=token)

    def event(self, app, sid, event='command', control='DetailsButton'):
        params = {'event':event, 'revision':app.sessions[sid][0].session.revision}
        if event != 'close': params['control'] = control
        return self.rpc(app, 'form', session=sid, request={'jsonrpc':'2.0','id':1,'method':'form.event','params':params})

    def test_start_once_after_handshake_and_message_visible(self):
        broker, app, packets = self.setup_host()
        self.assertEqual((app.application.state, broker.application.state), ('prepared','prepared'))
        first = self.hello(app); second = self.hello(app)
        self.assertEqual(first['state']['messages'], ['4'])
        self.assertEqual(second['state']['lifecycle'], 'running')
        self.assertEqual(sum(p['operation']=='hello' for p in packets), 1)

    def test_startup_common_module_openform_queue(self):
        _, app, _ = self.setup_host(host_files('Procedure OnStart() Tools.Show(); EndProcedure'))
        r = self.hello(app); self.assertIsNone(r['error'])
        self.assertEqual(len(app.sessions), 1)
        self.assertEqual(next(iter(app.sessions.values()))[1], app.names['commonform.details'])

    def test_cancelled_start_discards_queued_openforms(self):
        _, app, _ = self.setup_host(host_files('Procedure BeforeStart(Cancel) Tools.Show(); Cancel = True; EndProcedure'))
        r = self.hello(app)
        self.assertEqual((r['error'],r['state']['lifecycle'],r['state']['kind']), ('startup_cancelled','cancelled','closed'))
        self.assertEqual(len(app.sessions), 0); self.assertEqual(len(app.pending), 0)

    def test_failed_start_is_not_replayed(self):
        _, app, packets = self.setup_host(host_files('Procedure OnStart() Tools.Show(); Raise "failed"; EndProcedure'))
        r = self.hello(app); self.assertEqual(r['error'], 'startup_failed'); self.assertTrue(r['state']['uncertain'])
        count = len(packets); self.hello(app)
        self.assertEqual(len(packets), count); self.assertFalse(app.pending)

    def test_client_commonmodule_call_from_form_is_side_bound(self):
        files = host_files(); key='CommonForms/Welcome/Ext/Form/Module.bsl'
        files[key] = files[key].replace(b'OpenForm("CommonForm.Details", New Structure("Message", Greeting));', b'Message(Service.Add(4)); Tools.Show();')
        broker, app, packets = self.setup_host(files)
        sid = self.open(app)['session']; r = self.event(app, sid)
        self.assertIsNone(r['error']); self.assertIsNone(r['form']['result']['error'])
        self.assertEqual(r['form']['result']['state']['messages'], ['server result','5'])
        self.assertEqual(len(app.sessions), 2)
        self.assertTrue(any(p['operation']=='applicationInvoke' for p in packets))
        self.assertEqual(app.application._modules['service','server'].routine('Add').body, [])
        self.assertTrue(broker.application._modules['service','server'].routine('Add').body)

    def test_failed_form_event_does_not_open_queued_form(self):
        files = host_files(); key='CommonForms/Welcome/Ext/Form/Module.bsl'
        files[key] = files[key].replace(b'OpenForm("CommonForm.Details", New Structure("Message", Greeting));', b'Tools.Show(); Raise "failed";')
        _, app, _ = self.setup_host(files); sid=self.open(app)['session']
        self.assertIsNotNone(self.event(app,sid)['form']['result']['error'])
        self.assertEqual(len(app.sessions), 1); self.assertFalse(app.pending)

    def test_closing_one_form_does_not_release_family(self):
        _, app, _ = self.setup_host(); first=self.open(app)['session']; second=self.open(app,'two')['session']
        self.assertIsNone(self.event(app,first,'close')['error'])
        self.assertFalse(app.application.interpreter._family_released)
        self.assertIsNone(self.event(app,second)['form']['result']['error'])

    def test_before_exit_can_refuse_and_explain(self):
        files=host_files('Procedure BeforeExit(Cancel, Warning) Cancel = True; Warning = "Keep application"; EndProcedure')
        _,app,_=self.setup_host(files); self.hello(app)
        r=self.rpc(app,'close'); self.assertEqual(r['error'],'exit_cancelled')
        self.assertEqual(r['state']['exitWarning'],'Keep application'); self.assertEqual(r['state']['lifecycle'],'running')
        self.assertFalse(app.idle_close())

    def test_exit_waits_for_all_forms_and_stops_both_families(self):
        broker,app,_=self.setup_host();sid=self.open(app)['session']
        self.assertEqual(self.rpc(app,'close')['error'],'forms_open')
        self.event(app,sid,'close');r=self.rpc(app,'close')
        self.assertEqual(r['state']['kind'],'closed');self.assertEqual(broker.application.state,'closed')

    def test_no_idle_discard_of_open_form(self):
        _,app,_=self.setup_host();self.open(app)
        self.assertFalse(app.idle_close());self.assertEqual(len(app.sessions),1)

    def test_idle_clean_application_uses_normal_exit(self):
        broker,app,_=self.setup_host();self.hello(app)
        self.assertTrue(app.idle_close());self.assertEqual(broker.application.state,'closed')

    def test_pending_family_tasks_guard_retirement_before_mutation(self):
        broker,app,_=self.setup_host();sid=self.open(app)['session']
        with patch.object(type(broker.application.interpreter._scheduler),'pending',new_callable=PropertyMock,return_value=1):
            self.assertFalse(broker.exchange({'operation':'guardClose','session':sid,'payload':{}})['allowed'])
            with self.assertRaises(ValueError): broker.exchange({'operation':'retire','session':sid,'payload':{}})
            self.assertIn(sid,broker.sessions)

    def test_server_boundary_is_a_real_owned_child(self):
        files=host_files('Procedure OnStart() Message(Service.Add(7)); EndProcedure')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,content in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            process=ConfigurationProcess(root,application_host=True)
            try:
                app=ConfigurationController(load_application(root,application_host=True),process.exchange,application_host=True)
                try:
                    r=self.hello(app);self.assertEqual(r['state']['messages'],['server result','8'])
                    self.assertTrue(app.idle_close())
                finally: app.close()
            finally: process.close()


if __name__=='__main__': unittest.main()

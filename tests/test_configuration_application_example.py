"""The shipped application example runs through the real owned child boundary."""
from pathlib import Path
import unittest

from yadinassi.ui.configuration_app import (
    ConfigurationController, ConfigurationProcess, PROTOCOL, load_application,
)

ROOT = Path(__file__).resolve().parents[1] / 'examples/configuration-application-host'


class ConfigurationApplicationExampleTests(unittest.TestCase):
    def test_example_has_explicit_composed_source_and_closed_forms(self):
        configuration = load_application(ROOT, application_host=True)
        self.assertEqual(configuration.name, 'ApplicationWorkshop')
        self.assertEqual(set(configuration.forms), {'commonform.welcome', 'commonform.details'})
        self.assertIn('CommonModules/Tools/Ext/Module.bsl', configuration.source_files)
        self.assertIn('CommonModules/Service/Ext/Module.bsl', configuration.source_files)

    def test_example_start_commonmodule_openform_servercall_and_exit(self):
        process = ConfigurationProcess(ROOT, application_host=True)
        self.addCleanup(process.close)
        app = ConfigurationController(load_application(ROOT, application_host=True),
                                      process.exchange, application_host=True)
        self.addCleanup(app.close)
        def rpc(method, **params):
            return app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,
                                 'params':params})['result']
        started = rpc('hello', protocol=PROTOCOL)
        self.assertIsNone(started['error'])
        self.assertEqual(started['state']['messages'], ['Calculated in the owned server process', '8'])
        self.assertEqual(len(app.sessions), 1)
        welcome = next(iter(app.sessions))
        result = rpc('form', session=welcome, request={'jsonrpc':'2.0','id':2,
            'method':'form.event','params':{'event':'command','control':'DetailsButton',
                'revision':app.sessions[welcome][0].session.revision}})
        self.assertIsNone(result['error'])
        self.assertIsNone(result['form']['result']['error'])
        self.assertEqual(result['form']['result']['state']['messages'],
                         ['Calculated in the owned server process', '5'])
        self.assertEqual(len(app.sessions), 2)
        for sid in tuple(app.sessions):
            result = rpc('form', session=sid, request={'jsonrpc':'2.0','id':3,
                'method':'form.event','params':{'event':'close',
                    'revision':app.sessions[sid][0].session.revision}})
            self.assertIsNone(result['error'])
        self.assertEqual(rpc('close')['state']['kind'], 'closed')


if __name__ == '__main__':
    unittest.main()

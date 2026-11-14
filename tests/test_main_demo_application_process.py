"""One main demo crosses the real owned child boundary, including lifecycle."""
from pathlib import Path
import tempfile
import unittest

from yadinassi.configuration_main_demo import import_main_demo_configuration, PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.form_dialogs import DIALOG_CAPABILITY
from yadinassi.ui.configuration_app import ConfigurationController, ConfigurationProcess, PROTOCOL, load_application

ROOT = Path(__file__).resolve().parents[1] / 'examples/demo'
STARTED = 'Основная демо: справочники, документы и складские отчёты.'

class ConfigurationApplicationExampleTests(unittest.TestCase):
    def test_example_has_explicit_composed_source_and_closed_forms(self):
        configuration = load_application(ROOT, main_demo_application=True)
        self.assertEqual(set(configuration.forms), {'commonform.operationdraft', 'commonform.draftdetails', 'commonform.demowelcome',
            'document.receipt.form.card', 'document.issue.form.card'})
        for name in ('DemoTools', 'DemoService'):
            self.assertIn('CommonModules/'+name+'/Ext/Module.bsl', configuration.source_files)

    def test_example_start_commonmodule_openform_servercall_and_exit(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'main.sqlite'
        files = {p.relative_to(ROOT).as_posix():p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        SQLiteDBContext.create_main_demo(path, import_main_demo_configuration(files, profile=PROFILE)).close()
        before = path.read_bytes()
        process = ConfigurationProcess(ROOT, path, main_demo_application=True)
        self.addCleanup(process.close)
        app = ConfigurationController(load_application(ROOT, main_demo_application=True),
                                      process.exchange, main_demo_application=True)
        self.addCleanup(app.close)
        def rpc(method, **params):
            result = app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,
                                   'params':params})['result']
            self.assertIsNone(result['error']); return result
        def event(sid, name, **extra):
            result = rpc('form', session=sid, request={'jsonrpc':'2.0','id':2,
                'method':'form.event','params':{'event':name,
                    'revision':app.sessions[sid][0].session.revision, **extra}})
            self.assertIsNone(result['form']['result']['error']); return result
        started = rpc('hello', protocol=PROTOCOL, dialogCapability=DIALOG_CAPABILITY)
        self.assertEqual(started['state']['messages'], [STARTED])
        self.assertFalse(app.sessions)  # Startup does not invisibly open or write a record.
        repeated = rpc('hello', protocol=PROTOCOL, dialogCapability=DIALOG_CAPABILITY)
        self.assertEqual(repeated['state']['messages'], [STARTED])
        welcome = rpc('open', entry=app.names['commonform.demowelcome'], request='overview')['session']
        result = event(welcome, 'command', control='DetailsButton')
        self.assertEqual(result['form']['result']['state']['messages'], ['Calculated in the owned server process', '5'])
        self.assertEqual(len(app.sessions), 2)
        owner = next(sid for sid in app.sessions if sid != welcome)
        self.assertEqual(app.definitions[app.sessions[owner][1]].name, 'CommonForm.OperationDraft')
        event(welcome, 'close')
        self.assertIn(owner, app.sessions)
        event(owner, 'command', control='EditButton')
        self.assertEqual(len(app.sessions), 2)
        child = next(sid for sid in app.sessions if sid != owner)
        self.assertEqual(app.sessions[child][0].session.form._data['drafttitle'], 'Новая операция')
        event(child, 'command', control='CancelButton')
        self.assertNotIn(child, app.sessions)
        self.assertIn(owner, app.sessions)
        event(owner, 'close')
        self.assertEqual(rpc('close')['state']['kind'], 'closed')
        app.close(); process.close()
        self.assertEqual(path.read_bytes(), before)

if __name__ == '__main__':
    unittest.main()

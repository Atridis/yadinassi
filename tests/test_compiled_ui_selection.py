"""UI backend selection is explicit across entrypoints and child protocols."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from yadinassi.execution.execution_policy import backend_entrypoint, current_backend, execution_backend_policy
from yadinassi.ui.form_app import FormProcess
from yadinassi.ui.configuration_app import ConfigurationProcess
from yadinassi.ui.local_app import RuntimeBridge

ROOT = Path(__file__).resolve().parents[1]

class UIBackendSelectionTests(unittest.TestCase):
    def test_entry_scope_restores_and_double_dash_is_data(self):
        entry_backend = current_backend()
        @backend_entrypoint
        def entry(argv):
            return current_backend(), argv
        self.assertEqual(entry(['--execution-backend', 'python-direct', 'file']),
                         ('python-direct', ['file']))
        self.assertEqual(current_backend(), entry_backend)
        self.assertEqual(entry(['--', '--execution-backend', 'python-direct']),
                         (entry_backend, ['--', '--execution-backend', 'python-direct']))
        with execution_backend_policy('python-direct'):
            self.assertEqual(entry(['file']), ('python-direct', ['file']))

    def test_child_argv_does_not_need_backend_selection(self):
        for cls in (RuntimeBridge, FormProcess, ConfigurationProcess):
            for mode in ('python-direct',):
                with self.subTest(cls=cls.__name__, mode=mode), execution_backend_policy(mode), \
                        patch.object(cls, '_start') as start:
                    cls('owned-path')
                    command = start.call_args.args[0]
                    self.assertNotIn('--execution-backend', command)

    def test_fresh_stdio_children_select_and_restore_backend(self):
        for module in ('form_app', 'configuration_app', 'editor_stdio'):
          for mode in ('python-direct',):
            with self.subTest(module=module, mode=mode):
                code = '''import sys,json,io
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch,Mock
from yadinassi.execution.execution_policy import current_backend
from yadinassi.ui import MODULE as app
seen=[]
def runtime(*a,**kw): seen.append(current_backend()); return 0
if 'MODULE' == 'editor_stdio':
 with patch.object(app,'SQLiteDBContext',side_effect=lambda *a: (seen.append(current_backend()),Mock())[1]), patch.object(app,'CatalogEditorApplication',return_value=Mock()),patch.object(app,'CatalogEditorSession',return_value=Mock()):
  result=app.main(['owned-path','--execution-backend','BACKEND'],source=io.BytesIO(),target=io.BytesIO())
else:
 with patch.object(app,'serve_runtime',side_effect=runtime):
  result=app.main(['owned-path','--runtime','--execution-backend','BACKEND'])
print(json.dumps({'result':result,'seen':seen,'after':current_backend()}))
'''.replace('MODULE', module).replace('BACKEND', mode)
                completed = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT)],
                    check=True, capture_output=True, text=True, timeout=20)
                self.assertEqual(json.loads(completed.stdout),
                    {'result': 0, 'seen': [mode], 'after': 'python-direct'})

    def test_legacy_hybrid_ui_is_rejected_before_body(self):
        seen = []
        @backend_entrypoint
        def entry(argv): seen.append(argv)
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            entry(['--execution-backend', 'hybrid'])
        self.assertEqual(seen, [])

    def test_backend_option_abbreviation_cannot_fall_through_to_old_mode(self):
        seen = []
        @backend_entrypoint
        def entry(argv): seen.append(current_backend())
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            entry(['--execution-back', 'python-direct'])
        self.assertEqual(seen, [])

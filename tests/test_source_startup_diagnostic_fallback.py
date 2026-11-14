"""Workspace startup failure stays failed, visible, closed, and never replayed."""
import contextlib
import io
import unittest
from unittest.mock import patch
from test_source_forms import files
from test_source_shell import request
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.ui.source_shell import main, SourceHandler

class SourceStartupDiagnosticFallbackTests(unittest.TestCase):
    def run_cli(self, code, *, app_factory=SourceApplication, extra=(), interrupt=False):
        mapping=files();mapping['Ext/ManagedApplicationModule.bsl']=code.encode();source=import_source(mapping)
        captured={};out,err=io.StringIO(),io.StringIO()
        class Server:
            launch_url='http://localhost/diagnostics'
            def __init__(self,shell,handler):captured.update(shell=shell,handler=handler)
            def serve_forever(self,**kwargs):
                captured['snapshot']=captured['shell'].exchange(request()) if captured['handler'] is SourceHandler else None
                if interrupt:raise KeyboardInterrupt
            def server_close(self):captured['server_closed']=True
        with patch('yadinassi.ui.source_shell.load_source_archive',return_value=source),patch('yadinassi.ui.source_shell.SourceApplication',side_effect=app_factory) as constructor,patch('yadinassi.ui.source_shell.LocalUIServer',Server),patch('yadinassi.ui.source_shell.webbrowser.open') as browser,contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            result=main(['--configuration-source','unused.zip','--run-startup','--source-workspace','--open-browser',*extra]);captured.update(code=result,constructor_calls=constructor.call_count,browser_calls=browser.call_count,stderr=err.getvalue(),stdout=out.getvalue())
        return captured

    def test_failed_startup_has_diagnostic_browser_not_success_and_no_retry(self):
        apps=[]
        def factory(*args,**kwargs):
            app=SourceApplication(*args,**kwargs);apps.append(app);return app
        c=self.run_cli('Message("before-failure"); MissingService();',app_factory=factory)
        self.assertEqual(c['code'],1);self.assertEqual(c['constructor_calls'],1);self.assertEqual(c['browser_calls'],1);self.assertIs(c['handler'],SourceHandler)
        state=c['snapshot']['result']['state'];self.assertEqual(state['startup'],'failed');self.assertFalse(state['runtime_active']);self.assertIn('MissingService',state['error']);self.assertEqual(state['messages'],['before-failure'])
        self.assertIn('MissingService',c['stderr']);self.assertIn('только диагностика',c['stderr']);self.assertNotIn('Source workspace:',c['stdout']);self.assertEqual(apps[0].state,'closed');self.assertTrue(c['server_closed'])
        for method in ['source.start','workspace.open','Execute']:
            with self.assertRaises(ValueError):c['shell'].exchange(request(method))

    def test_constructor_compile_failure_is_diagnostic_without_second_constructor(self):
        c=self.run_cli('',app_factory=lambda *a,**k:(_ for _ in ()).throw(ValueError('compile failure')))
        self.assertEqual(c['code'],1);self.assertEqual(c['constructor_calls'],1);self.assertEqual(c['snapshot']['result']['state']['error'],'compile failure')

    def test_cancel_is_not_failure_fallback_and_does_not_open_browser(self):
        c=self.run_cli('Procedure BeforeStart(Cancel)\nCancel=True;\nEndProcedure')
        self.assertEqual(c['code'],1);self.assertEqual(c['browser_calls'],0);self.assertNotIn('shell',c);self.assertIn('отменён',c['stderr'])

    def test_success_retains_workspace_handler_and_zero_exit(self):
        c=self.run_cli('Message("started");')
        self.assertEqual(c['code'],0);self.assertIn('started',c['stdout']);self.assertNotEqual(c['handler'],SourceHandler);self.assertEqual(c['constructor_calls'],1);self.assertEqual(c['browser_calls'],1)

    def test_failed_startup_does_not_execute_queued_openform(self):
        c=self.run_cli('OpenForm("CommonForm.Main"); Raise "stop after intent";')
        self.assertEqual(c['code'],1);self.assertIs(c['handler'],SourceHandler);self.assertFalse(hasattr(c['shell'],'open_forms'));self.assertIn('stop after intent',c['snapshot']['result']['state']['error'])

    def test_error_and_output_are_bounded(self):
        c=self.run_cli('For I=1 To 30 Do Message("text"); EndDo; Raise "'+('Ж'*10000)+'";')
        state=c['snapshot']['result']['state'];self.assertLessEqual(len(state['error'].encode()),8192);self.assertEqual(len(state['messages']),16);self.assertEqual(state['omitted_messages'],14)

    def test_interrupting_failed_diagnostics_preserves_failure_exit(self):
        c=self.run_cli('Raise "failed";',interrupt=True)
        self.assertEqual(c['code'],1);self.assertTrue(c['server_closed']);self.assertEqual(c['snapshot']['result']['state']['startup'],'failed')

    def test_interrupting_success_keeps_normal_exit(self):
        c=self.run_cli('Message("started");',interrupt=True)
        self.assertEqual(c['code'],0);self.assertTrue(c['server_closed']);self.assertNotEqual(c['handler'],SourceHandler)

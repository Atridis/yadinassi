import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch
from test_configuration_source_runtime import source
from yadinassi.ui.source_shell import SourceShell, SourceHandler
from yadinassi.ui.local_app import LocalUIServer
from yadinassi.ui.protocol import encode_line


def request(method='source.snapshot', **params):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}


class SourceShellTests(unittest.TestCase):
    def test_no_implicit_execution(self):
        shell = SourceShell(source(b'Raise "must not run";'))
        self.assertEqual(shell.outcome, 'not-run')
        self.assertFalse(shell.exchange(request())['result']['state']['runtime_active'])

    def test_success_output_and_closed_runtime(self):
        shell = SourceShell(source(b'Procedure OnStart()\nMessage("ready");\nEndProcedure'), run_startup=True)
        self.assertEqual(shell.outcome, 'completed')
        self.assertEqual(shell.messages, ['ready'])
        self.assertFalse(shell.exchange(request())['result']['state']['runtime_active'])

    def test_error_keeps_inventory(self):
        shell = SourceShell(source(b'Procedure OnStart()\nMissingService();\nEndProcedure'), run_startup=True)
        self.assertEqual(shell.outcome, 'failed')
        self.assertIn('MissingService', shell.error)
        self.assertEqual(shell.files, 2)

    def test_cancelled_is_not_success(self):
        shell = SourceShell(source(b'Procedure BeforeStart(Cancel)\nCancel=True;\nEndProcedure'), run_startup=True)
        self.assertEqual(shell.outcome, 'cancelled')

    def test_no_execute_rpc_or_browser_path(self):
        shell = SourceShell(source())
        for req in (request('source.start'), request('source.snapshot', path='/tmp/x'), request('Execute')):
            with self.assertRaises(ValueError): shell.exchange(req)

    def test_close_idempotent(self):
        shell = SourceShell(source())
        for _ in range(2):
            self.assertEqual(shell.exchange(request('source.close'))['result']['state']['kind'], 'closed')

    def test_scratch_requires_execution_opt_in(self):
        with self.assertRaises(ValueError): SourceShell(source(), scratch_database='unused.sqlite')

    def test_output_is_bounded_for_transport(self):
        shell = SourceShell(source())
        for _ in range(1000): shell._output('😃' * 10000)
        self.assertEqual(shell.omitted_messages, 984)
        self.assertLess(len(encode_line(shell.exchange(request()))), 131072)

    def test_multibyte_error_fits_transport(self):
        with patch('yadinassi.ui.source_shell.SourceApplication', side_effect=ValueError('😃' * 5000)):
            shell = SourceShell(source(), run_startup=True)
        self.assertEqual(shell.outcome, 'failed')
        self.assertLessEqual(len(shell.error.encode('utf-8')), 8192)
        encode_line(shell.exchange(request()))

    def test_invalid_oversized_target_rejected_before_state(self):
        with self.assertRaisesRegex(ValueError, 'four numeric'):
            SourceShell(source(), run_startup=True, compatibility_target='1' * 100000)

    def test_launcher_source_dispatch(self):
        from yadinassi.launcher import main
        with patch('yadinassi.ui.source_shell.main', return_value=7) as run:
            self.assertEqual(main(['--ui', '--configuration-source=x']), 7)
            run.assert_called_once_with(['--configuration-source=x'])

    def test_http_snapshot_and_invalid_token(self):
        shell = SourceShell(source())
        server = LocalUIServer(shell, handler=SourceHandler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            for token, status in ((server.token, 200), ('x' * 43, 403)):
                conn = http.client.HTTPConnection(server.authority)
                conn.request('POST', '/rpc', json.dumps(request()) + '\n',
                    {'Origin': server.origin, 'Content-Type': 'application/x-ndjson', 'X-Yadinassi-Session': token})
                response = conn.getresponse(); self.assertEqual(response.status, status)
                response.read(); conn.close()
            conn = http.client.HTTPConnection(server.authority)
            conn.request('GET', '/'); response = conn.getresponse()
            self.assertEqual(response.status, 200); self.assertIn('Content-Security-Policy', response.headers)
            self.assertIn('Диагностика'.encode(), response.read()); conn.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

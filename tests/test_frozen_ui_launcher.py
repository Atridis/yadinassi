"""Mode dispatch and frozen child command without launching a real process."""
import sys
import unittest
from unittest import mock

from scripts import entrypoint
from yadinassi.ui.local_app import RuntimeBridge


class FrozenLauncherTests(unittest.TestCase):
    def test_first_argument_only_selects_explicit_mode(self):
        with mock.patch.object(entrypoint, 'cli_main', return_value=9) as cli, \
                mock.patch.object(entrypoint.local_app, 'main', return_value=8) as ui, \
                mock.patch.object(entrypoint.editor_stdio, 'main', return_value=7) as child:
            self.assertEqual(entrypoint.main(['--catalog-ui', '--f', 'test.sqlite']), 8)
            ui.assert_called_once_with(['--f', 'test.sqlite'])
            self.assertEqual(entrypoint.main(['--catalog-ui-runtime', 'test.sqlite']), 7)
            child.assert_called_once_with(['test.sqlite'])
            for args in ([], ['-c', '--catalog-ui'], ['--', '--catalog-ui'],
                         ['sample.bsl', '--catalog-ui']):
                self.assertEqual(entrypoint.main(args), 9)
                cli.assert_called_with(args)

    def test_bridge_selects_interpreter_or_frozen_executable(self):
        child = mock.Mock(); child.poll.return_value = 0
        with mock.patch('yadinassi.ui.local_app.subprocess.Popen', return_value=child) as popen:
            for frozen in (False, True):
                with mock.patch.object(sys, 'frozen', frozen, create=True):
                    bridge = RuntimeBridge('owned.sqlite')
                    try:
                        command = popen.call_args.args[0]
                        self.assertEqual(command, ([sys.executable, '--catalog-ui-runtime', 'owned.sqlite']
                            if frozen else [sys.executable, '-m', 'yadinassi.ui.editor_stdio', 'owned.sqlite']))
                    finally: bridge.close()

"""Same-side adapters keep bind and after-argument admission, not both twice."""
import unittest
from unittest.mock import patch

from test_python_direct_source import common_module
from test_configuration_source_runtime import source
import test_source_server_call as server_fixtures
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.direct import python_direct_source as direct


class SourceRoutineChecks(unittest.TestCase):
    def run_counted(self, config):
        out = []
        app = SourceApplication(config, output=out.append)
        self.addCleanup(app.close)
        preflight = direct._preflight
        names = []

        def record(owner, routine):
            names.append(routine.name.casefold())
            return preflight(owner, routine)

        with patch.object(direct, '_preflight', record):
            self.assertTrue(app.start())
        self.assertEqual(out, ['8'])
        return names.count('increment')

    def test_client_common_module_reuses_current_admission(self):
        config = source(
            b'Procedure OnStart() Message(Helpers.Increment(7)); EndProcedure',
            common_module(b'Function Increment(Val X) Export Return X+1; EndFunction'),
        )
        self.assertEqual(self.run_counted(config), 2)

    def test_server_common_module_reuses_current_admission(self):
        config = server_fixtures.configuration(
            'Message(ServerAPI.Answer());',
            'Function Answer() Export Return Internal.Increment(7); EndFunction',
        )
        config = server_fixtures.SourceServerCallTests().with_extra(
            config, 'Internal', 'Function Increment(Val X) Export Return X+1; EndFunction',
            server_call=False,
        )
        self.assertEqual(self.run_counted(config), 2)

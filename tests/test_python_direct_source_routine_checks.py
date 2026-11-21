"""Same-side adapters admit just the selected signature before arguments."""
import unittest
from unittest.mock import patch

from yadinassi.configuration.configuration_source import import_source

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
        self.assertEqual(self.run_counted(config), 1)

    def test_server_common_module_reuses_current_admission(self):
        config = server_fixtures.configuration(
            'Message(ServerAPI.Answer());',
            'Function Answer() Export Return Internal.Increment(7); EndFunction',
        )
        config = server_fixtures.SourceServerCallTests().with_extra(
            config, 'Internal', 'Function Increment(Val X) Export Return X+1; EndFunction',
            server_call=False,
        )
        self.assertEqual(self.run_counted(config), 1)


    def test_three_server_modules_keep_live_aliases_and_client_boundary(self):
        config = server_fixtures.configuration(
            'Message(ServerAPI.Answer()); Try Middle.Change(0,0); Except Message("denied"); EndTry;',
            'Function Answer() Export X=7; Middle.Change(X,X); Return X; EndFunction',
        )
        fixtures = server_fixtures.SourceServerCallTests()
        config = fixtures.with_extra(config,'Middle',
            'Procedure Change(X,Y) Export Last.Change(X,Y); EndProcedure',server_call=False)
        files = {item.path:item.content for item in config.files}
        extra = server_fixtures.module('Last',
            'Procedure Change(X,Y) Export X=X+1; Y=Y+2; EndProcedure',server_call=False)
        extra['CommonModules/Last.xml'] = extra['CommonModules/Last.xml'].replace(
            b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000004">')
        files.update(extra)
        out = []
        app = SourceApplication(import_source(files),output=out.append)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        self.assertEqual(out,['10','denied'])

    def test_by_value_host_reference_still_expires(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.types.values import Reference

        config = source(b'', common_module(b'Function Identity(Val X) Export Return X; EndFunction'))
        app = SourceApplication(config)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        vm = app.interpreter
        original = Reference(lambda:7, lambda _:None)
        vm.variables['x'] = original
        returned = vm.execute('Helpers.Identity(X);')
        self.assertIsNot(returned, original)
        with self.assertRaises(BoundaryViolation):
            returned.get()

    def test_decoding_cache_never_reuses_module_permission(self):
        config = source(b'', common_module(b'Function Increment(Val X) Export Return X+1; EndFunction'))
        out = []
        app = SourceApplication(config,output=out.append)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        from yadinassi.configuration import configuration_source_runtime as runtime
        with patch.object(runtime, '_decoded_common_module_properties',
                          wraps=runtime._decoded_common_module_properties) as decoder:
            app.interpreter.execute('Message(Helpers.Increment(7)); Message(Helpers.Increment(7));')
        self.assertEqual(out,['8','8'])
        self.assertEqual(decoder.call_count,1)
        path = 'CommonModules/Helpers.xml'
        app.files[path] = app.files[path].replace(b'<Properties>',b'<Properties><Privileged>true</Privileged>')
        app.interpreter.execute('Try Message(Helpers.Increment(7)); Except Message("denied"); EndTry;')
        self.assertEqual(out,['8','8','denied'])

    def test_same_side_target_removed_by_plain_output_during_arguments(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

        config = source(
            b'Function Touch() Message("arg"); Return 7; EndFunction',
            common_module(b'Function Call(Val X) Export Message("callee"); Return X; EndFunction'),
        )
        out = []

        def output(value):
            out.append(value)
            if value == 'arg':
                app._instances.clear()

        app = SourceApplication(config, output=output)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('R=Helpers.Call(Touch()); Message("later");')
        self.assertEqual(out, ['arg'])

    def test_qualified_call_sees_new_invalid_alias_and_can_recover(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

        out = []
        config = source(b'', common_module(b'Function Identity(Val X) Export Return X; EndFunction'))
        app = SourceApplication(config, output=out.append)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        vm = app.interpreter
        vm.execute('Message(Helpers.Identity(7));')
        app._instances['invalid-alias'] = app._instances[('helpers','client',False)]
        with self.assertRaises(BoundaryViolation):
            vm.execute('Message(Helpers.Identity(8));')
        app._instances.pop('invalid-alias')
        vm.execute('Message(Helpers.Identity(9));')
        self.assertEqual(out,['7','9'])

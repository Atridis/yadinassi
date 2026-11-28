"""Explicit managed CLI starts real stored BSL through its owned application."""
from contextlib import redirect_stderr, redirect_stdout
import dis
from io import StringIO
from pathlib import Path
import tempfile
from types import CodeType
import unittest
from unittest.mock import patch

from yadinassi.cli import main
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from configuration_runtime_fixture import SERVER, module_files


TOOLS = ('Tools', '''
Function Increment(Val X) Return X+1; EndFunction
Function Compute(Val N) Export
    Result=0;
    For I=1 To N Do
        Result=Increment(Result);
    EndDo;
    Return Result;
EndFunction''', {})


class ManagedCLIRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / 'managed.sqlite'

    def archive(self, app='', modules=(TOOLS,)):
        files = module_files(modules, application=app)
        config = import_configuration(files, numbering_policy='decimal_v1', module_runtime=MODULE_RUNTIME)
        SQLiteDBContext.create(self.db, config).close()
        return files

    def cli(self, args, *, stdin='', managed=True):
        options = ['--f', str(self.db)]
        if managed:
            options += ['--module-runtime', MODULE_RUNTIME]
        out, err = StringIO(), StringIO()
        with patch('sys.stdin', StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            status = main(options+args)
        return status, out.getvalue(), err.getvalue()

    def test_command_file_stdin_and_console_share_application(self):
        self.archive('Message("boot"); Procedure OnStart() Message("ready"); EndProcedure')
        command = 'Message(Tools.Compute(4));'
        source = self.root/'run.bsl'
        source.write_text(command, encoding='utf-8')
        self.assertEqual(self.cli(['-c', command]), (0, 'boot\nready\n4\n', ''))
        self.assertEqual(self.cli([str(source)]), (0, 'boot\nready\n4\n', ''))
        self.assertEqual(self.cli(['-'], stdin=command), (0, 'boot\nready\n4\n', ''))
        self.assertEqual(self.cli([], stdin='X=Tools.Compute(4);\nX\n/exit\n'), (0, 'boot\nready\n4\n', ''))
        self.assertEqual(self.cli(['-c', 'Message(7);'], managed=False), (0, '7\n', ''))

    def test_managed_cli_leaves_only_actual_boundary_dispatch(self):
        def operations(code):
            # The generated source is intentionally not retained in this mode.
            names = {op.argval for op in dis.get_instructions(code)
                     if op.opname in ('LOAD_METHOD', 'LOAD_ATTR')}
            for constant in code.co_consts:
                if type(constant) is CodeType:
                    names.update(operations(constant))
            return names

        files = self.archive('Var X; X=Tools.Compute(2); Procedure OnStart() Message(X); EndProcedure')
        guarded = ConfigurationApplication.from_files(
            files, output=lambda value: None, allow_extensions=True)
        self.addCleanup(guarded.close, force=True)
        guarded_plan = guarded._modules['tools', 'client'].interpreter._direct_configuration_plan
        self.assertLessEqual({'checkpoint', '_check'}, operations(guarded_plan.function.__code__))
        self.assertIs(guarded.interpreter.allow_extensions, True)
        with SQLiteDBContext(self.db) as context:
            cli_app = ConfigurationApplication._from_cli_database(context)
            self.addCleanup(cli_app.close, force=True)
            cli_plan = cli_app._modules['tools', 'client'].interpreter._direct_configuration_plan
            self.assertTrue({'checkpoint', '_check'}.isdisjoint(operations(cli_plan.function.__code__)))
            self.assertIs(cli_app.interpreter.allow_extensions, False)
            with redirect_stdout(StringIO()) as out:
                self.assertTrue(cli_app.start())
                self.assertEqual(cli_app.execute('Tools.Compute(4)'), 4)
            self.assertEqual(out.getvalue(), '2\n')
            self.assertTrue(cli_app.close())

    def test_start_cancellation_does_not_execute_command(self):
        self.archive('Message("boot"); Procedure BeforeStart(Cancel) Cancel=True; EndProcedure')
        self.assertEqual(self.cli(['-c', 'Message("not run");']), (0, 'boot\n', ''))

    def test_shutdown_cancellation_still_fails_finite_cli(self):
        self.archive('Procedure BeforeExit(Cancel, Warning) Cancel=True; EndProcedure')
        result, output, error = self.cli(['-c', 'Message("command");'])
        self.assertEqual((result, output), (1, 'command\n'))
        self.assertIn('shutdown cancelled', error)

    def test_command_keeps_profile_and_transaction_boundaries(self):
        self.archive(
            'Procedure OnStart() Try BeginTransaction(); Except Message("blocked"); EndTry; EndProcedure',
            modules=(TOOLS, ('Gateway', 'Function ServerValue(Val X) Export Return X; EndFunction', SERVER)),
        )
        result, output, error = self.cli(['-c', 'Message(Gateway.ServerValue(7));'])
        self.assertEqual((result, output), (1, 'blocked\n'))
        self.assertIn('only client scalar modules', error)
        result, output, error = self.cli(['-c', 'Message(Catalogs.Products.Count());'])
        self.assertEqual((result, output), (1, 'blocked\n'))
        self.assertIn('only client scalar modules', error)
        with SQLiteDBContext(self.db) as context:
            self.assertIsNone(getattr(context.backend, '_bsl_transaction', None))

    def test_rebound_database_is_not_admitted_in_live_cli_application(self):
        self.archive()
        with SQLiteDBContext(self.db) as context, SQLiteDBContext(self.db) as other:
            cli_app = ConfigurationApplication._from_cli_database(context)
            self.addCleanup(cli_app.close, force=True)
            self.assertTrue(cli_app.start())
            cli_app.interpreter._database_context = other
            with self.assertRaisesRegex(BoundaryViolation, 'database owner changed'):
                cli_app.execute('Message(Tools.Compute(4));')
            cli_app.interpreter._database_context = context
            self.assertEqual(cli_app.execute('Tools.Compute(4)'), 4)
            cli_app.close()

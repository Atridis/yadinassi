"""Origin-bound transaction admission across configured common-module calls."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from configuration_runtime_fixture import module_files, SERVER
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration_xml import import_configuration
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_migration_plan import prepare, apply
from yadinassi.errors import BSLError


class TransactionOriginTests(unittest.TestCase):
    def app(self, *, global_tools=False):
        source = 'Procedure Start() Export BeginTransaction(); CommitTransaction(); EndProcedure'
        alias = 'Procedure AliasStart() Export НачатьТранзакцию(); ОтменитьТранзакцию(); EndProcedure'
        flags = {'Server': 'true', 'Global': 'true' if global_tools else 'false'}
        target = 'Start()' if global_tools else 'Tools.Start()'
        modules = [('Tools', source + '\n' + alias, flags),
                   ('Gateway', 'Procedure Go() Export ' + target + '; EndProcedure', SERVER),
                   ('Middle', 'Procedure Go() Export Gateway.Go(); EndProcedure', SERVER)]
        program = ('&AtServer\nProcedure Direct() ' + target + '; EndProcedure\n'
                   '&AtServerNoContext\nProcedure Stateless() ' + target + '; EndProcedure\n')
        config = import_configuration(module_files(modules), module_runtime=MODULE_RUNTIME)
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'origin.sqlite'
        context = SQLiteDBContext.create(path, config); context.close()
        apply(path, prepare(path, maintenance=True), maintenance=True)
        context = SQLiteDBContext(path); self.addCleanup(context.close)
        app = ConfigurationApplication(config, database_context=context, output=lambda x: None)
        app.start()
        app.execute(program)
        return app, context.backend

    def refused(self, command, *, global_tools=False):
        app, backend = self.app(global_tools=global_tools)
        with patch.object(backend, 'begin_unit_of_work', wraps=backend.begin_unit_of_work) as begin:
            with self.assertRaises(BSLError): app.execute(command)
            begin.assert_not_called()
        self.assertIsNone(getattr(backend, '_bsl_transaction', None))
        app.execute('BeginTransaction(); RollbackTransaction();')

    def test_server_same_context_indirect_named_module(self):
        self.refused('Direct();')

    def test_server_no_context_indirect_named_module(self):
        self.refused('Stateless();')

    def test_servercall_indirect_module_chain(self):
        self.refused('Middle.Go();')

    def test_server_same_context_global_export(self):
        self.refused('Direct();', global_tools=True)

    def test_server_no_context_global_export(self):
        self.refused('Stateless();', global_tools=True)

    def test_server_alias_indirect(self):
        app, backend = self.app()
        app.execute('&AtServer\nProcedure AliasGateway() Tools.AliasStart(); EndProcedure')
        with patch.object(backend, 'begin_unit_of_work', wraps=backend.begin_unit_of_work) as begin:
            with self.assertRaises(BSLError): app.execute('AliasGateway();')
            begin.assert_not_called()

    def test_caught_failure_restores_client_admission_same_execution(self):
        app, backend = self.app()
        app.execute('Try Direct(); Except EndTry; BeginTransaction(); RollbackTransaction();')
        self.assertIsNone(getattr(backend, '_bsl_transaction', None))

    def test_client_named_common_module_remains_allowed(self):
        app, backend = self.app()
        app.execute('Tools.Start(); Tools.AliasStart();')
        self.assertIsNone(getattr(backend, '_bsl_transaction', None))

    def test_client_global_common_module_remains_allowed(self):
        app, backend = self.app(global_tools=True)
        app.execute('Start(); AliasStart();')
        self.assertIsNone(getattr(backend, '_bsl_transaction', None))

"""The host's independent form VM factories cannot acquire root transaction rights."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from configuration_runtime_fixture import module_files
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.errors import BSLError
from yadinassi.form_runtime import FormSession
from yadinassi.sqlite_migration_plan import prepare, apply


class ApplicationTransactionOriginTests(unittest.TestCase):
    def app(self, *, global_tools=False, side='client'):
        source = 'Procedure Start() Export BeginTransaction(); RollbackTransaction(); EndProcedure'
        flags = {'Server': 'true', 'Global': 'true' if global_tools else 'false'}
        target = 'Start()' if global_tools else 'Tools.Start()'
        files = module_files([
            ('Tools', source, flags),
            ('Gateway', 'Procedure Go() Export ' + target + '; EndProcedure', {'Server':'true'}),
        ])
        config = import_configuration(files, module_runtime=MODULE_RUNTIME)
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'form-origin.sqlite'
        context = SQLiteDBContext.create(path, config); context.close()
        apply(path, prepare(path, maintenance=True), maintenance=True)
        context = SQLiteDBContext(path); self.addCleanup(context.close)
        app = ConfigurationApplication(config, side=side, database_context=context,
                                       output=lambda value: None)
        self.addCleanup(lambda: app.close(force=True))
        app.start()
        return app, context, target

    def assert_refused(self, backend, action):
        with patch.object(backend, 'begin_unit_of_work', wraps=backend.begin_unit_of_work) as begin:
            with self.assertRaises(BSLError): action()
            begin.assert_not_called()
        self.assertIsNone(getattr(backend, '_bsl_transaction', None))

    def test_independent_factory_denies_direct_begin(self):
        app, context, _ = self.app()
        child = app.interpreter_factory(lambda value: None, database_context=context)
        self.addCleanup(child.close)
        self.assert_refused(context.backend, lambda: child.execute('BeginTransaction();'))
        app.execute('BeginTransaction(); RollbackTransaction();')

    def test_independent_factory_denies_indirect_common_chain_and_restores_root(self):
        app, context, _ = self.app()
        child = app.interpreter_factory(lambda value: None, database_context=context)
        self.addCleanup(child.close)
        self.assert_refused(context.backend, lambda: child.execute('Gateway.Go();'))
        app.execute('Gateway.Go();')

    def test_independent_factory_denies_global_common_export(self):
        app, context, target = self.app(global_tools=True)
        child = app.interpreter_factory(lambda value: None, database_context=context)
        self.addCleanup(child.close)
        self.assert_refused(context.backend, lambda: child.execute(target + ';'))
        app.execute(target + ';')

    def test_server_factory_cannot_inherit_common_owner_admission(self):
        app, context, _ = self.app(side='server')
        child = app.interpreter_factory(lambda value: None, database_context=context)
        self.addCleanup(child.close)
        self.assertEqual(child.execution_context, 'server')
        self.assert_refused(context.backend, lambda: child.execute('Gateway.Go();'))

    def test_form_open_denies_indirect_begin(self):
        app, context, _ = self.app()
        form = FormSession('&AtClient\nProcedure Opening(Cancel) Gateway.Go(); EndProcedure',
                           bindings={'OnOpen':'Opening'}, database_context=context,
                           interpreter_factory=app.form_interpreter_factory)
        self.addCleanup(form.interpreter.close)
        self.assert_refused(context.backend, form.open)
        self.assertEqual(form.state, 'failed')
        app.execute('Gateway.Go();')

    def test_caught_form_failure_does_not_widen_same_event(self):
        app, context, _ = self.app()
        form = FormSession('&AtClient\nProcedure Opening(Cancel) '
                           'Try Gateway.Go(); Except EndTry; BeginTransaction(); EndProcedure',
                           bindings={'OnOpen':'Opening'}, database_context=context,
                           interpreter_factory=app.form_interpreter_factory)
        self.addCleanup(form.interpreter.close)
        self.assert_refused(context.backend, form.open)
        app.execute('Gateway.Go();')

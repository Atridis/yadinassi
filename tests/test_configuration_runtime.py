from contextlib import ExitStack, redirect_stdout, redirect_stderr
from dataclasses import replace
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from yadinassi.cli import main
from yadinassi.configuration_modules import MODULE_RUNTIME, compile_module
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.errors import BSLError
from yadinassi.runtime import Interpreter
from configuration_runtime_fixture import CLIENT, SERVER, module_files


class ModuleValidationTests(unittest.TestCase):
    def test_import_is_opt_in_and_keeps_exact_source(self):
        files = module_files([CLIENT])
        self.assertTrue(import_configuration(files).activation_issues)
        config = import_configuration(files, module_runtime=MODULE_RUNTIME)
        self.assertFalse(config.activation_issues)
        self.assertEqual({f.path: f.content for f in config.files}, files)
        self.assertEqual(config.common_modules[0].name, 'Tools')
        self.assertEqual(config.modules[-1].kind, 'CommonModule')

    def test_common_body_and_variables_are_rejected(self):
        for source in ('Var X;', 'Message("unexpected");', 'X = 1;',
                       'Procedure P() EndProcedure\nX = 1;'):
            with self.subTest(source=source), self.assertRaises((ValueError, BSLError)):
                ConfigurationApplication.from_files(module_files([('Tools', source, {})]))

    def test_authority_and_reuse_flags_fail_closed(self):
        for flags in ({'Privileged': 'true'}, {'ClientOrdinaryApplication': 'true'},
                      {'ExternalConnection': 'true'}, {'ReturnValuesReuse': 'DuringSession'},
                      {'Server': 'yes'}, {'ClientManagedApplication': 'false'}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                ConfigurationApplication.from_files(module_files([('Tools', CLIENT[1], flags)]))

    def test_servercall_invalid_combinations(self):
        for flags in ({'ServerCall': 'true'}, {**SERVER, 'Global': 'true'},
                      {**SERVER, 'ClientManagedApplication': 'true'}, {**SERVER, 'Server': 'false'}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                ConfigurationApplication.from_files(module_files([('Tools', CLIENT[1], flags)]))

    def test_unknown_properties_remain_activation_issues(self):
        files = module_files([CLIENT])
        files['CommonModules/Tools.xml'] = files['CommonModules/Tools.xml'].replace(
            b'<Properties>', b'<Properties><UnknownBehavior>true</UnknownBehavior>')
        config = import_configuration(files, module_runtime=MODULE_RUNTIME)
        self.assertTrue(config.activation_issues)
        with self.assertRaises(ValueError): ConfigurationApplication(config)

    def test_missing_source_uuid_name_and_orphan_rejected(self):
        for kind in ('missing', 'name', 'duplicate', 'orphan'):
            files = module_files([CLIENT])
            if kind == 'missing': del files['CommonModules/Tools/Ext/Module.bsl']
            elif kind == 'name': files['CommonModules/Tools.xml'] = files['CommonModules/Tools.xml'].replace(b'<Name>Tools', b'<Name>Other')
            elif kind == 'duplicate': files['Configuration.xml'] = files['Configuration.xml'].replace(b'</ChildObjects>', b'<CommonModule>Tools</CommonModule></ChildObjects>')
            else: files['CommonModules/Orphan/Ext/Module.bsl'] = b'// orphan'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                ConfigurationApplication.from_files(files)

    def test_session_object_and_other_modules_remain_closed(self):
        for path in ('Ext/SessionModule.bsl', 'Ext/ExternalConnectionModule.bsl',
                     'Catalogs/Products/Ext/ObjectModule.bsl'):
            files = module_files([CLIENT]); files[path] = b'Procedure P() EndProcedure'
            with self.subTest(path=path), self.assertRaises(ValueError): ConfigurationApplication.from_files(files)

    def test_annotations_and_imports_rejected(self):
        for source in ('&AtClient\nProcedure P() EndProcedure', 'Import Other;',
                       '&AtServer\nProcedure P() EndProcedure'):
            with self.subTest(source=source), self.assertRaises((ValueError, BSLError)):
                ConfigurationApplication.from_files(module_files([('Tools', source, {})]))

    def test_async_server_rejected(self):
        with self.assertRaises((ValueError, BSLError)):
            ConfigurationApplication.from_files(module_files([('Tools', 'Async Function F() Export Return 1; EndFunction', SERVER)]))

    def test_preflight_collisions_before_initializer_effects(self):
        cases = [([('Message', CLIENT[1], {})], ''),
                 ([CLIENT], 'Var Tools;'),
                 ([('G', 'Function Message() Export Return 1; EndFunction', {'Global': 'true'})], ''),
                 ([('G', 'Function Work() Export Return 1; EndFunction', {'Global': 'true'}),
                   ('H', 'Function Work() Export Return 2; EndFunction', {'Global': 'true'})], ''),
                 ([('G', 'Function Work() Export Return 1; EndFunction', {'Global': 'true'})], 'Procedure Work() EndProcedure')]
        for modules, app in cases:
            output = []
            with self.subTest(modules=modules), self.assertRaises(ValueError):
                ConfigurationApplication.from_files(module_files(modules, application=app+'\nMessage("side effect");'), output=output.append)
            self.assertEqual(output, [])

    def test_duplicate_declarations_and_unknown_profile_rejected(self):
        with self.assertRaises(BSLError):
            ConfigurationApplication.from_files(module_files([('Tools', 'Procedure P() EndProcedure\nProcedure P() EndProcedure', {})]))
        with self.assertRaises(ValueError): import_configuration(module_files(), module_runtime='anything')

    def test_forged_config_is_not_activation_authority(self):
        config = import_configuration(module_files([CLIENT]), module_runtime=MODULE_RUNTIME)
        with self.assertRaises(ValueError): ConfigurationApplication(replace(config, common_modules=()))
        with self.assertRaises(TypeError): ConfigurationApplication(replace(config, module_runtime=None))


class ConfiguredCallsTests(unittest.TestCase):
    def app(self, modules=(CLIENT,), application=''):
        output = []
        app = ConfigurationApplication.from_files(module_files(modules, application=application), output=output.append)
        self.addCleanup(app.close, force=True)
        app.start()
        return app, output

    def test_named_export_private_routine_and_casefold(self):
        source = 'Function Hidden(X) Return X+1; EndFunction\nFunction Public(X) Export Return Hidden(X)*2; EndFunction'
        app, output = self.app([('Tools', source, {})])
        app.execute('Message(tOoLs.pUbLiC(3));')
        self.assertEqual(output, ['8'])
        with self.assertRaises(BSLError): app.execute('Tools.Hidden(1);')

    def test_same_side_byref_defaults_and_procedure(self):
        source = 'Procedure Add(X, Val N = 2) Export X = X+N; EndProcedure'
        app, output = self.app([('Tools', source, {})])
        app.execute('X=1; Tools.Add(X,); Message(X);')
        self.assertEqual(output, ['3'])
        with self.assertRaises(BSLError): app.execute('Y=Tools.Add(X);')

    def test_global_exports_call_private_helpers(self):
        source = 'Function Helper() Return 7; EndFunction\nFunction Public() Export Return Helper(); EndFunction'
        app, output = self.app([('GlobalTools', source, {'Global': 'true'})])
        app.execute('Message(Public());')
        self.assertEqual(output, ['7'])
        with self.assertRaises(BSLError): app.execute('Helper();')
        with self.assertRaises(BSLError): app.execute('GlobalTools.Public();')

    def test_cross_module_repeated_nested_calls(self):
        app, output = self.app([CLIENT, ('Other', 'Function Go(Val X) Export Return Tools.Double(X)+Tools.Double(X); EndFunction', {})])
        app.execute('Message(Other.Go(2)); Message(Other.Go(3));')
        self.assertEqual(output, ['8', '12'])

    def test_two_context_copies_selected_by_caller(self):
        source = '#If Client Then\nFunction Side() Export Return "client"; EndFunction\n#Else\nFunction Side() Export Return "server"; EndFunction\n#EndIf'
        app, output = self.app([('Both', source, {'Server': 'true'}),
            ('Gateway', 'Function Go() Export Return Both.Side(); EndFunction', SERVER)])
        app.execute('Message(Both.Side()); Message(Gateway.Go());')
        self.assertEqual(output, ['client', 'server'])

    def test_global_two_context_copies(self):
        source = '#If Client Then\nFunction Side() Export Return "client"; EndFunction\n#Else\nFunction Side() Export Return "server"; EndFunction\n#EndIf'
        app, output = self.app([('Both', source, {'Server': 'true', 'Global': 'true'}),
            ('Gateway', 'Function Go() Export Return Side(); EndFunction', SERVER)])
        app.execute('Message(Side()); Message(Gateway.Go());')
        self.assertEqual(output, ['client', 'server'])

    def test_servercall_copy_in_out_and_value_result(self):
        source = 'Function Change(X, Val Y) Export X.Add(2); Y.Add(3); Return X; EndFunction'
        app, output = self.app([('Gateway', source, SERVER)])
        app.execute('X=New Array; Y=X; R=Gateway.Change(X,Y); R.Add(4); Message(X.Count()); Message(Y.Count()); Message(R.Count());')
        self.assertEqual(output, ['1', '0', '2'])

    def test_unsupported_crossing_argument_before_side_effects(self):
        source = 'Procedure P(Val A, B) Export EndProcedure'
        app, output = self.app([('Gateway', source, SERVER)], 'Function Effect() Message("bad"); Return 1; EndFunction')
        with self.assertRaises(BSLError): app.execute('Gateway.P(Effect(), New Structure);')
        self.assertEqual(output, [])

    def test_unavailable_context_before_argument_effects(self):
        app, output = self.app([('Hidden', CLIENT[1], {'ClientManagedApplication': 'false', 'Server': 'true'})],
                              'Function Effect() Message("bad"); Return 1; EndFunction')
        with self.assertRaises(BSLError): app.execute('Hidden.Double(Effect());')
        self.assertEqual(output, [])

    def test_server_cannot_enter_client_module(self):
        app, output = self.app([CLIENT, ('Gateway', 'Function Go() Export Return Tools.Double(1); EndFunction', SERVER)])
        with self.assertRaises(BSLError): app.execute('Gateway.Go();')
        self.assertEqual(output, [])

    def test_stored_receiver_eval_and_identity(self):
        app, output = self.app()
        app.execute('M=Eval("Tools"); Message(M=Tools); Message(M.Double(3));')
        self.assertEqual(output, ['Да', '6'])

    def test_callback_by_receiver_and_string(self):
        source = 'Function Done(Val Result, Val Extra) Export Return Result+Extra; EndFunction'
        app, output = self.app([('Tools', source, {})])
        app.execute('C=New CallbackDescription("Done", Tools, 3); Message(RunCallback(C, 2)); C=New CallbackDescription("Done", "Tools", 4); Message(RunCallback(C, 2));')
        self.assertEqual(output, ['5', '6'])

    def test_async_await_and_callback_use_existing_scheduler(self):
        source = 'Async Function Double(Val X) Export Return X*2; EndFunction'
        app, output = self.app([('Tools', source, {})])
        app.execute('Async Procedure Go() Message(Await Tools.Double(3)); EndProcedure\nGo();')
        app.interpreter.ensure_complete()
        self.assertEqual(output, ['6'])

    def test_application_exports_persistent_state_and_instance_isolation(self):
        source = 'Function Go() Export Return Next(); EndFunction'
        program = 'Var N;\nFunction Next() Export N=N+1; Return N; EndFunction\nN=0;'
        app, output = self.app([('Tools', source, {})], program)
        other, other_output = self.app([('Tools', source, {})], program)
        app.execute('Message(Tools.Go()); Message(Tools.Go());')
        other.execute('Message(Tools.Go());')
        self.assertEqual(output, ['1', '2']); self.assertEqual(other_output, ['1'])

    def test_readonly_metadata_registry(self):
        app, output = self.app()
        app.execute('Message(Metadata.CommonModules.Count()); Message(Metadata.CommonModules.Find("tools").Name); Message(Metadata.CommonModules["Tools"].ClientManagedApplication);')
        self.assertEqual(output, ['1', 'Tools', 'Да'])
        for command in ('Metadata.CommonModules.Tools.Name="X";', 'Tools=1;', 'Var Tools;',
                        'Procedure Tools() EndProcedure', 'Import Other;'):
            with self.subTest(command=command), self.assertRaises(BSLError): app.execute(command)

    def test_global_declaration_cannot_replace_registry(self):
        app, _ = self.app([('G', 'Function Public() Export Return 1; EndFunction', {'Global': 'true'})])
        with self.assertRaises(BSLError): app.execute('Function Public() Return 9; EndFunction')

    def test_ordinary_errors_are_catchable_and_registry_survives(self):
        app, output = self.app([('Tools', 'Procedure Fail() Export Raise "boom"; EndProcedure', {})])
        app.execute('Try Tools.Fail(); Except Message("caught"); EndTry;')
        app.execute('Try Tools.Fail(); Except Message("again"); EndTry;')
        self.assertEqual(output, ['caught', 'again'])

    def test_no_context_entry_can_call_stateless_common_module(self):
        app, output = self.app()
        app.execute('&AtClientAtServerNoContext\nFunction Go() Return Tools.Double(2); EndFunction\nMessage(Go());')
        self.assertEqual(output, ['4'])

    def test_other_scheduler_cannot_bind(self):
        app, _ = self.app()
        outsider = Interpreter()
        self.addCleanup(outsider.close)
        with self.assertRaises(ValueError): app.bind_interpreter(outsider)


class ApplicationLifecycleTests(unittest.TestCase):
    def prepare(self, source):
        output = []
        app = ConfigurationApplication.from_files(module_files([CLIENT], application=source), output=output.append)
        self.addCleanup(app.close, force=True)
        return app, output

    def test_start_and_close_order_with_deferred_constructor(self):
        app, output = self.prepare('Procedure BeforeStart(Cancel) Message("before"); EndProcedure\nProcedure OnStart() Message(Tools.Double(2)); EndProcedure\nProcedure BeforeExit(Cancel, WarningText) Message("leaving"); EndProcedure\nProcedure OnExit() EndProcedure\nMessage("body");')
        self.assertEqual(output, [])
        self.assertTrue(app.start()); self.assertEqual(app.state, 'running')
        self.assertTrue(app.close()); self.assertTrue(app.close())
        self.assertEqual(output, ['body', 'before', '4', 'leaving'])

    def test_start_cancel_skips_onstart_and_cannot_restart(self):
        app, output = self.prepare('Procedure BeforeStart(Cancel) Cancel=True; EndProcedure\nProcedure OnStart() Message("bad"); EndProcedure')
        self.assertFalse(app.start()); self.assertEqual(app.state, 'cancelled')
        self.assertEqual(output, [])
        with self.assertRaises(ValueError): app.start()
        with self.assertRaises(ValueError): app.execute('Message(1);')

    def test_shutdown_cancellation_keeps_state_and_retry(self):
        app, output = self.prepare('Var Closing;\nProcedure BeforeExit(Cancel, WarningText) Closing=Closing+1; Cancel=Closing=1; WarningText="pending"; EndProcedure\nClosing=0;')
        app.start(); self.assertFalse(app.close()); self.assertEqual(app.state, 'running')
        self.assertEqual(app.last_exit_warning, 'pending')
        app.execute('Message(Closing);'); self.assertTrue(app.close())
        self.assertEqual(output, ['1'])

    def test_start_and_exit_errors_close_lifetime(self):
        for source, phase in [('Procedure BeforeStart(Cancel) Raise "bad"; EndProcedure', 'start'),
                              ('Procedure OnExit() Raise "bad"; EndProcedure', 'exit')]:
            app, _ = self.prepare(source)
            if phase == 'exit': app.start()
            with self.subTest(phase=phase), self.assertRaises(BSLError):
                app.start() if phase == 'start' else app.close()
            self.assertEqual(app.state, 'failed')

    def test_shutdown_refuses_messages_async_and_server_calls(self):
        for source in ('Procedure OnExit() Message("bad"); EndProcedure',
                       'Async Procedure Later() Message("bad"); EndProcedure\nProcedure BeforeExit(Cancel, WarningText) Later(); EndProcedure',
                       'Async Procedure Later() EndProcedure\nProcedure OnExit() Later(); EndProcedure'):
            app, output = self.prepare(source); app.start()
            with self.subTest(source=source), self.assertRaises(BSLError): app.close()
            self.assertEqual(output, [])
        app = ConfigurationApplication.from_files(module_files([('Gateway', 'Procedure P() Export EndProcedure', SERVER)],
            application='Procedure BeforeExit(Cancel, WarningText) Gateway.P(); EndProcedure'))
        self.addCleanup(app.close, force=True); app.start()
        with self.assertRaises(BSLError): app.close()

    def test_onexit_cannot_publish_precreated_user_message(self):
        for command in ('M.Message();', 'Send = M.Message; Send();'):
            app, output = self.prepare('Var M;\nProcedure OnExit() ' + command +
                ' EndProcedure\nM=New UserMessage; M.Text="bad";')
            app.start()
            with self.subTest(command=command), self.assertRaises(BSLError): app.close()
            self.assertEqual(output, [])

    def test_lifecycle_handler_cannot_be_replaced_after_validation(self):
        app, output = self.prepare('Procedure BeforeExit(Cancel, WarningText) Message("original"); EndProcedure')
        app.start()
        with self.assertRaises(BSLError):
            app.execute('Procedure BeforeExit(Cancel, WarningText) Message("replacement"); EndProcedure')
        app.close(); self.assertEqual(output, ['original'])

    def test_event_signatures_are_not_guessed(self):
        for source in ('Function OnStart() Return 1; EndFunction', 'Async Procedure OnStart() EndProcedure',
                       'Procedure BeforeStart(Val Cancel) EndProcedure', 'Procedure BeforeExit(Cancel) EndProcedure',
                       'Procedure OnStart() EndProcedure\nProcedure ПриНачалеРаботыСистемы() EndProcedure'):
            with self.subTest(source=source), self.assertRaises(ValueError): self.prepare(source)

    def test_cancellation_types_checked_and_force_does_not_invoke_handlers(self):
        app, _ = self.prepare('Procedure BeforeStart(Cancel) Cancel=1; EndProcedure')
        with self.assertRaises(TypeError): app.start()
        app, output = self.prepare('Procedure BeforeExit(Cancel, WarningText) Message("bad"); EndProcedure')
        app.start(); self.assertTrue(app.close(force=True)); self.assertEqual(output, [])

    def test_russian_lifecycle_names(self):
        app, output = self.prepare('Процедура ПередНачаломРаботыСистемы(Отказ) Сообщить("до"); КонецПроцедуры\nПроцедура ПриНачалеРаботыСистемы() Сообщить("после"); КонецПроцедуры')
        app.start(); app.close(); self.assertEqual(output, ['до', 'после'])


class ConfigurationRuntimeStorageTests(unittest.TestCase):
    def test_create_reopen_does_not_execute_and_explicit_start_does(self):
        files = module_files([CLIENT], application='Message("start");')
        config = import_configuration(files, module_runtime=MODULE_RUNTIME)
        with tempfile.TemporaryDirectory() as temp, ExitStack() as owners:
            path = Path(temp)/'owned.sqlite'
            context = SQLiteDBContext.create(path, config); context.close()
            context = SQLiteDBContext(path)
            owners.callback(context.close)
            output = []
            app = ConfigurationApplication.from_database(context, output=output.append)
            owners.callback(app.close, force=True)
            self.assertEqual(output, []); app.start(); app.execute('Message(Tools.Double(3));')
            self.assertEqual(output, ['start', '6'])
            self.assertEqual(context.backend.export_configuration(), files)

    def test_cli_explicit_activation_and_ordinary_database_open(self):
        with tempfile.TemporaryDirectory() as temp:
            source, path = Path(temp)/'xml', Path(temp)/'db.sqlite'
            for name, value in module_files([CLIENT], application='Message("start");').items():
                target = source/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)
            def run(args):
                out, err = StringIO(), StringIO()
                with redirect_stdout(out), redirect_stderr(err): result = main(args)
                return result, out.getvalue(), err.getvalue()
            result = run(['--create-db', str(path), '--import-xml', str(source), '--module-runtime', MODULE_RUNTIME])
            self.assertEqual(result[0], 0, result); self.assertNotIn('start', result[1])
            result = run(['--f', str(path), '-c', 'Message(2);'])
            self.assertEqual(result[:2], (0, '2\n'), result)
            result = run(['--f', str(path), '--module-runtime', MODULE_RUNTIME, '-c', 'Message(Tools.Double(3));'])
            self.assertEqual(result[:2], (0, 'start\n6\n'), result)


class AdditionalConfigurationBoundaryTests(unittest.TestCase):
    def test_metadata_is_absent_without_opt_in(self):
        interpreter = Interpreter()
        self.addCleanup(interpreter.close)
        with self.assertRaises(BSLError): interpreter.execute('Message(Metadata.CommonModules.Count());')

    def test_server_error_has_no_partial_copyback(self):
        app = ConfigurationApplication.from_files(module_files([('Gateway',
            'Procedure Fail(X) Export X.Add(1); Raise "bad"; EndProcedure', SERVER)]))
        self.addCleanup(app.close, force=True); app.start()
        app.execute('A=New Array; Try Gateway.Fail(A); Except EndTry;')
        self.assertEqual(len(app.interpreter.variables['a'].items), 0)

    def test_dynamic_assignment_does_not_replace_module(self):
        app = ConfigurationApplication.from_files(module_files([CLIENT]))
        self.addCleanup(app.close, force=True); app.start()
        app.execute('Execute("Tools=7;"); Result=Tools.Double(2);')
        self.assertEqual(app.interpreter.variables["result"], 4)

    def test_host_interpreter_binding_reuses_module_state_and_exports(self):
        output = []
        app = ConfigurationApplication.from_files(module_files([CLIENT], application=
            'Var N; Function Next() Export N=N+1; Return N; EndFunction\nN=0;'), output=output.append)
        self.addCleanup(app.close, force=True); app.start()
        child = app.interpreter._activation_interpreter()
        child._scheduler = app.interpreter._scheduler
        app.bind_interpreter(child)
        child.execute('Message(Tools.Double(Next()));')
        app.execute('Message(Next());')
        self.assertEqual(output, ['2', '2'])

    def test_rebinding_foreign_application_is_rejected(self):
        first = ConfigurationApplication.from_files(module_files([CLIENT]))
        second = ConfigurationApplication.from_files(module_files([CLIENT]))
        self.addCleanup(first.close, force=True); self.addCleanup(second.close, force=True)
        with self.assertRaises(ValueError): first.bind_interpreter(second.interpreter)

    def test_global_unavailable_on_client_rejected_before_effect(self):
        out = []
        app = ConfigurationApplication.from_files(module_files([('G',
            'Function Public(Val X) Export Return X; EndFunction',
            {'Global': 'true', 'ClientManagedApplication': 'false', 'Server': 'true'})],
            application='Function Effect() Message("bad"); Return 1; EndFunction'), output=out.append)
        self.addCleanup(app.close, force=True); app.start()
        with self.assertRaises(BSLError): app.execute('Public(Effect());')
        self.assertEqual(out, [])

    def test_closed_lifetime_cannot_be_used_through_bound_child(self):
        app = ConfigurationApplication.from_files(module_files([CLIENT]))
        child = app.interpreter._activation_interpreter(); child._scheduler = app.interpreter._scheduler
        app.bind_interpreter(child); app.start(); app.close()
        with self.assertRaises(ValueError): child.execute('Tools.Double(1);')

    def test_source_and_schema_must_match_connected_database(self):
        files = module_files([CLIENT]); config = import_configuration(files, module_runtime=MODULE_RUNTIME)
        with tempfile.TemporaryDirectory() as temp:
            context = SQLiteDBContext.create(Path(temp)/'db.sqlite', config)
            try:
                files['CommonModules/Tools/Ext/Module.bsl'] = CLIENT[1].replace('* 2', '* 3').encode()
                with self.assertRaises(ValueError):
                    ConfigurationApplication.from_files(files, database_context=context)
            finally: context.close()


class ModuleOnlyConfigurationTests(unittest.TestCase):
    def files(self, modules=(), application=''):
        files = module_files(modules, application=application)
        files = {path: content for path, content in files.items() if not path.startswith('Catalogs/')}
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'<Catalog>Categories</Catalog><Catalog>Products</Catalog>', b'')
        return files

    def test_common_module_only_configuration(self):
        output = []
        app = ConfigurationApplication.from_files(self.files([CLIENT]), output=output.append)
        self.addCleanup(app.close, force=True); app.start()
        app.execute('Message(Tools.Double(2));'); self.assertEqual(output, ['4'])
        self.assertEqual(app.configuration.catalogs, ())

    def test_application_only_configuration(self):
        output = []
        app = ConfigurationApplication.from_files(self.files(application='Message("start");'), output=output.append)
        self.addCleanup(app.close, force=True); self.assertEqual(output, [])
        app.start(); self.assertEqual(output, ['start'])

    def test_default_importer_and_storage_zero_inventory_stay_closed(self):
        from yadinassi.catalog_backend import BackendError
        files = self.files([CLIENT])
        with self.assertRaises(ValueError): import_configuration(files)
        config = import_configuration(files, module_runtime=MODULE_RUNTIME)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'db.sqlite'
            with self.assertRaises(BackendError): SQLiteDBContext.create(path, config)
            self.assertFalse(path.exists())

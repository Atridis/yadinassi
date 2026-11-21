import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLError
from yadinassi.cli import main


def source(code=b'', extra=None):
    xml = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Configuration uuid="00000000-0000-0000-0000-000000000001"><Properties><Name>Demo</Name></Properties></Configuration></MetaDataObject>'
    files = {'Configuration.xml': xml, 'Ext/ManagedApplicationModule.bsl': code}
    files.update(extra or {})
    return import_source(files)


class SourceStartupTests(unittest.TestCase):
    def test_platform_services_do_not_enable_python_registration(self):
        app = SourceApplication(source())
        self.addCleanup(app.close)
        vm = app.interpreter
        self.assertFalse(vm.allow_extensions)
        self.assertIs(vm.functions['safemode'], vm.functions['безопасныйрежим'])
        self.assertIs(vm.types['systeminfo'], vm.types['системнаяинформация'])
        self.assertIs(vm._builtin_functions['safemode'][0], vm.functions['safemode'])
        self.assertIs(vm._builtin_types['systeminfo'][0], vm.types['systeminfo'])
        for register in (vm.register_function, vm.register_type):
            with self.assertRaisesRegex(ValueError, 'allow_extensions=True'):
                register('HostExtension', lambda: 1)
        self.assertTrue(app.start())
        self.assertIs(vm.execute('SafeMode()'), False)
        child = vm._activation_interpreter()
        self.addCleanup(child.close)
        self.assertFalse(child.allow_extensions)

    def test_explicit_python_extension_mode_propagates_to_source_family(self):
        app = SourceApplication(source(extra={'Ext/SessionModule.bsl':
            b'Procedure SessionParametersSetting(Names) EndProcedure'}),
            allow_extensions=True)
        self.addCleanup(app.close)
        vm = app.interpreter
        vm.register_function('HostExtension', lambda: 'host-result')
        self.assertTrue(app.start())
        self.assertEqual(vm.execute('HostExtension()'), 'host-result')
        self.assertTrue(app._session_owner.allow_extensions)
        child = vm._activation_interpreter()
        self.addCleanup(child.close)
        self.assertTrue(child.allow_extensions)

    def test_start_event_runs(self):
        output = []
        app = SourceApplication(source(b'Procedure OnStart()\n Message("ready");\nEndProcedure'), output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, ['ready'])
        app.close()

    def test_unused_broken_module_not_compiled(self):
        app = SourceApplication(source(extra={'CommonModules/Unused/Ext/Module.bsl': b'not valid ??'}))
        self.assertTrue(app.start())
        app.close()

    def test_unknown_service_has_source_location(self):
        app = SourceApplication(source(b'Procedure OnStart()\nUnknownService();\nEndProcedure'))
        with self.assertRaises(BSLError) as error:
            app.start()
        self.assertIn('ManagedApplicationModule.bsl', str(error.exception))
        self.assertEqual(app.state, 'failed')

    def test_metadata_source_name_is_not_empty_fake(self):
        output = []
        app = SourceApplication(source(b'Procedure OnStart()\nMessage(Metadata.Name);\nEndProcedure'), output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, ['Demo'])
        app.close()

    def test_cancel_is_respected(self):
        output = []
        code = b'Procedure BeforeStart(Cancel)\nCancel = True;\nEndProcedure\nProcedure OnStart()\nMessage("wrong");\nEndProcedure'
        app = SourceApplication(source(code), output=output.append)
        self.assertFalse(app.start())
        self.assertEqual(output, [])
        self.assertEqual(app.state, 'cancelled')

    def test_restart_rejected(self):
        app = SourceApplication(source())
        app.start()
        with self.assertRaises(ValueError): app.start()
        app.close()

    def test_bad_event_signature_rejected(self):
        app = SourceApplication(source(b'Function OnStart()\nReturn 1;\nEndFunction'))
        with self.assertRaisesRegex(ValueError, 'сигнатура'): app.start()

    def test_named_client_module_on_demand(self):
        xml = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Helpers</Name><ClientManagedApplication>true</ClientManagedApplication></Properties></CommonModule></MetaDataObject>'
        output = []
        app = SourceApplication(source(b'Procedure OnStart()\nMessage(Helpers.Answer());\nEndProcedure', {
            'CommonModules/Helpers.xml': xml,
            'CommonModules/Helpers/Ext/Module.bsl': b'Function Answer() Export\nReturn 42;\nEndFunction'}), output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, ['42'])
        app.close()

    def test_import_never_executes_without_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            for entry in source(b'UnknownService();').files:
                path = Path(directory) / entry.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(entry.content)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--configuration-source', directory]), 0)
                self.assertEqual(main(['--configuration-source', directory, '--run-startup']), 1)

    def test_source_archive_roundtrip_startup(self):
        from yadinassi.configuration.configuration_source import save_source_archive, load_source_archive
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.zip'
            save_source_archive(path, source())
            app = SourceApplication(load_source_archive(path))
            self.assertTrue(app.start())
            app.close()

    def test_session_event_precedes_application(self):
        output = []
        app = SourceApplication(source(b'Procedure OnStart()\nMessage("app");\nEndProcedure', {
            'Ext/SessionModule.bsl': b'Procedure SessionParametersSetting(Names)\nMessage("session");\nEndProcedure'}), output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, ['session', 'app'])
        app.close()

    def test_session_failure_not_skipped(self):
        app = SourceApplication(source(extra={
            'Ext/SessionModule.bsl': b'Procedure SessionParametersSetting(Names)\nUnknownService();\nEndProcedure'}))
        with self.assertRaisesRegex(BSLError, 'SessionModule.bsl'): app.start()
        self.assertEqual(app.state, 'failed')

    def test_privileged_module_fails_only_on_use(self):
        xml = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Helpers</Name><ClientManagedApplication>true</ClientManagedApplication><Privileged>true</Privileged></Properties></CommonModule></MetaDataObject>'
        extra = {'CommonModules/Helpers.xml': xml,
                 'CommonModules/Helpers/Ext/Module.bsl': b'Function Answer() Export\nReturn 42;\nEndFunction'}
        app = SourceApplication(source(extra=extra)); self.assertTrue(app.start()); app.close()
        app = SourceApplication(source(b'Procedure OnStart()\nMessage(Helpers.Answer());\nEndProcedure', extra))
        with self.assertRaisesRegex(BSLError, 'Режим общего модуля'): app.start()

    def test_same_side_server_module_from_session(self):
        xml = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Helpers</Name><Server>true</Server></Properties></CommonModule></MetaDataObject>'
        output = []
        app = SourceApplication(source(extra={
            'CommonModules/Helpers.xml': xml,
            'CommonModules/Helpers/Ext/Module.bsl': b'Function Answer() Export\nReturn 42;\nEndFunction',
            'Ext/SessionModule.bsl': b'Procedure SessionParametersSetting(Names)\nMessage(Helpers.Answer());\nEndProcedure'}), output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, ['42'])
        app.close()

    def test_mobile_symbols_false_in_nonmobile_profiles(self):
        from yadinassi.syntax.preprocessor import ConditionalCompilation, COMPILATION_PROFILES
        for profile in COMPILATION_PROFILES:
            for side in ('client', 'server', 'server_nocontext', 'dual_client', 'dual_server'):
                for symbol in ('MobileClient', 'МобильныйКлиент', 'MobileStandaloneServer',
                               'МобильныйАвтономныйСервер', 'MobileAppClient',
                               'МобильноеПриложениеКлиент', 'MobileAppServer', 'МобильноеПриложениеСервер'):
                    with self.subTest(profile=profile, side=side, symbol=symbol):
                        policy = ConditionalCompilation('<test>', side, compilation_profile=profile)
                        policy.process('#If ' + symbol + ' Then', 1, 1)
                        self.assertFalse(policy.active)

    def test_unknown_symbol_still_rejected(self):
        from yadinassi.syntax.preprocessor import ConditionalCompilation
        with self.assertRaisesRegex(BSLError, 'Неподдерживаемый символ'):
            ConditionalCompilation('<test>').process('#If ImaginaryPlatform Then', 1, 1)

    def test_keyword_property_names(self):
        from yadinassi.runtime import Interpreter
        vm = Interpreter(output=lambda x: None)
        for key in ('Procedure', 'Процедура', 'Function', 'If', 'True', 'Return'):
            with self.subTest(key=key):
                self.assertEqual(vm.execute('s = New Structure("' + key + '", 1); s.' + key + ' = 42; s.' + key), 42)
        vm.close()

    def test_keyword_standalone_is_not_variable(self):
        from yadinassi.syntax.parser import parse
        with self.assertRaises(BSLError): parse('Procedure = 42;')

    def test_local_name_precedes_common_module(self):
        xml = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Helpers</Name><ClientManagedApplication>true</ClientManagedApplication></Properties></CommonModule></MetaDataObject>'
        output = []
        app = SourceApplication(source(b'Function Echo(Helpers)\nReturn Helpers;\nEndFunction\nProcedure OnStart()\nMessage(Echo(42));\nEndProcedure', {'CommonModules/Helpers.xml': xml}), output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, ['42'])
        app.close()

    def test_invalid_archives_produce_concise_cli_errors(self):
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            for missing_manifest in (False, True):
                path = Path(directory) / 'bad.zip'
                if missing_manifest:
                    with zipfile.ZipFile(path, 'w') as archive:
                        archive.writestr('source/a', 'a')
                        archive.writestr('source/b', 'b')
                else:
                    path.write_bytes(b'not a ZIP')
                stderr = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                    self.assertEqual(main(['--configuration-source', str(path)]), 1)
                self.assertIn('invalid or unreadable', stderr.getvalue())
                self.assertNotIn('Traceback', stderr.getvalue())

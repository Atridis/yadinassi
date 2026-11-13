"""Explicit branch selection across source module kinds; not native parity."""
import unittest
from unittest.mock import patch

from test_configuration_source_runtime import source
from test_source_metadata import xml
from test_source_forms import files as form_files, request
from test_source_global_modules import configuration as global_configuration
from test_source_manager_modules import configuration as manager_configuration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication, _SourceInterpreter
from yadinassi.configuration_modules import compile_module, compile_session_module
from yadinassi.source_forms import SourceFormController
from yadinassi.form_program import compile_form_module, admitted_program
from yadinassi.errors import BSLError
from yadinassi.syntax import ast

PROFILE = 'managed-thick-file'
BODY = '''Function Answer() Export
#If ThickClientManagedApplication Then
 Return 42;
#Else
 Return 7;
#EndIf
EndFunction'''


class SourceCompilationProfiles(unittest.TestCase):
    def app(self, config, profile=PROFILE):
        output = []
        app = SourceApplication(config, output=output.append, compilation_profile=profile)
        self.addCleanup(app.close)
        app.start()
        return app, output

    def test_application_explicit_profile(self):
        _, output = self.app(source(b'#If ThickClientManagedApplication Then\nMessage(42);\n#Else\nMessage(7);\n#EndIf'))
        self.assertEqual(output, ['42'])

    def test_standalone_default_unchanged(self):
        _, output = self.app(source(b'#If ThickClientManagedApplication Then\nMessage(42);\n#Else\nMessage(7);\n#EndIf'), 'standalone')
        self.assertEqual(output, ['7'])

    def test_profile_is_fixed_for_application_lifetime(self):
        app, _ = self.app(source())
        with self.assertRaises(AttributeError):
            app.compilation_profile = 'standalone'
        self.assertEqual(app.interpreter.compilation_profile, PROFILE)

    def test_invalid_profile_fails_before_database_creation(self):
        with patch('yadinassi.source_constant_store.SourceConstantStore.create') as create:
            with self.assertRaises(ValueError):
                SourceApplication(source(), compilation_profile='guessed-native', scratch_database='unused')
            create.assert_not_called()

    def test_child_cannot_override_application_profile(self):
        app, _ = self.app(source())
        with self.assertRaisesRegex(ValueError, 'profile mismatch'):
            _SourceInterpreter(app, compilation_profile='standalone')

    def test_session_module_inherits_profile(self):
        _, output = self.app(source(extra={'Ext/SessionModule.bsl':
            ('Procedure SessionParametersSetting(Names)\n#If ThickClientManagedApplication Then\nMessage(42);\n#Else\nMessage(7);\n#EndIf\nEndProcedure').encode()}))
        self.assertEqual(output, ['42'])

    def test_named_common_module_each_side(self):
        for side in ('client', 'server'):
            with self.subTest(side=side):
                files = {'CommonModules/Helpers.xml': xml('CommonModule', 'Helpers', properties='<ClientManagedApplication>true</ClientManagedApplication><Server>true</Server>'),
                         'CommonModules/Helpers/Ext/Module.bsl': BODY.encode()}
                appcode = b'Procedure OnStart()\nMessage(Helpers.Answer());\nMessage(Helpers.Answer());\nEndProcedure'
                if side == 'server':
                    files['Ext/SessionModule.bsl'] = appcode.replace(b'OnStart()', b'SessionParametersSetting(Names)')
                    appcode = b''
                _, output = self.app(source(appcode, files))
                self.assertEqual(output, ['42', '42'])

    def test_global_module_discovery_and_execution_agree(self):
        body = '#If ThickClientManagedApplication Then\n' + BODY + '\n#EndIf'
        for side in (False, True):
            with self.subTest(server=side):
                _, output = self.app(global_configuration(modules=[('Helpers', body, False)], server=side))
                self.assertEqual(output, ['42'])

    def test_manager_module_inherits_profile(self):
        _, output = self.app(manager_configuration(body=BODY))
        self.assertEqual(output, ['42'])

    def test_client_does_not_gain_manager_authority(self):
        with self.assertRaisesRegex(BSLError, 'synchronous server'):
            self.app(manager_configuration(body=BODY, session=False))

    def test_profile_does_not_grant_privileged_module(self):
        with self.assertRaisesRegex(BSLError, 'Режим общего модуля'):
            self.app(global_configuration(modules=[('Helpers', BODY, True)]))

    def test_profile_does_not_fake_native_run_mode(self):
        _, output = self.app(source(b'Procedure OnStart()\nMessage(CurrentRunMode() = Undefined);\nEndProcedure'))
        self.assertEqual(output, ['Да'])

    def test_unknown_preprocessor_symbols_remain_errors(self):
        with self.assertRaisesRegex(BSLError, 'Неподдерживаемый символ'):
            self.app(source(b'#If ImaginaryClient Then\n#EndIf'))

    def test_configured_source_import_remains_rejected(self):
        with self.assertRaisesRegex(BSLError, 'импорты'):
            self.app(source('// #Импорт Dangerous.bsl'.encode()))

    def test_excluded_bad_module_remains_lazy(self):
        self.app(source(extra={'CommonModules/Unused/Ext/Module.bsl': b'???'}))

    def test_profiles_do_not_share_cached_common_modules(self):
        config = global_configuration(modules=[('Helpers', BODY, False)])
        _, first = self.app(config)
        _, second = self.app(config, 'standalone')
        self.assertEqual((first, second), (['42'], ['7']))

    def test_module_compilation_keeps_execution_side(self):
        code = b'#If Client Then\nFunction C() Export\nReturn 1;\nEndFunction\n#EndIf\n#If Server Then\nFunction S() Export\nReturn 2;\nEndFunction\n#EndIf'
        for side in ('client', 'server'):
            nodes = compile_module(code, 'Module.bsl', side, common=True, compilation_profile=PROFILE)
            self.assertEqual([n.name for n in nodes], ['C', 'S'])
            self.assertTrue(all(n.execution_context == side for n in nodes))

    def test_session_contract_still_checked(self):
        with self.assertRaisesRegex(ValueError, 'signature'):
            compile_session_module(b'Procedure SessionParametersSetting(Val Names)\nEndProcedure', compilation_profile=PROFILE)

    def test_form_compilation_records_profile_and_separates_sides(self):
        code = '#If ThickClientManagedApplication Then\n&AtClient\nProcedure C()\nEndProcedure\n&AtServer\nProcedure S()\nEndProcedure\n#EndIf'
        program = compile_form_module(code, compilation_profile=PROFILE)
        self.assertEqual([n.name for n in program.client.program()], ['C'])
        self.assertEqual([n.name for n in program.server.program()], ['S'])
        for side in (program.client, program.server, program.nocontext):
            self.assertEqual(side.compilation_profile, PROFILE)
            with self.assertRaisesRegex(ValueError, 'profile mismatch'):
                admitted_program(side, compilation_profile='standalone')

    def test_selected_form_create_and_command_use_same_profile(self):
        code = b'''&AtServer
Procedure Created(Cancel, StandardProcessing)
#If ThickClientManagedApplication Then
 Greeting = "created";
#Else
 Greeting = "wrong";
#EndIf
EndProcedure
&AtServer
Procedure UpdateAtServer()
 Greeting = Helpers.Text();
EndProcedure
&AtClient
Procedure Go(Command)
#If ThickClientManagedApplication Then
 UpdateAtServer();
#Else
 Greeting = "wrong";
#EndIf
EndProcedure'''
        files = form_files(code)
        files['CommonModules/Helpers/Ext/Module.bsl'] = BODY.replace('Answer', 'Text').replace('42', '"updated"').encode()
        app, _ = self.app(import_source(files))
        controller = SourceFormController(app, 'CommonForm.Main')
        self.assertIsNone(controller.exchange(request())['result']['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'], 'created')
        result = controller.exchange(request('event', event='command', revision=controller.client.session.revision, control='GoButton'))
        self.assertIsNone(result['result']['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'], 'updated')
        for vm in (controller.server.session.interpreter, controller.client.session.interpreter):
            self.assertEqual(vm.compilation_profile, PROFILE)
            child = vm._activation_interpreter()
            self.addCleanup(child.close)
            self.assertEqual(child.compilation_profile, PROFILE)

    def test_source_shell_uses_explicit_profile(self):
        from yadinassi.ui.source_shell import SourceShell
        shell = SourceShell(source(b'#If ThickClientManagedApplication Then\nMessage(42);\n#EndIf'),
                            run_startup=True, compilation_profile=PROFILE)
        self.assertEqual(shell.outcome, 'completed')
        self.assertEqual(shell.messages, ['42'])

    def test_ui_cli_passes_profile_to_diagnostic_startup(self):
        from yadinassi.ui.source_shell import main
        with patch('yadinassi.ui.source_shell.load_source_archive', return_value=source()) as load, \
             patch('yadinassi.ui.source_shell.SourceShell') as shell, \
             patch('yadinassi.ui.source_shell.LocalUIServer'):
            self.assertEqual(main(['--configuration-source', 'unused.zip', '--run-startup',
                                   '--preprocessor-profile', PROFILE]), 0)
            self.assertEqual(shell.call_args.kwargs['compilation_profile'], PROFILE)

    def test_ui_cli_passes_profile_to_selected_form_startup(self):
        from yadinassi.ui.source_shell import main
        with patch('yadinassi.ui.source_shell.load_source_archive', return_value=import_source(form_files())), \
             patch('yadinassi.ui.source_shell.SourceApplication') as app, \
             patch('yadinassi.source_forms.SourceFormController'), \
             patch('yadinassi.ui.source_shell.LocalUIServer'):
            self.assertEqual(main(['--configuration-source', 'unused.zip', '--run-startup',
                                   '--source-form', 'CommonForm.Main', '--preprocessor-profile', PROFILE]), 0)
            self.assertEqual(app.call_args.kwargs['compilation_profile'], PROFILE)

    def test_generic_nocontext_port_does_not_accept_another_profile(self):
        from yadinassi.invocation import InvocationServer
        program = compile_form_module('&AtServerNoContext\nFunction Answer(Val X)\nReturn X;\nEndFunction', compilation_profile=PROFILE)
        with self.assertRaisesRegex(ValueError, 'profile mismatch'):
            InvocationServer(program.nocontext, program.nocontext_endpoints)

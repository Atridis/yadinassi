"""Restored workspace features retain main's profile and application exports."""
import unittest
from test_source_forms import files, FORM, request
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_forms import SourceFormController
from yadinassi.ui.source_workspace import SourceWorkspace

CODE = b'''#If ThickClientManagedApplication Then
&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "created";
EndProcedure
&AtClient
Procedure Go(Command)
 Greeting = Answer();
EndProcedure
#EndIf'''


class SourceUIMainIntegrationTests(unittest.TestCase):
    def application(self, *, startup=False):
        mapping = files(CODE)
        mapping['Ext/ManagedApplicationModule.bsl'] = (
            ('Procedure OnStart() OpenForm("CommonForm.Main"); EndProcedure\n' if startup else '') +
            'Function Answer() Export Return "application-export"; EndFunction').encode()
        app = SourceApplication(import_source(mapping), compilation_profile='managed-thick-file')
        self.addCleanup(app.close)
        return app

    def check_command(self, controller):
        self.assertIsNone(controller.exchange(request())['result']['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'], 'created')
        result = controller.exchange(request('event', event='command', control='GoButton', revision=controller.client.session.revision))
        self.assertIsNone(result['result']['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'], 'application-export')

    def test_strict_and_progressive_forms_keep_profile_and_exports(self):
        for progressive in (False, True):
            with self.subTest(progressive=progressive):
                app = self.application()
                app.start()
                self.check_command(SourceFormController(app, 'CommonForm.Main', progressive=progressive))

    def test_startup_navigation_keeps_profile_and_exports(self):
        workspace = SourceWorkspace.start(self.application(startup=True))
        self.assertEqual(workspace.selected, 'CommonForm.Main')
        self.check_command(workspace.form)
        self.assertEqual(len(workspace.open_forms), 1)

"""Actual supported source form events, not browser/native parity claims."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from test_source_metadata import xml
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_forms import SourceFormController, source_form_definition
from yadinassi.ui.form_app import PROTOCOL

FORM = b'''<Form xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema" version="2.17"><Title>Counter</Title><Attributes><Attribute name="Greeting" id="1"><Type><v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>256</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers></Type></Attribute></Attributes><ChildItems><LabelField name="GreetingLabel" id="1"><DataPath>Greeting</DataPath></LabelField><Button name="GoButton" id="2"><CommandName>Go</CommandName><Title>Run</Title></Button></ChildItems><Commands><Command name="Go" id="1"><Title>Run</Title><Action>Go</Action></Command></Commands><Events><Event name="OnCreateAtServer">Created</Event></Events></Form>'''
CODE = b'''&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = Metadata.Name;
EndProcedure
&AtServer
Procedure UpdateAtServer()
 Greeting = Helpers.Text();
EndProcedure
&AtClient
Procedure Go(Command)
 UpdateAtServer();
EndProcedure'''


def files(code=CODE):
    return {'Configuration.xml': xml('Configuration', 'Demo', children='<CommonForm>Main</CommonForm><CommonModule>Helpers</CommonModule>'),
            'Ext/ManagedApplicationModule.bsl': b'',
            'CommonForms/Main.xml': xml('CommonForm', 'Main', properties='<FormType>Managed</FormType>'),
            'CommonForms/Main/Ext/Form.xml': FORM,
            'CommonForms/Main/Ext/Form/Module.bsl': code,
            'CommonModules/Helpers.xml': xml('CommonModule', 'Helpers', properties='<Server>true</Server><ClientManagedApplication>true</ClientManagedApplication>'),
            'CommonModules/Helpers/Ext/Module.bsl': b'Function Text() Export\nReturn "updated";\nEndFunction'}


def request(method='hello', **params):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'form.'+method,
            'params': {'protocol': PROTOCOL} if method=='hello' else params}


class SourceFormTests(unittest.TestCase):
    def app(self, mapping=None):
        app=SourceApplication(import_source(files() if mapping is None else mapping))
        self.addCleanup(app.close)
        app.start()
        return app

    def test_real_server_create_and_command_roundtrip(self):
        controller=SourceFormController(self.app(), 'CommonForm.Main')
        initial=controller.exchange(request())['result']
        self.assertIsNone(initial['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'], 'Demo')
        result=controller.exchange(request('event',event='command',revision=controller.client.session.revision,control='GoButton'))['result']
        self.assertIsNone(result['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'], 'updated')
        child = controller.client.session.interpreter._activation_interpreter()
        self.assertFalse(child._transaction_activation_allowed)

    def test_repeat_hello_does_not_repeat_startup(self):
        controller=SourceFormController(self.app(), 'CommonForm.Main')
        controller.exchange(request()); revision=controller.client.session.revision
        controller.exchange(request())
        self.assertEqual(controller.client.session.revision, revision)

    def test_unselected_bad_form_is_not_compiled(self):
        mapping=files(); mapping['CommonForms/Unused.xml']=xml('CommonForm','Unused',properties='<FormType>Managed</FormType>')
        mapping['Configuration.xml']=mapping['Configuration.xml'].replace(b'</ChildObjects>',b'<CommonForm>Unused</CommonForm></ChildObjects>')
        mapping['CommonForms/Unused/Ext/Form.xml']=b'<anything/>'
        controller=SourceFormController(self.app(mapping),'CommonForm.Main')
        self.assertIsNone(controller.exchange(request())['result']['error'])

    def test_unknown_form_not_synthesized(self):
        with self.assertRaisesRegex(ValueError,'declared source'):
            SourceFormController(self.app(),'CommonForm.Absent')

    def test_missing_form_definition_explicit(self):
        mapping=files();del mapping['CommonForms/Main/Ext/Form.xml']
        with self.assertRaisesRegex(ValueError,'definition missing'):
            SourceFormController(self.app(mapping),'CommonForm.Main')

    def test_unsupported_form_control_explicit(self):
        mapping=files();mapping['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'<ChildItems>',b'<ChildItems><UnknownWidget/>')
        with self.assertRaises(ValueError):SourceFormController(self.app(mapping),'CommonForm.Main')

    def test_application_must_have_started(self):
        app=SourceApplication(import_source(files()));self.addCleanup(app.close)
        with self.assertRaisesRegex(ValueError,'not running'):SourceFormController(app,'CommonForm.Main')

    def test_privileged_common_module_not_activated(self):
        mapping=files();mapping['CommonModules/Helpers.xml']=mapping['CommonModules/Helpers.xml'].replace(b'<Server>',b'<Privileged>true</Privileged><Server>')
        controller=SourceFormController(self.app(mapping),'CommonForm.Main');controller.exchange(request())
        result=controller.exchange(request('event',event='command',revision=controller.client.session.revision,control='GoButton'))['result']
        self.assertIsNotNone(result['error'])

    def test_closed_application_rejects_events(self):
        controller=SourceFormController(self.app(),'CommonForm.Main');controller.close()
        with self.assertRaisesRegex(ValueError,'not running'):controller.exchange(request())

    def test_safe_mode_effect_guard_in_client_event(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'must-not-exist.txt'
            code = CODE.replace(b' UpdateAtServer();', (' SetSafeMode(True);\n D = New TextDocument;\n D.SetText("blocked");\n D.Write("' + str(target) + '");').encode())
            controller = SourceFormController(self.app(files(code)), 'CommonForm.Main')
            controller.exchange(request())
            result = controller.exchange(request('event', event='command', revision=controller.client.session.revision, control='GoButton'))['result']
            self.assertIsNotNone(result['error'])
            self.assertFalse(target.exists())

    def test_cli_selected_form_is_actual_form_bridge(self):
        from yadinassi.ui.source_shell import main
        from yadinassi.ui.form_app import FormHandler
        with patch('yadinassi.ui.source_shell.load_source_archive', return_value=import_source(files())), patch('yadinassi.ui.source_shell.LocalUIServer') as server:
            self.assertEqual(main(['--configuration-source', 'unused.archive', '--run-startup', '--source-form', 'CommonForm.Main']), 0)
            args, kwargs = server.call_args
            self.assertIsInstance(args[0], SourceFormController)
            self.assertIs(kwargs['handler'], FormHandler)
            self.assertEqual(args[0].application.state, 'closed')

    def test_cli_form_cannot_gain_scratch_database(self):
        from yadinassi.ui.source_shell import main
        with self.assertRaises(SystemExit):
            main(['--configuration-source', 'unused', '--run-startup', '--source-form', 'CommonForm.Main', '--source-scratch-db', 'unused.sqlite'])

class SourceNoContextTests(unittest.TestCase):
    app = SourceFormTests.app
    def controller(self, body='Return Value+"/"+Metadata.Name;', call='Greeting=Calculate("ok");', *, server_call=False):
        source=('&AtServer\nProcedure Created(Cancel,StandardProcessing)\n Greeting="initial";\nEndProcedure\n&AtServerNoContext\nFunction Calculate(Val Value)\n'+body+'\nEndFunction\n')
        if server_call:
            source+='&AtServer\nProcedure Compute()\n'+call+'\nEndProcedure\n&AtClient\nProcedure Go(Command)\nCompute();\nEndProcedure'
        else:
            source+='&AtClient\nProcedure Go(Command)\n'+call+'\nEndProcedure'
        controller=SourceFormController(self.app(files(source.encode())),'CommonForm.Main')
        self.assertIsNone(controller.exchange(request())['result']['error']);return controller

    def run_command(self,controller):
        return controller.exchange(request('event',event='command',revision=controller.client.session.revision,control='GoButton'))['result']

    def test_nocontext_client_scalar_call_resolves_source_metadata(self):
        c=self.controller();self.assertIsNone(self.run_command(c)['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'ok/Demo')

    def test_nocontext_contextful_common_module_remains_explicitly_unavailable(self):
        c=self.controller('Return Helpers.Text();');self.assertIsNotNone(self.run_command(c)['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'initial')

    def test_same_server_call_uses_formless_activation(self):
        c=self.controller(server_call=True);self.assertIsNone(self.run_command(c)['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'ok/Demo')

    def test_nocontext_cannot_read_form_state_or_parameters(self):
        for expression in ('Greeting','Parameters','ThisObject','Items'):
            for server in (False,True):
                with self.subTest(expression=expression,server=server):
                    c=self.controller('Return '+expression+';',server_call=server)
                    self.assertIsNotNone(self.run_command(c)['error'])
                    self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'initial')

    def test_same_server_does_not_inherit_bound_form_services(self):
        for expression in ('GetAttributes()','New FormAttribute("Injected", New TypeDescription("String"))'):
            with self.subTest(expression=expression):
                c=self.controller('Return '+expression+';',server_call=True)
                self.assertIsNotNone(self.run_command(c)['error'])
                self.assertNotIn('Injected',dict(c.client.session.snapshot().attributes))

    def test_nocontext_non_scalar_result_rejected_by_existing_wire(self):
        c=self.controller('Return New Array;');self.assertIsNotNone(self.run_command(c)['error'])

    def test_nocontext_failures_do_not_replay_on_next_command(self):
        c=self.controller('Raise "failure";')
        self.assertIsNotNone(self.run_command(c)['error']);count=c.nocontext.server._requests
        self.assertIsNotNone(self.run_command(c)['error']);self.assertEqual(c.nocontext.server._requests,count+1)

    def test_nocontext_invocation_has_bounded_execution(self):
        c=self.controller('While True Do EndDo; Return "never";')
        self.assertIsNotNone(self.run_command(c)['error'])

    def test_nocontext_cannot_activate_database_transaction(self):
        c=self.controller('BeginTransaction(); Return "bad";')
        self.assertIsNotNone(self.run_command(c)['error'])
        self.assertIsNone(c.nocontext.prototype.database_context)

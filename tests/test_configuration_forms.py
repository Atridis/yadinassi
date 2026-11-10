"""Closed configuration-form compilation and execution, not native GUI evidence."""
from decimal import Decimal
from pathlib import Path
import unittest

from yadinassi.configuration_forms import load_configuration_forms, bind_parameters
from yadinassi.form_program import compile_form_module, FormSideProgram
from yadinassi.form_replication import ReplicatedFormSession, ReplicatedFormServer
from yadinassi.invocation import InvocationServer, InvocationPort
from yadinassi.structures import BSLStructure, BSLFixedStructure

ROOT = Path(__file__).resolve().parents[1] / 'examples/configuration-forms'


def sources(app='welcome'):
    root = ROOT / app
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def pair(definition, parameters=None):
    server = definition.create_server(parameters=parameters)
    program = definition.program
    client = ReplicatedFormSession(program.client, server.exchange,
        handlers=program.handlers, bindings=program.server_bindings,
        parameters={} if parameters is None else parameters)
    if program.nocontext_bindings:
        invocation = InvocationServer(program.nocontext, program.nocontext_endpoints)
        port = InvocationPort(invocation.exchange)
        for binding in invocation.bindings:
            client.bind_nocontext(port, binding)
    return server, client


class ConfigurationFormCompilerTests(unittest.TestCase):
    def test_side_programs_do_not_share_bodies(self):
        p = compile_form_module('&AtClient\nProcedure C()\nEndProcedure\n&AtServer\nProcedure S()\nEndProcedure\n&AtServerNoContext\nFunction N()\nReturn 1;\nEndFunction')
        self.assertEqual([n.name for n in p.client.program()], ['C'])
        self.assertEqual([n.name for n in p.server.program()], ['S', 'N'])
        self.assertEqual([n.name for n in p.nocontext.program()], ['N'])
        self.assertEqual(p.endpoints, {1:'S'})
        self.assertEqual(p.nocontext_endpoints, {1:'N'})

    def test_interpreter_ast_is_detached(self):
        p = compile_form_module('Procedure C()\nEndProcedure')
        p.client.program()[0].name = 'Changed'
        self.assertEqual(p.client.program()[0].name, 'C')

    def test_side_program_cannot_be_constructed(self):
        with self.assertRaises(TypeError):
            FormSideProgram('client', [], 'fake')

    def test_module_body_rejected(self):
        with self.assertRaises(ValueError):
            compile_form_module('Message("not a declaration");')

    def test_reserved_openform_declaration_rejected(self):
        with self.assertRaises(ValueError):
            compile_form_module('Procedure OpenForm()\nEndProcedure')

    def test_nocontext_non_val_rejected(self):
        with self.assertRaises(ValueError):
            compile_form_module('&AtServerNoContext\nFunction F(X)\nReturn X;\nEndFunction')

    def test_wrong_side_rejected(self):
        p = compile_form_module('Procedure C()\nEndProcedure')
        with self.assertRaises(ValueError):
            ReplicatedFormServer(p.client, {}, handlers=())

    def test_load_declared_common_forms_and_identity(self):
        config = load_configuration_forms(sources())
        self.assertEqual(config.name, 'WelcomeApp')
        self.assertEqual(len(config.forms), 2)
        self.assertEqual(config.resolve('COMMONFORM.WELCOME').name, 'CommonForm.Welcome')
        self.assertNotEqual(config.source_sha256, config.resolve('CommonForm.Welcome').source_sha256)

    def test_design_exists_before_create_event(self):
        files = sources()
        key = 'CommonForms/Welcome/Ext/Form/Module.bsl'
        files[key] = files[key].replace(b'Greeting = "Hello from a configuration form";',
            b'Greeting = Items.GreetingLabel.Name;')
        server, client = pair(load_configuration_forms(files).resolve('CommonForm.Welcome'))
        client.open()
        self.assertEqual(client.form._data['greeting'], 'GreetingLabel')
        self.assertIsNot(client.form, server.session.form)

    def test_immutable_parameters_separate_client_and_server(self):
        definition = load_configuration_forms(sources()).resolve('CommonForm.Details')
        parameters = BSLStructure('Message', 'Copied')
        server, client = pair(definition, parameters)
        parameters.set('Message', 'Changed')
        client.open()
        self.assertEqual(client.form._data['messagetext'], 'Copied')
        self.assertIs(type(client._parameters), BSLFixedStructure)
        self.assertIsNot(client._parameters, server.session._parameters)

    def test_parameters_reject_collection_and_late_bind(self):
        definition = load_configuration_forms(sources()).resolve('CommonForm.Welcome')
        with self.assertRaises(TypeError):
            definition.create_server(parameters={'Nested': BSLStructure()})
        server, client = pair(definition)
        client.open()
        with self.assertRaises(ValueError):
            bind_parameters(client, {})

    def test_second_configuration_server_and_nocontext_calls(self):
        definition = load_configuration_forms(sources('counter')).resolve('CommonForm.Counter')
        server, client = pair(definition)
        client.open()
        client.dispatch('command', revision=client.revision, control='IncrementButton')
        self.assertEqual(client.form._data['count'], Decimal(1))
        self.assertEqual(server.session.form._data['count'], Decimal(1))

    def test_unknown_xml_behavior_rejected(self):
        files = sources()
        key = 'CommonForms/Welcome/Ext/Form.xml'
        files[key] = files[key].replace(b'<Title>Welcome</Title>', b'<Title>Welcome</Title><AutoSave>true</AutoSave>')
        with self.assertRaises(ValueError):
            load_configuration_forms(files)

    def test_duplicate_uuid_rejected(self):
        files = sources()
        key = 'CommonForms/Details.xml'
        files[key] = files[key].replace(b'00000000-0000-0000-0000-000000000066', b'00000000-0000-0000-0000-000000000065')
        with self.assertRaises(ValueError):
            load_configuration_forms(files)

    def test_undeclared_form_is_not_activated(self):
        files = sources()
        files['CommonForms/Unlisted.xml'] = files['CommonForms/Welcome.xml']
        config = load_configuration_forms(files)
        with self.assertRaises(ValueError):
            config.resolve('CommonForm.Unlisted')

    def test_wrong_handler_arity_rejected_at_load(self):
        files = sources()
        key = 'CommonForms/Welcome/Ext/Form/Module.bsl'
        files[key] = files[key].replace(b'ShowDetails(Command)', b'ShowDetails()')
        with self.assertRaises(ValueError):
            load_configuration_forms(files)

    def test_dangling_control_target_rejected(self):
        files = sources()
        key = 'CommonForms/Welcome/Ext/Form.xml'
        files[key] = files[key].replace(b'<DataPath>Greeting</DataPath>', b'<DataPath>Missing</DataPath>')
        with self.assertRaises(ValueError):
            load_configuration_forms(files)

    def test_source_binding_changes_with_module(self):
        files = sources()
        before = load_configuration_forms(files)
        files['CommonForms/Welcome/Ext/Form/Module.bsl'] += b'\n// changed source\n'
        after = load_configuration_forms(files)
        self.assertNotEqual(before.source_sha256, after.source_sha256)
        self.assertNotEqual(before.resolve('CommonForm.Welcome').source_sha256,
                            after.resolve('CommonForm.Welcome').source_sha256)


if __name__ == '__main__':
    unittest.main()

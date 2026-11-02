"""Closed trusted application actions, not new public BSL or native Write APIs."""
import unittest
from unittest.mock import Mock

from test_form_runtime import SOURCE
from yadinassi.form_runtime import FormApplicationAction, FormActionResult, FormSession
from yadinassi.form_model import BSLFormAttribute
from yadinassi.type_descriptions import BSLTypeDescription


def session(callback, *, outputs=('Name',), source=SOURCE):
    return FormSession(source, attributes=(BSLFormAttribute('Name', BSLTypeDescription('String')),),
        initial_values={'Name': 'initial'}, bindings={'OnCreateAtServer': 'Create'},
        application_actions=(FormApplicationAction('Apply', 'ApplyCommand', ('Name',), outputs, callback),))


class FormApplicationActionTests(unittest.TestCase):
    def test_fixed_action_receives_detached_scalars_and_applies_typed_result(self):
        callback = Mock(return_value=FormActionResult((('Name', 'saved'),)))
        form = session(callback); form.open()
        result = form.dispatch('command', revision=1, control='ApplyButton')
        callback.assert_called_once_with((('Name', 'initial'),))
        self.assertEqual(dict(result.attributes)['Name'], 'saved')
        self.assertEqual(result.revision, 2)
        self.assertEqual(dict(result.item_views)['NameField'], 'InputField')

    def test_rebound_handler_cannot_reuse_capability(self):
        callback = Mock()
        form = session(callback, source=SOURCE.replace('C.Action = "ApplyCommand";', 'C.Action = "Changed";'))
        form.open()
        with self.assertRaises(ValueError): form.dispatch('command', revision=1, control='ApplyButton')
        callback.assert_not_called()
        self.assertEqual(form.revision, 1)

    def test_renderer_cannot_invoke_action_or_handler_name(self):
        callback = Mock()
        form = session(callback); form.open()
        for event, control in (('ApplyCommand', ''), ('command', 'Apply')):
            with self.assertRaises(ValueError): form.dispatch(event, revision=1, control=control)
        callback.assert_not_called()

    def test_invalid_result_does_not_partially_apply_patch(self):
        callback = lambda values: FormActionResult((('Name', 'partial'), ('Other', 'bad')))
        form = session(callback); form.open()
        with self.assertRaises(TypeError): form.dispatch('command', revision=1, control='ApplyButton')
        snapshot = form.snapshot()
        self.assertEqual(dict(snapshot.attributes)['Name'], 'initial')
        self.assertEqual(dict(snapshot.attributes)['Dynamic'], 'command')
        self.assertEqual(snapshot.revision, 2)

    def test_callback_exception_preserves_bsl_mutations_and_revision(self):
        form = session(Mock(side_effect=OSError('not a native rollback'))); form.open()
        with self.assertRaises(OSError): form.dispatch('command', revision=1, control='ApplyButton')
        self.assertEqual(dict(form.snapshot().attributes)['Dynamic'], 'command')
        self.assertEqual(form.revision, 2)

    def test_callback_cannot_reenter_or_snapshot_active_event(self):
        def callback(values):
            with self.assertRaises(ValueError): form.snapshot()
            with self.assertRaises(ValueError): form.dispatch('close', revision=1)
            return FormActionResult()
        form = session(callback); form.open()
        form.dispatch('command', revision=1, control='ApplyButton')
        self.assertEqual(form.revision, 2)

    def test_registration_rejects_unknown_attributes_and_mutable_schema(self):
        for outputs in (['Name'], ('Unknown',), ('Name', 'name')):
            with self.assertRaises(ValueError): session(lambda values: FormActionResult(), outputs=outputs)

    def test_result_cannot_export_host_objects_or_attribute_alias_collision(self):
        for result in (FormActionResult((('Name', object()),)), {'Name': 'bad'},
                       FormActionResult((('Unknown', 'bad'),))):
            form = session(lambda values: result); form.open()
            with self.assertRaises((TypeError, ValueError)):
                form.dispatch('command', revision=1, control='ApplyButton')
            self.assertEqual(dict(form.snapshot().attributes)['Name'], 'initial')

    def test_result_transfers_text_budget_by_shrinking_before_growth(self):
        from unittest.mock import patch
        source = '''
&AtServer
Procedure Create(Cancel, StandardProcessing)
 C = Commands.Add("Apply"); C.Action = "ApplyCommand";
 B = Items.Add("ApplyButton", Type("FormButton")); B.CommandName = "Apply";
EndProcedure
&AtClient
Procedure ApplyCommand(Command)
EndProcedure
'''
        attributes = tuple(BSLFormAttribute(key, BSLTypeDescription('String')) for key in ('First', 'Second', 'Third'))
        ack = Mock()
        with patch('yadinassi.form_model.MAX_TOTAL_TEXT', 20), patch('yadinassi.form_runtime.MAX_TOTAL_TEXT', 20):
            form = FormSession(source, attributes=attributes,
                initial_values={'First': '', 'Second': '1234567890', 'Third': 'abcdefghij'},
                bindings={'OnCreateAtServer': 'Create'}, application_actions=(
                    FormApplicationAction('Apply', 'ApplyCommand', (), ('First', 'Second'),
                        lambda values: FormActionResult((('First', 'ABCDEFGHIJ'), ('Second', ''))), ack),))
            form.open(); result = form.dispatch('command', revision=1, control='ApplyButton')
        self.assertEqual(dict(result.attributes), {'First': 'ABCDEFGHIJ', 'Second': '', 'Third': 'abcdefghij'})
        ack.assert_called_once_with()

    def test_application_acknowledgement_runs_only_after_valid_patch(self):
        ack = Mock()
        for result in (FormActionResult((('Name', 'bad\x00'),)), FormActionResult((('Unknown', 'bad'),))):
            form = FormSession(SOURCE, attributes=(BSLFormAttribute('Name', BSLTypeDescription('String')),),
                bindings={'OnCreateAtServer': 'Create'}, application_actions=(
                    FormApplicationAction('Apply', 'ApplyCommand', (), ('Name',), lambda values: result, ack),))
            form.open()
            with self.assertRaises(ValueError): form.dispatch('command', revision=1, control='ApplyButton')
        ack.assert_not_called()

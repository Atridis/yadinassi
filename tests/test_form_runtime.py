"""Ordinary local prototype tests; native automatic-event parity is pending."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi.form_runtime import FormSession, FormLimitError
from yadinassi.form_model import BSLFormAttribute
from yadinassi.type_descriptions import BSLTypeDescription

SOURCE = '''
&AtServer
Procedure Create(Cancel, StandardProcessing)
 A = New Array;
 A.Add(New FormAttribute("Dynamic", New TypeDescription("String")));
 ChangeAttributes(A);
 ThisObject.Dynamic = "created";
 F = Items.Add("NameField", Type("FormField"));
 F.DataPath = "Name";
 F.SetAction("OnChange", "Changed");
 C = Commands.Add("Apply");
 C.Action = "ApplyCommand";
 B = Items.Add("ApplyButton", Type("FormButton"));
 B.CommandName = "Apply";
EndProcedure
&AtClient
Procedure Open(Cancel)
 ThisObject.Dynamic = ThisObject.Dynamic + ":open";
EndProcedure
&AtClient
Procedure Changed(Element)
 ThisObject.Dynamic = "changed";
EndProcedure
&AtClient
Procedure ApplyCommand(Command)
 ThisObject.Dynamic = "command";
EndProcedure
&AtClient
Procedure Before(Cancel, Exit, MessageText, StandardProcessing)
 If ThisObject.Name = "stay" Then Cancel = True; EndIf;
EndProcedure
&AtClient
Procedure Closed(Exit)
 ThisObject.Dynamic = "closed";
EndProcedure
'''


def make(source=SOURCE):
    return FormSession(source, attributes=(BSLFormAttribute('Name',BSLTypeDescription('String')),),
        bindings={'OnCreateAtServer':'Create','OnOpen':'Open','BeforeClose':'Before','OnClose':'Closed'})


class FormRuntimeTests(unittest.TestCase):
    def test_card_complete_workflow(self):
        session=make(); first=session.open()
        self.assertEqual(dict(first.attributes),{'Name':'','Dynamic':'created:open'})
        changed=session.dispatch('change',revision=1,control='NameField',value='Ada')
        self.assertEqual(dict(changed.attributes),{'Name':'Ada','Dynamic':'changed'})
        command=session.dispatch('command',revision=2,control='ApplyButton')
        self.assertEqual(dict(command.attributes)['Dynamic'],'command')
        closed=session.dispatch('close',revision=3)
        self.assertEqual(closed.state,'closed')
        self.assertEqual(dict(closed.attributes)['Dynamic'],'closed')
        self.assertEqual(dict(first.attributes)['Name'],'')
        with self.assertRaises(ValueError):session.dispatch('close',revision=4)

    def test_cancel_close_and_revision(self):
        session=make();session.open()
        session.dispatch('change',revision=1,control='NameField',value='stay')
        result=session.dispatch('close',revision=2)
        self.assertEqual(result.state,'open')
        with self.assertRaises(ValueError):session.dispatch('close',revision=2)
        self.assertEqual(session.revision,3)

    def test_no_renderer_procedure_endpoint(self):
        session=make();session.open()
        for event in ('Create','eval','ApplyCommand'):
            with self.assertRaises(ValueError):session.dispatch(event,revision=1)
        with self.assertRaises(ValueError):session.dispatch('command',revision=1,control='Apply')

    def test_server_only_binding(self):
        source=SOURCE.replace('ThisObject.Dynamic = ThisObject.Dynamic + ":open";', 'Commands.Add("Wrong");')
        session=make(source)
        with self.assertRaises(Exception):session.open()
        self.assertTrue(session.closed)
        self.assertNotIn('wrong',session.form.commands._values)

    def test_dynamic_not_module_local(self):
        source=SOURCE.replace('ThisObject.Dynamic = ThisObject.Dynamic + ":open";', 'Dynamic = "local";')
        session=make(source);result=session.open()
        self.assertEqual(dict(result.attributes)['Dynamic'],'created')

    def test_set_once_data_path(self):
        source=SOURCE.replace('F.SetAction("OnChange", "Changed");','F.DataPath = "Name";')
        session=make(source)
        with self.assertRaises(Exception):session.open()
        self.assertEqual(session.form.items._values['namefield'].data_path,'Name')

    def test_binding_wrong_arity_rejected(self):
        with self.assertRaises(ValueError):make(SOURCE.replace('Procedure Open(Cancel)','Procedure Open()'))

    def test_no_global_initialization_or_async(self):
        with self.assertRaises(ValueError):make(SOURCE+'\nMessage("not run");')

    def test_execution_budget(self):
        session=make(SOURCE.replace('ThisObject.Dynamic = ThisObject.Dynamic + ":open";', 'While True Do EndDo;'))
        with patch('yadinassi.form_runtime.MAX_STEPS',100):
            with self.assertRaises(FormLimitError):session.open()
        self.assertFalse(session._busy)
        self.assertTrue(session.closed)

    def test_exception_retains_state_and_advances_revision(self):
        source=SOURCE.replace('ThisObject.Dynamic = "command";', 'ThisObject.Dynamic = "changed-before-error"; Raise "stop";')
        session=make(source);session.open()
        with self.assertRaises(Exception):session.dispatch('command',revision=1,control='ApplyButton')
        self.assertEqual(session.revision,2)
        self.assertEqual(dict(session.snapshot().attributes)['Dynamic'],'changed-before-error')
        self.assertFalse(session._busy)

    def test_initial_cancel(self):
        session=make(SOURCE.replace('A = New Array;', 'Cancel = True; A = New Array;'))
        snap=session.open()
        self.assertEqual(snap.state,'cancelled')
        self.assertTrue(session.closed)

    def test_wrong_type_event_value_preflight(self):
        session=make();session.open()
        with self.assertRaises(TypeError):session.dispatch('change',revision=1,control='NameField',value={})
        self.assertEqual(session.revision,1)

if __name__=='__main__':unittest.main()

class FormIntegrityTests(unittest.TestCase):
    def test_mutation_batch_is_atomic(self):
        source=SOURCE.replace('ThisObject.Dynamic = "created";', '''
        Bad = New Array;
        Bad.Add(New FormAttribute("Good", New TypeDescription("String")));
        Bad.Add(New FormAttribute("Dynamic", New TypeDescription("String")));
        Try ChangeAttributes(Bad); Except EndTry;
        ThisObject.Dynamic = "created";''')
        session=make(source);session.open()
        self.assertNotIn('good',session.form._attributes)

    def test_nocontext_cannot_access_form(self):
        source=SOURCE.replace('ThisObject.Dynamic = "command";', 'Detached();')+'''
&AtServerNoContext
Procedure Detached()
 ThisObject.Dynamic = "wrong";
EndProcedure
'''
        session=make(source);session.open()
        with self.assertRaises(Exception):session.dispatch('command',revision=1,control='ApplyButton')
        self.assertEqual(dict(session.snapshot().attributes)['Dynamic'],'created:open')

    def test_contextful_server_updates_form(self):
        source=SOURCE.replace('ThisObject.Dynamic = "command";', 'UpdateAtServer();')+'''
&AtServer
Procedure UpdateAtServer()
 ThisObject.Dynamic = "server";
EndProcedure
'''
        session=make(source);session.open()
        self.assertEqual(dict(session.dispatch('command',revision=1,control='ApplyButton').attributes)['Dynamic'],'server')

    def test_reentrancy_and_snapshot_denied_inside_handler(self):
        session=make();session.open()
        original=session._invoke
        def callback(*args):
            with self.assertRaises(ValueError):session.dispatch('close',revision=1)
            with self.assertRaises(ValueError):session.snapshot()
            return original(*args)
        with patch.object(session,'_invoke',callback):
            session.dispatch('command',revision=1,control='ApplyButton')
        self.assertEqual(session.revision,2)

    def test_readonly_and_disabled_edit(self):
        for assignment in ('F.ReadOnly = True;', 'F.Enabled = False;', 'F.Visible = False;'):
            session=make(SOURCE.replace('F.DataPath = "Name";', 'F.DataPath = "Name";'+assignment))
            session.open()
            with self.assertRaises(ValueError):session.dispatch('change',revision=1,control='NameField',value='x')
            self.assertEqual(dict(session.snapshot().attributes)['Name'],'')

    def test_allocation_ledger_and_no_partially_added_item(self):
        session=make()
        with patch('yadinassi.form_model.MAX_ALLOCATED',2):
            with self.assertRaises(Exception):session.open()
        self.assertEqual(session._allocated,2)
        self.assertEqual(tuple(session.form.commands._values),())

    def test_static_name_collision_and_subclass_admission(self):
        class Attr(BSLFormAttribute):pass
        for attr in (BSLFormAttribute('Items',BSLTypeDescription('String')),Attr('x',BSLTypeDescription('String'))):
            with self.assertRaises(ValueError):FormSession(SOURCE,attributes=(attr,))

    def test_collection_foreach(self):
        source=SOURCE.replace('ThisObject.Dynamic = ThisObject.Dynamic + ":open";', '''
        Counter = 0;
        For Each Item In Items Do Counter = Counter + 1; EndDo;
        ThisObject.Dynamic = String(Counter);''')
        session=make(source);self.assertEqual(dict(session.open().attributes)['Dynamic'],'2')

    def test_initial_cancel_snapshot_revision(self):
        session=make(SOURCE.replace('A = New Array;', 'Cancel = True; A = New Array;'))
        self.assertEqual(session.open().revision,session.revision)
        self.assertEqual(session.revision,1)

    def test_registry_codec_refusal(self):
        from yadinassi import type_values
        from yadinassi.values import BSLType
        session=make();session.open()
        self.assertIs(type_values.type_of(session.form),BSLType.FORM)
        self.assertIs(type_values.type_of(session.form.items),BSLType.FORM_ITEMS)
        self.assertIs(type_values.type_of(session.form.commands),BSLType.FORM_COMMANDS)

class FormScalarBoundaryTests(unittest.TestCase):
    def test_host_initial_data_without_generated_source(self):
        session=FormSession(SOURCE,attributes=(BSLFormAttribute('Name',BSLTypeDescription('String')),),
            initial_values={'Name':'quote"; Raise "not code";'},bindings={'OnCreateAtServer':'Create'})
        self.assertEqual(dict(session.open().attributes)['Name'],'quote"; Raise "not code";')

    def test_descriptor_mutation_is_detached_from_added_schema(self):
        source=SOURCE.replace('ChangeAttributes(A);', '''
        Descriptor=A[0]; Descriptor.Title="Label";
        ChangeAttributes(A); Descriptor.Name="Detached";
        Meta=GetAttributes(); Meta[0].Title="Copy";''')
        session=make(source);session.open()
        self.assertIn('dynamic',session.form._attributes)
        self.assertNotIn('detached',session.form._attributes)
        self.assertEqual(session.form._attributes['dynamic'].title,'Label')

    def test_messages_do_not_write_transport_stdout(self):
        source=SOURCE.replace('ThisObject.Dynamic = "command";', 'Message("notice");')
        session=make(source);session.open();session.dispatch('command',revision=1,control='ApplyButton')
        self.assertEqual(session.messages,('notice',))

    def test_static_nonval_transfer_explicitly_unsupported(self):
        source=SOURCE.replace('ThisObject.Dynamic = "command";', 'Mutate(Name);')+'''
&AtClient
Procedure Mutate(Value)
 Value="new";
EndProcedure
'''
        session=make(source);session.open()
        with self.assertRaises(Exception):session.dispatch('command',revision=1,control='ApplyButton')
        self.assertEqual(dict(session.snapshot().attributes)['Name'],'')

class FormStandardProcessingTests(unittest.TestCase):
    def test_create_standard_processing_is_not_ignored(self):
        for value in ('False','"bad"'):
            session=make(SOURCE.replace('A = New Array;', 'StandardProcessing='+value+'; A = New Array;'))
            with self.assertRaises(ValueError):session.open()
            self.assertEqual(session.state,'failed')
            self.assertEqual(session.revision,1)
            self.assertFalse(session._busy)

    def test_close_standard_processing_is_not_ignored(self):
        for value in ('False','"bad"'):
            session=make(SOURCE.replace('If ThisObject.Name = "stay"', 'StandardProcessing='+value+'; If ThisObject.Name = "stay"'))
            session.open()
            with self.assertRaises(ValueError):session.dispatch('close',revision=1)
            self.assertEqual(session.state,'open')
            self.assertEqual(session.revision,2)
            self.assertFalse(session._busy)

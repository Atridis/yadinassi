"""Actual demo import/event slice; full application and DB execution remain unsupported."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi.configuration.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.ui.configuration_app import load_application

ROOT=Path(__file__).resolve().parents[1]/'examples/demo'

class DirectFormTests(unittest.TestCase):
    def test_real_demo_import_database_reopen_and_created_without_vm_dispatch(self):
        files={p.relative_to(ROOT).as_posix():p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        config=import_main_demo_configuration(files,profile=PROFILE)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'demo.sqlite'
            SQLiteDBContext.create_main_demo(path,config).close()
            with SQLiteDBContext(path) as reopened:
                self.assertEqual(len(reopened.backend.accumulation_configuration.catalogs),3)
            before=path.read_bytes()
            app=load_application(ROOT,main_demo_application=True)
            server=app.forms['commonform.demowelcome'].create_server()
            session=server.session
            session._begin(session.revision)
            try:
                self.assertEqual(session._event('oncreateatserver',[False,True]),[False,True])
                self.assertEqual(session.form.get_member('Greeting'),'Справочники, документы и регистр накопления работают в одной базе')
            finally:
                session._busy=False
                session._gate.release()
            self.assertEqual(path.read_bytes(),before)

    def test_scalar_qualifier_constructors_in_form(self):
        from yadinassi.forms.form_runtime import FormSession
        session=FormSession("""
            &AtClient
            Procedure Opened(Cancel)
                N = New NumberQualifiers(5, 2);
                S = New КвалификаторыСтроки(12);
                D = New DateQualifiers;
                B = New КвалификаторыДвоичныхДанных(4);
                T = New TypeDescription("Number", N);
                ThisObject.Title = "qualifiers constructed";
            EndProcedure
        """, bindings={'OnOpen':'Opened'})
        self.addCleanup(session.interpreter.close)
        session.open()
        self.assertEqual(session.form.title,'qualifiers constructed')

    def test_form_qualifier_constructor_rejects_replaced_registration(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.forms.form_runtime import FormSession
        session=FormSession('&AtClient\nProcedure Opened(Cancel) '
                            'N = New NumberQualifiers(5, 2); EndProcedure',
                            bindings={'OnOpen':'Opened'})
        self.addCleanup(session.interpreter.close)
        factory=session.interpreter.types['numberqualifiers']
        with patch.object(factory, 'function', side_effect=AssertionError('foreign constructor')) as foreign:
            with self.assertRaisesRegex(BoundaryViolation, 'canonical registration'):
                session.open()
            foreign.assert_not_called()

    def test_event_transaction_service_rejected_before_effect(self):
        from yadinassi.forms.form_runtime import FormSession
        source='&AtServer\nProcedure Created(Cancel, StandardProcessing) BeginTransaction(); EndProcedure'
        session=FormSession(source,bindings={'OnCreateAtServer':'Created'})
        with patch('yadinassi.db.database_transactions.begin',side_effect=AssertionError('transaction effect')) as begin:
            with self.assertRaises(Exception):session.open()
            begin.assert_not_called()
        self.assertFalse(session._busy)
        self.assertEqual(session.interpreter.execution_context,'client')

    def test_loop_budget_and_closed_interpreter_reject(self):
        from yadinassi.forms.form_runtime import FormSession, FormLimitError
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        source='&AtServer\nProcedure Created(Cancel, StandardProcessing) While True Do EndDo; EndProcedure'
        session=FormSession(source,bindings={'OnCreateAtServer':'Created'})
        with patch('yadinassi.forms.form_runtime.MAX_STEPS',5):
            with self.assertRaises(FormLimitError):session.open()
        self.assertFalse(session._busy)
        session=FormSession('&AtServer\nProcedure Created(Cancel, StandardProcessing) EndProcedure',bindings={'OnCreateAtServer':'Created'})
        session.interpreter.close()
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertFalse(session._busy)

class DirectDeclarationTests(unittest.TestCase):
    def session(self,body,side='Server',*,allow_extensions=False):
        from yadinassi.forms.form_runtime import FormSession
        event='OnCreateAtServer' if side=='Server' else 'OnOpen'
        parameters='Cancel, StandardProcessing' if side=='Server' else 'Cancel'
        session=FormSession(f'&At{side}\nProcedure Event({parameters}) {body} EndProcedure',bindings={event:'Event'},allow_extensions=allow_extensions)
        self.addCleanup(session.interpreter.close)
        return session

    def test_dynamic_scalar_declaration_read_write_remove_without_vm(self):
        body=('A=New Array; A.Add(New FormAttribute("Text",New TypeDescription("String"))); '
              'A.Add(New РеквизитФормы("Total",New ОписаниеТипов("Number"))); ChangeAttributes(A); '
              'ThisObject.Text="hello"; ЭтотОбъект.Total=42; Message(ThisObject.Text); Message(ЭтотОбъект.Total); '
              'D=New Array; D.Add("Text"); ИзменитьРеквизиты(New Array,D);')
        session=self.session(body)
        session.open()
        self.assertNotIn('text',session.form._attributes)
        self.assertEqual(session.form._data['total'],42)
        self.assertFalse(session._busy)

    def test_constructor_override_rejected_before_argument_effect(self):
        from yadinassi.types.values import HostFunction
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        for constructor in ('TypeDescription','ОписаниеТипов','FormAttribute','РеквизитФормы'):
            session=self.session(f'A=New {constructor}(Argument());',allow_extensions=True);effects=[]
            session.interpreter.types[constructor.casefold()]=HostFunction(constructor,lambda *args:effects.append('factory'))
            session.interpreter.register_function('Argument',lambda:effects.append('argument'))
            with self.subTest(constructor=constructor),self.assertRaises(BoundaryViolation):session.open()
            self.assertEqual(effects,[])

    def test_foreign_attribute_factory_rejected(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        other=self.session('');session=self.session('A=New FormAttribute("X",New TypeDescription("String"));')
        session.interpreter.types['formattribute']=other.interpreter.types['formattribute']
        with self.assertRaises(BoundaryViolation):session.open()

    def test_client_attribute_creation_remains_denied(self):
        session=self.session('A=New FormAttribute("X",New TypeDescription("String"));',side='Client')
        with self.assertRaises(Exception):session.open()
        self.assertNotIn('x',session.form._attributes)

    def test_change_attributes_keeps_atomic_validation(self):
        session=self.session('A=New Array; A.Add(New FormAttribute("X",New TypeDescription("String"))); '
                             'A.Add(New FormAttribute("X",New TypeDescription("String"))); ChangeAttributes(A);')
        with self.assertRaises(Exception):session.open()
        self.assertEqual(session.form._attributes,{})
        self.assertEqual(session._allocated,0)

    def test_self_form_private_and_unknown_fields_denied(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.types.errors import BSLRuntimeError
        for body,error in (('X=ThisObject._session;',BoundaryViolation),('ThisObject._data=1;',BoundaryViolation),('ThisObject.Missing=1;',BSLRuntimeError)):
            session=self.session(body)
            with self.subTest(body=body),self.assertRaises(error):session.open()

    def test_foreign_self_form_receiver_denied(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        other=self.session('');session=self.session('X=Foreign(); X.Title="bad";',allow_extensions=True)
        session.interpreter.register_function('Foreign',lambda:other.form)
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertEqual(other.form.title,'')

    def test_original_managed_form_completes_without_vm_dispatch(self):
        import sys
        from yadinassi.forms.form_runtime import FormSession
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        with patch.object(sys,'path',[str(Path(__file__).resolve().parents[1]/'scripts')]+sys.path):
            from form_runtime_packet import source,parse_records,require_available
        session=FormSession(source(),bindings={'OnCreateAtServer':'FormCreate','OnOpen':'FormOpen','BeforeClose':'FormBeforeClose'})
        self.addCleanup(session.interpreter.close)
        snapshot=session.open()
        raw=dict(snapshot.attributes)['FLog'].encode('ascii')
        require_available(parse_records(raw))
        self.assertEqual(set(session.form._attributes),{'fname','fflag','famount','ftrace','flog'})
        self.assertEqual(session.form._data['fname'],'leave')
        self.assertEqual(session.form._data['famount'],43)
        self.assertIn('MF22=temp|MF23=removed|MF24=server-create|',session.form._data['flog'])
        self.assertIn('MF25=server-create:client-open|MF26=Ada|MF27=server-updated|',session.form._data['flog'])
        self.assertIn('MF31=direct-change:NameField|MF32=handler-change|MF33=direct-command:Apply|MF34=43|',session.form._data['flog'])
        self.assertTrue(session.form._data['flog'].endswith('MF40=direct-calls-complete|'))

    def test_live_constructor_replacement_denied_before_argument(self):
        from yadinassi.types.values import HostFunction
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        session=self.session('Change(); A=New TypeDescription(Argument());',allow_extensions=True);effects=[]
        def change():session.interpreter.types['typedescription']=HostFunction('TypeDescription',lambda *args:effects.append('factory'))
        session.interpreter.register_function('Change',change)
        session.interpreter.register_function('Argument',lambda:effects.append('argument'))
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertEqual(effects,[])

    def test_change_attributes_client_side_stays_denied(self):
        session=self.session('ChangeAttributes(New Array);',side='Client')
        with self.assertRaises(Exception):session.open()
        self.assertEqual(session.form._attributes,{})


class DirectFormReferenceTests(unittest.TestCase):
    def boundary(self):
        from yadinassi.forms.form_runtime import FormSession
        from yadinassi.execution.direct.python_direct_forms import FormBoundary
        session=FormSession('&AtServer\nProcedure Event(Cancel, StandardProcessing) '
                            'Items.Add("Field",Type("FormField")); Commands.Add("Apply"); EndProcedure',
                            bindings={'OnCreateAtServer':'Event'})
        self.addCleanup(session.interpreter.close)
        session.open();session._begin(session.revision)
        vm=session.interpreter;vm._context_stack.append('server')
        def release():
            vm._context_stack.pop();session._busy=False;session._gate.release()
        self.addCleanup(release)
        context=FormBoundary(session,vm.server_routines['event']);context.enter()
        self.addCleanup(context.leave)
        return session,context

    def test_readonly_control_and_command_slots_bind_but_reject_write(self):
        session,context=self.boundary()
        for collection,name in ((session.form.items,'Field'),(session.form.commands,'Apply')):
            ref=context.reference_member(collection,name)
            item=ref.get()
            self.assertIs(item,collection.get_member(name))
            with self.assertRaises(ValueError):ref.set(None)
            self.assertIs(collection.get_member(name),item)

    def test_live_writable_properties_and_self_form(self):
        session,context=self.boundary()
        field=session.form.items.get_member('Field')
        ref=context.reference_member(field,'Title');ref.set('first')
        field.set_member('Title','second')
        self.assertEqual(ref.get(),'second')
        own=context.reference_member(session.form,'Title');own.set('own')
        self.assertEqual(own.get(),'own')

    def test_foreign_private_and_missing_slots_rejected_at_bind(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        session,context=self.boundary();other,_=self.boundary()
        for receiver in (other.form,other.form.items,other.form.items.get_member('Field')):
            with self.subTest(receiver=type(receiver)),self.assertRaises(BoundaryViolation):
                context.reference_member(receiver,'Title')
        with self.assertRaises(BoundaryViolation):context.reference_member(session.form,'_session')
        with self.assertRaises(ValueError):context.reference_member(session.form.items,'Missing')

    def test_retired_control_and_collection_cannot_use_retained_reference(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        session,context=self.boundary();items=session.form.items
        field=items.get_member('Field');ref=context.reference_member(field,'Title')
        items.delete(field)
        for name,operation in (('get',ref.get),('set',lambda:ref.set('bad'))):
            with self.subTest(retired='control',operation=name):
                with self.assertRaisesRegex(ValueError,'^Форма: объект удален$'):operation()
        slot=context.reference_member(session.form.commands,'Apply')
        from yadinassi.forms.form_model import BSLFormCommands
        session.form.commands=BSLFormCommands(session.form)
        for name,operation in (('get',slot.get),('set',lambda:slot.set('bad'))):
            with self.subTest(retired='collection',operation=name):
                with self.assertRaises(BoundaryViolation):operation()

    def test_retained_reference_requires_active_open_family(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        session,context=self.boundary();ref=context.reference_member(session.form,'Title')
        session._busy=False
        with self.assertRaises(ValueError):ref.get()
        session._busy=True;session.interpreter.close()
        with self.assertRaises(BoundaryViolation):ref.get()
        with self.assertRaises(BoundaryViolation):ref.set('bad')

    def test_source_byref_writes_public_property_and_readonly_slot_stays_readonly(self):
        from yadinassi.forms.form_runtime import FormSession
        source=('&AtServer\nProcedure Event(Cancel, StandardProcessing) '
                'Items.Add("Field",Type("FormField")); Assign(ThisObject.Title); '
                'Assign(Items.Field.Title); Try Assign(Items.Field); Except Message("readonly"); EndTry; EndProcedure\n'
                '&AtServer\nProcedure Assign(X) X="updated"; EndProcedure')
        session=FormSession(source,bindings={'OnCreateAtServer':'Event'})
        self.addCleanup(session.interpreter.close)
        session.open()
        self.assertEqual(session.form.title,'updated')
        self.assertEqual(session.form.items._values['field'].title,'updated')
        self.assertIn('readonly',str(session.messages))

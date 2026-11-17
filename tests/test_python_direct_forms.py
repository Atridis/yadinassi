"""Actual demo import/event slice; full application and DB execution remain unsupported."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.configuration_app import load_application

ROOT=Path(__file__).resolve().parents[1]/'examples/demo'

class DirectFormTests(unittest.TestCase):
    def test_real_demo_import_database_reopen_and_created_without_vm_dispatch(self):
        files={p.relative_to(ROOT).as_posix():p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')), patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
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

    def test_event_transaction_service_rejected_before_effect(self):
        from yadinassi.form_runtime import FormSession
        source='&AtServer\nProcedure Created(Cancel, StandardProcessing) BeginTransaction(); EndProcedure'
        session=FormSession(source,bindings={'OnCreateAtServer':'Created'})
        with patch('yadinassi.database_transactions.begin',side_effect=AssertionError('transaction effect')) as begin:
            with self.assertRaises(Exception):session.open()
            begin.assert_not_called()
        self.assertFalse(session._busy)
        self.assertEqual(session.interpreter.execution_context,'client')

    def test_loop_budget_and_closed_interpreter_reject(self):
        from yadinassi.form_runtime import FormSession, FormLimitError
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        source='&AtServer\nProcedure Created(Cancel, StandardProcessing) While True Do EndDo; EndProcedure'
        session=FormSession(source,bindings={'OnCreateAtServer':'Created'})
        with patch('yadinassi.form_runtime.MAX_STEPS',5):
            with self.assertRaises(FormLimitError):session.open()
        self.assertFalse(session._busy)
        session=FormSession('&AtServer\nProcedure Created(Cancel, StandardProcessing) EndProcedure',bindings={'OnCreateAtServer':'Created'})
        session.interpreter.close()
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertFalse(session._busy)

class DirectDeclarationTests(unittest.TestCase):
    def session(self,body,side='Server'):
        from yadinassi.form_runtime import FormSession
        event='OnCreateAtServer' if side=='Server' else 'OnOpen'
        parameters='Cancel, StandardProcessing' if side=='Server' else 'Cancel'
        session=FormSession(f'&At{side}\nProcedure Event({parameters}) {body} EndProcedure',bindings={event:'Event'})
        self.addCleanup(session.interpreter.close)
        return session

    def test_dynamic_scalar_declaration_read_write_remove_without_vm(self):
        body=('A=New Array; A.Add(New FormAttribute("Text",New TypeDescription("String"))); '
              'A.Add(New РеквизитФормы("Total",New ОписаниеТипов("Number"))); ChangeAttributes(A); '
              'ThisObject.Text="hello"; ЭтотОбъект.Total=42; Message(ThisObject.Text); Message(ЭтотОбъект.Total); '
              'D=New Array; D.Add("Text"); ИзменитьРеквизиты(New Array,D);')
        session=self.session(body)
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            session.open()
        self.assertNotIn('text',session.form._attributes)
        self.assertEqual(session.form._data['total'],42)
        self.assertFalse(session._busy)

    def test_constructor_override_rejected_before_argument_effect(self):
        from yadinassi.values import HostFunction
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        for constructor in ('TypeDescription','ОписаниеТипов','FormAttribute','РеквизитФормы'):
            session=self.session(f'A=New {constructor}(Argument());');effects=[]
            session.interpreter.types[constructor.casefold()]=HostFunction(constructor,lambda *args:effects.append('factory'))
            session.interpreter.register_function('Argument',lambda:effects.append('argument'))
            with self.subTest(constructor=constructor),self.assertRaises(BoundaryViolation):session.open()
            self.assertEqual(effects,[])

    def test_foreign_attribute_factory_rejected(self):
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
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
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.errors import BSLRuntimeError
        for body,error in (('X=ThisObject._session;',BoundaryViolation),('ThisObject._data=1;',BoundaryViolation),('ThisObject.Missing=1;',BSLRuntimeError)):
            session=self.session(body)
            with self.subTest(body=body),self.assertRaises(error):session.open()

    def test_foreign_self_form_receiver_denied(self):
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        other=self.session('');session=self.session('X=Foreign(); X.Title="bad";')
        session.interpreter.register_function('Foreign',lambda:other.form)
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertEqual(other.form.title,'')

    def test_original_managed_form_reaches_cross_side_call(self):
        import sys
        from yadinassi.form_runtime import FormSession
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        with patch.object(sys,'path',[str(Path(__file__).resolve().parents[1]/'scripts')]+sys.path):
            from form_runtime_packet import source
        session=FormSession(source(),bindings={'OnCreateAtServer':'FormCreate','OnOpen':'FormOpen','BeforeClose':'FormBeforeClose'})
        self.addCleanup(session.interpreter.close)
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            with self.assertRaisesRegex(BoundaryViolation,'unregistered host service: serverread'):session.open()
        self.assertEqual(set(session.form._attributes),{'fname','fflag','famount','ftrace','flog'})
        self.assertEqual(session.form._data['fname'],'Ada')
        self.assertEqual(session.form._data['famount'],42)
        self.assertIn('MF22=temp|MF23=removed|MF24=server-create|',session.form._data['flog'])
        self.assertIn('MF25=server-create:client-open|',session.form._data['flog'])

    def test_live_constructor_replacement_denied_before_argument(self):
        from yadinassi.values import HostFunction
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        session=self.session('Change(); A=New TypeDescription(Argument());');effects=[]
        def change():session.interpreter.types['typedescription']=HostFunction('TypeDescription',lambda *args:effects.append('factory'))
        session.interpreter.register_function('Change',change)
        session.interpreter.register_function('Argument',lambda:effects.append('argument'))
        with self.assertRaises(BoundaryViolation):session.open()
        self.assertEqual(effects,[])

    def test_change_attributes_client_side_stays_denied(self):
        session=self.session('ChangeAttributes(New Array);',side='Client')
        with self.assertRaises(Exception):session.open()
        self.assertEqual(session.form._attributes,{})

"""Finite standalone message ownership and current dispatch authority."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import make_boundary
from yadinassi.application.user_messages import BSLUserMessage

class DirectUserMessageSecurity(unittest.TestCase):
    def vm(self,**kwargs):
        vm=Interpreter(**kwargs);self.addCleanup(vm.close);return vm

    def test_prepared_dynamic_and_captured_delivery(self):
        seen=[];vm=self.vm(user_message_sink=seen.append)
        plan=vm.prepare('M=New("UserMessage");M.Text="once";Saved=M.Message;Saved();')
        with patch('yadinassi.execution.direct.python_direct._compile',side_effect=AssertionError('recompile')):
            vm.execute_prepared(plan);vm.execute_prepared(plan)
        self.assertEqual([r.text for r in seen],['once','once'])

    def test_foreign_message_cannot_deliver_or_change(self):
        seen=[];a=self.vm(user_message_sink=seen.append);b=self.vm()
        a.execute('M=New UserMessage;M.Text="owned";Saved=M.Message;');b.variables['m']=a.variables['m'];b.variables['saved']=a.variables['saved']
        for source in ('M.Message();','M.Text="foreign";','X=M.Text;','Saved();'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):b.execute(source)
        self.assertEqual(a.variables['m']._text,'owned');self.assertEqual(seen,[])

    def test_registry_mutation_during_argument_denies_before_factory(self):
        vm=self.vm();seen=[]
        def change():
            vm.register_type('UserMessage',lambda:seen.append('foreign'));return None
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('M=New UserMessage(Change());')
        self.assertEqual(seen,[]);self.assertNotIn('m',vm.variables)

    def test_close_during_rhs_prevents_assignment(self):
        vm=self.vm();vm.execute('M=New UserMessage;M.Text="kept";');message=vm.variables['m']
        vm.register_function('Stop',lambda:vm.close() or 'changed')
        with self.assertRaises(BoundaryViolation):vm.execute('M.Text=Stop();')
        self.assertEqual(message._text,'kept')

    def test_captured_metadata_and_policy_denial(self):
        seen=[];vm=self.vm(user_message_sink=seen.append);vm.execute('M=New UserMessage;Saved=M.Message;')
        saved=vm.variables['saved'];context=make_boundary(vm);context.start()
        bound=context.resolve_callable(saved)
        context.policy=lambda op,name:False
        with self.assertRaises(BoundaryViolation):bound()
        context.policy=None;saved.function=lambda:seen.append('bad')
        with self.assertRaises(BoundaryViolation):bound()
        self.assertEqual(seen,[])

    def test_receiver_hooks_do_not_gain_dispatch(self):
        seen=[];vm=self.vm(user_message_sink=seen.append);vm.execute('M=New UserMessage;')
        with patch.object(BSLUserMessage,'message',lambda self:seen.append('bad')):
            with self.assertRaises(BoundaryViolation):vm.execute('M.Message();')
        with patch.object(BSLUserMessage,'__init__',lambda *args:seen.append('bad')):
            with self.assertRaises(BoundaryViolation):vm.execute('New UserMessage;')
        vm.user_messages.publish=lambda record:seen.append('bad')
        with self.assertRaises(BoundaryViolation):vm.execute('M.Message();')
        self.assertEqual(seen,[])

    def test_procedure_value_and_unknown_member_have_no_delivery(self):
        seen=[];vm=self.vm(user_message_sink=seen.append);vm.execute('M=New UserMessage;')
        for source in ('R=M.Message();','M._context;','M.Unknown=1;'):
            with self.subTest(source=source),self.assertRaises(BSLError):vm.execute(source)
        self.assertEqual(seen,[])

    def test_sink_close_stops_following_effect_without_retry(self):
        seen=[];vm=self.vm()
        def deliver(record):seen.append(record.text);vm.close()
        vm.user_messages.set_sink(deliver)
        with self.assertRaises(BoundaryViolation):
            vm.execute('M=New UserMessage;M.Text="sent";M.Message();After=True;')
        self.assertEqual(seen,['sent']);self.assertNotIn('after',vm.variables)

    def test_form_procedure_value_is_not_delivered(self):
        from yadinassi.forms.form_runtime import FormSession
        source='&AtClient\nProcedure Open(Cancel) M=New UserMessage;M.Text="not sent";X=M.Message();EndProcedure'
        session=FormSession(source,bindings={'OnOpen':'Open'})
        with self.assertRaises(BSLError):session.open()
        self.assertEqual(session.messages,())

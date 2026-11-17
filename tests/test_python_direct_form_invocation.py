"""Real Receipt client command uses the existing bound server transport."""
from unittest import TestCase
from unittest.mock import patch
from decimal import Decimal
import test_main_demo_host as fixture
from yadinassi.ui.configuration_app import PROTOCOL
from yadinassi.python_direct_forms import FormBoundary
from yadinassi.experimental_naked_boundaries import BoundaryViolation

class FormInvocationTests(TestCase):
    def setUp(self):
        self.f=fixture.MainDemoHostTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.assertIsNone(self.f.rpc('select',epoch=self.f.host.epoch,surface='documents')['error'])
        self.app=self.f.host.owner
        self.rpc('hello',protocol=PROTOCOL)
        self.sid=self.rpc('open',entry=self.app.names['document.receipt.form.card'],request='new')['session']
        self.session=self.app.sessions[self.sid][0].session
    def rpc(self,method,**params):
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
        self.assertIsNone(result['error']);return result
    def test_actual_receipt_add_line_uses_direct_endpoint(self):
        vm=self.session.interpreter
        with patch.object(type(vm),'call_routine',side_effect=AssertionError('legacy VM')):
            result=self.rpc('form',session=self.sid,request={'jsonrpc':'2.0','id':1,'method':'form.event',
                'params':{'event':'command','control':'AddLineButton','revision':self.session.revision}})
        self.assertIsNone(result['form']['result']['error'])
        rows=next(iter(self.session.form._tables.values()))
        self.assertEqual(len(rows._rows),1)
        self.assertEqual(rows._rows[0]._data['quantity'],Decimal(1))
        self.assertEqual(rows._rows[0]._data['amount'],Decimal(0))
        self.assertTrue(self.session.form._data['dirty'])
    def boundary(self):
        vm=self.session.interpreter
        self.session._begin(self.session.revision)
        def done():
            self.session._busy=False;self.session._gate.release()
        self.addCleanup(done)
        context=FormBoundary(self.session,vm.routines['addlinecommand']);context.enter()
        self.addCleanup(context.leave)
        return context
    def test_retained_binding_replacement_rejected_before_transport(self):
        context=self.boundary();bound=context.resolve_service('addatserver')
        vm=self.session.interpreter;old=vm._invocation_bindings['addatserver']
        with patch.dict(vm._invocation_bindings,{'addatserver':(old[0],lambda values:self.fail('foreign transport'))}):
            with self.assertRaises(BoundaryViolation):bound()
    def test_wrong_result_kind_arity_and_side_do_not_call_transport(self):
        context=self.boundary()
        with self.assertRaises(TypeError):context.resolve_service('addatserver',require_value=True)
        bound=context.resolve_service('addatserver')
        with self.assertRaises(TypeError):bound(Decimal(1))
        vm=self.session.interpreter
        vm._context_stack.append('server')
        try:
            with self.assertRaises(BoundaryViolation):bound()
        finally:vm._context_stack.pop()
        self.assertEqual(len(next(iter(self.session.form._tables.values()))._rows),0)
    def test_retained_call_rejects_closed_owner_and_changed_signature(self):
        context=self.boundary();bound=context.resolve_service('addatserver')
        vm=self.session.interpreter;routine=vm.server_routines['addatserver']
        with patch.object(routine,'is_function',True):
            with self.assertRaises(BoundaryViolation):bound()
        vm.close()
        with self.assertRaises(BoundaryViolation):bound()


class StandaloneServerCallTests(TestCase):
    def session(self,body='Set(); Message(Read());',server=None,**kwargs):
        from yadinassi.form_runtime import FormSession
        if server is None:
            server=('&AtServer\nProcedure Set() ThisObject.Title="server"; EndProcedure\n'
                    '&AtServer\nFunction Read() Return ThisObject.Title; EndFunction')
        session=FormSession('&AtClient\nProcedure Event(Cancel) '+body+' EndProcedure\n'+server,
                            bindings={'OnOpen':'Event'},**kwargs)
        self.addCleanup(session.interpreter.close)
        return session

    def test_function_and_procedure_use_direct_server_side(self):
        from yadinassi import Interpreter
        session=self.session(server='&AtServer\nProcedure Set() Side(); ThisObject.Title="server"; EndProcedure\n&AtServer\nFunction Read() Side(); Return ThisObject.Title; EndFunction');sides=[]
        session.interpreter.register_function('Side',lambda:sides.append(session.interpreter.execution_context))
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            session.open()
        self.assertEqual(session.form.title,'server')
        self.assertEqual(sides,['server','server'])
        self.assertEqual(session.interpreter.execution_context,'client')
        self.assertTrue(session.interpreter._transaction_activation_allowed)

    def test_server_failure_restores_scope_and_client_continues(self):
        session=self.session('Try X=Read(); Except ThisObject.Title="caught"; EndTry;',
                             '&AtServer\nFunction Read() Raise "boom"; EndFunction')
        session.open()
        self.assertEqual(session.form.title,'caught')
        self.assertEqual(session.interpreter.execution_context,'client')
        self.assertTrue(session.interpreter._transaction_activation_allowed)
        self.assertFalse(session._busy)

    def test_cross_side_capability_result_rejected(self):
        session=self.session('X=Read(); ThisObject.Title="escaped";',
                             '&AtServer\nFunction Read() Return ThisObject; EndFunction')
        with self.assertRaisesRegex(Exception,'Межконтекстная передача'):session.open()
        self.assertEqual(session.form.title,'')

    def test_parameterized_routine_and_custom_factory_not_auto_enrolled(self):
        from yadinassi.form_runtime import _FormInterpreter
        session=self.session('X=Read(1);','&AtServer\nFunction Read(Val X) Return X; EndFunction')
        with self.assertRaisesRegex(BoundaryViolation,'unregistered host service'):session.open()
        session=self.session(interpreter_factory=_FormInterpreter)
        with self.assertRaisesRegex(BoundaryViolation,'unregistered host service'):session.open()

    def boundary(self,session):
        session._begin(session.revision)
        def release():session._busy=False;session._gate.release()
        self.addCleanup(release)
        context=FormBoundary(session,session.interpreter.routines['event']);context.enter()
        self.addCleanup(context.leave)
        return context

    def test_bound_call_checks_signature_registry_side_and_lifetime(self):
        session=self.session();vm=session.interpreter;context=self.boundary(session)
        bound=context.resolve_service('read',require_value=True)
        with patch.object(vm.server_routines['read'],'is_function',False):
            with self.assertRaises(BoundaryViolation):bound()
        with patch.dict(vm._invocation_bindings,{'read':(vm.server_routines['read'],lambda values:self.fail('replaced'))}):
            with self.assertRaises(BoundaryViolation):bound()
        vm._context_stack.append('server')
        try:
            with self.assertRaises(BoundaryViolation):bound()
        finally:vm._context_stack.pop()
        with self.assertRaises(TypeError):bound(1)
        with self.assertRaises(TypeError):context.resolve_service('set',require_value=True)
        vm.close()
        with self.assertRaises(BoundaryViolation):bound()

    def test_local_binding_denies_later_enrollment(self):
        session=self.session();context=self.boundary(session);bound=context.resolve_service('read')
        with patch.object(session,'_owned_form_enrollment',object()):
            with self.assertRaisesRegex(BoundaryViolation,'standalone ownership'):bound()

    def test_server_transaction_activation_remains_denied(self):
        session=self.session('Set();','&AtServer\nProcedure Set() BeginTransaction(); EndProcedure')
        with patch('yadinassi.database_transactions.begin',side_effect=AssertionError('transaction effect')) as begin:
            with self.assertRaises(Exception):session.open()
            begin.assert_not_called()
        self.assertTrue(session.interpreter._transaction_activation_allowed)

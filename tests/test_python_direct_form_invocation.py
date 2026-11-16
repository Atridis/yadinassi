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

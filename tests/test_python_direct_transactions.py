"""Standalone direct transactions own one execution, never an ambient grant."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi import database_transactions as tx
import test_bsl_transactions as fixtures
from test_catalog_commit_cleanup_recovery import FaultConnection

class DirectTransactionTests(unittest.TestCase):
    def setUp(self):
        fixtures.BSLTransactionsTests.setUp(self);self.addCleanup(self.vm.close)
    def assert_clean(self):
        self.assertIsNone(tx._execution.get());self.assertIsNone(tx._execution_backend.get())
        self.assertIsNone(getattr(self.backend,'_bsl_transaction',None));self.assertIsNone(self.backend._active)
    def test_source_ast_prepared_commit_and_rollback(self):
        from yadinassi.syntax.parser import parse
        for route in ('source','ast','prepared'):
            source='C=Catalogs.Products.CreateItem();C.Code="'+route+'";BeginTransaction();C.Write();CommitTransaction();BeginTransaction();RollbackTransaction();'
            if route=='source':self.vm.execute(source)
            elif route=='ast':self.vm.execute_program(parse(source))
            else:self.vm.execute_prepared(self.vm.prepare(source))
            self.assertFalse(self.vm.variables['c'].is_new());self.assert_clean()
            self.assertTrue(self.vm._transaction_activation_allowed)
    def test_managed_compilation_profile_preserves_owned_transaction_lifecycle(self):
        vm=Interpreter(database_context=self.context,compilation_profile='managed-thick-file');self.addCleanup(vm.close)
        vm.execute('C=Catalogs.Products.CreateItem();C.Code="managed";BeginTransaction();C.Write();CommitTransaction();')
        self.assertFalse(vm.variables['c'].is_new());self.assert_clean()
        vm.execute('C=Catalogs.Products.CreateItem();C.Code="rollback";BeginTransaction();C.Write();RollbackTransaction();')
        self.assertTrue(vm.variables['c'].is_new());self.assert_clean()
        self.assertTrue(vm.execute('Catalogs.Products.FindByCode("rollback").IsEmpty()'))
    def test_unclosed_and_baseexception_rollback(self):
        for statement in ('','Stop();'):
            class Stop(BaseException):pass
            def stop():raise Stop()
            self.vm.register_function('Stop',stop)
            with self.assertRaises((BackendError,BSLRuntimeError,Stop)):
                self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();'+statement)
            self.assert_clean();self.assertTrue(self.vm.variables['c'].is_new())
            self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))
    def test_pending_and_active_task_rejected_before_body_effects(self):
        events=[];self.vm.register_function('Effect',lambda:events.append(1))
        promise=self.vm._scheduler.new_pending()
        try:
            with self.assertRaises((ValueError,BoundaryViolation)):self.vm.execute('Effect();BeginTransaction();')
        finally:self.vm._scheduler._pending.clear()
        self.vm._scheduler._active_task=object()
        try:
            with self.assertRaises((ValueError,BoundaryViolation)):self.vm.execute('Effect();BeginTransaction();')
        finally:self.vm._scheduler._active_task=None
        self.assertEqual(events,[]);self.assert_clean()
    def test_pending_added_by_callback_aborts_and_rolls_back(self):
        self.vm.register_function('Pending',self.vm._scheduler.new_pending)
        try:
            with self.assertRaises(BoundaryViolation):self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();Pending();CommitTransaction();')
        finally:self.vm._scheduler._pending.clear()
        self.assert_clean();self.assertTrue(self.vm.variables['c'].is_new())
    def test_denied_caller_and_ambient_admission_stay_denied(self):
        for mode in ('vm','context'):
            self.vm._transaction_activation_allowed=mode!='vm'
            with tx.admission(mode!='context'):
                with self.assertRaises(BSLRuntimeError):self.vm.execute('BeginTransaction();')
            self.assertEqual(self.vm._transaction_activation_allowed,mode!='vm');self.assert_clean()
    def test_foreign_root_token_is_not_adopted_or_cleaned(self):
        with tx.execution(self.backend):
            tx.begin(self.backend);owner=tx.current(self.backend)
            with self.assertRaises(BoundaryViolation):self.vm.execute('RollbackTransaction();')
            self.assertIs(tx.current(self.backend),owner);tx.rollback(self.backend)
        self.assert_clean()
    def test_callback_corrupts_token_or_backend_without_leaking_journal(self):
        for variable in (tx._execution,tx._execution_backend):
            self.vm.register_function('Corrupt',lambda:variable.set(object()))
            with self.assertRaises(BoundaryViolation):self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();Corrupt();CommitTransaction();')
            self.assert_clean();self.assertTrue(self.vm.variables['c'].is_new())
    def test_callback_reentry_cannot_commit_outer_transaction(self):
        self.vm.register_function('Reenter',lambda:self.vm.execute('CommitTransaction();'))
        with self.assertRaises(BoundaryViolation):self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();Reenter();')
        self.assert_clean();self.assertTrue(self.vm.variables['c'].is_new())
    def test_uncertain_commit_resolved_without_replay(self):
        for fault in ('before','after'):
            def inject():
                unit=tx.current(self.backend).unit
                unit._view._connection=FaultConnection(unit._view._connection,commit_fault=fault)
            self.vm.register_function('Inject',inject)
            source='C=Catalogs.Products.CreateItem();C.Code="'+fault+'";BeginTransaction();C.Write();Inject();CommitTransaction();'
            with self.assertRaises((BackendError,BSLRuntimeError)):self.vm.execute(source)
            self.assert_clean();self.assertEqual(self.vm.variables['c'].is_new(),fault=='before')
    def test_import_scalar_call_shares_owner_but_not_foreign_object_authority(self):
        module=self.path.parent/'Helper.bsl';module.write_text('Function Active() Export Return TransactionActive();EndFunction',encoding='utf-8')
        self.vm.execute('// #Import Helper.bsl\nBeginTransaction();A=Helper.Active();RollbackTransaction();',str(self.path.parent/'main.bsl'))
        self.assertIs(self.vm.variables['a'],True);self.assert_clean()
    def test_source_server_transaction_guard_not_widened(self):
        self.vm.execute('&AtServerNoContext\nProcedure S() BeginTransaction();EndProcedure\nTry S();Except E=ErrorDescription();EndTry;')
        self.assertIn('transaction',self.vm.variables['e'].lower());self.assert_clean()

    def test_status_outside_transaction_has_no_writer(self):
        self.assertIs(self.vm.execute('TransactionActive()'),False);self.assert_clean()

    def test_corruption_before_begin_is_revoked_without_opening_journal(self):
        for variable in (tx._execution,tx._execution_backend):
            self.vm.register_function('Corrupt',lambda:variable.set(object()))
            with self.assertRaises(BoundaryViolation):self.vm.execute('Corrupt();BeginTransaction();')
            self.assert_clean()

    def test_token_never_reused_and_closed_owner_is_rejected(self):
        captured=[]
        self.vm.register_function('Capture',lambda:captured.append(tx._execution.get()))
        self.vm.execute('BeginTransaction();Capture();RollbackTransaction();BeginTransaction();Capture();CommitTransaction();')
        self.assertEqual(len(captured),2);self.assertIsNot(captured[0],captured[1]);self.assert_clean()
        from yadinassi import python_direct
        contexts=[];original=python_direct.make_boundary
        def remember(*args,**kwargs):
            context=original(*args,**kwargs);contexts.append(context);return context
        with patch.object(python_direct,'make_boundary',remember):self.vm.execute('BeginTransaction();RollbackTransaction();')
        owned=[context for context in contexts if context._direct_transaction_owner is not None]
        self.assertTrue(owned)
        with self.assertRaises(BoundaryViolation):owned[-1]._check()

    def test_revoked_interpreter_rolls_back_own_staged_write(self):
        self.vm.register_function('CloseOwner',self.vm.close)
        with self.assertRaises(BoundaryViolation):self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();CloseOwner();')
        self.assert_clean();self.assertTrue(self.vm.variables['c'].is_new())

    def test_pending_or_service_replacement_at_policy_boundary_opens_no_writer(self):
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        original=BoundaryContext._before
        for action in ('pending','replace'):
            function=self.vm.functions['begintransaction'];implementation=function.function
            def mutate(context,operation,name):
                original(context,operation,name)
                if name=='begintransaction':
                    if action=='pending':self.vm._scheduler.new_pending()
                    else:function.function=lambda:None
            try:
                with patch.object(BoundaryContext,'_before',mutate):
                    with self.assertRaises((BSLRuntimeError,BoundaryViolation)):self.vm.execute('BeginTransaction();')
            finally:self.vm._scheduler._pending.clear();function.function=implementation
            self.assert_clean()

    def test_server_crossing_inside_transaction_has_no_effect_and_rolls_back(self):
        events=[];self.vm.register_function('Effect',lambda:events.append(1))
        with self.assertRaises((BSLRuntimeError,BoundaryViolation)):
            self.vm.execute('&AtServerNoContext\nProcedure S() Effect();EndProcedure\nBeginTransaction();S();CommitTransaction();')
        self.assertEqual(events,[]);self.assert_clean()

    def test_uncertain_journal_can_be_resolved_in_later_root_without_replay(self):
        def inject():
            unit=tx.current(self.backend).unit
            unit._view._connection=FaultConnection(unit._view._connection,commit_fault='after')
        self.vm.register_function('Inject',inject)
        with patch.object(self.backend,'resolve_unit_of_work',side_effect=BackendError('uncertain_commit')):
            with self.assertRaises((BackendError,BSLRuntimeError)):
                self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();Inject();CommitTransaction();')
        self.assertIsNotNone(self.backend._bsl_transaction)
        self.assertTrue(self.vm.variables['c'].is_new());self.assertIsNone(tx._execution.get())
        self.vm.execute('CommitTransaction();')
        self.assertFalse(self.vm.variables['c'].is_new());self.assert_clean()

    def test_callback_cannot_widen_inherited_denial(self):
        self.vm.register_function('Widen',lambda:tx._admission_allowed.set(True))
        with tx.admission(False):
            with self.assertRaises(BSLRuntimeError):self.vm.execute('Widen();BeginTransaction();')
        self.assert_clean()

    def test_eval_and_execute_share_owner_without_leaking_or_false_procedure_value(self):
        self.vm.execute('BeginTransaction();A=Eval("TransactionActive()");Execute("CommitTransaction();");B=TransactionActive();')
        self.assertIs(self.vm.variables['a'],True);self.assertIs(self.vm.variables['b'],False);self.assert_clean()
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();Execute("RollbackTransaction();");')
        self.assertTrue(self.vm.variables['c'].is_new());self.assert_clean()
        self.vm.execute('BeginTransaction();Try X=Eval("CommitTransaction()");Except Caught=True;EndTry;StillActive=TransactionActive();RollbackTransaction();')
        self.assertTrue(self.vm.variables['caught']);self.assertTrue(self.vm.variables['stillactive']);self.assert_clean()
        with self.assertRaises(BSLRuntimeError):self.vm.execute('BeginTransaction();Execute("Raise 123;");')
        self.assert_clean()

    def test_imported_controls_share_dynamic_owner_but_initializers_are_denied(self):
        module=self.path.parent/'Controls.bsl'
        module.write_text('Procedure Begin() Export BeginTransaction();EndProcedure\nProcedure Commit() Export CommitTransaction();EndProcedure\nProcedure Rollback() Export RollbackTransaction();EndProcedure',encoding='utf-8')
        self.vm.execute('// #Import Controls.bsl\nControls.Begin();A=TransactionActive();Controls.Commit();Controls.Begin();Controls.Rollback();',str(self.path.parent/'main.bsl'))
        self.assertTrue(self.vm.variables['a']);self.assert_clean()
        bad=self.path.parent/'Bad.bsl';bad.write_text('BeginTransaction();',encoding='utf-8')
        with self.assertRaises(BSLRuntimeError):self.vm.execute('// #Import Bad.bsl\nMarker=1;',str(self.path.parent/'bad-main.bsl'))
        self.assert_clean();self.assertNotIn('marker',self.vm.variables)

    def test_other_interpreter_same_backend_cannot_commit_owned_transaction(self):
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        self.vm.register_function('Cross',lambda:other.execute('CommitTransaction();'))
        with self.assertRaises(BoundaryViolation):self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();Cross();')
        self.assert_clean();self.assertTrue(self.vm.variables['c'].is_new())

    def test_captured_control_keeps_own_owner_and_rejects_foreign_canonical_owner(self):
        self.vm.variables['control']=self.vm.functions['committransaction']
        self.vm.execute('BeginTransaction();control();');self.assert_clean()
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        self.vm.variables['control']=other.functions['committransaction']
        with self.assertRaises(BoundaryViolation):self.vm.execute('BeginTransaction();control();')
        self.assert_clean()
        self.vm.variables['control']=self.vm.functions['committransaction']
        self.vm.execute('BeginTransaction();Try X=Eval("control()");Except Caught=True;EndTry;Active=TransactionActive();RollbackTransaction();')
        self.assertTrue(self.vm.variables['caught']);self.assertTrue(self.vm.variables['active']);self.assert_clean()

    def test_foreign_canonical_begin_service_cannot_acquire_writer(self):
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        self.vm.functions['foreignbegin']=other.functions['begintransaction']
        with patch.object(self.backend,'begin_unit_of_work',wraps=self.backend.begin_unit_of_work) as begin:
            with self.assertRaises(BoundaryViolation):self.vm.execute('ForeignBegin();')
            begin.assert_not_called()
        self.assert_clean()

    def test_other_backend_ambient_transaction_is_not_adopted_or_rolled_back(self):
        foreign=fixtures.BSLTransactionsTests();foreign.setUp();self.addCleanup(foreign.doCleanups)
        with tx.execution(foreign.backend):
            tx.begin(foreign.backend);owner=tx.current(foreign.backend)
            with self.assertRaises(BoundaryViolation):self.vm.execute('BeginTransaction();')
            self.assertIs(tx.current(foreign.backend),owner);self.assertEqual(owner.unit.state,'open')
            tx.rollback(foreign.backend)
        self.assert_clean()

    def test_owner_cannot_be_used_from_another_host_thread_before_begin(self):
        from threading import Thread
        from yadinassi import python_direct
        contexts=[];original=python_direct.make_boundary;errors=[]
        def remember(*args,**kwargs):
            context=original(*args,**kwargs);contexts.append(context);return context
        def callback():
            context=next(c for c in reversed(contexts) if c._direct_transaction_owner is not None)
            def foreign():
                try:context.resolve_service('BeginTransaction')()
                except BaseException as error:errors.append(error)
            worker=Thread(target=foreign);worker.start();worker.join()
        self.vm.register_function('ThreadCall',callback)
        with patch.object(python_direct,'make_boundary',remember):self.vm.execute('ThreadCall();')
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],BoundaryViolation);self.assert_clean()

    def test_execute_can_begin_write_and_commit_but_inherited_denial_has_no_effect(self):
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="fragment";Execute("BeginTransaction();C.Write();CommitTransaction();");')
        self.assertFalse(self.vm.variables['c'].is_new());self.assert_clean()
        with tx.admission(False),patch('yadinassi.database_transactions.begin',side_effect=AssertionError('effect')) as begin:
            with self.assertRaises(BSLRuntimeError):self.vm.execute('Execute("BeginTransaction();");')
            begin.assert_not_called()
        self.assert_clean()

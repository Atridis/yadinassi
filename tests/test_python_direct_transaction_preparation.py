"""Selected BeforeWrite runs once inside its owned root journal."""
import unittest
from unittest.mock import patch
from contextvars import copy_context
from contextlib import contextmanager
from yadinassi.db import database_transactions as tx
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalog_object_preparation import CatalogWriteRefused
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
import yadinassi.db.catalog.catalog_object_preparation as prep
import test_python_direct_catalog_preparation as fixture
from test_catalog_commit_cleanup_recovery import FaultConnection

def raw_clone(value):
    # Identity fault injection must not install copyreg.__slotnames__ caches on
    # otherwise sealed shared classes, especially under Python 3.10.
    result=object.__new__(type(value));result.__dict__=dict(vars(value));return result

class DirectTransactionPreparationTests(unittest.TestCase):
    def setUp(self):
        fixture.DirectCatalogPreparationTests.setUp(self, allow_extensions=True)
    def _callTestMethod(self,method):
        # Each host-coordinator probe runs inside a real admitted direct root.
        # Native root ingress/recovery cases explicitly drive their own roots.
        if method.__name__.startswith(('test_actual_','test_later_root_','test_ingress_')):
            return super()._callTestMethod(method)
        self.vm.register_function('CaseBody',method)
        self.vm.execute('CaseBody();')
    @contextmanager
    def activation(self):
        from yadinassi.execution.direct.python_direct_transactions import _ROOT_OWNER
        owner=_ROOT_OWNER.get();owner.check_origin();owner.start()
        try:yield
        except BaseException as error:
            owner.close(error);raise
        else:owner.close()
    def clean(self):
        self.assertIsNone(tx._execution.get());self.assertIsNone(tx._execution_backend.get())
        self.assertIsNone(self.db.backend._active);self.assertIsNone(tx._registered(self.db.backend))
    def test_original_handler_commit_and_rollback(self):
        for commit in (False,True):
            with self.activation():
                tx.begin(self.db.backend);self.card.write()
                owner=tx.current(self.db.backend)
                self.assertEqual(owner.leases,0);self.assertEqual(len(owner.participants),1)
                self.assertEqual(owner.unit.requests[0].draft.description,'Кабель')
                self.assertTrue(self.card.is_new())
                (tx.commit if commit else tx.rollback)(self.db.backend)
            self.clean();self.assertEqual(self.card.is_new(),not commit)
    def test_existing_autocommit_object_update_commit_and_rollback(self):
        self.card.write()
        ref=self.card.get_member('Ссылка')
        second=self.cats.get_member('Склады').create_item()
        second.set_member('Наименование','Дополнительный');second.write()
        for commit in (False,True):
            card=ref.get_object(ref);revision=card._revision
            card.set_member('Наименование','  Изменённый  ')
            card.get_member('Склады').add().set_member('Склад',second.get_member('Ссылка'))
            with self.activation():
                tx.begin(self.db.backend);card.write()
                owner=tx.current(self.db.backend)
                self.assertEqual(owner.unit.requests[0].draft.description,'Изменённый')
                self.assertEqual(card._revision,revision)
                self.assertIsNotNone(card._pending_write)
                (tx.commit if commit else tx.rollback)(self.db.backend)
            self.clean();self.assertIsNone(card._pending_write)
            saved=ref.get_object(ref)
            self.assertEqual(saved.get_member('Наименование'),'Изменённый' if commit else 'Кабель')
            self.assertEqual(saved.get_member('Склады').count(),2 if commit else 1)
            self.assertEqual(int(saved._revision.token),int(revision.token)+(1 if commit else 0))

    def test_read_sees_prior_stage_and_cancel_preserves_it_when_caught(self):
        with self.activation():
            tx.begin(self.db.backend)
            self.warehouse.set_member('ПометкаУдаления',True);self.warehouse.write()
            owner=tx.current(self.db.backend);requests=owner.unit.requests;participants=owner.participants
            with self.assertRaises(CatalogWriteRefused) as error:self.card.write()
            self.assertTrue(any('удаление' in m.text for m in error.exception.messages))
            self.assertIs(owner.unit.requests,requests);self.assertIs(owner.participants,participants)
            self.assertIsNone(self.card._pending_write);self.assertEqual(owner.leases,0)
            tx.commit(self.db.backend)
        self.clean();ref=self.warehouse.get_member('Ссылка')
        self.assertTrue(ref.get_object(ref).get_member('ПометкаУдаления'))
        self.assertTrue(self.card.is_new())
    def test_bad_source_and_interrupt_leave_no_stage(self):
        class Stop(BaseException):pass
        original=prep._prepare_catalog_object
        for mode in ('source','interrupt'):
            def change(*args,**kwargs):
                original(*args,**kwargs)
                if mode=='interrupt':raise Stop()
                tx.current(self.db.backend).unit._view._connection.execute("UPDATE configuration_file SET content=x'00' WHERE path LIKE '%ObjectModule.bsl'")
                return False,()
            with patch.object(prep,'_prepare_catalog_object',side_effect=change):
                with self.assertRaises((BackendError,Stop)):
                    with self.activation():
                        tx.begin(self.db.backend);self.card.write()
            self.clean();self.assertIsNone(self.card._pending_write);self.assertTrue(self.card.is_new())
    def test_copied_context_and_recursive_write_are_refused(self):
        original=prep._prepare_catalog_object
        for mode in ('copy','recursive','control'):
            def change(*args,**kwargs):
                if mode=='copy':return copy_context().run(original,*args,**kwargs)
                if mode=='recursive':self.card.write()
                else:tx.commit(self.db.backend)
                return original(*args,**kwargs)
            with patch.object(prep,'_prepare_catalog_object',side_effect=change):
                with self.assertRaises((BoundaryViolation,BackendError)):
                    with self.activation():
                        tx.begin(self.db.backend);self.card.write()
            self.clean();self.assertIsNone(self.card._pending_write)
    def test_preparation_lease_is_readonly_and_same_writer(self):
        original=prep._prepare_catalog_object
        def observe(*args,**kwargs):
            lease=kwargs['write_view'];owner=tx.current(self.db.backend)
            self.assertIs(lease._connection,owner.unit._view._connection)
            with self.assertRaises(BackendError):lease._require(True)
            self.assertEqual(owner.leases,1)
            return original(*args,**kwargs)
        with patch.object(prep,'_prepare_catalog_object',side_effect=observe):
            with self.activation():
                tx.begin(self.db.backend);self.card.write();tx.commit(self.db.backend)
        self.clean()
    def test_stage_failure_restores_journal_and_pending_flags(self):
        with self.activation():
            tx.begin(self.db.backend);owner=tx.current(self.db.backend)
            original=owner.unit.stage
            def stage(request):original(request);raise ValueError('stage fault')
            with patch.object(owner.unit,'stage',side_effect=stage):
                with self.assertRaisesRegex(ValueError,'stage fault'):self.card.write()
            self.assertEqual(owner.unit.requests,());self.assertEqual(owner.unit._results,())
            self.assertEqual(owner.participants,());self.assertIsNone(self.card._pending_write)
            self.assertEqual(owner.leases,0);tx.rollback(self.db.backend)
        self.clean()
    def test_uncertain_commit_does_not_rerun_handler(self):
        original=prep._prepare_catalog_object
        for fault in ('before','after'):
            with patch.object(prep,'_prepare_catalog_object',wraps=original) as handler:
                with self.assertRaises(BackendError):
                    with self.activation():
                        tx.begin(self.db.backend);self.card.write()
                        view=tx.current(self.db.backend).unit._view
                        view._connection=FaultConnection(view._connection,commit_fault=fault)
                        tx.commit(self.db.backend)
                self.assertEqual(handler.call_count,1)
            self.clean();self.assertEqual(self.card.is_new(),fault=='before')
    def test_rebinding_pinned_owner_parts_fails_before_stage(self):
        original=prep._prepare_catalog_object
        for mode in ('manager','unit','metadata','connection'):
            def change(*args,**kwargs):
                result=original(*args,**kwargs);scope=kwargs['_transaction_scope']
                if mode=='manager':target,name,new=self.card,'_manager',object()
                elif mode=='unit':target,name,new=scope.transaction,'unit',raw_clone(scope.unit)
                elif mode=='metadata':target,name,new=scope.catalogs,'_metadata',object()
                else:target,name,new=scope.view,'_connection',object()
                old=getattr(target,name);setattr(target,name,new)
                try:scope.check()
                finally:setattr(target,name,old)
                return result
            with self.subTest(mode=mode),patch.object(prep,'_prepare_catalog_object',side_effect=change):
                with self.assertRaises(BoundaryViolation):
                    with self.activation():
                        tx.begin(self.db.backend);self.card.write()
            self.clean();self.assertIsNone(self.card._pending_write);self.assertTrue(self.card.is_new())
    def test_foreign_thread_cannot_use_handler_scope(self):
        from threading import Thread
        original=prep._prepare_catalog_object
        def inspect(*args,**kwargs):
            scope=kwargs['_transaction_scope'];context=copy_context();errors=[]
            def foreign():
                try:context.run(scope.check)
                except BaseException as error:errors.append(error)
            worker=Thread(target=foreign);worker.start();worker.join()
            self.assertEqual(len(errors),1);self.assertIs(type(errors[0]),BoundaryViolation)
            return original(*args,**kwargs)
        with patch.object(prep,'_prepare_catalog_object',side_effect=inspect):
            with self.activation():
                tx.begin(self.db.backend);self.card.write();tx.commit(self.db.backend)
        self.clean()
    def test_reference_reads_remain_explicit_getobject_only(self):
        from yadinassi.execution.direct.python_direct_catalog_preparation import CatalogPreparationBoundary
        original=prep._prepare_catalog_object
        def inspect(*args,**kwargs):
            vm=prep._ObjectInterpreter(self.card,lambda record:None,kwargs['write_view'])
            vm._direct_transaction_preparation_scope=kwargs['_transaction_scope']
            context=CatalogPreparationBoundary(vm);context.enter()
            try:
                ref=context._adopt(self.warehouse.get_member('Ref'))
                with self.assertRaisesRegex(ValueError,'GetObject'):context.get_member(ref,'Description')
                for service in ('строка','формат'):
                    with self.assertRaisesRegex(ValueError,'presentation'):context.resolve_service(service)(ref)
                self.assertIs(context.resolve_service('значениезаполнено')(ref),True)
                obj=context.resolve_member(ref,'GetObject')()
                self.assertEqual(context.get_member(obj,'Description'),'Основной')
            finally:context.leave();vm.close()
            return original(*args,**kwargs)
        with patch.object(prep,'_prepare_catalog_object',side_effect=inspect):
            with self.activation():
                tx.begin(self.db.backend);self.card.write();tx.commit(self.db.backend)
        self.clean()
    def test_backend_change_cannot_enter_legacy_preparation(self):
        from yadinassi.execution.execution_policy import execution_backend_policy
        original=prep._prepare_catalog_object
        def change(*args,**kwargs):
            with execution_backend_policy('compiled-strict'):
                return original(*args,**kwargs)
        with patch.object(prep,'_prepare_catalog_object',side_effect=change):
            with patch.object(prep._ObjectInterpreter,'execute_program',side_effect=AssertionError('legacy execution')) as legacy:
                with self.assertRaisesRegex(ValueError,'unsupported execution backend'):
                    with self.activation():
                        tx.begin(self.db.backend);self.card.write()
                legacy.assert_not_called()
        self.clean();self.assertTrue(self.card.is_new())
    def test_public_policy_rebinding_cannot_substitute_ungranted_handler(self):
        replacement='Процедура ПередЗаписью(Отказ) Наименование="forged"; КонецПроцедуры'
        with patch.object(self.db.backend,'catalog_write_preparation',return_value=replacement):
            with patch.object(prep,'_prepare_catalog_object',side_effect=AssertionError('ungranted handler')) as handler:
                with self.assertRaises(BackendError):
                    with self.activation():
                        tx.begin(self.db.backend);self.card.write()
                handler.assert_not_called()
        self.clean();self.assertEqual(self.card.get_member('Description'),'  Кабель  ')
    def test_actual_direct_root_and_owner_corruption_cleanup(self):
        self.vm.variables['p']=self.card
        original=prep._prepare_catalog_object
        def corrupt(*args,**kwargs):
            result=original(*args,**kwargs);tx._execution.set(object());return result
        with patch.object(prep,'_prepare_catalog_object',side_effect=corrupt):
            with self.assertRaises(BoundaryViolation):self.vm.execute('BeginTransaction();P.Write();CommitTransaction();')
        self.clean();self.assertTrue(self.card.is_new())
        self.vm.execute('BeginTransaction();P.Write();CommitTransaction();R=P.Ref.GetObject().Description;')
        self.assertEqual(self.vm.variables['r'],'Кабель');self.clean()
    def test_later_root_resolution_retains_frozen_draft_without_handler(self):
        original=prep._prepare_catalog_object;backend=self.db.backend
        self.vm.variables['p']=self.card
        def inject():
            view=tx.current(backend).unit._view
            view._connection=FaultConnection(view._connection,commit_fault='after')
        self.vm.register_function('Inject',inject)
        with patch.object(prep,'_prepare_catalog_object',wraps=original) as handler:
            with patch.object(backend,'resolve_unit_of_work',side_effect=BackendError('uncertain_commit')):
                with self.assertRaises(Exception):
                    self.vm.execute('BeginTransaction();P.Write();Inject();CommitTransaction();')
            self.assertEqual(handler.call_count,1)
        owner=tx._registered(backend)
        self.assertEqual(owner.unit.requests[0].draft.description,'Кабель')
        with self.assertRaises(BackendError):self.card.set_member('Description','different')
        with patch.object(prep,'_prepare_catalog_object',side_effect=AssertionError('handler replay')):
            self.vm.execute('CommitTransaction();')
        self.clean();self.assertFalse(self.card.is_new())
        ref=self.card.get_member('Ref');self.assertEqual(ref.get_object(ref).get_member('Description'),'Кабель')
    def test_ingress_copied_context_and_foreign_thread_preserve_original_journal(self):
        from threading import Thread
        backend=self.db.backend
        def probe():
            owner=tx.current(backend);requests=owner.unit.requests;participants=owner.participants
            for threaded in (False,True):
                context=copy_context();errors=[]
                def foreign():
                    try:context.run(self.card.write)
                    except BaseException as error:errors.append(error)
                with patch.object(backend,'begin_read',side_effect=AssertionError('lease before origin')),patch.object(backend,'capabilities',side_effect=AssertionError('capability before origin')):
                    if threaded:
                        worker=Thread(target=foreign);worker.start();worker.join()
                    else:foreign()
                self.assertEqual(len(errors),1);self.assertIs(type(errors[0]),BoundaryViolation)
                self.assertIs(owner.unit.requests,requests);self.assertIs(owner.participants,participants)
                self.assertEqual(owner.leases,0)
        self.vm.register_function('Probe',probe)
        with patch.object(prep,'_prepare_catalog_object',side_effect=AssertionError('handler before origin')):
            self.vm.execute('BeginTransaction();Probe();RollbackTransaction();')
        self.clean();self.assertTrue(self.card.is_new())
    def test_ingress_copied_context_cannot_mint_begin_authority(self):
        from types import SimpleNamespace
        from yadinassi.execution.direct.python_direct_transactions import _ROOT_OWNER,service
        def probe():
            context=SimpleNamespace(vm=self.vm,_direct_transaction_owner=_ROOT_OWNER.get(),_eval_depth=[0])
            begin=service(context,self.vm.functions['begintransaction'])
            with patch.object(self.db.backend,'begin_unit_of_work',side_effect=AssertionError('writer before origin')) as writer:
                with self.assertRaises(BoundaryViolation):copy_context().run(begin)
                writer.assert_not_called()
        self.vm.register_function('Probe',probe)
        self.vm.execute('Probe();BeginTransaction();RollbackTransaction();')
        self.clean()
    def test_ingress_live_root_replacements_cannot_acquire_handler_scope(self):
        from yadinassi.execution import safe_mode
        from yadinassi.db import source_transactions
        backend=self.db.backend
        def probe():
            for mode in ('scheduler','database','generation','family','released','configuration','locals','profile','server','module','safe','source'):
                if mode=='safe' or mode=='source':
                    variable=safe_mode._CURRENT if mode=='safe' else source_transactions._current
                    token=variable.set(object());restore=lambda:variable.reset(token)
                else:
                    target=self.vm
                    if mode=='scheduler':name,new='_scheduler',raw_clone(self.vm._scheduler)
                    elif mode=='database':name,new='_database_context',raw_clone(self.vm.database_context)
                    elif mode=='generation':name,new='_family_generation',self.vm._family_generation+1
                    elif mode=='family':name,new='_family_owner',object()
                    elif mode=='locals':name,new='locals',{}
                    elif mode=='profile':name,new='_compilation_profile','foreign'
                    elif mode=='released':name,new='_family_released',True
                    elif mode=='configuration':name,new='_configuration_runtime',object()
                    elif mode=='server':name,new='_context_stack',['server']
                    else:name,new='_module_context_stack',[False]
                    old=getattr(target,name);setattr(target,name,new)
                    restore=lambda:setattr(target,name,old)
                try:
                    with self.subTest(mode=mode),patch.object(backend,'capabilities',side_effect=AssertionError('effect before root check')):
                        with self.assertRaises(BoundaryViolation):self.card.write()
                finally:restore()
                self.assertEqual(tx.current(backend).unit.requests,())
                self.assertEqual(tx.current(backend).leases,0)
        self.vm.register_function('Probe',probe)
        self.vm.execute('BeginTransaction();Probe();RollbackTransaction();')
        self.clean()
    def test_ingress_inherited_denial_and_pending_scheduler(self):
        def probe():
            with tx.admission(False):
                with self.assertRaises(BackendError):self.card.write()
            self.vm._scheduler.new_pending()
            try:
                with self.assertRaises(BoundaryViolation):self.card.write()
            finally:self.vm._scheduler._pending.clear()
            self.assertEqual(tx.current(self.db.backend).unit.requests,())
        self.vm.register_function('Probe',probe)
        with patch.object(prep,'_prepare_catalog_object',side_effect=AssertionError('denied handler')):
            self.vm.execute('BeginTransaction();Probe();RollbackTransaction();')
        self.clean()
    def test_ingress_foreign_catalog_family_same_backend_is_not_authority(self):
        from yadinassi import Interpreter
        foreign=Interpreter(database_context=self.db, allow_extensions=True);self.addCleanup(foreign.close)
        other=foreign._catalogs.get_member('Номенклатура').create_item()
        original_catalogs=self.vm._catalogs
        def probe():
            owner=tx.current(self.db.backend)
            with patch.object(owner,'savepoint',side_effect=AssertionError('foreign savepoint')):
                with self.assertRaises(BoundaryViolation):other.write()
            self.assertEqual(owner.unit.requests,())
            self.vm._catalogs=foreign._catalogs
            try:
                with patch.object(self.db.backend,'capabilities',side_effect=AssertionError('rebound root capability')):
                    with self.assertRaises(BoundaryViolation):other.write()
            finally:self.vm._catalogs=original_catalogs
            self.assertEqual(owner.unit.requests,());self.assertEqual(owner.leases,0)
            self.card.write()
        self.vm.register_function('Probe',probe)
        self.vm.execute('BeginTransaction();Probe();CommitTransaction();')
        self.clean();self.assertFalse(self.card.is_new());self.assertTrue(other.is_new())
    def test_ingress_host_transaction_and_postroot_context_gain_no_authority(self):
        with self.assertRaises(BackendError):
            with tx.execution(self.db.backend):
                tx.begin(self.db.backend);self.card.write()
        self.clean()
        captured=[];self.vm.register_function('Capture',lambda:captured.append(copy_context()))
        self.vm.execute('BeginTransaction();Capture();RollbackTransaction();')
        with self.assertRaises((BoundaryViolation,BackendError)):
            captured[0].run(self.card.write)
        self.clean()
    def test_no_grant_cannot_gain_handler_execution(self):
        with self.assertRaises(BackendError):
            with self.activation():
                tx.begin(self.db.backend)
                prep.write_prepared_catalog_object(fixture.SOURCE,self.warehouse)
        self.clean()

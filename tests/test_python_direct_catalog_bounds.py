"""Scoped preparation budgets cover intermediate work, not only final output."""
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from yadinassi import BSLError,Interpreter
from yadinassi.db.catalog.catalog_object_preparation import _ObjectInterpreter,prepare_catalog_object
from yadinassi.execution.direct.python_direct_catalog_preparation import CatalogPreparationBoundary,prepared_validator
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse
import test_catalog_object_preparation as catalog_fixture


def handler(body):return 'Процедура ПередЗаписью(Отказ) '+body+' КонецПроцедуры'

class DirectCatalogBoundsTests(unittest.TestCase):
    def setUp(self):
        catalog_fixture.CatalogObjectPreparationTests.setUp(self, allow_extensions=True)

    def test_intermediate_expansion_rejects_before_assignment_without_vm(self):
        source=handler('Наименование="changed";x="'+'x'*1024+'";'+'x=x+x;'*8+'Наименование="success";')
        with patch.object(_ObjectInterpreter,'compiled_before',side_effect=AssertionError('VM')),patch.object(_ObjectInterpreter,'compiled_after',side_effect=AssertionError('VM')),patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(self.context.backend,'begin_write',side_effect=AssertionError('write')):
            with self.assertRaisesRegex(BSLError,'text budget'):prepare_catalog_object(source,self.card)
        # Existing partial candidate mutation is not rollback or committed success.
        self.assertEqual(self.card.get_member('Description'),'changed');self.assertTrue(self.card.is_new())
        self.assertIsNone(self.card._pending_write)

    def test_cumulative_utf8_budget_when_each_value_is_bounded(self):
        source=handler('x="'+'я'*2048+'";'+'x=x+x;'*4+'x;'*20)
        with self.assertRaisesRegex(BSLError,'text budget'):prepare_catalog_object(source,self.card)

    def test_numeric_intermediate_and_literal_bounds(self):
        for body in ('x=100000000000000000000000000000000;x=x*x;x=x*x;',
                     'x='+('9'*600)+';',
                     'Если '+('9'*600)+' Тогда x=1;КонецЕсли;',
                     'x="prefix"+'+('9'*600)+';'):
            with self.subTest(body=body[:30]),self.assertRaisesRegex(BSLError,'numeric budget'):
                prepare_catalog_object(handler(body),self.card)

    def test_loop_and_nested_routines_share_steps(self):
        for _ in range(20):self.card.get_member('Склады').add()
        for body in ('','Продолжить;'):
            source=handler('Для Каждого Р Из Склады Цикл '+body+'КонецЦикла;Наименование="success";')
            with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',20),self.assertRaisesRegex(BSLError,'step budget'):
                prepare_catalog_object(source,self.card)
        self.assertNotEqual(self.card.get_member('Description'),'success')
        recursive=handler('Helper();')+' Процедура Helper() Helper();КонецПроцедуры'
        with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',20),self.assertRaisesRegex(BSLError,'step budget'):
            prepare_catalog_object(recursive,self.card)

    def test_cached_validator_counters_reset_per_invocation_and_after_error(self):
        source=handler('x="abc";')
        with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',5):
            for _ in range(5):self.assertEqual(prepare_catalog_object(source,self.card),(False,()))
        first=prepared_validator(self.card._manager,source)
        self.assertIs(first,prepared_validator(self.card._manager,source))
        with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',0),self.assertRaises(BSLError):prepare_catalog_object(source,self.card)
        self.assertEqual(prepare_catalog_object(source,self.card),(False,()))
        self.assertIs(first,prepared_validator(self.card._manager,source))
        from dataclasses import replace
        stale=replace(first,_key=first._key[:-1])
        self.card._manager._direct_validator_plan=stale
        refreshed=prepared_validator(self.card._manager,source)
        self.assertIsNot(refreshed,stale)
        with self.assertRaises(ValueError):prepared_validator(self.card._manager,source,prepared=stale)

    def test_short_circuit_and_early_return_skip_unreached_large_values(self):
        huge='9'*600
        for body in ('Если Ложь И '+huge+' Тогда x=1;КонецЕсли;',
                     'Если Истина Или '+huge+' Тогда x=1;КонецЕсли;',
                     'Возврат;x='+huge+';'):
            with self.subTest(body=body[:30]):self.assertEqual(prepare_catalog_object(handler(body),self.card),(False,()))

    def test_rebound_repairs_invalidate_and_cannot_disable_required_budget_profile(self):
        import yadinassi.execution.direct.python_direct_catalog_preparation as direct
        source=handler('x=1;')
        first=prepared_validator(self.card._manager,source)
        with patch.object(direct,'REPAIRS',direct.REPAIRS+('authority_checkpoints',)):
            second=prepared_validator(self.card._manager,source)
            self.assertIsNot(first,second)
            with self.assertRaises(ValueError):prepared_validator(self.card._manager,source,prepared=first)
            self.assertIn('preparation_step',second._plan.generated_source)
            self.assertIn('preparation_value',second._plan.generated_source)
        for options in ((),('authority_checkpoints',)):
            with patch.object(direct,'REPAIRS',options),self.assertRaises(ValueError):
                prepared_validator(self.card._manager,source)
        self.assertEqual(prepare_catalog_object(source,self.card),(False,()))
        # Cache identity uses a snapshot, not a mutable options container.
        mutable=list(direct.REPAIRS)
        with patch.object(direct,'REPAIRS',mutable):
            before=prepared_validator(self.card._manager,source)
            mutable.append('authority_checkpoints')
            after=prepared_validator(self.card._manager,source)
            self.assertIsNot(before,after)
            with self.assertRaises(ValueError):prepared_validator(self.card._manager,source,prepared=before)

    def test_options_snapshot_is_shared_by_cache_key_and_compilation(self):
        import yadinassi.execution.direct.python_direct_catalog_preparation as direct
        import yadinassi.db.catalog.catalog_object_preparation as preparation
        original=preparation._admit_catalog_object_source
        source=handler('x=2;')
        def change(*args):
            direct.REPAIRS=()
            return original(*args)
        with patch.object(direct,'REPAIRS',direct.REPAIRS),patch.object(preparation,'_admit_catalog_object_source',change):
            result=prepared_validator(self.card._manager,source)
            self.assertIn('service_boundaries',result._plan.repairs)
            self.assertIn('preparation_value',result._plan.generated_source)
            with self.assertRaises(ValueError):prepared_validator(self.card._manager,source,prepared=result)

    def test_exact_scalar_guard_never_calls_foreign_hooks_or_traverses(self):
        vm=_ObjectInterpreter(self.card,lambda record:None);self.addCleanup(vm.close)
        boundary=CatalogPreparationBoundary(vm);boundary.enter();self.addCleanup(boundary.leave)
        seen=[]
        class Evil(str):
            def __len__(self):seen.append('len');raise AssertionError
            def __str__(self):seen.append('str');raise AssertionError
            def encode(self,*args):seen.append('encode');raise AssertionError
        value=Evil('x');container=[value];container.append(container)
        self.assertIs(boundary.preparation_value(value),value)
        self.assertIs(boundary.preparation_value(container),container)
        boundary.revoke()
        with self.assertRaises(BoundaryViolation):boundary.preparation_value('x')
        self.assertEqual(seen,[])

    def test_dead_branch_no_cost_and_regular_compiler_profile_unchanged(self):
        source=handler('Если Ложь Тогда x=1;x=x+x;КонецЕсли;')
        self.assertEqual(prepare_catalog_object(source,self.card),(False,()))
        code='X=1;X=X+1;'
        base=compile_owned(parse(code),source_text=code,source_name='bounds.bsl')
        explicit=compile_owned(parse(code),source_text=code,source_name='bounds.bsl',catalog_bounds=False)
        self.assertEqual(base.generated_source,explicit.generated_source)
        self.assertNotIn('preparation_',base.generated_source)
        with self.assertRaises(ValueError):compile_owned(parse(code),source_text=code,source_name='bounds.bsl',catalog_bounds=True)

import test_python_direct_catalog_preparation as main_fixture
import test_python_direct_transaction_preparation as transaction_fixture
from yadinassi.db import database_transactions as tx

class DirectCatalogBoundsWriteTests(unittest.TestCase):
    def setUp(self):
        main_fixture.DirectCatalogPreparationTests.setUp(self, allow_extensions=True)

    def test_selected_standalone_write_budget_failure_never_persists(self):
        with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',0),self.assertRaisesRegex(BSLError,'step budget'):
            self.card.write()
        self.assertTrue(self.card.is_new());self.assertIsNone(self.card._pending_write)
        self.assertIsNone(self.db.backend._active)
        self.assertEqual(len(self.card._manager.select()._rows),0)
        self.card.write()
        self.assertFalse(self.card.is_new());self.assertEqual(len(self.card._manager.select()._rows),1)

    def test_uncaught_budget_failure_rolls_back_owned_transaction_prior_stage(self):
        ref=self.warehouse.get_member('Ссылка');original=ref.get_object(ref).get_member('Наименование')
        owners=[]
        def probe():
            with transaction_fixture.DirectTransactionPreparationTests.activation(self):
                tx.begin(self.db.backend)
                self.warehouse.set_member('Наименование','must rollback');self.warehouse.write()
                owners.append(tx.current(self.db.backend))
                with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',0):self.card.write()
        self.vm.register_function('Probe',probe)
        with self.assertRaisesRegex(BSLError,'step budget'):self.vm.execute('Probe();')
        transaction_fixture.DirectTransactionPreparationTests.clean(self)
        self.assertEqual(ref.get_object(ref).get_member('Наименование'),original)
        self.assertEqual(len(self.card._manager.select()._rows),0)
        self.assertIsNone(self.card._pending_write);self.assertIsNone(self.warehouse._pending_write)
        self.assertEqual(owners[0].leases,0)

    def test_owned_transaction_preserves_prior_stage_without_failed_participant(self):
        def probe():
            with transaction_fixture.DirectTransactionPreparationTests.activation(self):
                tx.begin(self.db.backend)
                self.warehouse.set_member('Наименование','prior stage');self.warehouse.write()
                owner=tx.current(self.db.backend);requests=owner.unit.requests;participants=owner.participants
                with patch('yadinassi.db.catalog.catalog_object_preparation._MAX_STEPS',0),self.assertRaisesRegex(BSLError,'step budget'):
                    self.card.write()
                self.assertIs(owner.unit.requests,requests);self.assertIs(owner.participants,participants)
                self.assertEqual(len(requests),1);self.assertEqual(owner.leases,0)
                self.assertTrue(self.card.is_new());self.assertIsNone(self.card._pending_write)
                tx.commit(self.db.backend)
        self.vm.register_function('Probe',probe);self.vm.execute('Probe();')
        transaction_fixture.DirectTransactionPreparationTests.clean(self)
        self.assertEqual(len(self.card._manager.select()._rows),0)
        ref=self.warehouse.get_member('Ссылка');self.assertEqual(ref.get_object(ref).get_member('Наименование'),'prior stage')
        # New admitted root/preparation gets new counters after the caught failure.
        self.vm.register_function('WriteCard',self.card.write);self.vm.execute('WriteCard();')
        self.assertFalse(self.card.is_new());transaction_fixture.DirectTransactionPreparationTests.clean(self)

if __name__=='__main__':unittest.main()

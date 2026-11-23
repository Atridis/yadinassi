"""Posting code reuse does not reuse document, frame, transaction or grants."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
import test_python_direct_posting as fixture
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.document.document_posting_values import DocumentWriteMode
from yadinassi.execution.direct.python_direct_posting import prepared_posting
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508

class PreparedPostingTests(TestCase):
    def setUp(self):
        self.f=fixture.DirectPostingTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.vm=self.f.vm
    def test_compile_once_before_own_transaction_fresh_receivers_contexts(self):
        import yadinassi.execution.direct.python_direct_posting as direct
        original=direct.compile_owned;boundary=direct.PostingBoundary;compiles=[];contexts=[]
        def compile(*args,**kwargs):
            self.assertIsNone(self.f.fixture.context.backend._active);compiles.append(1)
            return original(*args,**kwargs)
        def context(vm):
            result=boundary(vm);contexts.append(result);return result
        with patch.object(direct,'compile_owned',compile),patch.object(direct,'PostingBoundary',context):
            a=self.f.document();a.write(DocumentWriteMode.POSTING);a.write(DocumentWriteMode.POSTING)
            b=self.f.document();b.set_member('Number','second');b.write(DocumentWriteMode.POSTING)
        self.assertEqual(len(compiles),1);self.assertEqual(len(contexts),3)
        self.assertEqual(len({id(c) for c in contexts}),3)
        self.assertIs(contexts[0].document,a);self.assertIs(contexts[-1].document,b)
        runtime=self.vm._documents.posting_runtime();cached=runtime._direct_plans[a._key.document_id]
        self.assertIsNone(cached._plan.last_state);self.assertIsNone(a._posting_active);self.assertIsNone(b._posting_active)
        self.assertEqual(self.f.counts(),(2,2,2))
    def test_cached_handler_cancel_and_raise_read_current_inputs(self):
        d=self.f.document();d.write(DocumentWriteMode.POSTING);before=self.f.counts()
        with patch('yadinassi.execution.direct.python_direct_posting.compile_owned',side_effect=AssertionError('recompile')):
            for mode in (1,2):
                d.get_member('AdditionalProperties').insert('Mode',Decimal(mode))
                with self.assertRaises(Exception):d.write(DocumentWriteMode.POSTING)
                self.assertEqual(d.get_member('AdditionalProperties').get_member('Inside'),1)
                self.assertEqual(self.f.counts(),before);self.assertIsNone(d._posting_active)
    def test_target_schema_and_compiler_options_replace_only_slot(self):
        import yadinassi.execution.direct.python_direct_posting as direct
        d=self.f.document();runtime=self.vm._documents.posting_runtime()
        a=prepared_posting(runtime,d,self.vm)
        old=d._manager._schema
        try:
            d._manager._schema=replace(old,number_length=old.number_length+1)
            b=prepared_posting(runtime,d,self.vm);self.assertIsNot(a,b)
        finally:d._manager._schema=old
        with patch.object(self.vm,'_native_target',LINUX_8_3_27_1508):
            c=prepared_posting(runtime,d,self.vm);self.assertIsNot(a,c)
        with patch.object(direct,'REPAIRS',direct.REPAIRS+('authority_checkpoints',)):
            e=prepared_posting(runtime,d,self.vm);self.assertIsNot(a,e)
        self.assertEqual(len(runtime._direct_plans),1)
    def test_distinct_admitted_source_is_not_shared(self):
        import test_document_posting_runtime as other
        f=other.PostingRuntimeTests();f.setUp();self.addCleanup(f.doCleanups)
        plans=[]
        for marker in ('first','second'):
            f.make('Procedure Posting(Cancel,Mode) AdditionalProperties.Insert("Marker","'+marker+'"); EndProcedure')
            d=f.vm._documents.get_member('OwnedPostingDoc').create_document()
            d.set_member('Number','3');d.set_member('Date',self.vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
            d.write(DocumentWriteMode.POSTING)
            self.assertEqual(d.get_member('AdditionalProperties').get_member('Marker'),marker)
            plans.append(f.vm._documents.posting_runtime()._direct_plans[d._key.document_id])
        self.assertIsNot(plans[0],plans[1]);self.assertNotEqual(plans[0]._key[0],plans[1]._key[0])

    def persisted_document(self, key):
        # A new owned connection, not a cached outcome or recovery API.
        with SQLiteDBContext(self.f.fixture.path) as context:
            with closing(context.backend.begin_document_read()) as view:
                card = view.read_document(key)
                self.assertIsNotNone(card)
                self.assertTrue(card.posted)
                self.assertEqual(card.number, 'r1')
                self.assertEqual(card.tabular_sections[0].rows[0].values[1], Decimal(5))
                return card

    def refuse_stale_create_without_preparing(self, host, operation, draft):
        with patch('yadinassi.execution.direct.python_direct_posting.prepared_posting',
                   side_effect=AssertionError('prepare on stale create')), \
             patch('yadinassi.db.document.document_posting.PostingRuntime.write',
                   side_effect=AssertionError('handler replay')):
            with self.assertRaises(BackendError) as error:
                host.execute(operation, draft, None, form='Document.Receipt.Form.Card', command='Post')
        self.assertEqual(error.exception.code, 'conflict')

    def test_committed_create_rejects_stale_intent_without_preparing(self):
        from yadinassi.configuration.demos.inventory_host_operations import InventoryRootOperations
        context = self.f.fixture.context
        host = InventoryRootOperations(context, context.backend.accumulation_configuration)
        self.addCleanup(host.close)
        draft, operation = self.f.document()._draft(), uuid4()
        result = host.execute(operation, draft, None, form='Document.Receipt.Form.Card', command='Post')
        self.assertEqual(result.state, 'committed')
        self.assertTrue(result.accepted)
        before = self.persisted_document(draft.key)
        self.refuse_stale_create_without_preparing(host, operation, draft)
        self.assertEqual(self.persisted_document(draft.key), before)
        self.assertEqual(self.f.counts(), (1, 1, 1))

    def test_uncertain_post_does_not_retry_and_persisted_state_can_be_reopened(self):
        from yadinassi.configuration.demos.inventory_host_operations import InventoryRootOperations
        from yadinassi.db.sqlite.sqlite_transactions import UnitOfWork
        context = self.f.fixture.context
        host = InventoryRootOperations(context, context.backend.accumulation_configuration)
        self.addCleanup(host.close)
        draft, operation = self.f.document()._draft(), uuid4()
        original = UnitOfWork.commit
        commits = []
        def lost(unit):
            original(unit)
            commits.append(unit.state)
            unit.state = 'uncertain'
            raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork, 'commit', lost):
            result = host.execute(operation, draft, None, form='Document.Receipt.Form.Card', command='Post')
        self.assertEqual(commits, ['committed'])
        self.assertEqual(result.state, 'uncertain')
        self.assertFalse(result.accepted)
        self.assertEqual(result.error, 'uncertain_commit')
        self.assertIsNone(context.backend._active)
        before = self.persisted_document(draft.key)
        self.refuse_stale_create_without_preparing(host, operation, draft)
        self.assertEqual(self.persisted_document(draft.key), before)
        self.assertEqual(self.f.counts(), (1, 1, 1))

    def test_plain_write_without_selected_handlers_does_not_compile(self):
        d=self.f.document()
        with patch('yadinassi.execution.direct.python_direct_posting.compile_owned',side_effect=AssertionError('unused posting compile')):
            d.write(DocumentWriteMode.WRITE)
        self.assertEqual(self.f.counts(),(1,1,0))
        self.assertFalse(d.get_member('Posted'))

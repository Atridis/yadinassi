"""Posting code reuse does not reuse document, frame, transaction or grants."""
from dataclasses import replace
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
import test_python_direct_posting as fixture
from yadinassi.document_posting_values import DocumentWriteMode
from yadinassi.python_direct_posting import prepared_posting
from yadinassi.native_targets import LINUX_8_3_27_1508

class PreparedPostingTests(TestCase):
    def setUp(self):
        self.f=fixture.DirectPostingTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.vm=self.f.vm
    def test_compile_once_before_own_transaction_fresh_receivers_contexts(self):
        import yadinassi.python_direct_posting as direct
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
        with patch('yadinassi.python_direct_posting.compile_owned',side_effect=AssertionError('recompile')):
            for mode in (1,2):
                d.get_member('AdditionalProperties').insert('Mode',Decimal(mode))
                with self.assertRaises(Exception):d.write(DocumentWriteMode.POSTING)
                self.assertEqual(d.get_member('AdditionalProperties').get_member('Inside'),1)
                self.assertEqual(self.f.counts(),before);self.assertIsNone(d._posting_active)
    def test_target_schema_and_compiler_options_replace_only_slot(self):
        import yadinassi.python_direct_posting as direct
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

    def test_original_receipt_committed_id_never_prepares_or_replays(self):
        from uuid import uuid4
        from yadinassi.inventory_host_operations import InventoryRootOperations
        host=InventoryRootOperations(self.f.fixture.context,self.f.fixture.context.backend.accumulation_configuration)
        self.addCleanup(host.close)
        d=self.f.document();draft=d._draft();operation=uuid4()
        receipt=host.execute(operation,draft,None,form='Document.Receipt.Form.Card',command='Post')
        self.assertEqual(receipt.state,'committed');self.assertEqual(self.f.counts(),(1,1,1))
        with patch('yadinassi.python_direct_posting.prepared_posting',side_effect=AssertionError('prepare on receipt')),patch('yadinassi.document_posting.PostingRuntime.write',side_effect=AssertionError('handler replay')):
            again=host.execute(operation,draft,None,form='Document.Receipt.Form.Card',command='Post')
        self.assertIs(again,receipt);self.assertEqual(self.f.counts(),(1,1,1))

    def test_original_receipt_uncertain_commit_resolves_without_prepare(self):
        from uuid import uuid4
        from yadinassi.inventory_host_operations import InventoryRootOperations
        from yadinassi.sqlite_transactions import UnitOfWork
        from yadinassi.catalog_backend import BackendError
        host=InventoryRootOperations(self.f.fixture.context,self.f.fixture.context.backend.accumulation_configuration)
        self.addCleanup(host.close)
        d=self.f.document();original=UnitOfWork.commit
        def lost(unit):original(unit);unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):
            receipt=host.execute(uuid4(),d._draft(),None,form='Document.Receipt.Form.Card',command='Post')
        self.assertEqual(receipt.state,'uncertain')
        with patch('yadinassi.python_direct_posting.prepared_posting',side_effect=AssertionError('prepare on receipt')),patch('yadinassi.document_posting.PostingRuntime.write',side_effect=AssertionError('handler replay')):
            resolved=host.resolve(receipt.operation_id)
        self.assertEqual(resolved.state,'committed');self.assertEqual(self.f.counts(),(1,1,1))

    def test_plain_write_without_selected_handlers_does_not_compile(self):
        d=self.f.document()
        with patch('yadinassi.python_direct_posting.compile_owned',side_effect=AssertionError('unused posting compile')):
            d.write(DocumentWriteMode.WRITE)
        self.assertEqual(self.f.counts(),(1,1,0))
        self.assertFalse(d.get_member('Posted'))

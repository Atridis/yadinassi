"""Trusted-root posting identity, terminal faults and activation boundaries."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.db.catalog.catalog_backend import BackendError, TabularSectionRows, TabularRow
from yadinassi.configuration.configuration_posting_application import import_posting_application, PROFILE
from yadinassi.configuration.configuration_document import DocumentObjectSession
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.database_transactions import admission, execution, Transaction
from yadinassi.db.document.document_backend import DocumentDraft, DocumentKey
from yadinassi.db.document.document_posting_host import RootPostingOperations
from yadinassi.db.sqlite.sqlite_transactions import UnitOfWork
from posting_application_fixture import source, FORM

ROOT=Path(__file__).resolve().parents[1]


class PostingHostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.files=source();self.config=import_posting_application(self.files,posting_runtime=PROFILE)
        self.context=SQLiteDBContext.create_posting(Path(self.temp.name)/'app.sqlite',self.config)
        self.addCleanup(self.context.close);self.backend=self.context.backend
        self.host=RootPostingOperations(self.context,self.config)
        self.addCleanup(self.cleanup_host)
        self.schema=self.config.documents[0]
        self.key=DocumentKey(self.backend.database_id,self.schema.identity,uuid4())
        self.draft=DocumentDraft(self.key,'1',datetime(2024,1,1),False,(Decimal(7),),
            (TabularSectionRows(self.schema.tabular_sections[0].identity,(TabularRow(uuid4(),(Decimal(2),)),)),),False)

    def cleanup_host(self):
        if self.host._closed:return
        self.host.close()

    def execute(self,command='DoPost',draft=None,expected=None,operation=None):
        return self.host.execute(operation or uuid4(),self.draft if draft is None else draft,expected,form=FORM,command=command)

    def card(self):
        with closing(self.backend.begin_document_read()) as view:return view.read_document(self.key)

    def movement(self):return self.backend.read_recorder(self.config.registers[0].identity,self.key).rows

    def test_atomic_post_contains_document_state_and_movements(self):
        receipt=self.execute()
        self.assertEqual(receipt.state,'committed');self.assertTrue(receipt.accepted)
        self.assertEqual([r.kind for r in receipt.requests],['document_create','document_set_posted','recorder_replace'])
        self.assertTrue(self.card().posted);self.assertEqual(self.movement()[0].values,(Decimal(1),Decimal(7)))
        self.assertEqual(self.card().tabular_sections,self.draft.tabular_sections)

    def test_write_is_unposted_and_has_no_movements(self):
        self.execute('DoWrite');self.assertFalse(self.card().posted);self.assertEqual(self.movement(),())

    def test_undo_posting_clears_owned_movements(self):
        self.execute();card=self.card();self.execute('DoUndo',expected=card.revision)
        self.assertFalse(self.card().posted);self.assertEqual(self.movement(),())

    def test_write_preserves_posted_and_prior_movements(self):
        self.execute();card=self.card();rows=self.movement()
        self.execute('DoWrite',draft=replace(self.draft,values=(Decimal(9),)),expected=card.revision)
        self.assertTrue(self.card().posted);self.assertEqual(self.movement(),rows)

    def test_new_operation_uses_new_empty_movement_buffer(self):
        self.execute();self.execute(expected=self.card().revision)
        self.assertEqual(len(self.movement()),1)

    def test_repeated_stale_input_cannot_replay_after_commit(self):
        operation=uuid4();self.execute(operation=operation)
        with patch('yadinassi.db.document.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            with self.assertRaisesRegex(BackendError,'conflict'):
                self.execute(operation=operation)
        self.assertEqual(self.card().revision.token,'1')
        self.assertIsNone(self.host._active_operation)

    def test_correlation_id_is_not_a_persistent_history_key(self):
        operation=uuid4();self.execute(operation=operation)
        second=self.execute(expected=self.card().revision,operation=operation)
        self.assertTrue(second.accepted)
        self.assertEqual(self.card().revision.token,'2')
        self.assertIsNone(self.host._active_operation)

    def test_reentrant_execute_is_refused_before_effect(self):
        execute=self.execute
        real=self.host._verify
        def verify():
            with self.assertRaisesRegex(BackendError,'busy'):
                execute()
            return real()
        with patch.object(self.host,'_verify',side_effect=verify):
            self.assertTrue(execute().accepted)
        self.assertEqual(self.card().revision.token,'1')

    def test_ungranted_command_refused(self):
        with self.assertRaisesRegex(BackendError,'unsupported'):self.execute('Post')

    def test_wrong_form_refused(self):
        with self.assertRaises(BackendError):self.host.execute(uuid4(),self.draft,None,form='Document.Other.Form.Card',command='DoPost')

    def test_stale_revision_refused_before_begin(self):
        self.execute()
        with patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('begin')):
            with self.assertRaises(BackendError):self.execute()

    def test_mutable_draft_payload_refused(self):
        with self.assertRaises(BackendError):self.execute(draft=replace(self.draft,values=[Decimal(7)]))

    def test_uuid_string_and_zero_refused(self):
        for operation in (str(uuid4()),UUID(int=0)):
            with self.assertRaises(BackendError):self.host.execute(operation,self.draft,None,form=FORM,command='DoPost')

    def test_child_admission_cannot_activate_host_operation(self):
        with admission(False):
            with self.assertRaises(BackendError):self.execute()
        self.assertIsNone(self.card())

    def test_nested_execution_cannot_activate_host_operation(self):
        with execution(self.backend):
            with self.assertRaises(BackendError):self.execute()
        self.assertIsNone(self.card())

    def test_old_nonposting_session_still_refuses_backend(self):
        with self.assertRaises(BackendError):DocumentObjectSession(self.context,self.schema,self.files)

    def test_no_lookup_or_history_on_live_or_reopened_adapter(self):
        self.assertTrue(self.execute().accepted)
        for name in ('_operations','receipt','resolve','intent','acknowledge'):
            self.assertFalse(hasattr(self.host,name))
        self.assertIsNone(self.host._active_operation)
    def test_final_source_recheck_does_not_retain_operation(self):
        real=self.host._verify;count=0;operation=uuid4()
        def verify():
            nonlocal count
            count+=1
            if count==2:raise BackendError('schema_changed')
            return real()
        with patch.object(self.host,'_verify',side_effect=verify):
            with self.assertRaises(BackendError):self.execute(operation=operation)
        self.assertIsNone(self.host._active_operation)
        self.assertIsNone(self.card());self.host.close()

    def test_handler_cancellation_rolls_back_whole_operation(self):
        with patch('yadinassi.db.document.document_posting._PostingInterpreter.invoke',side_effect=ValueError('cancelled')):
            receipt=self.execute()
        self.assertEqual(receipt.state,'rejected');self.assertIsNone(self.card());self.assertEqual(self.movement(),())

    def test_lost_commit_reply_stays_unknown_without_lookup_or_replay(self):
        real=UnitOfWork.commit;operation=uuid4()
        def lost(unit):real(unit);unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):result=self.execute(operation=operation)
        self.assertEqual(result.state,'uncertain');self.assertFalse(result.accepted)
        self.assertIsNone(self.host._active_operation)
        with patch('yadinassi.db.document.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            with self.assertRaisesRegex(BackendError,'conflict'):self.execute(operation=operation)
            self.host.close()
        self.assertTrue(self.card().posted)

    def test_unknown_before_commit_does_not_claim_success_or_replay(self):
        def lost(unit):unit._view.close();unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):result=self.execute()
        self.assertEqual(result.state,'uncertain');self.assertFalse(result.accepted)
        self.assertIsNone(self.host._active_operation)
        with patch('yadinassi.db.document.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            self.host.close()
        self.assertIsNone(self.card())

    def test_known_commit_acceptance_failure_is_not_reported_as_rollback(self):
        with patch.object(Transaction,'_install',side_effect=RuntimeError('refresh')):result=self.execute()
        self.assertEqual(result.state,'committed');self.assertFalse(result.accepted);self.assertTrue(self.card().posted)
        self.assertIsNone(self.host._active_operation)
        self.host.close()

    def test_lost_reply_and_cleanup_interrupt_do_not_retain_closed_operation(self):
        real=UnitOfWork.commit
        def lost(unit):real(unit);unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost),patch.object(UnitOfWork,'close',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.execute()
        self.assertIsNone(self.host._active_operation)
        self.assertTrue(self.card().posted)

    def test_known_commit_with_retained_connection_can_refresh_without_replay(self):
        def committed(unit):
            unit._view._connection.execute('COMMIT')
            unit.state='committed'
            raise BackendError('storage_error')
        with patch.object(UnitOfWork,'commit',committed),patch.object(UnitOfWork,'close',side_effect=BackendError('storage_error')):
            result=self.execute()
            self.assertEqual((result.state,result.accepted),('committed',False))
            self.assertTrue(self.host._active_operation.needs_cleanup)
        with patch('yadinassi.db.document.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            self.host.verify_source()
        self.assertIsNone(self.host._active_operation)
        self.assertTrue(self.card().posted)

    def test_no_outcome_allocation_is_needed_after_commit(self):
        real=UnitOfWork.commit
        def committed(unit):
            result=real(unit)
            allocation=patch('yadinassi.db.database_transactions.RootOperationReceipt',side_effect=MemoryError)
            allocation.start();self.addCleanup(allocation.stop)
            return result
        with patch.object(UnitOfWork,'commit',committed):result=self.execute()
        self.assertEqual(result.state,'committed');self.assertTrue(result.accepted)
        self.assertIsNone(self.host._active_operation)

    def test_commit_memory_error_does_not_retain_already_closed_operation(self):
        real=UnitOfWork.commit
        def lost(unit):real(unit);unit.state='uncertain';raise MemoryError
        with patch.object(UnitOfWork,'commit',lost):
            with self.assertRaises(MemoryError):self.execute()
        self.assertIsNone(self.host._active_operation)
        self.assertTrue(self.card().posted)

    def test_failed_rollback_retains_only_physical_cleanup(self):
        with patch('yadinassi.db.document.document_posting.PostingRuntime.write',side_effect=ValueError('fail')),patch.object(UnitOfWork,'rollback',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.execute()
            active=self.host._active_operation
            self.assertIsNotNone(active);self.assertTrue(active.needs_cleanup)
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):self.execute()
            with self.assertRaises(KeyboardInterrupt):self.host.close()
            self.assertIs(self.host._active_operation,active)
        with patch('yadinassi.db.document.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            self.host.close()
        self.assertIsNone(self.host._active_operation);self.assertIsNone(self.card())

    def test_full_source_mismatch_refused_before_begin(self):
        with patch.object(self.backend,'export_configuration',return_value={}):
            with patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('begin')):
                with self.assertRaises(BackendError):self.execute()

    def test_empty_additional_properties_are_not_external_inputs(self):
        seen=[]
        real=self.host._document
        def construct(intent):
            doc=real(intent)
            seen.append(intent)
            self.assertEqual(set(intent.__dataclass_fields__),{'operation_id','mode','draft','expected'})
            return doc
        with patch.object(self.host,'_document',side_effect=construct):
            self.assertTrue(self.execute().accepted)
        self.assertEqual(len(seen),1)
        self.assertIsNone(self.host._active_operation)

    def test_root_entry_failure_is_terminal_not_perpetual_prepared(self):
        operation=uuid4()
        with patch('yadinassi.db.database_transactions.RootOperation._enter',side_effect=MemoryError):
            with self.assertRaises(MemoryError):self.execute(operation=operation)
        self.assertIsNone(self.host._active_operation)
        self.assertIsNone(self.card());self.host.close()

    def test_second_root_context_token_failure_restores_first_token(self):
        from yadinassi.db import database_transactions as tx
        operation=uuid4()
        class Fault:
            def get(self):return None
            def set(self,value):raise MemoryError
        with patch.object(tx,'_execution_backend',Fault()):
            with self.assertRaises(MemoryError):self.execute(operation=operation)
            self.assertIsNone(tx._execution.get())
        self.assertIsNone(self.host._active_operation)
        self.assertIsNone(self.card());self.host.close()

"""Explicit v2 root acknowledgement preserves exact recovery and all identities."""
from contextlib import closing
from dataclasses import replace
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import UUID,uuid4
import test_document_posting_host as posting
import test_inventory_host_operations as inventory
from yadinassi.catalog_backend import BackendError
from yadinassi.database_transactions import Transaction,RootOperation,admission
from yadinassi.sqlite_transactions import UnitOfWork
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.document_posting_host import PostingRecoveryUnavailable


class RootAcknowledgementTests(unittest.TestCase):
    setUp=posting.PostingHostTests.setUp
    cleanup_host=posting.PostingHostTests.cleanup_host
    execute=posting.PostingHostTests.execute
    def rows(self):
        with closing(sqlite3.connect(self.context.path)) as db:
            return {table:db.execute('SELECT * FROM '+table+' ORDER BY operation_id').fetchall()
                for table in ('unit_of_work_receipt','document_commit_receipt','document_posting_receipt','recorder_movement_receipt')}
    def root(self,receipt): return self.host._operations[receipt.operation_id][1]
    def test_ack_compacts_only_duplicate_root_and_preserves_exact_recovery(self):
        receipt=self.execute();before=self.rows()
        result=self.host.acknowledge(receipt.operation_id);after=self.rows()
        self.assertEqual(result.version,2);self.assertEqual(result.children,3)
        self.assertLess(result.compact_bytes,result.original_bytes)
        for table in before:
            if table!='unit_of_work_receipt':self.assertEqual(before[table],after[table])
        self.assertEqual(before['unit_of_work_receipt'][0][:2],after['unit_of_work_receipt'][0][:2])
        self.assertEqual(json.loads(after['unit_of_work_receipt'][0][2])['schema'],'unit-of-work-ack-v2')
        self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
        self.assertIs(self.host.resolve(receipt.operation_id),receipt)
        self.assertEqual(self.host.acknowledge(receipt.operation_id),result)
        self.assertEqual(self.rows(),after)
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.begin_unit_of_work(receipt.operation_id)
        child=UUID(json.loads(before['unit_of_work_receipt'][0][2])[0][1])
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.begin_unit_of_work(child)
    def test_reopen_resolves_original_outcomes_without_host_object(self):
        receipt=self.execute();self.host.acknowledge(receipt.operation_id)
        with closing(SQLiteCatalogBackend(self.context.path)) as reopened:
            self.assertEqual(reopened.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
            with self.assertRaisesRegex(BackendError,'conflict'):reopened.begin_unit_of_work(receipt.operation_id)
    def test_failure_before_commit_rolls_back_and_retry_is_idempotent(self):
        receipt=self.execute();before=self.rows()
        with patch('yadinassi.sqlite_transactions._commit_acknowledgement',side_effect=OSError('before commit')):
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):self.host.acknowledge(receipt.operation_id)
        self.assertEqual(before,self.rows())
        self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
        self.host.acknowledge(receipt.operation_id)
    def test_lost_commit_response_retries_without_callback_or_writes(self):
        receipt=self.execute()
        def lost(connection):connection.execute('COMMIT');raise OSError('lost response')
        with patch('yadinassi.sqlite_transactions._commit_acknowledgement',side_effect=lost):
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):self.host.acknowledge(receipt.operation_id)
        after=self.rows()
        with patch('yadinassi.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            self.host.acknowledge(receipt.operation_id)
            self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
        self.assertEqual(after,self.rows())
    def test_unaccepted_commit_cannot_acknowledge(self):
        with patch.object(Transaction,'_install',side_effect=RuntimeError('install')):receipt=self.execute()
        self.assertFalse(receipt.accepted);before=self.rows()
        with self.assertRaisesRegex(BackendError,'unsupported'):self.host.acknowledge(receipt.operation_id)
        self.assertEqual(before,self.rows());receipt=self.host.resolve(receipt.operation_id)
        self.assertTrue(receipt.accepted);self.host.acknowledge(receipt.operation_id)
    def test_uncertain_without_commit_cannot_acknowledge(self):
        def lost(unit):unit._view.close();unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):receipt=self.execute()
        before=self.rows()
        with self.assertRaisesRegex(BackendError,'unsupported'):self.host.acknowledge(receipt.operation_id)
        self.assertEqual(before,self.rows());self.host.resolve(receipt.operation_id)
    def test_forged_acceptance_image_and_foreign_operation_refused(self):
        receipt=self.execute();root=self.root(receipt);root.receipt=replace(receipt)
        with self.assertRaisesRegex(BackendError,'unsupported'):root.acknowledge()
        root.receipt=receipt
        with self.assertRaises(PostingRecoveryUnavailable):self.host.acknowledge(uuid4())
    def test_child_change_after_typed_resolution_is_detected_under_writer_lock(self):
        receipt=self.execute();before=self.rows();original=self.backend.resolve_unit_of_work
        def race(*args):
            result=original(*args)
            with closing(sqlite3.connect(self.context.path)) as db,db:
                db.execute("UPDATE document_commit_receipt SET number='changed'")
            return result
        with patch.object(self.backend,'resolve_unit_of_work',side_effect=race):
            with self.assertRaisesRegex(BackendError,'integrity'):self.host.acknowledge(receipt.operation_id)
        self.assertEqual(before['unit_of_work_receipt'],self.rows()['unit_of_work_receipt'])
    def test_bad_v2_and_missing_child_never_resolve_as_absence(self):
        receipt=self.execute();self.host.acknowledge(receipt.operation_id)
        with closing(sqlite3.connect(self.context.path)) as db,db:db.execute('DELETE FROM document_commit_receipt')
        with self.assertRaisesRegex(BackendError,'integrity'):self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.begin_unit_of_work(receipt.operation_id)

    def test_oversized_root_race_is_refused_before_payload_fetch(self):
        receipt=self.execute('DoWrite');trace=[];original=self.backend.resolve_unit_of_work
        begin=self.backend.begin_write
        def race(*args):
            result=original(*args)
            with closing(sqlite3.connect(self.context.path)) as db,db:
                db.execute('UPDATE unit_of_work_receipt SET outcomes_json=?',('x'*2048,))
            return result
        def writer(*args):
            view=begin(*args);view._connection.set_trace_callback(trace.append);return view
        with patch('yadinassi.sqlite_transactions.MAX_BYTES',1024), \
                patch.object(self.backend,'resolve_unit_of_work',side_effect=race), \
                patch.object(self.backend,'begin_write',side_effect=writer):
            with self.assertRaisesRegex(BackendError,'integrity'):self.host.acknowledge(receipt.operation_id)
        self.assertFalse(any(sql.startswith('SELECT request_hash,outcomes_json FROM unit_of_work_receipt') for sql in trace))
    def test_oversized_child_is_refused_before_payload_fetch(self):
        receipt=self.execute('DoWrite');self.host.acknowledge(receipt.operation_id);trace=[]
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('UPDATE document_commit_receipt SET number=?',('я'*40000,))
        begin=self.backend.begin_read
        def reader():
            view=begin();view._connection.set_trace_callback(trace.append);return view
        with patch.object(self.backend,'begin_read',side_effect=reader):
            with self.assertRaisesRegex(BackendError,'integrity'):
                self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
        self.assertFalse(any(sql.startswith('SELECT document_id,record_id,revision,number FROM document_commit_receipt') for sql in trace))
    def test_noninteger_child_revision_is_not_fetched_by_preflight(self):
        receipt=self.execute('DoWrite');self.host.acknowledge(receipt.operation_id);trace=[]
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('UPDATE document_commit_receipt SET revision=?',(b'x'*131072,))
        begin=self.backend.begin_read
        def reader():
            view=begin();view._connection.set_trace_callback(trace.append);return view
        with patch.object(self.backend,'begin_read',side_effect=reader):
            with self.assertRaisesRegex(BackendError,'integrity'):
                self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
        self.assertTrue(any("CASE WHEN typeof(revision)='integer' THEN revision ELSE NULL END" in sql for sql in trace))
        self.assertFalse(any(sql.startswith('SELECT document_id,record_id,revision,number FROM document_commit_receipt') for sql in trace))
    def test_unknown_version_and_bad_v2_shape_do_not_erase_identity(self):
        receipt=self.execute('DoWrite');self.host.acknowledge(receipt.operation_id)
        original=self.rows()['unit_of_work_receipt'][0][2]
        for changed,code in ((dict(json.loads(original),schema='unit-of-work-ack-v99'),'conflict'),
                             (dict(json.loads(original),extra=True),'integrity')):
            with closing(sqlite3.connect(self.context.path)) as db,db:
                db.execute('UPDATE unit_of_work_receipt SET outcomes_json=?',(json.dumps(changed,separators=(',',':')),))
            with self.assertRaisesRegex(BackendError,code):
                self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
            with self.assertRaisesRegex(BackendError,'conflict'):self.backend.begin_unit_of_work(receipt.operation_id)
    def test_interruption_before_and_after_ack_commit_preserves_recovery(self):
        receipt=self.execute();before=self.rows()
        for committed in (False,True):
            def interrupt(connection):
                if committed:connection.execute('COMMIT')
                raise KeyboardInterrupt()
            with patch('yadinassi.sqlite_transactions._commit_acknowledgement',side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):self.host.acknowledge(receipt.operation_id)
            self.assertIs(self.host.receipt(receipt.operation_id),receipt)
            self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
            if not committed:self.assertEqual(self.rows(),before)
        self.host.acknowledge(receipt.operation_id)
    def test_oversized_generic_child_is_not_materialized(self):
        receipt=self.execute();self.host.acknowledge(receipt.operation_id);trace=[]
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('UPDATE recorder_movement_receipt SET outcome_json=?',('x'*16384,))
        begin=self.backend.begin_read
        def reader():
            view=begin();view._connection.set_trace_callback(trace.append);return view
        with patch('yadinassi.sqlite_transactions.MAX_BYTES',4096),patch.object(self.backend,'begin_read',side_effect=reader):
            with self.assertRaisesRegex(BackendError,'integrity'):
                self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
        self.assertFalse(any(sql.startswith('SELECT outcome_json FROM recorder_movement_receipt') for sql in trace))
    def test_changed_request_and_reordered_compact_bindings_refuse(self):
        receipt=self.execute();self.host.acknowledge(receipt.operation_id)
        first=receipt.requests[0]
        changed=(replace(first,draft=replace(first.draft,number='changed')),*receipt.requests[1:])
        with self.assertRaisesRegex(BackendError,'conflict'):
            self.backend.resolve_unit_of_work(receipt.operation_id,changed)
        compact=json.loads(self.rows()['unit_of_work_receipt'][0][2])
        compact['bindings'].reverse()
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('UPDATE unit_of_work_receipt SET outcomes_json=?',(json.dumps(compact,separators=(',',':')),))
        with self.assertRaisesRegex(BackendError,'conflict'):
            self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
    def test_old_root_digest_still_binds_acknowledged_children(self):
        receipt=self.execute('DoWrite');self.host.acknowledge(receipt.operation_id)
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('UPDATE unit_of_work_receipt SET request_hash=?',('0'*64,))
        with self.assertRaisesRegex(BackendError,'conflict'):
            self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
    def test_rehydration_budget_counts_json_escaping_before_allocation(self):
        receipt=self.execute();self.host.acknowledge(receipt.operation_id)
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('UPDATE recorder_movement_receipt SET outcome_json=?',('\x00'*1000,))
        with patch('yadinassi.sqlite_transactions.MAX_BYTES',4096):
            with self.assertRaisesRegex(BackendError,'unsupported'):
                self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
    def test_later_object_update_does_not_change_acknowledged_outcomes(self):
        receipt=self.execute()
        with closing(self.backend.begin_document_read()) as view:card=view.read_document(self.key)
        later=self.execute('DoWrite',expected=card.revision)
        self.assertTrue(later.accepted)
        self.host.acknowledge(receipt.operation_id)
        self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
        with closing(self.backend.begin_document_read()) as view:
            self.assertEqual(view.read_document(self.key).revision.token,'2')
    def test_epoch_and_non_host_versions_refused_before_storage_access(self):
        receipt=self.execute('DoWrite');root=self.root(receipt);before=self.rows()
        for version in (11,12,14):
            with patch.object(root,'_admit_root'),patch.object(self.backend,'format_version',version), \
                    patch.object(self.backend,'begin_write',side_effect=AssertionError('write')):
                with self.assertRaisesRegex(BackendError,'unsupported'):root.acknowledge()
        self.assertEqual(before,self.rows())


class InventoryAcknowledgementTests(unittest.TestCase):
    setUp=inventory.InventoryHostTests.setUp
    cleanup_host=inventory.InventoryHostTests.cleanup_host
    execute=inventory.InventoryHostTests.execute
    def test_inventory_root_roundtrip_and_ack_is_not_bsl_authority(self):
        receipt=self.execute();before=receipt.outcomes
        result=self.host.acknowledge(receipt.operation_id)
        self.assertEqual(result.children,3)
        self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),before)
        with closing(SQLiteCatalogBackend(self.context.path)) as reopened:
            self.assertEqual(reopened.resolve_unit_of_work(receipt.operation_id,receipt.requests),before)
        with admission(False):
            with self.assertRaisesRegex(BackendError,'unsupported'):self.host.acknowledge(receipt.operation_id)


class EnumInventoryAcknowledgementTests(unittest.TestCase):
    def test_v16_catalog_child_ack_and_reopen_recovery(self):
        import tempfile
        from pathlib import Path
        from inventory_enum_application_fixture import source
        from yadinassi.configuration_inventory_enum_application import import_inventory_application,PROFILE
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi.runtime import Interpreter
        from yadinassi.inventory_host_operations import InventoryRootOperation
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'enum.sqlite'
            with SQLiteDBContext.create_inventory_enum_application(path,import_inventory_application(source(),inventory_runtime=PROFILE)) as context:
                with closing(Interpreter(database_context=context)) as vm:
                    obj=vm.execute('P=Catalogs.Products.CreateItem();P.Code="1";P.Unit=Enums.Units.Piece;P')
                    root=InventoryRootOperation(context.backend,uuid4());receipt=root.run(obj.write)
                    self.assertTrue(receipt.accepted)
                    ack=root.acknowledge();self.assertEqual(ack.children,1)
                    self.assertEqual(context.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
            with closing(SQLiteCatalogBackend(path)) as reopened:
                self.assertEqual(reopened.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)
                with self.assertRaisesRegex(BackendError,'conflict'):reopened.begin_unit_of_work(receipt.operation_id)


class AcknowledgementSizeTests(unittest.TestCase):
    def test_ascii_json_size_matches_serializer_without_large_copy(self):
        from yadinassi.sqlite_transactions import _quoted_json_size,_json
        for value in ('', ''.join(chr(i) for i in range(128)), 'я😀', '\\"\n'*100):
            expected=len(_json(value))
            self.assertEqual(_quoted_json_size(value,expected),expected)
            with self.assertRaisesRegex(BackendError,'unsupported'):
                _quoted_json_size(value,expected-1)

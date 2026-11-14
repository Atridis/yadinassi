"""Executable retention constraints; intentional corruption only in disposable DBs.

These are not GC implementation tests: they prove why deleting accepted receipts
without a separately admitted tombstone protocol is unsafe.
"""
from contextlib import closing
import json
import sqlite3
import unittest
from uuid import UUID
from yadinassi.catalog_backend import BackendError
import test_document_posting_host as posting_fixtures


class ReceiptRetentionFrontierTests(unittest.TestCase):
    setUp = posting_fixtures.PostingHostTests.setUp
    cleanup_host = posting_fixtures.PostingHostTests.cleanup_host
    execute = posting_fixtures.PostingHostTests.execute

    def write_sql(self, sql, args):
        with closing(sqlite3.connect(self.context.path)) as connection, connection:
            connection.execute(sql,args)

    def child(self, operation):
        with closing(sqlite3.connect(self.context.path)) as connection:
            raw=connection.execute('SELECT outcomes_json FROM unit_of_work_receipt WHERE operation_id=?',
                                   (str(operation),)).fetchone()[0]
        return UUID(json.loads(raw)[0][1])

    def assert_reuse_refused(self, operation):
        with self.assertRaisesRegex(BackendError,'conflict'):
            self.backend.begin_unit_of_work(operation)

    def test_acceptance_does_not_release_root_or_child_replay_guards(self):
        receipt=self.execute('DoWrite')
        self.assertTrue(receipt.accepted)
        self.assert_reuse_refused(receipt.operation_id)
        self.assert_reuse_refused(self.child(receipt.operation_id))
        self.assertEqual(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests),receipt.outcomes)

    def test_child_deletion_breaks_recovery_and_releases_child_identity(self):
        receipt=self.execute('DoWrite');child=self.child(receipt.operation_id)
        self.write_sql('DELETE FROM document_commit_receipt WHERE operation_id=?',(str(child),))
        with self.assertRaisesRegex(BackendError,'integrity'):
            self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
        self.assert_reuse_refused(receipt.operation_id)
        # Even retaining the root cannot protect the removed child's UUID.
        # No mutation is staged or committed in this demonstration.
        with closing(self.backend.begin_unit_of_work(child)):pass

    def test_root_deletion_changes_known_commit_into_absence(self):
        receipt=self.execute('DoWrite')
        self.write_sql('DELETE FROM unit_of_work_receipt WHERE operation_id=?',(str(receipt.operation_id),))
        self.assertIsNone(self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests))
        with closing(self.backend.begin_unit_of_work(receipt.operation_id)):pass

    def test_unversioned_compact_marker_is_not_valid_recovery(self):
        receipt=self.execute('DoWrite')
        self.write_sql('UPDATE unit_of_work_receipt SET outcomes_json=? WHERE operation_id=?',
                       ('{"acknowledged":true}',str(receipt.operation_id)))
        with self.assertRaisesRegex(BackendError,'conflict'):
            self.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests)
        self.assert_reuse_refused(receipt.operation_id)

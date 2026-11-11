"""Writer rejection rolls back before a fresh reader budget can be exceeded."""
import unittest
from unittest.mock import patch
from uuid import uuid4
from yadinassi.catalog_backend import BackendError
from yadinassi.document_backend import DocumentKey
from yadinassi.sqlite_document_posting_state import PostedIntent,stage_posted
from yadinassi import sqlite_recorder_movements as movements
from yadinassi import sqlite_document_posting_state as posted
import test_recorder_movement_storage as movement_fixture
import test_document_posting_state as posted_fixture

class GlobalMovementBudgetTests(unittest.TestCase):
    def setUp(self):
        self.f=movement_fixture.RecorderStorageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def other(self):
        f=self.f;key=DocumentKey(f.db,f.doc,uuid4())
        f.c.execute('INSERT INTO document_record VALUES(?,?)',(str(f.doc),str(key.record_id)))
        return key
    def reject_second(self,limit,value,empty=False):
        f=self.f;first=f.request(rows=() if empty else None);op=uuid4();out=f.port.replace(op,first)
        key=self.other();second=f.request(key,rows=() if empty else None);second_op=uuid4()
        before=f.port.read(f.reg,key)
        with patch.object(movements,limit,value):
            with self.assertRaises(BackendError):f.port.replace(second_op,second)
            movements.validate_database_budget(f.c)
        self.assertEqual(f.port.read(f.reg,key),before)
        self.assertIsNone(f.port.resolve(second_op,second))
        self.assertEqual(f.port.resolve(op,first),out)
        self.assertEqual(f.c.execute('SELECT COUNT(*) FROM recorder_partition').fetchone()[0],1)
    def test_aggregate_row_limit_rolls_back_child_and_receipt(self):
        self.reject_second('MAX_DATABASE_ROWS',1)
    def test_aggregate_byte_limit_rolls_back_child_and_receipt(self):
        f=self.f;raw=f.port._encoded(f.schema,f.request().rows)[0][2]
        self.reject_second('MAX_DATABASE_BYTES',len(raw.encode()))
    def test_empty_partitions_cannot_exceed_limit(self):
        self.reject_second('MAX_DATABASE_PARTITIONS',1,True)
    def test_existing_partition_replacement_at_limit_allowed(self):
        f=self.f;f.port.replace(uuid4(),f.request())
        with patch.object(movements,'MAX_DATABASE_ROWS',1),patch.object(movements,'MAX_DATABASE_PARTITIONS',1):
            f.port.replace(uuid4(),f.request())
            movements.validate_database_budget(f.c)
    def test_budget_failure_does_not_poison_owner_transaction(self):
        self.reject_second('MAX_DATABASE_ROWS',1)
        f=self.f;f.port.replace(uuid4(),f.request(rows=()))
        self.assertTrue(f.c.in_transaction)
    def test_aggregate_validator_matches_writer_limit(self):
        f=self.f;f.port.replace(uuid4(),f.request())
        with patch.object(movements,'MAX_DATABASE_ROWS',0):
            with self.assertRaises(BackendError):movements.validate_database_budget(f.c)

class GlobalPostedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.f=posted_fixture.PostedStorageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_new_posted_state_refused_before_mutation(self):
        f=self.f;stage_posted(f.c,f.db,PostedIntent(f.key,1,True))
        key=DocumentKey(f.db,f.key.document_id,uuid4())
        f.c.execute('INSERT INTO document_record VALUES(?,?,1)',(str(key.document_id),str(key.record_id)))
        with patch.object(posted,'MAX_POSTED_RECORDS',1):
            with self.assertRaises(BackendError):stage_posted(f.c,f.db,PostedIntent(key,1,True))
            posted.validate_database_budget(f.c)
        self.assertEqual(f.c.execute('SELECT COUNT(*) FROM document_posting_state').fetchone()[0],1)
    def test_existing_state_can_change_at_limit(self):
        f=self.f;stage_posted(f.c,f.db,PostedIntent(f.key,1,True))
        with patch.object(posted,'MAX_POSTED_RECORDS',1):
            stage_posted(f.c,f.db,PostedIntent(f.key,1,False));posted.validate_database_budget(f.c)
        self.assertIs(posted.read_posted(f.c,f.db,f.key),False)

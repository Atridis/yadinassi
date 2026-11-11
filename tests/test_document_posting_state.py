import sqlite3
import unittest
from uuid import uuid4
from yadinassi.catalog_backend import BackendError
from yadinassi.document_backend import DocumentKey
from yadinassi.sqlite_document_posting_state import POSTED_DDL,PostedIntent,read_posted,stage_posted

class PostedStorageTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:',isolation_level=None);self.addCleanup(self.c.close)
        self.c.execute('PRAGMA foreign_keys=ON');self.c.execute('CREATE TABLE document_record(document_id TEXT,record_id TEXT,revision INTEGER,PRIMARY KEY(document_id,record_id))');self.c.execute(POSTED_DDL)
        self.db=uuid4();self.key=DocumentKey(self.db,uuid4(),uuid4());self.c.execute('INSERT INTO document_record VALUES(?,?,1)',(str(self.key.document_id),str(self.key.record_id)));self.c.execute('BEGIN')
    def test_default_false_and_explicit_true(self):
        self.assertIs(read_posted(self.c,self.db,self.key),False)
        stage_posted(self.c,self.db,PostedIntent(self.key,1,True))
        self.assertIs(read_posted(self.c,self.db,self.key),True)
    def test_revision_conflict_before_change(self):
        with self.assertRaises(BackendError):stage_posted(self.c,self.db,PostedIntent(self.key,2,True))
        self.assertIs(read_posted(self.c,self.db,self.key),False)
    def test_outer_rollback_restores_unposted(self):
        stage_posted(self.c,self.db,PostedIntent(self.key,1,True));self.c.execute('ROLLBACK');self.c.execute('BEGIN')
        self.assertIs(read_posted(self.c,self.db,self.key),False)
    def test_missing_document_distinct_from_unposted(self):
        self.assertIsNone(read_posted(self.c,self.db,DocumentKey(self.db,self.key.document_id,uuid4())))
    def test_corrupt_future_posted_revision_is_not_hidden(self):
        self.c.execute('INSERT INTO document_posting_state VALUES(?,?,2,1)',(str(self.key.document_id),str(self.key.record_id)))
        with self.assertRaises(BackendError):read_posted(self.c,self.db,self.key)
    def test_borrowed_transaction_required(self):
        self.c.execute('ROLLBACK')
        with self.assertRaises(BackendError):read_posted(self.c,self.db,self.key)

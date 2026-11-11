"""Host intent boundaries, not native posting observations."""
from dataclasses import replace
from uuid import uuid4
import unittest
from yadinassi.catalog_backend import BackendError, FieldSchema
from yadinassi.document_backend import DocumentKey
from yadinassi.document_movements import (RecorderRegisterSchema, RecorderMovementRow,
    RecorderReplacement, validate_replacement, mutation_identity)

class MovementIntentTests(unittest.TestCase):
    def setUp(self):
        self.database, self.document, self.register = uuid4(), uuid4(), uuid4()
        self.schema = RecorderRegisterSchema(self.register,(self.document,),
            (FieldSchema(uuid4(),'Flag','boolean'),))
        self.request = RecorderReplacement(self.register,
            DocumentKey(self.database,self.document,uuid4()),
            (RecorderMovementRow(1,True,(False,)),),'0'*64)
    def check(self, request): return validate_replacement(self.schema,request,self.database)
    def test_valid_partition(self): self.assertIs(self.check(self.request),self.request)
    def test_empty_replacement_still_snapshot_bound(self):
        self.check(replace(self.request,rows=()))
        with self.assertRaises(BackendError):self.check(replace(self.request,rows=(),expected_snapshot=None))
    def test_cross_database_refused(self):
        with self.assertRaises(BackendError):self.check(replace(self.request,recorder=replace(self.request.recorder,database_id=uuid4())))
    def test_unlisted_recorder_refused(self):
        with self.assertRaises(BackendError):self.check(replace(self.request,recorder=replace(self.request.recorder,document_id=uuid4())))
    def test_contiguous_lines_required(self):
        with self.assertRaises(BackendError):self.check(replace(self.request,rows=(RecorderMovementRow(2,True,(False,)),)))
    def test_active_is_exact_boolean(self):
        with self.assertRaises(BackendError):self.check(replace(self.request,rows=(RecorderMovementRow(1,1,(False,)),)))
    def test_scalar_types_are_not_coerced(self):
        with self.assertRaises(BackendError):self.check(replace(self.request,rows=(RecorderMovementRow(1,True,(1,)),)))
    def test_duplicate_schema_fields_refused(self):
        with self.assertRaises(BackendError):validate_replacement(replace(self.schema,fields=self.schema.fields*2),self.request,self.database)
    def test_different_recorders_have_disjoint_mutation_identity(self):
        other=replace(self.request,recorder=replace(self.request.recorder,record_id=uuid4()))
        self.assertNotEqual(mutation_identity(self.request),mutation_identity(other))

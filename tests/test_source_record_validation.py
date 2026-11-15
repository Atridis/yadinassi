"""Independent record validation bounds and single canonical identity decoding."""
import sqlite3
import unittest
from uuid import UUID,uuid4
from unittest.mock import patch
import test_source_record_stream as fixture
from yadinassi.source_catalog_store import _record_identity

class RecordValidationTests(unittest.TestCase):
    setUp=fixture.SourceRecordStreamTests.setUp
    values=fixture.SourceRecordStreamTests.values
    store=fixture.SourceRecordStreamTests.store
    populated=fixture.SourceRecordStreamTests.populated
    read=fixture.SourceRecordStreamTests.read
    def test_validate_count_without_preflight(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind)
            with patch('yadinassi.source_'+kind+'_store._MAX_RECORDS',3):s.validate_records()
            with patch('yadinassi.source_'+kind+'_store._MAX_RECORDS',2):
                with self.assertRaisesRegex(ValueError,'record bound'):s.validate_records()
            s.close();self.path.unlink()
    def test_one_identity_parse_per_read_and_validation_record(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind)
            with patch('yadinassi.source_catalog_store.UUID',wraps=UUID) as parse:
                self.read(s,kind);self.assertEqual(parse.call_count,3)
                parse.reset_mock();s.validate_records();self.assertEqual(parse.call_count,3)
            s.close();self.path.unlink()
    def test_identity_revision_boundaries(self):
        raw='abcdefab-cdef-abcd-efab-cdefabcdefab'
        for family in ('catalog','document'):
            for revision in (1,2**53):self.assertEqual(_record_identity(raw,revision,family),UUID(raw))
            for revision in (0,-1,2**53+1,True,1.0,'1',None):
                with self.subTest(revision=revision):
                    with self.assertRaises(ValueError):_record_identity(raw,revision,family)
            for identity in (str(UUID(int=0)),raw.upper(),raw.replace('-',''),'{'+raw+'}',raw.encode(),None,1,'z'*36):
                with self.subTest(identity=identity):
                    with self.assertRaises(ValueError):_record_identity(identity,1,family)
    def test_validator_error_does_not_hold_statement(self):
        for kind in ('catalog','document'):
            s,ids=self.populated(kind)
            s._connection.execute('UPDATE source_'+kind+'_record SET payload=? WHERE record_identity=?',('[]',str(min(ids,key=str))))
            retained=None
            try:s.validate_records()
            except ValueError as error:retained=error
            self.assertIsNotNone(retained);self.assertIsNotNone(retained.__traceback__)
            other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            try:
                other.execute('BEGIN IMMEDIATE');other.execute('UPDATE source_'+kind+'_record SET revision=revision');other.execute('COMMIT')
            finally:other.close()
            s.close();self.path.unlink()
    def test_validator_bound_error_does_not_hold_statement(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind);retained=None
            with patch('yadinassi.source_'+kind+'_store._MAX_RECORDS',1):
                try:s.validate_records()
                except ValueError as error:retained=error
            self.assertIsNotNone(retained)
            other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            try:
                other.execute('BEGIN IMMEDIATE');other.execute('UPDATE source_'+kind+'_record SET revision=revision');other.execute('COMMIT')
            finally:other.close()
            s.close();self.path.unlink()

"""Streaming validators enforce aggregate byte limits independently of preflight."""
import unittest
import sqlite3
from unittest.mock import patch
import test_source_record_stream as records
import test_source_section_global_stream as sections

class RecordByteBoundsTests(unittest.TestCase):
    setUp=records.SourceRecordStreamTests.setUp
    values=records.SourceRecordStreamTests.values
    store=records.SourceRecordStreamTests.store
    populated=records.SourceRecordStreamTests.populated
    def test_exact_total_and_one_byte_over(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind)
            total=s._connection.execute('SELECT sum(length(CAST(payload AS BLOB))) FROM source_'+kind+'_record').fetchone()[0]
            with patch('yadinassi.source_'+kind+'_store._MAX_RECORD_BYTES',total):s.validate_records()
            with patch('yadinassi.source_'+kind+'_store._MAX_RECORD_BYTES',total-1):
                with self.assertRaisesRegex(ValueError,'record bounds'):s.validate_records()
            s.close();self.path.unlink()
    def test_overflow_releases_cursor(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind);retained=None
            with patch('yadinassi.source_'+kind+'_store._MAX_RECORD_BYTES',1):
                try:s.validate_records()
                except ValueError as error:retained=error
            self.assertIsNotNone(retained)
            other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            try:
                other.execute('BEGIN IMMEDIATE');other.execute('UPDATE source_'+kind+'_record SET revision=revision');other.execute('COMMIT')
            finally:other.close()
            s.close();self.path.unlink()
    def test_multibyte_payload_uses_bytes(self):
        s,_=self.populated('catalog');s._connection.execute("UPDATE source_catalog_record SET payload=replace(payload,'One','ёж')")
        total,chars=s._connection.execute('SELECT sum(length(CAST(payload AS BLOB))),sum(length(payload)) FROM source_catalog_record').fetchone()
        self.assertGreater(total,chars)
        # Canonical JSON escapes Unicode. Isolate the byte guard from the
        # subsequent canonical decoder using a single malformed row.
        s._connection.execute('DELETE FROM source_catalog_record WHERE record_identity NOT IN (SELECT record_identity FROM source_catalog_record LIMIT 1)')
        total,chars=s._connection.execute('SELECT length(CAST(payload AS BLOB)),length(payload) FROM source_catalog_record').fetchone()
        with patch('yadinassi.source_catalog_store._MAX_RECORD_BYTES',total):
            with self.assertRaisesRegex(ValueError,'canonical payload'):s.validate_records()
        with patch('yadinassi.source_catalog_store._MAX_RECORD_BYTES',chars):
            with self.assertRaisesRegex(ValueError,'record bounds'):s.validate_records()

class SectionByteBoundsTests(unittest.TestCase):
    setUp=sections.SectionGlobalStreamTests.setUp
    values=sections.SectionGlobalStreamTests.values
    store=sections.SectionGlobalStreamTests.store
    populated=sections.SectionGlobalStreamTests.populated
    def test_total_accumulates_across_families(self):
        s,_=self.populated(3)
        total=s._connection.execute('SELECT sum(length(CAST(payload AS BLOB))) FROM source_document_section').fetchone()[0]
        with patch('yadinassi.source_document_section_store._MAX_STORAGE_BYTES',total):s.validate_records()
        with patch('yadinassi.source_document_section_store._MAX_STORAGE_BYTES',total-1):
            with self.assertRaisesRegex(ValueError,'aggregate storage bound'):s.validate_records()
    def test_total_error_closes_statement(self):
        s,_=self.populated(3);retained=None
        with patch('yadinassi.source_document_section_store._MAX_STORAGE_BYTES',1):
            try:s.validate_records()
            except ValueError as error:retained=error
        self.assertIsNotNone(retained)
        other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
        try:
            other.execute('BEGIN IMMEDIATE');other.execute('UPDATE source_document_section SET payload=payload');other.execute('COMMIT')
        finally:other.close()

"""Record aggregate preflight preserves bounds and exception priority."""
import sqlite3
import unittest
from unittest.mock import patch
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.source_document_store import SourceDocumentStore

class RecordPreflightTests(unittest.TestCase):
    def store(self,kind):
        cls={'catalog':SourceCatalogStore,'document':SourceDocumentStore}[kind]
        s=object.__new__(cls);s._connection=sqlite3.connect(':memory:')
        self.addCleanup(s._connection.close)
        s._catalog_rows=();s._document_rows=()
        for k,field in [('catalog','code'),('document','number')]:
            s._connection.execute(f'CREATE TABLE source_{k}_schema(identity,name,definition)')
            # Deliberately weak fixture admits corrupt raw SQLite values.
            s._connection.execute(f'CREATE TABLE source_{k}_record({k}_identity,record_identity,revision,payload,{field})')
        return s
    def insert(self,s,k,**changes):
        values={k+'_identity':'a'*36,'record_identity':'b'*36,'revision':1,'payload':'[]',
                'code' if k=='catalog' else 'number':'1'}
        values.update(changes)
        s._connection.execute(f"INSERT INTO source_{k}_record VALUES(?,?,?,?,?)",tuple(values.values()))
    def test_one_scan_empty_and_populated(self):
        for k in ('catalog','document'):
            s=self.store(k)
            for populated in (False,True):
                if populated:self.insert(s,k)
                queries=[];s._connection.set_trace_callback(queries.append);s.verify_extra()
                self.assertEqual(len([q for q in queries if 'FROM source_'+k+'_record' in q]),1)
    def test_malformed_columns_and_byte_bounds(self):
        for k in ('catalog','document'):
            field='code' if k=='catalog' else 'number';limit=256 if k=='catalog' else 36
            cases=[{k+'_identity':'é'*36},{'record_identity':b'b'*36},
                   {'payload':b'[]'},{'payload':'é'*32769},
                   {'revision':0},{'revision':9007199254740993},{'revision':1.5},
                   {field:'é'*(limit//2+1)},{field:b'1'},{'payload':None}]
            for changes in cases:
                with self.subTest(kind=k,changes=list(changes)):
                    s=self.store(k);self.insert(s,k,**changes)
                    with self.assertRaisesRegex(ValueError,'record storage bounds'):s.verify_extra()
    def test_payload_and_revision_exact_boundaries(self):
        for k in ('catalog','document'):
            s=self.store(k);self.insert(s,k,payload='é'*32768,revision=9007199254740992)
            s.verify_extra()
    def test_aggregate_byte_boundary(self):
        for k in ('catalog','document'):
            s=self.store(k)
            for _ in range(256):self.insert(s,k,payload='x'*65536)
            s.verify_extra();self.insert(s,k,payload='x')
            with self.assertRaisesRegex(ValueError,'record bounds'):s.verify_extra()
    def test_row_count_boundary(self):
        for k in ('catalog','document'):
            s=self.store(k)
            s._connection.executemany(f'INSERT INTO source_{k}_record VALUES(?,?,?,?,?)',
                                     [('a'*36,'b'*36,1,'','1')]*10000)
            s.verify_extra();self.insert(s,k,payload='')
            with self.assertRaisesRegex(ValueError,'record bounds'):s.verify_extra()
    def test_schema_binding_precedes_aggregate_bounds(self):
        for k in ('catalog','document'):
            s=self.store(k);setattr(s,'_'+k+'_rows',(('unexpected',),))
            self.insert(s,k)
            with patch('yadinassi.source_'+k+'_store._MAX_RECORDS',0):
                with self.assertRaisesRegex(ValueError,'schema binding integrity'):s.verify_extra()
    def test_malformed_precedes_schema_binding(self):
        for k in ('catalog','document'):
            s=self.store(k);setattr(s,'_'+k+'_rows',(('unexpected',),))
            self.insert(s,k,revision=0)
            with self.assertRaisesRegex(ValueError,'record storage bounds'):s.verify_extra()

"""Authored format16 storage contracts; not native assignment semantics."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID, uuid4

from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogKey,
    TabularRow, TabularSectionRows, CatalogScanRequest, CatalogOrder)
from yadinassi.document_backend import DocumentDraft, DocumentKey
from yadinassi.transaction_backend import TransactionRequest
from yadinassi.accumulation_movements import (AccumulationMovementRow,
    AccumulationDirection, AccumulationReplacement)
from yadinassi.configuration_inventory_enums import import_inventory_enum_configuration, PROFILE
from yadinassi.enum_storage_values import EnumKey
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from test_configuration_inventory_enums import source

ROOT=Path(__file__).resolve().parents[1]

class InventoryEnumStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'enum.sqlite'
        self.config=import_inventory_enum_configuration(source(),inventory_runtime=PROFILE)
        self.backend=SQLiteCatalogBackend.create_inventory_enum(self.path,self.config)
        self.addCleanup(self.backend.close)
        self.domain=self.backend._enum_domain
        self.units=next(e for e in self.config.enumerations if e.name=='Units')
        self.unit=EnumKey(self.backend.database_id,self.units.identity,self.units.values[0].identity)
        self.products=next(c for c in self.config.catalogs if c.name=='Products')
        self.document=next(d for d in self.config.documents if d.name=='Receipt')
        self.register=self.config.registers[0]

    def sql(self,statement,args=()):
        with closing(sqlite3.connect(self.path)) as db,db:return db.execute(statement,args).fetchall()

    def values(self,fields):
        def value(f):
            if f.kind=='enum_ref':return self.unit if f.target_enum_id==self.units.identity else self.domain.empty(f.target_enum_id)
            if f.kind=='catalog_ref':return CatalogKey(self.backend.database_id,f.target_catalog_id,UUID(int=0))
            return {'string':'','number':Decimal('1'),'boolean':False,'datetime':datetime(2025,1,1)}[f.kind]
        return tuple(value(f) for f in fields)

    def catalog(self):
        return CatalogDraft(CatalogKey(self.backend.database_id,self.products.identity,uuid4()),'1','Product',False,self.values(self.products.fields))

    def document_draft(self):
        sections=tuple(TabularSectionRows(s.identity,(TabularRow(uuid4(),self.values(s.fields)),)) for s in self.document.tabular_sections)
        return DocumentDraft(DocumentKey(self.backend.database_id,self.document.identity,uuid4()),'1',datetime(2025,1,1),False,self.values(self.document.fields),sections)

    def seed(self,*,commit=True):
        catalog=self.catalog();document=self.document_draft()
        operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            tx.stage(TransactionRequest('catalog_create',catalog))
            tx.stage(TransactionRequest('document_create',document))
            snapshot=tx.read_accumulation(self.register.identity,document.key).snapshot
            row=AccumulationMovementRow(1,datetime(2025,1,1),True,AccumulationDirection.RECEIPT,
                self.values(self.register.dimensions),self.values(self.register.resources),self.values(self.register.attributes))
            request=AccumulationReplacement(self.register.identity,document.key,(row,),snapshot)
            tx.stage(TransactionRequest('accumulation_replace',request))
            self.assertEqual(tx.read_catalog(catalog.key).values,catalog.values)
            self.assertEqual(tx.read_document(document.key).values,document.values)
            self.assertEqual(tx.read_accumulation(self.register.identity,document.key).rows,(row,))
            if commit:outcomes=tx.commit()
            else:outcomes=None
            requests=tx.requests
        return catalog,document,row,operation,requests,outcomes

    def test_fresh_format16_and_no_old_domain(self):
        self.assertEqual((self.backend.format_version,self.backend.storage_version),(16,7))
        self.assertEqual(self.domain.database_id,self.backend.database_id)

    def test_staged_catalog_document_lines_movements_reopen(self):
        c,d,row,_,_,_=self.seed()
        self.backend.close()
        with closing(SQLiteCatalogBackend(self.path)) as backend:
            with backend.begin_unit_of_work(uuid4()) as tx:
                self.assertEqual(tx.read_catalog(c.key).values,c.values)
                self.assertEqual(tx.read_document(d.key).tabular_sections,d.tabular_sections)
                self.assertEqual(tx.read_accumulation(self.register.identity,d.key).rows,(row,))

    def test_shared_receipt_recovery(self):
        *_,operation,requests,outcomes=self.seed()
        self.assertEqual(self.backend.resolve_unit_of_work(operation,requests),outcomes)

    def test_staged_rollback_all_ports(self):
        c,d,_,operation,requests,_=self.seed(commit=False)
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            self.assertIsNone(tx.read_catalog(c.key));self.assertIsNone(tx.read_document(d.key))
            self.assertEqual(tx.read_accumulation(self.register.identity,d.key).rows,())
        self.assertIsNone(self.backend.resolve_unit_of_work(operation,requests))

    def test_catalog_projected_enum(self):
        c,*_=self.seed()
        with closing(self.backend.begin_read()) as view:
            fields=tuple(f.identity for f in self.products.fields)
            page=view.scan_catalog_values(self.products.identity,CatalogScanRequest(),fields)
            self.assertEqual(page.rows[0].values,c.values)

    def test_typed_empty_catalog_roundtrip(self):
        c=self.catalog();c=replace(c,values=tuple(self.domain.empty(f.target_enum_id) if f.kind=='enum_ref' else v for f,v in zip(self.products.fields,c.values)))
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            tx.stage(TransactionRequest('catalog_create',c));self.assertEqual(tx.read_catalog(c.key).values,c.values);tx.commit()

    def test_wrong_owner_target_unknown_and_string_refused(self):
        c=self.catalog();index=next(i for i,f in enumerate(self.products.fields) if f.kind=='enum_ref')
        other=next(e for e in self.config.enumerations if e.identity!=self.units.identity)
        for bad in (replace(self.unit,database_id=uuid4()),self.domain.empty(other.identity),replace(self.unit,value_id=uuid4()),'Piece'):
            values=list(c.values);values[index]=bad
            with self.backend.begin_unit_of_work(uuid4()) as tx:
                with self.assertRaises(BackendError):tx.stage(TransactionRequest('catalog_create',replace(c,values=tuple(values))))

    def test_old_creator_refuses_new_configuration(self):
        for creator in (SQLiteCatalogBackend.create_inventory,SQLiteCatalogBackend.create_accumulation):
            path=Path(self.temp.name)/('old-'+creator.__name__+'.sqlite')
            with self.assertRaises(BackendError):creator(path,self.config)
            self.assertFalse(path.exists())

    def test_source_hash_corruption_rejected_each_begin(self):
        self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'",('0'*64,))
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_actual_bytes_rehashed_not_trusted_receipt(self):
        self.sql("UPDATE configuration_file SET content=CAST(content||' ' AS BLOB) WHERE path='Configuration.xml'")
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_consistent_new_source_is_not_cached_old_authority(self):
        path='Configuration.xml';raw=source()[path]+b'\n'
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',(raw,sha256(raw).hexdigest(),path))
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_catalog_field_target_corruption_rejected(self):
        raw=self.sql('SELECT definition FROM catalog_schema WHERE identity=?',(str(self.products.identity),))[0][0]
        data=json.loads(raw);data[4][-1][-1]=str(uuid4())
        self.sql('UPDATE catalog_schema SET definition=? WHERE identity=?',(json.dumps(data),str(self.products.identity)))
        with self.assertRaises(BackendError):self.backend.begin_read()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)

    def test_document_schema_corruption_rejected(self):
        self.sql("UPDATE document_schema SET definition=replace(definition,'enum_document_v1','nonposting_document_v1')")
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_register_field_corruption_rejected(self):
        self.sql("UPDATE accumulation_register_schema SET definition=replace(definition,'enum_ref','string')")
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_recorder_membership_corruption_rejected(self):
        self.sql('DELETE FROM accumulation_register_document WHERE document_id=?',(str(self.document.identity),))
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_marker_corruption_rejected(self):
        self.sql("UPDATE inventory_profile SET profile='accumulation-reference-v1'")
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_format_downgrade_not_migration(self):
        self.sql('PRAGMA user_version=15')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)

    def test_extra_ddl_rejected(self):
        self.sql('CREATE TABLE extra(value TEXT)')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
        with self.assertRaises(BackendError):self.backend.begin_read()

    def test_read_only_open_and_begin_execute_no_ddl(self):
        before=self.sql('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')
        with closing(SQLiteCatalogBackend(self.path,read_only=True)) as backend:
            with closing(backend.begin_read()) as view:self.assertEqual(len(view.catalogs()),2)
        self.assertEqual(before,self.sql('SELECT type,name,sql FROM sqlite_master ORDER BY type,name'))

    def test_unknown_persisted_enum_uuid_rejected_on_read(self):
        c,*_=self.seed();field=next(f for f in self.products.fields if f.kind=='enum_ref')
        table=self.backend._layout.table_name(self.products.identity);column=self.backend._layout.field_name(self.products.identity,field.identity)
        self.sql('UPDATE "'+table+'" SET "'+column+'"=?',(str(uuid4()),))
        with closing(self.backend.begin_read()) as view:
            with self.assertRaises(BackendError):view.read_catalog(c.key)

    def test_close_clears_domain(self):
        self.backend.close();self.assertIsNone(self.backend._enum_domain)

    def test_enum_ordering_not_implicitly_granted(self):
        self.seed();field=next(f for f in self.products.fields if f.kind=='enum_ref')
        with closing(self.backend.begin_read()) as view:
            with self.assertRaises(BackendError):
                view.scan_catalog(self.products.identity,CatalogScanRequest(order=(CatalogOrder(field.identity),)))

    def test_repair_after_failed_source_admission(self):
        old=self.sql("SELECT sha256 FROM configuration_file WHERE path='Configuration.xml'")[0][0]
        self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'",('0'*64,))
        with self.assertRaises(BackendError):self.backend.begin_read()
        self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'",(old,))
        with closing(self.backend.begin_read()) as view:self.assertEqual(len(view.catalogs()),2)

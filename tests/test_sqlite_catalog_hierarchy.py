"""Owned hierarchy storage contracts; not native hierarchy parity evidence."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import (BackendError, CatalogSchema, CatalogKey,
    CatalogDraft, CatalogScanRequest, CatalogComparison, CatalogOrder,
    CatalogWriteRequest, FieldSchema, TabularSectionSchema, TabularSectionRows, TabularRow)
from yadinassi.configuration_xml import ConfigurationImport, ConfigurationFile
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _schema, _schema_data, _json, _View
from yadinassi.document_backend import DocumentSchema, DocumentKey, DocumentDraft
from yadinassi.register_backend import InformationRegisterSchema, RegisterKey, RegisterDraft
from test_catalog_commit_cleanup_recovery import FaultConnection


def configuration(*, mixed=False, numbered=False):
    folder = CatalogSchema(uuid4(), 'Products', 8, 64,
        tabular_sections=(TabularSectionSchema(uuid4(),'Lines',(FieldSchema(uuid4(),'Text','string',(32,)),)),),
        numbering='decimal_v1' if numbered else 'explicit', hierarchy='groups_v1')
    flat = CatalogSchema(uuid4(), 'Flat', 8, 64)
    docs = (DocumentSchema(uuid4(),'Orders',8),) if mixed else ()
    registers = (InformationRegisterSchema(uuid4(),'Prices',(FieldSchema(uuid4(),'Item','string',(16,)),),
                    (FieldSchema(uuid4(),'Price','number',(8,2,'Any')),),periodicity='Day'),) if mixed else ()
    return ConfigurationImport(config_uuid=uuid4(),name='OwnedHierarchy',catalogs=(folder,flat),
        documents=docs,information_registers=registers,activation_issues=(),modules=(),
        files=(ConfigurationFile(path='Configuration.xml',content=b'<owned/>',kind='xml'),))


class SQLiteHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'hierarchy.sqlite'
        self.config=configuration();self.schema,self.flat=self.config.catalogs
        self.backend=SQLiteCatalogBackend.create(self.path,self.config)
        self.addCleanup(lambda:self.backend.close())

    def draft(self,*,folder=False,parent=None,schema=None,code=None,auto=False,sections=None):
        schema=schema or self.schema
        return CatalogDraft(CatalogKey(self.backend.database_id,schema.identity,uuid4()),
            code if code is not None else uuid4().hex[:8],'item',False,(),sections,
            auto_number=auto,parent=parent,is_folder=folder)

    def save(self,draft,expected=None,operation=None):
        view=self.backend.begin_write(operation or uuid4())
        try:
            if expected is None:view.create(draft)
            else:view.update(draft,expected)
            return view.commit_outcomes()[0]
        finally:view.close()

    def read(self,key):
        view=self.backend.begin_read()
        try:return view.read_catalog(key)
        finally:view.close()

    def sql(self,statement,args=()):
        with closing(sqlite3.connect(self.path)) as connection,connection:
            return connection.execute(statement,args).fetchall()

    def test_v10_separate_table_and_reopen(self):
        root=self.draft(folder=True);self.save(root)
        item=self.draft(parent=root.key);self.save(item)
        self.assertEqual(self.backend.storage_version,10)
        table=self.backend._layout.table_name(self.schema.identity)
        self.assertNotIn('parent_id',[row[1] for row in self.sql('PRAGMA table_info("%s")'%table)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM catalog_hierarchy'),[(2,)])
        self.backend.close();self.backend=SQLiteCatalogBackend(self.path)
        self.assertEqual(self.read(item.key).parent,root.key)
        self.assertTrue(self.read(root.key).is_folder)

    def test_schema_legacy_exact_and_closed_profile(self):
        definition=_schema_data(self.flat)
        self.assertEqual(len(definition),5)
        self.assertEqual(_schema(_json(definition)),self.flat)
        hierarchical=_schema_data(self.schema)
        self.assertEqual(hierarchical[-1],['hierarchy_v1','groups_v1'])
        with self.assertRaisesRegex(BackendError,'unsupported'):_schema(_json(hierarchical),allow_numbering=True)
        self.assertEqual(_schema(_json(hierarchical),allow_numbering=True,allow_hierarchy=True),self.schema)
        with self.assertRaisesRegex(BackendError,'invalid_input'):_schema_data(replace(self.schema,hierarchy='unsupported'))

    def test_flat_schema_database_stays_v2_and_inputs_refuse(self):
        p=Path(self.temp.name)/'flat.sqlite'; config=replace(self.config,catalogs=(self.flat,))
        b=SQLiteCatalogBackend.create(p,config)
        try:
            self.assertEqual(b.storage_version,2)
            with closing(sqlite3.connect(p)) as conn:
                self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='catalog_hierarchy'").fetchone())
            d=CatalogDraft(CatalogKey(b.database_id,self.flat.identity,uuid4()),'a','a',False,(),is_folder=True)
            v=b.begin_write(uuid4())
            try:
                with self.assertRaisesRegex(BackendError,'invalid_input'):v.create(d)
            finally:v.close()
        finally:b.close()

    def test_flat_catalog_in_v10_keeps_default_fields(self):
        draft=self.draft(schema=self.flat);self.save(draft)
        card=self.read(draft.key);self.assertIsNone(card.parent);self.assertFalse(card.is_folder)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM catalog_hierarchy'),[(0,)])
        with self.assertRaisesRegex(BackendError,'invalid_input'):self.save(self.draft(schema=self.flat,folder=True))

    def test_root_projection_is_typed_empty_reference(self):
        root=self.draft(folder=True);self.save(root)
        view=self.backend.begin_read()
        try:
            page=view.scan_catalog_values(self.schema.identity,CatalogScanRequest(),('ref','parent','is_folder'))
            self.assertEqual(page.rows[0].values,(root.key,CatalogKey(self.backend.database_id,self.schema.identity,UUID(int=0)),True))
        finally:view.close()

    def test_projected_filtered_ordered_pages(self):
        root=self.draft(folder=True);self.save(root)
        children=[self.draft(parent=root.key,code=code) for code in ('B','A')]
        for child in children:self.save(child)
        view=self.backend.begin_read()
        try:
            request=CatalogScanRequest(CatalogComparison('parent','eq',root.key),(CatalogOrder('code'),),1)
            first=view.scan_catalog_values(self.schema.identity,request,('code','parent','is_folder'))
            second=view.scan_catalog_values(self.schema.identity,replace(request,continuation=first.continuation),('code','parent','is_folder'))
            self.assertEqual(first.rows[0].values,('A',root.key,False));self.assertEqual(second.rows[0].values,('B',root.key,False))
            self.assertIsNone(second.continuation)
        finally:view.close()

    def test_nonfolder_missing_foreign_parent_refuse(self):
        item=self.draft();self.save(item)
        bad=[item.key,CatalogKey(self.backend.database_id,self.schema.identity,uuid4()),
             CatalogKey(uuid4(),self.schema.identity,uuid4()),CatalogKey(self.backend.database_id,self.flat.identity,uuid4()),
             CatalogKey(self.backend.database_id,self.schema.identity,UUID(int=0))]
        for parent in bad:
            with self.subTest(parent=parent),self.assertRaises(BackendError):self.save(self.draft(parent=parent))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM catalog_hierarchy'),[(1,)])

    def test_kind_is_immutable_and_stale_revision_conflicts(self):
        root=self.draft(folder=True);rev=self.save(root).revision
        with self.assertRaisesRegex(BackendError,'invalid_input'):self.save(replace(root,is_folder=False),rev)
        changed=replace(root,description='changed');self.save(changed,rev)
        with self.assertRaisesRegex(BackendError,'conflict'):self.save(root,rev)
        self.assertEqual(self.read(root.key).description,'changed')

    def test_move_and_root_detach_preserve_kind_and_sections(self):
        a=self.draft(folder=True);b=self.draft(folder=True);self.save(a);self.save(b)
        section=TabularSectionRows(self.schema.tabular_sections[0].identity,(TabularRow(uuid4(),('payload',)),))
        child=self.draft(parent=a.key,sections=(section,));rev=self.save(child).revision
        moved=replace(child,parent=b.key,tabular_sections=None);rev=self.save(moved,rev).revision
        self.assertEqual(self.read(child.key).parent,b.key);self.assertEqual(self.read(child.key).tabular_sections,(section,))
        self.save(replace(moved,parent=None),rev)
        self.assertIsNone(self.read(child.key).parent)

    def test_self_parent_and_cycle_rejected_atomically(self):
        root=self.draft(folder=True);r=self.save(root).revision
        child=self.draft(folder=True,parent=root.key);self.save(child)
        for parent in (root.key,child.key):
            with self.subTest(parent=parent),self.assertRaisesRegex(BackendError,'invalid_input'):self.save(replace(root,parent=parent),r)
        self.assertIsNone(self.read(root.key).parent)
        self.assertEqual(self.read(root.key).revision,r)

    def test_depth_limit_includes_moved_descendants(self):
        chain=[];parent=None
        tx=self.backend.begin_write(uuid4())
        try:
            for unused in range(32):
                d=self.draft(folder=True,parent=parent);tx.create(d);chain.append(d);parent=d.key
            with self.assertRaisesRegex(BackendError,'invalid_input'):tx.create(self.draft(parent=parent))
            tx.commit()
        finally:tx.close()
        extra=self.draft(folder=True);self.save(extra)
        card=self.read(chain[0].key)
        with self.assertRaisesRegex(BackendError,'invalid_input'):self.save(replace(chain[0],parent=extra.key),card.revision)
        self.assertIsNone(self.read(chain[0].key).parent)

    def test_multiple_operations_in_one_view_see_current_graph(self):
        a=self.draft(folder=True);b=self.draft(parent=a.key)
        tx=self.backend.begin_write(uuid4())
        try:
            tx.create(a);tx.create(b)
            self.assertEqual(tx.read_catalog(b.key).parent,a.key)
            tx.update(replace(b,parent=None),tx.read_catalog(b.key).revision)
            self.assertIsNone(tx.read_catalog(b.key).parent)
            tx.commit()
        finally:tx.close()
        self.assertIsNone(self.read(b.key).parent)

    def test_savepoint_failure_preserves_prior_work_and_graph(self):
        a=self.draft(folder=True);b=self.draft(parent=a.key)
        tx=self.backend.begin_write(uuid4())
        try:
            tx.create(a)
            with patch.object(_View,'_record_change',side_effect=MemoryError):
                with self.assertRaises(MemoryError):tx.create(b)
            self.assertIsNone(tx.read_catalog(b.key))
            tx.create(b);tx.commit()
        finally:tx.close()
        self.assertEqual(self.read(b.key).parent,a.key)

    def test_rollback_restores_parent_and_revision(self):
        a=self.draft(folder=True);b=self.draft(folder=True);self.save(a);self.save(b)
        item=self.draft(parent=a.key);rev=self.save(item).revision
        tx=self.backend.begin_write(uuid4())
        try:
            tx.update(replace(item,parent=b.key),rev);tx.rollback()
        finally:tx.close()
        self.assertEqual(self.read(item.key).parent,a.key);self.assertEqual(self.read(item.key).revision,rev)

    def test_receipt_binds_parent_and_kind(self):
        root=self.draft(folder=True);self.save(root)
        operation=uuid4();draft=self.draft(parent=root.key);outcome=self.save(draft,operation=operation)
        self.assertEqual(self.backend.resolve_write_outcome(operation,draft),outcome)
        for changed in (replace(draft,parent=None),replace(draft,is_folder=True)):
            with self.subTest(changed=changed),self.assertRaisesRegex(BackendError,'conflict'):
                self.backend.resolve_write_outcome(operation,changed)

    def test_uncertain_commit_recovers_exact_parent_intent(self):
        root=self.draft(folder=True);self.save(root)
        operation=uuid4();draft=self.draft(parent=root.key)
        tx=self.backend.begin_write(operation)
        try:
            tx.create(draft);tx._connection=FaultConnection(tx._connection,commit_fault='after')
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):tx.commit()
        finally:tx.close()
        self.assertIsNotNone(self.backend.resolve_write_outcome(operation,draft))
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.resolve_write_outcome(operation,replace(draft,parent=None))
        self.assertEqual(self.read(draft.key).parent,root.key)

    def test_batch_receipts_bind_each_ordered_hierarchy_intent(self):
        op=uuid4();a=self.draft(folder=True);b=self.draft(parent=a.key)
        tx=self.backend.begin_write(op)
        try:tx.create(a);tx.create(b);outcomes=tx.commit_outcomes()
        finally:tx.close()
        requests=(CatalogWriteRequest(a),CatalogWriteRequest(b))
        self.assertEqual(self.backend.resolve_write_outcomes(op,requests),outcomes)
        with self.assertRaisesRegex(BackendError,'conflict'):
            self.backend.resolve_write_outcomes(op,(requests[0],CatalogWriteRequest(replace(b,parent=None))))

    def test_read_only_refuses_writes_but_reads_hierarchy(self):
        root=self.draft(folder=True);self.save(root);self.backend.close()
        self.backend=SQLiteCatalogBackend(self.path,read_only=True)
        self.assertTrue(self.read(root.key).is_folder)
        with self.assertRaises(BackendError):self.backend.begin_write(uuid4())

    def test_corruption_missing_or_orphan_rows_refuses_before_filtered_page(self):
        root=self.draft(folder=True);self.save(root)
        self.sql('DELETE FROM catalog_hierarchy WHERE record_id=?',(str(root.key.record_id),))
        v=self.backend.begin_read()
        try:
            with self.assertRaisesRegex(BackendError,'integrity'):
                v.scan_catalog_values(self.schema.identity,CatalogScanRequest(CatalogComparison('code','eq','absent')),('code',))
        finally:v.close()

    def test_corruption_cycle_folder_flag_and_depth_refuse(self):
        root=self.draft(folder=True);self.save(root)
        for parent,kind in ((str(root.key.record_id),1),(None,2)):
            self.sql('UPDATE catalog_hierarchy SET parent_id=?,is_folder=?',(parent,kind))
            with self.assertRaisesRegex(BackendError,'integrity'):self.read(root.key)
        self.sql('UPDATE catalog_hierarchy SET parent_id=NULL,is_folder=1')
        self.assertTrue(self.read(root.key).is_folder)

    def test_unknown_catalog_hierarchy_rows_fail_admission(self):
        self.sql('INSERT INTO catalog_hierarchy VALUES(?,?,NULL,1)',(str(uuid4()),str(uuid4())))
        self.backend.close()
        with self.assertRaisesRegex(BackendError,'integrity'):SQLiteCatalogBackend(self.path)

    def test_v10_header_cannot_be_downgraded_to_v9(self):
        self.backend.close();self.sql('PRAGMA user_version=9')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)

    def test_numbering_and_hierarchy_rollback_share_savepoint(self):
        path=Path(self.temp.name)/'numbered.sqlite';config=configuration(numbered=True)
        b=SQLiteCatalogBackend.create(path,config)
        try:
            schema=config.catalogs[0];d=CatalogDraft(CatalogKey(b.database_id,schema.identity,uuid4()),'', 'folder',False,(),auto_number=True,is_folder=True)
            tx=b.begin_write(uuid4())
            try:
                with patch.object(_View,'_record_change',side_effect=MemoryError):
                    with self.assertRaises(MemoryError):tx.create(d)
                tx.create(d);outcome=tx.commit_outcomes()[0]
            finally:tx.close()
            self.assertEqual(outcome.code,'00000001')
        finally:b.close()

    def test_mixed_documents_and_periodic_registers_keep_v9_ports(self):
        path=Path(self.temp.name)/'mixed.sqlite';config=configuration(mixed=True)
        b=SQLiteCatalogBackend.create(path,config)
        try:
            self.assertEqual(b.storage_version,10)
            doc=DocumentDraft(DocumentKey(b.database_id,config.documents[0].identity,uuid4()),'A',datetime(2026,1,1),False,())
            tx=b.begin_document_write(uuid4())
            try:tx.create(doc);tx.commit()
            finally:tx.close()
            reg=config.information_registers[0]
            row=RegisterDraft(RegisterKey(b.database_id,reg.identity,(datetime(2026,1,1),'A')),(Decimal('2.50'),))
            tx=b.begin_register_write(uuid4())
            try:tx.write(row);tx.commit()
            finally:tx.close()
            view=b.begin_document_read()
            try:
                self.assertEqual(view.read_document(doc.key).number,'A')
                self.assertEqual(view.registers(),(reg,))
            finally:view.close()
        finally:b.close()

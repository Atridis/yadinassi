"""Сквозные страницы списков: реальные backend/replicas, не browser evidence."""
from contextlib import closing
from uuid import uuid4
import unittest
import test_configuration_inventory_app as helpers
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import CatalogDraft,CatalogKey

class ConfigurationRecordPagesTests(unittest.TestCase):
    setUp=helpers.InventoryApplicationTests.setUp
    rpc=helpers.InventoryApplicationTests.rpc
    open=helpers.InventoryApplicationTests.open
    event=helpers.InventoryApplicationTests.event
    def seed(self,count,prefix='X'):
        with closing(SQLiteDBContext(self.path)) as context:
            schema=next(s for s in self.config.catalogs if s.name=='Warehouses')
            with closing(context.backend.begin_write(uuid4())) as view:
                for n in range(count):
                    view.create(CatalogDraft(CatalogKey(context.backend.database_id,schema.identity,uuid4()),
                        prefix+str(n).zfill(4),prefix+' warehouse '+str(n),False,(),()))
                view.commit()
    def listing(self):
        entry=self.app.names['catalog.warehouses.form.card']
        return self.rpc('catalog',entry=entry)['state']['catalog']
    def next_page(self,catalog):
        return self.rpc('catalogPage',entry=catalog['entry'],snapshot=catalog['navigation']['snapshot'],
            cursor=catalog['navigation']['next'])['state']['catalog']
    def test_large_list_pages_revoke_old_keys_without_reuse(self):
        self.seed(260);first=self.listing();self.assertEqual(first['navigation']['total'],261)
        self.assertEqual(len(first['rows']),50)
        second=self.next_page(first);self.assertEqual(second['navigation']['page'],2)
        self.assertEqual(len(self.broker.records),50)
        self.assertFalse(set(r['key'] for r in first['rows'])&set(r['key'] for r in second['rows']))
        denied=self.broker.exchange({'operation':'create','session':'','payload':{'entry':first['entry'],
            'parameters':{},'record':first['rows'][0]['key']}})
        self.assertEqual(denied,{'error':'invalid_record'})
    def test_saved_second_page_refresh_preserves_other_draft(self):
        self.seed(60);second=self.next_page(self.listing());record=second['rows'][0]['key']
        sid=self.open('Catalog.Warehouses.Form.Card',record=record,request='edit-page2')
        other=self.open('Catalog.Products.Form.Card',request='retained-draft')
        self.event(other,'change',control='DescriptionInput',value='unsaved draft')
        self.event(sid,'change',control='DescriptionInput',value='updated second-page warehouse')
        self.event(sid,control='SaveButton')
        self.assertFalse(self.broker.objects[sid].pending_refresh)
        self.assertEqual(self.app.catalog['navigation']['page'],2)
        self.assertTrue(any(r['description']=='updated second-page warehouse' for r in self.app.catalog['rows']))
        self.assertIn(other,self.app.sessions)
        self.assertIn('unsaved draft',str(self.app.sessions[other][0]._snapshot()))
    def test_search_snapshot_is_stable_until_explicit_refresh(self):
        self.seed(60);first=self.listing();nav=first['navigation']
        filtered=self.rpc('catalogFilter',entry=first['entry'],snapshot=nav['snapshot'],query='X warehouse 5',order='description')['state']['catalog']
        self.assertEqual(filtered['navigation']['total'],11)
        self.seed(1,prefix='X warehouse 5')
        self.assertEqual(self.app.catalog['navigation']['total'],11)
        refreshed=self.listing();self.assertEqual(refreshed['navigation']['total'],12)
        self.assertEqual(refreshed['navigation']['query'],'X warehouse 5')
    def test_retired_page_cursor_is_bounded_refusal(self):
        self.seed(60);first=self.listing();self.next_page(first)
        answer=self.broker.exchange({'operation':'catalogPage','session':'','payload':{'entry':first['entry'],
            'snapshot':first['navigation']['snapshot'],'cursor':first['navigation']['next']}})
        self.assertEqual(answer,{'error':'catalog_unavailable'})
    def test_document_pages_search_and_open_use_current_storage(self):
        from datetime import datetime
        from yadinassi.document_backend import DocumentDraft,DocumentKey
        from uuid import UUID
        with closing(SQLiteDBContext(self.path)) as context:
            schema=next(s for s in self.config.documents if s.name=='Receipt')
            values=tuple(CatalogKey(context.backend.database_id,f.target_catalog_id,UUID(int=0)) for f in schema.fields)
            for n in range(51):
                with closing(context.backend.begin_document_write(uuid4())) as view:
                    view.create(DocumentDraft(DocumentKey(context.backend.database_id,schema.identity,uuid4()),
                        'R'+str(n).zfill(4),datetime(2024,1,1),False,values,()))
                    view.commit()
        entry=self.app.names['document.receipt.form.card']
        first=self.rpc('catalog',entry=entry)['state']['catalog'];self.assertEqual(first['navigation']['total'],51)
        page=self.next_page(first);self.assertEqual(page['navigation']['page'],2);self.assertEqual(len(page['rows']),1)
        sid=self.open('Document.Receipt.Form.Card',record=page['rows'][0]['key'],request='document-page2')
        self.assertEqual(self.broker.objects[sid].object.get_member('Number'),'R0050')
        filtered=self.rpc('catalogFilter',entry=entry,snapshot=page['navigation']['snapshot'],query='R000',order='number')['state']['catalog']
        self.assertEqual(filtered['navigation']['total'],10)

    def test_external_delete_before_open_is_safe_refusal(self):
        import sqlite3
        from yadinassi.sqlite_catalog import quote_identifier
        self.seed(1);listing=self.listing()
        row=next(r for r in listing['rows'] if r['code']=='X0000')
        with closing(SQLiteDBContext(self.path)) as context:
            schema=next(s for s in self.config.catalogs if s.name=='Warehouses')
            table=quote_identifier(context.backend._layout.table_name(schema.identity))
        # A separate writer edits only this test's freshly generated database.
        from yadinassi.sqlite_query_indexes import register_query_collations
        with sqlite3.connect(self.path) as writer:
            register_query_collations(writer)
            writer.execute('DELETE FROM '+table+' WHERE code=?',('X0000',))
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.openRecord',
            'params':{'entry':listing['entry'],'record':row['key'],'request':'deleted-record'}})['result']
        self.assertEqual(result['error'],'invalid_record')
        self.assertIsNone(result['session']);self.assertFalse(self.app.uncertain)

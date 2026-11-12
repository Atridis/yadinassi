"""Проверки detached списков: без браузера и без длительного read lease."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from inventory_enum_application_fixture import source
from yadinassi.configuration_inventory_enum_application import import_inventory_application, PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.ui.record_pages import RecordPages, load_record_snapshot, RecordRow, validate_navigation


class RecordPagesTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.files=source(); config=import_inventory_application(self.files,inventory_runtime=PROFILE)
        self.context=SQLiteDBContext.create_inventory_enum_application(Path(tmp.name)/'db.sqlite',config)
        self.addCleanup(self.context.close)
        self.schema=next(s for s in config.catalogs if s.name=='Warehouses')
        self.doc=next(s for s in config.documents if s.name=='Receipt')
        self.pages=RecordPages(self.files)

    def seed(self,count):
        with closing(self.context.backend.begin_write(uuid4())) as view:
            for n in range(count):
                view.create(CatalogDraft(CatalogKey(self.context.backend.database_id,self.schema.identity,uuid4()),
                    str(n).zfill(4), 'Warehouse '+str(n),False,(),()))
            view.commit()

    def capture(self,**kwargs):
        return self.pages.capture(self.context,1,catalog_schema=self.schema,**kwargs)

    def test_empty_catalog_and_document_pages(self):
        page=self.capture()
        self.assertEqual((page.page,page.pages,page.total,page.rows),(1,1,0,()))
        page=self.pages.capture(self.context,2,document_schema=self.doc)
        self.assertEqual(page.order,'date');self.assertEqual(page.rows,())
        self.assertIsNone(self.context.backend._active)

    def test_more_than_256_records_and_single_use_navigation(self):
        self.seed(257);page=self.capture()
        self.assertEqual((len(page.rows),page.total,page.pages),(50,257,6))
        validate_navigation(page.navigation,document=False,row_count=len(page.rows))
        for patch_values in ({'page':True},{'total':8193},{'next':None},{'query':False},{'extra':0}):
            with self.assertRaises(BackendError):
                validate_navigation(dict(page.navigation,**patch_values),document=False,row_count=len(page.rows))
        old=page
        page=self.pages.navigate(self.context,page.snapshot,page.next)
        self.assertEqual(page.page,2)
        with self.assertRaises(BackendError):self.pages.navigate(self.context,old.snapshot,old.next)
        page=self.pages.navigate(self.context,page.snapshot,page.previous)
        self.assertEqual(page.rows,old.rows)
        self.assertLessEqual(len(self.pages._tokens),2)

    def test_filter_sort_and_snapshot_retirement(self):
        self.seed(51);old=self.capture()
        page=self.pages.filter(self.context,query='WAREHOUSE 5',order='description')
        self.assertEqual(page.total,2)
        self.assertEqual([r.values[1] for r in page.rows],['Warehouse 5','Warehouse 50'])
        with self.assertRaises(BackendError):self.pages.navigate(self.context,old.snapshot,old.next)

    def test_read_lease_closed_and_refresh_sees_new_writes(self):
        self.seed(1);first=self.capture()
        self.assertIsNone(self.context.backend._active)
        with closing(self.context.backend.begin_write(uuid4())) as view:
            view.create(CatalogDraft(CatalogKey(self.context.backend.database_id,self.schema.identity,uuid4()),
                'NEW','New warehouse',False,(),()))
            view.commit()
        self.assertEqual(first.total,1)
        self.assertEqual(self.capture().total,2)

    def test_overflow_has_no_partial_result_and_closes_lease(self):
        self.seed(51)
        with patch('yadinassi.ui.record_pages.MAX_RECORDS',50):
            with self.assertRaises(BackendError):self.capture()
        self.assertIsNone(self.context.backend._active)
        self.assertIsNone(self.pages._snapshot)

    def test_text_budget_and_changed_source_are_refused(self):
        self.seed(1)
        with patch('yadinassi.ui.record_pages.MAX_BYTES',1):
            with self.assertRaises(BackendError):self.capture()
        wrong=dict(self.files);wrong['Configuration.xml']+=b'\n'
        with self.assertRaises(BackendError):load_record_snapshot(self.context.backend,self.schema,source_files=wrong)
        self.assertIsNone(self.context.backend._active)

    def test_source_change_invalidates_navigation(self):
        self.seed(51);page=self.capture()
        with patch.object(self.context.backend,'export_configuration',return_value={}):
            with self.assertRaises(BackendError):self.pages.navigate(self.context,page.snapshot,page.next)
        self.assertIsNone(self.pages._snapshot)

    def test_foreign_typed_row_and_invalid_query_are_refused(self):
        snap=load_record_snapshot(self.context.backend,self.schema,source_files=self.files)
        key=CatalogKey(uuid4(),self.schema.identity,uuid4())
        with self.assertRaises(BackendError):self.pages.replace(replace(snap,rows=(RecordRow(key,('A','B',False)),)),entry=1)
        with self.assertRaises(BackendError):self.capture(query='x'*129)
        with self.assertRaises(BackendError):self.capture(order='sql')

    def test_requested_page_clamps_and_clear_retires_tokens(self):
        self.seed(51);page=self.capture(page=99)
        self.assertEqual((page.page,len(page.rows)),(2,1))
        self.pages.clear()
        with self.assertRaises(BackendError):self.pages.navigate(self.context,page.snapshot,page.previous)

    def test_failed_view_close_never_publishes_snapshot(self):
        self.seed(1)
        original=self.context.backend.begin_read
        def opening():
            view=original();close=view.close
            def failed_close():
                close();raise BackendError('integrity')
            view.close=failed_close
            return view
        with patch.object(self.context.backend,'begin_read',opening):
            with self.assertRaises(BackendError):self.capture()
        self.assertIsNone(self.pages._snapshot)
        self.assertIsNone(self.context.backend._active)

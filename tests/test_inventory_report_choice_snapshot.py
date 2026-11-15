"""Полные admitted report-choice snapshots; без UI и расширения grants."""
from contextlib import closing
from dataclasses import replace, FrozenInstanceError
from datetime import datetime
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_inventory_application_reports as support
from yadinassi.catalog_backend import CatalogDraft, CatalogKey, CatalogValuePage, BackendError
from yadinassi.inventory_application_reports import InventoryReportChoiceSnapshot, InventoryReportFilter, UNAVAILABLE
from yadinassi.sqlite_catalog import _View

MODULE='yadinassi.inventory_application_reports.'

class ChoiceSnapshotTests(unittest.TestCase):
    setUp=support.InventoryReportTests.setUp
    catalog=support.InventoryReportTests.catalog
    sql=support.InventoryReportTests.sql

    def capture(self, code=''):
        return self.service.choice_snapshot('StockStatement','Product',code)

    def test_empty_frozen_bound_and_released(self):
        result=self.capture()
        self.assertIs(type(result),InventoryReportChoiceSnapshot)
        self.assertEqual((result.rows,result.error),((),None))
        self.assertEqual(result.source_digest,self.config.source_digest)
        self.assertEqual((result.database_id,result.configuration_generation),self.service._binding)
        self.assertIsNone(self.backend._active)
        with self.assertRaises(FrozenInstanceError):result.rows=()

    def test_full_multi_page_standard_projection_and_legacy_limit(self):
        with closing(self.backend.begin_write(uuid4())) as owner:
            for i in range(257):
                owner.create(CatalogDraft(CatalogKey(self.backend.database_id,self.catalogs['Products'].identity,uuid4()),f'P{i:03}','Item',False,()))
            owner.commit()
        original=_View.scan_catalog_values
        with patch.object(_View,'scan_catalog_values',autospec=True,side_effect=original) as scan:
            result=self.capture()
        self.assertEqual(len(result.rows),257)
        self.assertEqual(scan.call_count,2)
        self.assertTrue(all(c.args[3]==('code','description','deletion_mark') for c in scan.call_args_list))
        self.assertIsNone(self.backend._active)
        self.assertEqual(self.service.choices('StockStatement','Product').error,'too_many_matches')

    def test_budget_overflow_has_no_partial_and_exact_recovers(self):
        self.catalog('Products','P1','é');self.catalog('Products','P2','other')
        with patch(MODULE+'MAX_CHOICE_SNAPSHOT_ROWS',1):
            result=self.capture();self.assertEqual((result.rows,result.error),((),'snapshot_limit'))
            self.assertEqual(len(self.capture('P1').rows),1)
        with patch(MODULE+'MAX_CHOICE_SNAPSHOT_BYTES',66):
            self.assertEqual(self.capture('P1').error,'snapshot_limit')
        self.assertIsNone(self.backend._active)

    def test_deleted_choices_excluded_historical_filter_preserved(self):
        key=self.catalog('Products','P1','Old')
        first=self.capture()
        with closing(self.backend.begin_read()) as owner: card=owner.read_catalog(key)
        with closing(self.backend.begin_write(uuid4())) as owner:
            owner.update(CatalogDraft(key,card.code,card.description,True,card.values,card.tabular_sections),card.revision);owner.commit()
        self.assertEqual(self.capture().rows,())
        selected=InventoryReportFilter(first.dimension_id,key,first.configuration_generation)
        result=self.service.read('StockStatement',start=datetime(2024,1,1),end=datetime(2024,12,31),periodicity='None',filters=(selected,))
        self.assertIn((key,UNAVAILABLE),result.labels)

    def test_wrong_report_dimension_input_and_unicode_denied(self):
        for args in [('StockMovements','Product',''),('StockStatement','Missing',''),('StockStatement','Product','\ud800'),('StockStatement','Product',False)]:
            with self.assertRaises(BackendError):self.service.choice_snapshot(*args)
        self.assertIsNone(self.backend._active)

    def test_bad_rows_and_cursor_refused_lease_closed(self):
        self.catalog('Products','P1','Item')
        original=_View.scan_catalog_values
        for mode in ('foreign','deleted','duplicate','cursor'):
            def scan(owner,*args):
                page=original(owner,*args);row=page.rows[0]
                if mode=='foreign': return replace(page,rows=(replace(row,key=replace(row.key,database_id=uuid4())),))
                if mode=='deleted': return replace(page,rows=(replace(row,values=('P1','Item',True)),))
                if mode=='duplicate': return replace(page,rows=(row,row))
                return replace(page,continuation='bad')
            with patch.object(_View,'scan_catalog_values',scan):
                with self.assertRaises(BackendError):self.capture()
            self.assertIsNone(self.backend._active)

    def test_source_content_mutation_refused(self):
        path=next(path for path, _ in self.config.files if path.endswith('.bsl'))
        raw=b'// changed source\n'
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',(raw,sha256(raw).hexdigest(),path))
        with self.assertRaises(BackendError):self.capture()
        self.assertIsNone(self.backend._active)

    def test_same_lease_schema_rechecked_after_scan(self):
        self.catalog('Products','P1','Item')
        original=_View.catalog_schema
        calls=0
        def schema(owner,identity):
            nonlocal calls
            calls+=1
            value=original(owner,identity)
            return replace(value,name='Changed') if calls>1 else value
        with patch.object(_View,'catalog_schema',schema):
            with self.assertRaises(BackendError):self.capture()
        self.assertIsNone(self.backend._active)

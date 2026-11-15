"""Closed detached record-list predicates, not database query or write authority."""
from datetime import datetime
from uuid import uuid4
import unittest

from yadinassi.catalog_backend import BackendError, CatalogKey
from yadinassi.document_backend import DocumentKey
from yadinassi.ui.record_pages import (RecordPages, RecordSnapshot, RecordRow,
    DEFAULT_FILTERS, FILTER_NAMES, record_filters, validate_navigation)


def filters(**changes):
    return dict(zip(FILTER_NAMES, DEFAULT_FILTERS), **{}) | changes


class RecordFilterTests(unittest.TestCase):
    def setUp(self):
        self.pages = RecordPages({'Configuration.xml': b'<root/>'})
        self.db, self.schema = uuid4(), uuid4()
        self.rows = tuple(RecordRow(DocumentKey(self.db, self.schema, uuid4()),
            (str(n), datetime(2024, 2, day, hour), marked, posted))
            for n, day, hour, marked, posted in ((1,28,0,False,False),(2,29,0,False,True),
                                               (3,29,23,True,True)))
        self.snapshot = RecordSnapshot(self.db,1,'a'*64,self.schema,True,self.rows)

    def test_inclusive_calendar_range_and_status_intersection(self):
        page=self.pages.replace(self.snapshot,entry=1,filters=filters(dateFrom='2024-02-29',
            dateTo='2024-02-29',posting='posted',deletion='unmarked'))
        self.assertEqual(page.rows,(self.rows[1],));self.assertEqual(page.total,1)
        validate_navigation(page.navigation,document=True,row_count=1)

    def test_end_date_includes_final_second_without_overflow(self):
        row=RecordRow(DocumentKey(self.db,self.schema,uuid4()),('9',datetime.max.replace(microsecond=0),False,False))
        from dataclasses import replace
        page=self.pages.replace(replace(self.snapshot,rows=(row,)),entry=1,
                                filters=filters(dateTo='9999-12-31'))
        self.assertEqual(page.rows,(row,))

    def test_descending_is_stable_and_reset_restores_defaults(self):
        page=self.pages.replace(self.snapshot,entry=1,filters=filters(descending=True))
        self.assertEqual(page.rows,tuple(reversed(self.rows)))
        self.assertTrue(page.navigation['filters']['descending'])
        page=self.pages.replace(self.snapshot,entry=1)
        self.assertEqual(page.rows,self.rows);self.assertNotIn('filters',page.navigation)

    def test_catalog_only_deletion_and_direction_are_allowed(self):
        rows=(RecordRow(CatalogKey(self.db,self.schema,uuid4()),('A','Alpha',True)),
              RecordRow(CatalogKey(self.db,self.schema,uuid4()),('B','Beta',False)))
        snap=RecordSnapshot(self.db,1,'a'*64,self.schema,False,rows)
        page=self.pages.replace(snap,entry=1,filters=filters(deletion='marked',descending=True))
        self.assertEqual(page.rows,(rows[0],))
        for value in (filters(posting='posted'),filters(dateFrom='2024-01-01'),filters(dateTo='2024-01-01')):
            with self.assertRaises(BackendError):self.pages.replace(snap,entry=1,filters=value)

    def test_strict_shapes_dates_and_types(self):
        values=[{},[],filters(extra=1),filters(deletion=True),filters(posting=0),filters(descending=1),
            filters(dateFrom='2023-02-29'),filters(dateTo='2024-2-01'),filters(dateFrom='0000-01-01'),
            filters(dateFrom='2024-03-01',dateTo='2024-02-29'),filters(dateFrom=None)]
        for value in values:
            with self.subTest(value=value),self.assertRaises(BackendError):record_filters(value,document=True)

    def test_failed_filter_does_not_retire_previous_snapshot(self):
        first=self.pages.replace(self.snapshot,entry=1)
        with self.assertRaises(BackendError):self.pages.replace(self.snapshot,entry=1,filters=filters(dateTo='bad'))
        self.assertEqual(self.pages._token,first.snapshot)
        self.assertEqual(self.pages._rows,first.rows)

    def test_query_and_filters_share_one_honest_total(self):
        page=self.pages.replace(self.snapshot,entry=1,query='3',filters=filters(posting='unposted'))
        self.assertEqual((page.total,page.pages,page.rows),(0,1,()))

    def test_navigation_rejects_noncanonical_or_foreign_filter_values(self):
        first=self.pages.replace(self.snapshot,entry=1)
        for value in (None, filters(),filters(dateFrom='bad'),filters(unknown=0)):
            with self.subTest(value=value),self.assertRaises(BackendError):
                validate_navigation(dict(first.navigation,filters=value),document=True,row_count=3)

    def test_filter_dict_is_detached_from_caller_and_projection(self):
        value=filters(deletion='marked')
        page=self.pages.replace(self.snapshot,entry=1,filters=value)
        value['deletion']='unmarked';page.navigation['filters']['deletion']='unmarked'
        self.assertEqual(page.navigation['filters']['deletion'],'marked')

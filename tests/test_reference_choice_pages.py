"""Detached picker navigation preserves owner fencing and opaque capabilities."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import unittest
import test_configuration_reference_choice as base
from yadinassi.catalog_backend import CatalogKey,CatalogValueRow,CatalogValuePage,BackendError
from yadinassi.reference_choice_pages import load_choices,SnapshotLimit


class ReferencePageTests(unittest.TestCase):
    def setUp(self):
        self.fixture=base.PickerTests();self.fixture.setUp()
        f=self.fixture;self.records=tuple(CatalogValueRow(CatalogKey(f.db,f.key.catalog_id,uuid4()),
            ('P%04d'%n,'Product %04d'%n)) for n in range(70))
        outer=self
        class View:
            database_id=f.db
            def scan_catalog_values(self,identity,request,fields):
                records=outer.records
                if getattr(request.predicate,'kind',None)=='and':
                    code=request.predicate.terms[1].value
                    records=tuple(r for r in records if r.values[0]==code)
                start=0 if request.continuation is None else int(request.continuation,16)
                end=start+request.page_size
                return CatalogValuePage(records[start:end],format(end,'032x') if len(records)>end else None)
            def read_catalog(self,key):return None if f.deleted else SimpleNamespace(deletion_mark=False)
            def close(self):f.views_closed+=1
        f.server.session._reference_managers[1]._view=View

    def test_pages_revoke_old_choices_and_cursors_without_view(self):
        f=self.fixture;p=f.begin();self.assertEqual(p['navigation']['total'],70)
        self.assertEqual(len(p['rows']),32);self.assertEqual(f.views_closed,1)
        action=dict(action='page',ticket=p['ticket'],cursor=p['navigation']['next'])
        self.assertEqual(f.execute(action),'paged');q=f.choice.projection()
        self.assertEqual(q['navigation']['page'],2);self.assertEqual(f.views_closed,1)
        with self.assertRaises(ValueError):f.execute(action)
        with self.assertRaises(ValueError):f.execute(dict(action='apply',ticket=p['ticket'],choice=p['rows'][0]['choice']))
        self.assertNotIn(str(f.db),str(q))

    def test_search_after_exact_filter_restores_full_snapshot(self):
        f=self.fixture;p=f.begin()
        f.execute(dict(action='filter',ticket=p['ticket'],code='P0001'))
        self.assertEqual(f.choice.projection()['navigation']['total'],1)
        f.execute(dict(action='search',ticket=p['ticket'],query='PRODUCT 006'))
        q=f.choice.projection();self.assertEqual(q['code'],'');self.assertEqual(q['navigation']['total'],10)
        self.assertEqual(f.views_closed,3)
        f.execute(dict(action='search',ticket=p['ticket'],query=''))
        self.assertEqual(f.choice.projection()['navigation']['total'],70);self.assertEqual(f.views_closed,3)

    def test_overflow_filter_recovery_and_search_overflow(self):
        f=self.fixture
        with patch('yadinassi.reference_choice_pages.MAX_ROWS',32):
            p=f.begin();self.assertEqual(p['error'],'snapshot_limit');self.assertIsNone(p['navigation'])
            f.execute(dict(action='filter',ticket=p['ticket'],code='P0001'))
            self.assertEqual(f.choice.projection()['navigation']['total'],1)
            f.execute(dict(action='search',ticket=p['ticket'],query='Product 0001'))
            q=f.choice.projection();self.assertEqual(q['rows'],[]);self.assertEqual(q['error'],'snapshot_limit')
        self.assertEqual(f.views_closed,3)

    def test_owner_change_blocks_page_and_deleted_apply_still_rechecks(self):
        f=self.fixture;p=f.begin();owner=f.owned.object;f.owned.object=object()
        with self.assertRaises(ValueError):f.execute(dict(action='page',ticket=p['ticket'],cursor=p['navigation']['next']))
        f.owned.object=owner;f.deleted=True
        with self.assertRaises(BackendError):f.execute(dict(action='apply',ticket=p['ticket'],choice=p['rows'][0]['choice']))
        self.assertTrue(f.server.session.form._data['product'].is_empty())

    def test_wire_preflight_failure_does_not_revoke_previous_page(self):
        f=self.fixture;p=f.begin();action=dict(action='page',ticket=p['ticket'],cursor=p['navigation']['next'])
        with patch('yadinassi.configuration_reference_choice.encode_line',side_effect=ValueError('budget')):
            with self.assertRaises(ValueError):f.execute(action)
        self.assertEqual(f.choice.projection(),p)
        f.execute(action);self.assertEqual(f.choice.projection()['navigation']['page'],2)

    def test_invalid_query_and_byte_budget(self):
        f=self.fixture;p=f.begin()
        for query in (False,'x'*129,'\x00'):
            with self.assertRaises(ValueError):f.execute(dict(action='search',ticket=p['ticket'],query=query))
        with patch('yadinassi.reference_choice_pages.MAX_BYTES',1):
            with self.assertRaises(SnapshotLimit):load_choices(f.server.session._reference_managers[1])
        self.assertEqual(f.views_closed,2)

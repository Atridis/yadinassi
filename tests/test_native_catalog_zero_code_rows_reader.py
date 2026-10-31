"""Actual public API adapter; standalone physical oracle must never be invoked."""
from dataclasses import replace
from decimal import Decimal
import inspect
import unittest
from unittest import mock
import test_native_catalog_zero_code_physical as fixture
import catalog_zero_code_physical as standalone
import catalog_zero_code_rows_reader as subject

class ZeroRowsReaderTests(unittest.TestCase):
    def test_public_read_once_and_no_observer_or_expected_selector(self):
        self.assertEqual(tuple(inspect.signature(subject.read_zero_code_rows).parameters),('read_at','file_size','catalog_name','limits'))
        for description in (0,8):
            for payload in (32,64):
                value=fixture.source(description,payload)
                with mock.patch.object(standalone,'read_zero_code',side_effect=AssertionError('standalone observer forbidden')),mock.patch.object(subject.loader,'read_catalog_rows',wraps=subject.loader.read_catalog_rows)as call:
                    actual=subject.read_zero_code_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
                self.assertEqual(call.call_count,1)
                self.assertEqual(set(call.call_args.kwargs),{'catalog_name','limits'})
                self.assertFalse(any(f.name.upper()=='_CODE' for f in actual.physical.table.fields))
                self.assertEqual(actual.physical.typed_uuid,standalone.read_zero_code(value.read_at,value.size,catalog_name='NativeOracleItems').typed_uuid)
                self.assertEqual(actual.physical.status,'layout_observed')
    def test_unexpected_descriptor_is_rejected(self):
        value=fixture.source(edit=lambda ds:ds[:4]+[('_CODE','NVC',0,2,0,'CI')]+ds[4:])
        with self.assertRaises(subject.loader.catalog_module.CatalogError):
            subject.read_zero_code_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
    def test_single_graph_consumed_on_success_and_failure(self):
        c=subject.loader.catalog_module;original=c._CatalogBindingGraph.__init__;graphs=[]
        def track(graph,*args,**kw):original(graph,*args,**kw);graphs.append(graph)
        with mock.patch.object(c._CatalogBindingGraph,'__init__',track):
            value=fixture.source();subject.read_zero_code_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            bad=fixture.source();bad.page(43)[139+68]=0xff
            with self.assertRaises(c.CatalogError):subject.read_zero_code_rows(bad.read_at,bad.size,catalog_name='NativeOracleItems')
        self.assertEqual(len(graphs),2);self.assertFalse(graphs[0].failed);self.assertTrue(graphs[1].failed)
        for graph in graphs:
            with self.assertRaises(ValueError):
                with graph.stage('config'):pass

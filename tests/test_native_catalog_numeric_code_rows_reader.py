"""Actual public API adapter; standalone physical oracle must never be invoked."""
from dataclasses import replace
from decimal import Decimal
import inspect
import unittest
from unittest import mock
import test_native_catalog_numeric_code_physical as fixture
import catalog_numeric_code_physical as standalone
import catalog_numeric_code_rows_reader as subject

class NumericRowsReaderTests(unittest.TestCase):
    def test_public_read_once_and_no_observer_or_expected_selector(self):
        self.assertEqual(tuple(inspect.signature(subject.read_numeric_code_rows).parameters),('read_at','file_size','catalog_name','limits'))
        for length,number in ((3,123),(6,432109),(5,98765)):
            for payload in (32,64):
                value=fixture.source(length,number,payload)
                with mock.patch.object(standalone,'read_numeric_code',side_effect=AssertionError('standalone observer forbidden')),mock.patch.object(subject.loader,'read_catalog_rows',wraps=subject.loader.read_catalog_rows)as call:
                    actual=subject.read_numeric_code_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
                self.assertEqual(call.call_count,1)
                self.assertEqual(set(call.call_args.kwargs),{'catalog_name','limits'})
                self.assertEqual(actual.records.rows[0].fields[4].value,Decimal(number))
                self.assertEqual(actual.typed_uuid,fixture.read(value).typed_uuid)
                self.assertEqual(actual.status,'layout_observed')
    def test_unexpected_descriptor_is_rejection_not_observation(self):
        value=fixture.source(edit=lambda ds:ds[:4]+[('_CODE','N',0,3,1,'CS')]+ds[5:])
        with self.assertRaises(subject.loader.catalog_module.UnsupportedLayout)as cm:subject.read_numeric_code_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(cm.exception.code,'declaration_mismatch')
    def test_same_public_graph_consumed_on_success_and_failure(self):
        c=subject.loader.catalog_module;original=c._CatalogBindingGraph.__init__;graphs=[]
        def track(graph,*args,**kw):original(graph,*args,**kw);graphs.append(graph)
        with mock.patch.object(c._CatalogBindingGraph,'__init__',track):
            value=fixture.source();subject.read_numeric_code_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            bad=fixture.source();bad.page(43)[141+50]=0xff
            with self.assertRaises(c.CatalogError):subject.read_numeric_code_rows(bad.read_at,bad.size,catalog_name='NativeOracleItems')
        self.assertEqual(len(graphs),2);self.assertFalse(graphs[0].failed);self.assertTrue(graphs[1].failed)
        for graph in graphs:
            with self.assertRaises(ValueError):
                with graph.stage('config'):pass

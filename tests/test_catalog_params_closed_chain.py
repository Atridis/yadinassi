"""Complete invented CONFIG/PARAMS/Catalog bytes; no native acceptance claim."""
from dataclasses import replace
from uuid import UUID
import unittest
from unittest import mock
import test_native_catalog_description_physical as fixture
import catalog_binding_reader as entry


def source(length=8,payload=32,count=3,*,broken=None):
    value=fixture.source(length,'Я ' if length else '',payload)
    stride=301
    value.page(32)[1:5]=(2 if count else 0).to_bytes(4,'little')
    for index in range(count):
        slot=index+2
        row=b'\x01'+(slot+1 if index+1<count else 0).to_bytes(4,'little')+b'\xff'*296
        value.page(32)[slot*stride:(slot+1)*stride]=row
    value.page(30)[16:24]=((count+2)*stride).to_bytes(8,'little')
    if broken=='unlinked':value.page(32)[1:5]=bytes(4)
    if broken=='zero_target':value.page(32)[1:5]=(1).to_bytes(4,'little')
    return value

class PublicClosedChainTests(unittest.TestCase):
    def test_public_fixture_changes_only_reserved_head_not_historical_fixture(self):
        captured=[];params=fixture.fixture.params_fixture;original=params.source
        def collect(*args,**kwargs):
            image=original(*args,**kwargs);captured.append(image);return image
        with mock.patch.object(params,'source',collect):image=fixture.fixture.source()
        self.assertEqual(len(captured),1)
        before=bytes(captured[0].page(10));after=bytes(image.page(32))
        self.assertEqual(before[1:5],b'RRRR')
        expected=bytearray(before);expected[1:5]=bytes(4)
        self.assertEqual(after,bytes(expected))
        self.assertEqual((before[0],after[0]),(1,1))
        self.assertEqual(before[301:],after[301:])
        self.assertEqual(bytes(captured[0].page(10)),before)

    def test_metadata_zero_and_positive_raw_typed_one_graph(self):
        for length in (0,8,17):
            for payload in (32,64):
                for count in (0,1,3,17):
                    left,right=source(length,payload,count),source(length,payload,count)
                    raw=entry.read_catalog_binding(left.read_at,left.size,catalog_name='NativeOracleItems')
                    graphs=[];c=entry.catalog_module;original=c._CatalogBindingGraph.__init__
                    def init(obj,*args,**kwargs):original(obj,*args,**kwargs);graphs.append(obj)
                    with mock.patch.object(c._CatalogBindingGraph,'__init__',init):
                        typed=entry.read_catalog_rows(right.read_at,right.size,catalog_name='NativeOracleItems')
                    self.assertEqual(len(graphs),1);self.assertFalse(graphs[0].failed)
                    self.assertEqual(graphs[0]._next,3)
                    self.assertEqual(raw.records,typed.records);self.assertEqual(raw.binding,typed.binding)
                    self.assertEqual(typed.binding.description_length,length)
                    self.assertEqual(typed.rows[0].reference_uuid,UUID('52525252-5252-5252-5252-525252525252'))
                    self.assertEqual(len(typed.binding.placements),7+bool(length))
                    if length:self.assertEqual(typed.records.rows[0].fields[5].value,'Я ')
    def test_chain_rejection_poison_and_no_params_blob_body(self):
        for fault in ('unlinked','zero_target'):
            value=source(broken=fault);graphs=[];c=entry.catalog_module;original=c._CatalogBindingGraph.__init__
            def init(obj,*args,**kwargs):original(obj,*args,**kwargs);graphs.append(obj)
            with mock.patch.object(c._CatalogBindingGraph,'__init__',init),self.assertRaisesRegex(c.UnsupportedLayout,'dbnames_chain_'+fault):
                entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            self.assertEqual(len(graphs),1);self.assertTrue(graphs[0].failed)
            self.assertFalse(any(offset//fixture.fixture.P==33 for offset,_ in value.calls))
            with self.assertRaises(ValueError):
                with graphs[0].stage('params'):pass
    def test_cumulative_budget_still_shared_and_failure_consumes_graph(self):
        value=source();c=entry.catalog_module
        with self.assertRaises(c.ResourceLimit):
            entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems',
                limits=replace(c.CatalogLimits(),max_output_bytes=1024))

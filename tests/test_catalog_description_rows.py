"""CONFIG-derived raw/typed Description support; invented bytes not native proof."""
from dataclasses import replace
from uuid import UUID
import unittest
from unittest import mock
import test_native_catalog_description_physical as fixture
import catalog_binding_reader as entry
import catalog_description_physical as adapter

class CatalogDescriptionRowsTests(unittest.TestCase):
    def test_metadata_width_generalization_and_zero_exact_compatibility(self):
        for n in (0,1,3,8,17,31,127):
            value=fixture.source(n,'Я' if n else '')
            raw=entry.read_catalog_binding(value.read_at,value.size,catalog_name='NativeOracleItems')
            typed=entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            self.assertEqual(raw.records,typed.records)
            self.assertEqual(raw.binding,typed.binding)
            self.assertEqual(typed.binding.description_length,n)
            self.assertEqual(len(typed.binding.placements),7+bool(n))
            self.assertEqual(typed.binding.record_size,127+(2+2*n if n else 0))
            self.assertIs(typed.rows[0].physical_record,typed.records.rows[0])
            self.assertEqual(typed.rows[0].reference_uuid,UUID('52525252-5252-5252-5252-525252525252'))
            if n:self.assertEqual(typed.records.rows[0].fields[5].value,'Я')
    def test_payload_migration_and_unicode_prefix(self):
        for n,text in ((8,'AБ😀xy  '),(17,'AbВгДеЖзИйКл😀x  ')):
            for payload in (32,64):
                value=fixture.source(n,text,payload)
                observed,identifier=adapter.read_description_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
                summary=adapter.public_observation(observed)
                self.assertEqual(summary['description_width'],2+2*n)
                self.assertEqual(summary['used_utf16_units'],n)
                self.assertEqual(summary['unicode_scalars'],n-1)
                self.assertEqual(summary['payload_length'],payload)
                self.assertEqual(summary['record_size'],127+2+2*n+2*(payload-32))
                self.assertIs(type(identifier),UUID)
    def test_adapter_one_public_call_same_owner_graph_and_only_selector(self):
        value=fixture.source();graphs=[];c=entry.catalog_module
        original=c._CatalogBindingGraph.__init__
        def init(obj,*a,**k):original(obj,*a,**k);graphs.append(obj)
        with mock.patch.object(c._CatalogBindingGraph,'__init__',init),\
             mock.patch.object(entry,'read_catalog_rows',wraps=entry.read_catalog_rows) as call:
            observed,identifier=adapter.read_description_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(call.call_count,1);self.assertEqual(set(call.call_args.kwargs),{'catalog_name','limits'})
        self.assertEqual(len(graphs),1);self.assertEqual(graphs[0]._next,3)
        self.assertFalse(graphs[0].failed);self.assertEqual(observed.usage,graphs[0].reader.usage)
    def test_metadata_fact_and_placement_forgery_rejected(self):
        value=fixture.source();modules=entry._load_storage();rows=modules['config_catalog_records']
        compiler=modules['config_catalog_binding'];raw=entry.read_catalog_binding(value.read_at,value.size,catalog_name='NativeOracleItems')
        class Budget:
            def charge(self,*args):pass
        for change in ({'description_length':False},{'description_length':0},{'description_length':17},
                       {'description_length':-1},{'description_length':2048},
                       {'record_size':raw.binding.record_size-1},
                       {'placements':raw.binding.placements[:5]+(replace(raw.binding.placements[5],offset=50),)+raw.binding.placements[6:]}):
            with self.assertRaises(entry.catalog_module.CatalogError):rows._validate_binding(replace(raw.binding,**change),Budget())
    def test_unknown_type_order_capacity_duplicate_or_freed_rejected(self):
        edits=(lambda ds:ds[:5]+[('_DESCRIPTION','B',0,8,0,'CI')]+ds[6:],
               lambda ds:ds[:5]+[('_DESCRIPTION','NVC',0,17,0,'CI')]+ds[6:],
               lambda ds:ds[:5]+ds[6:]+ds[5:6],
               lambda ds:ds[:6]+[ds[5]]+ds[7:])
        for edit in edits:
            value=fixture.source(edit=edit)
            with self.assertRaises(entry.catalog_module.CatalogError):entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        value=fixture.source();value.page(43)[145]=1
        with self.assertRaises(entry.catalog_module.CatalogError):entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
    def test_used_prefix_shorter_update_ignores_unused_tail_but_never_trims_spaces(self):
        value=fixture.source(text='Я ');start=145+56+2+4
        value.page(43)[start:start+12]=b'\xff'*12
        raw=entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(raw.records.rows[0].fields[5].value,'Я ')
    def test_malformed_prefix_surrogate_and_lower_budget_fail_closed(self):
        for data in (b'\xff\xff',b'\x01\x00\x00\xd8'):
            value=fixture.source();value.page(43)[145+56:145+56+len(data)]=data
            with self.assertRaises(entry.catalog_module.CatalogError):entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        value=fixture.source()
        with self.assertRaises(entry.catalog_module.ResourceLimit):entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems',limits=replace(entry.catalog_module.CatalogLimits(),max_output_bytes=1024))

if __name__=='__main__':unittest.main()

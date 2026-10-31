"""Invented images and hostile envelopes; never authentic native slot evidence."""
import copy
import json
import unittest
from unittest import mock
import test_native_catalog_description_physical as fixture
import catalog_read_physical as subject
import catalog_read_fixture
from yadinassi.storage import catalog_reader


class PhysicalSlotMeasurementTests(unittest.TestCase):
    def read(self, value=None, uuid=None):
        value = fixture.source() if value is None else value
        return subject._catalog(value.read_at, value.size, 'NativeOracleItems',
            fixture.fixture.config_fixture.KEYS[0] if uuid is None else uuid)

    def envelope(self):
        b, _, _ = catalog_read_fixture.load(1)
        actual = self.read()
        catalogs=[]
        for i,(name, uuid) in enumerate(zip(b.setup.names,b.setup.metadata_ids)):
            item=copy.deepcopy(actual);item.update(name=name,metadata_uuid=uuid,
                table='_Reference'+str(19+i),data_header_page=40+i)
            catalogs.append(item)
        return b,dict(schema=1,capability='owned_raw_slot_measurement_only',catalogs=catalogs,
                      source_reads=dict(calls=100,bytes=sum(c['usage']['read_bytes'] for c in catalogs)))

    def test_complete_graph_actual_invented_bytes(self):
        result=self.read()
        self.assertEqual(result['record_size'],145)
        self.assertEqual(result['logical_length'],290)
        self.assertEqual([s['marker'] for s in result['slots']],[1,0])
        self.assertEqual(result['slots'][0]['logical_marked_hex'],None)
        self.assertEqual(result['slots'][1]['logical_marked_hex'],'00')
        self.assertEqual(result['placements'][5]['offset'],56)
        self.assertGreater(result['usage']['read_bytes'],0)

    def test_multiple_deleted_and_unknown_markers_retained_not_decoded(self):
        value=fixture.source(rows=3)
        value.page(43)[145*2]=1
        value.page(43)[145*3]=173
        value.page(43)[145+33]=1
        result=self.read(value)
        self.assertEqual([x['marker'] for x in result['slots']],[1,0,1,173])
        self.assertEqual([x['logical_marked_hex'] for x in result['slots']],[None,'01',None,None])
        self.assertEqual(len(result['slots'][2]['raw_hex']),290)
        self.assertNotIn('active_count',result)

    def test_production_refusal_unchanged(self):
        for rows,marker,code in ((2,0,'active_records'),(1,1,'nonreserved_free_slot')):
            value=fixture.source(rows=rows);value.page(43)[145]=marker
            with self.assertRaisesRegex(catalog_reader.catalog_module.CatalogError,code):
                catalog_reader.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')

    def test_empty_shapes(self):
        for length,count in ((0,0),(145,1)):
            value=fixture.source();value.page(40)[16:24]=length.to_bytes(8,'little')
            self.assertEqual(len(self.read(value)['slots']),count)

    def test_slot_bound_before_payload(self):
        value=fixture.source(rows=16)
        with self.assertRaisesRegex(subject.c.ResourceLimit,'measurement_slots'):self.read(value)
        self.assertFalse(any(offset==43*fixture.fixture.P for offset,_ in value.calls))

    def test_partial_record_refused(self):
        value=fixture.source();value.page(40)[16:24]=(291).to_bytes(8,'little')
        with self.assertRaisesRegex(subject.c.InvalidStructure,'record_file_length'):self.read(value)

    def test_expected_identity_not_used_to_construct_binding(self):
        with self.assertRaisesRegex(subject.c.InvalidStructure,'measurement_saved_identity'):
            self.read(uuid='ffffffff-ffff-ffff-ffff-ffffffffffff')

    def test_owned_shape_closed(self):
        for args in ((0,'',32),(17,'A',32),(8,'A',64)):
            with self.assertRaisesRegex(subject.c.UnsupportedLayout,'measurement_owned_profile'):
                self.read(fixture.source(*args))

    def test_changed_field_rejected_before_payload(self):
        def edit(ds):return ds[:5]+[('_OTHER',*ds[5][1:])]+ds[6:]
        value=fixture.source(edit=edit)
        with self.assertRaisesRegex(subject.c.UnsupportedLayout,'measurement_declaration_mismatch'):self.read(value)
        self.assertFalse(any(offset==43*fixture.fixture.P for offset,_ in value.calls))

    def test_json_validator_accepts_roundtrip(self):
        b,v=self.envelope();self.assertEqual(subject.validate_observation(json.loads(json.dumps(v)),b),v)

    def test_validator_hostile_primitives_and_raw_alignment(self):
        b,v=self.envelope()
        changes=[('schema',True),('schema',1.0),('catalogs',()),('source_reads',{'calls':True,'bytes':1})]
        for key,value in changes:
            bad=copy.deepcopy(v);bad[key]=value
            with self.assertRaises(ValueError):subject.validate_observation(bad,b)
        for key,value in [('record_size',True),('record_size',144),('data_header_page',0),
                          ('metadata_uuid',b.setup.record_ids[0]),('table','_Reference01'),
                          ('logical_length',291)]:
            bad=copy.deepcopy(v);bad['catalogs'][0][key]=value
            with self.assertRaises(ValueError):subject.validate_observation(bad,b)
        for key,value in [('slot',True),('logical_offset',0),('marker',1),('raw_hex','00'),
                          ('logical_marked_hex','01')]:
            bad=copy.deepcopy(v);bad['catalogs'][0]['slots'][1][key]=value
            with self.assertRaises(ValueError):subject.validate_observation(bad,b)

    def test_validator_declarations_usage_and_aliases(self):
        b,v=self.envelope()
        for change in ('primitive','offset','extra','usage','tablealias','headeralias'):
            bad=copy.deepcopy(v);a=bad['catalogs'][0]
            if change=='primitive':a['placements'][0]['declaration'][2]=False
            if change=='offset':a['placements'][0]['offset']=1
            if change=='extra':a['extra']=1
            if change=='usage':a['usage']['read_bytes']=2**60
            if change=='tablealias':bad['catalogs'][1]['table']=a['table']
            if change=='headeralias':bad['catalogs'][1]['data_header_page']=a['data_header_page']
            with self.assertRaises(ValueError):subject.validate_observation(bad,b)

    def test_shared_callback_budget_before_read(self):
        b,_,_=catalog_read_fixture.load(1);calls=[]
        def reader(offset,length):calls.append((offset,length));return bytes(length)
        def catalog(read_at,*args):read_at(0,8);read_at(0,8)
        with mock.patch.object(subject,'_catalog',catalog),mock.patch.object(subject,'MAX_READ_BYTES',15):
            with self.assertRaisesRegex(subject.c.ResourceLimit,'measurement_source_budget'):
                subject.observe(reader,100,b)
        self.assertEqual(calls,[(0,8)])

    def test_callback_bad_range_not_forwarded(self):
        b,_,_=catalog_read_fixture.load(1)
        def catalog(read_at,*args):read_at(True,1)
        reader=mock.Mock()
        with mock.patch.object(subject,'_catalog',catalog):
            with self.assertRaisesRegex(subject.c.InvalidStructure,'measurement_source_range'):
                subject.observe(reader,100,b)
        reader.assert_not_called()


if __name__=='__main__':unittest.main()

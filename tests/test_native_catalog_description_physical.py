"""Invented full CONFIG/PARAMS/record images, not native evidence."""
from dataclasses import replace
import hashlib
import inspect
import json
import unittest
from unittest import mock
import test_catalog_binding_integration as fixture
from test_filedb_records import text_value, serialize
import catalog_binding_reader as existing
import catalog_description_physical as subject


def source(length=8, text='AБ😀xy  ', payload_length=32, *, edit=None, rows=1):
    cf = fixture.config_fixture
    def config_source():
        payloads = []
        for i, (key, (name, code, kind, description)) in enumerate(zip(cf.KEYS, cf.policy.MATRIX)):
            prefix = cf.matrix.names.document(name='"'+name+'"', code=str(code), kind=str(kind),
                description=str(length if i == 0 else description), metadata_uuid=key)
            attrs = [] if i else [cf.constructed.attribute('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '"Payload"', '{"Pattern",{"S",'+str(payload_length)+',1}}'),
                cf.constructed.attribute('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '"Amount"', '{"Pattern",{"N",9,2,0}}')]
            coll = cf.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9', str(len(attrs)), *attrs)
            payloads.append(cf.stored_literal(prefix[:-1]+b',0,0,0,0,'+coll.encode()+b'}'))
        return cf.content_source(cf.entries(refs=cf.KEYS, payload=payloads[0],
            tail=tuple((key, p, 0) for key,p in zip(cf.KEYS[1:],payloads[1:]))))
    with mock.patch.object(cf, 'source', config_source):
        value = fixture.source()
    declarations = [('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
        ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),
        ('_CODE','NVC',0,2,0,'CI')]
    if length:
        declarations.append(('_DESCRIPTION','NVC',0,length,0,'CI'))
    declarations += [('_FLD62','NVC',0,payload_length,0,'CI'),('_FLD741','N',0,9,2,'CS')]
    if edit:
        declarations = edit(declarations)
    descriptor = serialize(('_Reference19',0,('Fields',*declarations),('Indexes',),('Recordlock','0'),('Files',40,41,42))).encode()
    value.chain(tuple(range(14,14+(len(descriptor)+249)//250)),descriptor)
    row = (b'\0'+b'V'*16+b'R'*16+b'\0'+b'P'*16+text_value('K1',2)
           +(text_value(text,length) if length else b'')+text_value('alpha',payload_length)+b'\x10\0\0\x01\x25')
    raw = b'\x01'+bytes(4)+b'R'*(len(row)-5)+row*rows
    value.page(40)[16:24] = len(raw).to_bytes(8,'little')
    value.page(43)[:] = bytes(fixture.P)
    value.page(43)[:len(raw)] = raw
    return value


def read(value=None, **kw):
    value = source() if value is None else value
    return subject.read_description(value.read_at, value.size, catalog_name='NativeOracleItems', **kw)


class DescriptionPhysicalTests(unittest.TestCase):
    def test_only_source_and_name_selector(self):
        self.assertEqual(tuple(inspect.signature(subject.read_description).parameters),
                         ('read_at','file_size','catalog_name','limits'))

    def test_actual_bytes_both_lengths_and_payload_migration(self):
        for length,text in ((8,'AБ😀xy  '),(17,'AbВгДеЖзИйКл😀x  ')):
            for payload_length in (32,64):
                with self.subTest(length=length,payload=payload_length):
                    actual=read(source(length,text,payload_length))
                    self.assertEqual(actual.identity.description_length,length)
                    self.assertEqual(actual.status,'layout_observed')
                    self.assertEqual(actual.records.rows[0].fields[5].value,text)
                    summary=subject.public_observation(actual)
                    self.assertTrue(summary['active_count_known'])
                    self.assertEqual(summary['used_utf16_units'],length)
                    self.assertEqual(summary['unicode_scalars'],length-1)
                    self.assertEqual(summary['trailing_spaces'],2)
                    self.assertTrue(summary['utf16_count_matches'])
                    self.assertEqual(summary['description_offset'],56)
                    self.assertEqual(summary['description_width'],2+2*length)
                    self.assertEqual(summary['record_size'],127+2*(payload_length-32)+2+2*length)
                    self.assertEqual(summary['next_displacement'],2+2*length)
                    self.assertEqual(summary['value_sha256'],hashlib.sha256(text.encode('utf-16-le')).hexdigest())
                    for private in ('_DESCRIPTION','NativeOracleItems','Payload',text):
                        self.assertNotIn(private,json.dumps(summary,ensure_ascii=False))

    def test_zero_control_same_old_seven_fields_and_rows(self):
        value=source(0,'')
        actual=read(value)
        baseline=existing.read_catalog_binding(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(actual.placements,baseline.binding.placements)
        self.assertEqual(actual.record_size,127)
        self.assertEqual(actual.records.rows,baseline.records.rows)
        self.assertEqual(subject.public_observation(actual)['description_width'],0)

    def test_production_binding_positive_is_metadata_derived(self):
        for n in (8,17):
            value=source(n,'Я ')
            result=existing.read_catalog_binding(value.read_at,value.size,catalog_name='NativeOracleItems')
            self.assertEqual(result.binding.description_length,n)
            self.assertEqual(result.records.rows[0].fields[5].value,'Я ')

    def test_shorter_replacement_padding_not_decoded_or_stripped(self):
        actual=read(source(text='Я '))
        field=actual.records.rows[0].fields[5]
        self.assertEqual(field.value,'Я ')
        self.assertIn(b'\xcc',field.raw)
        self.assertEqual(subject.public_observation(actual)['used_utf16_units'],2)

    def test_unexpected_value_not_used_as_selector(self):
        self.assertEqual(read(source(text='other')).records.rows[0].fields[5].value,'other')

    def test_unexpected_name_order_type_and_capacity_retained_without_decode(self):
        def name(ds):return ds[:5]+[('_OTHER',*ds[5][1:])]+ds[6:]
        def order(ds):return ds[:5]+[ds[6],ds[5]]+ds[7:]
        def kind(ds):return ds[:5]+[('_DESCRIPTION','B',0,8,0,'CS')]+ds[6:]
        def capacity(ds):return ds[:5]+[('_DESCRIPTION','NVC',0,17,0,'CI')]+ds[6:]
        for edit in (name,order,kind,capacity):
            value=source(edit=edit)
            result=read(value)
            self.assertEqual(result.status,'layout_unresolved')
            self.assertIsNone(result.records)
            self.assertEqual(len(result.descriptor_sha256),64)
            self.assertFalse(any(offset==43*fixture.P for offset,_ in value.calls))
            self.assertEqual(subject.public_observation(result)['active_count'],0)
            self.assertFalse(subject.public_observation(result)['active_count_known'])

    def test_one_shared_graph_lifetime_and_budgets(self):
        c=existing.catalog_module
        original_init=c.CatalogReader.__init__; original_graph=c._CatalogBindingGraph.__init__
        readers=[];graphs=[]
        def ri(obj,*a,**k):original_init(obj,*a,**k);readers.append(obj)
        def gi(obj,*a,**k):original_graph(obj,*a,**k);graphs.append(obj)
        with mock.patch.object(c.CatalogReader,'__init__',ri),mock.patch.object(c._CatalogBindingGraph,'__init__',gi):
            actual=read()
        self.assertEqual(len(readers),1);self.assertEqual(len(graphs),1)
        self.assertEqual(graphs[0]._next,3);self.assertFalse(graphs[0].failed)
        self.assertEqual(actual.usage,readers[0].usage)
        self.assertGreater(actual.usage.bytes_processed,0)

    def test_zero_or_two_active_rows_rejected(self):
        for count in (0,2):
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(rows=count))

    def test_free_row_and_prefix_overflow_and_surrogate_rejected(self):
        for offset,data in ((0,b'\x01'),(56,b'\xff\xff'),(56,b'\x01\x00\x00\xd8')):
            value=source();size=145
            value.page(43)[size+offset:size+offset+len(data)]=data
            with self.assertRaises(existing.catalog_module.CatalogError):read(value)

    def test_truncated_file_and_shared_pages_rejected(self):
        value=source();value.page(40)[16:24]=(289).to_bytes(8,'little')
        with self.assertRaises(existing.catalog_module.InvalidStructure):read(value)
        value=source();value.page(40)[24:28]=fixture.u32(32)
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)

    def test_duplicate_and_excess_fields_rejected(self):
        for edit in (lambda ds:ds+[ds[5]], lambda ds:ds+[(f'_UNKNOWN{i}','B',0,1,0,'CS') for i in range(9)]):
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(edit=edit))

    def test_lower_budget_rejected(self):
        limits=replace(existing.catalog_module.CatalogLimits(),max_output_bytes=1024)
        with self.assertRaises(existing.catalog_module.ResourceLimit):read(limits=limits)

    def test_wrong_selector_and_invalid_types(self):
        value=source()
        for name in ('Missing','nativeoracleitems',True,[], '\ud800'):
            with self.assertRaises(existing.catalog_module.CatalogError):
                subject.read_description(value.read_at,value.size,catalog_name=name)


if __name__=='__main__':unittest.main()

"""Invented full CONFIG/PARAMS/record images, not native evidence."""
from dataclasses import replace
import hashlib
import inspect
from decimal import Decimal
from uuid import UUID
import json
import unittest
from unittest import mock
import test_catalog_binding_integration as fixture
from test_filedb_records import text_value, serialize
import catalog_binding_reader as existing
import catalog_zero_code_physical as subject


def bcd(number, precision):
    digits = str(abs(number)).zfill(precision)
    if len(digits) != precision:
        raise ValueError('synthetic number exceeds precision')
    nibbles = ('1' if number >= 0 else '0') + digits
    if len(nibbles) % 2:
        nibbles += '0'
    return bytes.fromhex(nibbles)


def source(description=8, payload_length=32, *, edit=None, rows=1, length=0, kind=1):
    requested_description = description
    cf = fixture.config_fixture
    def config_source():
        payloads = []
        for i, (key, (name, code, matrix_kind, description)) in enumerate(zip(cf.KEYS, cf.policy.MATRIX)):
            prefix = cf.matrix.names.document(name='"'+name+'"', code=str(length if i == 0 else code), kind=str(kind if i == 0 else matrix_kind),
                description=str(requested_description if i == 0 else description), metadata_uuid=key)
            attrs = [] if i else [cf.constructed.attribute('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '"Payload"', '{"Pattern",{"S",'+str(payload_length)+',1}}'),
                cf.constructed.attribute('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '"Amount"', '{"Pattern",{"N",9,2,0}}')]
            coll = cf.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9', str(len(attrs)), *attrs)
            payloads.append(cf.stored_literal(prefix[:-1]+b',0,0,0,0,'+coll.encode()+b'}'))
        return cf.content_source(cf.entries(refs=cf.KEYS, payload=payloads[0],
            tail=tuple((key, p, 0) for key,p in zip(cf.KEYS[1:],payloads[1:]))))
    with mock.patch.object(cf, 'source', config_source):
        value = fixture.source()
    declarations = [('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
        ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS')]
    if description:
        declarations.append(('_DESCRIPTION','NVC',0,description,0,'CI'))
    declarations += [('_FLD62','NVC',0,payload_length,0,'CI'),('_FLD741','N',0,9,2,'CS')]
    if edit:
        declarations = edit(declarations)
    descriptor = serialize(('_Reference19',0,('Fields',*declarations),('Indexes',),('Recordlock','0'),('Files',40,41,42))).encode()
    value.chain(tuple(range(14,14+(len(descriptor)+249)//250)),descriptor)
    row = (b'\0'+b'V'*16+b'R'*16+b'\0'+b'P'*16+(text_value('X',description) if description else b'')+text_value('alpha',payload_length)+b'\x10\0\0\x01\x25')
    raw = b'\x01'+b'R'*(len(row)-1)+row*rows
    value.page(40)[16:24] = len(raw).to_bytes(8,'little')
    value.page(43)[:] = bytes(fixture.P)
    value.page(43)[:len(raw)] = raw
    return value


def read(value=None, **kw):
    value = source() if value is None else value
    return subject.read_zero_code(value.read_at, value.size, catalog_name='NativeOracleItems', **kw)


class ZeroCodePhysicalTests(unittest.TestCase):
    def test_metadata_driven_optional_description(self):
        for desc in (0,1,8,17):
            for payload in (32,64):
                actual=read(source(desc,payload))
                self.assertEqual(actual.status,'layout_observed')
                self.assertEqual(actual.identity.code_length,0)
                self.assertEqual(type(actual.typed_uuid),UUID)
                out=subject.public_observation(actual)
                self.assertEqual(out['code_field_count'],0)
                self.assertEqual(out['description_field_count'],bool(desc))
                self.assertEqual(out['first_attribute_offset'],50+(2+2*desc if desc else 0))
                self.assertEqual(actual.records.rows[0].fields[-2].value,'alpha')
                self.assertNotIn(str(actual.typed_uuid),json.dumps(out))
                self.assertNotIn('NativeOracleItems',json.dumps(out))
    def test_unexpected_valid_layout_retained(self):
        for edit in (lambda x:x[:4]+[('_CODE','NVC',0,2,0,'CI')]+x[4:],
                     lambda x:x[:4]+list(reversed(x[4:])),
                     lambda x:x[:-1]+[('_FLD741','N',0,8,2,'CS')]):
            value=source(edit=edit);actual=read(value)
            self.assertEqual(actual.status,'layout_unresolved')
            self.assertIsNone(actual.records)
            self.assertFalse(any(offset==43*fixture.P for offset,_ in value.calls))
    def test_reject_positive_and_number_metadata(self):
        for kw in ({'length':2},{'kind':0}):
            with self.assertRaises(existing.catalog_module.UnsupportedLayout):read(source(**kw))
    def test_no_production_compiler_shortcut(self):
        modules=existing._load_storage(project_rows=True)
        with mock.patch.object(modules['config_catalog_binding'],'compile_catalog_binding',side_effect=AssertionError('no shortcut')):
            self.assertEqual(read().status,'layout_observed')
    def test_one_active_bound(self):
        for count in (0,2):
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(rows=count))
    def test_selector_signature(self):
        self.assertEqual(tuple(inspect.signature(subject.read_zero_code).parameters),('read_at','file_size','catalog_name','limits'))
    def test_complete_single_graph_success_and_failure_poison(self):
        c=existing.catalog_module;ri=c.CatalogReader.__init__;gi=c._CatalogBindingGraph.__init__
        readers=[];graphs=[]
        def r(obj,*a,**k):ri(obj,*a,**k);readers.append(obj)
        def g(obj,*a,**k):gi(obj,*a,**k);graphs.append(obj)
        with mock.patch.object(c.CatalogReader,'__init__',r),mock.patch.object(c._CatalogBindingGraph,'__init__',g):
            actual=read()
            bad=source();bad.page(43)[139+50]=0xff
            with self.assertRaises(c.CatalogError):read(bad)
        self.assertEqual(len(readers),2);self.assertEqual(len(graphs),2)
        self.assertEqual(graphs[0]._next,3);self.assertFalse(graphs[0].failed)
        self.assertTrue(graphs[1].failed)
        self.assertEqual(actual.usage,readers[0].usage)
        for graph in graphs:
            with self.assertRaises(ValueError):
                with graph.stage('config'):pass

    def test_cumulative_exact_limits_and_one_less(self):
        usage=read().usage;c=existing.catalog_module
        for field in ('page_reads','read_bytes','bytes_processed','output_bytes','tokens'):
            amount=getattr(usage,field)
            limits=replace(c.CatalogLimits(),**{'max_'+field:amount})
            self.assertEqual(read(limits=limits).usage,usage)
            with self.assertRaises(c.ResourceLimit):read(limits=replace(limits,**{'max_'+field:amount-1}))

    def test_short_tail_callback_and_page_ownership(self):
        value=source();original=value.read_at
        def short(offset,length):
            raw=original(offset,length)
            return raw[:-1] if offset==43*fixture.P else raw
        with self.assertRaises(existing.catalog_module.CatalogError):
            subject.read_zero_code(short,value.size,catalog_name='NativeOracleItems')
        value=source();value.page(40)[24:28]=fixture.u32(32)
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)

    def test_row_count_free_marker_and_truncated_length(self):
        for count in (0,2):
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(rows=count))
        value=source();value.page(43)[139]=1
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)
        value=source();value.page(40)[16:24]=(277).to_bytes(8,'little')
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)


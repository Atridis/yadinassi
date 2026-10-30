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
import catalog_numeric_code_physical as subject


def bcd(number, precision):
    digits = str(abs(number)).zfill(precision)
    if len(digits) != precision:
        raise ValueError('synthetic number exceeds precision')
    nibbles = ('1' if number >= 0 else '0') + digits
    if len(nibbles) % 2:
        nibbles += '0'
    return bytes.fromhex(nibbles)


def source(length=3, number=987, payload_length=32, *, edit=None, rows=1, kind=0):
    cf = fixture.config_fixture
    def config_source():
        payloads = []
        for i, (key, (name, code, matrix_kind, description)) in enumerate(zip(cf.KEYS, cf.policy.MATRIX)):
            prefix = cf.matrix.names.document(name='"'+name+'"', code=str(length if i == 0 else code), kind=str(kind if i == 0 else matrix_kind),
                description=str(8 if i == 0 else description), metadata_uuid=key)
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
        ('_CODE','N',0,length,0,'CS')]
    declarations.append(('_DESCRIPTION','NVC',0,8,0,'CI'))
    declarations += [('_FLD62','NVC',0,payload_length,0,'CI'),('_FLD741','N',0,9,2,'CS')]
    if edit:
        declarations = edit(declarations)
    descriptor = serialize(('_Reference19',0,('Fields',*declarations),('Indexes',),('Recordlock','0'),('Files',40,41,42))).encode()
    value.chain(tuple(range(14,14+(len(descriptor)+249)//250)),descriptor)
    row = (b'\0'+b'V'*16+b'R'*16+b'\0'+b'P'*16+bcd(number,max(1,length))
           +text_value('Name ',8)+text_value('alpha',payload_length)+b'\x10\0\0\x01\x25')
    raw = b'\x01'+b'R'*(len(row)-1)+row*rows
    value.page(40)[16:24] = len(raw).to_bytes(8,'little')
    value.page(43)[:] = bytes(fixture.P)
    value.page(43)[:len(raw)] = raw
    return value


def read(value=None, **kw):
    value = source() if value is None else value
    return subject.read_numeric_code(value.read_at, value.size, catalog_name='NativeOracleItems', **kw)


class NumericCodePhysicalTests(unittest.TestCase):
    def test_only_source_and_catalog_selector(self):
        self.assertEqual(tuple(inspect.signature(subject.read_numeric_code).parameters),
                         ('read_at','file_size','catalog_name','limits'))

    def test_odd_even_and_metadata_not_case_constants(self):
        for precision, number in ((3,987),(6,654321),(4,1234),(1,7),(38,10**37+1)):
            for payload in (32,64):
                with self.subTest(precision=precision,payload=payload):
                    actual=read(source(precision,number,payload))
                    self.assertEqual(actual.status,'layout_observed')
                    field=actual.records.rows[0].fields[4]
                    self.assertEqual(field.value,Decimal(number))
                    self.assertEqual(field.width,(precision+2)//2)
                    self.assertEqual(actual.identity.code_length,precision)
                    self.assertEqual(actual.identity.code_type,0)
                    self.assertEqual(type(actual.typed_uuid),UUID)
                    self.assertNotEqual(actual.typed_uuid.int,0)
                    out=subject.public_observation(actual)
                    self.assertEqual(out['code_offset'],50)
                    self.assertEqual(out['code_precision'],precision)
                    self.assertEqual(out['code_scale'],0)
                    self.assertEqual(out['next_displacement'],(precision+2)//2)
                    self.assertEqual(out['record_size'],139+(precision+2)//2+2*(payload-32))
                    self.assertEqual(out['digit_count'],len(str(number)))
                    self.assertEqual(out['runtime_support'],'not_claimed')
                    self.assertNotIn('value_sha256',out)
                    for private in ('NativeOracleItems','_CODE','Name ',str(actual.typed_uuid)):
                        self.assertNotIn(private,json.dumps(out))

    def test_shorter_replacement_unexpected_value_and_sign_are_observations(self):
        # Sign support is synthetic decoder coverage, NOT native write semantics.
        for n in (1,42,0,-42):
            self.assertEqual(read(source(6,n)).records.rows[0].fields[4].value,Decimal(n))

    def test_production_number_binding_still_rejects(self):
        value=source()
        with self.assertRaises(existing.catalog_module.UnsupportedLayout) as cm:
            existing.read_catalog_binding(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(cm.exception.code,'binding_metadata_profile')

    def test_unexpected_descriptor_retained_without_record_read(self):
        for edit in (lambda ds:ds[:4]+[('_OTHER',*ds[4][1:])]+ds[5:],
                     lambda ds:ds[:4]+[('_CODE','N',0,6,0,'CS')]+ds[5:],
                     lambda ds:ds[:4]+[('_CODE','N',0,3,1,'CS')]+ds[5:],
                     lambda ds:ds[:4]+[('_CODE','NVC',0,3,0,'CI')]+ds[5:],
                     lambda ds:ds[:4]+[ds[5],ds[4]]+ds[6:]):
            value=source(edit=edit);actual=read(value)
            self.assertEqual(actual.status,'layout_unresolved')
            self.assertIsNone(actual.records);self.assertIsNone(actual.typed_uuid)
            self.assertFalse(any(offset==43*fixture.P for offset,_ in value.calls))
            out=subject.public_observation(actual)
            self.assertFalse(out['active_count_known'])
            self.assertEqual(out['code_type'],'unresolved')

    def test_invalid_sign_digit_and_even_padding_rejected(self):
        for precision,replacement,code in ((3,b'\x29\x87','decimal_sign'),
                                           (3,b'\x1a\x87','decimal_digit'),
                                           (6,b'\x16\x54\x32\x11','decimal_padding')):
            value=source(precision,987 if precision==3 else 654321)
            size=139+(precision+2)//2
            value.page(43)[size+50:size+50+len(replacement)]=replacement
            with self.assertRaises(existing.catalog_module.UnsupportedLayout) as cm:read(value)
            self.assertEqual(cm.exception.code,code)

    def test_complete_single_graph_success_and_failure_poison(self):
        c=existing.catalog_module;ri=c.CatalogReader.__init__;gi=c._CatalogBindingGraph.__init__
        readers=[];graphs=[]
        def r(obj,*a,**k):ri(obj,*a,**k);readers.append(obj)
        def g(obj,*a,**k):gi(obj,*a,**k);graphs.append(obj)
        with mock.patch.object(c.CatalogReader,'__init__',r),mock.patch.object(c._CatalogBindingGraph,'__init__',g):
            actual=read()
            bad=source();bad.page(43)[141+50]=0xff
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
            subject.read_numeric_code(short,value.size,catalog_name='NativeOracleItems')
        value=source();value.page(40)[24:28]=fixture.u32(32)
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)

    def test_row_count_free_marker_and_truncated_length(self):
        for count in (0,2):
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(rows=count))
        value=source();value.page(43)[141]=1
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)
        value=source();value.page(40)[16:24]=(281).to_bytes(8,'little')
        with self.assertRaises(existing.catalog_module.CatalogError):read(value)

    def test_closed_metadata_grammar_and_selector(self):
        for precision in (0,39):
            # The chosen values are outside this observer grammar, not a claim
            # that Designer rejects those metadata settings.
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(precision,0))
        with self.assertRaises(existing.catalog_module.CatalogError):read(source(kind=1))
        value=source()
        for name in (True,[], '\ud800','Missing'):
            with self.assertRaises(existing.catalog_module.CatalogError):
                subject.read_numeric_code(value.read_at,value.size,catalog_name=name)

    def test_closed_marker1_params_and_invalid_chain_before_blob(self):
        for count in (0,1,3,17):
            value=source(6,42,64);stride=301
            value.page(32)[1:5]=(2 if count else 0).to_bytes(4,'little')
            for index in range(count):
                slot=index+2
                value.page(32)[slot*stride:(slot+1)*stride]=(b'\x01'+
                    (slot+1 if index+1<count else 0).to_bytes(4,'little')+b'\xff'*296)
            value.page(30)[16:24]=((count+2)*stride).to_bytes(8,'little')
            self.assertEqual(read(value).records.rows[0].fields[4].value,Decimal(42))
            if count:
                value.calls.clear();value.page(32)[1:5]=bytes(4)
                with self.assertRaises(existing.catalog_module.UnsupportedLayout) as cm:read(value)
                self.assertEqual(cm.exception.code,'dbnames_chain_unlinked')
                self.assertFalse(any(offset//fixture.P==33 for offset,_ in value.calls))

    def test_duplicate_or_excess_fields_rejected(self):
        for edit in (lambda ds:ds+[ds[4]],lambda ds:ds+[(f'_EXTRA{i}','B',0,1,0,'CS') for i in range(9)]):
            with self.assertRaises(existing.catalog_module.CatalogError):read(source(edit=edit))


if __name__=='__main__':unittest.main()

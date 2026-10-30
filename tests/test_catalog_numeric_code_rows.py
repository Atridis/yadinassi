"""CONFIG-derived Number Code structural admission; no fresh native runtime proof."""
from dataclasses import replace
from decimal import Decimal,localcontext
from uuid import UUID
import unittest
from unittest import mock
import test_config_catalog_binding as binding_fixture
import test_config_catalog_records as records_fixture
import test_native_catalog_numeric_code_physical as fixture
import catalog_binding_reader as entry

def numeric_source(length=3, number=987, payload_length=32, *, edit=None, rows=1, kind=0, description_length=8):
    cf = fixture.fixture.config_fixture
    def config_source():
        payloads = []
        for i, (key, (name, code, matrix_kind, description)) in enumerate(zip(cf.KEYS, cf.policy.MATRIX)):
            prefix = cf.matrix.names.document(name='"'+name+'"', code=str(length if i == 0 else code), kind=str(kind if i == 0 else matrix_kind),
                description=str(description_length if i == 0 else description), metadata_uuid=key)
            attrs = [] if i else [cf.constructed.attribute('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '"Payload"', '{"Pattern",{"S",'+str(payload_length)+',1}}'),
                cf.constructed.attribute('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '"Amount"', '{"Pattern",{"N",9,2,0}}')]
            coll = cf.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9', str(len(attrs)), *attrs)
            payloads.append(cf.stored_literal(prefix[:-1]+b',0,0,0,0,'+coll.encode()+b'}'))
        return cf.content_source(cf.entries(refs=cf.KEYS, payload=payloads[0],
            tail=tuple((key, p, 0) for key,p in zip(cf.KEYS[1:],payloads[1:]))))
    with mock.patch.object(cf, 'source', config_source):
        value = fixture.fixture.source()
    declarations = [('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
        ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),
        ('_CODE','N',0,length,0,'CS')]
    if description_length:
        declarations.append(('_DESCRIPTION','NVC',0,description_length,0,'CI'))
    declarations += [('_FLD62','NVC',0,payload_length,0,'CI'),('_FLD741','N',0,9,2,'CS')]
    if edit:
        declarations = edit(declarations)
    descriptor = fixture.serialize(('_Reference19',0,('Fields',*declarations),('Indexes',),('Recordlock','0'),('Files',40,41,42))).encode()
    value.chain(tuple(range(14,14+(len(descriptor)+249)//250)),descriptor)
    row = (b'\0'+b'V'*16+b'R'*16+b'\0'+b'P'*16+fixture.bcd(number,max(1,length))
           +(fixture.text_value('X',description_length) if description_length else b'')+fixture.text_value('alpha',payload_length)+b'\x10\0\0\x01\x25')
    raw = b'\x01'+b'R'*(len(row)-1)+row*rows
    value.page(40)[16:24] = len(raw).to_bytes(8,'little')
    value.page(43)[:] = bytes(fixture.fixture.P)
    value.page(43)[:len(raw)] = raw
    return value


class NumericCodeRowsTests(unittest.TestCase):
    def compile(self,length=5,kind=0,*,legacy=False,limits=None,profile=None):
        b=binding_fixture.binding;i,a=binding_fixture.identities(code=length)
        i=replace(i,code_type=kind)
        p=profile or b.CatalogBindingProfile(b.PROFILE_IDENTIFIER if legacy else b.NUMERIC_PROFILE_IDENTIFIER)
        return b.compile_catalog_binding(i,a,binding_fixture.index(),profile=p,budget=binding_fixture.catalog._Budget(binding_fixture.catalog.CatalogLimits()),limits=limits)
    def test_old_string_profile_and_constructor_defaults_unchanged(self):
        b=binding_fixture.binding
        with self.assertRaises(b.CatalogBindingError):self.compile(legacy=True)
        old=self.compile(kind=1,legacy=True);new=self.compile(kind=1)
        self.assertEqual(old,new);self.assertEqual(old.code_type,1)
        self.assertEqual(old.declarations[4],('_CODE','NVC',0,5,0,'CI'))
        self.assertEqual(old.placements[4].width,12)
    def test_precision_is_metadata_and_number_value_is_exact_decimal(self):
        for n in (1,2,3,5,6,7,16,37,38):
            number=10**(n-1)+1 if n>1 else 7
            for payload in (32,64):
                with self.subTest(n=n,payload=payload),localcontext() as ctx:
                    ctx.prec=1
                    value=fixture.source(n,number,payload)
                    raw=entry.read_catalog_binding(value.read_at,value.size,catalog_name='NativeOracleItems')
                    typed=entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
                    self.assertEqual(raw.binding,typed.binding);self.assertEqual(raw.records,typed.records)
                    field=typed.records.rows[0].fields[4]
                    self.assertIs(type(field.value),Decimal);self.assertEqual(field.value,Decimal(number))
                    self.assertEqual(field.value.as_tuple().exponent,0)
                    self.assertEqual((field.offset,field.width),(50,(n+2)//2))
                    self.assertEqual(typed.binding.code_type,0);self.assertEqual(typed.binding.code_length,n)
                    self.assertIs(type(typed.rows[0].reference_uuid),UUID)
    def test_metadata_qualifiers_and_profile_forgery_fail_without_hooks(self):
        b=binding_fixture.binding
        class Hostile(int):
            def __eq__(self,other):raise AssertionError('no equality hook')
        class Text(str):
            def __eq__(self,other):raise AssertionError('no equality hook')
        for kind in (True,Hostile(0),2,-1,'0'):
            with self.subTest(kind=type(kind)),self.assertRaises(b.CatalogBindingError):self.compile(kind=kind)
        for length in (0,-1,39,2047,True,Hostile(3),'3'):
            with self.subTest(length=type(length)),self.assertRaises(b.CatalogBindingError):self.compile(length)
        with self.assertRaises(b.CatalogBindingError):self.compile(6,limits=b.CatalogBindingLimits(max_numeric_precision=5))
        for value in (39,Hostile(38),True):
            limits=b.CatalogBindingLimits();object.__setattr__(limits,'max_numeric_precision',value)
            with self.assertRaises(b.CatalogBindingError):self.compile(limits=limits)
        for identifier in (Text(b.NUMERIC_PROFILE_IDENTIFIER),'other',False):
            p=b.CatalogBindingProfile(b.PROFILE_IDENTIFIER);object.__setattr__(p,'identifier',identifier)
            with self.assertRaises(b.CatalogBindingError):self.compile(profile=p)
    def test_binding_revalidation_rejects_type_width_and_descriptor_forgery(self):
        c=binding_fixture.catalog;validate=records_fixture.records._validate_binding;bound=self.compile()
        for changed in (replace(bound,code_type=1),replace(bound,code_type=True),replace(bound,code_type=2),replace(bound,code_length=39),replace(bound,code_length=4),replace(bound,record_size=bound.record_size+1),replace(bound,placements=bound.placements[:4]+(replace(bound.placements[4],width=9),)+bound.placements[5:])):
            with self.assertRaises(c.CatalogError):validate(changed,c._Budget(c.CatalogLimits()))
    def test_physical_code_declaration_must_exactly_match_metadata(self):
        edits=(lambda ds:ds[:4]+[('_CODE','N',0,3,1,'CS')]+ds[5:],lambda ds:ds[:4]+[('_CODE','N',0,6,0,'CS')]+ds[5:],lambda ds:ds[:4]+[('_CODE','N',0,3,0,'CI')]+ds[5:],lambda ds:ds[:4]+[('_CODE','N',1,3,0,'CS')]+ds[5:],lambda ds:ds[:4]+[('_CODE','NVC',0,3,0,'CI')]+ds[5:])
        for edit in edits:
            value=fixture.source(edit=edit)
            with self.assertRaises(entry.catalog_module.UnsupportedLayout)as cm:entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            self.assertEqual(cm.exception.code,'declaration_mismatch')
    def test_existing_strict_decimal_decoder_and_budget_edges(self):
        for n,raw,code in ((3,b'\x29\x87','decimal_sign'),(3,b'\x1a\x87','decimal_digit'),(6,b'\x16\x54\x32\x11','decimal_padding')):
            value=fixture.source(n,987 if n==3 else 654321);size=139+(n+2)//2;value.page(43)[size+50:size+50+len(raw)]=raw
            with self.assertRaises(entry.catalog_module.UnsupportedLayout)as cm:entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            self.assertEqual(cm.exception.code,code)
        value=fixture.source(7,1234567);usage=entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems').usage
        for name in ('page_reads','read_bytes','bytes_processed','output_bytes','tokens'):
            amount=getattr(usage,name);limits=replace(entry.catalog_module.CatalogLimits(),**{'max_'+name:amount})
            self.assertEqual(entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems',limits=limits).usage,usage)
            with self.assertRaises(entry.catalog_module.ResourceLimit):entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems',limits=replace(limits,**{'max_'+name:amount-1}))
    def test_description_zero_and_positive_with_both_payload_widths(self):
        for description in (0,1,8,17):
            for precision in (4,9):
                for payload in (32,64):
                    value=numeric_source(precision,1234,payload,description_length=description)
                    result=entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
                    self.assertEqual(result.binding.description_length,description)
                    self.assertEqual(len(result.records.rows[0].fields),7+int(description>0))
                    self.assertEqual(result.records.rows[0].fields[4].value,Decimal(1234))
                    self.assertEqual(result.records.rows[0].fields[-2].value,'alpha')
    def test_public_typed_single_graph_and_metadata_join_failure_poison(self):
        c=entry.catalog_module;modules=entry._load_storage(project_rows=True);runtime=modules['catalog_reader']
        original=runtime._project_rows;init=c._CatalogBindingGraph.__init__;graphs=[]
        def track(graph,*args,**kw):init(graph,*args,**kw);graphs.append(graph)
        def forged(graph,identity,binding,records):return original(graph,replace(identity,code_length=identity.code_length+1),binding,records)
        with mock.patch.object(c._CatalogBindingGraph,'__init__',track):
            value=fixture.source();entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            with mock.patch.object(runtime,'_project_rows',forged),self.assertRaises(c.InvalidStructure):
                entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(len(graphs),2);self.assertFalse(graphs[0].failed);self.assertTrue(graphs[1].failed)
        for graph in graphs:
            with self.assertRaises(ValueError):
                with graph.stage('config'):pass
    def test_existing_number_sign_grammar_is_not_assignment_claim(self):
        # Invented bytes only: no claim that native Catalog writes accept these.
        for number in (0,-1234):
            value=fixture.source(5,number)
            result=entry.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
            self.assertEqual(result.records.rows[0].fields[4].value,Decimal(number))

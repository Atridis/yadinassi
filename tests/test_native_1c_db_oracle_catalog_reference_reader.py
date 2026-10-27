"""Local synthetic integration only; not a native or Catalog identity proof."""
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_framing_reader as core
import config_catalog_references as parser
import config_catalog_observation as policy
import filedb_catalog as catalog
from test_native_1c_db_oracle_config_content_decode_reader import content_source,ABC_FIXED,EMPTY,DECLARATIONS
from test_native_1c_db_oracle_config_root_projection_reader import stored_literal,GUID,PREFIX
from test_native_1c_db_oracle_config_blob_chain_reader import row
A='22222222-2222-4222-8222-222222222222'
B='33333333-3333-4333-8333-333333333333'
G='9cd510cd-abfc-11d4-9434-004095e12fc7'
T='cf4abea6-37b2-11d4-940f-008048da11f9'

def target(*refs):
    return ('{0,0,1,{'+G+',{0,0,1,{'+T+','+str(len(refs))+','+','.join(refs)+'}}}}').encode()

def entries(*,refs=(A,),payload=ABC_FIXED,tail=(),target_bytes=None):
    return [(A.upper(),payload,0),('root',stored_literal(PREFIX+b'UNREAD\xff'),0),
        (GUID,stored_literal(target(*refs) if target_bytes is None else target_bytes),0),*tail]

def successful_source(**kwargs):return content_source(entries(**kwargs))
def profile():return core.ConfigCatalogReferenceProfile(DECLARATIONS,'0',0)

def read(source,**kwargs):
    return core.observe_config_catalog_references(source.read_at,source.size,profile=profile(),**kwargs)

class CatalogReferenceReaderTests(unittest.TestCase):
    def test_positive_finite_partial_observation(self):
        value=read(successful_source())
        self.assertEqual((value.catalog_collection_count,value.catalog_declared_count,
            value.catalog_resolved_count,value.catalog_positive_count),(1,1,1,1))
        self.assertEqual(value.completed_chain_count,3)
        self.assertEqual(value.root_suffix_validation,'not_performed')
        self.assertEqual(value.root_identity,'not_observed')
        self.assertNotIn(A,repr(asdict(value)));self.assertNotIn(GUID,repr(asdict(value)))
        self.assertNotIn('UNREAD',repr(asdict(value)))

    def test_one_graph_each_entry_once_and_same_parser_budget(self):
        readers=[];decoders=[];calls=[];budgets=[]
        init=core.CatalogReader.__init__; dec=core._ConfigContentDecoder.__init__
        chain=core._ConfigBlobChains.read; project=parser.project_catalog_references
        def ri(obj,*args,**kw):init(obj,*args,**kw);readers.append(obj)
        def di(obj,*args,**kw):dec(obj,*args,**kw);decoders.append(obj)
        def cr(obj,start,length):calls.append((id(obj),start));return chain(obj,start,length)
        def cp(data,**kw):budgets.append(kw['budget']);return project(data,**kw)
        with mock.patch.object(core.CatalogReader,'__init__',ri),mock.patch.object(core._ConfigContentDecoder,'__init__',di),mock.patch.object(core._ConfigBlobChains,'read',cr),mock.patch.object(parser,'project_catalog_references',cp):
            value=read(successful_source())
        self.assertEqual(len(readers),1);self.assertEqual(len(decoders),1)
        self.assertIs(budgets[0],readers[0]._budget);self.assertIs(budgets[0],decoders[0].budget)
        self.assertEqual([s for _,s in calls],[2,3,1]);self.assertEqual(len(set(i for i,_ in calls)),1)
        self.assertEqual(value.completed_chain_count,3)

    def test_candidate_physical_order_does_not_change_completion(self):
        rows=entries()
        for permutation in (rows,rows[::-1],rows[1:]+rows[:1]):
            value=read(content_source(permutation));self.assertEqual(value.catalog_positive_count,1)

    def test_multiple_generic_refs_but_owned_gate_exactly_one(self):
        source=successful_source(refs=(A,B),tail=((B,ABC_FIXED,0),))
        value=policy.read_projection(source.read_at,source.size,limits=catalog.CatalogLimits())
        self.assertEqual(value['catalog_positive_count'],2)
        with self.assertRaises(policy.OracleError):policy.validate_owned_projection(value)

    def test_missing_self_empty_and_duplicate_references(self):
        for source,code in ((successful_source(refs=(B,)),'config_catalog_reference_missing'),
            (successful_source(refs=(GUID,)),'config_catalog_self_reference'),
            (successful_source(payload=EMPTY),'config_catalog_content_empty'),
            (successful_source(refs=(A,A)),'config_catalog_prefix'),
            (successful_source(refs=()),'config_catalog_prefix')):
            with self.assertRaises(catalog.CatalogError) as ctx:read(source)
            self.assertEqual(ctx.exception.code,code)

    def test_no_substring_search_or_foreign_target_fallback(self):
        for data in (T.encode()+b','+A.encode(),b'{0,0,0,'+target(A)+b'}'):
            with self.assertRaises(core.InvalidStructure):read(successful_source(target_bytes=data))
        with self.assertRaises(core.UnsupportedLayout) as ctx:
            read(content_source(entries()[1:]+[('CONFIGSAVE.'+A,ABC_FIXED,0)]))
        self.assertEqual(ctx.exception.code,'config_catalog_reference_missing')

    def test_target_suffix_not_validated_but_transport_is(self):
        prefix=target(A).split(A.encode())[0]+A.encode()+b','
        for tail in (b'\xff',b'"unterminated',b'\x00',b'{{{'):
            self.assertEqual(read(successful_source(target_bytes=prefix+tail)).catalog_positive_count,1)
        rows=entries();rows[2]=(GUID,rows[2][1]+b'x',0)
        with self.assertRaises(core.InvalidStructure):read(content_source(rows))

    def test_every_selected_guard_precedes_parser(self):
        for name,part in (('x.new',0),('x_dynupdate_y',0),('x',1),(A,0)):
            with mock.patch.object(parser,'project_catalog_references',side_effect=AssertionError('too early')):
                with self.assertRaises(core.UnsupportedLayout):read(successful_source(tail=((name,ABC_FIXED,part),)))

    def test_late_failure_poisons_without_refund_or_partial_result(self):
        decoders=[];old=core._ConfigContentDecoder.__init__
        def init(obj,*args,**kw):old(obj,*args,**kw);decoders.append(obj)
        for source in (successful_source(target_bytes=b'PRIVATE'),
            successful_source(refs=(B,)),successful_source(payload=EMPTY),
            successful_source(tail=(('late',b'bad-deflate',0),))):
            with mock.patch.object(core._ConfigContentDecoder,'__init__',init):
                with self.assertRaises(catalog.CatalogError):read(source)
            decoder=decoders[-1];self.assertTrue(decoder.failed);self.assertTrue(decoder.chains.failed)
            counts=dict(decoder.budget.counts)
            with self.assertRaises(core.InvalidStructure):decoder.decode(ABC_FIXED,'raw_deflate')
            self.assertEqual(counts,decoder.budget.counts)

    def test_exact_shared_budgets_and_one_short(self):
        baseline=read(successful_source())
        for name in ('bytes_processed','output_bytes','tokens','read_bytes','page_reads'):
            amount=getattr(baseline.usage,name)
            self.assertEqual(read(successful_source(),catalog_limits=catalog.CatalogLimits(**{'max_'+name:amount})).usage,baseline.usage)
            with self.assertRaises(core.ResourceLimit):read(successful_source(),catalog_limits=catalog.CatalogLimits(**{'max_'+name:amount-1}))

    def test_last_output_charge_failure_also_poisons(self):
        baseline=read(successful_source());decoders=[];old=core._ConfigContentDecoder.__init__
        def init(obj,*args,**kw):old(obj,*args,**kw);decoders.append(obj)
        with mock.patch.object(core._ConfigContentDecoder,'__init__',init):
            with self.assertRaises(core.ResourceLimit):read(successful_source(),catalog_limits=catalog.CatalogLimits(max_output_bytes=baseline.usage.output_bytes-1))
        self.assertTrue(decoders[-1].failed);self.assertTrue(decoders[-1].chains.failed)

    def test_late_shared_chain_rejects_after_candidate_completion(self):
        source=content_source(entries(),trailing_rows=[row('later',start=1,length=len(ABC_FIXED))])
        with self.assertRaises(catalog.UnsupportedSharing) as ctx:read(source)
        self.assertEqual(ctx.exception.code,'config_chain_overlap')

    def test_parser_resource_failure_is_finite_and_poisons(self):
        decoders=[];old=core._ConfigContentDecoder.__init__
        def init(obj,*args,**kw):old(obj,*args,**kw);decoders.append(obj)
        with mock.patch.object(core._ConfigContentDecoder,'__init__',init):
            with self.assertRaises(core.ResourceLimit) as ctx:
                read(successful_source(refs=(A,B),tail=((B,ABC_FIXED,0),)),
                    reference_limits=parser.CatalogReferenceLimits(max_references=1))
        self.assertEqual(ctx.exception.code,'config_catalog_limits')
        self.assertTrue(decoders[-1].failed);self.assertTrue(decoders[-1].chains.failed)

    def test_existing_full_observer_is_exact_prefix(self):
        raw=(ROOT/'scripts/native_1c_db_oracle/config_framing_reader.py').read_text().split('\n\n# Explicit partial Catalog-reference prototype.')[0]
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(),
            'ad31309724b0494fa995b097039bff8eeda3c2a81f36b5349bcc453282af06b2')

    def test_literal_recipe_matches(self):
        self.assertEqual(profile().recipe(),policy.RECIPE_DESCRIPTION)
        self.assertEqual(profile().recipe_sha256,policy.RECIPE_SHA256)
        self.assertEqual(policy.RECIPE_SHA256,'af9381415545bae5adb0f8b06f81571806334212d98e944ab6987803360ca156')

if __name__=='__main__':unittest.main()

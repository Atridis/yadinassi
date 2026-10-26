"""Exact synthetic stored-byte transport; no native/compression/file evidence."""
from dataclasses import FrozenInstanceError, asdict, fields
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_framing_reader as core
from filedb_catalog import CatalogError, UnsupportedSharing
from test_native_1c_db_oracle_config_entry_reference_reader import (
    DECLARATIONS, P, RECIPE as ENTRY_RECIPE, row, source as entry_source, u32)

RECIPE=dict(ENTRY_RECIPE, identifier='config_blob_chain_8380_8192_v1',
    source_commit='d5e31816f4c9b11a445f73fc92d08803840ce599',
    chain_header='block256_next_u32le_at0_used_u16le_at4_payload_at6_v1',
    chain_termination='follow_until_zero_even_after_declared_length_v1',
    chain_length='exact_stored_length_stricter_local_hypothesis_v1',
    zero_used='allowed_intermediate_and_terminal_bounded_hops_v1',
    chain_ownership='table_blob_local_no_sharing_stricter_local_hypothesis_v1',
    phases='all_entry_prerequisites_then_all_selected_chains_v1',
    assembly='one_private_fixed_buffer_and_returned_copy_no_export_v1',
    chain_limits=(1048576,4194304,8192,32768),
    shared_limits=(100000,67108864,134217728,100000,1048576,1048576,16777216,
                   4096,65536,262144,64,65536,20,262144,33554432),
    budget_policy='intersect_remaining_shared_no_reset_refund_or_raise_v1',
    representation_weights=(192,2,128,128,3,128),image_bytes_ceiling=67108864,
    selected_part_zero_witness='completely_read_positive_stored_chain_required',
    compression='not_classified',file_assembly='not_run',root_identity='not_observed',
    applied_state='not_observed')
RECIPE_SHA256='e4d826310b61731e380156aaf2dc81e1a1bb342212f5a5f7596b30a51f1e6137'


def profile():return core.ConfigBlobChainProfile(DECLARATIONS,'0',0)


def source(rows=None, nodes=None, *, blob_length=None, **kwargs):
    """Independently built 256/6-byte blocks on nonadjacent reversed backing pages."""
    if nodes is None:nodes={1:(0,b'x')}
    if blob_length is None:blob_length=256*(max((1,*nodes))+1)
    if rows is None:rows=[row(marker=1),row('private',length=1)]
    v=entry_source(rows,blob_length=0,**kwargs)
    count=(blob_length+P-1)//P
    first=max(v.data_pages,default=10)+3
    v.blob_pages=list(reversed([first+2*i for i in range(count)]))
    v.page_count=max((20,*v.blob_pages))+1;v.size=v.page_count*P
    v.page(0)[12:16]=u32(v.page_count)
    h=v.page(8);h[16:24]=blob_length.to_bytes(8,'little');h[24:]=b'\xa5'*(P-24)
    for i,p in enumerate(v.blob_pages):
        h[24+4*i:28+4*i]=u32(p);v.page(p)[:]=b'\xb7'*P
    for index,node in nodes.items():
        if len(node)==2:following,payload=node;raw=u32(following)+len(payload).to_bytes(2,'little')+payload
        else:raw=node[2]
        offset=index*256;page,within=divmod(offset,P)
        if page<count:v.page(v.blob_pages[page])[within:within+len(raw)]=raw
    return v


def blob_calls(value):
    return [(a,n) for a,n in value.calls if a//P in value.blob_pages]


def primitive(value, *, limits=None, catalog_limits=None):
    reader=core.CatalogReader(value.read_at,value.size,limits=catalog_limits)
    table=reader.read_catalog().tables[0]
    reader._open_table_data(table)
    blob=reader._open_table_blob(table)
    return core._ConfigBlobChains(blob,limits or core.ConfigBlobChainLimits()),reader


def chain_nodes(payload,start=1):
    pieces=[payload[i:i+250] for i in range(0,len(payload),250)]
    return {start+i:(start+i+1 if i+1<len(pieces) else 0,p) for i,p in enumerate(pieces)}


class ConfigBlobChainCoreTests(unittest.TestCase):
    def read(self,value,**kwargs):
        return core.observe_config_blob_chains(value.read_at,value.size,profile=profile(),**kwargs)

    def test_independent_recipe_exact_profiles_and_lowerable_limits(self):
        p=profile();self.assertEqual(p.recipe(),RECIPE);self.assertEqual(p.recipe_sha256,RECIPE_SHA256)
        self.assertEqual(hashlib.sha256(json.dumps(RECIPE,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RECIPE_SHA256)
        self.assertEqual(tuple(getattr(core.CatalogLimits(),f.name) for f in fields(core.CatalogLimits)),RECIPE['shared_limits'])
        for kind in (core.ConfigFramingProfile,core.ConfigMarkerCensusProfile,core.ConfigZeroMarkerFilenameProfile,core.ConfigEntryReferenceProfile):
            with self.assertRaises(ValueError):core.observe_config_blob_chains(lambda a,n:b'',0,profile=kind(DECLARATIONS,'0',0))
        for key in ('limits','chain_limits','catalog_limits'):
            with self.assertRaises(ValueError):self.read(source(),**{key:{}})
        for key,ceiling in zip(('max_chain_bytes','max_total_bytes','max_chain_hops','max_total_hops'),(1048576,4194304,8192,32768)):
            for value in (False,0,-1,ceiling+1,1.0,'1'):
                with self.assertRaises(ValueError):core.ConfigBlobChainLimits(**{key:value})
        with self.assertRaises(FrozenInstanceError):p.identifier='x'
        for f in fields(core.CatalogLimits):
            defaults=core.CatalogLimits(); raised=getattr(defaults,f.name)+1
            v=source()
            with self.assertRaises(ValueError):self.read(v,catalog_limits=core.CatalogLimits(**{f.name:raised}))
            self.assertEqual(v.calls,[])

    def test_exact_private_bytes_single_partial_full_mixed_and_nonmonotonic(self):
        for payload in (b'x',bytes(range(250)),bytes(range(256))*3):
            nodes=chain_nodes(payload);v=source(nodes=nodes,rows=[row(marker=1),row('x',length=len(payload))])
            store,_=primitive(v);actual,hops,zeros=store.read(1,len(payload))
            self.assertEqual(actual,payload);self.assertEqual(hops,len(nodes));self.assertEqual(zeros,0)
            self.assertEqual([n for a,n in blob_calls(v)],sum(([6,len(p)] for _,p in nodes.values()),[]))
        nodes={8:(2,b'abc'),2:(7,b'd'),7:(0,b'ef')};v=source(nodes=nodes)
        store,_=primitive(v);self.assertEqual(store.read(8,6),(b'abcdef',3,0))

    def test_page31_to32_shuffled_pages_and_last_valid_block(self):
        v=source(nodes={31:(32,b'ab'),32:(1,b'c'),1:(0,b'd')})
        store,_=primitive(v);self.assertEqual(store.read(31,4),(b'abcd',3,0))
        self.assertIn((v.blob_pages[0]*P+31*256,6),v.calls)
        self.assertIn((v.blob_pages[1]*P,6),v.calls)
        self.assertNotEqual(v.blob_pages[1],v.blob_pages[0]+1)
        v=source(nodes={63:(0,b'last')});store,_=primitive(v)
        self.assertEqual(store.read(63,4)[0],b'last')

    def test_zero_used_intermediate_terminal_and_after_exact_length(self):
        for nodes,expected in (({1:(2,b''),2:(0,b'x')},(b'x',2,1)),
                               ({1:(2,b'x'),2:(0,b'')},(b'x',2,1)),
                               ({1:(2,b''),2:(3,b'x'),3:(0,b'')},(b'x',3,2))):
            v=source(nodes=nodes);store,_=primitive(v);self.assertEqual(store.read(1,1),expected)
            self.assertEqual([n for _,n in blob_calls(v)].count(6),len(nodes))
            self.assertEqual([n for _,n in blob_calls(v)].count(1),1)
            self.assertFalse(any(n==0 or n==256 for _,n in blob_calls(v)))

    def test_explicit_little_endian_unsigned_used_and_invalid_next(self):
        for used in (251,32768,65535):
            v=source(nodes={1:(None,None,u32(0)+used.to_bytes(2,'little'))})
            with self.assertRaisesRegex(core.InvalidStructure,'config_chain_used'):self.read(v)
            self.assertEqual([n for _,n in blob_calls(v)],[6])
        for following in (2,2**32-1):
            with self.assertRaisesRegex(core.InvalidStructure,'config_chain_next'):
                self.read(source(nodes={1:(following,b'x')}))
        for raw in ((1).to_bytes(4,'big')+b'\x01\x00',u32(0)+(1).to_bytes(2,'big')):
            with self.assertRaises(core.InvalidStructure):self.read(source(nodes={1:(None,None,raw)}))

    def test_short_header_payload_and_nonbytes_do_not_retry(self):
        for request in (6,1):
            v=source();good=v.read_at
            def short(a,n):
                result=good(a,n)
                return result[:-1] if a//P in v.blob_pages and n==request else result
            with self.assertRaisesRegex(core.InvalidStructure,'inexact_read'):
                core.observe_config_blob_chains(short,v.size,profile=profile())
        v=source();store,_=primitive(v)
        with self.assertRaisesRegex(core.InvalidStructure,'config_chain_length'):store.read(1,2)
        calls=list(v.calls);owned=set(store.owners);usage=store.budget.usage()
        with self.assertRaisesRegex(core.InvalidStructure,'config_chain_failed_attempt'):store.read(1,1)
        self.assertEqual(v.calls,calls);self.assertEqual(store.owners,owned);self.assertEqual(store.budget.usage(),usage)

    def test_exact_length_mismatch_and_no_payload_read_on_excess(self):
        for nodes,length in (({1:(0,b'x')},2),({1:(0,b'ab')},1),({1:(2,b'x'),2:(0,b'y')},1)):
            v=source(nodes=nodes);store,_=primitive(v)
            with self.assertRaisesRegex(core.InvalidStructure,'config_chain_length'):store.read(1,length)
            if length==1:self.assertFalse(any(n==2 for _,n in blob_calls(v)))
            if len(nodes)==2:self.assertEqual([n for _,n in blob_calls(v)],[6,1,6])

    def test_cycles_even_after_length_or_in_zero_used_nodes(self):
        for nodes in ({1:(1,b'x')},{1:(2,b'x'),2:(3,b''),3:(2,b'')},
                      {1:(2,b''),2:(1,b'')},{1:(1,b'')}):
            with self.assertRaisesRegex(core.InvalidStructure,'config_chain_cycle'):self.read(source(nodes=nodes))

    def test_sharing_identical_conflicting_starts_and_suffix_merge(self):
        for first,second,nodes in ((1,1,{1:(0,b'x')}),(1,2,{1:(3,b'a'),2:(3,b'b'),3:(0,b'c')})):
            v=source(nodes=nodes);store,_=primitive(v)
            length=1 if first==second else 2;store.read(first,length)
            with self.assertRaisesRegex(UnsupportedSharing,'config_chain_overlap'):store.read(second,length)
        v=source();store,_=primitive(v);store.read(1,1)
        with self.assertRaisesRegex(UnsupportedSharing,'config_chain_overlap'):store.read(1,2)
        # Same physical page is not sharing, nor root logical index 2 vs table 2.
        v=source(nodes={1:(0,b'a'),2:(0,b'b')});store,_=primitive(v)
        self.assertEqual(store.read(1,1)[0],b'a');self.assertEqual(store.read(2,1)[0],b'b')

    def test_invalid_start_length_types_alignment_and_bounds(self):
        for start,length in ((0,1),(-1,1),(2,1),(False,1),(1,False),(1,0),(1,-1),(1,1.0)):
            v=source();store,_=primitive(v)
            with self.assertRaisesRegex(core.InvalidStructure,'config_chain_reference'):store.read(start,length)
            self.assertEqual(blob_calls(v),[])
        for length in (1,255,257,511,513):
            with self.assertRaisesRegex(core.InvalidStructure,'config_blob_alignment'):self.read(source(blob_length=length))
        for length in (0,256):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_blob_capacity'):self.read(source(blob_length=length))

    def test_two_phases_last_prerequisite_prevents_any_chain_read(self):
        for last in (row('bad',part=4096),row('bad',length=251),row(raw=b'\0\xd8',units=1,start=0)):
            v=source(rows=[row(marker=1),row('good'),last])
            with self.assertRaises(CatalogError):self.read(v)
            self.assertEqual(blob_calls(v),[])
        v=source(rows=[row(marker=1),row('good',start=1),row('last',start=2)],nodes={1:(0,b'x'),2:(0,b'')})
        with self.assertRaisesRegex(core.InvalidStructure,'config_chain_length'):self.read(v)
        self.assertEqual([n for _,n in blob_calls(v)],[6,1,6])

    def test_all_selected_chains_counter_witness_and_no_private_export(self):
        v=source(rows=[row(marker=1),row('PRIVATE_Ω',start=1,length=3),row('same',start=2,length=1,part=7),
                       row('',start=99,length=99,part_raw=b'\xff'*6),row('excluded',start=0,part_raw=b'\xff'*6),
                       b'\xff'+b'\xff'*300],nodes={1:(3,b'ab'),3:(4,b'c'),4:(0,b''),2:(0,b'z')})
        r=self.read(v)
        self.assertEqual((r.completed_chain_count,r.total_stored_bytes_read,r.total_chain_blocks,r.maximum_chain_hops,
                          r.multi_block_chain_count,r.zero_payload_block_count),(2,4,4,3,1,1))
        self.assertEqual((r.selected_part_zero_count,r.selected_part_nonzero_count),(1,1))
        self.assertEqual(r.chain_validation,'selected_zero_terminated_exact_stored_length')
        self.assertEqual((r.compression_validation,r.file_identity,r.applied_state,r.native_acceptance),
                         ('not_classified','not_observed','not_observed','pending'))
        raw=repr(asdict(r));self.assertNotIn('PRIVATE',raw);self.assertNotIn('Ω',raw)
        self.assertFalse({'payload','names','pointers','parts','lengths','block_indices','positions','payload_hash'} & set(asdict(r)))
        self.assertFalse(v.closed)
        with self.assertRaises(FrozenInstanceError):r.completed_chain_count=0
        for rows in ([row(marker=1),row('x',part=1)],[row(marker=1),row('',part=0)],[row(marker=1),row('x',start=0)]):
            v=source(rows=rows)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_reference_no_part_zero_witness'):self.read(v)
            self.assertEqual(blob_calls(v),[])

    def test_selected_duplicate_part_numbers_are_not_grouped(self):
        v=source(rows=[row(marker=1),row('same',start=1),row('same',start=2)],nodes={1:(0,b'a'),2:(0,b'b')})
        self.assertEqual(self.read(v).completed_chain_count,2)

    def test_shared_budget_intersection_after_catalog_and_scan_without_reset(self):
        v=source(nodes={1:(2,b'x'),2:(0,b'')});r=self.read(v)
        for key in ('page_reads','read_bytes','bytes_processed','blob_visits','total_blob_bytes','output_bytes'):
            used=getattr(r.usage,key)
            self.read(source(nodes={1:(2,b'x'),2:(0,b'')}),catalog_limits=core.CatalogLimits(**{'max_'+key:used}))
            with self.assertRaises(core.ResourceLimit):
                self.read(source(nodes={1:(2,b'x'),2:(0,b'')}),catalog_limits=core.CatalogLimits(**{'max_'+key:used-1}))
        # Root+selected data+BLOB maps use three pages, one shared role graph.
        self.read(source(),catalog_limits=core.CatalogLimits(max_mapping_pages=3))
        v=source()
        with self.assertRaisesRegex(core.ResourceLimit,'mapping_pages'):self.read(v,catalog_limits=core.CatalogLimits(max_mapping_pages=2))
        self.assertEqual(blob_calls(v),[])
        # Lower total stored bytes to prerequisite usage; even one byte cannot fit.
        old=core.observe_config_entry_references(source().read_at,source().size,profile=core.ConfigEntryReferenceProfile(DECLARATIONS,'0',0))
        with self.assertRaisesRegex(core.ResourceLimit,'total_blob_bytes'):
            self.read(source(),catalog_limits=core.CatalogLimits(max_total_blob_bytes=old.usage.total_blob_bytes))

    def test_reserve_before_buffer_read_owner_insert_and_no_refund(self):
        v=source();store,_=primitive(v)
        remaining=store.budget.limits.max_output_bytes-store.budget.counts['output_bytes']
        store.budget.charge('output_bytes',remaining-2)
        with mock.patch.object(core,'bytearray',side_effect=AssertionError('allocation before budget'),create=True):
            with self.assertRaisesRegex(core.ResourceLimit,'output_bytes'):store.read(1,1)
        self.assertEqual(blob_calls(v),[]);self.assertEqual(store.owners,set())
        v=source();store,_=primitive(v)
        # length reservation258 + first visited128 leaves no global owner allowance.
        remaining=store.budget.limits.max_output_bytes-store.budget.counts['output_bytes']
        store.budget.charge('output_bytes',remaining-386)
        with self.assertRaisesRegex(core.ResourceLimit,'output_bytes'):store.read(1,1)
        self.assertEqual(blob_calls(v),[]);self.assertEqual(store.owners,set())
        self.assertEqual(store.total_bytes,1);self.assertEqual(store.total_hops,1)

    def test_chain_and_total_limits_boundaries_and_plus_one_before_reads(self):
        for key,limit,nodes,length,code in (
            ('max_chain_bytes',1,{1:(0,b'ab')},2,'config_chain_bytes'),
            ('max_total_bytes',1,{1:(0,b'ab')},2,'config_chain_total_bytes'),
            ('max_chain_hops',1,{1:(2,b'x'),2:(0,b'')},1,'config_chain_hops'),
            ('max_total_hops',1,{1:(2,b'x'),2:(0,b'')},1,'config_chain_total_hops')):
            v=source(nodes=nodes);store,_=primitive(v,limits=core.ConfigBlobChainLimits(**{key:limit}))
            with self.assertRaisesRegex(core.ResourceLimit,code):store.read(1,length)
            self.assertEqual(len(blob_calls(v)),0 if key.endswith('bytes') else 2)
        nodes={1:(0,b'a'),2:(0,b'b')}
        for key in ('max_total_bytes','max_total_hops'):
            v=source(nodes=nodes);store,_=primitive(v,limits=core.ConfigBlobChainLimits(**{key:1}))
            self.assertEqual(store.read(1,1)[0],b'a');before=list(v.calls)
            with self.assertRaises(core.ResourceLimit):store.read(2,1)
            self.assertEqual(v.calls,before)
        v=source(nodes=nodes);store,_=primitive(v,limits=core.ConfigBlobChainLimits(1,2,1,2))
        store.read(1,1);store.read(2,1);self.assertEqual((store.total_bytes,store.total_hops),(2,2))

    def test_hard_chain_bytes_and_hops_boundaries(self):
        payload=bytes(range(256))*4096
        v=source(nodes=chain_nodes(payload));store,_=primitive(v)
        self.assertEqual(store.read(1,len(payload))[0],payload)
        v=source();store,_=primitive(v)
        with self.assertRaisesRegex(core.ResourceLimit,'config_chain_bytes'):store.read(1,1048577)
        self.assertEqual(blob_calls(v),[])
        for count in (8192,8193):
            nodes={i:(i+1 if i<count else 0,b'x' if i==1 else b'') for i in range(1,count+1)}
            v=source(nodes=nodes);store,_=primitive(v)
            if count==8192:self.assertEqual(store.read(1,1),(b'x',8192,8191))
            else:
                with self.assertRaisesRegex(core.ResourceLimit,'config_chain_hops'):store.read(1,1)
            self.assertEqual(len(blob_calls(v)),8193)

    def test_hard_total_bytes_and_hops_boundaries_across_small_chains(self):
        payload=b'z'*1048576;nodes={};starts=[];start=1
        for _ in range(4):
            starts.append(start);part=chain_nodes(payload,start);nodes.update(part);start=max(part)+1
        nodes[start]=(0,b'q');v=source(nodes=nodes);store,_=primitive(v)
        for s in starts:self.assertEqual(store.read(s,len(payload))[0],payload)
        self.assertEqual(store.total_bytes,4194304)
        with self.assertRaisesRegex(core.ResourceLimit,'config_chain_total_bytes'):store.read(start,1)
        nodes={};starts=[]
        for chain in range(4):
            start=1+chain*8192;starts.append(start)
            for i in range(start,start+8192):nodes[i]=(i+1 if i<start+8191 else 0,b'x' if i==start else b'')
        nodes[32769]=(0,b'y');v=source(nodes=nodes);store,_=primitive(v)
        for s in starts:self.assertEqual(store.read(s,1),(b'x',8192,8191))
        self.assertEqual(store.total_hops,32768)
        with self.assertRaisesRegex(core.ResourceLimit,'config_chain_total_hops'):store.read(32769,1)

    def test_every_slot_selected_bound_and_no_new_image_allowance(self):
        nodes={i:(0,b'x') for i in range(1,4096)}
        v=source(rows=[row(marker=1)]+[row('a',start=i) for i in range(1,4096)],nodes=nodes)
        r=self.read(v);self.assertEqual((r.completed_chain_count,r.total_chain_blocks),(4095,4095))
        calls=[]
        with self.assertRaisesRegex(core.ResourceLimit,'config_chain_image_bytes'):
            core.observe_config_blob_chains(lambda a,n:calls.append((a,n)),67108865,profile=profile())
        self.assertEqual(calls,[])

    def test_cold_stdlib_only_complete_observation(self):
        code=('import sys,json,dataclasses;sys.path[:0]=sys.argv[1:];import config_framing_reader as c;raw=sys.stdin.buffer.read();'
              'p=c.ConfigBlobChainProfile(c.DECLARATIONS,"0",0);o=c.observe_config_blob_chains(lambda a,n:raw[a:a+n],len(raw),profile=p);'
              'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);print(json.dumps(dataclasses.asdict(o),sort_keys=True))')
        v=source(nodes={1:(2,b'x'),2:(0,b'')})
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')],
                              input=v.full_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout),asdict(self.read(v)))

if __name__=='__main__':unittest.main()

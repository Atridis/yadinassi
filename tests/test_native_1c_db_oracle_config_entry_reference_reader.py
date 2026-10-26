"""Synthetic entry prerequisites; never native file, chain or applied-state evidence."""
from dataclasses import FrozenInstanceError, asdict, replace
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
from filedb_catalog import CatalogError
from test_native_1c_db_oracle_config_framing_reader import DECLARATIONS,P,u32,row as base_row,source as base_source

RECIPE={'identifier':'config_entry_reference_8380_8192_v1','declarations':DECLARATIONS,
    'recordlock':'0','format_item':0,'candidate_stride':301,'filename_offset':1,'filename_width':258,
    'first_marker':'one_reserved_opaque_v1','later_selection':'zero_validate_nonzero_opaque_v1',
    'filename':'u16le_units_at_most_128_strict_utf16le_v1','selection':'CONFIG_ascii_case_only_no_fallback_v1',
    'binarydata_offset':287,'binarydata_width':8,'partno_offset':295,'partno_width':6,
    'reference':'u32le_start_length_both_positive_nonempty_name_v1',
    'locator':'aligned_256_start_in_range_length_at_most_250_capacity_v1',
    'partno':'positive_sign1_ten_decimal_digits_pad0_at_most_4095_v1',
    'empty_data':'unsupported','selected_part_zero_witness':'required','framing':'not_accepted'}
RECIPE_SHA256=hashlib.sha256(json.dumps(RECIPE,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def profile():return core.ConfigEntryReferenceProfile(DECLARATIONS,'0',0)

def partno(value):
    return bytes.fromhex('1'+f'{value:010d}'+'0')

def row(name='', *, start=1,length=1,part=0,reference=None,part_raw=None,**kwargs):
    value=bytearray(base_row(name,**kwargs))
    value[287:295]=u32(start)+u32(length) if reference is None else reference
    value[295:301]=partno(part) if part_raw is None else part_raw
    return bytes(value)

def source(rows=None,**kwargs):
    if rows is None: rows=[row(marker=1),row('private_filename_Ω')]
    kwargs.setdefault('blob_length',512)
    return base_source(rows,**kwargs)

class ConfigEntryReferenceCoreTests(unittest.TestCase):
    def read(self,value,**kwargs):return core.observe_config_entry_references(value.read_at,value.size,profile=profile(),**kwargs)

    def test_exact_independent_recipe_and_required_profile(self):
        p=profile();self.assertEqual(p.recipe(),RECIPE);self.assertEqual(p.recipe_sha256,RECIPE_SHA256)
        self.assertEqual((p.binarydata_offset,p.binarydata_width,p.partno_offset,p.partno_width),(287,8,295,6))
        for lock,form in ((0,0),('1',0),('0',False),('0','0'),('0',1)):
            with self.assertRaises(ValueError):core.ConfigEntryReferenceProfile(DECLARATIONS,lock,form)
        for ds in (list(DECLARATIONS),DECLARATIONS[:-1],(list(DECLARATIONS[0]),*DECLARATIONS[1:]),(('FILENAME','NVC',False,128,0,'CI'),*DECLARATIONS[1:])):
            with self.assertRaises(ValueError):core.ConfigEntryReferenceProfile(ds,'0',0)
        with self.assertRaises(FrozenInstanceError):p.candidate_stride=1
        p.recipe()['partno_offset']=0;self.assertEqual(p.partno_offset,295)
        for wrong in (None,core.ConfigFramingProfile(DECLARATIONS,'0',0),core.ConfigMarkerCensusProfile(DECLARATIONS,'0',0),core.ConfigZeroMarkerFilenameProfile(DECLARATIONS,'0',0)):
            with self.assertRaises(ValueError):core.observe_config_entry_references(lambda a,n:b'',0,profile=wrong)

    def test_all256_markers_and_opaque_reserved_nonzero_payload(self):
        v=source([b'\x01'+b'\xff'*300,row('x')]+[bytes([i])+b'\xff'*300 for i in range(1,256)])
        r=self.read(v)
        self.assertEqual((r.candidate_slots,r.later_zero_count,r.later_one_count,r.later_other_count),(257,1,1,254))
        for i in range(2,257):
            off=301*i;physical=v.data_pages[off//P]*P+off%P
            self.assertIn((physical,1),v.calls)
            self.assertFalse(any(a<=physical+1<a+n for a,n in v.calls))
        self.assertEqual((r.selected_reference_count,r.selected_part_zero_count),(1,1))
        self.assertEqual((r.framing_validation,r.locator_validation,r.partno_validation,r.native_acceptance),('not_accepted','selected_capacity_bounds_only','selected_canonical_bcd_0_4095','pending'))
        self.assertFalse({'filenames','positions','pointers','lengths','filename_hash'} & set(asdict(r)))

    def test_reference_then_empty_exclusions_conserve_counts_and_part_opaque(self):
        poison=b'\xff'*6
        rows=[row(marker=1),row('selected'),row('selected2',part=4095),row('',part_raw=poison),
              row('either',start=0,part_raw=poison),row('either',length=0,part_raw=poison),row('',start=0,length=0,part_raw=poison)]
        v=source(rows);r=self.read(v)
        self.assertEqual((r.validated_zero_count,r.empty_filenames,r.nonempty_filenames),(6,2,4))
        self.assertEqual((r.selected_reference_count,r.reference_excluded_count,r.empty_name_excluded_count,r.selected_part_zero_count,r.selected_part_nonzero_count),(2,3,1,1,1))
        for i in range(3,7):
            off=10*P+i*301+295
            self.assertFalse(any(a<=off<a+n for a,n in v.calls))
        self.assertFalse(any(v.blob_page*P<=a<(v.blob_page+1)*P for a,n in v.calls))
        self.assertFalse(v.closed)

    def test_all_zero_names_must_validate_even_if_reference_excluded(self):
        for start,length in ((0,0),(0,1),(1,0)):
            for raw,units,code in ((b'',129,'config_filename_length'),(b'\0\xd8',1,'config_filename_encoding')):
                with self.assertRaisesRegex(CatalogError,code):self.read(source([row(marker=1),row('valid'),row(raw=raw,units=units,start=start,length=length)]))

    def test_lengths_unicode_and_no_identity_normalization(self):
        names=['','x','x'*127,'x'*128,'x'*126+'😀','PRIVATE_Ω','\0\ufeff']
        r=self.read(source([row(marker=1)]+[row(n) for n in names]))
        self.assertEqual((r.validated_zero_count,r.empty_filenames,r.nonempty_filenames,r.max_filename_units),(7,1,6,128))
        self.assertNotIn('PRIVATE',repr(r));self.assertNotIn('Ω',repr(r))
        self.assertEqual((r.selected_reference_count,r.empty_name_excluded_count),(6,1))
        with self.assertRaises(FrozenInstanceError):r.selected_reference_count=0

    def test_reference_capacity_boundaries_reversed_endian_and_no_blob_reads(self):
        for blob_length,start,length in ((512,1,1),(512,1,250),(768,2,500),(8192,31,7750)):
            v=source([row(marker=1),row('yes',start=start,length=length)],blob_length=blob_length)
            self.assertEqual(self.read(v).selected_reference_count,1)
            self.assertFalse(any(v.blob_page*P<=a<(v.blob_page+1)*P for a,n in v.calls))
        for start,length in ((2,1),(2**32-1,1),(1,251),(1,2**32-1)):
            with self.assertRaisesRegex(core.InvalidStructure,'config_reference_bounds'):
                self.read(source([row(marker=1),row('bad',start=start,length=length)]))
        for reference in ((1).to_bytes(4,'big')+u32(1),u32(1)+(1).to_bytes(4,'big')):
            with self.assertRaisesRegex(core.InvalidStructure,'config_reference_bounds'):
                self.read(source([row(marker=1),row('bad',reference=reference)]))
        # Positive but out-of-range reference on an empty name is not selected.
        self.assertEqual(self.read(source([row(marker=1),row('yes'),row('',start=2**32-1,length=2**32-1,part_raw=b'\xff'*6)])).empty_name_excluded_count,1)

    def test_blob_alignment_and_minimum_capacity(self):
        for length in (1,255,257,511,513):
            with self.assertRaisesRegex(core.InvalidStructure,'config_blob_alignment'):self.read(source(blob_length=length))
        for length in (0,256):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_blob_capacity'):self.read(source(blob_length=length))

    def test_every_part_sign_digit_padding_invalid_and_resource_limit(self):
        valid=partno(0)
        for sign in range(16):
            if sign==1:continue
            raw=bytes([(sign<<4)|(valid[0]&15)])+valid[1:]
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_partno_encoding'):self.read(source([row(marker=1),row('yes'),row('bad',part_raw=raw)]))
        for index in range(1,11):
            for digit in range(10,16):
                raw=bytearray(valid);shift=4 if index%2==0 else 0;raw[index//2]|=digit<<shift
                with self.assertRaisesRegex(core.UnsupportedLayout,'config_partno_encoding'):self.read(source([row(marker=1),row('yes'),row('bad',part_raw=bytes(raw))]))
        for padding in range(1,16):
            raw=valid[:-1]+bytes([padding])
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_partno_encoding'):self.read(source([row(marker=1),row('yes'),row('bad',part_raw=raw)]))
        for part in (4096,9999999999):
            with self.assertRaisesRegex(core.ResourceLimit,'config_partno_limit'):self.read(source([row(marker=1),row('yes'),row('bad',part=part)]))
        self.assertEqual(self.read(source([row(marker=1)]+[row('same',part=p) for p in (0,1,9,10,999,4095)])).selected_part_nonzero_count,5)

    def test_positive_selected_part_zero_witness_not_empty_or_excluded(self):
        for rows in ([row(marker=1)],[row(marker=1),row('')],[row(marker=1),row('x',part=1)],
                     [row(marker=1),row('x',part=1),row('excluded',start=0,part=0)],
                     [row(marker=1),row('x',part=1),row('',part=0)],
                     [row(marker=1),row('x',marker=255)]):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_reference_no_part_zero_witness'):self.read(source(rows))

    def test_last_selected_failure_never_skipped_or_partial_success(self):
        for last,code in ((row('last',length=251),'config_reference_bounds'),(row('last',part_raw=b'\xff'*6),'config_partno_encoding'),(row('last',part=4096),'config_partno_limit')):
            with self.assertRaisesRegex(CatalogError,code):self.read(source([row(marker=1),row('good'),row(marker=255),last]))
        for offset in (602,603,605,889,897):
            v=source([row(marker=1),row('valid'),row('last')])
            def bad(a,n):return b'' if a==10*P+offset else v.read_at(a,n)
            with self.assertRaises(CatalogError):core.observe_config_entry_references(bad,v.size,profile=profile())

    def test_exact_reads_and_cross_page_fields(self):
        v=source([row(marker=1),row('abc'),row(raw=b'\0\xd8',units=65535,marker=1)]);self.read(v)
        self.assertEqual([x for x in v.calls if x[0]>=10*P],[(10*P,1),(10*P+301,1),(10*P+302,2),(10*P+304,6),(10*P+588,8),(10*P+596,6),(10*P+602,1)])
        v=source([row(marker=1)]+[row('a')]*26+[row('x'*128)]);self.assertEqual(self.read(v).max_filename_units,128)
        self.assertIn((10*P+8130,62),v.calls);self.assertIn((11*P,194),v.calls)
        # Independently calculated crossing candidates: reference625, PARTNO1006.
        v=source([row(marker=1)]+[row('a')]*4095);r=self.read(v)
        self.assertEqual(r.selected_reference_count,4095)
        self.assertIn(((10+22)*P+8188,4),v.calls)
        self.assertIn(((10+23)*P,4),v.calls)
        self.assertIn(((10+36)*P+8189,3),v.calls)
        self.assertIn(((10+37)*P,3),v.calls)

    def test_variable_counts_caps_and_cumulative_budgets(self):
        for count in (2,3,7,16,29,4096):
            r=self.read(source([row(marker=1),row('a')]+[row(marker=255)]*(count-2)))
            self.assertEqual((r.candidate_slots,r.selected_reference_count),(count,1))
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):self.read(source([row(marker=1),row('a')]+[row(marker=255)]*4095))
        v=source()
        with self.assertRaisesRegex(core.ResourceLimit,'config_record_bytes'):self.read(v,limits=core.ConfigFramingLimits(max_record_bytes=300))
        self.assertEqual(v.calls,[])
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):self.read(source(),limits=core.ConfigFramingLimits(max_slots=1))
        for key in ('limits','catalog_limits'):
            with self.assertRaises(ValueError):self.read(source(),**{key:{}})
        r=self.read(source())
        for key,used in [('max_output_bytes',r.usage.output_bytes),('max_bytes_processed',r.usage.bytes_processed),('max_read_bytes',r.usage.read_bytes)]:
            with self.assertRaises(core.ResourceLimit):self.read(source(),catalog_limits=core.CatalogLimits(**{key:used-1}))

    def test_selection_schema_ownership_and_reserved_gates(self):
        for name in ('CONFIG','config','CoNfIg'):self.assertEqual(self.read(source(table_name=name)).target,'CONFIG')
        for name in ('CONFIGSAVE','PARAMS','CONFIG ','CОNFIG','CONFIG\0'):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_missing'):self.read(source(table_name=name))
        for changes in ({'lock':'1'},{'format_item':'0'},{'format_item':1},{'declarations':DECLARATIONS[:-1]}):
            v=source(**changes)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_profile_mismatch'):self.read(v)
            self.assertNotIn((5*P,P),v.calls);self.assertNotIn((8*P,P),v.calls)
        original=core.CatalogReader.read_catalog
        def duplicate(reader):
            c=original(reader);return replace(c,tables=(*c.tables,replace(c.tables[0],name='config')))
        with mock.patch.object(core.CatalogReader,'read_catalog',duplicate):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_ambiguous'):self.read(source())
        for marker in (0,2,255):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_reserved_slot'):self.read(source([row(marker=marker),row('yes')]))
        for mutation in (lambda v:v.page(8).__setitem__(slice(0,2),b'xx'),lambda v:v.page(8).__setitem__(slice(24,28),u32(10)),lambda v:v.page(8).__setitem__(slice(24,28),u32(9))):
            v=source();mutation(v)
            with self.assertRaises(CatalogError):self.read(v)
        for raw,code in ((b'','config_empty_data'),(bytes(300),'config_record_length'),(bytes(302),'config_record_length')):
            with self.assertRaisesRegex(CatalogError,code):self.read(source(raw=raw))

    def test_old_profiles_unchanged_and_datasize_opaque(self):
        for name,digest in (('ConfigFramingProfile','48fc146c1e748b877b518993d09e7050f4c57cd6cd8682596f97411655c4a7e3'),('ConfigMarkerCensusProfile','a73b1d173b65726fd0d06a09bab112e0ab287fc9206f289538ce7169d93d80ba'),('ConfigZeroMarkerFilenameProfile','8de171031a518dc9ac6446dd9425118be1d1d7151ff87607b93086cd924e8d4b')):
            self.assertEqual(getattr(core,name)(DECLARATIONS,'0',0).recipe_sha256,digest)
        v=source([row(marker=1),row('okay'),row(marker=255)])
        with self.assertRaisesRegex(core.UnsupportedLayout,'config_nonreserved_slot'):core.observe_config_framing(v.read_at,v.size,profile=core.ConfigFramingProfile(DECLARATIONS,'0',0))
        # DATASIZE, date, attributes and padding all contain poison from base_row.
        r=self.read(v);self.assertEqual(r.selected_reference_count,1)
        for a,n in v.calls:
            self.assertFalse(a<10*P+588 and a+n>10*P+560)

    def test_cold_stdlib_only(self):
        code=('import sys,json,dataclasses;sys.path[:0]=sys.argv[1:];import config_framing_reader as c;raw=sys.stdin.buffer.read();p=c.ConfigEntryReferenceProfile(c.DECLARATIONS,"0",0);o=c.observe_config_entry_references(lambda a,n:raw[a:a+n],len(raw),profile=p);assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);print(json.dumps(dataclasses.asdict(o),sort_keys=True))')
        v=source([row(marker=1),row('bounded'),row(marker=255)])
        r=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')],input=v.full_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),asdict(self.read(v)))

if __name__=='__main__':unittest.main()

"""Synthetic field-only hypothesis tests; no native or active-file acceptance."""
from dataclasses import FrozenInstanceError,asdict,replace
import hashlib,json,subprocess,sys,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_framing_reader as core
from filedb_catalog import CatalogError
from test_native_1c_db_oracle_config_framing_reader import DECLARATIONS,source,row,P,u32

def profile():return core.ConfigZeroMarkerFilenameProfile(DECLARATIONS,'0',0)

class ConfigZeroMarkerFilenameCoreTests(unittest.TestCase):
    def read(self,value,**kwargs):
        return core.observe_config_zero_marker_filenames(value.read_at,value.size,profile=profile(),**kwargs)

    def test_independent_exact_recipe(self):
        p=profile();expected={'identifier':'config_zero_marker_filename_8380_8192_v1','declarations':DECLARATIONS,
            'recordlock':'0','format_item':0,'candidate_stride':301,'filename_offset':1,'filename_width':258,
            'first_marker':'one_reserved_opaque_v1','later_selection':'zero_validate_nonzero_opaque_v1',
            'filename':'u16le_units_at_most_128_strict_utf16le_v1',
            'selection':'CONFIG_ascii_case_only_no_fallback_v1','empty_data':'unsupported',
            'nonempty_witness':'required','framing':'not_accepted'}
        self.assertEqual(p.recipe(),expected)
        self.assertEqual(p.recipe_sha256,hashlib.sha256(json.dumps(expected,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(p.recipe_sha256,'8de171031a518dc9ac6446dd9425118be1d1d7151ff87607b93086cd924e8d4b')
        for lock,form in ((0,0),('1',0),('0',False),('0','0'),('0',1)):
            with self.assertRaises(ValueError):core.ConfigZeroMarkerFilenameProfile(DECLARATIONS,lock,form)
        for ds in (list(DECLARATIONS),DECLARATIONS[:-1],(list(DECLARATIONS[0]),*DECLARATIONS[1:]),(('FILENAME','NVC',False,128,0,'CI'),*DECLARATIONS[1:])):
            with self.assertRaises(ValueError):core.ConfigZeroMarkerFilenameProfile(ds,'0',0)
        with self.assertRaises(FrozenInstanceError):p.candidate_stride=1
        p.recipe()['filename_width']=1;self.assertEqual(p.filename_width,258)
        for wrong in (None,core.ConfigFramingProfile(DECLARATIONS,'0',0),core.ConfigMarkerCensusProfile(DECLARATIONS,'0',0)):
            with self.assertRaises(ValueError):core.observe_config_zero_marker_filenames(lambda a,n:b'',0,profile=wrong)

    def test_all256_markers_nonzero_fields_opaque(self):
        value=source([b'\x01'+b'\xff'*300,row('x')]+[bytes([i])+b'\xff'*300 for i in range(1,256)])
        r=self.read(value)
        self.assertEqual((r.candidate_slots,r.later_zero_count,r.later_one_count,r.later_other_count,r.validated_zero_count),(257,1,1,254,1))
        for i in range(2,257):
            off=301*i;physical=value.data_pages[off//P]*P+off%P
            self.assertIn((physical,1),value.calls)
            self.assertFalse(any(a<=physical+1<a+n for a,n in value.calls))
        self.assertEqual((r.framing_validation,r.filename_validation,r.root_identity,r.native_acceptance),('not_accepted','zero_marker_bounded_utf16le','not_observed','pending'))
        self.assertFalse({'active_slots','free_slots','filenames','positions','filename_hash'} & set(asdict(r)))

    def test_lengths_unicode_and_finite_nonidentifying_counts(self):
        names=['','x','x'*127,'x'*128,'x'*126+'😀','PRIVATE_Ω','\0\ufeff']
        value=source([row(marker=1)]+[row(n) for n in names]);r=self.read(value)
        self.assertEqual((r.validated_zero_count,r.empty_filenames,r.nonempty_filenames,r.max_filename_units),(7,1,6,128))
        self.assertNotIn('PRIVATE',repr(r));self.assertNotIn('Ω',repr(r));self.assertFalse(value.closed)
        self.assertNotIn((value.blob_page*P,P),value.calls)
        with self.assertRaises(FrozenInstanceError):r.validated_zero_count=0

    def test_zero_field_predicate_is_not_blob_eligibility(self):
        for blob in (b'\0'*8,b'\xff'*8):
            candidate=bytearray(row('bounded'));candidate[287:295]=blob
            self.assertEqual(self.read(source([row(marker=1),bytes(candidate)])).nonempty_filenames,1)

    def test_nonempty_witness_required_not_native_empty_name_prohibition(self):
        for rows in ([row(marker=1)],[row(marker=1),row('')],[row(marker=1),row(marker=1),row(marker=255)],[row(marker=1),row(''),row('PRIVATE',marker=1)]):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_filename_no_nonempty_witness'):self.read(source(rows))

    def test_reserved_marker_required_and_other300_bytes_opaque(self):
        for marker in (0,2,255):
            v=source([row(marker=marker),row('valid')])
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_reserved_slot'):self.read(v)
            self.assertEqual([x for x in v.calls if x[0]>=10*P],[(10*P,1)])
        self.assertEqual(self.read(source([b'\x01'+b'\xff'*300,row('valid')])).validated_zero_count,1)

    def test_old_strict_failure_and_census_semantics_unchanged(self):
        self.assertEqual(core.ConfigFramingProfile(DECLARATIONS,'0',0).recipe_sha256,'48fc146c1e748b877b518993d09e7050f4c57cd6cd8682596f97411655c4a7e3')
        cp=core.ConfigMarkerCensusProfile(DECLARATIONS,'0',0)
        self.assertEqual(cp.recipe_sha256,'a73b1d173b65726fd0d06a09bab112e0ab287fc9206f289538ce7169d93d80ba')
        v=source([row(marker=1),row('valid'),row(raw=b'\0\xd8',units=65535,marker=255)])
        self.assertEqual(self.read(v).later_other_count,1)
        r=core.observe_config_marker_census(v.read_at,v.size,profile=cp)
        self.assertEqual((r.later_zero_count,r.later_other_count,r.filename_validation),(1,1,'not_run'))
        with self.assertRaisesRegex(core.UnsupportedLayout,'config_nonreserved_slot'):
            core.observe_config_framing(v.read_at,v.size,profile=core.ConfigFramingProfile(DECLARATIONS,'0',0))

    def test_last_zero_invalid_length_or_encoding_never_partial_success(self):
        for raw,units,kind,code in ((b'',129,core.InvalidStructure,'config_filename_length'),(b'',65535,core.InvalidStructure,'config_filename_length'),(b'\0\xd8',1,core.UnsupportedLayout,'config_filename_encoding'),(b'\0\xdc',1,core.UnsupportedLayout,'config_filename_encoding'),(b'\0\xd8A\0',2,core.UnsupportedLayout,'config_filename_encoding')):
            with self.assertRaisesRegex(kind,code):self.read(source([row(marker=1),row('valid'),row(marker=1),row(raw=raw,units=units)]))

    def test_last_zero_short_marker_length_or_payload_fails(self):
        for offset in (602,603,605):
            v=source([row(marker=1),row('valid'),row('last')])
            def bad(a,n):return b'' if a==10*P+offset else v.read_at(a,n)
            with self.assertRaises(CatalogError):core.observe_config_zero_marker_filenames(bad,v.size,profile=profile())

    def test_exact_read_ranges_and_cross_page_payload(self):
        v=source([row(marker=1),row('abc'),row(raw=b'\0\xd8',units=65535,marker=1)]);self.read(v)
        self.assertEqual([x for x in v.calls if x[0]>=10*P],[(10*P,1),(10*P+301,1),(10*P+302,2),(10*P+304,6),(10*P+602,1)])
        v=source([row(marker=1)]+[row('a')]*26+[row('x'*128)]);self.assertEqual(self.read(v).max_filename_units,128)
        self.assertIn((10*P+8130,62),v.calls);self.assertIn((11*P,194),v.calls)

    def test_variable_counts_and_exact_slot_cap(self):
        for count in (2,3,7,16,29,4096):
            r=self.read(source([row(marker=1),row('a')]+[row(marker=255)]*(count-2)))
            self.assertEqual((r.candidate_slots,r.validated_zero_count,r.later_other_count),(count,1,count-2))
        v=source([row(marker=1),row('a')]+[row(marker=255)]*4095)
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):self.read(v)
        self.assertFalse([x for x in v.calls if x[0]>=10*P])

    def test_selection_and_profile_gate_before_mapping(self):
        for name in ('config','CoNfIg','CONFIG'):self.assertEqual(self.read(source(table_name=name)).target,'CONFIG')
        for name in ('CONFIGSAVE','PARAMS','CONFIG ','CОNFIG','CONFIG\x00'):
            v=source(table_name=name)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_missing'):self.read(v)
            self.assertNotIn((5*P,P),v.calls)
        for changes in ({'lock':'1'},{'format_item':'0'},{'format_item':1},{'declarations':DECLARATIONS[:-1]},{'declarations':(('FILENAME','NVC',0,127,0,'CI'),*DECLARATIONS[1:])}):
            v=source(**changes)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_profile_mismatch'):self.read(v)
            self.assertNotIn((5*P,P),v.calls);self.assertNotIn((8*P,P),v.calls)
        original=core.CatalogReader.read_catalog
        def duplicate(reader):
            c=original(reader);return replace(c,tables=(*c.tables,replace(c.tables[0],name='config')))
        v=source()
        with mock.patch.object(core.CatalogReader,'read_catalog',duplicate):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_ambiguous'):self.read(v)
        self.assertNotIn((5*P,P),v.calls)

    def test_empty_unaligned_and_ownership_errors_before_markers(self):
        for raw,kind,code in ((b'',core.UnsupportedLayout,'config_empty_data'),(bytes(300),core.InvalidStructure,'config_record_length'),(bytes(302),core.InvalidStructure,'config_record_length')):
            v=source(raw=raw)
            with self.assertRaisesRegex(kind,code):self.read(v)
            self.assertFalse([x for x in v.calls if x[0]>=10*P])
        for mutation in (lambda v:v.page(8).__setitem__(slice(0,2),b'xx'),lambda v:v.page(8).__setitem__(slice(24,28),u32(10)),lambda v:v.page(8).__setitem__(slice(24,28),u32(9))):
            v=source();mutation(v)
            with self.assertRaises(CatalogError):self.read(v)
            self.assertFalse([x for x in v.calls if x[0]>=10*P])

    def test_lowerable_limits_and_cumulative_budgets(self):
        v=source()
        with self.assertRaisesRegex(core.ResourceLimit,'config_record_bytes'):self.read(v,limits=core.ConfigFramingLimits(max_record_bytes=300))
        self.assertEqual(v.calls,[])
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):self.read(source(),limits=core.ConfigFramingLimits(max_slots=1))
        with self.assertRaises(ValueError):self.read(source(),limits={})
        with self.assertRaises(ValueError):self.read(source(),catalog_limits={})
        r=self.read(source())
        for key,used in [('max_output_bytes',r.usage.output_bytes),('max_bytes_processed',r.usage.bytes_processed),('max_read_bytes',r.usage.read_bytes)]:
            with self.assertRaises(core.ResourceLimit):self.read(source(),catalog_limits=core.CatalogLimits(**{key:used-1}))

    def test_cold_stdlib_only(self):
        code=('import sys,json,dataclasses;sys.path[:0]=sys.argv[1:];import config_framing_reader as c;raw=sys.stdin.buffer.read();p=c.ConfigZeroMarkerFilenameProfile(c.DECLARATIONS,"0",0);o=c.observe_config_zero_marker_filenames(lambda a,n:raw[a:a+n],len(raw),profile=p);assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);print(json.dumps(dataclasses.asdict(o),sort_keys=True))')
        v=source([row(marker=1),row('bounded'),row(raw=b'\0\xd8',units=65535,marker=255)])
        r=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')],input=v.full_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),asdict(self.read(v)))

if __name__=='__main__':unittest.main()

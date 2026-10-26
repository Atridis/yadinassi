"""Independent candidate-marker fixtures; never framing, filename or free-slot acceptance."""
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
from test_native_1c_db_oracle_config_framing_reader import DECLARATIONS, source, row, P, u32


def profile():
    return core.ConfigMarkerCensusProfile(DECLARATIONS,'0',0)


class ConfigMarkerCensusCoreTests(unittest.TestCase):
    def read(self,value,**kwargs):
        return core.observe_config_marker_census(value.read_at,value.size,profile=profile(),**kwargs)

    def test_separate_exact_recipe_and_strict_profile_unchanged(self):
        p=profile()
        expected={'identifier':'config_marker_census_8380_8192_v1','declarations':DECLARATIONS,
            'recordlock':'0','format_item':0,'candidate_stride':301,
            'observation':'first_and_later_zero_one_other_candidate_markers_v1',
            'selection':'CONFIG_ascii_case_only_no_fallback_v1',
            'empty_data':'unsupported','single_candidate':'admitted',
            'framing':'not_accepted','filename':'not_read'}
        self.assertEqual(p.recipe(),expected)
        self.assertEqual(p.recipe_sha256,hashlib.sha256(json.dumps(expected,ensure_ascii=True,
            sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest())
        self.assertEqual(core.ConfigFramingProfile(DECLARATIONS,'0',0).recipe_sha256,
            '48fc146c1e748b877b518993d09e7050f4c57cd6cd8682596f97411655c4a7e3')
        for lock,form in ((0,0),('1',0),('0',False),('0','0'),('0',1)):
            with self.assertRaises(ValueError):core.ConfigMarkerCensusProfile(DECLARATIONS,lock,form)
        for ds in (list(DECLARATIONS),DECLARATIONS[:-1],(list(DECLARATIONS[0]),*DECLARATIONS[1:]),
                   (('FILENAME','NVC',False,128,0,'CI'),*DECLARATIONS[1:])):
            with self.assertRaises(ValueError):core.ConfigMarkerCensusProfile(ds,'0',0)
        with self.assertRaises(FrozenInstanceError):p.candidate_stride=1
        recipe=p.recipe();recipe['candidate_stride']=1
        self.assertEqual(p.candidate_stride,301)
        with self.assertRaises(ValueError):
            core.observe_config_marker_census(lambda a,n:b'',0,
                profile=core.ConfigFramingProfile(DECLARATIONS,'0',0))

    def test_all_marker_values_counted_neutrally_no_active_or_free_claim(self):
        for first in (0,1,2,255):
            value=source([row(marker=first)]+[row(marker=i) for i in range(256)])
            result=self.read(value)
            self.assertEqual((result.candidate_slots,result.later_zero_count,
                result.later_one_count,result.later_other_count),(257,1,1,254))
            self.assertEqual(result.first_marker_class,'zero' if first==0 else 'one' if first==1 else 'other')
            self.assertEqual(result.framing_validation,'not_accepted')
            self.assertEqual(result.filename_validation,'not_run')
            self.assertEqual(result.root_identity,'not_observed')
            self.assertEqual(result.native_acceptance,'pending')
            self.assertFalse({'active_slots','free_slots','filenames','positions'} & set(asdict(result)))

    def test_invalid_filename_bytes_and_fields_are_completely_opaque(self):
        value=source([b'\x01'+b'\xff'*300,row(raw=b'\0\xd8',units=65535),
                      row('PRIVATE',marker=1),row(raw=b'\0\xdc',units=1,marker=255)])
        result=self.read(value)
        self.assertEqual((result.later_zero_count,result.later_one_count,result.later_other_count),(1,1,1))
        self.assertNotIn('PRIVATE',repr(result))
        self.assertEqual([call for call in value.calls if call[0]>=10*P],
                         [(10*P+i*301,1) for i in range(4)])
        self.assertNotIn((value.blob_page*P,P),value.calls)
        self.assertFalse(value.closed)

    def test_strict_framing_still_rejects_same_nonzero_later_marker(self):
        for marker in (1,2,255):
            v=source([row(marker=1),row('okay'),row(marker=marker)])
            self.assertEqual(self.read(v).candidate_slots,3)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_nonreserved_slot'):
                core.observe_config_framing(v.read_at,v.size,
                    profile=core.ConfigFramingProfile(DECLARATIONS,'0',0))

    def test_single_candidate_and_variable_counts_no_native_expected_sixteen(self):
        for count in (1,2,3,16,29):
            result=self.read(source([row(marker=255)]*count))
            self.assertEqual((result.candidate_slots,result.later_other_count),(count,count-1))
            self.assertEqual(result.data_logical_bytes,301*count)

    def test_every_candidate_read_across_backing_pages(self):
        value=source([row(marker=1)]+[row(marker=2)]*29);self.read(value)
        calls=[call for call in value.calls if call[0]>=10*P]
        self.assertEqual(calls,[(value.data_pages[(301*i)//P]*P+(301*i)%P,1) for i in range(30)])

    def test_last_candidate_read_failure_does_not_return_partial_counts(self):
        value=source([row(marker=1),row(marker=2),row(marker=255)])
        def bad(offset,size):
            return b'' if offset==10*P+602 else value.read_at(offset,size)
        with self.assertRaises(CatalogError):
            core.observe_config_marker_census(bad,value.size,profile=profile())

    def test_slot_cap_and_one_over_before_marker_scan(self):
        self.assertEqual(self.read(source([row(marker=255)]*4096)).candidate_slots,4096)
        value=source([row(marker=255)]*4097)
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):self.read(value)
        self.assertFalse([call for call in value.calls if call[0]>=10*P])

    def test_exact_selection_no_fallback_or_case_ambiguity(self):
        for name in ('config','CoNfIg','CONFIG'):self.assertEqual(self.read(source(table_name=name)).target,'CONFIG')
        for name in ('CONFIGSAVE','PARAMS','CONFIG ','CОNFIG','CONFIG\x00'):
            value=source(table_name=name)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_missing'):self.read(value)
            self.assertNotIn((5*P,P),value.calls)
        original=core.CatalogReader.read_catalog
        def duplicate(reader):
            catalog=original(reader)
            return replace(catalog,tables=(*catalog.tables,replace(catalog.tables[0],name='config')))
        value=source()
        with mock.patch.object(core.CatalogReader,'read_catalog',duplicate):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_ambiguous'):self.read(value)
        self.assertNotIn((5*P,P),value.calls)

    def test_profile_gate_precedes_data_and_blob_mapping(self):
        for changes in ({'lock':'1'},{'format_item':'0'},{'format_item':1},
                {'declarations':DECLARATIONS[:-1]},
                {'declarations':(('FILENAME','NVC',0,127,0,'CI'),*DECLARATIONS[1:])}):
            value=source(**changes)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_profile_mismatch'):self.read(value)
            self.assertNotIn((5*P,P),value.calls);self.assertNotIn((8*P,P),value.calls)

    def test_empty_or_unaligned_data_rejected_without_marker_read(self):
        for raw,kind,code in ((b'',core.UnsupportedLayout,'config_empty_data'),
                (bytes(300),core.InvalidStructure,'config_record_length'),
                (bytes(302),core.InvalidStructure,'config_record_length')):
            value=source(raw=raw)
            with self.assertRaisesRegex(kind,code):self.read(value)
            self.assertFalse([call for call in value.calls if call[0]>=10*P])

    def test_lowerable_limits_and_shared_budgets(self):
        value=source()
        with self.assertRaisesRegex(core.ResourceLimit,'config_record_bytes'):
            self.read(value,limits=core.ConfigFramingLimits(max_record_bytes=300))
        self.assertEqual(value.calls,[])
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):
            self.read(source(),limits=core.ConfigFramingLimits(max_slots=1))
        with self.assertRaises(ValueError):self.read(source(),limits={})
        with self.assertRaises(ValueError):self.read(source(),catalog_limits={})
        result=self.read(source())
        with self.assertRaises(core.ResourceLimit):
            self.read(source(),catalog_limits=core.CatalogLimits(max_output_bytes=result.usage.output_bytes-1))

    def test_blob_ownership_checked_but_never_payload(self):
        for mutation in (lambda v:v.page(8).__setitem__(slice(0,2),b'xx'),
                         lambda v:v.page(8).__setitem__(slice(24,28),u32(10)),
                         lambda v:v.page(8).__setitem__(slice(24,28),u32(9))):
            value=source();mutation(value)
            with self.assertRaises(CatalogError):self.read(value)
            self.assertFalse([call for call in value.calls if call[0]>=10*P])

    def test_cold_stdlib_only_diagnostic(self):
        code=('import sys,json,dataclasses;sys.path[:0]=sys.argv[1:];import config_framing_reader as c;'
            'raw=sys.stdin.buffer.read();p=c.ConfigMarkerCensusProfile(c.DECLARATIONS,"0",0);'
            'o=c.observe_config_marker_census(lambda a,n:raw[a:a+n],len(raw),profile=p);'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print(json.dumps(dataclasses.asdict(o),sort_keys=True))')
        value=source([row(marker=255),row(marker=1),row(marker=2)])
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,
            str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')],
            input=value.full_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),asdict(self.read(value)))


if __name__=='__main__':unittest.main()

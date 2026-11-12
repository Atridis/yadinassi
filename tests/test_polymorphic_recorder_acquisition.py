"""Offline stage failure/binding checks; no native process or container."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'scripts/native_1c_bootstrap'))
from polymorphic_recorder_behavior import route, fixture
import polymorphic_recorder_suite as suite

class RecorderAcquisitionTests(unittest.TestCase):
    nonce='a'*32

    def test_empty_stage_has_no_success_claim(self):
        report=suite.empty_report(self.nonce)
        self.assertEqual(report['schema'],route.STAGE_SCHEMA)
        self.assertEqual(report['record_count'],None)
        self.assertTrue(report['incomplete'])
        self.assertFalse(report['witness_verified'])

    def test_stage_adapter_requires_all_eight_groups(self):
        lines=['entered']+[str(i)+'|ERR' for i in range(1,9)]+['completed']
        raw=('\n'.join('PRQ|'+self.nonce+'|'+x for x in lines)+'\n').encode()
        observations,errors=route.parse_attempt(raw,self.nonce)
        self.assertEqual(len(observations),8);self.assertEqual(errors,[])
        with self.assertRaises(ValueError):route.parse_attempt(raw.replace(b'|4|ERR\n',b'|4|ERR\nextra\n'),self.nonce)

    def test_failure_details_do_not_export_payload_or_nonce(self):
        details=route.failure_details({'messages':['PRQ|'+self.nonce+'|entered'],'error':'secret=/tmp/private'},self.nonce)
        self.assertTrue(route.valid_failure_details(details))
        self.assertEqual(details,{'entered':True,'category':'native_failure'})
        self.assertNotIn(self.nonce,json.dumps(details))
        self.assertFalse(route.valid_failure_details({**details,'raw':'secret'}))

    def test_failure_envelope_is_bounded(self):
        for result in [{'messages':[],'error':'x'*16385},{'messages':['x']*11,'error':''},{'messages':[],'error':None}]:
            with self.assertRaises(ValueError):route.failure_details(result,self.nonce)

    def test_fixture_limits_match_secure_dump_contract(self):
        self.assertEqual(fixture.MAX_FILE,fixture.inventory.MAX_FILE)
        self.assertEqual(fixture.MAX_TOTAL,fixture.inventory.MAX_TOTAL)
        self.assertIs(fixture._files,fixture.inventory._files)

    def test_prerequisite_failure_restores_launcher_hooks_without_execution(self):
        old=lambda *args:None
        launcher=SimpleNamespace(read_result=old,run_process=old,build_epf=old)
        platform=SimpleNamespace(user='wrong',password=None,timeout=120)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(suite.full,'run_process',side_effect=AssertionError('must not execute')):
            report=suite.run_suite(launcher,platform,None,Path(tmp)/'stage',Path(tmp),self.nonce)
        self.assertEqual(report['status'],'failed')
        self.assertFalse(report['witness_verified'])
        self.assertIs(launcher.run_process,old);self.assertIs(launcher.read_result,old);self.assertIs(launcher.build_epf,old)

    def test_stage_rechecks_sources_and_material_redump_before_export(self):
        # Static contract until host synthetic lifecycle harness is added.
        source=(ROOT/'scripts/native_1c_bootstrap/polymorphic_recorder_suite.py').read_text()
        self.assertIn('if input_hashes(inputs)!=hashes:',source)
        self.assertIn('fixture.verify_redump(expected,dump_files(prepared))',source)
        self.assertIn('full.final_client_process_census(nonce)',source)
        self.assertIn("root/'polymorphic-recorder.out'",source)
        self.assertNotIn("root/'inventory-reference.out'",source)

    def test_cleanup_failure_cannot_export(self):
        report={'status':'ok','native_tests_completed':True}
        stage=suite.empty_report(self.nonce)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(suite.full,'secure_bytes',return_value=json.dumps(stage).encode()):
            raw=suite.finish_report(report,self.nonce,Path(tmp)/'stage',quiet=False,bus_cleanup_failed=True)
        value=json.loads(raw)
        self.assertEqual(value['outputs'],[])
        self.assertFalse(value['report']['native_tests_completed'])

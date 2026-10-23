"""Separate opt-in measurement integration. All execution here is synthetic."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_async_protocol as proto
import test_native_1c_full_host as fixture
from test_native_1c_smoke import smoke
suite=proto.suite
full=proto.full

class AsyncIntegrationTests(fixture.SyntheticFilesystemCase):
    def setUp(self):
        super().setUp()
        self.env,self.inputs,self.modules=fixture.fixture()
        self.inputs[full.CLIENT_SOURCE]='c'*64
        self.modules['client_probe']='d'*64
        identity=full.async_source_identity(Path(suite.__file__).read_bytes())
        self.modules['client_async']=identity
        stage=self.env['report']['stage3']
        stage['client_probe']={'status':'ok','failure_kind':'none','source_sha256':'c'*64,
            'module_sha256':'d'*64,'roundtrip_sha256':'d'*64,
            'process_diagnostics':proto.fixtures.process_diagnostics(),**dict.fromkeys(full.CLIENT_FLAGS,True)}
        record=proto.record();record['template_sha256']=identity['template']
        for row,sha in zip(record['cases'],identity['modules']):row[3]=sha
        stage['client_async']=record
        self.stage=stage
    def validate(self,*,enabled=True):
        env=copy.deepcopy(self.env);env['report']['stage3']=suite.encode_stage_wire(self.stage)
        return full.validate_envelope(fixture.encode(env),fixture.NONCE,self.inputs,self.modules,
            smoke.validate_report,client_async=enabled)
    def test_schema4_roundtrip_fixed_inputs_and_six_outputs(self):
        wire=suite.encode_stage_wire(self.stage);self.assertEqual(wire['schema'],4)
        report,outputs=self.validate()
        self.assertEqual(report['stage3']['client_async'],self.stage['client_async'])
        self.assertEqual(len(self.inputs),24);self.assertEqual(list(outputs),list(full.SCENARIOS))
        self.assertEqual(len(full.ARTIFACT_FILES),7)
    def test_unsolicited_or_missing_async_rejected(self):
        with self.assertRaises(full.FullError):self.validate(enabled=False)
        self.stage.pop('client_async')
        with self.assertRaises(full.FullError):self.validate()
        self.validate(enabled=False)
    def test_standard_false_schema_is_identical(self):
        self.stage.pop('client_async')
        a=suite.encode_stage_wire(self.stage)
        self.assertNotEqual(a['schema'],4)
        baseline=suite.empty_report(fixture.NONCE,client_probe=True)
        self.assertEqual(baseline,suite.empty_report(fixture.NONCE,client_probe=True,client_async=False))
    def test_source_ast_is_pinned_and_never_executed(self):
        source=Path(suite.__file__).read_bytes()
        self.assertEqual(full.async_source_identity(source),full.ASYNC_EXPECTED_IDENTITY)
        self.assertEqual(full.async_source_identity(source+b'\nraise RuntimeError("not executed")\n'),full.ASYNC_EXPECTED_IDENTITY)
        for suffix in (b'\nASYNC_TEMPLATE = "replacement"\n',b'\nASYNC_CASE_SOURCES = tuple()\n'):
            with self.assertRaises(full.FullError):full.async_source_identity(source+suffix)
    def test_false_proof_and_noncanonical_source_identity_fail(self):
        self.stage['client_async']['cases'][0][4]=62
        with self.assertRaises(full.FullError):self.validate()
    def test_measurement_cannot_silently_mix_standard_extras(self):
        for flag in ('watchdog_check','client_dates','client_values','client_collections','client_numbers'):
            with self.subTest(flag=flag),self.assertRaises(suite.FullError):
                suite.empty_report(fixture.NONCE,client_probe=True,client_async=True,**{flag:True})
    def test_unreached_async_census_keeps_order_valid(self):
        self.stage['client_async']=suite.empty_async_report()
        self.stage['client_probe']=suite.empty_client_report()
        suite.fail_client_process_checkpoint(self.stage,False)
        self.assertEqual(self.stage['client_async']['status'],'not_started')
    def test_private_continuity_worst_case_fits_unchanged_private_bound(self):
        paths=suite.async_manifest_paths(Path('/tmp/onec-smoke/stage3-'+'a'*32+'/client-async'),Path('/smoke'))
        self.assertEqual(len(paths),133)
        value={'schema':1,'nonce':'a'*32,'files':{name:[['9'*20]*7,'a'*64] for name in paths}}
        self.assertLessEqual(len(json.dumps(value,sort_keys=True,separators=(',',':')).encode()),65536)
    def test_continuity_anchor_is_mandatory_only_for_complete_measurements(self):
        for invalid in (None,True,1,'A'*64,'a'*63,'a'*65):
            with self.subTest(value=invalid):
                record=proto.record();record['continuity_sha256']=invalid
                with self.assertRaises(suite.FullError):suite.validate_async_report(record,proto.H,proto.MODULES)
                with self.assertRaises(ValueError):full.validate_client_async(record,proto.H,proto.MODULES)
        record=suite.empty_async_report();record['continuity_sha256']='a'*64
        with self.assertRaises(suite.FullError):suite.validate_async_report(record,proto.H,proto.MODULES)
        with self.assertRaises(ValueError):full.validate_client_async(record,proto.H,proto.MODULES)
    def test_default_timeout_old_path_remains_exact(self):
        with self.assertRaises(suite.FullError):suite.run_process([],Path('/tmp'),Path('/tmp/x'),119)
        for timeout in (0,121,True,None,float('nan')):
            with self.subTest(timeout=timeout),self.assertRaises(suite.FullError):
                suite.run_async_process([],Path('/tmp'),Path('/tmp/x'),timeout)

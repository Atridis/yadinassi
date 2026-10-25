"""Strict current whole138 admission. Synthetic harness tests are not native runs."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_preprocessor_measurement as observation
import test_native_infobase_budget as ib
import test_native_1c_full_host as host_fixture
from infobase_preflight_test_support import offline_fixture
from test_native_1c_full_host import SyntheticFilesystemCase

full, suite, smoke, ROOT, NONCE = observation.full, observation.suite, observation.smoke, observation.ROOT, observation.NONCE
TOKEN = 'pp.v1:135135139139131131131131131131'
PROFILE = 'managed-thick-file'


def marker(phase='completed', token=TOKEN):
    return observation.marker(phase, token)


def bind(stage, inputs, modules):
    stage.update(schema=9, nonce=NONCE, preprocessor_status='matched', compilation_profile=PROFILE)
    inputs[full.CLIENT_SOURCE] = full.PREPROCESSOR_SOURCE_SHA256
    modules['client_probe'] = full.PREPROCESSOR_MODULE_SHA256
    record=stage['client_probe']
    record.update(source_sha256=full.PREPROCESSOR_SOURCE_SHA256,
                  module_sha256=full.PREPROCESSOR_MODULE_SHA256, roundtrip_sha256=full.PREPROCESSOR_MODULE_SHA256,
                  infobase_context=full.INFOBASE_CONTEXT_EXPECTED_TOKEN, preprocessor_profile=TOKEN)


class PreprocessorRuntimeTests(SyntheticFilesystemCase):
    def test_audited_record_and_immutable_measurement_plan(self):
        captured=ROOT/'integrational_tests/directive_probes/preprocessor_profiles_native.json'
        self.assertEqual(hashlib.sha256(captured.read_bytes()).hexdigest(), '5e8dd7c1552785e83cb6304252d6b33692a34be47c30f15afe8d51e415c77c27')
        record=json.loads(captured.read_text(encoding="utf-8"))
        self.assertEqual(record['observation_token'],TOKEN)
        self.assertEqual(record['source_sha256'],full.PREPROCESSOR_SOURCE_SHA256)
        self.assertEqual(record['module_sha256'],full.PREPROCESSOR_MODULE_SHA256)
        self.assertFalse(record['preprocessor_parity_claimed']);self.assertFalse(record['new_async_claim'])
        plan=ROOT/'integrational_tests/directive_probes/preprocessor_profiles_measurement.json'
        self.assertEqual(full.digest(plan.read_bytes()), record['measurement_manifest_sha256'])
        self.assertIsNone(json.loads(plan.read_text(encoding="utf-8"))['native_expected_token'])
        self.assertEqual(full.PREPROCESSOR_RUNTIME_TOKEN,suite.PREPROCESSOR_RUNTIME_TOKEN)

    def test_exact138_marker_rejects_every_wrong_slot_and_all_other_finite_suffixes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder).resolve()/'marker.json'
            def read(value):
                path.write_text(json.dumps(value,separators=(',',':')),encoding='utf-8')
                return suite.preprocessor_runtime_marker(path,NONCE,'completed',source_hash=full.PREPROCESSOR_SOURCE_SHA256)
            reader=(mock.patch.object(suite,'secure_bytes',new=observation.probe.stage_fixture.portable_fixture_bytes)
                    if os.name=='nt' else __import__('contextlib').nullcontext())
            with reader:
                self.assertEqual(read(marker()),marker())
                for index in range(138):
                    value=marker();value['values'][index]=None
                    with self.subTest(index=index),self.assertRaises(suite.FullError):read(value)
                for position in range(10):
                    for mask in range(512):
                        tokens=[TOKEN[6+i*3:9+i*3] for i in range(10)]
                        if tokens[position]==f'{mask:03}':continue
                        tokens[position]=f'{mask:03}'
                        value=marker(token='pp.v1:'+''.join(tokens))
                        with self.assertRaises(suite.FullError):read(value)

    def test_current_source_requires_strict_schema_status_profile_and_exact_token(self):
        stage,inputs,modules=ib.parity_stage((False,)*5);bind(stage,inputs,modules)
        wire=suite.encode_stage_wire(stage)
        self.assertEqual(full.validate_stage3(wire,NONCE,inputs,modules,prerequisites=True),stage)
        for wrong_nonce in ('0'*32, 'invalid', True):
            with self.subTest(nonce=wrong_nonce),self.assertRaises(ValueError):
                full.validate_stage3(wire,wrong_nonce,inputs,modules,prerequisites=True)
        for change in ({'schema':1},{'schema':5},{'schema':True},{'preprocessor_status':'observed'},
                       {'preprocessor_status':'failed'},{'compilation_profile':None},{'compilation_profile':'standalone'}):
            bad=copy.deepcopy(wire);bad.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):full.validate_stage3(bad,NONCE,inputs,modules,prerequisites=True)
        for field in ('preprocessor_status','compilation_profile'):
            bad=copy.deepcopy(wire);del bad[field]
            with self.assertRaises(ValueError):full.validate_stage3(bad,NONCE,inputs,modules,prerequisites=True)
        for token in (None,observation.TOKEN,full.PREPROCESSOR_DEFAULT_TOKEN):
            bad=copy.deepcopy(wire);bad['client_probe']['preprocessor_profile']=token
            with self.assertRaises(ValueError):full.validate_stage3(bad,NONCE,inputs,modules,prerequisites=True)
        with self.assertRaises(ValueError):full.validate_stage3(wire,NONCE,inputs,modules,prerequisites=True,preprocessor_measurement=True)
        bad=copy.deepcopy(wire);bad['schema']=1;bad.pop('preprocessor_status');bad.pop('compilation_profile');bad['client_probe'].pop('preprocessor_profile')
        with self.assertRaises(ValueError):full.validate_stage3(bad,NONCE,inputs,modules,prerequisites=True)

    def test_default_preflight_uses_unchanged138_real_context_and_explicit_profile(self):
        source=observation.linux_fixture(ROOT/full.CLIENT_SOURCE)
        with tempfile.TemporaryDirectory() as folder,offline_fixture(full):
            path=Path(folder).resolve()/'probe.bsl';path.write_bytes(source)
            def runner(args,cwd):
                self.assertEqual(args[-3],PROFILE);self.assertEqual(Path(args[-2]),path)
                self.assertEqual(path.read_bytes(),source)
                self.assertIn('FileDBContext(sys.argv[4])',args[-5]);self.assertIn('compilation_profile=sys.argv[2]',args[-5])
                return 0,json.dumps(full.CLIENT_RUNTIME_VALUES+[TOKEN],ensure_ascii=False,separators=(',',':')).encode(),b''
            full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,runner=runner)
            for values in (full.CLIENT_RUNTIME_VALUES,full.CLIENT_RUNTIME_VALUES+[full.PREPROCESSOR_DEFAULT_TOKEN]):
                with self.assertRaises(full.FullError):full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,
                    runner=lambda *a:(0,json.dumps(values,ensure_ascii=False,separators=(',',':')).encode(),b''))
            path.write_bytes(source+b'\n')
            with self.assertRaisesRegex(full.FullError,'source_changed'):full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,runner=runner)

    def test_public_parity_needs_host_profile_native_status_and_cleanup(self):
        import test_native_preprocessor_runtime_budget as budget
        stage,inputs,modules=ib.parity_stage((False,)*5);budget.bind(stage,inputs,modules)
        value=budget.report_for(stage,accepted=True)
        raw,code=budget.summary(value,selected=(False,)*5)
        self.assertEqual(code,0);self.assertTrue(json.loads(raw)['preprocessor_parity_claimed'])
        variants=[]
        for profile in (None,'standalone','unknown'):
            bad=copy.deepcopy(value);bad['preprocessor_host_profile']=profile;variants.append(bad)
        bad=copy.deepcopy(value);del bad['preprocessor_host_profile'];variants.append(bad)
        for name in ('container_cleanup_verified','private_payloads_removed','native_evidence_accepted'):
            bad=copy.deepcopy(value);bad[name]=False;variants.append(bad)
        bad=copy.deepcopy(value);bad['stage3']['preprocessor_status']='observed';variants.append(bad)
        bad=copy.deepcopy(value);bad['stage3']['compilation_profile']='standalone';variants.append(bad)
        for bad in variants:
            raw,code=budget.summary(bad,selected=(False,)*5)
            self.assertEqual(code,1);self.assertFalse(json.loads(raw)['preprocessor_parity_claimed'])

    def test_late_artifact_or_host_cleanup_failure_revokes_strict_claim(self):
        import test_native_preprocessor_runtime_budget as budget
        stage,inputs,modules=ib.parity_stage((False,)*5);budget.bind(stage,inputs,modules)
        value=budget.report_for(stage,accepted=True)
        for options in ({'artifact_error':True},{'error':True}):
            raw,code=budget.summary(value,selected=(False,)*5,**options)
            result=json.loads(raw)
            self.assertEqual(code,1);self.assertFalse(result['smoke_completed'])
            self.assertFalse(result['preprocessor_parity_claimed'])
            self.assertEqual(result['probe']['stage3']['preprocessor_status'],'failed')
            self.assertNotIn('preprocessor_profile',result['probe']['stage3']['client_probe'])
            if options.get('artifact_error'):
                self.assertFalse(result['probe']['native_output_artifact_ready'])

    def test_default_native_producer_accepts_exact_token_and_strips_late_failure(self):
        fixture=observation.ProfileObservationHarnessTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        f=fixture.fixture
        def completion(mode):
            if mode=='enterprise':
                (f.work/'completed.json').write_text(json.dumps(marker(),separators=(',',':')),encoding='utf-8')
        f.hook=completion
        record=f.run_probe()
        self.assertEqual(record['status'],'ok');self.assertEqual(record['preprocessor_profile'],TOKEN)
        full.validate_client_probe(record,full.PREPROCESSOR_SOURCE_SHA256,full.PREPROCESSOR_MODULE_SHA256,
            infobase_allowed=True,preprocessor_allowed=True,preprocessor_runtime=True)
        self.assertEqual(f.events,['build','dump','enterprise'])
        f.reset();f.hook=completion;f.run_error='timeout';record=f.run_probe()
        self.assertEqual(record['status'],'failed')
        self.assertNotIn('preprocessor_profile',record);self.assertNotIn('infobase_context',record)

    @unittest.skipIf(os.name=='nt','bounded child uses real POSIX process groups')
    def test_child_rejects_missing_or_unknown_profile_before_database_open(self):
        import sys
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            for args in ([str(ROOT),'unknown',str(root/'missing.bsl'),str(root/'missing-db')],
                         [str(ROOT),str(root/'missing.bsl'),str(root/'missing-db')]):
                code,out,error=full.bounded_child([sys.executable,'-I','-B','-c',full.CLIENT_EXECUTE_SCRIPT,*args],ROOT)
                self.assertNotEqual(code,0);self.assertEqual(out,b'')
                self.assertIn(b'invalid compilation profile',error)
                self.assertEqual(list(root.iterdir()),[])

    def test_suite_read_failure_and_unknown_source_stay_strict(self):
        f=observation.probe.stage_fixture.FullSuiteHarness();f.setUp();self.addCleanup(f.doCleanups)
        def run():return suite.run_suite(f.launcher,f.platform,f.epf,f.work,f.inputs,NONCE,client_probe=True)
        with mock.patch.object(suite,'input_hashes',side_effect=suite.FullError('artifact_missing')):
            result=run()
        self.assertEqual((result['schema'],result['compilation_profile'],result['preprocessor_status']),(9,PROFILE,'failed'))
        self.assertEqual(f.events,[])
        with mock.patch.object(suite,'input_hashes',return_value={suite.CLIENT_SOURCE:'a'*64}):result=run()
        self.assertEqual((result['schema'],result['failure_kind']),(9,'invalid_input'));self.assertEqual(f.events,[])

    def test_stage_controller_and_shell_fallbacks_bind_strict_profile(self):
        from test_native_1c_stage2 import Stage2Harness
        f=Stage2Harness();f.setUp();self.addCleanup(f.doCleanups);f.failures['verify']='process_failed'
        with mock.patch.object(suite,'run_suite') as run:
            f.module.run(full_nonce=NONCE,client_probe=True)
        run.assert_not_called()
        record=json.loads((f.root/'stage3-report.json').read_bytes())
        self.assertEqual((record['schema'],record['compilation_profile'],record['preprocessor_status']),(9,PROFILE,'not_started'))
        # Evaluate both actual shell fallback constructor expressions, without
        # rewriting/launching its native process lifecycle or touching fixed paths.
        script=smoke.PROBE.read_text(encoding="utf-8").split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        calls=[node for node in ast.walk(ast.parse(script)) if isinstance(node,ast.Call)
               and isinstance(node.func,ast.Attribute) and node.func.attr=='empty_report']
        namespace=dict(full_suite=suite,nonce=NONCE,client_mode='true',watchdog_mode='false',dates_mode='false',
            values_mode='false',collections_mode='false',numbers_mode='false',async_mode='false',preprocessor_mode='false')
        self.assertEqual(len(calls),2)
        for call in calls:
            record=eval(compile(ast.Expression(call),'shell-fallback-expression','eval'),namespace)
            self.assertEqual((record['schema'],record['compilation_profile']),(9,PROFILE))


if __name__=='__main__':unittest.main()

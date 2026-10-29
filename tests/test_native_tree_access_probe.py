"""Bounded separate probe transport; synthetic fixtures are not native evidence."""
import contextlib
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from scripts import native_1c_tree_access_probe as probe
from test_native_tree_copy_measurement import capture, maximum_output, PROBE_RECORD
from test_native_tree_copy_profile import host, tree, full, smoke, success_envelope, PROFILE, SPEC, NONCE, budget


def failed_envelope():
    raw = capture(maximum_output())
    lines = raw.splitlines(keepends=True); lines[6] = b'TC-5: [XM15G01]\n'; raw = b''.join(lines)
    value, hashes, modules = success_envelope(capture(maximum_output()))
    value['outputs'] = []
    report = value['report']; report.update(status='stage3_failed',native_tests_completed=False)
    stage = report['stage3']; stage.update(status='failed',failure_kind='unsupported_observation',failed_case=SPEC.case)
    stage['observation_diagnostic'] = dict(site='server',case=5,category='case5_step15_registry_62',calibration=None)
    stage['cases'][0].update(status='failed',module_sha256=None,output_sha256=None,output_size=None,message_count=None)
    stage['client_tree'] = full.empty_dates_report()
    stage['copy_access_probes'] = dict(server=probe.witness(raw,'server',NONCE,SPEC.source_sha256,modules[SPEC.case]),client=None)
    return value,hashes,modules


class AccessProbeTests(unittest.TestCase):
    def test_strict_full_capture_order_count_and_no_legacy_fallback(self):
        main=maximum_output(); raw=capture(main)
        self.assertEqual(probe.split_capture(raw),(PROBE_RECORD,main))
        lines=raw.splitlines(keepends=True)
        for bad in (main, raw+b'\n',raw+PROBE_RECORD,PROBE_RECORD+raw,raw.replace(b'\n',b'\r\n'),
                    b''.join([lines[1],lines[0],*lines[2:]]),raw.replace(b'TC-5:',b'TC-6:'),raw.replace(b'TC-P:',b'TF-P:')):
            with self.subTest(bad=bad[:20]),self.assertRaises(probe.ProbeError): probe.split_capture(bad)
        with self.assertRaises(tree.ObservationFailure): tree.validate_observations(main,profile=PROFILE)

    def test_finite_records_and_truthful_controls(self):
        for i in range(23):
            for char in b'TFEA':
                value=bytearray(b'TFTFTFTFTTFTTFTTFTTFTTF'); value[i]=char
                result=probe.parse_record(b'TC-P: ['+value+b']\n')
                self.assertEqual(result['scalar_controls_valid'],bytes(value[:4])==b'TFTF')
        self.assertFalse(probe.scalar_controls_valid(b'TC-P: [B]\n'))
        for raw in (b'TC-P: []\n',b'TC-P: [X]\n',PROBE_RECORD+b'x',PROBE_RECORD.replace(b'T',b'Z'),PROBE_RECORD.decode()):
            with self.assertRaises(probe.ProbeError): probe.parse_record(raw)

    def test_probe_witness_is_source_module_nonce_site_and_capture_bound(self):
        raw=capture(maximum_output()); w=probe.witness(raw,'server',NONCE,SPEC.source_sha256,'a'*64)
        for key,bad in (('nonce','1'*32),('site','client'),('module_sha256','b'*64),('source_sha256','b'*64),
                        ('capture_size',True),('main_size',-1),('message_count',10),('controls_valid',False),
                        ('record','TC-P: [B]\n'),('main_sha256','private'),('schema','other')):
            with self.subTest(key=key),self.assertRaises(probe.ProbeError):
                probe.validate_witness({**w,key:bad},'server',NONCE,SPEC.source_sha256,'a'*64)
        with self.assertRaises(probe.ProbeError): probe.validate_witness({**w,'extra':1},'server',NONCE,SPEC.source_sha256,'a'*64)

    def test_failed_observer_keeps_only_authenticated_probe_metadata(self):
        value,hashes,modules=failed_envelope()
        def validate(v):return host.validate_envelope(budget.wire(v),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        with self.assertRaises(host.TreeError) as caught: validate(value)
        self.assertEqual(caught.exception.copy_probe_report,value['report'])
        self.assertNotIn('TC-5: [',json.dumps(caught.exception.copy_probe_report))
        self.assertIsNone(value['report']['stage3']['copy_access_probes']['client'])
        for change in (lambda v:v['report']['stage3']['copy_access_probes']['server'].update(module_sha256='f'*64),
                       lambda v:v['report']['stage3']['copy_access_probes']['server'].update(record='TC-P: [PRIVATE]\n'),
                       lambda v:v['report']['stage3']['copy_access_probes'].update(client=v['report']['stage3']['copy_access_probes']['server']),
                       lambda v:v.update(nonce='2'*32)):
            changed=copy.deepcopy(value);change(changed)
            with self.assertRaises(host.TreeError) as bad:validate(changed)
            self.assertFalse(hasattr(bad.exception,'copy_probe_report'))

    def test_impossible_probe_control_diagnostic_states_are_rejected(self):
        value,hashes,modules=failed_envelope()
        def validate(v):return host.validate_envelope(budget.wire(v),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        changed=copy.deepcopy(value)
        changed['report']['stage3']['observation_diagnostic']=dict(site='server',case=None,category='access_probe',calibration=None)
        with self.assertRaises(host.TreeError) as caught:validate(changed)
        self.assertFalse(hasattr(caught.exception,'copy_probe_report'))
        changed=copy.deepcopy(value);w=changed['report']['stage3']['copy_access_probes']['server']
        w['record']='TC-P: [FFFFEEEEEEEEEEEEEEEEEEE]\n';w['controls_valid']=False
        with self.assertRaises(host.TreeError) as caught:validate(changed)
        self.assertFalse(hasattr(caught.exception,'copy_probe_report'))
        changed['report']['stage3']['observation_diagnostic']=dict(site='server',case=None,category='access_probe',calibration=None)
        with self.assertRaises(host.TreeError) as caught:validate(changed)
        self.assertTrue(hasattr(caught.exception,'copy_probe_report'))

    def test_probe_outcomes_never_join_main_parity(self):
        raw=capture(maximum_output()); different=raw.replace(PROBE_RECORD,b'TC-P: [TFTFEEEEEEEEEEEEEEEEEEE]\n')
        with tempfile.TemporaryDirectory() as tmp,budget.synthetic_inventory_reader():
            root=Path(tmp).resolve(strict=True);source=root/SPEC.source;source.parent.mkdir(parents=True)
            source.write_bytes((budget.ROOT/SPEC.source).read_text(encoding='utf-8').encode())
            result=host.compare_output(root,root,raw,{SPEC.source:SPEC.source_sha256},runner=lambda *a:(0,different,b''),profile=PROFILE)
        self.assertEqual(result['status'],'matched')
        self.assertNotEqual(result['native_sha256'],result['interpreter_sha256'])
        self.assertEqual(result['native_main_sha256'],result['interpreter_main_sha256'])
        self.assertEqual(result['parity_projection'],'TC-C-and-nine-cases')

    def test_client_failure_still_binds_successful_server_probe(self):
        value,hashes,modules=success_envelope(capture(maximum_output()))
        value['outputs']=[]; report=value['report'];report.update(status='stage3_failed',native_tests_completed=False)
        stage=report['stage3'];stage.update(status='failed',failure_kind='unsupported_observation',failed_case=None)
        stage['observation_diagnostic']=dict(site='client',case=5,category='case5_step15_registry_62',calibration=None)
        stage['copy_access_probes']['client']=None
        client=stage['client_tree'];client.update(status='failed',failure_kind='unsupported_observation',witness_verified=False,completed=False)
        client.update(dict.fromkeys(host.FULL.CLIENT_OUTPUT_KEYS))
        def validate(v):return host.validate_envelope(budget.wire(v),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        with self.assertRaises(host.TreeError) as caught:validate(value)
        self.assertTrue(hasattr(caught.exception,'copy_probe_report'))
        injected=copy.deepcopy(value)
        injected['report']['stage3']['copy_access_probes']['client']=probe.witness(
            capture(maximum_output()),'client',NONCE,SPEC.source_sha256,modules['client_tree'])
        with self.assertRaises(host.TreeError) as caught:validate(injected)
        self.assertFalse(hasattr(caught.exception,'copy_probe_report'))
        for key,bad in (('capture_sha256','0'*64),('capture_size',8192),('message_count',10)):
            changed=copy.deepcopy(value);changed['report']['stage3']['copy_access_probes']['server'][key]=bad
            with self.assertRaises(host.TreeError) as caught:validate(changed)
            self.assertFalse(hasattr(caught.exception,'copy_probe_report'))

    def test_bad_scalar_controls_never_produce_runtime_acceptance(self):
        raw=capture(maximum_output());bad=raw.replace(PROBE_RECORD,b'TC-P: [FFFFEEEEEEEEEEEEEEEEEEE]\n')
        with tempfile.TemporaryDirectory() as tmp,budget.synthetic_inventory_reader():
            root=Path(tmp).resolve(strict=True);source=root/SPEC.source;source.parent.mkdir(parents=True)
            source.write_bytes((budget.ROOT/SPEC.source).read_text(encoding='utf-8').encode())
            result=host.compare_output(root,root,raw,{SPEC.source:SPEC.source_sha256},runner=lambda *a:(0,bad,b''),profile=PROFILE)
            self.assertEqual(result['status'],'invalid_interpreter_output');self.assertEqual(result['acceptance_status'],'rejected')
            with self.assertRaises(host.TreeError):host.compare_output(root,root,bad,{SPEC.source:SPEC.source_sha256},runner=lambda *a:(0,raw,b''),profile=PROFILE)

    def test_probe_failure_lifecycle_must_finish_cleanup_and_provenance_without_artifacts(self):
        value,hashes,modules=failed_envelope()
        with self.assertRaises(host.TreeError) as caught:
            host.validate_envelope(budget.wire(value),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        authenticated=caught.exception
        for failure in (None,'cleanup','provenance','source','private','wrong_exit','unauthenticated'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
                root=Path(tmp).resolve(strict=True)
                stack.enter_context(mock.patch.object(host,'sibling',return_value=smoke))
                stack.enter_context(mock.patch.dict(os.environ,GHCR_TOKEN='synthetic-not-secret',GHCR_USER='Atridis'))
                for name,result in (('repository_provenance',{'sha':'a'*40}),('interpreter_provenance',{}),
                                    ('windows_fingerprints',{}),('read_regular',b'host'),('verify_client_interpreter',None)):
                    stack.enter_context(mock.patch.object(host.FULL,name,return_value=result))
                if failure=='provenance':host.FULL.repository_provenance.side_effect=[{'sha':'a'*40},{'sha':'b'*40}]
                if failure=='source':host.FULL.read_regular.side_effect=[b'host']*8+[b'changed']
                stack.enter_context(mock.patch.object(host,'stage_inputs',return_value={**hashes,host.FULL.CLIENT_SOURCE:'a'*64}))
                stack.enter_context(mock.patch.object(host,'module_hashes',return_value=modules))
                stack.enter_context(mock.patch.object(host,'validate_inputs'))
                stack.enter_context(mock.patch.object(host,'container_command',return_value=['container']))
                stack.enter_context(mock.patch.object(host,'validate_envelope',side_effect=host.TreeError('untrusted') if failure=='unauthenticated' else authenticated))
                compare=stack.enter_context(mock.patch.object(host,'compare_output',side_effect=AssertionError('must not compare failed Copy')))
                stack.enter_context(mock.patch.object(smoke,'run_silent'))
                stack.enter_context(mock.patch.object(smoke,'bounded_run',side_effect=[(0,b'linux/amd64|0'),(0 if failure=='wrong_exit' else 1,b'wire'),(0,b'left' if failure=='cleanup' else b'')]))
                export=stack.enter_context(mock.patch.object(host,'export_artifact'))
                if failure=='private':
                    original=host.private_work
                    @contextlib.contextmanager
                    def bad_private(*a):
                        with original(*a) as directory:yield directory
                        raise OSError('private cleanup unverified')
                    stack.enter_context(mock.patch.object(host,'private_work',side_effect=bad_private))
                if failure:
                    with self.assertRaises((host.TreeError,OSError)):host.run(root,root,export_native_outputs=True,profile=PROFILE)
                else:
                    result=host.run(root,root,export_native_outputs=True,profile=PROFILE)
                    self.assertFalse(result['native_measurement_accepted']);self.assertFalse(result['runtime_parity_accepted'])
                    self.assertEqual(result['probe_measurement_accepted'],{'server':True,'client':False})
                    self.assertTrue(result['container_cleanup_verified']);self.assertTrue(result['private_payloads_removed'])
                    self.assertEqual(result['native_report'],value['report']);self.assertNotIn('native_artifact_sha256',result)
                export.assert_not_called();compare.assert_not_called()
                self.assertFalse(list(root.glob('onec-tree-*')))

    def test_exact_probe_inverse_and_failed_stage_exit_are_preserved(self):
        from test_native_async_fixture import without_tree_access_probe, without_tree_copy_profile
        import run_stage
        source=(budget.ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_text(encoding='utf-8')
        previous=without_tree_access_probe(source)
        self.assertEqual(host.FULL.digest(previous.encode()),'e203d1469d191d48ab3db74d03877010b833689b46263f4585723bc29a0f928a')
        self.assertEqual(host.FULL.digest(without_tree_copy_profile(previous).encode()),'02fbe29f8b30213e79ea63709bcf84f5f5788ae8b33a5122ab1a567e2b07c6e1')
        with self.assertRaises(AssertionError):without_tree_access_probe(source+'\n')
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
            root=Path(tmp).resolve(strict=True)
            stack.enter_context(mock.patch.object(run_stage,'ROOT',root))
            stack.enter_context(mock.patch.object(run_stage,'run',return_value={'status':'ok'}))
            if os.name=='nt':
                from test_native_1c_full_host import read_synthetic_file
                stack.enter_context(mock.patch.object(full,'secure_bytes',side_effect=lambda path,limit,**kw:read_synthetic_file(path,limit)))
            (root/'stage3-report.json').write_text('{"status":"failed"}')
            self.assertEqual(run_stage.main(['--tree-copy-suite','--invocation-nonce',NONCE]),1)
        shell=(budget.ROOT/'scripts/native_1c_smoke_probe.sh').read_text(encoding='utf-8')
        self.assertIn('    exit "$result"',shell)
        self.assertIn('python3 /smoke/bootstrap/run_stage.py "$tree_flag" --invocation-nonce "$invocation_nonce"',shell)

    def test_real_server_producer_retains_probe_only_after_module_and_serialization_checks(self):
        import types
        raw=capture(maximum_output());lines=raw.splitlines(keepends=True);lines[6]=b'TC-5: [XM15G01]\n';raw=b''.join(lines)
        for failure in (None,'module','serialization','error_file'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as tmp:
                parent=Path(tmp).resolve(strict=True);inputs=parent/'inputs';inputs.mkdir()
                for source,target in tree.input_files(profile=PROFILE).items():
                    path=inputs/target;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes((budget.ROOT/source).read_text(encoding='utf-8').encode())
                def run_case(platform,source,epf,directory,output):
                    module=directory/'src/TestModule/Ext/ObjectModule.bsl';module.parent.mkdir(parents=True)
                    module.write_bytes(full.generated_module(source.read_bytes())+(b'x' if failure=='module' else b''))
                    (directory/'TestModule.build-result.txt').write_text('0');(directory/'TestModule.epf').write_bytes(b'synthetic')
                    (directory/'result.json').write_text(json.dumps({'messages':raw.decode().splitlines(),'error':''}))
                    output.write_bytes(raw+(b'x' if failure=='serialization' else b''))
                    if failure=='error_file':(directory/'result.err').write_text('private')
                original=(lambda *a:None,lambda *a:None,lambda *a:None)
                launcher=types.SimpleNamespace(read_result=original[0],run_process=original[1],build_epf=original[2],run_case=run_case)
                platform=types.SimpleNamespace(timeout=120,user='NativeSmoke',password=None)
                def portable(path,limit,**kwargs):
                    data=path.read_bytes()
                    if len(data)>limit:raise full.FullError('output_limit')
                    return data
                with mock.patch.object(full,'secure_bytes',side_effect=portable),mock.patch.object(full,'require_epf'),mock.patch.object(full,'require_zero_result'),mock.patch.object(full,'run_client_probe') as client:
                    result=tree.run_suite(launcher,platform,parent/'launcher.epf',parent/'result',inputs,NONCE,profile=PROFILE)
                client.assert_not_called();self.assertEqual(result['status'],'failed')
                self.assertEqual((launcher.read_result,launcher.run_process,launcher.build_epf),original)
                if failure is None:
                    self.assertEqual(result['observation_diagnostic']['category'],'case5_step15_registry_62')
                    expected=probe.witness(raw,'server',NONCE,SPEC.source_sha256,full.digest(full.generated_module((inputs/SPEC.target).read_bytes())))
                    self.assertEqual(result['copy_access_probes'],{'server':expected,'client':None})
                else:self.assertEqual(result['copy_access_probes'],{'server':None,'client':None})

"""Synthetic owned evidence only; no platform execution or UI event claim."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'scripts/native_1c_bootstrap'))
import native_1c_form_runtime_profile as host
import form_runtime_suite as lane
from form_runtime_packet import route
from test_form_runtime_route import files,marker
from test_native_1c_ci_policy import workflow_job,inline_program,subprocess_environment
import subprocess
NONCE='a'*32


def envelope():
    hashes={key:host.FULL.digest((ROOT/key).read_bytes()) for key in host.staged_files()}
    raw=marker()['records'].encode('ascii')
    stage=lane.empty_report(NONCE)
    module=host.FULL.digest(host.FULL.generated_module(route.module()))
    stage.update(status='ok',failure_kind='none',failure_phase='final',input_sha256=hashes,
                 source_sha256=host.SOURCE_SHA256,form_sha256=route.FORM_SHA256,
                 module_sha256=module,roundtrip_sha256=module,output_sha256=host.FULL.digest(raw),
                 output_size=len(raw),record_count=40)
    for key in host.FLAGS:stage[key]=True
    stage['process_diagnostics'].update(stage='after_exit',reason='none')
    value={'schema':host.SCHEMA,'profile':host.PROFILE,'nonce':NONCE,
           'report':{'status':'ok','native_tests_completed':True,'stage3':stage},
           'outputs':[{'name':'managed-form.out','size':len(raw),'sha256':host.FULL.digest(raw),
                       'data_b64':base64.b64encode(raw).decode()}]}
    return value,hashes,raw


def identity_validator(raw,**kwargs):return json.loads(raw)


class ManagedFormProfileTests(unittest.TestCase):
    def setUp(self):
        # Owned synthetic fixtures on Windows: not Linux descriptor-security proof.
        # Bind the exact imported host helper, restoring after each test.
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patcher.start();self.addCleanup(patcher.stop)

    def test_real_outer_validator_and_cleanup_refuse_export(self):
        from test_native_1c_smoke import bootstrap_report
        from test_native_tree_profile_host import synthetic_producer_reader
        value,hashes,raw=envelope()
        outer=bootstrap_report();outer.update(native_tests_completed=True,stage3=value['report']['stage3'])
        value['report']=outer
        self.assertEqual(host.validate_envelope(json.dumps(value).encode(),NONCE,hashes)[1],raw)
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary).resolve();root=parent/('stage3-'+NONCE);root.mkdir()
            (parent/'stage3-report.json').write_text(json.dumps(outer['stage3']),encoding='utf-8')
            (root/'managed-form.out').write_bytes(raw)
            for quiet,bus in ((False,False),(True,True)):
                with synthetic_producer_reader(lane.full),mock.patch.object(lane.full,'final_client_process_census'):
                    wire=lane.finish_report(copy.deepcopy(outer),NONCE,root,quiet=quiet,bus_cleanup_failed=bus)
                failed=json.loads(wire)
                self.assertEqual(failed['outputs'],[])
                self.assertFalse(failed['report']['native_tests_completed'])
                with self.assertRaises(host.FormError):host.validate_envelope(wire,NONCE,hashes)

    def test_closed_shell_flag_and_stage_forwarding(self):
        from native_workflow_shell import dispatch
        from test_native_tree_profile_host import synthetic_producer_reader
        import run_stage
        shell=(ROOT/'scripts/native_1c_smoke_probe.sh').read_text(encoding='utf-8')
        setup='tree_suite=false\n'+shell.split('tree_suite=false\n',1)[1].split('if [ "$#" -ge 5 ]',1)[0]
        flags='tree_flag=--tree-suite\n'+shell.split('tree_flag=--tree-suite\n',1)[1].split('        python3 /smoke/bootstrap/run_stage.py',1)[0]
        script='set -- --form-runtime-suite --invocation-nonce '+NONCE+'\n'+setup+'printf "%s\\n" "$tree_suite" "$*"\n'+flags+'printf "%s\\n" "$tree_flag"'
        result=dispatch(script)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),['form-runtime','--full-suite --invocation-nonce '+NONCE+' --client-probe','--form-runtime-suite'])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            (root/'stage3-report.json').write_text('{"status":"ok"}',encoding='utf-8')
            with mock.patch.object(run_stage,'ROOT',root),mock.patch.object(run_stage,'run',return_value={'status':'ok'}) as run,synthetic_producer_reader(lane.full):
                self.assertEqual(run_stage.main(['--form-runtime-suite','--invocation-nonce',NONCE]),0)
                self.assertTrue(run.call_args.kwargs['form_runtime'])
                self.assertFalse(run.call_args.kwargs['client_probe'])
                self.assertNotIn('tree_suite',run.call_args.kwargs)
        with mock.patch.object(run_stage,'run') as run:
            self.assertEqual(run_stage.main(['--form-runtime-suite','--invocation-nonce',NONCE,'--client-probe']),2)
            run.assert_not_called()

    def test_bootstrap_and_host_fixed_input_inventories_equal(self):
        self.assertEqual(host.staged_files(),lane.INPUT_FILES)
        self.assertNotIn('tree_suite.py',str(host.staged_files()))
        self.assertNotIn('client_probe.bsl',str(host.staged_files()))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();staged=root/'staged'
            hashes=host.stage_inputs(ROOT,staged,host.SMOKE)
            command=host.container_command(staged,hashes,'onec-form-'+'b'*32,NONCE,host.SMOKE)
            self.assertEqual(command[-3:],['--form-runtime-suite','--invocation-nonce',NONCE])
            for flag,value in (('--network','none'),('--user','1000:1000'),('--memory','2g'),('--cpus','2')):
                self.assertEqual(command[command.index(flag)+1],value)
            self.assertIn('--read-only',command);self.assertNotIn('--privileged',command)
            (staged/'extra').write_text('unexpected',encoding='utf-8')
            with self.assertRaises(host.FormError):host.validate_inputs(staged,hashes,host.SMOKE)

    def test_closed_success_identity_and_missing_witness_refusal(self):
        value,hashes,raw=envelope()
        actual=host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity_validator)
        self.assertEqual(actual[1],raw)
        for key in host.FLAGS:
            bad=copy.deepcopy(value);bad['report']['stage3'][key]=False
            with self.subTest(key=key),self.assertRaises(host.FormError):
                host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity_validator)
        for key in ('source_sha256','form_sha256','module_sha256','roundtrip_sha256','output_sha256'):
            bad=copy.deepcopy(value);bad['report']['stage3'][key]='f'*64
            with self.subTest(key=key),self.assertRaises(host.FormError):
                host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity_validator)
        for key,value2 in (('record_count',True),('output_size',True),('input_sha256',{}),('unknown','private')):
            bad=copy.deepcopy(value);bad['report']['stage3'][key]=value2
            with self.assertRaises(host.FormError):host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity_validator)

    def test_finite_failed_phase_never_exports_partial_observations(self):
        value,hashes,_=envelope();value['outputs']=[]
        value['report'].update(status='stage3_failed',native_tests_completed=False)
        stage=value['report']['stage3'];stage.update(status='failed',failure_kind='module_mismatch',failure_phase='redump',completed=False)
        with self.assertRaises(host.FormError) as caught:
            host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity_validator)
        self.assertEqual(caught.exception.native_failure['failure_phase'],'redump')
        stage['failure_phase']='private/path'
        with self.assertRaises(host.FormError) as caught:
            host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity_validator)
        self.assertFalse(hasattr(caught.exception,'native_failure'))

    def test_exact_dump_inventory_and_no_extra_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for name,raw in files().items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            with mock.patch.object(lane.full,'secure_bytes',side_effect=lambda p,*a,**k:p.read_bytes()):
                self.assertEqual(lane._dump_files(root),files())
                (root/'extra').mkdir()
                with self.assertRaises(lane.full.FullError):lane._dump_files(root)

    def test_comparison_contract_uses_closed_session_entry(self):
        from yadinassi.form_runtime import FormSession
        from form_runtime_packet import source
        session=FormSession(source(),bindings={'OnCreateAtServer':'FormCreate','OnOpen':'FormOpen','BeforeClose':'FormBeforeClose'})
        raw=dict(session.open().attributes)['FLog'].encode('ascii')
        hashes={host.SOURCE:host.SOURCE_SHA256}
        with tempfile.TemporaryDirectory() as directory:
            runner=mock.Mock(return_value=(0,raw,b''))
            result=host.compare_output(ROOT,Path(directory).resolve(),raw,hashes,runner=runner)
            self.assertEqual(runner.call_args.args[0][1:3],['-I','-B'])
            self.assertIn(host.EXECUTE_SCRIPT,runner.call_args.args[0])
        self.assertEqual(result['acceptance_status'],'accepted')
        self.assertEqual(result['scope'],'programmatic-and-direct-handler-with-create-open-lifecycle')

    @unittest.skipUnless(os.name=='posix','Production native-host bounded-child containment requires POSIX')
    def test_actual_bounded_child_replay(self):
        from yadinassi.form_runtime import FormSession
        from form_runtime_packet import source
        session=FormSession(source(),bindings={'OnCreateAtServer':'FormCreate','OnOpen':'FormOpen','BeforeClose':'FormBeforeClose'})
        raw=dict(session.open().attributes)['FLog'].encode('ascii')
        with tempfile.TemporaryDirectory() as directory:
            result=host.compare_output(ROOT,Path(directory).resolve(),raw,{host.SOURCE:host.SOURCE_SHA256})
        self.assertEqual(result['acceptance_status'],'accepted')

    def test_closed_job_and_required_gate_not_paired_tree_matrix(self):
        job=workflow_job('form_smoke');workflow=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        self.assertIn('native_1c_form_runtime_profile.py --execute-approved-image --export-native-outputs',job)
        self.assertIn('persist-credentials: false',job);self.assertIn('contents: read\n      packages: read',job)
        self.assertIn('native_1c_ci_policy.py bind',job)
        self.assertIn('needs: [eligibility, smoke, tree_smoke, tree_copy_smoke, catalog_object_smoke, form_smoke, catalog_query_smoke, http_smoke]',workflow)
        self.assertNotIn('managed-form-programmatic-v1',workflow_job('tree_copy_smoke'))
        env={'ELIGIBILITY_RESULT':'success','NATIVE_RESULT':'success','TREE_REQUIRED':'true',
             'TREE_RESULT':'success','TREE_COPY_RESULT':'success','FORM_RESULT':'success','CATALOG_OBJECT_RESULT':'success','CATALOG_QUERY_RESULT':'success','HTTP_RESULT':'success'}
        for result in ('success','failure','skipped','cancelled',''):
            env['FORM_RESULT']=result
            process=subprocess.run([sys.executable,'-I','-B','-c',inline_program('verdict')],
                                   env=subprocess_environment(env),capture_output=True,timeout=10)
            self.assertEqual(process.returncode,0 if result=='success' else 1)

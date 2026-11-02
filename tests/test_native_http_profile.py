"""Synthetic exact HTTP evidence; no Docker, real 1C, or external endpoint."""
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
for p in (ROOT,ROOT/'scripts',ROOT/'scripts/native_1c_bootstrap'):
    if str(p) not in sys.path:sys.path.insert(0,str(p))
import native_1c_http_profile as host
import native_1c_http_route as route
import native_1c_http_family_contract as contract
import http_suite as lane
NONCE='a'*32


def envelope():
    from test_native_1c_smoke import bootstrap_report
    hashes={key:host.FULL.digest((ROOT/key).read_bytes()) for key in host.staged_files()}
    raw=contract.CALIBRATION+b''.join(f'HT-{n:02}: [ok|S0:]\n'.encode() for n in range(1,41))
    stage=lane.empty_report(NONCE)
    module=host.FULL.digest(host.FULL.generated_module(route.program((ROOT/route.SOURCE).read_bytes(),12345,NONCE)))
    stage.update(status='ok',failure_kind='none',failure_phase='final',input_sha256=hashes,
        source_sha256=contract.SOURCE_SHA256,module_sha256=module,module_verified_sha256=module,
        output_sha256=host.FULL.digest(raw),output_size=len(raw),record_count=40,port=12345,request_count=20)
    for key in host.FLAGS:stage[key]=True
    stage['process_diagnostics'].update(stage='after_exit',reason='none')
    report=bootstrap_report();report.update(native_tests_completed=True,stage3=stage)
    return dict(schema=host.SCHEMA,profile=host.PROFILE,nonce=NONCE,report=report,
        outputs=[dict(name='http-family.out',size=len(raw),sha256=host.FULL.digest(raw),
            data_b64=base64.b64encode(raw).decode())]),hashes,raw


class HTTPHostTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patcher.start();self.addCleanup(patcher.stop)

    def test_real_outer_validator_and_bound_port_module(self):
        value,hashes,raw=envelope()
        self.assertEqual(host.validate_envelope(json.dumps(value).encode(),NONCE,hashes)[1],raw)
        for key,bad_value in [('port',12346),('port',True),('request_count',0),('record_count',39),
                              ('module_verified_sha256','f'*64),('input_sha256',{})]:
            bad=copy.deepcopy(value);bad['report']['stage3'][key]=bad_value
            with self.subTest(key=key),self.assertRaises(host.HTTPError):
                host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes)
        for key in host.FLAGS:
            bad=copy.deepcopy(value);bad['report']['stage3'][key]=False
            with self.subTest(key=key),self.assertRaises(host.HTTPError):
                host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes)

    def test_failed_cleanup_never_exports(self):
        from test_native_tree_profile_host import synthetic_producer_reader
        value,hashes,raw=envelope()
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve();root=parent/('stage3-'+NONCE);root.mkdir()
            (parent/'stage3-report.json').write_text(json.dumps(value['report']['stage3']),encoding='utf-8')
            (root/'http-family.out').write_bytes(raw)
            for quiet,bus in ((False,False),(True,True)):
                with synthetic_producer_reader(lane.full),mock.patch.object(lane.full,'final_client_process_census'):
                    wire=lane.finish_report(copy.deepcopy(value['report']),NONCE,root,quiet=quiet,bus_cleanup_failed=bus)
                failed=json.loads(wire)
                self.assertEqual(failed['outputs'],[])
                self.assertFalse(failed['report']['native_tests_completed'])
                with self.assertRaises(host.HTTPError):host.validate_envelope(wire,NONCE,hashes)

    def test_staged_inventory_and_network_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged=Path(tmp).resolve()/'staged'
            hashes=host.stage_inputs(ROOT,staged,host.SMOKE)
            command=host.container_command(staged,hashes,'onec-http-family-'+'b'*32,NONCE,host.SMOKE)
            self.assertEqual(command[-3:],['--http-family-suite','--invocation-nonce',NONCE])
            for key,value in [('--network','none'),('--user','1000:1000'),('--cap-drop','ALL')]:
                self.assertEqual(command[command.index(key)+1],value)
            self.assertIn('--read-only',command);self.assertNotIn('--privileged',command)
            self.assertNotIn('client_probe.bsl',str(host.staged_files()))
            (staged/'extra').write_bytes(b'not admitted')
            with self.assertRaises(host.HTTPError):host.validate_inputs(staged,hashes,host.SMOKE)

    def test_comparison_requires_available_not_equal_errors(self):
        _,hashes,raw=envelope()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            runner=mock.Mock(return_value=(0,raw,b''))
            self.assertEqual(host.compare_output(ROOT,root,raw,hashes,runner)['acceptance_status'],'accepted')
            bad=raw.replace(b'HT-18: [ok|S0:]',b'HT-18: [action-error]')
            runner.return_value=(0,bad,b'')
            result=host.compare_output(ROOT,root,bad,hashes,runner)
            self.assertEqual(result['acceptance_status'],'rejected')
            self.assertFalse(result['native_observations_available'])

    def test_actual_emitter_uses_only_http_lane(self):
        import io
        import types
        from test_native_tree_emitter_dispatch import EMITTER,arguments
        fake=types.ModuleType('http_suite');fake.finish_report=mock.Mock(return_value=b'owned-http-envelope\n')
        full=types.ModuleType('full_suite');full.native_processes_quiet=lambda path:True
        binary=io.BytesIO();output=io.TextIOWrapper(binary,encoding='utf-8',write_through=True)
        with mock.patch.object(sys,'argv',['emitter',*arguments('http-family')]),mock.patch.object(sys,'stdout',output),\
             mock.patch.dict(sys.modules,{'http_suite':fake,'full_suite':full}),\
             mock.patch.object(sys,'path',list(sys.path)),mock.patch.object(os,'geteuid',return_value=1000,create=True),\
             mock.patch.object(os,'access',return_value=False),self.assertRaises(SystemExit) as done:
            exec(compile(EMITTER,'owned-emitter','exec'),{})
        self.assertEqual(done.exception.code,0)
        self.assertEqual(binary.getvalue(),b'owned-http-envelope\n');output.detach()
        self.assertEqual(fake.finish_report.call_args.kwargs,dict(quiet=True,bus_cleanup_failed=False))

    def test_closed_shell_and_required_job(self):
        from native_workflow_shell import dispatch
        from test_native_1c_ci_policy import workflow_job
        shell=(ROOT/'scripts/native_1c_smoke_probe.sh').read_text(encoding='utf-8')
        setup='tree_suite=false\n'+shell.split('tree_suite=false\n',1)[1].split('if [ "$#" -ge 5 ]',1)[0]
        result=dispatch('set -- --http-family-suite --invocation-nonce '+NONCE+'\n'+setup+'printf "%s\\n" "$tree_suite" "$*"')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),['http-family','--full-suite --invocation-nonce '+NONCE+' --client-probe'])
        job=workflow_job('http_smoke');verdict=workflow_job('verdict')
        self.assertIn('native_1c_http_profile.py --execute-approved-image --export-native-outputs',job)
        self.assertIn('contents: read\n      packages: read',job)
        self.assertIn('native_1c_ci_policy.py bind',job)
        self.assertIn('HTTP_RESULT',verdict)
        self.assertIn('or os.environ.get("HTTP_RESULT") != "success"',verdict)


if __name__=='__main__':unittest.main()

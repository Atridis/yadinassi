"""Owned synthetic envelope/staging tests; no native platform or physical formats."""
import base64
import copy
import contextlib
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
import native_1c_catalog_object_profile as host
import catalog_object_suite as lane
from catalog_object_behavior import fixture,route
NONCE='a'*32


def values():
    rows=[True]*24
    for index in (9,10,13,17,20,21):rows[index-1]='owned'
    rows[17]=1
    return rows


def envelope():
    hashes={key:host.FULL.digest((ROOT/key).read_bytes()) for key in host.staged_files()}
    raw=route.canonical(values())
    stage=lane.empty_report(NONCE)
    module=host.FULL.digest(host.FULL.generated_module(route.program(fixture.load_saved()[0],NONCE)))
    stage.update(status='ok',failure_kind='none',failure_phase='final',input_sha256=hashes,
        source_sha256=host.SOURCE_SHA256,module_sha256=module,module_verified_sha256=module,
        output_sha256=host.FULL.digest(raw),output_size=len(raw),record_count=24)
    for key in host.FLAGS:stage[key]=True
    stage['process_diagnostics'].update(stage='after_exit',reason='none')
    value={'schema':host.SCHEMA,'profile':host.PROFILE,'nonce':NONCE,
        'report':{'status':'ok','native_tests_completed':True,'stage3':stage},
        'outputs':[{'name':'catalog-object.out','size':len(raw),'sha256':host.FULL.digest(raw),
                    'data_b64':base64.b64encode(raw).decode()}]}
    return value,hashes,raw


def identity(raw,**kwargs):return json.loads(raw)


class CatalogObjectProfileTests(unittest.TestCase):
    def setUp(self):
        # Only this imported host's own static fixtures: not a Windows security proof.
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patcher.start();self.addCleanup(patcher.stop)

    def test_real_outer_validator(self):
        from test_native_1c_smoke import bootstrap_report
        value,hashes,raw=envelope()
        outer=bootstrap_report();outer.update(native_tests_completed=True,stage3=value['report']['stage3'])
        value['report']=outer
        self.assertEqual(host.validate_envelope(json.dumps(value).encode(),NONCE,hashes)[1],raw)

    def test_identity_types_caps_and_witnesses_closed(self):
        value,hashes,raw=envelope()
        self.assertEqual(host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity)[1],raw)
        for key,replacement in [(k,False) for k in host.FLAGS]+[(k,'f'*64) for k in host.HASH_FIELDS]+[
            ('record_count',True),('output_size',True),('input_sha256',{}),('unknown','secret')]:
            bad=copy.deepcopy(value);bad['report']['stage3'][key]=replacement
            with self.subTest(key=key),self.assertRaises(host.CatalogObjectError):
                host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity)
        for key,replacement in [('nonce','b'*32),('profile','other'),('schema','other')]:
            bad=copy.deepcopy(value);bad[key]=replacement
            with self.assertRaises(host.CatalogObjectError):host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity)
        with self.assertRaises(host.CatalogObjectError):host.validate_envelope(b' '*65537,NONCE,hashes,identity)
        with self.assertRaises(host.CatalogObjectError):host.validate_envelope(json.dumps(value).encode(),NONCE,{},identity)

    def test_failure_has_no_partial_output_or_arbitrary_error(self):
        value,hashes,_=envelope();value['outputs']=[]
        value['report'].update(status='stage3_failed',native_tests_completed=False)
        stage=value['report']['stage3'];stage.update(status='failed',failure_kind='module_mismatch',failure_phase='redump',completed=False)
        with self.assertRaises(host.CatalogObjectError) as caught:
            host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity)
        self.assertEqual(caught.exception.native_failure['failure_phase'],'redump')
        stage['failure_phase']='private/path'
        with self.assertRaises(host.CatalogObjectError) as caught:
            host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity)
        self.assertFalse(hasattr(caught.exception,'native_failure'))
        value,hashes,_=envelope();value['report']['stage3']['status']='failed'
        with self.assertRaises(host.CatalogObjectError):host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity)

    def test_canonical_output_and_transport_reject(self):
        raw=route.canonical(values());self.assertEqual(host.parse_output(raw),values())
        for bad in (b'[]\n',raw+b' ',raw.replace(b'true',b'1',1),b'null\n'):
            with self.assertRaises(ValueError):host.parse_output(bad)
        value,hashes,_=envelope();value['outputs'][0]['data_b64']+='='
        with self.assertRaises(host.CatalogObjectError):host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity)

    def test_closed_staging_manifest_and_container_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged=Path(temporary).resolve()/'stage'
            hashes=host.stage_inputs(ROOT,staged,host.SMOKE)
            self.assertEqual(json.loads((staged/'catalog-inputs.json').read_bytes()),host.staged_files())
            self.assertNotIn('form_runtime',str(host.staged_files()))
            command=host.container_command(staged,hashes,'onec-catalog-object-'+'b'*32,NONCE,host.SMOKE)
            self.assertEqual(command[-3:],['--catalog-object-suite','--invocation-nonce',NONCE])
            for flag,expected in (('--network','none'),('--user','1000:1000'),('--memory','2g'),('--cpus','2')):
                self.assertEqual(command[command.index(flag)+1],expected)
            self.assertIn('--read-only',command);self.assertNotIn('--privileged',command)
            (staged/'catalog-inputs.json').write_bytes(b'{}')
            with self.assertRaises(host.CatalogObjectError):host.validate_inputs(staged,hashes,host.SMOKE)
            (staged/'catalog-inputs.json').write_bytes(host.manifest_bytes())
            (staged/'extra').write_bytes(b'x')
            with self.assertRaises(host.CatalogObjectError):host.validate_inputs(staged,hashes,host.SMOKE)

    def test_owned_cleanup_precedes_export(self):
        from test_native_1c_smoke import bootstrap_report
        value,hashes,raw=envelope()
        outer=bootstrap_report();outer.update(native_tests_completed=True,stage3=value['report']['stage3'])
        value['report']=outer
        events=[];cleanup_failed=False;native_failed=False
        def bounded(command,*args):
            if command[:3]==['docker','image','inspect']:return 0,b'linux/amd64|0'
            if command[:2]==['docker','run']:
                nonce=command[-1]
                current=copy.deepcopy(value);current['nonce']=nonce;current['report']['stage3']['nonce']=nonce
                module=host.FULL.digest(host.FULL.generated_module(route.program(fixture.load_saved()[0],nonce)))
                current['report']['stage3'].update(module_sha256=module,module_verified_sha256=module)
                if native_failed:
                    current['outputs']=[]
                    current['report'].update(status='stage3_failed',native_tests_completed=False)
                    current['report']['stage3'].update(status='failed',failure_kind='module_mismatch',failure_phase='redump',entered=False,completed=False,process_exited=False,witness_verified=False,output_size=None,record_count=None,output_sha256=None)
                return int(native_failed),json.dumps(current).encode()
            if command[:2]==['docker','ps']:
                events.append('container_clean');return 0,b'owned-still-running' if cleanup_failed else b''
            self.fail('unexpected command')
        def exported(root,files):
            self.assertEqual(events,['container_clean'])
            self.assertEqual(list(Path(temporary).iterdir()),[])
            events.append('export')
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ,{'GHCR_TOKEN':'synthetic','GHCR_USER':'owner'}), \
             mock.patch.object(host.FULL,'repository_provenance',return_value={}), \
             mock.patch.object(host.FULL,'interpreter_provenance',return_value={}), \
             mock.patch.object(host.FULL,'windows_fingerprints',return_value={}), \
             mock.patch.object(host.SMOKE,'run_silent'),mock.patch.object(host.SMOKE,'bounded_run',side_effect=bounded), \
             mock.patch.object(host,'compare_output',return_value={'acceptance_status':'accepted'}), \
             mock.patch.object(host,'export_artifact',side_effect=exported):
            result=host.run(ROOT,Path(temporary),export_native_outputs=True)
            self.assertTrue(result['private_payloads_removed']);self.assertEqual(events,['container_clean','export'])
            self.assertNotIn('GHCR_TOKEN',os.environ)
            events.clear();native_failed=True
            os.environ.update(GHCR_TOKEN='synthetic',GHCR_USER='owner')
            failed=host.run(ROOT,Path(temporary),export_native_outputs=True)
            self.assertEqual(failed['status'],'failed')
            self.assertFalse(failed['native_measurement_accepted'])
            self.assertFalse(failed['runtime_parity_accepted'])
            self.assertIsNone(failed['comparison'])
            self.assertEqual(failed['trusted_input_sha256'],hashes)
            self.assertEqual(failed['native_report']['stage3']['input_sha256'],hashes)
            self.assertIn('scripts/catalog_object_behavior/replay.py',failed['host_source_sha256'])
            self.assertTrue(failed['container_cleanup_verified'])
            self.assertTrue(failed['private_payloads_removed'])
            self.assertNotIn('native_artifact_sha256',failed)
            self.assertEqual(events,['container_clean'])
            events.clear();cleanup_failed=True
            os.environ.update(GHCR_TOKEN='synthetic',GHCR_USER='owner')
            with self.assertRaisesRegex(host.CatalogObjectError,'container_cleanup_unverified') as caught:
                host.run(ROOT,Path(temporary),export_native_outputs=True)
            self.assertEqual(events,['container_clean'])
            self.assertEqual(list(Path(temporary).iterdir()),[])
            self.assertFalse(hasattr(caught.exception,'validated_report'))
            self.assertFalse(hasattr(caught.exception,'native_failure'))
            cleanup_failed=False
            os.environ.update(GHCR_TOKEN='synthetic',GHCR_USER='owner')
            with mock.patch.object(host.FULL,'repository_provenance',side_effect=[{}, {'changed':True}]):
                with self.assertRaisesRegex(host.CatalogObjectError,'execution_provenance_changed') as caught:
                    host.run(ROOT,Path(temporary),export_native_outputs=True)
            self.assertFalse(hasattr(caught.exception,'validated_report'))
            self.assertEqual(list(Path(temporary).iterdir()),[])
            original_work=host.private_work
            @contextlib.contextmanager
            def fail_private_cleanup(*args):
                with original_work(*args) as directory:yield directory
                raise host.CatalogObjectError('private_cleanup_unverified')
            os.environ.update(GHCR_TOKEN='synthetic',GHCR_USER='owner')
            with mock.patch.object(host,'private_work',side_effect=fail_private_cleanup):
                with self.assertRaisesRegex(host.CatalogObjectError,'private_cleanup_unverified') as caught:
                    host.run(ROOT,Path(temporary),export_native_outputs=True)
            self.assertFalse(hasattr(caught.exception,'validated_report'))
            self.assertNotIn('export',events)

    @unittest.skipUnless(os.name=='posix','real isolated child containment is POSIX-only')
    def test_real_isolated_logical_replay(self):
        from catalog_object_behavior.replay import replay
        raw=route.canonical(replay())
        hashes={host.SOURCE:host.SOURCE_SHA256}
        with tempfile.TemporaryDirectory() as temporary:
            result=host.compare_output(ROOT,Path(temporary).resolve(),raw,hashes)
        self.assertEqual(result['status'],'matched')
        self.assertFalse(result['metadata_import_parity_claimed'])

    def test_comparison_contract_is_output_only(self):
        _,hashes,raw=envelope()
        with tempfile.TemporaryDirectory() as temporary:
            def run(args,root):
                self.assertIn('-I',args);self.assertIn('-B',args)
                self.assertIn('catalog_object_behavior.replay',args[-2])
                return 0,raw,b''
            result=host.compare_output(ROOT,Path(temporary),raw,hashes,run)
            self.assertEqual(result['status'],'matched')
            self.assertFalse(result['metadata_import_parity_claimed'])
            self.assertEqual(host.compare_output(ROOT,Path(temporary),raw,hashes,lambda *a:(1,b'',b'private'))['status'],'invalid_interpreter_output')

if __name__=='__main__':unittest.main()

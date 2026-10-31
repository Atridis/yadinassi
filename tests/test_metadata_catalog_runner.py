"""Local isolated runner/source/postimage tests; never launches native or Docker."""
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import os
import unittest
from unittest import mock
import test_metadata_catalog_acquisition as fixture
import test_native_1c_db_oracle_stage as stages
import metadata_catalog_inputs as inputs
import metadata_catalog_run as runner
import metadata_catalog_report as policy
import metadata_catalog_acquisition as measurement
import metadata_catalog_probe_contract as wire
import inject_metadata
import protocol
from snapshots import OracleError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import native_1c_metadata_catalog_oracle as host


def identity():
    result=stages.provenance();result['sources']=inputs.source_hashes(ROOT);return result


def helpers():
    return {context:hashlib.sha256(inject_metadata._module(name,stages.NONCE,
        '/tmp/onec-db-oracle/evidence',metadata_catalog_probe=True)).hexdigest()
        for context,name in (('client','ManagedApplicationModule.bsl'),('server','NativeOracleServer.bsl'))}


def captures(snapshot, length=None):
    length=(64 if snapshot=='applied' else 32) if length is None else length
    physical=stages.physical(snapshot)
    result=[]
    for context in measurement.CONTEXTS:
        config=dict(count=1,name='NativeOracleItems',payload_length=length,applied_state='not_observed')
        output=fixture.output(length)
        result.append(dict(snapshot=snapshot,context=context,
            token=hashlib.md5((snapshot+context).encode()).hexdigest(),
            origin={k:physical[k] for k in ('bytes','sha256')},
            postimage=dict(bytes=12288,sha256='b'*64),marker_sha256='c'*64,
            wire=output.decode(),config=config,comparison=measurement.compare(wire.validate_output(output),config)))
    return result


def report():
    ident=identity();backend=stages.FixtureNative(ident)
    backend.launch_metadata=lambda *a,**k:None;backend.metadata_attempt=None
    controller=runner.Controller(backend,protocol.empty_report(stages.NONCE,ident));backend.controller=controller
    with mock.patch.object(measurement,'acquire',side_effect=lambda b,s,**kw:captures(s)):
        lifecycle=controller.run()
    return dict(schema=1,lane=inputs.LANE,lifecycle=lifecycle,
        states=controller.metadata_states,verdict=controller.metadata_verdict,
        helpers=helpers(),measurement_failure=controller.metadata_failure)


class MetadataRunnerTests(unittest.TestCase):
    def test_staging_source_closure_and_old_lane_isolation(self):
        import inputs as old
        self.assertNotIn('metadata_catalog_run.py',old.SOURCE_FILES.values())
        ident=identity()
        with tempfile.TemporaryDirectory() as work:
            staged=Path(work)/'inputs';inputs.stage_inputs(ROOT,staged,stages.NONCE,ident)
            self.assertEqual(inputs.verify_inputs(staged,stages.NONCE),ident)
            (staged/'unexpected').write_text('x')
            with self.assertRaises(OracleError):inputs.verify_inputs(staged,stages.NONCE)
            (staged/'unexpected').unlink()
            (staged/'metadata_catalog_run.py').chmod(0o600)
            (staged/'metadata_catalog_run.py').write_text('changed')
            with self.assertRaises(OracleError):inputs.verify_inputs(staged,stages.NONCE)
    def test_cold_staged_import_and_helper_capture(self):
        ident=identity()
        with tempfile.TemporaryDirectory() as work:
            staged=Path(work)/'inputs';inputs.stage_inputs(ROOT,staged,stages.NONCE,ident)
            code="import metadata_catalog_run; import metadata_catalog_inputs as i; from pathlib import Path; i.verify_inputs(Path('.'),'"+stages.NONCE+"'); import inject_metadata; assert b'@@' not in inject_metadata._module('NativeOracleServer.bsl','"+stages.NONCE+"','/tmp/onec-db-oracle/evidence',metadata_catalog_probe=True)"
            result=subprocess.run([sys.executable,'-B','-c',code],cwd=staged,
                env={'PATH':os.environ.get('PATH','')},capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode())
    def test_legacy_generated_modules_are_identical_when_disabled(self):
        for name in ('ManagedApplicationModule.bsl','NativeOracleServer.bsl','SessionModule.bsl'):
            self.assertEqual(inject_metadata._module(name,stages.NONCE,'/owned'),
                inject_metadata._module(name,stages.NONCE,'/owned',metadata_catalog_probe=False))
    def test_full_synthetic_lifecycle_envelope(self):
        value=report()
        self.assertEqual(value['lifecycle']['status'],'ok')
        self.assertEqual(len(value['states']),6)
        policy.validate_report(policy.encode_report(value),nonce=stages.NONCE,provenance=value['lifecycle']['provenance'])
        for mutate in (lambda v:v['helpers'].update(client='a'*64),
                       lambda v:v['states'][2]['origin'].update(sha256='e'*64),
                       lambda v:v['states'][2]['comparison'].update(payload_matches=False),
                       lambda v:v['states'][2]['config'].update(payload_length=64),
                       lambda v:v.update(states=v['states'][:-1]),
                       lambda v:v.update(verdict='not_established')):
            bad=copy.deepcopy(value);mutate(bad)
            with self.assertRaises((OracleError,ValueError)):
                policy.validate_report(policy.encode_report(bad),nonce=stages.NONCE,provenance=value['lifecycle']['provenance'])
    def test_constructive_component_budgets(self):
        value=report()
        largest=wire.C1+wire.C2+b''.join(f'MC-{i:02}: [ok|S64:'.encode()+b'0061'*64+b']\n' for i in range(1,27))
        self.assertEqual(len(largest),7148)
        for state in value['states']:
            state['wire']=largest.decode()
            state['config']['name']='x'*64
            state['comparison']=measurement.compare(wire.validate_output(largest),state['config'])
        raw=policy.encode_report(value)
        self.assertLess(len(raw),policy.MAX_REPORT_BYTES)
        self.assertEqual(policy.MAX_REPORT_BYTES,32768+65536+1024)
        for mutate in (lambda v:v['states'][0].update(wire='x'*measurement.MAX_STATE_BYTES),
                       lambda v:v.update(verdict='x'*1024),
                       lambda v:v.update(states=v['states']+[v['states'][0]])):
            bad=copy.deepcopy(value);mutate(bad)
            with self.assertRaises(OracleError):policy.encode_report(bad)
    def test_host_preflight_missing_credentials_is_closed_and_clean(self):
        ident=identity()
        with tempfile.TemporaryDirectory() as work,mock.patch.object(host,'provenance',return_value=ident),mock.patch.dict(host.os.environ,{},clear=True):
            value=host.run_oracle(Path(work))
        self.assertEqual(value['lifecycle']['failure_kind'],'registry_credentials_missing')
        self.assertTrue(all(value['lifecycle']['cleanup'].values()))
        self.assertFalse(value['lifecycle']['accepted'])
    def test_container_is_confined_and_closed(self):
        ident=identity()
        with tempfile.TemporaryDirectory() as work:
            staged=Path(work)/'inputs';inputs.stage_inputs(ROOT,staged,stages.NONCE,ident)
            command=host.container_command(staged,'onec-db-oracle-'+'d'*32,stages.NONCE)
            self.assertEqual(command[command.index('--network')+1],'none')
            self.assertEqual(command[command.index('--user')+1],'1000:1000')
            for flag in ('--read-only','--cap-drop','--init','--tmpfs'):self.assertIn(flag,command)
            self.assertEqual(command[-5:],['python3','-B','/oracle/metadata_catalog_run.py','--invocation-nonce',stages.NONCE])
    def test_acquisition_separate_clones_and_exact_postimage(self):
        events=[];image=fixture.source();summary=dict(bytes=image.size,sha256='a'*64)
        class Backend:
            stage='update';nonce=stages.NONCE;artifacts=Path('/synthetic-only')
            def remaining(self):events.append('remaining')
            def physical_summary(self,path):return dict(summary,header='unknown',page_analysis='unsupported')
            @contextmanager
            def temporary_clone(self,identifier,label):
                events.append('clone');yield self.artifacts/'auditor';events.append('remove-clone')
            @contextmanager
            def command_context(self,op):yield
            def quiescent(self):return True
            def budgets(self,*a):pass
            def remove(self,p):events.append('remove-frozen')
        backend=Backend()
        tokens=[]
        def launch(db,context,token):
            events.append('launch-'+context);tokens.append(token)
            return json.dumps(dict(schema=1,nonce=stages.NONCE,token=token,
                operation='metadata_catalog_'+context,status='ok',output=fixture.output().decode())).encode()
        def inspect(path,**kw):
            events.append('read')
            self.assertEqual(path,backend.artifacts/'auditor_frozen')
            return summary.copy(),kw['read_catalog'](image.read_at,image.size,limits=kw['limits'])
        with mock.patch.object(measurement,'freeze_database',return_value=summary),mock.patch.object(measurement,'inspect_frozen_catalog',side_effect=inspect),mock.patch.object(runner.lifecycle,'absent'):
            result=measurement.acquire(backend,'updated',launch=launch)
        self.assertEqual(len(set(tokens)),2)
        self.assertEqual(events.count('clone'),2)
        self.assertLess(events.index('remove-clone'),events.index('launch-server'))
        self.assertTrue(all(r['comparison']['payload_matches']for r in result))
        self.assertIsNone(backend.metadata_attempt)
    def test_launch_completion_nonce_and_cleanup(self):
        for bad in (None,'token','schema','status','operation','absent'):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as work:
                backend=runner.Native(stages.NONCE,identity())
                backend.stage='update';backend.evidence=Path(work)/'evidence';backend.evidence.mkdir()
                backend.artifacts=Path(work)/'artifacts';backend.artifacts.mkdir()
                database=backend.artifacts/'auditor';database.mkdir()
                backend.remaining=lambda:10
                token='b'*32
                def process(*args,**kw):
                    completion=dict(schema=1,nonce=stages.NONCE,token=token,
                        operation='metadata_catalog_client',phase='complete',status='ok')
                    if bad=='absent':return
                    if bad=='token':completion['token']='c'*32
                    if bad=='schema':completion['schema']=True
                    if bad=='status':completion['status']='error';completion['phase']='probe'
                    if bad=='operation':completion['operation']='audit_record_metadata'
                    (backend.evidence/'completion.json').write_text(json.dumps(completion))
                    (backend.evidence/'result.json').write_text(json.dumps(dict(schema=1,nonce=stages.NONCE,
                        token=token,operation='metadata_catalog_client',status='ok',output=fixture.output().decode())))
                backend.process=process
                if bad is None:
                    self.assertTrue(backend.launch_metadata(database,context='client',token=token))
                else:
                    with self.assertRaises(OracleError):backend.launch_metadata(database,context='client',token=token)
                self.assertFalse(any((backend.evidence/name).exists() for name in (
                    'control.json','result.json','completion.json','completion.pending.json')))
    def test_failed_reader_removes_frozen_and_preserves_failure_phase(self):
        events=[]
        class Backend:
            stage='load_cf';nonce=stages.NONCE;artifacts=Path('/synthetic-only')
            def remaining(self):pass
            def physical_summary(self,path):return dict(bytes=12288,sha256='a'*64,header='unknown',page_analysis='unsupported')
            @contextmanager
            def temporary_clone(self,*a):
                try:yield self.artifacts/'auditor'
                finally:events.append('clone-removed')
            @contextmanager
            def command_context(self,*a):yield
            def quiescent(self):return True
            def budgets(self,*a):pass
            def remove(self,p):events.append('frozen-removed')
        backend=Backend()
        def launch(db,context,token):
            return json.dumps(dict(schema=1,nonce=stages.NONCE,token=token,
                operation='metadata_catalog_'+context,status='ok',output=fixture.output().decode())).encode()
        with mock.patch.object(measurement,'freeze_database',return_value=dict(bytes=12288,sha256='a'*64)),mock.patch.object(measurement,'inspect_frozen_catalog',side_effect=measurement.filedb_catalog.UnsupportedLayout('test')),mock.patch.object(runner.lifecycle,'absent'):
            with self.assertRaises(OracleError) as caught:measurement.acquire(backend,'loaded',launch=launch)
        self.assertEqual(caught.exception.kind,'metadata_rejected')
        self.assertEqual(events,['frozen-removed','clone-removed'])
        self.assertEqual(backend.metadata_attempt,dict(snapshot='loaded',context='client',phase='reader'))
    def test_wrong_stage_never_launches(self):
        backend=mock.Mock(stage='baseline')
        with self.assertRaises(OracleError):measurement.acquire(backend,'updated',launch=backend.launch)
        backend.launch.assert_not_called()
    def test_failure_context_and_cleanup_preserved(self):
        ident=identity();backend=stages.FixtureNative(ident)
        backend.launch_metadata=lambda *a,**k:None
        controller=runner.Controller(backend,protocol.empty_report(stages.NONCE,ident));backend.controller=controller
        def broken(b,s,**kw):
            b.metadata_attempt=dict(snapshot=s,context='server',phase='reader')
            raise OracleError('metadata_rejected')
        with mock.patch.object(measurement,'acquire',side_effect=broken):value=controller.run()
        self.assertEqual(value['failed_stage'],'update')
        self.assertEqual(controller.metadata_failure,dict(snapshot='updated',context='server',phase='reader'))
        self.assertTrue(value['cleanup']['raw_files_removed'])

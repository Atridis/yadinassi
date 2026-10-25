"""Explicit local observation routing and frozen-postimage mechanics, never native proof."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage'),
                str(ROOT/'scripts'), str(ROOT/'tests')]
import comparison
import inputs
import protocol
import record_observation as observation
import snapshots
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_comparison as old
from test_native_1c_db_oracle_catalog_reader import normalize_owners
from test_filedb_catalog import Source, descriptor

_spec = importlib.util.spec_from_file_location('record_observation_host_under_test', ROOT/'scripts/native_1c_db_oracle.py')
host = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(host)
NONCE = fixtures.NONCE
TOKEN = 'd'*32


def identity():
    value = fixtures.provenance()
    value['sources'] = {source:'c'*64 for source in inputs.RECORD_SOURCE_FILES}
    return value


def native_projection():
    return {'schema':1,'target':comparison.TARGET,'table':{
        'storage_name':'Physical','logical_name':'Catalog.NativeOracleItems','metadata_name':'',
        'fields':[{'storage_name':'Field','logical_name':'','metadata_name':'','type_text':'Uninterpreted'}]}}


def marker(token=TOKEN):
    value = old.marker(token)
    del value['storage_names']
    value.update(operation=observation.OPERATION, record_metadata=native_projection())
    return value


def source(private=False):
    return Source().ready({2:descriptor(field_type='N'), **({3:descriptor('PRIVATE')} if private else {})})


def evidence(token=TOKEN):
    data = source()
    _, physical = observation.project_catalog(old.catalog(data), native_projection())
    return {'marker':marker(token),
        'origin':{'nonce':NONCE,'token':token,'clone':'auditor',
                  **{key:fixtures.physical('baseline')[key] for key in ('bytes','sha256')}},
        'postimage':{'bytes':data.size,'sha256':hashlib.sha256(data.full_bytes()).hexdigest()},
        'reader':physical}


class Backend(fixtures.FixtureNative):
    def observe_record_metadata(self, identifier):
        self.event('record_metadata', identifier)
        return evidence()


def fixture(fail=None, cleanup=(True,True)):
    provenance = identity(); report = observation.empty_report(NONCE, provenance)
    backend = Backend(provenance, fail); backend.clean = cleanup
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


def writable(root):
    for path in (root,*root.rglob('*')):
        if not path.is_symlink(): path.chmod(0o755 if path.is_dir() else 0o644)


class ExplicitRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:writable(self.root))

    def stage(self, observed):
        target = self.root/('new' if observed else 'old')
        value = fixtures.provenance(); value['sources'] = inputs.source_hashes(ROOT,record_metadata=observed)
        inputs.stage_inputs(ROOT,target,NONCE,value,record_metadata=observed)
        return target,value

    def test_exact_inventories_invocations_and_cross_lane_rejection(self):
        self.assertEqual(len(inputs.SOURCE_FILES),20)
        self.assertEqual(len(inputs.RECORD_SOURCE_FILES),21)
        self.assertEqual(set(inputs.RECORD_SOURCE_FILES)-set(inputs.SOURCE_FILES),
                         {'scripts/native_1c_db_oracle/record_observation.py'})
        for observed in (False,True):
            target,value = self.stage(observed)
            self.assertEqual(inputs.verify_inputs(target,NONCE,record_metadata=observed),value)
            invocation = json.loads((target/'invocation.json').read_text(encoding='utf-8'))
            self.assertEqual(invocation['schema'],2 if observed else 1)
            self.assertEqual('lane' in invocation,observed)
            self.assertEqual((target/'record_observation.py').exists(),observed)
            with self.assertRaises(OracleError): inputs.verify_inputs(target,NONCE,record_metadata=not observed)
            with self.assertRaises(OracleError): inputs.staged_hashes(target,record_metadata=not observed)

    def test_new_invocation_mode_missing_changed_extra_and_source_mutation_reject(self):
        target,value = self.stage(True); writable(target)
        original=(target/'invocation.json').read_bytes()
        for edit in (lambda v:v.pop('lane'),lambda v:v.update(lane='default'),
                     lambda v:v.update(schema=1),lambda v:v.update(extra='PRIVATE')):
            data=json.loads(original); edit(data)
            (target/'invocation.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(OracleError): inputs.verify_inputs(target,NONCE,record_metadata=True)
        (target/'invocation.json').write_bytes(original)
        with (target/'record_observation.py').open('ab') as stream: stream.write(b'\n# altered\n')
        with self.assertRaises(OracleError): inputs.verify_inputs(target,NONCE,record_metadata=True)

    def test_default_staged_runtime_imports_without_unstaged_new_module(self):
        target,_=self.stage(False)
        code = ("import sys;sys.path.insert(0,sys.argv[1]);import run,comparison,inputs;"
                "assert 'record_observation' not in sys.modules;"
                "n=run.Native('a'*32,{});assert n.observation is None;"
                "assert 'enterprise_audit_record_metadata' not in n.command_stages();"
                "assert 'record_observation' not in sys.modules")
        completed=subprocess.run([sys.executable,'-I','-B','-c',code,str(target)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
        self.assertEqual(completed.returncode,0,completed.stderr.decode('utf-8'))
        self.assertEqual(completed.stdout,b'')

    def test_container_adds_only_explicit_flag_and_retains_isolation(self):
        old_target,_=self.stage(False); new_target,_=self.stage(True)
        name='onec-db-oracle-'+'b'*32
        old_command=host.container_command(old_target,name,NONCE)
        new_command=host.container_command(new_target,name,NONCE,record_metadata=True)
        self.assertEqual(new_command[-1],'--record-metadata-observation')
        # Only the authorized stage path and explicit selection differ.
        expected=[item.replace(str(old_target),str(new_target)) for item in old_command]
        self.assertEqual(new_command[:-1],expected)
        self.assertEqual(new_command[new_command.index('--network')+1],'none')
        self.assertEqual(new_command[new_command.index('--log-driver')+1],'none')
        self.assertEqual((host.MAX_RUNTIME,fixtures.stage.WORK_SECONDS,fixtures.stage.COMMAND_SECONDS),
                         (2400,2340,120))

    def test_host_cli_default_and_explicit_flag_select_exact_route(self):
        for observed in (False,True):
            result={'accepted':False}
            with mock.patch.object(host,'ROOT',self.root), mock.patch.object(host,'run_oracle',return_value=result) as run, \
                 mock.patch.object(host,'export_report') as export, mock.patch.dict(os.environ,{},clear=True), \
                 contextlib.redirect_stdout(__import__('io').StringIO()):
                args=['--execute-approved-image','--file-db-oracle']+(['--record-metadata-observation'] if observed else [])
                self.assertEqual(host.main(args),1)
                self.assertEqual(run.call_args.kwargs,{'record_metadata':True} if observed else {})
                export.assert_called_once()

    def test_old_validator_new_operation_payload_phase_and_context_reject(self):
        with self.assertRaises(OracleError):
            protocol.marker(protocol.encode(marker()),nonce=NONCE,token=TOKEN,
                            operation=observation.OPERATION,contract_version=4)
        done={'schema':1,'nonce':NONCE,'token':TOKEN,'operation':observation.OPERATION,'phase':'complete','status':'ok'}
        with self.assertRaises(OracleError): protocol.completion_marker(protocol.encode(done),nonce=NONCE,token=TOKEN,operation=observation.OPERATION)
        context={'operation':'enterprise_audit_record_metadata','site':'result','bsl_phase':'record_scan','region':None,'reason':None}
        with self.assertRaises(OracleError): protocol.validate_failure_context(context,'baseline')
        report,_=fixture()
        for validator in (protocol.validate_report,comparison.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=report['provenance'])


class ObservationLifecycleTests(unittest.TestCase):
    def check(self,report):
        return observation.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity())

    def test_baseline_replacement_keeps_full_existing_lifecycle(self):
        report,backend=fixture(); self.check(report)
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertNotIn(('audit_clone','baseline'),backend.events)
        self.assertIn(('audit_clone','restored'),backend.events)
        self.assertNotIn('storage_contract',report)
        self.assertLess(backend.events.index(('record_metadata','baseline')),backend.events.index(('discard','baseline')))
        for key in ('mapping_validation','record_validation'): self.assertEqual(report[key],'not_run')
        self.assertEqual(report['layout_validation'],'declarations_only')
        self.assertEqual(report['native_compatibility'],'not_claimed')

    def test_every_later_stage_or_native_cleanup_failure_discards_projection(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed); self.check(report)
            self.assertIsNone(report['record_observation']); self.assertNotIn(b'Uninterpreted',protocol.encode(report))
            self.assertNotEqual(report['metadata_validation'],'metadata_projection_captured')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup); self.check(report)
            self.assertIsNone(report['record_observation']); self.assertEqual(report['artifacts'],[])

    def test_attempted_reader_timeout_or_unexpected_failure_is_not_reported_not_run(self):
        for error in (OracleError('timeout'), AssertionError('PRIVATE')):
            provenance=identity(); report=observation.empty_report(NONCE,provenance)
            backend=Backend(provenance); controller=fixtures.stage.Controller(backend,report); backend.controller=controller
            def observe(_identifier):
                backend.reader_attempted=True
                raise error
            backend.observe_record_metadata=observe
            result=controller.run(); self.check(result)
            self.assertEqual(result['reader_validation'],'failed')
            self.assertEqual(result['metadata_validation'],'not_run')
            self.assertIsNone(result['record_observation']); self.assertNotIn(b'PRIVATE',protocol.encode(result))

    def test_finite_reader_rejection_and_new_native_context_are_lane_scoped(self):
        for error in (observation.ObservationFailure('unsupported_layout','declaration_token'),
                      comparison.reader_failure(fixtures.stage.filedb_catalog.ResourceLimit('read_bytes'))):
            provenance=identity(); report=observation.empty_report(NONCE,provenance)
            backend=Backend(provenance); controller=fixtures.stage.Controller(backend,report); backend.controller=controller
            backend.observe_record_metadata=mock.Mock(side_effect=error)
            result=controller.run(); self.check(result)
            self.assertEqual(result['failure_kind'],observation.FAILURE_KIND)
            self.assertFalse(result['accepted']); self.assertNotIn(b'Uninterpreted',protocol.encode(result))
        native=fixtures.stage.Native(NONCE,identity(),record_metadata=True); native.stage='baseline'
        with self.assertRaises(OracleError) as caught:
            with native.command_context('enterprise_audit_record_metadata'):
                error=OracleError('artifact_limit'); error.oracle_site='result'; error.bsl_phase='record_limit'; raise error
        self.assertEqual(caught.exception.failure_context['bsl_phase'],'record_limit')
        ordinary=fixtures.stage.Native(NONCE,identity()); ordinary.stage='baseline'
        with mock.patch.object(ordinary,'_enterprise') as launch, self.assertRaises(OracleError):
            ordinary.enterprise(Path('/unused'),observation.OPERATION)
        launch.assert_not_called()


@unittest.skipIf(os.name=='nt','POSIX anchored frozen postimage boundary')
class ObservationPostimageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.artifacts=self.root/'artifacts'; self.artifacts.mkdir()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:writable(self.root)); normalize_owners(self)
        self.seed=self.artifacts/'seed'; self.seed.mkdir(); self.pre=source(); self.post=source(True)
        (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed,self.artifacts/'baseline',quiescent=lambda:True)
        self.native=fixtures.stage.Native(NONCE,identity(),record_metadata=True)
        self.native.root=self.root; self.native.artifacts=self.artifacts; self.native.stage='baseline'
        self.native.quiescent=lambda:True; self.native.budgets=mock.Mock(); self.calls=[]
        def enterprise(database,operation,*,token):
            self.calls.append((database,operation,token)); (database/'1Cv8.1CD').write_bytes(self.post.full_bytes())
            return marker(token)
        self.native.enterprise=enterprise

    def test_independent_closed_postimage_parse_and_both_cleanup_gates(self):
        with mock.patch.object(fixtures.stage.filedb_catalog,'read_catalog',wraps=fixtures.stage.filedb_catalog.read_catalog) as read:
            result=self.native.observe_record_metadata('baseline')
        read.assert_called_once(); self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][:2],(self.artifacts/'auditor',observation.OPERATION))
        self.assertEqual(result['origin']['token'],result['marker']['token'])
        self.assertNotEqual(result['origin']['sha256'],result['postimage']['sha256'])
        self.assertEqual(result['postimage']['sha256'],hashlib.sha256(self.post.full_bytes()).hexdigest())
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())
        self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(),self.pre.full_bytes())
        self.assertNotIn(b'PRIVATE',protocol.encode(result['reader']))
        self.assertGreaterEqual(self.native.budgets.call_args_list.count(mock.call(self.pre.size)),2)

    def test_prelaunch_changed_origin_rejects_without_native_call(self):
        original=self.native.clone
        def clone(*args):
            result=original(*args); (result/'1Cv8.1CD').write_bytes(self.post.full_bytes()); return result
        self.native.clone=clone
        with self.assertRaises(observation.ObservationFailure) as caught: self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.code,'origin_changed'); self.assertEqual(self.calls,[])

    def test_changed_postimage_rejects_and_removes_private_clones(self):
        original=snapshots.inspect_frozen_catalog
        def inspect(*args,**kwargs):
            summary,catalog=original(*args,**kwargs); summary['sha256']='e'*64; return summary,catalog
        with mock.patch.object(snapshots,'inspect_frozen_catalog',side_effect=inspect), self.assertRaises(observation.ObservationFailure) as caught:
            self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.code,'postimage_changed')
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_remove_failure_deadline_and_wrong_scope_never_return_evidence(self):
        with self.assertRaises(OracleError): self.native.observe_record_metadata('created')
        self.native.stage='create'
        with self.assertRaises(OracleError): self.native.observe_record_metadata('baseline')
        self.assertEqual(self.calls,[]); self.native.stage='baseline'; self.native.deadline=0
        with self.assertRaises(OracleError) as caught: self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.kind,'timeout')
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())
        self.native.deadline=__import__('time').monotonic()+60
        original=self.native.remove
        def remove(path):
            if path.name=='auditor_frozen': raise OracleError('cleanup_unverified')
            return original(path)
        self.native.remove=remove
        with self.assertRaises(OracleError) as caught: self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.kind,'cleanup_unverified')


class ObservationHostCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:writable(self.root))
        self.work=self.root/'work'; self.work.mkdir()
        self.identity=fixtures.provenance()
        self.identity['sources']=inputs.source_hashes(ROOT,record_metadata=True)
        self.events=[]

    def invoke(self, *, native_cleanup=(True,True), container_bad=False, staging_bad=False, source_changed=False):
        report,_=fixture(cleanup=native_cleanup)
        report['provenance']=copy.deepcopy(self.identity)
        report['provenance']['actual_version']=protocol.VERSION
        if report['status']=='ok': report['record_observation']=observation.bind_capture(evidence(),report)
        def provenance(**kwargs):
            self.assertEqual(kwargs,{'record_metadata':True})
            self.assertNotIn('GHCR_TOKEN',os.environ); self.assertNotIn('GHCR_USER',os.environ)
            self.events.append('provenance'); value=copy.deepcopy(self.identity)
            if source_changed and self.events.count('provenance')>1: value['tree']='e'*40
            return value
        def silent(args,env,seconds,input_bytes=None):
            self.assertNotIn('GHCR_TOKEN',os.environ); self.assertNotIn('GHCR_USER',os.environ)
            self.assertNotIn('PRIVATE-SECRET',json.dumps(args)); self.assertNotIn('PRIVATE-SECRET',json.dumps(env))
            self.events.append(args[1])
        def bounded(args,env,seconds,limit):
            self.events.append(args[1])
            if args[1]=='image': return 0,b'linux/amd64|0'
            if args[1]=='ps': return 0,b'still-live' if container_bad else b''
            self.assertEqual(args[1],'run'); self.assertEqual(args[-1],'--record-metadata-observation')
            self.assertEqual((seconds,limit),(2400,32768))
            return (0 if report['status']=='ok' else 1),protocol.encode(report)
        class LeftoverDirectory:
            def __init__(self,**kwargs): self.name=tempfile.mkdtemp(**kwargs)
            def __enter__(self): return self.name
            def __exit__(self,*args): return False
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ,{'GHCR_USER':'Atridis','GHCR_TOKEN':'PRIVATE-SECRET'},clear=True))
            stack.enter_context(mock.patch.object(host,'provenance',side_effect=provenance))
            stack.enter_context(mock.patch.object(host.uuid,'uuid4',return_value=SimpleNamespace(hex=NONCE)))
            stack.enter_context(mock.patch.object(host.smoke,'run_silent',side_effect=silent))
            stack.enter_context(mock.patch.object(host.smoke,'bounded_run',side_effect=bounded))
            popen=stack.enter_context(mock.patch.object(host.smoke.subprocess,'Popen',side_effect=AssertionError('real process forbidden')))
            run=stack.enter_context(mock.patch.object(host.smoke.subprocess,'run',side_effect=AssertionError('real process forbidden')))
            if staging_bad: stack.enter_context(mock.patch.object(host.tempfile,'TemporaryDirectory',LeftoverDirectory))
            result=host.run_oracle(self.work,record_metadata=True)
            popen.assert_not_called(); run.assert_not_called()
        observation.validate_report(protocol.encode(result),nonce=NONCE,provenance=self.identity,final=True)
        self.assertNotIn(b'PRIVATE-SECRET',protocol.encode(result))
        return result

    def test_host_accepts_only_all_four_cleanup_gates(self):
        result=self.invoke()
        self.assertTrue(result['accepted']); self.assertTrue(all(result['cleanup'].values()))
        self.assertEqual(list(self.work.iterdir()),[])
        self.assertEqual(self.events,['provenance','login','pull','image','run','rm','ps','provenance'])

    def test_each_late_host_cleanup_failure_discards_both_projections(self):
        for kwargs in ({'container_bad':True},{'staging_bad':True}):
            self.events.clear()
            result=self.invoke(**kwargs)
            self.assertFalse(result['accepted']); self.assertIsNone(result['record_observation'])
            self.assertEqual(result['metadata_validation'],'discarded')
            self.assertEqual(result['layout_validation'],'not_run')
            self.assertNotIn(b'Uninterpreted',protocol.encode(result)); self.assertEqual(result['artifacts'],[])
            writable(self.work)
            for child in self.work.iterdir(): shutil.rmtree(child)

    def test_native_cleanup_failure_never_promotes_partial_capture(self):
        for gates in ((False,True),(True,False),(False,False)):
            self.events.clear(); result=self.invoke(native_cleanup=gates)
            self.assertFalse(result['accepted']); self.assertIsNone(result['record_observation'])
            self.assertEqual(result['artifacts'],[])

    def test_source_changed_after_runtime_discards_capture(self):
        result=self.invoke(source_changed=True)
        self.assertFalse(result['accepted']); self.assertIsNone(result['record_observation'])
        self.assertEqual(result['failure_kind'],'provenance_mismatch')


if __name__=='__main__': unittest.main()

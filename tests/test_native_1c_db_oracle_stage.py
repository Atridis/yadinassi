"""Synthetic controller fixtures, not evidence from a native 1C installation."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
HELPERS=ROOT/'scripts/native_1c_db_oracle'
if str(HELPERS) not in sys.path: sys.path.insert(0,str(HELPERS))
import protocol as protocol
from snapshots import OracleError
SPEC=importlib.util.spec_from_file_location('db_oracle_controller_under_test',HELPERS/'run.py')
stage=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(stage)
NONCE='a'*32


def provenance():
    return {'commit':'a'*40,'tree':'b'*40,'sources':{'synthetic':'c'*64},'image':protocol.IMAGE,
        'platform':'linux/amd64','actual_version':None,'locale':'ru_RU.UTF-8','timezone':'Etc/UTC'}


def physical(tag='fixture'):
    return {'bytes':4,'sha256':hashlib.sha256(tag.encode()).hexdigest(),
        'header':'unknown','page_analysis':'unsupported'}


def comparison():
    counts={'changed_bytes':0,'unchanged_bytes':4,'added_bytes':0,'removed_bytes':0,
        'size_delta':0,'changed_windows':0}
    return {'predecessor_bytes':4,'control_bytes':4,'treatment_bytes':4,'control':counts.copy(),
        'treatment':counts.copy(),'byte_windows':{'window_bytes':65536,'count':1,
            'overlap_count':0,'control_only_count':0,'treatment_only_count':0,
            'overlap_sample':[],'control_only_sample':[],'treatment_only_sample':[]},
        'interpretation':'physical_byte_differences_not_causation'}


class FixtureNative:
    def __init__(self,provenance,fail=None):
        self.events=[]; self.provenance=provenance; self.dbs={}; self.reference=False
        self.fail=fail; self.clean=(True,True); self.controller=None
    def event(self,*args):
        self.events.append(args)
        if self.fail==self.controller.stage and args[0]!='cleanup':
            self.fail=None; raise OracleError('process_failed')
    def preflight(self): self.event('preflight')
    def seed(self):
        self.event('seed'); self.provenance['actual_version']=protocol.VERSION
        self.dbs['seed']={'designer':1,'applied':1,'row':None}; return 'seed'
    def freeze(self,database,identifier):
        self.event('freeze',database,identifier)
        self.dbs[identifier]=self.dbs.pop(database)
        return physical(identifier)
    def observe(self,identifier,designer):
        self.event('observe_clone',identifier,designer)
        data=self.dbs[identifier]; assert data['designer']==designer
        row=data['row']
        return {'count':0 if row is None else 1,'code':None if row is None else 'K1',
            'payload':None if row is None else row[0],'amount':None if row is None else row[1],
            'deletion_mark':None if row is None else False,
            'same_reference':True if row else (False if self.reference else None),
            'payload_length':32*data['applied'],'amount_digits':9,'amount_scale':2,
            'designer_version':designer,'applied_version':data['applied'],
            'user':'NativeOracleCRUD','role_verified':True,'nonprivileged':True}
    def audit(self,identifier): self.event('audit_clone',identifier)
    def clone(self,identifier,label):
        self.event('clone',identifier,label); assert label not in self.dbs
        self.dbs[label]=copy.deepcopy(self.dbs[identifier]); return label
    def mutate(self,database,operation):
        self.event('mutate',database,operation)
        if operation=='create': self.dbs[database]['row']=('alpha','1.25'); self.reference=True
        elif operation=='update': self.dbs[database]['row']=('beta','-2.50')
        elif operation=='delete': self.dbs[database]['row']=None
        else: assert operation=='observe'
    def compare(self,*names): self.event('compare',*names); return comparison()
    def discard(self,*names):
        self.event('discard',*names)
        for name in names: del self.dbs[name]
    def compare_pair(self,source,treatment):
        self.event('compare_pair',source,treatment)
        paired=comparison()
        return {'predecessor_bytes':4,'treatment_bytes':4,'treatment':paired['treatment'],
            'byte_windows':{'window_bytes':65536,'count':1,'changed_count':0,'changed_sample':[]},
            'interpretation':'observational_before_after_not_causation'}
    def export_configs(self): self.event('export_configs_from_baseline')
    def artifact(self,identifier): self.event('artifact',identifier); return physical(identifier)
    def load_cf(self,database,version):
        self.event('load_cf',database,version); self.dbs[database]['designer']=version
    def apply(self,database):
        self.event('apply',database); self.dbs[database]['applied']=self.dbs[database]['designer']
    def dump_dt(self):
        self.event('dump_dt_clone','applied'); self.saved=copy.deepcopy(self.dbs['applied'])
    def restore(self):
        self.event('restore_distinct'); self.dbs['restore-target']=copy.deepcopy(self.saved); return 'restore-target'
    def cleanup(self): self.event('cleanup'); return self.clean


def fixture_report(fail=None):
    identity=provenance(); report=protocol.empty_report(NONCE,identity)
    backend=FixtureNative(identity,fail); controller=stage.Controller(backend,report); backend.controller=controller
    return controller.run(),backend


class LifecycleTests(unittest.TestCase):
    def test_complete_synthetic_lifecycle(self):
        report,backend=fixture_report()
        self.assertEqual(report['status'],'ok')
        protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=report['provenance'])
        self.assertFalse(report['accepted'])
        self.assertEqual([x['id'] for x in report['snapshots']],list(protocol.SNAPSHOTS))
        self.assertEqual(len(report['comparisons']),5)

    def test_every_primary_is_frozen_before_auxiliary_observation(self):
        _,backend=fixture_report()
        for index,event in enumerate(backend.events):
            if event[0]=='freeze':
                self.assertEqual(backend.events[index+1][:2],('observe_clone',event[2]))

    def test_loaded_config_observed_v1_before_distinct_apply(self):
        report,backend=fixture_report()
        loaded=next(x for x in report['snapshots'] if x['id']=='loaded')['logical']
        self.assertEqual((loaded['designer_version'],loaded['applied_version']),(2,1))
        events=backend.events
        load=events.index(('load_cf','writer',2)); apply=events.index(('apply','writer'))
        observed=events.index(('observe_clone','loaded',2))
        self.assertLess(load,observed); self.assertLess(observed,apply)
        self.assertNotIn(('designer_noop','writer'),events)
        apply_comparison=next(x for x in report['comparisons'] if x['id']=='apply_cf')
        self.assertIsNone(apply_comparison['control'])
        self.assertEqual(apply_comparison['kind'],'observational')

    def test_restore_distinct_after_delete_never_applies(self):
        report,backend=fixture_report(); events=backend.events
        restored=events.index(('restore_distinct',))
        self.assertFalse(any(event[0]=='apply' for event in events[restored:]))
        self.assertIn(('observe_clone','deleted',2),events[restored:])
        self.assertNotEqual(next(x['physical']['sha256'] for x in report['snapshots'] if x['id']=='applied'),
                            next(x['physical']['sha256'] for x in report['snapshots'] if x['id']=='restored'))

    def test_failures_stop_dependencies_and_still_clean(self):
        for failed in protocol.STAGES[:-1]:
            with self.subTest(stage=failed):
                report,backend=fixture_report(failed)
                self.assertEqual(report['failed_stage'],failed)
                self.assertEqual(report['failure_kind'],'process_failed')
                self.assertEqual(report['artifacts'],[])
                self.assertEqual(backend.events[-1],('cleanup',))
                protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=report['provenance'])

    def test_cleanup_failure_rejects_otherwise_good_run(self):
        identity=provenance(); report=protocol.empty_report(NONCE,identity)
        backend=FixtureNative(identity); backend.clean=(False,True)
        controller=stage.Controller(backend,report); backend.controller=controller
        value=controller.run()
        self.assertEqual(value['failed_stage'],'cleanup'); self.assertFalse(value['accepted'])
        self.assertEqual(value['artifacts'],[])
        protocol.validate_report(protocol.encode(value),nonce=NONCE,provenance=identity)

    def test_unexpected_exception_never_exports_exception_text(self):
        identity=provenance(); report=protocol.empty_report(NONCE,identity)
        backend=FixtureNative(identity); controller=stage.Controller(backend,report); backend.controller=controller
        backend.seed=lambda: (_ for _ in ()).throw(RuntimeError('SECRET native path /tmp/private'))
        raw=protocol.encode(controller.run())
        self.assertNotIn(b'SECRET',raw); self.assertNotIn(b'/tmp/private',raw)


@unittest.skipUnless(os.name=='posix' and hasattr(os,'O_NOFOLLOW'), 'native file safety requires POSIX')
class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.native=stage.Native(NONCE,provenance())
        self.native.root=self.root; self.native.budget_base=self.root; self.native.artifacts=self.root/'artifacts'; self.native.artifacts.mkdir()
        self.native.evidence=self.root/'evidence'; self.native.evidence.mkdir()
        self.db=self.native.artifacts/'db'; self.db.mkdir()

    def test_commands_are_named_and_load_apply_restore_separate(self):
        calls=[]
        def batch(database,operation,label,user=stage.SETUP_USER): calls.append((database,operation,label,user))
        self.native.batch=batch
        self.native.load_cf(self.db,2); self.native.apply(self.db)
        self.assertEqual(calls[0][1][0],'/LoadCfg'); self.assertNotIn('/UpdateDBCfg',calls[0][1])
        self.assertEqual(calls[1][1],['/UpdateDBCfg'])
        with mock.patch.object(self.native,'create_db',return_value=self.db): self.native.restore()
        self.assertEqual(calls[-1][1][0],'/RestoreIB'); self.assertNotIn('/UpdateDBCfg',calls[-1][1])
        self.assertIsNone(calls[-1][3])
        args=self.native.command('ENTERPRISE',self.db,stage.CRUD_USER)
        self.assertEqual(args[args.index('/N')+1],stage.CRUD_USER)

    def test_rejects_paths_outside_disposable_root_and_arbitrary_user(self):
        for path,user in ((self.root/'external',stage.CRUD_USER),(self.db,'Administrator')):
            with self.assertRaises(OracleError): self.native.command('ENTERPRISE',path,user)

    def test_dump_result_rejects_missing_bad_duplicate_oversize_and_nonzero(self):
        for value in (b'',b'1',b'0\n0',b'not zero',b'0'*129,b'\xffbad'):
            with self.subTest(value=value):
                path=self.root/'result'; path.write_bytes(value)
                with self.assertRaises(OracleError): stage.zero_result(path)
        for value in (b'0\n','0'.encode('utf-16'),b'\xef\xbb\xbf0'):
            path.write_bytes(value); stage.zero_result(path)

    def test_stale_marker_refused_before_native_call(self):
        (self.native.evidence/'result.json').write_text('forged marker')
        with mock.patch.object(self.native,'process') as process:
            with self.assertRaises(OracleError): self.native.enterprise(self.db,'create')
            process.assert_not_called()

    def test_no_mutation_when_live_process_exists(self):
        with mock.patch.object(self.native,'quiescent',return_value=False), \
             mock.patch.object(self.native,'budgets'),mock.patch.object(stage.subprocess,'Popen') as launch:
            with self.assertRaises(OracleError) as failure: self.native.process(['synthetic'],'test')
            self.assertEqual(failure.exception.kind,'snapshot_not_quiescent'); launch.assert_not_called()

    def test_exit_failure_and_surviving_descendant_rejected(self):
        for code,quiet,kind in ((1,[True],'process_failed'),(0,[True,False],'snapshot_not_quiescent')):
            with self.subTest(kind=kind):
                child=mock.Mock(); child.poll.return_value=code; child.wait.return_value=code
                with mock.patch.object(self.native,'quiescent',side_effect=quiet), \
                    mock.patch.object(self.native,'budgets'),mock.patch.object(stage.subprocess,'Popen',return_value=child), \
                    mock.patch.object(stage.time,'monotonic',side_effect=[0,0,0,6]):
                    with self.assertRaises(OracleError) as failure: self.native.process(['synthetic'],'test')
                    self.assertEqual(failure.exception.kind,kind)

    def test_exhausted_overall_deadline_never_launches(self):
        child=mock.Mock(); child.pid=999; child.poll.return_value=None
        self.native.deadline=0
        with mock.patch.object(stage.subprocess,'Popen',return_value=child) as launch:
            with self.assertRaises(OracleError) as failure: self.native.process(['synthetic'],'test')
            self.assertEqual(failure.exception.kind,'timeout'); launch.assert_not_called()


    def test_launched_timeout_kills_and_reaps_despite_potential_marker(self):
        child=mock.Mock(); child.pid=999; child.poll.return_value=None
        (self.native.evidence/'fake-success.json').write_text('{"status":"ok"}')
        with mock.patch.object(self.native,'quiescent',return_value=True), \
            mock.patch.object(self.native,'budgets'),mock.patch.object(stage.subprocess,'Popen',return_value=child), \
            mock.patch.object(stage.time,'monotonic',side_effect=[0,0,121]), \
            mock.patch.object(stage.os,'killpg',create=True) as kill:
            with self.assertRaises(OracleError) as failure: self.native.process(['synthetic'],'test')
            self.assertEqual(failure.exception.kind,'timeout')
            kill.assert_called_once_with(999,stage.signal.SIGKILL)
            child.wait.assert_called_once_with(timeout=5)

    def test_tmpfs_budget_includes_home_and_default_temp_outside_experiment(self):
        home=self.root/'outside-home'; home.mkdir(); (home/'cache').write_bytes(b'x'*40)
        (self.root/'temp-file').write_bytes(b'x'*40)
        self.assertEqual(stage.sandbox_bytes(self.root),80)
        with mock.patch.object(stage,'MAX_LIVE_BYTES',100):
            with self.assertRaises(OracleError): stage.sandbox_bytes(self.root,21)

    def test_tmpfs_budget_rejects_unknown_special_and_link_entries(self):
        target=self.root/'ordinary'; target.write_text('x')
        link=self.root/'link'; link.symlink_to(target)
        with self.assertRaises(OracleError): stage.sandbox_bytes(self.root)


    def test_empty_native_exports_fail_at_boundary_before_later_commands(self):
        for identifier,switch,suffix in (('cf_v1','/DumpCfg','.cf'),('dt_updated','/DumpIB','.dt')):
            target=self.native.artifacts/(identifier+suffix)
            with self.subTest(identifier=identifier),mock.patch.object(self.native,'budgets'), \
                mock.patch.object(self.native,'batch',side_effect=lambda *args: target.write_bytes(b'')):
                with self.assertRaises(OracleError) as failure: self.native.export(self.db,identifier,switch)
                self.assertEqual(failure.exception.kind,'artifact_missing')
                with self.assertRaises(OracleError): self.native.artifact(identifier)

    def test_empty_native_database_cannot_be_frozen(self):
        (self.db/'1Cv8.1CD').write_bytes(b'')
        with mock.patch.object(stage,'freeze_database') as freeze:
            with self.assertRaises(OracleError) as failure: self.native.freeze(self.db,'baseline')
            self.assertEqual(failure.exception.kind,'artifact_missing'); freeze.assert_not_called()


    def test_clone_reserves_entire_tmpfs_budget_before_allocation(self):
        self.native.root=self.root/'experiment'; self.native.root.mkdir()
        self.native.artifacts=self.native.root/'artifacts'; self.native.artifacts.mkdir()
        frozen=self.native.artifacts/'baseline'; frozen.mkdir()
        source=frozen/'1Cv8.1CD'; source.write_bytes(b'data'); source.chmod(0o400); frozen.chmod(0o500)
        self.addCleanup(lambda: frozen.chmod(0o700))
        runtime=self.root/'runtime'; runtime.mkdir(); (runtime/'xauth').write_bytes(b'12345')
        with mock.patch.object(stage,'MAX_LIVE_BYTES',12),mock.patch.object(stage,'clone_database') as clone:
            with self.assertRaises(OracleError) as failure: self.native.clone('baseline','observer')
            self.assertEqual(failure.exception.kind,'artifact_limit'); clone.assert_not_called()
            self.assertFalse((self.native.artifacts/'observer').exists())


if __name__=='__main__': unittest.main()

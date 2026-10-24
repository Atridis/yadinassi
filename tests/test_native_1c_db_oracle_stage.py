"""Synthetic controller fixtures, not evidence from a native 1C installation."""
from __future__ import annotations

import contextlib
import copy
import errno
import hashlib
import importlib.util
import json
import os
import socket
import stat
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
    def begin_stage(self,stage): pass
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


class SeedDiagnosticTests(unittest.TestCase):
    """Synthetic launch-boundary injection; no native command is executed."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.identity=provenance(); self.native=stage.Native(NONCE,self.identity)
        self.native.root=self.root; self.native.artifacts=self.root/'artifacts'; self.native.artifacts.mkdir()
        self.native.evidence=self.root/'evidence'; self.native.evidence.mkdir()
        self.native.v1=self.root/'v1'; self.native.v2=self.root/'v2'
        self.native.begin_stage('seed_v1')
        self.launches=[]

    def platform(self, failed=None, exception=None):
        stack=contextlib.ExitStack()
        self.addCleanup(stack.close)
        for name in ('budgets','preflight'):
            stack.enter_context(mock.patch.object(self.native,name))
        stack.enter_context(mock.patch.object(self.native,'quiescent',return_value=True))
        stack.enter_context(mock.patch.object(self.native,'cleanup',return_value=(True,True)))
        for name in ('zero_result','inject','promote_v2','verify_redump'):
            stack.enter_context(mock.patch.object(stage,name))
        stack.enter_context(mock.patch.object(stage,'native_file_summary',return_value=physical()))
        stack.enter_context(mock.patch.object(stage,'regular_bytes',return_value=b'{}'))
        stack.enter_context(mock.patch.object(stage,'marker',return_value={'actual_version':protocol.VERSION}))
        def launch(*args,**kwargs):
            operation=self.native.seed_pending
            self.assertEqual(self.native.seed_launched,operation)
            self.launches.append(operation)
            if operation==failed and exception is not None: raise exception
            child=mock.Mock(); code=53 if operation==failed else 0
            child.poll.return_value=code; child.wait.return_value=code
            return child
        return stack.enter_context(mock.patch.object(stage.subprocess,'Popen',side_effect=launch))

    def test_each_seed_command_nonzero_is_identified_and_dependencies_stop(self):
        for operation in protocol.SEED_OPERATIONS:
            with self.subTest(operation=operation):
                # Use a fresh native instance/evidence directory for every run.
                self.native.counter+=10; self.launches.clear()
                with self.platform(failed=operation):
                    report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
                self.assertEqual(report['failed_stage'],'seed_v1')
                self.assertEqual(report['failure_kind'],'seed_'+operation+'_process_failed')
                self.assertEqual(self.launches,list(protocol.SEED_OPERATIONS[:protocol.SEED_OPERATIONS.index(operation)+1]))
                self.assertEqual(report['snapshots'],[]); self.assertEqual(report['artifacts'],[])
                self.assertEqual(self.native.stage,'cleanup')
                self.assertIsNone(self.native.seed_pending); self.assertIsNone(self.native.seed_launched)
                protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=self.identity)

    def test_prelaunch_failure_is_not_labeled_as_a_launched_operation(self):
        launch=self.platform()
        with mock.patch.object(self.native,'budgets',side_effect=OracleError('artifact_limit')):
            report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
        self.assertEqual(report['failure_kind'],'artifact_limit'); launch.assert_not_called()
        self.assertIsNone(self.native.seed_pending); self.assertIsNone(self.native.seed_launched)

    def test_metadata_preparation_does_not_inherit_dump_launch(self):
        self.platform()
        with mock.patch.object(stage,'inject',side_effect=ValueError('SECRET /private/config.xml')):
            report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
        self.assertEqual(self.launches,['create','dump_empty'])
        self.assertEqual(report['failure_kind'],'metadata_rejected')
        raw=protocol.encode(report)
        self.assertNotIn(b'SECRET',raw); self.assertNotIn(b'/private',raw)

    def test_postlaunch_result_validation_retains_operation(self):
        self.platform()
        with mock.patch.object(stage,'zero_result',side_effect=OracleError('invalid_dump_result')):
            report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
        self.assertEqual(report['failure_kind'],'seed_create_invalid_dump_result')

    def test_launch_exception_is_finite_and_never_exports_text(self):
        self.platform(failed='apply',exception=OSError('SECRET /private/native.log'))
        report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
        self.assertEqual(report['failure_kind'],'seed_apply_unexpected_failure')
        raw=protocol.encode(report)
        self.assertNotIn(b'SECRET',raw); self.assertNotIn(b'/private',raw)
        protocol.validate_report(raw,nonce=NONCE,provenance=self.identity)

    def test_success_clears_context_before_next_stage(self):
        self.platform(); self.native.seed()
        self.assertEqual(self.launches,list(protocol.SEED_OPERATIONS))
        self.assertIsNone(self.native.seed_pending); self.assertIsNone(self.native.seed_launched)
        self.native.seed_pending='apply'; self.native.seed_launched='apply'
        self.native.begin_stage('baseline')
        self.assertIsNone(self.native.seed_pending); self.assertIsNone(self.native.seed_launched)
        child=mock.Mock(); child.poll.return_value=1; child.wait.return_value=1
        with mock.patch.object(stage.subprocess,'Popen',return_value=child),self.assertRaises(OracleError) as error:
            self.native.process(['synthetic'],'later-command')
        self.assertEqual(error.exception.kind,'process_failed')

    def test_operation_context_rejects_unknown_boolean_and_wrong_stage(self):
        for operation in ('unknown',False,True,None,1):
            with self.subTest(operation=operation),self.assertRaises(OracleError):
                with self.native.seed_command(operation): self.fail('entered invalid context')
        for name in protocol.STAGES:
            if name=='seed_v1': continue
            self.native.begin_stage(name)
            with self.subTest(stage=name),self.assertRaises(OracleError):
                with self.native.seed_command('create'): self.fail('entered non-seed context')

    def test_controller_rejects_stale_seed_failure_in_later_stage(self):
        identity=provenance(); backend=FixtureNative(identity)
        controller=stage.Controller(backend,protocol.empty_report(NONCE,identity)); backend.controller=controller
        backend.freeze=lambda *args: (_ for _ in ()).throw(stage.SeedCommandError('process_failed','apply'))
        report=controller.run()
        self.assertEqual(report['failed_stage'],'baseline')
        self.assertEqual(report['failure_kind'],'unexpected_failure')
        protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity)

    def test_primary_seed_failure_survives_native_cleanup_failure(self):
        self.platform(failed='import')
        with mock.patch.object(self.native,'cleanup',return_value=(False,False)):
            report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
        self.assertEqual(report['failure_kind'],'seed_import_process_failed')
        self.assertEqual(report['failed_stage'],'seed_v1')
        self.assertEqual(report['stages'][-1]['status'],'failed')
        self.assertFalse(report['cleanup']['native_processes_stopped'])
        self.assertFalse(report['cleanup']['raw_files_removed']); self.assertFalse(report['accepted'])
        protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=self.identity)


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


@unittest.skipUnless(os.name=='posix' and hasattr(os,'O_NOFOLLOW'), 'native inventory requires POSIX')
class InventoryScannerTests(unittest.TestCase):
    """Real filesystem predicates and synthetic OS failures; no native 1C run."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()

    def assert_inventory(self,region,reason):
        with self.assertRaises(stage.SandboxInventoryError) as failure:
            stage.sandbox_bytes(self.root)
        error=failure.exception
        self.assertEqual((error.kind,error.region,error.reason),('invalid_input',region,reason))
        self.assertEqual(str(error),'invalid_input')
        self.assertNotIn(str(self.root),repr(error))
        return error

    def test_real_symlinks_map_only_to_fixed_regions(self):
        cases=(('onec-db-oracle/home/private','home'),('onec-db-oracle/temp/private','tmp'),
            ('onec-db-oracle/artifacts/private','experiment'),('runtime/private','runtime'),
            ('.X11-unix/private','runtime'),('other/private','tmp'),
            ('onec-db-oracle/home-other/private','experiment'),('runtime-other/private','tmp'))
        for relative,region in cases:
            with self.subTest(relative=relative):
                target=self.root/relative; target.parent.mkdir(parents=True,exist_ok=True)
                target.symlink_to('/SECRET/private-do-not-follow')
                self.assert_inventory(region,'symlink'); target.unlink()

    def test_real_hardlink_and_fifo_are_distinct(self):
        target=self.root/'regular'; target.write_bytes(b'x')
        linked=self.root/'hardlink'; os.link(target,linked)
        self.assert_inventory('tmp','hardlink'); linked.unlink()
        fifo=self.root/'fifo'; os.mkfifo(fifo)
        self.assert_inventory('tmp','special')

    @unittest.skipUnless(hasattr(socket,'AF_UNIX'),'requires UNIX sockets')
    def test_real_unexpected_socket_rejected_and_only_existing_service_paths_allowed(self):
        try:
            probe=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); probe.close()
        except OSError as error:
            if error.errno in (errno.EPERM,errno.EACCES,errno.EAFNOSUPPORT,errno.ENOSYS):
                self.skipTest('UNIX sockets unavailable in this execution environment')
            raise
        for relative,allowed,region in (('.X11-unix/X99',True,'runtime'),
                ('runtime/session-bus/bus',True,'runtime'),('.X11-unix/X98',False,'runtime'),
                ('onec-db-oracle/home/socket',False,'home'),('socket',False,'tmp')):
            with self.subTest(relative=relative):
                path=self.root/relative; path.parent.mkdir(parents=True,exist_ok=True)
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                    server.bind(str(path))
                    if allowed: self.assertEqual(stage.sandbox_bytes(self.root),0)
                    else: self.assert_inventory(region,'unexpected_socket')
                path.unlink()

    def scan_entries(self,*entries):
        return mock.patch.object(stage.os,'scandir',return_value=contextlib.nullcontext(entries))

    def entry(self,mode,links=1):
        entry=mock.Mock(); entry.name='SECRET-private'
        entry.stat.return_value=mock.Mock(st_mode=mode,st_nlink=links,st_size=1,st_dev=1,st_ino=2)
        return entry

    def test_zero_link_count_is_not_a_hardlink(self):
        for links,reason in ((0,'link_count'),(-1,'link_count'),(2,'hardlink')):
            with self.subTest(links=links),self.scan_entries(self.entry(stat.S_IFREG,links)):
                self.assert_inventory('tmp',reason)

    def test_socket_paths_and_link_counts_are_exact_even_without_real_sockets(self):
        real_scandir=stage.os.scandir
        cases=(('.X11-unix/X99',1,None),('runtime/session-bus/bus',1,None),
            ('.X11-unix/X99',0,'link_count'),('runtime/session-bus/bus',2,'hardlink'),
            ('.X11-unix/X98',1,'unexpected_socket'),('runtime/session-bus/other',1,'unexpected_socket'))
        for relative,links,reason in cases:
            path=self.root/relative; path.parent.mkdir(parents=True,exist_ok=True)
            socket_entry=self.entry(stat.S_IFSOCK,links); socket_entry.name=path.name
            def scan(descriptor):
                if os.fstat(descriptor).st_ino==path.parent.stat().st_ino:
                    return contextlib.nullcontext([socket_entry])
                return real_scandir(descriptor)
            with self.subTest(relative=relative,links=links),mock.patch.object(stage.os,'scandir',side_effect=scan):
                if reason is None: self.assertEqual(stage.sandbox_bytes(self.root),0)
                else: self.assert_inventory('runtime',reason)

    def test_root_open_os_errors_are_bounded(self):
        for number,reason in ((errno.ENOENT,'race'),(errno.ESTALE,'race'),
                (errno.EACCES,'access'),(errno.EPERM,'access'),(errno.EIO,'otherio')):
            with self.subTest(errno=number),mock.patch.object(stage.os,'open',
                    side_effect=OSError(number,'SECRET exception text','/private/secret')):
                self.assert_inventory('tmp',reason)

    def test_nested_stat_os_error_retains_only_fixed_region(self):
        home=self.root/'onec-db-oracle'/'home'; home.mkdir(parents=True)
        real_scandir=stage.os.scandir
        broken=self.entry(stat.S_IFREG)
        broken.stat.side_effect=PermissionError(errno.EACCES,'SECRET raw error','/private')
        def scan(descriptor):
            if os.fstat(descriptor).st_ino==home.stat().st_ino:
                return contextlib.nullcontext([broken])
            return real_scandir(descriptor)
        with mock.patch.object(stage.os,'scandir',side_effect=scan):
            self.assert_inventory('home','access')

    def test_scandir_failure_is_classified_without_raw_exception(self):
        with mock.patch.object(stage.os,'scandir',side_effect=OSError(errno.EIO,'SECRET scandir')):
            self.assert_inventory('tmp','otherio')

    def test_disappearing_stat_and_child_open_remain_tolerated(self):
        missing=self.entry(stat.S_IFREG); missing.stat.side_effect=FileNotFoundError('SECRET vanished')
        with self.scan_entries(missing): self.assertEqual(stage.sandbox_bytes(self.root),0)
        gone=self.entry(stat.S_IFDIR)
        real_open=stage.os.open
        def open_child(path,*args,**kwargs):
            if 'dir_fd' in kwargs: raise FileNotFoundError(errno.ENOENT,'SECRET vanished')
            return real_open(path,*args,**kwargs)
        with self.scan_entries(gone),mock.patch.object(stage.os,'open',side_effect=open_child):
            self.assertEqual(stage.sandbox_bytes(self.root),0)

    def test_stale_entry_stat_and_child_open_are_not_tolerated(self):
        stale=self.entry(stat.S_IFREG)
        stale.stat.side_effect=OSError(errno.ESTALE,'SECRET stale entry')
        with self.scan_entries(stale): self.assert_inventory('tmp','race')
        stale=self.entry(stat.S_IFDIR)
        real_open=stage.os.open
        def open_child(path,*args,**kwargs):
            if 'dir_fd' in kwargs: raise OSError(errno.ESTALE,'SECRET stale child')
            return real_open(path,*args,**kwargs)
        with self.scan_entries(stale),mock.patch.object(stage.os,'open',side_effect=open_child):
            self.assert_inventory('tmp','race')

    def test_directory_identity_change_remains_generic_snapshot_changed(self):
        directory=self.root/'directory'; directory.mkdir()
        entry=self.entry(stat.S_IFDIR)
        entry.name='directory'; entry.stat.return_value.st_ino=directory.stat().st_ino+1
        entry.stat.return_value.st_dev=directory.stat().st_dev
        with self.scan_entries(entry),self.assertRaises(OracleError) as failure:
            stage.sandbox_bytes(self.root)
        self.assertEqual(failure.exception.kind,'snapshot_changed')
        self.assertNotIsInstance(failure.exception,stage.SandboxInventoryError)

    def test_existing_byte_reserve_and_size_caps_remain_generic(self):
        (self.root/'regular').write_bytes(b'1234')
        with mock.patch.object(stage,'MAX_LIVE_BYTES',5):
            self.assertEqual(stage.sandbox_bytes(self.root,1),4)
            with self.assertRaises(OracleError) as failure: stage.sandbox_bytes(self.root,2)
            self.assertEqual(failure.exception.kind,'artifact_limit')
            self.assertNotIsInstance(failure.exception,stage.SandboxInventoryError)
        with self.scan_entries(self.entry(stat.S_IFREG)),mock.patch.object(stage,'MAX_FILE_BYTES',0):
            with self.assertRaises(OracleError) as failure: stage.sandbox_bytes(self.root)
            self.assertEqual(failure.exception.kind,'artifact_limit')


class InventoryMonitorTests(unittest.TestCase):
    """Exercise the real process loop with a synthetic child, never native 1C."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.identity=provenance()
        self.native=stage.Native(NONCE,self.identity)
        self.native.root=self.root; self.native.evidence=self.root/'evidence'; self.native.evidence.mkdir()
        self.native.begin_stage('seed_v1')

    @contextlib.contextmanager
    def process_fixture(self,phase,exception=None,quiet=True,code=0):
        child=mock.Mock(); child.pid=999
        child.poll.return_value=None if phase=='poll' else code
        child.wait.return_value=code
        error=exception or stage.SandboxInventoryError('home','unexpected_socket')
        with mock.patch.object(self.native,'budgets',side_effect=[None,error]) as budgets, \
                mock.patch.object(self.native,'quiescent',side_effect=[True,quiet]) as quiescent, \
                mock.patch.object(stage.subprocess,'Popen',return_value=child) as launch, \
                mock.patch.object(stage.os,'killpg',create=True) as kill, \
                mock.patch.object(stage.signal,'SIGKILL',9,create=True), \
                mock.patch.object(stage.time,'sleep') as sleep:
            yield child,budgets,quiescent,launch,kill,sleep

    def command(self,operation='bootstrap'):
        with self.native.seed_command(operation):
            self.native.process(['synthetic'],'inventory-boundary')

    def test_bootstrap_poll_rejection_aborts_then_kills_and_reaps_child(self):
        with self.process_fixture('poll') as (child,budgets,quiet,launch,kill,sleep):
            with self.assertRaises(stage.BootstrapInventoryError) as failure: self.command()
            self.assertEqual((failure.exception.phase,failure.exception.region,failure.exception.reason),
                ('poll','home','unexpected_socket'))
            kill.assert_called_once_with(999,stage.signal.SIGKILL)
            child.wait.assert_called_once_with(timeout=5)
            self.assertEqual(budgets.call_count,2); self.assertEqual(quiet.call_count,1)
            launch.assert_called_once(); sleep.assert_not_called()
        self.assertIsNone(self.native.seed_pending); self.assertIsNone(self.native.seed_launched)

    def test_bootstrap_post_exit_rejection_waits_for_zero_exit_and_quiescence(self):
        with self.process_fixture('post_exit') as (child,budgets,quiet,launch,kill,sleep):
            with self.assertRaises(stage.BootstrapInventoryError) as failure: self.command()
            self.assertEqual((failure.exception.phase,failure.exception.region,failure.exception.reason),
                ('post_exit','home','unexpected_socket'))
            child.wait.assert_called_once_with(); kill.assert_not_called()
            self.assertEqual(budgets.call_count,2); self.assertEqual(quiet.call_count,2)
            sleep.assert_not_called()

    def test_nonzero_exit_does_not_run_post_exit_monitor(self):
        with self.process_fixture('post_exit',code=7) as (child,budgets,quiet,launch,kill,sleep):
            with self.assertRaises(stage.SeedCommandError) as failure: self.command()
            self.assertEqual((failure.exception.kind,failure.exception.operation),('process_failed','bootstrap'))
            self.assertEqual(budgets.call_count,1); self.assertEqual(quiet.call_count,1)
            kill.assert_not_called()

    def test_failed_quiescence_does_not_run_post_exit_monitor(self):
        with self.process_fixture('post_exit',quiet=False) as (child,budgets,quiet,launch,kill,sleep), \
                mock.patch.object(stage.time,'monotonic',side_effect=[0,0,0,6]):
            with self.assertRaises(stage.SeedCommandError) as failure: self.command()
            self.assertEqual(failure.exception.kind,'snapshot_not_quiescent')
            self.assertEqual(budgets.call_count,1); kill.assert_not_called()

    def test_prelaunch_inventory_error_is_never_bootstrap_labeled(self):
        error=stage.SandboxInventoryError('tmp','access')
        with mock.patch.object(self.native,'budgets',side_effect=error), \
                mock.patch.object(stage.subprocess,'Popen') as launch:
            with self.assertRaises(stage.SandboxInventoryError) as failure: self.command()
            self.assertIs(failure.exception,error); launch.assert_not_called()
        self.assertIsNone(self.native.seed_pending); self.assertIsNone(self.native.seed_launched)

    def test_other_seed_operations_keep_existing_command_diagnostic(self):
        for operation in protocol.SEED_OPERATIONS:
            if operation=='bootstrap': continue
            for phase in protocol.INVENTORY_PHASES:
                with self.subTest(operation=operation,phase=phase),self.process_fixture(phase):
                    with self.assertRaises(stage.SeedCommandError) as failure: self.command(operation)
                    self.assertEqual((failure.exception.kind,failure.exception.operation),('invalid_input',operation))
                    self.assertNotIsInstance(failure.exception,stage.BootstrapInventoryError)

    def test_only_exact_launched_bootstrap_context_is_wrapped(self):
        cases=(('seed_v1','bootstrap',None),('seed_v1',None,'bootstrap'),
            ('seed_v1','create','bootstrap'),('seed_v1','bootstrap','create'),
            ('baseline','bootstrap','bootstrap'))
        for stage_name,pending,launched in cases:
            self.native.stage=stage_name; self.native.seed_pending=pending; self.native.seed_launched=launched
            error=stage.SandboxInventoryError('experiment','race')
            with self.subTest(context=(stage_name,pending,launched)), \
                    mock.patch.object(self.native,'budgets',side_effect=error):
                with self.assertRaises(stage.SandboxInventoryError) as failure:
                    self.native.monitor_budget('poll')
                self.assertIs(failure.exception,error)

    def test_generic_failures_and_raw_os_errors_are_not_inventory_reclassified(self):
        for error,kind in ((OracleError('artifact_limit'),'artifact_limit'),
                (OSError(errno.EIO,'SECRET /private/path'),'unexpected_failure')):
            for phase in protocol.INVENTORY_PHASES:
                with self.subTest(kind=kind,phase=phase),self.process_fixture(phase,exception=error):
                    with self.assertRaises(stage.SeedCommandError) as failure: self.command()
                    self.assertEqual((failure.exception.kind,failure.exception.operation),(kind,'bootstrap'))

    def test_controller_encodes_both_process_boundaries_without_raw_details(self):
        for phase in protocol.INVENTORY_PHASES:
            with self.subTest(phase=phase),self.process_fixture(phase), \
                    mock.patch.object(self.native,'preflight'), \
                    mock.patch.object(self.native,'seed',side_effect=self.command), \
                    mock.patch.object(self.native,'cleanup',return_value=(True,True)):
                report=stage.Controller(self.native,protocol.empty_report(NONCE,self.identity)).run()
            self.assertEqual(report['failed_stage'],'seed_v1')
            self.assertEqual(report['failure_kind'],'seed_bootstrap_inventory_'+phase+'_home_unexpected_socket')
            self.assertEqual(report['snapshots'],[]); self.assertEqual(report['artifacts'],[])
            raw=protocol.encode(report)
            self.assertNotIn(str(self.root).encode(),raw); self.assertNotIn(b'SECRET',raw)
            protocol.validate_report(raw,nonce=NONCE,provenance=self.identity)

    def test_controller_rejects_stale_inventory_failure_outside_seed(self):
        for failure_stage in ('preflight','baseline'):
            identity=provenance(); backend=FixtureNative(identity)
            controller=stage.Controller(backend,protocol.empty_report(NONCE,identity)); backend.controller=controller
            error=stage.BootstrapInventoryError('post_exit','runtime','otherio')
            method='preflight' if failure_stage=='preflight' else 'freeze'
            with self.subTest(stage=failure_stage),mock.patch.object(backend,method,side_effect=error):
                report=controller.run()
            self.assertEqual(report['failed_stage'],failure_stage)
            self.assertEqual(report['failure_kind'],'unexpected_failure')
            protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity)

    def test_bounded_error_constructors_reject_unknown_values(self):
        for region,reason in (('/private/path','race'),('home','SECRET'),(False,'race'),('tmp',None)):
            with self.subTest(region=region,reason=reason),self.assertRaises(OracleError):
                stage.SandboxInventoryError(region,reason)
        for phase in ('prelaunch','SECRET',False,None):
            with self.subTest(phase=phase),self.assertRaises(OracleError):
                stage.BootstrapInventoryError(phase,'home','race')


if __name__=='__main__': unittest.main()

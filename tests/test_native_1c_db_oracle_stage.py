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
from snapshots import DatabaseEntryError, ENTRY_CLASSES, ENTRY_SHAPES, OracleError
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
        stack.enter_context(mock.patch.object(stage,'completion_marker',return_value={'status':'ok','phase':'complete'}))
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
            with self.subTest(identifier=identifier),mock.patch.object(self.native,'quiescent',return_value=True),mock.patch.object(self.native,'budgets'), \
                mock.patch.object(self.native,'batch',side_effect=lambda *args: target.write_bytes(b'')):
                with self.assertRaises(OracleError) as failure: self.native.export(self.db,identifier,switch)
                self.assertEqual(failure.exception.kind,'artifact_missing')
                with self.assertRaises(OracleError): self.native.artifact(identifier)

    def test_empty_native_database_cannot_be_frozen(self):
        (self.db/'1Cv8.1CD').write_bytes(b'')
        with mock.patch.object(self.native,'quiescent',return_value=True),mock.patch.object(stage,'freeze_database') as freeze:
            with self.assertRaises(OracleError) as failure: self.native.freeze(self.db,'baseline')
            self.assertEqual(failure.exception.kind,'artifact_missing'); freeze.assert_not_called()


    def test_clone_reserves_entire_tmpfs_budget_before_allocation(self):
        self.native.root=self.root/'experiment'; self.native.root.mkdir()
        self.native.artifacts=self.native.root/'artifacts'; self.native.artifacts.mkdir()
        frozen=self.native.artifacts/'baseline'; frozen.mkdir()
        source=frozen/'1Cv8.1CD'; source.write_bytes(b'data'); source.chmod(0o400); frozen.chmod(0o500)
        self.addCleanup(lambda: frozen.chmod(0o700))
        runtime=self.root/'runtime'; runtime.mkdir(); (runtime/'xauth').write_bytes(b'12345')
        with mock.patch.object(self.native,'quiescent',return_value=True),mock.patch.object(stage,'MAX_LIVE_BYTES',12),mock.patch.object(stage,'clone_database') as clone:
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


@unittest.skipUnless(os.name=='posix' and hasattr(os,'O_NOFOLLOW'), 'native inventory requires POSIX')
class HomeSocketInventoryTests(unittest.TestCase):
    """Real directory anchors with controlled socket metadata, never native IPC."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve(); self.root=self.base/'sandbox'; self.root.mkdir()
        self.parent=self.root/'onec-db-oracle'; self.home=self.parent/'home'; self.home.mkdir(parents=True)
        self.park=self.base/'park'; self.park.mkdir()

    @staticmethod
    def identity(info): return info.st_dev,info.st_ino

    def leaf(self,relative,*,uid=1000,gid=1000,links=1,mode=stat.S_IFSOCK,size=0):
        path=self.root/relative; path.parent.mkdir(parents=True,exist_ok=True)
        entry=mock.Mock(); entry.name=path.name
        entry.stat.return_value=mock.Mock(st_mode=mode,st_nlink=links,st_size=size,
            st_dev=1,st_ino=2,st_uid=uid,st_gid=gid)
        return path,entry

    @contextlib.contextmanager
    def inventory(self,*leaves,owners=None,after_scan=None):
        # Normalize directory ownership only in metadata. Never chown/chmod and
        # never need the test runner itself to have the native UID/GID.
        owners={} if owners is None else owners
        real_fstat,real_stat,real_scandir=stage.os.fstat,stage.os.stat,stage.os.scandir
        grouped={}
        for path,entry in leaves:
            grouped.setdefault(self.identity(real_stat(path.parent)),[]).append(entry)
        def normalize(info):
            if not stat.S_ISDIR(info.st_mode): return info
            values=list(info); values[4:6]=owners.get(self.identity(info),(1000,1000))
            return os.stat_result(values)
        def fstat(descriptor): return normalize(real_fstat(descriptor))
        def lstat(*args,**kwargs): return normalize(real_stat(*args,**kwargs))
        @contextlib.contextmanager
        def scan_fd(descriptor):
            identity=self.identity(real_fstat(descriptor)); extra=grouped.get(identity,[])
            names={entry.name for entry in extra}; entries=[]
            with real_scandir(descriptor) as children:
                for child in children:
                    if child.name in names: continue
                    entry=mock.Mock(); entry.name=child.name
                    entry.stat.side_effect=lambda *,follow_symlinks,child=child: normalize(
                        child.stat(follow_symlinks=follow_symlinks))
                    entries.append(entry)
            yield entries+extra
            if after_scan is not None: after_scan(identity)
        def scan(descriptor):
            return scan_fd(descriptor) if isinstance(descriptor,int) else real_scandir(descriptor)
        with mock.patch.object(stage.os,'fstat',side_effect=fstat), \
                mock.patch.object(stage.os,'stat',side_effect=lstat), \
                mock.patch.object(stage.os,'scandir',side_effect=scan):
            yield

    def assert_kind(self,kind,action):
        with self.assertRaises(OracleError) as failure: action()
        self.assertEqual(failure.exception.kind,kind)
        self.assertNotIsInstance(failure.exception,stage.SandboxInventoryError)
        return failure.exception

    def assert_socket_rejection(self,anchor,region,reason):
        with self.assertRaises(stage.SandboxInventoryError) as failure:
            stage.sandbox_bytes(self.root,home_anchor=anchor)
        self.assertEqual((failure.exception.region,failure.exception.reason),(region,reason))
        self.assertNotIn(str(self.root),repr(failure.exception))

    def test_capture_pins_both_directory_identities_and_owners_using_directory_only_opens(self):
        real_open=stage.os.open
        with self.inventory(),mock.patch.object(stage.os,'open',wraps=real_open) as opened:
            anchor=stage.capture_home_anchor(self.root)
            expected=tuple(value for path in (self.parent,self.home) for value in
                (path.stat().st_dev,path.stat().st_ino,1000,1000))
            self.assertEqual(anchor,expected); self.assertTrue(all(type(value) is int for value in anchor))
            self.assertEqual(len(opened.call_args_list),3)
            for call in opened.call_args_list:
                self.assertTrue(call.args[1]&os.O_DIRECTORY)
                self.assertTrue(call.args[1]&os.O_NOFOLLOW)

    def test_capture_and_each_scan_reject_wrong_anchor_uid_or_gid(self):
        owners={}
        with self.inventory(owners=owners):
            anchor=stage.capture_home_anchor(self.root)
            for directory in (self.parent,self.home):
                for owner in ((0,1000),(1000,0),(1001,1000),(1000,1001)):
                    with self.subTest(directory=directory.name,owner=owner):
                        owners[self.identity(directory.stat())]=owner
                        self.assert_kind('snapshot_changed',lambda: stage.capture_home_anchor(self.root))
                        self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
                        owners.clear()

    def test_zero_one_four_nested_sockets_and_per_scan_counter_reset(self):
        self.assertEqual(stage.MAX_HOME_SOCKETS,4)
        for count in (0,1,4):
            leaves=[self.leaf(f'onec-db-oracle/home/private/level-{index}/ipc') for index in range(count)]
            with self.subTest(count=count),self.inventory(*leaves):
                anchor=stage.capture_home_anchor(self.root)
                for _ in range(3): self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=anchor),0)

    def test_fifth_owned_socket_is_generic_artifact_limit(self):
        leaves=[self.leaf(f'onec-db-oracle/home/level-{index}/ipc') for index in range(5)]
        with self.inventory(*leaves):
            anchor=stage.capture_home_anchor(self.root)
            self.assert_kind('artifact_limit',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))

    def test_socket_owner_and_link_failures_keep_existing_bounded_reasons(self):
        cases=((0,1000,1,'unexpected_socket'),(1000,0,1,'unexpected_socket'),
            (1001,1000,1,'unexpected_socket'),(1000,1001,1,'unexpected_socket'),
            (1000,1000,0,'link_count'),(1000,1000,-1,'link_count'),(1000,1000,2,'hardlink'))
        for uid,gid,links,reason in cases:
            leaf=self.leaf('onec-db-oracle/home/private/ipc',uid=uid,gid=gid,links=links)
            with self.subTest(uid=uid,gid=gid,links=links),self.inventory(leaf):
                self.assert_socket_rejection(stage.capture_home_anchor(self.root),'home',reason)

    def test_unpinned_calls_preserve_strict_home_socket_rejection(self):
        with self.inventory(self.leaf('onec-db-oracle/home/ipc')):
            self.assert_socket_rejection(None,'home','unexpected_socket')
            with self.assertRaises(stage.SandboxInventoryError) as failure: stage.sandbox_bytes(self.root)
            self.assertEqual(failure.exception.reason,'unexpected_socket')

    def test_only_strict_home_descendants_are_eligible(self):
        cases=(('onec-db-oracle/home','home'),('onec-db-oracle/home-other/ipc','experiment'),
            ('onec-db-oracle/homeish/ipc','experiment'),('onec-db-oracle/temp/ipc','tmp'),
            ('other/home/ipc','tmp'),('runtime/ipc','runtime'),('ipc','tmp'))
        for relative,region in cases:
            with self.subTest(relative=relative),self.inventory(self.leaf(relative)):
                self.assert_socket_rejection(stage.capture_home_anchor(self.root),region,'unexpected_socket')

    def test_legacy_two_service_sockets_do_not_consume_home_socket_allowance(self):
        leaves=[self.leaf('.X11-unix/X99',uid=0,gid=0),self.leaf('runtime/session-bus/bus',uid=0,gid=0)]
        leaves.extend(self.leaf(f'onec-db-oracle/home/ipc-{index}') for index in range(4))
        with self.inventory(*leaves):
            self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=stage.capture_home_anchor(self.root)),0)
        for relative in ('.X11-unix/X98','runtime/session-bus/other'):
            with self.subTest(relative=relative),self.inventory(self.leaf(relative)):
                self.assert_socket_rejection(stage.capture_home_anchor(self.root),'runtime','unexpected_socket')

    def test_pinned_scans_still_reject_other_specials_and_links(self):
        for mode,links,reason in ((stat.S_IFLNK,1,'symlink'),(stat.S_IFIFO,1,'special'),
                (stat.S_IFCHR,1,'special'),(stat.S_IFREG,2,'hardlink'),(stat.S_IFREG,0,'link_count')):
            with self.subTest(mode=mode,links=links),self.inventory(
                    self.leaf('onec-db-oracle/home/entry',mode=mode,links=links)):
                self.assert_socket_rejection(stage.capture_home_anchor(self.root),'home',reason)

    def test_regular_creation_and_same_scan_size_reserves_remain_valid(self):
        leaf=self.leaf('onec-db-oracle/home/ipc',size=stage.MAX_FILE_BYTES+1)
        with self.inventory(leaf):
            anchor=stage.capture_home_anchor(self.root)
            self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=anchor),0)
            (self.home/'new-child').mkdir(); (self.home/'new-child'/'ordinary').write_bytes(b'1234')
            (self.root/'outside-home').write_bytes(b'567')
            with mock.patch.object(stage,'MAX_LIVE_BYTES',8):
                self.assertEqual(stage.sandbox_bytes(self.root,1,home_anchor=anchor),7)
                self.assert_kind('artifact_limit',lambda: stage.sandbox_bytes(self.root,2,home_anchor=anchor))
            with mock.patch.object(stage,'MAX_FILE_BYTES',3):
                self.assert_kind('artifact_limit',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))

    def test_existing_entry_limit_counts_admitted_sockets(self):
        socket_leaf=self.leaf('onec-db-oracle/home/ipc')
        regular=[self.leaf(f'onec-db-oracle/home/regular-{index}',mode=stat.S_IFREG) for index in range(4094)]
        for count in (4093,4094):
            with self.subTest(count=count),self.inventory(socket_leaf,*regular[:count]):
                anchor=stage.capture_home_anchor(self.root)
                if count==4093: self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=anchor),0)
                else: self.assert_kind('artifact_limit',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))

    def test_existing_depth_limit_is_not_relaxed(self):
        directory=self.home
        for _ in range(14): directory=directory/'nested'; directory.mkdir()
        with self.inventory(self.leaf(str((directory/'ipc').relative_to(self.root)))):
            self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=stage.capture_home_anchor(self.root)),0)
        directory=directory/'too-deep'; directory.mkdir()
        with self.inventory():
            self.assert_kind('artifact_limit',lambda: stage.sandbox_bytes(self.root,
                home_anchor=stage.capture_home_anchor(self.root)))

    def test_replacement_between_scans_is_not_reanchored(self):
        for name in ('home','parent'):
            target=self.home if name=='home' else self.parent
            displaced=self.park/name
            with self.subTest(target=name),self.inventory():
                anchor=stage.capture_home_anchor(self.root)
                self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=anchor),0)
                target.rename(displaced); target.mkdir()
                if name=='parent': (target/'home').mkdir()
                self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
                if name=='parent': (target/'home').rmdir()
                target.rmdir(); displaced.rename(target)

    def test_opened_anchor_must_still_match_its_parent_entry(self):
        real_open=stage.os.open
        for name in ('home','parent'):
            target=self.home if name=='home' else self.parent
            original=self.identity(target.stat()); displaced=self.park/name; changed=False
            def opened(path,*args,**kwargs):
                nonlocal changed
                descriptor=real_open(path,*args,**kwargs)
                if not changed and self.identity(os.fstat(descriptor))==original:
                    changed=True; target.rename(displaced); target.mkdir()
                    if name=='parent': (target/'home').mkdir()
                return descriptor
            with self.subTest(target=name),self.inventory(),mock.patch.object(stage.os,'open',side_effect=opened):
                self.assert_kind('snapshot_changed',lambda: stage.capture_home_anchor(self.root))
                self.assertTrue(changed)
            if name=='parent': (target/'home').rmdir()
            target.rmdir(); displaced.rename(target)

    def test_walker_checks_anchor_identity_after_pre_scan_validation(self):
        # Swap just before the walk opens each fixed directory. Its entry stat
        # agrees with its newly opened descriptor, but not with the pinned tuple.
        for name in ('home','parent'):
            target=self.home if name=='home' else self.parent
            displaced=self.park/name; changed=False
            def scanned(identity):
                nonlocal changed
                # _checked_home_anchor does not call scandir; reaching root
                # scandir means pre-scan validation already completed.
                if identity==self.identity(self.root.stat()) and not changed:
                    changed=True; target.rename(displaced); target.mkdir()
                    if name=='parent': (target/'home').mkdir()
            with self.subTest(target=name),self.inventory():
                anchor=stage.capture_home_anchor(self.root)
                real_scan=stage.os.scandir
                def scan(descriptor):
                    scanned(self.identity(os.fstat(descriptor)))
                    return real_scan(descriptor)
                with mock.patch.object(stage.os,'scandir',side_effect=scan):
                    self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
                self.assertTrue(changed)
            if name=='parent': (target/'home').rmdir()
            target.rmdir(); displaced.rename(target)

    def test_after_open_rename_of_socket_ancestor_is_rejected(self):
        nested=self.home/'nested'; nested.mkdir()
        leaf=self.leaf('onec-db-oracle/home/nested/ipc'); real_open=stage.os.open
        for name,target in (('parent',self.parent),('home',self.home),('nested',nested)):
            original=self.identity(target.stat()); displaced=self.park/name; opens=0; changed=False
            def opened(path,*args,**kwargs):
                nonlocal opens,changed
                descriptor=real_open(path,*args,**kwargs)
                if self.identity(os.fstat(descriptor))==original:
                    opens+=1
                    # Fixed anchors are opened once in the pre-scan check first.
                    if opens==(1 if name=='nested' else 2):
                        changed=True; target.rename(displaced); target.mkdir()
                        if name=='parent': (target/'home').mkdir()
                return descriptor
            with self.subTest(target=name),self.inventory(leaf):
                anchor=stage.capture_home_anchor(self.root)
                with mock.patch.object(stage.os,'open',side_effect=opened):
                    self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
                self.assertTrue(changed)
            if name=='parent': (target/'home').rmdir()
            target.rmdir(); displaced.rename(target)

    def test_post_recursion_checks_missing_replaced_or_symlinked_ancestors(self):
        nested=self.home/'nested'; nested.mkdir(); leaf=self.leaf('onec-db-oracle/home/nested/ipc')
        nested_identity=self.identity(nested.stat())
        for name,target in (('parent',self.parent),('home',self.home),('nested',nested)):
            for replacement in ('missing','directory','symlink'):
                displaced=self.park/(name+'-'+replacement); changed=False
                def completed(identity):
                    nonlocal changed
                    if identity==nested_identity and not changed:
                        changed=True; target.rename(displaced)
                        if replacement=='directory':
                            target.mkdir()
                            if name=='parent': (target/'home').mkdir()
                        elif replacement=='symlink': target.symlink_to(displaced,target_is_directory=True)
                with self.subTest(target=name,replacement=replacement),self.inventory(leaf,after_scan=completed):
                    anchor=stage.capture_home_anchor(self.root)
                    self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
                    self.assertTrue(changed)
                if replacement=='directory':
                    if name=='parent': (target/'home').rmdir()
                    target.rmdir()
                elif replacement=='symlink': target.unlink()
                displaced.rename(target)

    def test_final_anchor_check_runs_even_when_no_home_sockets_were_seen(self):
        changed=False; displaced=self.park/'home'
        def completed(identity):
            nonlocal changed
            if identity==self.identity(self.root.stat()) and not changed:
                changed=True; self.home.rename(displaced); self.home.mkdir()
        with self.inventory(after_scan=completed):
            anchor=stage.capture_home_anchor(self.root)
            self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
            self.assertTrue(changed)

    def test_preexisting_symlink_ancestor_is_not_followed(self):
        for name,target in (('parent',self.parent),('home',self.home)):
            displaced=self.park/name
            with self.subTest(target=name),self.inventory():
                anchor=stage.capture_home_anchor(self.root)
                target.rename(displaced); target.symlink_to(displaced,target_is_directory=True)
                self.assert_kind('snapshot_changed',lambda: stage.sandbox_bytes(self.root,home_anchor=anchor))
                self.assert_kind('snapshot_changed',lambda: stage.capture_home_anchor(self.root))
                target.unlink(); displaced.rename(target)

    def test_missing_ordinary_entries_remain_tolerated_under_pinned_home(self):
        missing=self.leaf('onec-db-oracle/home/missing',mode=stat.S_IFREG)
        missing[1].stat.side_effect=FileNotFoundError(errno.ENOENT,'synthetic disappearance')
        gone=self.leaf('onec-db-oracle/home/gone',mode=stat.S_IFDIR)
        real_open=stage.os.open
        def opened(path,*args,**kwargs):
            if path=='gone': raise FileNotFoundError(errno.ENOENT,'synthetic disappearance')
            return real_open(path,*args,**kwargs)
        with self.inventory(missing,gone),mock.patch.object(stage.os,'open',side_effect=opened):
            self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=stage.capture_home_anchor(self.root)),0)

    def test_socket_metadata_is_never_opened_connected_copied_or_exported(self):
        leaves=[self.leaf('onec-db-oracle/home/nested/ipc'),self.leaf('.X11-unix/X99')]
        real_open=stage.os.open
        with self.inventory(*leaves),mock.patch.object(stage.os,'open',wraps=real_open) as opened, \
                mock.patch.object(socket,'socket',side_effect=AssertionError('no IPC')), \
                mock.patch.object(stage.shutil,'copyfile',side_effect=AssertionError('no copy')), \
                mock.patch.object(stage.shutil,'copytree',side_effect=AssertionError('no copy')), \
                mock.patch.object(stage,'file_summary',side_effect=AssertionError('no export')):
            anchor=stage.capture_home_anchor(self.root)
            self.assertEqual(stage.sandbox_bytes(self.root,home_anchor=anchor),0)
            for call in opened.call_args_list:
                self.assertTrue(call.args[1]&os.O_DIRECTORY)
                self.assertTrue(call.args[1]&os.O_NOFOLLOW)
                self.assertNotIn(str(call.args[0]),('ipc','X99'))

    def test_native_budget_forwards_the_original_pin_without_recapture(self):
        native=stage.Native(NONCE,provenance()); self.assertIsNone(native.home_anchor)
        native.root=self.parent; native.budget_base=self.root
        with self.inventory(): native.home_anchor=stage.capture_home_anchor(self.root)
        with mock.patch.object(stage,'sandbox_bytes') as scan,mock.patch.object(stage,'capture_home_anchor') as capture:
            native.budgets(17); native.budgets(19)
        self.assertEqual(scan.call_args_list,[mock.call(self.root,17,home_anchor=native.home_anchor),
            mock.call(self.root,19,home_anchor=native.home_anchor)])
        capture.assert_not_called()

    def test_preflight_captures_private_home_before_any_command(self):
        self.home.rmdir(); self.parent.rmdir()
        native=stage.Native(NONCE,provenance()); native.root=self.parent; native.budget_base=self.root
        native.artifacts=self.parent/'artifacts'; native.evidence=self.parent/'evidence'
        real_path=Path; sentinel=OracleError('process_failed')
        def path(value): return self.root/'runtime' if str(value)=='/tmp/runtime' else real_path(value)
        def command(*args,**kwargs):
            self.assertTrue(self.home.is_dir()); self.assertIsNotNone(native.home_anchor)
            self.assertEqual(native.home_anchor,stage.capture_home_anchor(self.root))
            raise sentinel
        with self.inventory(),mock.patch.object(stage,'Path',side_effect=path), \
                mock.patch.object(stage.os,'geteuid',return_value=1000,create=True), \
                mock.patch.object(stage.os,'access',return_value=True),mock.patch.object(stage,'ONEC') as onec, \
                mock.patch.object(stage.os,'pidfd_open',create=True), \
                mock.patch.object(stage.signal,'pidfd_send_signal',create=True), \
                mock.patch.dict(stage.os.environ),mock.patch.object(stage,'process_snapshot',return_value=set()), \
                mock.patch.object(native,'process',side_effect=command) as process:
            onec.is_file.return_value=True
            with self.assertRaises(OracleError) as failure: native.preflight()
            self.assertIs(failure.exception,sentinel); process.assert_called_once()

    def test_admitted_socket_never_bypasses_live_process_census_or_timeout(self):
        for outcome in ('census','timeout'):
            native=stage.Native(NONCE,provenance()); native.root=self.parent; native.budget_base=self.root
            native.evidence=self.parent/('evidence-'+outcome); native.evidence.mkdir(); native.deadline=1000
            native.begin_stage('seed_v1'); child=mock.Mock(); child.pid=999
            child.poll.return_value=None if outcome=='timeout' else 0; child.wait.return_value=0
            times=[0,0,1,121] if outcome=='timeout' else [0,0,0,6]
            quiet=[True] if outcome=='timeout' else [True,False]
            with self.subTest(outcome=outcome),self.inventory(self.leaf('onec-db-oracle/home/ipc')):
                native.home_anchor=stage.capture_home_anchor(self.root)
                with mock.patch.object(native,'quiescent',side_effect=quiet), \
                        mock.patch.object(stage.subprocess,'Popen',return_value=child), \
                        mock.patch.object(stage.time,'monotonic',side_effect=times), \
                        mock.patch.object(stage.time,'sleep'),mock.patch.object(stage.os,'killpg',create=True) as kill, \
                        mock.patch.object(stage.signal,'SIGKILL',9,create=True):
                    self.assert_kind('timeout' if outcome=='timeout' else 'snapshot_not_quiescent',
                        lambda: native.process(['synthetic'],'owned-home-socket'))
                    if outcome=='timeout':
                        kill.assert_called_once_with(999,9); child.wait.assert_called_once_with(timeout=5)
                    else: kill.assert_not_called(); child.wait.assert_called_once_with()


    def clone_fixture(self):
        native=stage.Native(NONCE,provenance());native.root=self.parent
        native.artifacts=self.parent/'artifacts';native.artifacts.mkdir()
        native.budget_base=self.root
        frozen=native.artifacts/'baseline';frozen.mkdir()
        data=b'synthetic clone bytes only'
        (frozen/'1Cv8.1CD').write_bytes(data);(frozen/'1Cv8.1CD').chmod(0o400)
        frozen.chmod(0o500);self.addCleanup(lambda:frozen.chmod(0o700))
        return native,data

    def test_clone_uses_artifact_local_accounting_with_allowed_pinned_home_socket(self):
        native,data=self.clone_fixture()
        with self.inventory(self.leaf('onec-db-oracle/home/ipc')):
            native.home_anchor=stage.capture_home_anchor(self.root)
            with mock.patch.object(native,'quiescent',return_value=True),                     mock.patch.object(native,'budgets',wraps=native.budgets) as budgets,                     mock.patch.object(stage,'clone_database',wraps=stage.clone_database) as clone:
                result=native.clone('baseline','observer')
                self.assertEqual(clone.call_args.kwargs,{'budget_root':native.artifacts})
                self.assertEqual(budgets.call_args_list,[mock.call(len(data)),mock.call()])
            self.assertEqual((result/'1Cv8.1CD').read_bytes(),data)
            self.assertEqual([path.name for path in result.iterdir()],['1Cv8.1CD'])

    def test_clone_still_reserves_entire_global_home_bytes_before_allocation(self):
        native,data=self.clone_fixture();(self.home/'cache').write_bytes(b'x'*len(data))
        with self.inventory(self.leaf('onec-db-oracle/home/ipc')):
            native.home_anchor=stage.capture_home_anchor(self.root)
            with mock.patch.object(native,'quiescent',return_value=True),                     mock.patch.object(stage,'MAX_LIVE_BYTES',len(data)*3-1),                     mock.patch.object(stage,'clone_database',wraps=stage.clone_database) as clone:
                self.assert_kind('artifact_limit',lambda:native.clone('baseline','observer'))
                clone.assert_not_called()
                self.assertFalse((native.artifacts/'observer').exists())

    def test_clone_global_postcheck_still_rejects_home_growth(self):
        native,data=self.clone_fixture();real_clone=stage.clone_database
        def clone(*args,**kwargs):
            real_clone(*args,**kwargs)
            (self.home/'cache').write_bytes(b'x'*len(data)*3)
        with self.inventory(self.leaf('onec-db-oracle/home/ipc')):
            native.home_anchor=stage.capture_home_anchor(self.root)
            with mock.patch.object(native,'quiescent',return_value=True),                     mock.patch.object(stage,'MAX_LIVE_BYTES',len(data)*4),                     mock.patch.object(stage,'clone_database',side_effect=clone):
                self.assert_kind('artifact_limit',lambda:native.clone('baseline','observer'))



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




class BaselineDiagnosticTests(unittest.TestCase):
    def injected(self,operation,error,*,clean=(True,True),failed_stage='baseline'):
        identity=provenance(); report=protocol.empty_report(NONCE,identity)
        backend=FixtureNative(identity); backend.clean=clean
        controller=stage.Controller(backend,report); backend.controller=controller
        original=getattr(backend,operation)
        def called(*args):
            if controller.stage==failed_stage: raise error
            return original(*args)
        with mock.patch.object(backend,operation,side_effect=called):
            value=controller.run()
        protocol.validate_report(protocol.encode(value),nonce=NONCE,provenance=identity)
        self.assertFalse(value['accepted'])
        self.assertEqual(backend.events[-1],('cleanup',))
        return value

    def test_each_baseline_operation_is_source_bound_and_has_exact_snapshot_prefix(self):
        for operation in ('freeze','observe','audit'):
            with self.subTest(operation=operation):
                value=self.injected(operation,OracleError('invalid_input'))
                self.assertEqual(value['failure_kind'],'baseline_'+operation+'_invalid_input')
                self.assertEqual([item['id'] for item in value['snapshots']],
                                 ['baseline'] if operation=='audit' else [])
                self.assertEqual(value['failed_stage'],'baseline')

    def test_every_root_entry_shape_is_finite_and_never_leaks_native_text(self):
        for operation in ('freeze','observe','audit'):
            for entry in ENTRY_CLASSES:
                for shape in ENTRY_SHAPES:
                    with self.subTest(operation=operation,entry=entry,shape=shape):
                        error=DatabaseEntryError(entry,shape)
                        error.args=('PRIVATE /raw/path native bytes',)
                        value=self.injected(operation,error)
                        self.assertEqual(value['failure_kind'],
                            'baseline_'+operation+'_entry_'+entry+'_'+shape)
                        self.assertNotIn(b'PRIVATE',protocol.encode(value))
                        self.assertNotIn(b'/raw/path',protocol.encode(value))

    def test_other_error_categories_are_not_relabelled(self):
        for operation in ('freeze','observe','audit'):
            for kind in ('snapshot_changed','snapshot_not_quiescent','artifact_limit',
                         'process_failed','metadata_rejected','invalid_marker'):
                with self.subTest(operation=operation,kind=kind):
                    value=self.injected(operation,OracleError(kind))
                    self.assertEqual(value['failure_kind'],kind)

    def test_later_stage_rejection_cannot_inherit_baseline_context(self):
        for operation in ('freeze','observe'):
            for error in (OracleError('invalid_input'),DatabaseEntryError('other','special')):
                with self.subTest(operation=operation,error=type(error)):
                    value=self.injected(operation,error,failed_stage='create')
                    self.assertEqual(value['failed_stage'],'create')
                    self.assertEqual(value['failure_kind'],'invalid_input')

    def test_wrapped_baseline_error_in_another_stage_fails_closed(self):
        value=self.injected('freeze',stage.BaselineInputError('freeze'),failed_stage='create')
        self.assertEqual(value['failure_kind'],'unexpected_failure')

    def test_primary_baseline_diagnosis_survives_cleanup_failure(self):
        for clean in ((False,True),(True,False),(False,False)):
            value=self.injected('freeze',DatabaseEntryError('session_history','owned_regular_nonzero'),clean=clean)
            self.assertEqual(value['failure_kind'],'baseline_freeze_entry_session_history_owned_regular_nonzero')
            self.assertEqual(value['stages'][-1]['status'],'failed')
            self.assertEqual(value['failed_stage'],'baseline')

    def test_baseline_internal_context_rejects_unknown_bool_and_partial_combinations(self):
        bad=(True,False,None,1,{},[], 'PRIVATE /path')
        for value in bad:
            with self.subTest(operation=value),self.assertRaises(OracleError):
                stage.BaselineInputError(value)
        for entry,shape in [('other',None),(None,'special'),*(('other',v) for v in bad),
                            *((v,'special') for v in bad)]:
            with self.subTest(entry=entry,shape=shape),self.assertRaises(OracleError):
                stage.BaselineInputError('freeze',entry,shape)

    def test_completed_baseline_does_not_leave_pending_operation_state(self):
        value,_=fixture_report()
        self.assertEqual(value['status'],'ok')
        self.assertEqual(value['failure_kind'],'none')
        self.assertFalse(any('baseline_' in key for key in value))



class BasenameControllerTests(unittest.TestCase):
    injected=BaselineDiagnosticTests.injected
    def test_private_candidate_survives_only_successful_native_cleanup(self):
        for clean in ((True,True),(False,True),(True,False),(False,False)):
            error=DatabaseEntryError('other','owned_regular_zero',basename='1Cv8.test')
            value=self.injected('freeze',error,clean=clean)
            self.assertEqual(value['failure_kind'],'baseline_freeze_entry_other_owned_regular_zero')
            self.assertEqual(value.get('rejected_basename'),'1Cv8.test' if all(clean) else None)

    def test_other_operations_and_later_stages_never_export_candidate(self):
        for operation,failed in (('observe','baseline'),('audit','baseline'),('freeze','create')):
            value=self.injected(operation,DatabaseEntryError('other','owned_regular_zero',basename='1Cv8.test'),failed_stage=failed)
            self.assertNotIn('rejected_basename',value)

    def test_internal_context_rejects_malformed_or_inconsistent_basename(self):
        for operation,entry,shape,name in (
            ('observe','other','owned_regular_zero','1Cv8.test'),
            ('freeze','other','owned_regular_nonzero','1Cv8.test'),
            ('freeze','other','owned_regular_zero','1Cv8.1CL'),
            ('freeze','database','owned_regular_zero','1Cv8.1CD'),
            ('freeze','other','owned_regular_zero','1Cv8.test\n'),
            ('freeze','other','owned_regular_zero',False)):
            with self.subTest(operation=operation,entry=entry,shape=shape,name=name),self.assertRaises(OracleError):
                stage.BaselineInputError(operation,entry,shape,basename=name)

    def test_native_capture_gate_is_original_seed_only_with_measured_version(self):
        cases=({},True),({'stage':'create'},False),({'identifier':'other'},False),              ({'database':'other'},False),({'version':None},False),({'root':Path('/tmp/other')},False),              ({'artifacts':Path('/tmp/other/artifacts')},False)
        for changes,expected in cases:
            identity=provenance();identity['actual_version']=changes.get('version',protocol.VERSION)
            native=stage.Native(NONCE,identity);native.stage=changes.get('stage','baseline')
            native.root=changes.get('root',stage.ROOT);native.artifacts=changes.get('artifacts',stage.ROOT/'artifacts')
            database=native.artifacts/changes.get('database','seed');identifier=changes.get('identifier','baseline')
            with self.subTest(changes=changes),mock.patch.object(native,'quiescent',return_value=True),mock.patch.object(stage,'native_file_summary',return_value=physical()),                     mock.patch.object(native,'budgets'),mock.patch.object(native,'remove'),                     mock.patch.object(stage,'freeze_database',return_value=physical()) as freeze:
                native.freeze(database,identifier)
                self.assertIs(freeze.call_args.kwargs['capture_source_name'],expected)
                self.assertEqual(freeze.call_args.args,(database,native.artifacts/identifier))



class NativePayloadCensusTests(unittest.TestCase):
    def test_every_native_payload_entrypoint_checks_census_before_any_read(self):
        native=stage.Native(NONCE,provenance());database=native.artifacts/'seed'
        actions=(('physical_summary',(database/'1Cv8.1CD',)),('create_db',('seed',)),
                 ('freeze',(database,'baseline')),('clone',('baseline','observer')),
                 ('artifact',('cf_v1',)),('export',(database,'cf_v1','/DumpCfg')),
                 ('compare',('baseline','create_control','created')),
                 ('compare_pair',('loaded','applied')))
        for method,args in actions:
            with self.subTest(method=method),contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(native,'quiescent',return_value=False))
                for helper in ('budgets','batch','process'):
                    stack.enter_context(mock.patch.object(native,helper))
                for helper in ('absent','zero_result'):
                    stack.enter_context(mock.patch.object(stage,helper))
                probes=[stack.enter_context(mock.patch.object(stage,name)) for name in
                        ('native_file_summary','file_summary','freeze_database','clone_database','compare_files','compare_pair')]
                with self.assertRaises(OracleError) as failure:getattr(native,method)(*args)
                self.assertEqual(failure.exception.kind,'snapshot_not_quiescent')
                for probe in probes:probe.assert_not_called()

    def test_summary_census_precedes_payload_hashing_and_preserves_result(self):
        native=stage.Native(NONCE,provenance());events=[];expected=physical()
        def quiet():events.append('census');return True
        def summary(path):events.append('payload');return expected
        with mock.patch.object(native,'quiescent',side_effect=quiet),                 mock.patch.object(stage,'native_file_summary',side_effect=summary):
            self.assertEqual(native.physical_summary(native.artifacts/'seed'/'1Cv8.1CD'),expected)
        self.assertEqual(events,['census','payload'])

    def test_comparison_census_precedes_every_frozen_payload_read(self):
        native=stage.Native(NONCE,provenance())
        for method,helper,args in (('compare','compare_files',('baseline','create_control','created')),
                                   ('compare_pair','compare_pair',('loaded','applied'))):
            events=[]
            def quiet():events.append('census');return True
            def compare(*paths):events.append('payload');return {'synthetic':True}
            with self.subTest(method=method),mock.patch.object(native,'quiescent',side_effect=quiet),                     mock.patch.object(stage,helper,side_effect=compare):
                self.assertEqual(getattr(native,method)(*args),{'synthetic':True})
                self.assertEqual(events,['census','payload'])

if __name__=='__main__': unittest.main()


class CommandCompletionBoundaryTests(unittest.TestCase):
    def setUp(self):
        NativeBoundaryTests.setUp(self)
        self.native.begin_stage('create')
    def run_client(self, completion='ok', phase='complete', result=True):
        def process(*args,**kwargs):
            control=json.loads((self.native.evidence/'control.json').read_text())
            if completion is not None:
                (self.native.evidence/'completion.json').write_bytes(protocol.encode({**control,'status':completion,'phase':phase}))
            if result:
                payload={**control,'status':'ok','actual_version':protocol.VERSION,'user':'NativeOracleCRUD',
                    'role_verified':True,'nonprivileged':True,'users_verified':False,'metadata_version':1,
                    'count':1,'code':'K1','payload':'alpha','amount':'1.25','deletion_mark':False,
                    'same_reference':True,'payload_length':32,'amount_digits':9,'amount_scale':2}
                (self.native.evidence/'result.json').write_bytes(protocol.encode(payload))
        return mock.patch.object(self.native,'process',side_effect=process)
    def test_success_requires_both_completion_and_strict_result(self):
        with self.run_client(): self.assertEqual(self.native.enterprise(self.db,'create')['payload'],'alpha')
        self.assertEqual(list(self.native.evidence.iterdir()),[])
    def test_error_completion_never_accepts_valid_result_at_any_create_phase(self):
        for phase in protocol.BSL_OPERATION_PHASES['create']:
            with self.subTest(phase=phase),self.run_client('error',phase):
                with self.assertRaises(OracleError) as caught:self.native.enterprise(self.db,'create')
                self.assertEqual(caught.exception.kind,'process_failed')
                self.assertEqual(caught.exception.failure_context,{'operation':'enterprise_create','site':'result',
                    'bsl_phase':phase,'region':None,'reason':None})
                self.assertEqual(caught.exception.failure_context_stage,'create')
            self.assertEqual(list(self.native.evidence.iterdir()),[])
    def test_missing_malformed_or_incomplete_completion_never_accepts_result(self):
        for status,phase in ((None,'complete'),('ok','write'),('error','PRIVATE /native/path')):
            with self.subTest(status=status),self.run_client(status,phase),self.assertRaises(OracleError):
                self.native.enterprise(self.db,'create')
            self.assertEqual(list(self.native.evidence.iterdir()),[])
        with self.run_client(result=False),self.assertRaises(OracleError):self.native.enterprise(self.db,'create')
    def test_stale_completion_or_pending_rejected_before_launch(self):
        for name in ('completion.json','completion.pending.json'):
            file=self.native.evidence/name;file.write_text('PRIVATE')
            with mock.patch.object(self.native,'process') as process,self.assertRaises(OracleError) as caught:
                self.native.enterprise(self.db,'create')
            self.assertEqual(caught.exception.kind,'stale_evidence');process.assert_not_called();file.unlink()
    @unittest.skipUnless(os.name=='posix','native launch control requires POSIX')
    def test_timeout_identifies_command_poll_and_retains_kill_reap(self):
        child=mock.Mock();child.pid=999;child.poll.return_value=None;self.native.deadline=1000
        with mock.patch.object(self.native,'quiescent',return_value=True),mock.patch.object(self.native,'budgets'), \
             mock.patch.object(stage.subprocess,'Popen',return_value=child), \
             mock.patch.object(stage.time,'monotonic',side_effect=[0,0,0,121]), \
             mock.patch.object(stage.os,'killpg',create=True) as kill:
            with self.assertRaises(OracleError) as caught:self.native.enterprise(self.db,'create')
        self.assertEqual(caught.exception.kind,'timeout')
        self.assertEqual(caught.exception.failure_context,{'operation':'enterprise_create','site':'poll',
            'bsl_phase':None,'region':None,'reason':None})
        kill.assert_called_once_with(999,stage.signal.SIGKILL);child.wait.assert_called_once_with(timeout=5)
    def test_context_cannot_outlive_stage_or_accept_arbitrary_operation(self):
        with self.assertRaises(OracleError) as caught:
            with self.native.command_context('enterprise_create'):
                self.native.begin_stage('update');raise OracleError('process_failed')
        self.assertFalse(hasattr(caught.exception,'failure_context'))
        for op in ('PRIVATE /native/path',True,False,None,[],{}):
            with self.subTest(op=op),self.assertRaises(OracleError):
                with self.native.command_context(op):pass
    def test_baseline_inventory_context_survives_freeze_observe_and_audit(self):
        for operation in ('freeze','observe','audit'):
            identity=provenance();backend=FixtureNative(identity)
            controller=stage.Controller(backend,protocol.empty_report(NONCE,identity));backend.controller=controller
            setattr(backend,operation,lambda *args: (_ for _ in ()).throw(stage.SandboxInventoryError('home','access')))
            report=controller.run();self.assertEqual(report['failure_kind'],'baseline_'+operation+'_invalid_input')
            self.assertEqual(report['failure_context'],{'operation':'inventory','site':'scan','bsl_phase':None,'region':'home','reason':'access'})
            protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity)
    def test_later_inventory_context_and_cleanup_failure_primary_preservation(self):
        for clean in ((True,True),(False,False)):
            identity=provenance();backend=FixtureNative(identity);backend.clean=clean
            controller=stage.Controller(backend,protocol.empty_report(NONCE,identity));backend.controller=controller
            backend.clone=lambda *args: (_ for _ in ()).throw(stage.SandboxInventoryError('runtime','special'))
            report=controller.run();self.assertEqual(report['failed_stage'],'create');self.assertEqual(report['failure_kind'],'invalid_input')
            self.assertEqual('failure_context' in report,all(clean))
            protocol.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity)

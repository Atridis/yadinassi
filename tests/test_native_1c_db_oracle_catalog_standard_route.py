"""Explicit closed routing/admission for partial Catalog standard-field binding.

Only disposable local files and stubbed process interfaces are used. These tests
are not native evidence and never start Docker or touch the shared smoke fixture.
"""
from __future__ import annotations
import contextlib
import copy
import dataclasses
import io
import hashlib
import shutil
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'),
               str(ROOT / 'yadinassi/storage'), str(ROOT / 'scripts'), str(ROOT / 'tests')]
import inputs
import protocol
import snapshots
import record_observation as metadata
import config_catalog_standard_binding as policy
from test_native_1c_db_oracle_catalog_reader import normalize_owners
from test_native_1c_db_oracle_catalog_reference_reader import (successful_source, entries, stored_literal, PREFIX, GUID, A, B)
from test_native_1c_db_oracle_config_content_decode_reader import content_source, ABC_FIXED, EMPTY
import test_native_1c_db_oracle_config_root_projection_policy as base_fixture
from test_native_1c_db_oracle_catalog_standard_binding import private, manifest, projection, source
import test_config_catalog_standard as name_vectors
from snapshots import OracleError
import test_native_1c_db_oracle_stage as stages
import test_native_1c_db_oracle_record_route as old
import test_native_1c_db_oracle_config_content_decode_policy as previous

FLAG = '--config-catalog-standard-binding'
OPTION = {'config_catalog_standard_binding': True}
NONCE = old.NONCE
host = old.host
OLD_OPTIONS = ('record_metadata', 'record_reader', 'params_transport', 'params_extraction',
    'dbnames_identity', 'config_transport', 'config_framing', 'config_marker_census',
    'config_zero_marker_filename', 'config_entry_reference', 'config_blob_chain',
    'config_content_decode', 'config_root_reference_projection', 'config_catalog_observation', 'config_catalog_name_binding')


def identity():
    value = previous.identity()
    value['sources'] = inputs.source_hashes(ROOT, **OPTION)
    return value




def evidence(token=old.TOKEN):
    value=base_fixture.evidence(token);value.update(reader=private(),identity_manifest=manifest());return value


class Backend(stages.FixtureNative):
    def observe_record_metadata(self,identifier):
        self.event('record_metadata',identifier);return evidence()


def fixture(fail=None,cleanup=(True,True)):
    provenance=identity();report=policy.empty_report(NONCE,provenance)
    backend=Backend(provenance,fail);backend.clean=cleanup
    controller=stages.stage.Controller(backend,report);backend.controller=controller
    return controller.run(),backend


class CatalogStandardBindingRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: old.writable(self.root))

    def stage(self):
        staged = self.root / 'inputs'
        value = identity()
        inputs.stage_inputs(ROOT, staged, NONCE, value, **OPTION)
        return staged, value

    def test_closed_inventory_and_historical_membership_unchanged(self):
        current=inputs.inventory(**OPTION)
        self.assertEqual(len(current),26)
        self.assertEqual(set(current),set(inputs.CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES)
            - {'scripts/native_1c_db_oracle/config_root_reference_projection.py'}
            | {'scripts/native_1c_db_oracle/config_catalog_standard_binding.py',
               'yadinassi/storage/config_catalog_references.py',
               'yadinassi/storage/config_catalog_name.py'})
        self.assertEqual(len(set(current.values())),26)
        for name in OLD_OPTIONS:
            self.assertNotIn('scripts/native_1c_db_oracle/config_catalog_standard_binding.py',inputs.inventory(**{name:True}))
            with self.assertRaises(OracleError):inputs.inventory(**OPTION,**{name:True})
        for value in (1,None,'true',(),[]):
            with self.assertRaises(OracleError):inputs.inventory(config_catalog_standard_binding=value)

    def test_standard_field_mismatches_reject_entire_controller_capture(self):
        for changes in ({'code_length':3},{'code_type':0},{'description_length':1}):
            value=evidence()
            value['identity_manifest']=dataclasses.replace(manifest(),**changes)
            with self.subTest(changes=changes),mock.patch.object(Backend,'observe_record_metadata',return_value=value):
                report,_=fixture()
            self.assertNotEqual(report['status'],'ok')
            self.assertEqual(report['config_catalog_standard_binding'],dict(schema=30,status='failed',
                category='structural_rejection',code='config_catalog_standard_mismatch'))
            self.assertEqual(report['artifacts'],[])
            raw=protocol.encode(report)
            self.assertNotIn(b'NativeOracleItems',raw)
            self.assertNotIn(A.encode(),raw)
            self.assertIn(b'config_catalog_standard_mismatch',raw)

    def test_invocation_nineteen_exact_closed_stage_and_container_command(self):
        staged, value = self.stage()
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)
        invocation = json.loads((staged / 'invocation.json').read_bytes())
        self.assertEqual(invocation['schema'], 19)
        self.assertEqual(invocation['lane'], inputs.CONFIG_CATALOG_STANDARD_LANE)
        self.assertTrue((staged / 'config_root_projection.py').is_file())
        self.assertFalse((staged / 'config_content_decode.py').exists())
        self.assertFalse((staged / 'config_root_reference.py').exists())
        self.assertFalse((staged / 'config_root_diagnostic.py').exists())
        command = host.container_command(staged, 'onec-db-oracle-' + 'a' * 32, NONCE, **OPTION)
        self.assertEqual(command[-1], FLAG)
        self.assertEqual(command[command.index('--network') + 1], 'none')
        self.assertIn('--read-only', command)
        self.assertIn('no-new-privileges:true', command)
        for name in OLD_OPTIONS:
            with self.assertRaises(OracleError):
                inputs.verify_inputs(staged, NONCE, **{name: True})

    def test_invocation_stale_schemas_and_tampering_rejected(self):
        staged, value = self.stage()
        old.writable(staged)
        path = staged / 'invocation.json'
        original = json.loads(path.read_bytes())
        changes = [lambda v, n=n: v.update(schema=n) for n in (True, 13, 14, 15, 16, 17, 18)]
        changes += [lambda v: v.update(lane=inputs.CONFIG_CONTENT_DECODE_LANE),
            lambda v: v.update(extra='PRIVATE'), lambda v: v.pop('lane'),
            lambda v: v['provenance']['sources'].pop('yadinassi/storage/config_catalog_references.py'),
            lambda v: v['provenance']['sources'].update({'foreign.py': 'f' * 64})]
        for change in changes:
            modified = copy.deepcopy(original)
            change(modified)
            path.write_bytes(protocol.encode(modified))
            with self.assertRaises(OracleError):
                inputs.verify_inputs(staged, NONCE, **OPTION)
        path.write_bytes(protocol.encode(original))
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)

    def test_missing_changed_or_extra_projector_rejected(self):
        staged, value = self.stage()
        old.writable(staged)
        path = staged / 'config_catalog_name.py'
        original = path.read_bytes()
        for mode in ('changed', 'missing', 'foreign'):
            if mode == 'changed': path.write_bytes(original + b'\n')
            elif mode == 'missing': path.unlink()
            else: (staged / 'foreign.py').write_bytes(b'not admitted')
            with self.subTest(mode=mode), self.assertRaises(OracleError):
                inputs.verify_inputs(staged, NONCE, **OPTION)
            path.write_bytes(original)
            if mode == 'foreign': (staged / 'foreign.py').unlink()
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)

    def test_cold_staged_policy_import_requires_no_interpreter(self):
        staged, _ = self.stage()
        code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'import config_catalog_standard_binding as p;import config_root_projection;'
            'assert p.SCHEMA==29 and p.CAPTURE_SCHEMA==30;'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print("closed")')
        env = {key: value for key, value in os.environ.items()
               if key.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(staged)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertIn(result.stdout, (b'closed\n', b'closed\r\n'))

    def test_cold_actual_image_projection_and_final_report_validation(self):
        staged, provenance = self.stage()
        value = source()
        env = {key: value for key, value in os.environ.items()
               if key.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
        code = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
            'import config_catalog_standard_binding as p;raw=sys.stdin.buffer.read();'
            'o=p.read_projection(lambda a,n:raw[a:a+n],len(raw),limits=p.reader.CatalogLimits());'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'm=p._IdentityManifest("'+NONCE+'","'+('a'*64)+'","'+('b'*64)+'","'+A+'","NativeOracleItems",2,1,0);'
            'print(json.dumps(p.compare_private(o,m,nonce=m.nonce),sort_keys=True))')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(staged)],
            input=value.full_bytes(), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertEqual(json.loads(result.stdout), projection())
        self.assertNotIn(GUID.encode(), result.stdout)
        self.assertNotIn(b'not-a-valid-tail', result.stdout)
        report, _ = fixture()
        report['provenance'] = copy.deepcopy(provenance)
        report['provenance']['actual_version'] = protocol.VERSION
        report['config_catalog_standard_binding'] = policy.bind_capture(evidence(), report)
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        report['accepted'] = True
        code = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
            'import config_catalog_standard_binding as p;r=json.loads(sys.stdin.buffer.read());'
            'p.validate_report(p.encode(r),nonce=r["nonce"],provenance=r["provenance"],final=True);'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print("validated")')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(staged)],
            input=protocol.encode(report), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertIn(result.stdout, (b'validated\n', b'validated\r\n'))

    def test_host_cli_is_explicit_and_mutually_exclusive(self):
        with mock.patch.object(host, 'ROOT', self.root), \
             mock.patch.object(host, 'run_oracle', return_value={'accepted': False}) as run, \
             mock.patch.object(host, 'export_report'), mock.patch.dict(os.environ, {}, clear=True), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(host.main(['--execute-approved-image', '--file-db-oracle', FLAG]), 1)
            self.assertEqual(run.call_args.kwargs, OPTION)
            for other in ('--config-content-decode-observation', '--config-blob-chain-observation',
                          '--config-entry-reference-observation', '--record-metadata-observation'):
                run.reset_mock()
                with self.assertRaises(SystemExit):
                    host.main(['--execute-approved-image', '--file-db-oracle', FLAG, other])
                run.assert_not_called()
            for flags in ([FLAG], ['--execute-approved-image', FLAG],
                          ['--execute-approved-image', '--file-db-oracle', FLAG + '=1']):
                run.reset_mock()
                with self.assertRaises(SystemExit): host.main(flags)
                run.assert_not_called()

    def test_native_and_controller_select_policy_without_native_execution(self):
        import config_catalog_standard_binding as policy
        value = identity()
        native = stages.stage.Native(NONCE, value, **OPTION)
        self.assertIs(native.params_policy, policy)
        report = policy.empty_report(NONCE, value)
        controller = stages.stage.Controller(mock.Mock(), report)
        self.assertIs(controller.params_policy, policy)
        self.assertIsNotNone(controller.observation)
        for name in OLD_OPTIONS:
            with self.assertRaises(OracleError):
                stages.stage.Native(NONCE, value, **OPTION, **{name: True})
        for bad in (1, None, 'true'):
            with self.assertRaises(OracleError):
                stages.stage.Native(NONCE, value, config_catalog_standard_binding=bad)

    def test_runtime_main_exact_selection_and_no_policy_guessing(self):
        import config_catalog_standard_binding as policy
        value = identity()
        result = policy.empty_report(NONCE, value)
        result['status'] = 'failed'
        output = io.BytesIO()
        with mock.patch.object(sys, 'argv', ['run.py', '--invocation-nonce', NONCE, FLAG]), \
             mock.patch.object(inputs, 'verify_inputs', return_value=value) as verify, \
             mock.patch.object(stages.stage, 'Native') as native, \
             mock.patch.object(stages.stage, 'Controller', return_value=types.SimpleNamespace(run=lambda: result)), \
             mock.patch.object(policy, 'validate_report') as validate, \
             mock.patch.object(sys, 'stdout', types.SimpleNamespace(buffer=output)):
            self.assertEqual(stages.stage.main(), 1)
        self.assertEqual(verify.call_args.kwargs, OPTION)
        self.assertEqual(native.call_args.kwargs, OPTION)
        self.assertEqual(json.loads(output.getvalue())['schema'], 29)
        validate.assert_called_once()
        for flags in ([FLAG, '--config-content-decode-observation'], [FLAG + '=1'], ['--config-root-reference-observation']):
            with mock.patch.object(sys, 'argv', ['run.py', '--invocation-nonce', NONCE] + flags), \
                 mock.patch.object(stages.stage, 'Native') as native:
                self.assertEqual(stages.stage.main(), 2)
                native.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX shell launcher')
    def test_shell_whitelist_forwards_only_single_exact_flag(self):
        stub = self.root / 'python3'
        stub.write_bytes(b'#!/bin/sh\nprintf "%s\\n" "$@"\n')
        stub.chmod(0o755)
        command = ['/bin/bash', str(ROOT / 'scripts/native_1c_db_oracle/probe.sh'), '--invocation-nonce', NONCE]
        for flags, expected in (([], 0), ([FLAG], 0), ([FLAG, '--config-content-decode-observation'], 2),
                                ([FLAG + '=1'], 2), (['--config-root-reference-observation'], 2)):
            result = subprocess.run(command + flags, env={'PATH': str(self.root)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(result.returncode, expected)
            self.assertEqual(result.stderr, b'')
            wanted = ('\n'.join(['-B', '/oracle/run.py', '--invocation-nonce', NONCE] + flags) + '\n').encode()
            self.assertEqual(result.stdout, wanted if expected == 0 else b'')


class CatalogStandardBindingHostCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))
        self.work=self.root/'work';self.work.mkdir()
        self.identity=identity();self.identity['sources']=inputs.source_hashes(ROOT,config_catalog_standard_binding=True)
        self.events=[]

    def invoke(self, *, native_cleanup=(True,True), container_bad=False, staging_bad=False, source_changed=False):
        report,_=fixture(cleanup=native_cleanup)
        report['provenance']=copy.deepcopy(self.identity);report['provenance']['actual_version']=protocol.VERSION
        if report['status']=='ok': report['config_catalog_standard_binding']=policy.bind_capture(evidence(),report)
        def provenance(**kwargs):
            self.assertEqual(kwargs,{'config_catalog_standard_binding':True})
            self.assertNotIn('GHCR_TOKEN',os.environ);self.assertNotIn('GHCR_USER',os.environ)
            self.events.append('provenance');value=copy.deepcopy(self.identity)
            if source_changed and self.events.count('provenance')>1: value['tree']='e'*40
            return value
        def silent(args,env,seconds,input_bytes=None):
            self.assertNotIn('GHCR_TOKEN',os.environ);self.assertNotIn('PRIVATE-SECRET',json.dumps(args))
            self.events.append(args[1])
        def bounded(args,env,seconds,limit):
            self.events.append(args[1])
            if args[1]=='image': return 0,b'linux/amd64|0'
            if args[1]=='ps': return 0,b'still-live' if container_bad else b''
            self.assertEqual(args[1],'run');self.assertEqual(args[-1],'--config-catalog-standard-binding')
            self.assertEqual((seconds,limit),(2400,32768))
            return (0 if report['status']=='ok' else 1),protocol.encode(report)
        class LeftoverDirectory:
            def __init__(self,**kwargs): self.name=tempfile.mkdtemp(**kwargs)
            def __enter__(self): return self.name
            def __exit__(self,*args): return False
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ,{'GHCR_USER':'Atridis','GHCR_TOKEN':'PRIVATE-SECRET'},clear=True))
            stack.enter_context(mock.patch.object(host,'provenance',side_effect=provenance))
            stack.enter_context(mock.patch.object(host.uuid,'uuid4',return_value=__import__('types').SimpleNamespace(hex=NONCE)))
            stack.enter_context(mock.patch.object(host.smoke,'run_silent',side_effect=silent))
            stack.enter_context(mock.patch.object(host.smoke,'bounded_run',side_effect=bounded))
            popen=stack.enter_context(mock.patch.object(host.smoke.subprocess,'Popen',side_effect=AssertionError('real process forbidden')))
            run=stack.enter_context(mock.patch.object(host.smoke.subprocess,'run',side_effect=AssertionError('real process forbidden')))
            if staging_bad: stack.enter_context(mock.patch.object(host.tempfile,'TemporaryDirectory',LeftoverDirectory))
            result=host.run_oracle(self.work,config_catalog_standard_binding=True)
            popen.assert_not_called();run.assert_not_called()
        policy.validate_report(protocol.encode(result),nonce=NONCE,provenance=self.identity,final=True)
        self.assertNotIn(b'PRIVATE-SECRET',protocol.encode(result))
        return result

    def test_all_four_cleanup_gates_and_source_recheck(self):
        result=self.invoke();self.assertTrue(result['accepted']);self.assertTrue(all(result['cleanup'].values()))
        self.assertEqual(self.events,['provenance','login','pull','image','run','rm','ps','provenance'])
        for kwargs in ({'container_bad':True},{'staging_bad':True},{'source_changed':True},
                       {'native_cleanup':(False,True)},{'native_cleanup':(True,False)}):
            self.events.clear();result=self.invoke(**kwargs)
            self.assertFalse(result['accepted']);self.assertIsNone(result['config_catalog_standard_binding'])
            self.assertEqual(result['artifacts'],[])
            old.writable(self.work)
            for child in self.work.iterdir(): shutil.rmtree(child)


@unittest.skipIf(os.name=='nt','POSIX anchored frozen postimage boundary')
class CatalogStandardBindingPostimageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.artifacts=self.root/'artifacts'; self.artifacts.mkdir()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root)); normalize_owners(self)
        self.seed=self.artifacts/'seed'; self.seed.mkdir()
        self.pre=successful_source(payload=stored_literal(b'before'))
        self.post=source()
        (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed,self.artifacts/'baseline',quiescent=lambda:True)
        self.native=stages.stage.Native(NONCE,identity(),config_catalog_standard_binding=True)
        self.native.root=self.root; self.native.artifacts=self.artifacts; self.native.stage='baseline'
        self.native.identity_manifest=manifest();self.native.identity_baseline_verified=True
        self.native.quiescent=lambda:True; self.native.budgets=mock.Mock(); self.calls=[]
        def enterprise(database,operation,*,token):
            self.calls.append((database,operation,token)); (database/'1Cv8.1CD').write_bytes(self.post.full_bytes())
            return old.marker(token)
        self.native.enterprise=enterprise

    def test_real_same_descriptor_projection_uses_closed_postimage_and_removes_both_clones(self):
        with mock.patch.object(policy,'read_owned_projection',wraps=policy.read_owned_projection) as read:
            result=self.native.observe_record_metadata('baseline')
        read.assert_called_once(); self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][:2],(self.artifacts/'auditor',metadata.OPERATION))
        self.assertEqual(result['reader'].projection['candidate_slots'],4)
        self.assertEqual((result['reader'].projection['validated_zero_count'],result['reader'].projection['nonempty_filenames'],
                          result['reader'].projection['later_other_count']),(3,3,0))
        self.assertEqual(result['postimage']['sha256'],hashlib.sha256(self.post.full_bytes()).hexdigest())
        self.assertNotEqual(result['origin']['sha256'],result['postimage']['sha256'])
        self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(),self.pre.full_bytes())
        self.assertFalse((self.artifacts/'auditor').exists());self.assertFalse((self.artifacts/'auditor_frozen').exists())
        report=policy.empty_report(NONCE,identity());report['provenance']['actual_version']=protocol.VERSION
        report['snapshots']=[{'id':'baseline','physical':self.native.physical_summary(self.artifacts/'baseline'/'1Cv8.1CD')}]
        capture=policy.bind_capture(result,report); self.assertEqual(capture['reader'],policy.compare_private(result['reader'],manifest(),nonce=NONCE))

    def test_real_owned_readback_rejects_multiple_candidates_before_evidence(self):
        self.post=source(refs=(A,B),tail=((B,stored_literal(name_vectors.document('\"Other\"')),0),))
        with mock.patch.object(policy,'read_owned_projection',wraps=policy.read_owned_projection) as read:
            with self.assertRaises(policy.ObservationFailure) as ctx:
                self.native.observe_record_metadata('baseline')
        read.assert_called_once()
        self.assertEqual(ctx.exception.code,'config_catalog_owned_count')
        self.assertFalse((self.artifacts/'auditor').exists())
        self.assertFalse((self.artifacts/'auditor_frozen').exists())
        self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(),self.pre.full_bytes())

    def test_changed_postimage_digest_and_nonquiescence_reject_without_capture(self):
        original=snapshots.inspect_frozen_catalog
        def changed(*args,**kwargs):
            summary,result=original(*args,**kwargs);summary['sha256']='e'*64;return summary,result
        with mock.patch.object(snapshots,'inspect_frozen_catalog',side_effect=changed), self.assertRaises(policy.ObservationFailure):
            self.native.observe_record_metadata('baseline')
        self.native.quiescent=lambda:False
        with self.assertRaises(OracleError): self.native.observe_record_metadata('baseline')
        self.assertFalse((self.artifacts/'auditor').exists());self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_new_field_failures_discard_observation_and_remove_both_private_clones(self):
        cases=((content_source([(GUID, ABC_FIXED, 0)]), 'config_projection_root_missing'),
               (content_source([('root', stored_literal(PREFIX), 0)]), 'config_projection_target_missing'),
               (successful_source(target_bytes=b'PRIVATE invalid prefix'), 'config_catalog_prefix'),
               (successful_source(payload=EMPTY), 'config_catalog_content_empty'),
               (source(tail=(('PRIVATE',b'bad',0),)), 'config_content_truncated_deflate'))
        for image,code in cases:
            self.post=image
            with self.subTest(code=code),self.assertRaises(policy.ObservationFailure) as error:
                self.native.observe_record_metadata('baseline')
            self.assertEqual(error.exception.code,code)
            self.assertNotIn('PRIVATE',str(error.exception))
            self.assertFalse((self.artifacts/'auditor').exists())
            self.assertFalse((self.artifacts/'auditor_frozen').exists())
            self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(),self.pre.full_bytes())


if __name__ == '__main__': unittest.main()

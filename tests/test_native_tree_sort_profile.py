"""Synthetic Sort integration/bounds, never real-platform Sort answers."""
import base64
import copy
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from yadinassi import Interpreter
import test_native_tree_profile_budget as budget
from test_native_tree_profile_host import synthetic_producer_reader
from test_native_1c_smoke import bootstrap_report
from test_native_tree_sort_contract import maximum_output
from test_native_tree_sort_measurement import emit

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE
PROFILE = 'tree-sort-v1'


def spec():
    return tree.profiles.select(PROFILE)


def success_envelope(raw):
    s = spec()
    hashes = dict.fromkeys(tree.input_files(profile=PROFILE), 'a'*64)
    hashes[s.source] = s.source_sha256
    modules = {s.case: 'b'*64, 'client_tree': 'c'*64}
    stage = tree.empty_report(NONCE, profile=PROFILE)
    stage.update(status='ok', failure_kind='none', input_sha256=hashes)
    case = stage['cases'][0]
    case.update(status='ok', source_sha256=s.source_sha256, module_sha256=modules[s.case],
                output_sha256=full.digest(raw), output_size=len(raw), message_count=22)
    client = stage['client_tree']
    client.update(status='ok', failure_kind='none', source_sha256=s.source_sha256,
                  module_sha256=modules['client_tree'], roundtrip_sha256=modules['client_tree'],
                  **dict.fromkeys(host.FULL.CLIENT_FLAGS, True),
                  **{k:case[k] for k in host.FULL.CLIENT_OUTPUT_KEYS})
    client['process_diagnostics'].update(stage='after_exit', reason='none')
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp).resolve(strict=True); root = parent/'capture'; root.mkdir()
        (root/(s.case+'.out')).write_bytes(raw)
        tree.write_report(parent/'stage3-report.json', stage, profile=PROFILE)
        with synthetic_producer_reader(tree.full), mock.patch.object(full, 'final_client_process_census'):
            envelope = tree.finish_report(bootstrap_report(), NONCE, root, quiet=True,
                                         bus_cleanup_failed=False, profile=PROFILE)
    return json.loads(envelope), hashes, modules


class SortProfileTests(unittest.TestCase):
    def test_closed_immutable_registry_and_independent_inventory(self):
        s = spec()
        self.assertEqual((s.name,s.case,s.count,s.artifact), (PROFILE,'tree_sort',22,'tree-sort'))
        self.assertEqual(s.source_sha256, '5607a0c42901d624cfae1d166aed8d3ea258a2b0c8e0c894dcd032526a6fb5a3')
        with self.assertRaises(AttributeError): s.case = 'injected'
        for bad in ('', 'sort', '../tree_sort.bsl', None, True, [], {}):
            with self.subTest(profile=bad), self.assertRaises(ValueError): tree.profiles.select(bad)
        inventory = tree.input_files(profile=PROFILE)
        self.assertEqual(inventory, host.staged_files(smoke,profile=PROFILE))
        self.assertIn(s.source,inventory)
        self.assertIn('scripts/native_1c_tree_sort_contract.py',inventory)
        for old in ('tree-v1','tree-copy-v1'):
            prior=tree.input_files(profile=old)
            self.assertNotIn(s.source,prior)
            self.assertNotIn('scripts/native_1c_tree_sort_contract.py',prior)
            self.assertNotIn(tree.profiles.select(old).source,inventory)
        self.assertFalse(any(k.startswith('integrational_tests/tests/') for k in inventory))
        self.assertEqual(full.SCENARIOS,('collections','dates','functions','numbers','strings','values'))

    def test_source_bound_adapter_preserves_capture_and_old_modules(self):
        s=spec();template=(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode()
        source=(ROOT/s.source).read_text(encoding='utf-8').encode()
        module=tree.client_module(source,template,profile=PROFILE)
        runtime=Interpreter();runtime.execute(module.decode('utf-8-sig'))
        runtime.execute('Result = ВычислитьПробу();')
        actual=('\n'.join(runtime.variables['result'].items)+'\n').encode()
        self.assertEqual(actual,emit())
        self.assertEqual(len(tree.validate_observations(actual,profile=PROFILE)),21)
        old_hashes={'tree-v1':'e43224c91c76a1c92dc6c2bf4e6c90a07fe23fbf4aa42d1c6a17630de70a937a',
                    'tree-copy-v1':'aa530ee549b1a1c86781ded0312a0762d25f1bb46c40d17418e2c9e017687cee'}
        for profile,digest in old_hashes.items():
            old=tree.profiles.select(profile)
            self.assertEqual(full.digest(tree.client_module((ROOT/old.source).read_text(encoding='utf-8').encode(),template,profile=profile)),digest)
            with self.assertRaises(full.FullError): tree.client_module(source,template,profile=profile)
        for bad in (source+b'\n',source.replace(b'\n',b'\r\n'),b'\xef\xbb\xbf'+source):
            with self.assertRaises(full.FullError): tree.client_module(bad,template,profile=PROFILE)

    def test_producer_and_host_reject_cross_profile_artifacts_and_bad_evidence(self):
        raw=maximum_output(); value,hashes,modules=success_envelope(raw)
        def validate(v,profile=PROFILE):
            return host.validate_envelope(budget.wire(v),NONCE,hashes,modules,smoke.validate_report,profile=profile)
        self.assertEqual(validate(value)[1],raw)
        for old in ('tree-v1','tree-copy-v1'):
            with self.assertRaises(host.TreeError): validate(value,old)
        changes=[lambda v:v.update(profile='tree-copy-v1'),lambda v:v.update(schema='native-1c-tree-v1'),
                 lambda v:v.update(nonce='1'*32),lambda v:v['report']['stage3'].update(profile='tree-v1'),
                 lambda v:v['report']['stage3']['input_sha256'].pop('scripts/native_1c_tree_sort_contract.py'),
                 lambda v:v['report']['stage3']['cases'][0].update(message_count=21),
                 lambda v:v['report']['stage3']['client_tree'].update(quiet=False),
                 lambda v:v['report']['stage3']['client_tree'].update(output_sha256='0'*64),
                 lambda v:v['outputs'][0].update(name='tree_copy.out'),
                 lambda v:v['outputs'].append(copy.deepcopy(v['outputs'][0])),
                 lambda v:v['outputs'][0].update(data_b64=base64.b64encode(raw+b'\n').decode())]
        for change in changes:
            changed=copy.deepcopy(value);change(changed)
            with self.assertRaises(host.TreeError): validate(changed)
        with self.assertRaises(host.TreeError):
            host.validate_envelope(budget.wire(value)+b' '*65536,NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)

    def test_real_producer_failure_and_unavailable_capture_paths(self):
        # Rebuild producer inputs, not a mutated already-serialized envelope.
        for state in ('success','server','client','server_observer','client_observer',
                      'invalid_capture','missing_capture','nonquiet','bus_cleanup','unavailable'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as tmp:
                raw=maximum_output('M' if state=='unavailable' else 'S')
                value,hashes,modules=success_envelope(raw)
                stage=value['report']['stage3'];s=spec()
                if state in ('server','server_observer'):
                    stage=tree.empty_report(NONCE,profile=PROFILE)
                    stage.update(status='failed',failure_kind='process_failed',input_sha256=hashes,failed_case=s.case)
                    stage['cases'][0].update(status='failed',source_sha256=s.source_sha256)
                elif state in ('client','client_observer'):
                    stage.update(status='failed',failure_kind='process_failed')
                    stage['client_tree'].update(status='failed',failure_kind='process_failed',completed=False,
                        witness_verified=False,**dict.fromkeys(host.FULL.CLIENT_OUTPUT_KEYS,None))
                if state.endswith('_observer'):
                    site=state.split('_')[0]
                    stage['failure_kind']='unsupported_observation'
                    stage['observation_diagnostic']=tree.observation_diagnostic(b'invalid',site,profile=PROFILE)
                    if site=='client': stage['client_tree']['failure_kind']='unsupported_observation'
                parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
                if state!='missing_capture':
                    (capture/(s.case+'.out')).write_bytes(b'invalid' if state=='invalid_capture' else raw)
                tree.write_report(parent/'stage3-report.json',stage,profile=PROFILE)
                with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                    produced=tree.finish_report(bootstrap_report(),NONCE,capture,quiet=state!='nonquiet',
                        bus_cleanup_failed=state=='bus_cleanup',profile=PROFILE)
                if state in ('success','unavailable'):
                    report,payload=host.validate_envelope(produced,NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
                    self.assertEqual(payload,raw)
                    self.assertTrue(report['native_tests_completed'])
                    # This is a synthetic comparison fixture, not raw checkout
                    # admission. Windows may store the BSL checkout as CRLF.
                    # Materialize the same canonical UTF-8/LF source used by
                    # the adjacent availability tests; keep production strict.
                    source=parent/s.source;source.parent.mkdir(parents=True)
                    source.write_bytes((ROOT/s.source).read_text(encoding='utf-8').encode('utf-8'))
                    with budget.synthetic_inventory_reader():
                        compared=host.compare_output(parent,parent,payload,hashes,
                            runner=lambda *a:(0,payload,b''),profile=PROFILE)
                    self.assertEqual(compared['acceptance_status'],'rejected' if state=='unavailable' else 'accepted')
                    self.assertEqual(compared['native_sort_available'],state!='unavailable')
                else:
                    envelope=json.loads(produced)
                    self.assertEqual(envelope['outputs'],[])
                    self.assertFalse(envelope['report']['native_tests_completed'])
                    with self.assertRaises(host.TreeError) as rejected:
                        host.validate_envelope(produced,NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
                    if state in ('server','client'):
                        self.assertEqual(rejected.exception.native_failure['reason'],'process_failed')
                    if state.endswith('_observer'):
                        self.assertEqual(rejected.exception.observation_diagnostic['site'],state.split('_')[0])

    def test_crlf_checkout_lifecycle_and_unchanged_source_hash_guard(self):
        from test_native_1c_full_host import read_synthetic_file
        s=spec();canonical=(ROOT/s.source).read_text(encoding='utf-8').encode('utf-8')
        self.assertEqual(full.digest(canonical),s.source_sha256)
        crlf=canonical.replace(b'\n',b'\r\n')
        self.assertEqual(len(crlf),14803)
        self.assertEqual(full.digest(crlf),'cec5ee13fc4ec61e80f0fa2c3addd987dfefcf6a15bdaa37e0557ebaef3ffc04')
        raw=maximum_output();hashes={s.source:s.source_sha256}
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);checkout=parent/'checkout'
            source=checkout/s.source;source.parent.mkdir(parents=True);source.write_bytes(crlf)
            # Exercise the exact Windows static-fixture reader instance. It
            # reads bytes without newline normalization; the host must reject.
            with mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file):
                self.assertEqual(host.FULL.read_regular(source,host.FULL.MAX_FILE),crlf)
                runner=mock.Mock(side_effect=AssertionError('untrusted source executed'))
                for data,claimed in ((crlf,s.source_sha256),(canonical+b'// drift\n',s.source_sha256),
                                     (canonical,'0'*64)):
                    source.write_bytes(data)
                    with self.assertRaisesRegex(host.TreeError,'tree_source_changed'):
                        host.compare_output(checkout,parent,raw,{s.source:claimed},runner=runner,profile=PROFILE)
                runner.assert_not_called()
                source.write_bytes(crlf)
                # Run the actual ten producer branches from this CRLF checkout,
                # including success and unavailable, not a separate facsimile.
                with mock.patch(__name__+'.ROOT',checkout):
                    self.test_real_producer_failure_and_unavailable_capture_paths()
                self.assertEqual(source.read_bytes(),crlf)

    def test_both_positive_controls_required_even_for_exact_parity(self):
        s=spec()
        for failed_case in (None,0,1,2,3,21):
            raw=maximum_output('M') if failed_case==0 else maximum_output()
            if failed_case: raw=raw.replace(f'TS-{failed_case}: [S/'.encode(),f'TS-{failed_case}: [M/'.encode())
            with tempfile.TemporaryDirectory() as tmp,budget.synthetic_inventory_reader():
                root=Path(tmp).resolve(strict=True);source=root/s.source;source.parent.mkdir(parents=True)
                source.write_bytes((ROOT/s.source).read_text(encoding='utf-8').encode())
                result=host.compare_output(root,root,raw,{s.source:s.source_sha256},runner=lambda *a:(0,raw,b''),profile=PROFILE)
            self.assertEqual(result['status'],'matched')
            self.assertEqual(result['acceptance_status'],'rejected' if failed_case in (0,1,2) else 'accepted')
            self.assertEqual(result['native_sort_available'],failed_case not in (0,1,2))

    def test_successful_controls_without_exact_parity_remain_rejected(self):
        s=spec();native=maximum_output()
        different=native.replace(b'TS-3: [S/',b'TS-3: [A/')
        for actual,status in ((different,'mismatched'),(native+b'\n','invalid_interpreter_output')):
            with tempfile.TemporaryDirectory() as tmp,budget.synthetic_inventory_reader():
                root=Path(tmp).resolve(strict=True);source=root/s.source;source.parent.mkdir(parents=True)
                source.write_bytes((ROOT/s.source).read_text(encoding='utf-8').encode())
                result=host.compare_output(root,root,native,{s.source:s.source_sha256},runner=lambda *a:(0,actual,b''),profile=PROFILE)
            self.assertEqual(result['status'],status)
            self.assertEqual(result['acceptance_status'],'rejected')
            self.assertTrue(result['native_sort_available'])

    def test_completed_marker_and_strict_boundaries(self):
        raw=maximum_output();marker=dict(schema=PROFILE,nonce=NONCE,phase='completed',witness='client',values=raw.decode().splitlines())
        encoded=budget.wire(marker).replace(b'/',b'\\/')
        self.assertEqual(len(raw),6443)
        self.assertEqual(len(encoded)+encoded.count(b',')+encoded.count(b':')+3,6702)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve(strict=True)/'marker.json';path.write_bytes(encoded)
            self.assertEqual(tree.client_marker(path,NONCE,'completed',profile=PROFILE),marker)
            with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed')
            marker['values'].append('extra');path.write_bytes(budget.wire(marker))
            with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed',profile=PROFILE)
            path.write_bytes(b' '*16385)
            with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed',profile=PROFILE)

    @unittest.skipUnless(os.name=='posix','strict POSIX stage')
    def test_stage_hash_binding_and_fixed_cli(self):
        with tempfile.TemporaryDirectory() as tmp,budget.synthetic_inventory_reader():
            root=Path(tmp).resolve(strict=True);stage=root/'stage'
            original=host.FULL.read_regular
            with mock.patch.object(host.FULL,'read_regular',side_effect=lambda p,*a,**k:original(p,*a,**k).replace(b'\r\n',b'\n')):
                hashes=host.stage_inputs(ROOT,stage,smoke,profile=PROFILE)
            modules=host.module_hashes(stage,hashes,smoke,profile=PROFILE)
            self.assertEqual(set(modules),{'tree_sort','client_tree'})
            command=host.container_command(stage,hashes,'onec-tree-'+'1'*32,NONCE,smoke,profile=PROFILE)
            self.assertEqual(command[-3:],['--tree-sort-suite','--invocation-nonce',NONCE])
            for flag in ('--read-only','--network','none','--user','1000:1000','ALL','no-new-privileges:true'):
                self.assertIn(flag,command)
            helper=stage/'bootstrap/native_1c_tree_sort_contract.py';helper.write_bytes(helper.read_bytes()+b'\n')
            with self.assertRaises(host.TreeError): host.module_hashes(stage,hashes,smoke,profile=PROFILE)

    def test_sort_diagnostic_is_finite_and_identical_at_both_boundaries(self):
        self.assertIsNone(tree.observation_diagnostic(maximum_output(),'server',profile=PROFILE))
        for site in ('server','client'):
            with self.assertRaises(tree.ObservationFailure) as caught:
                tree.validate_observations(b'private observer error',site,profile=PROFILE)
            value=caught.exception.diagnostic
            self.assertEqual(value,dict(site=site,case=None,category='record_count',calibration=None))
            tree.validate_diagnostic(value,profile=PROFILE);host.validate_diagnostic(value,profile=PROFILE)
            for key,bad in (('site','private'),('case',1),('case',True),('calibration','E'),('category','secret/path')):
                changed={**value,key:bad}
                with self.assertRaises(full.FullError): tree.validate_diagnostic(changed,profile=PROFILE)
                with self.assertRaises(host.TreeError): host.validate_diagnostic(changed,profile=PROFILE)

    def test_host_cli_rejects_unknown_and_duplicate_profile_before_any_work(self):
        options=(['--profile','tree-sort-v2'],['--profile',PROFILE,'--profile',PROFILE],
                 ['--profile',PROFILE,'--profile','tree-copy-v1'],
                 ['--profile='+PROFILE,'--profile='+PROFILE],
                 ['--profile=tree-v1','--profile='+PROFILE])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(strict=True)
            for flags in options:
                with mock.patch.object(host,'ROOT',root),mock.patch.object(host,'run') as run,\
                     mock.patch.object(sys,'argv',['tree','--execute-approved-image']+flags),\
                     contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
                    host.main()
                self.assertEqual(caught.exception.code,2)
                run.assert_not_called()
                self.assertEqual(list(root.iterdir()),[])

    def test_fixed_dispatch_rejects_unknown_duplicate_or_mixed_profile_flags(self):
        import run_stage
        with mock.patch.object(run_stage,'run') as run:
            for extra in ('--tree-sort-suite','--tree-suite','--tree-copy-suite','--client-probe','source.bsl'):
                self.assertEqual(run_stage.main(['--tree-sort-suite','--invocation-nonce',NONCE,extra]),2)
            run.assert_not_called()
        for options in ({'tree_profile':PROFILE},{'tree_suite':True,'tree_profile':'tree-sort-v2','full_nonce':NONCE},
                        {'tree_suite':True,'tree_profile':PROFILE,'full_nonce':NONCE,'client_probe':True}):
            with mock.patch.object(run_stage.uuid,'uuid4',side_effect=AssertionError('started')) as start:
                with self.assertRaises(run_stage.StageError): run_stage.run(**options)
                start.assert_not_called()

    @unittest.skipUnless(os.name=='posix','isolated staged imports')
    def test_old_staged_inventories_do_not_require_sort_contract(self):
        for profile in ('tree-v1','tree-copy-v1'):
            with tempfile.TemporaryDirectory() as tmp:
                stage=Path(tmp).resolve(strict=True)/'stage'
                original=host.FULL.read_regular
                with mock.patch.object(host.FULL,'read_regular',side_effect=lambda p,*a,**k:original(p,*a,**k).replace(b'\r\n',b'\n')):
                    host.stage_inputs(ROOT,stage,smoke,profile=profile)
                self.assertFalse((stage/'bootstrap/native_1c_tree_sort_contract.py').exists())
                # -I excludes repository/PYTHONPATH, proving actual staged import closure.
                code=("import sys;sys.path.insert(0,"+repr(str(stage/'bootstrap'))+");"
                      "import tree_suite;tree_suite.empty_report("+repr(NONCE)+",profile="+repr(profile)+");"
                      "tree_suite.observation_diagnostic(b'', 'server', profile="+repr(profile)+")")
                result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr.decode())

    @unittest.skipUnless(sys.platform.startswith('linux'),'atomic Linux artifact publisher')
    def test_fixed_artifact_export_refuses_mixing_and_cap_plus_one(self):
        files={'tree_sort.out':maximum_output(),'provenance.json':b'{}\n'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(strict=True)
            wrong=[{'tree_copy.out':files['tree_sort.out'],'provenance.json':b'{}\n'},
                   {**files,'tree_copy.out':b'wrong'},
                   {**files,'tree_sort.out':b'x'*8193},
                   {**files,'provenance.json':b'x'*32769}]
            for data in wrong:
                with self.assertRaises(host.FULL.FullError): host.export_artifact(root,data,profile=PROFILE)
                self.assertFalse((root/'native-smoke').exists())
            host.export_artifact(root,files,profile=PROFILE)
            target=root/'native-smoke/tree-sort-outputs'
            self.assertEqual({p.name for p in target.iterdir()},set(files))
            for name,raw in files.items(): self.assertEqual((target/name).read_bytes(),raw)
            self.assertFalse((root/'native-smoke/tree-copy-outputs').exists())
            with self.assertRaises(host.FULL.FullError): host.export_artifact(root,files,profile=PROFILE)

    def test_stage_writer_cap_plus_one_is_not_relaxed_for_sort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(strict=True)
            tree.write_report(root/'at-cap.json','x'*8190,profile=PROFILE)
            self.assertEqual((root/'at-cap.json').stat().st_size,8192)
            with self.assertRaises(full.FullError): tree.write_report(root/'over.json','x'*8191,profile=PROFILE)
            self.assertFalse((root/'over.json').exists())

    def test_workflow_matrix_is_exact_fixed_and_rejects_unknown_duplicate_or_mixed_rows(self):
        text=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        block=text.split('\n  tree_copy_smoke:\n',1)[1].split('\n  verdict:\n',1)[0]
        expected=("    strategy:\n      fail-fast: false\n      matrix:\n        include:\n"
                  "          - profile: tree-copy-v1\n            artifact: tree-copy\n            case: tree_copy\n"
                  "          - profile: tree-sort-v1\n            artifact: tree-sort\n            case: tree_sort\n"
                  "          - profile: tree-columns-move-v1\n            artifact: tree-columns-move\n            case: tree_columns_move\n"
                  "          - profile: tree-columns-clear-v1\n            artifact: tree-columns-clear\n            case: tree_columns_clear\n")
        def validate(value):
            strategy='    strategy:\n'+value.split('    strategy:\n',1)[1].split('    steps:\n',1)[0]
            self.assertEqual(strategy,expected)
        validate(block)
        self.assertNotIn('profile: tree-columns-move-tail-v1',block)
        bad=(block.replace('profile: tree-sort-v1','profile: arbitrary'),
             block.replace('profile: tree-sort-v1','profile: tree-copy-v1'),
             block.replace('artifact: tree-sort','artifact: tree-copy'),
             block.replace('case: tree_sort','case: tree_copy'),
             block.replace('    steps:\n','          - profile: tree-sort-v1\n            artifact: tree-sort\n            case: tree_sort\n    steps:\n'))
        for changed in bad:
            with self.assertRaises(AssertionError): validate(changed)
        self.assertIn('TREE_PROFILE: ${{ matrix.profile }}',block)
        self.assertIn('--profile "$TREE_PROFILE"',block)
        self.assertIn("github.event_name != 'workflow_dispatch'",block)
        self.assertIn('name: native-1c-${{ matrix.artifact }}-outputs',block)
        self.assertIn('native-smoke/${{ matrix.artifact }}-outputs/${{ matrix.case }}.out',block)
        self.assertIn('native-smoke/${{ matrix.artifact }}-outputs/provenance.json',block)
        self.assertNotIn('inputs.profile',text)
        fill=text.split('\n  tree_smoke:\n',1)[1].split('\n  tree_copy_smoke:\n',1)[0]
        self.assertEqual(hashlib.sha256(fill.encode()).hexdigest(),'601fefac810c0cfcafe51dbd4cee5e6bcc95c8748c779eee2bc74df608351131')

    def test_complete_structural_majorants_fit_unchanged_caps(self):
        s=spec();stage=budget.stage_majorant()
        stage.update(schema=s.stage_schema,profile=PROFILE,failed_case=s.case,
                     input_sha256=dict.fromkeys(tree.input_files(profile=PROFILE),budget.H))
        stage['cases'][0]['name']=s.case
        native=budget.native_majorant();native['stage3']=stage
        report=budget.host_majorant();report.update(profile=PROFILE,trusted_input_sha256=stage['input_sha256'],native_report=native)
        report['host_source_sha256']['scripts/native_1c_tree_sort_contract.py']=budget.H
        report['comparison'].update(profile=PROFILE,native_sort_available=False)
        report['observation_diagnostic']=stage['observation_diagnostic'];report['status']='failed'
        provenance=budget.wire(report)+b'\n'
        report['native_artifact_sha256']=dict.fromkeys((s.case+'.out','provenance.json'),budget.H)
        envelope=dict(schema=s.schema,profile=PROFILE,nonce=NONCE,report=native,
                      outputs=[dict(name=s.case+'.out',size=8192,sha256=budget.H,data_b64=base64.b64encode(b'x'*8192).decode())])
        bounds=dict(stage=len(budget.wire(stage)),native=len(budget.wire(native)),transport=len(budget.wire(envelope))+1,
                    host=len(budget.wire(report))+1,provenance=len(provenance))
        self.assertEqual((tree.MAX_OUTPUT,tree.MAX_TRANSPORT,full.MAX_STAGE_REPORT,host.FULL.MAX_REPORT),(8192,65536,8192,32768))
        for key,cap in (('stage',8192),('native',32768),('transport',65536),('host',32768),('provenance',32768)):
            self.assertLessEqual(bounds[key],cap,(key,bounds))


if __name__=='__main__': unittest.main()

"""Synthetic Copy shard integration, never native Copy semantics evidence."""
import base64
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from yadinassi import Interpreter
import test_native_tree_profile_budget as budget
from test_native_tree_copy_measurement import emit_capture as emit, maximum_capture as maximum_output, synthetic_method, emit_missing_capture
from yadinassi.value_trees import BSLValueTree
from test_native_tree_profile_host import synthetic_producer_reader
from test_native_1c_smoke import bootstrap_report
from scripts import native_1c_tree_copy_diagnostics as diagnostics

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE
PROFILE = 'tree-copy-v1'
SPEC = tree.profiles.select(PROFILE)


def success_envelope(raw):
    hashes = dict.fromkeys(tree.input_files(profile=PROFILE), 'a'*64)
    hashes[SPEC.source] = SPEC.source_sha256
    modules = {SPEC.case: 'b'*64, 'client_tree': 'c'*64}
    stage = tree.empty_report(NONCE, profile=PROFILE)
    stage.update(status='ok', failure_kind='none', input_sha256=hashes)
    case = stage['cases'][0]
    case.update(status='ok', source_sha256=SPEC.source_sha256,
        module_sha256=modules[SPEC.case], output_sha256=full.digest(raw),
        output_size=len(raw), message_count=11)
    client = stage['client_tree']
    client.update(status='ok', failure_kind='none', source_sha256=SPEC.source_sha256,
        module_sha256=modules['client_tree'], roundtrip_sha256=modules['client_tree'],
        **dict.fromkeys(host.FULL.CLIENT_FLAGS, True),
        **{k:case[k] for k in host.FULL.CLIENT_OUTPUT_KEYS})
    client['process_diagnostics'].update(stage='after_exit', reason='none')
    stage['copy_access_probes'] = {site: host.ACCESS_PROBE.witness(raw,site,NONCE,SPEC.source_sha256,
        modules[SPEC.case if site == 'server' else 'client_tree']) for site in ('server','client')}
    report = bootstrap_report()
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp).resolve(strict=True); root = parent/'capture'; root.mkdir()
        (root/(SPEC.case+'.out')).write_bytes(raw)
        tree.write_report(parent/'stage3-report.json', stage, profile=PROFILE)
        with synthetic_producer_reader(tree.full), mock.patch.object(full, 'final_client_process_census'):
            envelope = tree.finish_report(report, NONCE, root, quiet=True,
                bus_cleanup_failed=False, profile=PROFILE)
    return json.loads(envelope), hashes, modules


class CopyProfileTests(unittest.TestCase):
    def test_closed_profiles_and_independent_inventories(self):
        for bad in ('', 'copy', '../tree_copy.bsl', None, True, [], {}):
            with self.subTest(profile=bad), self.assertRaises(ValueError):
                tree.profiles.select(bad)
        with self.assertRaises(AttributeError): SPEC.case = 'injected'
        old = tree.input_files(); new = tree.input_files(profile=PROFILE)
        self.assertEqual((len(old), len(new)), (22, 24))
        self.assertEqual(new, host.staged_files(smoke, profile=PROFILE))
        self.assertNotIn(tree.SOURCE, new)
        self.assertNotIn(SPEC.source, old)
        self.assertFalse(any(k.startswith('integrational_tests/tests/') for k in new))
        self.assertEqual(new['scripts/native_1c_tree_copy_diagnostics.py'],
                         'bootstrap/native_1c_tree_copy_diagnostics.py')
        self.assertEqual(full.SCENARIOS, ('collections','dates','functions','numbers','strings','values'))

    def test_client_adapter_preserves_runtime_output_and_byte_identity(self):
        template = (ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode()
        source = (ROOT/SPEC.source).read_text(encoding='utf-8').encode()
        module = tree.client_module(source, template, profile=PROFILE)
        runtime = Interpreter(); runtime.execute(module.decode('utf-8-sig'))
        runtime.execute('Result = ВычислитьПробу();')
        actual = ('\n'.join(runtime.variables['result'].items)+'\n').encode()
        self.assertEqual(actual, emit())
        self.assertIn('ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина)'.encode(),module)
        self.assertIn(b'Code = 47',module)
        self.assertIn('TreeLaneCharacters + СтрДлина(Text) > 8181'.encode(),module)
        self.assertEqual(len(actual), 6269)
        self.assertEqual([v['status'] for v in tree.validate_observations(actual, profile=PROFILE)], ['S']*8+['A'])
        default = tree.client_module((ROOT/tree.SOURCE).read_text(encoding='utf-8').encode(), template)
        self.assertEqual(full.digest(default), 'e43224c91c76a1c92dc6c2bf4e6c90a07fe23fbf4aa42d1c6a17630de70a937a')
        for wrong_source, wrong_profile in ((source, 'tree-v1'), ((ROOT/tree.SOURCE).read_text(encoding='utf-8').encode(), PROFILE)):
            with self.assertRaises(full.FullError):
                tree.client_module(wrong_source, template, profile=wrong_profile)
        for bad in (source+b'\n', source.replace(b'\n', b'\r\n')):
            with self.assertRaises(full.FullError): tree.client_module(bad, template, profile=PROFILE)
        runtime.variables['alphabet'] = ''.join(sorted(diagnostics.MESSAGE_CHARACTERS))
        runtime.execute('TreeLaneMessages = Новый Массив; TreeLaneCharacters = 0; TreeLaneCapture(alphabet);')
        for bad in ('\n', '\r', 'é', '"', '\\', '<', '>', '&'):
            runtime.variables['bad'] = bad
            with self.assertRaises(Exception): runtime.execute('TreeLaneCapture(bad);')

    def test_diagnostics_have_identical_host_and_producer_admission(self):
        raw = maximum_output(); lines = raw.splitlines(keepends=True)
        for site in ('server', 'client'):
            for case in range(1,10):
                for phase in diagnostics.OBSERVER_STAGES:
                    changed = lines.copy(); changed[case+1] = f'TC-{case}: [X{phase}]\n'.encode()
                    with self.assertRaises(tree.ObservationFailure) as caught:
                        tree.validate_observations(b''.join(changed), site, profile=PROFILE)
                    value = caught.exception.diagnostic
                    self.assertEqual(value['category'], 'observer_'+phase.lower())
                    tree.validate_diagnostic(value, profile=PROFILE)
                    host.validate_diagnostic(value, profile=PROFILE)
                    for key, bad in (('case', True), ('case', 10), ('category', 'secret/path'), ('calibration', 'E')):
                        with self.assertRaises(full.FullError): tree.validate_diagnostic({**value,key:bad}, profile=PROFILE)
                        with self.assertRaises(host.TreeError): host.validate_diagnostic({**value,key:bad}, profile=PROFILE)
        self.assertIsNone(tree.observation_diagnostic(raw, 'server', profile=PROFILE))

    def test_real_producer_and_host_accept_only_bound_copy_evidence(self):
        raw = maximum_output(); value, hashes, modules = success_envelope(raw)
        def validate(value, profile=PROFILE):
            return host.validate_envelope(json.dumps(value).encode(), NONCE, hashes, modules,
                                          smoke.validate_report, profile=profile)
        self.assertEqual(validate(value)[1], raw)
        with self.assertRaises(host.TreeError): validate(value, 'tree-v1')
        changes = [lambda v:v.update(profile='tree-v1'), lambda v:v.update(schema='native-1c-tree-v1'),
            lambda v:v.update(nonce='1'*32), lambda v:v['report']['stage3'].update(profile='tree-v1'),
            lambda v:v['report']['stage3']['input_sha256'].pop('scripts/native_1c_tree_copy_diagnostics.py'),
            lambda v:v['report']['stage3']['cases'][0].update(message_count=34),
            lambda v:v['report']['stage3']['client_tree'].update(quiet=False),
            lambda v:v['report']['stage3']['client_tree'].update(output_sha256='0'*64),
            lambda v:v['outputs'][0].update(name='tree_fill_values.out'),
            lambda v:v['outputs'][0].update(data_b64=base64.b64encode(raw+b'\n').decode())]
        for change in changes:
            changed=copy.deepcopy(value);change(changed)
            with self.assertRaises(host.TreeError): validate(changed)

    def test_marker_caps_and_no_cross_profile_admission(self):
        raw = maximum_output()
        marker = dict(schema=PROFILE, nonce=NONCE, phase='completed', witness='client', values=raw.decode().splitlines())
        # JSON writers may escape slash: charge that overhead too, not only Python compact serialization.
        encoded = budget.wire(marker).replace(b'/', b'\\/')
        self.assertLessEqual(len(encoded)+encoded.count(b',')+encoded.count(b':')+3, 16384)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve(strict=True)/'marker.json';path.write_bytes(encoded)
            self.assertEqual(tree.client_marker(path, NONCE, 'completed', profile=PROFILE), marker)
            with self.assertRaises(full.FullError): tree.client_marker(path, NONCE, 'completed')
            marker['values'].append('extra');path.write_bytes(budget.wire(marker))
            with self.assertRaises(full.FullError): tree.client_marker(path, NONCE, 'completed', profile=PROFILE)

    @unittest.skipUnless(os.name == 'posix', 'strict POSIX staged descriptors')
    def test_stage_binding_hardening_and_fixed_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp).resolve(strict=True); stage=private/'stage'
            with budget.synthetic_inventory_reader():
                original=host.FULL.read_regular
                def canonical(path,*a,**k): return original(path,*a,**k).replace(b'\r\n',b'\n')
                with mock.patch.object(host.FULL,'read_regular',side_effect=canonical):
                    hashes=host.stage_inputs(ROOT,stage,smoke,profile=PROFILE)
            modules=host.module_hashes(stage,hashes,smoke,profile=PROFILE)
            self.assertEqual(set(modules), {'tree_copy','client_tree'})
            command=host.container_command(stage,hashes,'onec-tree-'+'1'*32,NONCE,smoke,profile=PROFILE)
            self.assertEqual(command[-3:], ['--tree-copy-suite','--invocation-nonce',NONCE])
            for flag in ('--read-only','--network','none','--user','1000:1000','ALL','no-new-privileges:true'):
                self.assertIn(flag, command)
            for path in (stage,*stage.rglob('*')):
                self.assertEqual(path.stat().st_mode&0o777,0o755 if path.is_dir() else 0o644)
            helper=stage/'bootstrap/native_1c_tree_copy_diagnostics.py';helper.write_bytes(helper.read_bytes()+b'\n')
            with self.assertRaises(host.TreeError): host.module_hashes(stage,hashes,smoke,profile=PROFILE)

    def test_no_native_only_success_bypass_in_cli_or_verdict(self):
        value={'native_measurement_accepted':True,'runtime_parity_accepted':False}
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(host,'ROOT',Path(tmp)),mock.patch.object(host,'run',return_value=value),\
                 mock.patch.object(sys,'argv',['tree','--execute-approved-image','--profile',PROFILE]):
                self.assertEqual(host.main(),1)
            self.assertEqual(json.loads((Path(tmp)/'native-smoke/tree-copy-report.json').read_bytes()),value)
        text=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text()
        begin=text.index('          # BEGIN NATIVE CI VERDICT');end=text.index('          PYTHON',begin)
        code='\n'.join(line[10:] for line in text[begin:end].splitlines())
        for status in ('success','failed','skipped','cancelled',''):
            env=dict(ELIGIBILITY_RESULT='success',NATIVE_RESULT='success',TREE_RESULT='success',TREE_COPY_RESULT=status,TREE_REQUIRED='true')
            with mock.patch.dict(os.environ,env,clear=True),mock.patch('builtins.print'),self.assertRaises(SystemExit) as caught:
                exec(code,{'os':os})
            self.assertEqual(caught.exception.code,0 if status=='success' else 1)

    def test_fixed_stage_cli_and_invalid_combinations_never_start(self):
        import run_stage
        import full_suite
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            # macOS temporary roots may start at the /var symlink. The owned
            # fixture must use its canonical path; production stays no-follow.
            root = Path(tmp).resolve(strict=True)
            stack.enter_context(mock.patch.object(run_stage, 'ROOT', root))
            run = stack.enter_context(mock.patch.object(run_stage, 'run', return_value={'status':'ok'}))
            if os.name == 'nt':
                # This is dispatch evidence, not a Windows descriptor-security
                # test. Patch the exact module imported by run_stage.main.
                from test_native_1c_full_host import read_synthetic_file
                stack.enter_context(mock.patch.object(full_suite, 'secure_bytes',
                    side_effect=lambda path, limit, *, allow_empty=False:
                        read_synthetic_file(path, limit, nonempty=not allow_empty)))
            (root/'stage3-report.json').write_text('{"status":"ok"}')
            self.assertEqual(run_stage.main(['--tree-copy-suite','--invocation-nonce',NONCE]),0)
            self.assertEqual(run.call_args.kwargs['tree_profile'],PROFILE)
            self.assertTrue(run.call_args.kwargs['tree_suite'])
        for options in ({'tree_profile':PROFILE}, {'tree_suite':True,'tree_profile':'arbitrary','full_nonce':NONCE},
                        {'tree_suite':True,'tree_profile':PROFILE,'full_nonce':NONCE,'client_probe':True}):
            with mock.patch.object(run_stage.uuid,'uuid4',side_effect=AssertionError('started')) as start:
                with self.assertRaises(run_stage.StageError): run_stage.run(**options)
                start.assert_not_called()
        with mock.patch.object(run_stage,'run') as run:
            for extra in ('--client-probe','--tree-suite','source.bsl'):
                self.assertEqual(run_stage.main(['--tree-copy-suite','--invocation-nonce',NONCE,extra]),2)
            run.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'requires owned POSIX directory symlink')
    def test_stage_fixture_alias_rejected_but_canonical_root_accepted(self):
        import run_stage
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve(strict=True)
            root = parent/'real'; root.mkdir()
            alias = parent/'alias'; alias.symlink_to(root, target_is_directory=True)
            (root/'stage3-report.json').write_text('{"status":"ok"}')
            with mock.patch.object(run_stage, 'run', return_value={'status':'ok'}) as run:
                with mock.patch.object(run_stage, 'ROOT', alias):
                    self.assertEqual(run_stage.main(['--tree-copy-suite','--invocation-nonce',NONCE]), 1)
                (root/'stage2-report.json').unlink()
                with mock.patch.object(run_stage, 'ROOT', alias.resolve(strict=True)):
                    self.assertEqual(run_stage.main(['--tree-copy-suite','--invocation-nonce',NONCE]), 0)
                self.assertEqual(run.call_count, 2)
                for call in run.call_args_list:
                    self.assertEqual(call.kwargs['tree_profile'], PROFILE)
                    self.assertTrue(call.kwargs['tree_suite'])

class CopyStructuralBudgetTests(unittest.TestCase):
    def test_complete_structural_majorants_fit_original_caps(self):
        stage=budget.stage_majorant()
        stage.update(schema=SPEC.stage_schema,profile=PROFILE,failed_case=SPEC.case,
                     input_sha256=dict.fromkeys(tree.input_files(profile=PROFILE),budget.H))
        stage['cases'][0]['name']=SPEC.case
        stage['observation_diagnostic']['category']=budget.longest(diagnostics.DIAGNOSTIC_CATEGORIES)
        raw=maximum_output()
        stage['copy_access_probes']={site: host.ACCESS_PROBE.witness(raw,site,NONCE,SPEC.source_sha256,budget.H)
            for site in ('server','client')}
        native=budget.native_majorant();native['stage3']=stage
        report=budget.host_majorant()
        report.update(profile=PROFILE,trusted_input_sha256=stage['input_sha256'],native_report=native)
        report['comparison']['profile']=PROFILE
        report['comparison'].update(native_copy_available=False,parity_projection='TC-C2-and-nine-cases',
            native_main_sha256=budget.H,native_main_size=8192,interpreter_main_sha256=budget.H,interpreter_main_size=8192)
        report['probe_measurement_accepted']={'server':False,'client':False}
        report['observation_diagnostic']=stage['observation_diagnostic']
        report['status']='failed'
        provenance=budget.wire(report)+b'\n'
        report['native_artifact_sha256']=dict.fromkeys((SPEC.case+'.out','provenance.json'),budget.H)
        envelope=dict(schema=SPEC.schema,profile=PROFILE,nonce=NONCE,report=native,
            outputs=[dict(name=SPEC.case+'.out',size=8192,sha256=budget.H,data_b64=base64.b64encode(b'x'*8192).decode())])
        bounds=dict(stage=len(budget.wire(stage)),native=len(budget.wire(native)),
                    transport=len(budget.wire(envelope))+1,host=len(budget.wire(report))+1,
                    provenance=len(provenance))
        for key,cap in (('stage',8192),('native',32768),('transport',65536),('host',32768),('provenance',32768)):
            self.assertLessEqual(bounds[key],cap,(key,bounds))
        # The exact host's eagerly loaded helpers must all be charged, not only the selected contract.
        identities=set(report['host_source_sha256'])
        self.assertEqual(identities,{'scripts/native_1c_tree_profile.py','scripts/native_1c_tree_fill_contract.py',
            'scripts/native_1c_tree_copy_contract.py','scripts/native_1c_tree_copy_diagnostics.py','scripts/native_1c_tree_access_probe.py',
            'scripts/native_1c_tree_profiles.py','scripts/native_1c_smoke.py','scripts/native_1c_full_host.py'})
        raw=maximum_output()
        self.assertEqual(len(raw),6778)
        marker=dict(schema=PROFILE,nonce=NONCE,phase='completed',witness='client',values=raw.decode().splitlines())
        encoded=budget.wire(marker).replace(b'/',b'\\/')
        self.assertLessEqual(len(encoded)+encoded.count(b',')+encoded.count(b':')+3,16384)


class CopyAvailabilityTests(unittest.TestCase):
    def test_all_missing_methods_are_exportable_but_never_accepted_as_copy(self):
        missing=emit_missing_capture(); value,hashes,modules=success_envelope(missing)
        self.assertEqual(host.validate_envelope(budget.wire(value),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)[1],missing)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(strict=True);source=root/SPEC.source;source.parent.mkdir(parents=True)
            source.write_bytes((ROOT/SPEC.source).read_text(encoding='utf-8').encode())
            def runner(*a): return 0,missing,b''
            with budget.synthetic_inventory_reader():
                result=host.compare_output(root,root,missing,hashes,runner=runner,profile=PROFILE)
        self.assertEqual(result['status'],'matched')
        self.assertFalse(result['native_copy_available'])
        self.assertEqual(result['acceptance_status'],'rejected')

    def test_only_empty_english_and_valid_russian_controls_are_required(self):
        # Synthetic success is only used to exercise acceptance plumbing, not as native semantics.
        with mock.patch.object(BSLValueTree,'get_method',synthetic_method('deep')):
            successful=emit()
        missing=emit_missing_capture().splitlines(keepends=True); lines=successful.splitlines(keepends=True)
        for failed_case in range(1,10):
            candidate=lines.copy();candidate[failed_case+1]=missing[failed_case+1];raw=b''.join(candidate)
            hashes={SPEC.source:SPEC.source_sha256}
            with tempfile.TemporaryDirectory() as tmp, budget.synthetic_inventory_reader():
                root=Path(tmp).resolve(strict=True);source=root/SPEC.source;source.parent.mkdir(parents=True)
                source.write_bytes((ROOT/SPEC.source).read_text(encoding='utf-8').encode())
                result=host.compare_output(root,root,raw,hashes,runner=lambda *a:(0,raw,b''),profile=PROFILE)
            required=failed_case in (1,8)
            self.assertEqual(result['native_copy_available'],not required)
            self.assertEqual(result['acceptance_status'],'rejected' if required else 'accepted')

"""Synthetic ColumnsClear integration/bounds, never real-platform ColumnsClear answers."""
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
from test_native_tree_columns_clear_metadata_contract import maximum_output as maximum_observation_output

def maximum_output(status="S"):
    return maximum_observation_output(available=True, status=status)


from test_native_tree_columns_clear_metadata_measurement import emit

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE
PROFILE = 'tree-columns-clear-metadata-v1'


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
                output_sha256=full.digest(raw), output_size=len(raw), message_count=4)
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


class MetadataProfileTests(unittest.TestCase):
    def test_fixed_registry_and_dependencies(self):
        s=spec(); self.assertEqual((s.case,s.count,s.artifact),('tree_columns_clear_metadata',4,'tree-columns-clear-metadata'))
        self.assertEqual(full.digest((ROOT/s.source).read_text(encoding='utf-8').encode()),s.source_sha256)
        inventory=tree.input_files(profile=PROFILE)
        self.assertEqual(inventory,host.staged_files(smoke,profile=PROFILE)); self.assertEqual(len(inventory),23)
        self.assertIn('scripts/native_1c_tree_columns_clear_contract.py',inventory)
        self.assertIn('scripts/native_1c_tree_columns_clear_metadata_contract.py',inventory)
        for old in ('tree-v1','tree-copy-v1','tree-sort-v1','tree-columns-move-v1','tree-columns-move-boundary-v1','tree-columns-move-tail-v1','tree-columns-clear-v1','tree-columns-clear-lifetime-v1'):
            self.assertNotIn(s.source,tree.input_files(profile=old))
            self.assertNotIn('scripts/native_1c_tree_columns_clear_metadata_contract.py',tree.input_files(profile=old))

    def test_actual_producer_host_and_failure_paths(self):
        for state in ('success','unavailable','bad_setup','missing','invalid','nonquiet','bus','client','server'):
            with self.subTest(state=state):
                raw=maximum_output('M' if state=='unavailable' else 'S')
                if state=='bad_setup':raw=raw.replace(b'1ad9',b'1aa9')
                envelope,hashes,modules=success_envelope(raw);stage=envelope['report']['stage3']
                if state=='client': stage.update(status='failed',failure_kind='process_failed');stage['client_tree'].update(status='failed',failure_kind='process_failed',completed=False,witness_verified=False,**dict.fromkeys(host.FULL.CLIENT_OUTPUT_KEYS,None))
                if state=='server': stage.update(status='failed',failure_kind='process_failed',failed_case=spec().case);stage['cases'][0]['status']='failed'
                with tempfile.TemporaryDirectory() as tmp, synthetic_producer_reader(tree.full):
                    private=Path(tmp).resolve(strict=True);capture=private/'capture';capture.mkdir()
                    if state!='missing': (capture/(spec().case+'.out')).write_bytes(b'invalid' if state=='invalid' else raw)
                    tree.write_report(private/'stage3-report.json',stage,profile=PROFILE)
                    with mock.patch.object(full,'final_client_process_census'):
                        value=json.loads(tree.finish_report(bootstrap_report(),NONCE,capture,quiet=state!='nonquiet',bus_cleanup_failed=state=='bus',profile=PROFILE))
                    if state in ('success','unavailable','bad_setup'):
                        host.validate_envelope(budget.wire(value),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
                        source=private/spec().source;source.parent.mkdir(parents=True);source.write_bytes((ROOT/spec().source).read_text(encoding='utf-8').encode())
                        with budget.synthetic_inventory_reader():
                            comparison=host.compare_output(private,private,raw,hashes,runner=lambda *a:(0,raw,b''),profile=PROFILE)
                        self.assertEqual(comparison['acceptance_status'],'accepted' if state=='success' else 'rejected')
                        self.assertEqual(comparison['native_columns_clear_metadata_available'],state=='success')
                    else:
                        self.assertEqual(value['outputs'],[])
                        with self.assertRaises(host.TreeError): host.validate_envelope(budget.wire(value),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)

    def test_module_cold_staging_and_missing_basis(self):
        with tempfile.TemporaryDirectory() as tmp, budget.synthetic_inventory_reader():
            parent=Path(tmp).resolve(strict=True);checkout=parent/'checkout';stage=parent/'stage'
            for source in tree.input_files(profile=PROFILE):
                path=checkout/source;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((ROOT/source).read_text(encoding='utf-8').encode('utf-8'))
            hashes=host.stage_inputs(checkout,stage,smoke,profile=PROFILE)
            host.module_hashes(stage,hashes,smoke,profile=PROFILE)
            code='import sys;sys.path.insert(0,'+repr(str(stage/'bootstrap'))+');import tree_suite;import native_1c_tree_columns_clear_metadata_contract as c;c.require_available('+repr(maximum_output())+');print(c.MAX_ENCODED_BYTES)'
            result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,('1109'+os.linesep).encode('ascii'),b''))
            basis=stage/'bootstrap/native_1c_tree_columns_clear_contract.py';basis.unlink()
            result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'FileNotFoundError',result.stderr)
            with self.assertRaises(host.TreeError) as caught:
                host.module_hashes(stage,hashes,smoke,profile=PROFILE)
            self.assertEqual(str(caught.exception),'tree_inventory_invalid')

    def test_generated_client_capture_and_canonical_source_guard(self):
        source=(ROOT/spec().source).read_text(encoding='utf-8').encode()
        module=tree.client_module(source,(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode(),profile=PROFILE)
        vm=Interpreter();vm.execute(module.decode('utf-8-sig'));vm.execute('Result = ВычислитьПробу();')
        self.assertEqual(('\n'.join(vm.variables['result'].items)+'\n').encode(),emit())
        raw=maximum_output();hashes={spec().source:spec().source_sha256};runner=mock.Mock(return_value=(0,raw,b''))
        with tempfile.TemporaryDirectory() as tmp, budget.synthetic_inventory_reader():
            root=Path(tmp).resolve(strict=True);path=root/spec().source;path.parent.mkdir(parents=True)
            for bad in (source.replace(b'\n',b'\r\n'),source+b'\n'):
                path.write_bytes(bad)
                with self.assertRaises(host.TreeError): host.compare_output(root,root,raw,hashes,runner=runner,profile=PROFILE)
            runner.assert_not_called();path.write_bytes(source)
            self.assertEqual(host.compare_output(root,root,raw,hashes,runner=runner,profile=PROFILE)['acceptance_status'],'accepted')

    def test_actual_emitter_both_closed_sets_and_partial_repairs(self):
        import test_native_tree_emitter_dispatch as emitter
        finish=mock.Mock(return_value=b'fixed\n');raw,error=emitter.execute(emitter.arguments('columns-clear-metadata'),finish)
        self.assertEqual(raw,b'fixed\n');self.assertEqual(error.code,0);self.assertEqual(finish.call_args.kwargs['profile'],PROFILE)
        for lead in ('if tree_mode not in ', 'if tree_mode in '):
            line=next(line for line in emitter.EMITTER.splitlines() if line.startswith(lead))
            member=', "columns-clear-metadata"'
            self.assertEqual(line.count(member),1)
            changed=line.replace(member,'')
            self.assertNotEqual(changed,line)
            broken=emitter.EMITTER.replace(line,changed)
            self.assertNotEqual(broken,emitter.EMITTER)
            finish.reset_mock();raw,error=emitter.execute(emitter.arguments('columns-clear-metadata'),finish,broken)
            finish.assert_not_called()
        for args in (emitter.arguments('columns-clear-metadata')+['columns-clear'],emitter.arguments('columns-clear-metadata')+['columns-clear-metadata'],emitter.arguments('columns_clear_metadata')):
            finish.reset_mock();raw,error=emitter.execute(args,finish)
            self.assertIsInstance(error,ValueError);finish.assert_not_called();self.assertEqual(raw,b'')

    def test_cold_stage_diagnostic_stdout_uses_exact_platform_newline(self):
        from test_native_tree_columns_clear_profile import ColumnsClearProfileTests
        cases=((ColumnsClearProfileTests().test_actual_cold_stage_has_exact_twenty_two_sources_and_no_implicit_contract_dependency,b'12'),
               (self.test_module_cold_staging_and_missing_basis,b'1109'))
        real_run=subprocess.run
        for method,value in cases:
            for newline in ('\n','\r\n'):
                def run(*args,**kwargs):
                    command=list(args[0])
                    self.assertEqual(command[-2],'-c')
                    command[-1]='import sys;sys.stdout.reconfigure(newline='+repr(newline)+');'+command[-1]
                    return real_run(command,*args[1:],**kwargs)
                with self.subTest(value=value,newline=repr(newline)), mock.patch.object(subprocess,'run',side_effect=run), mock.patch.object(os,'linesep',newline):
                    method()

    def test_cold_stage_stdout_assertions_do_not_strip_or_ignore_failures(self):
        from test_native_tree_columns_clear_profile import ColumnsClearProfileTests
        cases=((ColumnsClearProfileTests().test_actual_cold_stage_has_exact_twenty_two_sources_and_no_implicit_contract_dependency,b'12'),
               (self.test_module_cold_staging_and_missing_basis,b'1109'))
        for method,value in cases:
            for newline in ('\n','\r\n'):
                expected=value+newline.encode('ascii')
                variants=((0,expected+b' ',b''),(0,expected+newline.encode('ascii'),b''),
                          (0,value,b''),(0,expected,b'warning'),(1,expected,b''),
                          (0,value+(b'\r\n' if newline=='\n' else b'\n'),b''))
                for code,stdout,stderr in variants:
                    result=subprocess.CompletedProcess([],code,stdout,stderr)
                    with self.subTest(value=value,newline=repr(newline),code=code,stdout=stdout,stderr=stderr), mock.patch.object(os,'linesep',newline), mock.patch.object(subprocess,'run',return_value=result), self.assertRaises(AssertionError):
                        method()

    def test_host_cli_rejects_unknown_and_duplicate_profile_before_any_work(self):
        options=(['--profile','tree-columns-clear-metadata-v2'],['--profile',PROFILE,'--profile',PROFILE],
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
            for extra in ('--tree-columns-clear-metadata-suite','--tree-suite','--tree-copy-suite','--tree-sort-suite','--client-probe','source.bsl'):
                self.assertEqual(run_stage.main(['--tree-columns-clear-metadata-suite','--invocation-nonce',NONCE,extra]),2)
            run.assert_not_called()
        for options in ({'tree_profile':PROFILE},{'tree_suite':True,'tree_profile':'tree-columns-clear-metadata-v2','full_nonce':NONCE},
                        {'tree_suite':True,'tree_profile':PROFILE,'full_nonce':NONCE,'client_probe':True}):
            with mock.patch.object(run_stage.uuid,'uuid4',side_effect=AssertionError('started')) as start:
                with self.assertRaises(run_stage.StageError): run_stage.run(**options)
                start.assert_not_called()

    @unittest.skipUnless(os.name=='posix','isolated staged imports')
    def test_completed_marker_strict_capture_limit(self):
        raw=maximum_observation_output();marker=dict(schema=PROFILE,nonce=NONCE,phase='completed',witness='client',values=raw.decode().splitlines())
        self.assertEqual(len(raw),1109)
        with tempfile.TemporaryDirectory() as tmp, synthetic_producer_reader(tree.full):
            path=Path(tmp).resolve(strict=True)/'marker.json';path.write_text(json.dumps(marker),encoding='utf-8')
            self.assertEqual(tree.client_marker(path,NONCE,'completed',profile=PROFILE),marker)
            for field,value in (('schema','tree-columns-clear-v1'),('nonce','0'*32),('witness','server')):
                bad=dict(marker);bad[field]=value;path.write_text(json.dumps(bad),encoding='utf-8')
                with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed',profile=PROFILE)
            path.write_bytes(b'x'*16385)
            with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed',profile=PROFILE)


if __name__=='__main__': unittest.main()

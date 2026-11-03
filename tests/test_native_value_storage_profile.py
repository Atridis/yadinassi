"""ValueStorage profile integration; synthetic wires are not native evidence."""
import base64
import contextlib
import io
import json
import re
import types
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
import test_native_tree_profile_budget as budget
from test_native_tree_profile_host import synthetic_producer_reader
from test_native_1c_smoke import bootstrap_report
from test_native_value_storage_measurement import emit, with_synthetic_case, wire

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE
PROFILE = 'value-storage-v1'
def spec(): return tree.profiles.select(PROFILE)
def output(): return emit()
def envelope(raw):
    s=spec(); hashes=dict.fromkeys(tree.input_files(profile=PROFILE),'a'*64);hashes[s.source]=s.source_sha256
    modules={s.case:'b'*64,'client_tree':'c'*64};stage=tree.empty_report(NONCE,profile=PROFILE)
    stage.update(status='ok',failure_kind='none',input_sha256=hashes)
    case=stage['cases'][0];case.update(status='ok',source_sha256=s.source_sha256,module_sha256=modules[s.case],output_sha256=full.digest(raw),output_size=len(raw),message_count=s.count)
    client=stage['client_tree'];client.update(status='ok',failure_kind='none',source_sha256=s.source_sha256,module_sha256=modules['client_tree'],roundtrip_sha256=modules['client_tree'],**dict.fromkeys(host.FULL.CLIENT_FLAGS,True),**{k:case[k] for k in host.FULL.CLIENT_OUTPUT_KEYS})
    client['process_diagnostics'].update(stage='after_exit',reason='none')
    with tempfile.TemporaryDirectory(prefix='value-storage-profile-') as tmp,synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
        parent=Path(tmp).resolve();capture=parent/'capture';capture.mkdir();(capture/(s.case+'.out')).write_bytes(raw)
        tree.write_report(parent/'stage3-report.json',stage,profile=PROFILE)
        encoded=tree.finish_report(bootstrap_report(),NONCE,capture,quiet=True,bus_cleanup_failed=False,profile=PROFILE)
    return encoded,hashes,modules

class ValueStorageProfileTests(unittest.TestCase):
    def test_closed_registry_and_exact_staging(self):
        s=spec();self.assertEqual((s.case,s.count,s.print_sites,s.artifact),('value_storage',27,5,'value-storage'))
        self.assertEqual(tree.input_files(profile=PROFILE),host.staged_files(smoke,profile=PROFILE))
        self.assertEqual(len(tree.input_files(profile=PROFILE)),22)
        self.assertNotIn(s.source,tree.input_files(profile='tree-v1'))
        with tempfile.TemporaryDirectory(prefix='value-storage-stage-') as tmp,budget.synthetic_inventory_reader():
            parent=Path(tmp).resolve();checkout=parent/'checkout';staged=parent/'staged'
            for source in tree.input_files(profile=PROFILE):
                p=checkout/source;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/source).read_text(encoding='utf-8').encode())
            hashes=host.stage_inputs(checkout,staged,smoke,profile=PROFILE)
            self.assertEqual(set(host.module_hashes(staged,hashes,smoke,profile=PROFILE)),{s.case,'client_tree'})
            code='import sys;sys.path.insert(0,'+repr(str(staged/'bootstrap'))+');import native_1c_value_storage_contract as c;c.require_available('+repr(output())+');print(c.MAX_ENCODED_BYTES)'
            result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,('823'+os.linesep).encode(),b''))
            (staged/'bootstrap/native_1c_value_storage_contract.py').unlink()
            with self.assertRaises(host.TreeError):host.module_hashes(staged,hashes,smoke,profile=PROFILE)

    def test_generated_client_moves_global_and_captures_helpers(self):
        source=(ROOT/spec().source).read_bytes()
        template=(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8')
        module=tree.client_module(source,template,profile=PROFILE).decode('utf-8-sig')
        declaration='&НаКлиенте\nПерем VSPhase;\n'
        self.assertEqual(module.count(declaration),1)
        self.assertLess(module.index(declaration),module.index('Процедура '))
        marker='\nСообщить("VS-C1: [wire-v1]");\n'
        original=source.decode('utf-8')
        pre=original[:original.index(marker)+1]
        expected=re.sub(r'(?m)^(Функция |Процедура )',r'&НаКлиенте\n\1',pre)
        expected=expected.replace('Перем VSPhase;\n','',1).replace('Сообщить(','TreeLaneCapture(')
        self.assertEqual(module.count(expected),1)
        inverse=re.sub(r'(?m)^&НаКлиенте\n(?=Функция |Процедура )','',expected)
        inverse=inverse.replace('TreeLaneCapture(','Сообщить(')
        position=pre.index('Перем VSPhase;\n')
        inverse=inverse[:position]+'Перем VSPhase;\n'+inverse[position:]
        self.assertEqual(inverse,pre)
        self.assertIn('Или Code = 124;',module)
        for bad in (source+b'\n',source.replace(b'\n',b'\r\n')):
            with self.assertRaises(full.FullError): tree.client_module(bad,template,profile=PROFILE)

    def test_real_observer_and_client_wrapper_synthetic_phase_failures(self):
        source=(ROOT/spec().source).read_bytes()
        template=(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8')
        server=[]
        Interpreter(server.append).execute(with_synthetic_case(source.decode('utf-8')))
        module=tree.client_module(source,template,profile=PROFILE).decode('utf-8-sig')
        vm=Interpreter(native_target=LINUX_8_3_27_1508)
        vm.execute(with_synthetic_case(module))
        vm.execute('Result = ВычислитьПробу();')
        client=vm.variables['result'].items
        self.assertEqual(client,server)
        self.assertIn('VS-09: [construct-error]',client)
        self.assertIn('VS-10: [inspect-error]',client)
        self.assertIn('VS-11: [observer-error]',client)
        self.assertIn('VS-12: [observer-error]',client)

    def test_real_envelope_validation_and_availability_not_equivalence(self):
        raw=output()
        encoded,hashes,modules=envelope(raw)
        _,observed=host.validate_envelope(encoded,NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        self.assertEqual(observed,raw)
        with tempfile.TemporaryDirectory(prefix='value-storage-compare-') as tmp,budget.synthetic_inventory_reader():
            root=Path(tmp).resolve();p=root/spec().source;p.parent.mkdir(parents=True);p.write_bytes((ROOT/spec().source).read_bytes())
            result=host.compare_output(root,root,raw,hashes,runner=lambda *args:(0,raw,b''),profile=PROFILE)
            self.assertTrue(result['native_value_storage_available'])
            self.assertEqual(result['acceptance_status'],'accepted')
        value=json.loads(encoded)
        for key in ('nonce','profile'):
            bad=dict(value);bad[key]='wrong'
            with self.assertRaises(host.TreeError):host.validate_envelope(budget.wire(bad),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        bad=json.loads(encoded);bad['report']['stage3']['client_tree']['quiet']=False
        with self.assertRaises(host.TreeError):host.validate_envelope(budget.wire(bad),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)

    def test_unavailable_rejected_from_both_contexts_to_export(self):
        candidates=(emit(missing=True),
                    output().replace(b'VS-09: [ok|ABCA]',b'VS-09: [observer-error]',1),
                    output().replace(b'VS-01: [ok|1]',b'VS-01: [ok|0]',1),
                    output().replace(b'VS-17: [ok|ABCA]',b'VS-17: [construct-error]',1),
                    output().replace(b'VS-22: [construct-error]',b'VS-22: [ok|1]',1))
        for unavailable in candidates:
            for site in ('server','client'):
                with self.subTest(site=site, witness=unavailable[:80]), self.assertRaises(tree.ObservationFailure) as failure:
                    tree.validate_observations(unavailable,site,profile=PROFILE)
                self.assertEqual(failure.exception.diagnostic['category'],'api_controls')
            encoded,hashes,modules=envelope(output())
            value=json.loads(encoded)
            digest=full.digest(unavailable)
            case=value['report']['stage3']['cases'][0]
            client=value['report']['stage3']['client_tree']
            case.update(output_sha256=digest,output_size=len(unavailable))
            client.update(output_sha256=digest,output_size=len(unavailable))
            value['outputs'][0].update(sha256=digest,size=len(unavailable),data_b64=base64.b64encode(unavailable).decode())
            forged=budget.wire(value)
            with self.assertRaises(host.TreeError) as rejected:
                host.validate_envelope(forged,NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
            self.assertEqual(rejected.exception.envelope_phase,'observation_contract')
            with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
                root=Path(directory)
                stack.enter_context(mock.patch.dict(os.environ,{'GHCR_TOKEN':'synthetic','GHCR_USER':'Atridis'}))
                stack.enter_context(mock.patch.object(host.uuid,'uuid4',return_value=types.SimpleNamespace(hex=NONCE)))
                for name,result in (('repository_provenance',{'sha':'a'*40}),('interpreter_provenance',{'source_sha256':'d'*64}),
                                    ('windows_fingerprints',{}),('read_regular',b'host'),('verify_client_interpreter',None)):
                    stack.enter_context(mock.patch.object(host.FULL,name,return_value=result))
                stack.enter_context(mock.patch.object(host,'stage_inputs',return_value=hashes))
                stack.enter_context(mock.patch.object(host,'module_hashes',return_value=modules))
                stack.enter_context(mock.patch.object(host,'validate_inputs'))
                stack.enter_context(mock.patch.object(host,'container_command',return_value=['container']))
                stack.enter_context(mock.patch.object(smoke,'run_silent'))
                stack.enter_context(mock.patch.object(smoke,'bounded_run',side_effect=[(0,b'linux/amd64|0'),(0,forged),(0,b'')]))
                original_sibling=host.sibling
                stack.enter_context(mock.patch.object(host,'sibling',side_effect=lambda name: smoke if name == 'native_1c_smoke' else original_sibling(name)))
                compare=stack.enter_context(mock.patch.object(host,'compare_output'))
                export=stack.enter_context(mock.patch.object(host,'export_artifact'))
                state={}
                with self.assertRaises(host.TreeError) as rejected:
                    host.run(root,root,export_native_outputs=True,failure_state=state,profile=PROFILE)
                self.assertEqual(rejected.exception.envelope_phase,'observation_contract')
                compare.assert_not_called();export.assert_not_called()
                self.assertEqual(state['stage'],'envelope')

    def test_runtime_mismatch_never_accepted(self):
        # Both observations are available, but the bytes disagree. The wire
        # contract does not choose a semantic answer for this mutation probe.
        native=output(); different=native.replace(b'VS-09: [ok|ABCA]',b'VS-09: [ok|ABBA]',1)
        wire.require_available(different)
        encoded,inputs,modules=envelope(native)
        with tempfile.TemporaryDirectory(prefix='value-storage-compare-') as tmp,budget.synthetic_inventory_reader():
            root=Path(tmp);p=root/spec().source;p.parent.mkdir(parents=True);p.write_bytes((ROOT/spec().source).read_bytes())
            result=host.compare_output(root,root,native,inputs,runner=lambda *args:(0,different,b''),profile=PROFILE)
        self.assertTrue(result['native_value_storage_available'])
        self.assertEqual(result['status'],'mismatched')
        self.assertEqual(result['acceptance_status'],'rejected')

    def test_matching_positive_failures_never_count_as_runtime_parity(self):
        for case in wire.POSITIVE_CASE_IDS:
            native = re.sub(rb'(VS-' + f'{case:02d}'.encode() + rb': \[)[^\n]+\]',
                            rb'\1construct-error]', output(), count=1)
            with tempfile.TemporaryDirectory(prefix='value-storage-unavailable-') as tmp,budget.synthetic_inventory_reader():
                root=Path(tmp);p=root/spec().source;p.parent.mkdir(parents=True);p.write_bytes((ROOT/spec().source).read_bytes())
                inputs={spec().source:spec().source_sha256}
                result=host.compare_output(root,root,native,inputs,runner=lambda *args:(0,native,b''),profile=PROFILE)
            self.assertEqual(result['status'],'matched')
            self.assertFalse(result['native_value_storage_available'])
            self.assertEqual(result['acceptance_status'],'rejected')

    def test_runtime_provenance_is_rechecked_before_export(self):
        raw=output();encoded,hashes,modules=envelope(raw)
        for changed in (False,True):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as directory,contextlib.ExitStack() as stack:
                root=Path(directory)
                stack.enter_context(mock.patch.dict(os.environ,{'GHCR_TOKEN':'synthetic','GHCR_USER':'Atridis'}))
                stack.enter_context(mock.patch.object(host.uuid,'uuid4',return_value=types.SimpleNamespace(hex=NONCE)))
                for name,result in (('repository_provenance',{'commit':'a'*40}),('windows_fingerprints',{}),
                                    ('read_regular',b'host'),('verify_client_interpreter',None)):
                    stack.enter_context(mock.patch.object(host.FULL,name,return_value=result))
                provenance=stack.enter_context(mock.patch.object(host.FULL,'interpreter_provenance',
                    side_effect=[{'source_sha256':'d'*64},{'source_sha256':('e' if changed else 'd')*64}]))
                stack.enter_context(mock.patch.object(host,'stage_inputs',return_value=hashes))
                stack.enter_context(mock.patch.object(host,'module_hashes',return_value=modules))
                stack.enter_context(mock.patch.object(host,'validate_inputs'))
                stack.enter_context(mock.patch.object(host,'container_command',return_value=['container']))
                stack.enter_context(mock.patch.object(smoke,'run_silent'))
                stack.enter_context(mock.patch.object(smoke,'bounded_run',side_effect=[(0,b'linux/amd64|0'),(0,encoded),(0,b'')]))
                original_sibling=host.sibling
                stack.enter_context(mock.patch.object(host,'sibling',side_effect=lambda name:smoke if name=='native_1c_smoke' else original_sibling(name)))
                stack.enter_context(mock.patch.object(host,'compare_output',return_value={'acceptance_status':'accepted'}))
                export=stack.enter_context(mock.patch.object(host,'export_artifact'))
                if changed:
                    with self.assertRaisesRegex(host.TreeError,'execution_provenance_changed'):
                        host.run(root,root,export_native_outputs=True,profile=PROFILE)
                    export.assert_not_called()
                else:
                    report=host.run(root,root,export_native_outputs=True,profile=PROFILE)
                    self.assertTrue(report['runtime_parity_accepted'])
                    self.assertEqual(report['interpreter']['source_sha256'],'d'*64)
                    export.assert_called_once()
                self.assertEqual(provenance.call_count,2)

    def test_client_server_evidence_tampering_is_rejected(self):
        encoded,hashes,modules=envelope(output())
        changes=[('source_sha256','e'*64),('module_sha256','e'*64),('roundtrip_sha256','e'*64),
                 ('output_sha256','e'*64),('output_size',1),('message_count',26),
                 ('message_count',True)]
        changes += [(flag,False) for flag in host.FULL.CLIENT_FLAGS]
        for key,value in changes:
            forged=json.loads(encoded);forged['report']['stage3']['client_tree'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(host.TreeError):
                host.validate_envelope(budget.wire(forged),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
        for key,value in (('source_sha256','e'*64),('module_sha256','e'*64),('message_count',26)):
            forged=json.loads(encoded);forged['report']['stage3']['cases'][0][key]=value
            with self.subTest(site='server',key=key),self.assertRaises(host.TreeError):
                host.validate_envelope(budget.wire(forged),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)

    def test_diagnostics_are_closed_and_profile_local(self):
        for validate,error in ((tree.validate_diagnostic,full.FullError),(host.validate_diagnostic,host.TreeError)):
            validate(None,profile=PROFILE)
            for site in ('server','client'):
                for category in ('record_count','api_controls'):
                    valid=dict(site=site,case=None,category=category,calibration=None)
                    validate(valid,profile=PROFILE)
                    mutations=[dict(valid,site='unknown'),dict(valid,case=18),dict(valid,category='private'),
                               dict(valid,calibration='X'),dict(valid,extra='private'),{},[],False]
                    for bad in mutations:
                        with self.subTest(bad=bad),self.assertRaises(error): validate(bad,profile=PROFILE)
                    for legacy in ('format-numbers-v1','format-dates-v1'):
                        if category == 'record_count': validate(valid,profile=legacy)
                        else:
                            with self.assertRaises(error): validate(valid,profile=legacy)

    def test_format_profiles_keep_original_source_and_contract(self):
        import hashlib
        expected=(('format-numbers-v1','format_numbers',50,
                   'a7f8e3c6105d4a7f28ef08a0865abcf01f7465f236fffe189c2da7272df04d84',
                   'a0297b354bebde983f48c86f6895ecc139f5cbfb3cf51723434b0f560178eb19'),
                  ('format-dates-v1','format_dates',58,
                   '7fbdcca1257bc6d754fd8a640f3ed4790196db12b8c61be2a8a88f93ee5adccb',
                   '41c8b62264e4588d2f3dc7170eff736f14aede530752220bb197c3735951af65'))
        for name,case,count,source_sha,contract_sha in expected:
            legacy=tree.profiles.select(name)
            self.assertEqual((legacy.case,legacy.count,legacy.source_sha256),(case,count,source_sha))
            self.assertEqual(hashlib.sha256((ROOT/legacy.source).read_bytes()).hexdigest(),source_sha)
            contract=(ROOT/'scripts'/(legacy.contract+'.py')).read_text(encoding='utf-8').encode('utf-8')
            self.assertEqual(hashlib.sha256(contract).hexdigest(),contract_sha)
            self.assertNotIn(spec().source,tree.input_files(profile=name))
            self.assertNotIn('scripts/native_1c_value_storage_contract.py',tree.input_files(profile=name))
            module=tree.client_module((ROOT/legacy.source).read_bytes(),
                (ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8'),profile=name)
            self.assertNotIn(b'VSPhase',module)

    def test_emitter_closed_dispatch_and_bad_flags(self):
        import test_native_tree_emitter_dispatch as emitter
        import run_stage
        finish=mock.Mock(return_value=b'fixed\n');raw,error=emitter.execute(emitter.arguments('value-storage'),finish)
        self.assertEqual((raw,error.code),(b'fixed\n',0));self.assertEqual(finish.call_args.kwargs['profile'],PROFILE)
        for lead in ('if tree_mode not in ','if tree_mode in '):
            line=next(line for line in emitter.EMITTER.splitlines() if line.startswith(lead));member=', "value-storage"';self.assertEqual(line.count(member),1)
            finish.reset_mock();emitter.execute(emitter.arguments('value-storage'),finish,emitter.EMITTER.replace(line,line.replace(member,'')))
            finish.assert_not_called()
        with tempfile.TemporaryDirectory(prefix='value-storage-stage-dispatch-') as tmp, mock.patch.object(run_stage,'ROOT',Path(tmp)), mock.patch.object(run_stage,'run',return_value=run_stage.empty_report()) as run, contextlib.redirect_stdout(io.StringIO()):
            run_stage.main(['--value-storage-suite','--invocation-nonce',NONCE])
            run.assert_called_once()
            self.assertTrue(run.call_args.kwargs['tree_suite'])
            self.assertEqual(run.call_args.kwargs['tree_profile'],PROFILE)
            self.assertEqual(run.call_args.kwargs['full_nonce'],NONCE)
        with mock.patch.object(run_stage,'run') as run:
            for extra in ('--value-storage-suite','--tree-suite','--client-probe','source.bsl'):
                self.assertEqual(run_stage.main(['--value-storage-suite','--invocation-nonce',NONCE,extra]),2)
            run.assert_not_called()
        for flags in (['--profile','value-storage-v2'],['--profile',PROFILE,'--profile',PROFILE]):
            with mock.patch.object(host,'run') as run,mock.patch.object(sys,'argv',['host','--execute-approved-image']+flags),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:host.main()
            self.assertEqual(error.exception.code,2);run.assert_not_called()

    def test_complete_rectangular_budgets_and_workflow(self):
        s=spec();stage=budget.stage_majorant();stage.update(schema=s.stage_schema,profile=PROFILE,failed_case=s.case,input_sha256=dict.fromkeys(tree.input_files(profile=PROFILE),budget.H));stage['cases'][0]['name']=s.case
        native=budget.native_majorant();native['stage3']=stage
        report=budget.host_majorant();report.update(profile=PROFILE,trusted_input_sha256=stage['input_sha256'],native_report=native)
        report['host_source_sha256']['scripts/native_1c_value_storage_contract.py']=budget.H
        report['comparison'].update(profile=PROFILE,native_value_storage_available=False)
        report['observation_diagnostic']=stage['observation_diagnostic'];report['status']='failed'
        provenance=budget.wire(report)+b'\n';report['native_artifact_sha256']=dict.fromkeys((s.case+'.out','provenance.json'),budget.H)
        transport=dict(schema=s.schema,profile=PROFILE,nonce=NONCE,report=native,outputs=[dict(name=s.case+'.out',size=8192,sha256=budget.H,data_b64=base64.b64encode(b'x'*8192).decode())])
        bounds={'stage':len(budget.wire(stage)),'native':len(budget.wire(native)),'transport':len(budget.wire(transport))+1,'host':len(budget.wire(report))+1,'provenance':len(provenance)}
        for key,cap in (('stage',8192),('native',32768),('transport',65536),('host',32768),('provenance',32768)):self.assertLessEqual(bounds[key],cap,(key,bounds))
        workflow=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text()
        self.assertEqual(workflow.count('- profile: '+PROFILE),1)
        self.assertIn('artifact: value-storage\n            case: value_storage',workflow)

if __name__=='__main__':unittest.main()

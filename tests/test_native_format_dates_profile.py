"""Format profile integration uses synthetic outputs, never real-platform answers."""
import base64
import contextlib
import io
import json
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
from test_native_format_dates_measurement import emit

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE
PROFILE = 'format-dates-v1'
def spec(): return tree.profiles.select(PROFILE)
def output(): return emit(lambda *args:'x'*32)
def envelope(raw):
    s=spec(); hashes=dict.fromkeys(tree.input_files(profile=PROFILE),'a'*64);hashes[s.source]=s.source_sha256
    modules={s.case:'b'*64,'client_tree':'c'*64};stage=tree.empty_report(NONCE,profile=PROFILE)
    stage.update(status='ok',failure_kind='none',input_sha256=hashes)
    case=stage['cases'][0];case.update(status='ok',source_sha256=s.source_sha256,module_sha256=modules[s.case],output_sha256=full.digest(raw),output_size=len(raw),message_count=s.count)
    client=stage['client_tree'];client.update(status='ok',failure_kind='none',source_sha256=s.source_sha256,module_sha256=modules['client_tree'],roundtrip_sha256=modules['client_tree'],**dict.fromkeys(host.FULL.CLIENT_FLAGS,True),**{k:case[k] for k in host.FULL.CLIENT_OUTPUT_KEYS})
    client['process_diagnostics'].update(stage='after_exit',reason='none')
    with tempfile.TemporaryDirectory(prefix='format-profile-') as tmp,synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
        parent=Path(tmp).resolve();capture=parent/'capture';capture.mkdir();(capture/(s.case+'.out')).write_bytes(raw)
        tree.write_report(parent/'stage3-report.json',stage,profile=PROFILE)
        encoded=tree.finish_report(bootstrap_report(),NONCE,capture,quiet=True,bus_cleanup_failed=False,profile=PROFILE)
    return encoded,hashes,modules

class FormatProfileTests(unittest.TestCase):
    def test_closed_registry_and_exact_staging(self):
        s=spec();self.assertEqual((s.case,s.count,s.print_sites,s.artifact),('format_dates',30,5,'format-dates'))
        self.assertEqual(tree.input_files(profile=PROFILE),host.staged_files(smoke,profile=PROFILE))
        self.assertEqual(len(tree.input_files(profile=PROFILE)),22)
        self.assertNotIn(s.source,tree.input_files(profile='tree-v1'))
        with tempfile.TemporaryDirectory(prefix='format-stage-') as tmp,budget.synthetic_inventory_reader():
            parent=Path(tmp).resolve();checkout=parent/'checkout';staged=parent/'staged'
            for source in tree.input_files(profile=PROFILE):
                p=checkout/source;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/source).read_text(encoding='utf-8').encode())
            hashes=host.stage_inputs(checkout,staged,smoke,profile=PROFILE)
            self.assertEqual(set(host.module_hashes(staged,hashes,smoke,profile=PROFILE)),{s.case,'client_tree'})
            code='import sys;sys.path.insert(0,'+repr(str(staged/'bootstrap'))+');import native_1c_format_dates_contract as c;c.require_available('+repr(output())+');print(c.MAX_ENCODED_BYTES)'
            result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,('4110'+os.linesep).encode(),b''))
            (staged/'bootstrap/native_1c_format_dates_contract.py').unlink()
            with self.assertRaises(host.TreeError):host.module_hashes(staged,hashes,smoke,profile=PROFILE)

    def test_generated_client_captures_helpers_and_utf16(self):
        source=(ROOT/spec().source).read_text(encoding='utf-8').encode()
        module=tree.client_module(source,(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode(),profile=PROFILE)
        for witness in (None,lambda *args:' \u00a0\U0001f600',lambda *args:'x'*32,lambda *args:42):
            vm=Interpreter(native_target=LINUX_8_3_27_1508)
            if witness:
                vm.register_function('Format',witness);vm.register_function('Формат',witness)
            vm.execute(module.decode('utf-8-sig'));vm.execute('Result = ВычислитьПробу();')
            self.assertEqual(('\n'.join(vm.variables['result'].items)+'\n').encode(),emit(witness))
        for bad in (source+b'\n',source.replace(b'\n',b'\r\n')):
            with self.assertRaises(full.FullError):tree.client_module(bad,(ROOT/full.CLIENT_SOURCE).read_bytes(),profile=PROFILE)

    def test_real_envelope_validation_and_availability_not_equivalence(self):
        for available,raw in ((True,output()),(False,emit(missing=True))):
            encoded,hashes,modules=envelope(raw)
            _,observed=host.validate_envelope(encoded,NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
            self.assertEqual(observed,raw)
            with tempfile.TemporaryDirectory(prefix='format-compare-') as tmp,budget.synthetic_inventory_reader():
                root=Path(tmp).resolve();p=root/spec().source;p.parent.mkdir(parents=True);p.write_bytes((ROOT/spec().source).read_text(encoding='utf-8').encode())
                result=host.compare_output(root,root,raw,hashes,runner=lambda *args:(0,raw,b''),profile=PROFILE)
                self.assertEqual(result['native_format_dates_available'],available)
                self.assertEqual(result['acceptance_status'],'accepted' if available else 'rejected')
                self.assertEqual(result['status'],'matched')
            value=json.loads(encoded)
            for key in ('nonce','profile'):
                bad=dict(value);bad[key]='wrong'
                with self.assertRaises(host.TreeError):host.validate_envelope(budget.wire(bad),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)
            bad=json.loads(encoded);bad['report']['stage3']['client_tree']['quiet']=False
            with self.assertRaises(host.TreeError):host.validate_envelope(budget.wire(bad),NONCE,hashes,modules,smoke.validate_report,profile=PROFILE)

    def test_emitter_closed_dispatch_and_bad_flags(self):
        import test_native_tree_emitter_dispatch as emitter
        import run_stage
        finish=mock.Mock(return_value=b'fixed\n');raw,error=emitter.execute(emitter.arguments('format-dates'),finish)
        self.assertEqual((raw,error.code),(b'fixed\n',0));self.assertEqual(finish.call_args.kwargs['profile'],PROFILE)
        for lead in ('if tree_mode not in ','if tree_mode in '):
            line=next(line for line in emitter.EMITTER.splitlines() if line.startswith(lead));member=', "format-dates"';self.assertEqual(line.count(member),1)
            finish.reset_mock();emitter.execute(emitter.arguments('format-dates'),finish,emitter.EMITTER.replace(line,line.replace(member,'')))
            finish.assert_not_called()
        with tempfile.TemporaryDirectory(prefix='format-stage-dispatch-') as tmp, mock.patch.object(run_stage,'ROOT',Path(tmp)), mock.patch.object(run_stage,'run',return_value=run_stage.empty_report()) as run, contextlib.redirect_stdout(io.StringIO()):
            run_stage.main(['--format-dates-suite','--invocation-nonce',NONCE])
            run.assert_called_once()
            self.assertTrue(run.call_args.kwargs['tree_suite'])
            self.assertEqual(run.call_args.kwargs['tree_profile'],PROFILE)
            self.assertEqual(run.call_args.kwargs['full_nonce'],NONCE)
        with mock.patch.object(run_stage,'run') as run:
            for extra in ('--format-dates-suite','--tree-suite','--client-probe','source.bsl'):
                self.assertEqual(run_stage.main(['--format-dates-suite','--invocation-nonce',NONCE,extra]),2)
            run.assert_not_called()
        for flags in (['--profile','format-dates-v2'],['--profile',PROFILE,'--profile',PROFILE]):
            with mock.patch.object(host,'run') as run,mock.patch.object(sys,'argv',['host','--execute-approved-image']+flags),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:host.main()
            self.assertEqual(error.exception.code,2);run.assert_not_called()

    def test_complete_rectangular_budgets_and_workflow(self):
        s=spec();stage=budget.stage_majorant();stage.update(schema=s.stage_schema,profile=PROFILE,failed_case=s.case,input_sha256=dict.fromkeys(tree.input_files(profile=PROFILE),budget.H));stage['cases'][0]['name']=s.case
        native=budget.native_majorant();native['stage3']=stage
        report=budget.host_majorant();report.update(profile=PROFILE,trusted_input_sha256=stage['input_sha256'],native_report=native)
        report['host_source_sha256']['scripts/native_1c_format_dates_contract.py']=budget.H
        report['comparison'].update(profile=PROFILE,native_format_dates_available=False)
        report['observation_diagnostic']=stage['observation_diagnostic'];report['status']='failed'
        provenance=budget.wire(report)+b'\n';report['native_artifact_sha256']=dict.fromkeys((s.case+'.out','provenance.json'),budget.H)
        transport=dict(schema=s.schema,profile=PROFILE,nonce=NONCE,report=native,outputs=[dict(name=s.case+'.out',size=8192,sha256=budget.H,data_b64=base64.b64encode(b'x'*8192).decode())])
        bounds={'stage':len(budget.wire(stage)),'native':len(budget.wire(native)),'transport':len(budget.wire(transport))+1,'host':len(budget.wire(report))+1,'provenance':len(provenance)}
        for key,cap in (('stage',8192),('native',32768),('transport',65536),('host',32768),('provenance',32768)):self.assertLessEqual(bounds[key],cap,(key,bounds))
        workflow=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text()
        self.assertEqual(workflow.count('- profile: '+PROFILE),1)
        self.assertIn('artifact: format-dates\n            case: format_dates',workflow)

if __name__=='__main__':unittest.main()

"""Synthetic offline contracts, never native dialog evidence."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import dialog_packet as packet
from dialog_packet import route


def records():
    return ''.join(f'DG{i}=1;{code};1;start,returned,callback,finish,|' for i,code in enumerate(('ok','cancel','no','cancel','warning','timeout'),1)).encode()


class DialogNativeTests(unittest.TestCase):
    def test_five_source_hashes(self):
        files=packet.packet();self.assertEqual(len(files),5)
        self.assertEqual({n:hashlib.sha256(v).hexdigest() for n,v in files.items()},packet.PACKET_HASHES)

    def test_authored_source_binding(self):
        self.assertEqual(route.validate_redump(route.sources()),route.module_digest())

    def test_executable_redump_not_xml_spelling(self):
        files={name:route.sources()[name] for name in route.EXECUTABLE_MODULES}
        self.assertEqual(len(files),2)
        self.assertEqual(route.validate_executable_redump(files),route.module_digest())
        files[route.MODULES[0]]+=b'bad'
        with self.assertRaises(ValueError):route.validate_executable_redump(files)

    def test_six_bounded_records(self):
        self.assertEqual(len(packet.require_available(packet.parse_records(records()))),6)
        self.assertLess(len(records()),packet.MAX_OUTPUT)

    def test_records_reject_unknown_and_duplicate(self):
        for raw in (records().replace(b';ok;',b';private;'),records()+records(),b'x'*4097):
            with self.assertRaises(ValueError):packet.parse_records(raw)

    def test_recorded_result_is_not_expected_native_golden(self):
        self.assertEqual(packet.parse_records(records().replace(b';timeout;',b';other;'))[-1][0],'other')

    def test_callback_arity_and_native_only_invocation(self):
        s=route.module().decode()
        self.assertIn('Procedure QuestionDone(Result, AdditionalParameters) Export',s)
        self.assertIn('Procedure WarningDone(AdditionalParameters) Export',s)
        for name in ('QuestionDone','WarningDone'):
            self.assertNotIn(name+'(',s.replace('Procedure '+name+'(',''))
        self.assertNotIn('RunCallback(',s)

    def test_four_modes_and_omitted_timeout_button(self):
        s=route.module().decode()
        for mode in ('OK','OKCancel','YesNo','YesNoCancel'):self.assertIn('QuestionDialogMode.'+mode,s)
        self.assertIn('QuestionDialogMode.YesNo, 1);',s)
        self.assertIn('ShowMessageBox(',s)
        self.assertNotIn('ShowWarning(',s);self.assertNotIn('ShowQuestion(',s)

    def test_client_state_and_bounded_watchdog(self):
        s=route.module().decode()
        self.assertIn('&AtClient\nVar Flow',s)
        self.assertIn('Turns < 15',s);self.assertIn('Flow > 6',s)
        self.assertIn('AttachIdleHandler("ObserveDialog", 1, True)',s)

    def test_no_next_dialog_inside_callback(self):
        s=route.module().decode()
        for name in ('QuestionDone','WarningDone'):
            body=s.split('Procedure '+name+'(',1)[1].split('EndProcedure',1)[0]
            self.assertNotIn('NextDialog(',body);self.assertNotIn('ShowQueryBox(',body)

    def test_exact_workflow_route(self):
        s=(ROOT/'.github/workflows/native-1c-dialogs.yml').read_text()
        self.assertIn('codex/configuration-dialogs',s)
        self.assertIn('native_1c_dialogs_profile.py --execute-approved-image --export-native-outputs',s)
        self.assertNotIn('workflow_dispatch:',s);self.assertNotIn('pull_request_target:',s)
        self.assertLess(s.index('native_1c_ci_policy.py bind'),s.index('GHCR_TOKEN:'))

    def test_dedicated_selector(self):
        s=(ROOT/'scripts/native_1c_dialogs_probe.sh').read_text()
        self.assertIn('[ "$1" = --dialogs-suite ] && [ "$2" = --invocation-nonce ] || exit 2',s)
        t=(ROOT/'scripts/native_1c_bootstrap/run_dialogs_stage.py').read_text()
        self.assertIn("if len(arguments)!=3 or arguments[0]!='--dialogs-suite':return 2",t)

    def test_envelope_with_real_host_and_suite(self):
        with mock.patch.object(sys,'path',[str(ROOT/'scripts/native_1c_bootstrap'),*sys.path]):
            import dialogs_suite as suite
            import native_1c_dialogs_profile as host
            from test_native_1c_smoke import bootstrap_report
        self.assertEqual(host.staged_files(),suite.INPUT_FILES)
        self.assertEqual(host.PROFILE,suite.PROFILE)
        nonce='a'*32;raw=records();hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in suite.INPUT_FILES}
        stage=suite.empty_report(nonce)
        stage.update(status='ok',failure_kind='none',failure_phase='final',input_sha256=hashes,
            source_sha256=packet.SOURCE_SHA256,form_sha256=packet.FORM_SHA256,
            module_sha256=route.module_digest(),roundtrip_sha256=route.module_digest(),
            output_sha256=hashlib.sha256(raw).hexdigest(),output_size=len(raw),record_count=6)
        for key in host.FLAGS:stage[key]=True
        stage['process_diagnostics'].update(stage='after_exit',reason='none')
        report=bootstrap_report();report.update(native_tests_completed=True,stage3=stage)
        value={'schema':suite.SCHEMA,'profile':suite.PROFILE,'nonce':nonce,'report':report,'outputs':[
            {'name':'dialogs.out','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'data_b64':base64.b64encode(raw).decode()}]}
        self.assertEqual(host.validate_envelope(json.dumps(value).encode(),nonce,hashes)[1],raw)

    def test_host_isolation_and_parity_limit(self):
        s=(ROOT/'scripts/native_1c_dialogs_profile.py').read_text()
        for v in ("'--network', 'none'","'--read-only'","'--cap-drop', 'ALL'","'runtime_parity_accepted':False","'acceptance_status':'not_evaluated'"):self.assertIn(v,s)

    def test_source_and_epf_witnesses(self):
        s=(ROOT/'scripts/native_1c_bootstrap/dialogs_suite.py').read_text()
        self.assertEqual(s.count('full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))!=epf_digest'),2)
        self.assertIn('route.validate_executable_redump(dumped_files)',s)
        self.assertGreaterEqual(s.count('route.validate_redump(_dump_files(src))'),3)

"""Explicit observation mode; all bytes here are synthetic, never native facts.

No test in this module creates the fixed native database path or launches 1C.
"""
from __future__ import annotations
import ast
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_client_probe as probe
from test_native_directive_witness import linux_fixture
from test_native_1c_full_host import SyntheticFilesystemCase
from infobase_preflight_test_support import offline_fixture

full, suite, smoke, ROOT, NONCE = probe.full, probe.suite, probe.smoke, probe.ROOT, probe.NONCE
TOKEN = 'pp.v1:' + '511000' * 5  # Deliberately unequal aliases; syntax witness only.
CORE = 'integrational_tests/directive_probes/preprocessor_profiles_core.bsl'


def marker(phase='completed', token=TOKEN):
    value = probe.marker(phase)
    if phase == 'completed':
        value['values'] = full.CLIENT_RUNTIME_VALUES + [token]
    return value


class ProfileObservationMarkerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name).resolve() / 'marker.json'
        if os.name == 'nt':
            reader = mock.patch.object(suite, 'secure_bytes', new=probe.stage_fixture.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def read(self, value, *, phase='completed', source=None):
        self.path.write_bytes(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode())
        return suite.preprocessor_client_marker(self.path, NONCE, phase,
            source_hash=source or full.PREPROCESSOR_SOURCE_SHA256)

    def test_all512_masks_at_all_ten_positions_and_independent_aliases(self):
        for position in range(10):
            for mask in range(512):
                parts = ['000'] * 10; parts[position] = f'{mask:03}'
                token = 'pp.v1:' + ''.join(parts)
                self.assertEqual(full.validate_preprocessor_profile(token), token)
                self.assertEqual(suite.validate_preprocessor_profile(token), token)
                self.assertEqual(len(token.encode('ascii')), 36)
        self.assertEqual(self.read(marker())['values'][-1], TOKEN)
        self.assertEqual(self.read(marker('entered'), phase='entered'), marker('entered'))

    def test_full137_prefix_types_and_every_slot_remain_strict(self):
        for index, expected in enumerate(full.CLIENT_RUNTIME_VALUES):
            value = marker(); value['values'][index] = None
            with self.subTest(index=index), self.assertRaises(suite.FullError): self.read(value)
            if type(expected) is int:
                value['values'][index] = float(expected)
                with self.assertRaises(suite.FullError): self.read(value)
        for values in (full.CLIENT_RUNTIME_VALUES, full.CLIENT_RUNTIME_VALUES + [TOKEN, TOKEN], []):
            value = marker(); value['values'] = values
            with self.assertRaises(suite.FullError): self.read(value)

    def test_invalid_tokens_schema_identity_and_bounds(self):
        for token in (None, True, 36, '', TOKEN[:-1], TOKEN+' ', TOKEN.replace('5','５',1),
                      'pp.v1:'+'512'*10, 'pp.v2:'+'000'*10, 'pp.v1:'+'-01'*10):
            with self.subTest(token=token), self.assertRaises(suite.FullError): self.read(marker(token=token))
        for patch in ({'schema':True}, {'nonce':'0'*32}, {'witness':'server'}, {'phase':'error'}, {'extra':'PRIVATE'}):
            value=marker();value.update(patch)
            with self.assertRaises(suite.FullError): self.read(value)
        for source in (full.INFOBASE_CONTEXT_SOURCE_SHA256, '0'*64):
            with self.assertRaises(suite.FullError): self.read(marker(),source=source)
        self.path.write_bytes(b' '*2049)
        with self.assertRaises(suite.FullError):
            suite.preprocessor_client_marker(self.path, NONCE, 'completed', source_hash=full.PREPROCESSOR_SOURCE_SHA256)
        raw=json.dumps(marker(),separators=(',',':')).encode()
        for value in (raw.replace(b'"schema":1',b'"schema":1,"schema":1'),raw+b' PRIVATE',raw.replace(b'42,',b'NaN,')):
            self.path.write_bytes(value)
            with self.assertRaises(suite.FullError):
                suite.preprocessor_client_marker(self.path,NONCE,'completed',source_hash=full.PREPROCESSOR_SOURCE_SHA256)

    def test_old_strict_readers_reject_all138_observation_markers(self):
        self.read(marker())
        with self.assertRaises(suite.FullError): suite.client_marker(self.path, NONCE, 'completed')
        with self.assertRaises(suite.FullError):
            suite.infobase_client_marker(self.path,NONCE,'completed',source_hash=full.INFOBASE_CONTEXT_SOURCE_SHA256)

    def test_finite_diagnostics_include138_count_without_token_or_native_text(self):
        for token in (TOKEN, 'pp.v1:'+'999'*10):
            value=marker(token=token);value['values'].append('PRIVATE');self.read_raw(value)
            result=suite.client_marker_diagnostics(self.path,NONCE,infobase_required=True,preprocessor_required=True)
            full.validate_marker_diagnostics(result,preprocessor_measurement=True)
            self.assertNotIn(token,json.dumps(result));self.assertNotIn('PRIVATE',json.dumps(result))
            self.assertEqual(result['ordinal'],138 if token == TOKEN else 137)

    def read_raw(self,value): self.path.write_bytes(json.dumps(value,separators=(',',':')).encode())


class ProfileObservationSourceTests(SyntheticFilesystemCase):
    def test_literal_core_and_whole_source_bindings(self):
        source=linux_fixture(ROOT/full.CLIENT_SOURCE);core=linux_fixture(ROOT/CORE)
        self.assertEqual(full.digest(source),full.PREPROCESSOR_SOURCE_SHA256)
        self.assertEqual(full.digest(full.generated_module(source)),full.PREPROCESSOR_MODULE_SHA256)
        self.assertEqual(core,full.PREPROCESSOR_CORE);self.assertEqual(core,suite.PREPROCESSOR_CORE)
        self.assertEqual(full.digest(core),full.PREPROCESSOR_CORE_SHA256)
        legacy=full.preprocessor_shared_source(source)
        self.assertEqual(legacy,suite.preprocessor_shared_source(source))
        self.assertEqual(full.digest(legacy),full.INFOBASE_CONTEXT_SOURCE_SHA256)
        for raw in (source+b'\n',source.replace(full.PREPROCESSOR_CALL,b''),source.replace(core,core+core),source[:-1]):
            for module in (full,suite):
                with self.assertRaises(module.FullError): module.preprocessor_shared_source(raw)
        text=core.decode();self.assertEqual(text.count('EnglishMask = 0;'),4)
        self.assertEqual(text.count('RussianMask = 0;'),4)
        for name in ('Client','Server','AtClient','AtServer','ThinClient','WebClient',
                     'ThickClientOrdinaryApplication','ThickClientManagedApplication','ExternalConnection'):
            self.assertEqual(text.count('#If '+name+' Then'),4)
        self.assertNotIn('Execute(',text);self.assertNotIn('InfoBaseConnectionString',text)

    def test_exact_source138_preflight_default_expectation_and_strict_mode_rejection(self):
        raw=linux_fixture(ROOT/full.CLIENT_SOURCE)
        with tempfile.TemporaryDirectory() as folder, offline_fixture(full):
            path=Path(folder).resolve()/'candidate.bsl';path.write_bytes(raw);seen=[]
            def runner(arguments,cwd):
                self.assertEqual(Path(arguments[-2]),path);self.assertEqual(path.read_bytes(),raw)
                self.assertIn('FileDBContext',full.CLIENT_EXECUTE_SCRIPT)
                self.assertNotIn('preprocessor_shared_source',full.CLIENT_EXECUTE_SCRIPT)
                seen.append(True)
                return 0,json.dumps(full.CLIENT_RUNTIME_VALUES+[full.PREPROCESSOR_DEFAULT_TOKEN],ensure_ascii=False,separators=(',',':')).encode(),b''
            full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,runner=runner,preprocessor_measurement=True)
            self.assertEqual(seen,[True])
            with self.assertRaises(full.FullError):
                full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,runner=runner)
            for values in (full.CLIENT_RUNTIME_VALUES,full.CLIENT_RUNTIME_VALUES+[TOKEN]):
                with self.assertRaises(full.FullError):
                    full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,preprocessor_measurement=True,
                        runner=lambda *args:(0,json.dumps(values,ensure_ascii=False,separators=(',',':')).encode(),b''))
            def mutator(arguments,cwd):
                result=runner(arguments,cwd);path.write_bytes(raw+b'\n');return result
            with self.assertRaises(full.FullError):
                full.verify_client_interpreter(ROOT,path,full.PREPROCESSOR_SOURCE_SHA256,runner=mutator,preprocessor_measurement=True)

    def test_preserved_adapters_async_identity_and_manifest(self):
        source=linux_fixture(ROOT/full.CLIENT_SOURCE)
        plan=json.loads((ROOT/'integrational_tests/directive_probes/infobase_context_measurement.json').read_text())
        for name,expected in plan['four_adapter_sha256'].items():
            actual=getattr(suite,'client_'+name+'_module')(linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl'),source)
            self.assertEqual(full.digest(actual),expected)
        self.assertEqual(full.async_source_identity(linux_fixture(ROOT/'scripts/native_1c_bootstrap/full_suite.py')),plan['async8_identity'])
        new=json.loads((ROOT/'integrational_tests/directive_probes/preprocessor_profiles_measurement.json').read_text())
        self.assertIsNone(new['native_expected_token']);self.assertFalse(new['native_suffix_parity_claimed'])
        self.assertEqual(new['source_sha256'],full.PREPROCESSOR_SOURCE_SHA256)
        self.assertEqual(len(suite.INPUT_FILES)+1,24)
        self.assertEqual(full.WINDOWS_TARGET,'windows-8.3.27.2342')


class ProfileObservationHarnessTests(unittest.TestCase):
    def setUp(self):
        # Existing helper intentionally initializes strict136. Only fixture setup
        # uses the historical inverse; production current-source admission never does.
        self.fixture=probe.ClientProbeHarness();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);f=self.fixture
        (f.inputs/suite.CLIENT_TARGET).write_bytes(linux_fixture(ROOT/full.CLIENT_SOURCE))
        f.hashes=suite.input_hashes(f.inputs,client_probe=True)
        f.platform=replace(f.platform,database=Path('/tmp/onec-smoke/db'))
        def tail(mode):
            if mode=='enterprise' and 'completed' in f.run_markers:
                (f.work/'completed.json').write_bytes(json.dumps(marker(),separators=(',',':')).encode())
        self.tail=tail;f.hook=tail

    def test_producer_observation_is_explicit_and_bound(self):
        f=self.fixture;record=f.run_probe(preprocessor_measurement=True)
        self.assertEqual(record['status'],'ok');self.assertEqual(record['preprocessor_profile'],TOKEN)
        self.assertEqual(record['infobase_context'],full.INFOBASE_CONTEXT_EXPECTED_TOKEN)
        full.validate_client_probe(record,full.PREPROCESSOR_SOURCE_SHA256,full.PREPROCESSOR_MODULE_SHA256,
                                  infobase_allowed=True,preprocessor_allowed=True)
        with self.assertRaises(ValueError):
            full.validate_client_probe(record,full.PREPROCESSOR_SOURCE_SHA256,full.PREPROCESSOR_MODULE_SHA256,infobase_allowed=True)
        self.assertEqual(f.events,['build','dump','enterprise'])
        self.assertNotIn('PRIVATE',json.dumps(record));self.assertNotIn('/tmp/',json.dumps(record))
        f.reset();record=f.run_probe();self.assertEqual(record['failure_kind'],'invalid_result');self.assertEqual(f.events,['build','dump','enterprise'])

    def test_failed_exit_late_module_and_missing_marker_never_export(self):
        f=self.fixture
        for kind in ('timeout','module','missing'):
            f.reset();f.run_error='timeout' if kind=='timeout' else None
            def hook(mode):
                if kind != 'missing': self.tail(mode)
                if kind=='module' and mode=='enterprise':
                    p=f.work/'src'/suite.CLIENT_MODULE;p.write_bytes(p.read_bytes()+b'\n')
            f.hook=hook;record=f.run_probe(preprocessor_measurement=True)
            self.assertEqual(record['status'],'failed');self.assertNotIn('preprocessor_profile',record)
            self.assertNotIn('infobase_context',record)
            if 'marker_diagnostics' in record:
                full.validate_marker_diagnostics(record['marker_diagnostics'],preprocessor_measurement=True)


if __name__=='__main__': unittest.main()


class ProfileObservationTransportTests(SyntheticFilesystemCase):
    def test_complete_envelope_requires_explicit_mode_and_preserves_six_bytes(self):
        import test_native_1c_full_host as h
        envelope,inputs,modules=h.fixture(b'unchanged\n')
        stage=envelope['report']['stage3'];inputs[full.CLIENT_SOURCE]=full.PREPROCESSOR_SOURCE_SHA256
        modules['client_probe']=full.PREPROCESSOR_MODULE_SHA256
        stage.update(schema=5,preprocessor_status='observed')
        stage['client_probe']=dict(suite.empty_client_report(),status='ok',failure_kind='none',
            source_sha256=full.PREPROCESSOR_SOURCE_SHA256,module_sha256=full.PREPROCESSOR_MODULE_SHA256,
            roundtrip_sha256=full.PREPROCESSOR_MODULE_SHA256,process_diagnostics=probe.process_diagnostics(),
            infobase_context=full.INFOBASE_CONTEXT_EXPECTED_TOKEN,preprocessor_profile=TOKEN,
            **dict.fromkeys(suite.CLIENT_FLAGS,True))
        envelope['report']['stage3']=suite.encode_stage_wire(stage)
        raw=json.dumps(envelope,separators=(',',':')).encode()
        report,outputs=full.validate_envelope(raw,h.NONCE,inputs,modules,smoke.validate_report,
                                             preprocessor_measurement=True)
        self.assertEqual(outputs,dict.fromkeys(full.SCENARIOS,b'unchanged\n'))
        self.assertEqual(report['stage3']['schema'],5)
        with self.assertRaises(full.FullError):
            full.validate_envelope(raw,h.NONCE,inputs,modules,smoke.validate_report)

    def test_cli_flag_requires_full_client_and_container_tail_is_fixed(self):
        for args in ([],['--full-suite'],['--client-probe']):
            with self.assertRaises(SystemExit),mock.patch('sys.stderr'):
                smoke.main(['--execute-approved-image','--client-preprocessor-measurement']+args)
        with tempfile.TemporaryDirectory() as folder:
            staged=Path(folder).resolve()/'inputs'
            smoke.stage_inputs(staged,full_suite=True,client_probe=True)
            common=dict(full_suite=True,client_probe=True,nonce=NONCE,preprocessor_measurement=True)
            command=smoke.container_command(staged,'fixed',**common)
            self.assertEqual(command[-5:],['--full-suite','--invocation-nonce',NONCE,'--client-probe','--client-preprocessor-measurement'])
            both=smoke.container_command(staged,'fixed',client_async=True,**common)
            self.assertEqual(both[-2:],['--client-async-measurement','--client-preprocessor-measurement'])
            self.assertIn('--network',both);self.assertEqual(both[both.index('--network')+1],'none')
        with self.assertRaises(smoke.SmokeError):
            smoke.container_command(ROOT,'fixed',preprocessor_measurement=True)

    def test_workflow_command_only_delta_and_shell_renderer_mode(self):
        source=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text()
        commands=[line for line in source.splitlines() if line.strip().startswith('run: python3 scripts/native_1c_smoke.py')]
        self.assertEqual(len(commands),2)
        self.assertTrue(all('--client-preprocessor-measurement' not in line for line in commands))
        self.assertEqual(source.count('--client-preprocessor-measurement'),0)
        self.assertEqual(source.count('packages: read'),1);self.assertNotIn(': write',source)
        script=smoke.PROBE.read_text().split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        compile(script,'embedded-report-emitter','exec')
        self.assertIn('preprocessor_mode = emitter_args.pop() if len(emitter_args) == 18 else "false"',script)
        self.assertEqual(script.count('"preprocessor_measurement": True'),2)

    def test_failed_teardown_strips_observation_and_keeps_mode(self):
        import test_native_preprocessor_budget as b
        stage,inputs,modules=b.ib.parity_stage((False,)*5);b.bind(stage,inputs,modules)
        suite.fail_client_process_checkpoint(stage,False)
        self.assertEqual(stage['schema'],5);self.assertEqual(stage['preprocessor_status'],'failed')
        self.assertNotIn('preprocessor_profile',stage['client_probe']);self.assertNotIn('infobase_context',stage['client_probe'])
        raw=suite.encode_stage_wire(stage)
        full.validate_stage3(raw,b.ab.NONCE,inputs,modules,prerequisites=True,preprocessor_measurement=True)

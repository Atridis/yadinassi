"""Rejected Date/Null capture. Synthetic fixtures never establish native semantics."""
import contextlib
import copy
from decimal import Decimal
import inspect
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from test_native_1c_full_host import SyntheticFilesystemCase
from test_native_client_probe import full, suite, ROOT, stage_fixture, NONCE, process_diagnostics
import test_native_client_probe as client_fixtures
from test_native_directive_witness import linux_fixture
import test_native_async_budget as budget
from test_native_1c_smoke import smoke

SOURCE = 'integrational_tests/directive_probes/date_null_core.bsl'
PLAN = 'integrational_tests/directive_probes/date_null_measurement.json'
TOKEN = 'dn.v1:01201278'  # arbitrary schema specimen, NOT a native expected result
PRODUCTION_MARKER = suite.date_null_client_marker


def marker(values=None, **kwargs):
    value = dict(schema=1, nonce=NONCE, phase='completed', witness='client',
                 values=list(full.CLIENT_VALUES) + [TOKEN] if values is None else values)
    value.update(kwargs)
    return value


def capture_record(token=TOKEN):
    return dict(status='failed', failure_kind='invalid_result',
                source_sha256=full.DATE_NULL_SOURCE_SHA256,
                module_sha256=full.DATE_NULL_MODULE_SHA256,
                roundtrip_sha256=full.DATE_NULL_MODULE_SHA256,
                entered=True, completed=False, process_exited=True, quiet=True,
                witness_verified=False, process_diagnostics=process_diagnostics(),
                marker_diagnostics=dict(phase='completed', kind='count', ordinal=135,
                                        error_stage=0, date_null=token))


class DateNullMeasurementTests(SyntheticFilesystemCase):
    def setUp(self):
        super().setUp()
        self.source=linux_fixture(ROOT/full.CLIENT_SOURCE)
        if os.name=='nt':
            patch=mock.patch.object(suite,'secure_bytes',new=stage_fixture.portable_fixture_bytes)
            patch.start();self.addCleanup(patch.stop)

    def diagnose(self, value, source=None):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'completed.json'
            raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
            p.write_bytes(raw)
            with self.assertRaises(suite.FullError):PRODUCTION_MARKER(p,NONCE,'completed')
            return suite.client_marker_diagnostics(p,NONCE,date_null_source=self.source if source is None else source)

    def test_unknown_native_values_and_source_bound_identity(self):
        plan=json.loads((ROOT/PLAN).read_text(encoding='utf-8'))
        self.assertIsNone(plan['native_observations']);self.assertIsNone(plan['expected_token'])
        self.assertEqual(plan['native_execution'],'not_run')
        self.assertEqual(full.DATE_NULL_SOURCE_SHA256,suite.DATE_NULL_SOURCE_SHA256)
        self.assertEqual(full.DATE_NULL_MODULE_SHA256,suite.DATE_NULL_MODULE_SHA256)
        self.assertEqual(full.DATE_NULL_SOURCE_SHA256,full.digest(self.source))
        self.assertEqual(full.DATE_NULL_MODULE_SHA256,full.digest(full.generated_module(self.source)))
        self.assertEqual(full.DATE_NULL_CORE_SHA256,full.digest(linux_fixture(ROOT/SOURCE)))
        self.assertEqual(len(full.CLIENT_VALUES),135)
        self.assertEqual(full.CLIENT_VALUES,suite.CLIENT_VALUES)
        self.assertEqual(full.CLIENT_VALUES[-1],'dual.v1:000032017000017041000032017')

    def test_entire_prefix_exact136_and_source_required_to_export(self):
        diagnostic=self.diagnose(marker())
        self.assertEqual(diagnostic,dict(phase='completed',kind='count',ordinal=135,error_stage=0,date_null=TOKEN))
        full.validate_marker_diagnostics(diagnostic)
        for src in (b'',self.source+b' ',full.date_null_shared_source(self.source)):
            self.assertNotIn('date_null',self.diagnose(marker(),source=src))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'marker.json';p.write_text(json.dumps(marker()),encoding='utf-8',newline='\n')
            self.assertNotIn('date_null',suite.client_marker_diagnostics(p,NONCE))
        for values in (full.CLIENT_VALUES,full.CLIENT_VALUES[:-1],full.CLIENT_VALUES+[TOKEN,0],full.CLIENT_VALUES[:134]+[TOKEN]):
            self.assertNotIn('date_null',self.diagnose(marker(values)))

    def test_every_old_value_and_type_must_match(self):
        for index,expected in enumerate(full.CLIENT_VALUES):
            for wrong in (None,not expected if type(expected) is bool else False,'PRIVATE'):
                values=list(full.CLIENT_VALUES)+[TOKEN];values[index]=wrong
                diagnostic=self.diagnose(marker(values))
                self.assertNotIn('date_null',diagnostic)
                self.assertNotIn('PRIVATE',json.dumps(diagnostic))
                self.assertEqual(diagnostic['ordinal'],index)

    def test_token_finite_grammar_rejects_all_other_forms(self):
        invalid=(None,False,0,[],{},'','dn.v1:'+'0'*7,'dn.v1:'+'0'*9,
                 'dn.v1:'+'٠'*8,'dn.v1:33333300','dn.v1:00000099',
                 TOKEN+'\n',TOKEN+'PRIVATE',TOKEN.replace('dn.v1:','dn.v2:'),
                 'dn.v1:-0101200','dn.v1:0.101200')
        for token in invalid:
            self.assertFalse(full.valid_date_null_token(token))
            self.assertFalse(suite.valid_date_null_token(token))
            self.assertNotIn('date_null',self.diagnose(marker(full.CLIENT_VALUES+[token])))
        for scalar in '012':
            for a in '012345678':
                for b in '012345678':
                    token='dn.v1:'+scalar*6+a+b
                    self.assertTrue(full.valid_date_null_token(token))
                    self.assertTrue(suite.valid_date_null_token(token))

    def test_nonce_schema_phase_witness_and_keys_fail_closed(self):
        for update in ({'nonce':'b'*32},{'nonce':None},{'schema':True},{'schema':2},
                       {'phase':'error'},{'phase':'entered'},{'witness':'server'},
                       {'private':'PRIVATE'},{'values':None}):
            value=marker();value.update(update)
            self.assertNotIn('date_null',self.diagnose(value))
        self.assertNotIn('date_null',self.diagnose(marker([],phase='error')))

    def test_invalid_json_and_oversize_still_use_unchanged_secure_limit(self):
        good=json.dumps(marker(),separators=(',',':')).encode()
        variants=(good+b' garbage',good[:-1],b'\xff',b'[]',b' '*2049,
                  good.replace(b'"schema":1',b'"schema":1,"schema":1'),
                  good.replace(b'42,',b'42.0,',1),good.replace(b'42,',b'NaN,',1),
                  good.replace(b'dn.v1:',b'dn.v1:\n',1))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'marker.json'
            for raw in variants:
                p.write_bytes(raw)
                with self.assertRaises(suite.FullError):PRODUCTION_MARKER(p,NONCE,'completed')
                self.assertNotIn('date_null',suite.client_marker_diagnostics(p,NONCE,date_null_source=self.source))

    @unittest.skipIf(os.name=='nt','POSIX descriptor boundary is not simulated')
    def test_symlink_hardlink_and_missing_markers_cannot_export(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'marker.json';p.write_text(json.dumps(marker()),encoding='utf-8',newline='\n')
            link=Path(folder)/'link.json';link.symlink_to(p)
            for path in (link,Path(folder)/'missing'):
                self.assertNotIn('date_null',suite.client_marker_diagnostics(path,NONCE,date_null_source=self.source))
            hard=Path(folder)/'hard.json';os.link(p,hard)
            for path in (p,hard):
                self.assertNotIn('date_null',suite.client_marker_diagnostics(path,NONCE,date_null_source=self.source))

    def test_host_capture_schema_requires_exact_failed_count_and_token(self):
        good=capture_record()['marker_diagnostics'];full.validate_marker_diagnostics(good)
        for update in ({'ordinal':134},{'ordinal':136},{'ordinal':True},{'error_stage':True},
                       {'error_stage':1},{'phase':'error'},{'kind':'value'},{'kind':'none'},
                       {'date_null':'PRIVATE'},{'extra':1}):
            with self.assertRaises(ValueError):full.validate_marker_diagnostics({**good,**update})

    def test_host_requires_identity_clean_completion_and_rejected_outcome(self):
        good=capture_record()
        full.validate_client_probe(good,full.DATE_NULL_SOURCE_SHA256,full.DATE_NULL_MODULE_SHA256)
        for key in ('source_sha256','module_sha256','roundtrip_sha256'):
            for wrong in (None,'f'*64):
                bad=copy.deepcopy(good);bad[key]=wrong
                with self.assertRaises(ValueError):full.validate_client_probe(bad,full.DATE_NULL_SOURCE_SHA256,full.DATE_NULL_MODULE_SHA256)
        for update in ({'entered':False},{'process_exited':False},{'quiet':False},
                       {'completed':True},{'witness_verified':True},{'status':'ok'},
                       {'failure_kind':'timeout'},{'process_diagnostics':None},
                       {'process_diagnostics':process_diagnostics(reason='unverified')},
                       {'process_diagnostics':process_diagnostics(stage='before_probe')}):
            with self.assertRaises(ValueError):full.validate_client_probe({**good,**update},full.DATE_NULL_SOURCE_SHA256,full.DATE_NULL_MODULE_SHA256)
        for source,module in (('f'*64,full.DATE_NULL_MODULE_SHA256),(full.DATE_NULL_SOURCE_SHA256,'f'*64)):
            with self.assertRaises(ValueError):full.validate_client_probe(good,source,module)

    def test_host_capture_requires_consistent_failed_stage_and_established_inputs(self):
        envelope,inputs,modules=client_fixtures.host_fixture.fixture()
        inputs[full.CLIENT_SOURCE]=full.DATE_NULL_SOURCE_SHA256
        modules['client_probe']=full.DATE_NULL_MODULE_SHA256
        envelope['report'].update(status='stage3_failed',native_tests_completed=False)
        envelope['report']['stage3'].update(status='failed',failure_kind='invalid_result',
                                            client_probe=capture_record())
        envelope['outputs']=[]
        nonce=client_fixtures.host_fixture.NONCE
        def validate(value):
            return full.validate_envelope(json.dumps(value,separators=(',',':')).encode(),
                                          nonce,inputs,modules,smoke.validate_report)
        accepted,outputs=validate(envelope)
        self.assertEqual(outputs,{})
        self.assertEqual(accepted['stage3']['client_probe'],capture_record())
        updates=({'status':'ok'},{'status':'not_started'},
                 {'failure_kind':'process_failed'},{'failure_kind':'export_failed'},
                 {'failure_kind':'timeout'},{'failed_case':'dates'},
                 {'input_sha256':{}},
                 {'input_sha256':{**inputs,full.CLIENT_SOURCE:'f'*64}})
        for update in updates:
            with self.subTest(update=update):
                changed=copy.deepcopy(envelope)
                changed['report']['stage3'].update(update)
                with self.assertRaises(full.FullError):validate(changed)
        maximum=budget.maximum_process_diagnostics();maximum['stage']='after_exit'
        for diagnostics in (maximum,process_diagnostics(reason='unverified'),
                            process_diagnostics(reason='native_not_quiet')):
            with self.subTest(teardown=diagnostics['reason']):
                changed=copy.deepcopy(envelope)
                stage=changed['report']['stage3']
                self.assertTrue(suite.discard_date_null_capture(stage,diagnostics))
                validate(changed)
                stage['client_probe']['marker_diagnostics']['date_null']=TOKEN
                with self.assertRaises(full.FullError):validate(changed)

    def test_no_baseline_or_unknown_capture_can_claim_measurement_success(self):
        good=capture_record();good.pop('marker_diagnostics')
        good.update(status='ok',failure_kind='none',completed=True,witness_verified=True)
        with self.assertRaises(ValueError):full.validate_client_probe(good,full.DATE_NULL_SOURCE_SHA256,full.DATE_NULL_MODULE_SHA256)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'marker.json';p.write_text(json.dumps(marker(full.CLIENT_VALUES)),encoding='utf-8',newline='\n')
            self.assertEqual(suite.client_marker(p,NONCE,'completed')['values'],full.CLIENT_VALUES)
            with self.assertRaises(suite.FullError):PRODUCTION_MARKER(p,NONCE,'completed')

    def test_exact_inverse_rejects_drift_and_preserves_four_adapters_async8(self):
        restored=full.date_null_shared_source(self.source)
        self.assertEqual(restored,suite.date_null_shared_source(self.source))
        self.assertEqual(full.digest(restored),'c991b9fbf808a59fad6edc10ad9768efe85bc3bd2da9d7b63c1daa5cdb118413')
        self.assertTrue(self.source.endswith(full.DATE_NULL_SUFFIX+full.CLIENT_NOCONTEXT_INITIALIZER))
        for wrong in (self.source+b' ',self.source[:-1],restored,
                      self.source.replace(full.DATE_NULL_CALL,b'',1),
                      self.source.replace(b'2031, 6, 7',b'2032, 6, 7',1),
                      self.source.replace(full.DATE_NULL_COMPACT_WRITER,full.DATE_NULL_OLD_WRITER)):
            for module in (full,suite):
                with self.assertRaises(module.FullError):module.date_null_shared_source(wrong)
        plan=json.loads((ROOT/PLAN).read_text(encoding='utf-8'))
        for name,expected in plan['four_adapter_sha256'].items():
            result=getattr(suite,'client_'+name+'_module')(linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl'),self.source)
            self.assertEqual(full.digest(result),expected)
        self.assertEqual(full.async_source_identity(linux_fixture(ROOT/'scripts/native_1c_bootstrap/full_suite.py')),plan['async8_identity'])
        self.assertEqual(len(smoke.staged_files(True,True)),24)

    @unittest.skipIf(os.name=='nt','production interpreter subprocess is POSIX-only')
    def test_preflight_executes_exact_restored_baseline_not_new_semantics(self):
        seen=[]
        def runner(arguments,cwd):
            path=Path(arguments[-1]);raw=path.read_bytes()
            self.assertEqual(full.digest(raw),full.DATE_NULL_BASE_SHA256)
            self.assertNotIn(b'DNCollect',raw)
            self.assertNotEqual(path,ROOT/full.CLIENT_SOURCE)
            self.assertEqual((ROOT/full.CLIENT_SOURCE).read_bytes(),self.source)
            seen.append(raw)
            return full.bounded_child(arguments,cwd)
        full.verify_client_interpreter(ROOT,ROOT/full.CLIENT_SOURCE,full.DATE_NULL_SOURCE_SHA256,runner=runner)
        self.assertEqual(len(seen),1)

    def test_changed_source_never_executes_and_baseline_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source.bsl';p.write_bytes(self.source+b' ')
            runner=mock.Mock(side_effect=AssertionError('changed source executed'))
            with self.assertRaisesRegex(full.FullError,'source_changed'):full.verify_client_interpreter(ROOT,p,full.digest(p.read_bytes()),runner=runner)
            runner.assert_not_called()
            p.write_bytes(self.source)
            def mutate(arguments,cwd):
                Path(arguments[-1]).write_bytes(b'changed')
                return 0,json.dumps(full.CLIENT_VALUES,separators=(',',':')).encode(),b''
            with self.assertRaisesRegex(full.FullError,'source_changed'):full.verify_client_interpreter(ROOT,p,full.DATE_NULL_SOURCE_SHA256,runner=mutate)

    def test_compact_writer_is_native_only_and_escaping_preserves_values(self):
        self.assertIn('ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина)'.encode(),self.source)
        self.assertIn('Запись.ОткрытьФайл(Путь, , , ПараметрыJSON);'.encode(),self.source)
        self.assertNotIn('Запись.ОткрытьФайл(Путь);'.encode(),self.source)
        self.assertNotIn(b'StrReplace',full.DATE_NULL_COMPACT_WRITER)
        value=marker();raw=json.dumps(value,separators=(',',':')).encode()
        self.assertEqual(len(raw),1359)
        self.assertEqual(len(json.dumps(value,indent=2).encode()),2063)
        self.assertEqual(suite.strict_json(raw,max_depth=3),value)
        for text in (' leading spaces ', '\\n\\r\\t', '\n\r\t', '"\\', 'Я😀', '\x00'):
            sample=marker(full.CLIENT_VALUES+[text])
            for ascii_mode in (False,True):
                raw=json.dumps(sample,ensure_ascii=ascii_mode,separators=(',',':')).encode()
                actual=json.loads(raw)
                self.assertEqual(actual,sample)
                self.assertEqual(list(map(type,actual['values'])),list(map(type,sample['values'])))
                self.assertFalse(any(c in raw for c in (b'\r',b'\n',b'\t')))

    def test_explicit_locals_literal_calls_and_encoder_meaning(self):
        from yadinassi import Interpreter
        text=linux_fixture(ROOT/SOURCE).decode()
        routines=re.findall(r'(?:Function|Procedure) (\w+)\(([^)]*)\)(?: Export)?\n(.*?)End(?:Function|Procedure)',text,re.S)
        self.assertEqual(len(routines),18)
        for name,formals,body in routines:
            declared={v.strip().removeprefix('Val ').casefold() for v in formals.split(',') if v.strip()}
            for group in re.findall(r'^\s*Var ([^;]+);',body,re.M):declared.update(v.strip().casefold() for v in group.split(','))
            assigned=re.findall(r'^\s*(\w+)\s*=(?!=)',body,re.M)+re.findall(r'For Each (\w+) In',body)
            self.assertLessEqual({v.casefold() for v in assigned},declared,name)
        collect=next(body for name,_,body in routines if name=='DNCollect')
        for name in ('DNEchoDate','DNEchoNull','DNDateToNull','DNNullToDate','DNValDate','DNValNull','DNValGraph','DNRefGraph'):
            self.assertEqual(len(re.findall(r'\b'+name+r'\(',collect)),1)
        vm=Interpreter(lambda _:self.fail('unexpected output'));vm.execute(text)
        for scalar in range(3):
            for a in range(9):
                values=[scalar]*6+[a,8-a]
                vm.execute('V=New Array;'+''.join(f'V.Add({v});' for v in values))
                self.assertEqual(vm.execute('DNEncode(V)'),'dn.v1:'+''.join(map(str,values)))
        for literal in ('True','Null','0.5','-1','3'):
            vm.execute('V=New Array;'+'V.Add(0);'*8+f'V[0]={literal};')
            with self.assertRaises(Exception):vm.execute('DNEncode(V)')
        self.assertIs(vm.execute('DNIsNull(Undefined)'),False)
        self.assertIs(vm.execute('DNIsNull(Null)'),True)
        self.assertIs(vm.execute('DNIsDateA(Date(2024,1,2,3,4,6))'),False)

    def test_production_serializer_bounds_for_valid_capture_record(self):
        stages=[];summaries=[]
        maximum=budget.maximum_process_diagnostics()
        maximum['stage']='after_exit'
        variants=(('capture',None),('unexpected_processes',maximum),
                  ('unverified',process_diagnostics(reason='unverified')),
                  ('native_not_quiet',process_diagnostics(reason='native_not_quiet')))
        for early in (False,True):
            for case in (None,*range(8)):
                majorant=budget.majorant(early=early,marker_case=case)
                for name,diagnostics in variants:
                    with self.subTest(early=early,case=case,variant=name):
                        value=copy.deepcopy(majorant)
                        record=capture_record('dn.v1:22222288')
                        value['stage3']['client_probe']=record
                        if name!='capture':
                            self.assertTrue(suite.discard_date_null_capture(
                                value['stage3'],copy.deepcopy(diagnostics)))
                            self.assertNotIn('date_null',record['marker_diagnostics'])
                            self.assertEqual(record['process_diagnostics'],diagnostics)
                            self.assertFalse(record['quiet'])
                            self.assertFalse(record['witness_verified'])
                        full.validate_client_probe(record,full.DATE_NULL_SOURCE_SHA256,full.DATE_NULL_MODULE_SHA256)
                        # Retain later maximal data conservatively even though
                        # this failure precedes it; each substituted client
                        # record satisfies every production applicability gate.
                        wire=budget.render_stage(value['stage3'])
                        self.assertEqual(full.decode_stage3_wire(json.loads(wire)),value['stage3'])
                        summary,_=budget.render_summary(value,error=True)
                        stages.append(len(wire));summaries.append(len(summary))
        self.assertLessEqual(max(stages),8192);self.assertLessEqual(max(summaries),32768)
        self.assertEqual((full.MAX_STAGE_REPORT,suite.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,8192,32768))


class DateNullNativeOrchestrationTests(unittest.TestCase):
    """Real orchestration with synthetic bytes and all process launch mocked."""
    def harness(self):
        h=client_fixtures.ClientProbeHarness();h.setUp();self.addCleanup(h.doCleanups)
        # Override any explicitly historical boundary used by older tests.
        patch=mock.patch.object(suite,'date_null_client_marker',new=PRODUCTION_MARKER)
        patch.start();self.addCleanup(patch.stop)
        def write_capture(mode):
            if mode=='enterprise':
                (h.work/'completed.json').write_bytes(json.dumps(marker(),separators=(',',':')).encode())
        h.hook=write_capture
        return h

    def test_genuine_route_exports_only_finite_capture_and_remains_rejected(self):
        h=self.harness();result=h.run_probe()
        self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_kind'],'invalid_result')
        self.assertFalse(result['completed']);self.assertFalse(result['witness_verified'])
        self.assertEqual(result['marker_diagnostics']['date_null'],TOKEN)
        full.validate_client_probe(result,full.DATE_NULL_SOURCE_SHA256,full.DATE_NULL_MODULE_SHA256)
        self.assertEqual(h.events,['build','dump','enterprise'])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_dirty_late_source_module_roundtrip_or_timestamp_suppresses_capture(self):
        for kind in ('source','module','roundtrip','mtime'):
            h=self.harness();original=h.hook
            def mutate(mode):
                original(mode)
                if mode=='enterprise':
                    paths={'source':h.inputs/suite.CLIENT_TARGET,'module':h.work/'src'/suite.CLIENT_MODULE,
                           'roundtrip':h.work/'roundtrip'/suite.CLIENT_MODULE}
                    if kind in paths:paths[kind].write_bytes(paths[kind].read_bytes()+b' ')
                    else:
                        os.utime(h.work/'entered.json',ns=(2_000_000_000,2_000_000_000))
                        os.utime(h.work/'completed.json',ns=(1_000_000_000,1_000_000_000))
            h.hook=mutate
            result=h.run_probe()
            self.assertEqual(result['status'],'failed')
            self.assertNotIn('date_null',result.get('marker_diagnostics',{}))
            h.doCleanups()

    def test_timeout_nonzero_missing_entry_or_nonquiet_cannot_export(self):
        for kind in ('timeout','process_failed','missing_entered','quiet'):
            h=self.harness()
            if kind in ('timeout','process_failed'):h.run_error=kind
            elif kind=='missing_entered':h.run_markers=('completed',)
            else:h.quiet=False
            result=h.run_probe()
            self.assertEqual(result['status'],'failed')
            self.assertNotIn('date_null',result.get('marker_diagnostics',{}))
            self.assertFalse(result['witness_verified'])
            h.doCleanups()


class DateNullFinalReportEmitterTests(unittest.TestCase):
    """Execute the actual final renderer; never start a native process."""
    def render(self, *, census_failed=False, cleanup_failed=False,
               quiet=True, capture=True):
        envelope, inputs, modules = client_fixtures.host_fixture.fixture()
        inputs[suite.CLIENT_SOURCE] = full.DATE_NULL_SOURCE_SHA256
        modules['client_probe'] = full.DATE_NULL_MODULE_SHA256
        record = capture_record()
        if not capture:
            record['marker_diagnostics'].pop('date_null')
        stage = envelope['report']['stage3']
        stage.update(nonce=NONCE, status='failed', failure_kind='invalid_result',
                     client_probe=record)
        expected_stage = copy.deepcopy(stage)
        script = smoke.PROBE.read_text(encoding='utf-8').split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "café-Проверка"
            root.mkdir()
            (root / 'config').mkdir()
            (root / 'config/Configuration.xml').write_text(
                '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20">'
                '<Configuration><Properties><Name/></Properties></Configuration></MetaDataObject>',
                encoding='utf-8', newline='\n')
            (root / 'stage2-report.json').write_text(
                json.dumps(envelope['report']['stage2']), encoding='utf-8', newline='\n')
            (root / 'stage3-report.json').write_text(json.dumps(
                suite.encode_stage_wire(stage), separators=(',', ':')),
                encoding='utf-8', newline='\n')
            script = client_fixtures.relocate_emitter_source(script, root)
            arguments = ['emitter', '1', 'stage2', 'true', 'true', 'true',
                         'true', 'true', 'true', NONCE, 'true', 'false',
                         'false', 'false', 'false', 'false',
                         'true' if cleanup_failed else 'false']
            diagnostic = process_diagnostics(reason='unexpected_processes',
                                             classes={'other': 1})
            failure = suite.ClientProcessError(diagnostic) if census_failed else None
            raw = io.BytesIO()
            reader = (mock.patch.object(suite, 'secure_bytes',
                                       new=stage_fixture.portable_fixture_bytes)
                      if os.name == 'nt' else contextlib.nullcontext())
            with reader, mock.patch.object(sys, 'argv', arguments), \
                    mock.patch.object(sys, 'path', sys.path.copy()), \
                    mock.patch.object(sys, 'stdout', SimpleNamespace(buffer=raw)), \
                    mock.patch.object(suite.os, 'geteuid', return_value=1000, create=True), \
                    mock.patch.object(suite.os, 'access', return_value=True), \
                    mock.patch.object(suite, 'native_processes_quiet', return_value=quiet) as quiet_check, \
                    mock.patch.object(suite, 'final_client_process_census', side_effect=failure) as census, \
                    mock.patch.object(subprocess, 'Popen', side_effect=AssertionError(
                        'Final renderer must not execute native processes')) as native, \
                    self.assertRaises(SystemExit) as caught:
                exec(compile(script, 'offline-date-null-final-renderer', 'exec'), {})
            self.assertEqual(caught.exception.code, 1)
            native.assert_not_called()
            quiet_check.assert_called_once()
        report, outputs = full.validate_envelope(
            raw.getvalue(), NONCE, inputs, modules, smoke.validate_report)
        self.assertEqual(outputs, {})
        self.assertEqual(json.loads(raw.getvalue())['outputs'], [])
        self.assertFalse(report['native_tests_completed'])
        self.assertEqual(report['status'], 'stage3_failed')
        self.assertEqual(report['stage2']['status'], 'ok')
        self.assertEqual(report['stage3']['status'], 'failed')
        self.assertEqual(report['stage3']['cases'], expected_stage['cases'])
        self.assertEqual(report['stage3']['input_sha256'], expected_stage['input_sha256'])
        return report, expected_stage, census, raw.getvalue()

    def test_clean_final_census_preserves_rejected_capture_without_success(self):
        report, expected_stage, census, _ = self.render()
        # A rejected measurement still needs the final post-teardown census.
        census.assert_called_once_with(NONCE)
        self.assertEqual(report['stage3'], expected_stage)
        self.assertEqual(report['stage3']['client_probe'], capture_record())

    def test_each_late_failure_and_combination_discards_only_optional_token(self):
        for census_failed in (False, True):
            for cleanup_failed in (False, True):
                for quiet in (False, True):
                    if not census_failed and not cleanup_failed and quiet:
                        continue
                    with self.subTest(census_failed=census_failed,
                                      cleanup_failed=cleanup_failed, quiet=quiet):
                        report, expected_stage, census, raw = self.render(
                            census_failed=census_failed, cleanup_failed=cleanup_failed,
                            quiet=quiet)
                        record = report['stage3']['client_probe']
                        expected = expected_stage['client_probe']
                        diagnostic = {key: value for key, value in expected['marker_diagnostics'].items()
                                      if key != 'date_null'}
                        self.assertEqual(record['marker_diagnostics'], diagnostic)
                        self.assertNotIn(TOKEN.encode(), raw)
                        self.assertEqual(record['status'], 'failed')
                        self.assertNotEqual(record['failure_kind'], 'none')
                        self.assertFalse(record['quiet'])
                        self.assertFalse(record['witness_verified'])
                        for key in ('source_sha256', 'module_sha256', 'roundtrip_sha256',
                                    'entered', 'completed', 'process_exited'):
                            self.assertEqual(record[key], expected[key], key)
                        census.assert_called_once_with(NONCE)

    def test_plain_failed_diagnostics_keep_previous_renderer_behavior(self):
        for census_failed in (False, True):
            for cleanup_failed in (False, True):
                for quiet in (False, True):
                    with self.subTest(census_failed=census_failed,
                                      cleanup_failed=cleanup_failed, quiet=quiet):
                        report, expected_stage, census, raw = self.render(
                            census_failed=census_failed, cleanup_failed=cleanup_failed,
                            quiet=quiet, capture=False)
                        self.assertEqual(report['stage3'], expected_stage)
                        self.assertNotIn(TOKEN.encode(), raw)
                        census.assert_not_called()

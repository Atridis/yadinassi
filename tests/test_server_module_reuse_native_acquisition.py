"""Offline source/marker contracts. Never starts 1C or a container."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from server_module_reuse_packet import route, packet, PACKET_HASHES, SOURCE_SHA256, FORM_SHA256, MODULES_SHA256, parse_records

class AcquisitionContracts(unittest.TestCase):
    def marker(self,phase='completed',count=16):
        return dict(schema=route.SCHEMA,nonce='a'*32,phase=phase,source_sha256=SOURCE_SHA256,
                    form_sha256=FORM_SHA256,modules_sha256=MODULES_SHA256,
                    records=''.join(f'SR{i}=1|' for i in range(1,count+1)) if phase not in ('entered','error') else '')
    def wire(self,value):return json.dumps(value).encode()
    def test_01_raw_pins(self):
        self.assertEqual(set(packet()),set(PACKET_HASHES))
        for p,raw in packet().items():self.assertEqual(hashlib.sha256(raw).hexdigest(),PACKET_HASHES[p])
    def test_02_prepared_identity(self):
        self.assertEqual(route.validate_prepared(route.sources()),route.module_digest())
    def test_03_prepared_drift(self):
        value=route.sources();value[next(iter(value))]+=b' '
        with self.assertRaises(ValueError):route.validate_prepared(value)
    def test_04_missing_source(self):
        value=route.sources();value.pop(next(iter(value)))
        with self.assertRaises(ValueError):route.validate_prepared(value)
    def test_05_manifest(self):
        route.verify_hashes({'scripts/server_module_reuse_packet/'+p:h for p,h in PACKET_HASHES.items()})
        with self.assertRaises(ValueError):route.verify_hashes({})
    def test_06_completed(self):
        self.assertEqual(route.marker(self.wire(self.marker()),'a'*32,'completed')['phase'],'completed')
    def test_07_nonce(self):
        with self.assertRaises(ValueError):route.marker(self.wire(self.marker()),'b'*32,'completed')
    def test_08_source(self):
        value=self.marker();value['source_sha256']='0'*64
        with self.assertRaises(ValueError):route.marker(self.wire(value),'a'*32,'completed')
    def test_09_module(self):
        value=self.marker();value['modules_sha256']='0'*64
        with self.assertRaises(ValueError):route.marker(self.wire(value),'a'*32,'completed')
    def test_10_duplicate_marker(self):
        raw=self.wire(self.marker());raw=raw[:-1]+b',"phase":"completed"}'
        with self.assertRaises(ValueError):route.marker(raw,'a'*32,'completed')
    def test_11_entered(self):
        route.marker(self.wire(self.marker('entered')),'a'*32,'entered')
    def test_12_intermediate(self):
        route.marker(self.wire(self.marker('event1_done',15)),'a'*32,'event1_done')
        with self.assertRaises(ValueError):route.marker(self.wire(self.marker('event1_done',16)),'a'*32,'event1_done')
    def test_13_record_inventory(self):
        with self.assertRaises(ValueError):parse_records(b'SR1=1|')
    def test_14_no_token_or_text_export(self):
        for payload in ('12345678901234567890','error message','abcd-uuid'):
            raw=self.marker()['records'].replace('SR1=1|','SR1='+payload+'|').encode()
            with self.assertRaises(ValueError):parse_records(raw)
    def test_15_server_only_metadata(self):
        for name in ('ServerSession','ServerRequest','CachedServerCall','ServerInspector'):
            text=packet()['CommonModules/'+name+'.xml'].decode()
            for prop in ('Global','Privileged','ExternalConnection','ClientOrdinaryApplication','ClientManagedApplication'):
                self.assertIn('<'+prop+'>false</'+prop+'>',text)
            self.assertIn('<Server>true</Server>',text)
            self.assertIn('<ServerCall>'+str(name in ('CachedServerCall','ServerInspector')).lower()+'</ServerCall>',text)
    def test_16_real_event_transition(self):
        text=route.module().decode()
        self.assertIn('AttachIdleHandler("SecondEvent", 1, True);',text)
        self.assertNotIn('SecondEvent();',text)
        self.assertIn('Procedure SecondEvent() Export',text)
        self.assertIn('Request.event1_done',text)
    def test_17_designer_result_gates(self):
        text=(ROOT/'scripts/native_1c_bootstrap/server_module_reuse_suite.py').read_text(encoding='utf-8')
        self.assertIn("full.require_zero_result(root/(label+'.result'),0)",text)
        self.assertIn("full.require_zero_result(root/'build.result',0)",text)
        for label in ('before','load','update'):self.assertIn("designer('"+label+"'",text)
        self.assertNotIn('/DumpExternalDataProcessorOrReportToFiles',text)
        self.assertEqual(text.count('/DumpConfigToFiles'),1)
    def test_18_baseline_source_preserved(self):
        text=(ROOT/'scripts/server_module_reuse_packet/fixture.py').read_text(encoding='utf-8')
        self.assertIn('original._baseline(files,setup)',text)
        self.assertIn("files['Ext/SessionModule.bsl']",text)
        self.assertNotIn('Role>',text)
    def test_19_packet_syntax_and_inventory(self):
        paths=[ROOT/'scripts'/p for p in ('native_1c_server_module_reuse_profile.py','native_1c_bootstrap/server_module_reuse_suite.py','native_1c_bootstrap/run_server_module_reuse_stage.py')]
        paths+=list((ROOT/'scripts/server_module_reuse_packet').glob('*.py'))
        for path in paths:ast.parse(path.read_text(encoding='utf-8'))
    def test_20_dedicated_source_bound_adapter(self):
        text=(ROOT/'scripts/native_1c_server_module_reuse_profile.py').read_text(encoding='utf-8')
        self.assertIn("PROFILE='server-module-reuse-v1'",text)
        self.assertIn('server_module_reuse_packet',text)
        probe=(ROOT/'scripts/native_1c_server_module_reuse_probe.sh').read_text(encoding='utf-8')
        self.assertIn('[ "$1" = --server_module_reuse-suite ]',probe)
        self.assertNotIn('--common_module_reuse-suite',probe)
        workflow=(ROOT/'.github/workflows/native-1c-server-module-reuse.yml').read_text(encoding='utf-8')
        self.assertIn("github.event.pull_request.head.ref == 'codex/server-module-return-reuse'",workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertIn('native_1c_server_module_reuse_profile.py',workflow)
        self.assertNotIn('workflow_dispatch',workflow)

    def adapters(self):
        # Load the actual source files with their real bootstrap helpers. Avoid
        # leaking generic module names into other suites or using stale aliases.
        import importlib.util
        names=('full_suite','inject_modules','evidence_gates','run_stage','diagnostics')
        saved={name:sys.modules.get(name) for name in names}
        old_path=list(sys.path)
        try:
            for name in names:sys.modules.pop(name,None)
            sys.path.insert(0,str(ROOT/'scripts/native_1c_bootstrap'))
            def load(name,path):
                spec=importlib.util.spec_from_file_location(name,path)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                return module
            host=load('owned_reuse_host',ROOT/'scripts/native_1c_server_module_reuse_profile.py')
            suite=load('owned_reuse_suite',ROOT/'scripts/native_1c_bootstrap/server_module_reuse_suite.py')
            if sys.platform == 'win32':
                # Static test fixtures use one metadata API; production secure
                # readers remain unchanged and are exercised on Linux/macOS.
                from test_native_1c_full_host import read_synthetic_file, full as synthetic_full
                def synthetic_regular(path,limit,*,nonempty=False):
                    try:
                        return read_synthetic_file(path,limit,nonempty=nonempty)
                    except synthetic_full.FullError:
                        raise host.FULL.FullError('invalid_private_file') from None
                patcher=mock.patch.object(host.FULL,'read_regular',side_effect=synthetic_regular)
                patcher.start();self.addCleanup(patcher.stop)
                def synthetic_bytes(path,limit,allow_empty=False):
                    try:
                        return read_synthetic_file(path,limit,nonempty=not allow_empty)
                    except synthetic_full.FullError:
                        raise suite.full.FullError('artifact_missing') from None
                patcher=mock.patch.object(suite.full,'secure_bytes',side_effect=synthetic_bytes)
                patcher.start();self.addCleanup(patcher.stop)
            return host,suite
        finally:
            sys.path[:]=old_path
            for name in names:
                sys.modules.pop(name,None)
                if saved[name] is not None:sys.modules[name]=saved[name]

    def test_21_actual_adapter_inventory(self):
        host,suite=self.adapters()
        self.assertEqual(host.staged_files(),suite.INPUT_FILES)
        self.assertEqual(set(suite.empty_report('a'*32)),host.STAGE_KEYS)
        self.assertEqual(suite.PHASES,host.PHASES)

    def test_22_stage_exact_inputs(self):
        import tempfile
        host,suite=self.adapters()
        with tempfile.TemporaryDirectory(prefix='reuse-stage-',dir=ROOT.parent) as tmp:
            destination=Path(tmp)/'staged'
            hashes=host.stage_inputs(ROOT,destination,host.SMOKE)
            self.assertEqual(hashes,suite.input_hashes(destination))
            self.assertEqual(set(hashes),set(suite.INPUT_FILES))
            for source,target in suite.INPUT_FILES.items():
                self.assertEqual((ROOT/source).read_bytes(),(destination/target).read_bytes())

    def test_23_stage_rejects_extra_inventory(self):
        import tempfile
        host,_=self.adapters()
        with tempfile.TemporaryDirectory(prefix='reuse-drift-',dir=ROOT.parent) as tmp:
            destination=Path(tmp)/'staged'
            hashes=host.stage_inputs(ROOT,destination,host.SMOKE)
            (destination/'unlisted.txt').write_bytes(b'not a source')
            with self.assertRaises(host.FormError):host.validate_inputs(destination,hashes,host.SMOKE)

    def test_24_stage_rejects_source_drift(self):
        import tempfile
        host,_=self.adapters()
        with tempfile.TemporaryDirectory(prefix='reuse-bytes-',dir=ROOT.parent) as tmp:
            destination=Path(tmp)/'staged'
            hashes=host.stage_inputs(ROOT,destination,host.SMOKE)
            target=destination/'bootstrap/server_module_reuse_packet/CommonModules/ServerSession/Ext/Module.bsl'
            target.write_bytes(target.read_bytes()+b'\n// drift\n')
            with self.assertRaises(host.FormError):host.validate_inputs(destination,hashes,host.SMOKE)

    def envelope(self,host,suite):
        import base64
        hashes={source:hashlib.sha256((ROOT/source).read_bytes()).hexdigest() for source in host.staged_files()}
        raw=self.marker()['records'].encode('ascii')
        stage=suite.empty_report('a'*32)
        stage.update(status='ok',failure_kind='none',failure_phase='final',input_sha256=hashes,
                     source_sha256=SOURCE_SHA256,form_sha256=FORM_SHA256,
                     module_sha256=route.module_digest(),prepared_sha256=route.module_digest(),
                     output_sha256=hashlib.sha256(raw).hexdigest(),output_size=len(raw),record_count=16)
        stage.update({name:True for name in host.FLAGS})
        stage['process_diagnostics'].update(stage='after_exit',reason='none')
        result=dict(schema=host.SCHEMA,profile=host.PROFILE,nonce='a'*32,
                    report=dict(status='ok',native_tests_completed=True,stage3=stage),
                    outputs=[dict(name='server_module_reuse.out',size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data_b64=base64.b64encode(raw).decode())])
        return result,hashes,raw

    def test_25_actual_stage_schema_accepts_bound_report(self):
        host,suite=self.adapters();value,hashes,raw=self.envelope(host,suite)
        # Isolate the new stage contract; unchanged stage2 has its own suite.
        report,output=host.validate_envelope(self.wire(value),'a'*32,hashes,validator=lambda raw,**kw:json.loads(raw))
        self.assertEqual(output,raw)
        self.assertTrue(report['stage3']['event1_done'])

    def test_26_actual_stage_requires_event1_and_exact_fields(self):
        import copy
        host,suite=self.adapters();value,hashes,_=self.envelope(host,suite)
        for change in ('false','missing','extra'):
            changed=copy.deepcopy(value);stage=changed['report']['stage3']
            if change=='false':stage['event1_done']=False
            elif change=='missing':stage.pop('event1_done')
            else:stage['unverified']=True
            with self.assertRaises(host.FormError):host.validate_envelope(self.wire(changed),'a'*32,hashes,validator=lambda raw,**kw:json.loads(raw))

    def test_27_windows_fixture_adapter_preserves_exact_bytes_and_drift(self):
        # Exercise the Windows-only static adapter on every platform, without
        # changing OS path semantics or any production admission code.
        with mock.patch.object(sys,'platform','win32'):
            self.test_22_stage_exact_inputs()
            self.test_24_stage_rejects_source_drift()
            import tempfile
            host,suite=self.adapters()
            with tempfile.TemporaryDirectory(prefix='reuse-reader-',dir=ROOT.parent) as tmp:
                missing=Path(tmp)/'missing'; oversized=Path(tmp)/'oversized'
                oversized.write_bytes(b'12345')
                for path in (missing,oversized):
                    with self.subTest(path=path.name):
                        with self.assertRaises(host.FULL.FullError):
                            host.FULL.read_regular(path,4)
                        with self.assertRaises(suite.full.FullError):
                            suite.full.secure_bytes(path,4)

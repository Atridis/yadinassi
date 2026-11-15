"""Ограниченные offline-контракты acquisition, не свидетельство поведения 1С."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
_saved_path=list(sys.path)
try:
    sys.path.insert(0,str(ROOT/'scripts'))
    from uuid_typed_pipeline_behavior import route,fixture
    import native_1c_uuid_typed_pipeline_profile as host
finally:
    sys.path[:]=_saved_path

class UUIDAcquisitionTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            import test_native_1c_full_host as synthetic
            def reader(path,limit,nonempty=False):
                try:return synthetic.read_synthetic_file(path,limit,nonempty=nonempty)
                except synthetic.full.FullError:raise host.FULL.FullError('invalid_private_file') from None
            patch=mock.patch.object(host.FULL,'read_regular',side_effect=reader)
            patch.start();self.addCleanup(patch.stop)
    def wire(self):
        prefix='UTP|'+'a'*32+'|'
        return (prefix+'entered\n'+''.join(prefix+str(n)+'|"S:1"\n' for n in range(1,17))+prefix+'completed\n').encode()
    def test_01_count_and_wire(self):
        self.assertEqual(route.COUNT,16);self.assertEqual(route.parse_wire(self.wire(),'a'*32),['S:1']*16)
    def test_02_nonce(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire(),'b'*32)
    def test_03_order(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire().replace(b'|2|',b'|3|'),'a'*32)
    def test_04_extra_output(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire()+b'extra\n','a'*32)
    def test_05_output_bounds(self):
        self.assertEqual(json.loads(route.canonical(['x'*4096]*16)),['x'*4096]*16)
        for v in [None,42,'x'*4097,'\ud800']:
            with self.assertRaises(ValueError):route.canonical([v]*16)
    def test_06_source_hash(self):
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(),route.SOURCE_SHA256)
    def test_07_program_markers(self):
        source=route.program(fixture.load_saved()[0],'a'*32)
        self.assertIn(b'UTP|'+b'a'*32+b'|entered',source);self.assertIn(b'UTP|'+b'a'*32+b'|completed',source)
        self.assertEqual(source.count(b'For CaseNo = 1 To 16 Do'),1)
    def test_08_fixed_uuid_only(self):
        source=route.source().decode()
        self.assertIn('Var UniqueLookupValue;',source)
        self.assertNotIn(' Key=',source)
        self.assertEqual(source.count('UniqueLookupValue=New УникальныйИдентификатор'),2)
        self.assertNotIn('New UUID()',source)
        self.assertNotIn('New УникальныйИдентификатор()',source)
        self.assertNotIn('Type("UUID")',source)
        self.assertIn('11111111-2222-4333-8444-555555555555',source)
        self.assertIn('00000000-0000-0000-0000-000000000000',source)
    def test_09_no_metadata_or_query_authority(self):
        source=route.source().decode()
        for forbidden in ('New Query','Catalogs.','Documents.','SessionParameters','Metadata.','_query_reference'):
            self.assertNotIn(forbidden,source)
    def test_10_correct_tree_api(self):
        self.assertIn('C=T.Copy()',route.source().decode());self.assertNotIn('CopyColumns',route.source().decode())
    def test_11_codec_writer_readback_distinct(self):
        source=route.source().decode()
        self.assertIn('Return "R:write"',source);self.assertIn('Return "R:read/"+Encoded',source)
        self.assertIn('Stage="observe"; Encoded=BoundedWire(Encoded)',source)
        self.assertIn('StrLen(V)>2048',source)
        self.assertNotIn('TypeDescription("UUID")',source)
    def test_12_observer_errors_are_not_refusals(self):
        source=route.source().decode()
        self.assertIn('Stage="observe"; Return "S:"',source)
        self.assertIn('UUIDTypedPipelineDiagnostic(CaseNo,Stage',source)
        self.assertIn("if report['incomplete'] or errors:raise",(ROOT/'scripts/native_1c_bootstrap/uuid_typed_pipeline_suite.py').read_text(encoding='utf-8'))
    def test_13_owned_baseline_unchanged(self):
        from test_catalog_object_fixture import baseline
        saved=list(sys.path)
        try:
            sys.path.insert(0,str(ROOT/'scripts'))
            from native_1c_bootstrap.inject_modules import render_module
        finally:sys.path[:]=saved
        before=baseline();before['Ext/SessionModule.bsl']=render_module(ROOT/'scripts/native_1c_bootstrap/modules/SessionModule.bsl','a'*32,'NativeSmoke','/tmp/onec-smoke/stage2-'+'b'*32)
        _,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        self.assertEqual(after,before)
    def test_14_bootstrap_mismatch_closed(self):
        from test_catalog_object_fixture import baseline
        with self.assertRaises(ValueError):fixture.prepare(baseline(),bootstrap_module=b'changed')
    def test_15_stage_inventory(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            dest=Path(tmp)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            self.assertIn('scripts/uuid_typed_pipeline_behavior/observe.bsl',hashes)
            self.assertEqual(hashes['scripts/uuid_typed_pipeline_behavior/observe.bsl'],route.SOURCE_SHA256)
    def test_16_stage_drift(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            dest=Path(tmp)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            (dest/'bootstrap/uuid_typed_pipeline_behavior/observe.bsl').write_bytes(b'drift')
            with self.assertRaises(ValueError):host.validate_inputs(dest,hashes,host.SMOKE)
    def test_17_workflow_exact_branch(self):
        source=(ROOT/'.github/workflows/native-1c-uuid-typed-pipeline.yml').read_text(encoding='utf-8')
        for expected in ("head.ref == 'codex/uuid-typed-pipeline'",'persist-credentials: false','native_1c_ci_policy.py bind','cancel-in-progress: false'):
            self.assertIn(expected,source)
        self.assertNotIn('workflow_dispatch',source);self.assertNotIn('pull_request_target',source)
    def test_18_source_rename_boundaries(self):
        for path in ('scripts/native_1c_uuid_typed_pipeline_profile.py','scripts/native_1c_bootstrap/uuid_typed_pipeline_suite.py'):
            source=(ROOT/path).read_text(encoding='utf-8');ast.parse(source)
            self.assertNotIn('regex_extensions',source)
        suite=(ROOT/'scripts/native_1c_bootstrap/uuid_typed_pipeline_suite.py').read_text(encoding='utf-8')
        self.assertIn('stat.S_ISREG',suite);self.assertNotIn('S_ICPEG',suite)
    def test_19_finite_diagnostics(self):
        details=route.failure_details({'messages':[],'error':'secret /private/path'},'a'*32)
        self.assertTrue(route.valid_failure_details(details));self.assertNotIn('secret',json.dumps(details))
    def test_20_refusals_distinct_from_errors(self):
        raw=self.wire().replace(b'"S:1"',b'"R:action"')
        observed,errors=route.parse_attempt(raw,'a'*32)
        self.assertEqual(len(observed),16);self.assertEqual(errors,[])
    def test_21_authored_bsl_parses_without_execution(self):
        from yadinassi.syntax.parser import parse
        parse(route.program(fixture.load_saved()[0],'a'*32).decode('utf-8'))

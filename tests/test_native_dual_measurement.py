"""Strict136 witness, preserving audited dual capture and explicit projection."""
import copy
import inspect
import json
import os
import sys
from pathlib import Path
import re
import tempfile
import unittest
from test_native_async_fixture import historical_tree_collections_module
from unittest import mock
from test_native_1c_full_host import SyntheticFilesystemCase
from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture
import test_native_async_budget as budget

NONCE = 'a' * 32
SOURCE = 'integrational_tests/directive_probes/dual_directive_core.bsl'
PLAN = 'integrational_tests/directive_probes/dual_directive_measurement.json'
BASE_SHA = 'b79c23abb756c3b3965e3a46ad7212e582db917ff319facc70a1efb18a470e14'
CAPTURE = [3,32,17,3,17,41,3,32,17]
PROJECTED = [0,32,17,0,17,41,0,32,17]
TOKEN = 'dual.v1:000032017000017041000032017'
GENERIC = b'#If Client Then\n    ProfileMask = ProfileMask + 1;\n#EndIf\n#If Server Then\n    ProfileMask = ProfileMask + 2;\n#EndIf\n'
LOGICAL = b'#If AtClient Then\n    ProfileMask = ProfileMask + 4;\n#EndIf\n#If AtServer Then\n    ProfileMask = ProfileMask + 8;\n#EndIf\n'


def marker(values):
    return dict(schema=1, nonce=NONCE, phase='completed', witness='client', values=values)


def measured(values):
    return (full.CLIENT_VALUES[:134]
            + ['dual.v1:' + ''.join(f'{value:03d}' for value in values)]
            + full.CLIENT_VALUES[135:])


class DualWitnessTests(SyntheticFilesystemCase):
    def setUp(self):
        super().setUp()
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start()
            self.addCleanup(patch.stop)

    def diagnose_rejected(self, value):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'completed.json'
            path.write_bytes(json.dumps(value, allow_nan=False, separators=(',', ':')).encode())
            with self.assertRaises(suite.FullError):
                suite.client_marker(path, NONCE, 'completed')
            diagnostic = suite.client_marker_diagnostics(path, NONCE)
            self.assertEqual(set(diagnostic), {'phase','kind','ordinal','error_stage'})
            full.validate_marker_diagnostics(diagnostic)
            return diagnostic

    def test_exact136_acceptance_and_dense_bound(self):
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual(len(full.CLIENT_VALUES),136)
        self.assertEqual(full.CLIENT_VALUES[134:], [TOKEN, 'dn.v1:22222277'])
        self.assertEqual(measured(PROJECTED),full.CLIENT_VALUES)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'completed.json'
            value=marker(full.CLIENT_VALUES)
            # The audited source uses compact JSON; the private marker cap is
            # unchanged even though pretty-printing the new suffix exceeds it.
            p.write_bytes(json.dumps(value,separators=(',', ':')).encode())
            self.assertEqual(suite.client_marker(p,NONCE,'completed'),value)
            self.assertEqual(len(p.read_bytes()),1359)
            self.assertLessEqual(len(p.read_bytes()),2048)
            p.write_bytes(json.dumps(value,indent=2).encode())
            self.assertGreater(len(p.read_bytes()),2048)
            with self.assertRaises(suite.FullError):
                suite.client_marker(p,NONCE,'completed')
        # The nine numeric fields cannot enlarge the fixed-width private token.
        for values in ([0]*9,[15,999,999,15,999,999,15,999,999]):
            self.assertEqual(len(json.dumps(marker(measured(values)),separators=(',', ':')).encode()),1359)
            self.diagnose_rejected(marker(measured(values)))
        self.assertEqual(len(TOKEN),35)
        self.diagnose_rejected(marker(full.CLIENT_VALUES[:134]))
        self.diagnose_rejected(marker(measured(CAPTURE)))

    def test_every_strict_value_and_type_is_checked_without_raw_exports(self):
        for index,expected in enumerate(full.CLIENT_VALUES):
            for invalid in (None, not expected if type(expected) is bool else False, 'PRIVATE'):
                values=list(full.CLIENT_VALUES); values[index]=invalid
                diagnostic=self.diagnose_rejected(marker(values))
                self.assertEqual(diagnostic['ordinal'],index)
                self.assertNotIn('PRIVATE',json.dumps(diagnostic))
        for values in (full.CLIENT_VALUES[:-1],full.CLIENT_VALUES+[0]):
            self.assertEqual(self.diagnose_rejected(marker(values))['kind'],'count')
        for invalid in ('dual.v1:'+'000'*9, TOKEN+'0', TOKEN[:-1], TOKEN+'\n',
                        'dual.v1:'+'٠'*27, 'dual.v1:'+'-01'*9, 'dual.v1:'+'1.0'*9,
                        'dual.v1:'+'999'*9, False,True,0,None,[],{}):
            diagnostic = self.diagnose_rejected(marker(full.CLIENT_VALUES[:134]+[invalid]+full.CLIENT_VALUES[135:]))
            self.assertEqual(diagnostic['ordinal'],134)
            self.assertIn(diagnostic['kind'],('type','value'))
        for index in range(9):
            values=PROJECTED.copy(); values[index]+=1
            diagnostic=self.diagnose_rejected(marker(measured(values)))
            self.assertEqual((diagnostic['kind'],diagnostic['ordinal']),('value',134))

    def test_nonce_phase_schema_and_witness_must_match(self):
        good=marker(full.CLIENT_VALUES)
        for update in ({'nonce':'b'*32},{'nonce':None},{'phase':'error'},
                       {'phase':'entered'},{'witness':'server'},{'schema':True},
                       {'schema':2},{'private':'PRIVATE'}):
            self.diagnose_rejected({**good,**update})

    def test_temporary_capture_metadata_is_not_accepted(self):
        for values in (CAPTURE,PROJECTED,[False]*9,[0]*8,[999]*9):
            with self.assertRaises(ValueError):
                full.validate_marker_diagnostics(dict(phase='completed',kind='count',
                    ordinal=134,error_stage=0,dual=values))
        self.assertNotIn("result['dual']",inspect.getsource(suite.client_marker_diagnostics))
        self.assertNotIn('dual_shared_source',inspect.getsource(full.verify_client_interpreter))
        self.assertNotIn('date_null_shared_source',inspect.getsource(full.verify_client_interpreter))
        self.assertFalse(hasattr(full,'dual_shared_source'))

    def test_capture_fixture_and_projection_reconstruct_historical_sources(self):
        plan=json.loads((ROOT/PLAN).read_text())
        self.assertEqual(plan['native_values'],CAPTURE)
        projected=[value & 12 if index in (0,3,6) else value for index,value in enumerate(CAPTURE)]
        self.assertEqual(projected,PROJECTED)
        self.assertEqual(plan['projected_values'],projected)
        self.assertEqual(plan['expected_dense_token'],TOKEN)
        self.assertEqual(plan['capture']['run_id'],40016529386)
        self.assertEqual(plan['capture']['artifact_id'],12527973799)
        self.assertEqual(plan['capture']['summary_zip_sha256'],'7dd804a26fb5cf63cf5de93c2dc1ba908767bba9f64e949f04626344d9278dba')
        self.assertEqual(plan['capture']['acceptance'],'rejected_measurement_only')
        self.assertEqual(plan['fresh_projected_native_validation'],'required_not_yet_obtained')
        raw=full.date_null_shared_source(full.infobase_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE))); standalone=linux_fixture(ROOT/SOURCE)
        self.assertEqual(raw.count(LOGICAL),1);self.assertEqual(standalone.count(LOGICAL),1)
        self.assertNotIn(GENERIC,raw);self.assertNotIn(GENERIC,standalone)
        old=raw.replace(LOGICAL,GENERIC+LOGICAL,1).replace(b'BEGIN bounded dual witness',b'BEGIN bounded dual measurement',1)
        old_standalone=standalone.replace(LOGICAL,GENERIC+LOGICAL,1).replace(
            b'// Audited historical projection; this exact source requires fresh native validation.\n',
            b'// Unexecuted measurement source. No native values are asserted.\n',1)
        self.assertEqual(full.digest(old),'9ce132a3edef0c944a9a2d6776f98d1f209ecbd57ae314e8f02ba4e56d23ae06')
        self.assertEqual(full.digest(old),plan['captured_integrated_source_sha256'])
        self.assertEqual(full.digest(full.generated_module(old)),plan['captured_integrated_module_sha256'])
        self.assertEqual(full.digest(old_standalone),plan['captured_source_sha256'])
        self.assertEqual(full.digest(old_standalone),'761b25578c9327dd3cf76a1f9ff81002c1c02d3e5df96f6c5616379a1058a345')
        self.assertEqual(full.digest(raw),plan['integrated_source_sha256'])
        self.assertEqual(full.digest(full.generated_module(raw)),plan['integrated_module_sha256'])
        self.assertEqual(full.digest(standalone),plan['source_sha256'])

    def test_historical_inverse_restores134_but_host_never_uses_it(self):
        measurement=linux_fixture(ROOT/full.CLIENT_SOURCE)
        raw=full.date_null_shared_source(full.infobase_shared_source(measurement))
        restored=suite.dual_shared_source(raw)
        self.assertEqual(full.digest(restored),BASE_SHA)
        self.assertEqual(full.CLIENT_WITNESS_SOURCE_SHA256,full.digest(measurement))
        self.assertEqual(full.DATE_NULL_BASE_SHA256,full.digest(raw))
        self.assertNotIn('DualProbe',restored.decode())
        for changed in (raw+b' ',raw[:-1],restored,
            raw.replace(suite.CLIENT_DUAL_CALL,b'',1),
            raw.replace(b'ReferenceValue + 10',b'ReferenceValue + 11',1),
            raw.replace(b'ContextServerCounter = 100;',b'ContextServerCounter = 101;',1),
            raw.replace(suite.CLIENT_DUAL_BLOCK,b'',1)+suite.CLIENT_DUAL_BLOCK,
            raw.replace(suite.CLIENT_DUAL_BLOCK,suite.CLIENT_DUAL_BLOCK*2,1)):
            with self.assertRaises(suite.FullError):suite.dual_shared_source(changed)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder).resolve()/'source.bsl';path.write_bytes(changed)
                runner=mock.Mock(side_effect=AssertionError('changed source must not execute'))
                with self.assertRaisesRegex(full.FullError,'^source_changed$'):
                    full.verify_client_interpreter(ROOT,path,full.digest(changed),runner=runner)
                runner.assert_not_called()

    @unittest.skipUnless(sys.platform == 'linux', 'fixed native fixture is Linux-only')
    def test_preflight_uses_exact_original_whole137_source(self):
        path = ROOT / full.CLIENT_SOURCE
        raw = linux_fixture(path)
        seen = []
        fixture = full._load_infobase_fixture()
        bounded = fixture.bounded_child
        def spy(arguments, cwd, **limits):
            self.assertEqual(Path(arguments[-2]), path)
            self.assertEqual(path.read_bytes(), raw)
            self.assertIn(b'DualProbe', raw)
            self.assertIn(b'DNAppend', raw)
            seen.append(full.digest(raw))
            return bounded(arguments, cwd, **limits)
        # Observe the real owner-mediated path; no injected runner or second
        # module/error identity can bypass the uncertain-shutdown boundary.
        with mock.patch.object(full, '_load_infobase_fixture', return_value=fixture), \
                mock.patch.object(fixture, 'bounded_child', side_effect=spy):
            full.verify_client_interpreter(ROOT, path, full.digest(raw))
        self.assertEqual(seen, [full.CLIENT_WITNESS_SOURCE_SHA256])

    def test_whole136_interpreter_witness_and_standalone_match_projected_capture(self):
        from yadinassi import Interpreter
        from decimal import Decimal
        vm=Interpreter(lambda _:self.fail('unexpected Message'))
        vm.execute(full.infobase_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE)).decode('utf-8-sig'))
        actual=[int(v) if type(v) is Decimal else v for v in vm.execute('ВычислитьПробу()')]
        self.assertEqual(actual,full.CLIENT_VALUES)
        self.assertEqual(list(map(type,actual)),list(map(type,full.CLIENT_VALUES)))
        self.assertEqual(vm.execution_context,'client')
        vm=Interpreter(lambda _:self.fail('unexpected Message'))
        vm.execute(linux_fixture(ROOT/SOURCE).decode())
        self.assertEqual(list(vm.execute('CollectDualDirectiveProbe()')),PROJECTED)

    def test_combined_async_serializers_retain_caps_without_capture_fields(self):
        for early in (False,True):
            for case in (None,*range(8)):
                value=budget.majorant(early=early,marker_case=case)
                wire=budget.render_stage(value['stage3'])
                self.assertEqual(full.decode_stage3_wire(json.loads(wire)),value['stage3'])
                summary,_=budget.render_summary(value,error=True)
                self.assertIn('probe',json.loads(summary))
                self.assertNotIn('dual',value['stage3']['client_probe']['marker_diagnostics'])
                self.assertLessEqual(len(wire),8192)
                self.assertLessEqual(len(summary),32768)
        self.assertEqual((suite.MAX_STAGE_REPORT,full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,8192,32768))

    @unittest.skipIf(os.name=='nt','Linux descriptor security is not replaced by fixture reads')
    def test_symlink_and_oversized_private_markers_remain_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); path=root/'marker.json'
            path.write_bytes(json.dumps(marker(full.CLIENT_VALUES),separators=(',', ':')).encode())
            link=root/'link.json';link.symlink_to(path)
            for target in (link,):
                with self.assertRaises(suite.FullError):suite.client_marker(target,NONCE,'completed')
                self.assertEqual(suite.client_marker_diagnostics(target,NONCE)['phase'],'invalid')
            path.write_bytes(b' '*2049)
            with self.assertRaises(suite.FullError):suite.client_marker(path,NONCE,'completed')
            self.assertEqual(suite.client_marker_diagnostics(path,NONCE)['phase'],'invalid')

    def test_literal_digit_encoder_matches_fixed_width_schema_not_native_values(self):
        from yadinassi import Interpreter
        source = suite.CLIENT_DUAL_BLOCK.decode()
        start = source.index('&AtClient\nFunction DualProbeEncode')
        end = source.index('EndFunction',start)+len('EndFunction')
        encoder = source[start:end]
        self.assertNotIn('Format(',encoder)
        self.assertNotIn('JSONWriterSettings',linux_fixture(ROOT/full.CLIENT_SOURCE).decode())
        vm = Interpreter(lambda _: self.fail('unexpected Message'))
        vm.execute(encoder)
        for value in (0,1,9,10,15,16,99,100,999):
            values = [min(value,15),value,value]*3
            setup = 'Values = New Array;'+''.join('Values.Add('+str(x)+');' for x in values)
            vm.execute(setup)
            self.assertEqual(vm.execute('DualProbeEncode(Values)'),measured(values)[134])
        for literal in ('True','False','Undefined','"PRIVATE"','-1','1000','0.5'):
            vm.execute('Values = New Array;'+ 'Values.Add(0);'*9+'Values[1] = '+literal+';')
            with self.assertRaisesRegex(Exception, 'dual-directive-invalid'): vm.execute('DualProbeEncode(Values)')
        for slot in (0,3,6):
            vm.execute('Values = New Array;'+'Values.Add(0);'*9+f'Values[{slot}] = 16;')
            with self.assertRaisesRegex(Exception, 'dual-directive-invalid'): vm.execute('DualProbeEncode(Values)')
        for count in (0,8,10):
            vm.execute('Values = New Array;'+'Values.Add(0);'*count)
            with self.assertRaisesRegex(Exception, 'dual-directive-invalid'): vm.execute('DualProbeEncode(Values)')

    def test_mechanical_standalone_integration_has_no_semantic_rewrite(self):
        source = linux_fixture(ROOT/SOURCE)
        start = source.index(b'&AtServer\nVar')
        split = source.index('&НаКлиентеНаСервереБезКонтекста'.encode())
        prefix = b'// BEGIN bounded dual declarations\n'+source[start:split]+b'// END bounded dual declarations\n'
        appendix = b'\n&AtClient\nFunction DualProbeEncode(Observations)\n    Var Encoded, Observation, Slot, Digits, Hundreds, Tens, Units;\n    If Observations.Count() <> 9 Then\n        Raise "dual-directive-invalid-count";\n    EndIf;\n    Encoded = "dual.v1:";\n    Digits = "0123456789";\n    Slot = 0;\n    For Each Observation In Observations Do\n        If TypeOf(Observation) <> Type("Number") Then\n            Raise "dual-directive-invalid-type";\n        EndIf;\n        If Observation < 0 Or Observation > 999 Or Int(Observation) <> Observation Then\n            Raise "dual-directive-invalid-range";\n        EndIf;\n        If (Slot = 0 Or Slot = 3 Or Slot = 6) And Observation > 15 Then\n            Raise "dual-directive-invalid-profile";\n        EndIf;\n        Hundreds = Int(Observation / 100);\n        Tens = Int(Observation / 10) - Hundreds * 10;\n        Units = Observation - Int(Observation / 10) * 10;\n        Encoded = Encoded + Mid(Digits, Hundreds + 1, 1)\n            + Mid(Digits, Tens + 1, 1) + Mid(Digits, Units + 1, 1);\n        Slot = Slot + 1;\n    EndDo;\n    Return Encoded;\nEndFunction\n\n&AtClient\nProcedure DualProbeAppend(RecordsOut)\n    RecordsOut.Add(DualProbeEncode(CollectDualDirectiveProbe()));\nEndProcedure\n'
        self.assertEqual(suite.CLIENT_DUAL_PREFIX, prefix)
        self.assertEqual(suite.CLIENT_DUAL_BLOCK, b'\n// BEGIN bounded dual witness\n'+source[split:]+appendix)
        self.assertEqual(suite.CLIENT_DUAL_CALL, '    DualProbeAppend(Значения);\n'.encode())
        self.assertIn(b'&AtClientAtServerNoContext\nFunction DualProbeOperation',source)
        self.assertIn('&НаКлиентеНаСервереБезКонтекста\nProcedure DualProbeLeaf'.encode(),source)

    def test_all_new_locals_explicit_and_module_storage_annotated(self):
        source = (suite.CLIENT_DUAL_PREFIX+suite.CLIENT_DUAL_BLOCK).decode()
        self.assertIn('&AtServer\nVar DualProbeServerState;',source)
        routines = re.findall(r'(?:Function|Procedure) (\w+)\(([^)]*)\)(?: Export)?\n(.*?)End(?:Function|Procedure)', source, re.S)
        self.assertEqual(len(routines), 8)
        for name, formals, body in routines:
            declared = {v.strip().removeprefix('Val ').casefold() for v in formals.split(',') if v.strip()}
            for group in re.findall(r'^\s*Var ([^;]+);',body,re.M):
                declared.update(v.strip().casefold() for v in group.split(','))
            if name == 'DualProbeFromServer': declared.add('dualprobeserverstate')
            assigned = re.findall(r'^\s*(\w+)\s*=(?!=)',body,re.M)+re.findall(r'For Each (\w+) In',body)
            self.assertLessEqual({v.casefold() for v in assigned},declared,name)
        for name in ('DualProbeLeaf','DualProbeOperation'):
            body = next(body for routine,_,body in routines if routine==name)
            self.assertNotIn('DualProbeServerState',body)
            self.assertNotIn('ThisObject',body)

    def test_declarations_and_helpers_precede_module_initializer(self):
        raw = full.date_null_shared_source(full.infobase_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE)))
        tail = full.CLIENT_NOCONTEXT_INITIALIZER
        self.assertTrue(raw.startswith(suite.CLIENT_DUAL_PREFIX+full.CLIENT_MODULE_PREFIX))
        self.assertTrue(raw.endswith(full.CLIENT_NOCONTEXT_BLOCK+suite.CLIENT_DUAL_BLOCK+tail))
        self.assertEqual(raw.count(tail),1)
        self.assertLess(raw.index(b'Var DualProbeServerState;'),raw.index('Функция КонтекстПробы'.encode()))
        self.assertLess(raw.index(b'Function CollectDualDirectiveProbe'),raw.index(tail))
        self.assertLess(raw.index(b'Procedure DualProbeAppend'),raw.index(tail))
        self.assertNotRegex(tail.decode(),r'(?im)^\s*(?:Function|Procedure|Var|Функция|Процедура|Перем)\b')
        self.assertNotIn(tail,linux_fixture(ROOT/SOURCE))

    def test_three_historical_modules_and_current_collections_are_pinned(self):
        hashes = {'dates':'52b307cda539370ec0a7f5f28fbd22e0454934df2a287dcb2eb8e22f9f734d8e',
            'values':'814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824',
            # Collections now includes the source-only EXCLUDE measurement, not native parity.
            'collections':'b8d28abf2a28f7ff11958f9f3a31a966e3032484b8f0cf7d316b24ef8fb847e8',
            'numbers':'271be42fcb2df2ad497c5e8ba1edcfe94e24779f00820ba3a7191eddc60eb7f2'}
        raw = linux_fixture(ROOT/full.CLIENT_SOURCE)
        for name, expected in hashes.items():
            adapter = historical_tree_collections_module if name == 'collections' else getattr(suite, 'client_'+name+'_module')
            module = adapter(linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl'), raw)
            self.assertEqual(full.digest(module),expected)
            self.assertNotIn(b'DualProbe',module)


if __name__ == '__main__':
    unittest.main()

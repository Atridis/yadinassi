"""Finite native-only dual capture. Synthetic boundary values are NOT evidence."""
import copy
import inspect
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture
import test_native_async_budget as budget

NONCE = 'a' * 32
SOURCE = 'integrational_tests/directive_probes/dual_directive_core.bsl'
PLAN = 'integrational_tests/directive_probes/dual_directive_measurement.json'
BASE_SHA = 'b79c23abb756c3b3965e3a46ad7212e582db917ff319facc70a1efb18a470e14'
STANDALONE_SHA = '761b25578c9327dd3cf76a1f9ff81002c1c02d3e5df96f6c5616379a1058a345'


def marker(values):
    return dict(schema=1, nonce=NONCE, phase='completed', witness='client', values=values)


def measured(values):
    return full.CLIENT_VALUES + ['dual.v1:' + ''.join(f'{value:03d}' for value in values)]


class DualMeasurementTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start()
            self.addCleanup(patch.stop)

    def diagnose(self, value):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'completed.json'
            path.write_bytes(json.dumps(value, allow_nan=False).encode())
            with self.assertRaises(suite.FullError):
                suite.client_marker(path, NONCE, 'completed')
            return suite.client_marker_diagnostics(path, NONCE)

    def test_integer_boundaries_capture_but_never_accept(self):
        for values in ([0]*9, [15,999,999,15,999,999,15,999,999], list(range(9))):
            diagnostic = self.diagnose(marker(measured(values)))
            self.assertEqual(diagnostic, dict(phase='completed', kind='count', ordinal=134,
                                              error_stage=0, dual=values))
            full.validate_marker_diagnostics(diagnostic)
            self.assertLessEqual(len(json.dumps(marker(measured(values)), indent=2).encode()), 2048)
        self.assertEqual(len(full.CLIENT_VALUES), 134)
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)

    def test_original_strict134_still_accepts_without_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve()/'completed.json'
            value = marker(full.CLIENT_VALUES)
            path.write_bytes(json.dumps(value).encode())
            self.assertEqual(suite.client_marker(path,NONCE,'completed'),value)
            self.assertNotIn('dual',suite.client_marker_diagnostics(path,NONCE))

    def test_every_slot_rejects_noninteger_private_or_out_of_range_values(self):
        for index in range(9):
            for invalid in (False, True, None, 'U', 'PRIVATE', 0.0, -1, 1000, {}, []):
                values = [0]*9
                values[index] = invalid
                with self.assertRaises(ValueError):
                    full.validate_marker_diagnostics(dict(phase='completed', kind='count',
                        ordinal=134, error_stage=0, dual=values))

    def test_dense_token_rejects_noncanonical_or_private_input(self):
        good = 'dual.v1:'+'000'*9
        tokens = [good[:-1], good+'0', good.replace('dual.v1:', 'dual.v2:'),
                  good+'PRIVATE', 'PRIVATE', 'dual.v1:'+'٠'*27,
                  'dual.v1:'+'0|0|0|0|0|0|0|0|0', 'dual.v1:'+'-01'*9,
                  'dual.v1:'+'1.0'*9, 'dual.v1:'+'999'*9, good+'\n',
                  False, True, 0, 999, None, [], {}]
        for token in tokens:
            self.assertNotIn('dual',self.diagnose(marker(full.CLIENT_VALUES+[token])))
        for slot in (0,3,6):
            values = [0]*9
            values[slot] = 16
            self.assertNotIn('dual',self.diagnose(marker(measured(values))))

    def test_literal_digit_encoder_matches_fixed_width_schema_not_native_values(self):
        from yadinassi import Interpreter
        source = full.CLIENT_DUAL_BLOCK.decode()
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
            self.assertEqual(vm.execute('DualProbeEncode(Values)'),measured(values)[-1])
        for literal in ('True','False','Undefined','"PRIVATE"','-1','1000','0.5'):
            vm.execute('Values = New Array;'+ 'Values.Add(0);'*9+'Values[1] = '+literal+';')
            with self.assertRaisesRegex(Exception, 'dual-directive-invalid'): vm.execute('DualProbeEncode(Values)')
        for slot in (0,3,6):
            vm.execute('Values = New Array;'+'Values.Add(0);'*9+f'Values[{slot}] = 16;')
            with self.assertRaisesRegex(Exception, 'dual-directive-invalid'): vm.execute('DualProbeEncode(Values)')
        for count in (0,8,10):
            vm.execute('Values = New Array;'+'Values.Add(0);'*count)
            with self.assertRaisesRegex(Exception, 'dual-directive-invalid'): vm.execute('DualProbeEncode(Values)')

    def test_partial_extra_and_wrong_label_or_baseline_are_not_exported(self):
        values = measured([0]*9)
        variants = [values[:-2], values+[0], full.CLIENT_VALUES+['wrong']]
        for index in range(134):
            changed = list(values)
            changed[index] = not changed[index] if type(changed[index]) is bool else None
            variants.append(changed)
        for value in variants:
            self.assertNotIn('dual', self.diagnose(marker(value)))

    def test_nonce_phase_schema_and_witness_must_match(self):
        good = marker(measured([0]*9))
        for updates in ({'nonce':'b'*32}, {'nonce':None}, {'phase':'error'},
                        {'phase':'entered'}, {'witness':'server'}, {'schema':True},
                        {'schema':2}, {'private':'PRIVATE'}):
            self.assertNotIn('dual', self.diagnose({**good, **updates}))

    def test_capture_allowed_only_for_exact_failure_diagnostic_shape(self):
        good = dict(phase='completed', kind='count', ordinal=134, error_stage=0, dual=[0]*9)
        for changes in ({'phase':'error'}, {'kind':'none'}, {'kind':'value'},
                        {'ordinal':133}, {'ordinal':135}, {'error_stage':1},
                        {'dual':[0]*8}, {'dual':[0]*10}, {'dual':tuple([0]*9)},
                        {'private':'PRIVATE'}, {'nocontext':[0]*14}):
            with self.assertRaises(ValueError):
                full.validate_marker_diagnostics({**good, **changes})

    def test_source_plan_is_uncaptured_not_an_expected_vector(self):
        plan = json.loads((ROOT/PLAN).read_text())
        source = linux_fixture(ROOT/SOURCE)
        self.assertEqual(full.digest(source), STANDALONE_SHA)
        self.assertEqual(plan['source_sha256'], STANDALONE_SHA)
        self.assertEqual(plan['integrated_source_sha256'], full.digest(linux_fixture(ROOT/full.CLIENT_SOURCE)))
        self.assertEqual(plan['integrated_module_sha256'], full.digest(full.generated_module(linux_fixture(ROOT/full.CLIENT_SOURCE))))
        self.assertIsNone(plan['native_values'])
        self.assertIsNone(plan['boundedness']['accepted_native_values'])
        self.assertEqual(plan['record_count'], 9)
        self.assertEqual(len(set(plan['labels'])), 9)
        self.assertEqual(plan['status'], 'uncaptured_native_only_measurement')

    def test_exact_shared_inverse_restores_complete_strict134(self):
        raw = linux_fixture(ROOT/full.CLIENT_SOURCE)
        restored = full.dual_shared_source(raw)
        self.assertEqual(restored, suite.dual_shared_source(raw))
        self.assertEqual(full.digest(restored), BASE_SHA)
        self.assertEqual(inspect.getsource(full.dual_shared_source), inspect.getsource(suite.dual_shared_source))
        for name in ('CLIENT_DUAL_TEMPLATE_SHA256','CLIENT_DUAL_SHARED_SHA256',
                     'CLIENT_DUAL_PREFIX','CLIENT_DUAL_BLOCK','CLIENT_DUAL_CALL'):
            self.assertEqual(getattr(full,name), getattr(suite,name))
        mutations = (raw+b' ', raw[:-1], restored,
            raw.replace(full.CLIENT_DUAL_PREFIX,b'',1),
            raw.replace(full.CLIENT_DUAL_CALL,b'',1),
            raw.replace(b'ReferenceValue + 10',b'ReferenceValue + 11',1),
            raw.replace(b'ContextServerCounter = 100;',b'ContextServerCounter = 101;',1),
            raw.replace(full.CLIENT_DUAL_BLOCK,b'',1)+full.CLIENT_DUAL_BLOCK,
            raw.replace(full.CLIENT_DUAL_BLOCK,full.CLIENT_DUAL_BLOCK*2,1))
        for changed in mutations:
            for inverse, error in ((full.dual_shared_source,full.FullError),
                                   (suite.dual_shared_source,suite.FullError)):
                with self.assertRaises(error): inverse(changed)

    def test_mechanical_standalone_integration_has_no_semantic_rewrite(self):
        source = linux_fixture(ROOT/SOURCE)
        start = source.index(b'&AtServer\nVar')
        split = source.index('&НаКлиентеНаСервереБезКонтекста'.encode())
        prefix = b'// BEGIN bounded dual declarations\n'+source[start:split]+b'// END bounded dual declarations\n'
        appendix = b'\n&AtClient\nFunction DualProbeEncode(Observations)\n    Var Encoded, Observation, Slot, Digits, Hundreds, Tens, Units;\n    If Observations.Count() <> 9 Then\n        Raise "dual-directive-invalid-count";\n    EndIf;\n    Encoded = "dual.v1:";\n    Digits = "0123456789";\n    Slot = 0;\n    For Each Observation In Observations Do\n        If TypeOf(Observation) <> Type("Number") Then\n            Raise "dual-directive-invalid-type";\n        EndIf;\n        If Observation < 0 Or Observation > 999 Or Int(Observation) <> Observation Then\n            Raise "dual-directive-invalid-range";\n        EndIf;\n        If (Slot = 0 Or Slot = 3 Or Slot = 6) And Observation > 15 Then\n            Raise "dual-directive-invalid-profile";\n        EndIf;\n        Hundreds = Int(Observation / 100);\n        Tens = Int(Observation / 10) - Hundreds * 10;\n        Units = Observation - Int(Observation / 10) * 10;\n        Encoded = Encoded + Mid(Digits, Hundreds + 1, 1)\n            + Mid(Digits, Tens + 1, 1) + Mid(Digits, Units + 1, 1);\n        Slot = Slot + 1;\n    EndDo;\n    Return Encoded;\nEndFunction\n\n&AtClient\nProcedure DualProbeAppend(RecordsOut)\n    RecordsOut.Add(DualProbeEncode(CollectDualDirectiveProbe()));\nEndProcedure\n'
        self.assertEqual(full.CLIENT_DUAL_PREFIX, prefix)
        self.assertEqual(full.CLIENT_DUAL_BLOCK, b'\n// BEGIN bounded dual measurement\n'+source[split:]+appendix)
        self.assertEqual(full.CLIENT_DUAL_CALL, '    DualProbeAppend(Значения);\n'.encode())
        self.assertIn(b'&AtClientAtServerNoContext\nFunction DualProbeOperation',source)
        self.assertIn('&НаКлиентеНаСервереБезКонтекста\nProcedure DualProbeLeaf'.encode(),source)

    def test_all_new_locals_explicit_and_module_storage_annotated(self):
        source = (full.CLIENT_DUAL_PREFIX+full.CLIENT_DUAL_BLOCK).decode()
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
        raw = linux_fixture(ROOT/full.CLIENT_SOURCE)
        tail = full.CLIENT_NOCONTEXT_INITIALIZER
        self.assertTrue(raw.startswith(full.CLIENT_DUAL_PREFIX+full.CLIENT_MODULE_PREFIX))
        self.assertTrue(raw.endswith(full.CLIENT_NOCONTEXT_BLOCK+full.CLIENT_DUAL_BLOCK+tail))
        self.assertEqual(raw.count(tail),1)
        self.assertLess(raw.index(b'Var DualProbeServerState;'),raw.index('Функция КонтекстПробы'.encode()))
        self.assertLess(raw.index(b'Function CollectDualDirectiveProbe'),raw.index(tail))
        self.assertLess(raw.index(b'Procedure DualProbeAppend'),raw.index(tail))
        self.assertNotRegex(tail.decode(),r'(?im)^\s*(?:Function|Procedure|Var|Функция|Процедура|Перем)\b')
        self.assertNotIn(tail,linux_fixture(ROOT/SOURCE))

    def test_all_four_historical_modules_remain_exact(self):
        hashes = {'dates':'52b307cda539370ec0a7f5f28fbd22e0454934df2a287dcb2eb8e22f9f734d8e',
            'values':'814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824',
            'collections':'225d4f9d617872d821fcfcbe18c4bad7a0b2e43dda54aad6b9dbb02e7b3f01f0',
            'numbers':'271be42fcb2df2ad497c5e8ba1edcfe94e24779f00820ba3a7191eddc60eb7f2'}
        raw = linux_fixture(ROOT/full.CLIENT_SOURCE)
        for name, expected in hashes.items():
            module = getattr(suite,'client_'+name+'_module')(linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl'),raw)
            self.assertEqual(full.digest(module),expected)
            self.assertNotIn(b'DualProbe',module)

    @unittest.skipIf(os.name=='nt','production bounded interpreter child is POSIX-only')
    def test_exact_preflight_runs_only_restored134_in_real_child(self):
        raw = linux_fixture(ROOT/full.CLIENT_SOURCE)
        observed = []
        def runner(arguments, cwd):
            restored = Path(arguments[-1]).read_bytes()
            observed.append(full.digest(restored))
            self.assertNotIn(b'DualProbe',restored)
            return full.bounded_child(arguments,cwd)
        full.verify_client_interpreter(ROOT,ROOT/full.CLIENT_SOURCE,full.digest(raw),runner=runner)
        self.assertEqual(observed,[BASE_SHA])

    def test_diagnostic_cannot_turn_failure_into_success(self):
        report, inputs, modules = budget.stage(suite.empty_async_report())
        report.update(status='failed',failure_kind='invalid_result')
        client = report['client_probe']
        client.update(status='failed',failure_kind='invalid_result',witness_verified=False,
                      marker_diagnostics=budget.maximum_dual_marker_diagnostics())
        full.validate_stage3(json.loads(budget.render_stage(report)),budget.NONCE,inputs,modules,
                             prerequisites=True,client_async=True)
        for change in ({'status':'ok'},{'failure_kind':'none'},{'witness_verified':True}):
            changed = copy.deepcopy(report)
            changed['client_probe'].update(change)
            with self.assertRaises(ValueError):
                full.validate_stage3(json.loads(budget.render_stage(changed)),budget.NONCE,inputs,modules,
                                     prerequisites=True,client_async=True)
        result = budget.probe(suite.empty_async_report())
        result['stage3'] = report
        raw, code = budget.render_summary(result)
        public = json.loads(raw)
        self.assertEqual(code,1)
        self.assertFalse(public['client_async_measurement_completed'])
        self.assertFalse(public['client_async_parity_claimed'])
        self.assertEqual(public['probe']['stage3']['client_probe']['marker_diagnostics']['dual'],[15,999,999,15,999,999,15,999,999])
        with self.assertRaises(full.FullError):
            full.output_artifact_files(dict.fromkeys(full.ARTIFACT_FILES[:-1],b''),result,budget.smoke.IMAGE)

    def test_combined_async_serializers_cover_both_diagnostic_shapes(self):
        for early in (False,True):
            for case in (None,*range(8)):
                for dual in (False,True):
                    value = budget.majorant(early=early,marker_case=case,dual_capture=dual)
                    wire = budget.render_stage(value['stage3'])
                    self.assertEqual(full.decode_stage3_wire(json.loads(wire)),value['stage3'])
                    summary,_ = budget.render_summary(value,error=True)
                    self.assertIn('probe',json.loads(summary))
                    self.assertLessEqual(len(wire),8192)
                    self.assertLessEqual(len(summary),32768)
        self.assertEqual((suite.MAX_STAGE_REPORT,full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,8192,32768))

    @unittest.skipIf(os.name=='nt','Linux descriptor security is not replaced by fixture reads')
    def test_symlink_and_oversized_private_marker_never_export_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            path = root/'marker.json'
            path.write_bytes(json.dumps(marker(measured([0]*9))).encode())
            link = root/'link.json'
            link.symlink_to(path)
            self.assertNotIn('dual',suite.client_marker_diagnostics(link,NONCE))
            path.write_bytes(b' '*2049)
            self.assertNotIn('dual',suite.client_marker_diagnostics(path,NONCE))


if __name__ == '__main__':
    unittest.main()

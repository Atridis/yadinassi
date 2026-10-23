"""Finite NoContext measurement only; no native expected values or runtime parity."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock
from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture

class NoContextMeasurementTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start(); self.addCleanup(patch.stop)

    def marker(self, values):
        return dict(schema=1, nonce='a'*32, phase='completed', witness='client', values=values)

    def test_finite_capture_and_strict_rejection(self):
        for item in (False, True, 0, 999, 'U'):
            value = self.marker(full.CLIENT_VALUES + ['nocontext.core.v2'] + [item,item,63]+[item]*11)
            with tempfile.TemporaryDirectory() as folder:
                p = Path(folder).resolve()/'completed.json'
                p.write_bytes(json.dumps(value).encode())
                with self.assertRaises(suite.FullError): suite.client_marker(p, 'a'*32, 'completed')
                observed = suite.client_marker_diagnostics(p, 'a'*32)
                self.assertEqual(observed, dict(phase='completed', kind='count', ordinal=119,
                    error_stage=0, nocontext=[None if item == 'U' else item]*2+[63]+[None if item == 'U' else item]*11))
                full.validate_marker_diagnostics(observed)
            self.assertLessEqual(len(json.dumps(value, indent=2).encode()), 2048)

    def test_malformed_partial_or_unbound_values_are_not_exported(self):
        valid = full.CLIENT_VALUES + ['nocontext.core.v2'] + [False,False,63]+[False]*11
        changed_prefix = list(valid); changed_prefix[0] = 43
        for values in (valid[:-1], valid+[False], changed_prefix,
                       valid[:-1]+['PRIVATE'], valid[:-1]+[1000], valid[:-1]+[-1],
                       valid[:-1]+[0.5], valid[:-1]+[None], valid[:-1]+[{}],
                       valid[:122]+[False]+valid[123:], valid[:122]+[64]+valid[123:]):
            with tempfile.TemporaryDirectory() as folder:
                p = Path(folder).resolve()/'completed.json'; p.write_bytes(json.dumps(self.marker(values)).encode())
                self.assertNotIn('nocontext', suite.client_marker_diagnostics(p, 'a'*32))
        for records in ([False]*13, [False]*15, [True]*13+[1000], [True]*13+['PRIVATE'], [False]*14, [False,False,64]+[False]*11):
            with self.assertRaises(ValueError): full.validate_marker_diagnostics(dict(
                phase='completed', kind='count', ordinal=119, error_stage=0, nocontext=records))

    def test_inverse_restores_exact_audited119(self):
        raw = linux_fixture(ROOT/full.CLIENT_SOURCE)
        restored = full.nocontext_shared_source(raw)
        self.assertEqual(restored, suite.nocontext_shared_source(raw))
        self.assertEqual(full.digest(restored), 'a3e4fd9b809013b1d704a6a7af5b77353e04a129f3a0cd0ca3a40692458c1e17')
        for bad in (raw+b' ', raw[:-1], raw.replace(b'Value = Value + 10;', b'Value = Value + 11;')):
            with self.assertRaises(full.FullError): full.nocontext_shared_source(bad)
        self.assertEqual(len(full.CLIENT_VALUES), 119)
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT), (8192,8192,32768))

    @unittest.skipIf(os.name=='nt', 'production bounded interpreter child is POSIX-only')
    def test_restored119_interpreter_preflight(self):
        raw=linux_fixture(ROOT/full.CLIENT_SOURCE)
        full.verify_client_interpreter(ROOT, ROOT/full.CLIENT_SOURCE, full.digest(raw))

    def test_mechanical_source_adapter_and_explicit_locals(self):
        source=(ROOT/'integrational_tests/directive_probes/nocontext_core.bsl').read_text()
        helpers=source[source.index('&AtServerNoContext'):]
        helpers=helpers.replace('Procedure NoContextRecord(Val Label, Val Value)',
            'Procedure NoContextRecord(Records, Val Label, Val Value)').replace(
            'Message("nocontext.core." + Label + ": " + ValueToStringInternal(Value));',
            'If Value = Undefined Then\n        Records.Add("U");\n    Else\n        Records.Add(Value);\n    EndIf;').replace(
            'Procedure RunNoContextProbe() Export','Function RunNoContextProbe()').replace(
            '    Var Value, PrivateValue, Result, Failed, Matched, Nested;',
            '    Var Records, Value, PrivateValue, Result, Failed, Matched, Nested;\n    Records = New Array;\n    Records.Add("nocontext.core.v2");').replace(
            '    NoContextRecord("','    NoContextRecord(Records, "').rstrip()
        self.assertTrue(helpers.endswith('EndProcedure'))
        helpers=helpers[:-len('EndProcedure')]+'    Return Records;\nEndFunction\n'
        append='&AtClient\nProcedure NoContextAppend(RecordsOut)\n    Var NoContextValue;\n    For Each NoContextValue In RunNoContextProbe() Do\n        RecordsOut.Add(NoContextValue);\n    EndDo;\nEndProcedure\n'
        self.assertEqual(full.CLIENT_NOCONTEXT_BLOCK, ('\n// BEGIN bounded no-context measurement\n'+helpers+'\n'+append).encode())
        labels=re.findall(r'NoContextRecord\("([^"]+)"', source)
        self.assertEqual(len(labels),14); self.assertEqual(len(set(labels)),14)
        for name, formals, body in re.findall(r'(?:Function|Procedure) (\w+)\(([^)]*)\)(?: Export)?\n(.*?)End(?:Function|Procedure)', full.CLIENT_NOCONTEXT_BLOCK.decode(), re.S):
            declared={v.strip().removeprefix('Val ').casefold() for v in formals.split(',') if v.strip()}
            for group in re.findall(r'^\s*Var ([^;]+);',body,re.M): declared.update(v.strip().casefold() for v in group.split(','))
            assignments=re.findall(r'^\s*(\w+)\s*=(?!=)',body,re.M)+re.findall(r'For Each (\w+) In',body)
            self.assertTrue(all(v.casefold() in declared for v in assignments),name)

    def test_declarations_precede_the_unchanged_module_initializer_tail(self):
        raw=linux_fixture(ROOT/full.CLIENT_SOURCE)
        tail=full.CLIENT_NOCONTEXT_INITIALIZER
        self.assertTrue(raw.endswith(full.CLIENT_NOCONTEXT_BLOCK+tail))
        self.assertTrue(full.nocontext_shared_source(raw).endswith(tail))
        # No procedure/function declaration may follow the first module-body
        # assignment. This catches the invalid append-after-initializer layout.
        self.assertNotRegex(tail.decode(), r'(?im)^\s*(?:Function|Procedure|Функция|Процедура)\b')
        self.assertLess(raw.index(b'Function NoContextOperation'),raw.index(tail))
        self.assertLess(raw.index(b'Procedure NoContextAppend'),raw.index(tail))
        self.assertEqual(raw.count(tail),1)

    def test_six_flags_are_independent_and_mask_bounds_are_typed(self):
        source=(ROOT/'integrational_tests/directive_probes/nocontext_core.bsl').read_text()
        names=('Client','Server','AtClient','AtServer','ThickClientManagedApplication','ThickClientOrdinaryApplication')
        for bit,name in enumerate(names):
            self.assertEqual(source.count('#If '+name+' Then\n    ProfileMask = ProfileMask + '+str(2**bit)+';\n#EndIf'),1)
        self.assertNotIn('#If AtServerNoContext',source)
        for mask in range(64):
            full.validate_marker_diagnostics(dict(phase='completed',kind='count',ordinal=119,error_stage=0,nocontext=[False,False,mask]+[False]*11))

    def test_legacy_module_bytes_match_audited_main(self):
        hashes={'dates':'52b307cda539370ec0a7f5f28fbd22e0454934df2a287dcb2eb8e22f9f734d8e',
            'values':'814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824',
            'collections':'225d4f9d617872d821fcfcbe18c4bad7a0b2e43dda54aad6b9dbb02e7b3f01f0',
            'numbers':'271be42fcb2df2ad497c5e8ba1edcfe94e24779f00820ba3a7191eddc60eb7f2'}
        for name, expected in hashes.items():
            actual=getattr(suite,'client_'+name+'_module')(linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl'),linux_fixture(ROOT/full.CLIENT_SOURCE))
            self.assertEqual(full.digest(actual),expected)

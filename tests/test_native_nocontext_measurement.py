"""Historical NoContext capture and current exact whole-source witness."""
import json
import os
import sys
from pathlib import Path
import re
import tempfile
import unittest
from test_native_async_fixture import historical_tree_collections_module
from unittest import mock
from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture

class NoContextWitnessTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start(); self.addCleanup(patch.stop)

    def marker(self, values):
        return dict(schema=1, nonce='a'*32, phase='completed', witness='client', values=values)

    def test_captured_profile_projection_preserves_other_thirteen_values(self):
        capture=json.loads((ROOT/'integrational_tests/directive_probes/nocontext_native.json').read_text())
        raw=suite.dual_shared_source(full.date_null_shared_source(full.infobase_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE))))
        logical=b"#If AtClient Then\n    ProfileMask = ProfileMask + 1;\n#EndIf\n#If AtServer Then\n    ProfileMask = ProfileMask + 2;\n#EndIf"
        historical=b"\n".join(("#If %s Then\n    ProfileMask = ProfileMask + %s;\n#EndIf" % (name, bit)).encode()
            for name,bit in capture['profile_bits'].items())
        self.assertEqual(raw.count(logical),1)
        restored=raw.replace(logical,historical,1).replace(b'nocontext.core.v3',b'nocontext.core.v2',1).replace(
            b'// BEGIN bounded no-context witness',b'// BEGIN bounded no-context measurement',1)
        self.assertEqual(full.digest(restored),capture['source_sha256'])
        self.assertEqual(full.digest(full.generated_module(restored)),capture['module_sha256'])
        expected=list(capture['values'])
        self.assertEqual(expected[2],19)
        expected[2]=(1 if expected[2]&capture['profile_bits']['AtClient'] else 0) + (2 if expected[2]&capture['profile_bits']['AtServer'] else 0)
        self.assertEqual(full.CLIENT_VALUES[120:134],expected)
        self.assertEqual(capture['capture_acceptance'],'rejected_measurement_only')
        self.assertNotEqual(full.digest(raw),capture['source_sha256'])

    def test_strict136_typed_acceptance_and_no_raw_capture_export(self):
        self.assertEqual(full.CLIENT_VALUES[119:134], ['nocontext.core.v3', 12, 22, 0,
            12, 2, True, 16, True, 6, 14, 14, True, 7, 18])
        variants=[list(full.CLIENT_VALUES), full.CLIENT_VALUES[:-1], full.CLIENT_VALUES+[False]]
        for index in range(119,134):
            changed=list(full.CLIENT_VALUES)
            changed[index] = int(changed[index]) if type(changed[index]) is bool else (False if type(changed[index]) is int else 'wrong')
            variants.append(changed)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'completed.json'
            for index,values in enumerate(variants):
                p.write_bytes(json.dumps(self.marker(values),separators=(',', ':')).encode())
                if index == 0:
                    suite.client_marker(p,'a'*32,'completed')
                else:
                    with self.assertRaises(suite.FullError): suite.client_marker(p,'a'*32,'completed')
                diagnostic=suite.client_marker_diagnostics(p,'a'*32)
                self.assertNotIn('nocontext',diagnostic)
                full.validate_marker_diagnostics(diagnostic)
        self.assertLessEqual(len(json.dumps(self.marker(full.CLIENT_VALUES),separators=(',', ':')).encode()),2048)

    def test_removed_measurement_schema_is_rejected(self):
        with self.assertRaises(ValueError): full.validate_marker_diagnostics(dict(
            phase='completed',kind='count',ordinal=134,error_stage=0,nocontext=[False]*14))

    def test_inverse_restores_exact_audited119(self):
        raw = suite.dual_shared_source(full.date_null_shared_source(full.infobase_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE))))
        restored = full.nocontext_shared_source(raw)
        self.assertEqual(restored, suite.nocontext_shared_source(raw))
        self.assertEqual(full.digest(restored), 'a3e4fd9b809013b1d704a6a7af5b77353e04a129f3a0cd0ca3a40692458c1e17')
        for bad in (raw+b' ', raw[:-1], raw.replace(b'Value = Value + 10;', b'Value = Value + 11;')):
            with self.assertRaises(full.FullError): full.nocontext_shared_source(bad)
        self.assertEqual(len(full.CLIENT_VALUES), 136)
        self.assertEqual(full.CLIENT_VALUES[135:], ['dn.v1:22222277'])
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT), (8192,8192,32768))

    @unittest.skipUnless(sys.platform == 'linux', 'fixed native fixture is Linux-only')
    def test_whole_source137_interpreter_preflight(self):
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
            '    Var Records, Value, PrivateValue, Result, Failed, Matched, Nested;\n    Records = New Array;\n    Records.Add("nocontext.core.v3");').replace(
            '    NoContextRecord("','    NoContextRecord(Records, "').rstrip()
        self.assertTrue(helpers.endswith('EndProcedure'))
        helpers=helpers[:-len('EndProcedure')]+'    Return Records;\nEndFunction\n'
        append='&AtClient\nProcedure NoContextAppend(RecordsOut)\n    Var NoContextValue;\n    For Each NoContextValue In RunNoContextProbe() Do\n        RecordsOut.Add(NoContextValue);\n    EndDo;\nEndProcedure\n'
        self.assertEqual(full.CLIENT_NOCONTEXT_BLOCK, ('\n// BEGIN bounded no-context witness\n'+helpers+'\n'+append).encode())
        labels=re.findall(r'NoContextRecord\("([^"]+)"', source)
        self.assertEqual(len(labels),14); self.assertEqual(len(set(labels)),14)
        for name, formals, body in re.findall(r'(?:Function|Procedure) (\w+)\(([^)]*)\)(?: Export)?\n(.*?)End(?:Function|Procedure)', full.CLIENT_NOCONTEXT_BLOCK.decode(), re.S):
            declared={v.strip().removeprefix('Val ').casefold() for v in formals.split(',') if v.strip()}
            for group in re.findall(r'^\s*Var ([^;]+);',body,re.M): declared.update(v.strip().casefold() for v in group.split(','))
            assignments=re.findall(r'^\s*(\w+)\s*=(?!=)',body,re.M)+re.findall(r'For Each (\w+) In',body)
            self.assertTrue(all(v.casefold() in declared for v in assignments),name)

    def test_declarations_precede_the_unchanged_module_initializer_tail(self):
        raw=suite.dual_shared_source(full.date_null_shared_source(full.infobase_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE))))
        tail=full.CLIENT_NOCONTEXT_INITIALIZER
        self.assertTrue(raw.endswith(full.CLIENT_NOCONTEXT_BLOCK+tail))
        self.assertTrue(full.nocontext_shared_source(raw).endswith(tail))
        # No procedure/function declaration may follow the first module-body
        # assignment. This catches the invalid append-after-initializer layout.
        self.assertNotRegex(tail.decode(), r'(?im)^\s*(?:Function|Procedure|Функция|Процедура)\b')
        self.assertLess(raw.index(b'Function NoContextOperation'),raw.index(tail))
        self.assertLess(raw.index(b'Procedure NoContextAppend'),raw.index(tail))
        self.assertEqual(raw.count(tail),1)

    def test_only_logical_flags_are_compared(self):
        source=(ROOT/'integrational_tests/directive_probes/nocontext_core.bsl').read_text()
        for bit,name in enumerate(('AtClient','AtServer')):
            self.assertEqual(source.count('#If '+name+' Then\n    ProfileMask = ProfileMask + '+str(2**bit)+';\n#EndIf'),1)
        for name in ('Client','Server','ThickClientManagedApplication','ThickClientOrdinaryApplication','AtServerNoContext'):
            self.assertNotIn('#If '+name+' Then',source)

    def test_legacy_modules_and_source_only_collections_are_pinned(self):
        hashes={'dates':'52b307cda539370ec0a7f5f28fbd22e0454934df2a287dcb2eb8e22f9f734d8e',
            'values':'814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824',
            # Collections now includes the source-only EXCLUDE measurement, not native parity.
            'collections':'b8d28abf2a28f7ff11958f9f3a31a966e3032484b8f0cf7d316b24ef8fb847e8',
            'numbers':'271be42fcb2df2ad497c5e8ba1edcfe94e24779f00820ba3a7191eddc60eb7f2'}
        for name, expected in hashes.items():
            adapter = historical_tree_collections_module if name == 'collections' else getattr(suite, 'client_'+name+'_module')
            actual = adapter(linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl'), linux_fixture(ROOT/full.CLIENT_SOURCE))
            self.assertEqual(full.digest(actual),expected)

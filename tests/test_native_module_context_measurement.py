"""Audited side-local module-variable capture and strict whole-source parity."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock
from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture

class ModuleContextParityTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            p=mock.patch.object(suite,'secure_bytes',new=stage_fixture.portable_fixture_bytes)
            p.start();self.addCleanup(p.stop)
    def test_capture_identity_and_full_contract(self):
        capture=json.loads((ROOT/'integrational_tests/directive_probes/module_context_native.json').read_text())
        raw=full.nocontext_shared_source(suite.dual_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE)))
        self.assertEqual(full.digest(raw),capture['source_sha256'])
        self.assertEqual(full.digest(full.generated_module(raw)),capture['module_sha256'])
        self.assertEqual(full.CLIENT_VALUES[109:119],['module.context.v1']+capture['values'])
        self.assertEqual(full.CLIENT_VALUES,suite.CLIENT_VALUES)
        self.assertEqual(len(full.CLIENT_VALUES),135)
        from yadinassi import Interpreter
        from decimal import Decimal
        vm=Interpreter(lambda _: self.fail('unexpected output'))
        vm.execute(linux_fixture(ROOT/full.CLIENT_SOURCE).decode('utf-8-sig'))
        actual=[int(v) if type(v) is Decimal else v for v in vm.execute('ВычислитьПробу()')]
        self.assertEqual(actual,full.CLIENT_VALUES)
        self.assertEqual([type(v) for v in actual],[type(v) for v in full.CLIENT_VALUES])

    @unittest.skipIf(os.name=='nt','bounded native preflight is POSIX-only')
    def test_full_source_preflight_and_changed_initializer_rejection(self):
        raw=linux_fixture(ROOT/full.CLIENT_SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'source.bsl';p.write_bytes(raw)
            full.verify_client_interpreter(ROOT,p,full.digest(raw))
            changed=raw.replace(b'ContextServerCounter = 100;',b'ContextServerCounter = 101;')
            self.assertNotEqual(raw,changed);p.write_bytes(changed)
            with self.assertRaisesRegex(full.FullError,'^source_changed$'):
                full.verify_client_interpreter(ROOT,p,full.digest(changed))

    def test_strict_typed_contract_and_removed_capture_metadata(self):
        marker=dict(schema=1,nonce='a'*32,phase='completed',witness='client',values=suite.CLIENT_VALUES)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'completed.json';p.write_bytes(json.dumps(marker).encode())
            self.assertEqual(suite.client_marker(p,'a'*32,'completed'),marker)
            for index in range(109,119):
                values=list(suite.CLIENT_VALUES);v=values[index]
                values[index]=not v if type(v) is bool else (v+1 if type(v) is int else 'changed')
                p.write_bytes(json.dumps({**marker,'values':values}).encode())
                with self.assertRaises(suite.FullError):suite.client_marker(p,'a'*32,'completed')
                self.assertEqual(suite.client_marker_diagnostics(p,'a'*32)['ordinal'],index)
        with self.assertRaises(ValueError):
            full.validate_marker_diagnostics(dict(phase='completed',kind='count',ordinal=109,error_stage=0,module_context=[False]*9))
        self.assertLess(len(json.dumps(marker,indent=2).encode()),2048)
        self.assertEqual((suite.MAX_STAGE_REPORT,full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,8192,32768))

    def test_exact_three_part_inverse_preserves_audited_object_source(self):
        raw=full.nocontext_shared_source(suite.dual_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE)))
        restored=full.module_context_shared_source(raw)
        self.assertEqual(restored,suite.module_context_shared_source(raw))
        self.assertEqual(full.digest(restored),'6e29d85372e623c412e0662ad7514fbc76963fb5bd42bde6a100a4b5c7a2b120')
        self.assertEqual(full.digest(suite.client_parity_template(linux_fixture(ROOT/full.CLIENT_SOURCE))),
            '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        for changed in (raw+b' ',raw[:-1],raw.replace(b'ContextServerCounter = 100;',b'ContextServerCounter = 101;'),
                        raw.replace(full.CLIENT_MODULE_PREFIX,b'',1)):
            with self.assertRaises(full.FullError):full.module_context_shared_source(changed)
    def test_exact_mechanical_module_source_adapter_and_explicit_locals(self):
        source=(ROOT/'integrational_tests/directive_probes/module_context_core.bsl').read_text(encoding='utf-8')
        prefix=source[source.index('&AtClient\nVar'):source.index('&AtServer\nFunction')]
        prefix='// BEGIN bounded module context declarations\n'+prefix+'// END bounded module context declarations\n'
        self.assertEqual(full.CLIENT_MODULE_PREFIX,prefix.encode())
        helpers=source[source.index('&AtServer\nFunction'):source.index('// Initialization runs')]
        helpers=helpers.replace('Procedure ContextModuleRecord(Val Label, Val Value)',
            'Procedure ContextModuleRecord(Records, Val Label, Val Value)').replace(
            'Message("module.context.core." + Label + ": " + ValueToStringInternal(Value));',
            'If Value = Undefined Then\n        Records.Add("U");\n    Else\n        Records.Add(Value);\n    EndIf;').replace(
            'Procedure RunModuleContextProbe() Export','Function RunModuleContextProbe()').replace(
            '    Var First, Second, Third, Failed, Matched;',
            '    Var Records, First, Second, Third, Failed, Matched;\n    Records = New Array;\n    Records.Add("module.context.v1");').replace(
            '    ContextModuleRecord("','    ContextModuleRecord(Records, "').rstrip()
        self.assertTrue(helpers.endswith('EndProcedure'))
        helpers=helpers[:-len('EndProcedure')]+'    Return Records;\nEndFunction\n'
        append='&AtClient\nProcedure ContextModuleAppend(RecordsOut)\n    Var ModuleContextValue;\n    For Each ModuleContextValue In RunModuleContextProbe() Do\n        RecordsOut.Add(ModuleContextValue);\n    EndDo;\nEndProcedure\n'
        self.assertEqual(full.CLIENT_MODULE_SUFFIX,('\n// BEGIN bounded module context measurement\n'+helpers+'\n'+append+'\n'+source[source.index('// Initialization runs'):]).encode())
        labels=re.findall(r'ContextModuleRecord\("([^"]+)"',source)
        self.assertEqual(len(labels),9);self.assertEqual(len(set(labels)),9)
        self.assertEqual(source.count('ContextModuleCall(False);'),3)
        self.assertEqual(source.count('ContextModuleCall(True);'),1)
        self.assertIn('Var Initial, Nested, WasUndefined;',source)
        self.assertIn('Var First, Second, Third, Failed, Matched;',source)

"""Finite module-variable measurement; no expected native values are assumed."""
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

class ModuleContextMeasurementTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            p=mock.patch.object(suite,'secure_bytes',new=stage_fixture.portable_fixture_bytes)
            p.start();self.addCleanup(p.stop)
    def marker(self,records):
        return dict(schema=1,nonce='a'*32,phase='completed',witness='client',
            values=suite.CLIENT_VALUES+['module.context.v1']+records)
    def test_finite_capture_does_not_grant_acceptance(self):
        records=[True,False,0,999,10,100,7,'U',11]
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'completed.json';p.write_bytes(json.dumps(self.marker(records)).encode())
            with self.assertRaises(suite.FullError):suite.client_marker(p,'a'*32,'completed')
            d=suite.client_marker_diagnostics(p,'a'*32)
            self.assertEqual(d,dict(phase='completed',kind='count',ordinal=109,error_stage=0,
                module_context=[True,False,0,999,10,100,7,None,11]))
            self.assertEqual(full.validate_marker_diagnostics(d),d)
            self.assertEqual(len(full.CLIENT_VALUES),109)
            self.assertEqual(full.CLIENT_VALUES,suite.CLIENT_VALUES)
    def test_malformed_or_partial_records_never_export_list(self):
        good=self.marker([False]*9);cases=[]
        for bad in ([],[False]*8,[False]*10,['PRIVATE']*9,[1000]*9,[-1]*9,[1.5]*9,[None]*9,[{}]*9):
            cases.append(self.marker(bad))
        for change in ({'nonce':'b'*32},{'phase':'error'},{'extra':'PRIVATE'},{'witness':'server'}):
            cases.append({**good,**change})
        for index in (0,50,51,108,109):
            c=copy.deepcopy(good);c['values'][index]='PRIVATE';cases.append(c)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'completed.json'
            for value in cases:
                p.write_bytes(json.dumps(value).encode())
                self.assertNotIn('module_context',suite.client_marker_diagnostics(p,'a'*32))
            p.write_bytes(b'x'*2049)
            self.assertNotIn('module_context',suite.client_marker_diagnostics(p,'a'*32))
        valid=dict(phase='completed',kind='count',ordinal=109,error_stage=0,module_context=[None]*9)
        for change in ({'phase':'error'},{'kind':'value'},{'ordinal':108},{'error_stage':1},
                       {'module_context':[None]*8},{'module_context':[True]*10},
                       {'module_context':['U']*9},{'module_context':[1000]*9}):
            with self.assertRaises(ValueError):full.validate_marker_diagnostics({**valid,**change})
    def test_exact_three_part_inverse_preserves_audited_object_source(self):
        raw=linux_fixture(ROOT/full.CLIENT_SOURCE)
        restored=full.module_context_shared_source(raw)
        self.assertEqual(restored,suite.module_context_shared_source(raw))
        self.assertEqual(full.digest(restored),'6e29d85372e623c412e0662ad7514fbc76963fb5bd42bde6a100a4b5c7a2b120')
        self.assertEqual(full.digest(suite.client_parity_template(raw)),
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
    def test_private_marker_bounds_without_cap_changes(self):
        marker=self.marker([False]*9)
        self.assertEqual([len(json.dumps(marker,**kwargs).encode()) for kwargs in
            ({'separators':(',',':')},{},{'indent':2})],[1257,1384,1876])
        self.assertEqual((suite.MAX_STAGE_REPORT,full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,8192,32768))
    def test_exact_serializer_bounds_reachable_capture_failure(self):
        import test_native_client_wire_v3 as fixture_module
        f=fixture_module.ClientWireV3Tests();f.setUp();self.addCleanup(f.doCleanups)
        stage=copy.deepcopy(f.stage);stage.update(status='failed',failure_kind='invalid_result',failed_case=None)
        for name in ('dates','values','collections','numbers','watchdog'):
            stage['client_'+name]=getattr(suite,'empty_'+name+'_report')()
        for case in stage['cases']:case.update(output_size=209715,message_count=32768)
        stage['client_probe'].update(status='failed',failure_kind='invalid_result',completed=False,witness_verified=False,
            marker_diagnostics=dict(phase='completed',kind='count',ordinal=109,error_stage=0,module_context=[False]*9),
            process_diagnostics=fixture_module.fixtures.process_diagnostics(stage='after_exit',reason='unexpected_processes',
                classes={'native':100,'display':26,'session_bus':26,'shell':26,'python':26,'other':26,'unreadable':26},zombie_count=256))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder).resolve()/'stage.json';suite.write_report(p,stage);raw=p.read_bytes()
            self.assertLessEqual(len(raw),8192)
            self.assertEqual(full.decode_stage3_wire(full.strict_json(raw,8192)),stage)
            self.assertEqual(suite.decode_stage_wire(json.loads(raw)),stage)
        report=copy.deepcopy(f.fixture.envelope['report']);report.update(status='stage3_failed',native_tests_completed=False,stage3=stage)
        self.assertLessEqual(len(json.dumps(report,indent=2,sort_keys=True).encode()),32768)

    def test_failed_measurement_never_runs_later_client_cases(self):
        import test_native_client_probe as fixtures
        f=fixtures.ClientSuiteIntegrationTests();f.setUp();self.addCleanup(f.doCleanups)
        failed={**f.client,'status':'failed','failure_kind':'invalid_result',
            'completed':False,'witness_verified':False,
            'marker_diagnostics':dict(phase='completed',kind='count',ordinal=109,
                error_stage=0,module_context=[False]*9)}
        with mock.patch.object(suite,'run_client_probe',return_value=failed) as probe, \
             mock.patch.object(suite,'run_client_watchdog') as watchdog:
            result=suite.run_suite(f.launcher,f.platform,f.epf,f.work,f.inputs,fixtures.NONCE,
                client_probe=True,watchdog_check=True,client_dates=True,client_values=True,
                client_collections=True,client_numbers=True)
        probe.assert_called_once();watchdog.assert_not_called()
        for name in ('dates','values','collections','numbers','watchdog'):
            self.assertEqual(result['client_'+name],getattr(suite,'empty_'+name+'_report')())

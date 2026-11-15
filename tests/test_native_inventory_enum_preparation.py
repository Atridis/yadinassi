"""Offline source/phase/provenance gates; no native expected behaviors."""
import ast
from copy import deepcopy
from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest import mock
from inventory_enum_behavior import fixture, route
import native_1c_inventory_enum_profile as host

ROOT=Path(__file__).resolve().parents[1]
NONCE='b'*32

class InventoryEnumPreparationTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patcher.start();self.addCleanup(patcher.stop)

    def test_twelve_groups_with_disjoint_phase_ranges(self):
        self.assertEqual(route.COUNT,12)
        self.assertEqual(list(route.case_range(1)),list(range(1,12)))
        self.assertEqual(list(route.case_range(2)),[12])

    def test_invalid_phases_are_not_coerced(self):
        for value in (0,3,True,'1',None):
            with self.subTest(value=value),self.assertRaises(ValueError):route.case_range(value)

    def test_source_digest_is_bound(self):
        raw=route.source()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),route.SOURCE_SHA256)
        # Serialization must not call native IndexOf on a typed empty value.
        # Its -1 token is our owned wire spelling, not a native IndexOf result.
        enum_helper=raw.split(b'Function E(Val Value)',1)[1].split(b'EndFunction',1)[0]
        for prefix,name in ((b'u',b'Units'),(b's',b'States')):
            guard=b'If Value.IsEmpty() Then Return "'+prefix+b'-1"; EndIf;'
            index=b'Enums.'+name+b'.IndexOf(Value)'
            self.assertEqual(enum_helper.count(guard),1)
            self.assertLess(enum_helper.index(guard),enum_helper.index(index))

    def test_fixture_assets_are_bound(self):
        _,assets=fixture.load_saved()
        self.assertEqual(set(assets),set(fixture.ASSET_HASHES)|{'generated/observe.bsl'})
        self.assertIn('Units.xml',assets);self.assertIn('States.xml',assets)

    def test_two_generated_programs_parse_and_have_closed_bounds(self):
        from yadinassi.syntax.parser import parse
        for phase,last in ((1,11),(2,12)):
            raw=route.program(None,NONCE,phase);parse(raw.decode('utf-8'))
            self.assertLessEqual(len(raw),32768)
            self.assertIn(('ENP|'+NONCE+'|p'+str(phase)+'|entered').encode(),raw)
            self.assertIn(('To '+str(last)+' Do').encode(),raw)
        self.assertNotEqual(route.program(None,NONCE,1),route.program(None,NONCE,2))

    def test_bad_nonce_is_refused(self):
        with self.assertRaises(ValueError):route.program(None,'wrong',1)

    def wire(self,phase):
        prefix='ENP|'+NONCE+'|p'+str(phase)+'|'
        return ('\n'.join([prefix+'entered',*[prefix+str(n)+'|empty' for n in route.case_range(phase)],prefix+'completed'])+'\n').encode()

    def test_phase_one_wire(self):
        self.assertEqual(route.parse_wire(self.wire(1),NONCE,1),['empty']*11)

    def test_phase_two_wire(self):
        self.assertEqual(route.parse_wire(self.wire(2),NONCE,2),['empty'])

    def test_cross_phase_replay_is_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire(1),NONCE,2)

    def test_second_phase_cannot_claim_case_one(self):
        raw=self.wire(2).replace(b'|12|',b'|1|')
        with self.assertRaises(ValueError):route.parse_wire(raw,NONCE,2)

    def test_missing_case_is_refused(self):
        raw=self.wire(1).replace(('ENP|'+NONCE+'|p1|7|empty\n').encode(),b'')
        with self.assertRaises(ValueError):route.parse_wire(raw,NONCE,1)

    def test_diagnostic_is_not_an_observation(self):
        prefix='ENP|'+NONCE+'|p2|'
        raw=(prefix+'entered\n'+prefix+'error|12|read|"owned failure"\n'+prefix+'completed\n').encode()
        observed,errors=route.parse_attempt(raw,NONCE,2)
        self.assertEqual(observed,[]);self.assertEqual(errors,[(12,'read','owned failure')])
        with self.assertRaises(ValueError):route.parse_wire(raw,NONCE,2)

    def test_canonical_output_count_is_exact(self):
        self.assertTrue(route.canonical(['empty']*12))
        with self.assertRaises(ValueError):route.canonical(['empty']*11)

    def test_output_is_bounded_and_scalar(self):
        for value in ('x'*4097,'arbitrary\ntext',{'not':'scalar'}):
            with self.assertRaises(ValueError):route.canonical([value]*12)

    def test_module_digest_binds_both_phases(self):
        expected=hashlib.sha256(b'\0'.join(host.FULL.generated_module(route.program(None,NONCE,p)) for p in (1,2))).hexdigest()
        self.assertEqual(route.module_digest(host.FULL.generated_module,None,NONCE),expected)

    def test_staging_owns_every_new_asset(self):
        files=host.staged_files()
        for name in fixture.ASSET_HASHES:self.assertIn('scripts/inventory_enum_behavior/'+name,files)
        self.assertIn('scripts/inventory_enum_behavior/observe.bsl',files)
        self.assertNotIn('scripts/inventory_period_behavior/observe.bsl',files)

    def test_staging_revalidates_exact_bytes(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            stage=Path(tmp).resolve()/'stage';hashes=host.stage_inputs(ROOT,stage,host.SMOKE)
            host.validate_inputs(stage,hashes,host.SMOKE)
            (stage/'bootstrap/inventory_enum_behavior/Units.xml').write_bytes(b'drift')
            with self.assertRaises(ValueError):host.validate_inputs(stage,hashes,host.SMOKE)

    def test_enum_declaration_order_is_material(self):
        raw=(ROOT/'scripts/inventory_enum_behavior/Units.xml').read_bytes()
        import re
        first,second=re.findall(rb'<EnumValue.*?</EnumValue>',raw,re.S)
        changed=raw.replace(first,b'PLACEHOLDER').replace(second,first).replace(b'PLACEHOLDER',second)
        self.assertNotEqual(fixture._owned_projection(raw,'Enum'),fixture._owned_projection(changed,'Enum'))

    def test_field_target_is_material(self):
        raw=(ROOT/'scripts/inventory_enum_behavior/Stock.xml').read_bytes()
        changed=raw.replace(b'cfg:EnumRef.Units',b'cfg:EnumRef.States')
        self.assertNotEqual(fixture._owned_projection(raw,'AccumulationRegister'),fixture._owned_projection(changed,'AccumulationRegister'))

    def test_source_copies_both_enum_roles(self):
        for name in ('Receipt','Issue'):
            raw=(ROOT/'scripts/inventory_enum_behavior'/(name+'Module.bsl')).read_text(encoding='utf-8')
            self.assertIn('Row.Unit = Line.Unit;',raw);self.assertIn('Row.State = State;',raw)

    def test_unknown_source_file_is_not_a_passive_default(self):
        with self.assertRaises(ValueError):fixture.verify_redump({}, {'extra.xml':b'<x/>'})

    def test_controller_requires_first_exit_before_second_invocation(self):
        source=(ROOT/'scripts/native_1c_bootstrap/inventory_enum_suite.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn('for current_phase in (1,2):',source)
        self.assertLess(source.index("not report['phases'][0]['process_exited']"),source.index('launcher.run_case(platform,program_path'))
        self.assertIn("case=root/('case-'+str(current_phase))",source)
        self.assertIn("actual_module=full.secure_bytes(case/'src/TestModule/Ext/ObjectModule.bsl'",source)

    def test_workflow_keeps_owner_exact_source_and_branch_guards(self):
        source=(ROOT/'.github/workflows/native-1c-inventory-enum.yml').read_text(encoding='utf-8')
        for token in ("head.ref == 'codex/inventory-enum-storage'",'repository_id == \'359770628\'', 'ref: ${{ github.sha }}', 'scripts/native_1c_ci_policy.py bind'):
            self.assertIn(token,source)
        self.assertNotIn('workflow_dispatch',source)
        self.assertLess(source.index('scripts/native_1c_ci_policy.py bind'),source.index('GHCR_TOKEN'))

    def test_new_source_paths_have_lf_pins(self):
        source=(ROOT/'.gitattributes').read_text(encoding='utf-8')
        self.assertIn('scripts/inventory_enum_behavior/** text eol=lf',source)
        self.assertIn('scripts/native_1c_bootstrap/inventory_enum_suite.py text eol=lf',source)

class InventoryEnumPhaseEnvelopeTests(unittest.TestCase):
    def complete(self):
        facts=[]
        for p in (1,2):
            digest=host.FULL.digest(host.FULL.generated_module(route.program(None,NONCE,p)))
            facts.append(dict(phase=p,entered=True,completed=True,process_exited=True,quiet=True,
                record_count=len(route.case_range(p)),module_sha256=digest,module_verified_sha256=digest))
        return dict(status='ok',restart_verified=True,phases=facts)

    def test_success_requires_two_complete_processes(self):host.validate_phases(self.complete(),NONCE)

    def test_missing_restart_witness_is_refused(self):
        stage=self.complete();stage['restart_verified']=False
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_one_process_is_not_restart(self):
        stage=self.complete();stage['phases'].pop()
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_first_process_exit_is_required(self):
        stage=self.complete();stage['phases'][0]['process_exited']=False
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_first_quiet_census_is_required(self):
        stage=self.complete();stage['phases'][0]['quiet']=False
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_phase_order_is_bound(self):
        stage=self.complete();stage['phases'].reverse()
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_phase_counts_cannot_be_swapped(self):
        stage=self.complete();stage['phases'][0]['record_count']=1
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_second_module_is_not_first_module(self):
        stage=self.complete();stage['phases'][1]['module_sha256']=stage['phases'][0]['module_sha256']
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_verified_source_cannot_drift(self):
        stage=self.complete();stage['phases'][1]['module_verified_sha256']='0'*64
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_unknown_phase_fields_are_refused(self):
        stage=self.complete();stage['phases'][0]['command']='arbitrary'
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

    def test_failure_before_launch_has_no_restart_authority(self):
        host.validate_phases(dict(status='failed',restart_verified=False,phases=[]),NONCE)

    def test_failure_does_not_allow_second_process_before_first_completion(self):
        stage=self.complete();stage['status']='failed';stage['restart_verified']=False;stage['phases'][0]['completed']=False
        with self.assertRaises(ValueError):host.validate_phases(stage,NONCE)

class InventoryEnumControllerTests(unittest.TestCase):
    """Exercise real two-phase controller with synthetic native process IO.

    These mocks only stand in for native executables/Designer source. They do
    not supply a successful controller report or bypass its phase decisions.
    """
    def simulate(self, *, fail=None):
        import contextlib
        import importlib
        import json
        import sys
        from types import SimpleNamespace
        with mock.patch.object(sys,'path',[str(ROOT/'scripts/native_1c_bootstrap'),*sys.path]):
            suite=importlib.import_module('inventory_enum_suite')
        events=[]
        old_reader=lambda path: None
        old_process=lambda *args: None
        old_build=lambda *args: None
        launcher=SimpleNamespace(read_result=old_reader,run_process=old_process,build_epf=old_build)
        platform=SimpleNamespace(user='NativeSmoke',password=None,timeout=120,executable='owned-platform',
            command=lambda mode:['owned-platform',mode])
        def run_case(p,source,epf,case,output):
            number=int(case.name.split('-')[-1]);events.append(('start',number))
            self.assertIs(p,platform)
            module=suite.full.generated_module(source.read_bytes())
            target=case/'src/TestModule/Ext/ObjectModule.bsl';target.parent.mkdir(parents=True)
            target.write_bytes(module)
            launcher.build_epf(p,case/'src/TestModule.xml',case/'owned.epf')
            launcher.run_process(['owned-platform','ENTERPRISE'],case,case/'console',120)
            if fail=='first_exit' and number==1:raise suite.full.FullError('process_failed')
            prefix='ENP|'+NONCE+'|p'+str(number)+'|'
            messages=[prefix+'entered',*[prefix+str(n)+'|empty' for n in route.case_range(number)],prefix+'completed']
            if fail=='phase_two_markers' and number==2:messages[-1]=prefix+'wrong'
            raw=suite.full.serialize_messages(messages)
            (case/'result.json').write_text(json.dumps({'messages':messages,'error':''}),encoding='utf-8')
            output.write_bytes(raw)
            if fail=='phase_two_module' and number==2:target.write_bytes(module+b'// drift')
            events.append(('exit',number))
        launcher.run_case=run_case
        def quiet(executable):
            events.append(('quiet',len([v for k,v in events if k=='start'])))
            return not (fail=='first_quiet' and ('start',1) in events)
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp,contextlib.ExitStack() as stack:
            work=Path(tmp).resolve();root=work/'owned'
            def patch(obj,name,**kwargs):return stack.enter_context(mock.patch.object(obj,name,**kwargs))
            patch(suite,'input_hashes',return_value={'owned':'0'*64})
            patch(suite,'dump_files',return_value={'Configuration.xml':b'owned'})
            patch(suite.fixture,'prepare',return_value=(None,{'Configuration.xml':b'owned'}))
            patch(suite.fixture,'redump_diagnostic',return_value=[])
            patch(suite.fixture,'verify_redump',return_value=None)
            patch(suite.full,'client_process_baseline',return_value=set())
            patch(suite.full,'client_process_snapshot',return_value=set())
            patch(suite.full,'require_session_bus',return_value=None)
            patch(suite.full,'native_processes_quiet',side_effect=quiet)
            patch(suite.full,'validate_case_request',return_value=None)
            patch(suite.full,'run_process',return_value=None)
            if os.name=='nt':
                from test_native_1c_full_host import read_synthetic_file
                patch(suite.full,'secure_bytes',side_effect=lambda path,limit,allow_empty=False:
                      read_synthetic_file(path,limit,nonempty=not allow_empty))
            report=suite.run_suite(launcher,platform,work/'Launcher.epf',root,work,NONCE)
            self.assertIs(launcher.read_result,old_reader)
            self.assertIs(launcher.run_process,old_process)
            self.assertIs(launcher.build_epf,old_build)
            exists=(root/'inventory-enum.out').exists()
        return report,events,exists

    def test_two_distinct_processes_exit_and_quiet_before_restart(self):
        report,events,exists=self.simulate()
        self.assertEqual(report['status'],'ok');self.assertTrue(exists)
        self.assertTrue(report['restart_verified']);self.assertEqual(len(report['partial_observations']),12)
        self.assertLess(events.index(('exit',1)),events.index(('quiet',1)))
        self.assertLess(events.index(('quiet',1)),events.index(('start',2)))
        host.validate_phases(report,NONCE)

    def test_failed_first_exit_never_starts_second(self):
        report,events,exists=self.simulate(fail='first_exit')
        self.assertNotIn(('start',2),events);self.assertFalse(exists)
        self.assertEqual(report['status'],'failed');self.assertFalse(report['restart_verified'])

    def test_failed_first_quiet_never_starts_second(self):
        report,events,exists=self.simulate(fail='first_quiet')
        self.assertNotIn(('start',2),events);self.assertFalse(exists)
        self.assertEqual(report['status'],'failed');self.assertFalse(report['restart_verified'])

    def test_second_source_drift_has_no_accepted_output(self):
        report,events,exists=self.simulate(fail='phase_two_module')
        self.assertIn(('start',2),events);self.assertFalse(exists)
        self.assertEqual(report['failure_kind'],'module_mismatch');self.assertFalse(report['restart_verified'])

    def test_second_missing_completion_has_no_restart_witness(self):
        report,events,exists=self.simulate(fail='phase_two_markers')
        self.assertIn(('start',2),events);self.assertFalse(exists)
        self.assertFalse(report['restart_verified']);self.assertEqual(report['status'],'failed')

    def test_phase_two_diagnostic_counts_observations_not_case_number(self):
        prefix='ENP|'+NONCE+'|p2|'
        result=route.failure_details({'messages':[prefix+'entered',prefix+'12|empty'],'error':''},NONCE,2)
        self.assertEqual(result['cases'],1)

    def test_new_owned_identifiers_do_not_export_arbitrary_diagnostics(self):
        result=route.install_diagnostic('Units State ArbitraryPrivateValue secret=hidden\nEnumValue', 'load')
        self.assertNotIn('ArbitraryPrivateValue',repr(result));self.assertNotIn('hidden',repr(result))
        self.assertEqual(result['tokens'],['line_break','owned:EnumValue'])

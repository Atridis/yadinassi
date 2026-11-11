"""No native execution: source/transport/isolation contract checks only."""
import json
import os
from unittest import mock
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from accumulation_register_behavior import fixture,route
import native_1c_accumulation_register_profile as host

class AccumulationAcquisitionTests(unittest.TestCase):
    def setUp(self):
        # Static fixtures only, matching the other native profile tests.
        # This is not a Windows containment/security proof.
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_synthetic_file)
            patcher.start()
            self.addCleanup(patcher.stop)

    def wire(self):
        prefix='ACC|'+'a'*32+'|'
        return (prefix+'entered\n'+''.join(prefix+str(n)+'|0|0|0,0|before:0;\n' for n in range(1,17))+prefix+'completed\n').encode()
    def test_exact_sixteen_observations(self):
        values=route.parse_wire(self.wire(),'a'*32)
        self.assertEqual(len(values),16)
        self.assertEqual(json.loads(route.canonical(values)),values)
    def test_wrong_nonce_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire(),'b'*32)
    def test_reordered_case_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire().replace(b'|2|0|',b'|3|0|'),'a'*32)
    def test_unbounded_observation_refused(self):
        with self.assertRaises(ValueError):route.canonical(['x'*4097]*16)
    def test_extra_output_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire()+b'noise\n','a'*32)
    def test_source_fixture_hashes(self):
        setup,assets=fixture.load_saved()
        self.assertEqual(assets['generated/observe.bsl'],route.source())
        self.assertIn(b'<RegisterType>Balance</RegisterType>',assets['AccumulationRegister.xml'])
        from yadinassi.syntax.parser import parse
        parse(route.program(setup,'a'*32).decode())
        parse(assets['ObjectModule.bsl'].decode())
    def test_source_bound_packet_has_cross_platform_byte_pins(self):
        attributes=(ROOT/'.gitattributes').read_text(encoding='utf-8').splitlines()
        for path in ('scripts/accumulation_register_behavior/**',
                     'scripts/native_1c_bootstrap/accumulation_register_suite.py',
                     'scripts/native_1c_accumulation_probe.sh'):
            self.assertIn(path+' text eol=lf',attributes)
    def test_authored_child_order_matches_designer_220_sequence(self):
        # MDClasses 2.20 AccumulationRegisterChildObjects: Resource*,
        # Attribute*, Dimension*. Semantic projection alone sorts these groups.
        # https://github.com/yellow-hammer/namespace-forest/blob/0023896332406bdc163f746daaf91756d26a54bd/schemas/designer/2.20/v8.1c.ru-8.3-MDClasses.xsd#L111-L119
        from xml.etree import ElementTree as ET
        _,assets=fixture.load_saved()
        root=ET.fromstring(assets['AccumulationRegister.xml'])
        namespace='{http://v8.1c.ru/8.3/MDClasses}'
        children=root.find(namespace+'AccumulationRegister/'+namespace+'ChildObjects')
        self.assertEqual([child.tag.removeprefix(namespace) for child in children],
                         ['Resource','Resource','Attribute','Dimension','Dimension'])
    def test_distinct_staged_route_and_readonly_isolation(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            destination=Path(directory)/'inputs'
            hashes=host.stage_inputs(ROOT,destination,host.SMOKE)
            command=host.container_command(destination,hashes,'onec-accumulation-register-'+'a'*32,'a'*32,host.SMOKE)
            self.assertIn('--accumulation-register-suite',command)
            self.assertNotIn('--catalog-object-suite',command)
            self.assertIn('--read-only',command)
            self.assertEqual(command[command.index('--network')+1],'none')
    def test_no_runtime_parity_comparison(self):
        source=(ROOT/'scripts/native_1c_accumulation_register_profile.py').read_text(encoding='utf-8')
        self.assertIn("'runtime_parity_accepted':False",source)
        self.assertIn('comparison=None',source)
    def test_only_new_workflow_and_closed_branch(self):
        workflow=(ROOT/'.github/workflows/native-1c-accumulation-register.yml').read_text(encoding='utf-8')
        self.assertIn("head.ref == 'codex/accumulation-balance-registers'",workflow)
        self.assertNotIn('pull_request_target',workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('native_1c_ci_policy.py bind',workflow)
    def test_redump_diagnostic_does_not_accept_different_xml(self):
        name='Documents/OwnedAccumulationDoc.xml'
        expected={name:b'<Metadata><Posting>Deny</Posting></Metadata>'}
        actual={name:b'<Metadata><Posting>Allow</Posting></Metadata>'}
        self.assertTrue(fixture.redump_diagnostic(expected,actual))
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_redump_diagnostic_never_exports_module_text(self):
        value=fixture.redump_diagnostic({'secret/Ext/ObjectModule.bsl':b'private'}, {'secret/Ext/ObjectModule.bsl':b'changed'})
        self.assertNotIn('private',str(value));self.assertNotIn('secret',str(value))
        self.assertTrue(fixture.valid_diagnostic(value))
    def test_redump_diagnostic_bounded_and_text_redacted(self):
        name='Documents/OwnedAccumulationDoc.xml'
        expected={name:b'<Metadata><Text>old text</Text></Metadata>'}
        actual={name:b'<Metadata><Text>private text</Text></Metadata>'}
        value=fixture.redump_diagnostic(expected,actual)
        self.assertNotIn('private text',str(value));self.assertTrue(fixture.valid_diagnostic(value))
        self.assertFalse(fixture.valid_diagnostic(['x'*141]))
        self.assertFalse(fixture.valid_diagnostic(['x']*13))
    def test_equal_redump_diagnostic_empty(self):
        files={'Other.xml':b'<Metadata><Posting>Allow</Posting></Metadata>'}
        self.assertEqual(fixture.redump_diagnostic(files,files),[])
        self.assertTrue(fixture.verify_redump(files,files))
    def metadata(self):
        _,assets=fixture.load_saved()
        return {'Documents/OwnedAccumulationDoc.xml':assets['Document.xml'],
            'AccumulationRegisters/OwnedAccumulationRows.xml':assets['AccumulationRegister.xml'],
            'Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl':assets['ObjectModule.bsl']}
    def test_semantic_metadata_accepts_designer_ui_defaults(self):
        expected=self.metadata();actual=dict(expected);name='Documents/OwnedAccumulationDoc.xml'
        actual[name]=actual[name].replace(b'<Name>OwnedAccumulationDoc</Name>',b'<Name>OwnedAccumulationDoc</Name><AuxiliaryChoiceForm/><ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>')
        self.assertTrue(fixture.verify_redump(expected,actual))
    def test_semantic_metadata_rejects_changed_posting_or_recorder(self):
        expected=self.metadata();name='Documents/OwnedAccumulationDoc.xml'
        for before,after in [(b'<Posting>Allow',b'<Posting>Deny'),(b'AccumulationRegister.OwnedAccumulationRows',b'AccumulationRegister.Other')]:
            actual=dict(expected);actual[name]=actual[name].replace(before,after)
            with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_semantic_metadata_rejects_changed_field_types(self):
        expected=self.metadata();actual=dict(expected);name='AccumulationRegisters/OwnedAccumulationRows.xml'
        actual[name]=actual[name].replace(b'<v8:Digits>10',b'<v8:Digits>12')
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_semantic_metadata_rejects_changed_identity(self):
        expected=self.metadata();actual=dict(expected);name='Documents/OwnedAccumulationDoc.xml'
        actual[name]=actual[name].replace(b'98ed6b79-7763-539f-8055-e44fb8cb0ebf',b'08ed6b79-7763-539f-8055-e44fb8cb0ebf')
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_semantic_metadata_rejects_handler_and_extra_executable(self):
        expected=self.metadata();actual=dict(expected)
        actual['Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl']+=b'\n//changed'
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
        actual=dict(expected);actual['Ext/SessionModule.bsl']=b'//unknown'
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_semantic_metadata_rejects_extra_user_field(self):
        expected=self.metadata();actual=dict(expected);name='AccumulationRegisters/OwnedAccumulationRows.xml'
        actual[name]=actual[name].replace(b'</ChildObjects>',b'<Attribute uuid="extra"><Properties><Name>Extra</Name><Type/></Properties></Attribute></ChildObjects>')
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_observation_declarations_precede_entered_marker(self):
        program=route.program(None,'a'*32)
        self.assertLess(program.index(b'Function Numeric'),program.index(b'|entered'))
        self.assertLess(program.index(b'Function Raw'),program.index(b'|entered'))
        self.assertLess(program.index(b'|entered'),program.index(b'For CaseNo = 1'))
    def test_observation_program_retains_exact_source_segments(self):
        program=route.program(None,'a'*32)
        declarations,statements=route.source().split(b'For CaseNo = 1 To 16 Do')
        self.assertIn(declarations,program)
        self.assertIn(b'For CaseNo = 1 To 16 Do'+statements,program)
    def test_native_error_diagnostic_is_finite_vocabulary(self):
        self.assertIn('compile_error',host.SMOKE.DIAGNOSTICS.CATEGORIES)
        source=(ROOT/'scripts/native_1c_bootstrap/accumulation_register_suite.py').read_text(encoding='utf-8')
        self.assertIn("diagnostics.summarize_text(result['error'])['category']",source)
        self.assertNotIn("report['native_error_text']",source)
    def test_failure_diagnostic_reports_only_owned_frames_and_progress(self):
        value=route.failure_details({'messages':['ACC|'+'a'*32+'|entered','ACC|'+'a'*32+'|1|x'],
            'error':'{Обработка.TestModule.МодульОбъекта(19)} Ошибка при вызове метода контекста (Execute) Ошибка в запросе'},'a'*32)
        self.assertEqual(value['frames'],[['TestModule',19]])
        self.assertEqual(value['apis'],['execute']);self.assertEqual(value['cases'],1)
        self.assertIn('query',value['codes']);self.assertTrue(route.valid_failure_details(value))
    def test_failure_diagnostic_never_exports_arbitrary_error(self):
        value=route.failure_details({'messages':[],'error':'private-secret /private/path {OtherModule(12)} (UnknownAPI)'},'a'*32)
        self.assertNotIn('private',str(value));self.assertEqual(value['frames'],[])
        self.assertEqual(value['apis'],[]);self.assertTrue(route.valid_failure_details(value))
    def test_failure_diagnostic_limits_reject_unknown_values(self):
        value=route.failure_details({'messages':[],'error':''},'a'*32)
        value['apis']=['arbitrary'];self.assertFalse(route.valid_failure_details(value))
        with self.assertRaises(ValueError):route.failure_details({'messages':[],'error':'x'*16385},'a'*32)
    def test_partial_cases_retained_with_setup_failure(self):
        p='ACC|'+'a'*32+'|'
        raw=(p+'entered\n'+p+'1|0|0|0,0|before:0;\n'+p+'error|4|seed|"private error"\n'+p+'completed\n').encode()
        observations,errors=route.parse_attempt(raw,'a'*32)
        self.assertEqual(observations,[[1,'0|0|0,0|before:0;']]);self.assertEqual(errors,[(4,'seed','private error')])
    def test_case_diagnostic_json_cannot_inject_protocol_lines(self):
        p='ACC|'+'a'*32+'|'
        raw=(p+'entered\n'+p+'error|4|seed|'+json.dumps('line1\nline2')+'\n'+p+'completed\n').encode()
        observations,errors=route.parse_attempt(raw,'a'*32)
        self.assertEqual(observations,[]);self.assertEqual(errors[0][2],'line1\nline2')
    def test_all_case_observations_remain_ordered(self):
        observations,errors=route.parse_attempt(self.wire(),'a'*32)
        self.assertEqual(len(observations),16);self.assertEqual(errors,[])
        with self.assertRaises(ValueError):route.parse_attempt(self.wire().replace(b'|2|0|',b'|1|0|'),'a'*32)
    def test_observer_uses_detailed_error_and_distinct_phases(self):
        source=route.source().decode()
        for stage in ('setup','seed','write','readback','query'):self.assertIn('"'+stage+'"',source)
        self.assertIn('ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())',source)
        self.assertIn('If TransactionActive() Then RollbackTransaction()',source)
    def test_seed_identity_collision_is_explicit_not_assumed(self):
        source=route.source().decode()
        self.assertIn('CaseNo = 2 Or CaseNo = 3',source)
        self.assertIn('Item = "shared"',source)
        self.assertIn('AddRow(Rows,Item,1,3,2,T)',source)
    def test_absent_document_is_observed_by_query(self):
        source=route.source().decode()
        self.assertIn('FROM Document.OwnedAccumulationDoc',source)
        self.assertIn('If Not S.Next() Then Return "missing"',source)
    def test_exact_matrix_includes_metadata_and_boundaries(self):
        source=route.source().decode()
        self.assertIn('Description.NumberQualifiers',source)
        self.assertIn('Balance(Item,T-1)',source)
        self.assertIn('Balance(Item,T+2)',source)
        self.assertIn('Turnovers(Item,T,T+2)',source)
        self.assertIn('Turnovers(Item,T,T)',source)
        self.assertEqual(route.COUNT,16)
    def test_material_dimension_totals_property_is_verified(self):
        expected=self.metadata();actual=dict(expected);name='AccumulationRegisters/OwnedAccumulationRows.xml'
        actual[name]=actual[name].replace(b'<UseInTotals>true',b'<UseInTotals>false')
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_material_register_kind_is_verified(self):
        expected=self.metadata();actual=dict(expected);name='AccumulationRegisters/OwnedAccumulationRows.xml'
        actual[name]=actual[name].replace(b'<RegisterType>Balance',b'<RegisterType>Turnovers')
        with self.assertRaises(ValueError):fixture.verify_redump(expected,actual)
    def test_record_type_uses_native_enum_not_surrogate(self):
        source=route.source().decode()
        self.assertIn('AccumulationRecordType.Receipt',source)
        self.assertIn('AccumulationRecordType.Expense',source)
    def test_native_host_accepts_bounded_larger_source(self):
        self.assertLess(len(route.program(None,'a'*32)),32768)
    def test_exported_values_match_report_observations(self):
        values=['case'+str(n) for n in range(1,17)]
        stage={'record_count':16,'incomplete':False,'partial_observations':list(map(list,enumerate(values,1)))}
        self.assertEqual(host.validate_observation_binding(stage,route.canonical(values)),values)
    def test_contradictory_report_and_artifact_are_refused(self):
        values=['case'+str(n) for n in range(1,17)]
        stage={'record_count':16,'incomplete':False,'partial_observations':list(map(list,enumerate(values,1)))}
        stage['partial_observations'][7][1]='different'
        with self.assertRaises(ValueError):host.validate_observation_binding(stage,route.canonical(values))
    def test_incomplete_evidence_cannot_be_exported_as_complete(self):
        values=['case'+str(n) for n in range(1,17)]
        stage={'record_count':16,'incomplete':True,'partial_observations':list(map(list,enumerate(values,1)))}
        with self.assertRaises(ValueError):host.validate_observation_binding(stage,route.canonical(values))

    def test_install_diagnostic_retains_owned_identifiers(self):
        value=route.install_diagnostic('Error: invalid property EnableTotalsSplitting of AccumulationRegister.OwnedAccumulationRows','load')
        self.assertTrue(route.valid_install_diagnostic(value))
        self.assertIn('owned:EnableTotalsSplitting',value['tokens']);self.assertIn('invalid',value['tokens'])
    def test_install_diagnostic_redacts_arbitrary_text_and_values(self):
        value=route.install_diagnostic('private123 /private/path secret=Amount\nPrivatePerson 555 9999','update')
        self.assertTrue(route.valid_install_diagnostic(value))
        for raw in ('private','PrivatePerson','555','9999','owned:Amount'):self.assertNotIn(raw,str(value))
    def test_install_diagnostic_is_bounded(self):
        value=route.install_diagnostic('Error invalid '*300,'load')
        self.assertEqual(len(value['tokens']),96);self.assertTrue(value['truncated'])
        self.assertTrue(route.valid_install_diagnostic(value))
        with self.assertRaises(ValueError):route.install_diagnostic('x'*65537,'load')
    def test_install_diagnostic_rejects_unknown_output(self):
        value=route.install_diagnostic('Error','load');value['tokens']=['arbitrary']
        self.assertFalse(route.valid_install_diagnostic(value))
        with self.assertRaises(ValueError):route.install_diagnostic('error','arbitrary')
    def test_install_failure_capture_is_guarded_and_not_raw(self):
        source=(ROOT/'scripts/native_1c_bootstrap/accumulation_register_suite.py').read_text(encoding='utf-8')
        self.assertIn('full.secure_bytes(root/name,65536,allow_empty=True)',source)
        self.assertIn('route.install_diagnostic(diagnostics.native_text(raw),label,**facts)',source)
        self.assertIn("if stage['status']=='ok':require(stage['install_diagnostics']==[])",(ROOT/'scripts/native_1c_accumulation_register_profile.py').read_text(encoding='utf-8'))

    def test_install_diagnostic_discriminates_loader_terms(self):
        value=route.install_diagnostic('X Error: BadName named color or font does not exist','load')
        for token in ('error','invalid_name','color','font','not','exists'):self.assertIn(token,value['tokens'])
    def test_install_diagnostic_discriminates_xml_terms(self):
        value=route.install_diagnostic('Ошибка преобразования XDTO: Имя метаданных не определено. Свойство UseInTotals','load')
        for token in ('error','conversion','xml','name','metadata','not','defined','owned:UseInTotals'):self.assertIn(token,value['tokens'])
    def test_install_diagnostic_exact_facts(self):
        value=route.install_diagnostic('', 'load',exit_code=37,source_root_present=True,configuration_present=False)
        self.assertTrue(route.valid_install_diagnostic(value));self.assertEqual(value['exit_code'],37)
        self.assertIs(value['source_root_present'],True);self.assertIs(value['configuration_present'],False)
    def test_install_diagnostic_rejects_coerced_facts(self):
        for kwargs in ({'exit_code':True},{'exit_code':256},{'source_root_present':1},{'configuration_present':'true'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):route.install_diagnostic('', 'load',**kwargs)
    def test_install_preinvocation_facts_are_boolean_only(self):
        source=(ROOT/'scripts/native_1c_bootstrap/accumulation_register_suite.py').read_text(encoding='utf-8')
        self.assertIn("source_root=Path(args[1]) if label=='load' else None",source)
        self.assertLess(source.index('facts=dict(source_root_present='),source.index("full.run_process(platform.command('DESIGNER')"))
        self.assertIn("code=getattr(error,'exit_code',None)",source)
    def test_failed_native_process_retains_only_finite_exit_status(self):
        from unittest import mock
        from test_native_1c_full_stage import suite
        process=mock.MagicMock();process.__enter__.return_value=process;process.wait.return_value=37
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory)
            with mock.patch.object(suite.os,'name','posix'),mock.patch.object(suite.subprocess,'Popen',return_value=process),mock.patch.object(suite,'_stop_group'):
                with self.assertRaises(suite.FullError) as caught:suite.run_process(['native'],root,root/'console',120)
        self.assertEqual(caught.exception.kind,'process_failed');self.assertEqual(caught.exception.exit_code,37)
        self.assertEqual(str(caught.exception),'process_failed')

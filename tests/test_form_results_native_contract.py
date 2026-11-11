"""Source-only contracts for the narrow native route and unchanged legacy oracle."""
from pathlib import Path
import hashlib
import ast
import unittest
ROOT=Path(__file__).resolve().parents[1]


class NativeFormResultsContractTests(unittest.TestCase):
    def read(self,path):return (ROOT/path).read_text()

    def test_workflow_only_exact_owner_pr_branch(self):
        s=self.read('.github/workflows/native-1c-form-results.yml')
        for value in ("codex/configuration-form-results",'359770628','30860798',"github.triggering_actor == 'Atridis'",'persist-credentials: false','permissions: {}','cancel-in-progress: false'):
            self.assertIn(value,s)
        self.assertNotIn('pull_request_target:',s);self.assertNotIn('workflow_dispatch:',s)

    def test_admission_before_credentials_and_pinned_actions(self):
        s=self.read('.github/workflows/native-1c-form-results.yml')
        self.assertLess(s.index('native_1c_ci_policy.py bind'),s.index('GHCR_TOKEN:'))
        import re
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}',s)),4)

    def test_output_paths_allowlist(self):
        s=self.read('.github/workflows/native-1c-form-results.yml')
        for value in ('form-results-report.json','form-results.out','provenance.json','steps.results.outputs.form_results_outputs_ready'):
            self.assertIn(value,s)
        self.assertNotIn('**',s)

    def test_host_retains_container_isolation(self):
        s=self.read('scripts/native_1c_form_results_profile.py')
        for value in ("'--network', 'none'","'--read-only'","'--cap-drop', 'ALL'","'--security-opt', 'no-new-privileges:true'","'--user', '1000:1000'","container_cleanup_verified","private_payloads_removed"):
            self.assertIn(value,s)

    def test_no_manual_runtime_parity_replay(self):
        s=self.read('scripts/native_1c_form_results_profile.py')
        self.assertIn("'runtime_parity_accepted':False",s)
        self.assertIn("'acceptance_status':'not_evaluated'",s)
        self.assertNotIn('EXECUTE_SCRIPT=',s);self.assertNotIn('from yadinassi.form_runtime import FormSession',s)

    def test_lifecycle_is_native_open_close_not_handler_calls(self):
        a=self.read('scripts/form_results_packet/Launcher/Forms/Main/Ext/Form/Module.bsl')
        b=self.read('scripts/form_results_packet/Launcher/Forms/Child/Ext/Form/Module.bsl')
        self.assertIn('OpenForm("ExternalDataProcessor.Launcher.Form.Child"',a)
        self.assertIn('New CallbackDescription("Completed", ThisObject, Shared)',a)
        self.assertIn('Close(New Structure(',b)
        self.assertEqual(a.count('Procedure Completed('),1);self.assertNotIn('Completed(',a.replace('Procedure Completed(',''))
        self.assertNotIn('ChildBeforeClose(',b.replace('Procedure ChildBeforeClose(',''))

    def test_bounds_and_cancel_observation(self):
        a=self.read('scripts/form_results_packet/Launcher/Forms/Main/Ext/Form/Module.bsl')
        self.assertIn('WaitTurns >= 10',a);self.assertIn('WaitTurns < 3',a)
        self.assertIn('T.events.Count() >= 64',a);self.assertIn('Flow > 5',a)

    def test_early_and_final_source_witness(self):
        s=self.read('scripts/native_1c_bootstrap/form_results_suite.py')
        self.assertGreaterEqual(s.count('route.validate_redump('),3)
        self.assertLess(s.index("route.validate_executable_redump(dumped_files)"),s.index("phase='enterprise'"))
        self.assertIn("if input_hashes(inputs)!=hashes",s)
        self.assertIn('full.client_process_baseline(nonce)',s);self.assertIn('full.final_client_process_census(nonce)',s)

    def test_selector_closed_and_mutually_exclusive(self):
        s=self.read('scripts/native_1c_bootstrap/run_stage.py')
        self.assertIn('(form_runtime and form_results)',s)
        self.assertIn("type(form_results) is not bool",s)
        self.assertIn("arguments[0] == '--form-results-suite'",s)
        shell=self.read('scripts/native_1c_smoke_probe.sh')
        self.assertIn('[ "$#" -eq 3 ] && [ "$1" = --form-results-suite ]',shell)
        self.assertIn('tree_suite=form-results',shell)
        self.assertNotIn('importlib',shell)

    def test_old_packet_is_not_repurposed(self):
        s=self.read('scripts/form_runtime_packet/__init__.py')
        self.assertIn('COUNT = 40',s)
        self.assertIn("SOURCE_SHA256 = 'e05fed09cf85803443be815b357c5e20d9b05ad9c6f39bc622e111d0da1d3b73'",s)
        self.assertIn("len(children[0])!=1",self.read('scripts/form_runtime_packet/route.py'))

    def test_public_report_removes_private_nonce_after_validation(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        import native_1c_form_results_profile as host
        self.assertEqual(host.public_report({'nonce':'private','stage3':{'nonce':'private','status':'ok'}}),{'stage3':{'status':'ok'}})
        self.assertIn("'invocation_bound':True",self.read('scripts/native_1c_form_results_profile.py'))

    def test_host_and_suite_envelope_identity(self):
        # Parse literals only: never import or execute the native bootstrap.
        def identities(path):
            module=ast.parse(self.read(path))
            return {node.targets[0].id:ast.literal_eval(node.value)
                    for node in module.body if isinstance(node,ast.Assign)
                    and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
                    and node.targets[0].id in {'PROFILE','SCHEMA','STAGE_SCHEMA'}}
        expected={'PROFILE':'managed-form-results-v1',
                  'SCHEMA':'native-1c-form-results-v1',
                  'STAGE_SCHEMA':'native-1c-form-results-stage-v1'}
        self.assertEqual(identities('scripts/native_1c_form_results_profile.py'),expected)
        self.assertEqual(identities('scripts/native_1c_bootstrap/form_results_suite.py'),expected)

    def test_workflow_host_and_bootstrap_dispatch_alignment(self):
        workflow=self.read('.github/workflows/native-1c-form-results.yml')
        self.assertIn('python3 scripts/native_1c_form_results_profile.py --execute-approved-image --export-native-outputs',workflow)
        host=self.read('scripts/native_1c_form_results_profile.py')
        self.assertIn("'--form-results-suite', '--invocation-nonce', nonce",host)
        shell=self.read('scripts/native_1c_smoke_probe.sh')
        self.assertIn('if [ "$tree_suite" = form-results ]; then tree_flag=--form-results-suite; fi',shell)
        self.assertIn('if tree_mode == "form-results":',shell)
        self.assertIn('import form_results_suite as form_lane',shell)
        stage=self.read('scripts/native_1c_bootstrap/run_stage.py')
        self.assertIn('if form_results:',stage)
        self.assertIn('import form_results_suite as form_lane',stage)

    def test_synthetic_success_envelope_uses_real_host_validator(self):
        # Synthetic wire compatibility only, not native lifecycle evidence.
        import base64
        import json
        import sys
        from unittest import mock
        with mock.patch.object(sys,'path',[str(ROOT/'scripts'),
                str(ROOT/'scripts/native_1c_bootstrap'),*sys.path]):
            import native_1c_form_results_profile as host
            import form_results_suite as suite
            from test_native_1c_smoke import bootstrap_report
            from test_form_results_native_packet import records
        self.assertEqual(host.staged_files(),suite.INPUT_FILES)
        hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                for name in suite.INPUT_FILES}
        nonce='a'*32
        raw=records()
        digest=hashlib.sha256(raw).hexdigest()
        stage=suite.empty_report(nonce)
        stage.update(status='ok',failure_kind='none',failure_phase='final',
                     input_sha256=hashes,source_sha256=suite.SOURCE_SHA256,
                     form_sha256=suite.FORM_SHA256,
                     module_sha256=suite.route.module_digest(),
                     roundtrip_sha256=suite.route.module_digest(),
                     output_sha256=digest,output_size=len(raw),record_count=5)
        for key in host.FLAGS:stage[key]=True
        stage['process_diagnostics'].update(stage='after_exit',reason='none')
        report=bootstrap_report()
        report.update(native_tests_completed=True,stage3=stage)
        envelope={'schema':suite.SCHEMA,'profile':suite.PROFILE,'nonce':nonce,
                  'report':report,'outputs':[{'name':'form-results.out',
                  'size':len(raw),'sha256':digest,
                  'data_b64':base64.b64encode(raw).decode('ascii')}]}
        verified,output=host.validate_envelope(json.dumps(envelope).encode(),nonce,hashes)
        self.assertEqual(output,raw)
        self.assertEqual(verified['stage3']['schema'],suite.STAGE_SCHEMA)
        self.assertEqual(verified['stage3']['profile'],suite.PROFILE)

    def test_epf_and_authored_source_witnesses_bracket_execution(self):
        source=self.read('scripts/native_1c_bootstrap/form_results_suite.py')
        before,after=source.split("phase='enterprise'",1)
        self.assertIn('epf_digest=full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))',before)
        self.assertIn('full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))!=epf_digest',before)
        self.assertIn('full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))!=epf_digest',after)
        self.assertIn('route.validate_redump(_dump_files(src))',before)
        self.assertIn('route.validate_redump(_dump_files(src))',after)

    def test_dump_executable_inventory_ignores_xml_only(self):
        import sys
        import tempfile
        from unittest import mock
        with mock.patch.object(sys,'path',[str(ROOT/'scripts'),str(ROOT/'scripts/native_1c_bootstrap'),*sys.path]):
            import form_results_suite as suite
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in suite.route.EXECUTABLE_MODULES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(suite.route.sources()[name])
            (root/'SerializerExtra.xml').write_bytes(b'<changed/>')
            # Reader seam isolates Windows file metadata, not inventory logic.
            with mock.patch.object(suite.full,'secure_bytes',side_effect=lambda path,limit:path.read_bytes()):
                files=suite._dump_executable_files(root)
                self.assertEqual(suite.route.validate_executable_redump(files),suite.route.module_digest())
                (root/'Unknown.bsl').write_bytes(b'code')
                with self.assertRaises(suite.full.FullError):suite._dump_executable_files(root)

    def test_owner_state_explicitly_client_context(self):
        source=self.read('scripts/form_results_packet/Launcher/Forms/Main/Ext/Form/Module.bsl')
        self.assertIn('&AtClient\nVar Request, Flow, Shared, CompletionCount, ResultKind, ResultMatches, WaitTurns, Records;',source)

    def test_owner_entry_precedes_trace_and_startup_failure_exits(self):
        source=self.read('scripts/form_results_packet/Launcher/Forms/Main/Ext/Form/Module.bsl')
        owner=source.split('Procedure OwnerOpen(Cancel)',1)[1].split('EndProcedure',1)[0]
        self.assertLess(owner.index('Marker(Request.entered'),owner.index('SaveJSON(Request.trace'))
        self.assertIn('Try',owner)
        self.assertIn('Except',owner)
        self.assertIn('ЗавершитьРаботуСистемы(Ложь)',owner)
        self.assertNotIn('ErrorDescription(',owner)

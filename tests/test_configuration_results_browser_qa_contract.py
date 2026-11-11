"""Offline static contracts; never start a browser, host or native process."""
import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationResultsBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'tests/browser_ui/configuration_results_browser_qa.mjs').read_text()
        cls.workflow = (ROOT/'.github/workflows/configuration-results-browser-qa.yml').read_text()
        cls.docs = (ROOT/'docs/configuration-results-browser-qa.md').read_text()

    def contains(self, *parts):
        for part in parts:
            with self.subTest(part=part): self.assertIn(part, self.source)

    def test_exact_four_scenarios_and_seventeen_business_events(self):
        names = ast.literal_eval(self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(names, ['owned_result_once_with_shared_additional','owner_pause_before_close_refusal_undefined',
            'independent_retained_draft_and_natural_close','lost_confirmed_close_copy_only_no_replay'])
        plan = ast.literal_eval(self.source.split('const businessPlan=',1)[1].split(';',1)[0])
        self.assertEqual([len(part) for part in plan],[3,5,6,3])
        self.assertEqual(sum(map(len,plan)),17)
        self.assertEqual(self.source.count('await scenario(scenarioNames['),4)
        self.contains('businessEvents.slice(start),businessPlan[index]','results.map(row=>row.name),scenarioNames','total:4')

    def test_closed_reviewed_push_workflow(self):
        self.assertIn('branches: [codex/configuration-results-browser-reviewed]',self.workflow)
        for value in ('contents: read','persist-credentials: false','cancel-in-progress: false',
            'node tests/browser_ui/configuration_results_browser_qa.mjs','timeout-minutes: 5'):
            self.assertIn(value,self.workflow)
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'secrets.', 'sudo ', 'sysctl ', '--no-sandbox', 'contents: write', 'container:'):
            self.assertNotIn(forbidden,self.workflow)

    def test_dependencies_and_actions_remain_pinned(self):
        self.assertEqual(json.loads((ROOT/'tests/browser_ui/package.json').read_text())['devDependencies'],{'playwright':'1.64.1'})
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund',self.workflow)
        self.assertIn('install chromium --no-shell',self.workflow)
        self.assertNotIn('--with-deps',self.workflow)
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}',self.workflow)),3)
        self.contains("report.versions.playwright,'1.64.1'")

    def test_real_application_family_launcher(self):
        self.contains("'examples/configuration-form-results'),'--application-host','--browser-session'",'const parse=applicationLaunchReader()',
            "phase='results_host_start'","phase='results_fault_host_start'")
        self.assertNotIn('fixtureCode',self.source)
        self.assertNotIn('dispatch_completion(',self.source)
        self.assertNotIn('call_routine(',self.source)

    def test_existing_nonroot_sandbox_and_process_ownership(self):
        self.contains('process.getuid()===0','chromiumSandbox:true',"probe.goto('chrome://sandbox')",'sandboxCommand(args)',
            'sandboxStatus(',"'process_not_direct_child'","'process_group_not_owned'","'owned_process_identity_changed'",'await groupGone(hostGroup)',
            "readlinkSync('/proc/'+browserGroup.pid+'/exe')",'process.env.TMPDIR=home')
        self.assertEqual(self.source.count('chromium.launch('),1)
        for forbidden in ('--no-sandbox','chromiumSandbox:false','executablePath:','ignoreDefaultArgs:','sudo ','sysctl '):
            self.assertNotIn(forbidden,self.source)

    def test_deadlines_caps_and_no_transport_retry(self):
        self.contains('startedAt+220000','startedAt+240000','if(rpc>=96)','attachmentRequests<=96',
            'maxRetries:0','maxRedirects:0',"'late_reply_gate_timeout'","'natural_shutdown_timeout'")
        self.assertNotIn('page.waitForTimeout(',self.source)
        self.assertNotIn("'/tmp",self.source)

    def test_exact_source_binding_and_clean_checkout(self):
        self.contains("'tracked_checkout_dirty'","'source_binding_changed'","git('rev-parse','HEAD^{tree}')", "'frontend/form'", "'frontend/configuration'",
            "'examples/configuration-form-results'","'tests/test_configuration_form_results.py'","'tests/test_configuration_results_browser_qa_contract.py'",
            "'docs/configuration-form-results.md'","'docs/configuration-results-browser-qa.md'","'.github/workflows/configuration-results-browser-qa.yml'")
        self.assertNotIn('build.mjs',self.source)

    def test_owner_graph_and_completion_envelope_are_observed(self):
        self.contains("assert.equal(result.dialogCapability,'yadinassi-owned-dialog/1')","assert.deepEqual(result.dialogs,[],'unexpected_dialog')","exactKeys(result,'protocol state error session form updates dialogCapability dialogs')","exactKeys(item,'id entry title owner blocked')",
            "'owner_pause_graph'","'owner_identity_graph'","'update_requires_retired_child'","exactKeys(update,'session form')",
            "assert.equal(update.form.id,1)","'callback','additional_parameters','_form_target','enrollment'")

    def test_real_delayed_accept_double_click_and_exact_result(self):
        self.contains("report.commandStage='bind_session'","report.commandStage='read_response'","report.commandStage='completed'","'response_body_unavailable'","'ambiguous_locator'")
        self.contains('const actual=await auditResponse(response,packet)','observedCommands.set(packet.id,{packet,actual})',
            "assert.deepEqual(observed.packet,packet,'audited_command_mismatch')",'observedCommands.delete(packet.id)',
            "observedCommands.size<96,'audited_command_budget'",'observedCommands.clear();await startHost()')
        self.assertNotIn('await response.json()',self.source)
        self.contains('await repeatClick(action(\'Use value\'))','control.click();control.click();',
            'delayed={arrived,wait}',"completion(actual.result,'Selected once')",'gate.arrived();await bounded(gate.wait',
            "'busy_accept_enabled'","'retirement_before_response_delivery'", "['Completion count: 1']", "'completion_count_or_additional_changed'")
        self.assertNotIn('route.fulfill({body:',self.source)
        self.assertNotIn('route.fulfill({json:',self.source)

    def test_owner_pause_and_real_before_close_refusal(self):
        self.contains("'paused_owner_input_enabled'","'paused_owner_command_enabled'","'paused_owner_close_enabled'","'paused_owner_dispatched'",
            "await toggle(true);await command('Use value','AcceptButton')","lastApplicationResult.updates,[],'refused_close_completed'",
            "'refused_child_retired'","await toggle(false);await closeForm()","completion(lastApplicationResult,'Closed without a selection')")

    def test_independent_raw_draft_not_fabricated_same_owner_conflict(self):
        self.contains("'  independent raw draft  '","'navigation_flushed_sibling'","'retained_input_replaced'","'sibling_received_callback'",
            'sameOwnerRawConflictBrowserEvidence:false',"await action('Refresh state').click();await refreshed")
        self.assertIn('same-owner conflicting raw draft is not a browser claim',self.docs)
        self.assertNotIn('dispatchEvent(new Event(\'input\'',self.source)
        self.assertNotIn('node.value=',self.source)

    def test_real_confirmed_close_response_is_dropped_not_fabricated(self):
        self.contains('const actual=await auditResponse(response,packet)',"event.control==='AcceptButton'",'dropNextClose=false',
            "actual.result.form.result.state.kind,'closed'", "'real_child_not_retired'","completion(actual.result,'A chosen value')",
            'report.confirmedCloseBeforeLoss={retired:true,ownerUpdated:true,completionCount:1}',"return await route.abort('failed')")
        self.assertEqual(self.source.count('dropNextClose=true'),1)

    def test_locked_copy_and_no_retry_including_refresh(self):
        self.contains("'GreetingLabel:   raw copy after loss  '","'copy_not_selectable'","'locked_refresh_enabled'",
            "'locked_command_enabled'","'locked_close_enabled'","'locked_intent_replayed'",'getComputedStyle(node).userSelect',
            "await action('Refresh state').evaluate(node=>node.click())")

    def test_natural_shutdown_before_fault_and_honest_limits(self):
        self.assertEqual(self.source.count('await naturalStop();'),1)
        natural=self.source.split('async function naturalStop(){',1)[1].split('let delayed=',1)[0]
        self.assertNotIn('signalGroup(',natural)
        self.contains('{code:0,signal:null}','report.naturalShutdown=true','nativeLifecycleParity:false','durableCallbackRecovery:false')
        self.assertIn('forced owned cleanup',self.docs)
        self.assertIn('not native lifecycle parity',self.docs)

    def test_exact_redacted_artifacts_and_no_private_report_fields(self):
        paths=[line.strip().rsplit('/',1)[-1] for line in self.workflow.splitlines() if 'yadinassi-results-browser-artifacts/' in line]
        self.assertEqual(paths,['result.json','manifest.json','results-completion.png','results-refusal.png','results-retained.png','results-locked-copy.png'])
        self.contains("'capability_leak'","'capability_not_removed'","'only_resume_storage'","'unexpected_artifact'",'resultSha256:sha256(raw)')
        for forbidden in ('report.url','report.headers','report.response','report.stack','console.log(error','recordHar','tracing.start'):
            self.assertNotIn(forbidden,self.source)

    def test_attachment_refusal_not_replayed(self):
        self.contains("body.action==='heartbeat'&&response.status()===409", "value.error,'busy','unexpected_heartbeat_refusal'",
            "'writer_attachment'","'writer_generation'",'return await route.fulfill({response})')


if __name__=='__main__':unittest.main()

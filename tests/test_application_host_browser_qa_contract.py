"""Closed application-host acquisition contract; no browser launch here."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ApplicationHostBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'tests/browser_ui/application_host_browser_qa.mjs').read_text()
        cls.workflow = (ROOT/'.github/workflows/ui-browser-qa.yml').read_text()

    def test_exact_five_scenarios(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(names, ['shipped_startup_and_commonmodule_servercall',
            'two_tab_takeover_preserves_raw_draft_and_open_host',
            'resume_without_startup_replay_and_dropped_reply_not_retried',
            'real_grace_preserves_beforeexit_refusal','real_grace_closes_only_empty_clean_application'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 5)
        self.assertIn("assert.deepEqual(results.map(row=>row.name),scenarioNames,'incomplete_scenarios')",self.source)

    def test_sandbox_owned_processes_and_cleanup_retained(self):
        self.assertEqual(self.source.count('chromium.launch('),1)
        for text in ['chromiumSandbox:true', "process.platform!=='linux'||process.getuid()===0", 'sandboxCommand(args)',
                     "probe.goto('chrome://sandbox')", 'sandboxStatus(', 'processIdentity(', 'await groupGone(hostGroup)',
                     "'owned_process_identity_changed'", "'browser_socket_path_too_long'"]:
            self.assertIn(text,self.source)
        for forbidden in ['--no-sandbox','chromiumSandbox:false','executablePath:','sudo ','sysctl ']:self.assertNotIn(forbidden,self.source)

    def test_real_lifetime_and_no_timer_mock(self):
        for text in ['startedAt+220000','startedAt+240000','setTimeout(resolve,31500)',
                     "Date.now()-before>=30000", "host.exitCode,0,'ordinary_clean_host_exit'",
                     "host.signalCode,null,'no_forced_clean_shutdown'", "'refused_exit_retained'", "'open_pending_host_retained'"]:
            self.assertIn(text,self.source)
        for forbidden in ['clock.install','clock.fastForward','grace_seconds=','lease_seconds=','mock.patch','fakeTimers']:
            self.assertNotIn(forbidden,self.source)

    def test_actual_dropped_reply_once_and_fencing(self):
        for text in ["const response=await route.fetch", "return route.abort('failed')", "'dropped_command_really_executed'",
                     "'lost_reply_not_retried'", "'old_writer_fenced'", "'raw_draft_retained'", "'resume_retains_identity'",
                     "'startup_not_replayed'", "'uncertain_takeover_disabled'"]:self.assertIn(text,self.source)

        self.assertEqual(self.source.count("state(page).messages,['Calculated in the owned server process','8']"),2)
        self.assertIn("if(await page.locator('.browser-ownership').getAttribute('data-role')==='observer')",self.source)

        self.assertIn("await closedReply;await idle()",self.source)
        self.assertIn("'explicit_application_close_completed'",self.source)
        self.assertIn("report.routeFailure=routeFailure",self.source)
        self.assertIn("'application_close_exchange':'rpc_exchange'",self.source)

        for text in ["detachReceipts.set(key,{attachment,accept})", "'detach_http_accepted'", "'detach_attachment'",
                     "'detach_released_writer'", "'detach_generation'", "await bounded(received,remaining(10000),'detach_receipt_timeout')",
                     "lifetimeStage='detach_server_receipt'", "await p.goto('about:blank')"]:
            self.assertIn(text,self.source)
        self.assertNotIn('const confirmed=p.waitForResponse',self.source)
        self.assertIn('return Reflect.apply(original,this,arguments)',self.source)
        self.assertIn('detachDiagnostics={pagehide:0,fetch:0,request:0,route:0,receipt:0,matched:0}',self.source)
        self.assertIn("message.text()==='ya-qa-detach-fetch'",self.source)

    def test_closed_attachment_and_business_wire(self):
        for text in ["exactKeys(body,'action instance')", "exactKeys(body,'action generation pending')",
                     "parsed.pathname==='/attachment'", '!parsed.search', 'launchURL(match[0].slice(0,-13))',
                     "'yadinassi-configuration-app/3'", '/^open-[0-9a-f]{32}-[1-9][0-9]*$/', 'if(rpc>=100)']:
            self.assertIn(text,self.source)
        legacy=(ROOT/'tests/browser_ui/configuration_browser_qa.mjs').read_text()
        self.assertIn("'yadinassi-configuration-app/3'",legacy)
        self.assertIn('/^open-[0-9a-f]{32}-[1-9][0-9]*$/',legacy)
        self.assertEqual(legacy.count('await scenario(scenarioNames['),6)

    def test_shipped_source_and_derived_fixture_bound(self):
        for text in ["'examples/configuration-application-host'", "'tests/test_application_host_browser_qa_contract.py'",
                     "git('rev-parse','HEAD^{tree}')", "'source_binding_changed'", "'tracked_checkout_dirty'",
                     'report.fixtureBindings', "'fixture_patch_identity'", "'fixture_lifecycle_identity'",
                     "!stat.isSymbolicLink()", "'--application-host'"]:self.assertIn(text,self.source)

    def test_artifacts_no_credentials_storage_or_raw_errors(self):
        for text in ["'only_resume_storage'", "session:['yadinassi.browser.resume/1']", "'capability_leak'",
                     "tokens.push(value.credential)", "tokens.push(value.resume)", "'unexpected_artifact'",
                     'resultSha256:sha256(raw)', 'report.fixtureBindings']:
            self.assertIn(text,self.source)
        for forbidden in ['report.headers','report.url','report.storage','report.response','report.stack']:
            self.assertNotIn(forbidden,self.source)

    def test_exact_opt_in_workflow_and_closed_artifacts(self):
        source=self.workflow
        self.assertIn('codex/application-host-browser-reviewed]',source)
        acquisition=source.split('      - name: Acquire five application host lifetime flows with Chromium sandbox enabled\n',1)[1].split('\n      - ',1)[0]
        self.assertIn("if: github.ref == 'refs/heads/codex/application-host-browser-reviewed'",acquisition)
        self.assertIn('timeout-minutes: 5',acquisition)
        self.assertIn('QA_SOURCE_SHA: ${{ github.sha }}',acquisition)
        self.assertIn('run: node tests/browser_ui/application_host_browser_qa.mjs',acquisition)
        upload=source.split('      - name: Publish only application host screenshots and redacted source-bound report\n',1)[1].split('\n      - ',1)[0]
        paths=upload.split('          path: |\n',1)[1].split('          if-no-files-found:',1)[0]
        expected=['result.json','manifest.json','application-startup.png','application-takeover-draft.png','application-resumed.png','application-exit-refused.png','application-clean.png']
        self.assertEqual([line.strip() for line in paths.splitlines()],['${{ runner.temp }}/yadinassi-application-host-browser-artifacts/'+n for n in expected])
        self.assertIn('permissions:\n  contents: read',source)
        for forbidden in ['workflow_dispatch:','pull_request:','schedule:','secrets.','sudo ','sysctl ']:self.assertNotIn(forbidden,source)

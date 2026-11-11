"""Static contracts only: no browser launch, fixture execution or installation."""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PostingApplicationBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/posting_application_browser_qa.mjs').read_text(encoding='utf-8')

    def contains(self, *parts):
        for part in parts:
            with self.subTest(part=part):
                self.assertIn(part, self.source)

    def test_exact_four_flows(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(names, ['typed_write_post_undo_sql_readback',
            'repeat_late_navigation_dirty_sibling_close_fence', 'source_cancellation_atomicity',
            'persisted_reopen_natural_shutdown'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 4)
        self.contains('results.map(row=>row.name),scenarioNames', 'total:4')

    def test_sandbox_and_owned_processes(self):
        self.contains('chromiumSandbox:true', "probe.goto('chrome://sandbox')", 'sandboxCommand(args)',
            'sandboxStatus(', "'process_not_direct_child'", "'process_group_not_owned'",
            "'owned_process_identity_changed'", 'await groupGone(hostGroup)', 'process.getuid()===0')
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)

    def test_bounded_no_retry(self):
        self.contains('startedAt+220000', 'startedAt+240000', 'if(rpc>=180)',
            'attachmentRequests<=96', 'maxRetries:0', 'maxRedirects:0', 'maxBuffer:16384',
            "'reply_budget'", "'late_reply_gate_timeout'", "'natural_shutdown_timeout'")

    def test_owned_absolute_runner_temp_and_clean_source(self):
        self.contains('const temporary=process.env.RUNNER_TEMP',
            "if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)",
            "owned=await mkdtemp(path.join(temporary,'p-'))", "process.env.TMPDIR=home",
            "'browser_profile_not_owned'", "'tracked_checkout_dirty'", "'source_binding_changed'",
            "git('rev-parse','HEAD^{tree}')", "'tests/test_posting_application_browser_qa_contract.py'",
            "'docs/posting-application-browser-qa.md'")
        self.assertNotIn("'/tmp", self.source)
        self.assertNotIn("temporary!=='/workspace/", self.source)
        self.assertNotIn('process.env.TMPDIR!==temporary', self.source)

    def test_explicit_profile_and_source(self):
        self.contains("'examples/configuration-posting-application'", "'--posting-application'", "'--f'",
            'import_posting_application', 'posting_runtime=PROFILE', 'SQLiteCatalogBackend.create_posting',
            'explicitHostManifest:true', 'nativeStandardFormWrite:false')
        self.assertNotIn('--document-objects', self.source)

    def test_fixture_is_parseable_and_read_only(self):
        fixture = self.source.split('const fixtureCode=String.raw`',1)[1].split('`;',1)[0]
        ast.parse(fixture)
        self.contains("'?mode=ro'", 'PRAGMA query_only=ON', 'document_posting_state', 'recorder_movement',
            'LEFT JOIN document_posting_state', 'JOIN document_record', "owned_posting_fixture_failed")
        for forbidden in ('DELETE FROM', 'UPDATE ', 'INSERT INTO', 'unlink(', 'print(cards)'):
            self.assertNotIn(forbidden, fixture)

    def test_atomic_write_post_undo_sql_assertions(self):
        self.contains("command('Write document','WriteButton')", "command('Post document','PostButton')",
            "command('Undo posting','UndoButton')", "assert.deepEqual(db.posted,[['D1',1]])",
            "assert.deepEqual(db.posted,[['D1',0]])", 'assert.deepEqual(db.movements,[])',
            "[['n','1001'],['n','2.50']]", "[['s','First'],['n','2.50'],['b',true]]",
            "'20240229234517'", "event.value.type==='Date'?'type ticks':'type value'")

    def test_actual_replies_not_sleep_only(self):
        self.contains('page.waitForResponse', 'await reply;await idle()', "formReply('cell')",
            "formReply('close')", "formReply('command','WriteButton')", "'posting_outcome'")
        self.assertNotIn('page.waitForTimeout(', self.source)

    def test_duplicate_late_navigation_and_close_fence(self):
        self.contains('control.click();control.click();', "'duplicate_write'", 'delayed={arrived,wait}',
            "packet.method==='application.openRecord'", 'gate.arrived()', 'await bounded(gate.wait',
            "'dirty_sibling_was_closed'", "'close_implicitly_saved'", "'dirty_application_closed'",
            "await value('Note','Sibling draft')")

    def test_cancellation_no_replay_or_fault_switch(self):
        self.contains("await commitInput('Note','cancel')", "command('Post document','PostButton','rejected')",
            "'cancel_changed_persisted_state'", 'injectedUnknownCommit:false', 'restartReceiptRecovery:false')
        for forbidden in ('faultInjection', '--inject-', 'replay_handler', "method:'application.recoverPosting'"):
            self.assertNotIn(forbidden, self.source)

    def test_natural_shutdown_is_required_before_pass(self):
        self.contains("replyFor(packet=>packet.method==='application.close')", "{code:0,signal:null}",
            "'natural_shutdown_failed'", "'reopen_mutated_database'", "'shutdown_mutated_database'")
        self.assertEqual(self.source.count('await naturalStop();'), 2)
        natural = self.source.split('async function naturalStop(){',1)[1].split('let delayed=',1)[0]
        self.assertNotIn('signalGroup(', natural)
        self.assertNotIn('stopHost(', natural)

    def test_opaque_wire_and_redacted_artifacts(self):
        self.contains('/^record-[1-9][0-9]{0,8}$/', '/^form-[1-9][0-9]*$/',
            "'persistent_uuid_leak'", "'private_host_envelope_leak'", "'capability_leak'",
            "'capability_not_removed'", "'only_resume_storage'", "'unexpected_artifact'",
            'resultSha256:sha256(raw)', 'sha256:sha256(bytes)')
        for forbidden in ('report.url', 'report.headers', 'report.response', 'report.stack', 'console.log(error'):
            self.assertNotIn(forbidden, self.source)

    def test_command_outcome_is_bound_to_active_session(self):
        self.contains("nodes.findIndex(node=>!node.hidden)", "'session_panel_binding'",
            'lastApplicationState?.sessions[index]?.id', 'packet.params.session===session',
            "data.result.session,session,'command_session_changed'",
            'posting.filter(item=>item.session===session)', "outcomes.length,1,'command_outcome_count'",
            "outcomes[0].state,state,'posting_outcome'")
        self.assertNotIn('posting.some(item=>item.state===state)', self.source)

    def test_application_close_fence_has_visible_notice_and_preserves_panels(self):
        self.contains('const retainedPanels=await panels().count()',
            "Close each form, including hidden tabs, before closing the application.",
            "await panels().count(),retainedPanels,'application_close_removed_panels'")

    def test_documentation_limits_sql_snapshot_claim(self):
        docs=(ROOT/'docs/posting-application-browser-qa.md').read_text(encoding='utf-8')
        self.assertIn('document/posting/movement query snapshot',docs)
        self.assertIn('not journal, metadata or every database table',docs)
        self.assertNotIn('complete independent SQL snapshot',docs)

    def test_exact_heartbeat_busy_exception(self):
        self.contains("body.action==='heartbeat'&&response.status()===409",
            "exactKeys(value,'protocol error')", "value.error,'busy','unexpected_heartbeat_refusal'",
            '++report.heartbeatBusy<=attachmentRequests')

    def test_reviewed_transport_budgets_with_unchanged_total(self):
        self.contains('rpcFetchMs=35000,rpcReplyMs=50000', 'timeout:remaining(rpcFetchMs)',
            'timeout:remaining(rpcReplyMs)', 'startedAt+220000', 'startedAt+240000')

    def test_exact_business_plan_and_duplicate_owner_fences(self):
        self.contains("businessEvents.slice(start),businessPlan[index]", "'business_rpc_plan_changed'",
            "'duplicate_write_rpc'", "'duplicate_open_rpc'", "'late_reply_changed_owner'",
            "'local_close_fence_dispatched'")
        plan=self.source.split('const businessPlan=',1)[1].split(';',1)[0]
        import json
        rows=json.loads(plan.replace("'",'"'))
        self.assertEqual([len(row) for row in rows],[12,11,5,5])
        self.assertEqual(sum(len(row) for row in rows),33)

    def test_single_reviewed_route_and_closed_artifact_paths(self):
        workflow=(ROOT/'.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')
        self.assertIn('codex/posting-application-browser-reviewed]',workflow)
        step=workflow.split('      - name: Acquire four posting application flows with Chromium sandbox enabled\n',1)[1].split('\n      - ',1)[0]
        self.assertIn("if: github.ref == 'refs/heads/codex/posting-application-browser-reviewed'",step)
        self.assertIn('timeout-minutes: 5',step)
        self.assertIn('node tests/browser_ui/posting_application_browser_qa.mjs',step)
        upload=workflow.split('      - name: Publish only posting application screenshots and redacted source-bound report\n',1)[1]
        paths=upload.split('          path: |\n',1)[1].split('          if-no-files-found:',1)[0]
        self.assertEqual([p.strip() for p in paths.splitlines()],[
            '${{ runner.temp }}/yadinassi-posting-browser-artifacts/'+name for name in
            ['result.json','manifest.json','posting-cycle.png','posting-isolation.png','posting-cancelled.png','posting-reopened.png']])
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund',workflow)
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'schedule:', 'secrets.', 'sudo ', '--no-sandbox'):
            self.assertNotIn(forbidden,workflow)

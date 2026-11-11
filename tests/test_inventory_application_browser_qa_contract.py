"""Static acquisition contracts; importing this module never starts a browser."""
import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InventoryApplicationBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/inventory_application_browser_qa.mjs').read_text(encoding='utf-8')
        cls.workflow = (ROOT / '.github/workflows/inventory-application-browser-qa.yml').read_text(encoding='utf-8')
        cls.docs = (ROOT / 'docs/inventory-application-browser-qa.md').read_text(encoding='utf-8')

    def contains(self, *parts):
        for part in parts:
            with self.subTest(part=part):
                self.assertIn(part, self.source)

    def test_exact_four_scenarios(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0])
        self.assertEqual(names, ['catalog_references_write_without_movements',
            'receipt_issue_reports_periods_unsaved', 'shortage_repeat_late_navigation_dirty_close',
            'natural_restart_persisted_typed_audit'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 4)
        self.contains('results.map(row=>row.name),scenarioNames', 'total:4')

    def test_exact_sixty_business_requests(self):
        plan = json.loads(self.source.split('const businessPlan=', 1)[1].split(';', 1)[0].replace("'", '"'))
        self.assertEqual([len(row) for row in plan], [23, 23, 7, 7])
        self.assertEqual(sum(map(len, plan)), 60)
        self.contains('businessEvents.slice(start),businessPlan[index]', "'business_rpc_plan_changed'",
            "businessEvents.push('reference:'+packet.params.action.action)",
            "businessEvents.push('report:'+packet.params.report)")

    def test_unified_launcher_never_passes_an_external_source_directory(self):
        launch = self.source.split('async function startHost(){', 1)[1].split('const button=', 1)[0]
        self.assertIn("const args=['-m','yadinassi','--ui','--f',path.join(owned,'stock.sqlite')]", launch)
        for forbidden in ('yadinassi.ui.configuration_app', '--inventory-application', 'examples/', '--launch-binding'):
            self.assertNotIn(forbidden, launch)

    def test_fresh_full_source_and_core15_denial(self):
        self.contains('import_inventory_application(files,inventory_runtime=PROFILE)',
            'SQLiteCatalogBackend.create_inventory_application(database,config)',
            'validated_core(config)', 'core.launch_snapshot()', "except BackendError as failure: assert failure.code=='unsupported'",
            "raise AssertionError('core15_ui_grant')", 'assert not database.exists()',
            "snap.route=='inventory' and snap.profile==PROFILE", '{f.path:f.content for f in snap.files}==files')

    def test_fixture_is_ast_parseable_and_does_not_seed_business_rows(self):
        code = self.source.split('const fixtureCode=String.raw`', 1)[1].split('`;', 1)[0]
        ast.parse(code)
        for forbidden in ('Interpreter(', 'InventoryReports', 'Query(', 'INSERT INTO', 'UPDATE ',
                          'DELETE FROM', '.execute("', '.write(', '.post(', 'unlink(', 'requests.'):
            self.assertNotIn(forbidden, code)
        self.assertIn("print('{\"error\":\"owned_inventory_fixture_failed\"}',file=sys.stderr)", code)

    def test_readonly_typed_audit_pins_one_business_snapshot(self):
        self.contains('SQLiteCatalogBackend(database,read_only=True)', 'backend.begin_read()',
            'reader=DocumentView(owner)', '_accumulation_port(owner).scan(register.identity)',
            'type(card.key) is CatalogKey', 'type(card.key) is DocumentKey', 'type(card.date) is datetime',
            'type(value) is Decimal', 'type(row.direction) is AccumulationDirection',
            'sha256(database.read_bytes()).digest()==before')
        self.assertEqual(self.source.count('backend.begin_read()'), 1)

    def test_catalog_creation_and_typed_picker_are_real_ui_actions(self):
        self.contains("await action('Save record').click()", "await commitInput('Code',code)",
            "await choose('Warehouse','W1','Main warehouse')", "await choose('Product, row 1','P1','Widget')",
            "'reference_text_editable'", "'unissued_picker_ticket'", "'crossed_picker_owner'", "'unissued_choice'")

    def test_write_post_undo_and_decimal_resources(self):
        self.contains("await command('Write document','WriteButton')", "await command('Post document','PostButton')",
            "await command('Undo posting','UndoPostingButton')", "'write_created_movements'",
            "db.quantity,'7.25'", "db.amount,'72.5'", "'QuantityBalance','7.250'",
            "'QuantityReceipt','10.500'", "'QuantityExpense','3.250'")

    def test_periods_are_explicit_and_unsaved_values_excluded(self):
        self.contains("'balance_not_exclusive'", "'inclusive_single_second'",
            "'2026-11-11T12:00:00'", "'2026-11-11T12:00:01'", "'unsaved_draft_changed_persistence'",
            "'mutating_path_retained_report'", "await value('Quantity, row 1','99')")

    def test_readonly_report_cells_never_expose_capabilities(self):
        self.contains("exactKeys(projection,'report view at start end columns rows')",
            "if(['Catalog','Document'].includes(cell.type))exactKeys(cell,'type text')",
            "panel.locator('table button,table input,table select').count(),0", "'report_not_readonly'",
            "'persistent_uuid_in_request'", "'persistent_uuid_leak'", "'private_host_envelope_leak'")

    def test_shortage_refuses_without_changed_saved_rows(self):
        self.contains("'shortage_not_rejected'", "'shortage_changed_persisted_state'",
            "'duplicate_post_rpc'", "'save_recovery_required','dirty_close_not_refused'",
            "'local_close_fence_dispatched'")

    def test_real_response_delay_and_exact_owner_fence(self):
        self.contains("if(delayed&&packet.method==='application.openRecord')", 'gate.arrived()',
            'await bounded(gate.wait', 'await route.fulfill({response})', "'late_reply_changed_owner'",
            "'duplicate_open_rpc'", "'duplicate_write_rpc'", "'duplicate_write_revision'",
            'control.click();control.click();')
        self.assertNotIn('page.waitForTimeout(', self.source)

    def test_natural_exit_and_second_host_are_required(self):
        self.assertEqual(self.source.count('await naturalStop();'), 2)
        self.contains("replyFor(packet=>packet.method==='application.close')", '{code:0,signal:null}',
            "'natural_shutdown_failed'", "'reopen_mutated_database'", "'shutdown_mutated_database'")
        natural = self.source.split('async function naturalStop(){', 1)[1].split('let delayed=', 1)[0]
        self.assertNotIn('signalGroup(', natural)
        self.assertNotIn('stopHost(', natural)

    def test_no_unknown_commit_or_restart_recovery_claim(self):
        self.contains('injectedUnknownCommit:false', 'restartReceiptRecovery:false', 'nativeStandardFormWrite:false')
        for forbidden in ('faultInjection', '--inject-', "method:'application.recoverPosting'",
                          'dispatchEvent(', 'page.addInitScript(', 'evaluateOnNewDocument', 'setContent('):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('not restart recovery for an unknown commit', self.docs)

    def test_strict_sandbox_and_process_identity(self):
        self.contains('chromiumSandbox:true', "probe.goto('chrome://sandbox')", 'sandboxCommand(args)',
            'sandboxStatus(', "'process_not_direct_child'", "'process_group_not_owned'",
            "'owned_process_identity_changed'", 'await groupGone(hostGroup)', 'process.getuid()===0')
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)
            self.assertNotIn(forbidden, self.workflow)

    def test_loopback_only_and_no_retry(self):
        self.contains('applicationAllowedRequest(target)', 'allowedRequest(target,origin)',
            "parsed.origin===origin", "parsed.pathname==='/attachment'", 'maxRetries:0', 'maxRedirects:0')
        self.assertNotIn('route.fulfill({json:', self.source)
        self.assertNotIn('route.fulfill({body:', self.source)

    def test_bounded_execution_and_artifacts(self):
        self.contains('startedAt+220000', 'startedAt+240000', 'if(rpc>=180)', 'attachmentRequests<=96',
            'rpcFetchMs=35000,rpcReplyMs=50000', 'maxBuffer:16384', 'stat.size<=4*1024*1024',
            'Buffer.byteLength(raw)<=65536', "'late_reply_gate_timeout'", "'natural_shutdown_timeout'")
        self.assertIn('timeout-minutes: 5', self.workflow)

    def test_owned_temp_and_fail_closed_cleanup(self):
        self.contains('const temporary=process.env.RUNNER_TEMP', '!path.isAbsolute(temporary)',
            "owned=await mkdtemp(path.join(temporary,'p-'))", 'process.env.TMPDIR=home',
            "'browser_socket_path_too_long'", "'browser_profile_not_owned'", "'owned_directory_cleanup_unverified'")
        self.assertNotIn("'/tmp", self.source)
        self.assertNotIn('RUNNER_TEMP:', self.workflow)

    def test_exact_heartbeat_busy_exception(self):
        self.contains("body.action==='heartbeat'&&response.status()===409", "exactKeys(value,'protocol error')",
            "value.error,'busy','unexpected_heartbeat_refusal'", '++report.heartbeatBusy<=attachmentRequests')

    def test_manifest_covers_source_harness_and_route(self):
        self.contains("'examples/configuration-inventory-application'", "'frontend/configuration/src/reports.mjs'",
            "'yadinassi/sqlite_launch.py'", "'tests/test_inventory_application_browser_qa_contract.py'",
            "'docs/inventory-application-browser-qa.md'", "'source_manifest_missing'",
            "'tracked_checkout_dirty'", "'source_binding_changed'", "git('rev-parse','HEAD^{tree}')")
        self.assertIn('All business audit rows share one read lease', self.docs)

    def test_fixed_redacted_diagnostics(self):
        self.contains("'capability_leak'", "'capability_not_removed'", "'only_resume_storage'",
            "'unexpected_artifact'", 'resultSha256:sha256(raw)', 'sha256:sha256(bytes)',
            'const diagnosticPhases=', 'const diagnosticReasons=', 'diagnosticReasons.find(code=>error?.message===code||',
            "checkpoint('audit_document_quantity')", "checkpoint('screenshot_storage')",
            'scenario:activeScenario', "report.lastCommandOutcome=['saved','rejected','uncertain','committed']")
        for forbidden in ('report.url', 'report.headers', 'report.response', 'report.stack', 'console.log(error'):
            self.assertNotIn(forbidden, self.source)

    def test_one_reviewed_workflow_exact_artifact_allowlist(self):
        self.assertIn('branches: [codex/inventory-application-browser-reviewed]', self.workflow)
        self.assertIn('contents: read', self.workflow)
        self.assertIn('persist-credentials: false', self.workflow)
        self.assertIn('node tests/browser_ui/inventory_application_browser_qa.mjs', self.workflow)
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund', self.workflow)
        paths = self.workflow.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines()], [
            '${{ runner.temp }}/yadinassi-inventory-browser-artifacts/' + name for name in
            ['result.json', 'manifest.json', 'inventory-cards.png', 'inventory-reports.png',
             'inventory-fences.png', 'inventory-reopened.png']])
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}', self.workflow)), 3)
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'schedule:', 'secrets.'):
            self.assertNotIn(forbidden, self.workflow)

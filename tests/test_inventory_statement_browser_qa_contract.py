"""Offline source contracts only. No fixture, host, browser or installer runs."""
import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InventoryStatementBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/inventory_statement_browser_qa.mjs').read_text(encoding='utf-8')
        cls.workflow = (ROOT / '.github/workflows/inventory-statement-browser-qa.yml').read_text(encoding='utf-8')
        cls.docs = (ROOT / 'docs/inventory-statement-browser-qa.md').read_text(encoding='utf-8')
        cls.fixture = cls.source.split('const fixtureCode=String.raw`', 1)[1].split('`;', 1)[0]

    def contains(self, *parts):
        for part in parts:
            with self.subTest(part=part):
                self.assertIn(part, self.source)

    def test_four_closed_scenarios(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0])
        self.assertEqual(names, ['periods_pages_exact_saved_totals', 'typed_filters_closed_choices',
            'raw_draft_retirement_delayed_page', 'natural_restart_new_setup_readonly_audit'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 4)
        self.contains('results.map(row=>row.name),scenarioNames', 'total:4')

    def test_exact_forty_eight_business_requests(self):
        plan = json.loads(self.source.split('const businessPlan=', 1)[1].split(';', 1)[0].replace("'", '"'))
        self.assertEqual([len(row) for row in plan], [8, 21, 13, 6])
        self.assertEqual(sum(map(len, plan)), 48)
        self.contains('businessEvents.slice(start),businessPlan[index]', "'business_rpc_plan_changed'",
            "businessEvents.push('setup:'+packet.params.action)", "businessEvents.push('page')",
            "businessEvents.push('report:'+packet.params.periodicity)")

    def test_stored_source_launcher_only(self):
        launch = self.source.split('async function startHost(){', 1)[1].split('const button=', 1)[0]
        self.assertIn("const args=['-m','yadinassi','--ui','--f',path.join(owned,'stock.sqlite')]", launch)
        for item in ('--inventory-application', '--launch-binding', 'examples/', 'yadinassi.ui.configuration_app'):
            self.assertNotIn(item, launch)

    def test_owned_fixture_ast_and_exact_authored_hash(self):
        ast.parse(self.fixture)
        self.assertIn('Fixture SHA256: `' + sha256(self.fixture.encode()).hexdigest() + '`', self.docs)
        self.assertIn("print('{\"error\":\"owned_statement_fixture_failed\"}',file=sys.stderr)", self.fixture)
        for item in ('INSERT INTO', 'UPDATE ', 'DELETE FROM', 'sqlite3.connect', '.execute("', '.execute(\''):
            self.assertNotIn(item, self.fixture)

    def test_typed_seed_has_one_transaction_and_one_root_post(self):
        create = self.fixture.split("if sys.argv[1]=='create':", 1)[1].split("elif sys.argv[1]=='audit':", 1)[0]
        self.assertEqual(create.count('backend.begin_write('), 1)
        self.assertEqual(create.count('owner.commit()'), 1)
        self.assertEqual(create.count('operations.execute('), 1)
        for item in ('owner.create(CatalogDraft(', 'range(1,53)', 'len(owner.commit())==54',
                     'TabularSectionRows(', 'TabularRow(', "command='Post'", "receipt.state=='committed' and receipt.accepted"):
            self.assertIn(item, create)
        self.assertIn('one typed catalog transaction', self.docs)

    def test_seed_writes_precede_browser_launch(self):
        main = self.source.split('async function main(){', 1)[1]
        self.assertLess(main.index("inventoryFixture('create')"), main.index('chromium.launch('))
        self.assertLess(main.index("inventoryFixture('audit')"), main.index('chromium.launch('))
        self.contains('beforeBrowser:true,typedOnly:true', 'setupCatalogs:54,setupDocuments:1,setupMovements:52')

    def test_full_source_profile_and_core15_denial(self):
        self.contains('import_inventory_application(files,inventory_runtime=PROFILE)',
            'SQLiteDBContext.create_inventory_application(database,config)', 'assert not database.exists()',
            'validated_core(config)', 'core.launch_snapshot()', "failure.code=='unsupported'",
            "snap.route=='inventory' and snap.profile==PROFILE", '{f.path:f.content for f in snap.files}==files')

    def test_audit_uses_one_read_snapshot_and_no_report_or_write_api(self):
        audit = self.fixture.split("elif sys.argv[1]=='audit':", 1)[1].split("else: raise AssertionError('fixture_mode')", 1)[0]
        self.assertEqual(audit.count('backend.begin_read()'), 1)
        for item in ('InventoryReports', 'InventoryRootOperations(', '.execute(', '.create(', '.commit(', 'Query(', 'Interpreter('):
            self.assertNotIn(item, audit)
        self.assertIn('SQLiteCatalogBackend(database,read_only=True)', audit)
        self.assertIn('sha256(database.read_bytes()).digest()==before', audit)
        self.assertIn('fingerprint.append(repr(card))', audit)
        self.assertIn('snap.source_digest', audit)

    def test_audit_checks_real_typed_saved_rows(self):
        self.contains('type(card.key) is CatalogKey', 'type(card.key) is DocumentKey',
            'type(card.date) is datetime', 'type(v) is Decimal', 'DocumentView(owner)',
            '_accumulation_port(owner).scan(register.identity)', 'row.direction is AccumulationDirection.RECEIPT',
            'len(partition.rows)==52', 'quantity==Decimal(1378) and amount==Decimal(13780)',
            "'readonly_audit_changed'")

    def test_all_periodicities_and_typed_sums(self):
        self.contains("showStatement('Day')", "['Month','None']", "showStatement('None',true)",
            'exactInteger(row[resource+suffix])', '1378n', '13780n', 'OpeningBalance:', 'Receipt:', 'Expense:', 'ClosingBalance:',
            "row.Period.type,'Date'", 'initialAudit.dayTicks', 'initialAudit.monthTicks')

    def test_pages_are_same_snapshot_and_previous_is_exact(self):
        self.contains('first.rows.length,50', 'first.page.total,52', 'second.rows.length,2',
            "pageMove('Next',true)", "pageMove('Previous')", "assert.deepEqual(back,first,'report_page_order')",
            'after.page.snapshot,before.page.snapshot', 'after.page.cursor,expected', 'header(after),header(before)',
            "'duplicate_page_rpc'")

    def test_native_html_date_spelling_and_exact_rpc_boundaries(self):
        self.contains("value.endsWith(':00')?value.slice(0,-3):value", "'report_html_period'",
            "'2026-11-01T00:00:00'", "'2026-11-11T12:00:00'", "'2026-11-12T00:00:00'",
            "'report_period_request'", "'report_period_result'")

    def test_choice_bound_no_partial_and_exact_code(self):
        self.contains("setup.choice.error,'too_many_matches'", "setup.choice.rows,[],'too_many_partial'",
            "search('P001')", "[['P001','Product 001']]", "search('ABSENT')",
            "setup.choice.error,null", "'unissued_setup'", "'unissued_chooser'", "'unissued_row'")

    def test_cancel_empty_all_and_excluded_warehouse_are_distinct(self):
        self.contains("apply('Unused warehouse')", "'excluded_filter_rows'", "'cancel_changed_selection'",
            "filterAction('empty','Warehouse')", "filterAction('clear','Warehouse')",
            "filterAction('empty','Product')", "filterAction('clear','Product')", "'explicit_empty_mismatch'")

    def test_wire_reference_values_are_presentation_only(self):
        self.contains("exactKeys(row,'choice code description')", "exactKeys(f,'id mode text')",
            "exactKeys(projection,'report view at start end columns rows periodicity setup filters page')",
            "exactKeys(cell,'type text')", "panel.locator('table button,table input,table select').count(),0",
            "'persistent_uuid_in_request'", "'persistent_uuid_leak'", "'private_host_envelope_leak'")

    def test_raw_unsent_draft_survives_report_focus_without_form_event(self):
        self.contains("field('Document number').fill('RAW DRAFT')", "await value('Document number','RAW DRAFT')",
            "wireEvents.filter(e=>e.event==='change').length,0,'unexpected_form_change'",
            "getByLabel('From moment (inclusive)',{exact:true}).click()", 'await assertRaw();')
        self.assertGreaterEqual(self.source.count('await assertRaw();'), 5)

    def test_retired_dom_actions_cannot_retarget(self):
        self.contains('const retiredChoice=', "checkpoint('retired_choice');await clickRetired(retiredChoice)",
            'const retiredPage=', "checkpoint('retired_page');await clickRetired(retiredPage)",
            'await handle.evaluate(node=>node.click())', "'retired_dom_dispatched'",
            "commitInput('Document number','Edited')", 'lastApplicationState.reportSetup,null')
        for forbidden in ('dispatchEvent(', 'setContent(', 'page.addInitScript(', 'evaluateOnNewDocument'):
            self.assertNotIn(forbidden, self.source)

    def test_delayed_response_is_real_once_and_busy_fenced(self):
        self.contains("if(delayed&&packet.method==='application.reportPage')", 'gate.arrived()',
            'await bounded(gate.wait', 'await route.fulfill({response})', 'maxRetries:0',
            "await repeatClick(reportButton('Next saved page'))", "'busy_not_fenced'", "'late_owner_changed'")
        self.assertNotIn('route.fulfill({body:', self.source)
        self.assertNotIn('route.fulfill({json:', self.source)

    def test_exact_delivered_observer_and_ui_idle(self):
        self.contains('const observedReplies=new Map()', 'observedReplies.clear()', 'observedReplies.delete(packet.id)',
            "assert.deepEqual(observed.packet,packet,'audited_reply_request')",
            "assert.equal(observed.origin,origin,'audited_reply_origin')", 'observedReplies.set(packet.id,{packet,actual:decoded,origin})',
            'await auditResponse(response,packet)', 'const reportIdle=()=>page.waitForFunction', 'return n&&!n.disabled;')
        self.assertNotIn('.json()', self.source)
        self.assertNotIn('page.waitForTimeout(', self.source)

    def test_real_natural_restart_new_setup_and_pages(self):
        self.assertEqual(self.source.count('await naturalStop();'), 2)
        self.contains("replyFor(packet=>packet.method==='application.close')", '{code:0,signal:null}',
            "'restarted_ticket_reused'", "'restarted_page_reused'", 'lastApplicationState.sessions.length,0')
        stop = self.source.split('async function naturalStop(){', 1)[1].split('let delayed=', 1)[0]
        self.assertNotIn('signalGroup(', stop)
        self.assertNotIn('stopHost(', stop)
        self.contains('restartReceiptRecovery:false', 'nativeWindowParity:false', 'reportWrites:false')

    def test_strict_sandbox_and_owned_process_cleanup(self):
        self.contains('chromiumSandbox:true', "probe.goto('chrome://sandbox')", 'sandboxCommand(args)',
            'sandboxStatus(', "'process_not_direct_child'", "'process_group_not_owned'", "'owned_process_identity_changed'",
            'await groupGone(hostGroup)', 'process.getuid()===0', "'owned_directory_cleanup_unverified'")
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)
            self.assertNotIn(forbidden, self.workflow)

    def test_loopback_attachment_and_exact_busy_exception(self):
        self.contains('applicationAllowedRequest(target)', 'allowedRequest(target,origin)', 'parsed.origin===origin',
            "parsed.pathname==='/attachment'", 'maxRedirects:0', "body.action==='heartbeat'&&response.status()===409",
            "exactKeys(value,'protocol error')", "value.error,'busy','unexpected_heartbeat_refusal'")

    def test_hard_budgets_and_owned_temp(self):
        self.contains('startedAt+220000', 'startedAt+240000', 'if(rpc>=180)', 'attachmentRequests<=96',
            'rpcFetchMs=35000,rpcReplyMs=50000', 'maxBuffer:16384', 'stat.size<=4*1024*1024',
            'Buffer.byteLength(raw)<=65536', 'const temporary=process.env.RUNNER_TEMP',
            '!path.isAbsolute(temporary)', "owned=await mkdtemp(path.join(temporary,'p-'))", 'process.env.TMPDIR=home')
        self.assertNotIn("'/tmp", self.source)
        self.assertNotIn('RUNNER_TEMP:', self.workflow)
        self.assertIn('timeout-minutes: 5', self.workflow)

    def test_manifest_covers_service_controls_source_harness_workflow(self):
        self.contains("'yadinassi/ui/inventory_report_controls.py'", "'yadinassi/ui/report_pages.py'",
            "'yadinassi/accumulation_periods.py'", "'tests/test_inventory_statement_browser_qa_contract.py'",
            "'docs/inventory-statement-browser-qa.md'", "'tests/browser_ui/inventory_statement_browser_qa.mjs'",
            "'source_manifest_missing'", "'tracked_checkout_dirty'", "'source_binding_changed'", "git('rev-parse','HEAD^{tree}')")

    def test_fixed_diagnostics_and_artifact_integrity(self):
        self.contains('const diagnosticPhases=', 'const diagnosticReasons=', 'scenario:activeScenario',
            'report.failureClass=', 'report.observerFailure=', "'malformed_input'", "'unsupported_input'",
            "'capability_leak'", "'capability_not_removed'", "'only_resume_storage'", "'unexpected_artifact'",
            'resultSha256:sha256(raw)', 'sha256:sha256(bytes)', "{flag:'wx'}")
        for item in ('report.url', 'report.headers', 'report.response', 'report.stack', 'console.log(error'):
            self.assertNotIn(item, self.source)

    def test_one_reviewed_only_workflow_and_closed_artifact_allowlist(self):
        self.assertIn('branches: [codex/inventory-statement-browser-reviewed]', self.workflow)
        self.assertIn('contents: read', self.workflow)
        self.assertIn('persist-credentials: false', self.workflow)
        self.assertIn('node tests/browser_ui/inventory_statement_browser_qa.mjs', self.workflow)
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund', self.workflow)
        paths = self.workflow.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual([p.strip() for p in paths.splitlines()], [
            '${{ runner.temp }}/yadinassi-inventory-statement-browser-artifacts/' + name for name in
            ['result.json', 'manifest.json', 'statement-pages.png', 'statement-filters.png', 'statement-fences.png', 'statement-reopened.png']])
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}', self.workflow)), 3)
        for item in ('workflow_dispatch:', 'pull_request:', 'schedule:', 'secrets.'):
            self.assertNotIn(item, self.workflow)

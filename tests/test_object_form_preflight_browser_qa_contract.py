"""Offline source contracts only; importing never starts a fixture or browser."""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ObjectFormPreflightBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/object_form_preflight_browser_qa.mjs').read_text(encoding='utf-8')
        cls.workflow = (ROOT / '.github/workflows/object-form-preflight-browser-qa.yml').read_text(encoding='utf-8')
        cls.docs = (ROOT / 'docs/object-form-preflight-browser-qa.md').read_text(encoding='utf-8')
        cls.fixture = cls.source.split('const fixtureCode=String.raw`', 1)[1].split('`;', 1)[0]

    def contains(self, *parts):
        for part in parts:
            with self.subTest(part=part):
                self.assertIn(part, self.source)

    def test_exact_three_scenarios(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0])
        self.assertEqual(names, ['capacity_refusal_preserves_raw_sibling',
            'repeat_delayed_refusal_small_and_reports', 'natural_restart_same_saved_capacity'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 3)
        self.contains('results.map(row=>row.name),scenarioNames', 'total:3')

    def test_exact_twenty_business_and_twenty_five_total_requests(self):
        plan = json.loads(self.source.split('const businessPlan=', 1)[1].split(';', 1)[0].replace("'", '"'))
        self.assertEqual([len(row) for row in plan], [4, 7, 9])
        self.assertEqual(sum(map(len, plan)), 20)
        self.assertEqual(plan, [
            ['catalog', 'openRecord', 'catalog', 'openRecord'],
            ['openRecord', 'catalog', 'openRecord', 'close:', 'catalog', 'report:StockBalance', 'report:StockMovements'],
            ['close:', 'close', 'catalog', 'openRecord', 'openRecord', 'close:', 'report:StockBalance', 'report:StockMovements', 'close']])
        self.contains('businessEvents.slice(start),businessPlan[index]', "assert.equal(rpc,25,'no_replay')")

    def test_unified_launcher_uses_only_saved_source(self):
        launch = self.source.split('async function startHost(){', 1)[1].split('const button=', 1)[0]
        self.assertIn("const args=['-m','yadinassi','--ui','--f',path.join(owned,'stock.sqlite')]", launch)
        for forbidden in ('yadinassi.ui.configuration_app', '--inventory-application', 'examples/', '--launch-binding'):
            self.assertNotIn(forbidden, launch)

    def test_fixture_hash_and_python_syntax(self):
        ast.parse(self.fixture)
        self.assertEqual(hashlib.sha256(self.fixture.encode()).hexdigest(),
            '1c9b76113c02246d0c8a7221ad243acf17a7017f1adc50ae02587d45d63ee39f')
        self.assertIn("print('{\"error\":\"owned_preflight_fixture_failed\"}',file=sys.stderr)", self.fixture)

    def test_seed_is_typed_explicit_and_before_chromium(self):
        self.contains('SQLiteDBContext.create_inventory_application(database,config)',
            'backend.begin_write(uuid4())', 'owner.create(CatalogDraft(', 'assert len(owner.commit())==2',
            "[('R52',52,'Post'),('R1',1,'Write')]", 'InventoryRootOperations(context,config)',
            "form='Document.Receipt.Form.Card',command=command", "receipt.state=='committed' and receipt.accepted",
            'TabularRow(uuid4(),(cards[\'Products\'],Decimal(i),Decimal(i*10)))')
        self.assertLess(self.source.index("inventoryFixture('create')"), self.source.index('browser=await chromium.launch'))
        self.assertIn('setup writes, not effects performed by the browser', self.docs)

    def test_no_raw_sql_or_generated_bsl_in_fixture(self):
        for forbidden in ('Interpreter(', 'InventoryReports', 'Query(', 'INSERT INTO', 'UPDATE ',
                          'DELETE FROM', '.execute("', '.execute(\'', '.write(', '.post(', 'requests.'):
            self.assertNotIn(forbidden, self.fixture)
        self.assertEqual(self.fixture.count('operations.execute('), 1)

    def test_full_original_source_and_core15_denial(self):
        self.contains('import_inventory_application(files,inventory_runtime=PROFILE)', 'validated_core(config)',
            'core.launch_snapshot()', "except BackendError as failure: assert failure.code=='unsupported'",
            "raise AssertionError('core15_ui_grant')", 'assert not database.exists()',
            "snap.route=='inventory' and snap.profile==PROFILE", '{f.path:f.content for f in snap.files}==files',
            "[r.name for r in config.reports]==['StockMovements','StockBalance','StockTurnovers','StockStatement']")

    def test_readonly_one_lease_typed_audit(self):
        self.contains('SQLiteCatalogBackend(database,read_only=True)', 'reader=DocumentView(owner)',
            '_accumulation_port(owner).scan(register.identity)', 'type(card.key) is CatalogKey',
            'type(card.key) is DocumentKey', 'type(card.date) is datetime', 'type(v) is Decimal',
            'row.direction is AccumulationDirection.RECEIPT', 'repr(card)', 'repr(partition)',
            'str(owner.configuration_generation)', 'snap.source_digest')
        self.assertEqual(self.fixture.count('backend.begin_read()'), 1)
        audit = self.fixture.split("elif sys.argv[1]=='audit':", 1)[1]
        for forbidden in ('begin_write(', 'InventoryRootOperations(', 'operations.execute(', 'create_inventory('):
            self.assertNotIn(forbidden, audit)

    def test_audit_exact_53_saved_rows_and_52_movements(self):
        self.contains("card.posted is (card.number=='R52')", "len(rows)==(52 if card.number=='R52' else 1)",
            'len(documents)==2 and recorder is not None', 'len(partition.rows)==52',
            "resources=={'Quantity':Decimal(i),'Amount':Decimal(i*10)}", 'movements==list(range(1,53))',
            'quantity==Decimal(1378) and amount==Decimal(13780)', "'rows':53,'movements':52")

    def test_audit_file_bytes_and_fingerprint_unchanged(self):
        self.contains('before=sha256(database.read_bytes()).digest()',
            'sha256(database.read_bytes()).digest()==before', "'databaseSha256':before.hex()",
            "assert.deepEqual(inventoryFixture('audit'),initialAudit,'readonly_audit_changed')",
            'databaseSha256:initialAudit.databaseSha256')
        self.assertEqual(self.source.count('unchanged();'), 6)

    def test_capacity_is_known_no_session_no_lock(self):
        self.contains("result.error,'form_capacity','capacity_not_known'",
            "result.session,null,'capacity_allocated_form'", "result.form,null,'capacity_allocated_form'",
            "result.state.sessions,expectedSessions,'capacity_changed_sessions'",
            "result.state.kind,'application','capacity_locked'", "result.state.uncertain,false,'capacity_locked'",
            "'This saved document exceeds the editor row or cell limit. Nothing was opened or changed. Other forms and reports remain available.'")

    def test_raw_draft_owner_pinned_not_arbitrary_sibling(self):
        self.contains('owner=opened.result.session', 'ownerSessions=structuredClone(opened.result.state.sessions)',
            'lastApplicationState.sessions.findIndex(s=>s.id===owner)', "'owner_not_visible'",
            "inputValue(),'RAW DRAFT','draft_changed'", "await field('Description').fill('RAW DRAFT')",
            'await capacity(refused.result,ownerSessions)', "await catalogEntry('Receipt card');await assertRaw()")
        self.assertNotIn('sessions.at(-1)', self.source)

    def test_repeated_click_one_fresh_intent_real_response_only(self):
        self.contains('control.click();control.click();', 'const openIntents=new Set()',
            "!openIntents.has(packet.params.request),'open_request_reused'", 'openIntents.add(packet.params.request)',
            "if(delayed&&packet.method==='application.openRecord')", 'gate.arrived()',
            "await bounded(gate.wait,remaining(10000),'late_reply_gate_timeout')", 'await route.fulfill({response})',
            "businessEvents.length,before+1,'duplicate_open_rpc'")
        for forbidden in ('route.fulfill({json:', 'route.fulfill({body:', 'page.waitForTimeout('):
            self.assertNotIn(forbidden, self.source)

    def test_busy_and_late_reply_keep_owner(self):
        self.contains("'Open selected',exact:true}).isDisabled(),true,'busy_not_fenced'",
            "'Show saved stock',exact:true}).isDisabled(),true,'busy_not_fenced'",
            "checkpoint('delay_release');release()",
            "ownerPanel.isVisible(),true,'late_reply_changed_owner'")
        self.assertIn('if(!pending)await flushPaint()', self.source)
        self.contains("isEditable(),true,'capacity_locked'", 'pending.catch(()=>{});return pending;')
        pending=self.source.split('let arrived,release;',1)[1]
        self.assertLess(pending.index('await returnOwner(true);await assertRaw();'), pending.index("isDisabled(),true,'busy_not_fenced'"))

    def test_small_document_open_and_close_without_refusal_allocation(self):
        self.contains("const smallOpen=async(expectedSession)", "selectNumber('R1')",
            "result.session,expectedSession,'capacity_allocated_form'", "await smallOpen('form-2')",
            "await smallOpen('form-1')", "await value('Quantity, row 1','1.000')",
            "await value('Amount, row 1','10.00')", "locator('.form-table tbody tr').count(),1",
            "!closed.state.sessions.some(s=>s.id===result.session)")
        self.assertIn('exact 32-row boundary is', self.docs)
        self.assertNotIn('selectNumber(\'R32\')', self.source)

    def test_readonly_old_three_reports_only(self):
        self.contains("exactKeys(packet.params,'report at start end')",
            "['StockBalance','StockMovements'].includes(packet.params.report)",
            "exactKeys(projection,'report view at start end columns rows')",
            "panel.locator('table button,table input,table select').count(),0,'report_not_readonly'")
        for forbidden in ('application.reportSetup', 'application.reportPage', 'BalanceAndTurnovers'):
            self.assertNotIn(forbidden, self.source)

    def test_exact_report_period_and_resources(self):
        self.contains("'2026-11-11T12:00:01'", "value.endsWith(':00')?value.slice(0,-3):value",
            "'report_period_request'", "'report_period_result'", "rows[0].QuantityBalance,'1378.000'",
            "rows[0].AmountBalance,'13780.00'", "view==='Balance'?1:52", "ticks:initialAudit.periodTicks",
            "row.RecordType,{type:'String',value:'Receipt'}", "row.Active,{type:'Boolean',value:true}",
            "number(row.Quantity,i+'.000')", "number(row.Amount,String(Number(row.LineNumber.value)*10)+'.00')")

    def test_restore_local_raw_text_then_close_no_save(self):
        flow = self.source.split('await scenario(scenarioNames[2]', 1)[1].split("assert.equal(git('status'", 1)[0]
        self.assertIn("await field('Description').fill('Main warehouse')", flow)
        self.assertLess(flow.index("fill('Main warehouse')"), flow.index('const closed=await closeForm()'))
        self.contains("wireEvents.filter(e=>e.event!=='close').length,0,'unexpected_form_write'")
        for forbidden in ('.press(', "action('Save record')", "command('Write document'", "dispatchEvent("):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('No OnChange,', self.docs)

    def test_natural_restart_not_forced_teardown_success(self):
        self.assertEqual(self.source.count('await naturalStop();'), 2)
        self.assertEqual(self.source.count('await startHost();'), 2)
        self.contains("assert.deepEqual(result,{code:0,signal:null},'natural_shutdown_failed')",
            "await capacity(refused.result,[])", "await smallOpen('form-1')")
        natural = self.source.split('async function naturalStop(){', 1)[1].split('let delayed=', 1)[0]
        self.assertNotIn('signalGroup(', natural)
        self.assertNotIn('stopHost(', natural)

    def test_no_authority_fault_injection_or_dom_state_fabrication(self):
        self.contains('unknownOutcomeInjected:false', 'restartReceiptRecovery:false', 'nativeWindowParity:false')
        for forbidden in ('faultInjection', '--inject-', 'application.recoverPosting', 'page.addInitScript(',
                          'evaluateOnNewDocument', 'setContent(', 'dispatchEvent(', 'localStorage.setItem('):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('restart recovery\nfor an unknown commit', self.docs)

    def test_exact_delivered_observer_binds_request_and_origin(self):
        self.contains('const observedReplies=new Map()', 'observedReplies.clear();openIntents.clear()',
            'const packet=response.request().postDataJSON()', 'observedReplies.delete(packet.id)',
            "assert.deepEqual(observed.packet,packet,'audited_reply_request')",
            "assert.equal(observed.origin,origin,'audited_reply_origin')",
            'observedReplies.set(packet.id,{packet,actual:decoded,origin})', 'await auditResponse(response,packet,trace)')
        self.assertNotIn('.json()', self.source)

    def test_sandbox_ownership_and_no_security_changes(self):
        self.contains('chromiumSandbox:true', "probe.goto('chrome://sandbox')", 'sandboxCommand(args)', 'sandboxStatus(',
            "'process_not_direct_child'", "'process_group_not_owned'", "'owned_process_identity_changed'",
            'await groupGone(hostGroup)', 'process.getuid()===0', 'process.env.TMPDIR=home', "'browser_socket_path_too_long'")
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'sudo ', 'sysctl ', "'/tmp"):
            self.assertNotIn(forbidden, self.source)
            self.assertNotIn(forbidden, self.workflow)

    def test_network_finite_limits_and_exact_heartbeat_exception(self):
        self.contains('applicationAllowedRequest(target)', 'allowedRequest(target,origin)',
            'maxRetries:0', 'maxRedirects:0', 'startedAt+220000', 'startedAt+240000',
            'if(rpc>=180)', 'attachmentRequests<=96', 'rpcFetchMs=35000,rpcReplyMs=50000', 'maxBuffer:16384',
            'stat.size<=4*1024*1024', 'Buffer.byteLength(raw)<=65536', 'body.length<=262144',
            "body.action==='heartbeat'&&response.status()===409", "exactKeys(value,'protocol error')",
            "value.error,'busy','unexpected_heartbeat_refusal'")
        self.assertIn('timeout-minutes: 5', self.workflow)

    def test_source_manifest_and_fixed_diagnostics(self):
        self.contains("'yadinassi/configuration_document.py'", "'yadinassi/inventory_application_sessions.py'",
            "'yadinassi/configuration_posting_document.py'", "'tests/test_document_open_preflight.py'",
            "'docs/object-form-preflight-browser-qa.md'", "'tracked_checkout_dirty'", "'source_binding_changed'",
            'const wireStages=', 'const wireReasons=', 'report.wire={stage:', 'requestBytes:byteCount(',
            'const diagnosticPhases=', 'const diagnosticReasons=', 'report.failureClass=', 'report.observerFailure=')
        for forbidden in ('report.url', 'report.headers', 'report.response', 'report.stack', 'console.log(error)'):
            self.assertNotIn(forbidden, self.source)

    def test_fail_closed_cleanup_and_five_artifact_hashes(self):
        self.contains("await mkdir(output);outputCreated=true", 'await groupGone(browserGroup)',
            "'owned_directory_cleanup_unverified'", "'host_cleanup_unverified'", 'resultSha256:sha256(raw)',
            'sha256:sha256(bytes)', "'capability_leak'", "'only_resume_storage'", "'unexpected_artifact'",
            "'89504e470d0a1a0a'", 'const artifacts=[\'result.json\',\'manifest.json\',...screenshots]')
        self.assertIn('const temporary=process.env.RUNNER_TEMP', self.source)
        self.assertNotIn('RUNNER_TEMP:', self.workflow)

    def test_standalone_reviewed_workflow_exact_allowlist(self):
        self.assertIn('branches: [codex/object-form-preflight-browser-reviewed]', self.workflow)
        self.assertIn('contents: read', self.workflow)
        self.assertIn('persist-credentials: false', self.workflow)
        self.assertIn('node tests/browser_ui/object_form_preflight_browser_qa.mjs', self.workflow)
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund', self.workflow)
        paths = self.workflow.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines()], [
            '${{ runner.temp }}/yadinassi-object-form-preflight-browser-artifacts/' + name for name in
            ['result.json', 'manifest.json', 'preflight-draft.png', 'preflight-usable.png', 'preflight-reopened.png']])
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}', self.workflow)), 3)
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'schedule:', 'secrets.'):
            self.assertNotIn(forbidden, self.workflow)

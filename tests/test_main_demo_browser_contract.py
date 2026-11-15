"""Закрытый контракт нового Chromium сценария; не заменяет реальный браузер."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'tests/browser_ui/main_demo_browser_qa.mjs'
FIXTURE = ROOT / 'tests/browser_ui/main_demo_fixture.py'


class MainDemoBrowserContractTests(unittest.TestCase):
    def test_real_browser_guards_and_bounded_scope(self):
        text = HARNESS.read_text(encoding='utf-8')
        for required in (
            'ordinary_nonroot_runner_required', 'chromiumSandbox:true',
            "assert.equal(report.versions.playwright,'1.64.1')",
            'processIdentity(pid)', 'owned_process_identity_changed',
            "await groupGone(browserGroup)", 'owned_directory_retargeted',
            'allowedRequest(target,origin)', 'mainDemoLaunchOutputReader as launchOutputReader',
            'mainDemoAllowedRequest as allowedRequest', 'if(rpc>=180)',
            'startedAt+280000', 'startedAt+300000',
            'rpcFetchMs=35000,rpcReplyMs=50000', 'timeout:remaining(rpcReplyMs)',
            'report.progress={action:actionLog.length,name,state:',
            'if(report.rpcTail.length>12)report.rpcTail.shift()',
            'diagnosticMethods.has(value)',
            "assert.equal(results.length,5)", "assert.equal(actionLog.length,128",
            "assert.equal(actionLog.length,20", "'--ui','--f'",
        ):
            self.assertIn(required, text)
        workflow = (ROOT/'.github/workflows/main-demo-browser-qa.yml').read_text(encoding='utf-8')
        self.assertIn('branches: [codex/main-demo-browser-reviewed]', workflow)
        self.assertIn('contents: read', workflow)
        for screenshot in ('list.png', 'editor.png', 'narrow.png', 'choice.png'):
            self.assertIn('/yadinassi-browser-artifacts/'+screenshot, workflow)
        self.assertNotIn("act('report-start'", text)
        self.assertNotIn("act('report-end'", text)
        self.assertIn('Movements has no period filter', text)
        self.assertIn('narrow_choice_clipped', text)
        self.assertIn('embedded_title_collapsed', text)
        for marker in ('filter_exact_total', 'filter_exact_rows', 'filter_exact_navigation',
                       'filter_draft_lost_on_repaint', 'refresh_did_not_restore_applied_date',
                       'reset_omits_default_filters', 'readonly_record_filters_changed_database',
                       'filter_reply_body_budget'):
            self.assertIn(marker, text)
        self.assertIn('assert.equal(payload?.id,packet.params.request.id)', text)
        self.assertIn("postedOnDay:1,dateExcluded:0,unpostedOnDay:0,reset:1", text)
        self.assertIn("apply-excluded-posted-day", text)
        self.assertIn("0,{...expectedFilters,dateFrom:'2026-11-12',dateTo:'2026-11-12'}", text)
        for marker in ('owned_child_not_navigation', 'draft_keep_open_veto', 'prepared_draft_reopened',
                       'no_repeated_confirmation', 'memory_draft_changed_database', 'draft_applied_once',
                       "assert.equal(actionLog.length-start,22", "appliedAmount:'123.45',appliedCount:1"):
            self.assertIn(marker, text)
        for stage in ('await-response', 'read-response', 'validate-envelope', 'await-render-ready',
                      'validate-catalog', 'await-visible-rows', 'validate-unapplied-draft', 'draft-preserved'):
            self.assertIn("report.filterStage='" + stage + "'", text)
        self.assertIn("state?.surface,'catalogs'", text)
        self.assertIn("state?.canSwitch,true", text)
        self.assertNotIn('--no-sandbox', text)
        self.assertNotIn('page.evaluate(', text)
        self.assertNotIn('addInitScript', text)

    def test_response_loss_is_after_backend_and_recovery_has_no_replay(self):
        text = HARNESS.read_text(encoding='utf-8')
        for required in (
            'route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0})',
            'bytes.length<=131072', "return route.abort('failed')",
            "['demo.snapshot','editor.snapshot']",
            "['demo.snapshot','application.hello','application.form']",
            "requests.at(-1).nested,'form.snapshot'",
            "r.action==='apply').length,1", "'123x','document_local_draft_lost'",
        ):
            self.assertIn(required, text)
        self.assertLess(text.index('const response=await route.fetch'), text.index("return route.abort('failed')"))

    def test_complete_source_binding_and_readonly_audit(self):
        text = HARNESS.read_text(encoding='utf-8')
        for required in (
            "'frontend/main-demo'", "'frontend/configuration'", "'frontend/form'", "'examples/demo'",
            "'main_demo_fixture.py'", "'source_bytes_changed'", 'capability_leak',
            'verifyMainDemoAudit(saved,assert)',
            "assert.deepEqual(audit(),saved,'surface_switch_changed_saved_data')",
        ):
            self.assertIn(required.strip("'") if required == "'main_demo_fixture.py'" else required, text)

    def test_fixture_seeds_only_warehouses_and_audit_is_independent(self):
        source = FIXTURE.read_text(encoding='utf-8')
        tree = ast.parse(source)
        funcs = {node.name: ast.get_source_segment(source, node) for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertIn('range(70)', funcs['seed'])
        self.assertIn("c.name == 'Склады'", funcs['seed'])
        self.assertIn('create_main_demo', funcs['seed'])
        for forbidden in ('create_document(', 'Interpreter(', 'execute('):
            self.assertNotIn(forbidden, funcs['seed'])
        self.assertIn('read_only=True', funcs['audit'])
        self.assertIn("'?mode=ro'", funcs['audit'])
        self.assertIn('database_changed_during_audit', funcs['audit'])
        self.assertIn('authored_warehouse_changed', funcs['audit'])
        support = (ROOT/'tests/browser_ui/main_demo_browser_support.mjs').read_text(encoding='utf-8')
        for marker in ('audit_line_quantity', 'audit_line_amount', 'audit_receipt_warehouse', 'audit_line_product', 'audit_product_section', 'audit_product_kind', 'audit_movement_product', 'audit_movement_warehouse'):
            self.assertIn(marker, support)

    def test_owned_result_recovery_uses_real_completion_without_mutation_replay(self):
        text = HARNESS.read_text(encoding='utf-8')
        for marker in ('owned_result_delayed_delivery_independent_draft_and_loss_without_replay',
                       'owned_result_retired_before_delivery', 'owned_result_duplicate_accept',
                       'owned_paused_dispatched', 'owned_independent_draft_lost',
                       'owned_result_recovery_replayed', 'owned_result_raw_copy_lost',
                       'owned_result_unknown_draft_unlocked', 'owned_result_changed_database',
                       "assert.equal(actionLog.length-start,14", 'resultGate=null;gate.arrived()'):
            self.assertIn(marker, text)

    def test_filter_capture_is_single_request_exact_byte_observer(self):
        text = HARNESS.read_text(encoding='utf-8')
        capture = (ROOT/'tests/browser_ui/main_demo_filter_capture.mjs').read_text(encoding='utf-8')
        body = text.split('const filterReply=async(method,action)=>{', 1)[1].split('const formEvent=', 1)[0]
        self.assertNotIn('response.body()', body)
        for marker in ('filterCapture.begin(method)', 'filterCapture.consume(capture,packet.id)',
                       'finally{filterCapture.clear(capture);}', 'captured.packet.params.request.id'):
            self.assertIn(marker, body)
        for marker in ('maxRedirects:0,maxRetries:0', 'bytes.length<=131072',
                       'route.fulfill({response,body:bytes})', 'filter_capture_duplicate',
                       'filter_capture_request_origin', 'filter_capture_response_origin',
                       'filter_capture_outer_id', 'filter_capture_inner_id', 'response.dispose()'):
            self.assertIn(marker, capture)

    def test_owned_draft_failure_diagnostics_are_fixed_codes_without_raw_exceptions(self):
        text = HARNESS.read_text(encoding='utf-8')
        body = text.split('const observed=async(method,action)=>{', 1)[1].split('const command=', 1)[0]
        for stage in ('await-response', 'read-response', 'validate-envelope', 'await-idle', 'complete'):
            self.assertIn("report.draftStage='" + stage + "'", body)
        for code in ('draft_response_wait_failed', 'draft_action_failed', 'draft_reply_budget', 'draft_reply_json', 'draft_outer_id',
                     'draft_outer_error', 'draft_uncertain', 'draft_inner_id', 'draft_inner_error',
                     'draft_form_error', 'draft_idle_timeout'):
            self.assertIn("'" + code + "'", body)
            self.assertIn("'" + code + "'", text.split('const safeFailureCodes=new Set([', 1)[1])
        self.assertNotIn('response.body()', body)
        self.assertIn('finally{filterCapture.clear(capture);}', body)
        switch = text.split("const capture=filterCapture.begin('demo.select');", 1)[1].split("assert.equal(actionLog.length-start,22", 1)[0]
        self.assertNotIn('response.body()', switch)
        self.assertIn('finally{filterCapture.clear(capture);}', switch)
        self.assertNotIn('console.', body)
        self.assertNotIn('report.error', body)

    def test_dialog_recovery_is_same_demo_actual_answer_and_readonly_inspection(self):
        text = HARNESS.read_text(encoding='utf-8')
        for marker in ("const dialog=()=>page.locator('.configuration-dialog:not([hidden])')",
                       'dialog_confirmation_once_and_lost_answer_without_replay',
                       'dialog_answer_count', 'dialog_answer_amount', 'dialog_answer_applied_before_delivery',
                       'dialog_answer_repeated', 'dialog_escape_answered', 'dialog_owner_not_paused',
                       'dialog_independent_draft_lost', 'dialog_loss_not_observed',
                       'dialog_recovery_mutated', 'dialog_recovery_form_mutated',
                       'dialog_raw_copy_lost', 'dialog_unknown_draft_unlocked', 'dialog_changed_database',
                       'await stopHost();await startHost();await page.goto(url)',
                       'assert.equal(actionLog.length-start,26'):
            self.assertIn(marker, text)

"""Static contracts only: no browser launch, test fixture execution or installation."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'tests/browser_ui'


class ConfigurationLayoutBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (QA / 'configuration_layout_browser_qa.mjs').read_text(encoding='utf-8')
        cls.workflow = (ROOT / '.github/workflows/configuration-layout-browser-qa.yml').read_text(encoding='utf-8')

    def contains(self, *parts):
        for part in parts:
            with self.subTest(part=part):
                self.assertIn(part, self.source)

    def test_exact_four_flows_and_business_request_plan(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0])
        self.assertEqual(names, ['nested_drafts_hidden_flush_and_focus', 'delayed_repeat_and_group_readonly',
            'independent_pages_visibility_keyboard_narrow_natural_close', 'lost_real_response_copy_only_navigation'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 4)
        plan = json.loads(self.source.split('const businessPlan=', 1)[1].split(';', 1)[0].replace("'", '"'))
        self.assertEqual([len(row) for row in plan], [3, 3, 8, 2])
        self.contains('businessEvents.slice(start),businessPlan[index]', 'total:4', 'results.map(row=>row.name),scenarioNames')

    def test_single_closed_reviewed_route(self):
        self.assertIn('branches: [codex/configuration-layout-browser-reviewed]', self.workflow)
        self.assertIn('contents: read', self.workflow)
        self.assertIn('persist-credentials: false', self.workflow)
        self.assertIn('cancel-in-progress: false', self.workflow)
        self.assertIn('node tests/browser_ui/configuration_layout_browser_qa.mjs', self.workflow)
        self.assertIn('timeout-minutes: 5', self.workflow)
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'schedule:', 'secrets.', 'sudo ', 'sysctl ', '--no-sandbox', 'write', 'container:'):
            self.assertNotIn(forbidden, self.workflow)

    def test_exact_pinned_dependencies_and_actions(self):
        self.assertEqual(json.loads((QA / 'package.json').read_text(encoding='utf-8'))['devDependencies'], {'playwright': '1.64.1'})
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund', self.workflow)
        self.assertIn('install chromium --no-shell', self.workflow)
        self.assertNotIn('--with-deps', self.workflow)
        for revision in ('3d3c42e5aac5ba805825da76410c181273ba90b1',
                         '5fda3b95a4ea91299a34e894583c3862153e4b97', 'cf430e030ddbb5b0abf93d22962f4752f3646cd9'):
            self.assertIn('@' + revision, self.workflow)
        self.contains("report.versions.playwright,'1.64.1'")

    def test_sandbox_and_owned_processes(self):
        self.assertEqual(self.source.count('chromium.launch('), 1)
        self.contains('chromiumSandbox:true', "probe.goto('chrome://sandbox')", 'sandboxCommand(args)', 'sandboxStatus(',
            "'process_not_direct_child'", "'process_group_not_owned'", "'owned_process_identity_changed'",
            'await groupGone(hostGroup)', 'process.getuid()===0', "readlinkSync('/proc/'+browserGroup.pid+'/exe')")
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'ignoreDefaultArgs:', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)

    def test_bounded_no_retry_no_privileged_fixture(self):
        self.contains('startedAt+220000', 'startedAt+240000', 'if(rpc>=96)', 'attachmentRequests<=96',
            'maxRetries:0', 'maxRedirects:0', "'late_reply_gate_timeout'", "'natural_shutdown_timeout'",
            "'examples/configuration-forms/layouts'),'--browser-session']", "phase='layout_host_start'", "phase='layout_writer_attach'")
        for forbidden in ('page.waitForTimeout(', 'fixtureCode', 'SQLite', '--posting-application', '--document-objects', 'writeFileSync'):
            self.assertNotIn(forbidden, self.source)

    def test_plain_launcher_explicitly_enables_attachment_protocol(self):
        launch = self.source.split('async function startHost(){', 1)[1].split('const button=', 1)[0]
        self.assertIn("const args=['-m','yadinassi.ui.configuration_app',path.join(repo,'examples/configuration-forms/layouts'),'--browser-session'];", launch)
        self.assertIn('const parse=applicationLaunchReader()', launch)
        self.assertEqual(launch.count("'--browser-session'"), 1)
        self.contains("phase='layout_host_start';await startHost()",
            "phase='layout_writer_attach';await page.goto(url);await writer()",
            "phase='layout_fault_host_start';await startHost()",
            "phase='layout_fault_writer_attach';await page.goto(url);await writer()")

    def test_owned_temporary_paths_and_source_binding(self):
        self.contains('const temporary=process.env.RUNNER_TEMP', 'path.isAbsolute(temporary)',
            "owned=await mkdtemp(path.join(temporary,'l-'))", 'process.env.TMPDIR=home',
            "'browser_socket_path_too_long'", "'browser_profile_not_owned'", "'tracked_checkout_dirty'",
            "'source_binding_changed'", "git('rev-parse','HEAD^{tree}')", "'frontend/form'", "'frontend/configuration'",
            "'tests/test_configuration_layout_browser_qa_contract.py'", "'docs/configuration-layout-browser-qa.md'",
            "'.github/workflows/configuration-layout-browser-qa.yml'")
        self.assertNotIn("'/tmp", self.source)
        self.assertNotIn('build.mjs', self.source)

    def test_nested_drafts_and_focus_no_implicit_flush(self):
        self.contains("'hidden_draft_dispatched'", "'input_replaced'", "'focus_selection_not_retained'",
            'node.setSelectionRange(2,5)', "{focused:true,start:2,end:5}", "'.orientation-horizontal'",
            "'  Ada draft  '", "await action('Close form').click()", "await value('Summary','  Ada draft   : ')")

    def test_real_delayed_command_duplicate_fence_and_inheritance(self):
        self.contains('control.click();control.click();', 'delayed={arrived,wait}',
            "event.control==='ApplyIdentity'", 'gate.arrived()', 'await bounded(gate.wait',
            "'busy_page_enabled'", "'group_readonly_missing'", "'sibling_readonly_missing'", "'child_flag_not_restored'")
        self.assertNotIn('route.fulfill({body:', self.source)

    def test_command_observer_reuses_validated_real_route_response(self):
        self.contains('const observedCommands=new Map()', 'observedCommands.set(packet.id,{packet,actual})',
            'observedCommands.get(request.id)', 'observedCommands.delete(request.id)',
            "'command_observer_binding'", "'command_observer_budget'", "'response_body_unavailable'")
        self.assertNotIn('(await reply).json()', self.source)
        self.assertNotIn('route.fulfill({json:', self.source)

    def test_independent_pages_visibility_keyboard_and_narrow_view(self):
        self.contains('await countPanels(2)', "'instance_navigation_dispatched'", "'hidden_page_tab_exposed'",
            "press('End')", "press('ArrowRight')", 'width:390,height:844', "'narrow_horizontal_overflow'",
            "await value('Notes','Sibling draft')", "await value('Summary',' : Sibling draft')")

    def test_editor_selector_excludes_same_named_accessible_page_panel(self):
        self.contains("const field=name=>active().locator('input').and(active().getByLabel(name,{exact:true}))",
            "phase='layout_second_notes_draft'", "phase='layout_return_first_instance'",
            "phase='layout_keyboard_end'", "phase='layout_narrow'", 'report.businessRpc=businessEvents.length', "phase='layout_second_summary_command'", "phase='layout_second_summary_readback'",
            'fixedAssertions.includes(assertion)?assertion:', "safeError=code=>errors.includes(code)?code:'unexpected_protocol_code'")
        self.assertNotIn("const field=name=>active().getByLabel(", self.source)
        view = (ROOT / 'frontend/form/src/view.mjs').read_text(encoding='utf-8')
        self.assertIn("row.setAttribute('role', 'tabpanel')", view)
        self.assertIn("row.setAttribute('aria-labelledby', result.tab.id)", view)

    def test_selected_hover_observes_final_computed_contrast(self):
        self.contains('await selected.hover()', "style.backgroundColor==='rgb(14, 51, 46)'",
            "style.color==='rgb(255, 255, 255)'", "contrast>=4.5,'selected_tab_hover_contrast'",
            'report.selectedTabHoverContrast=Math.round(contrast*100)/100', "phase='layout_hover_contrast'")
        css = (ROOT / 'frontend/form/src/style.css').read_text(encoding='utf-8')
        self.assertIn('.page-tab[aria-selected="true"]:hover:not(:disabled) { background: #0e332e; color: white; border-color: #0e332e; }', css)

    def test_real_completed_response_loss_and_copy_only_no_retry(self):
        self.contains('const actual=await auditResponse(response)', 'dropNextChange=false',
            "'real_change_not_completed'", "return await route.abort('failed')", 'report.realReplyDroppedAfterConfirmedChange=true',
            "'exact_raw_copy_missing'", "'copy_not_selectable'", "'locked_intent_replayed'",
            "phase='layout_fault_await_global_lock'", "phase='layout_fault_idle'", "phase='layout_fault_select_local_notes'",
            "phase='layout_fault_copy_readonly'", "phase='layout_fault_suppressed_actions'", "phase='layout_fault_screenshot'",
            "'locked_layout_inspection_unavailable'", "'locked_outer_open_enabled'", "'locked_outer_close_enabled'",
            "'NotesInput:   retained note  '", 'getComputedStyle(node).userSelect', "new KeyboardEvent('keydown'")
        self.assertEqual(self.source.count('dropNextChange=true'), 1)
        self.assertNotIn('route.fulfill({json:', self.source)

    def test_natural_shutdown_before_last_fault_and_honest_scope(self):
        self.assertEqual(self.source.count('await naturalStop();'), 1)
        self.contains("{code:0,signal:null}", "'natural_shutdown_failed'", 'report.naturalShutdown=true',
            'nativeLayoutParity:false', 'nativeCurrentPage:false', 'serverInactivePageAuthorization:false')
        natural = self.source.split('async function naturalStop(){', 1)[1].split('let delayed=', 1)[0]
        self.assertNotIn('signalGroup(', natural)
        docs = (ROOT / 'docs/configuration-layout-browser-qa.md').read_text(encoding='utf-8')
        self.assertIn('not native layout parity', docs)
        self.assertIn('not server authorization', docs)
        self.assertIn('forced owned cleanup', docs)

    def test_exact_redacted_artifacts_and_attachment_contract(self):
        paths = [line.strip().rsplit('/', 1)[1] for line in self.workflow.splitlines() if 'yadinassi-layout-browser-artifacts/' in line]
        self.assertEqual(paths, ['result.json', 'manifest.json', 'layout-drafts.png', 'layout-inheritance.png',
            'layout-narrow.png', 'layout-locked-copy.png'])
        self.contains("'capability_leak'", "'capability_not_removed'", "'only_resume_storage'", "'unexpected_artifact'",
            'resultSha256:sha256(raw)', "body.action==='heartbeat'&&response.status()===409",
            "value.error,'busy','unexpected_heartbeat_refusal'", "'writer_attachment'", "'writer_generation'")
        for forbidden in ('report.url', 'report.headers', 'report.response', 'report.stack', 'console.log(error', 'recordHar', 'tracing.start'):
            self.assertNotIn(forbidden, self.source)


if __name__ == '__main__':
    unittest.main()

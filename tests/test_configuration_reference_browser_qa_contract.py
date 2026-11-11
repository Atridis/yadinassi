"""Offline acquisition contracts: no browser, child process, install or network."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationReferenceBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/configuration_reference_browser_qa.mjs').read_text(encoding='utf-8')
        cls.workflow = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')

    def requires(self, *values):
        for value in values:
            self.assertIn(value, self.source)

    def step(self, name):
        return self.workflow.split('      - name: ' + name + '\n', 1)[1].split('\n      - ', 1)[0]

    def test_four_named_scenarios_and_exact_rpc_plan(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0])
        self.assertEqual(names, ['catalog_choose_filter_cancel_clear_save', 'document_typed_choices_durable_restart',
                                'retained_picker_reload_dirty_sibling', 'repeated_apply_late_navigation_owned_shutdown'])
        self.assertEqual(re.findall(r'await scenario\(scenarioNames\[(\d)\]', self.source), ['0', '1', '2', '3'])
        self.requires('const plannedRPC=[20,23,14,10]', 'total:4', "'total_rpc_plan'", "'incomplete_scenarios'")

    def test_browser_sandbox_is_real_verified_and_never_overridden(self):
        self.assertEqual(self.source.count('chromium.launch('), 1)
        self.requires("process.platform!=='linux'||process.getuid()===0", 'chromiumSandbox:true',
                      "probe.goto('chrome://sandbox')", 'sandboxCommand(args)',
                      "sandboxStatus(await probe.locator('body').innerText())", "report.versions.playwright,'1.64.1'")
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'ignoreDefaultArgs', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)

    def test_process_groups_profiles_and_child_environment_are_owned(self):
        self.requires('priorChildren.has(pid)', "return {pid,start:fields[19]}", 'process_uid_mismatch',
                      'process_not_direct_child', 'process_group_not_owned', 'owned_process_identity_changed',
                      "readlinkSync('/proc/'+browserGroup.pid+'/exe'),chromium.executablePath()",
                      "cdp.send('SystemInfo.getProcessInfo')", 'ownBrowserPid(info.processInfo),browserGroup.pid',
                      "mkdtemp(path.join(temporary,'ya-cr-'))", 'browser_socket_path_too_long',
                      'browser_profile_not_owned', 'env=childEnvironment(process.env,home);env.PYTHONPATH=repo',
                      'process.env.TMPDIR=home', 'process.env.TMPDIR=previousTmp', "cwd:repo,env,detached:true")
        self.assertNotIn('env:process.env', self.source)
        self.assertNotIn('--open-browser', self.source)

    def test_deadlines_and_budgets_precede_admission(self):
        self.requires('startedAt+220000', 'startedAt+240000', 'Date.now()>=workDeadline',
                      'const deadline=setTimeout(abort', 'const totalTimer=setTimeout(()=>{abort();process.exit(1);}',
                      'if(rpc>=100){abort();return route.abort().catch(()=>{});}', '++attachmentRequests<=96',
                      'bytes.length<=131072', 'bytes.length<=8192', 'maxRetries:0', 'maxRedirects:0')
        route = self.source.split("await context.route('**/*'", 1)[1]
        self.assertLess(route.index('if(rpc>=100)'), route.index('const packet=checkRequest'))
        self.assertNotIn('bounded(main()', self.source)

    def test_network_is_exact_origin_with_one_attachment_extension(self):
        self.requires('if(aborted||!applicationAllowedRequest(target))return route.abort()',
                      'if(allowedRequest(target,origin))return true',
                      "parsed.origin===origin&&!parsed.username&&!parsed.password&&!parsed.search&&parsed.pathname==='/attachment'",
                      "serviceWorkers:'block'", 'acceptDownloads:false', 'applicationLaunchReader()',
                      'host_output_budget', 'invalid_launch_output')
        self.assertNotIn('route.fulfill({json:', self.source)
        self.assertNotIn('route.fulfill({body:', self.source)

    def test_attachment_credentials_and_storage_are_bounded_redacted(self):
        self.requires("'action instance'", "'action generation pending'", "'yadinassi-browser-attachment/1'",
                      "headers['x-yadinassi-attachment']", "headers['x-yadinassi-generation']",
                      'value.leaseSeconds,90', 'value.graceSeconds,30', 'tokens.push(token)',
                      "session:['yadinassi.browser.resume/1']", "'only_resume_storage'", "'capability_not_removed'",
                      "'browser_cookies_not_empty'", "'capability_leak'")

    def test_reference_requests_are_closed_server_owned_capabilities(self):
        self.requires("packet.method==='application.reference'", "'session revision action'", "'action control row column'",
                      "filter:'action ticket code',cancel:'action ticket',apply:'action ticket choice'",
                      "action.control==='CategoryInput'&&action.row===null&&action.column===null",
                      "action.control==='LinesTable'", "action.column==='Product'", 'action.row<=4096',
                      "'unissued_picker_ticket'", "'crossed_picker_owner'", "'unissued_choice'",
                      "'persistent_uuid_in_request'", "'persistent_uuid_in_reply'", "'type scope target key text'")
        request = self.source.split('function checkRequest(request){', 1)[1].split('async function scenario', 1)[0]
        self.assertNotIn("['String','Number','Boolean','FormCatalogRef']", request)

    def test_reference_column_descriptors_cannot_bypass_strict_value_validation(self):
        reply = self.source.split('function checkReply(body,packet,stage){', 1)[1].split('async function main(){', 1)[0]
        descriptor = reply.split("if(context==='table-column'){", 1)[1].split("assert.equal(context,'value'", 1)[0]
        for required in ("exactKeys(value,'name title type readOnly')", "!Array.isArray(value)",
                         "value.name.length>0", "value.name.length<=128", "value.title.length<=1024",
                         "['String','Number','Boolean','Date','FormCatalogRef'].includes(value.type)",
                         "typeof value.readOnly,'boolean'", 'return;'):
            self.assertIn(required, descriptor)
        value = reply.split("if(value.type==='FormCatalogRef'){", 1)[1].split('for(const [key,nested]', 1)[0]
        for required in ("exactKeys(value,'type scope target key text')", 'assert.match(value.scope,',
                         'value.target<=128', 'value.key===null||', "if(value.key===null)assert.equal(value.text,'')"):
            self.assertIn(required, value)
        self.assertIn("if(value.kind==='table'&&key==='columns'){", reply)
        self.assertIn("nested.length>0&&nested.length<=8", reply)
        self.assertIn("for(const column of nested)inspect(column,'table-column')", reply)
        self.assertIn("else inspect(nested,'value')", reply)
        self.assertNotIn("Object.hasOwn(value,'scope')", reply)
        self.assertEqual(self.source.count("inspect(column,'table-column')"), 1)
        # Failure metadata may only use these literal stages, never actual keys,
        # payloads, references or assertion/exception details.
        stages = set(re.findall(r"(?:wireStage=|stage\()'([^']+)'", self.source))
        self.assertEqual(stages, {'attachment_request', 'attachment_response', 'attachment_delivery',
            'request_schema', 'http_status', 'reply_budget', 'reply_json', 'held_apply',
            'reply_envelope', 'reference_descriptor', 'reference_value', 'delivery'})
        self.assertEqual(self.source.count('report.wireStage??=wireStage'), 2)
        self.assertNotIn('report.wireStage=error', self.source)

    def test_source_binding_includes_new_runtime_example_and_shared_application(self):
        self.requires("'examples/configuration-reference-application'", "'yadinassi/configuration_reference_profile.py'",
                      "'yadinassi/configuration_references.py'", "'yadinassi/configuration_reference_choice.py'",
                      "'yadinassi/form_references.py'", "'yadinassi/ui/configuration_app.py'",
                      "'frontend/form/src/attachment.mjs'", "'frontend/configuration/src/app.mjs'",
                      "'tests/test_configuration_reference_browser_qa_contract.py'", "'required_source_not_tracked'",
                      "tree:git('rev-parse','HEAD^{tree}')", 'source[name]=sha256(await readFile',
                      "'source_binding_changed'", "'source_commit_mismatch'")
        self.assertEqual(self.source.count("git('status','--porcelain','--untracked-files=all')"), 2)
        self.assertNotIn('build.mjs', self.source)

    def test_fixed_owned_fixture_script_is_valid_python_and_never_native(self):
        script = self.source.split('  const script=`', 1)[1].split('\n`;', 1)[0]
        ast.parse(script)
        self.requires("'--reference-application'", "'references.sqlite'", 'assert not target.exists()',
                      'SQLiteCatalogBackend.create_reference_application', 'assert backend.storage_version==7',
                      "['create','empty','first','final']", 'maxBuffer:128', "'REFERENCE_FIXTURE_OK'")
        for forbidden in ('OwnedInfobase', 'tests/fixtures/native', 'integrational_tests', 'eval(', 'exec('):
            self.assertNotIn(forbidden, self.source)

    def test_catalog_choose_cancel_clear_and_save_are_real_ui_actions(self):
        self.requires("select('Category','C1','Category One')", "await filter('NONE')", "'cancel_changed_reference'",
                      "action('Clear Category').click()", "'clear_not_typed_empty'", "fixture('empty')",
                      "'reference_text_editable'", "commitInput('Product code','P2')", "commitInput('Unit price','7.25')")
        self.assertNotIn('dispatchEvent(', self.source)

    def test_document_restarts_and_independently_audits_exact_reference_types(self):
        self.requires("select('Product, row 1','P2','Reference product')", "commitInput('Quantity, row 1','3.25')",
                      "await closeForm(1);await closeForm(0);await ordinaryShutdown()", "fixture('first')",
                      "await openNumber('D1')", 'SQLiteCatalogBackend(target,read_only=True)',
                      'backend.export_configuration()==files', "type(category) is CatalogKey",
                      "category==categories['C1'].key", "type(rows[0].values[0]) is CatalogKey",
                      "rows[0].values==(products['P2'].key,'Reference line',Decimal('3.25'),True)",
                      'sha256(target.read_bytes()).digest()==before')

    def test_picker_snapshot_and_real_reload_preserve_sibling_and_owner(self):
        self.requires("await button('Check connection').click()", "'snapshot_lost_picker'",
                      "page.once('dialog',dialog=>dialog.accept());await page.reload()", "'reload_retargeted_picker'",
                      "'reload_changed_owner'", "'reload_cancel_cleared_reference'", "'sibling_dirty_lost'",
                      "commitInput('Note','Sibling draft')", "document.documentElement.scrollWidth<=innerWidth")
        self.assertNotIn('page.setContent', self.source)
        self.assertNotIn('page.addInitScript', self.source)

    def test_repeated_apply_uses_a_real_held_reply_and_rejects_late_intents(self):
        self.requires('control.click();control.click()', 'gate.entered()', 'await bounded(gate.released',
                      'return await route.fulfill({response})', "'repeated_apply_sent_twice'", "'late_navigation_sent_work'",
                      "'retired_choice_retargeted_sibling'", "'dirty_sibling_closed'", 'finally{release();}',
                      "fixture('final')", "'C2' if mode=='final' else 'C1'")
        self.assertLess(self.source.index('const response=await route.fetch', self.source.index("if(rpc>=100)")),
                        self.source.index('await bounded(gate.released'))

    def test_natural_exit_and_verified_cleanup_are_required_for_pass(self):
        self.requires("host.exitCode,0,'ordinary_host_exit_failed'", 'await groupGone(hostGroup);host=null;hostGroup=null',
                      "signalGroup(browserGroup,'SIGKILL');await groupGone(browserGroup)", 'attempt<20&&Date.now()<totalDeadline',
                      "process.kill(-identity.pid,0)", "'host_cleanup_unverified'", "'browser_cleanup_unverified'",
                      "'owned_directory_cleanup_unverified'", "await lstat(owned);throw Error('owned_directory_remains')")
        close = self.source.split('const ordinaryShutdown=async()=>{', 1)[1].split('const referenceValue=', 1)[0]
        self.assertNotIn('signalGroup', close)
        self.assertNotIn('stopHost(', close)
        self.assertLess(self.source.index('await stopHost();}catch'), self.source.index('rm(owned,{recursive:true'))
        self.assertLess(self.source.index('rm(owned,{recursive:true'), self.source.index("writeFile(path.join(output,'result.json')"))

    def test_only_fixed_screenshots_result_and_manifest_can_be_emitted(self):
        self.requires("const screenshots=['reference-product.png','reference-document.png','reference-resumed.png','reference-independent.png']",
                      "const artifacts=['result.json','manifest.json',...screenshots]", 'stat.size<=4*1024*1024',
                      "'screenshot_not_png'", 'sha256:sha256(bytes)', 'resultSha256:sha256(raw)',
                      "'unexpected_artifact'", 'Buffer.byteLength(raw)<=65536', "{flag:'wx'}")
        for forbidden in ('report.url', 'report.headers', 'report.response', 'report.stack', 'report.appState',
                          'tracing.start', 'recordHar', 'recordVideo', 'console.error'):
            self.assertNotIn(forbidden, self.source)
        self.assertEqual(self.source.count('console.log('), 1)

    def test_exact_eighth_reviewed_route_pins_and_artifacts(self):
        trigger = self.workflow.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip()
        self.assertEqual(trigger, 'push:\n    branches: [codex/ui-browser-reviewed, codex/form-browser-reviewed, codex/reference-browser-reviewed, codex/configuration-browser-reviewed, codex/application-host-browser-reviewed, codex/business-application-browser-reviewed, codex/document-form-browser-reviewed, codex/configuration-reference-browser-reviewed]')
        step = self.step('Acquire four configuration reference flows with Chromium sandbox enabled')
        for value in ("if: github.ref == 'refs/heads/codex/configuration-reference-browser-reviewed'", 'timeout-minutes: 5',
                      'QA_SOURCE_SHA: ${{ github.sha }}', 'run: node tests/browser_ui/configuration_reference_browser_qa.mjs'):
            self.assertIn(value, step)
        upload = self.step('Publish only configuration reference screenshots and redacted source-bound report')
        paths = upload.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines()], [
            '${{ runner.temp }}/yadinassi-configuration-reference-browser-artifacts/' + name for name in
            ['result.json', 'manifest.json', 'reference-product.png', 'reference-document.png', 'reference-resumed.png', 'reference-independent.png']])
        self.assertIn("if: always() && github.ref == 'refs/heads/codex/configuration-reference-browser-reviewed'", upload)
        self.assertIn('if-no-files-found: error\n          retention-days: 14', upload)
        self.assertEqual(self.workflow.split('\npermissions:\n', 1)[1].split('\nconcurrency:', 1)[0].strip(), 'contents: read')
        self.assertEqual(re.findall(r'uses: (\S+)', self.workflow), [
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
            'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
            *['actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'] * 8])
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'secrets.', 'sudo ', 'sysctl ', '--with-deps'):
            self.assertNotIn(forbidden, self.workflow)

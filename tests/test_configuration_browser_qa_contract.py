"""Static source-bound configuration-browser contracts; no browser or subprocess."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationBrowserQAContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/configuration_browser_qa.mjs').read_text()

    def test_exactly_six_closed_scenarios(self):
        declaration = self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0]
        self.assertEqual(re.findall(r"'([^']+)'", declaration), [
            'declared_welcome_bsl_openform_child_parameters_close',
            'server_nocontext_repeated_commands_and_independent_forms',
            'retained_hidden_invalid_draft_blocks_close',
            'declared_catalog_create_form_and_object_refusals_save',
            'catalog_selection_and_independent_dirty_forms',
            'bsl_declared_second_catalog_and_durable_reopen'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 6)
        self.assertIn("assert.deepEqual(results.map(row=>row.name),scenarioNames,'incomplete_scenarios')", self.source)

    def test_one_sandboxed_browser_and_nonroot_only(self):
        self.assertEqual(self.source.count('chromium.launch('), 1)
        self.assertIn("process.platform!=='linux'||process.getuid()===0", self.source)
        self.assertIn("chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:remaining(20000)})", self.source)
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('sandboxCommand(args)', self.source)
        self.assertIn("probe.goto('chrome://sandbox')", self.source)
        self.assertIn("sandboxStatus(await probe.locator('body').innerText())", self.source)

    def test_short_owned_temp_and_socket_budget(self):
        self.assertIn("mkdtemp(path.join(temporary,'ya-cfg-'))", self.source)
        self.assertIn("Buffer.byteLength(path.join(home,'org.chromium.Chromium.XXXXXX','SingletonSocket'))<108", self.source)
        self.assertIn('const previousTmp=process.env.TMPDIR', self.source)
        self.assertIn('process.env.TMPDIR=home', self.source)
        self.assertIn('else process.env.TMPDIR=previousTmp', self.source)

    def test_source_commit_tree_cleanliness_and_final_recheck(self):
        for required in ("process.env.QA_SOURCE_SHA", "git('rev-parse','HEAD^{tree}')",
                         "git('status','--porcelain','--untracked-files=all')", "'source_binding_changed'",
                         "sha256(await readFile(path.join(repo,name)))"):
            self.assertIn(required, self.source)
        self.assertIn(".split('\\0').filter(Boolean)", self.source)
        for prefix in ('frontend/form', 'frontend/configuration', 'examples/configuration-forms', 'examples/configuration-catalog-forms',
                       'tests/test_configuration_browser_qa_contract.py'):
            self.assertIn("'" + prefix + "'", self.source)

    def test_exact_executable_group_and_profile_ownership(self):
        for required in ('processIdentity(Number(children[0]))', "process.getuid(),'process_uid_mismatch'",
                         "process.pid,'process_not_direct_child'", "pid,'process_group_not_owned'",
                         "chromium.executablePath(),'browser_executable_mismatch'",
                         "ownBrowserPid(info.processInfo),browserGroup.pid", "'browser_profile_not_owned'",
                         "'owned_process_identity_changed'"):
            self.assertIn(required, self.source)

    def test_bounded_work_cleanup_and_rpc(self):
        for required in ('startedAt+160000', 'startedAt+180000', 'if(rpc>=100)',
                         "remaining(15000),'host_start_timeout'", 'cleanupRemaining(8000)',
                         'const deadline=setTimeout(abort', 'const totalTimer=setTimeout'):
            self.assertIn(required, self.source)

    def test_closed_wire_methods_and_no_code_inputs(self):
        validator = self.source.split('function checkRequest(request){', 1)[1].split('async function repeatClick', 1)[0]
        for method in ('application.hello','application.open','application.openRecord','application.catalog','application.snapshot','application.close','application.form'):
            self.assertIn("'"+method+"'", validator)
        self.assertIn("exactKeys(packet.params,'entry request')", validator)
        self.assertIn("exactKeys(packet.params,'session request')", validator)
        self.assertIn("exactKeys(event,keys[event.event])", validator)
        for forbidden in ("'source'", "'routine'", "'path'", "'eval'", "'handler'"):
            self.assertNotIn(forbidden, validator)
        self.assertIn('!allowedRequest(target,origin)', self.source)

    def test_closed_apps_and_explicit_owned_database_without_native_claim(self):
        self.assertIn("['welcome','counter','catalog'].includes(application)", self.source)
        self.assertIn("'-m','yadinassi.ui.configuration_app'", self.source)
        self.assertIn("path.join(repo,'examples/configuration-forms',application)", self.source)
        self.assertNotIn('--create-db', self.source)
        self.assertIn('nativeWindowParity:false', self.source)

    def test_exercises_parameters_independence_and_no_replay(self):
        for required in ("value('MessageLabel','Hello from a configuration form')",
                         "'duplicate_openform_command'", "'duplicate_counter_command'",
                         "'counter_sessions_not_independent'", "value('CountInput','3')"):
            self.assertIn(required, self.source)

    def test_hidden_invalid_draft_close_is_explicitly_local(self):
        for required in ("'tab_switch_submitted_hidden_draft'", "'invalid_close_cancelled_before_wire'",
                         "assert.equal(rpc,beforeClose,'invalid_close_sent_request')",
                         "value('CountInput','not-a-number')", "field('CountInput').fill('4')",
                         "'narrow_page_overflow'"):
            self.assertIn(required, self.source)

    def test_owned_cleanup_and_redacted_fixed_diagnostics(self):
        for required in ('signalGroup(browserGroup,\'SIGKILL\')', 'await groupGone(browserGroup)',
                         'await stopHost()', 'rm(owned,{recursive:true,force:true})',
                         "'owned_directory_remains'", 'function launchFailureCode(error)',
                         "'unclassified_launch_failure'"):
            self.assertIn(required, self.source)
        self.assertNotIn('console.error', self.source)
        self.assertNotIn('report.error=error', self.source)
        self.assertEqual(self.source.count('console.log('), 1)

    def test_exact_artifact_allowlist_hashes_and_no_capability_storage(self):
        declared = self.source.split('const screenshots=', 1)[1].split(';', 1)[0]
        self.assertEqual(re.findall(r"'([^']+)'", declared), [
            'configuration-parameters.png', 'configuration-independent.png', 'configuration-draft-narrow.png',
            'configuration-catalog-saved.png', 'configuration-catalog-selection.png', 'configuration-catalog-narrow.png'])
        for required in ("await mkdir(output)", "'wx'", "'screenshot_not_png'", 'sha256:sha256(bytes)',
                         'resultSha256:sha256(raw)', "'unexpected_artifact'", "'capability_leak'",
                         'localStorage.length+sessionStorage.length', '(await context.cookies()).length,0'):
            self.assertIn(required, self.source)

    def test_workflow_route_is_only_the_explicit_configuration_branch(self):
        workflow = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')
        self.assertEqual(workflow.split('\non:\n',1)[1].split('\npermissions:',1)[0].strip(),
            'push:\n    branches: [codex/ui-browser-reviewed, codex/form-browser-reviewed, codex/reference-browser-reviewed, codex/configuration-browser-reviewed, codex/application-host-browser-reviewed, codex/business-application-browser-reviewed, codex/document-form-browser-reviewed]')
        step = workflow.split('      - name: Acquire six configuration and catalog form flows with Chromium sandbox enabled\n',1)[1].split('\n      - ',1)[0]
        self.assertIn("if: github.ref == 'refs/heads/codex/configuration-browser-reviewed'", step)
        self.assertIn('timeout-minutes: 5', step)
        self.assertIn('QA_SOURCE_SHA: ${{ github.sha }}', step)
        self.assertIn('run: node tests/browser_ui/configuration_browser_qa.mjs', step)
        self.assertEqual(workflow.count('run: node tests/browser_ui/configuration_browser_qa.mjs'), 1)
        self.assertEqual(workflow.split('\npermissions:\n',1)[1].split('\nconcurrency:',1)[0].strip(), 'contents: read')
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'secrets.', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, workflow)
        self.assertIn("'configuration-browser-reviewed' }}\n  cancel-in-progress: false", workflow)
        self.assertIn("'.github/workflows/ui-browser-qa.yml'", self.source)

    def test_workflow_upload_is_exact_redacted_allowlist(self):
        workflow = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')
        step = workflow.split('      - name: Publish only configuration screenshots and redacted source-bound report\n',1)[1].split('\n      - ',1)[0]
        self.assertIn("if: always() && github.ref == 'refs/heads/codex/configuration-browser-reviewed'", step)
        self.assertIn('uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9', step)
        self.assertIn('name: configuration-browser-${{ github.sha }}-${{ github.run_attempt }}', step)
        paths = step.split('          path: |\n',1)[1].split('          if-no-files-found:',1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines()],
            ['${{ runner.temp }}/yadinassi-configuration-browser-artifacts/'+name for name in (
                'result.json','manifest.json','configuration-parameters.png','configuration-independent.png','configuration-draft-narrow.png',
                'configuration-catalog-saved.png','configuration-catalog-selection.png','configuration-catalog-narrow.png')])
        self.assertIn('if-no-files-found: error\n          retention-days: 14', step)

    def test_catalog_flow_covers_real_refusals_selection_and_durable_reopen(self):
        for required in ("'Form reject'", "'Object reject'", "'repeat_save_duplicated_record'",
                         "'single_multi_selection_and_exact_opaque_target'", "'per_row_commands_returned'",
                         "'independent_backend_audit_and_fresh_host_reopen'", "catalogFixture('audit')",
                         "'catalog_narrow_page_overflow'", "datePicker:false,nativeStandardFormWrite:false"):
            self.assertIn(required, self.source)
        self.assertIn("exactKeys(packet.params,'entry record request')", self.source)
        self.assertIn("/^record-[1-9][0-9]{0,8}$/", self.source)
        self.assertIn("'yadinassi-configuration-app/3'", self.source)

    def test_owned_fixture_uses_explicit_profile_and_independent_read_only_audit(self):
        fixture = (ROOT / 'tests/browser_ui/configuration_catalog_fixture.py').read_text()
        for required in ('SQLiteCatalogBackend.create_catalog_forms', 'read_only=True',
                         "root / 'catalogs.sqlite'", 'root.is_symlink()', "BSLDate(0)",
                         "Decimal('9.00')", "'emptyDatePreserved': True"):
            self.assertIn(required, fixture)
        self.assertNotIn('sqlite3', fixture)
        self.assertIn("timeout:remaining(10000),maxBuffer:4096", self.source)
        self.assertIn("path.join(owned,'catalogs.sqlite')", self.source)

    def test_catalog_selectors_follow_declared_accessible_titles_not_control_names(self):
        tail = self.source.split('await scenario(scenarioNames[3]', 1)[1]
        for catalog, names in (('Products', ('CodeInput', 'DescriptionInput', 'PriceInput', 'ActiveInput', 'AvailableDateInput', 'StatusLabel')),
                               ('Categories', ('CodeInput', 'DescriptionInput', 'StatusLabel'))):
            form = ET.parse(ROOT / 'examples/configuration-catalog-forms/Catalogs' / catalog / 'Forms/Card/Ext/Form.xml').getroot()
            ns = {'f': 'http://v8.1c.ru/8.3/xcf/logform'}
            controls = {item.attrib['name']: item for item in form.find('f:ChildItems', ns)}
            for name in names:
                title = controls[name].findtext('f:Title', namespaces=ns)
                self.assertTrue(title)
                self.assertRegex(tail, r"(?:field|value|commitInput)\('" + re.escape(title) + r"'")
                self.assertNotRegex(tail, r"(?:field|value|commitInput)\('" + re.escape(name) + r"'")

    def test_async_text_commits_use_enter_and_busy_state_but_keep_final_draft(self):
        helper = self.source.split('async function commitInput(name,text){',1)[1].split('\n}',1)[0]
        self.assertIn("await field(name).fill(text);await field(name).press('Enter');await idle()",helper)
        self.assertIn("await field('Unit price').fill('5');await value('Unit price','5')",self.source)
        self.assertIn("phase='declared_product_checkbox_after_dirty_price'",self.source)
        self.assertIn("phase='second_card_retained_price'",self.source)
        self.assertNotIn('waitForTimeout', self.source)

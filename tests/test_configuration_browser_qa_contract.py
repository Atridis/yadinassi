"""Static source-bound configuration-browser contracts; no browser or subprocess."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationBrowserQAContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/configuration_browser_qa.mjs').read_text()

    def test_exactly_three_closed_scenarios(self):
        declaration = self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0]
        self.assertEqual(re.findall(r"'([^']+)'", declaration), [
            'declared_welcome_bsl_openform_child_parameters_close',
            'server_nocontext_repeated_commands_and_independent_forms',
            'retained_hidden_invalid_draft_blocks_close'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['), 3)
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
        for prefix in ('frontend/form', 'frontend/configuration', 'examples/configuration-forms',
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
        for method in ('application.hello','application.open','application.snapshot','application.close','application.form'):
            self.assertIn("'"+method+"'", validator)
        self.assertIn("exactKeys(packet.params,'entry request')", validator)
        self.assertIn("exactKeys(packet.params,'session request')", validator)
        self.assertIn("exactKeys(event,keys[event.event])", validator)
        for forbidden in ("'source'", "'routine'", "'path'", "'eval'", "'handler'"):
            self.assertNotIn(forbidden, validator)
        self.assertIn('!allowedRequest(target,origin)', self.source)

    def test_closed_apps_and_no_database_or_native_claim(self):
        self.assertIn("['welcome','counter'].includes(application)", self.source)
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
        self.assertIn("const screenshots=['configuration-parameters.png','configuration-independent.png','configuration-draft-narrow.png']", self.source)
        for required in ("await mkdir(output)", "'wx'", "'screenshot_not_png'", 'sha256:sha256(bytes)',
                         'resultSha256:sha256(raw)', "'unexpected_artifact'", "'capability_leak'",
                         'localStorage.length+sessionStorage.length', '(await context.cookies()).length,0'):
            self.assertIn(required, self.source)

    def test_workflow_route_is_only_the_explicit_configuration_branch(self):
        workflow = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')
        self.assertEqual(workflow.split('\non:\n',1)[1].split('\npermissions:',1)[0].strip(),
            'push:\n    branches: [codex/ui-browser-reviewed, codex/form-browser-reviewed, codex/reference-browser-reviewed, codex/configuration-browser-reviewed]')
        step = workflow.split('      - name: Acquire three configuration form flows with Chromium sandbox enabled\n',1)[1].split('\n      - ',1)[0]
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
                'result.json','manifest.json','configuration-parameters.png','configuration-independent.png','configuration-draft-narrow.png')])
        self.assertIn('if-no-files-found: error\n          retention-days: 14', step)

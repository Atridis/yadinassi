"""Offline contract only; no browser, installation, subprocess or network starts."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DemoKindBrowserContractTests(unittest.TestCase):
    def source(self):
        return (ROOT / 'tests/browser_ui/demo_kind_browser_qa.mjs').read_text(encoding='utf8')

    def test_one_sandboxed_launch_and_no_privilege_changes(self):
        source = self.source()
        self.assertEqual(source.count('chromium.launch('), 1)
        self.assertIn('chromiumSandbox:true', source)
        self.assertIn("channel:'chromium'", source)
        self.assertIn('sandboxCommand(commandLineArgs(args))', source)
        self.assertIn("sandboxStatus(await probe.locator('body').innerText())", source)
        for forbidden in ('--no-sandbox', '--disable-setuid-sandbox', 'ignoreDefaultArgs', 'args:', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, source)
        workflow = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf8')
        self.assertIn('run: node tests/browser_ui/demo_kind_browser_qa.mjs', workflow)

    def test_exact_demo_source_and_eight_real_ui_scenarios(self):
        source = self.source()
        self.assertIn('SQLiteCatalogBackend.create_demo_kinds', source)
        self.assertIn('tests/fixtures/demo_cf/source', source)
        self.assertIn('assert len(f)==19', source)
        self.assertEqual(source.count("await scenario('"), 8)
        self.assertIn("page.locator('.editor').waitFor({state:'detached'})", source)
        self.assertIn("button.textContent.trim()==='+ New record'&&!button.disabled", source)
        self.assertIn("phase='reattach_existing_host'", source)
        self.assertIn('process.env.QA_SOURCE_SHA', source)
        self.assertIn('tracked_checkout_dirty', source)
        self.assertIn('source_changed', source)
        self.assertNotIn('build.mjs', source)

    def test_deadline_rpc_admission_and_owned_cleanup(self):
        source = self.source()
        self.assertIn('const workDeadline=startedAt+160000', source)
        self.assertIn('Date.now()>=workDeadline', source)
        self.assertIn('timeout:remaining(15000)', source)
        self.assertIn("if(rpc>=200)", source)
        self.assertLess(source.index('if(rpc>=200)'), source.index('return route.continue()'))
        self.assertIn('browser_process_group_not_owned', source)
        self.assertIn("process.kill(-browserGroup,'SIGKILL')", source)
        self.assertIn('browser_cleanup_unverified', source)
        self.assertNotIn('bounded(main()', source)

    def test_fixed_failure_codes_and_bounded_source_bound_artifacts(self):
        source = self.source()
        self.assertIn("reason:aborted?'deadline_or_rpc_budget'", source)
        self.assertNotIn('redact(error', source)
        self.assertNotIn('error.stack', source)
        self.assertIn("catch(error){failure=error;report.status='FAIL';report.failure=", source)
        self.assertIn('Buffer.byteLength(raw)<=65536', source)
        self.assertIn('stat.size<=4*1024*1024', source)
        self.assertIn('resultSha256:sha256(raw)', source)
        self.assertIn("['result.json','manifest.json','list.png','editor.png','narrow.png']", source)
        self.assertIn('capability_leak', source)

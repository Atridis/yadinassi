"""Статический контракт отдельного Chromium QA; без запуска браузера."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class LegacyBrowserContractTests(unittest.TestCase):
    def setUp(self):
        self.script=(ROOT/'tests/browser_ui/legacy_reference_pages_browser_qa.mjs').read_text()

    def test_sandbox_source_and_cleanup_guards(self):
        for text in ('ordinary_nonroot_runner_required','chromiumSandbox:true','sandboxCommand(commandLineArgs',
                     'sandboxStatus(', 'browser_process_group_not_owned','browser_executable_mismatch',
                     'source_commit_mismatch','tracked_checkout_dirty','source_bytes_changed',
                     'allowedRequest(target,origin)','serviceWorkers:\'block\'','browser_cleanup_unverified',
                     'capability_leak','processIdentity','owned_process_identity_changed','await groupGone(hostGroup)',
                     'totalTimer=setTimeout','owned_directory_changed','apply_body_budget','frontend/catalog','rm(owned,{recursive:true,force:true})'):
            self.assertIn(text,self.script)
        self.assertNotIn('--no-sandbox',self.script)

    def test_lost_response_after_real_apply_snapshot_only(self):
        start=self.script.index('const response=await route.fetch({timeout:remaining(10000),maxRedirects:0,maxRetries:0})')
        self.assertLess(start,self.script.index("return route.abort('failed')",start))
        for text in ("body.result.state.referenceChoice,null", "['editor.snapshot'],'recovery_replayed_event'",
                     "'scalar_apply_replayed'", "'description_draft_lost'", "'code_draft_lost'"):
            self.assertIn(text,self.script)
        self.assertNotIn('route.fulfill',self.script)
        self.assertNotIn('page.evaluate(',self.script)

    def test_scenario_budget_and_independent_audit(self):
        for text in ("'business_request_count'", "length,20", "length,2,'apply_count'", "rpc>=50",
                     "'source_changed'", "assert.deepEqual(audit(),saved", "'Choose Warehouses row 1'",
                     "'Choose DefaultWarehouse'", "'Next choices'", "'Previous choices'", "'Search references'"):
            self.assertIn(text,self.script)
        self.assertEqual(self.script.count('await scenario('),1)

    def test_dedicated_authored_seed_no_legacy_fixture_mutation(self):
        source=(ROOT/'tests/browser_ui/legacy_reference_pages_fixture.py').read_text()
        for text in ('range(70)', "'productsInitially':0", 'read_only=True', "'DefaultWarehouse'", "'section_reference'"):
            self.assertIn(text,source)
        self.assertIn('legacy_reference_pages_fixture.py',self.script)
        self.assertNotIn('reference_rows_fixture.py',self.script)

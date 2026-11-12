"""Статические контракты QA; браузер и процессы здесь не запускаются."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InventoryEnumBrowserQAContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'tests/browser_ui/inventory_enum_application_browser_qa.mjs').read_text()

    def test_four_scenarios_and_exact_business_requests(self):
        names=ast.literal_eval(self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(len(names),4)
        plan=ast.literal_eval(self.source.split('const businessPlan=',1)[1].split(';',1)[0])
        self.assertEqual([len(p) for p in plan],[14,15,3,7])
        self.assertEqual(sum(map(len,plan)),39)
        self.assertEqual(self.source.count('await scenario(scenarioNames['),4)

    def test_empty_explicit_database_and_readonly_audit(self):
        fixture=self.source.split('const fixtureCode=String.raw`',1)[1].split('`;',1)[0]
        ast.parse(fixture)
        for token in ('create_inventory_enum_application(database,config)', 'core16Denied',
                      'SQLiteCatalogBackend(database,read_only=True)', 'type(value) is EnumKey',
                      'backend._enum_domain.encode', 'sha256(database.read_bytes()).digest()==before'):
            self.assertIn(token,fixture)
        for token in ('INSERT INTO','UPDATE ','DELETE FROM','.execute("','.write(','.post('):
            self.assertNotIn(token,fixture)

    def test_actual_ui_choices_and_durable_reopen(self):
        for token in ("await choose('Unit','Piece','Piece')", "await choose('State','Approved','Approved')",
                      "await choose('Unit, row 1','Piece','Piece')", "await command('Write document','WriteButton')",
                      "await command('Post document','PostButton')", "await command('Undo posting','UndoPostingButton')",
                      "await openNumber('R1')", "await value('State','Approved')", "reportPanel().getByRole('cell'"):
            self.assertIn(token,self.source)
        self.assertNotIn('page.addInitScript',self.source)
        self.assertNotIn('localStorage.setItem',self.source)

    def test_sandbox_and_owned_process_guards_retained(self):
        for token in ('chromiumSandbox:true','sandboxCommand(args)','sandboxStatus(', 'processIdentity(',
                      'process_not_direct_child','process_group_not_owned','owned_directory_cleanup_unverified',
                      'ordinary_nonroot_linux_runner_required','groupGone(hostGroup)'):
            self.assertIn(token,self.source)
        self.assertNotIn('--no-sandbox',self.source)
        self.assertNotIn('chromiumSandbox:false',self.source)

    def test_network_capability_and_budget_guards_retained(self):
        for token in ("context.route('**/*'", 'applicationAllowedRequest(target)', 'maxRedirects:0,maxRetries:0',
                      'persistent_uuid_in_request','persistent_uuid_leak','private_host_envelope_leak',
                      "acceptDownloads:false,serviceWorkers:'block'", 'rpc>=180','220000','240000'):
            self.assertIn(token,self.source)

    def test_source_binding_and_non_native_artifacts(self):
        for token in ('QA_SOURCE_SHA','source_commit_mismatch','tracked_checkout_dirty','source_binding_changed',
                      'configuration-inventory-enum-application/InventoryApplication.xml',
                      'inventory_enum_application_browser_qa.mjs','capability_leak','resultSha256',
                      'nativeParity:false','enumReportTextOnly:true'):
            self.assertIn(token,self.source)

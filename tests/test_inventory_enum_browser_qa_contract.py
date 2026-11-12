"""Статические контракты QA; браузер и процессы здесь не запускаются."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InventoryEnumBrowserQAContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'tests/browser_ui/inventory_enum_application_browser_qa.mjs').read_text()

    def test_five_scenarios_and_exact_business_requests(self):
        names=ast.literal_eval(self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(len(names),5)
        plan=ast.literal_eval(self.source.split('const businessPlan=',1)[1].split(';',1)[0])
        self.assertEqual([len(p) for p in plan],[14,15,3,7,212])
        self.assertEqual(sum(map(len,plan)),251)
        self.assertEqual(self.source.count('await scenario(scenarioNames['),5)
        self.assertIn('total:scenarioNames.length',self.source)

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
                      "acceptDownloads:false,serviceWorkers:'block'", 'rpc>=360','400000','420000'):
            self.assertIn(token,self.source)

    def test_source_binding_and_non_native_artifacts(self):
        for token in ('QA_SOURCE_SHA','source_commit_mismatch','tracked_checkout_dirty','source_binding_changed',
                      'configuration-inventory-enum-application/InventoryApplication.xml',
                      'inventory_enum_application_browser_qa.mjs','capability_leak','resultSha256',
                      'nativeParity:false','enumReportTextOnly:true'):
            self.assertIn(token,self.source)

    def test_ci_is_exact_opt_in_and_keeps_readonly_sandbox_route(self):
        workflow=(ROOT/'.github/workflows/inventory-enum-application-browser-qa.yml').read_text()
        self.assertIn('branches: [codex/inventory-enum-application-browser-reviewed]',workflow)
        self.assertIn('contents: read',workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('ref: ${{ github.sha }}',workflow)
        self.assertIn('QA_SOURCE_SHA: ${{ github.sha }}',workflow)
        self.assertIn('node tests/browser_ui/inventory_enum_application_browser_qa.mjs',workflow)
        self.assertNotIn('pull_request:',workflow)
        self.assertNotIn('sudo',workflow)
        self.assertNotIn('--no-sandbox',workflow)
        for name in ('enum-catalogs.png','enum-written.png','enum-posted-report.png','enum-reopened-unposted.png'):
            self.assertIn(name,workflow)

    def test_paging_created_through_ui_with_navigation_and_saved_page(self):
        for token in ("index<50", "await commitInput('Code','Z'+suffix)",
                      "await turn('Next records')", "await turn('Previous records')",
                      "await search('Z0049','code')", "await search('','description')",
                      "nav().total,51", "nav().page,2", "warehouses.length,51",
                      "navigation_snapshot", "navigation_cursor", "rowsCreatedThroughUI=51"):
            self.assertIn(token,self.source)
        self.assertIn('CatalogSelection(limit=64)',self.source)
        self.assertIn('assert len(rows)<64',self.source)

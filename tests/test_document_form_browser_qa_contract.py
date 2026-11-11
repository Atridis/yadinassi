"""Static contract for the opt-in real document browser acquisition."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class DocumentBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'tests/browser_ui/document_form_browser_qa.mjs').read_text()
        cls.fixture=(ROOT/'tests/browser_ui/document_form_fixture.py').read_text()
        cls.workflow=(ROOT/'.github/workflows/ui-browser-qa.yml').read_text()

    def test_exact_five_scenarios(self):
        names=re.findall(r"'([^']+)'",self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(names,['explicit_document_list_and_new','typed_header_rows_write_refresh',
            'selected_delete_add_durable_reopen','independent_dirty_sibling_refused_close','bounded_rows_readonly_date_no_posting'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['),5)
        self.assertIn("results.map(row=>row.name),scenarioNames",self.source)

    def test_owned_sandbox_and_timeout(self):
        for text in ['chromiumSandbox:true',"probe.goto('chrome://sandbox')",'sandboxCommand(args)',
            'processIdentity(', 'await groupGone(hostGroup)',"'owned_process_identity_changed'",'startedAt+220000','startedAt+240000',
            "'ya-doc-'","process.platform!=='linux'||process.getuid()===0"]:self.assertIn(text,self.source)
        for forbidden in ['--no-sandbox','chromiumSandbox:false','executablePath:','sudo ','sysctl ']:self.assertNotIn(forbidden,self.source)

    def test_closed_source_and_fresh_database(self):
        for text in ["'examples/configuration-document-forms'","'--document-objects'","'--f'",
            "'tests/test_document_form_browser_qa_contract.py'","'tracked_checkout_dirty'","'source_binding_changed'",
            "git('rev-parse','HEAD^{tree}')"]:self.assertIn(text,self.source)
        self.assertIn('SQLiteCatalogBackend.create_document_forms',self.fixture)
        self.assertNotIn('unlink(',self.fixture)
        self.assertIn('sha256(database.read_bytes()).digest()==before',self.fixture)

    def test_exact_existing_rpc_scalar_cells_and_opaque_selection(self):
        for text in ["'yadinassi-configuration-app/3'","'application.catalog'","'application.openRecord'",
            '/^record-[1-9][0-9]{0,8}$/','/^open-[0-9a-f]{32}-[1-9][0-9]*$/',
            "cell:'event revision control row column value'","select:'event revision control row'",
            "['Label','Quantity','Checked']",'event.row<=4096','if(rpc>=180)']:self.assertIn(text,self.source)
        self.assertNotIn("page.evaluate(async",self.source)
        for text in ["launchURL(match[0].slice(0,-13))", "parsed.pathname==='/attachment'",
            "'action generation pending'", "'yadinassi-browser-attachment/1'", "tokens.push(token)",
            "headers['x-yadinassi-attachment']", "session:['yadinassi.browser.resume/1']",'maxRetries:0']:
            self.assertIn(text,self.source)

    def test_actual_ui_write_delete_reopen_and_sibling_refusal(self):
        for text in ["action('Write document')","action('Delete selected line')","'Select row 1 in Order lines'",
            "documentFixture('audit-first')","'Rows loaded: 2'","'dirty_sibling_was_closed'","'close_implicitly_saved'",
            'await reply;await idle()']:self.assertIn(text,self.source)
        self.assertIn("owned.object.get_member('Posted') is False",self.fixture)

    def test_limit_is_rejection_not_truncation_or_posting_claim(self):
        for text in ['i<=32',"'overflow_not_explicitly_rejected'","'overflow_truncated_or_appended'",
            "getAttribute('readonly')","name:/^(Post|Unpost)$/",'datePicker:false,posting:false',"documentFixture('audit-final')"]:self.assertIn(text,self.source)
        self.assertIn('len(bounded)==32',self.fixture)

    def test_artifact_allowlist_and_no_sensitive_output(self):
        for text in ["'capability_not_removed'","'only_resume_storage'","'browser_cookies_not_empty'",
            "'capability_leak'","'unexpected_artifact'",'resultSha256:sha256(raw)']:self.assertIn(text,self.source)
        for text in ['report.url','report.headers','report.response','report.stack']:self.assertNotIn(text,self.source)
        self.assertNotIn('print(cards)',self.fixture)

    def test_exact_optin_and_closed_uploaded_paths(self):
        workflow=self.workflow
        self.assertIn('codex/document-form-browser-reviewed, codex/configuration-reference-browser-reviewed, codex/scalar-editor-browser-reviewed]',workflow)
        step=workflow.split('      - name: Acquire five document form flows with Chromium sandbox enabled\n',1)[1].split('\n      - ',1)[0]
        for text in ["if: github.ref == 'refs/heads/codex/document-form-browser-reviewed'",'timeout-minutes: 5','QA_SOURCE_SHA: ${{ github.sha }}','node tests/browser_ui/document_form_browser_qa.mjs']:self.assertIn(text,step)
        upload=workflow.split('      - name: Publish only document form screenshots and redacted source-bound report\n',1)[1]
        paths=upload.split('          path: |\n',1)[1].split('          if-no-files-found:',1)[0]
        self.assertEqual([x.strip() for x in paths.splitlines()],['${{ runner.temp }}/yadinassi-document-form-browser-artifacts/'+n for n in ['result.json','manifest.json','document-new.png','document-written.png','document-reopened.png','document-independent.png','document-bounded.png']])
        for text in ['workflow_dispatch:','pull_request:','schedule:','secrets.']:self.assertNotIn(text,workflow)
        self.assertIn('permissions:\n  contents: read',workflow)

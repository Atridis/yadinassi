"""Closed opt-in acceptance for the authored mixed business application."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class BusinessBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'tests/browser_ui/business_browser_qa.mjs').read_text()
        cls.workflow=(ROOT/'.github/workflows/ui-browser-qa.yml').read_text()

    def test_exact_four_scenarios(self):
        names=re.findall(r"'([^']+)'",self.source.split('const scenarioNames=',1)[1].split(';',1)[0])
        self.assertEqual(names,['mixed_startup_servercall_common_navigation','catalog_validation_write_authoritative_refresh',
            'document_rows_write_durable_reopen','dirty_sibling_refused_close_ordinary_shutdown'])
        self.assertEqual(self.source.count('await scenario(scenarioNames['),4)
        self.assertIn('total:4',self.source)

    def test_sandbox_owned_cleanup_and_budgets(self):
        for text in ['chromiumSandbox:true',"probe.goto('chrome://sandbox')",'sandboxCommand(args)',
            'processIdentity(', 'await groupGone(hostGroup)',"'owned_process_identity_changed'",'startedAt+220000','startedAt+240000',
            "'ya-biz-'","process.platform!=='linux'||process.getuid()===0",'if(rpc>=180)']:
            self.assertIn(text,self.source)
        for text in ['--no-sandbox','chromiumSandbox:false','executablePath:','sudo ','sysctl ']:self.assertNotIn(text,self.source)

    def test_fresh_source_bound_grant(self):
        for text in ["'examples/configuration-business-application'","'--business-application'","'--f'",
            'assert not target.exists()','SQLiteCatalogBackend.create_business_application',
            'assert backend.storage_version==7',"'tests/test_business_browser_qa_contract.py'",
            "'tracked_checkout_dirty'","'source_binding_changed'","git('rev-parse','HEAD^{tree}')"]:
            self.assertIn(text,self.source)
        self.assertNotIn('documentFixture(',self.source)

    def test_strict_attachment_and_wire(self):
        for text in ["'yadinassi-configuration-app/3'","'yadinassi-browser-attachment/1'",
            "'action generation pending'","headers['x-yadinassi-attachment']",'maxRetries:0',
            "session:['yadinassi.browser.resume/1']","tokens.push(token)",
            "cell:'event revision control row column value'","['Label','Quantity','Checked']",'event.row<=4096',
            '/^open-[0-9a-f]{32}-[1-9][0-9]*$/','/^record-[1-9][0-9]{0,8}$/']:
            self.assertIn(text,self.source)

    def test_real_common_navigation_and_catalog_validation(self):
        for text in ["['Calculated in the owned server process','8']","action('Open details')","action('New product')",
            "value('MessageLabel'","'Form reject'","'Object reject'","'rejected_form_wrote'","'rejected_object_wrote'",
            "'catalog_success_refresh'","name:'Business product'","await saveProduct()",
            "tabs().getByRole('button',{name:'Product pricing card',exact:true}).click()",
            "tabs().getByRole('button',{name:'Non-posting order',exact:true}).click()"]:
            self.assertIn(text,self.source)

    def test_durable_document_and_real_close_reply(self):
        for text in ["action('New order')","action('Select row 1 in Order lines')","action('Delete selected line')",
            "phase='durable_reopen_new_process';await stopHost()","await openNumber('D1')", "value('Quantity, row 1','3.25')",
            "field('Checked, row 1').isChecked()","'dirty_sibling_was_closed'","'close_implicitly_saved'",
            "await applicationState(await closed)","finalState.lifecycle,'closed'"]:
            self.assertIn(text,self.source)
        self.assertNotIn('dispatchEvent(',self.source)
        self.assertIn('posting:false,references:false,nativeStandardFormWrite:false',self.source)

    def test_closed_artifacts_and_redaction(self):
        for text in ["'capability_not_removed'","'only_resume_storage'","'browser_cookies_not_empty'",
            "'capability_leak'","'unexpected_artifact'",'resultSha256:sha256(raw)']:
            self.assertIn(text,self.source)
        for text in ['report.url','report.headers','report.response','report.stack','report.appState']:
            self.assertNotIn(text,self.source)

    def test_exact_reviewed_route_and_upload(self):
        step=self.workflow.split('      - name: Acquire four mixed business flows with Chromium sandbox enabled\n',1)[1].split('\n      - ',1)[0]
        for text in ["if: github.ref == 'refs/heads/codex/business-application-browser-reviewed'",'timeout-minutes: 5',
            'QA_SOURCE_SHA: ${{ github.sha }}','node tests/browser_ui/business_browser_qa.mjs']:
            self.assertIn(text,step)
        upload=self.workflow.split('      - name: Publish only business application screenshots and redacted source-bound report\n',1)[1].split('\n      - ',1)[0]
        paths=upload.split('          path: |\n',1)[1].split('          if-no-files-found:',1)[0]
        self.assertEqual([x.strip() for x in paths.splitlines()],['${{ runner.temp }}/yadinassi-business-browser-artifacts/'+n for n in
            ['result.json','manifest.json','business-startup.png','business-product.png','business-document.png','business-independent.png']])
        for text in ['workflow_dispatch:','pull_request:','schedule:','secrets.']:self.assertNotIn(text,self.workflow)
        self.assertIn('permissions:\n  contents: read',self.workflow)

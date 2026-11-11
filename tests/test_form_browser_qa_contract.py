"""Offline form-browser contracts. No browser, subprocess, install or network."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FormBrowserQAContractTests(unittest.TestCase):
    def source(self):
        return (ROOT / 'tests/browser_ui/form_browser_qa.mjs').read_text(encoding='utf-8')

    def workflow(self):
        return (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')

    def step(self, name):
        prefix = '      - name: ' + name + '\n'
        return self.workflow().split(prefix, 1)[1].split('\n      - ', 1)[0]

    def test_closed_push_routes_select_exact_harnesses(self):
        workflow = self.workflow()
        trigger = workflow.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip()
        self.assertEqual(trigger, 'push:\n    branches: [codex/ui-browser-reviewed, codex/form-browser-reviewed, codex/reference-browser-reviewed, codex/configuration-browser-reviewed, codex/application-host-browser-reviewed, codex/business-application-browser-reviewed, codex/document-form-browser-reviewed, codex/configuration-reference-browser-reviewed, codex/scalar-editor-browser-reviewed, codex/posting-application-browser-reviewed]')
        catalog = self.step('Acquire eight original-demo kind flows with Chromium sandbox enabled')
        form = self.step('Acquire five form flows with Chromium sandbox enabled')
        configuration = self.step('Acquire six configuration and catalog form flows with Chromium sandbox enabled')
        reference = self.step('Acquire three reference order flows with Chromium sandbox enabled')
        for step, branch, script in ((catalog, 'ui', 'demo_kind'), (form, 'form', 'form'), (configuration, 'configuration', 'configuration'), (reference, 'reference', 'reference')):
            self.assertIn(f"if: github.ref == 'refs/heads/codex/{branch}-browser-reviewed'", step)
            self.assertIn(f'run: node tests/browser_ui/{script}_browser_qa.mjs', step)
            self.assertIn('QA_SOURCE_SHA: ${{ github.sha }}', step)
            self.assertIn('timeout-minutes: 5', step)
        self.assertEqual(workflow.count('run: node tests/browser_ui/demo_kind_browser_qa.mjs'), 1)
        self.assertEqual(workflow.count('run: node tests/browser_ui/form_browser_qa.mjs'), 1)
        self.assertEqual(workflow.count('run: node tests/browser_ui/configuration_browser_qa.mjs'), 1)
        self.assertEqual(workflow.count('run: node tests/browser_ui/reference_browser_qa.mjs'), 1)
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'push:\n    branches: [main]'):
            self.assertNotIn(forbidden, workflow)

    def test_runner_dependencies_permissions_and_catalog_scope_unchanged(self):
        workflow = self.workflow()
        self.assertEqual(workflow.split('\npermissions:\n', 1)[1].split('\nconcurrency:', 1)[0].strip(), 'contents: read')
        self.assertIn("if: github.repository == 'Atridis/yadinassi'", workflow)
        self.assertIn("group: ${{ github.ref == 'refs/heads/codex/posting-application-browser-reviewed' && 'posting-application-browser-reviewed' || github.ref == 'refs/heads/codex/ui-browser-reviewed' && 'catalog-browser-reviewed' || github.ref == 'refs/heads/codex/form-browser-reviewed' && 'form-browser-reviewed' || github.ref == 'refs/heads/codex/reference-browser-reviewed' && 'reference-browser-reviewed' || github.ref == 'refs/heads/codex/application-host-browser-reviewed' && 'application-host-browser-reviewed' || github.ref == 'refs/heads/codex/business-application-browser-reviewed' && 'business-application-browser-reviewed' || github.ref == 'refs/heads/codex/document-form-browser-reviewed' && 'document-form-browser-reviewed' || github.ref == 'refs/heads/codex/configuration-reference-browser-reviewed' && 'configuration-reference-browser-reviewed' || github.ref == 'refs/heads/codex/scalar-editor-browser-reviewed' && 'scalar-editor-browser-reviewed' || 'configuration-browser-reviewed' }}\n  cancel-in-progress: false", workflow)
        self.assertIn('runs-on: ubuntu-22.04\n    timeout-minutes: 10', workflow)
        self.assertIn('ref: ${{ github.sha }}\n          persist-credentials: false', workflow)
        self.assertIn('python -m pip install -e . wcwidth==0.8.2', workflow)
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund', workflow)
        self.assertIn('install chromium --no-shell', workflow)
        self.assertEqual(re.findall(r'uses: (\S+)', workflow), [
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
            'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'])
        for forbidden in ('sudo ', 'sysctl ', 'container:', 'secrets.', 'write', '--with-deps', 'QA_CHROMIUM'):
            self.assertNotIn(forbidden, workflow)

    def test_route_specific_uploads_have_exact_fixed_files(self):
        catalog = self.step('Publish only catalog screenshots and redacted source-bound report')
        form = self.step('Publish only form screenshots and redacted source-bound report')
        configuration = self.step('Publish only configuration screenshots and redacted source-bound report')
        reference = self.step('Publish only reference screenshots and redacted source-bound report')
        for step, branch, prefix, files in (
                (catalog, 'ui', 'yadinassi-browser-artifacts', ['result.json', 'manifest.json', 'list.png', 'editor.png', 'narrow.png']),
                (form, 'form', 'yadinassi-form-browser-artifacts', ['result.json', 'manifest.json', 'estimate.png', 'product-narrow.png', 'order-table-narrow.png', 'order-editor-narrow.png', 'orders-workspace-narrow.png']),
                (configuration, 'configuration', 'yadinassi-configuration-browser-artifacts', ['result.json', 'manifest.json', 'configuration-parameters.png', 'configuration-independent.png', 'configuration-draft-narrow.png', 'configuration-catalog-saved.png', 'configuration-catalog-selection.png', 'configuration-catalog-narrow.png']),
                (reference, 'reference', 'yadinassi-reference-browser-artifacts', ['result.json', 'manifest.json', 'reference-created.png', 'reference-choice-narrow.png', 'reference-reopened.png'])):
            self.assertIn(f"if: always() && github.ref == 'refs/heads/codex/{branch}-browser-reviewed'", step)
            paths = step.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
            self.assertEqual([line.strip() for line in paths.splitlines()],
                             ['${{ runner.temp }}/' + prefix + '/' + name for name in files])
            self.assertIn('if-no-files-found: error\n          retention-days: 14', step)
        self.assertIn('name: catalog-browser-${{ github.sha }}-${{ github.run_attempt }}', catalog)
        self.assertIn('name: form-browser-${{ github.sha }}-${{ github.run_attempt }}', form)
        self.assertIn('name: configuration-browser-${{ github.sha }}-${{ github.run_attempt }}', configuration)

    def test_one_nonroot_sandboxed_browser_without_executable_override(self):
        source = self.source()
        self.assertEqual(source.count('chromium.launch('), 1)
        self.assertIn("process.platform!=='linux'||process.getuid()===0", source)
        self.assertIn("chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:remaining(20000)})", source)
        self.assertIn('sandboxCommand(args)', source)
        self.assertIn("probe.goto('chrome://sandbox')", source)
        self.assertIn("sandboxStatus(await probe.locator('body').innerText())", source)
        self.assertIn("assert.equal(report.versions.playwright,'1.64.1'", source)
        for forbidden in ('QA_CHROMIUM', 'executablePath:', 'ignoreDefaultArgs', 'args:', '--no-sandbox',
                          '--disable-setuid-sandbox', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, source)

    def test_browser_pid_group_uid_executable_and_actual_command_are_verified(self):
        source = self.source()
        for required in ('priorChildren.has(pid)', "processIdentity(Number(children[0]))",
                         'process_uid_mismatch', 'process_not_direct_child', 'process_group_not_owned',
                         "return {pid,start:fields[19]}", 'owned_process_identity_changed',
                         "readlinkSync('/proc/'+browserGroup.pid+'/exe'),chromium.executablePath()",
                         "readFileSync('/proc/'+browserGroup.pid+'/cmdline')", 'bytes.length<=16384',
                         "cdp.send('SystemInfo.getProcessInfo')", 'ownBrowserPid(info.processInfo),browserGroup.pid'):
            self.assertIn(required, source)
        self.assertNotIn('Browser.getBrowserCommandLine', source)
        self.assertLess(source.index('browserGroup=processIdentity'), source.index('browser.newBrowserCDPSession'))

    def test_database_profile_and_child_environment_are_owned_and_disposable(self):
        source = self.source()
        for required in ("mkdtemp(path.join(temporary,'yadinassi-form-browser-'))",
                         'env=childEnvironment(process.env,home);env.PYTHONPATH=repo',
                         'process.env.TMPDIR=home', 'delete process.env.TMPDIR', 'process.env.TMPDIR=previousTmp',
                         "arg.startsWith('--user-data-dir=')", 'browser_profile_not_owned',
                         "path.join(owned,'products.sqlite')", 'cwd:repo,env,detached:true',
                         "stdio:['ignore','pipe','ignore']"):
            self.assertIn(required, source)
        self.assertNotIn('env:process.env', source)
        self.assertNotIn('--open-browser', source)

    def test_global_deadline_and_rpc_budget_fail_before_admission(self):
        source = self.source()
        for required in ('const workDeadline=startedAt+160000', 'const totalDeadline=startedAt+180000',
                         'Date.now()>=workDeadline', 'timeout:remaining(15000)', 'maxBuffer:16384',
                         'const deadline=setTimeout(abort', 'const totalTimer=setTimeout(()=>{abort();process.exit(1);}',
                         'if(aborted||!allowedRequest(target,origin))return route.abort()',
                         "if(rpc>=100){abort();return route.abort().catch(()=>{});}"):
            self.assertIn(required, source)
        self.assertLess(source.index('if(rpc>=100)'), source.index('return route.continue()'))
        self.assertNotIn('bounded(main()', source)

    def test_cleanup_is_bounded_owned_verified_and_required_for_pass(self):
        source = self.source()
        for required in ("process.kill(-identity.pid,signal)", 'await groupGone(hostGroup);host=null;hostGroup=null',
                         "signalGroup(browserGroup,'SIGKILL');await groupGone(browserGroup)",
                         'attempt<20&&Date.now()<totalDeadline', "process.kill(-identity.pid,0)",
                         "bounded(browser.close(),cleanupRemaining(8000)",
                         "bounded(rm(owned,{recursive:true,force:true}),cleanupRemaining(2000)",
                         "await lstat(owned);throw Error('owned_directory_remains')",
                         "const cleanupFailure=code=>{report.status='FAIL'", 'browser_cleanup_unverified',
                         'host_cleanup_unverified', 'owned_directory_cleanup_unverified'):
            self.assertIn(required, source)
        self.assertLess(source.index('await stopHost();}catch'), source.index('rm(owned,{recursive:true'))
        self.assertLess(source.index('rm(owned,{recursive:true'), source.index("writeFile(path.join(output,'result.json')"))
        self.assertNotIn('pkill', source)
        self.assertNotIn('killall', source)

    def test_exact_checkout_tree_and_relevant_source_hashes_are_rechecked(self):
        source = self.source()
        self.assertIn("assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/", source)
        self.assertIn("assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA", source)
        self.assertEqual(source.count("git('status','--porcelain','--untracked-files=all')"), 2)
        for required in ("'frontend/form'", "'examples/forms'", "'tests/browser_ui'",
                         "'tests/test_form_browser_qa_contract.py'", "'.github/workflows/ui-browser-qa.yml'",
                         "tree:git('rev-parse','HEAD^{tree}')", 'source[name]=sha256(await readFile',
                         "assert.deepEqual(await sourceBinding(),report.binding,'source_binding_changed')"):
            self.assertIn(required, source)
        self.assertNotIn('build.mjs', source)
        self.assertNotIn('git checkout', source)

    def test_five_scenarios_include_exact_decimal_repeated_click_cancel_and_reattach(self):
        source = self.source()
        self.assertEqual(re.findall(r'await scenario\(scenarioNames\[(\d)\]', source), ['0', '1', '2', '3', '4', '5'])
        self.assertIn("const scenarioNames=['edit_then_command_exact_decimal','duplicate_click_close_cancel_and_reattach',\n  'sqlite_save_close_and_durable_readback','table_intake_edit_delete_save_reopen',\n  'existing_order_edit_discard_save_reopen','workspace_retained_forms_create_edit_reopen']", source)
        self.assertIn("page.getByLabel(name,{exact:true})", source)
        self.assertIn("await field('Unit price').fill('7.25');\n    await button('Calculate').click()", source)
        self.assertIn("assert.equal(await field('Total').inputValue(),'21.75')", source)
        self.assertIn('control.click();control.click()', source)
        self.assertIn("assert.deepEqual(events,['command'])", source)
        self.assertIn('Run the command before closing, or stop the launcher to discard edits.', source)
        self.assertIn('await idle();await page.goto(url)', source)
        self.assertIn("assert.equal(await field('Unit price').inputValue(),'9')", source)
        self.assertIn("assert.equal(await field('Total').inputValue(),'27')", source)
        self.assertIn('assert.deepEqual(results.map(row=>row.name),scenarioNames', source)
        workspace = source.split('await scenario(scenarioNames[5]', 1)[1]
        self.assertIn("visibleField('Order code').waitFor()", workspace)
        self.assertIn("[['Order code','B003'],['Description','Workspace created order']]", workspace)
        self.assertNotIn("visibleField('Code')", workspace)
        self.assertIn("phase='workspace_independent_readback'", workspace)
        self.assertIn("phase='workspace_intake_save'", workspace)
        self.assertIn("phase='workspace_intake_close'", workspace)
        self.assertIn("visibleField('Status').inputValue(),'Order saved'", workspace)
        self.assertIn("visibleField('Total').inputValue(),'3.25'", workspace)
        self.assertIn("visibleButton('Save order').isDisabled(),true", workspace)
        self.assertIn("report.workspaceCheckpoint=await bounded", workspace)
        self.assertIn("Math.min(32,document.querySelectorAll(selector).length)", workspace)

    def test_actual_product_is_saved_closed_then_reopened_for_exact_amount(self):
        source = self.source().split('await scenario(scenarioNames[2]', 1)[1]
        self.assertIn("'--import-xml',path.join(repo,'examples/forms/product-intake/configuration')", source)
        self.assertIn("await startHost('product-intake',database)", source)
        self.assertIn("await field(name).fill(value);await field(name).press('Enter');await idle()", source)
        self.assertIn("await button('Create product').click()", source)
        self.assertIn("assert.equal(await button('Create product').isDisabled(),true)", source)
        self.assertIn('This form is closed. You can close this tab.', source)
        self.assertIn('Message(Catalogs.Products.FindByCode("B001").Amount);', source)
        self.assertIn("assert.equal(readback.trim(),'18,75')", source)
        self.assertLess(source.index('await stopHost()'), source.index('const readback=runPython'))
        self.assertIn("report.durable={reopenedAfterHostClose:true,exactAmount:'18.75'}", source)

    def test_order_table_uses_real_edits_identity_delete_and_exact_durable_rows(self):
        source = self.source().split('await scenario(scenarioNames[3]', 1)[1]
        for required in ("path.join(owned,'orders.sqlite')",
                         "'--import-xml',path.join(repo,'examples/forms/order-intake/configuration')",
                         "await startHost('order-intake',database)",
                         "await button('Add line').click();await idle()",
                         "await field('Price, row '+id).fill(price)",
                         "await button('Select row 2 in Order lines').click();await idle()",
                         "await button('Delete selected line').click();await idle()",
                         "await field('Description, row 2').count(),0",
                         "await field('Description, row 3').inputValue(),'Service'",
                         "locator('tbody tr').count(),2",
                         "await field('Total').inputValue(),'9.08'",
                         "assert.equal(rpc,beforeInvalid,'invalid_command_draft_sent')",
                         "assert.equal(rpc,beforeInvalid,'invalid_selection_draft_sent')",
                         "await field('Price, row 1').fill('2.35');\n    await button('Save order').click()",
                         "await field('Total').inputValue(),'9.14'",
                         "await field('Amount, row 1').inputValue(),'2.94'",
                         "await field('Amount, row 3').inputValue(),'6.20'",
                         "await button(name).isDisabled(),true",
                         "await field(name).isEditable(),false",
                         "await page.setViewportSize({width:390,height:844})",
                         "node.scrollIntoView({block:'start'})",
                         "await field('Description, row 3').isVisible(),true",
                         "document.documentElement.scrollWidth<=innerWidth",
                         "await screenshot('order-table-narrow.png')",
                         'A=O.Lines.Get(0); B=O.Lines.Get(1)',
                         'A.ItemDescription<>"Cable" Or A.Quantity<>1.25 Or A.Price<>2.35 Or A.Amount<>2.94',
                         'B.ItemDescription<>"Service" Or B.Quantity<>2 Or B.Price<>3.10 Or B.Amount<>6.20',
                         'If N<>1 Then Raise "record count"',
                         "assert.equal(readback.trim(),'ORDER_READBACK_OK')",
                         "report.tableDurable={reopenedAfterHostClose:true,records:1,rows:2,exactTotal:'9.14',rowOrder:['Cable','Service']}"):
            self.assertIn(required, source)
        self.assertLess(source.index('await stopHost()'), source.index('const readback=runPython'))
        self.assertIn('completed:results.length,total:6,', self.source())

    def test_existing_order_edits_discard_invalid_draft_and_independently_reopens(self):
        source = self.source().split('await scenario(scenarioNames[4]', 1)[1]
        for required in ("await startHost('order-editor',database)",
                         "await button('Open selected order').click()",
                         "await field('Price, row 1').fill('invalid decimal')",
                         "assert.equal(rpc,beforeDiscard+1,'discard_flushed_invalid_draft')",
                         "await field('Price, row 1').count(),0,'discard_reused_row_identity'",
                         "await field('Price, row 3').fill('2.40')",
                         "await button('Save changes').isEnabled(),true",
                         "await field('Price, row 5').isEditable(),true",
                         'No changes; nothing was written',
                         "await screenshot('order-editor-narrow.png')",
                         "assert.equal(readback.trim(),'ORDER_EDITOR_READBACK_OK')",
                         'independentFormReopen:true,records:1,rows:2,exactTotal:'):
            self.assertIn(required, source)
        self.assertEqual(source.count("await startHost('order-editor',database)"), 2)
        self.assertLess(source.index('await stopHost()'), source.index('const readback=runPython'))
        self.assertLess(source.index('const readback=runPython'), source.rindex("await startHost('order-editor',database)"))

    def test_only_bounded_source_bound_screenshots_and_fixed_verdicts_are_emitted(self):
        source = self.source()
        for required in ("output=path.join(temporary,'yadinassi-form-browser-artifacts')", 'await mkdir(output);',
                         "const screenshots=['estimate.png','product-narrow.png','order-table-narrow.png','order-editor-narrow.png','orders-workspace-narrow.png']",
                         "const artifacts=['result.json','manifest.json',...screenshots]",
                         'stat.isFile()&&!stat.isSymbolicLink()&&stat.size>0&&stat.size<=4*1024*1024',
                         "'89504e470d0a1a0a'", 'Buffer.byteLength(raw)<=65536',
                         'resultSha256:sha256(raw)', 'sha256:sha256(bytes)', 'capability_leak',
                         "(await readdir(output)).every(name=>artifacts.includes(name))",
                         "reason:aborted?'deadline_or_rpc_budget'", "'sandbox_start_denied':'step_failed'",
                         "if(failed||report.status!=='PASS')process.exitCode=1",
                         "localStorage.length+sessionStorage.length),0", "(await context.cookies()).length,0"):
            self.assertIn(required, source)
        for forbidden in ('error.stack', 'console.error(error', 'console.log(error', 'redact(error',
                          'recordHar', 'recordVideo', 'tracing.start', 'storageState(', 'writeFile(database'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()

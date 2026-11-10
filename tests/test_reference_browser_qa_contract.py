"""Closed reference-browser acquisition contracts. No launch, network or install."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReferenceBrowserQAContractTests(unittest.TestCase):
    def source(self):
        return (ROOT / 'tests/browser_ui/reference_browser_qa.mjs').read_text(encoding='utf-8')

    def workflow(self):
        return (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')

    def test_third_route_is_exact_and_preserves_two_existing_routes(self):
        source = self.workflow()
        trigger = source.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip()
        self.assertEqual(trigger, 'push:\n    branches: [codex/ui-browser-reviewed, codex/form-browser-reviewed, codex/reference-browser-reviewed, codex/configuration-browser-reviewed, codex/application-host-browser-reviewed]')
        for branch, harness in [('ui', 'demo_kind'), ('form', 'form'), ('reference', 'reference'), ('configuration', 'configuration')]:
            self.assertEqual(source.count(f"if: github.ref == 'refs/heads/codex/{branch}-browser-reviewed'"), 1)
            self.assertEqual(source.count(f'run: node tests/browser_ui/{harness}_browser_qa.mjs'), 1)
        self.assertIn("|| github.ref == 'refs/heads/codex/form-browser-reviewed' && 'form-browser-reviewed' || github.ref == 'refs/heads/codex/reference-browser-reviewed' && 'reference-browser-reviewed' || github.ref == 'refs/heads/codex/application-host-browser-reviewed' && 'application-host-browser-reviewed' || 'configuration-browser-reviewed' }}", source)
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'sudo ', 'sysctl ', 'container:', 'secrets.', 'write', '--with-deps'):
            self.assertNotIn(forbidden, source)
        self.assertIn('permissions:\n  contents: read', source)
        self.assertIn('runs-on: ubuntu-22.04\n    timeout-minutes: 10', source)
        self.assertEqual(source.count('timeout-minutes: 5'), 5)

    def test_exact_reference_artifact_allowlist_and_pinned_actions(self):
        source = self.workflow()
        step = source.split('      - name: Publish only reference screenshots and redacted source-bound report\n', 1)[1]
        self.assertIn("if: always() && github.ref == 'refs/heads/codex/reference-browser-reviewed'", step)
        self.assertIn('name: reference-browser-${{ github.sha }}-${{ github.run_attempt }}', step)
        paths = step.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines()], [
            '${{ runner.temp }}/yadinassi-reference-browser-artifacts/' + name for name in
            ['result.json', 'manifest.json', 'reference-created.png', 'reference-choice-narrow.png', 'reference-reopened.png']])
        self.assertIn('if-no-files-found: error\n          retention-days: 14', step)
        self.assertEqual(re.findall(r'uses: (\S+)', source), [
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
            'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
            *['actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'] * 5])
        self.assertIn('npm ci --prefix tests/browser_ui --ignore-scripts --no-audit --no-fund', source)
        self.assertIn('install chromium --no-shell', source)

    def test_three_scenarios_only_with_exact_completion(self):
        source = self.source()
        self.assertIn("const scenarioNames=['create_choose_save_exact_references',\n  'edit_invalid_draft_cancel_and_selected_row_ownership','independent_readback_and_fresh_workspace_reopen']", source)
        self.assertEqual(re.findall(r'await scenario\(scenarioNames\[(\d)\]', source), ['0', '1', '2'])
        self.assertIn('assert.deepEqual(results.map(row=>row.name),scenarioNames', source)
        self.assertIn('completed:results.length,total:3,', source)

    def test_sandbox_must_be_requested_and_independently_verified(self):
        source = self.source()
        self.assertEqual(source.count('chromium.launch('), 1)
        for required in ("process.platform!=='linux'||process.getuid()===0",
                         "chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:remaining(20000)})",
                         'sandboxCommand(args)', "probe.goto('chrome://sandbox')",
                         "sandboxStatus(await probe.locator('body').innerText())",
                         "assert.equal(report.versions.playwright,'1.64.1'"):
            self.assertIn(required, source)
        for forbidden in ('QA_CHROMIUM', 'executablePath:', 'ignoreDefaultArgs', 'args:', '--no-sandbox', '--disable-setuid-sandbox', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, source)

    def test_launch_checkpoints_identify_the_last_safe_stage_without_raw_data(self):
        source = self.source()
        stages = re.findall(r"report\.launch\.stage='([^']+)'", source)
        self.assertEqual(stages, ['socket_path_budget', 'chromium_launch', 'children_after', 'process_identity',
            'executable_identity', 'browser_command', 'browser_profile', 'browser_ready',
            'cdp_session', 'cdp_process_identity', 'cdp_detach', 'browser_context',
            'sandbox_page', 'sandbox_status', 'sandbox_probe_close', 'verified'])
        self.assertIn("report.launch={stage:'children_before',returned:false,children:null,groupVerified:false,", source)
        self.assertIn('report.launch.children=Math.min(children.length,2)', source)
        for flag in ['returned', 'groupVerified', 'executableVerified', 'commandVerified', 'profileVerified']:
            self.assertEqual(source.count('report.launch.' + flag + '=true'), 1)
        self.assertIn('report.launch.launchFailure=launchFailureCode(error);throw error', source)
        self.assertIn("if(phase==='sandbox_launch'&&report.launch)report.launch.failure=launchFailureCode(error)", source)
        self.assertNotIn('report.launch.error=', source)
        self.assertNotIn('report.launch.pid=', source)
        self.assertNotIn('report.launch.path=', source)
        self.assertNotIn('report.launch.args=', source)

    def test_launch_error_diagnostics_are_an_explicit_fixed_allowlist(self):
        source = self.source()
        classifier = source.split('function launchFailureCode(error){', 1)[1].split('function processIdentity', 1)[0]
        self.assertIn("message===code||message.startsWith(code+'\\n')", classifier)
        self.assertIn("return 'unclassified_launch_failure'", classifier)
        self.assertEqual(re.findall(r"return '([^']+)'", classifier), [
            'sandbox_start_denied', 'browser_binary_missing', 'browser_dependency_missing',
            'browser_operation_timeout', 'launch_file_missing', 'launch_access_denied',
            'launch_process_gone', 'unclassified_launch_failure'])
        self.assertIn("'process_uid_mismatch','process_not_direct_child'", classifier)
        self.assertIn("'browser_executable_mismatch'", classifier)
        self.assertIn("'browser_profile_not_owned'", classifier)
        for forbidden in ('return message', 'return error', 'error.stack', 'error.actual', 'error.expected',
                          'JSON.stringify', 'console.', 'writeFile', 'process.env'):
            self.assertNotIn(forbidden, classifier)

    def test_owned_temp_prefix_fits_pinned_chromium_linux_socket_path(self):
        source = self.source()
        prefix = re.search(r"owned=await mkdtemp\(path.join\(temporary,'([^']+)'\)\)", source).group(1)
        self.assertEqual(prefix, 'ya-ref-')
        runner_temp = '/home/runner/work/_temp'
        suffix = '/org.chromium.Chromium.XXXXXX/SingletonSocket'
        fixed = f'{runner_temp}/{prefix}XXXXXX/home{suffix}'
        previous = f'{runner_temp}/yadinassi-reference-browser-XXXXXX/home{suffix}'
        working_form = f'{runner_temp}/yadinassi-form-browser-XXXXXX/home{suffix}'
        self.assertEqual(len(previous.encode('utf-8')), 108)
        self.assertEqual(len(working_form.encode('utf-8')), 103)
        self.assertEqual(len(fixed.encode('utf-8')), 87)
        self.assertLess(len(fixed.encode('utf-8')), 108)
        self.assertIn("home=path.join(owned,'home');await mkdir(home)", source)
        self.assertNotIn("mkdtemp('/tmp/", source)

    def test_socket_path_budget_fails_closed_before_chromium_launch(self):
        source = self.source()
        guard = "assert.ok(Buffer.byteLength(path.join(home,'org.chromium.Chromium.XXXXXX','SingletonSocket'))<108,'browser_socket_path_too_long');"
        self.assertEqual(source.count(guard), 1)
        self.assertLess(source.index(guard), source.index('browser=await chromium.launch('))
        self.assertIn("'browser_socket_path_too_long','browser_process_missing'", source)
        # Buffer.byteLength is intentional: non-ASCII runner paths consume bytes,
        # and the final NUL must also fit Linux's 108-byte sockaddr_un.sun_path.
        self.assertEqual(len(('a' * 107).encode('utf-8')), 107)
        self.assertGreaterEqual(len(('é' * 54).encode('utf-8')), 108)
        self.assertNotIn('report.launch.socketPath=', source)
        self.assertNotIn('report.launch.home=', source)

    def test_browser_identity_group_profile_and_environment_are_owned(self):
        source = self.source()
        for required in ('priorChildren.has(pid)', 'process_not_direct_child', 'process_uid_mismatch',
                         'process_group_not_owned', "return {pid,start:fields[19]}",
                         "readlinkSync('/proc/'+browserGroup.pid+'/exe'),chromium.executablePath()",
                         "readFileSync('/proc/'+browserGroup.pid+'/cmdline')", 'bytes.length<=16384',
                         "cdp.send('SystemInfo.getProcessInfo')", 'ownBrowserPid(info.processInfo),browserGroup.pid',
                         "mkdtemp(path.join(temporary,'ya-ref-'))",
                         'env=childEnvironment(process.env,home);env.PYTHONPATH=repo',
                         'process.env.TMPDIR=home', 'delete process.env.TMPDIR', 'process.env.TMPDIR=previousTmp',
                         'browser_profile_not_owned', 'cwd:repo,env,detached:true', "stdio:['ignore','pipe','ignore']"):
            self.assertIn(required, source)
        self.assertNotIn('env:process.env', source)
        self.assertNotIn('--open-browser', source)

    def test_closed_loopback_and_one_hundred_rpc_deadline_admission(self):
        source = self.source()
        for required in ('const workDeadline=startedAt+160000', 'const totalDeadline=startedAt+180000',
                         'Date.now()>=workDeadline', 'timeout:remaining(15000)', 'maxBuffer:16384',
                         'if(aborted||!allowedRequest(target,origin))return route.abort()',
                         "if(rpc>=100){abort();return route.abort().catch(()=>{});}",
                         'const deadline=setTimeout(abort', 'const totalTimer=setTimeout(()=>{abort();process.exit(1);}'):
            self.assertIn(required, source)
        self.assertLess(source.index('if(rpc>=100)'), source.index('return route.continue()'))
        self.assertNotIn('route.fulfill', source)
        support = (ROOT / 'tests/browser_ui/support.mjs').read_text(encoding='utf-8')
        self.assertIn('url.origin === origin && !url.username && !url.password && !url.search', support)
        self.assertIn("['/', '/app.js', '/style.css', '/LICENSE.txt', '/rpc', '/favicon.ico']", support)

    def test_cleanup_is_positive_bounded_owned_and_mandatory(self):
        source = self.source()
        for required in ('owned_process_identity_changed', 'process.kill(-identity.pid,signal)',
                         'await groupGone(hostGroup);host=null;hostGroup=null',
                         "signalGroup(browserGroup,'SIGKILL');await groupGone(browserGroup)",
                         'attempt<20&&Date.now()<totalDeadline', 'process.kill(-identity.pid,0)',
                         'bounded(browser.close(),cleanupRemaining(8000)',
                         "bounded(rm(owned,{recursive:true,force:true}),cleanupRemaining(2000)",
                         "await lstat(owned);throw Error('owned_directory_remains')",
                         "const cleanupFailure=code=>{report.status='FAIL'", 'browser_cleanup_unverified',
                         'host_cleanup_unverified', 'owned_directory_cleanup_unverified'):
            self.assertIn(required, source)
        self.assertLess(source.index('await stopHost();}catch'), source.index('rm(owned,{recursive:true'))
        self.assertLess(source.index('rm(owned,{recursive:true'), source.index("writeFile(path.join(output,'result.json')"))
        self.assertNotIn('pkill', source)
        self.assertNotIn('killall', source)

    def test_binding_covers_reference_code_and_rechecks_exact_clean_tree(self):
        source = self.source()
        self.assertIn("assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/", source)
        self.assertIn('assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA', source)
        self.assertEqual(source.count("git('status','--porcelain','--untracked-files=all')"), 2)
        for required in ("'frontend/reference-workspace'", "'frontend/form'", "'examples/forms'", "'tests/browser_ui'",
                         "'tests/test_reference_browser_qa_contract.py'", "'.github/workflows/ui-browser-qa.yml'",
                         "tree:git('rev-parse','HEAD^{tree}')", 'source[name]=sha256(await readFile',
                         "assert.deepEqual(await sourceBinding(),report.binding,'source_binding_changed')"):
            self.assertIn(required, source)
        self.assertNotIn('build.mjs', source)
        self.assertNotIn('git checkout', source)

    def test_real_fixed_launcher_and_fresh_seed_never_reuse_fixture(self):
        source = self.source()
        for required in ("'-m','yadinassi.ui.reference_orders_workspace',path.join(repo,'examples/forms'),'--f',database",
                         "path.join(owned,'references.sqlite')", "'--create-db',database,'--import-xml'",
                         "'examples/forms/reference-order/configuration'", 'C1.Code="C001"', 'C2.Code="C002"',
                         'P1.UnitPrice=2.50', 'P2.UnitPrice=4.25', 'O.Customer=C1.Ref', 'R.Product=P1.Ref',
                         "page.locator('#reference-orders-app')", "'Open order O001: First order'"):
            self.assertIn(required, source)
        self.assertEqual(source.count('await startHost(database)'), 2)
        self.assertNotIn('tests/test_reference_orders.py', source)

    def test_browser_requests_are_scalar_form_events_without_reference_payloads(self):
        source = self.source()
        for required in ("exactKeys(packet,'jsonrpc id method params')", "'yadinassi-reference-orders/1'",
                         "exactKeys(packet.params,'session request')", "exactKeys(nested,'jsonrpc id method params')",
                         "'yadinassi-form-ui/1'", "assert.equal(nested.method,'form.event')",
                         "cell:'event revision control row column value'", "exactKeys(event.value,'type value')",
                         "'scalar_value_only'", "assert.equal(wireFailure,false,'wire_contract_failed')"):
            self.assertIn(required, source)
        wire = source.split('function checkRequest', 1)[1].split('async function repeatClick', 1)[0]
        for forbidden in ('CatalogKey', 'ApplyChoice', 'endpoint', 'routine', 'path:'):
            self.assertNotIn(forbidden, wire)

    def test_new_order_choices_exact_decimal_and_repeated_intent(self):
        source = self.source().split('await scenario(scenarioNames[0]', 1)[1].split('await scenario(scenarioNames[1]', 1)[0]
        for required in ("repeatClick(button('New order'))", 'rpc,before+2', "owner().count(),1",
                         "[['Order code','B001'],['Description','Browser reference order']]",
                         "openChoice('Choose customer',{repeat:true})", "chooseCode('C002',{search:true,holdRefresh:true})",
                         "openChoice('Choose product for selected line')", "chooseCode('P002')",
                         "ownerField('Price, row 1').inputValue(),'4.25'", "ownerField('Quantity, row 1').fill('2')",
                         "ownerField('Total').inputValue(),'8.50'", "screenshot('reference-created.png')"):
            self.assertIn(required, source)

    def test_owner_stays_frozen_until_ordinary_snapshot_finishes(self):
        source = self.source()
        for required in ("packet.params.request.method==='form.snapshot'", 'held.admitted()',
                         "bounded(held.gate,remaining(5000),'snapshot_hold_timeout')", "owner_thawed_before_snapshot",
                         "node.inert&&node.querySelector('fieldset').disabled", 'frozen_owner_sent_request',
                         'owner_mutation_during_refresh', 'finally{release();snapshotGate=null;}',
                         "await dialog().waitFor({state:'detached'});await ownerReady()"):
            self.assertIn(required, source)
        self.assertNotIn('setTimeout(resolve,500', source)

    def test_invalid_draft_cancel_close_and_selected_row_are_meaningful(self):
        source = self.source().split('await scenario(scenarioNames[1]', 1)[1].split('await scenario(scenarioNames[2]', 1)[0]
        for required in ("ownerField('Price, row 2').fill('not-a-number')", 'invalid_choice_draft_sent',
                         "dialog().count(),0", "ownerField('Price, row 2').fill('9')", 'choice_changed_unselected_row',
                         "ownerField('Description, row 1').inputValue(),'Original description'",
                         "ownerField('Price, row 2').inputValue(),'4.25'", "ownerField('Quantity, row 2').fill('2')",
                         "repeatClick(childButton('Cancel selection'))", "event.control==='CancelButton'", 'cancel_repeated',
                         "await dialog().press('Escape')", "ownerField('Total').inputValue(),'11.00'",
                         'width:390,height:844', 'document.documentElement.scrollWidth<=innerWidth',
                         "screenshot('reference-choice-narrow.png')"):
            self.assertIn(required, source)

    def test_independent_cli_sqlite_typed_keys_then_fresh_host_reopen(self):
        source = self.source()
        third = source.split('await scenario(scenarioNames[2]', 1)[1]
        for required in ('REFERENCE_CLI_READBACK_OK', 'REFERENCE_SQLITE_READBACK_OK',
                         'with SQLiteDBContext(sys.argv[1]) as context:', 'type(stored[0]) is not CatalogKey',
                         'type(row.values[0]) is not CatalogKey or row.values[0] != refs[product]',
                         "manager._stored(field, obj.get_member(field.name))", "obj._sections['lines']._stored_rows().rows",
                         'Decimal(quantity), Decimal(price), Decimal(amount)', 'If N<>2 Then Raise',
                         'B.Customer<>Catalogs.Customers.FindByCode("C001")', 'A.Customer<>Catalogs.Customers.FindByCode("C002")',
                         "await startHost(database);await page.goto(url)", "page.getByLabel('Find exact code',{exact:true}).fill('B001')",
                         "ownerField('Total').inputValue(),'8.50'", "ownerField('Total').inputValue(),'11.00'",
                         'independentCli:true,independentSQLite:true,freshHostReopen:true,typedKeys:true'):
            self.assertIn(required, third)
        self.assertLess(source.index('await stopHost();\n  });\n  await scenario(scenarioNames[2]'), source.index('const readback=runPython'))
        self.assertLess(third.index('const audit=runPython'), third.index('await startHost(database)'))

    def test_fresh_reopen_requires_exact_two_place_quantity_not_draft_text(self):
        source = self.source()
        fresh = source.split("phase='fresh_host_reopen';", 1)[1]
        self.assertIn("ownerField('Quantity, row 1').inputValue(),'2.00','reopened_quantity_scale'", fresh)
        self.assertNotIn("ownerField('Quantity, row 1').inputValue(),'2')", fresh)
        self.assertIn("ownerField('Quantity, row 2').inputValue(),'2'", source)
        self.assertNotIn('parseFloat(', fresh)
        configuration = (ROOT / 'examples/forms/reference-order/configuration/Catalogs/Orders.xml').read_text(encoding='utf-8')
        quantity = configuration.split('<Name>Quantity</Name>', 1)[1].split('</Attribute>', 1)[0]
        self.assertIn('<v8:FractionDigits>2</v8:FractionDigits>', quantity)

    def test_small_fixed_artifacts_hashes_and_no_raw_diagnostics(self):
        source = self.source()
        for required in ("output=path.join(temporary,'yadinassi-reference-browser-artifacts')", 'await mkdir(output);',
                         "const screenshots=['reference-created.png','reference-choice-narrow.png','reference-reopened.png']",
                         "const artifacts=['result.json','manifest.json',...screenshots]",
                         'stat.isFile()&&!stat.isSymbolicLink()&&stat.size>0&&stat.size<=4*1024*1024',
                         "'89504e470d0a1a0a'", 'Buffer.byteLength(raw)<=65536',
                         'resultSha256:sha256(raw)', 'sha256:sha256(bytes)', 'capability_leak',
                         "(await readdir(output)).every(name=>artifacts.includes(name))",
                         "if(failed||report.status!=='PASS')process.exitCode=1",
                         'localStorage.length+sessionStorage.length),0', '(await context.cookies()).length,0'):
            self.assertIn(required, source)
        for forbidden in ('error.stack', 'console.error(error', 'console.log(error', 'redact(error', 'recordHar',
                          'recordVideo', 'tracing.start', 'storageState(', 'writeFile(database'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()

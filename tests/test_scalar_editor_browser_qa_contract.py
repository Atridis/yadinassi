"""Offline source contracts only: no browser, process, acquisition or network."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ['ui', 'form', 'reference', 'configuration', 'application-host',
          'business-application', 'document-form', 'configuration-reference', 'scalar-editor']


class ScalarEditorBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tests/browser_ui/scalar_editor_browser_qa.mjs').read_text(encoding='utf-8')
        cls.workflow = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')

    def requires(self, *values):
        for value in values:
            self.assertIn(value, self.source)

    def scenario(self, index):
        return self.source.split(f'await scenario(scenarioNames[{index}]', 1)[1].split(
            f'await scenario(scenarioNames[{index + 1}]', 1)[0]

    def step(self, name):
        return self.workflow.split('      - name: ' + name + '\n', 1)[1].split('\n      - ', 1)[0]

    def test_four_named_scenarios_and_exact_56_rpc_plan(self):
        names = re.findall(r"'([^']+)'", self.source.split('const scenarioNames=', 1)[1].split(';', 1)[0])
        self.assertEqual(names, ['catalog_datetime_empty_qualifier_preflight', 'document_datetime_lines_durable_restart',
                                'isolated_invalid_drafts_retained_tabs', 'held_write_reply_dirty_sibling_natural_shutdown'])
        self.assertEqual(re.findall(r'await scenario\(scenarioNames\[(\d)\]', self.source), ['0', '1', '2', '3'])
        self.requires('const plannedRPC=[13,29,7,7]', 'total:4', "'total_rpc_plan'", "'incomplete_scenarios'",
                      "'catalog_rpc_plan'", "'restart_rpc_plan'", "'invalid_draft_rpc_plan'")

    def test_pinned_browser_and_real_nonroot_sandbox_are_mandatory(self):
        self.assertEqual(self.source.count('chromium.launch('), 1)
        self.requires("process.platform!=='linux'||process.getuid()===0", 'chromiumSandbox:true',
                      "probe.goto('chrome://sandbox')", 'sandboxCommand(args)',
                      "sandboxStatus(await probe.locator('body').innerText())", "report.versions.playwright,'1.64.1'")
        for forbidden in ('--no-sandbox', 'chromiumSandbox:false', 'executablePath:', 'ignoreDefaultArgs', 'sudo ', 'sysctl '):
            self.assertNotIn(forbidden, self.source)

    def test_process_groups_profiles_and_sanitized_environment_are_owned(self):
        self.requires('priorChildren.has(pid)', 'return {pid,start:fields[19]}', 'process_uid_mismatch',
                      'process_not_direct_child', 'process_group_not_owned', 'owned_process_identity_changed',
                      "readlinkSync('/proc/'+browserGroup.pid+'/exe'),chromium.executablePath()",
                      "cdp.send('SystemInfo.getProcessInfo')", 'ownBrowserPid(info.processInfo),browserGroup.pid',
                      "mkdtemp(path.join(temporary,'ya-se-'))", 'browser_socket_path_too_long',
                      'browser_profile_not_owned', 'env=childEnvironment(process.env,home);env.PYTHONPATH=repo',
                      'process.env.TMPDIR=home', 'process.env.TMPDIR=previousTmp', 'cwd:repo,env,detached:true')
        self.assertNotIn('env:process.env', self.source)
        self.assertNotIn('--open-browser', self.source)

    def test_deadline_and_request_caps_precede_admission(self):
        self.requires('startedAt+220000', 'startedAt+240000', 'performance.now()>=workDeadline',
                      'const deadline=setTimeout(abort', 'const totalTimer=setTimeout(()=>{abort();process.exit(1);}',
                      'if(rpc>=100){abort();return route.abort().catch(()=>{});}', '++attachmentRequests<=96',
                      'bytes.length<=131072', 'bytes.length<=8192', 'maxRetries:0', 'maxRedirects:0')
        route = self.source.split("await context.route('**/*'", 1)[1]
        self.assertLess(route.index('if(rpc>=100)'), route.index('const packet=checkRequest'))
        self.assertNotIn('bounded(main()', self.source)

    def test_network_is_closed_to_exact_owned_origin_and_existing_paths(self):
        self.requires('if(aborted||!applicationAllowedRequest(target))return route.abort()',
                      'if(allowedRequest(target,origin))return true',
                      "parsed.origin===origin&&!parsed.username&&!parsed.password&&!parsed.search&&parsed.pathname==='/attachment'",
                      "serviceWorkers:'block'", 'acceptDownloads:false', 'applicationLaunchReader()',
                      'host_output_budget', 'invalid_launch_output')
        self.assertNotIn('route.fulfill({json:', self.source)
        self.assertNotIn('route.fulfill({body:', self.source)
        request = self.source.split('function checkRequest(request){', 1)[1].split('async function scenario', 1)[0]
        for forbidden in ("'source'", "'routine'", "'eval'", "'handler'"):
            self.assertNotIn(forbidden, request)

    def test_only_exact_busy_heartbeat_refusal_passes_through_without_retry(self):
        attachment = self.source.split("if(new URL(target).pathname==='/attachment'){", 1)[1].split(
            "if(new URL(target).pathname==='/rpc'){", 1)[0]
        condition = "if(body.action==='heartbeat'&&response.status()===409){"
        self.assertEqual(attachment.count(condition), 1)
        benign = attachment.split(condition, 1)[1].split("assert.equal(response.status(),200,'attachment_refused')", 1)[0]
        for required in ("exactKeys(value,'protocol error')", "assert.equal(value.protocol,'yadinassi-browser-attachment/1')",
                         "assert.equal(value.error,'busy','unexpected_heartbeat_refusal')",
                         '++report.heartbeatBusy<=attachmentRequests', 'return await route.fulfill({response})'):
            self.assertIn(required, benign)
        self.assertEqual(attachment.count('route.fetch('), 1)
        self.assertNotIn('route.fetch(', benign)
        self.assertNotIn('route.continue(', attachment)
        self.requires("assert.equal(response.status(),200,'rpc_status')", "headers['x-yadinassi-attachment']",
                      "headers['x-yadinassi-generation']", 'value.leaseSeconds,90', 'value.graceSeconds,30')

    def test_date_and_reference_wire_packets_remain_closed_and_distinct(self):
        self.requires("exactKeys(value,'type ticks')", 'String(BigInt(value.ticks))===value.ticks',
                      'BigInt(event.value.ticks)<=3155378975980000n', 'BigInt(event.value.ticks)%10000n===0n',
                      "['DateInput','AvailableDateInput'].includes(event.control)", "event.column==='DeliveryDate'",
                      "['DeliveryDate','Label','Quantity','Checked'].includes(event.column)",
                      "exactKeys(value,'type scope target key text')", "'unissued_picker_ticket'", "'unissued_choice'",
                      "'persistent_uuid_in_request'", "'persistent_uuid_in_reply'")
        request = self.source.split('function checkRequest(request){', 1)[1].split('async function scenario', 1)[0]
        self.assertIn("['String','Number','Boolean','Date'].includes(event.value.type)", request)
        self.assertNotIn("'FormCatalogRef'].includes(event.value.type)", request)
        for forbidden in ('new Date(', 'Date.parse(', 'Date.UTC(', '.toISOString(', '.getTimezoneOffset('):
            self.assertNotIn(forbidden, self.source)

    def test_source_binding_includes_example_projection_frontend_and_all_bundles(self):
        self.requires("'examples/configuration-scalar-editors'", "'yadinassi/ui/form_app.py'",
                      "'frontend/form/src/client.mjs'", "'frontend/form/src/view.mjs'", "'frontend/form/src/app.mjs'",
                      "'frontend/configuration/src/app.mjs'", "'frontend/reference-workspace'", "'frontend/workspace'",
                      "'yadinassi/ui/assets/form/app.js'", "'yadinassi/ui/assets/configuration/app.js'",
                      "'yadinassi/ui/assets/reference-workspace/app.js'", "'yadinassi/ui/assets/workspace/app.js'",
                      "'tests/test_form_editor_projection.py'", "'tests/test_configuration_scalar_editors.py'",
                      "'tests/test_scalar_editor_browser_qa_contract.py'", "'docs/typed-scalar-browser-qa.md'",
                      "tree:git('rev-parse','HEAD^{tree}')", 'source[name]=sha256(await readFile', "'source_binding_changed'")
        self.assertEqual(self.source.count("git('status','--porcelain','--untracked-files=all')"), 2)
        self.assertNotIn('build.mjs', self.source)

    def test_fixture_is_fixed_valid_python_for_only_the_fresh_owned_database(self):
        script = self.source.split('  const script=`', 1)[1].split('\n`;', 1)[0]
        ast.parse(script)
        self.requires("'--reference-application'", "'scalars.sqlite'", 'assert not target.exists()',
                      'SQLiteCatalogBackend.create_reference_application', 'assert backend.storage_version==7',
                      "['create','leap','empty','first','final']", 'maxBuffer:128', "'SCALAR_FIXTURE_OK'")
        for forbidden in ('OwnedInfobase', 'tests/fixtures/native', 'integrational_tests'):
            self.assertNotIn(forbidden, self.source)
        # Inspect Python calls, not JavaScript's unrelated RegExp.exec method.
        for node in ast.walk(ast.parse(script)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('eval', 'exec', '__import__'))

    def test_catalog_audits_prove_naive_typed_leap_day_and_empty_with_separate_read_only_access(self):
        self.requires('SQLiteCatalogBackend(target,read_only=True)', 'backend.export_configuration()==files',
                      "type(values['Price']) is Decimal", 'type(stamp) is datetime and stamp.tzinfo is None and stamp.microsecond==0',
                      "datetime(2024,2,29,23,45,17) if mode=='leap' else datetime(1,1,1)",
                      "fixture('leap')", "fixture('empty')", 'sha256(target.read_bytes()).digest()==before')

    def test_document_audit_uses_field_names_and_exact_datetime_decimal_reference_types(self):
        self.requires('view.read_document(card.key)', 'zip(schema.fields,first.values)', 'zip(fields,rows[0].values)',
                      'zip(fields,rows[1].values)', 'type(first.date) is datetime and first.date.tzinfo is None',
                      "first.date==datetime(2024,3,10,2,30,1 if mode=='final' else 0)",
                      "first_line['DeliveryDate']==datetime(2024,11,3,1,30,0)",
                      "second_line['DeliveryDate']==datetime(2024,3,31,2,30,0)",
                      "type(line['Quantity']) is Decimal", "type(line['Product']) is CatalogKey",
                      "first_line['Product']==products['P2'].key", "sibling.date==datetime(1,1,1)", "fixture('final')")

    def test_product_price_and_length_preflight_are_individually_unmasked(self):
        scenario = self.scenario(0)
        self.requires("'price_precision_sent_rpc'", "'title_silently_truncated'", "'long_title_sent_rpc'",
                      "commitInput('Unit price','8.5000')", "value('Unit price','8.50')", "'corrected_price_sent_twice'",
                      "typed(appState.active,'AvailableDateInput'),{type:'Date',ticks:'0'},'clear_not_typed_date_zero'")
        self.assertLess(scenario.index("field('Unit price').fill('7.25')"), scenario.index("field('Product title').fill('x'.repeat(81))"))
        self.assertLess(scenario.index("field('Product title').fill('Scalar product')"), scenario.index("commitInput('Unit price','8.5000')"))

    def test_document_real_ui_save_natural_exit_restart_and_reopen_are_explicit(self):
        scenario = self.scenario(1)
        self.requires("commitInput('Order date and time','2024-03-10T02:30:00')",
                      "commitInput('DeliveryDate, row 1','2024-11-03T01:30:00')",
                      "commitInput('DeliveryDate, row 2','2024-03-31T02:30:00')",
                      "select('Product, row 1','P2','Scalar product')", "commitInput('Quantity, row 1','3.2500')",
                      "phase='document_close_saved';await closeForm(1)", "phase='document_close_welcome';await closeForm(0)",
                      "phase='document_ordinary_shutdown';await ordinaryShutdown()", "fixture('first')",
                      "await openNumber('D1')", "value('DeliveryDate, row 2','2024-03-31T02:30:00')")
        self.assertLess(scenario.index('await ordinaryShutdown()'), scenario.index("fixture('first')"))
        self.assertLess(scenario.index("fixture('first')"), scenario.index('await startHost()'))

    def test_each_invalid_class_blocks_save_selection_and_reference_without_business_rpc(self):
        helper = self.source.split('const blockedIntents=async()=>{', 1)[1].split('let firstOrder', 1)[0]
        for required in ("'invalid_save_sent_rpc'", "'invalid_selection_sent_rpc'", "'invalid_reference_sent_rpc'",
                         "'invalid_opened_picker'", "action('Choose Product, row 1').click()"):
            self.assertIn(required, helper)
        scenario = self.scenario(2)
        self.assertEqual(scenario.count('await blockedIntents()'), 4)
        self.requires("field('Order date and time').fill('2024-02-30T02:30:00')", "'isolated_negative_quantity_preflight'",
                      "field('Quantity, row 1').fill('-1')", "field('Quantity, row 1').fill('3.25')",
                      "'isolated_quantity_scale_preflight'", "field('Quantity, row 1').fill('3.251')",
                      "'isolated_note_length_preflight'", "field('Note').fill('n'.repeat(81))", "'note_silently_truncated'")
        self.assertLess(scenario.index("commitInput('Order date and time','2024-03-10T02:30:01')"), scenario.index("field('Quantity, row 1').fill('-1')"))
        self.assertLess(scenario.index("field('Quantity, row 1').fill('3.25')"), scenario.index("field('Quantity, row 1').fill('3.251')"))
        self.assertLess(scenario.index("commitInput('Quantity, row 1','4.5000')"), scenario.index("field('Note').fill('n'.repeat(81))"))

    def test_raw_tab_retention_and_exactly_once_corrections_preserve_reference_identities(self):
        self.requires("'invalid_close_sent_rpc'", "'tab_switch_submitted_draft'", "'corrected_date_sent_twice'",
                      "'corrected_quantity_sent_twice'", "'corrected_note_sent_twice'", "value('Note','n'.repeat(81))",
                      "'header_reference_changed_by_scalar_input'", "'line_reference_changed_by_scalar_input'",
                      "grid.columns.findIndex(column=>column.name==='Product')")
        self.assertNotIn('page.reload()', self.scenario(2))

    def test_held_response_is_real_once_only_after_the_server_completed_write(self):
        rpc = self.source.split("if(new URL(target).pathname==='/rpc'){", 1)[1]
        self.assertLess(rpc.index('const response=await route.fetch'), rpc.index('await bounded(gate.released'))
        self.requires("packet.params.request.params.event==='command'&&packet.params.request.params.control==='WriteButton'",
                      'control.click();control.click()', 'gate.entered()', 'await bounded(gate.released',
                      'return await route.fulfill({response})', 'finally{release();}', "'double_write_replayed'",
                      "'held_write_not_saved'")
        self.assertNotIn('dispatchEvent(', self.source)

    def test_late_navigation_does_not_steal_sibling_or_send_close_and_dirty_sibling_is_saved(self):
        self.requires("'late_close_sent_work'", "'late_close_removed_owner'", "'late_reply_changed_sibling'",
                      "await value('Number (blank for automatic)','D2')", 'await ownerClose.evaluate(control=>control.click())',
                      "'dirty_sibling_closed'", "typed(sibling,'NoteInput').value,'Sibling draft'",
                      'await writeDocument();await closeForm(2);await switchOrder(0);await closeForm(1);await closeForm(0);await ordinaryShutdown()')
        self.assertNotIn("action('Discard')", self.source)

    def test_screenshots_prove_visible_editable_dates_tables_and_invalid_raw_input(self):
        self.requires("const screenshots=['scalar-product.png','scalar-document.png','scalar-invalid.png','scalar-independent.png']",
                      "await hasDateEditor('Available since')", "await hasDateEditor('Order date and time')",
                      "await hasDateEditor('DeliveryDate, row 1')", "'date_not_editable'", "'evidence_input_offscreen'",
                      "await captureEvidence(screenshots[0],['Unit price','Available since'])",
                      "await captureEvidence(screenshots[1],['Order date and time','DeliveryDate, row 1','DeliveryDate, row 2'])",
                      "await captureEvidence(screenshots[2],['Order date and time','DeliveryDate, row 1'])",
                      "await captureEvidence(screenshots[3],['Note'])")
        self.assertNotIn('page.setContent', self.source)
        self.assertNotIn('page.addInitScript', self.source)

    def test_evidence_scrolls_real_inputs_and_keeps_failed_capture_without_claiming_pass(self):
        helper = self.source.split('const captureEvidence=async(name,labels)=>{', 1)[1].split('const blockedIntents=', 1)[0]
        self.assertIn('for(const label of labels)await field(label).scrollIntoViewIfNeeded()', helper)
        anchor = "field(labels[0]).evaluate(input=>input.scrollIntoView({block:'start',inline:'nearest',behavior:'instant'}))"
        self.assertIn(anchor, helper)
        self.assertLess(helper.index('scrollIntoViewIfNeeded()'), helper.index(anchor))
        self.assertLess(helper.index(anchor), helper.index('await screenshot(name)'))
        self.assertLess(helper.index('await screenshot(name)'), helper.index('await visibleInShot(labels)'))
        for forbidden in ('catch', '.focus(', '.fill(', '.click(', '.style', 'setViewportSize', 'fullPage:', 'clip:'):
            self.assertNotIn(forbidden, helper)
        self.assertIn("async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}", self.source)

    def test_evidence_rejects_viewport_and_nested_scrollport_clipping(self):
        helper = self.source.split('const visibleInShot=async labels=>{', 1)[1].split('const captureEvidence=', 1)[0]
        for required in ('const viewport=page.viewportSize()', 'box.width>0&&box.height>0',
                         'box.x+box.width<=viewport.width&&box.y+box.height<=viewport.height',
                         "['auto','scroll','hidden','clip'].includes(value)",
                         'parent=input.parentElement;parent;parent=parent.parentElement',
                         'bounds.left+parent.clientLeft', 'bounds.top+parent.clientTop',
                         'rect.left<left||rect.right>left+parent.clientWidth',
                         'rect.top<top||rect.bottom>top+parent.clientHeight',
                         "assert.equal(unclipped,true,'evidence_input_clipped')"):
            self.assertIn(required, helper)
        self.assertNotIn('report.', helper)
        self.assertNotIn('1440', helper)
        self.assertNotIn('1100', helper)

    def test_step_diagnostics_allowlist_codes_and_distinguish_reopen_from_evidence(self):
        helper = self.source.split('function stepFailureCode(error){', 1)[1].split('// Only fixed labels', 1)[0]
        fixed = re.findall(r"'([^']+)'", helper.split('const fixed=[', 1)[1].split('];', 1)[0])
        self.assertEqual(fixed, ['ordinary_host_exit_timeout', 'ordinary_host_exit_failed', 'owned_group_cleanup_unverified',
            'independent_typed_readback', 'catalog_rpc_plan', 'restart_rpc_plan', 'invalid_draft_rpc_plan', 'total_rpc_plan',
            'evidence_input_offscreen', 'evidence_input_clipped', 'evidence_viewport_missing',
            'reopened_checkbox_changed', 'reference_not_typed', 'reopened_lines_missing',
            'reopened_product_column_missing', 'reopened_product_not_typed', 'save_reply_not_saved'])
        self.assertIn("fixed.find(code=>message===code||message.startsWith(code+'\\n'))", helper)
        self.assertNotIn('return message', helper)
        self.requires('report.failure={phase,code:stepFailureCode(error)', "phase='document_write'",
                      "phase='document_close_saved'", "phase='independent_typed_datetime_audit'",
                      "phase='document_restart'", "phase='document_reopen_catalog'", "phase='document_reopen_header'",
                      "phase='document_reopen_line_dates'", "phase='document_reopen_quantities'",
                      "phase='document_reopen_references'", "phase='document_reopen_reference_snapshots'",
                      "phase='document_reopen_evidence'", "phase='document_restart_rpc_count'")

    def test_response_wait_covers_click_and_real_fetch_without_extending_global_budget(self):
        self.requires('const rpcFetchMs=35000,rpcReplyMs=rpcFetchMs+10000+5000',
                      'route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0})',
                      'predicate(response.request().postDataJSON()),{timeout:remaining(rpcReplyMs)})',
                      'context.setDefaultTimeout(10000)', 'startedAt+220000', 'startedAt+240000')
        attachment = self.source.split("if(new URL(target).pathname==='/attachment'){", 1)[1].split(
            "if(new URL(target).pathname==='/rpc'){", 1)[0]
        self.assertIn('route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0})', attachment)
        transport = (ROOT / 'frontend/form/src/attachment.mjs').read_text(encoding='utf-8')
        self.assertIn('setTimeout(() => controller.abort(), 35000)', transport)
        helper = self.source.split('const save=async(name,control,status)=>{', 1)[1].split('const saveProduct=', 1)[0]
        self.assertLess(helper.index('const reply=replyFor'), helper.index('await action(name).click()'))
        self.assertLess(helper.index('reply.catch(()=>{})'), helper.index('await action(name).click()'))
        self.assertEqual(helper.count('await action(name).click()'), 1)
        self.assertEqual(helper.count('await reply'), 1)
        self.assertIn("await value(status,'saved')", helper)

    def test_save_receipt_flags_and_status_are_closed_and_do_not_infer_success_from_admission(self):
        self.requires("packet.params.session===save.session&&packet.params.request.method==='form.event'",
                      "packet.params.request.params.event==='command'&&packet.params.request.params.control===save.control",
                      "requestAdmitted:false,bodyAccepted:false,deliveryCompleted:false,responseMatched:false,status:'not_received'",
                      "if(!matchesSave(packet,saving))return false", 'diagnostic.responseMatched=true;return true',
                      'saving.diagnostic.status=diagnosticSaveStatus(result.result)',
                      "assert.equal(diagnostic.status,'saved','save_reply_not_saved')")
        status = self.source.split('function diagnosticSaveStatus(result){', 1)[1].split('const exactKeys=', 1)[0]
        self.assertIn("const items=result.form?.result?.state?.items", status)
        self.assertIn("items.find(item=>item?.name==='StatusLabel')", status)
        self.assertIn("['saved','unchanged','rejected','uncertain','committed']", status)
        self.assertIn(".find(allowed=>allowed===value.value)??'other':'other'", status)
        self.assertNotIn('return value', status.replace("return value?.type==='String'?", ''))
        rpc = self.source.split("if(new URL(target).pathname==='/rpc'){", 1)[1].split('page=await context.newPage()', 1)[0]
        self.assertLess(rpc.index('requestAdmitted=true'), rpc.index('await route.fetch'))
        self.assertLess(rpc.index('checkReply(result,packet,stage)'), rpc.index('bodyAccepted=true'))
        self.assertLess(rpc.index('bodyAccepted=true'), rpc.index('await route.fulfill({response})'))
        self.assertLess(rpc.index('await route.fulfill({response})'), rpc.index('deliveryCompleted=true'))
        helper = self.source.split('const save=async(name,control,status)=>{', 1)[1].split('const saveProduct=', 1)[0]
        self.assertEqual(set(re.findall(r"stage[:=]'([^']+)'", helper)),
                         {'click_command', 'await_response', 'await_saved_field', 'await_idle', 'complete'})

    def test_natural_exit_and_verified_cleanup_precede_final_artifacts(self):
        close = self.source.split('const ordinaryShutdown=async()=>{', 1)[1].split('const referenceValue=', 1)[0]
        for forbidden in ('signalGroup', 'stopHost('):
            self.assertNotIn(forbidden, close)
        self.requires("host.exitCode,0,'ordinary_host_exit_failed'", 'await groupGone(hostGroup);host=null;hostGroup=null',
                      "signalGroup(browserGroup,'SIGKILL');await groupGone(browserGroup)",
                      "'owned_directory_cleanup_unverified'", "await lstat(owned);throw Error('owned_directory_remains')")
        self.assertLess(self.source.index('await stopHost();}catch'), self.source.index('rm(owned,{recursive:true'))
        self.assertLess(self.source.index('rm(owned,{recursive:true'), self.source.index("writeFile(path.join(output,'result.json')"))

    def test_artifacts_are_allowlisted_hashed_bounded_and_diagnostics_are_not_payloads(self):
        self.requires("const artifacts=['result.json','manifest.json',...screenshots]", 'stat.size<=4*1024*1024',
                      "'screenshot_not_png'", 'sha256:sha256(bytes)', 'resultSha256:sha256(raw)',
                      "'unexpected_artifact'", 'Buffer.byteLength(raw)<=65536', "{flag:'wx'}",
                      "session:['yadinassi.browser.resume/1']", "'capability_leak'", "'browser_cookies_not_empty'")
        for forbidden in ('report.url', 'report.headers', 'report.response', 'report.stack', 'report.appState',
                          'tracing.start', 'recordHar', 'recordVideo', 'console.error'):
            self.assertNotIn(forbidden, self.source)
        self.assertEqual(self.source.count('console.log('), 1)
        stages = set(re.findall(r"(?:wireStage=|stage\()'([^']+)'", self.source))
        self.assertEqual(stages, {'attachment_request', 'attachment_fetch', 'attachment_budget', 'attachment_json',
            'attachment_status', 'attachment_schema', 'attachment_delivery', 'request_schema', 'rpc_fetch',
            'http_status', 'reply_budget', 'reply_json', 'held_write', 'reply_envelope', 'reference_descriptor',
            'reference_value', 'scalar_descriptor', 'scalar_value', 'delivery'})

    def test_exact_ninth_route_preserves_all_previous_routes_pins_and_artifact_lists(self):
        trigger = self.workflow.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip()
        self.assertEqual(trigger, 'push:\n    branches: [' + ', '.join('codex/' + route + '-browser-reviewed' for route in ROUTES) + ']')
        step = self.step('Acquire four typed scalar flows with Chromium sandbox enabled')
        for value in ("if: github.ref == 'refs/heads/codex/scalar-editor-browser-reviewed'", 'timeout-minutes: 5',
                      'QA_SOURCE_SHA: ${{ github.sha }}', 'run: node tests/browser_ui/scalar_editor_browser_qa.mjs'):
            self.assertIn(value, step)
        self.assertEqual(re.findall(r'uses: (\S+)', self.workflow), [
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
            'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
            *['actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'] * 9])
        self.assertEqual(self.workflow.split('\npermissions:\n', 1)[1].split('\nconcurrency:', 1)[0].strip(), 'contents: read')
        upload = self.step('Publish only typed scalar screenshots and redacted source-bound report')
        paths = upload.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines()], [
            '${{ runner.temp }}/yadinassi-scalar-editor-browser-artifacts/' + name for name in
            ['result.json', 'manifest.json', 'scalar-product.png', 'scalar-document.png', 'scalar-invalid.png', 'scalar-independent.png']])
        self.assertIn('if-no-files-found: error\n          retention-days: 14', upload)
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'secrets.', 'sudo ', 'sysctl ', '--with-deps'):
            self.assertNotIn(forbidden, self.workflow)

    def test_legacy_reference_descriptor_compatibility_remains_strict_for_scoped_values(self):
        source = (ROOT / 'tests/browser_ui/configuration_reference_browser_qa.mjs').read_text(encoding='utf-8')
        self.assertIn("exactKeys(value,'name title type readOnly'+(Object.hasOwn(value,'editor')?' editor':''))", source)
        self.assertIn("if(Object.hasOwn(value,'editor'))checkEditor(value.editor,value.type)", source)
        for required in ("exactKeys(editor,'kind parts')", "exactKeys(editor,'kind digits scale nonnegative')",
                         'count(editor.digits,128)&&count(editor.scale,editor.digits)',
                         "assert.equal(type,'String','editor_scalar_type')", "exactKeys(editor,'kind length fixed')",
                         'count(editor.length,65536)', "exactKeys(value,'type scope target key text')"):
            self.assertIn(required, source)
        self.assertNotIn("Object.hasOwn(value,'scope')", source)
        self.assertIn('const plannedRPC=[20,23,14,10]', source)

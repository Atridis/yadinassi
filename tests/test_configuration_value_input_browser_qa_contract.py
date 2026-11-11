"""Static browser-source contracts only, never browser or application execution."""
import ast
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]


class ValueInputBrowserContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=(ROOT/'tests/browser_ui/configuration_value_input_browser_qa.mjs').read_text(encoding='utf-8')
        cls.w=(ROOT/'.github/workflows/configuration-value-input-browser-qa.yml').read_text(encoding='utf-8')

    def contains(self,*items):
        for item in items:self.assertIn(item,self.s)

    def test_four_scenarios_exact_twenty_five_business_requests(self):
        plan=ast.literal_eval(self.s.split('const businessPlan=',1)[1].split(';',1)[0])
        self.assertEqual(list(map(len,plan)),[8,6,9,2]);self.assertEqual(sum(map(len,plan)),25)
        self.assertEqual(self.s.count('await scenario(scenarioNames['),4)
        self.contains('businessEvents.slice(start),businessPlan[index]')

    def test_real_example_and_commands(self):
        xml=(ROOT/'examples/configuration-value-input/CommonForms/Welcome/Ext/Form.xml').read_text(encoding='utf-8')
        for name in ('QuestionButton','WarningButton','ReasonButton','PriorityButton','GreetingLabel','CountLabel'):self.assertIn(name,xml)
        self.contains("ask('Enter quantity','QuestionButton')","ask('Enter date','WarningButton')","ask('Enter reason','ReasonButton')","ask('Choose priority','PriorityButton')")

    def test_closed_reviewed_workflow(self):
        self.assertIn('branches: [codex/configuration-value-input-browser-reviewed]',self.w)
        self.assertIn('cancel-in-progress: false',self.w);self.assertIn('persist-credentials: false',self.w)
        for bad in ('pull_request:','workflow_dispatch:','schedule:','secrets.','sudo ','sysctl ','--no-sandbox'):self.assertNotIn(bad,self.w)

    def test_pinned_dependencies(self):
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}',self.w)),3)
        self.contains("report.versions.playwright,'1.64.1'")
        self.assertIn('install chromium --no-shell',self.w);self.assertNotIn('--with-deps',self.w)

    def test_sandbox_and_owned_cleanup(self):
        self.contains('process.getuid()===0','chromiumSandbox:true',"probe.goto('chrome://sandbox')",'sandboxCommand(args)','await groupGone(hostGroup)','await groupGone(browserGroup)')
        for bad in ('--no-sandbox','chromiumSandbox:false','executablePath:','ignoreDefaultArgs:'):self.assertNotIn(bad,self.s)

    def test_caps_deadlines_and_no_retries(self):
        self.contains('startedAt+220000','startedAt+240000','if(rpc>=96)','attachmentRequests<=96','maxRetries:0','maxRedirects:0')
        self.assertNotIn('page.waitForTimeout(',self.s)

    def test_source_binding_and_supported_cli(self):
        self.contains("'examples/configuration-value-input'),'--application-host','--browser-session'","'frontend/form'","'frontend/configuration'","'tests/test_form_value_input.py'","'source_binding_changed'","'tracked_checkout_dirty'")
        self.assertNotIn('call_routine(',self.s)

    def test_separate_negotiated_input_envelope(self):
        self.contains("exactKeys(packet.params,'protocol dialogCapability inputCapability')","'yadinassi-owned-input/1'","result.inputs.length<=8","'ticket owner kind title text value editor'","'ticket owner kind title choices initial'")

    def test_exact_scalar_shapes_and_opaque_choice_binding(self):
        self.contains("exactKeys(value,'type ticks')","exactKeys(value,'type value')","exactKeys(row,'choice value presentation')","'opaque_choice_binding'","'input_scalar_type'","'choice_initial_binding'")
        self.assertNotIn('Number(packet.params.value.value)',self.s)

    def test_invalid_draft_empty_and_cancel_are_distinct(self):
        self.contains("inputValue().fill('not a number')","'invalid_local_input_sent'","inputValue().fill('first line\\nmust not submit')","'Reason cancelled',2,'15,125'","'Reason confirmed',4,''")

        self.contains("'untouched_crlf_wire_changed'","completion(untouched,'Reason confirmed',3,'Draft\\r\\nreason')")

    def test_real_held_response_and_repeat_click_fencing(self):
        self.contains('observedCommands.set(packet.id,{packet,actual})',"await repeatClick(answerButton('OK'))",'control.click();control.click();','gate.arrived();await bounded(gate.wait',"'answer_applied_before_delivery'")
        for bad in ('route.fulfill({body:','route.fulfill({json:','await response.json()'):self.assertNotIn(bad,self.s)

    def test_date_ticks_and_original_item_evidence(self):
        self.contains("ticks:'638425299060000'","ticks:'638848805500000'","'date_timezone_conversion'","descriptor.choices[1].choice","'Original second item: Да'")
        self.assertNotIn('new Date(',self.s)
        self.contains('3155378975990000n','10,000 ticks/second')
        self.contains("timezoneId:'Pacific/Auckland'")

    def test_sibling_authoritative_and_raw_drafts_retained(self):
        self.contains("commitInput('Owner draft','Authoritative sibling')","'  independent raw draft  '","'navigation_flushed_sibling'","'retained_input_replaced'","'sibling_received_callback'")
        self.assertNotIn('node.value=',self.s)

    def test_escape_and_retired_control_cannot_retarget(self):
        self.contains("page.keyboard.press('Escape')","'Reason cancelled',8,'urgent'",'await retired.evaluate(n=>{n.click();n.click();})',"'retired_control_retargeted'","'retired_control_changed_owner'")

    def test_real_reply_loss_not_fabricated_callback(self):
        self.contains("dropNextAnswer&&packet.method==='application.answerInput'","completion(actual.result,'Quantity confirmed',1,'77,125')","return await route.abort('failed')")
        self.assertEqual(self.s.count('dropNextAnswer=true'),1)

    def test_copy_only_raw_input_and_no_blind_retry(self):
        self.contains("inputValue().inputValue(),'77.125'","'locked_input_editable'","'copy_input_disabled'","page.keyboard.press('ControlOrMeta+A')","'locked_answer_enabled'","'locked_intent_replayed'")
        self.assertNotIn('selectText()',self.s)
        self.contains("locator('[data-value-input=\"scalar\"]')")

    def test_natural_shutdown_and_honest_limits(self):
        self.assertEqual(self.s.count('await naturalStop();'),1)
        self.contains('{code:0,signal:null}','nativeDialogParity:false','nativeKeyboardParity:false','durableCallbackRecovery:false')

    def test_redacted_bounded_artifacts(self):
        names=[line.strip().rsplit('/',1)[-1] for line in self.w.splitlines() if 'yadinassi-value-input-browser-artifacts/' in line]
        self.assertEqual(names,['result.json','manifest.json','input-completion.png','input-date-choice.png','input-retained.png','input-locked-copy.png'])
        self.contains("'capability_leak'","'only_resume_storage'",'resultSha256:sha256(raw)',"'input_date_choice'")
        for bad in ('report.url','report.headers','report.response','report.stack','console.log(error','recordHar'):self.assertNotIn(bad,self.s)

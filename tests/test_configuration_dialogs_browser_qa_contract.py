"""Source-only browser contracts. No browser, application or native execution."""
import ast
import re
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class DialogBrowserContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=(ROOT/'tests/browser_ui/configuration_dialogs_browser_qa.mjs').read_text(encoding='utf-8')
        cls.w=(ROOT/'.github/workflows/configuration-dialogs-browser-qa.yml').read_text(encoding='utf-8')
    def contains(self,*items):
        for item in items:self.assertIn(item,self.s)
    def test_four_scenarios_exact_seventeen_business_requests(self):
        plan=ast.literal_eval(self.s.split('const businessPlan=',1)[1].split(';',1)[0])
        self.assertEqual(list(map(len,plan)),[2,6,6,3]);self.assertEqual(sum(map(len,plan)),17)
        self.assertEqual(self.s.count('await scenario(scenarioNames['),4)
        self.contains('businessEvents.slice(start),businessPlan[index]')
    def test_example_commands_are_actual_names(self):
        xml=(ROOT/'examples/configuration-dialogs/CommonForms/Welcome/Ext/Form.xml').read_text(encoding='utf-8')
        for name in ('QuestionButton','WarningButton','GreetingLabel','AnswerLabel','CountLabel'):self.assertIn(name,xml)
        self.contains("command('Ask confirmation','QuestionButton')","command('Show warning','WarningButton')")
    def test_closed_workflow(self):
        self.assertIn('branches: [codex/configuration-dialogs-browser-reviewed]',self.w)
        for bad in ('pull_request:','workflow_dispatch:','schedule:','secrets.','sudo ','sysctl ','--no-sandbox'):self.assertNotIn(bad,self.w)
        self.assertIn('persist-credentials: false',self.w);self.assertIn('cancel-in-progress: false',self.w)
    def test_pinned_actions_and_browser(self):
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}',self.w)),3)
        self.contains("report.versions.playwright,'1.64.1'")
        self.assertIn('install chromium --no-shell',self.w);self.assertNotIn('--with-deps',self.w)
    def test_sandbox_and_owned_process_cleanup(self):
        self.contains('process.getuid()===0','chromiumSandbox:true',"probe.goto('chrome://sandbox')",'sandboxCommand(args)','await groupGone(hostGroup)','await groupGone(browserGroup)')
        for bad in ('--no-sandbox','chromiumSandbox:false','executablePath:','ignoreDefaultArgs:'):self.assertNotIn(bad,self.s)
    def test_deadlines_caps_no_retries(self):
        self.contains('startedAt+220000','startedAt+240000','if(rpc>=96)','attachmentRequests<=96','maxRetries:0','maxRedirects:0')
        self.assertNotIn('page.waitForTimeout(',self.s)
    def test_source_binding_and_launcher(self):
        self.contains("'examples/configuration-dialogs'),'--application-host','--browser-session'","'frontend/form'","'frontend/configuration'","'tests/configuration_dialog_fixture.py'","'source_binding_changed'","'tracked_checkout_dirty'")
        self.assertNotIn('call_routine(',self.s)
    def test_descriptor_and_answer_binding(self):
        self.contains("exactKeys(dialog,'ticket owner kind title text choices')","exactKeys(packet.params,'session ticket answer')","'answer_descriptor_binding'","'dialog_owner_missing'",'owners.has(item.id)')
    def test_completion_snapshot_not_update_child(self):
        self.contains("assert.deepEqual(result.updates,[],'answer_updates')","result.form.result.state","'completion_total'","Additional parameters shared: Да")
    def test_real_reply_held_and_double_click(self):
        self.contains('observedCommands.set(packet.id,{packet,actual})',"await repeatClick(answerButton('Yes'))",'control.click();control.click();','gate.arrived();await bounded(gate.wait',"'answer_applied_before_delivery'")
        self.assertNotIn('await response.json()',self.s)
        self.assertNotIn('route.fulfill({body:',self.s);self.assertNotIn('route.fulfill({json:',self.s)
    def test_no_cancel_warning_escape(self):
        self.contains("answer('No','no')","answer('Cancel','cancel')","answer('Continue','dismiss')","page.keyboard.press('Escape')","'escape_sent_answer'")
    def test_retained_independent_draft(self):
        self.contains("'  independent raw draft  '","'retained_input_replaced'","'navigation_flushed_sibling'","'sibling_received_callback'","await action('Refresh state').click();await refreshed")
        self.assertNotIn('node.value=',self.s)
    def test_real_confirmed_answer_drop(self):
        self.contains("dropNextAnswer&&packet.method==='application.answerDialog'","completion(actual.result,'Yes',1)",'report.confirmedAnswerBeforeLoss={ownerUpdated:true,completionCount:1}',"return await route.abort('failed')")
        self.assertEqual(self.s.count('dropNextAnswer=true'),1)
    def test_locked_copy_and_no_replay(self):
        self.contains("'GreetingLabel:   raw copy after loss  '",'getComputedStyle(n).userSelect',"'locked_input_enabled'","'locked_intent_replayed'")
    def test_natural_exit_and_explicit_parity_limits(self):
        self.assertEqual(self.s.count('await naturalStop();'),1)
        self.contains('{code:0,signal:null}','nativeDialogParity:false','nativeKeyboardParity:false','durableCallbackRecovery:false')
    def test_exact_artifacts_and_redaction(self):
        paths=[line.strip().rsplit('/',1)[-1] for line in self.w.splitlines() if 'yadinassi-dialogs-browser-artifacts/' in line]
        self.assertEqual(paths,['result.json','manifest.json','dialogs-completion.png','dialogs-refusal.png','dialogs-retained.png','dialogs-locked-copy.png'])
        self.contains("'capability_leak'","'only_resume_storage'",'resultSha256:sha256(raw)')
        for bad in ('report.url','report.headers','report.response','report.stack','console.log(error','recordHar'):self.assertNotIn(bad,self.s)

from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ValueInputAcquisitionWorkflowTests(unittest.TestCase):
    def source(self):
        return (ROOT/'.github/workflows/native-1c-value-inputs.yml').read_text(encoding='utf-8')

    def test_exact_owner_and_branch_before_credentials(self):
        text=self.source()
        for token in ("github.repository == 'Atridis/yadinassi'", "github.repository_id == '359770628'", "github.repository_owner_id == '30860798'", "github.actor_id == '30860798'", "github.triggering_actor == 'Atridis'", "github.event.pull_request.head.ref == 'codex/configuration-value-input'"):
            self.assertIn(token,text)
        self.assertLess(text.index('native_1c_ci_policy.py bind'),text.index('GHCR_TOKEN:'))
        self.assertNotIn('pull_request_target',text)

    def test_pinned_actions_readonly_permissions_and_no_dispatch_inputs(self):
        text=self.source()
        self.assertEqual(len(re.findall(r'uses: [^\n]+@[0-9a-f]{40}',text)),4)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('contents: read',text);self.assertIn('packages: read',text)
        self.assertIn("NATIVE_DISPATCH_INPUTS: '{}'",text)
        self.assertNotIn('workflow_dispatch',text)

    def test_only_validated_bounded_output_names_export(self):
        text=self.source()
        self.assertIn("steps.results.outputs.value_inputs_outputs_ready == 'true'",text)
        self.assertIn('native-smoke/value_inputs-outputs/value_inputs.out',text)
        self.assertIn('native-smoke/value_inputs-outputs/provenance.json',text)
        self.assertNotIn('path: .',text)

    def test_packet_and_controller_have_explicit_lf_policy(self):
        attrs=(ROOT/'.gitattributes').read_text(encoding='utf-8').splitlines()
        paths=[p.relative_to(ROOT).as_posix() for p in (ROOT/'scripts/value_input_packet').rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.bsl')]
        paths+=['scripts/native_1c_bootstrap/value_input_controller.py','scripts/native_1c_bootstrap/run_value_inputs_stage.py','scripts/native_1c_value_inputs_probe.sh']
        for name in paths:self.assertIn(name+' text eol=lf',attrs)

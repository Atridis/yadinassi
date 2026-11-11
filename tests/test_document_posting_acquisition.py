"""No native execution: source/transport/isolation contract checks only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from document_posting_behavior import fixture,route
import native_1c_document_posting_profile as host

class PostingAcquisitionTests(unittest.TestCase):
    def wire(self):
        prefix='POST|'+'a'*32+'|'
        return (prefix+'entered\n'+''.join(prefix+str(n)+'|0|0|0,0|before:0;\n' for n in range(1,13))+prefix+'completed\n').encode()
    def test_exact_twelve_observations(self):
        values=route.parse_wire(self.wire(),'a'*32)
        self.assertEqual(len(values),12)
        self.assertEqual(json.loads(route.canonical(values)),values)
    def test_wrong_nonce_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire(),'b'*32)
    def test_reordered_case_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire().replace(b'|2|0|',b'|3|0|'),'a'*32)
    def test_unbounded_observation_refused(self):
        with self.assertRaises(ValueError):route.canonical(['x'*513]*12)
    def test_extra_output_refused(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire()+b'noise\n','a'*32)
    def test_source_fixture_hashes(self):
        setup,assets=fixture.load_saved()
        self.assertEqual(assets['generated/observe.bsl'],route.source())
        self.assertIn(b'RecorderSubordinate',assets['InformationRegister.xml'])
    def test_distinct_staged_route_and_readonly_isolation(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            destination=Path(directory)/'inputs'
            hashes=host.stage_inputs(ROOT,destination,host.SMOKE)
            command=host.container_command(destination,hashes,'onec-document-posting-'+'a'*32,'a'*32,host.SMOKE)
            self.assertIn('--document-posting-suite',command)
            self.assertNotIn('--catalog-object-suite',command)
            self.assertIn('--read-only',command)
            self.assertEqual(command[command.index('--network')+1],'none')
    def test_no_runtime_parity_comparison(self):
        source=(ROOT/'scripts/native_1c_document_posting_profile.py').read_text()
        self.assertIn("'runtime_parity_accepted':False",source)
        self.assertIn('comparison=None',source)
    def test_only_new_workflow_and_closed_branch(self):
        workflow=(ROOT/'.github/workflows/native-1c-document-posting.yml').read_text()
        self.assertIn("head.ref == 'codex/document-posting-movements'",workflow)
        self.assertNotIn('pull_request_target',workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('native_1c_ci_policy.py bind',workflow)

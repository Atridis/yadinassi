"""Replays the immutable native packet, not a replacement native producer."""
import hashlib
import json
from pathlib import Path
import unittest
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT/'tests/fixtures/native_dom_xpath_43093418847.json').read_text())
SOURCE = (ROOT/'scripts/dom_xpath_behavior/observe.bsl').read_bytes()
DEFINITIONS = SOURCE.decode().split('For CaseNo = 1 To 12 Do')[0]

class NativeXPathReplay(unittest.TestCase):
    def test_immutable_source_and_evidence(self):
        self.assertEqual(hashlib.sha256(SOURCE).hexdigest(), FIXTURE['source_sha256'])
        raw = (json.dumps(FIXTURE['observations'], separators=(',', ':'))+'\n').encode('ascii')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FIXTURE['output_sha256'])
        self.assertEqual(len(raw), FIXTURE['output_size'])
        self.assertEqual(FIXTURE['run_id'], 43093418847)
        self.assertEqual(len(FIXTURE['observations']), 12)


def replay(index):
    def test(self):
        out = []; vm = Interpreter(out.append)
        vm.execute(DEFINITIONS+'\nStage=""; Message(ObserveCase('+str(index)+',Stage));')
        self.assertEqual(out, [FIXTURE['observations'][index-1]])
    return test

for index in range(1, 13):
    setattr(NativeXPathReplay, 'test_native_case_%02d' % index, replay(index))

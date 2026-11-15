"""Exact source replay of the bounded UUID native16 packet, not general parity."""
import hashlib
import json
from pathlib import Path
import unittest
from yadinassi import Interpreter
from scripts.uuid_typed_pipeline_behavior import route
ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'tests/fixtures/native_uuid_typed_pipeline_43270339666.json'

class NativeUUIDTypedPipelineReplay(unittest.TestCase):
    def test_source_and_evidence_binding(self):
        raw=NATIVE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'043951620d954acd805284d3699b8a9770996822ac1db788353108dbe3648255')
        evidence=json.loads(raw)
        self.assertEqual(evidence['run_id'],43270339666)
        self.assertEqual(evidence['head_sha'],'799a37915133f9cb623ce3503977d726acb85479')
        self.assertEqual(evidence['source_sha256'],hashlib.sha256(route.source()).hexdigest())
        output=route.canonical(evidence['observations'])
        self.assertEqual(len(output),evidence['output_size'])
        self.assertEqual(hashlib.sha256(output).hexdigest(),evidence['output_sha256'])
        self.assertEqual(len(evidence['observations']),16)

def case(number):
    def test(self):
        source=route.source().decode('utf-8')
        declarations=source.split('For CaseNo = 1 To 16 Do')[0]
        vm=Interpreter(lambda _:None)
        vm.execute(declarations)
        actual=vm.execute(f'Stage="setup"; ObserveCase({number},Stage)')
        expected=json.loads(NATIVE.read_bytes())['observations'][number-1]
        self.assertEqual(actual,expected)
    return test
for number in range(1,17):
    setattr(NativeUUIDTypedPipelineReplay,f'test_native_{number:02d}',case(number))

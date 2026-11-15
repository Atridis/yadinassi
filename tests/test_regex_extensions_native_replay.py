"""Replay the exact twelve observed regex cases, not invented expected values."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from regex_extensions_behavior import route
FIXTURE=ROOT/'tests/fixtures/native_regex_extensions_43178980355.json'

class NativeRegexExtensionsReplay(unittest.TestCase):
    def test_source_binding(self):
        value=json.loads(FIXTURE.read_bytes());summary=value['summary'];stage=summary['native_report']['stage3']
        self.assertEqual(value['run_id'],43178980355)
        self.assertEqual(value['head_sha'],'e672db45da464dc7cd3789a5e6f063d33aa7360c')
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(),stage['source_sha256'])
        raw=route.canonical(value['observations'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),stage['output_sha256'])
        self.assertEqual(len(raw),stage['output_size'])
        self.assertEqual(value['observations'],[v for _,v in stage['partial_observations']])
        self.assertEqual(stage['record_count'],12)
        self.assertTrue(summary['native_measurement_accepted'])
        self.assertFalse(summary['runtime_parity_accepted'])

def case(number):
    def test(self):
        source=route.source().decode('utf-8-sig')
        declarations=source[:source.index('For CaseNo = 1 To 12 Do')]
        vm=Interpreter(lambda value:None);self.addCleanup(vm.close)
        program=declarations+'\nStage="read";ObserveCase('+str(number)+',Stage)'
        expected=json.loads(FIXTURE.read_bytes())['observations'][number-1]
        if number == 7:
            # The measured native no-match is retained. This composition is
            # deliberately refused, not represented as matching native output.
            self.assertEqual(expected, ':0:0')
            with self.assertRaisesRegex(BSLError,'lookahead'):
                vm.execute(program)
        else:
            self.assertEqual(vm.execute(program),expected)
    return test
for number in range(1,13):setattr(NativeRegexExtensionsReplay,('test_native_%02d'%number)+('_host_closed_capture_escape' if number==7 else ''),case(number))

"""Authenticated 32-case native observations; measurement mismatch, not runtime acceptance.

Linux 1C 8.3.27.1508 run 40734394630 attempt 1 on b5637894a3758de5f691f1ef3eafe94ef66cc3bb.
The finite literal below is captured native output, not generated expected behavior.
"""
import hashlib
from pathlib import Path
import unittest
from unittest import mock
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.value_trees import BSLValueTreeRowCollection
from scripts.native_1c_tree_move_contract import validate_payload

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'a0212150d3d5d2a7252971aa8ba509d439ced04e85b5a157ff1148bf3eff4574'
CAPTURE = {'run':40734394630, 'attempt':1,
           'head':'b5637894a3758de5f691f1ef3eafe94ef66cc3bb',
           'tree':'dad89282b854ed03d4d31b37cf3493423b182ca8',
           'status':'failed_host_comparison_not_runtime_acceptance'}
NATIVE_RECORD = b'TM: [11ACBDE1BACDE1ABCDE1BCADE1CABDE0ABCDE0ABCDE0ABCDE0ABCDE1BACDE1BACDE0ABCDE0ABCDE0ABCDE1ABCDE1ACBDE1ABCDE1BACDE0ABCDE1ACBDE1ACBDE0ABCDE1ACBDE1ACBDE0-----0A----1ABCED1ABCED0ABCDE0ABCDE0ABCDE0ABCDE]\n'
NATIVE_RECORD_SHA256 = '2c70541dc506b5ff148fec364ebd813c94502f14a846a15557522af2a7364fab'


def source():
    # CanonicalLF synthetic fixture only; production native bytes stay untouched.
    raw = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise AssertionError('native Move source changed')
    return raw.decode('utf-8-sig')


def helpers():
    text=source(); blocks=[]
    for name in ('LoadColumn','Move'):
        start=f'// Begin bounded ValueTree {name} helpers (measurement only; no native answers).\n'
        end=f'// End bounded ValueTree {name} helpers.\n'
        blocks.append(start+text.split(start,1)[1].split(end,1)[0]+end)
    return '\n'.join(blocks)


class NativeMoveTests(unittest.TestCase):
    def test_literal_integrity_and_complete32_grammar(self):
        self.assertEqual(hashlib.sha256(NATIVE_RECORD).hexdigest(), NATIVE_RECORD_SHA256)
        self.assertEqual(len(NATIVE_RECORD),200)
        observations=validate_payload(NATIVE_RECORD[5:-2])
        self.assertEqual(len(observations),32)
        self.assertEqual(observations[11],(12,b'0',b'ABCDE'))
        self.assertEqual(observations[16],(17,b'1',b'ABCDE'))
        self.assertEqual(observations[-1],(32,b'0',b'ABCDE'))

    def test_exact_native32_on_both_targets(self):
        for target in (None, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                output=[]; vm=Interpreter(output.append,**({} if target is None else {'native_target':target}))
                vm.execute(helpers()+'Message("TM: [" + TreeMoveObservations() + "]");')
                self.assertEqual(('\n'.join(output)+'\n').encode(),NATIVE_RECORD)

    def test_all_prior1021_messages_unchanged_on_both_targets(self):
        original=BSLValueTreeRowCollection.get_method
        def missing(receiver,name):
            if name.casefold() in ('move','сдвинуть'):
                raise ValueError('synthetic old missing method')
            return original(receiver,name)
        for target in (None, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                outputs=[]
                for old in (True,False):
                    result=[];vm=Interpreter(result.append,**({} if target is None else {'native_target':target}))
                    if old:
                        with mock.patch.object(BSLValueTreeRowCollection,'get_method',missing): vm.execute(source())
                    else: vm.execute(source())
                    outputs.append(result)
                self.assertEqual(len(outputs[0]),1022);self.assertEqual(len(outputs[1]),1022)
                self.assertEqual(outputs[0][:1021],outputs[1][:1021])
                self.assertEqual((outputs[1][-1]+'\n').encode(),NATIVE_RECORD)

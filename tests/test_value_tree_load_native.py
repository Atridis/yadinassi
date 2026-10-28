"""Authenticated native45 LoadColumn observations; failed measurement run, not CI acceptance.

Linux 1C 8.3.27.1508 run40689638260 on d5c795e70d2d5afe5b97a9855b06983223ed01a0.
Literal finite output below is native evidence, not generated expected behavior.
"""
import hashlib
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from scripts.native_1c_tree_load_contract import validate_records

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'ca23e52041022f2085c6cb7d4393a84834e75c69856c756b92e8531ad35c7c3e'
NATIVE_COLLECTIONS_SHA256 = '30f5f24d1c807814c3ba5fe19ed0396f04630b1f42ff6715ed6018bb006fcefd'
CAPTURE = {'run': 40689638260, 'attempt': 1,
           'head': 'd5c795e70d2d5afe5b97a9855b06983223ed01a0',
           'tree': 'c1290b5c4ab5d9bcc5f6fedde96de2fb03acba47',
           'status': 'failed_host_comparison_not_runtime_acceptance'}
NATIVE_TAIL_SHA256 = '1d78e9e267d3b5c10109aed319dd1f386c3f42d92db4193dd05dc85bec80c7f6'
OBSERVATIONS = ('TL01: [1000--BB6_b_c_e_7_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL02: [1100--BB6_b_c_e_7_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL03: [1200--BB1_b_c_e_2_b_d_e_3_b_c_e_6_b_c_e_7_b_d_e_6_b_d_e_A126_7_..]\n', 'TL04: [1300--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL05: [1400--EE................................................A126_7_..]\n', 'TL06: [1510--NN................................................A126_7_..]\n', 'TL07: [1600--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A10......]\n', 'TL08: [1700--BB6_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A116_....]\n', 'TL09: [1800--BB6_b_c_e_7_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A136_7_5_]\n', 'TL10: [1910--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_F126_7_..]\n', 'TL11: [1A00--BB6_b_c_e_7_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL12: [1B00--BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL13: [1C00--BB6_b_c_e_7_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL14: [1D00--BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL15: [1E00--BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL16: [1F00--BB6_b_c_e_7_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL17: [1G00--BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL18: [1H10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL19: [1I10--EE................................................A126_7_..]\n', 'TL20: [1J10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A10......]\n', 'TL21: [1K10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL22: [1L10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL23: [1M10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL24: [1N10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL25: [1O10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL26: [1P10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_S01h_....]\n', 'TL27: [1Q10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_N017_....]\n', 'TL28: [1R10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_U01U_....]\n', 'TL29: [1S10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_L01L_....]\n', 'TL30: [1T10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_R01P0....]\n', 'TL31: [1U10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL32: [1V10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL33: [1W10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL34: [1X10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n', 'TL35: [1Y00--BB1_1_c_e_2_T_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A121_T_..]\n', 'TL36: [1Z00--BB1_U_c_e_2_L_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A12U_L_..]\n', 'TL37: [1a01--BB1_P0c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A12P07_..|BB1_Q0c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A12Q07_..]\n', 'TL38: [1b01--BB1_P0c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A12P07_..|BB1_R0c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A12R07_..]\n', 'TL39: [1c01--BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..|BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A117_....]\n', 'TL40: [1d01--BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..|BB1_6_c_e_2_7_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A125_7_..]\n', 'TL41: [1e00--BB1_7_c_e_2_0_d_e_3_0_c_e_4_0_c_e_5_0_d_e_6_0_d_e_A127_h_..]\n', 'TL42: [1f00--BB1_0_c_e_2_7_d_e_3_0_c_e_4_0_c_e_5_0_d_e_6_0_d_e_A12h_7_..]\n', 'TL43: [1g00--BB1_7_c_e_2_0_d_e_3_0_c_e_4_0_c_e_5_0_d_e_6_0_d_e_A127_U_..]\n', 'TL44: [1h00--BB1_6_c_e_2_7_d_e_3_0_c_e_4_0_c_e_5_0_d_e_6_0_d_e_A136_7_h_]\n', 'TL45: [1i10--BB1_b_c_e_2_b_d_e_3_b_c_e_4_b_c_e_5_b_d_e_6_b_d_e_A126_7_..]\n')


def source():
    # Canonical source fixture only: production capture bytes are never normalized.
    raw = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n', b'\n')
    from scripts.native_historical_replay import without_tree_move_probes
    raw = without_tree_move_probes(raw.decode('utf-8-sig')).encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise AssertionError('Native measurement source changed')
    return raw.decode('utf-8-sig')


def fragments():
    text = source()
    def block(start, end):
        return start + text.split(start, 1)[1].split(end, 1)[0] + end
    return (block('// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\n',
                  '// End bounded ValueTree LoadColumn helpers.\n\n'),
            block('// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\n',
                  '// End bounded ValueTree LoadColumn observations.\n'))


class NativeLoadColumnTests(unittest.TestCase):
    def test_native_literal_integrity_and_strict_grammar(self):
        raw = ''.join(OBSERVATIONS).encode('ascii')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), NATIVE_TAIL_SHA256)
        records = [None] * 976
        successes = 0
        for case, message in enumerate(OBSERVATIONS, 1):
            label = f'TL{case:02d}'
            framed = message.encode('ascii')
            payload = framed[len(label) + 3:-2]
            records.append((label, framed, payload))
            successes += payload[2:3] == b'0'
        self.assertEqual(validate_records(records), {'records': 45, 'message_units': 3525})
        self.assertEqual(successes, 25)

    def test_exact45_native_observations_on_both_targets(self):
        helper, calls = fragments()
        for target in (None, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                output = []
                vm = Interpreter(output.append, **({} if target is None else {'native_target': target}))
                vm.execute('Procedure Показать(Label, Value) Message(Label + ": [" + Value + "]"); EndProcedure;' + helper + calls)
                self.assertEqual(tuple(x + '\n' for x in output), OBSERVATIONS)

    def test_complete1021_source_keeps_native45_suffix(self):
        output = []
        Interpreter(output.append, native_target=LINUX_8_3_27_1508).execute(source())
        self.assertEqual(len(output), 1021)
        self.assertEqual(tuple(x + '\n' for x in output[976:]), OBSERVATIONS)


if __name__ == '__main__':
    unittest.main()

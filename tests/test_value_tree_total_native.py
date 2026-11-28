"""Authenticated native32 observations; original run was measurement, not acceptance.

Linux1C8.3.27.1508 run40768375140 attempt1, PR141 head ef151a879b57e286882c3450c3ea965afa322a00.
Finite literal is captured native output, not generated expected behavior.
"""
import hashlib
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508
from scripts.native_1c_tree_total_contract import validate_payload

ROOT=Path(__file__).resolve().parents[1]
SOURCE_SHA256='55bf37f0ac53a5ae2e1a519a190847ddece4df0abcf387179e0fd7ae22bdca5c'
CAPTURE={'run':40768375140,'attempt':1,'head':'ef151a879b57e286882c3450c3ea965afa322a00',
         'tree':'082b86126110a95b50fc0ec268d8c6bc6417d56d','status':'failed_host_comparison_not_runtime_acceptance',
         'collections_sha256':'ffb5c25587a158008d5e10ce3aae078d1d0f80f9623283253ee4f7a4bcdee3df'}
NATIVE_RECORD=b'TT: [144C99B0034222U2444EE4EEEEECC1134]\n'
NATIVE_RECORD_SHA256='ec2a4cb29a7b9fc0e8114d1fb095f3c165b109d3dcefbe7a73dacbd9b47c25be'


def source():
    raw=(ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:raise AssertionError('native Total source changed')
    return raw.decode('utf-8-sig')


def helpers():
    text=source();start='// Begin bounded ValueTree Total helpers (measurement only; no native answers).\n'
    end='// End bounded ValueTree Total helpers.\n'
    total=start+text.split(start,1)[1].split(end,1)[0]+end
    exact=text[text.index('Функция TreeLoadExact('):text.index('Функция TreeLoadPair(')]
    return total+'\n'+exact


class NativeTotalTests(unittest.TestCase):
    def test_literal_integrity_and_all32_typed_ledger_entries(self):
        self.assertEqual(hashlib.sha256(NATIVE_RECORD).hexdigest(),NATIVE_RECORD_SHA256)
        self.assertEqual(len(NATIVE_RECORD),40)
        observations=validate_payload(NATIVE_RECORD[5:-2])
        expected=('5','5','28','16','16','23','0','0','3.75','5','2','2','2','U','2',
                  '5','5','5','E','E','5','E','E','E','E','E','28','28',
                  '10000000000000000000000000001','1','0.3','5')
        self.assertEqual(observations,tuple((i,'undefined' if v=='U' else 'exception' if v=='E' else 'number',
                                            None if v in ('E','U') else v) for i,v in enumerate(expected,1)))

    def test_exact_native32_on_both_targets(self):
        for target in (None,LINUX_8_3_27_1508):
            with self.subTest(target=target):
                output=[];vm=Interpreter(output.append,**({} if target is None else {'native_target':target}))
                vm.execute(helpers()+'Message("TT: [" + TreeTotalObservations() + "]");')
                self.assertEqual(('\n'.join(output)+'\n').encode(),NATIVE_RECORD)

    def test_complete_old1022_messages_unchanged_on_both_targets(self):
        complete = source()
        start = '// Begin bounded ValueTree Total observations (measurement only; no native answers).'
        prefix, separator, tail = complete.partition(start)
        self.assertEqual(separator, start)
        self.assertEqual(tail.splitlines()[1:], [
            'Показать("TT", TreeTotalObservations());',
            '// End bounded ValueTree Total observations.',
        ])
        for target in (None, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                outputs = []
                for program in (prefix, complete):
                    result = []
                    vm = Interpreter(result.append, **({} if target is None else {"native_target": target}))
                    vm.execute(program)
                    outputs.append(result)
                before, after = outputs
                self.assertEqual(len(before), 1022)
                self.assertEqual(after[:-1], before)
                self.assertEqual((after[-1] + '\n').encode(), NATIVE_RECORD)

"""Authenticated finite native UnloadColumn witnesses, not CI acceptance.

PR132 run40496124727 attempt1 failed host collections comparison. These literal
outputs are authenticated Linux1C8.3.27.1508 bytes, never interpreter output.
The 27 observations occupy records947–973 of the exact pinned collections source.
"""
import hashlib
import unittest
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from test_native_tree_unload_measurement import (
    fragments, raw_source, SOURCE_SHA, CALLS_START, CALLS_END,
    block, HELPER_START, HELPER_END,
)
from test_native_tree_findrows_measurement import fragments as old_fragments, PRESENT
from scripts.native_historical_replay import without_tree_unload_supplement

CAPTURE = {'run': 40496124727,
 'attempt': 1,
 'head': '04d67b04f03b7d4f4a397d2753a86ca8eeba2c84',
 'merge': '77addb530e83901b68407be758e6d85bfd5a8289',
 'tree': '15a00e396d7567a78763100ffee4382102062e2b',
 'report_sha256': '47020fd2f41507e462ee56ced8ab26ff49bbb6a2e3c8718584b576fba4b1faa9',
 'source_sha256': 'bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada',
 'native_collections_sha256': '437404ee6b0416a04be3a16b24c9fc1d4a466bc9d3213cf04d686bde47c68eca',
 'native_tail_sha256': 'd0d73074747583c7c3b0858fad84079144b45d267adf81581857c24e340cc13b',
 'native_tail_bytes': 6330}

# Verbatim authenticated native ledger bytes, not predicted answers.
OBSERVATIONS = (
    'tree.unload.alias.ru: [ok|change=none|result=array:2:n1,n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.alias.en: [ok|change=none|result=array:2:n1,n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.child: [ok|change=none|result=array:2:n4,n5,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.leaf: [ok|change=none|result=array:0:|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.empty: [ok|change=none|result=array:0:|state=empty:rows=n0:columns=n4]\n',
    'tree.unload.no-columns: [action-error|state=empty:rows=n0:columns=n0]\n',
    'tree.unload.selector.case: [ok|change=none|result=array:2:n1,n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.index-zero: [ok|change=none|result=array:2:n1,n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.index-one: [ok|change=none|result=array:2:s104.105.116.,s104.105.116.,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.fraction: [ok|change=none|result=array:2:n1,n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.negative: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.out-of-range: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.own-column: [ok|change=none|result=array:2:s104.105.116.,s104.105.116.,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.foreign-column: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.unknown: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.unknown-empty: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.undefined: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.boolean: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.missing-argument: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.extra-argument: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.wrong-tree: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.values.scalars: [ok|change=none|result=array:2:n1,b1,|state=2,2,1,1,0,0,0,;n1/n1/s120./base;n2/b1/s121./base;n3/n2/s120./base;n4/s49./s120./base;n5/b0/s121./base;n6/u/s121./base]\n',
    'tree.unload.values.nullish: [ok|change=none|result=array:2:u,l,|state=2,2,1,1,0,0,0,;n1/u/s120./base;n2/l/s121./base;n3/u/s120./base;n4/s/s120./base;n5/n0/s121./base;n6/l/s121./base]\n',
    'tree.unload.array-delete: [ok|change=ok|result=array:1:n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.source-add: [ok|change=ok|result=array:2:n1,n2,|state=3,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.mutable.result-to-source: [ok|change=ok|result=array:2:structure-mark:from-result,s104.105.116.,|state=2,2,1,1,0,0,0,;n1/structure-mark:from-result/s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.mutable.source-to-result: [ok|change=ok|result=array:2:structure-mark:from-source,s104.105.116.,|state=2,2,1,1,0,0,0,;n1/structure-mark:from-source/s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
)

def original27_source():
    """Restore the complete authenticated973 input, never slice native output."""
    return without_tree_unload_supplement(raw_source().decode('utf-8-sig')).encode('utf-8-sig')


def native_calls():
    text = original27_source().decode('utf-8-sig')
    helpers = block(text, HELPER_START, HELPER_END)
    calls = block(text, CALLS_START, CALLS_END)
    lines = calls.splitlines(keepends=True)
    if len(lines) != 29 or lines[0] != CALLS_START or lines[-1] != CALLS_END:
        raise AssertionError('unexpected exact UnloadColumn input matrix')
    return helpers, calls


class UnloadNativeObservations(unittest.TestCase):
    def test_exact_native27_literals_and_current_source_binding(self):
        self.assertEqual(hashlib.sha256(raw_source()).hexdigest(), SOURCE_SHA)
        self.assertEqual(hashlib.sha256(original27_source()).hexdigest(), CAPTURE['source_sha256'])
        _, calls = native_calls()
        self.assertEqual(len(OBSERVATIONS), 27)
        expected_labels = tuple(line.split(': [')[0] for line in OBSERVATIONS)
        self.assertEqual(tuple(line.split('"')[1] for line in calls.splitlines()[1:-1]), expected_labels)
        raw = ''.join(OBSERVATIONS).encode('ascii')
        self.assertEqual(len(raw), CAPTURE['native_tail_bytes'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CAPTURE['native_tail_sha256'])
        self.assertEqual(sum(': [ok|' in line for line in OBSERVATIONS), 16)
        self.assertEqual(sum(': [action-error|' in line for line in OBSERVATIONS), 11)
        for stage in ('setup-error', 'change-error', 'observer-error'):
            self.assertNotIn(stage, ''.join(OBSERVATIONS))

    def test_native27_observations_individually(self):
        helpers, calls = native_calls()
        checked = 0
        for call, expected in zip(calls.splitlines()[1:-1], OBSERVATIONS):
            label = expected.split(': [')[0]
            with self.subTest(label=label):
                output = []
                vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
                vm.execute(PRESENT + old_fragments()[0] + helpers + call)
                self.assertEqual(tuple(line + '\n' for line in output), (expected,))
                checked += 1
        self.assertEqual(checked, 27)

    def test_native27_all_native_bytes_without_filtering(self):
        helpers, calls = native_calls()
        output = []
        vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
        vm.execute(PRESENT + old_fragments()[0] + helpers + calls)
        self.assertEqual(tuple(line + '\n' for line in output), OBSERVATIONS)



SUPPLEMENTAL_CAPTURE = {'run': 40525937279,
 'attempt': 1,
 'head': 'e88a6f46f9f4de85304d17531f6be7948a7b53b0',
 'merge': 'bf6535a38c354231206ebbf1e68d604f2cb1e232',
 'tree': 'cf56474b41f6350cd1de8e8a65da7dd23f06e0e7',
 'report_sha256': '6d8055b99c9c4209f46a06e7ee86b3b278cbeee1f03c0f81e995cbbbd79fd3be',
 'source_sha256': '5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4',
 'native_collections_sha256': '7c6622008978cda52a80b7e87d0d6653ce58592ff48902b51b4576e7233e5ce3',
 'native_tail_sha256': '72a59158a5545513e71cf4b3d76c15dccb9915a904af06d6656e3cbf763d19a7',
 'native_tail_bytes': 7183,
 'supplement_sha256': '11b61c87c1fe5dd062209ee4456c6d6843f2ba9f4ed17e9729ffdc568e124fa7',
 'supplement_bytes': 853}

# Verbatim distinct supplemental capture; original27 metadata/literals stay frozen.
SUPPLEMENTAL_OBSERVATIONS = (
    'tree.unload.selector.fraction-one-half: [ok|change=none|result=array:2:s104.105.116.,s104.105.116.,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.fraction-one-nine: [ok|change=none|result=array:2:s104.105.116.,s104.105.116.,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.unload.selector.fraction-negative-half: [ok|change=none|result=array:2:n1,n2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
)

CURRENT_OBSERVATIONS = OBSERVATIONS + SUPPLEMENTAL_OBSERVATIONS

class UnloadNative30(unittest.TestCase):
    def test_exact_supplement_and_current30_source_binding(self):
        self.assertEqual(hashlib.sha256(raw_source()).hexdigest(), SOURCE_SHA)
        self.assertEqual(SOURCE_SHA, SUPPLEMENTAL_CAPTURE['source_sha256'])
        _, calls = fragments()
        call_lines = calls.splitlines(keepends=True)
        self.assertEqual(len(call_lines), 32)
        self.assertEqual(call_lines[0], CALLS_START)
        self.assertEqual(call_lines[-1], CALLS_END)
        self.assertEqual(len(SUPPLEMENTAL_OBSERVATIONS), 3)
        self.assertEqual(len(CURRENT_OBSERVATIONS), 30)
        labels = tuple(line.split(': [')[0] for line in CURRENT_OBSERVATIONS)
        self.assertEqual(len(set(labels)), 30)
        self.assertEqual(tuple(line.split('"')[1] for line in call_lines[1:-1]), labels)
        data = ''.join(CURRENT_OBSERVATIONS).encode('ascii')
        supplement = ''.join(SUPPLEMENTAL_OBSERVATIONS).encode('ascii')
        self.assertEqual(len(data), SUPPLEMENTAL_CAPTURE['native_tail_bytes'])
        self.assertEqual(hashlib.sha256(data).hexdigest(), SUPPLEMENTAL_CAPTURE['native_tail_sha256'])
        self.assertEqual(len(supplement), SUPPLEMENTAL_CAPTURE['supplement_bytes'])
        self.assertEqual(hashlib.sha256(supplement).hexdigest(), SUPPLEMENTAL_CAPTURE['supplement_sha256'])
        self.assertEqual(sum(': [ok|' in line for line in CURRENT_OBSERVATIONS), 19)
        self.assertEqual(sum(': [action-error|' in line for line in CURRENT_OBSERVATIONS), 11)
        for stage in ('setup-error', 'change-error', 'observer-error'):
            self.assertNotIn(stage, ''.join(CURRENT_OBSERVATIONS))

    def test_supplemental3_observations_individually(self):
        helpers, calls = fragments()
        supplement_calls = calls.splitlines()[-4:-1]
        self.assertEqual(len(supplement_calls), 3)
        checked = 0
        for call, expected in zip(supplement_calls, SUPPLEMENTAL_OBSERVATIONS):
            with self.subTest(label=expected.split(': [')[0]):
                output = []
                vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
                vm.execute(PRESENT + old_fragments()[0] + helpers + call)
                self.assertEqual(tuple(line + '\n' for line in output), (expected,))
                checked += 1
        self.assertEqual(checked, 3)

    def test_current30_all_native_bytes_without_filtering(self):
        helpers, calls = fragments()
        output = []
        vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
        vm.execute(PRESENT + old_fragments()[0] + helpers + calls)
        self.assertEqual(tuple(line + '\n' for line in output), CURRENT_OBSERVATIONS)


if __name__ == '__main__':
    unittest.main()

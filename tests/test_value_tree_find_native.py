"""Authentic finite native Find witnesses, not a successful CI acceptance claim.

PR128 initial42 run40461349726 failed host comparison. These literal outputs
come from authenticated Linux1C8.3.27.1508 capture, never interpreter output.
Two descendant-only probes were subsequently authenticated in run40469971658.
"""
import hashlib
import unittest
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from test_native_tree_find_measurement import (
    fragments, raw_source, SOURCE_SHA, CALLS_START, CALLS_END,
)
from test_native_tree_findrows_measurement import fragments as old_fragments, PRESENT

INITIAL_CAPTURE = {
    'run': 40461349726,
    'head': 'e77c74fd7a3457f09f0c018ead102488c0449d7b',
    'merge': 'aa44eb78d61784b5f4f2f280fa8432afee4717c8',
    'tree': '9fee431ab9939f4880e06a93664eb95c35f02ae4',
    'report_sha256': '5718140ab58c69222db996fee144a9c4e82288b21ecead97399cd1372916e23f',
    'source_sha256': 'd94101cf391fa84668b7f94bb9295655d62d3ff6baa084de17a48b62966a0901',
    'native_tail_sha256': 'f16abd91ab91ea7135231ae1dfdcb3f9ac7b6f2c2a97e2ea97532af6d686ec02',
    'native_tail_bytes': 10836,
}

# Verbatim authenticated native ledger bytes, not predicted answers.
INITIAL_OBSERVATIONS = (
    'tree.find.alias.ru: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.alias.en: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.root.false: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.root.omitted: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.child.true: [ok|change=none|result=row:4:parent=n1:level=n1:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.child.false: [ok|change=none|result=row:4:parent=n1:level=n1:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.child.omitted: [ok|change=none|result=row:4:parent=n1:level=n1:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.leaf: [ok|change=none|result=undefined|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.no-match: [ok|change=none|result=undefined|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.descendants.true: [ok|change=none|result=row:6:parent=n4:level=n2:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.descendants.false: [ok|change=none|result=undefined|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.descendants.omitted: [ok|change=none|result=undefined|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.child-descendants: [ok|change=none|result=row:6:parent=n4:level=n2:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.omitted: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.empty: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.undefined: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.case: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.order: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s104.105.116./base;n2/s104.105.116./s109.105.115.115./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.reversed: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s104.105.116./base;n2/s104.105.116./s109.105.115.115./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.spaces: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s104.105.116./base;n2/s104.105.116./s109.105.115.115./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.duplicate: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.unknown: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.unknown-empty: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.known-unknown: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.columns.number: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.value.number: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/n1/s120./base;n2/b1/s121./base;n3/n2/s120./base;n4/s49./s120./base;n5/b0/s121./base;n6/u/s121./base]\n',
    'tree.find.value.boolean: [ok|change=none|result=row:2:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/n1/s120./base;n2/b1/s121./base;n3/n2/s120./base;n4/s49./s120./base;n5/b0/s121./base;n6/u/s121./base]\n',
    'tree.find.value.string-case: [ok|change=none|result=row:2:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s120./s120./base;n2/s88./s121./base;n3/s120.32./s120./base;n4/s88.32./s120./base;n5/s120.120./s121./base;n6/s120./s121./base]\n',
    'tree.find.value.string-space: [ok|change=none|result=row:3:parent=n2:level=n1:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s120./s120./base;n2/s88./s121./base;n3/s120.32./s120./base;n4/s88.32./s120./base;n5/s120.120./s121./base;n6/s120./s121./base]\n',
    'tree.find.value.undefined: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/u/s120./base;n2/l/s121./base;n3/u/s120./base;n4/s/s120./base;n5/n0/s121./base;n6/l/s121./base]\n',
    'tree.find.value.null: [ok|change=none|result=row:6:parent=n4:level=n2:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/u/s120./base;n2/l/s121./base;n3/u/s120./base;n4/s/s120./base;n5/n0/s121./base;n6/l/s121./base]\n',
    'tree.find.result-to-source: [ok|change=ok|result=row:4:parent=n1:level=n1:owner=b1:mark=from-result|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./from-result;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.source-to-result: [ok|change=ok|result=row:4:parent=n1:level=n1:owner=b1:mark=from-source|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./from-source;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.missing-value: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.flag.undefined: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.flag.number: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.flag.string: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.wrong-tree: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.wrong-row: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.empty-tree: [ok|change=none|result=undefined|state=empty:rows=n0:columns=n4]\n',
    'tree.find.no-columns: [ok|change=none|result=undefined|state=empty:rows=n0:columns=n0]\n',
    'tree.find.empty-token: [ok|change=none|result=row:1:parent=undefined:level=n0:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
)

def initial_calls():
    helpers, calls = fragments()
    lines = calls.splitlines(keepends=True)
    if len(lines) != 46 or lines[0] != CALLS_START or lines[-1] != CALLS_END:
        raise AssertionError('unexpected current Find source')
    if not lines[-3].startswith('Показать("tree.find.flag.number-descendants",'):
        raise AssertionError('missing explicit Number descendant supplement')
    if not lines[-2].startswith('Показать("tree.find.flag.string-descendants",'):
        raise AssertionError('missing explicit String descendant supplement')
    original_calls = ''.join(lines[:-3] + [lines[-1]])
    original_source = raw_source().decode('utf-8-sig').replace(calls, original_calls)
    if hashlib.sha256(original_source.encode('utf-8-sig')).hexdigest() != INITIAL_CAPTURE['source_sha256']:
        raise AssertionError('initial42 exact source reconstruction failed')
    return helpers, original_calls


class FindNativeObservations(unittest.TestCase):
    def test_exact_initial42_literals_and_current_source_binding(self):
        self.assertEqual(hashlib.sha256(raw_source()).hexdigest(), SOURCE_SHA)
        _, calls = initial_calls()
        self.assertEqual(len(INITIAL_OBSERVATIONS), 42)
        expected_labels = tuple(line.split(': [')[0] for line in INITIAL_OBSERVATIONS)
        self.assertEqual(tuple(line.split('"')[1] for line in calls.splitlines()[1:-1]), expected_labels)
        raw = ''.join(INITIAL_OBSERVATIONS).encode('ascii')
        self.assertEqual(len(raw), INITIAL_CAPTURE['native_tail_bytes'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), INITIAL_CAPTURE['native_tail_sha256'])
        self.assertEqual(sum(': [ok|' in line for line in INITIAL_OBSERVATIONS), 34)
        self.assertEqual(sum(': [action-error|' in line for line in INITIAL_OBSERVATIONS), 8)
        for stage in ('setup-error', 'change-error', 'observer-error'):
            self.assertNotIn(stage, ''.join(INITIAL_OBSERVATIONS))

    def test_initial42_observations_individually(self):
        helpers, calls = initial_calls()
        checked = 0
        for call, expected in zip(calls.splitlines()[1:-1], INITIAL_OBSERVATIONS):
            label = expected.split(': [')[0]
            with self.subTest(label=label):
                output = []
                vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
                vm.execute(PRESENT + old_fragments()[0] + helpers + call)
                self.assertEqual(tuple(line + '\n' for line in output), (expected,))
                checked += 1
        self.assertEqual(checked, 42)

    def test_initial42_all_native_bytes_without_filtering(self):
        helpers, calls = initial_calls()
        output = []
        vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
        vm.execute(PRESENT + old_fragments()[0] + helpers + calls)
        self.assertEqual(tuple(line + '\n' for line in output), INITIAL_OBSERVATIONS)


SUPPLEMENTAL_CAPTURE = {'run': 40469971658, 'head': 'bf238305999e866af12c93ee5c3113dca867d39a', 'merge': 'e01a7d98e2a9588a941e54576834f336785fc132', 'tree': '1e92f147380eee7afe8926b58e2d432ae7a8bde3', 'report_sha256': '789ede42ca62aaac3e3db9e67b269f12e4fb88b66db595ab4dcf10ef5408429e', 'source_sha256': '9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3', 'native_tail_sha256': 'b5860b93e283c20c8d8a3272e778139f2a37333e64cc1f0b42e05b55e1a31f58', 'native_tail_bytes': 11444}

SUPPLEMENTAL_OBSERVATIONS = (
    'tree.find.flag.number-descendants: [ok|change=none|result=row:6:parent=n4:level=n2:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.find.flag.string-descendants: [ok|change=none|result=row:6:parent=n4:level=n2:owner=b1:mark=base|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
)

CURRENT_OBSERVATIONS = INITIAL_OBSERVATIONS + SUPPLEMENTAL_OBSERVATIONS

class FindNative44(unittest.TestCase):
    def test_current_capture_identity(self):
        data = "".join(CURRENT_OBSERVATIONS).encode()
        self.assertEqual(len(CURRENT_OBSERVATIONS), 44)
        self.assertEqual(len(data), SUPPLEMENTAL_CAPTURE["native_tail_bytes"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), SUPPLEMENTAL_CAPTURE["native_tail_sha256"])
        self.assertEqual(SOURCE_SHA, SUPPLEMENTAL_CAPTURE["source_sha256"])
        self.assertEqual(sum(": [ok|" in x for x in CURRENT_OBSERVATIONS), 36)

    def test_current44_all_native_bytes_without_filtering(self):
        helpers, calls = fragments()
        output = []
        vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
        vm.execute(PRESENT + old_fragments()[0] + helpers + calls)
        self.assertEqual(tuple(line + "\n" for line in output), CURRENT_OBSERVATIONS)


if __name__ == '__main__':
    unittest.main()

"""Exact finite native witnesses, separate from local-policy extension tests.

PR119 run 40283979870, Linux 1C 8.3.27.1508. The initial workflow failed
host comparison; these 36 successful/error observations are evidence, not fresh
native acceptance. Literal public fixed-input output only; no private artifacts.
"""
import hashlib
import unittest
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from test_native_tree_findrows_measurement import fragments, PRESENT, raw_source, SOURCE_SHA, LABELS

CAPTURE = {
    'run': 40283979870,
    'head': '39f59c076bcfbf4d594b4f51ef363f579f9a489e',
    'merge': '4d67ef8b5dec7b07f8c01325c107d6d0ad6363bc',
    'tree': 'b99576697424054b7a2944860d8d43602e78dd01',
    'ledger_sha256': '115e44cb3e11a4e929c1fd465d190b978989a05366da75cd069d8967b3c28d91',
    'native_tail_sha256': 'ff0e72138da5f1e41a4853f7fe797acc9e82a2f8e4ff792704bb6eca219402e3',
    'native_tail_bytes': 8881,
}

# Transcribed from the authenticated native ledger, never interpreter output.
OBSERVATIONS = (
    'tree.findrows.alias.ru: [ok|change=none|result=array:6:1,4,6,5,2,3,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.alias.en: [ok|change=none|result=array:6:1,4,6,5,2,3,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.root.false: [ok|change=none|result=array:2:1,2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.root.omitted: [ok|change=none|result=array:2:1,2,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.child.true: [ok|change=none|result=array:3:4,6,5,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.child.false: [ok|change=none|result=array:2:4,5,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.child.omitted: [ok|change=none|result=array:2:4,5,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.leaf: [ok|change=none|result=array:0:|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.no-match: [ok|change=none|result=array:0:|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.nonmatching-parents: [ok|change=none|result=array:3:6,5,3,|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.conjunction: [ok|change=none|result=array:1:3,|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.conjunction-reversed: [ok|change=none|result=array:1:3,|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.column-case: [ok|change=none|result=array:1:3,|state=2,2,1,1,0,0,0,;n1/s109.105.115.115./s120./base;n2/s109.105.115.115./s121./base;n3/s104.105.116./s120./base;n4/s109.105.115.115./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.empty-filter.nonempty: [ok|change=none|result=array:0:|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.empty-filter.empty: [ok|change=none|result=array:0:|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.number-boolean: [ok|change=ok|result=array:1:1,|second=array:1:2,|state=2,2,1,1,0,0,0,;n1/n1/s120./base;n2/b1/s121./base;n3/n2/s120./base;n4/s49./s120./base;n5/b0/s121./base;n6/u/s121./base]\n',
    'tree.findrows.string-case: [ok|change=none|result=array:2:1,6,|state=2,2,1,1,0,0,0,;n1/s120./s120./base;n2/s88./s121./base;n3/s120.32./s120./base;n4/s88.32./s120./base;n5/s120.120./s121./base;n6/s120./s121./base]\n',
    'tree.findrows.string-space: [ok|change=none|result=array:1:3,|state=2,2,1,1,0,0,0,;n1/s120./s120./base;n2/s88./s121./base;n3/s120.32./s120./base;n4/s88.32./s120./base;n5/s120.120./s121./base;n6/s120./s121./base]\n',
    'tree.findrows.undefined-value: [ok|change=none|result=array:2:1,3,|state=2,2,1,1,0,0,0,;n1/u/s120./base;n2/l/s121./base;n3/u/s120./base;n4/s/s120./base;n5/n0/s121./base;n6/l/s121./base]\n',
    'tree.findrows.null-value: [ok|change=none|result=array:2:6,2,|state=2,2,1,1,0,0,0,;n1/u/s120./base;n2/l/s121./base;n3/u/s120./base;n4/s/s120./base;n5/n0/s121./base;n6/l/s121./base]\n',
    'tree.findrows.result-to-source: [ok|change=ok|result=array:1:4,|result-mark=from-result|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./from-result;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.source-to-result: [ok|change=ok|result=array:1:4,|result-mark=from-source|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./from-source;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.array-delete: [ok|change=ok|result=array:5:4,6,5,2,3,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.add-node: [ok|change=ok|result=array:6:1,4,6,5,2,3,|second=array:7:1,4,6,5,7,2,3,|state=2,3,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.filter-change: [ok|change=ok|result=array:6:1,4,6,5,2,3,|second=array:0:|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.unknown-column.nonempty: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.unknown-column.empty: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.missing-filter: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.undefined-filter: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.number-filter: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.fixed-filter: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.undefined-flag: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.number-flag: [ok|change=none|result=array:6:1,4,6,5,2,3,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.string-flag: [ok|change=none|result=array:6:1,4,6,5,2,3,|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.wrong-tree: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
    'tree.findrows.wrong-row: [action-error|state=2,2,1,1,0,0,0,;n1/s104.105.116./s120./base;n2/s104.105.116./s121./base;n3/s104.105.116./s120./base;n4/s104.105.116./s120./base;n5/s104.105.116./s121./base;n6/s104.105.116./s121./base]\n',
)


class FindRowsNativeObservations(unittest.TestCase):
    def test_exact_source_all36_native_literals_are_retained(self):
        self.assertEqual(hashlib.sha256(raw_source()).hexdigest(), SOURCE_SHA)
        self.assertEqual(len(OBSERVATIONS), 36)
        self.assertEqual(tuple(row.split(': [')[0].removeprefix('tree.findrows.')
                               for row in OBSERVATIONS), LABELS)
        raw = ''.join(OBSERVATIONS).encode('ascii')
        self.assertEqual(len(raw), CAPTURE['native_tail_bytes'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CAPTURE['native_tail_sha256'])
        self.assertEqual(sum(': [ok|' in row for row in OBSERVATIONS), 27)
        self.assertEqual(sum(': [action-error|' in row for row in OBSERVATIONS), 9)
        self.assertNotIn('setup-error', ''.join(OBSERVATIONS))
        self.assertNotIn('change-error', ''.join(OBSERVATIONS))
        self.assertNotIn('observer-error', ''.join(OBSERVATIONS))

    def test_unchanged36_probes_match_exact_native_bytes_without_filtering(self):
        output = []
        vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
        helpers, calls = fragments()
        vm.execute(PRESENT + helpers + calls)
        self.assertEqual(tuple(line + '\n' for line in output), OBSERVATIONS)


if __name__ == '__main__':
    unittest.main()

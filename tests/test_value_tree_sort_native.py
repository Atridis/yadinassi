"""Authenticated Linux Tree Sort checkpoint, not guessed expected semantics."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from scripts import native_1c_tree_sort_contract as contract
from scripts import native_1c_tree_profile as host

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'integrational_tests/measurements/tree_sort.bsl'
FIXTURE = ROOT/'tests/fixtures/value_tree_sort'
SOURCE_HASH = '5607a0c42901d624cfae1d166aed8d3ea258a2b0c8e0c894dcd032526a6fb5a3'
NATIVE_HASH = '63264e3a24c6b3381e300f22766c11eecbffb20e17a03fadc95745aec6594871'


def native():
    raw=(FIXTURE/'linux-8.3.27.1508.out').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=NATIVE_HASH:
        raise AssertionError('native Sort capture changed')
    return raw


def source():
    raw=SOURCE.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=SOURCE_HASH:
        raise AssertionError('native Sort source changed')
    return raw.decode()


class NativeTreeSortTests(unittest.TestCase):
    def test_source_capture_provenance_and_all21_observed_cases(self):
        source();raw=native();self.assertEqual(len(raw),6443)
        provenance=json.loads((FIXTURE/'provenance.json').read_text(encoding='utf-8'))
        self.assertEqual((provenance['run_id'],provenance['attempt']),(40966832988,1))
        self.assertEqual(provenance['head'],'c460c127e76571e6b7930e60d074c19e7373a295')
        self.assertEqual(provenance['tree'],'02225abeed780d76cfdb16e148d69f144fb8c02d')
        self.assertEqual(provenance['source_sha256'],SOURCE_HASH)
        self.assertEqual(provenance['native_sha256'],NATIVE_HASH)
        self.assertTrue(provenance['server_client_equal'])
        self.assertTrue(provenance['native_acquisition_accepted'])
        self.assertFalse(provenance['runtime_parity_accepted'])  # Original acquisition predates implementation.
        decoded=contract.require_available(raw)
        self.assertEqual([r['status'] for r in decoded],['S']*10+['O']*4+['A']*2+['O']*2+['S','O','O'])
        orders=['fghabcde','fghabcde','fghaebdc','aebdcfgh','aebcdfgh','fhgaebdc','fhgaebdc',
                'rcoflibqnkhejmgpda','adpgmjbqnkheilfocr','']
        for record in decoded:
            before,after=record['snapshots']
            if record['case']<=10:
                self.assertEqual(''.join(n.cells[2][1] for n in after['nodes']),orders[record['case']-1])
            if record['status']!='S': self.assertEqual(before,after)
            self.assertEqual({n.row:n for n in before['nodes']},{n.row:n for n in after['nodes']})
            self.assertEqual({k:v for k,v in before.items() if k!='nodes'},
                             {k:v for k,v in after.items() if k!='nodes'})

    def test_exact_authenticated_server_and_generated_client_capture(self):
        output=[];Interpreter(output.append,native_target=LINUX_8_3_27_1508).execute(source())
        self.assertEqual(('\n'.join(output)+'\n').encode(),native())
        import test_native_tree_profile_budget as budget
        module=budget.tree.client_module(source().encode(),
            (ROOT/budget.suite.CLIENT_SOURCE).read_bytes().replace(b'\r\n',b'\n'),profile='tree-sort-v1')
        self.assertEqual(hashlib.sha256(module).hexdigest(),'cb9238022105b01dc1bbfe1c7c5a05835991c167e7ac75c6eee3297d22140e41')
        vm=Interpreter(native_target=LINUX_8_3_27_1508);vm.execute(module.decode('utf-8-sig'))
        vm.execute('Observed=ВычислитьПробу();')
        self.assertEqual(('\n'.join(vm.variables['observed'].items)+'\n').encode(),native())

    @unittest.skipUnless(os.name == 'posix', 'strict POSIX host runner; semantic-target tests above run on every OS')
    def test_real_isolated_profile_comparison_accepts_exact_native_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=host.compare_output(ROOT,Path(temporary).resolve(),native(),
                {'integrational_tests/measurements/tree_sort.bsl':SOURCE_HASH},profile='tree-sort-v1')
        self.assertEqual(result['status'],'matched')
        self.assertEqual(result['acceptance_status'],'accepted')
        self.assertTrue(result['native_sort_available'])
        self.assertEqual(result['interpreter_sha256'],NATIVE_HASH)


if __name__=='__main__': unittest.main()

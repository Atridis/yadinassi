"""Exact CC12 and CL6 Linux native replays, preserving original run attribution."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from scripts import native_1c_tree_profile as host
from scripts import native_1c_tree_profiles as profiles
from test_value_tree_columns_move_native import synthetic_source_reader

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/value_tree_columns_clear'
PROVENANCE_SHA='7e313d56654634af3a6bcd89ba244883e1b86f54d66fdc6ab27007e9d75dc71e'
PINS=(('tree-columns-clear-v1',12,2252,41066943188,'4db4c7b231ca12b087ba6ff7e3a16069b0dffc27b5c35c12db7dc061d082460c'),
      ('tree-columns-clear-lifetime-v1',6,2820,41072087598,'ae2cba92a2129f9ba4695413aab6a739577bbef75b5283338d8552cd94ffddfb'))


def checkpoints():
    raw=(FIXTURE/'provenance.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROVENANCE_SHA:raise AssertionError('Clear provenance changed')
    return json.loads(raw.decode('utf-8'))['captures']


def native(record):
    raw=(FIXTURE/record['fixture']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record['native_sha256']:raise AssertionError('Clear native capture changed')
    return raw


def source(record):
    raw=(ROOT/record['source']).read_text(encoding='utf-8').encode('utf-8')
    if hashlib.sha256(raw).hexdigest()!=record['source_sha256']:raise AssertionError('Clear source changed')
    return raw


class NativeClearTests(unittest.TestCase):
    def test_original_native_provenance_and_exact_18_records(self):
        total=0
        for record,pin in zip(checkpoints(),PINS):
            self.assertEqual((record['profile'],record['case_count'],record['native_size'],record['run_id'],record['native_sha256']),pin)
            self.assertTrue(record['native_acquisition_accepted']);self.assertFalse(record['runtime_parity_accepted'])
            self.assertTrue(record['server_client_equal']);self.assertTrue(record['cleanup_verified'])
            spec=profiles.select(record['profile']);self.assertEqual(spec.source,record['source']);self.assertEqual(spec.source_sha256,record['source_sha256'])
            raw=native(record);self.assertEqual(len(raw),record['native_size']);self.assertNotIn(b'\r',raw)
            records=host.selected_contract(record['profile']).require_available(raw)
            self.assertEqual(len(records),record['case_count']);total+=len(records);source(record)
        self.assertEqual(total,18)

    def test_exact_server_replay_all18(self):
        for record in checkpoints():
            with self.subTest(profile=record['profile']):
                output=[];Interpreter(output.append,native_target=LINUX_8_3_27_1508).execute(source(record).decode('utf-8'))
                self.assertEqual(('\n'.join(output)+'\n').encode('ascii'),native(record))

    def test_exact_generated_client_replay_all18(self):
        import test_native_tree_profile_budget as budget
        template=(ROOT/budget.suite.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8')
        for record in checkpoints():
            with self.subTest(profile=record['profile']):
                module=budget.tree.client_module(source(record),template,profile=record['profile'])
                self.assertEqual(hashlib.sha256(module).hexdigest(),record['server_client_modules']['client'])
                vm=Interpreter(native_target=LINUX_8_3_27_1508);vm.execute(module.decode('utf-8-sig'));vm.execute('Observed=ВычислитьПробу();')
                self.assertEqual(('\n'.join(vm.variables['observed'].items)+'\n').encode('ascii'),native(record))

    @unittest.skipUnless(os.name=='posix','strict POSIX production host runner; semantic server/client replays run on every OS')
    def test_real_host_comparison_with_private_canonical_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(strict=True)
            shutil.copytree(ROOT/'yadinassi',root/'yadinassi',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            private=root/'private';private.mkdir()
            for record in checkpoints():
                path=root/record['source'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source(record))
                result=host.compare_output(root,private,native(record),{record['source']:record['source_sha256']},profile=record['profile'])
                self.assertEqual((result['status'],result['acceptance_status']),('matched','accepted'))
                self.assertEqual(result['interpreter_sha256'],record['native_sha256'])

    def test_strict_source_hash_before_runner_and_private_canonical_fixture(self):
        for record in checkpoints():
            with self.subTest(profile=record['profile']),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve(strict=True);path=root/record['source'];path.parent.mkdir(parents=True)
                canonical=source(record);runner=Mock(return_value=(0,native(record),b''))
                with synthetic_source_reader(path):
                    for bad in (canonical.replace(b'\n',b'\r\n'),canonical+b'\n'):
                        path.write_bytes(bad)
                        with self.assertRaises(host.TreeError):host.compare_output(root,root,native(record),{record['source']:record['source_sha256']},runner=runner,profile=record['profile'])
                    runner.assert_not_called();path.write_bytes(canonical)
                    result=host.compare_output(root,root,native(record),{record['source']:record['source_sha256']},runner=runner,profile=record['profile'])
                self.assertEqual(result['acceptance_status'],'accepted')

    def test_required_clear_lane_restored_and_exploratory_lane_retired(self):
        workflow=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        self.assertIn('          - profile: tree-columns-clear-v1\n            artifact: tree-columns-clear\n            case: tree_columns_clear\n',workflow)
        self.assertNotIn('profile: tree-columns-clear-lifetime-v1',workflow)
        self.assertEqual(profiles.select('tree-columns-clear-lifetime-v1').count,7)
        attrs=(ROOT/'.gitattributes').read_text(encoding='utf-8')
        self.assertIn('tests/fixtures/value_tree_columns_clear/*.out -text',attrs)
        self.assertIn('tests/fixtures/value_tree_columns_clear/provenance.json -text',attrs)


if __name__=='__main__':unittest.main()

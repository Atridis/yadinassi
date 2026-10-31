"""Exact DL14/DS6 observations, retaining original mismatched-runtime attribution."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from scripts import native_1c_tree_profile as host
from scripts import native_1c_tree_profiles as profiles

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/value_tree_columns_delete'
PROVENANCE_SHA = '4a105cfe2330cc11097185c994671f7f001ac6e14a1d3d0c4e358148e423597b'


def captures():
    raw = (FIXTURE / 'provenance.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROVENANCE_SHA:
        raise AssertionError('Delete provenance changed')
    return json.loads(raw)['captures']


def native(record):
    raw = (FIXTURE / record['fixture']).read_bytes()
    if len(raw) != record['native_size'] or hashlib.sha256(raw).hexdigest() != record['native_sha256']:
        raise AssertionError('Native Delete bytes changed')
    return raw


def source(record):
    # Repository checkout may use CRLF; original native source stays canonical LF.
    raw = (ROOT / record['source']).read_text(encoding='utf-8').encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != record['source_sha256']:
        raise AssertionError('Delete source changed')
    return raw


class NativeDeleteTests(unittest.TestCase):
    def test_original_acquisition_not_relabelled_as_runtime_pass(self):
        records = captures()
        self.assertEqual([r['run_id'] for r in records], [41135287284, 41140659293])
        self.assertEqual([r['case_count'] for r in records], [14, 6])
        for record in records:
            self.assertTrue(record['native_acquisition_accepted'])
            self.assertFalse(record['runtime_parity_accepted'])
            self.assertTrue(record['cleanup_verified'])
            spec = profiles.select(record['profile'])
            self.assertEqual(spec.source_sha256, record['source_sha256'])
            self.assertEqual(len(host.selected_contract(record['profile']).require_available(native(record))), record['case_count'])
            source(record)

    def test_exact_server_replay_all20(self):
        for record in captures():
            with self.subTest(profile=record['profile']):
                out = []
                Interpreter(out.append, native_target=LINUX_8_3_27_1508).execute(source(record).decode('utf-8'))
                self.assertEqual(('\n'.join(out) + '\n').encode('ascii'), native(record))

    def test_exact_generated_client_replay_all20(self):
        import test_native_tree_profile_budget as budget
        template = (ROOT / budget.suite.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8')
        for record in captures():
            with self.subTest(profile=record['profile']):
                module = budget.tree.client_module(source(record), template, profile=record['profile'])
                self.assertEqual(hashlib.sha256(module).hexdigest(), record['server_client_modules']['client'])
                vm = Interpreter(native_target=LINUX_8_3_27_1508)
                vm.execute(module.decode('utf-8-sig')); vm.execute('Observed=ВычислитьПробу();')
                self.assertEqual(('\n'.join(vm.variables['observed'].items) + '\n').encode('ascii'), native(record))

    @unittest.skipUnless(os.name == 'posix', 'strict POSIX production host runner; semantic replays run everywhere')
    def test_production_host_replay_canonical_private_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=True)
            shutil.copytree(ROOT / 'yadinassi', root / 'yadinassi', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            private = root / 'private'; private.mkdir()
            for record in captures():
                path = root / record['source']; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(source(record))
                result = host.compare_output(root, private, native(record), {record['source']: record['source_sha256']}, profile=record['profile'])
                self.assertEqual((result['status'], result['acceptance_status']), ('matched', 'accepted'))

    def test_required_delete_lane_restored_string_probe_offline(self):
        workflow = (ROOT / '.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        self.assertIn('          - profile: tree-columns-delete-v1\n            artifact: tree-columns-delete\n            case: tree_columns_delete\n', workflow)
        self.assertNotIn('profile: tree-columns-delete-string-v1', workflow)
        self.assertEqual(profiles.select('tree-columns-delete-string-v1').count, 7)

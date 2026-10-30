"""Exact authenticated Linux Columns.Move captures; no snapshot normalization."""
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
FIXTURE = ROOT / 'tests/fixtures/value_tree_columns_move'
PINS = (
    ('tree-columns-move-v1', 28, 7480, 41030064575,
     '2a691dda9e209583781d356a142f8866e057400bebfc6f83a5d39581d27b727c'),
    ('tree-columns-move-boundary-v1', 17, 4779, 41034467262,
     'f19dee0a3f8ec4cb718902b2e259ee8c269ffd4d89803289dce73e5c62b150ad'),
    ('tree-columns-move-tail-v1', 6, 1691, 41037650691,
     '564cd7b8bd2d859471e6be65ab02e7f045294d77d97034160d5e78c9f7b54b2e'),
)


def checkpoints():
    raw = (FIXTURE / 'provenance.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '0eaa13052ec8154fc36c68cd28a32fd35e83fe848cb9e8b9e9b97763eabcd914':
        raise AssertionError('native Columns.Move provenance changed')
    return json.loads(raw.decode('utf-8'))['captures']


def native(record):
    raw = (FIXTURE / record['fixture']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != record['native_sha256']:
        raise AssertionError('native Columns.Move capture changed')
    return raw


def source(record):
    # Only the checkout source is canonicalized; authenticated outputs never are.
    raw = (ROOT / record['source']).read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(raw).hexdigest() != record['source_sha256']:
        raise AssertionError('native Columns.Move source changed')
    return raw


class NativeColumnsMoveTests(unittest.TestCase):
    def test_original_acquisition_provenance_and_all51_cases(self):
        captures = checkpoints()
        self.assertEqual(len(captures), 3)
        total = 0
        for record, pin in zip(captures, PINS):
            with self.subTest(profile=pin[0]):
                self.assertEqual(tuple(record[k] for k in
                    ('profile','case_count','native_size','run_id','native_sha256')), pin)
                spec = profiles.select(record['profile'])
                self.assertEqual(record['source'], spec.source)
                self.assertEqual(record['source_sha256'], spec.source_sha256)
                self.assertEqual(record['attempt'], 1)
                self.assertTrue(record['server_client_equal'])
                self.assertTrue(record['cleanup_verified'])
                self.assertTrue(record['native_acquisition_accepted'])
                self.assertFalse(record['runtime_parity_accepted'])
                raw = native(record); source(record)
                self.assertEqual(len(raw), record['native_size'])
                self.assertNotIn(b'\r', raw)
                decoded = host.selected_contract(record['profile']).require_available(raw)
                self.assertEqual(len(decoded), record['case_count'])
                total += len(decoded)
                for case in decoded:
                    before, after = case['snapshots']
                    self.assertEqual(before['tree'], after['tree'])
                    self.assertEqual({c[0]: c for c in before['schema']},
                                     {c[0]: c for c in after['schema']})
                    self.assertEqual(len(before['nodes']), len(after['nodes']))
                    for old, new in zip(before['nodes'], after['nodes']):
                        self.assertEqual(old[:6], new[:6])
                        self.assertEqual(dict(zip((c[0] for c in before['schema']), old.cells)),
                                         dict(zip((c[0] for c in after['schema']), new.cells)))
                        self.assertEqual(old.cells, old.named_cells)
                        self.assertEqual(new.cells, new.named_cells)
                    if case['status'] != 'S': self.assertEqual(before, after)
        self.assertEqual(total, 51)

    def test_exact_server_replay_all51(self):
        for record in checkpoints():
            with self.subTest(profile=record['profile']):
                output = []
                Interpreter(output.append, native_target=LINUX_8_3_27_1508).execute(source(record).decode('utf-8'))
                self.assertEqual(('\n'.join(output)+'\n').encode('ascii'), native(record))

    def test_exact_generated_client_replay_all51(self):
        import test_native_tree_profile_budget as budget
        template = (ROOT / budget.suite.CLIENT_SOURCE).read_bytes().replace(b'\r\n', b'\n')
        for record in checkpoints():
            with self.subTest(profile=record['profile']):
                module = budget.tree.client_module(source(record), template, profile=record['profile'])
                self.assertEqual(hashlib.sha256(module).hexdigest(), record['server_client_modules']['client'])
                vm = Interpreter(native_target=LINUX_8_3_27_1508)
                vm.execute(module.decode('utf-8-sig'))
                vm.execute('Observed=ВычислитьПробу();')
                self.assertEqual(('\n'.join(vm.variables['observed'].items)+'\n').encode('ascii'), native(record))

    @unittest.skipUnless(os.name == 'posix', 'strict POSIX host subprocess; semantic replays run on every host OS')
    def test_real_host_comparison_with_private_canonical_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(ROOT / 'yadinassi', root / 'yadinassi',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            private = root / 'private'; private.mkdir()
            for record in checkpoints():
                with self.subTest(profile=record['profile']):
                    path = root / record['source']; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(source(record))
                    result = host.compare_output(root, private, native(record),
                        {record['source']: record['source_sha256']}, profile=record['profile'])
                    self.assertEqual(result['status'], 'matched')
                    self.assertEqual(result['acceptance_status'], 'accepted')
                    self.assertEqual(result['interpreter_sha256'], record['native_sha256'])

    def test_crlf_source_is_rejected_before_runner_then_private_canonical_source_admitted(self):
        for record in checkpoints():
            with self.subTest(profile=record['profile']), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(); path = root / record['source']
                path.parent.mkdir(parents=True); canonical = source(record)
                path.write_bytes(canonical.replace(b'\n', b'\r\n'))
                calls = []
                def runner(*args):
                    calls.append(args)
                    return 0, native(record), b''
                with self.assertRaisesRegex(host.TreeError, 'tree_source_changed'):
                    host.compare_output(root, root, native(record),
                        {record['source']: record['source_sha256']}, runner=runner, profile=record['profile'])
                self.assertEqual(calls, [])
                path.write_bytes(path.read_text(encoding='utf-8').encode('utf-8'))
                self.assertEqual(path.read_bytes(), canonical)
                result = host.compare_output(root, root, native(record),
                    {record['source']: record['source_sha256']}, runner=runner, profile=record['profile'])
                self.assertEqual(result['acceptance_status'], 'accepted')
                self.assertEqual(len(calls), 1)


if __name__ == '__main__': unittest.main()

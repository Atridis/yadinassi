"""Exact observed surface replay, distinct from actual public file readback."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
import metadata_catalog_runtime_readback as subject
import metadata_catalog_probe_contract as wire

CAPTURE = ROOT / 'tests/fixtures/metadata_catalog_runtime/native_observations.json'


def native_wire(rows):
    def encoded(row):
        if row['status'] != 'ok': return row['status']
        kind, value = row['kind'], row['value']
        if kind == 'string':
            raw = value.encode('utf-16-be')
            scalar = 'S' + str(len(raw) // 2) + ':' + raw.hex()
        elif kind == 'number': scalar = 'N' + str(value)
        elif kind == 'boolean': scalar = 'B' + str(int(value))
        elif kind == 'undefined': scalar = 'U'
        else: raise AssertionError(kind)
        return 'ok|' + scalar
    return wire.C1 + wire.C2 + b''.join(
        f'MC-{row["id"]:02}: [{encoded(row)}]\n'.encode('ascii') for row in rows)


class MetadataRuntimeReplayTests(unittest.TestCase):
    def test_source_bound_all_six_native_captures_supported24_exact(self):
        raw = CAPTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'e7a54e3ed988c32ecf897710c32e7c6c32a46b906009c846a34970b3f497b124')
        captures = json.loads(raw)
        self.assertEqual([(c['snapshot'], c['context']) for c in captures],
                         [(s, c) for s in ('updated', 'loaded', 'applied') for c in ('client', 'server')])
        self.assertEqual(subject.SUPPORTED_IDS, tuple(i for i in range(1, 27) if i not in (7, 8)))
        for capture in captures:
            with self.subTest(snapshot=capture['snapshot'], context=capture['context']):
                # Explicit stub: this test proves behavior, not CONFIG acquisition.
                context = mock.Mock()
                context.catalog_metadata.return_value = (SimpleNamespace(name=capture['config']['name']),)
                actual = subject._execute(context)
                comparison = subject.compare_readback(actual, native_wire(capture['rows']))
                self.assertTrue(comparison['supported_match'])
                self.assertEqual(len(comparison['matched_ids']), 24)
                self.assertEqual(comparison['mismatched_ids'], [])
                self.assertEqual([c['runtime_status'] for c in comparison['excluded_controls']],
                                 ['action-error', 'action-error'])
                self.assertEqual([c['native_status'] for c in comparison['excluded_controls']], ['ok', 'ok'])
                context.catalog_metadata.assert_called_once_with()

    def test_supported_mismatch_cannot_be_hidden_as_exclusion(self):
        rows = json.loads(CAPTURE.read_bytes())[0]['rows']
        original = native_wire(rows)
        rows[8]['value'] = 'WrongCatalog'
        result = subject.compare_readback(native_wire(rows), original)
        self.assertFalse(result['supported_match'])
        self.assertEqual(result['mismatched_ids'], [9])

    def test_public_helper_constructs_actual_context_not_expected_values(self):
        from yadinassi.database_context import FileDBContext
        rows = json.loads(CAPTURE.read_bytes())[0]['rows']
        raw = native_wire(rows)
        with mock.patch.object(subject, '_execute', return_value=raw) as run:
            result = subject.readback(Path('owned-frozen'), native_wire=raw)
        context = run.call_args.args[0]
        self.assertIs(type(context), FileDBContext)
        self.assertEqual(context.directory, str(Path('owned-frozen').absolute()))
        self.assertTrue(result['comparison']['supported_match'])

    def test_actual_public_adapter_reads_config_only_image_and_replays24(self):
        from test_catalog_metadata_reader import image
        value = image(names=('NativeOracleItems',))
        rows = json.loads(CAPTURE.read_bytes())[0]['rows']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '1Cv8.1CD'
            path.write_bytes(value.read_at(0, value.size))
            original = path.read_bytes()
            result = subject.readback(Path(directory), native_wire=native_wire(rows))
            self.assertEqual(path.read_bytes(), original)
        self.assertTrue(result['comparison']['supported_match'])
        self.assertEqual(len(result['comparison']['matched_ids']), 24)
        self.assertEqual([c['runtime_status'] for c in result['comparison']['excluded_controls']],
                         ['action-error', 'action-error'])

    def test_probe_source_change_rejected(self):
        with mock.patch.object(subject, 'PROBE_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                subject._execute(mock.Mock())

if __name__ == '__main__': unittest.main()

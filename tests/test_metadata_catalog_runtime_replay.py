"""Exact observed BSL surface replay against owned SQLite, not native-file parity."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_reference'))
import metadata_catalog_runtime_readback as subject
import metadata_catalog_probe_contract as wire

CAPTURE = ROOT / 'tests/fixtures/metadata_catalog_runtime/native_observations.json'


def create_database(directory):
    from yadinassi.configuration_xml import import_configuration
    from yadinassi.database_context import SQLiteDBContext
    prefix = '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20">'
    files = {
        'Configuration.xml': (prefix + '<Configuration uuid="20000000-0000-4000-8000-000000000001"><Properties><Name>ReferenceReplay</Name></Properties><ChildObjects><Catalog>NativeOracleItems</Catalog></ChildObjects></Configuration></MetaDataObject>').encode(),
        'Catalogs/NativeOracleItems.xml': (prefix + '<Catalog uuid="20000000-0000-4000-8000-000000000002"><Properties><Name>NativeOracleItems</Name><CodeType>String</CodeType><CodeLength>8</CodeLength><DescriptionLength>32</DescriptionLength><Autonumbering>false</Autonumbering><CheckUnique>true</CheckUnique></Properties><ChildObjects/></Catalog></MetaDataObject>').encode(),
    }
    path = directory / 'application.sqlite'
    with SQLiteDBContext.create(path, import_configuration(files)):
        pass
    return path


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
                # Authored configuration is independent of the captured result.
                from yadinassi.database_context import SQLiteDBContext
                with tempfile.TemporaryDirectory() as directory:
                    path = create_database(Path(directory))
                    with SQLiteDBContext(path) as context:
                        actual = subject._execute(context)
                comparison = subject.compare_readback(actual, native_wire(capture['rows']))
                self.assertTrue(comparison['supported_match'])
                self.assertEqual(len(comparison['matched_ids']), 24)
                self.assertEqual(comparison['mismatched_ids'], [])
                self.assertEqual([c['runtime_status'] for c in comparison['excluded_controls']],
                                 ['action-error', 'action-error'])
                self.assertEqual([c['native_status'] for c in comparison['excluded_controls']], ['ok', 'ok'])

    def test_supported_mismatch_cannot_be_hidden_as_exclusion(self):
        rows = json.loads(CAPTURE.read_bytes())[0]['rows']
        original = native_wire(rows)
        rows[8]['value'] = 'WrongCatalog'
        result = subject.compare_readback(native_wire(rows), original)
        self.assertFalse(result['supported_match'])
        self.assertEqual(result['mismatched_ids'], [9])

    def test_public_helper_opens_sqlite_and_preserves_owned_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = create_database(Path(directory))
            original = path.read_bytes()
            rows = json.loads(CAPTURE.read_bytes())[0]['rows']
            result = subject.readback(path, native_wire=native_wire(rows))
            self.assertEqual(path.read_bytes(), original)
            self.assertTrue(result['comparison']['supported_match'])
            self.assertEqual(len(result['comparison']['matched_ids']), 24)

    def test_probe_source_change_rejected(self):
        with mock.patch.object(subject, 'PROBE_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                subject._execute(mock.Mock())

if __name__ == '__main__': unittest.main()

"""Inventory growth is source-hashed; no provenance/schema cap relaxation."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import test_native_1c_full_host as host_tests
from test_native_1c_full_host import full, SyntheticFilesystemCase

ROOT = Path(__file__).resolve().parents[1]
CODEC = 'yadinassi/storage/catalog_reference_uuid.py'
METADATA = ('yadinassi/metadata.py', 'yadinassi/storage/catalog_metadata.py')
DRIVERS = ('pyproject.toml', 'scripts/native_1c_full_host.py',
           'scripts/native_1c_smoke.py', 'scripts/native_1c_map_contract.py',
           'scripts/native_1c_tree_load_contract.py',
           'scripts/native_1c_tree_move_contract.py',
           'scripts/native_1c_tree_total_contract.py',
           'scripts/native_async_comparison.py', 'scripts/native_infobase_fixture.py')


def independent_hashes():
    # Include every non-cache package file, rejecting rather than omitting
    # unexpected suffixes. This mirrors the documented inventory domain, not
    # the production traversal or digest functions.
    paths = [p for p in (ROOT/'yadinassi').rglob('*')
             if not p.is_dir() and '__pycache__' not in p.parts]
    if any(p.suffix not in ('.py','.txt') for p in paths):
        raise AssertionError('unexpected runtime source')
    paths += [ROOT/p for p in DRIVERS]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


def provenance():
    with mock.patch.object(full.importlib.metadata,'version',
                           side_effect=lambda name:full.DEPENDENCIES[name]):
        return full.interpreter_provenance(ROOT)


class CodecProvenanceTests(SyntheticFilesystemCase):
    def test_actual_111_source_inventory_includes_format_and_metadata_and_recomputes_digest(self):
        hashes = independent_hashes()
        self.assertEqual(len(hashes),111)
        self.assertIn(CODEC,hashes)
        self.assertIn('yadinassi/data_io.py', hashes)
        self.assertIn('yadinassi/data_hashing.py', hashes)
        self.assertIn('yadinassi/json_processing.py', hashes)
        self.assertIn('yadinassi/file_io.py', hashes)
        self.assertIn('yadinassi/binary_streams.py', hashes)
        for name in ('regex_parser', 'regex_vm', 'regex_functions'):
            self.assertIn('yadinassi/' + name + '.py', hashes)
        self.assertIn('yadinassi/zip_archives.py', hashes)
        self.assertIn('yadinassi/catalogs.py', hashes)
        self.assertIn('yadinassi/catalog_types.py', hashes)
        self.assertIn('yadinassi/xml_io.py', hashes)
        self.assertIn('yadinassi/xml_writer.py', hashes)
        for name in ("documents.py", "document_types.py", "storage/config_document_binding.py",
                     "storage/config_document_metadata.py", "storage/config_document_records.py", "storage/document_reader.py"):
            self.assertIn("yadinassi/" + name, hashes)
        for name in ('document_lines.py','storage/config_document_sections.py',
                     'storage/config_document_lines_binding.py','storage/config_document_lines_records.py'):
            self.assertIn('yadinassi/'+name,hashes)
        for name in ('information_registers.py', 'storage/config_information_register_metadata.py',
                     'storage/config_information_register_binding.py', 'storage/config_information_register_records.py',
                     'storage/information_register_reader.py'):
            self.assertIn('yadinassi/'+name,hashes)
        self.assertIn('yadinassi/dom_nodes.py',hashes)
        self.assertIn('yadinassi/dom_io.py',hashes)
        # Current union adds five InformationRegister modules to reviewed DOM runtime106. This is an
        # exact source expectation, not the unchanged 512-file protocol cap.
        self.assertIn('yadinassi/value_tree_sort.py',hashes)
        self.assertIn('yadinassi/formatting.py',hashes)
        for name in METADATA:
            self.assertIn(name, hashes)
        value = provenance()
        expected = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(value['source_file_count'],111)
        self.assertEqual(value['source_sha256'],expected)
        self.assertEqual(value['comparison_driver_sha256'],hashes[DRIVERS[1]])
        self.assertEqual(value['map_contract_sha256'],hashes['scripts/native_1c_map_contract.py'])
        self.assertEqual((full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,32768))

    def test_codec_byte_drift_changes_only_aggregate_not_driver_identity(self):
        before = provenance()
        original = full.read_regular
        for source in (CODEC, 'yadinassi/formatting.py', 'yadinassi/json_processing.py', 'yadinassi/file_io.py', 'yadinassi/catalogs.py', 'yadinassi/catalog_types.py', 'yadinassi/xml_io.py', 'yadinassi/xml_writer.py', *METADATA):
            def changed(path, *args, **kwargs):
                raw = original(path,*args,**kwargs)
                return raw+b'\n' if path == ROOT/source else raw
            with self.subTest(source=source), mock.patch.object(full,'read_regular',side_effect=changed):
                after = provenance()
            self.assertNotEqual(before['source_sha256'],after['source_sha256'])
            self.assertEqual({k:v for k,v in before.items() if k!='source_sha256'},
                             {k:v for k,v in after.items() if k!='source_sha256'})


class CodecProvenanceFixtureScopeTests(unittest.TestCase):
    def test_windows_adapter_runs_both_provenance_assertions_and_is_restored(self):
        # Simulate only the existing test-fixture capability switch, not os.name.
        # A production-reader sentinel proves these assertions use the adapter.
        with mock.patch.object(host_tests, '_USE_SYNTHETIC_FILE_READER', True), \
                mock.patch.object(full, 'read_regular',
                                  side_effect=AssertionError('production reader called')) as original:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(CodecProvenanceTests)
            result = unittest.TestResult()
            suite.run(result)
            self.assertEqual(result.testsRun, 2)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.failures, [])
            self.assertEqual(result.skipped, [])
            self.assertIs(full.read_regular, original)
            original.assert_not_called()

    def test_posix_setup_keeps_production_reader_unchanged(self):
        original = full.read_regular
        case = CodecProvenanceTests('test_actual_111_source_inventory_includes_format_and_metadata_and_recomputes_digest')
        with mock.patch.object(host_tests, '_USE_SYNTHETIC_FILE_READER', False):
            try:
                case.setUp()
                self.assertIs(full.read_regular, original)
            finally:
                case.doCleanups()
        self.assertIs(full.read_regular, original)

    def test_windows_adapter_rejection_is_not_swallowed_and_cleanup_restores_reader(self):
        original = full.read_regular
        case = CodecProvenanceTests('test_actual_111_source_inventory_includes_format_and_metadata_and_recomputes_digest')
        with mock.patch.object(host_tests, '_USE_SYNTHETIC_FILE_READER', True), \
                mock.patch.object(host_tests, 'read_synthetic_file',
                                  side_effect=full.FullError('invalid_private_file')) as rejected:
            try:
                case.setUp()
                with self.assertRaisesRegex(full.FullError, '^invalid_private_file$'):
                    provenance()
                rejected.assert_called()
            finally:
                case.doCleanups()
        self.assertIs(full.read_regular, original)

"""Synthetic header integration tests; no native 1C compatibility claim."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_snapshots as filesystem_fixtures
import protocol
import snapshots

stage = fixtures.stage
POSIX = filesystem_fixtures.POSIX_FILE_API


def header(version=(8, 3, 8, 0), pages=3, page_size=4096):
    return (b'1CDBMSV8' + bytes(version) + pages.to_bytes(4, 'little')
            + b'OPAQ' + page_size.to_bytes(4, 'little'))


class HeaderProtocolTests(unittest.TestCase):
    def setUp(self):
        self.report, _ = fixtures.fixture_report()

    def validate(self, value):
        return protocol.validate_report(protocol.encode(value), nonce=fixtures.NONCE,
                                        provenance=fixtures.provenance())

    def test_v2_preserves_lifecycle_and_opaque_artifacts(self):
        self.validate(self.report)
        self.assertEqual((protocol.SCHEMA, protocol.LANE), (2, 'native-file-db-oracle-v2'))
        self.assertEqual(len(self.report['stages']), 13)
        self.assertEqual(len(self.report['snapshots']), 11)
        self.assertEqual(len(self.report['comparisons']), 5)
        self.assertLess(len(protocol.encode(self.report)), protocol.MAX_REPORT_BYTES)
        for item in self.report['snapshots']:
            self.assertEqual(item['physical']['header']['status'], 'header_layout_match')
            self.assertEqual(item['physical']['page_analysis'], 'unsupported')
        for item in self.report['artifacts']:
            self.assertEqual(item['physical']['header'], 'unknown')
            self.assertEqual(set(item['physical']), {'bytes','sha256','header','page_analysis'})
        old = copy.deepcopy(self.report)
        old.update(schema=1, lane='native-file-db-oracle-v1')
        with self.assertRaises(snapshots.OracleError): self.validate(old)

    def test_hostile_header_objects_are_rejected(self):
        bad = [None, True, 'unknown', {'raw':'PRIVATE'}]
        original = self.report['snapshots'][0]['physical']['header']
        changes = [{'status':'valid_database'}, {'version':[8,3,8,True]},
                   {'version':[8,3,8,1]}, {'version':'8.3.8.0'},
                   {'version':(8,3,8,0)}, {'version':[8,3,8]},
                   {'page_size':True}, {'page_size':4096.0}, {'page_size':4097},
                   {'page_count':True}, {'page_count':0}, {'page_count':2},
                   {'page_count':4}, {'page_count':1 << 32},
                   {'raw':'PRIVATE'}, {'file_size':12288},
                   {'reason':None}, {'status':'unsupported_format'}]
        bad += [dict(original, **change) for change in changes]
        for value in bad:
            with self.subTest(value=value):
                # Validate the exact in-memory type too: JSON turns tuples into lists.
                physical = copy.deepcopy(self.report['snapshots'][0]['physical'])
                physical['header'] = value
                with self.assertRaises(snapshots.OracleError):
                    protocol.database_physical(physical)

    def test_old_format_page_size_and_cf_dt_shape_cannot_be_confused(self):
        physical = copy.deepcopy(self.report['snapshots'][0]['physical'])
        physical['header']['version'] = [8,2,14,0]
        protocol.database_physical(physical)
        physical['bytes'] = 3 * 8192
        physical['header']['page_size'] = 8192
        with self.assertRaises(snapshots.OracleError): protocol.database_physical(physical)
        physical = self.report['snapshots'][0]['physical']
        with self.assertRaises(snapshots.OracleError): protocol.physical(physical)
        with self.assertRaises(snapshots.OracleError):
            protocol.database_physical(self.report['artifacts'][0]['physical'])

    def test_unknown_and_invalid_headers_fail_without_bytes_or_guessing(self):
        for raw, size in ((header((8,3,8,1)),12288), (b'private native bytes',12288),
                          (header(),12289), (header(pages=4),12288),
                          (header(pages=2),8192)):
            with self.subTest(raw=raw), self.assertRaises(snapshots.OracleError) as caught:
                stage.database_header_facts(raw, size)
            self.assertEqual(str(caught.exception), 'invalid_header')
            self.assertEqual(vars(caught.exception), {'kind':'invalid_header'})

    def test_standalone_decoder_import_needs_only_standard_library(self):
        code = "import sys; sys.path.insert(0, sys.argv[1]); import filedb; " \
               "assert not any(n=='yadinassi' or n.startswith('yadinassi.') for n in sys.modules); " \
               "assert 'pyuca' not in sys.modules; assert 'prompt_toolkit' not in sys.modules; " \
               "assert filedb.decode_header(b'', 0).status.value == 'invalid_layout'"
        for staged in (False, True):
            with self.subTest(staged=staged), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp) if staged else ROOT / 'yadinassi/storage'
                if staged:
                    (directory / 'filedb.py').write_bytes((ROOT / 'yadinassi/storage/filedb.py').read_bytes())
                result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(directory)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejected_header_at_each_snapshot_preserves_failure_and_cleanup(self):
        for bad_snapshot in protocol.SNAPSHOTS:
            with self.subTest(snapshot=bad_snapshot):
                identity = fixtures.provenance()
                report = protocol.empty_report(fixtures.NONCE, identity)
                backend = fixtures.FixtureNative(identity)
                original = backend.freeze
                def freeze(database, identifier):
                    if identifier == bad_snapshot:
                        stage.database_header_facts(b'PRIVATE NATIVE INPUT', 12288)
                    return original(database, identifier)
                backend.freeze = freeze
                controller = stage.Controller(backend, report)
                backend.controller = controller
                result = controller.run()
                protocol.validate_report(protocol.encode(result), nonce=fixtures.NONCE,
                                         provenance=identity)
                self.assertEqual((result['status'], result['failure_kind']),
                                 ('failed', 'invalid_header'))
                self.assertEqual(result['failed_stage'], protocol.SNAPSHOT_STAGE[bad_snapshot])
                self.assertEqual([item['id'] for item in result['snapshots']],
                                 list(protocol.SNAPSHOTS[:protocol.SNAPSHOTS.index(bad_snapshot)]))
                self.assertEqual(result['artifacts'], [])
                self.assertEqual(backend.events[-1], ('cleanup',))
                self.assertNotIn(b'PRIVATE', protocol.encode(result))


@unittest.skipUnless(POSIX, 'Native Linux descriptor operations are unavailable')
class HeaderDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / 'offline.1CD'
        self.data = header() + b'\0' * (12288-24)
        self.path.write_bytes(self.data)
        self.addCleanup(self.temporary.cleanup)

    def test_prefix_is_from_same_descriptor_and_both_hash_passes(self):
        real_read, real_open = os.read, os.open
        payload_opens, reads, prefixes = [], [], []
        def opened(path, *args, **kwargs):
            descriptor = real_open(path, *args, **kwargs)
            if os.fspath(path) == self.path.name: payload_opens.append(descriptor)
            return descriptor
        def read(descriptor, amount):
            reads.append((descriptor, amount))
            return real_read(descriptor, min(amount, 7))
        def decoder(raw, size):
            prefixes.append((raw, size))
            return stage.database_header_facts(raw, size)
        with mock.patch.object(os, 'open', side_effect=opened), \
             mock.patch.object(os, 'read', side_effect=read):
            result = snapshots.file_summary(self.path, header_decoder=decoder)
        self.assertEqual(len(payload_opens), 1)
        self.assertEqual({fd for fd, _ in reads}, set(payload_opens))
        self.assertEqual({amount for _, amount in reads}, {snapshots.WINDOW_BYTES})
        self.assertEqual(prefixes, [(header(), len(self.data))])
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(result['header'], stage.database_header_facts(header(), len(self.data)))
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_differing_prefix_is_rejected_even_with_equal_mock_digest(self):
        calls = []
        def digest(descriptor, size, prefix):
            prefix.extend(header() if not calls else b'changed')
            calls.append(1)
            return 'a' * 64
        decoder = mock.Mock(side_effect=AssertionError('not verified'))
        with mock.patch.object(snapshots, '_digest', side_effect=digest), \
             self.assertRaises(snapshots.OracleError) as caught:
            snapshots.file_summary(self.path, header_decoder=decoder)
        self.assertEqual(caught.exception.kind, 'snapshot_changed')
        decoder.assert_not_called()

    def test_identity_failure_precedes_decoding(self):
        decoder = mock.Mock(side_effect=AssertionError('not verified'))
        with mock.patch.object(snapshots, '_unchanged', side_effect=snapshots.OracleError('snapshot_changed')), \
             self.assertRaises(snapshots.OracleError):
            snapshots.file_summary(self.path, header_decoder=decoder)
        decoder.assert_not_called()

    def test_generic_artifacts_never_decode(self):
        for raw in (b'CF bytes', b'DT bytes', header(), b''):
            self.path.write_bytes(raw)
            with mock.patch.object(stage, 'decode_header', side_effect=AssertionError('opaque')):
                result = snapshots.file_summary(self.path)
            self.assertEqual(result['header'], 'unknown')
            self.assertEqual(result['page_analysis'], 'unsupported')

    def test_frozen_destination_is_decoded_and_clone_stays_opaque(self):
        filesystem_fixtures.normalize_fixture_owners(self)
        source, frozen, clone = (self.root / name for name in ('live','frozen','clone'))
        source.mkdir()
        (source / snapshots.DATABASE_NAME).write_bytes(self.data)
        def cleanup():
            if frozen.exists():
                frozen.chmod(0o700)
                (frozen / snapshots.DATABASE_NAME).chmod(0o600)
        self.addCleanup(cleanup)
        decoder = mock.Mock(wraps=stage.database_header_facts)
        result = snapshots.freeze_database(source, frozen, quiescent=lambda: True,
                                           header_decoder=decoder)
        decoder.assert_called_once_with(header(), len(self.data))
        self.assertEqual(result['header']['page_count'], 3)
        self.assertEqual((frozen / snapshots.DATABASE_NAME).stat().st_mode & 0o222, 0)
        snapshots.clone_database(frozen, clone, budget_root=self.root)
        self.assertEqual(snapshots.file_summary(clone / snapshots.DATABASE_NAME)['header'], 'unknown')
        self.assertEqual((clone / snapshots.DATABASE_NAME).read_bytes(), self.data)


if __name__ == '__main__':
    unittest.main()

"""Offline tests for the unmeasured deletion-mark source and native route."""
from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/native_1c_bootstrap'))
from catalog_deletion_mark_behavior import fixture, route
import catalog_deletion_mark_suite as suite

spec = importlib.util.spec_from_file_location('catalog_deletion_host', ROOT / 'scripts/native_1c_catalog_deletion_mark_profile.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
NONCE = 'a' * 32


def wire(values, nonce=NONCE):
    prefix = 'CDM|' + nonce + '|'
    return (prefix + 'entered\n' + ''.join(prefix + str(i) + '|B|' + ('1' if v else '0') + '\n'
            for i, v in enumerate(values, 1)) + prefix + 'completed\n').encode('ascii')


def envelope():
    hashes = {name: host.FULL.digest((ROOT / name).read_bytes()) for name in host.staged_files()}
    raw = route.canonical([False] * 32)
    stage = suite.empty_report(NONCE)
    module = host.FULL.digest(host.FULL.generated_module(route.program(fixture.load_saved()[0], NONCE)))
    stage.update(status='ok', failure_kind='none', failure_phase='final', input_sha256=hashes,
                 source_sha256=host.SOURCE_SHA256, module_sha256=module, module_verified_sha256=module,
                 output_sha256=host.FULL.digest(raw), output_size=len(raw), record_count=32)
    for flag in host.FLAGS: stage[flag] = True
    stage['process_diagnostics'].update(stage='after_exit', reason='none')
    payload = {'schema': host.SCHEMA, 'profile': host.PROFILE, 'nonce': NONCE,
               'report': {'status': 'ok', 'native_tests_completed': True, 'stage3': stage},
               'outputs': [{'name': 'catalog-object.out', 'size': len(raw),
                            'sha256': host.FULL.digest(raw), 'data_b64': base64.b64encode(raw).decode()}]}
    return payload, hashes, raw


def identity(raw, **kwargs):
    return json.loads(raw)


class DeletionMarkPacketTests(unittest.TestCase):
    def test_source_hash_and_fixture(self):
        setup, assets = fixture.load_saved()
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(), route.SOURCE_SHA256)
        self.assertEqual(assets['generated/observe.bsl'], route.source())
        self.assertEqual(setup.name, 'OwnedCatalog4f4ccaa9')

    def test_source_tampering_fails(self):
        with mock.patch.object(Path, 'read_bytes', return_value=b'not the source'):
            with self.assertRaises(ValueError): route.source()

    def test_program_binds_setup_and_nonce(self):
        setup, _ = fixture.load_saved()
        data = route.program(setup, NONCE)
        self.assertIn(('CDM|' + NONCE + '|entered').encode(), data)
        self.assertIn(route.source(), data)
        self.assertLessEqual(len(data), route.MAX_OUTPUT)

    def test_program_rejects_bad_identity_and_nonce(self):
        setup, _ = fixture.load_saved()
        for nonce in ('', 'g' * 32, 'a' * 31):
            with self.assertRaises(ValueError): route.program(setup, nonce)
        with self.assertRaises(ValueError): route.program(object(), NONCE)

    def test_wire_roundtrip_all_32_boolean_observations(self):
        values = [i % 2 == 0 for i in range(route.COUNT)]
        self.assertEqual(route.parse_wire(wire(values), NONCE), values)
        self.assertEqual(json.loads(route.canonical(values)), values)

    def test_wire_rejects_wrong_nonce(self):
        with self.assertRaises(ValueError): route.parse_wire(wire([False] * 32), 'b' * 32)

    def test_wire_rejects_missing_and_extra_results(self):
        for n in (31, 33):
            with self.assertRaises(ValueError): route.parse_wire(wire([False] * n), NONCE)

    def test_wire_rejects_duplicate_number_and_invalid_type(self):
        raw = wire([False] * 32)
        for altered in (raw.replace(b'|2|B|0', b'|1|B|0'), raw.replace(b'|2|B|0', b'|2|N|0')):
            with self.assertRaises(ValueError): route.parse_wire(altered, NONCE)

    def test_wire_rejects_crlf_and_partial(self):
        raw = wire([False] * 32)
        for altered in (raw.replace(b'\n', b'\r\n'), raw[:-1]):
            with self.assertRaises(ValueError): route.parse_wire(altered, NONCE)

    def test_canonical_rejects_integers_and_wrong_length(self):
        for values in ([0] * 32, [False] * 31):
            with self.assertRaises(ValueError): route.canonical(values)

    def test_staging_binds_new_suite_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'staged'
            hashes = host.stage_inputs(ROOT, destination, host.SMOKE)
            self.assertEqual(hashes[host.SOURCE], route.SOURCE_SHA256)
            self.assertEqual((destination / 'bootstrap/catalog_object_suite.py').read_bytes(),
                             (ROOT / 'scripts/native_1c_bootstrap/catalog_deletion_mark_suite.py').read_bytes())
            host.validate_inputs(destination, hashes, host.SMOKE)

    def test_staging_detects_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'staged'
            hashes = host.stage_inputs(ROOT, destination, host.SMOKE)
            (destination / 'bootstrap/catalog_deletion_mark_behavior/observe.bsl').write_bytes(b'changed')
            with self.assertRaises(host.CatalogObjectError): host.validate_inputs(destination, hashes, host.SMOKE)


    def test_envelope_accepts_bound_32_observations(self):
        payload, hashes, raw = envelope()
        self.assertEqual(host.validate_envelope(json.dumps(payload).encode(), NONCE, hashes, identity)[1], raw)

    def test_envelope_rejects_mismatched_witnesses(self):
        payload, hashes, _ = envelope()
        for key, value in (('source_sha256', 'f' * 64), ('module_sha256', 'f' * 64),
                           ('record_count', 24), ('completed', False)):
            changed = copy.deepcopy(payload)
            changed['report']['stage3'][key] = value
            with self.assertRaises(host.CatalogObjectError):
                host.validate_envelope(json.dumps(changed).encode(), NONCE, hashes, identity)

    def test_envelope_fails_closed_without_output(self):
        payload, hashes, _ = envelope()
        payload['outputs'] = []
        payload['report'].update(status='stage3_failed', native_tests_completed=False)
        payload['report']['stage3'].update(status='failed', failure_kind='module_mismatch',
                                          failure_phase='enterprise', completed=False)
        with self.assertRaises(host.CatalogObjectError) as caught:
            host.validate_envelope(json.dumps(payload).encode(), NONCE, hashes, identity)
        self.assertEqual(caught.exception.native_failure['failure_phase'], 'enterprise')


if __name__ == '__main__': unittest.main()

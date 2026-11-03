"""Offline rights-variant checks; no native image or platform execution."""
from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/native_1c_bootstrap'))
from catalog_deletion_rights_behavior import fixture, route
from catalog_deletion_mark_behavior import route as control_route
from catalog_object_behavior import fixture as original
from native_1c_bootstrap.inject_modules import ROLE_FILES
from test_catalog_object_fixture import baseline
import catalog_deletion_rights_suite as suite

spec = importlib.util.spec_from_file_location('catalog_rights_host', ROOT / 'scripts/native_1c_catalog_deletion_rights_profile.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
NONCE = 'b' * 32


def prepared():
    return fixture.prepare(baseline())


def mutated_rights(files, old, new):
    result = dict(files)
    raw = result[ROLE_FILES[1]]
    if raw.count(old) != 1: raise AssertionError('mutation witness not unique')
    result[ROLE_FILES[1]] = raw.replace(old, new)
    return result


def envelope():
    hashes = {name: host.FULL.digest((ROOT/name).read_bytes()) for name in host.staged_files()}
    raw = route.canonical([False] * 32)
    stage = suite.empty_report(NONCE)
    module = host.FULL.digest(host.FULL.generated_module(route.program(fixture.load_saved()[0], NONCE)))
    stage.update(status='ok', failure_kind='none', failure_phase='final', input_sha256=hashes,
                 source_sha256=host.SOURCE_SHA256, module_sha256=module, module_verified_sha256=module,
                 output_sha256=host.FULL.digest(raw), output_size=len(raw), record_count=32)
    for flag in host.FLAGS: stage[flag] = True
    stage['process_diagnostics'].update(stage='after_exit', reason='none')
    payload = {'schema': host.SCHEMA, 'profile': host.PROFILE, 'nonce': NONCE,
               'report': {'status':'ok', 'native_tests_completed':True, 'stage3':stage},
               'outputs': [{'name':'catalog-object.out', 'size':len(raw),
                            'sha256':host.FULL.digest(raw), 'data_b64':base64.b64encode(raw).decode()}]}
    return payload, hashes, raw


def identity(raw, **kwargs): return json.loads(raw)


def read_windows_staging_fixture(path, limit, *, nonempty=False):
    """Bound owned Windows fixtures, without claiming Linux no-follow behavior."""
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError('link')
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError('file')
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
        after = path.lstat()
        key = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                            info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if key(before) != key(after) or len(data) != before.st_size or len(data) > limit or (nonempty and not data):
            raise ValueError('unstable')
        return data
    except (OSError, ValueError):
        raise host.FULL.FullError('invalid_private_file') from None


class CatalogDeletionRightsTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_windows_staging_fixture)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_exact_control_observation_source_and_program(self):
        setup, _ = fixture.load_saved()
        self.assertEqual(route.SOURCE_SHA256, control_route.SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(), route.SOURCE_SHA256)
        self.assertEqual(route.program(setup, NONCE), control_route.program(setup, NONCE))

    def test_profile_and_artifact_distinct(self):
        self.assertNotEqual(route.PROFILE, control_route.PROFILE)
        self.assertNotEqual(route.SCHEMA, control_route.SCHEMA)
        self.assertEqual(host.ARTIFACT, 'catalog-deletion-rights')

    def test_one_additional_right_only(self):
        files = baseline()
        setup, control = original.prepare(files)
        setup2, candidate = fixture.prepare(files)
        self.assertEqual(setup, setup2)
        for path in control:
            if path != ROLE_FILES[1]: self.assertEqual(control[path], candidate[path])
        marker = b'<right><name>Delete</name><value>true</value></right>'
        self.assertEqual(candidate[ROLE_FILES[1]].count(marker), 1)
        self.assertEqual(candidate[ROLE_FILES[1]].replace(marker, b''), control[ROLE_FILES[1]])
        self.assertTrue(fixture.verify_catalog_rights(candidate, setup.name))

    def test_strict_redump_accepts_exact(self):
        _, expected = prepared()
        self.assertTrue(fixture.verify_redump(expected, dict(expected)))

    def test_missing_delete_is_rejected(self):
        _, expected = prepared()
        changed = mutated_rights(expected, b'<right><name>Delete</name><value>true</value></right>', b'')
        with self.assertRaises(ValueError): fixture.verify_redump(expected, changed)

    def test_false_delete_is_rejected(self):
        _, expected = prepared()
        changed = mutated_rights(expected, b'<name>Delete</name><value>true</value>', b'<name>Delete</name><value>false</value>')
        with self.assertRaises(ValueError): fixture.verify_redump(expected, changed)

    def test_unexpected_and_duplicate_grants_rejected(self):
        _, expected = prepared()
        marker = b'<right><name>Delete</name><value>true</value></right>'
        for extra in (marker, b'<right><name>View</name><value>true</value></right>'):
            changed = mutated_rights(expected, marker, marker+extra)
            with self.assertRaises(ValueError): fixture.verify_redump(expected, changed)

    def test_wrong_target_rejected(self):
        setup, expected = prepared()
        changed = mutated_rights(expected, ('Catalog.'+setup.name).encode(), b'Catalog.Foreign')
        with self.assertRaises(ValueError): fixture.verify_redump(expected, changed)

    def test_other_metadata_changes_rejected(self):
        _, expected = prepared()
        changed = dict(expected)
        changed['Ext/SessionModule.bsl'] += b'UnexpectedCode();'
        with self.assertRaises(ValueError): fixture.verify_redump(expected, changed)

    def test_untrusted_baseline_rejected(self):
        files = baseline()
        files['Configuration.xml'] = files['Configuration.xml'].replace(b'<Role>', b'<Catalog>X</Catalog><Role>')
        with self.assertRaises(ValueError): fixture.prepare(files)

    def test_wire_and_32_booleans_remain_identical(self):
        values = [n % 2 == 0 for n in range(32)]
        self.assertEqual(route.canonical(values), control_route.canonical(values))
        with self.assertRaises(ValueError): route.canonical(values[:-1])

    def test_staging_binds_distinct_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp).resolve()/'stage'
            hashes = host.stage_inputs(ROOT, staged, host.SMOKE)
            self.assertEqual(hashes[host.SOURCE], control_route.SOURCE_SHA256)
            self.assertIn('scripts/catalog_deletion_rights_behavior/fixture.py', hashes)
            self.assertEqual((staged/'bootstrap/catalog_object_suite.py').read_bytes(),
                             (ROOT/'scripts/native_1c_bootstrap/catalog_deletion_rights_suite.py').read_bytes())
            host.validate_inputs(staged, hashes, host.SMOKE)

    def test_staging_detects_rights_fixture_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp).resolve()/'stage'
            hashes = host.stage_inputs(ROOT, staged, host.SMOKE)
            (staged/'bootstrap/catalog_deletion_rights_behavior/fixture.py').write_bytes(b'changed')
            with self.assertRaises(host.CatalogObjectError): host.validate_inputs(staged, hashes, host.SMOKE)

    def test_envelope_requires_variant_identity_and_redump(self):
        payload, hashes, raw = envelope()
        self.assertEqual(host.validate_envelope(json.dumps(payload).encode(), NONCE, hashes, identity)[1], raw)
        for key, value in (('profile', control_route.PROFILE), ('schema', control_route.SCHEMA)):
            changed = copy.deepcopy(payload); changed[key] = value
            with self.assertRaises(host.CatalogObjectError):
                host.validate_envelope(json.dumps(changed).encode(), NONCE, hashes, identity)
        changed = copy.deepcopy(payload); changed['report']['stage3']['config_verified'] = False
        with self.assertRaises(host.CatalogObjectError):
            host.validate_envelope(json.dumps(changed).encode(), NONCE, hashes, identity)


if __name__ == '__main__': unittest.main()

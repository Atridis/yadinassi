"""Inventory growth is source-hashed; no provenance/schema cap relaxation."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from test_native_1c_full_host import full

ROOT = Path(__file__).resolve().parents[1]
CODEC = 'yadinassi/storage/catalog_reference_uuid.py'
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


class CodecProvenanceTests(unittest.TestCase):
    def test_actual_77_source_inventory_includes_codec_and_recomputes_digest(self):
        hashes = independent_hashes()
        self.assertEqual(len(hashes),77)
        self.assertIn(CODEC,hashes)
        value = provenance()
        expected = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(value['source_file_count'],77)
        self.assertEqual(value['source_sha256'],expected)
        self.assertEqual(value['comparison_driver_sha256'],hashes[DRIVERS[1]])
        self.assertEqual(value['map_contract_sha256'],hashes['scripts/native_1c_map_contract.py'])
        self.assertEqual((full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,32768))

    def test_codec_byte_drift_changes_only_aggregate_not_driver_identity(self):
        before = provenance()
        original = full.read_regular
        def changed(path, *args, **kwargs):
            raw = original(path,*args,**kwargs)
            return raw+b'\n' if path == ROOT/CODEC else raw
        with mock.patch.object(full,'read_regular',side_effect=changed):
            after = provenance()
        self.assertNotEqual(before['source_sha256'],after['source_sha256'])
        self.assertEqual({k:v for k,v in before.items() if k!='source_sha256'},
                         {k:v for k,v in after.items() if k!='source_sha256'})

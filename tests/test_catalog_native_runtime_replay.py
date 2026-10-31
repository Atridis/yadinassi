"""Native scalar replay over captured slots in synthetic transport, not full images.

The actual native job reruns the same blocks on immutable native .1CD clones.
Here the ordinary production row parser admits native bytes within a synthetic
container; only catalog identity metadata is rebound to each saved probe setup.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'scripts')]

from yadinassi import Interpreter
from yadinassi.storage.catalog_metadata import CatalogMetadataIdentity
from yadinassi.native_targets import LINUX_8_3_27_1508
from catalog_read_fixture import load, BLOCKS
from catalog_read_readback import compare
from test_catalog_slot_liveness import CAPTURE, read

PATH = Path(__file__).parent/'fixtures/catalog_read_slots/native_outputs.json'
OBSERVATIONS = json.loads(PATH.read_text(encoding='utf-8'))


class CatalogNativeRuntimeReplayTests(unittest.TestCase):
    def test_all_native_states_contexts_and_operations(self):
        self.assertEqual(hashlib.sha256(PATH.read_bytes()).hexdigest(),
                         '4fc432e8c8de4025c0d7243a75192ca7d6c98c03cde4df492f8fe9c88efdd6cc')
        self.assertEqual(OBSERVATIONS['report_sha256'], CAPTURE['report_sha256'])
        self.assertEqual(len(OBSERVATIONS['states']), 20)
        for state in OBSERVATIONS['states']:
            b, _, files = load(state['repeat'])
            results = {}
            for name, metadata_uuid in zip(b.setup.names, b.setup.metadata_ids):
                captured = next(case for case in CAPTURE['cases']
                                if (case['repeat'], case['state'], case['context'], case['catalog'])
                                == (state['repeat'], state['state'], state['context'], name))
                self.assertEqual(captured['postimage'], state['postimage'])
                admitted = read(bytes.fromhex(''.join(captured['slots'])))
                results[name] = NS(identity=NS(name=name, metadata_uuid=metadata_uuid),
                                   binding=admitted.binding, rows=admitted.rows)

            class Context:
                def connection_string(self):
                    raise AssertionError('unexpected connection-string access')
                def catalog_metadata(self):
                    return tuple(CatalogMetadataIdentity(x.identity.metadata_uuid, name)
                                 for name, x in results.items())
                def catalog_rows(self, name):
                    return results[name]

            for block in BLOCKS:
                with self.subTest(repeat=state['repeat'], state=state['state'],
                                  context=state['context'], block=block):
                    output = []
                    vm = Interpreter(output.append, database_context=Context(),
                                     native_target=LINUX_8_3_27_1508)
                    try:
                        vm.execute(files[block+'.bsl'].decode('utf-8'))
                    finally:
                        vm.close()
                    raw = ('\n'.join(output)+'\n').encode('ascii')
                    compared = compare(raw, state['outputs'][block].encode('ascii'), b, block)
                    self.assertTrue(compared['matched'], compared)
                    # Fresh raw output is never normalized or byte-compared:
                    # compare() checks native and replay relational witnesses.

if __name__ == '__main__': unittest.main()

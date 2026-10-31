"""Native slot bytes in synthetic transport; not full native image replay."""
import json
import hashlib
from pathlib import Path
import unittest
from unittest import mock
import test_native_catalog_description_physical as fixture
from yadinassi.storage import catalog_reader as entry
from yadinassi.storage.filedb_catalog import CatalogError

CAPTURE_BYTES = (Path(__file__).parent/'fixtures/catalog_read_slots/native_slots.json').read_bytes()
CAPTURE = json.loads(CAPTURE_BYTES)


def image(raw):
    value = fixture.source(8, 'Alpha')
    value.page(40)[16:24] = len(raw).to_bytes(8, 'little')
    value.page(43)[:] = bytes(fixture.fixture.P)
    value.page(43)[:len(raw)] = raw
    return value


def read(raw):
    value = image(raw)
    return entry.read_catalog_rows(value.read_at, value.size, catalog_name='NativeOracleItems')


class CatalogSlotLivenessTests(unittest.TestCase):
    def test_native_all_repeats_contexts_catalogs_and_states(self):
        self.assertEqual(hashlib.sha256(CAPTURE_BYTES).hexdigest(), '0e5d967d22be1ff43b26f4bbc88ee5acddbaa25336f34f8897f993e7ecca5e96')
        self.assertEqual(CAPTURE['report_sha256'], '923a8c3f6e5cb529a4d7ffb864e87398ad831dff3150a95f7f0f81a6468cd7b3')
        self.assertEqual(hashlib.sha256((Path(__file__).parent/'fixtures/catalog_read_slots/native_slots.json').read_bytes()).hexdigest(),
                         '0e5d967d22be1ff43b26f4bbc88ee5acddbaa25336f34f8897f993e7ecca5e96')
        self.assertEqual(len(CAPTURE['cases']), 40)
        counts = {'empty': 0, 'one': 1, 'several': 3, 'deleted': 3, 'reused': 4}
        for case in CAPTURE['cases']:
            with self.subTest(repeat=case['repeat'], state=case['state'], context=case['context'], catalog=case['catalog']):
                rows = [bytes.fromhex(raw) for raw in case['slots']]
                self.assertTrue(all(len(raw) == case['record_size'] == 145 for raw in rows))
                result = read(b''.join(rows))
                self.assertEqual(len(result.rows), counts[case['state']])
                expected_slots = [n for n, raw in enumerate(rows) if n and raw[0] == 0]
                self.assertEqual([row.physical_record.slot for row in result.rows], expected_slots)
                marked = [row.physical_record.fields[2].value for row in result.rows]
                self.assertEqual(sum(marked), int(case['state'] in ('several', 'deleted', 'reused')))
                self.assertEqual([row.physical_record.raw for row in result.rows], [rows[n] for n in expected_slots])

    def test_free_head_coverage_and_no_decode_on_bad_liveness(self):
        case = next(c for c in CAPTURE['cases'] if c['state'] == 'deleted')
        baseline = bytearray.fromhex(''.join(case['slots']))
        edits = {
            'range': (1, (5).to_bytes(4, 'little')),
            'head_active': (1, (1).to_bytes(4, 'little')),
            'unlinked': (1, bytes(4)),
            'self_cycle': (2 * 145 + 1, (2).to_bytes(4, 'little')),
            'next_active': (2 * 145 + 1, (3).to_bytes(4, 'little')),
            'invalid_marker': (3 * 145, b'\x02'),
            'extra_free': (3 * 145, b'\x01'),
        }
        for name, (offset, patch) in edits.items():
            raw = baseline.copy(); raw[offset:offset + len(patch)] = patch
            with self.subTest(name=name), mock.patch.object(entry.row_reader, '_decode', side_effect=AssertionError('decoded before liveness')):
                with self.assertRaises(CatalogError):
                    read(bytes(raw))

    def test_free_record_body_is_opaque_not_a_logically_deleted_item(self):
        case = next(c for c in CAPTURE['cases'] if c['state'] == 'deleted')
        raw = bytearray.fromhex(''.join(case['slots']))
        raw[2 * 145 + 5:3 * 145] = b'\xff' * 140
        result = read(bytes(raw))
        self.assertEqual([row.physical_record.slot for row in result.rows], [1, 3, 4])
        self.assertEqual(len(result.rows), 3)

if __name__ == '__main__': unittest.main()

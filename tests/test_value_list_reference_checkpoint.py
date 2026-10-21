"""Instrumentation of pending native probes, not inferred native semantics."""
import hashlib
from pathlib import Path
import unittest

from scripts.native_1c_map_contract import RECORD_COUNT, SOURCE_SHA256, compare_collections
from scripts.native_historical_replay import FIELD_REFERENCE_BLOCKS, without_field_reference_probes
from yadinassi import Interpreter
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
CASES = ('value-ru', 'value-en', 'presentation-ru', 'presentation-en',
         'check-ru', 'check-en', 'value-val', 'presentation-val', 'check-val',
         'live', 'same-nested', 'write-throw', 'coercions', 'invalid-write',
         'receiver-once', 'reorder-delete', 'cache', 'missing-property',
         'invalid-receiver', 'function-result')


class ValueListReferenceCheckpointTests(unittest.TestCase):
    def test_only_unique_new_blocks_and_all_observations(self):
        source = SOURCE.read_text(encoding='utf-8-sig')
        for start, end in FIELD_REFERENCE_BLOCKS:
            self.assertEqual(source.count(start), 1)
            self.assertEqual(source.count(end), 1)
        parse(source)
        old = without_field_reference_probes(source)
        self.assertNotIn('list.reference.', old)
        body = source.split(FIELD_REFERENCE_BLOCKS[1][0])[1].split(FIELD_REFERENCE_BLOCKS[1][1])[0]
        for case in CASES:
            self.assertEqual(body.count('"list.reference.' + case + '"'), 1)
        self.assertEqual(body.count('НаблюдатьТаблицы('), len(CASES))
        self.assertEqual(body.count('table.list.reference.checkpoint.complete: [ok]'), 1)

    def test_current_count_hash_and_every_added_record_is_byte_exact(self):
        source = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(source).hexdigest(), SOURCE_SHA256)
        messages = []
        Interpreter(messages.append).execute(source.decode('utf-8-sig'))
        self.assertEqual(len(messages), RECORD_COUNT)
        raw = ('\n'.join(messages) + '\n').encode()
        self.assertEqual(compare_collections(raw, raw, SOURCE_SHA256)['status'], 'equivalent')
        for index, message in enumerate(messages):
            if not message.startswith('table.list.reference.'):
                continue
            changed = list(messages)
            changed[index] = message.replace(': [', ': [changed', 1)
            result = compare_collections(raw, ('\n'.join(changed) + '\n').encode(), SOURCE_SHA256)
            self.assertEqual(result['reason'], 'ineligible_difference', message)


if __name__ == '__main__':
    unittest.main()

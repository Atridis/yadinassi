"""Descriptor-key probe integrity; offline execution is not native evidence."""
from pathlib import Path
import hashlib
import unittest

from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'f8a5be47e937e39500c51a2b9c8fdaaf4becd68aa908cf7e99abe068a6c8cd4a'
PAIRS = ('same-object', 'equal-empty', 'equal-number', 'equal-reordered',
         'equal-copy', 'unequal-types', 'unequal-number-qualifiers',
         'unequal-string-qualifiers')


def source_lf(raw):
    # Test checkout portability only. Production adapter continues raw-byte pins.
    return raw.decode('utf-8-sig').replace('\r\n', '\n')


def inverse(text):
    begin = '// Begin descriptor Map-key checkpoint helpers.\n'
    end = '// End descriptor Map-key checkpoint helpers.\n\n'
    first, rest = text.split(begin)
    _, rest = rest.split(end)
    baseline, addition = (first + rest).split('// Begin descriptor Map-key checkpoint observations.\n')
    if not addition.endswith('// End descriptor Map-key checkpoint observations.\n'):
        raise AssertionError('unexpected checkpoint suffix')
    return baseline


class DescriptorMapCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
        cls.source = source_lf(cls.raw)
        cls.original = inverse(cls.source)
        cls.messages = []
        Interpreter(output=cls.messages.append).execute(cls.source)

    def test_original_source_exact_inverse_lf_and_crlf_checkout(self):
        lf = self.source.encode('utf-8-sig')
        for raw in (lf, lf.replace(b'\n', b'\r\n')):
            restored = inverse(source_lf(raw)).encode('utf-8-sig')
            self.assertEqual(hashlib.sha256(restored).hexdigest(), BASE_SHA)
        self.assertEqual(hashlib.sha256(self.original.encode('utf-8-sig')).hexdigest(), BASE_SHA)

    def test_historical_replay_inverse_is_source_bound(self):
        from scripts.native_historical_replay import without_descriptor_map_probes, historical_collections_source, git_blob, HISTORICAL_COLLECTIONS_BLOB
        self.assertEqual(without_descriptor_map_probes(self.source), self.original)
        golden = (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes()
        for raw in (self.source.encode('utf-8-sig'), self.source.replace('\n', '\r\n').encode('utf-8-sig')):
            restored = historical_collections_source(raw, golden)
            self.assertEqual(git_blob(restored), HISTORICAL_COLLECTIONS_BLOB)
        for mutant in (self.source + '\n', self.source.replace('array.shift', 'array.altered', 1),
                       self.source.replace('// End descriptor Map-key checkpoint helpers.', '// changed', 1)):
            with self.assertRaises(ValueError):
                without_descriptor_map_probes(mutant)

    def test_original_797_messages_are_byte_exact(self):
        old = []
        Interpreter(output=old.append).execute(self.original)
        self.assertEqual(len(old), 797)
        self.assertEqual(self.messages[:797], old)
        self.assertEqual(len(self.messages), 828)

    def test_bounded_matrix_complete_without_setup_or_serialization_failures(self):
        labels = []
        for pair in PAIRS:
            for mode in ('equality', 'mutable', 'fixed-copy'):
                labels.append(f'table.descriptor-key.{mode}.{pair}')
        for variant in ('single', 'unequal', 'duplicate-equal'):
            for kind in ('mutable', 'fixed'):
                labels.append(f'table.descriptor-key.codec-{kind}-{variant}')
        labels.append('table.descriptor-key.checkpoint.complete')
        self.assertEqual([m.split(':', 1)[0] for m in self.messages[797:]], labels)
        for message in self.messages[797:]:
            self.assertNotIn('setup-error', message)
            self.assertNotIn('[serialize-error]', message)
            self.assertFalse(message.endswith(': [error]'), message)
        self.assertEqual(self.messages[-1], 'table.descriptor-key.checkpoint.complete: [ok]')

    def test_audited_runtime_histories_keep_each_operation_observable(self):
        # Exact native payload and value semantics are pinned in runtime tests.
        # This source-contract test retains independently visible steps.
        histories = [m for m in self.messages[797:-1] if '.equality.' not in m]
        self.assertEqual(len(histories), 22)
        for message in histories:
            self.assertIn('insert-first:ok:', message)
            self.assertIn('count-first:ok:', message)
            self.assertIn('get-first:ok:', message)
            self.assertIn('get-second-before:ok:', message)
        for pair in PAIRS:
            message = next(m for m in histories if f'.mutable.{pair}:' in m)
            for step in ('insert-second', 'index-replace', 'delete-second', 'delete-first'):
                self.assertIn(step + ':ok:', message)
            self.assertIn('count-final:ok:', message)
            fixed = next(m for m in histories if f'.fixed-copy.{pair}:' in m)
            for step in ('fixed-count', 'copy-count', 'source-count', 'fixed-count-after'):
                self.assertIn(step + ':ok:', fixed)
        for message in histories:
            if '.codec-' in message:
                for step in ('codec-source-count', 'codec-write', 'codec-read', 'codec-count'):
                    self.assertIn(step + ':ok:', message)

    def test_no_new_map_iteration_or_order_normalization(self):
        helpers = self.source.split('// Begin descriptor Map-key checkpoint helpers.\n')[1].split('// End descriptor Map-key checkpoint helpers.')[0]
        self.assertEqual(helpers.count('Для Каждого'), 1)
        self.assertIn('Для Каждого Шаг Из Шаги Цикл', helpers)
        self.assertNotIn('Из Данные Цикл', helpers)
        from scripts import native_1c_map_contract as contract
        self.assertEqual(len(contract.ELIGIBLE_LABELS), 8)
        self.assertFalse(any('descriptor-key' in label for label in contract.ELIGIBLE_LABELS))


if __name__ == '__main__':
    unittest.main()

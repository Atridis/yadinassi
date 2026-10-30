"""Synthetic closed-marker1-chain mechanics, never native acceptance evidence."""
from dataclasses import replace
from itertools import permutations
import unittest

import test_filedb_named_file as f

c, n = f.c, f.n
POLICY = 'closed_marker1_chain_v1'
IDENTIFIER = 'params_dbnames_closed_marker1_chain_8380_8192_v1'


def profile():
    return n.DBNamesProfile(f.DECLARATIONS, '0', 0, slot_policy=POLICY)


def removed(next_slot=0, marker=1):
    # Deliberately invalid ordinary fields, independent from production codec.
    return bytes((marker,)) + next_slot.to_bytes(4, 'little') + b'\xff' * 296


def source(rows=None, head=0, marker=1, **kwargs):
    return f.named_source([f.named_row()] if rows is None else rows,
                          reserved=removed(head, marker), **kwargs)


def extract(value, **kwargs):
    return n.read_dbnames(value.read_at, value.size, profile=profile(), **kwargs)


class ClosedChainTests(unittest.TestCase):
    def test_profile_identity_default_and_keyword_only(self):
        default = n.DBNamesProfile(f.DECLARATIONS, '0', 0)
        self.assertEqual(default.slot_policy, 'reserved_and_active_v1')
        self.assertEqual(default.identifier, 'params_dbnames_8380_8192_v1')
        current = profile()
        self.assertEqual(current.identifier, IDENTIFIER)
        self.assertEqual(current.record_size, default.record_size)
        self.assertEqual(current.placements, default.placements)
        with self.assertRaises(TypeError):
            n.DBNamesProfile(f.DECLARATIONS, '0', 0, POLICY)
        class Text(str):
            pass
        for bad in (None, False, 1, [], '', 'other', Text(POLICY)):
            with self.subTest(value=repr(bad)), self.assertRaises(ValueError):
                n.DBNamesProfile(f.DECLARATIONS, '0', 0, slot_policy=bad)

    def test_default_strict_unchanged(self):
        value = source([f.named_row(), removed()], head=2)
        with self.assertRaisesRegex(c.UnsupportedLayout, 'dbnames_nonreserved_slot'):
            f.extract(value)
        # Legacy strict mode intentionally never interprets reserved link bytes.
        self.assertEqual(f.extract(source(head=0xffffffff)).data, b'hello')

    def test_profile_subclass_and_forgery_rejected_without_io(self):
        class Subclass(n.DBNamesProfile):
            pass
        forged = [Subclass(f.DECLARATIONS, '0', 0, slot_policy=POLICY)]
        for key, value in (('slot_policy', 'bogus'), ('identifier', 'bogus'),
                           ('record_size', 302), ('placements', ((0, 301),)),
                           ('declarations', ())):
            item = profile()
            object.__setattr__(item, key, value)
            forged.append(item)
        for item in forged:
            value = source()
            with self.subTest(profile=item), self.assertRaises(ValueError):
                n.read_dbnames(value.read_at, value.size, profile=item)
            self.assertEqual(value.calls, [])

    def test_forged_discriminator_hooks_never_run(self):
        class Hook:
            def __eq__(self, other):
                raise AssertionError('comparison hook executed')
            def __str__(self):
                raise AssertionError('string hook executed')
        for key in ('slot_policy', 'identifier', 'framing'):
            item = profile()
            object.__setattr__(item, key, Hook())
            value = source()
            with self.assertRaises(ValueError):
                n.read_dbnames(value.read_at, value.size, profile=item)
            self.assertEqual(value.calls, [])

    def test_hostile_string_and_metaclass_hooks_never_run(self):
        class Text(str):
            def __eq__(self, other):
                raise AssertionError('string equality hook executed')
            def __hash__(self):
                raise AssertionError('string hash hook executed')
        class Meta(type):
            def __eq__(cls, other):
                raise AssertionError('metaclass equality hook executed')
            def __hash__(cls):
                raise AssertionError('metaclass hash hook executed')
        class Profile(n.DBNamesProfile, metaclass=Meta):
            pass
        with self.assertRaises(ValueError):
            n.DBNamesProfile(f.DECLARATIONS, '0', 0, slot_policy=Text(POLICY))
        for item in (Profile(f.DECLARATIONS, '0', 0, slot_policy=POLICY), profile()):
            if type(item) is n.DBNamesProfile:
                object.__setattr__(item, 'slot_policy', Text(POLICY))
            value = source()
            with self.assertRaises(ValueError):
                n.read_dbnames(value.read_at, value.size, profile=item)
            self.assertEqual(value.calls, [])

    def test_forged_dict_colliding_key_rejected_without_hooks_or_io(self):
        calls = []
        class Key:
            def __hash__(self):
                calls.append('hash')
                return hash('slot_policy')
            def __eq__(self, other):
                calls.append('eq')
                raise AssertionError('colliding key equality executed')
        # Exactly eight entries: a length guard alone cannot reject this case.
        item = profile()
        stored = dict(object.__getattribute__(item, '__dict__'))
        del stored['slot_policy']
        stored[Key()] = POLICY
        self.assertEqual(len(stored), 8)
        object.__setattr__(item, '__dict__', stored)
        calls.clear()  # Fixture insertion legitimately hashes its key.
        value = source()
        with self.assertRaises(ValueError):
            n.read_dbnames(value.read_at, value.size, profile=item)
        self.assertEqual(calls, [])
        self.assertEqual(value.calls, [])

    def test_forged_dict_subclass_and_metaclass_hooks_never_run(self):
        calls = []
        def forbidden(name):
            calls.append(name)
            raise AssertionError('stored dictionary hook executed')
        class Meta(type):
            def __eq__(cls, other):
                return forbidden('meta_eq')
            def __hash__(cls):
                return forbidden('meta_hash')
        class Stored(dict, metaclass=Meta):
            def __iter__(self):
                return forbidden('iter')
            def __len__(self):
                return forbidden('len')
            def get(self, key, default=None):
                return forbidden('get')
            def __eq__(self, other):
                return forbidden('eq')
            def __getitem__(self, key):
                return forbidden('getitem')
        item = profile()
        stored = Stored(object.__getattribute__(item, '__dict__'))
        object.__setattr__(item, '__dict__', stored)
        calls.clear()
        value = source()
        with self.assertRaises(ValueError):
            n.read_dbnames(value.read_at, value.size, profile=item)
        self.assertEqual(calls, [])
        self.assertEqual(value.calls, [])

    def test_forged_stored_key_count_and_domain(self):
        for change in ('missing', 'extra', 'same_count_wrong_key'):
            item = profile()
            stored = dict(object.__getattribute__(item, '__dict__'))
            if change != 'extra':
                del stored['slot_policy']
            if change != 'missing':
                stored['unexpected'] = POLICY
            object.__setattr__(item, '__dict__', stored)
            value = source()
            with self.subTest(change=change), self.assertRaises(ValueError):
                n.read_dbnames(value.read_at, value.size, profile=item)
            self.assertEqual(value.calls, [])

    def test_zero_one_and_many_permuted_chains(self):
        for size in (0, 1, 2, 3, 5, 31, 256):
            order = list(range(2, size + 2))[::-1]
            rows = [f.named_row()] + [None] * size
            for position, slot in enumerate(order):
                rows[slot - 1] = removed(order[position + 1] if position + 1 < size else 0)
            result = extract(source(rows, head=order[0] if order else 0))
            self.assertEqual(result.data, b'hello')
            self.assertEqual(result.profile_id, IDENTIFIER)
            self.assertEqual(result.usage.slots, size + 2)
        for order in permutations((1, 3, 4)):
            rows = [None, f.named_row(), None, None]
            for index, slot in enumerate(order):
                rows[slot - 1] = removed(order[index + 1] if index < 2 else 0)
            self.assertEqual(extract(source(rows, head=order[0])).data, b'hello')

    def test_all_rejected_chain_classes_before_blob(self):
        cases = [([f.named_row()], 2, 'reference'),
                 ([f.named_row()], 0xffffffff, 'reference'),
                 ([f.named_row()], 1, 'zero_target'),
                 ([f.named_row(), removed(2)], 2, 'cycle'),
                 ([f.named_row(), removed(3), removed(2)], 2, 'cycle'),
                 ([f.named_row(), removed(99)], 2, 'reference'),
                 ([f.named_row(), removed(1)], 2, 'zero_target'),
                 ([f.named_row(), removed()], 0, 'unlinked'),
                 ([f.named_row(), removed(), removed()], 2, 'unlinked')]
        for rows, head, suffix in cases:
            value = source(rows, head=head)
            with self.subTest(suffix=suffix), self.assertRaisesRegex(
                    c.UnsupportedLayout, 'dbnames_chain_' + suffix):
                extract(value)
            self.assertFalse(any(offset // f.P in (6, 8) for offset, _ in value.calls))

    def test_markers_reserved_and_later_exact(self):
        for marker in (0, 2, 255):
            with self.assertRaisesRegex(c.UnsupportedLayout, 'dbnames_reserved_slot'):
                extract(source(marker=marker))
        for marker in (2, 255):
            with self.assertRaisesRegex(c.UnsupportedLayout, 'dbnames_nonreserved_slot'):
                extract(source([f.named_row(), removed(marker=marker)], head=2))

    def test_removed_stale_dbnames_and_invalid_payload_not_decoded(self):
        stale = bytearray(f.named_row('DBNames', marker=1))
        stale[1:5] = bytes(4)
        stale[276:301] = b'\xff' * 25
        value = source([bytes(stale), f.named_row()], head=1)
        self.assertEqual(extract(value).data, b'hello')
        # Reads into the removed row are only its marker and four-byte link.
        calls = [(offset - 20 * f.P - 301, length) for offset, length in value.calls
                 if 20 * f.P + 301 <= offset < 20 * f.P + 602]
        self.assertEqual(calls, [(0, 1), (1, 4)])

    def test_active_duplicates_and_malformed_tail_before_blob(self):
        bad = bytearray(f.named_row('x')); bad[1:3] = (129).to_bytes(2, 'little')
        utf16 = bytearray(f.named_row('x')); utf16[3:5] = b'\x00\xd8'
        for row, kind, code in ((f.named_row('dbnames'), c.InvalidStructure, 'dbnames_duplicate'),
                                (bytes(bad), c.InvalidStructure, 'dbnames_filename_length'),
                                (bytes(utf16), c.UnsupportedLayout, 'dbnames_filename_encoding')):
            value = source([f.named_row(), removed(), row], head=2)
            with self.assertRaisesRegex(kind, code):
                extract(value)
            self.assertFalse(any(offset // f.P in (6, 8) for offset, _ in value.calls))

    def test_cross_page_and_max_slots(self):
        rows = [f.named_row('x' * 128)] * 28 + [removed(), f.named_row()]
        self.assertEqual(extract(source(rows, head=29)).data, b'hello')
        rows = [f.named_row()] + [removed(slot + 1) for slot in range(2, 4095)] + [removed()]
        value = source(rows, head=2)
        self.assertEqual(extract(value).usage.slots, 4096)
        with self.assertRaisesRegex(c.ResourceLimit, 'dbnames_slots'):
            extract(source([f.named_row(), removed()], head=2), limits=n.NamedFileLimits(max_slots=2))

    def test_shared_mapping_ownership_rejected(self):
        value = source([f.named_row(), removed()], head=2)
        f.internal(value, 6, f.P, (20,))
        with self.assertRaises(c.UnsupportedSharing):
            extract(value)

    def test_cumulative_exact_budget_boundaries(self):
        result = extract(source([f.named_row(), removed(3), removed()], head=2))
        for key in ('output_bytes', 'bytes_processed', 'read_bytes', 'page_reads'):
            count = getattr(result.usage.catalog, key)
            limits = replace(c.CatalogLimits(), **{'max_' + key: count})
            self.assertEqual(extract(source([f.named_row(), removed(3), removed()], head=2),
                                     catalog_limits=limits).data, b'hello')
            with self.subTest(budget=key), self.assertRaises(c.ResourceLimit):
                extract(source([f.named_row(), removed(3), removed()], head=2),
                        catalog_limits=replace(limits, **{'max_' + key: count - 1}))

    def test_failure_consumes_same_catalog_attempt(self):
        value = source([f.named_row(), removed(2)], head=2)
        reader = c.CatalogReader(value.read_at, value.size)
        catalog = reader.read_catalog()
        with self.assertRaisesRegex(c.UnsupportedLayout, 'dbnames_chain_cycle'):
            n._read_dbnames_from_catalog(reader, catalog, profile=profile())
        before = reader.usage
        with self.assertRaises(ValueError):
            n._read_dbnames_from_catalog(reader, catalog, profile=profile())
        self.assertEqual(reader.usage, before)


if __name__ == '__main__':
    unittest.main()

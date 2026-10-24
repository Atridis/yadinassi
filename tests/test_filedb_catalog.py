"""Independent synthetic mechanics; no native compatibility claims or fixtures."""
from dataclasses import FrozenInstanceError
import importlib.util
import io
import os
from pathlib import Path
import random
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

# Load independently of yadinassi.__init__, which imports the existing runtime.
_spec = importlib.util.spec_from_file_location(
    "filedb_catalog_test_subject",
    Path(__file__).resolve().parents[1] / "yadinassi" / "storage" / "filedb_catalog.py")
c = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = c
_spec.loader.exec_module(c)


P = 8192


def u32(value):
    return value.to_bytes(4, 'little')


def descriptor(name='Physical', field_type='Undocumented', files=(0, 0, 0), fields=None,
               format_item='0', indexes='{"Indexes",{"Raw",1,{"Field",13}}}', suffix=b''):
    if fields is None:
        fields = '{"Field","' + field_type + '",1,17,3,"CS"}'
    text = ('{"' + name + '",' + format_item + ',{"Fields"' + (',' + fields if fields else '')
            + '},' + indexes + ',{"Recordlock","1"},{"Files",'
            + ','.join(str(value) for value in files) + '}}')
    return text.encode('utf-8') + suffix


class Source:
    """Sparse synthetic physical file, never a native or redistributed fixture."""

    def __init__(self, data_pages=(3,), length=P, fat_level=0, fat_pages=(4,), page_count=None):
        self.mapping = tuple(data_pages)
        self.length = length
        self.page_count = page_count or max((2, *data_pages, *fat_pages)) + 1
        self.size = self.page_count * P
        self.pages = {}
        self.calls = []
        self.closed = False
        header = b'1CDBMSV8' + bytes((8, 3, 8, 0)) + u32(self.page_count) + b'abcd' + u32(P)
        self.page(0)[:24] = header
        root = self.page(2)
        root[:24] = b'\x1c\xfd' + fat_level.to_bytes(2, 'little', signed=True) + u32(7) + u32(8) + u32(9) + length.to_bytes(8, 'little')
        root[24:] = b'\xa5' * (P - 24)  # Unused pointer bytes are not required to be zero.
        pointers = data_pages if fat_level == 0 else fat_pages
        for index, page in enumerate(pointers):
            root[24 + index * 4:28 + index * 4] = u32(page)
        if fat_level == 1:
            for fat_index, page in enumerate(fat_pages):
                raw = self.page(page)
                raw[:] = b'\xb6' * P
                for index, target in enumerate(data_pages[fat_index * 2048:(fat_index + 1) * 2048]):
                    raw[index * 4:index * 4 + 4] = u32(target)

    def page(self, number):
        return self.pages.setdefault(number, bytearray(P))

    def read_at(self, offset, length):
        self.calls.append((offset, length))
        if offset < 0 or offset + length > self.size:
            raise AssertionError('reader requested an out-of-bounds physical range')
        result = bytearray()
        while length:
            page, within = divmod(offset, P)
            amount = min(length, P - within)
            result.extend(self.pages.get(page, bytes(P))[within:within + amount])
            offset += amount
            length -= amount
        return bytes(result)

    def close(self):
        self.closed = True

    def logical(self, offset, raw):
        while raw:
            index, within = divmod(offset, P)
            amount = min(len(raw), P - within)
            self.page(self.mapping[index])[within:within + amount] = raw[:amount]
            offset += amount
            raw = raw[amount:]

    def block(self, index, payload=b'', following=0, used=None):
        used = len(payload) if used is None else used
        raw = u32(following) + used.to_bytes(2, 'little') + payload
        self.logical(index * 256, raw.ljust(256, b'\xcc'))

    def chain(self, indices, payload):
        for position, block in enumerate(indices):
            chunk, payload = payload[:250], payload[250:]
            self.block(block, chunk, indices[position + 1] if position + 1 < len(indices) else 0)
        if payload:
            raise AssertionError('not enough synthetic chain blocks')

    def catalog(self, ids=(2,), locale=b'en_US', trailing=b''):
        payload = locale.ljust(32, b'\0') + len(ids).to_bytes(4, 'little', signed=True)
        payload += b''.join(u32(value) for value in ids) + trailing
        self.block(1, payload)

    def ready(self, descriptions=None):
        descriptions = descriptions if descriptions is not None else {2: descriptor()}
        self.catalog(tuple(descriptions))
        for index, raw in descriptions.items():
            self.block(index, raw)
        return self

    def read(self, **limits):
        return c.read_catalog(self.read_at, self.size, limits=c.CatalogLimits(**limits))

    def full_bytes(self):
        return self.read_at(0, self.size)


class CatalogLayoutTests(unittest.TestCase):
    def test_ordered_immutable_raw_schema_and_opaque_data(self):
        source = Source().ready({2: descriptor('Repeated', suffix=b'\x00\xffTAIL'),
                                 3: descriptor('Repeated', fields='{"Dup","X",-1,-2,-3,"?"},{"Dup","Q",0,0,0,""}',
                                               format_item='{"future",19}')})
        source.catalog((2, 3), trailing=b'\xfeCATALOG')
        result = source.read()
        self.assertEqual(result.capability, 'physical_schema_read_only')
        self.assertEqual(result.locale, 'en_US')
        self.assertEqual(result.header.opaque_word, b'abcd')
        self.assertEqual(result.root.version_words, (7, 8, 9))
        self.assertEqual(result.root.unused_header_pointers, b'\xa5' * (P - 28))
        self.assertEqual([table.name for table in result.tables], ['Repeated', 'Repeated'])
        self.assertEqual([field.name for field in result.tables[1].fields], ['Dup', 'Dup'])
        self.assertEqual(result.tables[0].fields[0].type_name, 'Undocumented')
        self.assertEqual(result.tables[1].format_item, ('future', 19))
        self.assertEqual(result.tables[1].fields[0].raw, ('Dup', 'X', -1, -2, -3, '?'))
        self.assertEqual(result.tables[0].raw_indexes, ('Indexes', ('Raw', 1, ('Field', 13))))
        self.assertEqual(result.tables[0].recordlock, '1')
        self.assertEqual(result.tables[0].trailing_descriptor_bytes, b'\x00\xffTAIL')
        self.assertEqual(result.trailing_catalog_bytes, b'\xfeCATALOG')
        for obj, name in ((result, 'locale'), (result.header, 'page_size'),
                          (result.root, 'fat_level'), (result.tables[0], 'name'),
                          (result.tables[0].fields[0], 'name'), (result.usage, 'tokens')):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, name, None)

    def test_logical_blob_ids_not_physical_header_pages(self):
        source = Source(data_pages=(4, 6), page_count=8, length=2 * P)
        source.catalog((31,))
        payload = descriptor(name='x' * 300)
        source.chain((31, 33), payload)
        result = source.read()
        self.assertEqual(result.tables[0].description_blob_id, 31)
        self.assertEqual(result.tables[0].name, 'x' * 300)
        self.assertIn((4 * P + 31 * 256, 256), source.calls)
        self.assertIn((6 * P + 256, 256), source.calls)
        self.assertNotIn((31 * P, P), source.calls)

    def test_catalog_chain_fragmentation_and_same_backing_page_allowed(self):
        source = Source(data_pages=(6, 4), length=2 * P, page_count=8)
        catalog = b'en\0'.ljust(32, b'\xff') + u32(1) + u32(2) + b'opaque' * 50
        source.chain((1, 32), catalog)
        source.block(2, descriptor())
        result = source.read()
        self.assertEqual(result.locale, 'en')
        self.assertEqual(result.trailing_catalog_bytes, b'opaque' * 50)
        self.assertEqual(result.usage.blob_visits, 3)
        self.assertEqual(result.root.data_page_count, 2)

    def test_files_are_range_checked_without_opening(self):
        source = Source(page_count=9).ready({2: descriptor(files=(5, 6, 7))})
        result = source.read()
        self.assertEqual(result.tables[0].files, (5, 6, 7))
        self.assertTrue(all(offset // P not in (5, 6, 7) for offset, length in source.calls))
        # There are intentionally no object signatures at these target pages.
        for page in (-1, 9, (1 << 32) - 1):
            with self.subTest(page=page), self.assertRaises(c.InvalidStructure):
                Source(page_count=9).ready({2: descriptor(files=(page, 0, 0))}).read()

    def test_version_and_page_size_dispatch(self):
        for version in ((8, 2, 14, 0), (8, 3, 8, 1), (8, 3, 9, 0)):
            source = Source().ready()
            source.page(0)[8:12] = bytes(version)
            with self.assertRaisesRegex(c.UnsupportedLayout, 'storage_version'):
                source.read()
            self.assertEqual(source.calls, [(0, 24)])
        for size in (0, 4096, 16384, (1 << 32) - 1):
            source = Source().ready()
            source.page(0)[20:24] = u32(size)
            with self.assertRaisesRegex(c.UnsupportedLayout, 'page_size'):
                source.read()

    def test_header_geometry_and_signatures(self):
        for offset, payload, error in ((0, b'BADMAGIC', c.InvalidStructure),
                                       (2 * P, b'\x1c\xff', c.UnsupportedLayout),
                                       (2 * P, b'??', c.InvalidStructure)):
            source = Source().ready()
            page, within = divmod(offset, P)
            source.page(page)[within:within + len(payload)] = payload
            with self.assertRaises(error):
                source.read()
        source = Source().ready()
        for size in (0, 8, 23, source.size - 1, source.size + P):
            with self.subTest(size=size), self.assertRaises(c.InvalidStructure):
                c.read_catalog(source.read_at, size)
        for level in (-1, 2, 255, 32767):
            source = Source().ready()
            source.page(2)[2:4] = level.to_bytes(2, 'little', signed=True)
            with self.assertRaises(c.UnsupportedLayout):
                source.read()

    def test_complete_fat1_catalog_ignores_reserved_block_zero(self):
        source = Source(data_pages=(7,), fat_level=1, fat_pages=(4,), page_count=9).ready()
        source.block(0, b'not the root catalog', following=(1 << 32) - 1, used=65535)
        result = source.read()
        self.assertEqual(result.root.fat_level, 1)
        self.assertEqual(result.tables[0].name, 'Physical')
        self.assertEqual(result.usage.blob_visits, 2)
        self.assertNotIn((7 * P, 256), source.calls)

    def test_empty_catalog_and_unused_data_are_not_scanned(self):
        source = Source().ready({})
        source.block(31, b'not referenced', following=31, used=65535)
        result = source.read()
        self.assertEqual(result.tables, ())
        self.assertEqual(result.usage.blob_visits, 1)
        self.assertEqual(len(source.calls), 3)

    def test_minimum_and_empty_root(self):
        source = Source(length=0)
        reader = c.CatalogReader(source.read_at, source.size)
        self.assertEqual(reader.root.read_range(0, 0), b'')
        with self.assertRaises(c.InvalidStructure):
            reader.read_catalog()
        source = Source(length=513)
        with self.assertRaisesRegex(c.InvalidStructure, 'unaligned_blob_store'):
            source.read()
        for size in (P, 2 * P):
            source = Source()
            source.page(0)[12:16] = u32(size // P)
            with self.assertRaisesRegex(c.InvalidStructure, 'missing_root_page'):
                c.read_catalog(source.read_at, size)


class InternalFileTests(unittest.TestCase):
    def test_fragmented_range_crosses_pages_and_excludes_padding(self):
        source = Source(data_pages=(5, 3), page_count=7, length=P + 8)
        source.logical(P - 3, b'abcdefghijk')
        reader = c.CatalogReader(source.read_at, source.size)
        self.assertEqual(reader.root.read_range(P - 3, 11), b'abcdefghijk')
        self.assertEqual(source.calls[-2:], [(5 * P + P - 3, 3), (3 * P, 8)])
        self.assertEqual(reader.root.read_range(P + 8, 0), b'')
        for offset, length in ((P + 8, 1), (P + 9, 0), (-1, 0), (0, -1), (0, 1 << 100)):
            before = list(source.calls)
            with self.assertRaises(c.InvalidStructure):
                reader.root.read_range(offset, length)
            self.assertEqual(source.calls, before)
        for value in (True, 1.0, '0'):
            with self.assertRaises(ValueError):
                reader.root.read_range(value, 0)

    def test_fat1_first_pointer_is_data_not_count_and_unused_nonzero(self):
        source = Source(data_pages=(7, 5), length=P + 3, fat_level=1, fat_pages=(4,), page_count=9)
        source.logical(P - 2, b'abcde')
        reader = c.CatalogReader(source.read_at, source.size)
        self.assertEqual(reader.root.read_range(P - 2, 5), b'abcde')
        self.assertEqual(reader.root.info.unused_fat_pointers, ((4, b'\xb6' * (P - 8)),))
        self.assertEqual(reader.root.info.unused_header_pointers, b'\xa5' * (P - 28))

    def test_fat1_second_intermediate_page_and_fragmentation(self):
        pages = tuple(range(5, 2054))
        pages = pages[-1:] + pages[1:-1] + pages[:1]
        source = Source(data_pages=pages, length=2049 * P, fat_level=1, fat_pages=(3, 4), page_count=2054)
        source.logical(2048 * P - 2, b'jump')
        reader = c.CatalogReader(source.read_at, source.size)
        self.assertEqual(reader.root.read_range(2048 * P - 2, 4), b'jump')
        self.assertEqual(reader.root.info.data_page_count, 2049)
        self.assertEqual(source.calls[1:4], [(2 * P, P), (3 * P, P), (4 * P, P)])
        self.assertEqual(len(reader.root.info.unused_fat_pointers), 1)
        self.assertEqual(reader.root.info.unused_fat_pointers[0][0], 4)

    def test_pointer_bounds_and_sharing_policy(self):
        for value, error in ((0, c.InvalidStructure), (1, c.UnsupportedSharing), (2, c.UnsupportedSharing),
                             (5, c.InvalidStructure), ((1 << 32) - 1, c.InvalidStructure)):
            source = Source(page_count=5)
            source.page(2)[24:28] = u32(value)
            with self.subTest(value=value), self.assertRaises(error):
                c.CatalogReader(source.read_at, source.size)
        with self.assertRaises(c.UnsupportedSharing):
            source = Source(data_pages=(3, 3), length=2 * P)
            c.CatalogReader(source.read_at, source.size)
        with self.assertRaises(c.UnsupportedSharing):
            source = Source(data_pages=(4,), fat_level=1, fat_pages=(4,))
            c.CatalogReader(source.read_at, source.size)
        with self.assertRaises(c.UnsupportedSharing):
            source = Source(data_pages=tuple(range(5, 2054)), length=2049 * P,
                            fat_level=1, fat_pages=(3, 3), page_count=2054)
            c.CatalogReader(source.read_at, source.size)
        # A data pointer to a later FAT page is rejected even before it is read.
        with self.assertRaises(c.UnsupportedSharing):
            source = Source(data_pages=(4,) + tuple(range(6, 2054)), length=2049 * P,
                            fat_level=1, fat_pages=(3, 4), page_count=2054)
            c.CatalogReader(source.read_at, source.size)

    def test_fat0_full_pointer_capacity_and_partial_last_page(self):
        pages = tuple(range(3, 2045))
        source = Source(data_pages=pages, length=2042 * P - 1, page_count=2045)
        source.logical(source.length - 1, b'Z')
        reader = c.CatalogReader(source.read_at, source.size)
        self.assertEqual(reader.root.info.unused_header_pointers, b'')
        self.assertEqual(reader.root.info.data_page_count, 2042)
        self.assertEqual(reader.root.read_range(source.length - 1, 1), b'Z')
        with self.assertRaises(c.InvalidStructure):
            reader.root.read_range(source.length, 1)

    def test_required_fat_pointer_bounds_are_checked(self):
        for where in ('header', 'data'):
            for value, error in ((0, c.InvalidStructure), (1, c.UnsupportedSharing),
                                 (2, c.UnsupportedSharing), (9, c.InvalidStructure)):
                source = Source(data_pages=(7,), fat_level=1, fat_pages=(4,), page_count=9)
                page, offset = (2, 24) if where == 'header' else (4, 0)
                source.page(page)[offset:offset + 4] = u32(value)
                with self.subTest(where=where, value=value), self.assertRaises(error):
                    c.CatalogReader(source.read_at, source.size)

    def test_address_capacity_and_mapping_budget_precede_allocation(self):
        for level, length in ((0, 2043 * P), (1, (2042 * 2048 + 1) * P), (0, (1 << 64) - 1)):
            source = Source(length=length, fat_level=level)
            with self.subTest(level=level, length=length), self.assertRaisesRegex(c.InvalidStructure, 'capacity'):
                c.CatalogReader(source.read_at, source.size)
            self.assertEqual(source.calls, [(0, 24), (2 * P, P)])
        source = Source(data_pages=(3, 5), length=2 * P, page_count=6)
        with self.assertRaisesRegex(c.ResourceLimit, 'mapping_pages'):
            c.CatalogReader(source.read_at, source.size, limits=c.CatalogLimits(max_mapping_pages=1))


class BlobAndDescriptorTests(unittest.TestCase):
    def test_cycles_including_zero_payload(self):
        for used in (0, 1):
            for edges in (((1, 1),), ((1, 2), (2, 1))):
                source = Source()
                for start, following in edges:
                    source.block(start, b'x' * used, following)
                with self.subTest(used=used, edges=edges), self.assertRaisesRegex(c.InvalidStructure, 'blob_chain_cycle'):
                    source.read()

    def test_blob_lengths_references_short_catalog_and_counts(self):
        for used in (251, 256, 65535):
            source = Source()
            source.block(1, used=used)
            with self.assertRaisesRegex(c.InvalidStructure, 'payload_length'):
                source.read()
        for following in (32, (1 << 32) - 1):
            source = Source()
            source.block(1, following=following)
            with self.assertRaisesRegex(c.InvalidStructure, 'next_reference'):
                source.read()
        for length in range(36):
            source = Source()
            source.block(1, b'\0' * length)
            with self.assertRaisesRegex(c.InvalidStructure, 'catalog_header_length'):
                source.read()
        for count in (-1, (1 << 31) - 1, 1):
            source = Source()
            source.block(1, b'\0' * 32 + count.to_bytes(4, 'little', signed=True))
            with self.assertRaises(c.InvalidStructure):
                source.read()
        for blob_id in (0, 32, (1 << 32) - 1):
            source = Source()
            source.catalog((blob_id,))
            with self.assertRaisesRegex(c.InvalidStructure, 'description_blob_reference'):
                source.read()

    def test_duplicate_ids_shared_tails_and_roles_are_policy_not_corruption(self):
        source = Source().ready()
        source.catalog((2, 2))
        with self.assertRaisesRegex(c.UnsupportedSharing, 'duplicate_description_id'):
            source.read()
        source = Source()
        source.catalog((0, 0))
        with self.assertRaisesRegex(c.InvalidStructure, 'description_blob_reference'):
            source.read()
        source = Source().ready()
        source.catalog((1,))
        with self.assertRaisesRegex(c.UnsupportedSharing, 'logical_blob_chain_overlap'):
            source.read()
        source = Source()
        source.catalog((2, 3))
        source.block(2, descriptor(), following=4)
        source.block(3, descriptor(), following=4)
        source.block(4)
        with self.assertRaisesRegex(c.UnsupportedSharing, 'logical_blob_chain_overlap'):
            source.read()
        for files in ((1, 0, 0), (2, 0, 0), (3, 0, 0), (5, 5, 0)):
            source = Source(page_count=7).ready({2: descriptor(files=files)})
            with self.subTest(files=files), self.assertRaises(c.UnsupportedSharing):
                source.read()
        source = Source(page_count=7).ready({2: descriptor(files=(5, 0, 0)), 3: descriptor(files=(5, 0, 0))})
        with self.assertRaises(c.UnsupportedSharing):
            source.read()

    def test_locale_is_bounded_utf8_and_preserves_opaque_padding(self):
        source = Source().ready()
        source.catalog(locale='Русский'.encode())
        self.assertEqual(source.read().locale, 'Русский')
        for locale, code in ((b'x' * 32, 'locale_terminator'), (b'\xff', 'locale_utf8')):
            source = Source().ready()
            source.catalog(locale=locale)
            with self.assertRaisesRegex(c.InvalidStructure, code):
                source.read()

    def test_quote_whitespace_utf8_and_raw_unknown_types(self):
        raw = descriptor(name='A""Б', field_type='Новое', format_item=' { -19, +3, {}, "C:\\folder" } ')
        source = Source().ready({2: b'\r\n\t' + raw + b' \r\n'})
        result = source.read().tables[0]
        self.assertEqual(result.name, 'A"Б')
        self.assertEqual(result.fields[0].type_name, 'Новое')
        self.assertEqual(result.format_item, (-19, 3, (), 'C:\\folder'))
        self.assertEqual(result.trailing_descriptor_bytes, b' \r\n')
        self.assertEqual(result.raw_descriptor, b'\r\n\t' + raw + b' \r\n')

    def test_incomplete_syntax_and_unfamiliar_structures(self):
        for raw in (b'{', b'{"unfinished', b'{"a" 1}', b'{1,}', b'{"\xff"}', b'{1,,2}'):
            with self.subTest(raw=raw), self.assertRaises(c.InvalidStructure):
                Source().ready({2: raw}).read()
        for raw in (b'{"a",0}', descriptor().replace(b'"Fields"', b'"Other"'),
                    descriptor().replace(b'"Recordlock","1"', b'"Recordlock",1'),
                    descriptor().replace(b'"Files",0,0,0', b'"Files",0,0'),
                    descriptor().replace(b'"Files",0,0,0', b'"Files","0",0,0'),
                    descriptor(fields='{"short"}'), descriptor(fields='{"x","N","0",0,0,""}'),
                    b'{true}', descriptor(name='A\\"B')):
            with self.subTest(raw=raw), self.assertRaises(c.UnsupportedLayout):
                Source().ready({2: raw}).read()

    def test_bounded_random_adversarial_descriptors_never_leak_parser_exceptions(self):
        rng = random.Random(1259)
        alphabet = b'{}",+-0123456789 \t\nabc\\\xff'
        for _ in range(200):
            raw = bytes(rng.choice(alphabet) for _ in range(rng.randrange(1, 180)))
            with self.assertRaises(c.CatalogError):
                Source().ready({2: raw}).read(max_tree_depth=8, max_tokens=200)


class BudgetAndOwnershipTests(unittest.TestCase):
    def test_exact_limits_and_one_below_for_all_cumulative_counters(self):
        baseline = Source().ready().read()
        for field in ('page_reads', 'read_bytes', 'bytes_processed', 'blob_visits',
                      'total_blob_bytes', 'tables', 'fields', 'tokens', 'output_bytes'):
            used = getattr(baseline.usage, field)
            with self.subTest(field=field):
                result = Source().ready().read(**{'max_' + field: used})
                self.assertEqual(getattr(result.usage, field), used)
                if used > 1:
                    with self.assertRaises(c.ResourceLimit):
                        Source().ready().read(**{'max_' + field: used - 1})
        source = Source().ready({2: descriptor(), 3: descriptor()})
        for field in ('tables', 'fields'):
            with self.assertRaisesRegex(c.ResourceLimit, field):
                source.read(**{'max_' + field: 1})

    def test_chain_string_integer_depth_and_token_caps(self):
        for limits in ({'max_catalog_bytes': 39}, {'max_description_bytes': len(descriptor()) - 1},
                       {'max_string_bytes': 3}, {'max_tree_depth': 1}, {'max_tokens': 1},
                       {'max_integer_digits': 1}):
            with self.subTest(limits=limits), self.assertRaises(c.ResourceLimit):
                Source().ready().read(**limits)
        self.assertEqual(len(Source().ready().read(max_catalog_bytes=40).tables), 1)
        nested = '{' * 70 + '0' + '}' * 70
        raw = descriptor(format_item=nested)
        source = Source()
        source.catalog((2,))
        source.chain((2, 3), raw)
        with self.assertRaisesRegex(c.ResourceLimit, 'tree_depth'):
            source.read()
        for raw in (descriptor(format_item='9' * 40), descriptor(name='x' * 100)):
            source = Source()
            source.catalog((2,))
            source.chain((2, 3), raw)
            with self.assertRaises(c.ResourceLimit):
                source.read(max_integer_digits=20, max_string_bytes=30)

    def test_visits_include_zero_payload_and_repeated_work_not_unique_pages(self):
        source = Source()
        for index in range(1, 12):
            source.block(index, following=index + 1)
        source.block(12)
        with self.assertRaisesRegex(c.ResourceLimit, 'blob_visits'):
            source.read(max_blob_visits=5)
        source = Source().ready()
        reader = c.CatalogReader(source.read_at, source.size, limits=c.CatalogLimits(max_page_reads=4))
        reader.root.read_range(256, 1)
        reader.root.read_range(256, 1)
        self.assertEqual(reader.usage.page_reads, 4)
        with self.assertRaisesRegex(c.ResourceLimit, 'page_reads'):
            reader.root.read_range(256, 1)
        self.assertEqual(len(source.calls), 4)

    def test_range_return_bytes_consume_cumulative_output_budget(self):
        source = Source().ready()
        baseline = c.CatalogReader(source.read_at, source.size).usage.output_bytes
        reader = c.CatalogReader(source.read_at, source.size,
                                 limits=c.CatalogLimits(max_output_bytes=baseline + 2))
        self.assertEqual(reader.root.read_range(0, 1), b'\0')
        self.assertEqual(reader.root.read_range(0, 1), b'\0')
        calls = len(source.calls)
        with self.assertRaisesRegex(c.ResourceLimit, 'output_bytes'):
            reader.root.read_range(0, 1)
        self.assertEqual(len(source.calls), calls)

    def test_limits_are_exact_finite_and_validated_before_callbacks(self):
        for field in c.CatalogLimits.__dataclass_fields__:
            for value in (True, False, 0, -1, 1.1, '3', None, 1 << 100):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    c.CatalogLimits(**{field: value})
        callback = mock.Mock()
        for size in (True, -1, 1.0, None):
            with self.assertRaises(ValueError):
                c.read_catalog(callback, size)
        with self.assertRaises(ValueError):
            c.read_catalog(callback, P, limits={})
        callback.assert_not_called()

    def test_borrowed_callback_never_closed_and_single_use(self):
        source = Source().ready()
        reader = c.CatalogReader(source.read_at, source.size)
        reader.read_catalog()
        with self.assertRaises(ValueError):
            reader.read_catalog()
        self.assertFalse(source.closed)
        stream = io.BytesIO(source.full_bytes())
        stream.seek(17)
        def positioned(offset, length):
            return stream.getbuffer()[offset:offset + length].tobytes()
        c.read_catalog(positioned, len(stream.getbuffer()))
        self.assertFalse(stream.closed)
        self.assertEqual(stream.tell(), 17)
        with self.assertRaises(c.ResourceLimit):
            c.read_catalog(source.read_at, source.size, limits=c.CatalogLimits(max_read_bytes=1))
        self.assertFalse(source.closed)

    def test_exact_reads_and_sanitized_errors(self):
        source = Source().ready()
        for response in (b'', b'x' * 25):
            with self.assertRaisesRegex(c.InvalidStructure, 'inexact_read'):
                c.read_catalog(lambda offset, length: response, source.size)
        for response in (None, bytearray(24), 'secret'):
            with self.assertRaisesRegex(c.SourceIOError, '^read_result_type$'):
                c.read_catalog(lambda offset, length: response, source.size)
        def broken(offset, length):
            raise OSError('private/path secret')
        with self.assertRaisesRegex(c.SourceIOError, '^read_failed$'):
            c.read_catalog(broken, source.size)
        for fail_at in range(4):
            calls = 0
            def shortened(offset, length):
                nonlocal calls
                raw = source.read_at(offset, length)
                calls += 1
                return raw[:-1] if calls == fail_at + 1 else raw
            with self.assertRaises(c.InvalidStructure):
                c.read_catalog(shortened, source.size)

    def test_path_owns_descriptor_read_only_and_closes_on_success_and_failure(self):
        source = Source().ready()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'offline.1CD'
            path.write_bytes(source.full_bytes())
            before = path.read_bytes()
            real_close = c.os.close
            with mock.patch.object(c.os, 'close', wraps=real_close) as closed:
                result = c.inspect_catalog(path)
                self.assertEqual(len(result.tables), 1)
                self.assertEqual(closed.call_count, 1)
            self.assertEqual(path.read_bytes(), before)
            with mock.patch.object(c.os, 'close', wraps=real_close) as closed:
                with self.assertRaises(c.ResourceLimit):
                    c.inspect_catalog(path, limits=c.CatalogLimits(max_read_bytes=1))
                self.assertEqual(closed.call_count, 1)
            with self.assertRaisesRegex(c.SourceIOError, '^file_io_failed$'):
                c.inspect_catalog(Path(folder) / 'missing-private-name')

    def test_path_seek_read_fallback_and_access_time_change(self):
        source = Source().ready()
        info = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600, st_size=source.size,
                    st_mtime_ns=3, st_ctime_ns=4, st_atime_ns=5)
        positions = []
        def seek(fd, offset, origin):
            positions.append(offset)
            self.assertEqual(origin, os.SEEK_SET)
        fake_os = SimpleNamespace(O_RDONLY=os.O_RDONLY, O_BINARY=getattr(os, 'O_BINARY', 0),
                                  O_NONBLOCK=getattr(os, 'O_NONBLOCK', 0), SEEK_SET=os.SEEK_SET,
                                  open=mock.Mock(return_value=71), close=mock.Mock(),
                                  fstat=mock.Mock(side_effect=[SimpleNamespace(**info),
                                                              SimpleNamespace(**dict(info, st_atime_ns=999))]),
                                  lseek=seek, read=lambda fd, length: source.read_at(positions[-1], length))
        with mock.patch.object(c, 'os', fake_os):
            self.assertEqual(c.inspect_catalog('private-offline-path').tables[0].name, 'Physical')
        fake_os.close.assert_called_once_with(71)
        self.assertEqual(fake_os.open.call_args.args[1] & os.O_RDWR, 0)
        self.assertEqual(len(positions), 4)

    def test_path_metadata_change_and_nonregular_rejected(self):
        source = Source().ready()
        info = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600, st_size=source.size,
                    st_mtime_ns=3, st_ctime_ns=4)
        for field in info:
            after = dict(info)
            after[field] += 1
            with mock.patch.object(c.os, 'open', return_value=71), \
                 mock.patch.object(c.os, 'fstat', side_effect=[SimpleNamespace(**info), SimpleNamespace(**after)]), \
                 mock.patch.object(c.os, 'pread', side_effect=lambda fd, length, offset: source.read_at(offset, length), create=True), \
                 mock.patch.object(c.os, 'close') as closed:
                with self.subTest(field=field), self.assertRaises(c.ChangedDuringRead):
                    c.inspect_catalog('not-a-real-path')
                closed.assert_called_once_with(71)
        nonregular = dict(info, st_mode=stat.S_IFIFO | 0o600)
        with mock.patch.object(c.os, 'open', return_value=71), \
             mock.patch.object(c.os, 'fstat', return_value=SimpleNamespace(**nonregular)), \
             mock.patch.object(c.os, 'close') as closed:
            with self.assertRaises(c.NotRegularFile):
                c.inspect_catalog('not-a-real-path')
            closed.assert_called_once_with(71)

    def test_standalone_stdlib_load_does_not_import_runtime(self):
        path = Path(c.__file__).resolve()
        code = ('import importlib.util, sys\n'
                'spec = importlib.util.spec_from_file_location("standalone_catalog", sys.argv[1])\n'
                'module = importlib.util.module_from_spec(spec)\n'
                'sys.modules[spec.name] = module\n'
                'spec.loader.exec_module(module)\n'
                'assert not any(n == "yadinassi" or n.startswith("yadinassi.") for n in sys.modules)\n'
                'assert module.CatalogLimits().max_tree_depth == 64\n')
        result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(path)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

"""Synthetic table-BLOB and raw-DEFLATE mechanics, not native evidence."""
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
from unittest import mock
import zlib

from test_filedb_catalog import P, Source, descriptor, u32

STORAGE = Path(__file__).resolve().parents[1] / "yadinassi" / "storage"
PACKAGE = "synthetic_named_transport"
pkg = ModuleType(PACKAGE)
pkg.__path__ = [str(STORAGE)]
sys.modules[PACKAGE] = pkg
for name in ("filedb_catalog", "filedb_named_file"):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, STORAGE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
c = sys.modules[PACKAGE + ".filedb_catalog"]
n = sys.modules[PACKAGE + ".filedb_named_file"]


def internal(value, header, length, pages, fats=()):
    raw = value.page(header)
    raw[:24] = b"\x1c\xfd" + bool(fats).to_bytes(2, "little") + bytes(12) + length.to_bytes(8, "little")
    raw[24:] = b"\xcc" * (P - 24)
    for i, page in enumerate(fats or pages):
        raw[24 + 4 * i:28 + 4 * i] = u32(page)
    for fi, fat in enumerate(fats):
        raw = value.page(fat)
        raw[:] = b"\xdd" * P
        for i, page in enumerate(pages[fi * 2048:(fi + 1) * 2048]):
            raw[4 * i:4 + 4 * i] = u32(page)


def source(*, blob_length=P, blob_pages=(8,), fats=(), blob_header=6, other=False,
           root_fat=False):
    value = Source(page_count=max(20, *(page + 1 for page in (*blob_pages, *fats))),
                   fat_level=int(root_fat))
    descriptions = {2: descriptor("Synthetic", fields="", files=(5, blob_header, 7))}
    if other:
        descriptions[3] = descriptor("Other", fields="", files=(12, 13, 14))
    value.ready(descriptions)
    internal(value, 5, 1, (9,))
    if blob_header:
        internal(value, blob_header, blob_length, blob_pages, fats)
    value.blob_mapping = blob_pages
    return value


def block(value, index, payload=b"", following=0, used=None):
    raw = (u32(following) + (len(payload) if used is None else used).to_bytes(2, "little")
           + payload).ljust(256, b"\xee")
    page, within = divmod(index * 256, P)
    value.page(value.blob_mapping[page])[within:within + 256] = raw


def opened(value, *, limits=None, catalog_limits=None):
    reader = c.CatalogReader(value.read_at, value.size, limits=catalog_limits)
    table = reader.read_catalog().tables[0]
    reader._open_table_data(table)
    blob = reader._open_table_blob(table)
    budget = n._TransportBudget(reader._budget, limits)
    return reader, blob, n._TableBlobStore(blob, budget), budget


def budget(**limits):
    return n._TransportBudget(c._Budget(c.CatalogLimits()), n._TransportLimits(**limits))


def compressed(raw, wbits=-15):
    encoder = zlib.compressobj(wbits=wbits)
    return encoder.compress(raw) + encoder.flush()


class TableBlobTests(unittest.TestCase):
    def test_identity_order_single_use_and_index_not_read(self):
        value = source(other=True)
        reader = c.CatalogReader(value.read_at, value.size)
        with self.assertRaises(ValueError):
            reader._open_table_blob(None)
        table, other = reader.read_catalog().tables
        count = len(value.calls)
        for wrong in (table, other, replace(table)):
            with self.assertRaises(ValueError):
                reader._open_table_blob(wrong)
        self.assertEqual(len(value.calls), count)
        reader._open_table_data(table)
        for wrong in (other, replace(table)):
            with self.assertRaises(ValueError):
                reader._open_table_blob(wrong)
        blob = reader._open_table_blob(table)
        self.assertEqual(blob.info.physical_header_page, 6)
        with self.assertRaises(ValueError):
            reader._open_table_blob(table)
        with self.assertRaises(ValueError):
            reader._open_table_data(table)
        self.assertNotIn(7, [offset // P for offset, length in value.calls])
        self.assertFalse(value.closed)

    def test_failed_data_open_cannot_authorize_blob(self):
        value = source()
        value.page(5)[:2] = b"??"
        reader = c.CatalogReader(value.read_at, value.size)
        table = reader.read_catalog().tables[0]
        with self.assertRaisesRegex(c.InvalidStructure, "object_signature"):
            reader._open_table_data(table)
        count = len(value.calls)
        with self.assertRaises(ValueError):
            reader._open_table_blob(table)
        self.assertEqual(len(value.calls), count)

    def test_missing_wrong_role_and_bad_signature(self):
        with self.assertRaisesRegex(c.UnsupportedLayout, "missing_table_blob_header"):
            opened(source(blob_header=0))
        value = source()
        reader = c.CatalogReader(value.read_at, value.size)
        reader.read_catalog()
        count = len(value.calls)
        with self.assertRaisesRegex(c.InvalidStructure, "table_blob_header_role"):
            c.InternalFile._table_blob(reader._source, 5)
        self.assertEqual(len(value.calls), count)
        value = source()
        value.page(6)[:2] = b"??"
        with self.assertRaisesRegex(c.InvalidStructure, "object_signature"):
            opened(value)

    def test_fragmented_fat_zero_and_one_logical_addressing(self):
        for fats in ((), (11,)):
            value = source(blob_length=2 * P, blob_pages=(10, 8), fats=fats)
            block(value, 31, b"a" * 250, following=33)
            block(value, 33, b"last")
            reader, blob, store, used = opened(value)
            self.assertEqual(store.chain(31, 254), b"a" * 250 + b"last")
            self.assertEqual(used.usage().blob_visits, 2)
            self.assertEqual(used.usage().blob_bytes, 254)
            self.assertIn((10 * P + 31 * 256, 256), value.calls)
            self.assertIn((8 * P + 256, 256), value.calls)
            self.assertNotIn((31 * P, 256), value.calls)
            self.assertEqual(reader._source.roles[8], "table_blob_data")
            self.assertEqual(blob.read_range(P - 2, 4), bytes(value.page(10)[-2:]) + bytes(value.page(8)[:2]))
            count = len(value.calls)
            with self.assertRaisesRegex(c.InvalidStructure, "logical_read_range"):
                blob.read_range(2 * P - 1, 2)
            self.assertEqual(len(value.calls), count)

    def test_same_physical_page_is_not_logical_overlap(self):
        value = source()
        block(value, 1, b"first")
        block(value, 2, b"next")
        _, _, store, _ = opened(value)
        self.assertEqual(store.chain(1, 5), b"first")
        self.assertEqual(store.chain(2, 4), b"next")
        with self.assertRaisesRegex(c.UnsupportedSharing, "logical_blob_chain_overlap"):
            store.chain(1, 5)

    def test_tail_sharing_and_cycles(self):
        value = source()
        block(value, 1, b"a", following=3)
        block(value, 2, b"b", following=3)
        block(value, 3, b"c")
        _, _, store, _ = opened(value)
        self.assertEqual(store.chain(1, 2), b"ac")
        with self.assertRaisesRegex(c.UnsupportedSharing, "logical_blob_chain_overlap"):
            store.chain(2, 2)
        for payload in (b"", b"a"):
            value = source()
            block(value, 1, payload, following=1)
            _, _, store, _ = opened(value)
            with self.assertRaisesRegex(c.InvalidStructure, "blob_chain_cycle"):
                store.chain(1, 2)

    def test_exact_length_termination_and_payload_limit(self):
        for expected in (1, 3):
            value = source()
            block(value, 1, b"ab")
            _, _, store, _ = opened(value)
            with self.assertRaisesRegex(c.InvalidStructure, "blob_declared_length"):
                store.chain(1, expected)
        value = source()
        block(value, 1, used=251)
        _, _, store, _ = opened(value)
        with self.assertRaisesRegex(c.InvalidStructure, "blob_payload_length"):
            store.chain(1, 1)
        value = source()
        block(value, 1, following=2)
        block(value, 2, b"ok")
        _, _, store, _ = opened(value)
        self.assertEqual(store.chain(1, 2), b"ok")
        value = source()
        block(value, 1, b"ok", following=2)
        block(value, 2)
        _, _, store, _ = opened(value)
        with self.assertRaisesRegex(c.InvalidStructure, "blob_declared_length"):
            store.chain(1, 2)

    def test_invalid_start_next_and_unaligned_store(self):
        for first in (0, -1, 32):
            value = source()
            _, _, store, _ = opened(value)
            count = len(value.calls)
            with self.assertRaisesRegex(c.InvalidStructure, "blob_start_reference"):
                store.chain(first, 1)
            self.assertEqual(len(value.calls), count)
        for first, length in ((True, 1), (1, False), (1.0, 1), (1, "1")):
            _, _, store, _ = opened(source())
            with self.assertRaises(ValueError):
                store.chain(first, length)
        value = source()
        block(value, 1, b"a", following=32)
        _, _, store, _ = opened(value)
        with self.assertRaisesRegex(c.InvalidStructure, "blob_next_reference"):
            store.chain(1, 1)
        with self.assertRaisesRegex(c.InvalidStructure, "unaligned_blob_store"):
            opened(source(blob_length=P - 1))

    def test_every_reserved_role_and_data_overlap_is_global(self):
        for target in (1, 2, 3, 5, 6, 7, 9, 12, 13, 14):
            value = source(other=True)
            value.page(6)[24:28] = u32(target)
            with self.subTest(target=target), self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
                opened(value)
        value = source(fats=(11,))
        value.page(6)[24:28] = u32(7)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            opened(value)
        value = source(fats=(11,))
        value.page(11)[:4] = u32(11)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            opened(value)
        value = source(root_fat=True)
        value.page(6)[24:28] = u32(4)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            opened(value)
        value = source()
        internal(value, 5, 1, (9,), (16,))
        value.page(6)[24:28] = u32(16)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            opened(value)

    def test_second_fat_page_is_used_and_all_fats_reserved_first(self):
        pages = tuple(range(100, 2149))
        value = source(blob_length=len(pages) * P, blob_pages=pages, fats=(11, 15))
        block(value, 2048 * 32, b"last FAT")
        _, _, store, _ = opened(value)
        self.assertEqual(store.chain(2048 * 32, 8), b"last FAT")
        self.assertIn((15 * P, P), value.calls)
        # A first FAT data reference must not steal the later FAT header.
        value.page(11)[:4] = u32(15)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            opened(value)

    def test_aggregate_mapping_visit_and_chain_bounds_before_callback(self):
        with self.assertRaisesRegex(c.ResourceLimit, "mapping_pages"):
            opened(source(), catalog_limits=c.CatalogLimits(max_mapping_pages=2))
        value = source()
        block(value, 1, b"a")
        _, _, store, _ = opened(value, catalog_limits=c.CatalogLimits(max_blob_visits=2))
        count = len(value.calls)
        with self.assertRaisesRegex(c.ResourceLimit, "blob_visits"):
            store.chain(1, 1)
        self.assertEqual(len(value.calls), count)
        for ceiling, error in ((1, "transport_blob_bytes"), (2, "transport_blob_visits")):
            value = source()
            block(value, 1, following=2)
            block(value, 2, b"ok")
            limits = n._TransportLimits(max_packed_bytes=ceiling, max_blob_visits=1)
            _, _, store, _ = opened(value, limits=limits)
            count = len(value.calls)
            with self.assertRaisesRegex(c.ResourceLimit, error):
                store.chain(1, 2)
            self.assertEqual(len(value.calls) - count, 0 if ceiling == 1 else 1)

    def test_output_reservation_precedes_allocation_and_callback(self):
        value = source()
        block(value, 1, b"abc")
        reader, _, store, _ = opened(value)
        reader._budget.limits = replace(reader._budget.limits, max_output_bytes=reader.usage.output_bytes + 5)
        count = len(value.calls)
        with mock.patch.object(n, "bytearray", create=True) as allocate:
            with self.assertRaisesRegex(c.ResourceLimit, "output_bytes"):
                store.chain(1, 3)
            allocate.assert_not_called()
        self.assertEqual(len(value.calls), count)

    def test_shared_read_and_processing_bounds_precede_callback(self):
        for metric in ("page_reads", "read_bytes", "bytes_processed"):
            value = source()
            block(value, 1, b"abc")
            reader, _, store, _ = opened(value)
            used = getattr(reader.usage, metric)
            reader._budget.limits = replace(reader._budget.limits, **{"max_" + metric: used})
            count = len(value.calls)
            with self.subTest(metric=metric), self.assertRaisesRegex(c.ResourceLimit, metric):
                store.chain(1, 3)
            self.assertEqual(len(value.calls), count)


class InflateTests(unittest.TestCase):
    def test_fixed_independent_vectors_and_empty_stream(self):
        for packed, plain in ((b"\x03\0", b""), (bytes.fromhex("cb48cdc9c90700"), b"hello")):
            used = budget()
            self.assertEqual(n._inflate_raw(packed, used), plain)
            self.assertEqual(used.usage().plain_bytes, len(plain))
            self.assertEqual(used.usage().inflate_input_bytes, len(packed))
            with self.assertRaises(FrozenInstanceError):
                used.usage().plain_bytes = 1

    def test_exact_output_cap_and_limit_plus_one(self):
        for raw in (b"x", b"A" * 200_000):
            self.assertEqual(n._inflate_raw(compressed(raw), budget(max_plain_bytes=len(raw))), raw)
            if len(raw) > 1:
                with self.assertRaisesRegex(c.ResourceLimit, "transport_plain_bytes"):
                    n._inflate_raw(compressed(raw), budget(max_plain_bytes=len(raw) - 1))
        with self.assertRaisesRegex(c.ResourceLimit, "transport_plain_bytes"):
            n._inflate_raw(compressed(b"xy"), budget(max_plain_bytes=1))

    def test_input_bound_before_zlib_construction(self):
        with mock.patch.object(n.zlib, "decompressobj") as construct:
            with self.assertRaisesRegex(c.ResourceLimit, "transport_inflate_input_bytes"):
                n._inflate_raw(b"abcdef", budget(max_packed_bytes=5))
            construct.assert_not_called()
        for raw in (bytearray(b"\x03\0"), memoryview(b"\x03\0"), "abc"):
            with self.assertRaises(ValueError):
                n._inflate_raw(raw, budget())

    def test_truncated_invalid_wrapped_trailing_and_concatenated(self):
        packed = compressed(b"hello" * 100)
        for raw in (b"", packed[:-1], packed[:1]):
            with self.subTest(raw=raw), self.assertRaisesRegex(c.InvalidStructure, "deflate_truncated"):
                n._inflate_raw(raw, budget())
        for raw in (b"\x07", compressed(b"abc", 15), compressed(b"abc", 31)):
            with self.assertRaises(c.InvalidStructure) as raised:
                n._inflate_raw(raw, budget())
            self.assertIn(raised.exception.code, ("deflate_invalid", "deflate_trailing"))
        for raw in (packed + b"x", packed + packed, b"\x03\0" + bytes(32769)):
            with self.assertRaisesRegex(c.InvalidStructure, "deflate_trailing"):
                n._inflate_raw(raw, budget())

    def test_bounded_calls_unconsumed_tails_and_no_flush(self):
        real_factory = zlib.decompressobj
        calls = []
        class Wrapped:
            def __init__(self):
                self.inner = real_factory(-15)
            def decompress(self, data, *, max_length):
                calls.append((len(data), max_length))
                return self.inner.decompress(data, max_length)
            def __getattr__(self, name):
                if name == "flush":
                    raise AssertionError("flush must never be used")
                return getattr(self.inner, name)
        raw = b"A" * 300_000
        with mock.patch.object(n.zlib, "decompressobj", return_value=Wrapped()) as factory:
            self.assertEqual(n._inflate_raw(compressed(raw), budget()), raw)
            factory.assert_called_once_with(wbits=-15)
        self.assertGreater(len(calls), 1)
        self.assertTrue(all(0 <= size <= 32768 and 1 <= cap <= 65536 for size, cap in calls))
        with self.assertRaisesRegex(c.ResourceLimit, "transport_inflate_calls"):
            n._inflate_raw(compressed(raw), budget(max_inflate_calls=1))

    def test_real_stream_crosses_input_chunk_boundaries(self):
        raw = b"0123456789abcdef" * 5000
        encoder = zlib.compressobj(level=0, wbits=-15)
        packed = encoder.compress(raw) + encoder.flush()
        self.assertGreater(len(packed), 2 * 32768)
        used = budget()
        self.assertEqual(n._inflate_raw(packed, used), raw)
        self.assertGreaterEqual(used.usage().inflate_calls, 3)

    def test_one_byte_consumption_and_nonprogress(self):
        class OneByte:
            eof = False
            unused_data = b""
            unconsumed_tail = b""
            def decompress(self, data, *, max_length):
                self.unconsumed_tail = data[1:]
                self.eof = not self.unconsumed_tail
                return b"x"
        used = budget()
        with mock.patch.object(n.zlib, "decompressobj", return_value=OneByte()):
            self.assertEqual(n._inflate_raw(b"abcd", used), b"xxxx")
        self.assertEqual(used.usage().inflate_calls, 4)
        class Stuck(OneByte):
            def decompress(self, data, *, max_length):
                self.unconsumed_tail = data
                return b""
        with mock.patch.object(n.zlib, "decompressobj", return_value=Stuck()):
            with self.assertRaisesRegex(c.InvalidStructure, "deflate_nonprogress"):
                n._inflate_raw(b"abc", budget())

    def test_work_and_scratch_reservations_precede_native_call(self):
        for limits in (c.CatalogLimits(max_output_bytes=10),
                       c.CatalogLimits(max_bytes_processed=10)):
            used = n._TransportBudget(c._Budget(limits))
            decoder = mock.Mock()
            with mock.patch.object(n.zlib, "decompressobj", return_value=decoder):
                with self.assertRaises(c.ResourceLimit):
                    n._inflate_raw(b"\x03\0", used)
            decoder.decompress.assert_not_called()
        used = budget(max_plain_bytes=1)
        # Input slice (2) + output/probe copies (4) + possible tails (4).
        used.catalog.limits = replace(used.catalog.limits, max_output_bytes=9)
        decoder = mock.Mock()
        with mock.patch.object(n.zlib, "decompressobj", return_value=decoder):
            with self.assertRaisesRegex(c.ResourceLimit, "output_bytes"):
                n._inflate_raw(b"\x03\0", used)
        decoder.decompress.assert_not_called()

    def test_catalog_charge_includes_final_copy_and_shared_blob_work(self):
        value = source()
        packed = bytes.fromhex("cb48cdc9c90700")
        block(value, 1, packed)
        reader, _, store, used = opened(value)
        recovered = store.chain(1, len(packed))
        prior = reader.usage
        self.assertEqual(n._inflate_raw(recovered, used), b"hello")
        self.assertGreater(reader.usage.output_bytes, prior.output_bytes + 5)
        self.assertEqual(used.usage().catalog, reader.usage)
        used = budget(max_plain_bytes=5)
        # slice 7 + scratch (2*6 + 2*7), then immutable final copy 5.
        used.catalog.limits = replace(used.catalog.limits, max_output_bytes=37)
        with self.assertRaisesRegex(c.ResourceLimit, "output_bytes"):
            n._inflate_raw(packed, used)

    def test_limits_exact_types_and_hard_ceilings(self):
        ceilings = dict(max_packed_bytes=16 * 1024 * 1024, max_plain_bytes=64 * 1024 * 1024,
                        max_blob_visits=131_072, max_inflate_calls=65_536)
        for item in fields(n._TransportLimits):
            for bad in (True, False, 0, -1, 1.0, "1", ceilings[item.name] + 1):
                with self.subTest(field=item.name, bad=bad), self.assertRaises(ValueError):
                    n._TransportLimits(**{item.name: bad})
            n._TransportLimits(**{item.name: ceilings[item.name]})
        with self.assertRaises(FrozenInstanceError):
            n._TransportLimits().max_packed_bytes = 1

    def test_standalone_isolated_stdlib_load(self):
        script = '''import importlib.util, pathlib, sys, types
root = pathlib.Path(sys.argv[1])
p = types.ModuleType("isolated_transport")
p.__path__ = [str(root)]
sys.modules[p.__name__] = p
for name in ("filedb_catalog", "filedb_named_file"):
    spec = importlib.util.spec_from_file_location(p.__name__ + "." + name, root / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
assert "yadinassi" not in sys.modules
assert not any("Interpreter" in name for name in sys.modules)
assert hasattr(module, "read_dbnames")
'''
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script, str(STORAGE)],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)




# Independently assembled synthetic declarations/bytes, not observed native rows.
DECLARATIONS = (("FILENAME", "NVC", 0, 128, 0, "CI"),
                ("CREATION", "DT", 0, 0, 0, "CS"),
                ("MODIFIED", "DT", 0, 0, 0, "CS"),
                ("ATTRIBUTES", "N", 0, 5, 0, "CS"),
                ("DATASIZE", "N", 0, 20, 0, "CS"),
                ("BINARYDATA", "I", 0, 0, 0, "CS"),
                ("PARTNO", "N", 0, 10, 0, "CS"))


def serialize(value):
    if type(value) is tuple:
        return "{" + ",".join(serialize(item) for item in value) + "}"
    if type(value) is str:
        return '"' + value.replace('"', '""') + '"'
    return str(value)


def profile(**changes):
    options = dict(declarations=DECLARATIONS, recordlock="0", format_item=0)
    options.update(changes)
    return n.DBNamesProfile(**options)


def number(value, digits):
    # Hex textual nibbles are a distinct construction from the reader loop.
    text = str(value).rjust(digits, "0")
    assert len(text) == digits and value >= 0
    return bytes.fromhex("1" + text + "0")


def named_row(name="DBNames", *, packed_bytes=7, first=1, part=0, marker=0,
              size=None, opaque=b"\xff" * 17):
    text = name.encode("utf-16-le")
    assert len(text) <= 256 and len(opaque) == 17
    return (bytes((marker,)) + (len(text) // 2).to_bytes(2, "little")
            + text.ljust(256, b"\xdc") + opaque
            + number(packed_bytes if size is None else size, 20)
            + u32(first) + u32(packed_bytes) + number(part, 10))


def named_source(rows=None, *, packed=bytes.fromhex("cb48cdc9c90700"),
                 declarations=DECLARATIONS, lock="0", format_item=0, name="PARAMS",
                 reserved=None, data_length=None, duplicate_table=False):
    value = source()
    description = serialize((name, format_item, ("Fields", *declarations), ("Indexes",),
                             ("Recordlock", lock), ("Files", 5, 6, 7))).encode("utf-8")
    indices = tuple(range(2, 2 + (len(description) + 249) // 250))
    value.catalog((2, 20) if duplicate_table else (2,))
    value.chain(indices, description)
    if duplicate_table:
        value.block(20, descriptor("params", fields="", files=(12, 13, 14)))
    rows = [named_row(packed_bytes=len(packed))] if rows is None else rows
    reserved = b"\x01" + b"\xff" * 300 if reserved is None else reserved
    raw = reserved + b"".join(rows)
    length = len(raw) if data_length is None else data_length
    pages = tuple(range(20, 20 + (length + P - 1) // P))
    # Expand physical geometry without allocating unused pages.
    value.page_count = max(value.page_count, 21 + len(pages))
    value.size = value.page_count * P
    value.page(0)[12:16] = u32(value.page_count)
    internal(value, 5, length, pages)
    for index, page in enumerate(pages):
        chunk = raw[index * P:(index + 1) * P]
        value.page(page)[:len(chunk)] = chunk
    chunks = (len(packed) + 249) // 250
    for i in range(chunks):
        block(value, i + 1, packed[250 * i:250 * (i + 1)], following=i + 2 if i + 1 < chunks else 0)
    return value


def extract(value, **kwargs):
    return n.read_dbnames(value.read_at, value.size, profile=profile(), **kwargs)


class ExtractionTests(unittest.TestCase):
    def test_explicit_profile_exact_hypothesis_and_immutability(self):
        value = profile()
        self.assertEqual(value.identifier, "params_dbnames_8380_8192_v1")
        self.assertEqual(value.record_size, 301)
        self.assertEqual(value.placements, ((1, 258), (259, 7), (266, 7), (273, 3),
                                            (276, 11), (287, 8), (295, 6)))
        self.assertEqual(n.DBNAMES_DECLARATIONS, DECLARATIONS)
        with self.assertRaises(FrozenInstanceError):
            value.record_size = 302
        with self.assertRaises(TypeError):
            n.DBNamesProfile()
        for bad in (False, "0", 1, 0.0):
            with self.assertRaises(ValueError):
                profile(format_item=bad)
        for bad in (0, False, "1", "", None):
            with self.assertRaises(ValueError):
                profile(recordlock=bad)
        for bad in (list(DECLARATIONS), DECLARATIONS[:-1], DECLARATIONS[::-1]):
            with self.assertRaises(ValueError):
                profile(declarations=bad)
        for field_index, value_index, bad in ((0, 0, "Filename"), (0, 1, "NC"),
                (0, 2, False), (0, 2, 1), (0, 3, 129), (4, 4, 1), (6, 5, "CI")):
            vector = list(DECLARATIONS)
            values = list(vector[field_index]); values[value_index] = bad
            vector[field_index] = tuple(values)
            with self.assertRaises(ValueError):
                profile(declarations=tuple(vector))

    def test_success_has_only_bytes_identifiers_digest_and_combined_usage(self):
        import hashlib
        value = named_source()
        result = extract(value)
        self.assertEqual(result.target, "PARAMS/DBNames")
        self.assertEqual(result.profile_id, profile().identifier)
        self.assertEqual(result.data, b"hello")
        self.assertEqual(result.packed_bytes, 7)
        self.assertEqual(result.packed_sha256, hashlib.sha256(bytes.fromhex("cb48cdc9c90700")).hexdigest())
        self.assertEqual(result.capability, "experimental_named_file_bytes")
        self.assertEqual(result.native_acceptance, "pending")
        self.assertEqual(result.usage.slots, 2)
        self.assertEqual(result.usage.blob_bytes, 7)
        self.assertEqual(result.usage.plain_bytes, 5)
        self.assertGreater(result.usage.catalog.blob_visits, result.usage.blob_visits)
        self.assertEqual({item.name for item in fields(result)},
                         {"target", "profile_id", "data", "packed_bytes", "packed_sha256", "usage",
                          "capability", "native_acceptance"})
        with self.assertRaises(FrozenInstanceError):
            result.data = b"other"
        with self.assertRaises(FrozenInstanceError):
            result.usage.slots = 27
        self.assertFalse(value.closed)
        self.assertNotIn(7, [offset // P for offset, length in value.calls])

    def test_profile_mismatch_before_selected_data_access(self):
        changed = list(DECLARATIONS); changed[0] = ("Filename", "NVC", 0, 128, 0, "CI")
        for options in (dict(declarations=tuple(changed)), dict(declarations=DECLARATIONS[:-1]),
                        dict(lock="1"), dict(format_item=1), dict(format_item="0")):
            value = named_source(**options)
            with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_profile_mismatch"):
                extract(value)
            self.assertFalse(any(offset // P in (5, 6, 7, 20) for offset, length in value.calls))

    def test_fixed_ascii_table_and_filename_case_keys(self):
        for table, filename in (("params", "dbnames"), ("PaRaMs", "DBNAMES")):
            self.assertEqual(extract(named_source([named_row(filename)], name=table)).data, b"hello")
        with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_table_missing"):
            extract(named_source(name="CONFIG"))
        with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_table_ambiguous"):
            extract(named_source(duplicate_table=True))
        for filename in ("DBNames ", "DBNameſ", "ＤＢNames", "prefixDBNames", "DBNames\0"):
            with self.assertRaisesRegex(c.InvalidStructure, "dbnames_not_found"):
                extract(named_source([named_row(filename)]))

    def test_full_scan_duplicate_and_case_ambiguity_before_blob_access(self):
        for name in ("DBNames", "dbNAMES"):
            value = named_source([named_row(), named_row("other"), named_row(name)])
            with self.assertRaisesRegex(c.InvalidStructure, "dbnames_duplicate"):
                extract(value)
            self.assertFalse(any(offset // P in (6, 8) for offset, length in value.calls))
        value = named_source([named_row(), named_row("other", marker=1)])
        with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_nonreserved_slot"):
            extract(value)
        self.assertFalse(any(offset // P == 6 for offset, length in value.calls))

    def test_empty_reserved_only_and_no_target_are_not_empty_success(self):
        for value in (named_source([], reserved=b""), named_source([]),
                      named_source([named_row("unrelated")])):
            with self.assertRaisesRegex(c.InvalidStructure, "dbnames_not_found"):
                extract(value)
        self.assertEqual(extract(named_source(packed=b"\x03\0")).data, b"")

    def test_framing_stride_and_slot_caps_before_row_read(self):
        for marker in (0, 2, 255):
            value = named_source(reserved=bytes((marker,)) + bytes(300))
            with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_reserved_slot"):
                extract(value)
        for marker in (1, 2, 255):
            with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_nonreserved_slot"):
                extract(named_source([named_row(marker=marker)]))
        for length in (1, 300, 302, 603):
            value = named_source(data_length=length)
            with self.assertRaisesRegex(c.InvalidStructure, "dbnames_record_length"):
                extract(value)
            self.assertFalse(any(offset // P == 20 for offset, amount in value.calls))
        value = named_source()
        with self.assertRaisesRegex(c.ResourceLimit, "dbnames_slots"):
            extract(value, limits=n.NamedFileLimits(max_slots=1))
        self.assertFalse(any(offset // P == 20 for offset, amount in value.calls))
        value = named_source()
        with self.assertRaisesRegex(c.ResourceLimit, "dbnames_record_bytes"):
            extract(value, limits=n.NamedFileLimits(max_record_bytes=300))
        self.assertEqual(value.calls, [])

    def test_no_measured_slot_count_and_cross_page_selection(self):
        rows = [named_row("ignored") for _ in range(31)] + [named_row()]
        result = extract(named_source(rows))
        self.assertEqual(result.usage.slots, 33)
        self.assertEqual(result.data, b"hello")

    def test_filename_length_utf16_and_slack_policy(self):
        row = bytearray(named_row())
        row[1:3] = (129).to_bytes(2, "little")
        value = named_source([bytes(row)])
        with self.assertRaisesRegex(c.InvalidStructure, "dbnames_filename_length"):
            extract(value)
        # Payload must not be read after a failing prefix bound.
        self.assertFalse(any(offset == 20 * P + 301 + 3 for offset, length in value.calls))
        row = bytearray(named_row())
        row[1:5] = b"\x01\0\0\xd8"
        with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_filename_encoding"):
            extract(named_source([bytes(row)]))
        rows = [named_row("Я😀"), named_row("a" * 128), named_row("") , named_row()]
        self.assertEqual(extract(named_source(rows)).data, b"hello")

    def test_numeric_sign_digit_padding_and_part_are_strict(self):
        for field_start, field_end in ((276, 287), (295, 301)):
            for value in (0x00, 0x20, 0xf0):
                row = bytearray(named_row()); row[field_start] = value
                with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_numeric_sign"):
                    extract(named_source([bytes(row)]))
            row = bytearray(named_row()); row[field_start + 1] = 0xa0
            with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_numeric_digit"):
                extract(named_source([bytes(row)]))
            row = bytearray(named_row()); row[field_end - 1] |= 1
            with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_numeric_padding"):
                extract(named_source([bytes(row)]))
        for part in (1, 9_999_999_999):
            with self.assertRaisesRegex(c.UnsupportedLayout, "dbnames_part"):
                extract(named_source([named_row(part=part)]))
        for amount in (0, 8, 99_999_999_999_999_999_999):
            with self.assertRaisesRegex(c.InvalidStructure, "dbnames_size" if amount == 0 else "dbnames_size_mismatch"):
                extract(named_source([named_row(size=amount)]))

    def test_reference_and_packed_bound_before_blob_mapping_or_allocation(self):
        for row, code in ((named_row(first=0), "dbnames_reference"),
                          (named_row(packed_bytes=0, size=7), "dbnames_reference"),
                          (named_row(size=6), "dbnames_size_mismatch")):
            value = named_source([row])
            with self.assertRaisesRegex(c.InvalidStructure, code):
                extract(value)
            self.assertFalse(any(offset // P in (6, 8) for offset, amount in value.calls))
        value = named_source()
        with self.assertRaisesRegex(c.ResourceLimit, "transport_blob_bytes"):
            extract(value, limits=n.NamedFileLimits(max_packed_bytes=6))
        self.assertFalse(any(offset // P in (6, 8) for offset, amount in value.calls))

    def test_opaque_fields_and_unrelated_transport_are_never_decoded(self):
        ignored = bytearray(named_row("unrelated", first=0, packed_bytes=0))
        ignored[259:301] = b"\xff" * 42
        value = named_source([bytes(ignored), named_row(opaque=b"\xff" * 17)])
        self.assertEqual(extract(value).data, b"hello")
        reads = [(offset - 20 * P, length) for offset, length in value.calls if offset // P == 20]
        self.assertTrue(all(not (301 + 259 <= offset < 602) for offset, length in reads))
        self.assertTrue(all(not (602 + 259 <= offset < 602 + 276) for offset, length in reads))
        self.assertEqual([item for item in value.calls if item[0] // P == 8], [(8 * P + 256, 256)])

    def test_selected_blob_collisions_and_cumulative_limits(self):
        value = named_source()
        value.page(6)[24:28] = u32(20)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            extract(value)
        with self.assertRaisesRegex(c.ResourceLimit, "transport_plain_bytes"):
            extract(named_source(), limits=n.NamedFileLimits(max_plain_bytes=4))
        with self.assertRaisesRegex(c.ResourceLimit, "blob_visits"):
            extract(named_source(), catalog_limits=c.CatalogLimits(max_blob_visits=3))

    def test_limit_and_api_type_rejection(self):
        for name in ("max_slots", "max_record_bytes"):
            for value in (0, -1, True, False, 1.0, "1", 65_537):
                with self.assertRaises(ValueError):
                    n.NamedFileLimits(**{name: value})
            n.NamedFileLimits(**{name: 65_536})
        for name in ("max_packed_bytes", "max_plain_bytes", "max_blob_visits", "max_inflate_calls"):
            with self.assertRaises(ValueError):
                n.NamedFileLimits(**{name: True})
        value = named_source()
        for options in (dict(profile=None), dict(profile=profile(), limits=n._TransportLimits()),
                        dict(profile=profile(), catalog_limits={})):
            with self.assertRaises(ValueError):
                n.read_dbnames(value.read_at, value.size, **options)
        self.assertEqual(value.calls, [])


if __name__ == "__main__":
    unittest.main()

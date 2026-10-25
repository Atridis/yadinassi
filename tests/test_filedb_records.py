"""Independent synthetic rows and staged loading, not native 1C evidence."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest

from test_filedb_catalog import Source, P, u32

STORAGE = Path(__file__).resolve().parents[1] / "yadinassi" / "storage"
PACKAGE = "synthetic_record_reader"
pkg = ModuleType(PACKAGE)
pkg.__path__ = [str(STORAGE)]
sys.modules[PACKAGE] = pkg
for name in ("filedb_catalog", "filedb_records"):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, STORAGE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
r = sys.modules[PACKAGE + ".filedb_records"]
c = sys.modules[PACKAGE + ".filedb_catalog"]

# Synthetic names intentionally differ from observed native fixture names.
DECLARATIONS = (("REF", "B", 0, 16, 0, "CS"),
                ("REV", "RV", 0, 0, 0, "CS"),
                ("MARK", "L", 0, 0, 0, "CS"),
                ("PREDEF", "B", 0, 16, 0, "CS"),
                ("KEY", "NVC", 0, 2, 0, "CI"),
                ("TEXT", "NVC", 0, 32, 0, "CI"),
                ("NUMBER", "N", 0, 9, 2, "CS"))


def profile(**changes):
    values = dict(table_name="Synthetic", declarations=DECLARATIONS, recordlock="0", format_item=0)
    values.update(changes)
    return r.RecordProfile(**values)


def serialize(value):
    if type(value) is tuple:
        return "{" + ",".join(serialize(item) for item in value) + "}"
    if type(value) is str:
        return '"' + value.replace('"', '""') + '"'
    return str(value)


def text_value(value, width):
    encoded = value.encode("utf-16-le")
    return (len(encoded) // 2).to_bytes(2, "little") + encoded.ljust(width * 2, b"\xcc")


def row(payload="alpha", amount=b"\x10\x00\x00\x01\x25", marked=False):
    # Independent explicit fixture construction, not computed by reader offsets.
    return (b"\0" + b"V" * 16 + b"R" * 16 + bytes((marked,)) + b"P" * 16
            + text_value("K1", 2) + text_value(payload, 32) + amount)


def source(rows=None, *, length=None, fat_level=0, data_header=5,
           format_item=0, declarations=DECLARATIONS, recordlock="0", name="Synthetic"):
    rows = [row()] if rows is None else rows
    raw = b"\x01" + b"\xab" * 126 + b"".join(rows)
    length = len(raw) if length is None else length
    pages = tuple(range(10, 10 + (length + P - 1) // P))
    value = Source(page_count=max(20, 10 + len(pages)))
    value.catalog((2,))
    description = serialize((name, format_item, ("Fields", *declarations), ("Indexes",),
                             ("Recordlock", recordlock), ("Files", data_header, 8, 9))).encode("utf-8")
    value.chain(tuple(range(2, 2 + (len(description) + 249) // 250)), description)
    if data_header:
        header = value.page(data_header)
        header[:24] = b"\x1c\xfd" + fat_level.to_bytes(2, "little", signed=True) + bytes(12) + length.to_bytes(8, "little")
        header[24:] = b"\xff" * (P - 24)
        for index, page in enumerate((6,) if fat_level else pages):
            header[24 + index * 4:28 + index * 4] = u32(page)
        if fat_level:
            for index, page in enumerate(pages):
                value.page(6)[index * 4:index * 4 + 4] = u32(page)
        for index, page in enumerate(pages):
            chunk = raw[index * P:(index + 1) * P]
            value.page(page)[:len(chunk)] = chunk
    return value


def read(value, **kwargs):
    return r.read_records(value.read_at, value.size, profile=profile(), **kwargs)


class RecordTests(unittest.TestCase):
    def test_native_length_tokens_are_not_storage_widths(self):
        value = profile()
        self.assertEqual(value.record_size, 127)
        self.assertEqual([p.offset for p in value.placements], [17, 1, 33, 34, 50, 56, 122])
        self.assertEqual([p.width for p in value.placements], [16, 16, 1, 16, 6, 66, 5])
        self.assertEqual(value.declarations[1][3], 0)
        self.assertEqual(value.declarations[2][3], 0)
        with self.assertRaises(FrozenInstanceError):
            value.record_size = 9

    def test_owned_fixture_shapes_and_opaque_fields(self):
        for fat in (0, 1):
            with self.subTest(fat=fat):
                value = source(fat_level=fat)
                result = read(value, limits=r.RecordLimits(max_active_records=1))
                self.assertEqual(result.native_acceptance, "pending")
                self.assertEqual(result.capability, "experimental_physical_records")
                self.assertEqual(result.data_file.physical_header_page, 5)
                self.assertEqual(result.slots, 2)
                self.assertEqual(result.framing, "reserved_and_active")
                record = result.rows[0]
                self.assertEqual(record.slot, 1)
                self.assertEqual(record.raw, row())
                self.assertEqual([v.value for v in record.fields],
                                 [b"R" * 16, b"V" * 16, False, b"P" * 16, "K1", "alpha", Decimal("1.25")])
                self.assertEqual(tuple(v.declaration.raw for v in record.fields), DECLARATIONS)
                self.assertEqual(record.fields[5].raw, text_value("alpha", 32))
                self.assertFalse(value.closed)
                with self.assertRaises(FrozenInstanceError):
                    record.slot = 3

    def test_decimal_exact_under_low_ambient_precision(self):
        with localcontext() as context:
            context.prec = 1
            result = read(source([row("beta", b"\x00\x00\x00\x02\x50")]))
        self.assertEqual(result.rows[0].fields[-1].value.as_tuple(), Decimal("-2.50").as_tuple())

    def test_unicode_code_units_and_unused_slack_preserved(self):
        result = read(source([row("Я😀")]))
        self.assertEqual(result.rows[0].fields[5].value, "Я😀")
        self.assertEqual(result.rows[0].fields[5].raw[:2], b"\x03\0")
        self.assertTrue(result.rows[0].fields[5].raw.endswith(b"\xcc\xcc"))

    def test_empty_header_and_reserved_only_distinct_from_missing_header(self):
        for fat in (0, 1):
            result = read(source(length=0, fat_level=fat))
            self.assertEqual((result.framing, result.slots, result.rows), ("empty_zero_length", 0, ()))
        result = read(source([]))
        self.assertEqual((result.framing, result.slots, result.rows), ("empty_reserved", 1, ()))
        with self.assertRaisesRegex(c.UnsupportedLayout, "missing_table_data_header"):
            read(source(data_header=0))
        value = source(length=0)
        value.page(5)[:2] = b"??"
        with self.assertRaisesRegex(c.InvalidStructure, "object_signature"):
            read(value)

    def test_format_admission_is_predeclared_and_type_exact(self):
        for value, code in ((1, "integer_nonzero"), ("0", "string_zero"),
                            ("secret", "string_other"), (("private", 3), "list")):
            with self.subTest(code=code), self.assertRaises(c.UnsupportedLayout) as raised:
                read(source(format_item=value))
            self.assertEqual(str(raised.exception), "format_" + code)
        for value in (False, "0", (0,), 1):
            with self.assertRaises(ValueError):
                profile(format_item=value)
        class Unknown:
            def __eq__(self, other):
                raise AssertionError("must not compare unknown objects")
        self.assertEqual(r.format_discriminator(Unknown()), "other")

    def test_exact_declaration_and_lock_admission_before_data_open(self):
        altered = list(DECLARATIONS)
        altered[1] = ("REV", "RV", 0, 16, 0, "CS")
        for kwargs, code in ((dict(declarations=tuple(altered)), "declaration_mismatch"),
                             (dict(recordlock="1"), "recordlock_mismatch"),
                             (dict(name="synthetic"), "selected_table_count")):
            value = source(**kwargs)
            with self.assertRaisesRegex(c.UnsupportedLayout, code):
                read(value)
            self.assertNotIn((5 * P, P), value.calls)

    def test_rejects_unsupported_profiles_without_source_reads(self):
        for altered in (("REV", "RV", 0, 16, 0, "CS"), ("MARK", "L", 0, 1, 0, "CS"),
                        ("FIELD", "NC", 0, 2, 0, "CI"), ("FIELD", "N", 0, 8, 2, "CS"),
                        ("FIELD", "B", 1, 16, 0, "CS"), ("FIELD", "B", False, 16, 0, "CS")):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                profile(declarations=(altered,))
        with self.assertRaises(ValueError):
            profile(recordlock="1")
        with self.assertRaises(ValueError):
            profile(declarations=(DECLARATIONS[1], DECLARATIONS[1]))

    def test_framing_and_nonreserved_frees_are_not_logical_deletion(self):
        result = read(source([row(marked=True)]))
        self.assertIs(result.rows[0].fields[2].value, True)
        for offset, replacement, code in ((0, b"\0", "reserved_slot_marker"),
                                           (127, b"\x01", "nonreserved_free_slot"),
                                           (127, b"\xff", "nonreserved_free_slot")):
            value = source()
            value.page(10)[offset:offset + len(replacement)] = replacement
            with self.assertRaisesRegex(c.UnsupportedLayout, code):
                read(value)
        with self.assertRaisesRegex(c.InvalidStructure, "record_file_length"):
            read(source(length=255))

    def test_bad_primitive_encodings_fail_finitely(self):
        for offset, replacement, code in ((33, b"\x02", "boolean_encoding"),
                                          (56, b"\xff\xff", "string_length"),
                                          (56, b"\x01\0\0\xd8", "string_encoding"),
                                          (122, b"\x20", "decimal_sign"),
                                          (126, b"\xfa", "decimal_digit")):
            raw = bytearray(row())
            raw[offset:offset + len(replacement)] = replacement
            with self.assertRaises(c.CatalogError) as raised:
                read(source([bytes(raw)]))
            self.assertEqual(raised.exception.code, code)

    def test_limits_are_finite_and_cumulative(self):
        self.assertEqual(r.RecordLimits(), r.RecordLimits(4096, 4096, 4096, 16))
        for limits, code in ((r.RecordLimits(max_slots=1), "record_slots"),
                             (r.RecordLimits(max_active_records=1), "active_records"),
                             (r.RecordLimits(max_record_bytes=126), "record_bytes"),
                             (r.RecordLimits(max_fields=6), "record_fields")):
            with self.assertRaisesRegex(c.ResourceLimit, code):
                read(source([row(), row()]), limits=limits)
        for value in (0, -1, True, 65_537):
            with self.assertRaises(ValueError):
                r.RecordLimits(max_slots=value)
        with self.assertRaisesRegex(c.ResourceLimit, "mapping_pages"):
            read(source(), catalog_limits=c.CatalogLimits(max_mapping_pages=1))
        with self.assertRaisesRegex(c.ResourceLimit, "read_bytes"):
            read(source(), catalog_limits=c.CatalogLimits(max_read_bytes=24 + P))
        self.assertEqual(len(read(source([row(), row()])).rows), 2)

    def test_fragmented_data_crosses_page_boundary(self):
        value = source([row()] * 65, fat_level=1)
        # Remap the second logical data page to a nonadjacent physical page.
        value.page(14)[:] = value.page(11)
        del value.pages[11]
        value.page(6)[4:8] = u32(14)
        result = read(value)
        self.assertEqual(len(result.rows), 65)
        self.assertEqual(result.rows[63].raw, row())
        self.assertIn((10 * P + 8128, 64), value.calls)
        self.assertIn((14 * P, 63), value.calls)
        self.assertFalse(any(offset // P == 11 for offset, _ in value.calls))

    def test_roles_headers_and_exact_reads(self):
        for target in (2, 3, 5, 8, 9):
            value = source()
            value.page(5)[24:28] = u32(target)
            with self.subTest(target=target), self.assertRaises(c.UnsupportedSharing):
                read(value)
        value = source()
        value.page(5)[2:4] = b"\x02\0"
        with self.assertRaisesRegex(c.UnsupportedLayout, "fat_level"):
            read(value)
        value = source()
        def short(offset, length):
            raw = value.read_at(offset, length)
            return raw[:-1] if offset == 5 * P else raw
        with self.assertRaisesRegex(c.InvalidStructure, "inexact_read"):
            r.read_records(short, value.size, profile=profile())

    def test_unselected_table_header_remains_reserved(self):
        value = source()
        value.catalog((2, 4))
        other = serialize(("Unselected", 0, ("Fields", DECLARATIONS[0]), ("Indexes",),
                           ("Recordlock", "0"), ("Files", 12, 0, 0))).encode("utf-8")
        value.block(4, other)
        value.page(5)[24:28] = u32(12)
        with self.assertRaisesRegex(c.UnsupportedSharing, "physical_page_role_overlap"):
            read(value)
        self.assertNotIn((12 * P, P), value.calls)

    def test_record_output_and_processing_share_catalog_budgets(self):
        usage = read(source()).usage
        for name, used in (("max_output_bytes", usage.output_bytes),
                           ("max_bytes_processed", usage.bytes_processed)):
            value = source()
            with self.subTest(name=name), self.assertRaises(c.ResourceLimit) as raised:
                read(value, catalog_limits=c.CatalogLimits(**{name: used - 1}))
            self.assertEqual(raised.exception.code, name[4:])
            self.assertIn((10 * P + 127, 127), value.calls)
            self.assertEqual(len(read(source(), catalog_limits=c.CatalogLimits(**{name: used})).rows), 1)

    def test_only_identity_bound_single_table_open(self):
        value = source()
        reader = c.CatalogReader(value.read_at, value.size)
        table = reader.read_catalog().tables[0]
        with self.assertRaises(ValueError):
            reader._open_table_data(replace(table))
        data = reader._open_table_data(table)
        self.assertEqual(data.info.physical_header_page, 5)
        with self.assertRaises(ValueError):
            reader._open_table_data(table)

    def test_isolated_exact_sibling_loading_without_runtime_or_site(self):
        loader = r'''
import sys, hashlib, importlib.util, json, pathlib, types
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
root = pathlib.Path(sys.argv[1])
expected = json.loads(sys.argv[2])
package = "staged_owned_reader"
allowed = {package, package + ".filedb_catalog", package + ".filedb_records"}
forbidden = {"yadinassi", "Interpreter", "site", "pyuca", "prompt_toolkit", "requests"}
class Guard:
    def find_spec(self, fullname, path=None, target=None):
        base = fullname.split(".")[0]
        if fullname not in allowed and (base in forbidden or base not in sys.stdlib_module_names):
            raise ImportError("outside exact siblings and standard library")
sys.meta_path.insert(0, Guard())
pkg = types.ModuleType(package)
pkg.__path__ = [str(root)]
sys.modules[package] = pkg
for name in ("filedb_catalog", "filedb_records"):
    path = root / (name + ".py")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected[name]
    spec = importlib.util.spec_from_file_location(package + "." + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    assert module.__spec__.origin == str(path)
module = sys.modules[package + ".filedb_records"]
profile = module.RecordProfile("T", (("FLAG", "L", 0, 0, 0, "CS"),), "0", 0)
assert profile.record_size == 5
for name in forbidden:
    assert name not in sys.modules
    try:
        __import__(name)
    except ImportError:
        pass
    else:
        raise AssertionError("guard did not reject")
assert {n for n in sys.modules if n.startswith(package + ".")} == allowed - {package}
print("isolated_exact_siblings_ok")
'''
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            hashes = {}
            for name in ("filedb_catalog", "filedb_records"):
                raw = (STORAGE / (name + ".py")).read_bytes()
                (destination / (name + ".py")).write_bytes(raw)
                hashes[name] = hashlib.sha256(raw).hexdigest()
            completed = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", loader,
                                        str(destination), json.dumps(hashes)],
                                       text=True, encoding="utf-8", capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "isolated_exact_siblings_ok")
            self.assertFalse(list(destination.rglob("*.pyc")))


if __name__ == "__main__":
    unittest.main()

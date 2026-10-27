"""Synthetic lexical contract only: no native/file-database evidence."""
import dataclasses
import importlib.util
from pathlib import Path
import sys
import unittest


# Load only this stdlib-only module; importing the top-level interpreter is not
# a dependency of this experimental byte utility.
_PATH = Path(__file__).resolve().parents[1] / "yadinassi/storage/config_root_projection.py"
_SPEC = importlib.util.spec_from_file_location("_root_projection_test", _PATH)
projection = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = projection
_SPEC.loader.exec_module(projection)
P = projection.RootProjectionProfile(projection.PROFILE_IDENTIFIER)
L = projection.RootProjectionLimits()
BOM = b"\xef\xbb\xbf"
GUID = b"01234567-89AB-CDEF-0123-456789ABCDEF"


def project(data, limits=L):
    return projection.project_root_reference_prefix(data, profile=P, limits=limits)


class RootProjectionTests(unittest.TestCase):
    def rejected(self, data, code=None, **kwargs):
        with self.assertRaises(projection.RootProjectionError) as caught:
            project(data, **kwargs)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        self.assertIn(caught.exception.code, projection.RootProjectionError.codes)
        self.assertEqual(str(caught.exception), caught.exception.code)

    def test_partial_result_and_spelling(self):
        result = project(BOM + b"{2," + GUID + b",arbitrary suffix")
        self.assertEqual(result.reference, GUID.decode().lower())
        self.assertEqual(result.raw_reference, GUID.decode())
        self.assertEqual((result.header_value, result.raw_header), (2, "2"))
        self.assertEqual(result.delimiter, ",")
        self.assertEqual(result.prefix_end, 43)
        self.assertEqual(result.capability, "partial_root_reference_prefix")
        self.assertEqual(result.document_validation, "not_performed")
        self.assertEqual(result.suffix_validation, "not_performed")
        self.assertFalse(hasattr(result, "native_acceptance"))
        self.assertFalse(hasattr(result, "data"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.reference = "changed"

    def test_suffix_is_deliberately_not_validated(self):
        for delimiter in (b",", b"}"):
            prefix = BOM + b"{2," + GUID + delimiter
            for suffix in (b"", b"}", b"garbage", b"\xff\xfe\x00", b"{\"unterminated", b"other-guid"):
                with self.subTest(delimiter=delimiter, suffix=suffix):
                    result = project(prefix + suffix)
                    self.assertEqual(result.reference, GUID.decode().lower())
                    self.assertEqual(result.prefix_end, len(prefix))
                    self.assertEqual(result.suffix_validation, "not_performed")
                    self.assertEqual(result.document_validation, "not_performed")

    def test_header_has_no_count_semantics(self):
        for header in (b"0", b"1", b"2", b"3", b"2147483647"):
            result = project(BOM + b"{" + header + b"," + GUID + b",")
            self.assertEqual(result.header_value, int(header))
            self.assertEqual(result.raw_header, header.decode())

    def test_zero_guid_is_uninterpreted_not_lookup(self):
        guid = b"00000000-0000-0000-0000-000000000000"
        self.assertEqual(project(BOM + b"{2," + guid + b"}").reference, guid.decode())

    def test_all_allowed_whitespace_positions(self):
        for ws in (b"", b" ", b"\t", b"\r", b"\n", b" \t\r\n"):
            data = BOM + ws + b"{" + ws + b"2" + ws + b"," + ws + GUID + ws + b"}"
            self.assertEqual(project(data).prefix_end, len(data))

    def test_non_ascii_prefix_and_grammar_rejections(self):
        for data in (b"{2," + GUID + b"}", b"\xff{2," + GUID + b"}",
                     BOM + b"[2," + GUID + b"]", BOM + b"{{2}," + GUID + b"}",
                     BOM + b"{2;" + GUID + b"}", BOM + b"{2,\"" + GUID + b"\"}",
                     BOM + b"{2,{" + GUID + b"}}", BOM + b"{2," + GUID,
                     BOM + b"{2," + GUID + b"x}", BOM + b"{2," + GUID + b"\xc2\xa0}",
                     BOM + b"{2," + GUID + b"\v}", BOM + b"{2," + GUID + b"\x00}"):
            self.rejected(data)

    def test_header_boundaries(self):
        for header in (b"", b"00", b"02", b"-1", b"+2", b"2.0", b"2147483648", b"10000000000", b"\xff"):
            self.rejected(BOM + b"{" + header + b"," + GUID + b"}")

    def test_guid_every_byte_invalid_substitution(self):
        for i in range(36):
            guid = GUID[:i] + b"!" + GUID[i + 1:]
            self.rejected(BOM + b"{2," + guid + b"}", "guid")

    def test_every_truncation_rejects_before_delimiter(self):
        data = BOM + b"{2," + GUID + b"}"
        for stop in range(len(data)):
            self.rejected(data[:stop])
        self.assertEqual(project(data).prefix_end, len(data))

    def test_prefix_exact_boundary(self):
        short = BOM + b"{2," + GUID + b"}"
        data = BOM + b" " * (1024 - len(short)) + short[3:]
        self.assertEqual(project(data).prefix_end, 1024)
        self.assertEqual(project(data + b"\xff" * 100).prefix_end, 1024)
        self.rejected(BOM + b" " + data[3:], "prefix_bytes")
        self.rejected(short, "prefix_bytes", limits=dataclasses.replace(L, max_prefix_bytes=42))
        self.assertEqual(project(short, dataclasses.replace(L, max_prefix_bytes=43)).prefix_end, 43)

    def test_full_input_bound_even_with_short_prefix(self):
        prefix = BOM + b"{2," + GUID + b"}"
        data = prefix + b"\xff" * (L.max_input_bytes - len(prefix))
        result = project(data)
        self.assertEqual(result.prefix_end, 43)
        self.assertEqual(result.input_bytes, L.max_input_bytes)
        self.rejected(data + b"x", "input_bytes")
        self.rejected(prefix, "input_bytes", limits=dataclasses.replace(L, max_input_bytes=42))

    def test_reservation_is_bounded_before_scan(self):
        data = b"\xff" * 100_000
        reserve = projection.reserve_root_projection(data, profile=P, limits=L)
        self.assertEqual((reserve.input_bytes, reserve.prefix_byte_bound), (100_000, 1024))
        self.assertEqual((reserve.bytes_processed, reserve.output_bytes), (6144, 2048))
        self.rejected(BOM + b"{2," + GUID + b"}", "output_bytes",
                      limits=dataclasses.replace(L, max_output_bytes=2047))

    def test_exact_types_no_hostile_hooks(self):
        class Hostile(bytes):
            def __len__(self):
                raise AssertionError("hostile hook")
        for value in (None, "text", bytearray(b""), memoryview(b""), Hostile()):
            self.rejected(value, "input_type")
        for name in ("max_input_bytes", "max_prefix_bytes", "max_output_bytes"):
            for value in (True, False, 0, -1, 1.0, "1", None, getattr(L, name) + 1):
                with self.assertRaises(projection.RootProjectionError):
                    projection.RootProjectionLimits(**{name: value})

    def test_profile_and_diagnostic_are_closed(self):
        for value in (None, True, "", "other_profile"):
            with self.assertRaises(projection.RootProjectionError):
                projection.RootProjectionProfile(value)
        for value in (None, "source data", 1):
            with self.assertRaises(ValueError):
                projection.RootProjectionError(value)

    def test_mutated_selections_revalidated(self):
        profile = projection.RootProjectionProfile(projection.PROFILE_IDENTIFIER)
        object.__setattr__(profile, "identifier", "different")
        with self.assertRaises(projection.RootProjectionError):
            projection.reserve_root_projection(b"", profile=profile, limits=L)
        limits = projection.RootProjectionLimits()
        object.__setattr__(limits, "max_prefix_bytes", 1025)
        with self.assertRaises(projection.RootProjectionError):
            projection.reserve_root_projection(b"", profile=P, limits=limits)


if __name__ == "__main__":
    unittest.main()

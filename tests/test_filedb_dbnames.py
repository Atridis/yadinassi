"""Original synthetic grammar/budget cases, not captured native DBNames data."""
from dataclasses import FrozenInstanceError, fields, replace
import ast
import importlib.util
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock


SOURCE = (Path(__file__).resolve().parents[1]
          / "yadinassi" / "storage" / "filedb_dbnames.py")
SPEC = importlib.util.spec_from_file_location("synthetic_dbnames_pure_parser", SOURCE)
d = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = d
SPEC.loader.exec_module(d)

BOM = b"\xef\xbb\xbf"
ZERO = "00000000-0000-0000-0000-000000000000"
UPPER = "ABCDEF01-2345-6789-ABCD-EF0123456789"
OTHER = "f1234567-89ab-cdef-0123-456789abcdef"
PROFILE = d.DBNamesParseProfile("dbnames_utf8bom_counted_triples_v1")


def encoded(entries=(), *, header="0", count=None):
    """Independent explicit writer for only these synthetic test inputs."""
    if count is None:
        count = str(len(entries))
    triples = "".join(',{' + uuid + ',"' + kind + '",' + number + '}'
                      for uuid, kind, number in entries)
    return BOM + ("{" + header + ",{" + count + triples + "}}").encode("utf-8")


def parsed(data, *, limits=None, profile=PROFILE):
    return d.parse_dbnames(data, profile=profile,
                          limits=d.DBNamesParseLimits() if limits is None else limits)


class DBNamesParserTests(unittest.TestCase):
    def assert_code(self, code, data, *, kind=d.InvalidDBNames, limits=None):
        with self.assertRaises(kind) as caught:
            parsed(data, limits=limits)
        self.assertIs(type(caught.exception), kind)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertEqual(caught.exception.args, (code,))

    def test_empty_root_and_opaque_header_are_preserved(self):
        for header in ("0", "1", "81", "2147483647"):
            with self.subTest(header=header):
                result = parsed(encoded(header=header))
                self.assertEqual(result.profile, d.DBNAMES_PROFILE_IDENTIFIER)
                self.assertEqual(result.header_value, int(header))
                self.assertEqual(result.raw_header, header)
                self.assertEqual(result.declared_count, 0)
                self.assertEqual(result.raw_count, "0")
                self.assertEqual(result.entries, ())
                self.assertEqual(result.usage.entries, 0)
                self.assertEqual(result.usage.tokens, 7)
                self.assertEqual(result.usage.depth, 2)

    def test_exact_triples_preserve_raw_and_canonical_spellings(self):
        result = parsed(encoded(((UPPER, "Reference", "2147483647"),
                                 (OTHER, "Fld", "0")), header="517"))
        self.assertEqual(result.header_value, 517)
        self.assertEqual(result.declared_count, 2)
        self.assertEqual(result.raw_count, "2")
        self.assertEqual(result.entries, (
            d.DBNamesEntry(UPPER.lower(), UPPER, "Reference", '"Reference"',
                           2147483647, "2147483647", 0),
            d.DBNamesEntry(OTHER, OTHER, "Fld", '"Fld"', 0, "0", 1),
        ))
        self.assertEqual(result.usage.tokens, 23)
        self.assertEqual(result.usage.depth, 3)

    def test_whitespace_only_between_tokens_and_at_eof(self):
        wire = (BOM + b" \t\r\n{ \t19\n,\r{ 1 ,\t{ " + UPPER.encode("ascii")
                + b' , "Reference" \t,\n54\r } } } \t\r\n')
        result = parsed(wire)
        self.assertEqual(result.entries[0].raw_uuid, UPPER)
        self.assertEqual(result.entries[0].raw_kind, '"Reference"')
        self.assertEqual(result.entries[0].raw_id, "54")
        self.assertEqual(result.header_value, 19)

    def test_zero_unknown_duplicate_and_competing_records_are_not_filtered(self):
        triples = ((ZERO, "Opaque_9", "0"),
                   (UPPER, "Reference", "9"),
                   (UPPER.lower(), "Reference", "9"),
                   (UPPER, "Fld", "8"),
                   (OTHER, "reference", "9"),
                   (ZERO, "Opaque_9", "0"))
        result = parsed(encoded(triples, header="0"))
        self.assertEqual(result.declared_count, len(triples))
        self.assertEqual(len(result.entries), len(triples))
        self.assertEqual(tuple(entry.ordinal for entry in result.entries), tuple(range(6)))
        self.assertEqual(tuple((entry.raw_uuid, entry.kind, entry.raw_id)
                               for entry in result.entries), triples)
        self.assertEqual(result.entries[1].uuid, result.entries[2].uuid)
        self.assertNotEqual(result.entries[1].raw_uuid, result.entries[2].raw_uuid)
        self.assertEqual(result.entries[0].uuid, ZERO)

    def test_no_uuid_version_or_kind_whitelist(self):
        for uuid in (ZERO, "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF", OTHER):
            for kind in ("A", "z", "A_012", "Z" * 32, "UnrecognizedKind"):
                with self.subTest(uuid=uuid, kind=kind):
                    entry = parsed(encoded(((uuid, kind, "0"),))).entries[0]
                    self.assertEqual(entry.uuid, uuid.lower())
                    self.assertEqual(entry.raw_uuid, uuid)
                    self.assertEqual(entry.kind, kind)

    def test_bom_required_exactly_once_no_codec_search(self):
        for wire in (b"{0,{0}}", b"", b"\xef", b"\xef\xbb",
                     b" \xef\xbb\xbf{0,{0}}", b"\xff\xfe{\x000\x00}",
                     b"\xfe\xff\x00{", b"\xff\xfe\x00\x00"):
            with self.subTest(wire=wire):
                self.assert_code("dbnames_utf8_bom", wire)
        self.assert_code("dbnames_grammar", BOM + BOM + b"{0,{0}}")
        self.assert_code("dbnames_trailing", encoded() + BOM)

    def test_utf8_validation_rejects_invalid_unicode_scalars_everywhere(self):
        invalid = (
            b"\x80", b"\xbf", b"\xc0\x80", b"\xc1\xbf", b"\xc2",
            b"\xc2A", b"\xe0\x80\x80", b"\xe0\x9f\xbf", b"\xe1\x80",
            b"\xed\xa0\x80", b"\xed\xbf\xbf", b"\xf0\x80\x80\x80",
            b"\xf0\x8f\xbf\xbf", b"\xf1\x80\x80", b"\xf4\x90\x80\x80",
            b"\xf5\x80\x80\x80", b"\xfe", b"\xff",
        )
        for suffix in invalid:
            with self.subTest(suffix=suffix):
                self.assert_code("dbnames_utf8", encoded() + suffix)
                self.assert_code("dbnames_utf8", BOM + suffix + b"{0,{0}}")

    def test_valid_nonascii_is_not_admitted_as_grammar_or_whitespace(self):
        # Boundary scalar values are valid UTF-8 but outside this ASCII grammar.
        for char in ("\u0080", "\u07ff", "\u0800", "\ud7ff", "\ue000",
                     "\uffff", "\U00010000", "\U0010ffff", "\u00a0"):
            with self.subTest(char=repr(char)):
                self.assert_code("dbnames_trailing", encoded() + char.encode("utf-8"))
                self.assert_code("dbnames_grammar", BOM + char.encode("utf-8") + b"{0,{0}}")
        for byte in (b"\v", b"\f", b"\x00"):
            self.assert_code("dbnames_grammar", BOM + byte + b"{0,{0}}")
            self.assert_code("dbnames_trailing", encoded() + byte)

    def test_exact_root_arity_braces_and_complete_eof(self):
        for raw in (b"", b"{}", b"{0}", b"{0,0}", b"{{0},{0}}", b"{0,{0},0}",
                    b"[0,[0]]", b"{0,{0}", b"{0,{0},}", b"{0,{0}}}"):
            with self.subTest(raw=raw):
                with self.assertRaises(d.InvalidDBNames):
                    parsed(BOM + raw)
        for suffix in (b"{0,{0}}", b",", b";", b"# comment", b"text", b"\n0"):
            self.assert_code("dbnames_trailing", encoded() + suffix)

    def test_entry_arity_nesting_and_trailing_comma_rejected(self):
        uuid = UPPER.encode("ascii")
        entries = (
            b"{}", b"{" + uuid + b"}", b"{" + uuid + b',"Fld"}',
            b"{" + uuid + b',"Fld",0,1}', b"{" + uuid + b',"Fld",{0}}',
            b"{{" + uuid + b'},"Fld",0}', b"{" + uuid + b',"Fld",0,}',
            b"{" + uuid + b',"Fld",0}{' + uuid + b',"Fld",1}',
        )
        for entry in entries:
            with self.subTest(entry=entry):
                # Padding prevents the minimum-length count check from masking
                # the intended grammar case with a count-conservation failure.
                with self.assertRaises(d.InvalidDBNames):
                    parsed(BOM + b"{0,{1," + entry + b"}}" + b" " * 64)
        for wire in (encoded()[:-2] + b",}}",
                     encoded(((UPPER, "Fld", "1"),))[:-2] + b",}}"):
            with self.assertRaises(d.InvalidDBNames):
                parsed(wire)

    def test_count_conservation_not_header_or_expected_value(self):
        one = ((UPPER, "Reference", "54"),)
        self.assert_code("dbnames_count_mismatch", encoded(one, count="0"))
        self.assert_code("dbnames_count_mismatch", encoded(one, count="2") + b" " * 64)
        self.assert_code("dbnames_count_mismatch", encoded((), count="1"))
        self.assert_code("dbnames_count_mismatch", encoded(one * 2, count="1"))
        for header in ("0", "1", "2", "2147483647"):
            self.assertEqual(parsed(encoded(one, header=header)).declared_count, 1)
        self.assert_code("dbnames_entries", encoded(count="4097"),
                         kind=d.DBNamesParseResourceLimit)

    def test_canonical_unsigned_decimal_in_all_integer_positions(self):
        for bad in ("-1", "+1", "00", "01", "0x1", "1.0", "1e2", "1 2", "\u0661"):
            for position in ("header", "count", "id"):
                with self.subTest(bad=bad, position=position):
                    kwargs = {position: bad} if position != "id" else {}
                    triples = ((UPPER, "Fld", bad if position == "id" else "1"),)
                    with self.assertRaises(d.InvalidDBNames):
                        parsed(encoded(triples, **kwargs))
        for bad in ("2147483648", "4294967295", "9999999999"):
            self.assert_code("dbnames_integer_range", encoded(header=bad))
            self.assert_code("dbnames_integer_range", encoded(((UPPER, "Fld", bad),)))
        for position in ("header", "count", "id"):
            kwargs = {position: "10000000000"} if position != "id" else {}
            triples = ((UPPER, "Fld", "10000000000" if position == "id" else "1"),)
            self.assert_code("dbnames_integer_digits", encoded(triples, **kwargs),
                             kind=d.DBNamesParseResourceLimit)

    def test_quoted_integer_and_uuid_are_not_bare_tokens(self):
        uuid = UPPER.encode("ascii")
        for raw in (b'{"0",{0}}', b'{0,{"0"}}',
                    b'{0,{1,{"' + uuid + b'","Fld",1}}}',
                    b'{0,{1,{' + uuid + b',"Fld","1"}}}'):
            with self.subTest(raw=raw):
                with self.assertRaises(d.InvalidDBNames):
                    parsed(BOM + raw)

    def test_uuid_exact_groups_and_ascii_hex(self):
        invalid = (UPPER.replace("-", ""), UPPER + "0", UPPER[:-1],
                   "G" + UPPER[1:], "\u0410" + UPPER[1:], UPPER.replace("-", "_"),
                   UPPER[:8] + "0" + UPPER[9:], "{" + UPPER + "}")
        for uuid in invalid:
            with self.subTest(uuid=uuid):
                with self.assertRaises(d.InvalidDBNames):
                    parsed(encoded(((uuid, "Fld", "1"),)) + b" " * 8)

    def test_kind_exact_ascii_identifier_no_general_string_grammar(self):
        for kind in ("", "_Name", "1Name", "A-B", "A B", "A\tB", "A\nB",
                     "A\\B", 'A"B', 'A""B', "\u0421atalog", "A" * 33):
            with self.subTest(kind=kind):
                with self.assertRaises(d.InvalidDBNames):
                    parsed(encoded(((UPPER, kind, "1"),)))
        self.assert_code("dbnames_kind", BOM + b"{0,{1,{" + UPPER.encode("ascii")
                         + b",Fld,1}}}")
        with self.assertRaises(d.InvalidDBNames):
            parsed(BOM + b"{0,{1,{" + UPPER.encode("ascii") + b',"Unterminated,1}}}')

    def test_no_source_data_in_finite_diagnostics(self):
        marker = "PrivateMarkerNeverInDiagnostic"
        wire = encoded(((UPPER, marker + "!", "54"),))
        with self.assertRaises(d.DBNamesParseError) as caught:
            parsed(wire)
        self.assertEqual(str(caught.exception), "dbnames_kind")
        self.assertNotIn(marker, repr(caught.exception))
        self.assertNotIn(UPPER, repr(caught.exception))
        with self.assertRaises(ValueError):
            d.InvalidDBNames(marker)


class DBNamesContractAndBudgetTests(unittest.TestCase):
    def test_explicit_profile_limits_and_exact_primitive_types(self):
        with self.assertRaises(TypeError):
            d.DBNamesParseProfile()
        with self.assertRaises(TypeError):
            d.parse_dbnames(encoded())
        with self.assertRaises(TypeError):
            d.parse_dbnames(encoded(), profile=PROFILE)
        with self.assertRaises(TypeError):
            d.reserve_dbnames_parse(encoded(), limits=d.DBNamesParseLimits())
        for profile in ("unknown", "", None, True, 1):
            with self.assertRaises(d.UnsupportedDBNamesProfile):
                d.DBNamesParseProfile(profile)
        for profile in (None, PROFILE.identifier, object()):
            with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_profile_type$"):
                parsed(encoded(), profile=profile)
        for limits in (None, {}, object()):
            with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_limits_type$"):
                d.parse_dbnames(encoded(), profile=PROFILE, limits=limits)
        class BytesSubclass(bytes):
            pass
        for data in ("{0,{0}}", bytearray(encoded()), memoryview(encoded()),
                     BytesSubclass(encoded()), None):
            with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_input_type$"):
                parsed(data)
        class ProfileSubclass(d.DBNamesParseProfile):
            pass
        class LimitsSubclass(d.DBNamesParseLimits):
            pass
        with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_profile_type$"):
            parsed(encoded(), profile=ProfileSubclass(PROFILE.identifier))
        with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_limits_type$"):
            parsed(encoded(), limits=LimitsSubclass())

    def test_limits_cannot_widen_or_take_bool_and_only_entries_can_be_zero(self):
        defaults = d.DBNamesParseLimits()
        for field in fields(defaults):
            for bad in (-1, True, 1.0, "1", getattr(defaults, field.name) + 1):
                with self.subTest(field=field.name, bad=bad):
                    with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_limit$"):
                        replace(defaults, **{field.name: bad})
            if field.name != "max_entries":
                with self.assertRaises(d.InvalidDBNames):
                    replace(defaults, **{field.name: 0})
        self.assertEqual(parsed(encoded(), limits=replace(defaults, max_entries=0)).entries, ())
        with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^dbnames_entries$"):
            parsed(encoded(((ZERO, "A", "0"),)), limits=replace(defaults, max_entries=0))

    def test_all_public_result_and_policy_objects_are_frozen(self):
        limits = d.DBNamesParseLimits()
        wire = encoded(((UPPER, "Fld", "1"),))
        reservation = d.reserve_dbnames_parse(wire, profile=PROFILE, limits=limits)
        result = parsed(wire)
        for value in (PROFILE, limits, reservation, result, result.usage, result.entries[0]):
            with self.subTest(value=type(value).__name__):
                field = fields(value)[0]
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, field.name, getattr(value, field.name))
        self.assertIs(type(result.entries), tuple)
        with self.assertRaises(TypeError):
            result.entries[0] = result.entries[0]

    def test_shortest_entry_reservation_inequality_and_maximum_count(self):
        for count in (0, 1, 9, 10, 4095, 4096):
            with self.subTest(count=count):
                wire = encoded(((ZERO, "A", "0"),) * count)
                self.assertEqual(len(wire), 10 + 45 * count + len(str(count)) - 1)
                limits = d.DBNamesParseLimits()
                reserved = d.reserve_dbnames_parse(wire, profile=PROFILE, limits=limits)
                self.assertEqual(reserved.entry_bound, count)
                self.assertEqual(reserved.output_bytes, 1024 * (count + 1))
                self.assertEqual(reserved.bytes_processed, 8 * len(wire) + reserved.output_bytes)
                result = parsed(wire)
                self.assertEqual(len(result.entries), count)
                self.assertEqual(result.declared_count, count)
                self.assertEqual(result.usage.tokens, 7 + 8 * count)
                self.assertEqual(result.usage.bytes_processed, reserved.bytes_processed)
                self.assertEqual(result.usage.output_bytes, reserved.output_bytes)
                self.assertEqual(tuple(entry.ordinal for entry in result.entries), tuple(range(count)))

    def test_reservation_uses_actual_length_not_the_16_mib_ceiling(self):
        limits = d.DBNamesParseLimits()
        small = d.reserve_dbnames_parse(encoded(), profile=PROFILE, limits=limits)
        self.assertEqual(small.input_bytes, 10)
        self.assertEqual(small.entry_bound, 0)
        self.assertEqual(small.output_bytes, 1024)
        large = encoded() + b" " * (limits.max_input_bytes - 10)
        maximum = d.reserve_dbnames_parse(large, profile=PROFILE, limits=limits)
        self.assertEqual(maximum.entry_bound, 4096)
        self.assertEqual(maximum.output_bytes, 1024 * 4097)
        self.assertLess(maximum.output_bytes, limits.max_output_bytes)
        self.assertEqual(maximum.bytes_processed, 8 * len(large) + maximum.output_bytes)
        with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^dbnames_input_bytes$"):
            d.reserve_dbnames_parse(large + b" ", profile=PROFILE, limits=limits)

    def test_reservation_is_scan_free_and_counts_only_admissible_entries(self):
        limits = d.DBNamesParseLimits(max_entries=1)
        arbitrary = b"\xff" * 1024
        with mock.patch.object(d, "_validate_utf8", side_effect=AssertionError("must not scan")):
            result = d.reserve_dbnames_parse(arbitrary, profile=PROFILE, limits=limits)
        self.assertEqual(result.entry_bound, 1)
        self.assertEqual(result.output_bytes, 2048)
        for length in (0, 1, 9, 10, 54, 55, 99, 100):
            result = d.reserve_dbnames_parse(b"x" * length, profile=PROFILE,
                                             limits=d.DBNamesParseLimits())
            self.assertEqual(result.entry_bound, max(0, (length - 10) // 45))

    def test_input_output_reserved_before_scanning_or_entry_allocation(self):
        wire = encoded(((ZERO, "A", "0"),))
        for limits, code in (
            (d.DBNamesParseLimits(max_input_bytes=len(wire) - 1), "dbnames_input_bytes"),
            (d.DBNamesParseLimits(max_output_bytes=2047), "dbnames_output_bytes"),
        ):
            with self.subTest(code=code), mock.patch.object(d, "_validate_utf8") as scanner:
                with mock.patch.object(d, "DBNamesEntry") as entry:
                    with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^" + code + "$"):
                        parsed(wire, limits=limits)
                    scanner.assert_not_called()
                    entry.assert_not_called()
        exact = d.DBNamesParseLimits(max_input_bytes=len(wire), max_output_bytes=2048)
        self.assertEqual(parsed(wire, limits=exact).declared_count, 1)

    def test_impossible_declared_count_fails_before_entry_allocation(self):
        for wire in (encoded(count="1"), encoded(count="4096")):
            with mock.patch.object(d, "DBNamesEntry") as entry:
                with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_count_mismatch$"):
                    parsed(wire)
                entry.assert_not_called()
        # A complete undeclared extra entry is not allocated either.
        with mock.patch.object(d, "DBNamesEntry") as entry:
            with self.assertRaisesRegex(d.InvalidDBNames, "^dbnames_count_mismatch$"):
                parsed(encoded(((ZERO, "A", "0"),), count="0"))
            entry.assert_not_called()

    def test_token_depth_scalar_digit_and_entry_limits_at_boundaries(self):
        wire = encoded(((ZERO, "A", "9"),), header="9")
        for limits, code in (
            (d.DBNamesParseLimits(max_tokens=14), "dbnames_tokens"),
            (d.DBNamesParseLimits(max_depth=2), "dbnames_depth"),
            (d.DBNamesParseLimits(max_scalar_bytes=35), "dbnames_scalar_bytes"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^" + code + "$"):
                    parsed(wire, limits=limits)
        exact = d.DBNamesParseLimits(max_tokens=15, max_depth=3,
                                    max_scalar_bytes=36, max_integer_digits=1, max_entries=1)
        self.assertEqual(parsed(wire, limits=exact).entries[0].id, 9)
        self.assertEqual(parsed(encoded(), limits=d.DBNamesParseLimits(max_depth=2,
                                                                     max_tokens=7)).entries, ())
        for limits in (d.DBNamesParseLimits(max_depth=1), d.DBNamesParseLimits(max_tokens=6)):
            with self.assertRaises(d.DBNamesParseResourceLimit):
                parsed(encoded(), limits=limits)
        for wire in (encoded(header="10"), encoded(((ZERO, "A", "10"),))):
            with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^dbnames_integer_digits$"):
                parsed(wire, limits=d.DBNamesParseLimits(max_integer_digits=1))
        with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^dbnames_scalar_bytes$"):
            parsed(encoded(header="1" * 129))
        with self.assertRaisesRegex(d.DBNamesParseResourceLimit, "^dbnames_entries$"):
            parsed(encoded(((ZERO, "A", "0"),) * 2), limits=d.DBNamesParseLimits(max_entries=1))

    def test_public_apis_have_no_environment_expected_value_or_resolver_inputs(self):
        for function in (d.parse_dbnames, d.reserve_dbnames_parse):
            signature = inspect.signature(function)
            self.assertEqual(tuple(signature.parameters), ("data", "profile", "limits"))
            for name in ("profile", "limits"):
                self.assertIs(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(imports, ["__future__", "dataclasses"])
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))
        self.assertEqual(tuple(field.name for field in fields(d.DBNamesIndex)),
                         ("profile", "header_value", "raw_header", "declared_count",
                          "raw_count", "entries", "usage"))


if __name__ == "__main__":
    unittest.main()

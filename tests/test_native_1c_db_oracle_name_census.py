"""Complete bounded counts-only diagnostics, never real native compatibility."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import re
import sys
import tracemalloc
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(ROOT / 'yadinassi/storage'))
sys.path.insert(0, str(ROOT / 'tests'))
import comparison
import filedb_catalog as reader
import protocol
import snapshots
import test_native_1c_db_oracle_comparison as existing
import test_native_1c_db_oracle_name_diagnostic as previous
from snapshots import OracleError


def parsed(names, *, blob_bytes=None):
    if blob_bytes is None:
        blob_bytes = sum(len(name.encode('utf-8')) for name in names)
    return SimpleNamespace(tables=tuple(SimpleNamespace(name=name) for name in names),
        usage=SimpleNamespace(tables=len(names), total_blob_bytes=blob_bytes))


def binding():
    return comparison.capture_binding(existing.evidence(), nonce=existing.NONCE,
        provenance=existing.identity(), baseline=previous.fixtures.physical('baseline'))


def census(names=('private_reader',), selected=('PrivateNative',), **kwargs):
    return comparison.name_census(parsed(names), previous.native(selected), binding(), **kwargs)


def failure(names=('private_reader',), selected=('PrivateNative',), **kwargs):
    evidence = existing.evidence(); evidence['marker']['storage_names'] = previous.native(selected)
    return comparison.missing_table_failure(parsed(names), evidence, nonce=existing.NONCE,
        provenance=existing.identity(), baseline=previous.fixtures.physical('baseline'), **kwargs)


def hypothetical(names, selected, bound=None):
    # Independent real serializer oracle, used only for these bounded fixtures.
    return {'schema': 2, 'status': 'failed', 'category': 'name_mismatch', 'code': 'missing_table',
        **(bound or binding()), 'name_diagnostic': {'target': comparison.TARGET,
            'scope': comparison.NAME_SCOPE, 'status': 'complete',
            'native_tables': sorted(selected), 'reader_tables': sorted(names),
            'native_table_count': len(selected), 'reader_table_count': len(names), 'parser_table_count': len(names)}}


def max_counter_capture():
    # Independent maxima, including mutually exclusive widths. This proves the
    # complete schema size, not authenticity/attainability of fabricated counts.
    capture = failure().capture
    capture['origin']['bytes'] = snapshots.MAX_FILE_BYTES
    capture['postimage']['bytes'] = snapshots.MAX_FILE_BYTES
    value = capture['name_census']
    value.update(native_table_count=4, reader_table_count=4096, parser_table_count=4096,
        native_name_characters=256, reader_name_characters=16777216, total_name_characters=16777472,
        native_max_name_characters=64, reader_max_name_characters=65536,
        native_invalid_identifier_count=4, reader_invalid_identifier_count=4096,
        hypothetical_name_capture_bytes=comparison.MAX_HYPOTHETICAL_NAME_CAPTURE_BYTES,
        policy_flags=list(comparison.POLICY_FLAGS))
    return capture


class CompleteCensusTests(unittest.TestCase):
    def test_complete_counts_never_export_names_even_when_every_policy_fits(self):
        value = census(['other_private', 'other_private', 'Case_Private'], ['Native_Private', '_N'])
        self.assertEqual(value, {'target': comparison.TARGET, 'scope': comparison.NAME_SCOPE,
            'status': 'complete_counts_only', 'trigger_category': 'name_mismatch', 'trigger_code': 'missing_table',
            'native_table_count': 2, 'reader_table_count': 3, 'parser_table_count': 3,
            'native_name_characters': 16, 'reader_name_characters': 38,
            'native_max_name_characters': 14, 'reader_max_name_characters': 13,
            'native_invalid_identifier_count': 0, 'reader_invalid_identifier_count': 0,
            'total_name_characters': 54,
            'hypothetical_name_capture_bytes': len(protocol.encode(hypothetical(
                ['other_private', 'other_private', 'Case_Private'], ['Native_Private', '_N']))),
            'policy_flags': []})
        raw = protocol.encode(failure().capture)
        self.assertNotIn(b'private_reader', raw); self.assertNotIn(b'PrivateNative', raw)
        self.assertNotIn(b'native_tables', raw); self.assertNotIn(b'reader_tables', raw)

    def test_64_65_and_4096_tables_are_complete_not_truncated(self):
        for count in (0, 64, 65, 4096):
            value = census(['R'] * count, ['N'])
            self.assertEqual(value['reader_table_count'], count)
            self.assertEqual(value['parser_table_count'], count)
            self.assertEqual(value['reader_name_characters'], count)
            self.assertEqual('reader_table_limit' in value['policy_flags'], count > 64)
            self.assertEqual('capture_byte_limit' in value['policy_flags'],
                             value['hypothetical_name_capture_bytes'] > 12288)
        self.assertEqual(census([], ['N'])['reader_max_name_characters'], 0)

    def test_combined_2048_2049_threshold_is_only_a_flag(self):
        for last, total in (('R' * 31, 2048), ('R' * 32, 2049)):
            value = census(['R' * 31] * 63 + [last], ['N' * 64])
            self.assertEqual(value['total_name_characters'], total)
            self.assertEqual('name_character_limit' in value['policy_flags'], total > 2048)
            self.assertEqual(value['reader_invalid_identifier_count'], 0)

    def test_all_simultaneous_blockers_and_late_invalid_identifiers_are_counted(self):
        names = ['A' * 64] * 4094 + ['late-invalid', 'another!']
        value = census(names, ['Native-Invalid'])
        self.assertEqual(value['policy_flags'], list(comparison.POLICY_FLAGS))
        self.assertEqual(value['reader_invalid_identifier_count'], 2)
        self.assertEqual(value['native_invalid_identifier_count'], 1)
        self.assertEqual(value['reader_name_characters'], 4094 * 64 + 12 + 8)
        self.assertNotIn(b'late-invalid', protocol.encode(value))

    def test_empty_duplicate_invalid_and_long_reader_names_remain_observations(self):
        value = census(['', '', 'X' * 65, 'a-b', 'a-b', 'Good_1'], ['Native'])
        self.assertEqual(value['reader_table_count'], 6)
        self.assertEqual(value['reader_invalid_identifier_count'], 5)
        self.assertEqual(value['reader_max_name_characters'], 65)
        empty = census([''] * 65)
        self.assertEqual((empty['reader_name_characters'], empty['reader_max_name_characters'],
                          empty['reader_invalid_identifier_count']), (0, 0, 65))

    def test_existing_reader_limits_are_not_raised(self):
        self.assertEqual(comparison.CENSUS_LIMITS, reader.CatalogLimits())
        self.assertEqual((comparison.MAX_CENSUS_TABLES, comparison.MAX_CENSUS_NAME_BYTES,
                          comparison.MAX_CENSUS_BLOB_BYTES), (4096, 65536, 16777216))
        source = (ROOT / 'scripts/native_1c_db_oracle/run.py').read_text(encoding='utf-8')
        self.assertIn('limits=filedb_catalog.CatalogLimits()', source)
        self.assertIn('before_scan=self.remaining', source)

    def test_larger_counts_reject_before_traversal_with_no_partial_diagnostics(self):
        class Unreadable:
            @property
            def name(self):
                raise AssertionError('must reject count before reading a name')
        catalog = SimpleNamespace(tables=(Unreadable(),) * 4097,
            usage=SimpleNamespace(tables=4097, total_blob_bytes=16777216))
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.name_census(catalog, previous.native(), binding())
        self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'diagnostic_limit'))
        self.assertIsNone(caught.exception.capture)

    def test_malformed_parser_count_blob_count_or_collection_rejects_before_scanning(self):
        edits = [lambda c: setattr(c.usage, 'tables', True), lambda c: setattr(c.usage, 'tables', -1),
            lambda c: setattr(c.usage, 'tables', 2), lambda c: setattr(c.usage, 'tables', 4097),
            lambda c: setattr(c.usage, 'total_blob_bytes', True), lambda c: setattr(c.usage, 'total_blob_bytes', -1),
            lambda c: setattr(c.usage, 'total_blob_bytes', 16777217), lambda c: setattr(c, 'tables', iter(c.tables)),
            lambda c: setattr(c, 'tables', list(c.tables)), lambda c: setattr(c, 'usage', None)]
        for edit in edits:
            item = parsed(['R']); edit(item)
            with self.subTest(edit=edit), mock.patch.object(comparison, 'name_wire_metrics', side_effect=AssertionError('must not scan')), \
                 self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.name_census(item, previous.native(), binding())
            self.assertEqual(caught.exception.code, 'invalid_projection')
            self.assertIsNone(caught.exception.capture)

    def test_string_byte_and_aggregate_blob_limits_are_enforced_without_name_encoding(self):
        # BMP/astral character lengths can fit while their UTF-8 byte lengths do not.
        cases = [('a' * 65537, 65537), ('é' * 32769, 65538), ('🙂' * 16385, 65540),
                 ('a', 0), ('é', 1)]
        for name, blob in cases:
            with self.subTest(characters=len(name), blob=blob), self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.name_census(parsed([name], blob_bytes=blob), previous.native(), binding())
            self.assertEqual(caught.exception.code, 'diagnostic_limit'); self.assertIsNone(caught.exception.capture)
        for name in ('a' * 65536, 'é' * 32768, '🙂' * 16384):
            self.assertEqual(census([name])['reader_max_name_characters'], len(name))
        with self.assertRaises(comparison.ComparisonFailure):
            comparison.name_census(parsed(['é', 'é'], blob_bytes=3), previous.native(), binding())

    def test_aggregate_character_boundary_is_complete_and_overflow_precedes_next_scan(self):
        # Primitive scanning is independently tested at the per-string ceiling.
        # Here isolate complete accumulation at the 16 MiB aggregate boundary.
        name = 'x' * 65536
        original = comparison.name_wire_metrics
        def measured(value, **kwargs):
            return (65536, 65538, True) if value is name else original(value, **kwargs)
        for count in (256, 257):
            with self.subTest(count=count), mock.patch.object(comparison, 'name_wire_metrics', side_effect=measured) as scan:
                item = parsed([name] * count, blob_bytes=16777216)
                if count == 256:
                    result = comparison.name_census(item, previous.native(['N']), binding())
                    self.assertEqual(result['reader_name_characters'], 16777216)
                    self.assertEqual(result['reader_invalid_identifier_count'], 256)
                else:
                    with self.assertRaises(comparison.ComparisonFailure) as caught:
                        comparison.name_census(item, previous.native(['N']), binding())
                    self.assertEqual(caught.exception.code, 'diagnostic_limit')
                self.assertEqual(scan.call_count, 257)  # One native plus 256 reader strings.

    def test_lone_surrogates_and_non_strings_fail_with_finite_structural_code(self):
        for name in ('\ud800', 'x\udfff', None, True, 123):
            with self.subTest(name=repr(name)), self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.name_census(parsed([name], blob_bytes=65536), previous.native(), binding())
            self.assertEqual((caught.exception.category, caught.exception.code), ('structural_rejection', 'invalid_projection'))
            self.assertIsNone(caught.exception.capture)
            self.assertEqual(str(caught.exception), 'logical_mismatch')

    def test_native_is_bounded_before_marker_encoding(self):
        cases = (previous.native(['N' * 100000]), previous.native([]), previous.native(['N'] * 5), previous.native([True]))
        for selected in cases:
            evidence = existing.evidence(); evidence['marker']['storage_names'] = selected
            with self.subTest(selected=type(selected)), \
                 mock.patch.object(comparison, 'encode', side_effect=AssertionError('must reject before encoding')), \
                 self.assertRaises(OracleError):
                comparison.missing_table_failure(parsed(['R']), evidence, nonce=existing.NONCE,
                    provenance=existing.identity(), baseline=previous.fixtures.physical('baseline'))

    def test_checked_integer_arithmetic_rejects_bools_negatives_and_overflow(self):
        for left, right, maximum in ((True, 1, 10), (1, False, 10), (-1, 1, 10), (10, 1, 10), (11, 0, 10)):
            with self.subTest(left=left, right=right), self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.census_add(left, right, maximum)
            self.assertEqual(caught.exception.code, 'diagnostic_limit')
        self.assertEqual(comparison.census_add(9, 1, 10), 10)

    def test_deadline_checked_inside_long_name_and_timeout_retains_no_census(self):
        checks = mock.Mock(side_effect=[None, None, OracleError('timeout')])
        with self.assertRaises(OracleError) as caught:
            comparison.name_wire_metrics('x' * 65536, before_scan=checks)
        self.assertEqual(caught.exception.kind, 'timeout')
        self.assertEqual(checks.call_count, 3)  # At characters 0, 1024, 2048.
        report, _ = previous.fixture(OracleError('timeout')); previous.check(report)
        self.assertIsNone(report['storage_contract']); self.assertNotIn(b'name_census', protocol.encode(report))


class WireSizeTests(unittest.TestCase):
    def test_independent_exact_primitive_size_and_identifier_grammar(self):
        names = ['', 'A', '_A1', '1A', 'a-b', 'A' * 64, 'A' * 65, '"', '\\',
            '\b\f\n\r\t', '\x00\x01\x1f\x7f', 'éА漢', '🙂\U0010ffff', '\u2028\u2029']
        names.extend(chr(code) for code in range(256))
        for name in names:
            with self.subTest(name=repr(name)):
                utf8, wire, invalid = comparison.name_wire_metrics(name)
                self.assertEqual(utf8, len(name.encode('utf-8')))
                self.assertEqual(wire, len(json.dumps(name, ensure_ascii=True, separators=(',', ':')).encode('ascii')))
                self.assertEqual(invalid, re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name) is None)

    def test_exact_complete_hypothetical_capture_matches_protocol_encoder(self):
        cases = [([], ['N']), (['R'], ['N']), (['', '"', '\\', '\b\f\n\r\t', '\x00\x1f\x7f'], ['N']),
            (['éА漢', '🙂', 'same', 'same'], ['N-А', 'Quote"', 'Slash\\']),
            (['R' * 31] * 64, ['N' * 64]), (['R'] * 65, ['N1', 'N2', 'N3', 'N4'])]
        for names, selected in cases:
            with self.subTest(count=len(names)):
                self.assertEqual(census(names, selected)['hypothetical_name_capture_bytes'],
                                 len(protocol.encode(hypothetical(names, selected))))

    def test_hypothetical_12288_threshold_is_exact_and_not_an_allocation_permission(self):
        empty = census([''], ['N'])['hypothetical_name_capture_bytes']
        for target in (12288, 12289):
            value = census(['x' * (target - empty)], ['N'])
            self.assertEqual(value['hypothetical_name_capture_bytes'], target)
            self.assertEqual('capture_byte_limit' in value['policy_flags'], target > 12288)
            self.assertLess(len(protocol.encode(value)), 1024)

    def test_large_census_never_serializes_or_copies_inventory_and_has_bounded_workspace(self):
        catalog = parsed(['R' * 64] * 4096)
        native = previous.native(['N']); bound = binding(); encoder = comparison.encode
        seen = []
        def skeleton_only(value):
            self.assertEqual(value['schema'], 2)
            self.assertEqual(value['name_diagnostic']['native_tables'], [])
            self.assertEqual(value['name_diagnostic']['reader_tables'], [])
            raw = encoder(value); seen.append(len(raw)); return raw
        # Inputs are allocated before tracing. A copied 4096-item list alone is
        # over 32 KiB; full JSON would exceed 250 KiB. Neither is constructed.
        with mock.patch.object(comparison, 'encode', side_effect=skeleton_only), \
             mock.patch('builtins.sorted', side_effect=AssertionError('must not sort names')):
            tracemalloc.start()
            try:
                value = comparison.name_census(catalog, native, bound)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        self.assertEqual(len(seen), 2)  # Measurement and syntax revalidation.
        self.assertLess(max(seen), comparison.MAX_NAME_CAPTURE_SKELETON_BYTES)
        self.assertLess(peak, 32768)
        self.assertGreater(value['hypothetical_name_capture_bytes'], protocol.MAX_REPORT_BYTES)


class CensusValidationTests(unittest.TestCase):
    def test_all_counter_bools_and_out_of_range_values_reject(self):
        good = census(['R' * 65, '', 'valid'], ['Native'])
        keys = [key for key, value in good.items() if type(value) is int]
        for key in keys:
            for bad in (True, False, -1, 10 ** 30, None, '1'):
                item = copy.deepcopy(good); item[key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(OracleError):
                    comparison.validate_name_census(item, binding())

    def test_exact_shape_status_trigger_sum_maxima_and_derived_flags_reject_tampering(self):
        good = census(['R' * 64] * 65 + ['invalid!'], ['Native-Invalid'])
        edits = [lambda c: c.update(target='Other'), lambda c: c.update(scope='external'),
            lambda c: c.update(status='partial'), lambda c: c.update(trigger_category='resource_limit'),
            lambda c: c.update(trigger_code='duplicate_table'), lambda c: c.update(raw='PRIVATE'),
            lambda c: c.update(reader_tables=['PRIVATE']), lambda c: c.update(parser_table_count=1),
            lambda c: c.update(total_name_characters=c['total_name_characters'] - 1),
            lambda c: c.update(reader_max_name_characters=1), lambda c: c.update(native_max_name_characters=0),
            lambda c: c.update(reader_invalid_identifier_count=67), lambda c: c.update(hypothetical_name_capture_bytes=0),
            lambda c: c.update(policy_flags=[]), lambda c: c.update(policy_flags=list(reversed(c['policy_flags']))),
            lambda c: c.update(policy_flags=c['policy_flags'] + c['policy_flags'][:1]),
            lambda c: c.update(policy_flags=tuple(c['policy_flags'])), lambda c: c.update(policy_flags=['unknown'])]
        for edit in edits:
            item = copy.deepcopy(good); edit(item)
            with self.subTest(edit=edit), self.assertRaises(OracleError): comparison.validate_name_census(item, binding())

    def test_derivable_zero_and_identifier_feasibility_constraints(self):
        cases = [(census([]), {'reader_max_name_characters': 1}),
            (census([]), {'reader_invalid_identifier_count': 1}),
            (census(['', '']), {'reader_invalid_identifier_count': 1}),
            (census(['R' * 65]), {'reader_invalid_identifier_count': 0}),
            (census(['R', 'S']), {'reader_name_characters': 1, 'total_name_characters': 14}),
            (census(['R' * 64, 'S']), {'reader_name_characters': 64, 'total_name_characters': 77})]
        for good, changes in cases:
            good.update(changes); good['policy_flags'] = comparison.census_policy_flags(good)
            with self.subTest(changes=changes), self.assertRaises(OracleError): comparison.validate_name_census(good, binding())

    def test_review_witnesses_reject_impossible_reader_character_totals(self):
        # Preserve both independently discovered witnesses while keeping every
        # other counter, sum, flag and hypothetical ASCII size self-consistent.
        cases = [(['R' * 64, '?' * 65], 129, 1), (['R' * 64, 'S', ''], 65, -1)]
        for names, boundary, delta in cases:
            value = census(names, ['N'])
            self.assertEqual(value['reader_name_characters'], boundary)
            self.assertEqual(value['reader_invalid_identifier_count'], 1)
            comparison.validate_name_census(value, binding())
            value['reader_name_characters'] += delta
            value['total_name_characters'] += delta
            value['hypothetical_name_capture_bytes'] += delta
            with self.subTest(names=len(names), boundary=boundary, delta=delta), self.assertRaises(OracleError):
                comparison.validate_name_census(value, binding())

    def test_complete_reader_character_feasibility_minimum_and_maximum(self):
        # Each pair is an actual independent string witness at both extrema.
        # Invalid names have any length 0..M; valid names have length1..min(64,M).
        cases = [([], [], 0, 0), (['', ''], ['', ''], 0, 0),
            (['R', 'S', ''], ['R', 'S', '?'], 2, 3),
            (['R' * 64, 'S'], ['R' * 64, 'S' * 64], 65, 128),
            (['R' * 64, ''], ['R' * 64, '?' * 64], 64, 128),
            (['?' * 64, ''], ['?' * 64, '!' * 64], 64, 128),
            (['R', '?' * 65], ['R' * 64, '?' * 65], 66, 129),
            (['?' * 65, ''], ['?' * 65, '!' * 65], 65, 130),
            (['R' * 64, 'S', ''], ['R' * 64, 'S' * 64, '?' * 64], 65, 192)]
        for shortest, longest, minimum, maximum in cases:
            for names, expected, delta in ((shortest, minimum, -1), (longest, maximum, 1)):
                value = census(names, ['N'])
                self.assertEqual(value['reader_name_characters'], expected)
                comparison.validate_name_census(value, binding())
                value['reader_name_characters'] += delta
                value['total_name_characters'] += delta
                value['hypothetical_name_capture_bytes'] += delta
                with self.subTest(count=len(names), expected=expected, delta=delta), self.assertRaises(OracleError):
                    comparison.validate_name_census(value, binding())

    def test_valid_identifier_counts_determine_exact_hypothetical_size(self):
        for delta in (-1, 1):
            good = census(['Reader']); good['hypothetical_name_capture_bytes'] += delta
            with self.assertRaises(OracleError): comparison.validate_name_census(good, binding())

    def test_counter_syntax_does_not_authenticate_private_names_or_missing_truth(self):
        # With invalid identifiers, multiple encoded widths have the same public
        # counters. A plausible substitution is not independently authenticated.
        good = census(['é']); good['hypothetical_name_capture_bytes'] -= 1
        comparison.validate_name_census(good, binding())
        good = census(['Same'], ['Same'])
        comparison.validate_name_census(good, binding())
        # Only run.py's actual strict failure branch establishes missing-table.
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.project_catalog(parsed(['Different']), previous.native(['Same']))
        self.assertEqual(caught.exception.code, 'missing_table')

    def test_all_flags_empty_does_not_change_strict_failure_or_acceptance(self):
        report, _ = previous.fixture(failure(['Reader'], ['Native'])); previous.check(report)
        capture = report['storage_contract']
        self.assertEqual(capture['schema'], 3); self.assertEqual(capture['name_census']['policy_flags'], [])
        self.assertEqual((capture['category'], capture['code']), ('name_mismatch', 'missing_table'))
        self.assertEqual(report['native_compatibility'], 'not_claimed'); self.assertFalse(report['accepted'])

    def test_legacy_complete_name_capture_remains_syntax_compatible_but_not_active(self):
        capture = previous.maximum_name_capture()
        # Replace only the maximal-width origin with the fixture's real baseline.
        capture['origin']['bytes'] = existing.evidence()['origin']['bytes']
        report, _ = previous.fixture(comparison.ComparisonFailure('name_mismatch', 'missing_table', capture=capture))
        previous.check(report)
        self.assertEqual(failure().capture['schema'], 3)


class CensusBudgetTests(unittest.TestCase):
    def test_complete_counter_capture_maximum_and_all_finite_failure_enums(self):
        capture = max_counter_capture(); size = len(protocol.encode(capture))
        self.assertEqual(size, 1491)
        self.assertLessEqual(size, comparison.MAX_CAPTURE_BYTES)
        self.assertEqual(comparison.MAX_CAPTURE_BYTES, 12288)
        for category, codes in comparison.DIAGNOSTICS.items():
            for code in codes:
                self.assertLess(len(protocol.encode({'schema': 1, 'status': 'failed', 'category': category, 'code': code})), size)
        self.assertEqual(comparison.MAX_HYPOTHETICAL_NAME_CAPTURE_BYTES,
                         12 * (16777216 + 256) + 3 * (4096 + 4) + 2048)

    def test_small_skeleton_maximum_and_whole_report_with_newline(self):
        capture = max_counter_capture()
        bound = {key: capture[key] for key in comparison.BINDING_KEYS}
        skeleton = comparison.hypothetical_name_capture_base(bound, 4, 4096, 4096) - 3 - 4095
        self.assertEqual(skeleton, 1051)
        self.assertLessEqual(skeleton, comparison.MAX_NAME_CAPTURE_SKELETON_BYTES)
        self.assertEqual(existing.whole_report_size_upper_bound(), 29821)
        self.assertLess(existing.whole_report_size_upper_bound(), protocol.MAX_REPORT_BYTES)
        self.assertEqual(protocol.MAX_REPORT_BYTES, 32768)

    def test_fixture_text_io_has_explicit_utf8(self):
        tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
                self.assertTrue(any(kw.arg == 'encoding' and isinstance(kw.value, ast.Constant)
                                    and kw.value.value == 'utf-8' for kw in node.keywords))


if __name__ == '__main__':
    unittest.main()

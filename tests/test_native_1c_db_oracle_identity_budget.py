"""Whole identity lane envelopes, independently serialized, not native evidence."""
import copy
import unittest
from unittest import mock
import zlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage'), str(ROOT / 'tests')]

import dbnames_identity as policy
import inputs
import params_extraction
import protocol
import snapshots
import test_native_1c_db_oracle_extraction_budget as prior
import test_native_1c_db_oracle_record_budget as base
import test_native_1c_db_oracle_identity as fixtures

wire = base.wire


def projection_envelope():
    value = fixtures.projection()
    value['transport'].update(packed_bytes=params_extraction.MAX_PACKED_BYTES,
                              plain_bytes=params_extraction.MAX_PLAIN_BYTES)
    value['summary'].update(header_value=2147483647, declared_count=4096, entry_count=4096,
                            opaque_kind_count=4093, zero_uuid_count=4093)
    for position, row in enumerate(value['rows']):
        row.update(id=2147483647, ordinal=4095, raw_uuid=row['raw_uuid'].upper())
        row['predicted_native'] = row['native_name'] = ('_Reference' if position == 0 else '_Fld') + '2147483647'
        row['predicted_physical'] = row['physical_name'] = ('_Reference' if position == 0 else '_FLD') + '2147483647'
    return value


def capture_skeleton():
    report, _ = fixtures.fixture()
    value = copy.deepcopy(report['dbnames_identity'])
    value['reader'] = None
    value['origin']['bytes'] = value['postimage']['bytes'] = snapshots.MAX_FILE_BYTES
    return value


def report_envelope():
    value = prior.report_envelope()
    expected_base = protocol.empty_report(fixtures.NONCE, fixtures.identity())
    for key in set(value) - set(expected_base) - {'rejected_basename', 'failure_context'}:
        del value[key]
    current = policy.empty_report(fixtures.NONCE, fixtures.identity())
    for key in policy.EXTRA_KEYS:
        value[key] = current[key]
    value.update(schema=policy.SCHEMA, lane=policy.LANE, provenance=fixtures.identity())
    value['provenance']['actual_version'] = protocol.VERSION
    for key in ('reader_validation', 'mapping_validation'):
        value[key] = base.longest(('not_run', 'failed', 'discarded', policy.VERDICT))
    value['extraction_validation'] = base.longest(('not_run', 'failed', 'discarded', params_extraction.VERDICT))
    value['failure_kind'] = base.longest((value['failure_kind'], policy.FAILURE_KIND))
    return value


def proof_results():
    projection = projection_envelope()
    skeleton = len(wire(capture_skeleton()))
    report = len(wire(report_envelope()))
    failure = max(len(wire({'schema': policy.CAPTURE_SCHEMA, 'status': 'failed',
                           'category': category, 'code': code}))
                  for category, codes in policy.DIAGNOSTICS.items() for code in codes)
    return {'source_count': len(inputs.IDENTITY_SOURCE_FILES),
        'rows_envelope': len(wire(projection['rows'])),
        'other_envelope': len(wire({key: value for key, value in projection.items() if key != 'rows'})),
        'projection_envelope': len(wire(projection)),
        'capture_skeleton': skeleton,
        'capture_with_full_projection_cap': skeleton - 4 + policy.MAX_PROJECTION_BYTES,
        'capture_cap': policy.MAX_CAPTURE_BYTES, 'failure_capture': failure,
        'report_without_capture': report,
        'report_with_full_capture_cap_and_newline': report - 4 + policy.MAX_CAPTURE_BYTES + 1,
        'report_cap': protocol.MAX_REPORT_BYTES,
        'margin': protocol.MAX_REPORT_BYTES - (report - 4 + policy.MAX_CAPTURE_BYTES + 1)}


def sized_source(size=3500):
    # Synthetic valid grammar padded only with permitted whitespace. This does
    # not reconstruct or claim anything about the destroyed native payload.
    raw = fixtures.payload()
    raw += b' ' * (size - len(raw))
    value = fixtures.source()
    compressor = zlib.compressobj(wbits=-15)
    packed = compressor.compress(raw) + compressor.flush()
    assert len(raw) == size and 0 < len(packed) <= 250
    number = bytes.fromhex('1' + str(len(packed)).zfill(20) + '0')
    value.page(10)[301 + 276:301 + 287] = number
    value.page(10)[301 + 291:301 + 295] = len(packed).to_bytes(4, 'little')
    value.page(11)[256:262] = bytes(4) + len(packed).to_bytes(2, 'little')
    value.page(11)[262:262 + len(packed)] = packed
    return value, raw


class IdentityBudgetTests(unittest.TestCase):
    def test_complete_envelopes_include_new_sources_lifecycle_and_newline(self):
        result = proof_results(); report = report_envelope()
        self.assertEqual(result['source_count'], 26)
        self.assertEqual((len(report['stages']), len(report['snapshots']),
                          len(report['comparisons']), len(report['artifacts'])), (13, 11, 5, 3))
        self.assertEqual(len(report['cleanup']), 4)
        self.assertEqual(set(report) - set(protocol.empty_report(fixtures.NONCE, fixtures.identity())),
                         policy.EXTRA_KEYS | {'rejected_basename', 'failure_context'})
        self.assertLessEqual(result['rows_envelope'], policy.MAX_ROWS_BYTES)
        self.assertLessEqual(result['other_envelope'], policy.MAX_OTHER_BYTES)
        self.assertLessEqual(result['projection_envelope'], policy.MAX_PROJECTION_BYTES)
        self.assertLessEqual(result['capture_with_full_projection_cap'], policy.MAX_CAPTURE_BYTES)
        self.assertLessEqual(result['failure_capture'], policy.MAX_CAPTURE_BYTES)
        self.assertLessEqual(result['report_with_full_capture_cap_and_newline'], protocol.MAX_REPORT_BYTES)
        self.assertGreater(result['margin'], 0)
        for codes in policy.DIAGNOSTICS.values():
            self.assertTrue(all(type(code) is str and code.isascii() and len(code) <= 128 for code in codes))

    def test_actual_input_reservation_fits_existing_cumulative_catalog_budget(self):
        data, raw = sized_source()
        module = params_extraction.load_reader(ROOT / 'yadinassi/storage/filedb_named_file.py')
        extracted = module.read_dbnames(data.read_at, data.size,
            profile=module.DBNamesProfile(params_extraction.DECLARATIONS, '0', 0))
        self.assertEqual(extracted.data, raw)
        reservation = policy.parser.reserve_dbnames_parse(raw,
            profile=policy.parser.DBNamesParseProfile(policy.PROFILE_ID), limits=policy.parser.DBNamesParseLimits())
        self.assertEqual((reservation.entry_bound, reservation.output_bytes, reservation.bytes_processed),
                         (77, 79872, 107872))
        total = extracted.usage.catalog.output_bytes + reservation.output_bytes + policy.MAX_PROJECTION_BYTES
        self.assertLess(total, policy.reader.CatalogLimits().max_output_bytes)
        data, _ = sized_source()
        parsed = policy.read_projection(data.read_at, data.size,
            limits=policy.reader.CatalogLimits(max_output_bytes=total))
        self.assertEqual(parsed.budget.counts['output_bytes'], total)
        self.assertEqual(parsed.budget.counts['bytes_processed'],
                         extracted.usage.catalog.bytes_processed + reservation.bytes_processed + len(raw))
        self.assertEqual(parsed.index.usage.output_bytes, reservation.output_bytes)
        result = policy.compare_identity(parsed, fixtures.manifest(), fixtures.native_projection(), nonce=fixtures.NONCE)
        self.assertEqual(len(result['rows']), 3)
        self.assertEqual(parsed.budget.counts['output_bytes'], total)
        # Exact cumulative boundary: one byte below refuses before parser entry
        # allocation; no reset, refund, ceiling increase or second catalog pass.
        data, _ = sized_source()
        with mock.patch.object(policy.parser, 'parse_dbnames', side_effect=AssertionError('unreserved parse')) as parse:
            with self.assertRaises(policy.reader.ResourceLimit) as caught:
                policy.read_projection(data.read_at, data.size,
                    limits=policy.reader.CatalogLimits(max_output_bytes=total - 1))
        self.assertEqual(caught.exception.code, 'output_bytes'); parse.assert_not_called()

    def test_comparator_exhaustion_preserves_shared_budget_and_finite_diagnostic(self):
        parsed = fixtures.private(); budget = parsed.budget
        budget.charge('bytes_processed', budget.limits.max_bytes_processed - budget.counts['bytes_processed'])
        before = dict(budget.counts)
        with mock.patch.object(policy, '_native_names', side_effect=AssertionError('unreserved join')) as join:
            with self.assertRaises(policy.ObservationFailure) as caught:
                policy.compare_identity(parsed, fixtures.manifest(), fixtures.native_projection(), nonce=fixtures.NONCE)
        self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'bytes_processed'))
        self.assertEqual(budget.counts, before); join.assert_not_called()
        with self.assertRaises(policy.ObservationFailure):
            policy.compare_identity(parsed, fixtures.manifest(), fixtures.native_projection(), nonce=fixtures.NONCE)
        self.assertEqual(budget.counts, before)

    def test_comparator_exhaustion_retains_only_cleanup_gated_failure_capture(self):
        evidence = fixtures.evidence(); budget = evidence['reader'].budget
        budget.charge('bytes_processed', budget.limits.max_bytes_processed - budget.counts['bytes_processed'])
        with mock.patch.object(fixtures.Backend, 'observe_record_metadata', return_value=evidence):
            report, _ = fixtures.fixture()
        self.assertEqual((report['status'], report['failed_stage'], report['failure_kind']),
                         ('failed', 'baseline', policy.FAILURE_KIND))
        self.assertEqual(report['dbnames_identity'], {'schema': policy.CAPTURE_SCHEMA, 'status': 'failed',
            'category': 'resource_limit', 'code': 'bytes_processed'})
        policy.validate_report(protocol.encode(report), nonce=fixtures.NONCE, provenance=fixtures.identity())
        self.assertEqual(report['mapping_validation'], 'failed')

    def test_manifest_is_strictly_bounded_and_has_only_three_owned_roles(self):
        value = fixtures.manifest()
        self.assertLessEqual(len(wire(value)), policy.MAX_MANIFEST_BYTES)
        self.assertEqual([entry['role'] for entry in value['roles']], ['catalog', 'payload', 'amount'])
        self.assertEqual(len(value['roles']), 3)


if __name__ == '__main__':
    unittest.main()

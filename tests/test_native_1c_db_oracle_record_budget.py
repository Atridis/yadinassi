"""Complete schema-5 wire budgets, not native or record compatibility evidence.

These are upper envelopes, not fabricated valid native reports. Independent
maxima deliberately coexist even where a real report cannot contain them at
once. JSON punctuation, every exact key, source path, finite diagnostic and the
host's trailing newline are charged. Projection budgets alone are not a proof
of either the enclosing capture or the complete lifecycle report.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(ROOT / 'yadinassi/storage'))
import comparison
from contract import source_binding
import inputs
import protocol
import record_observation as observation
import snapshots

NONCE = 'a' * 32
TOKEN = 'd' * 32


def wire(value):
    """Independent serializer: never let the production cap hide an overflow."""
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def longest(values):
    return max(values, key=lambda value: len(wire(value)))


def identity():
    return {'commit': 'a' * 40, 'tree': 'b' * 40,
        'sources': {source: 'c' * 64 for source in inputs.RECORD_SOURCE_FILES},
        'image': protocol.IMAGE, 'platform': 'linux/amd64',
        'actual_version': protocol.VERSION, 'locale': 'ru_RU.UTF-8',
        'timezone': 'Etc/UTC'}


def native_projection(field_count=1):
    return {'schema': 1, 'target': observation.TARGET,
        'table': {'storage_name': 'Physical', 'logical_name': '',
            'metadata_name': '', 'fields': [
                {'storage_name': 'F%02d' % index, 'logical_name': '',
                 'metadata_name': '', 'type_text': ''}
                for index in range(field_count)]}}


def physical_projection(field_count=1):
    return {'schema': 1, 'target': observation.TARGET,
        'table': {'name': 'Physical', 'record_lock_token': '', 'fields': [
            {'name': 'F%02d' % index, 'type_token': '', 'nullability': 0,
             'length': 0, 'precision': 0, 'case_token': ''}
            for index in range(field_count)]}}


def native_projection_size_upper_bound():
    # Exactly one table, all 16 field objects, and all 67 scalar string cells.
    # BMP-only text needs at most six ASCII-JSON bytes per counted unit. Charge
    # all 768 units at six bytes, even though 17 nonempty ASCII identifiers make
    # that simultaneous maximum unattainable. Per-cell/uniqueness restrictions
    # can only reduce this bound. The deliberately overlong cell is not admitted.
    value = native_projection(observation.MAX_FIELDS)
    table = value['table']
    table.update(storage_name='', logical_name='\ufffd' * observation.MAX_TEXT_UNITS)
    for field in table['fields']:
        field['storage_name'] = ''
    return len(wire(value))


def physical_projection_size_upper_bound():
    # Every selected name/token is ASCII without escapable characters. All
    # 768 units therefore cost one byte, with all 16 declaration objects and
    # each of their three independently maximal five-digit integers retained.
    value = physical_projection(observation.MAX_FIELDS)
    table = value['table']; table['name'] = 'A' * observation.MAX_TEXT_UNITS
    for field in table['fields']:
        field['name'] = ''
        for key in ('nullability', 'length', 'precision'):
            field[key] = observation.MAX_INTEGER
    return len(wire(value))


def physical_snapshot(*, independent_maxima=False):
    return {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f' * 64,
        'header': {'status': 'header_layout_match',
            # The version/page-size/page-count maxima need not coexist.
            'version': [8, 2, 14, 0] if independent_maxima else [8, 3, 8, 0],
            'page_size': 65536 if independent_maxima else 8192,
            'page_count': (1 << 32) - 1 if independent_maxima else
                          snapshots.MAX_FILE_BYTES // 8192},
        'page_analysis': 'unsupported'}


def snapshot(identifier, *, independent_maxima=False):
    return {'id': identifier,
        'physical': physical_snapshot(independent_maxima=independent_maxima),
        'logical': protocol.expected_logical(identifier),
        'quiescent': True, 'copy_verified': True}


def bound_capture_skeleton():
    """Every success-capture binding, at its independent scalar maximum."""
    return {'schema': observation.CAPTURE_SCHEMA,
        'status': observation.METADATA_VERDICT,
        'comparison_policy': observation.COMPARISON_POLICY,
        'projection_mode': observation.PROJECTION_MODE,
        'operation': observation.OPERATION, 'nonce': NONCE, 'token': TOKEN,
        'source_manifest_sha256': source_binding(identity()),
        'reader_source_sha256': identity()['sources'][observation.READER_SOURCE],
        'actual_version': protocol.VERSION,
        'origin': {'snapshot': 'baseline', 'clone': 'auditor',
            'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f' * 64},
        'postimage': {'copy': 'auditor_frozen', 'binding': 'closed_post_audit_clone',
            'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'e' * 64,
            'storage_version': [8, 3, 8, 0], 'page_size': 8192},
        'native': None, 'reader': None}


def success_capture_size_upper_bound():
    skeleton = bound_capture_skeleton()
    # Replace, do not append to, both already-charged null payload slots.
    return (len(wire(skeleton)) - 2 * len(b'null')
            + observation.MAX_NATIVE_BYTES + observation.MAX_PHYSICAL_BYTES)


def failure_capture_size_upper_bound():
    # Category and code maxima are independent; a mismatched pair is an upper
    # envelope, not an accepted failure. Also exercise every real pair below.
    return len(wire({'schema': observation.CAPTURE_SCHEMA, 'status': 'failed',
        'category': longest(observation.DIAGNOSTICS),
        'code': longest(code for codes in observation.DIAGNOSTICS.values()
                        for code in codes)}))


def complete_capture_size_upper_bound():
    return max(success_capture_size_upper_bound(), failure_capture_size_upper_bound(),
               len(b'null'))


def complete_report_upper_envelope():
    """Every report key and maximal lifecycle collection, excluding capture."""
    report = observation.empty_report(NONCE, identity())
    report.update(status=longest(('ok', 'failed')),
        failed_stage=longest((*protocol.STAGES, None)),
        failure_kind=longest((*protocol.FAILURES, observation.FAILURE_KIND)),
        reader_validation=longest(('not_run', 'failed', 'discarded', observation.VERDICT)),
        metadata_validation=longest(('not_run', 'failed', 'discarded', observation.METADATA_VERDICT)),
        layout_validation=longest(('not_run', 'declarations_only')))
    # empty_report already includes all 13 stage IDs, exact check names and
    # false (five bytes rather than four) for every check and cleanup gate.
    for entry in report['stages']:
        entry['status'] = longest(('not_started', 'ok', 'failed'))
        entry['checks'] = {key: False for key in protocol.CHECKS[entry['id']]}
    report['snapshots'] = [snapshot(name, independent_maxima=True)
                           for name in protocol.SNAPSHOTS]
    report['artifacts'] = [
        {'id': name, 'source': source, 'status': 'ok',
         'physical': {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f' * 64,
                      'header': 'unknown', 'page_analysis': 'unsupported'}}
        for name, source in protocol.ARTIFACTS.items()]
    # Keep the old proof's conservative independent eight-digit counters and
    # samples, including a negative size_delta's extra sign. Geometry would
    # reduce window counts/sample widths; this proof does not need that saving.
    counts = {key: snapshots.MAX_FILE_BYTES for key in (
        'changed_bytes', 'unchanged_bytes', 'added_bytes', 'removed_bytes', 'changed_windows')}
    counts['size_delta'] = -snapshots.MAX_FILE_BYTES
    samples = [snapshots.MAX_FILE_BYTES] * snapshots.MAX_SAMPLES
    for name, (source, control, treatment) in protocol.COMPARISONS.items():
        pair = {'predecessor_bytes': snapshots.MAX_FILE_BYTES,
            'treatment_bytes': snapshots.MAX_FILE_BYTES, 'treatment': counts.copy()}
        windows = {'window_bytes': snapshots.WINDOW_BYTES, 'count': snapshots.MAX_FILE_BYTES}
        if control is None:
            pair['interpretation'] = 'observational_before_after_not_causation'
            windows.update(changed_count=snapshots.MAX_FILE_BYTES, changed_sample=samples.copy())
        else:
            pair.update(control_bytes=snapshots.MAX_FILE_BYTES, control=counts.copy(),
                interpretation='physical_byte_differences_not_causation')
            for category in ('overlap', 'control_only', 'treatment_only'):
                windows[category + '_count'] = snapshots.MAX_FILE_BYTES
                windows[category + '_sample'] = samples.copy()
        pair['byte_windows'] = windows
        report['comparisons'].append({'id': name,
            'kind': 'observational' if control is None else 'matched_control',
            'source': source, 'control': control, 'treatment': treatment, 'physical': pair})
    # Both optional diagnostics coexist with a full success-sized capture and
    # artifact list, even though the validator forbids that combination.
    report['rejected_basename'] = '1Cv8' + 'X' * 48
    report['failure_context'] = {
        'operation': longest((*protocol.COMMAND_STAGES, 'enterprise_' + observation.OPERATION)),
        'site': longest(protocol.CONTEXT_SITES),
        'bsl_phase': longest((*protocol.BSL_PHASES, *observation.PHASES, None)),
        'region': longest((*protocol.INVENTORY_REGIONS, None)),
        'reason': longest((*protocol.INVENTORY_REASONS, None)),
        'entry_class': longest(snapshots.ENTRY_CLASSES),
        'entry_shape': longest(snapshots.ENTRY_SHAPES)}
    return report


def whole_report_size_upper_bound(*, enclosing_cap=True):
    report = complete_report_upper_envelope()
    assert report['record_observation'] is None
    # The full enclosing 12288-byte cap is used by default, not the smaller
    # currently calculated capture. This independently covers any combination
    # of allowed capture values. The final newline is part of report.json.
    capture = observation.MAX_CAPTURE_BYTES if enclosing_cap else complete_capture_size_upper_bound()
    return len(wire(report)) - len(b'null') + capture + len(b'\n')


def real_bound_capture():
    """Exercise actual production construction, using only synthetic scalars."""
    report = observation.empty_report(NONCE, identity())
    report['snapshots'] = [snapshot('baseline')]
    data = {'schema': 1, 'nonce': NONCE, 'token': TOKEN,
        'operation': observation.OPERATION, 'status': 'ok', 'actual_version': protocol.VERSION,
        'user': 'NativeOracleSetup', 'role_verified': True, 'nonprivileged': True,
        'users_verified': True, 'metadata_version': 1,
        **{key: None for key in ('count', 'code', 'payload', 'amount', 'deletion_mark', 'same_reference')},
        'payload_length': 32, 'amount_digits': 9, 'amount_scale': 2,
        'record_metadata': native_projection()}
    evidence = {'marker': data,
        'origin': {'nonce': NONCE, 'token': TOKEN, 'clone': 'auditor',
            'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f' * 64},
        'postimage': {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'e' * 64},
        'reader': physical_projection()}
    return observation.bind_capture(evidence, report)


def failure_report(category, code):
    report = observation.empty_report(NONCE, identity())
    report.update(failed_stage='baseline', failure_kind=observation.FAILURE_KIND,
        metadata_validation='failed', reader_validation='failed')
    for entry in report['stages']:
        if entry['id'] in ('preflight', 'seed_v1', 'cleanup'):
            entry['status'] = 'ok'
            entry['checks'] = {key: True for key in entry['checks']}
        elif entry['id'] == 'baseline':
            entry['status'] = 'failed'
    report['cleanup'].update(native_processes_stopped=True, raw_files_removed=True)
    report['snapshots'] = [snapshot('baseline')]
    report['record_observation'] = {'schema': observation.CAPTURE_SCHEMA,
        'status': 'failed', 'category': category, 'code': code}
    return report


class CompleteRecordObservationBudgetTests(unittest.TestCase):
    def test_pinned_versions_limits_and_exact_source_inventory(self):
        self.assertEqual((observation.SCHEMA, observation.CAPTURE_SCHEMA), (5, 6))
        self.assertEqual(observation.LANE, 'owned_record_metadata_observation_v1')
        self.assertEqual(observation.PROJECTION_MODE, 'dbms_names_true')
        self.assertEqual(observation.COMPARISON_POLICY, 'exact_tables_ascii_fields_v1')
        self.assertEqual((observation.MAX_FIELDS, observation.MAX_TEXT,
            observation.MAX_TEXT_UNITS, observation.MAX_TOKEN, observation.MAX_INTEGER),
            (16, 64, 768, 8, 65535))
        self.assertEqual((observation.MAX_NATIVE_BYTES, observation.MAX_PHYSICAL_BYTES,
            observation.MAX_CAPTURE_BYTES, protocol.MAX_REPORT_BYTES),
            (6144, 4096, 12288, 32768))
        self.assertEqual((len(inputs.LEGACY_V3_SOURCE_FILES), len(inputs.SOURCE_FILES),
                          len(inputs.RECORD_SOURCE_FILES)), (18, 20, 21))
        self.assertEqual(inputs.RECORD_SOURCE_FILES,
            {**inputs.SOURCE_FILES, observation.MODULE_SOURCE: 'record_observation.py'})
        self.assertEqual(len(identity()['sources']), 21)
        self.assertTrue(all(len(value) == 64 for value in identity()['sources'].values()))

    def test_complete_independent_projection_envelopes_fit(self):
        self.assertLessEqual(native_projection_size_upper_bound(), observation.MAX_NATIVE_BYTES)
        self.assertLessEqual(physical_projection_size_upper_bound(), observation.MAX_PHYSICAL_BYTES)
        self.assertEqual(len(wire('\ufffd')) - 2, 6)
        self.assertEqual(len(wire('"\\')) - 2, 4)

    def test_reviewed_complete_bounds_are_pinned(self):
        # Measured on the parent's frozen-v1 candidate after its complete
        # focused run. Any source-path/key/enum/budget growth requires renewed
        # explicit review, not a silently moving assertion against the cap.
        self.assertEqual(native_projection_size_upper_bound(), 5938)
        self.assertEqual(physical_projection_size_upper_bound(), 2476)
        self.assertEqual(len(wire(bound_capture_skeleton())), 858)
        self.assertEqual(len(wire(bound_capture_skeleton())) - 2 * len(b'null'), 850)
        self.assertEqual(success_capture_size_upper_bound(), 11090)
        self.assertEqual(failure_capture_size_upper_bound(), 113)
        self.assertEqual(complete_capture_size_upper_bound(), 11090)
        self.assertEqual(len(wire(complete_report_upper_envelope())), 17920)
        self.assertEqual(whole_report_size_upper_bound(), 30205)
        self.assertEqual(protocol.MAX_REPORT_BYTES - whole_report_size_upper_bound(), 2563)
        self.assertEqual(whole_report_size_upper_bound(enclosing_cap=False), 29007)

    def test_real_admitted_native_projection_reaches_768_units_without_truncation(self):
        value = native_projection(observation.MAX_FIELDS)
        table = value['table']
        remaining = observation.MAX_TEXT_UNITS - len(table['storage_name']) - sum(
            len(field['storage_name']) for field in table['fields'])
        cells = [(table, key) for key in ('logical_name', 'metadata_name')]
        cells += [(field, key) for field in table['fields']
                  for key in ('logical_name', 'metadata_name', 'type_text')]
        for container, key in cells:
            count = min(remaining, observation.MAX_TEXT)
            container[key] = '\ufffd' * count; remaining -= count
        self.assertEqual(remaining, 0)
        original = copy.deepcopy(value)
        self.assertEqual(observation.validate_native_projection(value), original)
        self.assertEqual(value, original)
        self.assertLessEqual(len(wire(value)), native_projection_size_upper_bound())
        self.assertEqual(protocol.encode(value), wire(value))

    def test_real_admitted_physical_projection_reaches_all_scalar_maxima(self):
        value = physical_projection(observation.MAX_FIELDS)
        value['table']['record_lock_token'] = 'A' * observation.MAX_TOKEN
        for field in value['table']['fields']:
            field['name'] += 'x' * 28
            field.update(type_token='A' * observation.MAX_TOKEN,
                case_token='Z' * observation.MAX_TOKEN, nullability=observation.MAX_INTEGER,
                length=observation.MAX_INTEGER, precision=observation.MAX_INTEGER)
        table = value['table']
        units = len(table['name']) + len(table['record_lock_token']) + sum(
            len(field[key]) for field in table['fields']
            for key in ('name', 'type_token', 'case_token'))
        self.assertEqual(units, observation.MAX_TEXT_UNITS)
        original = copy.deepcopy(value)
        self.assertEqual(observation.validate_physical_projection(value), original)
        self.assertEqual(value, original)
        self.assertLessEqual(len(wire(value)), physical_projection_size_upper_bound())
        self.assertEqual(protocol.encode(value), wire(value))

    def test_complete_capture_includes_real_binding_and_both_full_caps(self):
        actual = real_bound_capture()
        actual.update(native=None, reader=None)
        self.assertEqual(actual, bound_capture_skeleton())
        self.assertEqual(set(actual), observation.BINDING_KEYS |
            {'schema', 'status', 'comparison_policy', 'projection_mode', 'native', 'reader'})
        self.assertGreater(success_capture_size_upper_bound(),
            observation.MAX_NATIVE_BYTES + observation.MAX_PHYSICAL_BYTES)
        self.assertLessEqual(complete_capture_size_upper_bound(), observation.MAX_CAPTURE_BYTES)

    def test_every_finite_failure_capture_and_whole_failed_report_fit(self):
        for category, codes in observation.DIAGNOSTICS.items():
            for code in codes:
                with self.subTest(category=category, code=code):
                    report = failure_report(category, code)
                    observation.validate_report(wire(report), nonce=NONCE,
                                                provenance=identity())
                    self.assertLessEqual(len(wire(report['record_observation'])),
                                         failure_capture_size_upper_bound())
                    self.assertLessEqual(len(wire(report)) + 1,
                                         whole_report_size_upper_bound())
        self.assertLess(failure_capture_size_upper_bound(), success_capture_size_upper_bound())

    def test_complete_lifecycle_report_not_only_capture_sum_fits_with_newline(self):
        report = complete_report_upper_envelope()
        self.assertEqual(len(report['stages']), 13)
        self.assertEqual(len(report['snapshots']), 11)
        self.assertEqual(len(report['comparisons']), 5)
        self.assertEqual(len(report['artifacts']), 3)
        self.assertEqual([item['id'] for item in report['stages']], list(protocol.STAGES))
        for entry in report['stages']:
            self.assertEqual(set(entry['checks']), set(protocol.CHECKS[entry['id']]))
            self.assertTrue(all(value is False for value in entry['checks'].values()))
        self.assertEqual(set(report['cleanup']), {'native_processes_stopped',
            'raw_files_removed', 'container_removed', 'private_staging_removed'})
        self.assertTrue(all(value is False for value in report['cleanup'].values()))
        self.assertIs(report['accepted'], False)
        self.assertNotIn('storage_contract', report)
        self.assertEqual(report['mapping_validation'], 'not_run')
        self.assertEqual(report['record_validation'], 'not_run')
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertEqual(report['layout_validation'], 'declarations_only')
        self.assertEqual(set(report) - set(protocol.empty_report(NONCE, identity())),
            observation.EXTRA_KEYS | {'rejected_basename', 'failure_context'})
        self.assertEqual(whole_report_size_upper_bound(), len(wire(report)) - 4 + 12288 + 1)
        self.assertLess(whole_report_size_upper_bound(), protocol.MAX_REPORT_BYTES)
        self.assertLessEqual(whole_report_size_upper_bound(enclosing_cap=False),
                             whole_report_size_upper_bound())

    def test_new_operation_and_phases_charged_without_widening_old_protocol(self):
        self.assertNotIn(observation.OPERATION, protocol.ENTERPRISE_OPERATIONS)
        self.assertNotIn('enterprise_' + observation.OPERATION, protocol.COMMAND_STAGES)
        self.assertTrue(observation.RECORD_PHASES.isdisjoint(protocol.BSL_PHASES))
        context = complete_report_upper_envelope()['failure_context']
        self.assertGreaterEqual(len(wire(context['operation'])),
                                len(wire('enterprise_' + observation.OPERATION)))
        self.assertGreaterEqual(len(wire(context['bsl_phase'])),
                                max(len(wire(value)) for value in observation.RECORD_PHASES))

    def test_test_source_text_io_is_explicit_utf8(self):
        tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ('read_text', 'write_text'):
                encoding = next((kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                self.assertIsInstance(encoding, ast.Constant)
                self.assertEqual(encoding.value, 'utf-8')


if __name__ == '__main__':
    unittest.main()

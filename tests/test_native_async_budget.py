"""Production-serializer bounds for the separate Async measurement invocation.

This is a structural proof, not a golden-run size sample. JSON length is additive
for a fixed tree: longer scalar spellings, additional keys/items, and a longer
fixed-length digest cannot make it smaller. The bound partitions execution at
stage2: diagnostics can be populated only before any async row is observed;
after stage2 succeeds diagnostics are exactly empty. Within each partition the
majorant deliberately combines mutually exclusive maxima, and thus bounds more
than the reachable states. Actual production serializers are used throughout.

Finite async paths are enumerated, not assumed from JavaScript: 8 scalar paths,
2 nested-Promise paths, and 5 rejection paths, for 80 distinct combinations.
Scheduling permutations do not change length: tokens are integers and preserve
the same multiset. Number -999999 is the longest accepted value payload; other
public scalar types, hashes, enum tags and error ordinals have fixed bounds.
A call-side rejection omits both Awaits, so at most SIX errors can coexist.
The failure-only diagnostic tuple has 729 legal encodings, plus null; its
longest compact encoding is ten bytes. The late majorant includes that tuple
even alongside every completed observation, a deliberately unreachable bound.
No native process or external action is invoked by these tests.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_async_protocol as protocol
from test_native_1c_full_host import fixture, NONCE
from test_native_1c_smoke import (smoke, bootstrap_report, read_staging_fixture,
                                  _USE_SYNTHETIC_STAGING_READER)

suite, full = protocol.suite, protocol.full
H = 'f' * 64
TEMPLATE = full.ASYNC_EXPECTED_IDENTITY['template']
MODULES = full.ASYNC_EXPECTED_IDENTITY['modules']
EXTRAS = ('client_dates', 'client_values', 'client_collections', 'client_numbers', 'client_watchdog')
CLASSES = ('native', 'display', 'session_bus', 'shell', 'python', 'other', 'unreadable')
CAPS = {'stage_wire': 8192, 'public_summary': 32768, 'provenance': 32768}
MAXIMUM_FAILURE_DIAGNOSTICS = [5, 3, 3, 17]


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def pretty(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def longest(values):
    return max(values, key=lambda value: len(json.dumps(value)))


def maximum_process_diagnostics():
    # Seven class counters sum to <=256. At most two can have three digits
    # while all seven have two: 100+100+10+10+10+10+16 = 256.
    return dict(stage='before_probe', reason='unexpected_processes',
                unexpected_count=256, zombie_count=256,
                classes=dict(zip(CLASSES, (100, 100, 10, 10, 10, 10, 16))))


def bind_identity(value):
    value['template_sha256'] = TEMPLATE
    for row, module in zip(value['cases'], MODULES):
        row[3] = module
    return value


def successful_records():
    for scalar, nested in itertools.product(itertools.product((False, True), repeat=3), (False, True)):
        yield bind_identity(protocol.record(scalar_errors=scalar, nested=nested, reject_call=True))
        for awaited in itertools.product((False, True), repeat=2):
            yield bind_identity(protocol.record(scalar_errors=scalar, nested=nested, await_errors=awaited))


def maximum_observed_record():
    records = list(successful_records())
    # The same maximizer works for compact and every pretty indentation depth.
    result = max(records, key=lambda value: len(compact(value)))
    assert len(pretty(result)) == max(map(lambda value: len(pretty(value)), records))
    return result


def failure_records():
    # A failed/unreached row is shorter than every complete observed row.
    # Therefore maximal observed prefixes bound ALL earlier conditional paths.
    for index, reason, verified in itertools.product(range(8), range(1, 15), (False, True)):
        if reason == 14 and not verified:
            continue
        value = maximum_observed_record()
        state = 3 if reason == 14 else 2
        value.update(status='inconclusive' if state == 3 else 'failed', failure_kind=suite.ASYNC_FAILURES[reason], continuity_sha256=None)
        value['cases'][index:] = [[index, state, reason, MODULES[index] if verified else None, 0, [], [], []]] + [
            [case, 0, 1, None, 0, [], [], []] for case in range(index + 1, 8)]
        value['process_diagnostics'] = maximum_process_diagnostics()
        value['failure_diagnostics'] = MAXIMUM_FAILURE_DIAGNOSTICS.copy()
        yield value


def stage(record=None):
    envelope, inputs, modules = fixture()
    inputs[full.CLIENT_SOURCE] = H
    inputs[full.COLLECTIONS_SOURCE] = full.COLLECTIONS_SOURCE_SHA256
    result = envelope['report']['stage3']
    result['cases'][0]['source_sha256'] = full.COLLECTIONS_SOURCE_SHA256
    # Six output widths with one seven-digit and five six-digit counters are
    # jointly legal under the unchanged 2 MiB aggregate cap.
    for index, case in enumerate(result['cases']):
        case.update(output_size=1048576 if index == 0 else 100000, message_count=32768)
    result['client_probe'] = dict(status='ok', failure_kind='none',
        **{key: H for key in full.CLIENT_HASHES}, **{key: True for key in full.CLIENT_FLAGS},
        process_diagnostics=protocol.fixtures.process_diagnostics())
    result['client_async'] = copy.deepcopy(record or maximum_observed_record())
    if result['client_async']['status'] != 'ok':
        result.update(status='failed', failure_kind=result['client_async']['failure_kind'])
    modules.update(client_probe=H, client_async={'template': TEMPLATE, 'modules': MODULES})
    return result, inputs, modules


def comparison(stage3):
    contract = full.map_contract()
    result = dict(schema=2, configured_timezone='Etc/UTC', configured_locale='C.UTF-8',
        native_target=full.LINUX_TARGET, comparison_mode=full.MAP_MODE, status='failed',
        acceptance_status='rejected', cases=[])
    for native in stage3['cases']:
        item = dict(name=native['name'], status='mismatched', failure_kind='none',
            native_size=native['output_size'], native_sha256=native['output_sha256'],
            interpreter_size=1048576, interpreter_sha256=H, acceptance_status='rejected', semantic=None,
            mismatch=dict(different_byte_positions=1048576, first_mismatch_byte=native['output_size'],
                          first_mismatch_native_line=1048577, native_line_count=1048577,
                          interpreter_line_count=1048577))
        if native['name'] == 'collections':
            item.update(acceptance_status='accepted', semantic=dict(status='equivalent',
                profile=full.MAP_MODE, records=841, byte_equal_records=833,
                accepted_labels=list(contract.ELIGIBLE_LABELS), reason='none'))
        result['cases'].append(item)
    full.validate_comparison(result, stage3, full.LINUX_TARGET, full.MAP_MODE)
    return result


def probe(record=None):
    result = bootstrap_report()
    stage3, inputs, _ = stage(record)
    result['stage3'] = stage3
    result.update(native_tests_completed=stage3['status'] == 'ok',
        status='ok' if stage3['status'] == 'ok' else 'stage3_failed',
        image=smoke.IMAGE, platform='linux/amd64', native_target=full.LINUX_TARGET,
        comparison_mode=full.MAP_MODE, container_exit_code=0,
        trusted_input_sha256=inputs, invocation_nonce=NONCE,
        configured_timezone='Etc/UTC', configured_native_locale='ru_RU',
        repository=dict(commit='f'*40, tree='f'*40, github_run_id='9'*20, github_run_attempt='9'*20),
        interpreter=dict(python_version='99.99.999', dependencies=full.DEPENDENCIES,
            source_file_count=512, source_sha256=H, comparison_driver_sha256=H, map_contract_sha256=H))
    for key in ('native_evidence_accepted', 'native_transport_validated', 'native_cases_completed',
                'container_cleanup_verified', 'private_payloads_removed', 'windows_goldens_unchanged',
                'native_output_artifact_ready'):
        result[key] = stage3['status'] == 'ok'
    result['native_output_artifact_sha256'] = {name: H for name in full.ARTIFACT_FILES}
    result['python_version'] = '99.99.999'
    # Validator permits repetition as well as the producer's sorted unique set.
    # Bounding that larger accepted space is deliberately conservative.
    result['configuration_format'].update(schema_version='99.999.999.999', element_count=4096,
        known_elements=[longest(smoke.KNOWN_ELEMENTS)] * len(smoke.KNOWN_ELEMENTS))
    result['comparison'] = comparison(stage3)
    return result


def maximum_bootstrap_diagnostics():
    d = smoke.DIAGNOSTICS
    return dict(category=longest(d.CATEGORIES), origin=longest(d.ORIGINS),
        module='ManagedApplicationModule', line=202, identifier=longest(d.IDENTIFIERS),
        native_exit_code=None, source_frames=[dict(module='ManagedApplicationModule', line=202)] * d.MAX_SOURCE_FRAMES,
        source_frames_truncated=False, session_marker=longest(d.MARKER_STATES),
        managed_marker=longest(d.MARKER_STATES), rendered_context=dict(origin='session_marker',
            representation='detailed_error_text', head=[longest(d.CONTEXT_TOKENS)] * 32,
            tail=[longest(d.CONTEXT_TOKENS)] * 32, omitted_middle=False))


def majorant(early=False):
    """Unreachable combinations are intentional upper bounds, never evidence."""
    result = probe()
    result['status'] = longest(smoke.STATUS | {'stage3_failed'})
    result['native_target'] = full.WINDOWS_TARGET  # Longer spelling, even with Map.
    result['container_exit_code'] = None  # Four bytes, vs every permitted exit.
    for key, value in result.items():
        if type(value) is bool:
            result[key] = False
    result['comparison']['native_target'] = full.WINDOWS_TARGET
    for case in result['comparison']['cases']:
        case['native_size'] = 1048576
        if case['mismatch'] is not None:
            case['mismatch']['first_mismatch_byte'] = 1048576
    s = result['stage3']
    s.update(status='not_started', failure_kind=longest(suite.ASYNC_FAILURES), failed_case=longest(full.SCENARIOS))
    for case in s['cases']:
        case.update(status='not_started', output_size=1048576)
    client = s['client_probe']
    client.update(status='not_started', failure_kind=longest(full.FAILURES), process_diagnostics=maximum_process_diagnostics())
    client.update({key: False for key in full.CLIENT_FLAGS})
    measurement = s['client_async']
    measurement.update(status='inconclusive', failure_kind=longest(suite.ASYNC_FAILURES),
        process_diagnostics=maximum_process_diagnostics(),
        failure_diagnostics=MAXIMUM_FAILURE_DIAGNOSTICS.copy())
    if early:
        # A failed bootstrap cannot precede any server/client observation.
        result['stage3']['client_async'] = suite.empty_async_report()
        # Retain maximal server/probe/input metadata anyway. This additionally
        # dominates a final census diagnostic on a never-reached client.
        result['stage2']['diagnostics'] = maximum_bootstrap_diagnostics()
        result['stage2'].update(status='failed', failed_stage=longest(smoke.STAGES),
            failure_kind=longest(smoke.FAILURE_KINDS), actual_version='9999.9999.9999.9999',
            version_source='SystemInfo.AppVersion', security_settings_state='not_attempted', security_change_attempted=False)
        result['runtime_version'] = '9999.9999.9999.9999'
        result['stage2'].update({key: False for key in smoke.STAGE_FLAGS})
        result['stage2']['protection_observation'] = dict(stage='bootstrap',
            property_type='UnsafeOperationProtectionDescription', warning_type='UnsafeOperationProtectionDescription')
    return result


def render_summary(value, *, error=False):
    """The real CLI constructs AND pretty-serializes the report; no copied codec."""
    with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
        path = Path(directory) / 'summary.json'
        options = dict(side_effect=smoke.SmokeError('x'*64, validated_report=copy.deepcopy(value), cleanup_error='x'*64)) if error else dict(return_value=copy.deepcopy(value))
        with mock.patch.object(smoke, 'run_smoke', **options), mock.patch.object(full, 'verify_output_artifact'):
            code = smoke.main(['--execute-approved-image', '--full-suite', '--client-probe',
                '--client-async-measurement', '--native-target', full.LINUX_TARGET,
                '--comparison-mode', full.MAP_MODE, '--export-native-outputs', '--output', str(path)])
        return path.read_bytes(), code


def render_stage(value):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'stage.json'
        suite.write_report(path, value)
        return path.read_bytes()


def render_provenance(record):
    result = probe(record)
    payloads = {case['name']+'.out': b'x' * case['output_size'] for case in result['stage3']['cases']}
    for case in result['stage3']['cases']:
        case['output_sha256'] = full.digest(payloads[case['name']+'.out'])
    result['comparison'] = comparison(result['stage3'])
    files = full.output_artifact_files(payloads, result, smoke.IMAGE)
    return files, result


def proof_results():
    wire = render_stage(majorant()['stage3'])
    late, _ = render_summary(majorant(), error=True)
    early, _ = render_summary(majorant(early=True), error=True)
    files, _ = render_provenance(maximum_observed_record())
    projected = json.loads(files['provenance.json'])
    # At most five additional bytes: all six native sizes independently get
    # seven digits. Likewise each first-mismatch position gets seven digits.
    # The actual builder validates the constrained witness first.
    for case in projected['cases']:
        case['output_size'] = 1048576
        case['mismatch']['first_mismatch_byte'] = 1048576
    projected['native_target'] = full.WINDOWS_TARGET
    return dict(stage_wire_upper_bytes=len(wire), public_summary_late_upper_bytes=len(late),
        public_summary_early_upper_bytes=len(early), provenance_upper_bytes=len(pretty(projected)),
        actual_provenance_boundary_bytes=len(files['provenance.json']),
        conditional_paths=80, failure_prefix_variants=216,
        failure_diagnostic_variants=730, maximum_failure_diagnostic_wire_bytes=10,
        maximum_simultaneous_errors=6, maximum_trace_events_per_case=24,
        staged_paths=24, artifact_classes=7)


class AsyncBudgetTests(unittest.TestCase):
    def test_caps_artifacts_and_staged_inventory_are_unchanged(self):
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT), (8192, 8192))
        self.assertEqual((suite.MAX_REPORT, full.MAX_REPORT, smoke.MAX_OUTPUT), (32768, 32768, 32768))
        self.assertEqual(len(stage()[1]), 24)
        self.assertEqual(full.ARTIFACT_FILES, tuple(name+'.out' for name in full.SCENARIOS) + ('provenance.json',))
        for name in EXTRAS:
            self.assertNotIn(name, stage()[0])
        legacy = suite.empty_report(NONCE, client_probe=True, client_dates=True, client_values=True,
            client_collections=True, client_numbers=True, watchdog_check=True)
        self.assertTrue(all(name in legacy for name in EXTRAS))
        self.assertEqual(suite.encode_stage_wire(legacy)['schema'], 3)
        self.assertEqual(suite.decode_stage_wire(suite.encode_stage_wire(legacy)), legacy)

    def test_measurement_is_separate_and_default_full_options_are_preserved(self):
        # Only copied Windows fixtures use the existing offline adapter.
        # Linux keeps the real production descriptor and identity checks.
        reader = (mock.patch.object(smoke.FULL, 'read_regular', side_effect=read_staging_fixture)
                  if _USE_SYNTHETIC_STAGING_READER else contextlib.nullcontext())
        with reader, tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inputs'
            hashes = smoke.stage_inputs(path, full_suite=True, client_probe=True)
            self.assertEqual(len(hashes), 24)
            standard = dict(full_suite=True, nonce=NONCE, client_probe=True,
                client_dates=True, client_values=True, client_collections=True,
                client_numbers=True, watchdog_check=True)
            command = smoke.container_command(path, 'budget-test', **standard)
            self.assertEqual(command, smoke.container_command(path, 'budget-test', **standard, client_async=False))
            for flag in ('--client-dates-parity', '--client-values-parity', '--client-collections-parity',
                         '--client-numbers-parity', '--client-watchdog-check'):
                self.assertIn(flag, command)
            self.assertNotIn('--client-async-measurement', command)
            with self.assertRaises(smoke.SmokeError):
                smoke.container_command(path, 'budget-test', **standard, client_async=True)
            measurement = smoke.container_command(path, 'budget-test', full_suite=True,
                nonce=NONCE, client_probe=True, client_async=True)
            self.assertIn('--client-async-measurement', measurement)
            self.assertEqual(len(smoke.stage_inputs(Path(directory) / 'again', full_suite=True, client_probe=True)), 24)

    def test_unreached_and_preclient_census_states_stay_finite(self):
        _, inputs, modules = stage()
        empty = suite.empty_report(NONCE, client_probe=True, client_async=True)
        full.validate_stage3(json.loads(render_stage(empty)), NONCE, inputs, modules,
                             prerequisites=False, client_async=True)
        before_client, _, _ = stage()
        before_client.update(status='failed', failure_kind='process_failed')
        before_client['client_probe'] = suite.empty_client_report()
        before_client['client_async'] = suite.empty_async_report()
        suite.fail_client_process_checkpoint(before_client, False, maximum_process_diagnostics())
        full.validate_stage3(json.loads(render_stage(before_client)), NONCE, inputs, modules,
                             prerequisites=True, client_async=True)
        self.assertEqual(before_client['client_async'], suite.empty_async_report())
        self.assertLessEqual(len(render_stage(before_client)), CAPS['stage_wire'])

    def test_structural_maxima_fit_actual_serializers_without_fallback(self):
        result = proof_results()
        self.assertLessEqual(result['stage_wire_upper_bytes'], CAPS['stage_wire'])
        self.assertLessEqual(result['public_summary_late_upper_bytes'], CAPS['public_summary'])
        self.assertLessEqual(result['public_summary_early_upper_bytes'], CAPS['public_summary'])
        self.assertLessEqual(result['provenance_upper_bytes'], CAPS['provenance'])
        for early in (False, True):
            raw, _ = render_summary(majorant(early=early), error=True)
            self.assertIn('probe', json.loads(raw))
            self.assertNotEqual(json.loads(raw).get('error'), 'public_report_limit')
        raw = render_stage(majorant()['stage3'])
        self.assertEqual(full.decode_stage3_wire(json.loads(raw)), majorant()['stage3'])

    def test_all_80_conditional_paths_use_real_codecs_and_projection(self):
        seen = set()
        for record in successful_records():
            seen.add(compact(record))
            suite.validate_async_report(record, TEMPLATE, MODULES)
            full.validate_client_async(record, TEMPLATE, MODULES)
            self.assertIsNone(record['failure_diagnostics'])
            self.assertLessEqual(sum(len(row[7]) for row in record['cases']), 6)
            s, inputs, modules = stage(record)
            raw = render_stage(s)
            full.validate_stage3(json.loads(raw), NONCE, inputs, modules, prerequisites=True, client_async=True)
            summary, _ = render_summary(probe(record))
            self.assertIn('probe', json.loads(summary))
            files, _ = render_provenance(record)
            self.assertEqual(tuple(files), full.ARTIFACT_FILES)
            self.assertEqual(json.loads(files['provenance.json'])['client_async'], record)
            self.assertLessEqual(len(summary), CAPS['public_summary'])
        self.assertEqual(len(seen), 80)

    def test_failure_inconclusive_prefixes_remain_bounded_and_nonexportable(self):
        count = 0
        for record in failure_records():
            count += 1
            suite.validate_async_report(record, TEMPLATE, MODULES)
            full.validate_client_async(record, TEMPLATE, MODULES)
            self.assertEqual(record['failure_diagnostics'], MAXIMUM_FAILURE_DIAGNOSTICS)
            self.assertIsNone(record['continuity_sha256'])
            self.assertTrue(all(row[4:] == [0, [], [], []]
                                for row in record['cases'] if row[1] != 1))
            s, inputs, modules = stage(record)
            full.validate_stage3(json.loads(render_stage(s)), NONCE, inputs, modules, prerequisites=True, client_async=True)
            summary, code = render_summary(probe(record))
            result = json.loads(summary)
            self.assertEqual(code, 1)
            self.assertFalse(result['client_async_measurement_completed'])
            self.assertFalse(result['client_async_parity_claimed'])
            self.assertIn('probe', result)
            self.assertLessEqual(len(summary), CAPS['public_summary'])
            with self.assertRaises(full.FullError):
                full.output_artifact_files(dict.fromkeys(full.ARTIFACT_FILES[:-1], b''), probe(record), smoke.IMAGE)
        self.assertEqual(count, 216)

    def test_final_census_invalidates_every_reached_prefix_without_growth(self):
        records = [maximum_observed_record(), *failure_records()]
        for record in records:
            s, inputs, modules = stage(record)
            suite.fail_client_process_checkpoint(s, False, maximum_process_diagnostics())
            full.validate_stage3(json.loads(render_stage(s)), NONCE, inputs, modules, prerequisites=True, client_async=True)
            self.assertEqual(s['status'], 'failed')
            self.assertEqual(s['client_async']['status'], 'failed')
            self.assertIsNone(s['client_async']['failure_diagnostics'])
            self.assertIsNone(s['client_async']['continuity_sha256'])
            self.assertTrue(all(row[4:] == [0, [], [], []]
                                for row in s['client_async']['cases'] if row[1] != 1))
            self.assertFalse(any(row[1] == 3 for row in s['client_async']['cases']))
            self.assertLessEqual(len(render_stage(s)), CAPS['stage_wire'])

    def test_every_finite_failure_diagnostic_encoding_is_bounded(self):
        self.assertEqual((len(suite.ASYNC_HOST_STAGES), len(suite.ASYNC_MARKER_STATES),
                          len(suite.ASYNC_LOG_CATEGORIES)), (6, 4, 18))
        self.assertEqual(len(compact(MAXIMUM_FAILURE_DIAGNOSTICS)), 10)
        record = next(failure_records())
        maximum_wire = len(render_stage(stage(record)[0]))
        maximum_public = len(pretty(record))
        original_rows = copy.deepcopy(record['cases'])
        count = 0
        # Exhaust the finite product independently of either validator. JSON
        # size is additive: all legal lists have four fixed-width integers,
        # with only the category ever taking two digits. Null is shorter.
        for value in (None, *map(list, itertools.product(range(6), range(4), range(4), range(18)))):
            allowed = value is None or (
                (value[0] >= 3 or value[1:3] == [0, 0])
                and (value[0] != 0 or value[3] == 0)
                and (value[3] < 13 or value[0] >= 3)
                and (value[2] != 3 or value[1] == 3))
            record['failure_diagnostics'] = value
            if not allowed:
                with self.assertRaises(suite.FullError):
                    suite.validate_async_report(record, TEMPLATE, MODULES)
                with self.assertRaises(ValueError):
                    full.validate_client_async(record, TEMPLATE, MODULES)
                continue
            count += 1
            suite.validate_async_report(record, TEMPLATE, MODULES)
            full.validate_client_async(record, TEMPLATE, MODULES)
            wire = render_stage(stage(record)[0])
            restored = full.decode_stage3_wire(json.loads(wire))['client_async']
            self.assertEqual(restored, record)
            self.assertEqual(restored['cases'], original_rows)
            self.assertIsNone(restored['continuity_sha256'])
            self.assertLessEqual(len(wire), maximum_wire)
            self.assertLessEqual(len(pretty(record)), maximum_public)
        self.assertEqual(count, 730)

    def test_process_counter_width_bound_is_derived_not_independent_maxima(self):
        # DP over seven nonnegative counters with a <=256 sum proves 16
        # decimal digits is the maximum. Zombie and unexpected are <=256.
        dp = {0: 0}
        for _ in CLASSES:
            dp = {total: max(dp[total-value] + len(str(value)) for value in range(total+1) if total-value in dp)
                  for total in range(257)}
        self.assertEqual(max(dp.values()), 16)
        diagnostic = maximum_process_diagnostics()
        full.validate_process_diagnostics(diagnostic)
        self.assertEqual(sum(map(lambda n: len(str(n)), diagnostic['classes'].values())), 16)

    def test_longest_fixed_host_failure_code_has_reserved_64_byte_bound(self):
        # Public error messages are fixed constructor constants or propagation
        # of those errors, never diagnostic text. Audit all literal candidates
        # in the two host modules; 64 safely bounds even unrelated constants.
        for source in (Path(smoke.__file__), Path(full.__file__)):
            tree = ast.parse(source.read_text())
            errors = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                and node.args and isinstance(node.args[0], ast.Constant) and type(node.args[0].value) is str
                and isinstance(node.func, (ast.Name, ast.Attribute))
                and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) in ('SmokeError', 'FullError')]
            self.assertTrue(errors)
            self.assertLessEqual(max(map(len, errors)), 64)


if __name__ == '__main__':
    unittest.main()

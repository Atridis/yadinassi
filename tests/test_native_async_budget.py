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
The failure-only diagnostic tuple has 1743 legal encodings, plus null; its
longest compact encoding is ten bytes. The late majorant includes that tuple
even alongside every completed observation, a deliberately unreachable bound.
Marker validation hints are enumerated independently for all eight failed-row
positions. They require an invalid-result row, so a separate majorant replaces
that row and all later rows with empty, failed/unreached observations. This keeps
all production applicability checks active; no validator is patched for size.
The standard client's 423 finite marker diagnostics are bounded independently;
both majorants include the longest diagnostic even when it is unreachable.
The strict dual suffix is one fixed string in the private136 witness; it adds
no public diagnostic payload. All generic finite failure limits remain intact.
Host-side Async comparison adds only a compact result to public summary and
artifact provenance, never to stage wire. Eight runtimeerror mismatches are the
longest valid comparator result; all existing early/late/marker partitions retain
that additional majorant, even when runtime comparison cannot have been reached.
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
from test_native_1c_full_host import fixture, NONCE, SyntheticFilesystemCase
from test_native_1c_smoke import (smoke, bootstrap_report, read_staging_fixture,
                                  _USE_SYNTHETIC_STAGING_READER)

suite, full = protocol.suite, protocol.full
H = 'f' * 64
TEMPLATE = full.ASYNC_EXPECTED_IDENTITY['template']
MODULES = full.ASYNC_EXPECTED_IDENTITY['modules']
EXTRAS = ('client_dates', 'client_values', 'client_collections', 'client_numbers', 'client_watchdog')
CLASSES = ('native', 'display', 'session_bus', 'shell', 'python', 'other', 'unreadable')
CAPS = {'stage_wire': 8192, 'public_summary': 32768, 'provenance': 32768}
STAGED_PATHS = (
    'integrational_tests/launcher_1c/Launcher.xml',
    'integrational_tests/launcher_1c/Launcher/Ext/ObjectModule.bsl',
    'integrational_tests/launcher_1c/Launcher/Forms/Main.xml',
    'integrational_tests/launcher_1c/Launcher/Forms/Main/Ext/Form.xml',
    'integrational_tests/launcher_1c/Launcher/Forms/Main/Ext/Form/Module.bsl',
    'integrational_tests/launcher_1c/TestModule.xml',
    'integrational_tests/launcher_1c/TestModule/Ext/ObjectModule.bsl',
    'integrational_tests/test_launcher.py',
    'integrational_tests/tests/collections.bsl',
    'integrational_tests/tests/dates.bsl',
    'integrational_tests/tests/functions.bsl',
    'integrational_tests/tests/numbers.bsl',
    'integrational_tests/tests/strings.bsl',
    'integrational_tests/tests/values.bsl',
    'scripts/native_1c_bootstrap/client_probe.bsl',
    'scripts/native_1c_bootstrap/diagnostics.py',
    'scripts/native_1c_bootstrap/evidence_gates.py',
    'scripts/native_1c_bootstrap/full_suite.py',
    'scripts/native_1c_bootstrap/inject_modules.py',
    'scripts/native_1c_bootstrap/modules/ManagedApplicationModule.bsl',
    'scripts/native_1c_bootstrap/modules/SessionModule.bsl',
    'scripts/native_1c_bootstrap/run_stage.py',
    'scripts/native_1c_bootstrap/simple_smoke.bsl',
    'scripts/native_1c_smoke_probe.sh',
)
ARTIFACT_CLASSES = ('collections.out', 'dates.out', 'functions.out', 'numbers.out',
                    'strings.out', 'values.out', 'provenance.json')
MAXIMUM_FAILURE_DIAGNOSTICS = [5, 3, 3, 43]
MAXIMUM_MARKER_VALIDATION_FAILURE = [1, 38, 3, 28]
# Frozen independently from the production validators.
MARKER_CASE_SLOTS = (4, 3, 5, 3, 4, 7, 3, 3)
MARKER_CASE_EDGES = (9, 10, 20, 10, 12, 7, 15, 8)


def marker_validation_allowed(case_id, value):
    if value is None:
        return True
    phase, site, descriptor, locator = value
    if phase == 0 and site not in (*range(1, 10), 42):
        return False
    if 14 <= site <= 26:
        if descriptor == 3:
            return False
        if site in (14, 26):
            return locator == 31
        if site in (15, 16):
            return locator == site - 15
        if site == 25:
            return 2 <= locator <= 9 or locator == 31
        return 2 <= locator <= 9
    if site in (34, 35):
        return descriptor < 3 and locator < MARKER_CASE_SLOTS[case_id]
    if descriptor != 3:
        return False
    if site in (29, 38, 39):
        return locator <= 28
    if site in (31, 32, 33, 37):
        return locator < MARKER_CASE_SLOTS[case_id]
    if site == 40:
        return locator < MARKER_CASE_EDGES[case_id]
    if site == 41:
        return case_id == 7 and locator == 2
    return locator == 31


def marker_validation_variants(case_id):
    yield None
    for value in itertools.product(range(2), range(1, 43), range(4), range(32)):
        if marker_validation_allowed(case_id, value):
            yield list(value)


def marker_failure_record(case_id, phase=1):
    value = maximum_observed_record()
    value.update(status='failed', failure_kind='invalid_result', continuity_sha256=None,
                 failure_diagnostics=[4, 3, 2, 43] if phase else [4, 2, 0, 43],
                 marker_validation_failure=MAXIMUM_MARKER_VALIDATION_FAILURE.copy())
    value['cases'][case_id:] = [[case_id, 2, 4, MODULES[case_id], 0, [], [], []]] + [
        [case, 0, 1, None, 0, [], [], []] for case in range(case_id + 1, 8)]
    return value


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


def maximum_standard_marker_diagnostics():
    # Longest finite diagnostic: runtime_error with two-digit stage and ordinal.
    return dict(phase='completed', kind='runtime_error', ordinal=14, error_stage=11)


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
                profile=full.MAP_MODE, records=1022, byte_equal_records=1014,
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
    result['async_comparison'] = maximum_async_comparison()
    return result


def maximum_async_comparison():
    result = dict(profile='async-language-8-v1', status='mismatched',
                  cases=[['mismatched', 'runtimeerror'] for _ in range(8)], actual_sha256=H)
    full.validate_async_comparison(result)
    return result


def accepted_comparison(stage3):
    result = comparison(stage3)
    result.update(status='ok', acceptance_status='accepted')
    for native, case in zip(stage3['cases'], result['cases']):
        case.update(status='matched', acceptance_status='accepted', mismatch=None,
                    interpreter_size=native['output_size'], interpreter_sha256=native['output_sha256'])
        if case['name'] == 'collections':
            case['semantic'].update(byte_equal_records=1022, accepted_labels=[])
    full.validate_comparison(result, stage3, full.LINUX_TARGET, full.MAP_MODE)
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


def majorant(early=False, marker_case=None):
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
    client.update(status='not_started', failure_kind=longest(full.FAILURES),
        process_diagnostics=maximum_process_diagnostics(),
        marker_diagnostics=maximum_standard_marker_diagnostics())
    client.update({key: False for key in full.CLIENT_FLAGS})
    measurement = s['client_async']
    measurement.update(status='inconclusive', failure_kind=longest(suite.ASYNC_FAILURES),
        process_diagnostics=maximum_process_diagnostics(),
        failure_diagnostics=MAXIMUM_FAILURE_DIAGNOSTICS.copy())
    if marker_case is not None:
        # A nonnull marker hint necessarily consumes a failed row and rules
        # out later observations. Use its own production-valid partition.
        value = marker_failure_record(marker_case)
        value['process_diagnostics'] = maximum_process_diagnostics()
        s['client_async'] = value
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


def render_summary(value, *, error=False, artifact_error=False):
    """The real CLI constructs AND pretty-serializes the report; no copied codec."""
    with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
        path = Path(directory) / 'summary.json'
        options = dict(side_effect=smoke.SmokeError('x'*64, validated_report=copy.deepcopy(value), cleanup_error='x'*64)) if error else dict(return_value=copy.deepcopy(value))
        with mock.patch.object(smoke, 'run_smoke', **options), mock.patch.object(full, 'verify_output_artifact', side_effect=full.FullError('native_artifact_evidence_invalid') if artifact_error else None):
            code = smoke.main(['--execute-approved-image', '--full-suite', '--client-probe',
                '--client-async-measurement', '--native-target', full.LINUX_TARGET,
                '--comparison-mode', full.MAP_MODE, '--export-native-outputs', '--output', str(path)])
        # The production cap measures rendered UTF-8 text before write_text.
        # Native execution is Linux-only, where that text is written with LF.
        # Windows test files may gain CRLF during text I/O: universal-newline
        # reading recovers exactly the Linux serializer bytes, not a new codec.
        return path.read_text(encoding='utf-8').encode('utf-8'), code


def render_stage(value):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'stage.json'
        suite.write_report(path, value)
        # This production writer uses binary xb/write, so its wire bytes must
        # remain exact on every OS; never normalize or reserialize the wire.
        return path.read_bytes()


def render_provenance(record, *, async_result=None, accepted=False):
    result = probe(record)
    payloads = {case['name']+'.out': b'x' * case['output_size'] for case in result['stage3']['cases']}
    from test_native_tree_move_contract import synthetic_output
    payloads['collections.out'] = synthetic_output(result['stage3']['cases'][0]['output_size'])
    result['stage3']['cases'][0]['message_count'] = 1022
    for case in result['stage3']['cases']:
        case['output_sha256'] = full.digest(payloads[case['name']+'.out'])
    result['comparison'] = accepted_comparison(result['stage3']) if accepted else comparison(result['stage3'])
    if async_result is not None:
        result['async_comparison'] = copy.deepcopy(async_result)
    files = full.output_artifact_files(payloads, result, smoke.IMAGE)
    return files, result


def proof_results():
    partitions = [majorant(marker_case=case) for case in (None, *range(8))]
    wire = max((render_stage(value['stage3']) for value in partitions), key=len)
    late = max((render_summary(value, error=True)[0] for value in partitions), key=len)
    early = render_summary(majorant(early=True), error=True)[0]
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
        failure_diagnostic_variants=1744, maximum_failure_diagnostic_wire_bytes=10,
        standard_marker_diagnostic_variants=423,
        strict_witness_entries=136, dense_dual_token_bytes=35,
        diagnostic_shape_partitions=1,
        marker_validation_diagnostic_variants=sum(len(list(marker_validation_variants(case))) for case in range(8)),
        marker_validation_diagnostic_variants_by_case=[len(list(marker_validation_variants(case))) for case in range(8)],
        maximum_marker_validation_diagnostic_wire_bytes=11,
        maximum_simultaneous_errors=6, maximum_trace_events_per_case=24,
        staged_paths=24, artifact_classes=7,
        async_comparison_compact_bytes=len(compact(maximum_async_comparison())))


class AsyncBudgetTests(SyntheticFilesystemCase):
    def test_linux_serializer_bound_is_independent_of_crlf_text_transport(self):
        value = majorant()
        expected, expected_code = render_summary(value, error=True)
        wire = render_stage(value['stage3'])
        written = []

        def windows_text_write(path, text, encoding=None, errors=None, newline=None):
            # Explicitly simulate Windows write_text transport on every runner.
            # JSON string newlines are escaped, so only formatting LF expands.
            raw = text.replace('\n', '\r\n').encode(encoding or 'utf-8', errors or 'strict')
            written.append(raw)
            path.write_bytes(raw)
            return len(text)

        with mock.patch.object(Path, 'write_text', windows_text_write):
            actual, code = render_summary(value, error=True)
            without = copy.deepcopy(value)
            del without['async_comparison']
            smaller, _ = render_summary(without, error=True)
            self.assertEqual(render_stage(value['stage3']), wire)
        self.assertEqual(code, expected_code)
        self.assertEqual(actual, expected)
        self.assertEqual(json.loads(actual), json.loads(written[0]))
        self.assertEqual(written[0], expected.replace(b'\n', b'\r\n'))
        self.assertGreater(len(written[0]), len(expected))
        self.assertLessEqual(len(actual), CAPS['public_summary'])
        self.assertEqual(len(actual) - len(smaller), 778)
        # Wire producer is already binary: preserve exact production bytes and
        # run the decoder rather than silently changing its transport.
        self.assertNotIn(b'\r', wire)
        self.assertNotIn(b'\n', wire)
        self.assertEqual(full.decode_stage3_wire(json.loads(wire)), value['stage3'])
        self.assertLessEqual(len(wire), CAPS['stage_wire'])

    def test_compact_async_result_maximum_is_production_valid(self):
        maximum = maximum_async_comparison()
        for code in ('none', 'trace', 'values', 'errors', 'lifecycle', 'runtimeerror'):
            status = 'matched' if code == 'none' else 'mismatched'
            value = dict(profile='async-language-8-v1', status=status,
                         cases=[[status, code] for _ in range(8)], actual_sha256=H)
            full.validate_async_comparison(value)
            self.assertLessEqual(len(compact(value)), len(compact(maximum)))
            self.assertLessEqual(len(pretty(value)), len(pretty(maximum)))
        value = majorant()
        self.assertNotIn('async_comparison', value['stage3'])
        with_result, _ = render_summary(value, error=True)
        without = copy.deepcopy(value)
        del without['async_comparison']
        without_result, _ = render_summary(without, error=True)
        self.assertEqual(len(with_result) - len(without_result), 778)
        self.assertEqual(json.loads(with_result)['probe']['async_comparison'], maximum)

    def test_accepted_native_fixture_and_comparator_gates_use_real_serializers(self):
        from scripts import native_async_comparison as adapter
        root = Path(__file__).resolve().parents[1]
        fixture_path = root / 'tests/fixtures/native_async_comparison_linux_8_3_27_1508.json'
        native = json.loads(fixture_path.read_text(encoding='utf-8'))['client_async']
        template, sources = adapter.read_pinned_sources((root / 'scripts/native_1c_bootstrap/full_suite.py').read_bytes())
        matched = adapter.compare(template, sources, native)
        self.assertEqual(matched['status'], 'matched')
        files, value = render_provenance(native, async_result=matched, accepted=True)
        metadata = json.loads(files['provenance.json'])
        self.assertEqual(metadata['async_comparison'], matched)
        self.assertTrue(metadata['client_async_parity_claimed'])
        raw, code = render_summary(value)
        public = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertTrue(public['client_async_parity_claimed'])
        self.assertTrue(public['smoke_completed'])
        self.assertLessEqual(len(raw), CAPS['public_summary'])
        self.assertLessEqual(len(files['provenance.json']), CAPS['provenance'])
        variants = [None, {}, {'status': 'matched'}, maximum_async_comparison()]
        for mismatch in ('trace', 'values', 'errors', 'lifecycle', 'runtimeerror'):
            changed = copy.deepcopy(matched)
            changed['status'] = 'mismatched'
            changed['cases'][0] = ['mismatched', mismatch]
            variants.append(changed)
        for candidate in variants:
            changed = copy.deepcopy(value)
            if candidate is None:
                changed.pop('async_comparison')
            else:
                changed['async_comparison'] = candidate
            raw, code = render_summary(changed)
            public = json.loads(raw)
            self.assertEqual(code, 1)
            self.assertFalse(public['client_async_parity_claimed'])
            self.assertFalse(public['smoke_completed'])
            self.assertLessEqual(len(raw), CAPS['public_summary'])
        # An accepted Async result cannot erase any native security/evidence gate.
        for gate in ('native_evidence_accepted', 'native_transport_validated',
                     'native_cases_completed', 'container_cleanup_verified',
                     'private_payloads_removed', 'windows_goldens_unchanged'):
            changed = copy.deepcopy(value)
            changed[gate] = False
            raw, code = render_summary(changed)
            public = json.loads(raw)
            self.assertEqual(code, 1)
            self.assertFalse(public['client_async_parity_claimed'])
            with self.assertRaises(full.FullError):
                full.output_artifact_files({name: files[name] for name in full.ARTIFACT_FILES[:-1]}, changed, smoke.IMAGE)
        for error, artifact_error in ((True, False), (False, True)):
            raw, code = render_summary(value, error=error, artifact_error=artifact_error)
            public = json.loads(raw)
            self.assertEqual(code, 1)
            self.assertFalse(public['client_async_parity_claimed'])
            self.assertFalse(public['smoke_completed'])
            self.assertLessEqual(len(raw), CAPS['public_summary'])
        rejected_files, _ = render_provenance(native, async_result=matched, accepted=False)
        self.assertFalse(json.loads(rejected_files['provenance.json'])['client_async_parity_claimed'])
        mismatch_files, _ = render_provenance(native, async_result=maximum_async_comparison(), accepted=True)
        self.assertFalse(json.loads(mismatch_files['provenance.json'])['client_async_parity_claimed'])

    def test_caps_artifacts_and_staged_inventory_are_unchanged(self):
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT), (8192, 8192))
        self.assertEqual((suite.MAX_REPORT, full.MAX_REPORT, smoke.MAX_OUTPUT), (32768, 32768, 32768))
        self.assertEqual(len(stage()[1]), 24)
        self.assertEqual(tuple(sorted(stage()[1])), STAGED_PATHS)
        self.assertEqual(full.ARTIFACT_FILES, ARTIFACT_CLASSES)
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
            self.assertEqual(tuple(sorted(hashes)), STAGED_PATHS)
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
            self.assertIsNone(record['marker_validation_failure'])
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
        records = [maximum_observed_record(), *failure_records(),
                   *(marker_failure_record(case) for case in range(8))]
        for record in records:
            s, inputs, modules = stage(record)
            suite.fail_client_process_checkpoint(s, False, maximum_process_diagnostics())
            full.validate_stage3(json.loads(render_stage(s)), NONCE, inputs, modules, prerequisites=True, client_async=True)
            self.assertEqual(s['status'], 'failed')
            self.assertEqual(s['client_async']['status'], 'failed')
            self.assertIsNone(s['client_async']['failure_diagnostics'])
            self.assertIsNone(s['client_async']['marker_validation_failure'])
            self.assertIsNone(s['client_async']['continuity_sha256'])
            self.assertTrue(all(row[4:] == [0, [], [], []]
                                for row in s['client_async']['cases'] if row[1] != 1))
            self.assertFalse(any(row[1] == 3 for row in s['client_async']['cases']))
            self.assertLessEqual(len(render_stage(s)), CAPS['stage_wire'])

    def test_every_finite_failure_diagnostic_encoding_is_bounded(self):
        self.assertEqual((len(suite.ASYNC_HOST_STAGES), len(suite.ASYNC_MARKER_STATES),
                          len(suite.ASYNC_LOG_CATEGORIES)), (6, 4, 44))
        self.assertEqual(len(compact(MAXIMUM_FAILURE_DIAGNOSTICS)), 10)
        record = next(failure_records())
        maximum_wire = len(render_stage(stage(record)[0]))
        maximum_public = len(pretty(record))
        original_rows = copy.deepcopy(record['cases'])
        count = 0
        # Exhaust the finite product independently of either validator. JSON
        # size is additive: all legal lists have four fixed-width integers,
        # with only the category ever taking two digits. Null is shorter.
        for value in (None, *map(list, itertools.product(range(6), range(4), range(4), range(44)))):
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
        self.assertEqual(count, 1744)

    def test_every_finite_marker_validation_hint_uses_real_codecs_and_stays_failure_only(self):
        self.assertEqual(tuple(suite.ASYNC_SLOTS), MARKER_CASE_SLOTS)
        self.assertEqual(tuple(map(len, suite.ASYNC_EDGES)), MARKER_CASE_EDGES)
        self.assertEqual(len(compact(MAXIMUM_MARKER_VALIDATION_FAILURE)), 11)
        counts = []
        for case_id in range(8):
            record = marker_failure_record(case_id)
            maximum_wire = len(render_stage(stage(record)[0]))
            maximum_public = len(pretty(record))
            original_rows = copy.deepcopy(record['cases'])
            count = 0
            values = itertools.chain((None,), map(list, itertools.product(range(2), range(1, 43), range(4), range(32))))
            for value in values:
                record['marker_validation_failure'] = value
                record['failure_diagnostics'] = [4, 2, 0, 43] if value is not None and value[0] == 0 else [4, 3, 2, 43]
                if not marker_validation_allowed(case_id, value):
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
                self.assertEqual(restored['cases'][case_id][4:], [0, [], [], []])
                self.assertLessEqual(len(wire), maximum_wire)
                self.assertLessEqual(len(pretty(record)), maximum_public)
            counts.append(count)
            summary, code = render_summary(probe(record))
            public = json.loads(summary)
            self.assertEqual(code, 1)
            self.assertFalse(public['client_async_measurement_completed'])
            self.assertFalse(public['client_async_parity_claimed'])
            self.assertLessEqual(len(summary), CAPS['public_summary'])
            with self.assertRaises(full.FullError):
                full.output_artifact_files(dict.fromkeys(full.ARTIFACT_FILES[:-1], b''), probe(record), smoke.IMAGE)
        self.assertEqual(counts, [396, 387, 417, 387, 399, 424, 392, 386])

    def test_standard_client_witness_and_marker_diagnostics_remain_bounded(self):
        expected = [42, 'client-probe', 3, 6,
            'directive.call.add: {"N",42}',
            'directive.preprocessor.server: server',
            'directive.preprocessor.client: client',
            'directive.call.nested: server',
            'directive.param.val: {"N",7}',
            'directive.exception: {"B",1}',
            'directive.return.number: {"N",42}',
            'directive.return.string: {"S","x"}',
            'directive.return.boolean: {"B",1}',
            'directive.return.undefined: {"U"}',
            'directive.call.recovery: {"N",42}',
            'copyback.core.v1', '{"B",1}', '{"B",0}', '{"N",43}', '{"B",0}',
            '{"N",1}', '{"B",0}', '{"N",97}', '{"N",43}', '{"B",0}',
            '{"B",1}', '{"N",47}', '{"B",1}', '{"B",1}', '{"N",1}',
            '{"N",2}', '{"N",3}', '{"B",0}', '{"N",1}', '{"N",1}',
            '{"B",0}', '{"N",52}', '{"B",0}', '{"N",1}', '{"B",0}',
            '{"N",1}', '{"B",0}', '{"N",1}', '{"B",0}', '{"N",192}',
            '{"N",9}', '{"N",2}', '{"B",0}', '{"N",43}', '{"B",1}']
        # Independently frozen from the audited native object-transfer capture.
        expected += ['object.transfer.v1', True, False, 1, 1, 1, False, 2, 21,
            23, 23, 2, False, 3, 3, 3, False, 41, 42, 4, False, 5, 51, 51, 51,
            51, 52, 51, 5, True, True, False, 6, 6, 6, False, 7, 8, False, 73,
            73, 73, 72, 1, False, True, 82, 10, True, False, 73, 72, 72, 74,
            11, 73, 74, 72, 1]
        expected += ['module.context.v1', 10, 100, 111, True, 100, True, 100, True, 11]
        expected += ['nocontext.core.v3', 12, 22, 0, 12, 2, True, 16, True, 6, 14, 14, True, 7, 18]
        expected += ['dual.v1:000032017000017041000032017']
        # Independent captured Date/Null observations, not a replacement dual token.
        expected += ['dn.v1:22222277']
        self.assertEqual(len(expected), 136)
        self.assertEqual(suite.CLIENT_VALUES, expected)
        self.assertEqual(full.CLIENT_VALUES, expected)
        current = expected + ['ibc.v1:121122221122021122021122021122']
        self.assertEqual(full.CLIENT_RUNTIME_VALUES, current)
        self.assertEqual(suite.CLIENT_RUNTIME_VALUES, current)
        self.assertEqual(len(current), 137)
        # Freeze bool/int distinctions as well as equality for the strict119
        # witness and its nine side-local module-context observations.
        self.assertEqual(list(map(type, suite.CLIENT_VALUES)), list(map(type, expected)))
        self.assertEqual(list(map(type, full.CLIENT_VALUES)), list(map(type, expected)))
        maximum = maximum_standard_marker_diagnostics()
        full.validate_marker_diagnostics(maximum)
        self.assertEqual(set(maximum), {"phase", "kind", "ordinal", "error_stage"})
        count = 0
        for phase, kind, ordinal, error_stage in itertools.product(
                ('invalid', 'error', 'completed'),
                ('none', 'count', 'type', 'value', 'runtime_error'),
                range(-1, 139), range(12)):
            diagnostic = dict(phase=phase, kind=kind, ordinal=ordinal, error_stage=error_stage)
            if phase != 'completed':
                allowed = kind == 'none' and ordinal == -1 and error_stage == 0
            elif kind == 'runtime_error':
                allowed = 1 <= error_stage <= 11 and ordinal == error_stage + 3
            elif kind == 'count':
                allowed = 0 <= ordinal <= 137 and error_stage == 0
            elif kind in ('type', 'value'):
                allowed = 0 <= ordinal < 137 and error_stage == 0
            else:
                allowed = ordinal == -1 and error_stage == 0
            if not allowed:
                with self.assertRaises(ValueError):
                    full.validate_marker_diagnostics(diagnostic)
                continue
            count += 1
            full.validate_marker_diagnostics(diagnostic)
            self.assertLessEqual(len(compact(diagnostic)), len(compact(maximum)))
            self.assertLessEqual(len(pretty(diagnostic)), len(pretty(maximum)))
            s, inputs, modules = stage(suite.empty_async_report())
            s.update(status='failed', failure_kind='invalid_result')
            s['client_probe'].update(status='failed', failure_kind='invalid_result',
                witness_verified=False, marker_diagnostics=diagnostic)
            wire = render_stage(s)
            full.validate_stage3(json.loads(wire), NONCE, inputs, modules,
                                 prerequisites=True, client_async=True)
            self.assertEqual(full.decode_stage3_wire(json.loads(wire)), s)
            result = probe(suite.empty_async_report())
            result['stage3'] = s
            summary, code = render_summary(result)
            public = json.loads(summary)
            self.assertEqual(code, 1)
            self.assertFalse(public['client_async_measurement_completed'])
            self.assertFalse(public['client_async_parity_claimed'])
            self.assertEqual(s['client_async'], suite.empty_async_report())
            self.assertNotIn(b'directive.', wire + summary)
            self.assertNotIn(b'copyback.core.', wire + summary)
            self.assertNotIn(b'object.transfer.', wire + summary)
            self.assertNotIn(b'module.context.', wire + summary)
            self.assertLessEqual(len(wire), CAPS['stage_wire'])
            self.assertLessEqual(len(summary), CAPS['public_summary'])
            with self.assertRaises(full.FullError):
                full.output_artifact_files(dict.fromkeys(full.ARTIFACT_FILES[:-1], b''), result, smoke.IMAGE)
        self.assertEqual(count, 426)

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
            tree = ast.parse(source.read_text(encoding="utf-8"))
            errors = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                and node.args and isinstance(node.args[0], ast.Constant) and type(node.args[0].value) is str
                and isinstance(node.func, (ast.Name, ast.Attribute))
                and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) in ('SmokeError', 'FullError')]
            self.assertTrue(errors)
            self.assertLessEqual(max(map(len, errors)), 64)


if __name__ == '__main__':
    unittest.main()

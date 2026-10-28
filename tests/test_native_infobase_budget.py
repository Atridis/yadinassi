"""Offline finite budgets, not native infobase observations or expected results.

Async is mutually exclusive with the five parity/watchdog options. Its existing
18 structural majorants therefore form one family; all 32 parity subsets form
the other. Successful captures pass the real host validator and both codecs.
Failure majorants never receive an inadmissible capture: their serializer sizes
are charged the independently measured fixed-field overhead arithmetically.
No production validator or serializer is patched to accept a size witness.
"""
from __future__ import annotations

import contextlib
import copy
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_async_budget as budget
import test_native_client_collections_host as collections
from test_native_1c_full_host import SyntheticFilesystemCase

full, suite, smoke = budget.full, budget.suite, budget.smoke
# Runtime-positive budget witnesses use the independently captured exact token.
# Other grammar strings below remain size witnesses, never runtime acceptance.
SIZE_TOKEN = full.INFOBASE_CONTEXT_EXPECTED_TOKEN
OPTION_NAMES = ('client_dates', 'client_values', 'client_collections',
                'client_numbers', 'watchdog_check')
RECORD_NAMES = OPTION_NAMES[:-1] + ('client_watchdog',)
COUNTS = {'dates': 185, 'values': 534, 'collections': 1023, 'numbers': 421}
CLI_FLAGS = ('--client-dates-parity', '--client-values-parity',
             '--client-collections-parity', '--client-numbers-parity',
             '--client-watchdog-check')
WIRE_INCREMENT = 59
SUMMARY_INCREMENT = 69


def bind_capture(stage, inputs, modules):
    inputs[full.CLIENT_SOURCE] = full.INFOBASE_CONTEXT_SOURCE_SHA256
    modules['client_probe'] = full.INFOBASE_CONTEXT_MODULE_SHA256
    for name in ('client_probe', 'client_watchdog'):
        if name in stage:
            stage[name].update(source_sha256=full.INFOBASE_CONTEXT_SOURCE_SHA256,
                module_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
                roundtrip_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256)
    stage['client_probe']['infobase_context'] = SIZE_TOKEN


def parity_stage(selected):
    fixture = collections.ClientCollectionsHostTests()
    fixture.setUp()
    stage = fixture.all_clients()
    native = stage['cases'][full.SCENARIOS.index('numbers')]
    fixture.inputs[full.NUMBERS_SOURCE] = full.NUMBERS_SOURCE_SHA256
    fixture.modules['client_numbers'] = '4' * 64
    native.update(source_sha256=full.NUMBERS_SOURCE_SHA256, message_count=421)
    stage['client_numbers'] = dict(copy.deepcopy(stage['client_values']),
        source_sha256=full.NUMBERS_SOURCE_SHA256, module_sha256='4' * 64,
        roundtrip_sha256='4' * 64, conversion_verified=True,
        **{key: native[key] for key in collections.OUTPUT_KEYS})
    for name, present in zip(RECORD_NAMES, selected):
        if not present:
            del stage[name]
    # All six sizes have six decimal digits; separately charging one digit per
    # size below dominates every permitted seven-digit counter and repetition.
    for native in stage['cases']:
        native.update(output_size=100000, message_count=32768)
    for scenario, count in COUNTS.items():
        name = 'client_' + scenario
        if name in stage:
            native = stage['cases'][full.SCENARIOS.index(scenario)]
            native['message_count'] = count
            stage[name].update(**{key: native[key] for key in collections.OUTPUT_KEYS})
    bind_capture(stage, fixture.inputs, fixture.modules)
    if 'client_collections' in stage:
        # The optional null diagnostic is accepted and larger than omission.
        stage['client_collections']['mismatch'] = None
    return stage, fixture.inputs, fixture.modules


def failed_frontier(stage, index, *, marker=False, mismatch=False):
    """A production-valid completed prefix, one failure and unreached suffix."""
    result = copy.deepcopy(stage)
    full.discard_infobase_capture(result)
    order = ['client_probe'] + [name for name in RECORD_NAMES if name in result]
    failure = result[order[index]]
    result.update(status='failed', failure_kind=budget.longest(
        full.FAILURES - {'none', 'prerequisites_failed'}))
    failure.update(status='failed', failure_kind=(
        'output_mismatch' if mismatch else 'invalid_result' if marker else result['failure_kind']),
        process_diagnostics=budget.maximum_process_diagnostics(),
        **dict.fromkeys(full.CLIENT_FLAGS, False))
    if marker:
        failure['marker_diagnostics'] = budget.maximum_standard_marker_diagnostics()
    if 'output_size' in failure:
        failure.update(dict.fromkeys(collections.OUTPUT_KEYS))
    for key in ('conversion_verified', 'timeout_verified'):
        if key in failure:
            failure[key] = False
    if mismatch:
        failure.update(**dict.fromkeys(('entered', 'completed', 'process_exited', 'quiet'), True),
            process_diagnostics=collections.process_diagnostics(),
            mismatch=dict(count=22, first=1000, ordinals=list(range(1000, 1016)),
                client_sha256='a' * 64, server_sha256='b' * 64,
                client_size=1048576, server_size=1048576))
    for name in order[index + 1:]:
        previous = result[name]
        extras = set(previous) - set(suite.empty_client_report())
        result[name] = dict(suite.empty_client_report(), **{
            key: False if key.endswith('_verified') else None for key in extras})
    # A failed or unreached parity record does not constrain the server's count.
    for scenario in COUNTS:
        name = 'client_' + scenario
        if name not in result or result[name]['status'] != 'ok':
            result['cases'][full.SCENARIOS.index(scenario)]['message_count'] = (
                1023 if mismatch and scenario == 'collections' else 32768)
    return result


def report_for(stage, *, accepted=False):
    report = budget.probe()
    report.pop('async_comparison', None)
    report['stage3'] = copy.deepcopy(stage)
    report['trusted_input_sha256'] = report['stage3']['input_sha256']
    report['comparison'] = (budget.accepted_comparison(stage) if accepted
                            else budget.comparison(stage))
    if stage['status'] != 'ok':
        report.update(status='stage3_failed', native_tests_completed=False,
            native_evidence_accepted=False, native_transport_validated=False,
            native_output_artifact_ready=False)
    return report


def render_parity_summary(report, selected, *, error=False):
    """Only external execution is replaced; the actual CLI renders the report."""
    options = (dict(side_effect=smoke.SmokeError('x' * 64,
        validated_report=copy.deepcopy(report), cleanup_error='x' * 64))
        if error else dict(return_value=copy.deepcopy(report)))
    with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
        path = Path(directory) / 'summary.json'
        arguments = ['--execute-approved-image', '--full-suite', '--client-probe',
            '--native-target', full.LINUX_TARGET, '--comparison-mode', full.MAP_MODE,
            '--export-native-outputs', '--output', str(path)]
        arguments.extend(flag for flag, present in zip(CLI_FLAGS, selected) if present)
        with mock.patch.object(smoke, 'run_smoke', **options), mock.patch.object(
                full, 'verify_output_artifact', return_value=None):
            code = smoke.main(arguments)
        # Match production's pre-write UTF-8 bound also on Windows text I/O.
        return path.read_text(encoding='utf-8').encode(), code


class InfobaseBudgetTests(SyntheticFilesystemCase):
    def roundtrip(self, stage, inputs, modules, **options):
        wire = budget.render_stage(stage)
        raw = json.loads(wire)
        self.assertEqual(full.validate_stage3(raw, budget.NONCE, inputs, modules,
            prerequisites=True, **options), stage)
        self.assertEqual(full.decode_stage3_wire(raw), stage)
        self.assertEqual(suite.decode_stage_wire(raw), stage)
        self.assertLessEqual(len(wire), 8192)
        return wire

    def test_all_finite_slot_encodings_have_identical_ascii_cost(self):
        slots = []
        for profile in range(4):
            slots.extend(f'{profile}{status}0000' for status in (1, 3))
            slots.extend(f'{profile}2{shape}{aliases}{english}{russian}'
                for shape, aliases, english, russian in itertools.product(
                    range(3), range(2), (1, 2), (1, 2)))
        self.assertEqual(len(set(slots)), 104)
        for position, slot in itertools.product(range(5), slots):
            values = ['321122'] * 5
            values[position] = slot
            token = 'ibc.v1:' + ''.join(values)
            self.assertEqual(full.validate_infobase_context(token), token)
            self.assertEqual(suite.validate_infobase_context(token), token)
            self.assertEqual(len(token.encode('ascii')), 37)

    def test_all_32_parity_subsets_use_real_success_validation_and_codecs(self):
        schemas = set()
        for selected in itertools.product((False, True), repeat=5):
            with self.subTest(selected=selected):
                stage, inputs, modules = parity_stage(selected)
                options = dict(zip(OPTION_NAMES, selected))
                full.validate_client_probe(stage['client_probe'],
                    full.INFOBASE_CONTEXT_SOURCE_SHA256, full.INFOBASE_CONTEXT_MODULE_SHA256,
                    infobase_allowed=True)
                wire = self.roundtrip(stage, inputs, modules, **options)
                schemas.add(json.loads(wire)['schema'])
                # Size delta, not a claim that absent capture passes semantics.
                without = copy.deepcopy(stage)
                full.discard_infobase_capture(without)
                self.assertEqual(len(wire) - len(budget.render_stage(without)), WIRE_INCREMENT)
                summary, code = render_parity_summary(report_for(stage, accepted=True), selected)
                self.assertEqual(code, 0)
                public = json.loads(summary)
                self.assertTrue(public['smoke_completed'])
                self.assertEqual(public['probe']['stage3']['client_probe']['infobase_context'], SIZE_TOKEN)
                # Charge all server/client sizes independently to seven digits;
                # the accepted comparison also repeats each server size twice.
                size_digits = 6 + sum(selected[:4])
                self.assertLessEqual(len(wire) + size_digits, 8192)
                self.assertLessEqual(len(summary) + size_digits + 12, 32768)
                # The complete public tree was genuinely rendered by main.
                # Removing one member establishes its arithmetic contribution,
                # without feeding an invalid missing-capture success to main.
                del public['probe']['stage3']['client_probe']['infobase_context']
                self.assertEqual(len(summary) - len(budget.pretty(public)), SUMMARY_INCREMENT)
        self.assertEqual(schemas, {1, 2, 3})

    def test_successful_async_capture_is_source_bound_and_roundtrips(self):
        stage, inputs, modules = budget.stage()
        bind_capture(stage, inputs, modules)
        self.roundtrip(stage, inputs, modules, client_async=True)
        for record in budget.successful_records():
            stage['client_async'] = record
            self.roundtrip(stage, inputs, modules, client_async=True)
        absent = copy.deepcopy(stage)
        full.discard_infobase_capture(absent)
        with self.assertRaises(ValueError):
            full.validate_stage3(suite.encode_stage_wire(absent), budget.NONCE,
                inputs, modules, prerequisites=True, client_async=True)
        for name in OPTION_NAMES:
            with self.assertRaises(ValueError):
                full.validate_stage3(suite.encode_stage_wire(stage), budget.NONCE,
                    inputs, modules, prerequisites=True, client_async=True, **{name: True})

    def test_18_async_majorants_keep_validators_and_unmodified_failure_serializers(self):
        wires, summaries = [], []
        for early, case in itertools.product((False, True), (None, *range(8))):
            value = budget.majorant(early=early, marker_case=case)
            self.assertNotIn('infobase_context', value['stage3']['client_probe'])
            # Existing structural majorants deliberately combine unreachable
            # maxima. Never label them validate_stage3-accepted evidence.
            wire = budget.render_stage(value['stage3'])
            self.assertEqual(full.decode_stage3_wire(json.loads(wire)), value['stage3'])
            summary, _ = budget.render_summary(value, error=True)
            self.assertIn('probe', json.loads(summary))
            wires.append(len(wire) + WIRE_INCREMENT)
            summaries.append(len(summary) + SUMMARY_INCREMENT)
        self.assertEqual(len(wires), 18)
        self.assertLessEqual(max(wires), 8192)
        self.assertLessEqual(max(summaries), 32768)

    def test_parity_failure_frontiers_validate_without_retaining_capture(self):
        wire_bounds, summary_bounds, schemas = [], [], set()
        summary_template = budget.majorant()
        summary_template.pop('async_comparison')
        for selected in itertools.product((False, True), repeat=5):
            stage, inputs, modules = parity_stage(selected)
            options = dict(zip(OPTION_NAMES, selected))
            order = ['client_probe'] + [name for name in RECORD_NAMES if name in stage]
            for index, marker in itertools.product(range(len(order)), (False, True)):
                failed = failed_frontier(stage, index, marker=marker)
                with self.subTest(selected=selected, index=index, marker=marker):
                    wire = self.roundtrip(failed, inputs, modules, **options)
                    schemas.add(json.loads(wire)['schema'])
                    self.assertNotIn('infobase_context', failed['client_probe'])
                    # Six server sizes + at most four repeated client sizes:
                    # charging each independently to seven digits is conservative
                    # even though the 2 MiB aggregate forbids their conjunction.
                    size_digits = 6 + sum(selected[:4])
                    wire_bounds.append(len(wire) + size_digits + WIRE_INCREMENT)
                    report = copy.deepcopy(summary_template)
                    report['stage3'] = failed
                    summary, _ = render_parity_summary(report, selected, error=True)
                    public = json.loads(summary)
                    self.assertIn('probe', public)
                    self.assertNotIn('infobase_context', public['probe']['stage3']['client_probe'])
                    summary_bounds.append(len(summary) + size_digits + SUMMARY_INCREMENT)
            if 'client_collections' in order:
                failed = failed_frontier(stage, order.index('client_collections'), mismatch=True)
                wire = self.roundtrip(failed, inputs, modules, **options)
                wire_bounds.append(len(wire) + 6 + sum(selected[:4]) + WIRE_INCREMENT)
                report = copy.deepcopy(summary_template)
                report['stage3'] = failed
                summary, _ = render_parity_summary(report, selected, error=True)
                self.assertIn('probe', json.loads(summary))
                summary_bounds.append(len(summary) + 6 + sum(selected[:4]) + SUMMARY_INCREMENT)
        self.assertEqual(schemas, {1, 2, 3})
        self.assertEqual(len(wire_bounds), 240)
        self.assertLessEqual(max(wire_bounds), 8192)
        self.assertLessEqual(max(summary_bounds), 32768)

    def test_all_32_early_failure_subsets_keep_bootstrap_diagnostic_budget(self):
        for selected in itertools.product((False, True), repeat=5):
            options = dict(zip(OPTION_NAMES, selected))
            _, inputs, modules = parity_stage(selected)
            stage = suite.empty_report(budget.NONCE, client_probe=True, **options)
            wire = budget.render_stage(stage)
            self.assertEqual(full.validate_stage3(json.loads(wire), budget.NONCE,
                inputs, modules, prerequisites=False, **options), stage)
            report = budget.majorant(early=True)
            report.pop('async_comparison')
            report['stage3'] = stage
            summary, _ = render_parity_summary(report, selected, error=True)
            self.assertIn('probe', json.loads(summary))
            self.assertLessEqual(len(wire) + WIRE_INCREMENT, 8192)
            self.assertLessEqual(len(summary) + SUMMARY_INCREMENT, 32768)

    def test_all_server_failure_frontiers_precede_every_client_option_subset(self):
        template = budget.majorant()
        template.pop('async_comparison')
        for selected in itertools.product((False, True), repeat=5):
            options = dict(zip(OPTION_NAMES, selected))
            successful, inputs, modules = parity_stage(selected)
            for index, name in enumerate(full.SCENARIOS):
                stage = suite.empty_report(budget.NONCE, client_probe=True, **options)
                stage.update(status='failed', failure_kind=budget.longest(
                    full.FAILURES - {'none', 'prerequisites_failed'}),
                    failed_case=name, input_sha256=copy.deepcopy(inputs))
                stage['cases'][:index + 1] = copy.deepcopy(successful['cases'][:index + 1])
                for case in stage['cases'][:index]:
                    case['message_count'] = 32768
                stage['cases'][index].update(status='failed',
                    output_sha256=None, output_size=None, message_count=None)
                wire = self.roundtrip(stage, inputs, modules, **options)
                report = copy.deepcopy(template)
                report['stage3'] = stage
                summary, _ = render_parity_summary(report, selected, error=True)
                self.assertIn('probe', json.loads(summary))
                self.assertLessEqual(len(wire) + 6 + WIRE_INCREMENT, 8192)
                self.assertLessEqual(len(summary) + 6 + SUMMARY_INCREMENT, 32768)

    def test_caps_strict_prefix_inventory_and_artifact_classes_are_unchanged(self):
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, smoke.MAX_OUTPUT),
                         (8192, 8192, 32768))
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual(len(full.CLIENT_VALUES), 136)
        stage, inputs, _ = parity_stage((True,) * 5)
        self.assertEqual(len(inputs), 24)
        self.assertEqual(full.ARTIFACT_FILES, tuple(name + '.out' for name in full.SCENARIOS)
                         + ('provenance.json',))
        self.assertTrue(all('infobase_context' not in stage[name] for name in RECORD_NAMES))


if __name__ == '__main__':
    unittest.main()

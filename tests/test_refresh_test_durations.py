"""Synthetic calibration evidence only; never execute a repository partition."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.refresh_test_durations import main, refresh
from scripts.test_partition import load_history, partition_suite, validate_history
from test_ci_test_gate import binding, push_binding, reports, C
from test_test_partition import case


def measured(b):
    values = reports(b)
    for index, report in enumerate(values.values()):
        report['durations'] = {name: float(index + 1) for name in report['executed_ids']}
    return values


def save(directory, values):
    for index, report in enumerate(values.values()):
        path = Path(directory) / str(index) / 'partition.json'
        path.parent.mkdir()
        path.write_text(json.dumps(report), encoding='utf-8')


def profile(b=None, **kwargs):
    b = binding() if b is None else b
    with tempfile.TemporaryDirectory() as directory:
        save(directory, measured(b))
        return refresh(directory, C, 1, run_attempt=b['run_attempt'], **kwargs)


class RefreshTestDurationsTests(unittest.TestCase):
    def test_complete_source_bound_data_only_refresh(self):
        b = push_binding()
        result = profile(b)
        self.assertEqual(result['schema'], 3)
        self.assertEqual(result['source'], b)
        self.assertEqual(result['calibration']['excluded_platforms'], [])
        self.assertEqual(len(result['calibration']['partitions']), 10)
        self.assertEqual(set(result['tests']), {'test_mod.A.test_light',
                                             'test_mod.B.test_heavy', 'test_mod.C.test_heavy'})
        self.assertEqual(result['tests']['test_mod.C.test_heavy']['intel_seconds'], 10.0)
        self.assertEqual(result['tests']['test_mod.A.test_light']['seconds'], 8.0)

    def test_required_scope_records_three_platforms_without_claiming_four(self):
        for b in (binding(), push_binding('refs/heads/main')):
            with self.subTest(ref=b['ref']):
                result = profile(b, scope='required-platforms')
                self.assertEqual(result['source'], b)
                self.assertEqual(result['calibration']['required_platforms'], ['linux', 'windows', 'mac-x86'])
                self.assertEqual(result['calibration']['excluded_platforms'], ['mac-arm'])
                self.assertEqual(len(result['calibration']['partitions']), 8)
                self.assertNotIn('full_coverage', result['calibration'])

    def test_reduced_pr_and_main_runs_cannot_refresh_four_platform_history(self):
        for b in (binding(), push_binding('refs/heads/main')):
            with self.subTest(ref=b['ref']), self.assertRaisesRegex(ValueError, 'four-platform'):
                profile(b)

    def test_required_scope_is_not_a_caller_selected_subset_of_tag_platforms(self):
        b = push_binding()
        values = measured(b)
        del values['mac-arm', 'light', 0]
        del values['mac-arm', 'heavy', 0]
        with tempfile.TemporaryDirectory() as directory:
            save(directory, values)
            with self.assertRaisesRegex(ValueError, 'missing/extra'):
                refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_light_only_even_complete_for_its_phase_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'phase'):
            profile(binding(True), scope='required-platforms')

    def test_missing_extra_duplicate_and_failed_artifacts_are_rejected(self):
        for mutation in ('missing', 'extra', 'duplicate', 'failed'):
            values = measured(binding())
            if mutation == 'missing':
                values.pop(('mac-x86', 'heavy', 1))
            elif mutation == 'extra':
                added = copy.deepcopy(values['linux', 'light', 0]); added['platform'] = 'other'
                values['other', 'light', 0] = added
            elif mutation == 'duplicate':
                values['duplicate'] = copy.deepcopy(values['linux', 'light', 0])
            else:
                values['windows', 'light', 0]['success'] = False
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                save(directory, values)
                with self.assertRaises(ValueError):
                    refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_empty_reports_are_not_a_new_skip_list(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_requested_source_run_and_attempt_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            save(directory, measured(binding()))
            for source, run, attempt in (('d' * 40, 1, 1), (C, 2, 1), (C, 1, 2)):
                with self.subTest(source=source, run=run, attempt=attempt), self.assertRaisesRegex(ValueError, 'wrong source/run/attempt'):
                    refresh(directory, source, run, run_attempt=attempt, scope='required-platforms')

    def test_mixed_head_base_run_attempt_or_phase_is_rejected(self):
        for field, value in (('head_sha', 'd' * 40), ('base_sha', 'd' * 40),
                             ('run_id', 2), ('run_attempt', 2), ('heavy', False)):
            values = measured(binding())
            values['windows', 'light', 0]['binding'][field] = value
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                save(directory, values)
                with self.assertRaisesRegex(ValueError, 'report source binding'):
                    refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_duration_keys_must_match_every_executed_id(self):
        for mutation in ('missing', 'extra'):
            values = measured(binding()); durations = values['linux', 'light', 0]['durations']
            if mutation == 'missing': durations.clear()
            else: durations['not.executed.test'] = 0.1
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                save(directory, values)
                with self.assertRaisesRegex(ValueError, 'duration coverage'):
                    refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_nonfinite_negative_bool_string_and_oversized_timings_rejected(self):
        for value in (float('nan'), float('inf'), -1, True, '1', 86401):
            values = measured(binding())
            values['linux', 'light', 0]['durations']['test_mod.A.test_light'] = value
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                save(directory, values)
                with self.assertRaisesRegex(ValueError, 'invalid duration'):
                    refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_wholly_skipped_fixtures_stay_unknown_not_fictitiously_zero_cost(self):
        values = measured(binding())
        for (_, tier, _), report in values.items():
            if tier != 'light': continue
            report['skipped_fixture_ids'] = report['executed_ids']
            report['executed_ids'] = []; report['tests_run'] = 0; report['durations'] = {}
        with tempfile.TemporaryDirectory() as directory:
            save(directory, values)
            result = refresh(directory, C, 1, run_attempt=1, scope='required-platforms')
        self.assertNotIn('test_mod.A.test_light', result['tests'])
        self.assertEqual(result['calibration']['unmeasured_ids'], ['test_mod.A.test_light'])

    def test_canonical_partition_fingerprints_bind_the_actual_numbers(self):
        values = measured(binding())
        with tempfile.TemporaryDirectory() as directory:
            save(directory, values)
            result = refresh(directory, C, 1, run_attempt=1, scope='required-platforms')
        report = values['linux', 'light', 0]
        raw = json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                         allow_nan=False).encode('utf-8')
        self.assertEqual(result['calibration']['partitions']['linux/light/0'], hashlib.sha256(raw).hexdigest())

    def test_v3_roundtrip_and_legacy_profile_remain_data_only(self):
        result = profile(scope='required-platforms')
        legacy = {'schema': 1, 'source': {'commit': C, 'run': 1}, 'tests': result['tests']}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            for data in (result, legacy):
                path.write_text(json.dumps(data), encoding='utf-8')
                self.assertEqual(load_history(path), result['tests'])

    def test_historical_v2_layout_is_readable_but_cannot_forge_current_coverage(self):
        current = profile(scope='required-platforms')
        previous = copy.deepcopy(current)
        previous['schema'] = 2
        previous['calibration']['partitions'].pop('windows/heavy/1')
        validate_history(previous)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            path.write_text(json.dumps(previous), encoding='utf-8')
            self.assertEqual(load_history(path), current['tests'])
        # A schema label cannot stand in for either layout's missing evidence.
        for changed in (dict(previous, schema=3), dict(current, schema=2)):
            with self.assertRaisesRegex(ValueError, 'partition evidence'):
                validate_history(changed)
        values = measured(binding())
        del values['windows', 'heavy', 1]
        with tempfile.TemporaryDirectory() as directory:
            save(directory, values)
            with self.assertRaisesRegex(ValueError, 'missing/extra'):
                refresh(directory, C, 1, run_attempt=1, scope='required-platforms')

    def test_profile_loader_rejects_forged_or_inconsistent_scope(self):
        original = profile(scope='required-platforms')
        for mutation in ('all', 'platforms', 'exclusions', 'partition', 'digest', 'light', 'unmeasured', 'unknown'):
            value = copy.deepcopy(original); evidence = value['calibration']
            if mutation == 'all': evidence['scope'] = 'all-platforms'
            elif mutation == 'platforms': evidence['required_platforms'] = ['linux']
            elif mutation == 'exclusions': evidence['excluded_platforms'] = []
            elif mutation == 'partition': evidence['partitions'].pop('linux/light/0')
            elif mutation == 'digest': evidence['partitions']['linux/light/0'] = 'not-a-hash'
            elif mutation == 'light': value['source']['heavy'] = False
            elif mutation == 'unmeasured': evidence['unmeasured_ids'] = [next(iter(value['tests']))]
            else: evidence['coverage_override'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_history(value)

    def test_unknown_ids_still_force_whole_fixture_group_and_full_union(self):
        known = case('same', 'Known'); added = case('same', 'Added'); slow = case('other', 'Slow')
        value = profile(scope='required-platforms')
        value['tests'] = {item.id(): {'seconds': 50.0, 'intel_seconds': 40.0} for item in (known, slow)}
        validate_history(value)
        plan = partition_suite(unittest.TestSuite(unittest.TestSuite([item]) for item in (known, added, slow)), value['tests'])
        light = set(plan.select('light')[1]['selected_ids'])
        heavy0 = set(plan.select('heavy', 2, 0)[1]['selected_ids'])
        heavy1 = set(plan.select('heavy', 2, 1)[1]['selected_ids'])
        self.assertEqual(light, {known.id(), added.id()})
        self.assertFalse(light & heavy0 or light & heavy1 or heavy0 & heavy1)
        self.assertEqual(light | heavy0 | heavy1, {known.id(), added.id(), slow.id()})

    def test_cli_records_explicit_attempt_and_required_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            save(directory, measured(binding()))
            output = Path(directory) / 'history.json'
            args = ['refresh', '--reports', directory, '--source', C, '--run', '1', '--attempt', '1',
                    '--scope', 'required-platforms', '--output', str(output)]
            with patch('sys.argv', args): main()
            self.assertEqual(load_history(output), profile(scope='required-platforms')['tests'])

    def test_bad_scope_and_attempt_are_rejected_before_calibration(self):
        for scope, attempt in (('linux-only', 1), ('required-platforms', 0), ('required-platforms', True)):
            with self.subTest(scope=scope, attempt=attempt), self.assertRaises(ValueError):
                refresh('.', C, 1, run_attempt=attempt, scope=scope)


if __name__ == '__main__':
    unittest.main()

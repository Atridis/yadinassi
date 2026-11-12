"""Partition discovered unittest module suites; history affects placement, never coverage.

Unknown tests keep their whole fixture group in the light tier. Original module
suite objects (including load_tests suites) are retained, not flattened/rebuilt.
"""
import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import unittest

from scripts.run_tests import TimedTextTestRunner, TimedTextTestResult, perf_counter
from scripts.ci_test_gate import PLATFORMS, partition_count, required_platforms, validate_binding

WEIGHTS = ('seconds', 'intel_seconds')
MAX_TESTS = 20000


def load_history(path):
    if path is None or not Path(path).exists():
        return {}
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate history key')
            result[key] = value
        return result
    with Path(path).open('rb') as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('history size limit')
    data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    validate_history(data)
    return data['tests']


def validate_history(data):
    if type(data) is not dict or type(data.get('schema')) is not int:
        raise ValueError('invalid history envelope')
    if data['schema'] == 1:
        if (set(data) != {'schema', 'source', 'tests'}
                or type(data['source']) is not dict or set(data['source']) != {'commit', 'run'}
                or type(data['source']['commit']) is not str
                or len(data['source']['commit']) != 40
                or any(c not in '0123456789abcdef' for c in data['source']['commit'])
                or type(data['source']['run']) is not int or data['source']['run'] <= 0):
            raise ValueError('invalid history envelope')
    elif data['schema'] in (2, 3):
        if set(data) != {'schema', 'source', 'calibration', 'tests'}:
            raise ValueError('invalid history envelope')
        validate_binding(data['source'])
        if not data['source']['heavy']:
            raise ValueError('history requires heavy coverage')
        platforms = list(required_platforms(data['source']))
        excluded = [p for p in PLATFORMS if p not in platforms]
        evidence = data['calibration']
        if (type(evidence) is not dict or set(evidence) != {
                'scope', 'required_platforms', 'excluded_platforms', 'partitions', 'unmeasured_ids'}
                or evidence['scope'] not in ('all-platforms', 'required-platforms')
                or evidence['required_platforms'] != platforms
                or evidence['excluded_platforms'] != excluded
                or (evidence['scope'] == 'all-platforms' and excluded)):
            raise ValueError('invalid history platform scope')
        # Schema 2 binds the historical one-Windows/two-Intel layout. Its data
        # remains usable without pretending the new shard was measured then.
        # Schema 3 binds the current two-Windows/two-Intel layout. This is only
        # a history format distinction, never a CI coverage override.
        expected = {f'{p}/light/0' for p in platforms} | {
            f'{p}/heavy/{i}' for p in platforms
            for i in range((2 if p == 'mac-x86' else 1) if data['schema'] == 2
                           else partition_count(p, heavy=True))}
        digests = evidence['partitions']
        if (type(digests) is not dict or set(digests) != expected
                or any(type(v) is not str or len(v) != 64
                       or any(c not in '0123456789abcdef' for c in v) for v in digests.values())):
            raise ValueError('invalid history partition evidence')
        missing = evidence['unmeasured_ids']
        if (type(missing) is not list or len(missing) > MAX_TESTS
                or any(type(v) is not str or not 0 < len(v) <= 1000 for v in missing)
                or missing != sorted(set(missing))):
            raise ValueError('invalid unmeasured history IDs')
        validate_weights(data['tests'])
        if set(missing) & set(data['tests']) or len(missing) + len(data['tests']) > MAX_TESTS:
            raise ValueError('invalid measured history coverage')
    else:
        raise ValueError('invalid history schema')
    validate_weights(data['tests'])


def validate_weights(weights):
    if type(weights) is not dict or len(weights) > MAX_TESTS:
        raise ValueError('invalid history tests')
    for name, values in weights.items():
        if (type(name) is not str or not name or len(name) > 1000 or type(values) is not dict
                or set(values) != set(WEIGHTS)
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       or not 0 <= value <= 86400 for value in values.values())):
            raise ValueError('invalid history weight')


def identity(test):
    if isinstance(test, unittest.FunctionTestCase):
        return unittest.FunctionTestCase.id(test), type(test).__module__
    if isinstance(test, unittest.TestCase):
        return unittest.TestCase.id(test), type(test).__module__
    raise ValueError('unsupported discovered test object')


def leaves(node):
    if isinstance(node, unittest.TestSuite):
        for child in node:
            yield from leaves(child)
    else:
        yield node


@dataclass
class Plan:
    nodes: list
    groups: list
    ids: list

    def select(self, tier, shard_count=1, shard_index=0):
        if tier not in ('light', 'heavy', 'all') or shard_count not in (1, 2):
            raise ValueError('invalid partition selection')
        if type(shard_index) is not int or not 0 <= shard_index < shard_count:
            raise ValueError('invalid shard index')
        selected = [g for g in self.groups if tier == 'all' or g['tier'] == tier]
        bins, totals = [[] for _ in range(shard_count)], [0.0] * shard_count
        # Longest-processing-time first, stable identity and index tie breaks.
        for group in sorted(selected, key=lambda g: (-g['intel_seconds'], g['ids'][0])):
            index = min(range(shard_count), key=lambda i: (totals[i], i))
            bins[index].append(group)
            totals[index] += group['intel_seconds']
        chosen = bins[shard_index]
        indexes = {index for group in chosen for index in group['nodes']}
        suite = unittest.TestSuite(node for index, node in enumerate(self.nodes) if index in indexes)
        selected_ids = [test_id for index, node_ids in enumerate(self.ids)
                        if index in indexes for test_id in node_ids]
        unknown = {name for group in self.groups for name in group['unknown_ids']}
        unknown_ids = [name for names in self.ids for name in names if name in unknown]
        return suite, {'tier': tier, 'shard_count': shard_count, 'shard_index': shard_index,
                       'selected_ids': selected_ids, 'estimated_intel_seconds': totals[shard_index],
                       'discovered_ids': [name for names in self.ids for name in names],
                       'unknown_ids': unknown_ids, 'unknown_count': len(unknown_ids),
                       'unknown_fraction': len(unknown_ids) / sum(map(len, self.ids))
                           if any(self.ids) else 0.0,
                       'selected_unknown_count': sum(len(group['unknown_ids']) for group in chosen),
                       'discovered_group_count': len(self.groups),
                       'unknown_group_count': sum(group['unknown'] for group in self.groups),
                       'selected_group_count': len(chosen)}


def partition_suite(suite, history, threshold=3.0):
    validate_weights(history)
    if (type(threshold) not in (float, int) or not math.isfinite(threshold) or threshold < 0
            or type(suite) is not unittest.TestSuite):
        raise ValueError('invalid discovery root or threshold')
    nodes = list(suite)
    ids, modules, seen = [], [], set()
    for node in nodes:
        node_ids, node_modules = [], set()
        for test in leaves(node):
            name, module = identity(test)
            if name in seen:
                raise ValueError('duplicate discovered test identity')
            seen.add(name)
            if len(seen) > MAX_TESTS:
                raise ValueError('too many discovered tests')
            node_ids.append(name)
            node_modules.add(module)
        ids.append(node_ids)
        modules.append(node_modules)
    # A load_tests suite can span modules. Coalesce overlapping fixture groups
    # so no module is ever divided between tiers/processes, retaining each node.
    components = []
    for index, names in enumerate(ids):
        if not names:
            # Even an empty custom suite may implement run-time behaviour.
            components.append({'nodes': {index}, 'modules': set(), 'empty': True})
            continue
        merged = {'nodes': {index}, 'modules': set(modules[index]), 'empty': False}
        remaining = []
        for group in components:
            if group['modules'] & merged['modules']:
                merged['nodes'].update(group['nodes'])
                merged['modules'].update(group['modules'])
            else:
                remaining.append(group)
        components = remaining + [merged]
    groups = []
    for component in components:
        indexes = sorted(component['nodes'])
        names = [name for index in indexes for name in ids[index]]
        unknown_ids = [name for name in names if name not in history]
        unknown = component['empty'] or bool(unknown_ids)
        sums = {platform: sum(history.get(name, {}).get(platform, 0.0) for name in names)
                for platform in WEIGHTS}
        groups.append({'nodes': indexes, 'ids': names or ['<empty-suite-%d>' % indexes[0]],
                       'tier': 'light' if unknown or sums['seconds'] <= threshold else 'heavy',
                       'intel_seconds': sums['intel_seconds'], 'unknown': unknown,
                       'unknown_ids': unknown_ids})
    return Plan(nodes, groups, ids)


class PartitionResult(TimedTextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_ids = []
        self.durations = {}
        self.fixture_ids = {}
        self.skipped_fixture_ids = []

    def startTest(self, test):
        super().startTest(test)
        self.executed_ids.append(self._test_id)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        # unittest emits an _ErrorHolder rather than test start/stop callbacks
        # for a skipped module/class fixture. Match only discovered fixtures;
        # never infer successful execution from arbitrary diagnostic text.
        if not isinstance(test, unittest.TestCase):
            description = getattr(test, 'description', None)
            if type(description) is str and description in self.fixture_ids:
                self.skipped_fixture_ids.extend(self.fixture_ids[description])

    def stopTest(self, test):
        self.durations[self._test_id] = perf_counter() - self._started
        super().stopTest(test)


class PartitionRunner(TimedTextTestRunner):
    resultclass = PartitionResult

    def run(self, test):
        self._fixture_ids = {}
        for item in leaves(test):
            name, module = identity(item)
            cls = type(item)
            for description in ('setUpModule (%s)' % module,
                                'setUpClass (%s.%s)' % (cls.__module__, cls.__qualname__)):
                self._fixture_ids.setdefault(description, []).append(name)
        return super().run(test)

    def _makeResult(self):
        result = super()._makeResult()
        result.fixture_ids = self._fixture_ids
        return result


def write_summary(report, path):
    """Append numeric diagnostics only; timing never changes placement or success."""
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(
            f"### Test partition: {report['tier']} ({report['shard_index']}/{report['shard_count']})\n\n"
            f"- Unknown IDs in discovery: {report['unknown_count']} / {len(report['discovered_ids'])} "
            f"({report['unknown_fraction']:.2%}).\n"
            f"- Unknown IDs selected: {report['selected_unknown_count']}; "
            f"selected fixture groups: {report['selected_group_count']}.\n"
            f"- Discovery wall time: {report['discovery_seconds']:.3f} s.\n"
            f"- Partition wall time: {report['partition_wall_seconds']:.3f} s "
            "(includes class/module fixtures, cleanups and runner reporting).\n"
            "- Per-test durations exclude class/module fixtures. Per-group wall time "
            "is not measured; history affects placement only, never coverage.\n\n"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tier', choices=('light', 'heavy', 'all'), required=True)
    parser.add_argument('--shard-count', type=int, choices=(1, 2), default=1)
    parser.add_argument('--shard-index', type=int, default=0)
    parser.add_argument('--history', default='scripts/test_durations.json')
    parser.add_argument('--report')
    parser.add_argument('--plan-output')
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args(argv)
    if args.plan_only and (not args.plan_output or args.report):
        parser.error('--plan-only requires --plan-output and forbids --report')
    discovery_started = perf_counter()
    suite = unittest.TestLoader().discover('tests')
    discovery_seconds = perf_counter() - discovery_started
    plan = partition_suite(suite, load_history(args.history))
    selected, report = plan.select(args.tier, args.shard_count, args.shard_index)
    report['discovery_seconds'] = discovery_seconds
    if args.plan_output:
        Path(args.plan_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.plan_output).write_text(json.dumps(report, sort_keys=True) + '\n', encoding='utf-8')
    if args.plan_only:
        return 0
    partition_started = perf_counter()
    result = PartitionRunner(verbosity=2).run(selected)
    report['partition_wall_seconds'] = perf_counter() - partition_started
    covered = result.executed_ids + result.skipped_fixture_ids
    success = (result.wasSuccessful() and len(covered) == len(set(covered))
               and set(covered) == set(report['selected_ids']))
    report.update(success=success, tests_run=result.testsRun,
                  executed_ids=result.executed_ids, skipped_fixture_ids=result.skipped_fixture_ids,
                  covered_ids=covered, durations=result.durations,
                  counts={'skipped': len(result.skipped), 'failures': len(result.failures),
                          'errors': len(result.errors),
                          'expected_failures': len(result.expectedFailures),
                          'unexpected_successes': len(result.unexpectedSuccesses)})
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=True, sort_keys=True) + '\n',
                                     encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        write_summary(report, os.environ['GITHUB_STEP_SUMMARY'])
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Partition discovered unittest module suites; history affects placement, never coverage.

Unknown tests keep their whole fixture group in the light tier. Original module
suite objects (including load_tests suites) are retained, not flattened/rebuilt.
"""
import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import unittest

from scripts.run_tests import TimedTextTestRunner, TimedTextTestResult, perf_counter

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
    if (type(data) is not dict or set(data) != {'schema', 'source', 'tests'}
            or type(data['schema']) is not int or data['schema'] != 1
            or type(data['source']) is not dict or set(data['source']) != {'commit', 'run'}
            or type(data['source']['commit']) is not str
            or len(data['source']['commit']) != 40
            or any(c not in '0123456789abcdef' for c in data['source']['commit'])
            or type(data['source']['run']) is not int or data['source']['run'] <= 0):
        raise ValueError('invalid history envelope')
    validate_weights(data['tests'])
    return data['tests']


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
        return suite, {'tier': tier, 'shard_count': shard_count, 'shard_index': shard_index,
                       'selected_ids': selected_ids, 'estimated_intel_seconds': totals[shard_index],
                       'discovered_ids': [name for names in self.ids for name in names]}


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
        unknown = component['empty'] or any(name not in history for name in names)
        sums = {platform: sum(history.get(name, {}).get(platform, 0.0) for name in names)
                for platform in WEIGHTS}
        groups.append({'nodes': indexes, 'ids': names or ['<empty-suite-%d>' % indexes[0]],
                       'tier': 'light' if unknown or sums['seconds'] <= threshold else 'heavy',
                       'intel_seconds': sums['intel_seconds'], 'unknown': unknown})
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
    suite = unittest.TestLoader().discover('tests')
    plan = partition_suite(suite, load_history(args.history))
    selected, report = plan.select(args.tier, args.shard_count, args.shard_index)
    if args.plan_output:
        Path(args.plan_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.plan_output).write_text(json.dumps(report, sort_keys=True) + '\n', encoding='utf-8')
    if args.plan_only:
        return 0
    result = PartitionRunner(verbosity=2).run(selected)
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
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())

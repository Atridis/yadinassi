"""Create a reviewable data-only timing profile from a complete heavy run.

Download and verify that run's artifacts first. This command does not fetch,
execute artifacts, commit, publish, or authorize a merge. Review the JSON diff.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts.ci_test_gate import coverage, read_json, require, sha, write_json
from scripts.test_partition import validate_history


def refresh(directory, source_sha, run_id, *, run_attempt, scope='all-platforms'):
    sha(source_sha)
    require(type(run_id) is int and run_id > 0, 'run identity')
    require(type(run_attempt) is int and run_attempt > 0, 'run attempt')
    require(scope in ('all-platforms', 'required-platforms'), 'calibration scope')
    paths = sorted(Path(directory).glob('**/partition.json'))
    require(0 < len(paths) <= 9, 'expected complete heavy partition artifacts')
    reports = {}; binding = None
    for path in paths:
        report = read_json(path)
        binding = report['binding'] if binding is None else binding
        key = (report['platform'], report['tier'], report['shard_index'])
        require(key not in reports, 'duplicate artifact')
        reports[key] = report
    require(binding['source_sha'] == source_sha and binding['run_id'] == run_id
            and binding['run_attempt'] == run_attempt, 'wrong source/run/attempt')
    verdict = coverage(binding, reports, True)
    require(verdict['required_coverage'] is True, 'complete required coverage required')
    if scope == 'all-platforms':
        require(verdict['full_coverage'] is True, 'complete four-platform coverage required')
    weights = {}; covered = set(); fingerprints = {}
    for (platform, tier, index), report in reports.items():
        duration = report['durations']
        require(type(duration) is dict and set(duration) == set(report['executed_ids']), 'duration coverage')
        covered.update(report['covered_ids'])
        for name, value in duration.items():
            require(type(value) in (float, int) and math.isfinite(value)
                    and 0 <= value <= 86400, 'invalid duration')
            item = weights.setdefault(name, {'seconds': 0.0, 'intel_seconds': 0.0})
            item['seconds'] = max(item['seconds'], value)
            if platform == 'mac-x86':
                item['intel_seconds'] = value
        # Hash canonical parsed JSON, not an asserted status or a ZIP filename.
        raw = json.dumps(report, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('utf-8')
        fingerprints[f'{platform}/{tier}/{index}'] = hashlib.sha256(raw).hexdigest()
    result = {'schema': 2, 'source': binding,
              'calibration': {'scope': scope, 'required_platforms': verdict['required_platforms'],
                              'excluded_platforms': verdict['excluded_platforms'],
                              'partitions': fingerprints,
                              'unmeasured_ids': sorted(covered - set(weights))},
              'tests': weights}
    validate_history(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', type=int, required=True)
    parser.add_argument('--attempt', type=int, required=True)
    parser.add_argument('--scope', choices=('all-platforms', 'required-platforms'), default='all-platforms')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    write_json(args.output, refresh(args.reports, args.source, args.run,
                                   run_attempt=args.attempt, scope=args.scope))


if __name__ == '__main__':
    main()

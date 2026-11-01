"""Create a reviewable data-only timing profile from a complete heavy run.

Download that run's partition artifacts first. This command does not fetch,
execute artifacts, commit or publish the result. Review the JSON diff normally.
"""
import argparse
import math
from pathlib import Path

from scripts.ci_test_gate import coverage, read_json, require, sha, write_json


def refresh(directory, source_sha, run_id):
    sha(source_sha)
    require(type(run_id) is int and run_id > 0, 'run identity')
    paths = list(Path(directory).glob('**/partition.json'))
    require(len(paths) == 9, 'expected complete heavy partition artifacts')
    reports = {}; binding = None
    for path in paths:
        report = read_json(path)
        binding = report['binding'] if binding is None else binding
        key = (report['platform'], report['tier'], report['shard_index'])
        require(key not in reports, 'duplicate artifact')
        reports[key] = report
    require(binding['source_sha'] == source_sha and binding['run_id'] == run_id, 'wrong source/run')
    coverage(binding, reports, True)
    weights = {}
    for report in reports.values():
        duration = report['durations']
        require(type(duration) is dict and set(duration) == set(report['executed_ids']), 'duration coverage')
        for name in report['covered_ids']:
            value = duration.get(name, 0.0)
            require(type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 86400, 'invalid duration')
            item = weights.setdefault(name, {'seconds': 0.0, 'intel_seconds': 0.0})
            item['seconds'] = max(item['seconds'], value)
            if report['platform'] == 'mac-x86':
                item['intel_seconds'] = value
    return {'schema': 1, 'source': {'commit': source_sha, 'run': run_id}, 'tests': weights}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', type=int, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    write_json(args.output, refresh(args.reports, args.source, args.run))


if __name__ == '__main__':
    main()

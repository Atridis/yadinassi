"""Create a reviewable data-only timing profile from a complete heavy run.

Download that run's partition artifacts first. This command does not fetch,
execute artifacts, commit or publish the result. Review the JSON diff normally.
"""
import argparse
import hashlib
import math
from pathlib import Path

from scripts.ci_test_gate import coverage, read_json, require, sha, write_json


def refresh_with_audit(directory, source_sha, run_id, *, scope="full-four"):
    require(scope in ("full-four", "required-platforms"), "timing scope")
    sha(source_sha)
    require(type(run_id) is int and run_id > 0, 'run identity')
    paths = sorted(Path(directory).glob('**/partition.json'))
    require(bool(paths), 'missing partition artifacts')
    reports = {}; binding = None
    for path in paths:
        report = read_json(path)
        binding = report['binding'] if binding is None else binding
        key = (report['platform'], report['tier'], report['shard_index'])
        require(key not in reports, 'duplicate artifact')
        reports[key] = report
    require(binding['source_sha'] == source_sha and binding['run_id'] == run_id, 'wrong source/run')
    verdict = coverage(binding, reports, True)
    require(verdict['required_coverage'] is True, 'required coverage')
    if scope == 'full-four':
        require(verdict['full_coverage'] is True, 'complete four-platform coverage required')
    weights = {}
    for report in reports.values():
        duration = report['durations']
        require(type(duration) is dict and set(duration) == set(report['executed_ids']), 'duration coverage')
        for value in duration.values():
            require(type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 86400, 'invalid duration')
        for name in report['covered_ids']:
            # Fixture skips are coverage, not measured execution. Audit them separately.
            value = duration.get(name, 0.0)
            item = weights.setdefault(name, {'seconds': 0.0, 'intel_seconds': 0.0})
            item['seconds'] = max(item['seconds'], value)
            if report['platform'] == 'mac-x86':
                item['intel_seconds'] = value
    require(bool(weights), 'empty timing history')
    profile = {'schema': 1, 'source': {'commit': source_sha, 'run': run_id}, 'tests': weights}
    audit = {'schema': 1, 'scope': scope, 'binding': binding, 'coverage': verdict,
             'fixture_timing': 'zero for fixture-only skips; not an execution measurement',
             'reports': [{'file': str(path.relative_to(directory)),
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'skipped_fixture_ids': read_json(path)['skipped_fixture_ids']}
                         for path in paths]}
    return profile, audit


def refresh(directory, source_sha, run_id, *, scope='full-four'):
    return refresh_with_audit(directory, source_sha, run_id, scope=scope)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', type=int, required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--scope', choices=('full-four', 'required-platforms'), default='full-four')
    args = parser.parse_args()
    profile, audit = refresh_with_audit(args.reports, args.source, args.run, scope=args.scope)
    write_json(args.output, profile)
    audit['profile_sha256'] = hashlib.sha256(Path(args.output).read_bytes()).hexdigest()
    write_json(args.output + '.audit.json', audit)


if __name__ == '__main__':
    main()

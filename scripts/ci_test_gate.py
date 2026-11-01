"""Read-only exact-source admission and coverage verdict for tiered CI.

No statuses, refs, settings or repository files are written through the API.
A successful old verdict is NOT permission to merge: check_fresh must be run
again immediately before merging, including after a change to main.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

REPOSITORY = 'Atridis/yadinassi'
PLATFORMS = ('linux', 'mac-arm', 'windows', 'mac-x86')
MAX_JSON = 16 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{40}')


def require(value, message):
    if not value:
        raise ValueError(message)


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, 'JSON size limit')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def api(path):
    require(path.startswith('/repos/' + REPOSITORY + '/'), 'API route')
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'yadinassi-ci-test-gate'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    request = urllib.request.Request('https://api.github.com' + path, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, 'API size limit')
    return json.loads(raw)


def sha(value):
    require(type(value) is str and SHA.fullmatch(value), 'invalid commit SHA')
    return value


def admit(event_name, event, source_sha, repository, fetch=api, *, run_id=1, run_attempt=1):
    require(repository == REPOSITORY, 'repository mismatch')
    source_sha = sha(source_sha)
    binding = {'schema': 1, 'repository': repository, 'source_sha': source_sha,
               'event': event_name, 'pr_number': None, 'head_sha': source_sha,
               'base_sha': None, 'heavy': True, 'run_id': run_id, 'run_attempt': run_attempt}
    if event_name == 'pull_request':
        request = event['pull_request']
        number = event['number']
        require(type(number) is int and number > 0, 'PR number')
        require(request['base']['repo']['full_name'] == repository and request['base']['ref'] == 'main', 'PR base')
        require(type(request['draft']) is bool, 'PR draft state')
        binding.update(pr_number=number, head_sha=sha(request['head']['sha']),
                       base_sha=sha(request['base']['sha']), heavy=not request['draft'])
        check_fresh(binding, fetch)
        commit = fetch('/repos/' + repository + '/git/commits/' + source_sha)
        require(commit['sha'] == source_sha, 'source commit mismatch')
        require([x['sha'] for x in commit['parents']] == [binding['base_sha'], binding['head_sha']],
                'PR merge source does not bind current base and head')
    else:
        require(event_name in ('push', 'workflow_dispatch'), 'event not supported')
    return binding


def validate_binding(binding):
    require(type(binding) is dict and set(binding) == {'schema', 'repository', 'source_sha', 'event',
            'pr_number', 'head_sha', 'base_sha', 'heavy', 'run_id', 'run_attempt'}, 'binding shape')
    require(type(binding['schema']) is int and binding['schema'] == 1 and binding['repository'] == REPOSITORY, 'binding repository/schema')
    require(all(type(binding[k]) is int and binding[k] > 0 for k in ('run_id', 'run_attempt')), 'run identity')
    sha(binding['source_sha']); sha(binding['head_sha'])
    require(type(binding['heavy']) is bool, 'binding phase')
    if binding['event'] == 'pull_request':
        require(type(binding['pr_number']) is int and binding['pr_number'] > 0, 'binding PR')
        sha(binding['base_sha'])
    else:
        require(binding['event'] in ('push', 'workflow_dispatch') and binding['pr_number'] is None
                and binding['base_sha'] is None and binding['head_sha'] == binding['source_sha']
                and binding['heavy'], 'binding non-PR')


def check_fresh(binding, fetch=api):
    validate_binding(binding)
    if binding['pr_number'] is None:
        return
    current = fetch('/repos/' + REPOSITORY + '/pulls/' + str(binding['pr_number']))
    require(current['state'] == 'open' and current['base']['ref'] == 'main'
            and current['base']['repo']['full_name'] == REPOSITORY, 'PR not open against main')
    require(current['head']['sha'] == binding['head_sha'] and current['base']['sha'] == binding['base_sha'],
            'stale PR head/base; prepare a new candidate run')
    main = fetch('/repos/' + REPOSITORY + '/git/ref/heads/main')
    require(main['object']['sha'] == binding['base_sha'], 'main changed since admission')
    require(not binding['heavy'] or not current['draft'], 'heavy candidate returned to draft')


def checkout(binding):
    validate_binding(binding)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(actual == binding['source_sha'], 'checkout differs from admitted source')


def ids(value):
    require(type(value) is list and len(value) <= 20000 and all(type(x) is str and 0 < len(x) <= 2048 for x in value), 'test IDs')
    require(len(value) == len(set(value)), 'duplicate test ID')
    return set(value)


def coverage(binding, reports, heavy):
    validate_binding(binding)
    require(type(heavy) is bool and heavy == binding['heavy'], 'verdict phase')
    expected = {(p, 'light', 0) for p in PLATFORMS}
    if heavy:
        expected |= {(p, 'heavy', i) for p in PLATFORMS for i in range(2 if p == 'mac-x86' else 1)}
    require(set(reports) == expected, 'missing/extra platform partition report')
    output = {}
    for platform in PLATFORMS:
        selected = set(); discovered = None
        for (p, tier, index), report in reports.items():
            if p != platform:
                continue
            require(report['binding'] == binding, 'report source binding')
            require(report['platform'] == p and report['tier'] == tier and report['shard_index'] == index,
                    'partition identity')
            count = 2 if p == 'mac-x86' and tier == 'heavy' else 1
            require(report['shard_count'] == count, 'partition count')
            require(report['success'] is True, 'failed partition')
            chosen = ids(report['selected_ids']); executed = ids(report['executed_ids']); all_ids = ids(report['discovered_ids'])
            fixture_skips = ids(report['skipped_fixture_ids']); covered = ids(report['covered_ids'])
            require(not executed & fixture_skips and covered == executed | fixture_skips, 'fixture skip coverage')
            require(chosen == covered and chosen <= all_ids and not selected & chosen, 'missing/duplicated execution')
            require(type(report['tests_run']) is int and report['tests_run'] == len(executed), 'execution count')
            require(all(report['counts'][k] == 0 for k in ('errors', 'failures', 'unexpected_successes')), 'failed result counts')
            require(discovered is None or discovered == all_ids, 'discovery changed across tiers')
            discovered = all_ids; selected |= chosen
        if heavy:
            require(selected == discovered, 'full premerge coverage incomplete')
        output[platform] = {'covered': len(selected), 'discovered': len(discovered),
                            'ids_sha256': hashlib.sha256('\n'.join(sorted(selected)).encode()).hexdigest()}
    return {'schema': 1, 'binding': binding, 'phase': 'heavy-premerge' if heavy else 'light-only',
            'full_coverage': heavy, 'platforms': output}


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('admit'); a.add_argument('--output', required=True)
    for command in ('checkout', 'fresh'):
        c = sub.add_parser(command); c.add_argument('--binding', required=True)
    s = sub.add_parser('stamp'); s.add_argument('--binding', required=True); s.add_argument('--report', required=True); s.add_argument('--platform', choices=PLATFORMS, required=True)
    v = sub.add_parser('verdict'); v.add_argument('--binding', required=True); v.add_argument('--reports', required=True); v.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'admit':
        binding = admit(os.environ['GITHUB_EVENT_NAME'], read_json(os.environ['GITHUB_EVENT_PATH']),
                        os.environ['GITHUB_SHA'], os.environ['GITHUB_REPOSITORY'],
                        run_id=int(os.environ['GITHUB_RUN_ID']), run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))
        checkout(binding); write_json(args.output, binding)
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('heavy=' + str(binding['heavy']).lower() + '\nsource_sha=' + binding['source_sha'] + '\n')
    else:
        binding = read_json(args.binding); validate_binding(binding)
        if args.command == 'fresh':
            check_fresh(binding)
        elif args.command == 'checkout':
            checkout(binding)
        elif args.command == 'stamp':
            checkout(binding)
            report = read_json(args.report); report.update(binding=binding, platform=args.platform)
            write_json(args.report, report)
        else:
            reports = {}
            paths = list(Path(args.reports).glob('**/partition.json'))
            require(len(paths) <= 9, 'too many reports')
            for path in paths:
                report = read_json(path)
                key = (report['platform'], report['tier'], report['shard_index'])
                require(key not in reports, 'duplicate partition artifact')
                reports[key] = report
            verdict = coverage(binding, reports, binding['heavy'])
            check_fresh(binding)  # Re-read live head AND main after every test/build job.
            write_json(args.output, verdict)
            print(json.dumps(verdict, sort_keys=True))


if __name__ == '__main__':
    main()

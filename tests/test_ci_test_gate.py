"""Exact candidate and tier coverage checks: synthetic API, never network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import ci_test_gate as gate

A, B, C = 'a'*40, 'b'*40, 'c'*40


def event(draft=False):
    return {'number': 12, 'pull_request': {'draft': draft, 'head': {'sha': B},
            'base': {'sha': A, 'ref': 'main', 'repo': {'full_name': gate.REPOSITORY}}}}


def fetch(path):
    if path.endswith('/pulls/12'):
        return dict(event()['pull_request'], state='open')
    if path.endswith('/git/ref/heads/main'):
        return {'object': {'sha': A}}
    if path.endswith('/git/commits/'+C):
        return {'sha': C, 'parents': [{'sha': A}, {'sha': B}]}
    raise AssertionError(path)


def binding(draft=False):
    return gate.admit('pull_request', event(draft), C, gate.REPOSITORY, fetch, ref='refs/pull/12/merge')


def push_event(ref):
    return {'ref': ref, 'after': C, 'deleted': False}


def push_binding(ref='refs/tags/v1.2.3'):
    return gate.admit('push', push_event(ref), C, gate.REPOSITORY, fetch, ref=ref)


def dispatch_binding(ref='refs/heads/main'):
    # Dispatch payload refs can be short; full identity comes from GITHUB_REF.
    return gate.admit('workflow_dispatch', {'ref': ref.rsplit('/', 1)[-1]}, C,
                      gate.REPOSITORY, fetch, ref=ref)


def context(b):
    return {'GITHUB_EVENT_NAME': b['event'], 'GITHUB_REF': b['ref'],
            'GITHUB_SHA': b['source_sha'], 'GITHUB_REPOSITORY': b['repository'],
            'GITHUB_RUN_ID': str(b['run_id']), 'GITHUB_RUN_ATTEMPT': str(b['run_attempt'])}


def reports(b):
    result = {}
    for p in gate.required_platforms(b):
        parts = [('light', 0, ['test_mod.A.test_light'])]
        if b['heavy']:
            parts += [('heavy', 0, ['test_mod.B.test_heavy'])]
            if p == 'mac-x86':
                parts += [('heavy', 1, ['test_mod.C.test_heavy'])]
        all_ids = [x for _, _, chosen in parts for x in chosen]
        for tier, index, chosen in parts:
            result[p,tier,index] = {'platform': p, 'tier': tier, 'shard_index': index,
                'shard_count': 2 if p == 'mac-x86' and tier == 'heavy' else 1,
                'binding': copy.deepcopy(b), 'selected_ids': chosen[:], 'executed_ids': chosen[:],
                'skipped_fixture_ids': [], 'covered_ids': chosen[:], 'discovered_ids': all_ids[:],
                'tests_run': len(chosen), 'success': True,
                'counts': {'errors': 0, 'failures': 0, 'unexpected_successes': 0}}
    return result


class CITestGateTests(unittest.TestCase):
    def test_exact_head_base_merge_parents_and_draft_phase(self):
        self.assertTrue(binding()['heavy'])
        self.assertFalse(binding(True)['heavy'])
        self.assertEqual(binding()['source_sha'], C)
        self.assertEqual(binding()['head_sha'], B)
        self.assertEqual(binding()['base_sha'], A)
        for mutation in ('head', 'base', 'main', 'parents', 'closed', 'draft'):
            def changed(path):
                r = fetch(path)
                if path.endswith('/pulls/12'):
                    if mutation in ('head', 'base'):
                        r[mutation]['sha'] = 'd'*40
                    if mutation == 'closed': r['state'] = 'closed'
                    if mutation == 'draft': r['draft'] = True
                if path.endswith('/git/ref/heads/main') and mutation == 'main': r['object']['sha'] = 'd'*40
                if '/git/commits/' in path and mutation == 'parents': r['parents'].reverse()
                return r
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.admit('pull_request', event(), C, gate.REPOSITORY, changed, ref='refs/pull/12/merge')

    def test_final_live_recheck_rejects_main_change_and_wrong_checkout(self):
        b = binding()
        def newer(path):
            r = fetch(path)
            if path.endswith('/git/ref/heads/main'): r['object']['sha'] = 'd'*40
            return r
        with self.assertRaises(ValueError): gate.check_fresh(b, newer)
        with mock.patch.object(gate.subprocess, 'check_output', return_value=B+'\n'):
            with self.assertRaises(ValueError): gate.checkout(b)
        with mock.patch.object(gate.subprocess, 'check_output', return_value=C+'\n'):
            gate.checkout(b)

    def test_heavy_union_complete_and_light_never_claims_full_gate(self):
        for draft in (False, True):
            b = binding(draft)
            verdict = gate.coverage(b, reports(b), not draft)
            self.assertFalse(verdict['full_coverage'])
            self.assertEqual(verdict['required_coverage'], not draft)
            self.assertEqual(verdict['excluded_platforms'], ['mac-arm'])
            self.assertEqual(verdict['phase'], 'light-only' if draft else 'heavy-premerge')
        b = binding(); r = reports(b)
        item = r['linux', 'heavy', 0]
        item['skipped_fixture_ids'] = item['executed_ids']; item['executed_ids'] = []; item['tests_run'] = 0
        self.assertTrue(gate.coverage(b, r, True)['required_coverage'])

    def test_missing_duplicate_failed_or_foreign_report_never_passes(self):
        b = binding()
        for mutation in ('missing', 'extra', 'duplicated_ids', 'unexecuted', 'wrong_source',
                         'failure', 'count', 'discovery', 'missing_test', 'skip_overlap', 'error_count'):
            r = reports(b); item = r['linux', 'heavy', 0]
            if mutation == 'missing': del r['linux', 'heavy', 0]
            if mutation == 'extra': r['linux','heavy',1] = copy.deepcopy(item)
            if mutation == 'duplicated_ids': item['selected_ids'] *= 2
            if mutation == 'unexecuted': item['covered_ids'] = []
            if mutation == 'wrong_source': item['binding']['head_sha'] = 'd'*40
            if mutation == 'failure': item['success'] = False
            if mutation == 'count': item['tests_run'] = 99
            if mutation == 'discovery': item['discovered_ids'].append('unknown')
            if mutation == 'missing_test':
                for key, value in r.items():
                    if key[0] == 'linux': value['discovered_ids'].append('uncovered')
            if mutation == 'skip_overlap': item['skipped_fixture_ids'] = item['executed_ids'][:]
            if mutation == 'error_count': item['counts']['errors'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.coverage(b, r, True)

    def test_closed_repository_events_and_bounded_json(self):
        for name in ('pull_request_target', 'workflow_run', 'issue_comment'):
            with self.assertRaises(ValueError): gate.admit(name, {}, C, gate.REPOSITORY, fetch, ref='refs/heads/main')
        with self.assertRaises(ValueError): gate.admit('push', {}, C, 'other/repo', fetch, ref='refs/heads/main')
        self.assertTrue(push_binding('refs/heads/main')['heavy'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'x.json';path.write_text(json.dumps({'x':1}))
            self.assertEqual(gate.read_json(path), {'x':1})
            with mock.patch.object(gate, 'MAX_JSON', 1):
                with self.assertRaises(ValueError):gate.read_json(path)

    def test_main_is_reduced_all_tags_and_manual_runs_remain_full(self):
        reduced = ('linux', 'windows', 'mac-x86')
        routes = [(binding(True), reduced), (binding(), reduced),
                  (push_binding('refs/heads/main'), reduced),
                  (push_binding(), gate.PLATFORMS),
                  (push_binding('refs/tags/non-v/nested'), gate.PLATFORMS),
                  (push_binding('refs/tags/release./v1'), gate.PLATFORMS),
                  (dispatch_binding(), gate.PLATFORMS),
                  (dispatch_binding('refs/heads/feature/topic'), gate.PLATFORMS),
                  (dispatch_binding('refs/heads/topic./x'), gate.PLATFORMS),
                  (dispatch_binding('refs/tags/v1.2.3'), gate.PLATFORMS)]
        for b, expected in routes:
            with self.subTest(event=b['event'], ref=b['ref'], heavy=b['heavy']):
                self.assertEqual(gate.required_platforms(b), expected)
                verdict = gate.coverage(b, reports(b), b['heavy'])
                self.assertEqual(verdict['required_platforms'], list(expected))
                self.assertEqual(set(verdict['platforms']), set(expected))
                self.assertEqual(verdict['full_coverage'], b['heavy'] and expected == gate.PLATFORMS)
                self.assertEqual(verdict['required_coverage'], b['heavy'])
                self.assertEqual(verdict['excluded_platforms'], [] if expected == gate.PLATFORMS else ['mac-arm'])

    def test_all_matrices_preserve_os_architecture_and_intel_shards(self):
        runners = [('windows', 'windows-2022', 'x64'), ('linux', 'ubuntu-22.04', 'x64'),
                   ('mac-x86', 'macos-15-intel', 'x64'), ('mac-arm', 'macos-15', 'arm64')]
        for b in (binding(True), binding(), push_binding('refs/heads/main'), push_binding(),
                  push_binding('refs/tags/preview/nested'), dispatch_binding()):
            for heavy in (False, True):
                with self.subTest(event=b['event'], ref=b['ref'], heavy=heavy):
                    expected = []
                    for target, os_name, arch in runners:
                        if target not in gate.required_platforms(b):
                            continue
                        count = 2 if heavy and target == 'mac-x86' else 1
                        for index in range(count):
                            row = {'target': target, 'os': os_name, 'architecture': arch}
                            if heavy:
                                row.update(shard_count=count, shard_index=index)
                            expected.append(row)
                    self.assertEqual(gate.job_matrix(b, heavy=heavy), {'include': expected})
                    self.assertEqual(len(expected), (5 if heavy else 4) - ('mac-arm' not in gate.required_platforms(b)))

    def test_push_ref_cannot_be_forged_empty_deleted_or_unsupported(self):
        for ref in ('refs/heads/topic', 'refs/tags/', 'refs/tags//v1', 'refs/tags/../v1',
                    'refs/tags/.hidden', 'refs/tags/a.lock', 'refs/tags/a.', 'refs/tags/a\n',
                    'refs/tags/a@{b', 'refs/tags/a^b', 'refs/pull/12/merge', 'main'):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                gate.admit('push', push_event(ref), C, gate.REPOSITORY, ref=ref)
        for actual, forged in (('refs/tags/v1', 'refs/heads/main'), ('refs/heads/main', 'refs/tags/v1')):
            with self.assertRaises(ValueError):
                gate.admit('push', push_event(actual), C, gate.REPOSITORY, ref=forged)
        for ref in ('refs/heads/main', 'refs/tags/v1'):
            for deleted in (True, None, 0, 'false'):
                payload = dict(push_event(ref), deleted=deleted)
                with self.subTest(ref=ref, deleted=deleted), self.assertRaises(ValueError):
                    gate.admit('push', payload, C, gate.REPOSITORY, ref=ref)
        with self.assertRaises(ValueError):
            gate.admit('push', dict(push_event('refs/heads/main'), after=A), C,
                       gate.REPOSITORY, ref='refs/heads/main')
        # Annotated tag object identity need not equal the checked-out commit.
        b = gate.admit('push', dict(push_event('refs/tags/v1'), after=A), C,
                       gate.REPOSITORY, ref='refs/tags/v1')
        self.assertEqual(gate.required_platforms(b), gate.PLATFORMS)

    def test_binding_shape_phase_and_route_have_no_scope_override(self):
        for base in (binding(), push_binding(), dispatch_binding()):
            mutations = [dict(base, schema=1), dict(base, heavy='false'), dict(base, heavy=1),
                         dict(base, platforms=['linux']), dict(base, excluded_platforms=['mac-arm']),
                         dict(base, scope='main'), dict(base, event='pull_request_target'),
                         dict(base, run_id=True), dict(base, run_attempt=0)]
            if base['event'] == 'pull_request':
                mutations += [dict(base, ref='refs/pull/13/merge'), dict(base, ref='refs/pull/12/head'),
                              dict(base, ref='refs/tags/v1'), dict(base, pr_number=True)]
            else:
                mutations += [dict(base, heavy=False), dict(base, pr_number=12),
                              dict(base, base_sha=A), dict(base, head_sha=B), dict(base, ref='refs/tags/')]
            for changed in mutations:
                with self.subTest(binding=changed), self.assertRaises(ValueError):
                    gate.required_platforms(changed)
        with self.assertRaises(ValueError):
            gate.coverage(binding(), reports(binding()), False)

    def test_current_context_rejects_forged_event_ref_phase_and_run(self):
        for b, payload in ((binding(), event()), (binding(True), event(True)),
                           (push_binding(), push_event('refs/tags/v1.2.3')),
                           (push_binding('refs/heads/main'), push_event('refs/heads/main')),
                           (dispatch_binding(), {'ref': 'main'})):
            environ = context(b)
            gate.verify_context(b, payload, environ)
            for key, value in (('GITHUB_SHA', A), ('GITHUB_RUN_ID', '2'), ('GITHUB_RUN_ATTEMPT', '2'),
                               ('GITHUB_REF', 'refs/tags/forged'), ('GITHUB_REPOSITORY', 'other/repo')):
                with self.subTest(event=b['event'], key=key), self.assertRaises(ValueError):
                    gate.verify_context(b, payload, dict(environ, **{key: value}))
        # A structurally valid reduced-main binding cannot replace a tag binding.
        with self.assertRaises(ValueError):
            gate.verify_context(push_binding('refs/heads/main'), push_event('refs/tags/v1.2.3'),
                                context(push_binding()))
        with self.assertRaises(ValueError):
            gate.verify_context(binding(True), event(), context(binding()))
        with self.assertRaises(ValueError):
            gate.verify_context(dispatch_binding(), push_event('refs/heads/main'),
                                context(push_binding('refs/heads/main')))

    def test_every_required_partition_is_mandatory_extra_arm_is_rejected(self):
        for b in (binding(True), binding(), push_binding('refs/heads/main'), push_binding(), dispatch_binding()):
            for key in reports(b):
                incomplete = reports(b); del incomplete[key]
                with self.subTest(ref=b['ref'], missing=key), self.assertRaises(ValueError):
                    gate.coverage(b, incomplete, b['heavy'])
        for b in (binding(True), binding(), push_binding('refs/heads/main')):
            extra = reports(b)
            extra['mac-arm', 'light', 0] = copy.deepcopy(extra['linux', 'light', 0])
            with self.assertRaises(ValueError):
                gate.coverage(b, extra, b['heavy'])
        for b in (binding(), push_binding('refs/heads/main'), push_binding()):
            for platform in gate.required_platforms(b):
                incomplete = reports(b)
                for key, item in incomplete.items():
                    if key[0] == platform:
                        item['discovered_ids'].append('not-covered')
                with self.subTest(platform=platform), self.assertRaises(ValueError):
                    gate.coverage(b, incomplete, True)

    def test_final_cli_verdict_checks_context_without_network_and_still_rechecks_freshness(self):
        b = push_binding()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); binding_path = root/'binding.json'; event_path = root/'event.json'
            output = root/'verdict.json'; partitions = root/'partitions'
            gate.write_json(binding_path, b); gate.write_json(event_path, push_event(b['ref']))
            for index, report in enumerate(reports(b).values()):
                gate.write_json(partitions/str(index)/'partition.json', report)
            argv = ['ci_test_gate.py', 'verdict', '--binding', str(binding_path),
                    '--reports', str(partitions), '--output', str(output)]
            environ = dict(context(b), GITHUB_EVENT_PATH=str(event_path))
            with mock.patch.dict(gate.os.environ, environ, clear=True), mock.patch('sys.argv', argv), \
                    mock.patch.object(gate, 'check_fresh') as fresh, mock.patch('builtins.print'):
                gate.main()
                fresh.assert_called_once_with(b)
            self.assertTrue(gate.read_json(output)['full_coverage'])
            gate.write_json(binding_path, push_binding('refs/heads/main'))
            with mock.patch.dict(gate.os.environ, environ, clear=True), mock.patch('sys.argv', argv), \
                    mock.patch.object(gate, 'coverage') as coverage, self.assertRaises(ValueError):
                gate.main()
            coverage.assert_not_called()

    def test_admission_serializes_the_same_trusted_matrices_used_by_jobs(self):
        for b in (push_binding('refs/heads/main'), push_binding()):
            with self.subTest(ref=b['ref']), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); event_path = root/'event.json'; output = root/'binding.json'
                github_output = root/'output.txt'
                gate.write_json(event_path, push_event(b['ref']))
                environ = dict(context(b), GITHUB_EVENT_PATH=str(event_path), GITHUB_OUTPUT=str(github_output))
                with mock.patch.dict(gate.os.environ, environ, clear=True), \
                        mock.patch('sys.argv', ['ci_test_gate.py', 'admit', '--output', str(output)]), \
                        mock.patch.object(gate, 'checkout') as checkout:
                    gate.main()
                    checkout.assert_called_once_with(b)
                self.assertEqual(gate.read_json(output), b)
                values = dict(line.split('=', 1) for line in github_output.read_text().splitlines())
                self.assertEqual(set(values), {'heavy', 'source_sha', 'light_matrix', 'heavy_matrix'})
                self.assertEqual(values['heavy'], 'true')
                self.assertEqual(values['source_sha'], C)
                for name, heavy in (('light_matrix', False), ('heavy_matrix', True)):
                    self.assertEqual(json.loads(values[name]), gate.job_matrix(b, heavy=heavy))

    def test_checkout_and_stamp_reject_context_forgery_before_git_or_report_write(self):
        b = push_binding()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'binding.json'; event_path = root/'event.json'
            report_path = root/'partition.json'
            gate.write_json(path, push_binding('refs/heads/main'))
            gate.write_json(event_path, push_event(b['ref']))
            environ = dict(context(b), GITHUB_EVENT_PATH=str(event_path))
            for command in ('checkout', 'stamp'):
                argv = ['ci_test_gate.py', command, '--binding', str(path)]
                if command == 'stamp':
                    argv += ['--report', str(report_path), '--platform', 'linux']
                with mock.patch.dict(gate.os.environ, environ, clear=True), mock.patch('sys.argv', argv), \
                        mock.patch.object(gate, 'checkout') as checkout, self.assertRaises(ValueError):
                    gate.main()
                checkout.assert_not_called()
                self.assertFalse(report_path.exists())
            # Even a correctly bound ordinary run cannot stamp excluded ARM.
            b = push_binding('refs/heads/main')
            gate.write_json(event_path, push_event(b['ref']))
            environ = dict(context(b), GITHUB_EVENT_PATH=str(event_path))
            argv = ['ci_test_gate.py', 'stamp', '--binding', str(path),
                    '--report', str(report_path), '--platform', 'mac-arm']
            with mock.patch.dict(gate.os.environ, environ, clear=True), mock.patch('sys.argv', argv), \
                    mock.patch.object(gate, 'checkout'), self.assertRaises(ValueError):
                gate.main()
            self.assertFalse(report_path.exists())


if __name__ == '__main__':
    unittest.main()

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
    return gate.admit('pull_request', event(draft), C, gate.REPOSITORY, fetch)


def reports(b):
    result = {}
    for p in gate.PLATFORMS:
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
                gate.admit('pull_request', event(), C, gate.REPOSITORY, changed)

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
            self.assertEqual(verdict['full_coverage'], not draft)
            self.assertEqual(verdict['phase'], 'light-only' if draft else 'heavy-premerge')
        b = binding(); r = reports(b)
        item = r['linux', 'heavy', 0]
        item['skipped_fixture_ids'] = item['executed_ids']; item['executed_ids'] = []; item['tests_run'] = 0
        self.assertTrue(gate.coverage(b, r, True)['full_coverage'])

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
            with self.assertRaises(ValueError): gate.admit(name, {}, C, gate.REPOSITORY, fetch)
        with self.assertRaises(ValueError): gate.admit('push', {}, C, 'other/repo', fetch)
        self.assertTrue(gate.admit('push', {}, C, gate.REPOSITORY, fetch)['heavy'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'x.json';path.write_text(json.dumps({'x':1}))
            self.assertEqual(gate.read_json(path), {'x':1})
            with mock.patch.object(gate, 'MAX_JSON', 1):
                with self.assertRaises(ValueError):gate.read_json(path)


if __name__ == '__main__':
    unittest.main()

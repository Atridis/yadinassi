import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.refresh_test_durations import refresh
from test_ci_test_gate import binding, push_binding, reports, C


class RefreshTestDurationsTests(unittest.TestCase):
    def test_complete_source_bound_data_only_refresh(self):
        b = push_binding(); values = reports(b)
        with tempfile.TemporaryDirectory() as directory:
            for index, report in enumerate(values.values()):
                report['durations'] = {name: float(index+1) for name in report['executed_ids']}
                path=Path(directory)/str(index)/'partition.json';path.parent.mkdir()
                path.write_text(json.dumps(report))
            result=refresh(directory,C,1)
            self.assertEqual(result['source'], {'commit':C,'run':1})
            self.assertEqual(set(result['tests']), {'test_mod.A.test_light','test_mod.B.test_heavy','test_mod.C.test_heavy'})
            with self.assertRaises(ValueError):refresh(directory,'d'*40,1)
            with self.assertRaises(ValueError):refresh(directory,C,2)
            sample=Path(directory)/'0'/'partition.json';data=json.loads(sample.read_text())
            data['durations'][next(iter(data['durations']))]=float('nan');sample.write_text(json.dumps(data))
            with self.assertRaises(ValueError):refresh(directory,C,1)

    def test_reduced_pr_and_main_runs_cannot_refresh_four_platform_history(self):
        for b in (binding(), push_binding('refs/heads/main')):
            with self.subTest(ref=b['ref']), tempfile.TemporaryDirectory() as directory:
                for index, report in enumerate(reports(b).values()):
                    report['durations'] = {name: 1.0 for name in report['executed_ids']}
                    path = Path(directory)/str(index)/'partition.json'; path.parent.mkdir()
                    path.write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    refresh(directory, C, 1)

    def test_missing_artifact_is_not_a_new_skip_list(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):refresh(directory,C,1)


class ScopedRefreshTests(unittest.TestCase):
    def write_reports(self,d,values):
        for i,r in enumerate(values):
            r.setdefault('durations',{n:1.0 for n in r['executed_ids']})
            p=Path(d)/str(i)/'partition.json';p.parent.mkdir();p.write_text(json.dumps(r),encoding='utf-8')

    def test_explicit_scope_audit_and_fixture_accounting(self):
        from scripts.refresh_test_durations import refresh_with_audit
        for skipped in (False,True):
            with tempfile.TemporaryDirectory() as d:
                values=list(reports(binding()).values())
                if skipped:
                    for r in values:
                        r['skipped_fixture_ids']=r['executed_ids'][:];r['executed_ids']=[];r['tests_run']=0
                self.write_reports(d,values)
                p,a=refresh_with_audit(d,C,1,scope='required-platforms')
                self.assertTrue(a['coverage']['required_coverage']);self.assertFalse(a['coverage']['full_coverage'])
                self.assertEqual(a['coverage']['excluded_platforms'],['mac-arm'])
                self.assertEqual(len(a['reports']),7);self.assertEqual(len(p['tests']),3)
                self.assertTrue(all(v['seconds']==(0 if skipped else 1) for v in p['tests'].values()))
                with self.assertRaises(ValueError):refresh(d,C,1)

    def test_invalid_sets_and_timings(self):
        for case in ('missing','extra','mixed','failed','light','empty','empty-discovery',True,-1,float('inf'),float('nan'),86401):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as d:
                v=list(reports(binding(case=='light')).values())
                if case=='missing':v.pop()
                elif case=='extra':v.append(copy.deepcopy(v[0]))
                elif case=='mixed':v[0]['binding']['run_attempt']+=1
                elif case=='failed':v[0]['success']=False
                elif case=='empty':v[0]['durations']={}
                elif case=='empty-discovery':
                    for r in v:
                        for key in ('selected_ids','executed_ids','skipped_fixture_ids','covered_ids','discovered_ids'): r[key]=[]
                        r['tests_run']=0
                elif not isinstance(case,str):v[0]['durations']={v[0]['executed_ids'][0]:case}
                self.write_reports(d,v)
                with self.assertRaises(ValueError):refresh(d,C,1,scope='required-platforms')

    def test_cli_sidecar_profile_hash(self):
        import hashlib
        from unittest.mock import patch
        from scripts.refresh_test_durations import main
        with tempfile.TemporaryDirectory() as d:
            self.write_reports(d,list(reports(binding()).values()));p=Path(d)/'weights.json'
            with patch('sys.argv',['refresh','--reports',d,'--source',C,'--run','1','--output',str(p),'--scope','required-platforms']):main()
            a=json.loads(Path(str(p)+'.audit.json').read_text())
            self.assertEqual(a['profile_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()

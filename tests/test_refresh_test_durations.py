import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.refresh_test_durations import refresh
from test_ci_test_gate import binding, reports, C


class RefreshTestDurationsTests(unittest.TestCase):
    def test_complete_source_bound_data_only_refresh(self):
        b = binding(); values = reports(b)
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

    def test_missing_artifact_is_not_a_new_skip_list(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):refresh(directory,C,1)


if __name__ == '__main__':unittest.main()

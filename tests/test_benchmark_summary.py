import unittest
from scripts.benchmark_summary import render


def report():
    return {'schema':'execution-layers-v1','environment':{'git_head':'abc','python':'3.12','processor':'test'},
            'cases':[{'case':'array','iterations':100000,'samples':[{}]*27,
                      'route':{'backend':'python-direct','api':'execute_program(preparsed_ast)'},
                      'summary':{name:{'median_seconds':value} for name,value in
                                 [('python',.001),('python_classes',.002),('bsl',.004)]}}]}


class BenchmarkSummaryTests(unittest.TestCase):
    def test_three_timings_and_ratios_visible(self):
        text=render(report())
        self.assertIn('| array | 1.000 | 2.000 | 4.000 | 2.00× | 4.00× | 2.00× |',text)
        self.assertIn('9 measured rounds',text)
        self.assertIn('No speed threshold',text)
        self.assertIn('execute_program(preparsed_ast)',text)

    def test_prepared_label_and_setup_are_distinct(self):
        data=report();case=data['cases'][0]
        case['route'].update(requested_route='prepared',api='execute_prepared(plan)')
        case['preparation_seconds']={'bsl_parse_prepare':.03}
        case['first_execution_seconds']={'bsl':.004}
        text=render(data)
        self.assertIn('Prepared execution (preparation excluded)',text)
        self.assertIn('| array | 30.000 | 4.000 |',text)
        self.assertIn('execute_prepared(plan)',text)

    def test_slowness_is_not_failure(self):
        data=report();data['cases'][0]['summary']['bsl']['median_seconds']=1e6
        self.assertIn('1000000000.00×',render(data))

    def test_wrong_backend_or_invalid_times_rejected(self):
        data=report();data['cases'][0]['route']['backend']='compiled-strict'
        with self.assertRaises(ValueError):render(data)
        for value in (0,-1,float('nan'),float('inf'),True):
            data=report();data['cases'][0]['summary']['bsl']['median_seconds']=value
            with self.assertRaises(ValueError):render(data)
        data=report();data['cases']=[]
        with self.assertRaises(ValueError):render(data)

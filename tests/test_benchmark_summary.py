import unittest
from scripts.benchmark_summary import ratio_cell, render


def report():
    return {'schema':'execution-layers-v1','environment':{'git_head':'abc','python':'3.12','processor':'test'},
            'cases':[{'case':'array','iterations':100000,'samples':[{}]*27,
                      'route':{'backend':'python-direct','api':'execute_program(preparsed_ast)'},
                      'summary':{name:{'median_seconds':value} for name,value in
                                 [('python',.001),('python_classes',.002),('bsl',.004)]}}]}


class BenchmarkSummaryTests(unittest.TestCase):
    def test_three_timings_and_ratios_visible(self):
        text=render(report())
        self.assertIn('| array | 1.000 | 2.000 | 4.000 | 🟨 2.00× | 🟧 4.00× | 🟨 2.00× |',text)
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

    def test_ratio_colors_use_exact_unrounded_boundaries(self):
        for value, expected in ((0, '🟩'), (1.9999, '🟩'), (2, '🟨'),
                                (2.5, '🟨'), (3, '🟨'), (3.0001, '🟧')):
            with self.subTest(value=value):
                self.assertTrue(ratio_cell(value).startswith(expected + ' '))

    def test_only_ratio_cells_are_colored_in_both_routes(self):
        for route in ('default', 'prepared'):
            with self.subTest(route=route):
                data = report()
                case = data['cases'][0]
                case['route']['requested_route'] = route
                case['preparation_seconds'] = {'bsl_parse_prepare': .03}
                case['first_execution_seconds'] = {'bsl': .004}
                text = render(data)
                rows = [line for line in text.splitlines() if line.startswith('| array |')]
                cells = rows[0].split('|')[1:-1]
                self.assertEqual([cell.strip() for cell in cells[:4]], ['array', '1.000', '2.000', '4.000'])
                self.assertEqual([cell.strip() for cell in cells[4:]], ['🟨 2.00×', '🟧 4.00×', '🟨 2.00×'])
                self.assertEqual(rows[1], '| array | 30.000 | 4.000 |')
                self.assertIn('🟩 0 ≤ ratio < 2; 🟨 2 ≤ ratio ≤ 3; 🟧 ratio > 3', text)
                self.assertNotIn('<', text.replace('ratio < 2', ''))
                self.assertNotIn('style=', text)

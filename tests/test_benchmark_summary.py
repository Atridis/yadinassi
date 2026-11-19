import unittest
from copy import deepcopy
from scripts.benchmark_summary import ratio_cell, render


def report():
    return {'schema':'execution-layers-v1','environment':{'git_head':'abc','python':'3.12','processor':'test'},
            'cases':[{'case':'array','iterations':100000,'samples':[{}]*27,
                      'route':{'backend':'python-direct','api':'execute_program(preparsed_ast)'},
                      'summary':{name:{'median_seconds':value} for name,value in
                                 [('python',.001),('python_classes',.002),('bsl',.004)]}}]}


class BenchmarkSummaryTests(unittest.TestCase):
    def test_historical_report_hides_class_timing_and_ratios(self):
        text=render(report())
        self.assertIn('| array | 1.000 | 4.000 | 🟧 4.00× |',text)
        self.assertIn('9 измеренных повторов',text)
        self.assertIn('Порогов скорости нет',text)
        self.assertIn('execute_program(preparsed_ast)',text)

    def test_prepared_label_and_setup_are_distinct(self):
        data=report();case=data['cases'][0]
        case['route'].update(requested_route='prepared',api='execute_prepared(plan)')
        case['preparation_seconds']={'bsl_parse_prepare':.03}
        case['first_execution_seconds']={'bsl':.004}
        text=render(data)
        self.assertIn('Подготовленное исполнение (без времени подготовки)',text)
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
                self.assertEqual([cell.strip() for cell in cells[:3]], ['array', '1.000', '4.000'])
                self.assertEqual([cell.strip() for cell in cells[3:]], ['🟧 4.00×'])
                self.assertEqual(rows[1], '| array | 30.000 | 4.000 |')
                self.assertIn('🟩 0 ≤ коэффициент < 2; 🟨 2 ≤ коэффициент ≤ 3; 🟧 коэффициент > 3', text)
                self.assertNotIn('<', text.replace('коэффициент < 2', ''))
                self.assertNotIn('style=', text)

    def test_identical_conditions_are_printed_once_for_both_routes(self):
        for route, api in [('default','execute_program(preparsed_ast)'), ('prepared','execute_prepared(plan)')]:
            data = report()
            template = data['cases'][0]
            template['route'].update(requested_route=route, api=api)
            data['cases'] = [dict(deepcopy(template), case=name)
                             for name in ('arithmetic','calls','byref','array','map')]
            before = deepcopy(data)
            text = render(data)
            self.assertEqual(text.count('100000 итераций, 9 измеренных повторов;'), 1)
            self.assertIn(f'- Все сценарии: 100000 итераций, 9 измеренных повторов; `{api}`.', text)
            self.assertEqual(data, before)
            self.assertEqual(len([line for line in text.splitlines() if line.startswith('| ') and '1.000 | 4.000' in line]), 5)

    def test_different_iterations_rounds_or_api_remain_visible(self):
        data = report(); base = data['cases'][0]
        data['cases'] = [dict(deepcopy(base), case=name) for name in ('arithmetic','calls','byref','array','map')]
        data['cases'][1]['iterations'] = 64
        data['cases'][2]['samples'] = [{}]*15
        data['cases'][4]['route'].update(requested_route='prepared', api='execute_prepared(plan)')
        text = render(data)
        self.assertNotIn('- Все сценарии:', text)
        self.assertIn('- arithmetic, array: 100000 итераций, 9 измеренных повторов; `execute_program(preparsed_ast)`.', text)
        self.assertIn('- calls: 64 итераций, 9 измеренных повторов;', text)
        self.assertIn('- byref: 100000 итераций, 5 измеренных повторов;', text)
        self.assertIn('- map: 100000 итераций, 9 измеренных повторов; `execute_prepared(plan)`.', text)
        self.assertEqual(text.count(' измеренных повторов;'), 4)

    def test_different_sample_counts_or_requested_routes_do_not_merge(self):
        for difference in ('samples', 'route'):
            data = report(); second = deepcopy(data['cases'][0]); second['case'] = 'map'
            if difference == 'samples': second['samples'].append({})
            else: second['route']['requested_route'] = 'prepared'
            data['cases'].append(second)
            text = render(data)
            self.assertNotIn('- Все сценарии:', text)
            self.assertIn('- array:', text)
            self.assertIn('- map:', text)

    def test_single_workload_keeps_its_name(self):
        self.assertIn('- array: 100000 итераций, 9 измеренных повторов;', render(report()))

    def test_new_two_layer_report_counts_rounds_correctly(self):
        data=report();case=data['cases'][0]
        del case['summary']['python_classes']
        case['samples']=[{'round':r,'layer':layer} for r in range(9) for layer in ('python','bsl')]
        text=render(data)
        self.assertIn('9 измеренных повторов',text)
        self.assertIn('| array | 1.000 | 4.000 | 🟧 4.00× |',text)
        self.assertNotIn('Классы',text)
        self.assertNotIn('классов',text)

    def test_historical_classes_are_ignored_without_mutating_input(self):
        data=report();case=data['cases'][0]
        case['summary']['python_classes']['median_seconds']=float('nan')
        case['case']='arithmetic.int'
        text=render(data)
        self.assertNotIn('Классы',text)
        self.assertNotIn('классов',text)
        self.assertIn('python_classes',case['summary'])

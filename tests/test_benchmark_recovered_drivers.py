import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.benchmark_recovered_drivers import CONTRACTS, binding, main, measure_case, summary
from scripts.benchmark_recovery import LAYERS, scaffold

class DriversTests(unittest.TestCase):
    def test_all_bound_workloads_three_report_layers(self):
        for case in CONTRACTS:
            for n in (1, 7):
                with self.subTest(case=case,n=n):
                    rows=measure_case(case,n,3)
                    self.assertEqual([r['layer'] for r in rows],['python','default','prepared'])
                    for row in rows:
                        self.assertEqual(row['status'],'measured')
                        self.assertEqual(len(row['samples']),3)
                        self.assertGreater(row['python_calls'],0)
                        self.assertGreaterEqual(row['c_calls'],0)
                        self.assertEqual(len(row['source_sha256']),64)
                    self.assertEqual(rows[0]['ratio_to_python'],1)
    def test_classes_lane_is_not_bound_timed_or_profiled(self):
        with patch('scripts.benchmark_recovered_drivers.binding', wraps=binding) as selected:
            rows = measure_case('addition', 3, 3)
        self.assertEqual([call.args[2] for call in selected.call_args_list],
                         ['python', 'default', 'prepared'])
        report = dict(commit='abc', rows=rows)
        self.assertNotIn('"layer": "classes"', json.dumps(report))
        self.assertNotIn('Классы', summary(report))
        self.assertEqual(len(rows), 3)

    def test_cli_selected_size_is_only_size_measured_and_published(self):
        def sample(case, n, rounds):
            return [dict(case=case, n=n, layer=layer, status='measured',
                         wall_seconds=.001, ratio_to_python=1, python_calls=1, c_calls=0)
                    for layer in LAYERS]

        with TemporaryDirectory() as root:
            output = Path(root) / 'recovered-bare.json'
            with patch('sys.argv', ['runner', '--output', str(output), '--size', '4096']), \
                 patch('scripts.benchmark_recovered_drivers.measure_case', side_effect=sample) as measure:
                main()
            report = json.loads(output.read_text(encoding='utf-8'))
            text = output.with_suffix('.md').read_text(encoding='utf-8')
        self.assertEqual([call.args for call in measure.call_args_list],
                         [(case, 4096, 5) for case in CONTRACTS if case != 'method.valuetable.find'])
        self.assertTrue(report['complete'])
        self.assertEqual({row['n'] for row in report['rows']}, {4096})
        self.assertEqual(len(report['rows']), 156)
        self.assertEqual({(row['case'], row['layer']) for row in report['rows']
                          if row['status'] == 'skipped'},
                         {('method.valuetable.find', layer) for layer in LAYERS})
        self.assertEqual(text.count('### N='), 1)
        self.assertIn('### N=4096', text)
        self.assertNotIn('N=512', text)

    def test_state_corruption_rejected(self):
        for case in ('method.array.add','method.valuetable.add','method.valuelist.add'):
            for layer in ('python','classes','default','prepared'):
                reset,run,validate,_,_=binding(case,3,layer)
                reset(); value=run(); validate(value)
                if case=='method.array.add': value[0]=99
                elif case=='method.valuetable.add': list(value)[0][0]=99
                else: value[0][0]=99
                with self.assertRaises(AssertionError): validate(value)
                reset(); validate(run())
    def test_explicit_bare_does_not_call_public_dispatch(self):
        from yadinassi import Interpreter
        with patch.object(Interpreter, 'execute_program', side_effect=AssertionError('public dispatch')), patch.object(Interpreter, 'execute_prepared', side_effect=AssertionError('public dispatch')), patch.object(Interpreter, 'prepare_program', side_effect=AssertionError('public dispatch')):
            for layer in ('default', 'prepared'):
                reset, run, validate, _, _ = binding('method.map.insert', 3, layer)
                reset(); validate(run())
    def test_map_corruption_rejected(self):
        for layer in ('python', 'classes', 'default', 'prepared'):
            reset, run, validate, _, _ = binding('method.map.insert', 3, layer)
            reset(); value = run(); validate(value); value[1] = 99
            with self.assertRaises(AssertionError): validate(value)
    def test_summary_marks_incomplete_scope(self):
        report = scaffold('a'*40)
        text = summary(report)
        self.assertIn('Не production default', text)
        self.assertIn('Не восстановлены:', text)
        self.assertIn('method.valuetable.find N4096', text)
        self.assertNotIn('0.00', text)
    def test_summary_colors_structure_ratios_only_before_rounding(self):
        rows = [
            dict(case='method.structure.get', n=512, layer=layer, status='measured',
                 wall_seconds=.000012, ratio_to_python=ratio, python_calls=9, c_calls=2)
            for layer, ratio in zip(('python', 'default', 'prepared'),
                                    (1, 1.999, 3.001))
        ]
        text = summary(dict(commit='abc', rows=rows))
        self.assertIn('| method.structure.get | 0.0120 | 🟩 2.00× | 🟧 3.00× | 9/2 |', text)

    def test_limits(self):
        for n,rounds in ((0,3),(1,2),(True,3)):
            with self.assertRaises(ValueError): measure_case('addition',n,rounds)

class MoreDriversTests(unittest.TestCase):
    def test_mutated_results_rejected_and_reset(self):
        cases = ('method.array.create','method.array.insert','method.array.delete',
                 'method.structure.create','method.structure.insert','method.structure.set','method.structure.delete')
        for case in cases:
            for layer in ('python','classes','default','prepared'):
                with self.subTest(case=case,layer=layer):
                    reset,run,validate,_,_=binding(case,5,layer)
                    reset(); value=run(); validate(value)
                    if 'structure' in case: value['extra']=None
                    elif layer=='python': value.append(99)
                    else: value.add(99)
                    with self.assertRaises(AssertionError): validate(value)
                    reset(); validate(run())
    def test_scalar_validation_not_boolean(self):
        for case in ('calls','byref','method.structure.property','method.array.find'):
            for layer in ('python','classes','default','prepared'):
                reset,run,validate,_,_=binding(case,1,layer)
                reset(); validate(run())
                with self.assertRaises(AssertionError): validate(True)
    def test_contract_differences_explicit(self):
        self.assertIn('not N distinct fields',CONTRACTS['method.structure.insert'][3])
        self.assertIn('remaining missing',CONTRACTS['method.structure.delete'][3])
        self.assertIn('quadratic',CONTRACTS['method.array.find'][3])
        self.assertIn('mutable list cell',CONTRACTS['byref'][3])

class TableListDriversTests(unittest.TestCase):
    def test_iterate_reference_reads_each_row_by_name(self):
        from unittest.mock import patch
        from scripts.benchmark_recovered_more import ReferenceRow, ReferenceTable

        reset, run, validate, source, _ = binding('method.valuetable.iterate', 7, 'python')
        self.assertIn("row.get_member('n')", source)
        reads = []
        original = ReferenceRow.get_member

        def get_member(row, name):
            reads.append((row.schema, name, row[0]))
            return original(row, name)

        with patch.object(ReferenceRow, 'get_member', get_member):
            reset()
            self.assertEqual(reads, [])
            with patch.object(ReferenceTable, '__iter__', autospec=True,
                              side_effect=ReferenceTable.__iter__) as iterate:
                result = run()
                iterate.assert_called_once()
                table = iterate.call_args.args[0]
            self.assertEqual(result, 21)
            self.assertEqual(reads, [(table.schema, 'n', i) for i in range(7)])
            self.assertTrue(all(schema is table.schema for schema, _, _ in reads))
            validate(result)

    def test_named_and_positional_table_references_are_separate_single_loops(self):
        import ast
        for suffix, lookup in (('set', True), ('set_positional', False)):
            reset, run, validate, source, _ = binding('method.valuetable.'+suffix, 7, 'python')
            tree = ast.parse(source)
            self.assertEqual(sum(isinstance(node, ast.For) for node in ast.walk(tree)), 1)
            self.assertEqual('set_member' in {node.attr for node in ast.walk(tree)
                                              if isinstance(node, ast.Attribute)}, lookup)
            self.assertIn('a.get(i)', source)
            reset()
            validate(run())

    def test_minimal_table_shared_schema_and_positional_classes_control(self):
        from scripts.benchmark_recovered_more import ReferenceTable, CASES
        for suffix in ('set', 'set_positional'):
            reset, run, validate, _, _ = binding('method.valuetable.'+suffix, 7, 'python')
            reset(); table = run(); validate(table)
            self.assertIs(type(table), ReferenceTable)
            self.assertEqual(table.rows, [[i] for i in range(7)])
            self.assertTrue(all(row.schema is table.schema for row in table.rows))
            table.rows[0].schema = dict(table.schema)
            with self.assertRaises(AssertionError): validate(table)
            reset(); validate(run())
        positional = CASES['method.valuetable.set_positional']
        self.assertEqual(positional[1], positional[2])
        self.assertIn('a.get(i)[0]=i', positional[2])

    def test_nested_result_corruption_and_reset(self):
        names=('method.valuetable.create','method.valuetable.delete','method.valuetable.insert',
               'method.valuetable.set','method.valuetable.set_positional','method.valuetable.sort',
               'method.valuelist.insert','method.valuelist.set','method.valuelist.sort')
        for name in names:
            for layer in ('python','classes','default','prepared'):
                with self.subTest(name=name,layer=layer):
                    reset,run,validate,_,_=binding(name,5,layer)
                    reset(); value=run(); validate(value)
                    if name=='method.valuetable.create' and layer=='python': value.schema['extra']=1
                    elif 'valuetable' in name and layer!='python': value.schema['extra']=1
                    elif len(value): value[0][0]=999
                    else: value.append([999])
                    with self.assertRaises(AssertionError): validate(value)
                    reset(); validate(run())
    def test_create_reference_constructs_then_adds_column(self):
        from scripts.benchmark_recovered_more import ReferenceTable
        reset, run, validate, source, _ = binding('method.valuetable.create', 7, 'python')
        self.assertIn('r=ReferenceTable()', source)
        self.assertIn('r.add_column("N")', source)
        reset()
        result = run()
        validate(result)
        self.assertIs(type(result), ReferenceTable)
        self.assertEqual((result.schema, result.rows), ({'n': 0}, []))
    def test_all_method_ids_bound(self):
        from scripts.benchmark_recovery import load_manifest
        self.assertEqual(set(load_manifest()['method']) - set(CONTRACTS),set())
    def test_searches_exact_results_small_sizes(self):
        for name in ('method.valuelist.find','method.valuetable.find'):
            for layer in ('python','classes','default','prepared'):
                reset,run,validate,_,_=binding(name,11,layer)
                reset(); result=run(); self.assertEqual(result,55); validate(result)

class FinalCoreDriversTests(unittest.TestCase):
    def test_all_ids_bound(self):
        from scripts.benchmark_recovery import load_manifest
        manifest=load_manifest()
        self.assertEqual(set(CONTRACTS),set(manifest['core']+manifest['method']))
    def test_core_expected_outputs_both_routes(self):
        expectations={'arithmetic':72,'array':28,'map':28,'string.concat':'x'*8,
                      'string.slice':'bcd','string.replace':'xybcxybc'}
        for name, expected in expectations.items():
            for layer in ('python','classes','default','prepared'):
                reset,run,validate,_,_=binding(name,8,layer)
                reset(); result=run(); self.assertEqual(result,expected); validate(result)
                with self.assertRaises(AssertionError): validate(None)

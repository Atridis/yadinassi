import unittest
from unittest.mock import patch
from scripts.benchmark_recovered_drivers import CONTRACTS, binding, measure_case, summary
from scripts.benchmark_recovery import scaffold

class DriversTests(unittest.TestCase):
    def test_all_bound_workloads_four_layers(self):
        for case in CONTRACTS:
            for n in (1, 7):
                with self.subTest(case=case,n=n):
                    rows=measure_case(case,n,3)
                    self.assertEqual([r['layer'] for r in rows],['python','classes','default','prepared'])
                    for row in rows:
                        self.assertEqual(row['status'],'measured')
                        self.assertEqual(len(row['samples']),3)
                        self.assertGreater(row['python_calls'],0)
                        self.assertGreaterEqual(row['c_calls'],0)
                        self.assertEqual(len(row['source_sha256']),64)
                    self.assertEqual(rows[0]['ratio_to_python'],1)
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
    def test_nested_result_corruption_and_reset(self):
        names=('method.valuetable.create','method.valuetable.delete','method.valuetable.insert',
               'method.valuetable.set','method.valuetable.set_positional','method.valuetable.sort',
               'method.valuelist.insert','method.valuelist.set','method.valuelist.sort')
        for name in names:
            for layer in ('python','classes','default','prepared'):
                with self.subTest(name=name,layer=layer):
                    reset,run,validate,_,_=binding(name,5,layer)
                    reset(); value=run(); validate(value)
                    if name=='method.valuetable.create' and layer=='python': value['schema']['extra']=1
                    elif 'valuetable' in name and layer!='python': value.schema['extra']=1
                    elif len(value): value[0][0]=999
                    else: value.append([999])
                    with self.assertRaises(AssertionError): validate(value)
                    reset(); validate(run())
    def test_all_method_ids_bound(self):
        from scripts.benchmark_recovery import load_manifest
        self.assertEqual(set(load_manifest()['method']) - set(CONTRACTS),set())
    def test_searches_exact_results_small_sizes(self):
        for name in ('method.valuelist.find','method.valuetable.find'):
            for layer in ('python','classes','default','prepared'):
                reset,run,validate,_,_=binding(name,11,layer)
                reset(); result=run(); self.assertEqual(result,55); validate(result)

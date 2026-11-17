"""Correctness and capability reporting, never timing thresholds."""
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from pathlib import Path
import copy
import tempfile
from decimal import Decimal, localcontext, getcontext, Inexact, Rounded
from scripts import benchmark_extended_layers as bench

class ExtendedReferenceTests(unittest.TestCase):
    def setUp(self):
        # Plain Python reference work intentionally rounds Decimals. Keep its
        # flags/context local to this test, not the following runtime contracts.
        context = localcontext()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def test_actual_workloads_repeat_on_both_routes(self):
        expected={
            'structure.fields':'3','valuetable.build_scan':'3','valuelist.build_scan':'3',
            'types.adjust_value':'3.39','json.roundtrip':'3','xml.scalar_codec':'3',
            'file.stat':'12288','file.binary_roundtrip':'12288','xml.roundtrip':'3',
            'db.count':'96','db.update':'3','form.event':'6','form.open':'1',
        }
        for route in ('default','prepared'):
            for name in (bench.PREPARED_CASES if route == 'prepared' else bench.CASES):
                with self.subTest(route=route,case=name):
                    case=bench.measure(name,3,3,route)
                    self.assertEqual(Decimal(case['expected']),Decimal(expected[name]))
                    self.assertTrue(case['samples'])
                    for sample in case['samples']:
                        self.assertEqual(Decimal(sample['result']),Decimal(expected[name]))
                    if name=='db.update':self.assertNotIn('python',case['summary'])
                    if name.startswith('form.'):
                        self.assertEqual(set(case['summary']),{'bsl'})
                        self.assertIn('FormSession',case['api'])
                    if name=='xml.roundtrip' and 'bsl' not in case['summary']:
                        self.assertEqual(case['statuses']['bsl']['status'],'unsupported')
    def test_wrong_type_or_checksum_rejected(self):
        case=bench.Case('wrong',Decimal(1))
        for result in (True,1,1.0,'1',Decimal(2)):
            with self.assertRaises(AssertionError):bench.validate(case,'bsl',result)
    def test_missing_layer_is_explicit_in_summary(self):
        case=bench.measure('form.event',3,3,'default')
        text=bench.render({'schema':'execution-layers-extended-v1', 'environment':{'git_head':'test'}, 'cases':[case]})
        self.assertIn('—',text)
        self.assertIn('несопоставимо',text)

    def test_api_bounds_and_prepared_form_rejected_before_fixture(self):
        with patch.object(bench, 'make_case', side_effect=AssertionError('fixture touched')):
            for rounds in (True, 0, 2, 21, 3.0):
                with self.assertRaises(ValueError): bench.measure('file.stat', 3, rounds, 'default')
        for n in (True, 0, -1, 1001, 3.0):
            with ExitStack() as stack, self.assertRaises(ValueError):
                bench.make_case('file.stat', n, 'default', stack)
        for name, route in (('missing', 'default'), ('file.stat', 'legacy'), ('form.event', 'prepared')):
            with ExitStack() as stack, self.assertRaises(ValueError):
                bench.make_case(name, 3, route, stack)

    def test_known_xml_capability_only_is_optional(self):
        case = bench.Case('xml.roundtrip', Decimal(1), allow_unsupported=True)
        self.assertTrue(bench.optional_xml_constructor(case, bench.PythonDirectUnsupported('python-direct: constructor XMLWriter; select legacy')))
        self.assertFalse(bench.optional_xml_constructor(case, bench.PythonDirectUnsupported('member Read not supported')))
        case.name = 'structure.fields'
        self.assertFalse(bench.optional_xml_constructor(case, bench.PythonDirectUnsupported('constructor XMLWriter;')))

    def test_fixture_directories_removed_on_success_and_validation_error(self):
        original = tempfile.TemporaryDirectory
        for name in ('file.binary_roundtrip', 'db.count'):
            for fail in (False, True):
                directories = []
                def tracked(*args, **kwargs):
                    directory = original(*args, **kwargs)
                    directories.append(Path(directory.name))
                    return directory
                with patch.object(bench, 'TemporaryDirectory', side_effect=tracked):
                    if fail:
                        with patch.object(bench, 'validate', side_effect=AssertionError('injected mismatch')):
                            with self.assertRaises(AssertionError): bench.measure(name, 1, 3, 'default')
                    else:
                        bench.measure(name, 1, 3, 'default')
                self.assertTrue(directories)
                self.assertTrue(all(not path.exists() for path in directories))

    def test_json_checks_actual_decoded_payload(self):
        with ExitStack() as stack:
            case = bench.make_case('json.roundtrip', 3, 'default', stack)
            class FakeArray:
                items = ['wrong'] * 3
            with patch.object(bench, 'read_json', return_value=FakeArray()):
                result = case.runs['python_classes']()
            with self.assertRaises(AssertionError): bench.validate(case, 'python_classes', result)

    def test_renderer_rejects_invalid_or_unexplained_results(self):
        case = bench.measure('structure.fields', 3, 3, 'default')
        source = {'schema': 'execution-layers-extended-v1', 'environment': {'git_head': 'test'}, 'cases': [case]}
        for value in (0, -1, True, float('nan'), float('inf')):
            data = copy.deepcopy(source)
            data['cases'][0]['summary']['python']['median_seconds'] = value
            with self.assertRaises(ValueError): bench.render(data)
        data = copy.deepcopy(source); del data['cases'][0]['summary']['bsl']
        with self.assertRaises(ValueError): bench.render(data)
        data['cases'][0]['statuses']['bsl'] = {'status':'unsupported', 'reason':'explicit test'}
        self.assertIn('не поддерживается', bench.render(data))
        data['cases'][0]['statuses']['bsl']['status'] = 'ok'
        with self.assertRaises(ValueError): bench.render(data)
        with self.assertRaises(ValueError): bench.render({**source, 'cases': []})

    def test_colors_only_on_ratios_and_no_comparison_without_baseline(self):
        for route in ('default', 'prepared'):
            case = bench.measure('structure.fields', 3, 3, route)
            data = {'schema': 'execution-layers-extended-v1', 'environment': {'git_head': 'test'}, 'cases': [case]}
            rows = [line for line in bench.render(data).splitlines() if line.startswith('| structure.fields |')]
            timing = rows[0].split('|')[1:-1]
            self.assertFalse(any(c in ''.join(timing[:4]) for c in '🟩🟨🟧'))
            self.assertTrue(all(any(c in cell for c in '🟩🟨🟧') for cell in timing[4:]))
            self.assertFalse(any(c in rows[1] for c in '🟩🟨🟧'))
        case = bench.measure('db.update', 1, 3, 'default')
        text = bench.render({**data, 'cases':[case]})
        row = next(line for line in text.splitlines() if line.startswith('| db.update |'))
        cells = [cell.strip() for cell in row.split('|')[1:-1]]
        self.assertEqual((cells[1],cells[4],cells[5]), ('—','—','—'))
        self.assertTrue(any(c in cells[6] for c in '🟩🟨🟧'))

    def test_xml_reader_wrong_order_with_same_checksum_is_rejected(self):
        with ExitStack() as stack:
            case = bench.make_case('xml.roundtrip', 3, 'default', stack)
            with patch.object(bench.BSLXMLReader, 'get_attribute', side_effect=['2','1','0']):
                result = case.runs['python_classes']()
            self.assertEqual(result, case.expected)
            with self.assertRaises(AssertionError): bench.validate(case, 'python_classes', result)

    def test_shared_prepared_api_once_without_losing_special_notes_or_json(self):
        base = bench.measure('structure.fields', 3, 3, 'prepared')
        cases = [dict(copy.deepcopy(base), case=name) for name in
                 ('structure.fields', 'valuetable.build_scan', 'file.stat', 'xml.roundtrip', 'db.count')]
        cases[2]['notes'] = next(text for text in bench.labels.NOTES if text.startswith('Warm filesystem'))
        cases[3]['notes'] = next(text for text in bench.labels.NOTES if text.startswith('Host XML classes'))
        del cases[3]['summary']['bsl']
        cases[3]['statuses']['bsl'] = {'status':'unsupported', 'reason':'python-direct: constructor XMLWriter; select legacy'}
        cases[4]['notes'] = 'Same SQLite file and 32 catalog rows. Raw SQL baseline excludes BSL catalog/query admission.'
        data = {'schema':'execution-layers-extended-v1', 'environment':{'git_head':'test'}, 'cases':cases}
        before = copy.deepcopy(data)
        text = bench.render(data)
        self.assertEqual(text.count('execute_prepared(plan)'), 1)
        self.assertIn('Общий режим исполнения для всех сценариев:', text)
        self.assertNotIn('- **structure.fields**:', text)
        self.assertNotIn('- **valuetable.build_scan**:', text)
        self.assertIn('- **file.stat**: Прогретый файловый кеш ОС', text)
        self.assertIn('Прямой BSL не поддерживает конструктор XMLWriter', text)
        self.assertIn('строк справочника: 32', text)
        self.assertNotIn('Raw SQL baseline', text)
        self.assertEqual(data, before)

    def test_mixed_apis_keep_exceptions_visible(self):
        base = bench.measure('structure.fields', 3, 3, 'default')
        cases = [dict(copy.deepcopy(base), case=name) for name in ('structure.fields','json.roundtrip','form.open')]
        cases[-1]['api'] = 'FormSession construction + open + close'
        text = bench.render({'schema':'execution-layers-extended-v1', 'environment':{'git_head':'test'}, 'cases':cases})
        self.assertEqual(text.count('execute_program(preparsed_ast)'), 1)
        self.assertIn('для всех сценариев, кроме form.open', text)
        self.assertIn('- **form.open**: FormSession: создание, открытие и закрытие.', text)


class BenchmarkDecimalIsolationTests(unittest.TestCase):
    def test_actual_reference_workloads_restore_callers_decimal_context(self):
        with localcontext() as caller:
            caller.prec = 28
            caller.traps[Inexact] = caller.traps[Rounded] = False
            caller.clear_flags()
            saved = caller.copy()
            result = unittest.TestResult()
            ExtendedReferenceTests('test_actual_workloads_repeat_on_both_routes').run(result)
            self.assertEqual(result.testsRun, 1)
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
            self.assertIs(getcontext(), caller)
            self.assertEqual(caller.prec, saved.prec)
            self.assertEqual(caller.rounding, saved.rounding)
            self.assertEqual(caller.traps, saved.traps)
            self.assertEqual(caller.flags, saved.flags)

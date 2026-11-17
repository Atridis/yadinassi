"""Pair separate tables without merging results or hiding partial failures."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts import benchmark_report as paired
from tests.test_benchmark_summary import report


def reports():
    result = {}
    for family, route, filename, _ in paired.INPUTS:
        if family == 'core':
            data = report()
            case = data['cases'][0]
            case['case'] = family + '-' + route
            case['route'].update(requested_route=route, api='execute_prepared(plan)' if route=='prepared' else 'execute_program(preparsed_ast)')
            case['preparation_seconds'] = {'bsl_parse_prepare': .003}
            case['first_execution_seconds'] = {'bsl': .004}
        else:
            data = {'schema':'execution-layers-extended-v1', 'environment':{'git_head':'abc'}, 'cases': [{
                'case':family+'-'+route, 'requested_route':route, 'iterations':64,
                'api':'execute_prepared(plan)' if route=='prepared' else 'execute_program(preparsed_ast)',
                'summary':{'python':{'median_seconds':.001},'python_classes':{'median_seconds':.002},'bsl':{'median_seconds':.004}},
                'statuses':{},'notes':'','first_execution_seconds':{'python':.001,'python_classes':.002,'bsl':.004},
                'fixture_and_prepare_seconds':.003,
            }]}
        result[filename] = data
    return result


class PairedReportTests(unittest.TestCase):
    def test_separate_main_tables_are_adjacent_in_each_family(self):
        data = reports(); before = deepcopy(data)
        text, errors = paired.assemble(data)
        self.assertFalse(errors)
        self.assertEqual(data, before)
        for family,title in [('core','Основные сценарии'),('extended','Расширенные сценарии')]:
            section=text.split('### '+title,1)[1].split('#### Подготовка и первый вызов',1)[0]
            self.assertLess(section.index('#### Подготовка включена в замер'), section.index('| '+family+'-default |'))
            self.assertLess(section.index('| '+family+'-default |'), section.index('#### План подготовлен заранее'))
            self.assertLess(section.index('#### План подготовлен заранее'), section.index('| '+family+'-prepared |'))
            self.assertNotIn('Пояснения', section)
        self.assertEqual(text.count('## Сравнение производительности\n'),1)
        self.assertEqual(text.count(paired.LEGEND),1)
        self.assertLess(text.index(paired.LEGEND),text.index('### Основные сценарии'))
        self.assertNotIn('холодн',text)
        self.assertNotIn('горяч',text)
        self.assertNotIn('без подготовки',text)
        self.assertNotIn('с подготовкой',text)
        self.assertIn('предварительный разбор исходного BSL в AST не входит',text)
        self.assertIn('отдельный жизненный цикл FormSession',text)

    def test_all_numeric_table_lines_are_preserved_verbatim(self):
        data = reports(); text,_ = paired.assemble(data)
        for family,route,filename,renderer in paired.INPUTS:
            original=renderer(data[filename])
            rows=[line for line in original.splitlines() if line.startswith('| '+family+'-'+route+' |')]
            self.assertEqual(len(rows),2)
            for row in rows: self.assertEqual(text.count(row),1)

    def test_partial_failure_retains_valid_tables_and_explicit_missing_markers(self):
        data=reports();data['extended-prepared.json']=None
        data['execution-layers-prepared.json']={'broken':True}
        text,errors=paired.assemble(data)
        self.assertEqual(set(errors),{'extended-prepared.json','execution-layers-prepared.json'})
        self.assertIn('| core-default |',text)
        self.assertIn('| extended-default |',text)
        self.assertIn('Неполный отчёт',text)
        self.assertEqual(text.count('Результат не получен или некорректен.'),2)

    def test_mislabeled_route_not_shown_as_opposite_measurement(self):
        data=reports();data['execution-layers-prepared.json']['cases'][0]['route']['requested_route']='default'
        text,errors=paired.assemble(data)
        self.assertIn('execution-layers-prepared.json',errors)
        self.assertNotIn('| core-prepared |',text)

    def test_different_source_commits_are_not_combined(self):
        data=reports();data['extended-prepared.json']['environment']['git_head']='different'
        with self.assertRaises(ValueError):paired.assemble(data)

    def test_cli_publishes_partial_output_and_returns_failure(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);data=reports()
            (root/'execution-layers.json').write_text(json.dumps(data['execution-layers.json']))
            (root/'extended-default.json').write_text('{invalid JSON')
            output=root/'summary-paired.md';stdout=io.StringIO()
            with redirect_stdout(stdout):
                code=paired.main(['--directory',str(root),'--output',str(output)])
            self.assertEqual(code,1)
            self.assertEqual(output.read_text(),stdout.getvalue())
            self.assertIn('| core-default |',output.read_text())
            self.assertIn('Неполный отчёт',output.read_text())

    def test_malformed_nested_route_still_preserves_other_results(self):
        data=reports();data['execution-layers-prepared.json']['cases'][0]['route']=None
        text,errors=paired.assemble(data)
        self.assertIn('execution-layers-prepared.json',errors)
        self.assertIn('| extended-prepared |',text)


class ExplanationDedupTests(unittest.TestCase):
    def test_common_lines_once_and_different_conditions_scoped(self):
        parts = {'default': ('', '', 'Коммит: `abc`\nShared warning\n- API A\n- file: same'),
                 'prepared': ('', '', 'Коммит: `abc`\nShared warning\n- API B\n- file: same')}
        text = '\n'.join(paired.explanations(parts))
        self.assertEqual(text.count('Shared warning'), 1)
        self.assertEqual(text.count('- file: same'), 1)
        self.assertIn('**Подготовка включена в замер:**\n\n- API A', text)
        self.assertIn('**План подготовлен заранее:**\n\n- API B', text)
        self.assertNotIn('Коммит:', text)

    def test_partial_prose_keeps_scope_and_all_warnings(self):
        text='\n'.join(paired.explanations({'default':None,'prepared':('', '', 'Warning\nAPI B')}))
        self.assertIn('**План подготовлен заранее:**',text)
        self.assertIn('Warning',text)
        self.assertNotIn('**Подготовка включена в замер:**',text)

    def test_metadata_difference_including_missing_is_explicit(self):
        envs={'основные / Подготовка включена в замер':{'python':'3.12','processor':'x','timer':'A'},
              'основные / План подготовлен заранее':{'python':'3.12','processor':'y'}}
        text='\n'.join(paired.environment_lines(envs))
        self.assertEqual(text.count('Python:'),1)
        self.assertIn('Процессор (основные / Подготовка включена в замер)',text)
        self.assertIn('Процессор (основные / План подготовлен заранее)',text)
        self.assertIn('timer (основные / План подготовлен заранее): не указано',text)

    def test_commit_global_once_environment_not_silently_merged(self):
        data=reports()
        for value in data.values():value['environment'].update(python='same',processor='cpu')
        data['extended-prepared.json']['environment']['processor']='other'
        text,errors=paired.assemble(data)
        self.assertFalse(errors)
        self.assertEqual(text.count('Коммит: `abc`'),1)
        self.assertEqual(text.count('Python:'),1)
        self.assertIn('Процессор (расширенные / План подготовлен заранее): `"other"`',text)
        self.assertNotIn('#### Пояснения:',text)

    def test_identical_file_notes_and_form_suffix_keep_operations(self):
        lines=['- **file.stat**: same', '- **file.binary_roundtrip**: same',
               '- **form.event**: dispatch. Настоящий жизненный цикл формы. N/A reason',
               '- **form.open**: open/close. Настоящий жизненный цикл формы. N/A reason']
        text='\n'.join(paired.compact_notes(lines))
        self.assertIn('**file.stat, file.binary_roundtrip**: same',text)
        self.assertEqual(text.count('N/A reason'),1)
        self.assertIn('**form.event**: dispatch.',text)
        self.assertIn('**form.open**: open/close.',text)

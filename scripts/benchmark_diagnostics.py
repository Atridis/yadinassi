"""Untimed, opt-in call counters. Run only AFTER the uninstrumented timings."""
import argparse
import ast
import builtins
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import benchmark_execution_layers as core
from scripts import benchmark_extended_layers as extended
from scripts import performance_summary_labels as labels

CASES = ('core.map', 'core.byref', 'structure.fields', 'valuetable.build_scan',
         'json.roundtrip', 'xml.scalar_codec', 'db.count', 'db.update',
         'form.event', 'form.open')
COUNT_SIZES = (32, 128, 512)
# Keys specify exact source file AND function name, not similarly named functions
# from unrelated subsystems. Counts are entries, including recursive calls.
WATCHED = {
    'source_map_compile': ('experimental_naked_errors.py', 'compile'),
    'prepared_ast_snapshot': ('python_direct.py', '_snapshot'),
    'sqlite_catalog_begin': ('sqlite_catalog.py', '_begin'),
    'configuration_read_source': ('sqlite_inventory_enum_profile.py', 'read_source'),
    'configuration_validate_ddl': ('sqlite_main_demo_profile.py', 'validate_main_demo_ddl'),
    'configuration_validate_canonical': ('configuration_main_demo.py', 'validate_canonical'),
    'configuration_same_recursive': ('configuration_inventory_enums.py', '_same'),
    'direct_boundary_check': ('python_direct.py', '_check'),
    'base_boundary_check': ('experimental_naked_boundaries.py', '_check'),
    'catalog_owner_check': ('python_direct_database.py', '_catalog_owner'),
    'catalog_resolve_member_call': ('python_direct_database.py', 'resolve_member_call'),
    'catalog_resolve_member': ('python_direct_database.py', 'resolve_member'),
    'catalog_invoke': ('python_direct_database.py', 'invoke'),
    'live_source_reference': ('experimental_naked_live_state.py', 'source_reference'),
}


def validate_targets():
    """Fail visibly on renamed instrumentation targets instead of false zeros."""
    for file, name in WATCHED.values():
        tree = ast.parse((ROOT / 'yadinassi' / file).read_text())
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name for node in ast.walk(tree)):
            raise ValueError(f'missing diagnostic target: {file}:{name}')


def capture(run):
    """Observe one current-thread invocation; never return instrumented timings."""
    if sys.getprofile() is not None:
        raise RuntimeError('diagnostics require an unprofiled current thread')
    targets = {(str(ROOT / 'yadinassi' / file), name): key
               for key, (file, name) in WATCHED.items()}
    counts = dict.fromkeys(('python_calls', 'builtin_compile', 'sqlite_execute',
                            'sqlite_executemany', 'sqlite_executescript', *WATCHED), 0)

    def profile(frame, event, arg):
        if event == 'call':
            counts['python_calls'] += 1
            key = targets.get((frame.f_code.co_filename, frame.f_code.co_name))
            if key is not None:
                counts[key] += 1
        elif event == 'c_call':
            if arg is builtins.compile:
                counts['builtin_compile'] += 1
            receiver = getattr(arg, '__self__', None)
            if isinstance(receiver, (sqlite3.Connection, sqlite3.Cursor)):
                key = 'sqlite_' + getattr(arg, '__name__', '')
                if key in counts:
                    counts[key] += 1
    sys.setprofile(profile)
    try:
        result = run()
    finally:
        sys.setprofile(None)
    return result, counts


def diagnose(name, iterations, route, *, catalog_rows=32):
    if name not in CASES or route not in ('default', 'prepared'):
        raise ValueError('unknown diagnostic case or route')
    if type(iterations) is not int or not 1 <= iterations <= 64:
        raise ValueError('diagnostic iterations must be an integer in 1..64')
    if type(catalog_rows) is not int or not 1 <= catalog_rows <= 1024:
        raise ValueError('catalog rows must be an integer in 1..1024')
    if route == 'prepared' and name.startswith('form.'):
        raise ValueError('form lifecycle has no execute_prepared route')
    with ExitStack() as stack:
        if name.startswith('core.'):
            workload = core.workload(name.removeprefix('core.'), iterations)
            case = extended.Case(name, workload.expected, operations=iterations)
            case.runs.update(python=workload.native, python_classes=workload.classes)
            extended.attach_bsl(case, workload.source, route, stack)
        else:
            case = extended.make_case(name, iterations, route, stack, catalog_rows=catalog_rows)
        layers = {}
        for layer in extended.LAYERS:
            if layer not in case.runs:
                continue
            run = case.runs[layer]
            # Match a checked first invocation + warmup, all outside the profiler.
            for _ in range(2):
                if layer in case.before: case.before[layer]()
                extended.validate(case, layer, run())
            if layer in case.before: case.before[layer]()
            result, counts = capture(run)
            extended.validate(case, layer, result)
            layers[layer] = {'result': str(result), 'counters': counts}
        return {'case': name, 'iterations': iterations, 'operations_per_capture': case.operations,
                'catalog_rows': catalog_rows if name == 'db.count' else None,
                'requested_route': route, 'api': case.api, 'expected': str(case.expected),
                'source_sha256': hashlib.sha256(case.source.encode()).hexdigest(),
                'statuses': case.statuses, 'notes': case.notes, 'layers': layers}


def render(report):
    if report['schema'] != 'execution-call-diagnostics-v1' or not report['cases']:
        raise ValueError('invalid diagnostic report')
    columns = ('python_calls', 'builtin_compile', 'source_map_compile', 'sqlite_execute',
               'configuration_read_source', 'configuration_validate_ddl',
               'configuration_validate_canonical', 'direct_boundary_check', 'catalog_owner_check')
    lines = ['## Диагностика вызовов без замера времени (отдельный процесс)', '',
             'Коммит: `' + report['environment']['git_head'] + '`', '',
             'Один вызов со счётчиками для каждого слоя после двух проверенных прогревочных вызовов без профилирования. '
             'Подготовка, сброс состояния и проверка результата исключены. Это числа вызовов, не время. '
             'Нулевой read_source при прогретом readonly COUNT допустим: полный допуск уже выполнен до профилирования; '
             'счётчик не измеряет число проверок полномочий или холодных допусков. '
             'В подписи указаны итерации и операции за один запуск; жизненный цикл формы считается одной операцией.', '',
             '| Сценарий / режим / объём | Слой | Вызовы Python | Встроенный compile | SourceMap.compile | API SQLite execute | read_source | Проверки DDL | Проверки конфигурации | Прямой _check | Проверки владельца |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for case in report['cases']:
        for layer, data in case['layers'].items():
            if data['result'] != case['expected'] or any(type(v) is not int or v < 0 for v in data['counters'].values()):
                raise ValueError('invalid diagnostic result')
            label = (case['case'] + ' / ' + labels.ROUTES.get(case['requested_route'],case['requested_route'])
                     + ' / итераций=' + str(case['iterations']) + ' / операций=' + str(case['operations_per_capture']))
            if case['catalog_rows'] is not None: label += ' / строк=' + str(case['catalog_rows'])
            lines.append('| ' + label + ' | ' + labels.LAYERS.get(layer,layer) + ' | ' + ' | '.join(str(data['counters'][key]) for key in columns) + ' |')
    lines += ['', 'Порогов скорости нет; коэффициенты времени и цветовые категории к счётчикам не применяются. '
              'Счётчики SQLite отражают вызовы API Connection/Cursor, а не SQL-операторы, инструкции виртуальной машины, строки или триггеры. '
              'Встроенный compile включает разбор в AST; SourceMap.compile — другая метрика, складывать их нельзя. '
              'Вызовы Python учитывают рекурсию; профилировщик добавляет накладные расходы и не подходит для сравнения времени. '
              'Наблюдается только текущий поток. Отсутствующие или несопоставимые слои не подменяются вымышленными данными.', '',
              'JSON сохраняет все именованные счётчики и сведения об исходниках и среде. COUNT выполняет одинаковое число '
              'запросов при разном числе строк; заполнение тестовой БД исключено. Сырой SQLite по-прежнему не включает проверки допуска к каталогу и запросам.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=8)
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--count-rows', type=int, action='append')
    parser.add_argument('--output', required=True)
    parser.add_argument('--summary', required=True)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 64: parser.error('iterations must be 1..64')
    sizes = args.count_rows or COUNT_SIZES
    if any(not 1 <= n <= 1024 for n in sizes) or len(sizes) != len(set(sizes)):
        parser.error('distinct row counts must be 1..1024')
    selected = args.case or CASES
    if len(selected) != len(set(selected)): parser.error('duplicate case')
    validate_targets()
    cases = []
    for route in ('default', 'prepared'):
        for name in selected:
            if route == 'prepared' and name.startswith('form.'): continue
            for size in sizes if name == 'db.count' else (32,):
                cases.append(diagnose(name, args.iterations, route, catalog_rows=size))
    report = {'schema': 'execution-call-diagnostics-v1', 'environment': core.metadata(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'counter_targets': {key: {'file': file, 'function': name} for key, (file, name) in WATCHED.items()},
              'scope': 'one checked current-thread invocation; no setup/reset/validation; no timings', 'cases': cases}
    for path in (args.output, args.summary): Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    Path(args.summary).write_text(render(report), encoding='utf-8')


if __name__ == '__main__':
    main()

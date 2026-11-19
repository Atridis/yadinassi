"""Runnable reconstructed workloads. Not source-identical historical benchmarks."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.benchmark_call_counts import capture
from scripts.benchmark_recovery import scaffold
from scripts.benchmark_summary import ratio_cell

# Each Python source is the actual executed 1x baseline, not pseudocode.
CONTRACTS = {
    'method.map.get': ('R=0; For I=0 To N-1 Do R=R+A.Get(I); EndDo;', 'r = 0\nfor i in range(n):\n    r += a.get(i)', 'map_read', 'N prefilled integer key lookups, accumulated'),
    'method.map.set': ('For I=0 To N-1 Do A[I]=I; EndDo; R=A;', 'for i in range(n):\n    a[i] = i\nr = a', 'map_set', 'N overwrites of prefilled zero integer values'),
    'method.map.iterate': ('R=0; For Each P In A Do R=R+P.Key+P.Value; EndDo;', 'r = 0\nfor k, v in a.items():\n    r += k + v', 'map_iterate', 'One prefilled Map items traversal, both key/value projections; no pair materialization'),
    'method.valuetable.get': ('R=0; For I=0 To N-1 Do R=R+A.Get(I).N; EndDo;', 'r = 0\nfor i in range(n):\n    r += a[i][0]', 'table_read', 'N row lookups and named field reads (Python positional one-column baseline)'),
    'method.valuetable.get_positional': ('R=0; For I=0 To N-1 Do R=R+A.Get(I)[0]; EndDo;', 'r = 0\nfor i in range(n):\n    r += a[i][0]', 'table_pos', 'N row lookups and positional cell reads'),
    'method.valuetable.iterate': ('R=0; For Each Row In A Do R=R+Row.N; EndDo;', 'r = 0\nfor row in a:\n    r += row[0]', 'table_iterate', 'One traversal, named field read per row (Python positional baseline)'),
    'method.valuelist.get': ('R=0; For I=0 To N-1 Do R=R+A.Get(I).Value; EndDo;', 'r = 0\nfor i in range(n):\n    r += a[i][0]', 'list_read', 'N item lookups and Value field reads'),
    'method.valuelist.iterate': ('R=0; For Each Item In A Do R=R+Item.Value; EndDo;', 'r = 0\nfor item in a:\n    r += item[0]', 'list_iterate', 'One traversal, Value field read per item'),

    'method.array.get': ('R=0; For I=0 To N-1 Do R=R+A.Get(I); EndDo;', 'r = 0\nfor i in range(n):\n    r += a[i]', 'array_read', 'N indexed reads of prefilled ascending integers, accumulated'),
    'method.array.set': ('For I=0 To N-1 Do A.Set(I,I); EndDo; R=A;', 'for i in range(n):\n    a[i] = i\nr = a', 'array_set', 'N indexed writes into preallocated zero-filled array'),
    'method.array.iterate': ('R=0; For Each X In A Do R=R+X; EndDo;', 'r = 0\nfor x in a:\n    r += x', 'array_iterate', 'One traversal of N prefilled ascending integers, accumulated'),
    'method.map.insert': ('For I=0 To N-1 Do A.Insert(I,I); EndDo; R=A;', 'for i in range(n):\n    a[i] = i\nr = a', 'map', 'N unique integer key/value inserts; empty fixture outside timer'),
    'assignment': ('R=0; For I=0 To N-1 Do R=I; EndDo;', 'r = 0\nfor i in range(n):\n    r = i', 'last', 'N assignments, initial R=0'),
    'addition': ('R=0; For I=0 To N-1 Do R=R+I; EndDo;', 'r = 0\nfor i in range(n):\n    r += i', 'sum', 'N integer additions of indices'),
    'string.length': ('R=0; For I=0 To N-1 Do R=R+StrLen("abc"); EndDo;', 'r = 0\nfor i in range(n):\n    r += len("abc")', 'length', 'N lengths of fixed ASCII string, accumulated'),
    'method.array.add': ('For I=0 To N-1 Do A.Add(I); EndDo; R=A;', 'for i in range(n):\n    a.append(i)\nr = a', 'array', 'N append operations; empty fixture outside timer'),
    'method.valuetable.add': ('For I=0 To N-1 Do A.Add(); EndDo; R=A;', 'for i in range(n):\n    a.append([None])\nr = a', 'table', 'N default rows; one-column schema and empty table outside timer'),
    'method.valuelist.add': ('For I=0 To N-1 Do A.Add(I); EndDo; R=A;', 'for i in range(n):\n    a.append([i, "", False, None])\nr = a', 'list', 'N default four-field items; empty fixture outside timer'),
}


from scripts.benchmark_recovered_more import CASES as MORE_CASES, bind as bind_more
CONTRACTS.update({name: (entry[0],entry[1],entry[4],entry[5]) for name,entry in MORE_CASES.items()})

def binding(case, n, layer):
    if case in MORE_CASES: return bind_more(case,n,layer)
    from yadinassi import Interpreter
    from yadinassi.execution.codegen import native_bare_compiler as bare
    from yadinassi.syntax.parser import parse
    from yadinassi.execution.codegen.native_bare_collections import BareArray, BareValueList, BareMap
    from yadinassi.execution.codegen.native_bare_table import BareTable
    bsl, python, kind, description = CONTRACTS[case]
    classes = python
    if kind == 'map_iterate': classes = python.replace('a.items()', 'dict.items(a)')
    if kind == 'table_read': classes = python.replace('a[i][0]', "a.get(i).get_member('n')")
    if kind == 'table_pos': classes = python.replace('a[i][0]', 'a.get(i).get(0)')
    if kind == 'table_iterate': classes = python.replace('row[0]', "row.get_member('n')")
    if kind == 'list_read': classes = python.replace('a[i][0]', "a.get(i).get_member('value')")
    if kind == 'list_iterate': classes = python.replace('item[0]', "item.get_member('value')")
    if kind == 'array_read': classes = python.replace('a[i]', 'a.get(i)')
    if kind == 'array_set': classes = python.replace('a[i] = i', 'a.set(i, i)')
    if kind == 'map': classes = python.replace('a[i] = i', 'a.insert(i, i)')
    if kind == 'array': classes = python.replace('a.append(i)', 'a.add(i)')
    if kind == 'table': classes = python.replace('a.append([None])', 'a.add()')
    if kind == 'list': classes = python.replace('a.append([i, "", False, None])', 'a.add(i)')
    def fixture():
        if kind in ('map_read', 'map_set', 'map_iterate'):
            data = {i: (0 if kind == 'map_set' else i) for i in range(n)}
            return data if layer == 'python' else BareMap(data)
        if kind in ('table_read', 'table_pos', 'table_iterate', 'list_read', 'list_iterate'):
            table_kind = kind.startswith('table')
            if layer == 'python': return [[i] if table_kind else [i, '', False, None] for i in range(n)]
            value = BareTable() if table_kind else BareValueList()
            if table_kind: value.add_column('N')
            for i in range(n):
                if table_kind: value.add()[0] = i
                else: value.add(i)
            return value
        if kind in ('array_read', 'array_iterate', 'array_set'):
            data = [0]*n if kind == 'array_set' else list(range(n))
            if layer == 'python': return data
            array = BareArray(); array._data = data; return array
        if layer == 'python': return {} if kind == 'map' else []
        if kind == 'map': return BareMap()
        if kind == 'array': return BareArray()
        if kind == 'list': return BareValueList()
        if kind == 'table':
            table = BareTable(); table.add_column('N'); return table
        return None
    fixture_ref = [None]
    readonly = kind in ('array_read','array_iterate','map_read','map_iterate','table_read','table_pos','table_iterate','list_read','list_iterate')
    def snapshot(value):
        if kind.startswith('map'): return list(dict.items(value))
        if kind.startswith(('table','list')):
            return [list(row) for row in value]
        return list(value)
    original = [None]
    def new_fixture():
        value = fixture(); fixture_ref[0] = value
        if readonly: original[0] = snapshot(value)
        return value
    if layer in ('python', 'classes'):
        source = python if layer == 'python' else classes
        namespace = {}
        exec('def run(n, a):\n' + '\n'.join('    '+line for line in source.splitlines()) + '\n    return r', namespace)
        function = namespace['run']
        state = [None]
        def reset(): state[0] = new_fixture()
        def run(): return function(n, state[0])
    else:
        source = bsl
        vm = Interpreter()
        program = parse(bsl)
        plan = bare.prepare_module(vm, program) if layer == 'prepared' else None
        def reset():
            vm.variables.clear(); vm.variables.update(n=n, a=new_fixture())
        def run():
            if layer == 'prepared': bare.execute_prepared(vm, plan)
            else: bare.execute(vm, program)
            return vm.variables['r']
    def validate(value):
        if readonly:
            if snapshot(fixture_ref[0]) != original[0]: raise AssertionError('read workload mutated full state')
            if kind.startswith('table') and layer != 'python':
                table = fixture_ref[0]
                if table.schema != {'n': 0} or any(row.table is not table for row in table.rows):
                    raise AssertionError('read workload changed schema or owner')
        if kind in ('map_read','map_iterate','table_read','table_pos','table_iterate','list_read','list_iterate'):
            expected = n*(n-1)//2 * (2 if kind == 'map_iterate' else 1)
            if type(value) is not int or value != expected: raise AssertionError((case,value,expected))
            return
        if kind in ('last', 'sum', 'length', 'array_read', 'array_iterate'):
            expected = {'last': n-1, 'sum': n*(n-1)//2, 'length': 3*n, 'array_read': n*(n-1)//2, 'array_iterate': n*(n-1)//2}[kind]
            if type(value) is not int or value != expected: raise AssertionError((case, value, expected))
        elif kind in ('map','map_set'):
            if dict.items(value) != dict.items({i: i for i in range(n)}):
                raise AssertionError('full map state differs')
        else:
            actual = list(value)
            if kind in ('array', 'array_set'): expected = list(range(n))
            elif kind == 'list':
                actual = [list(x) for x in actual]
                expected = [[i, '', False, None] for i in range(n)]
            else:
                actual = [list(x) for x in actual]
                expected = [[None] for _ in range(n)]
                if layer != 'python':
                    if value.schema != {'n': 0} or any(row.table is not value for row in value.rows):
                        raise AssertionError('table schema/owner changed')
            if actual != expected: raise AssertionError('full collection state differs: '+case)
    return reset, run, validate, source, description


def measure_case(case, n, rounds=5):
    if type(n) is not int or n < 1 or type(rounds) is not int or rounds < 3:
        raise ValueError('positive N and at least three rounds required')
    jobs = {layer: binding(case, n, layer) for layer in ('python','classes','default','prepared')}
    samples = {layer: [] for layer in jobs}
    for reset, run, validate, _, _ in jobs.values():
        reset(); validate(run())
    for round_index in range(rounds):
        layers = list(jobs)
        for layer in layers[round_index % 4:] + layers[:round_index % 4]:
            reset, run, validate, _, _ = jobs[layer]
            reset()
            cpu = time.process_time_ns(); wall = time.perf_counter_ns()
            result = run()
            elapsed = time.perf_counter_ns()-wall; used = time.process_time_ns()-cpu
            validate(result)
            samples[layer].append({'wall_seconds': elapsed/1e9, 'cpu_seconds': used/1e9})
    rows = []
    # Profiling is a separate untimed pass, never mixed with timing samples.
    for layer, (reset, run, validate, source, description) in jobs.items():
        reset(); result, counts = capture(run); validate(result)
        rows.append(dict(case=case,n=n,layer=layer,status='measured',
            contract=description,workload_source=source,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            samples=samples[layer],wall_seconds=statistics.median(s['wall_seconds'] for s in samples[layer]),
            cpu_seconds=statistics.median(s['cpu_seconds'] for s in samples[layer]),**counts))
    baseline = rows[0]['wall_seconds']
    for row in rows: row['ratio_to_python'] = row['wall_seconds']/baseline
    return rows


def summary(report):
    from collections import Counter
    counts = Counter(row['status'] for row in report['rows'])
    lines = ['## Изолированный bare: предварительные реконструированные сценарии',
             '', 'Не production default и не точная копия исторических workloads.',
             'Обычный bare включает компиляцию AST; готовый bare исключает её. Профиль отдельно от времени.',
             f"Коммит `{report['commit']}`; статусы: {dict(counts)}.",
             'Python = 1×. Короткая серия, общая машина: не гарантия ускорения.', '']
    measured = {(r['case'],r['n'],r['layer']):r for r in report['rows'] if r['status']=='measured'}
    if any(case in ('method.valuetable.set', 'method.valuetable.set_positional') for case, _, _ in measured):
        lines += ['Эталон Python для set/set_positional: минимальная Table с общим словарём схемы и списком строк; '
                  'Table.get возвращает rows[index], Row(list).set_member пишет self[self.schema[name]]. '
                  'Нет epoch или индексов. Named: a.get(i).set_member("n",i); positional: a.get(i)[0]=i. '
                  'Классы positional выполняют тот же a.get(i)[0]=i на BareTable, что и BSL: это контроль трансляции. '
                  'Подготовка таблиц и полная проверка результата вне таймера. Один проход на сценарий.', '']
    for n in (512,4096):
        lines += [f'### N={n}', '| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |', '|---|---:|---:|---:|---:|---:|']
        for case in CONTRACTS:
            if (case,n,'prepared') not in measured: continue
            rows = [measured[case,n,layer] for layer in ('python','classes','default','prepared')]
            ratios = ' | '.join(ratio_cell(row['ratio_to_python']) for row in rows[1:])
            lines.append(f"| {case} | {rows[0]['wall_seconds']*1000:.4f} | {ratios} | {rows[3]['python_calls']}/{rows[3]['c_calls']} |")
    unbound=sorted({r['case'] for r in report['rows'] if r['status']=='unbound'})
    lines += ['', 'Не восстановлены: '+(', '.join(unbound) if unbound else 'нет'), '', 'Явный пропуск: method.valuetable.find N4096 во всех слоях.']
    for r in report['rows']:
        if r['status']=='error': lines.append(f"ERROR {r['case']} N{r['n']} {r['layer']}: {r['reason']}")
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=5)
    args=parser.parse_args()
    report=scaffold(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    report.update(python=sys.version,dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
                  reconstructed_workloads=True, historical_source_equivalence=False,
                  backend='explicit native_bare_compiler (not public default)',
                  api_contract={'default': 'bare.execute(vm, preparsed_ast)', 'prepared': 'bare.execute_prepared(vm, plan)'},
                  compiler_sha256=hashlib.sha256((ROOT/'yadinassi/execution/codegen/native_bare_compiler.py').read_bytes()).hexdigest())
    index={(r['case'],r['n'],r['layer']): r for r in report['rows']}
    for case in CONTRACTS:
        for n in (512,4096):
            if case == 'method.valuetable.find' and n == 4096: continue
            try:
                for row in measure_case(case,n,args.rounds): index[row['case'],n,row['layer']].update(row,reason=None)
            except Exception as exc:
                for layer in ('python','classes','default','prepared'):
                    index[case,n,layer].update(status='error',reason=f'{type(exc).__name__}: {exc}')
    report['complete'] = all(r['status'] in ('measured','skipped') for r in report['rows'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    args.output.with_suffix('.md').write_text(summary(report),encoding='utf-8')
    if any(r['status']=='error' for r in report['rows']): raise SystemExit(1)

if __name__ == '__main__': main()

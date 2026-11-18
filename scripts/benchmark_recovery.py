"""Evidence-backed coverage scaffold; deliberately not a benchmark runner.

Never substitute old timings for a missing executable workload. Runtime bindings
must be reconstructed and validated separately before a row can be measured.
"""
import argparse
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name('benchmark_recovery_manifest.json')
SIZES = (512, 4096)
LAYERS = ('python', 'classes', 'default', 'prepared')
MODES = {'default': 'Подготовка включена в замер',
         'prepared': 'План подготовлен заранее'}


def load_manifest():
    value = json.loads(MANIFEST.read_text(encoding='utf-8'))
    names = value['core'] + value['method']
    if len(value['core']) != 11 or len(value['method']) != 41 or len(set(names)) != 52:
        raise ValueError('expected 11 distinct core and 41 distinct method identifiers')
    return value


def scaffold(commit):
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('exact source commit required')
    manifest = load_manifest()
    rows = []
    for group in ('core', 'method'):
        for case in manifest[group]:
            for n in SIZES:
                for layer in LAYERS:
                    skipped = case == 'method.valuetable.find' and n == 4096
                    rows.append(dict(group=group, case=case, n=n, layer=layer,
                        status='skipped' if skipped else 'unbound',
                        reason='Исторический явный пропуск table.find N4096 (квадратичная работа).'
                               if skipped else 'Исполняемый сценарий и проверка полного состояния ещё не восстановлены.',
                        wall_seconds=None, cpu_seconds=None, python_calls=None, c_calls=None,
                        source_sha256=None))
    return dict(schema_version=1, commit=commit, complete=False,
                historical_measurements_reused=False, evidence=manifest['sources'], rows=rows)


def render(report):
    if any(row['status'] not in ('unbound', 'skipped') for row in report['rows']):
        raise ValueError('scaffold renderer does not accept measured rows')
    lines = ['## Восстановление отчёта: матрица покрытия', '',
             'Это scaffold, не новый замер. Исторические результаты не перенесены.',
             'Цель: 11 основных + 41 методический сценарий, N512/N4096.',
             'Python/C-вызовы считаются отдельно от времени; отсутствующее значение не равно нулю.',
             f"Коммит исходников: `{report['commit']}`", '']
    for n in SIZES:
        for api, title in MODES.items():
            lines += [f'### N={n}: {title}', '', '| Сценарий | Python | Классы | BSL |', '|---|---|---|---|']
            cases = load_manifest()['core'] + load_manifest()['method']
            index = {(r['case'], r['n'], r['layer']): r for r in report['rows']}
            for case in cases:
                states = [index[case, n, layer]['status'] for layer in ('python', 'classes', api)]
                labels = ['пропуск: квадратичный поиск' if state == 'skipped' else 'не восстановлен' for state in states]
                lines.append('| ' + case + ' | ' + ' | '.join(labels) + ' |')
            lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = scaffold(args.commit)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.output / 'coverage.md').write_text(render(report), encoding='utf-8')


if __name__ == '__main__':
    main()

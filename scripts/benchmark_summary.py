"""Render timing references, never apply a performance threshold."""
import json
import math
from pathlib import Path
import sys


def ratio_cell(value):
    """Use portable color indicators; GitHub strips inline cell styles."""
    indicator = "🟩" if value < 2 else "🟨" if value <= 3 else "🟧"
    return f"{indicator} {value:.2f}×"


def render(report):
    if report['schema'] != 'execution-layers-v1':
        raise ValueError('unsupported benchmark report')
    environment = report['environment']
    routes = {case['route'].get('requested_route', 'default') for case in report['cases']}
    title = 'Подготовленное исполнение (без времени подготовки)' if routes == {'prepared'} else 'Обычный публичный API (включает внутреннюю подготовку)'
    lines = ['## Сравнение производительности: ' + title, '',
             f"Коммит: `{environment['git_head']}`", '',
             '| Сценарий | Python, мс | Классы yadinassi, мс | Прямой BSL, мс | Классы / Python | BSL / Python | BSL / классы |',
             '|---|---:|---:|---:|---:|---:|---:|']
    if not report['cases']:
        raise ValueError('empty benchmark report')
    for case in report['cases']:
        if case['route']['backend'] != 'python-direct':
            raise ValueError('reference job must measure the direct backend')
        values = [case['summary'][layer]['median_seconds'] for layer in ('python', 'python_classes', 'bsl')]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError('invalid timing')
        native, classes, bsl = values
        name = case['case'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f'| {name} | {native*1000:.3f} | {classes*1000:.3f} | {bsl*1000:.3f} | {ratio_cell(classes/native)} | {ratio_cell(bsl/native)} | {ratio_cell(bsl/classes)} |')
    lines += ['', 'Индикаторы коэффициентов (до округления): 🟩 0 ≤ коэффициент < 2; 🟨 2 ≤ коэффициент ≤ 3; 🟧 коэффициент > 3. Ячейки времени не окрашиваются.', '', 'Коэффициенты сравнивают время: **меньше — быстрее**, Python = 1×. Порогов скорости нет; замедление само по себе не вызывает ошибку.', '',
              'Медианы полного времени выполнения; результат каждого вызова сверяется с ожидаемым Decimal. '
              'Подготовка и первое исполнение записаны отдельно в исходном JSON. '
              'API BSL указан ниже: execute_program включает выполняемую внутри него подготовку. '
              'Эти микротесты не измеряют всё приложение и не доказывают полную семантическую эквивалентность; общие машины CI дают шум.', '']
    names = {case['case'] for case in report['cases']}
    references = {case.get('python_reference') for case in report['cases']}
    if 'arithmetic.int' in names:
        lines += ['`arithmetic.int`: Python считает на `int` и один раз преобразует итог в `Decimal`; столбец классов использует числовые операции yadinassi на `Decimal`.', '']
    if 'native-int-arithmetic-v2' in references:
        lines += ['`arithmetic`: Python считает на `int` и преобразует только итог. По сравнению со старыми отчётами изменился референс Python, а не BSL-сценарий.', '']
    if 'int-counter-decimal-factor-v2' in references:
        lines += ['`arithmetic.fractional`: в референсе счётчик `int`, множитель `Decimal`; явного преобразования счётчика на каждом витке нет.', '']
    elif 'arithmetic.fractional' in names:
        lines += ['`arithmetic.fractional`: контроль с дробным множителем на `Decimal`.', '']
    lines += ['| Подготовка / первый вызов | Разбор + подготовка BSL, мс | Первое исполнение BSL, мс |', '|---|---:|---:|']
    for case in report['cases']:
        if 'preparation_seconds' in case:
            lines.append(f"| {case['case']} | {case['preparation_seconds']['bsl_parse_prepare']*1000:.3f} | {case['first_execution_seconds']['bsl']*1000:.3f} |")
    lines.append('')
    conditions = {}
    for case in report['cases']:
        # Group only identical execution conditions, never just matching rounded
        # round counts or similarly named APIs. Preserve first-occurrence order.
        key = (case['iterations'], len(case['samples']),
               case['route'].get('api', 'unknown'),
               case['route'].get('requested_route', 'default'), case['route']['backend'])
        conditions.setdefault(key, []).append(case['case'])
    for (iterations, sample_count, api, _, _backend), names in conditions.items():
        label = 'Все сценарии' if len(conditions) == 1 and len(names) > 1 else ', '.join(names)
        lines.append(f"- {label}: {iterations} итераций, {sample_count//3} измеренных повторов; `{api}`.")
    lines += ['', f"Python: `{environment['python'].splitlines()[0]}`", f"Процессор: `{environment['processor']}`", '',
              'Артефакт содержит все замеры полного и процессорного времени, хеши исходников, окружение, время подготовки и первого вызова.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    print(render(json.loads(Path(sys.argv[1]).read_text())), end='')

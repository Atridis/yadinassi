"""Assemble paired Russian Summary tables without changing measured reports."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.benchmark_summary import render as render_core
from scripts.benchmark_extended_layers import render as render_extended

INPUTS = (
    ('core', 'default', 'execution-layers.json', render_core),
    ('core', 'prepared', 'execution-layers-prepared.json', render_core),
    ('extended', 'default', 'extended-default.json', render_extended),
    ('extended', 'prepared', 'extended-prepared.json', render_extended),
)
MODES = {'default': 'с подготовкой', 'prepared': 'без подготовки'}
LEGEND = 'Индикаторы коэффициентов (до округления): 🟩 0 ≤ коэффициент < 2; 🟨 2 ≤ коэффициент ≤ 3; 🟧 коэффициент > 3. Ячейки времени не окрашиваются.'


def sections(text):
    """Split our renderer output into two tables and all retained explanations."""
    lines = text.splitlines()
    tables = []
    prose = []
    pos = 1  # The original title is replaced by the shared section title.
    while pos < len(lines):
        if lines[pos].startswith('|'):
            table = []
            while pos < len(lines) and lines[pos].startswith('|'):
                table.append(lines[pos]); pos += 1
            tables.append('\n'.join(table))
        else:
            if lines[pos] != LEGEND:
                prose.append(lines[pos])
            pos += 1
    if len(tables) != 2:
        raise ValueError('expected timing and preparation tables')
    return tables[0], tables[1], '\n'.join(prose).strip()


def compact_notes(lines):
    """Group identical case explanations, retaining distinct form operations."""
    groups = {}
    result = []
    form_marker = 'Настоящий жизненный цикл формы.'
    for line in lines:
        if not line.startswith('- **') or '**: ' not in line:
            result.append(line)
            continue
        name, body = line[4:].split('**: ', 1)
        if name in ('form.event', 'form.open') and form_marker in body:
            operation, shared = body.split(form_marker, 1)
            result.append('- **' + name + '**: ' + operation.strip())
            body = form_marker + shared
        groups.setdefault(body, []).append(name)
    for body, names in groups.items():
        result.append('- **' + ', '.join(names) + '**: ' + body)
    return result


def explanations(parts):
    """Factor only exact complete lines, scoped to the available mode(s)."""
    by_mode = {route: [line for line in part[2].splitlines() if line.strip()
                       and not line.startswith(('Коммит:', 'Python:', 'Процессор:'))]
               for route, part in parts.items() if part}
    if not by_mode:
        return []
    common = []
    if len(by_mode) == 2:
        common = [line for line in by_mode['default'] if line in by_mode['prepared']]
    lines = ['#### Пояснения', '']
    for line in compact_notes(list(dict.fromkeys(common))):
        lines += [line, '']
    for route, prose in by_mode.items():
        unique = [line for line in prose if line not in common]
        if unique:
            lines += ['**' + MODES[route] + ':**', '', *compact_notes(unique), '']
    return lines


def environment_lines(environments):
    """Never label differing or missing metadata as common environment."""
    if not environments:
        return []
    lines = ['### Окружение', '']
    keys = list(dict.fromkeys(key for env in environments.values() for key in env))
    labels = {'python': 'Python', 'processor': 'Процессор', 'platform': 'Платформа'}
    for key in keys:
        if key == 'git_head':
            continue
        groups = {}
        for scope, env in environments.items():
            token = json.dumps(env[key], ensure_ascii=False, sort_keys=True) if key in env else None
            groups.setdefault(token, []).append(scope)
        if len(groups) == 1 and key not in labels:
            continue  # Complete common metadata remains in the source JSON.
        for value, scopes in groups.items():
            scope = '' if len(scopes) == len(environments) else ' (' + '; '.join(scopes) + ')'
            lines += [labels.get(key, key) + scope + ': ' +
                      ('не указано' if value is None else '`' + value + '`'), '']
    lines += ['Полные метаданные каждого запуска сохранены в его JSON.', '']
    return lines


def assemble(reports):
    """Available reports are rendered independently, even if another failed."""
    rendered = {}
    errors = []
    commits = set()
    environments = {}
    for family, route, filename, renderer in INPUTS:
        report = reports.get(filename)
        if report is None:
            rendered[family, route] = None
            errors.append(filename)
            continue
        try:
            sha = report['environment']['git_head']
            if type(sha) is not str or not sha:
                raise ValueError('missing source commit')
            routes = {case['route'].get('requested_route', 'default') if family == 'core'
                      else case['requested_route'] for case in report['cases']}
            if routes != {route}:
                raise ValueError('report route does not match its label')
            rendered[family, route] = sections(renderer(report))
            commits.add(sha)
            scope = ('основные' if family == 'core' else 'расширенные') + ' / ' + MODES[route]
            environments[scope] = report['environment']
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            rendered[family, route] = None
            errors.append(filename)
    if len(commits) > 1:
        raise ValueError('reports have different source commits')
    lines = ['## Сравнение производительности', '', LEGEND, '',
             '**с подготовкой** — execute_program(preparsed_ast), включая выполняемую внутри него подготовку; '
             'предварительный разбор исходного BSL в AST не входит в это время. '
             '**без подготовки** — execute_prepared(plan), с подготовкой плана до измерения. '
             'Оба режима измеряются после проверочных вызовов и прогрева. '
             'Сценарии form.event и form.open используют отдельный жизненный цикл FormSession, '
             'а не эти API; они остаются только в первой расширенной таблице.', '']
    if commits:
        lines += ['Коммит: `' + next(iter(commits)) + '`', '']
    lines += environment_lines(environments)
    for family, title in (('core', 'Основные сценарии'), ('extended', 'Расширенные сценарии')):
        lines += ['### ' + title, '']
        for route in ('default', 'prepared'):
            lines += ['#### ' + MODES[route], '']
            part = rendered[family, route]
            lines += [part[0] if part else 'Результат не получен или некорректен. См. шаг с ошибкой; отсутствие результата не означает нулевое время.', '']
        lines += ['#### Подготовка и первый вызов', '']
        for route in ('default', 'prepared'):
            part = rendered[family, route]
            if part:
                lines += ['**' + MODES[route] + '**', '', part[1], '']
        lines += explanations({route: rendered[family, route] for route in ('default', 'prepared')})
    if errors:
        lines += ['**Неполный отчёт.** Недоступные или некорректные файлы: '
                  + ', '.join('`' + name + '`' for name in errors) + '.', '']
    return '\n'.join(lines), errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    reports = {}
    for _, _, name, _ in INPUTS:
        try:
            reports[name] = json.loads((args.directory / name).read_text())
        except (OSError, ValueError):
            reports[name] = None
    try:
        text, errors = assemble(reports)
    except ValueError:
        text = '## Сравнение производительности\n\n**Неполный отчёт.** Файлы относятся к разным коммитам; объединение остановлено.\n'
        errors = list(reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='utf-8')
    # stdout is always available to GITHUB_STEP_SUMMARY, including partial failure.
    print(text, end='')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Lossy, allowlisted failure diagnostics. Never return native text or paths."""
from __future__ import annotations

import json
from pathlib import Path
import re

CATEGORIES = frozenset({'none', 'unknown', 'compile_error', 'runtime_error',
                       'unsupported_api', 'permission_denied', 'authentication_failed',
                       'license_unavailable', 'training_restriction', 'startup_failed',
                       'evidence_invalid', 'conflicting_evidence'})
ORIGINS = frozenset({'none', 'native_log', 'session_marker', 'managed_marker'})
MARKER_STATES = frozenset({'not_checked', 'absent', 'invalid', 'ok', 'error'})
# Must match the unchanged trusted BSL sources; tests verify these exact limits.
SOURCE_LINE_LIMITS = {'SessionModule': 144, 'ManagedApplicationModule': 83}
MODULE_ALIASES = {'МодульСеанса': 'SessionModule', 'SessionModule': 'SessionModule',
                  'МодульУправляемогоПриложения': 'ManagedApplicationModule',
                  'ManagedApplicationModule': 'ManagedApplicationModule'}
IDENTIFIERS = frozenset({
    'ЗащитаОтОпасныхДействий', 'АутентификацияСтандартная',
    'ПользователиИнформационнойБазы', 'ПолучитьПользователей', 'ТекущийПользователь',
    'СоздатьПользователя', 'НайтиПоИмени', 'Записать', 'Роли', 'Количество',
    'Имя', 'ПолноеИмя', 'ТипЗнч', 'Тип', 'СистемнаяИнформация', 'ВерсияПриложения',
    'ЧтениеJSON', 'ЗаписьJSON', 'ОткрытьФайл', 'ПрочитатьJSON', 'ЗаписатьJSON',
    'Закрыть', 'Файл', 'Существует', 'ПараметрЗапуска', 'УстановкаПараметровСеанса',
    'ПриНачалеРаботыСистемы', 'ЗавершитьРаботуСистемы', 'NativeПрочитатьJSON',
    'NativeЗаписатьJSON', 'NativeПроверитьПользователя', 'ПодробноеПредставлениеОшибки',
    'ИнформацияОбОшибке', 'Структура', 'Вставить', 'ПустаяСтрока',
})
PHRASES = {
    'compile_error': ('ошибка компиляции', 'ошибки компиляции', 'compilation error',
                      'syntax error', 'синтаксическая ошибка', 'переменная не определена',
                      'variable is not defined', 'variable not defined',
                      'процедура или функция с указанным именем не определена',
                      'procedure or function with the specified name is not defined'),
    'unsupported_api': ('поле объекта не обнаружено', 'метод объекта не обнаружен',
                        'object field not found', 'object method not found'),
    'permission_denied': ('недостаточно прав', 'нарушение прав доступа',
                          'insufficient rights', 'access denied', 'permission denied'),
    'authentication_failed': ('ошибка аутентификации', 'неверное имя пользователя или пароль',
                              'authentication failed', 'invalid user name or password'),
    'license_unavailable': ('не обнаружен ключ защиты', 'не найдена лицензия',
                            'лицензия не обнаружена', 'no license found',
                            'license not found', 'license acquisition failed'),
    'training_restriction': ('ограничение учебной версии', 'ограничения учебной версии',
                             'training version restriction', 'training version limitation'),
    'startup_failed': ('ошибка запуска приложения', 'ошибка при запуске приложения',
                       'application startup error', 'application startup failed'),
    'runtime_error': ('ошибка при вызове метода контекста', 'ошибка выполнения',
                      'error calling context method', 'runtime error'),
}
IDENTIFIER_PATTERNS = (
    r'(?:поле объекта не обнаружено|метод объекта не обнаружен|переменная не определена|'
    r'процедура или функция с указанным именем не определена|object field not found|'
    r'object method not found|variable(?: is)? not defined|'
    r'procedure or function with the specified name is not defined)\s*\(([^()\r\n]{1,96})\)',
    r'<\?>\s*([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]{0,95})',
)
LOCATION_PATTERN = re.compile(r'\{(' + '|'.join(map(re.escape, MODULE_ALIASES)) +
                              r')\(([0-9]{1,4})(?:,\s*[0-9]{1,4})?\)\}')


def empty_diagnostics() -> dict:
    return {'category': 'none', 'origin': 'none', 'module': None, 'line': None,
            'identifier': None, 'native_exit_code': None,
            'session_marker': 'not_checked', 'managed_marker': 'not_checked'}


def bounded_exit_code(value: object) -> int | None:
    return value if type(value) is int and -64 <= value <= 255 and value != 0 else None


def validate_diagnostics(value: object, *, success: bool = False, primary_kind: str | None = None) -> dict:
    if type(value) is not dict or set(value) != set(empty_diagnostics()):
        raise ValueError('diagnostic keys')
    for key, allowed in (('category', CATEGORIES), ('origin', ORIGINS),
                         ('session_marker', MARKER_STATES), ('managed_marker', MARKER_STATES)):
        if type(value[key]) is not str or value[key] not in allowed:
            raise ValueError('diagnostic enum')
    code = value['native_exit_code']
    if code is not None and (bounded_exit_code(code) is None or primary_kind != 'process_failed'):
        raise ValueError('diagnostic exit code')
    module, line, identifier = value['module'], value['line'], value['identifier']
    if module is None:
        if line is not None:
            raise ValueError('line without module')
    elif (type(module) is not str or module not in SOURCE_LINE_LIMITS
          or type(line) is not int or not 1 <= line <= SOURCE_LINE_LIMITS[module]):
        raise ValueError('diagnostic location')
    if identifier is not None and (type(identifier) is not str or identifier not in IDENTIFIERS):
        raise ValueError('diagnostic identifier')
    if value['origin'] == 'none' and any(item is not None for item in (module, line, identifier)):
        raise ValueError('diagnostic provenance')
    if value['category'] not in {'none', 'unknown', 'evidence_invalid', 'conflicting_evidence'} and value['origin'] == 'none':
        raise ValueError('unobserved diagnostic category')
    if value['category'] in {'none', 'evidence_invalid', 'conflicting_evidence'} and value['origin'] != 'none':
        raise ValueError('diagnostic category provenance')
    if value['origin'].endswith('_marker') and value[value['origin']] != 'error':
        raise ValueError('diagnostic marker provenance')
    if value['category'] == 'none' and value != empty_diagnostics():
        raise ValueError('nonempty absent diagnostics')
    if primary_kind == 'stale_evidence' and value != empty_diagnostics():
        raise ValueError('diagnostics from stale evidence')
    if success and value != empty_diagnostics():
        raise ValueError('diagnostics on success')
    return value


def bounded_file(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('unavailable diagnostic input')
    with path.open('rb') as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError('excessive diagnostic input')
    return data


def native_text(data: bytes) -> str:
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    if data.startswith(b'\xef\xbb\xbf'):
        return data.decode('utf-8-sig')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('cp1251')


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate marker key')
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError('nonfinite marker constant')


def marker_error(path: Path, stage: str, hook: str, manifest: dict) -> tuple[str, str | None]:
    try:
        if not path.exists() and not path.is_symlink():
            return 'absent', None
        value = json.loads(bounded_file(path, 65536).decode('utf-8-sig'),
                           object_pairs_hook=unique_pairs, parse_constant=reject_constant)
        if type(value) is not dict:
            raise ValueError('marker object')
        expected = {'protocol': 'native-bootstrap-v1', 'run_id': manifest['run_id'],
                    'stage': stage, 'hook': hook, 'user': manifest['user']}
        if any(type(value.get(key)) is not str or value[key] != item for key, item in expected.items()):
            raise ValueError('marker identity')
        if type(value.get('status')) is not str or value['status'] not in {'error', 'ok'}:
            raise ValueError('marker status')
        if type(value.get('error')) is not str:
            raise ValueError('marker error')
        if value['status'] == 'ok':
            return ('ok', None) if value['error'] == '' else ('invalid', None)
        return 'error', value['error']
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        return 'invalid', None


def summarize_text(text: str) -> dict:
    lowered = text.casefold()
    categories = [key for key, phrases in PHRASES.items() if any(phrase in lowered for phrase in phrases)]
    # Generic context/runtime wrappers do not conflict with a more specific cause.
    specific = set(categories) - {'runtime_error', 'startup_failed'}
    category = next(iter(specific)) if len(specific) == 1 else 'conflicting_evidence' if len(specific) > 1 else categories[0] if categories else 'unknown'
    # A location or identifier must belong to the SAME diagnostic line as
    # the chosen category, not an unrelated stack frame elsewhere in the text.
    relevant = [line for line in text.splitlines()
                if category == 'unknown' or any(phrase in line.casefold()
                                               for phrase in PHRASES.get(category, ()))]
    details = set()
    for record in relevant:
        locations = {(MODULE_ALIASES[match[1]], int(match[2])) for match in LOCATION_PATTERN.finditer(record)
                     if 1 <= int(match[2]) <= SOURCE_LINE_LIMITS[MODULE_ALIASES[match[1]]]}
        frames = re.findall(r'\{[^{}\r\n]{1,200}\([0-9]{1,4}(?:,\s*[0-9]{1,4})?\)\}', record)
        module, line = next(iter(locations)) if len(locations) == 1 and len(frames) == 1 else (None, None)
        identifiers = {match.group(1).strip() for pattern in IDENTIFIER_PATTERNS
                       for match in re.finditer(pattern, record, re.I)
                       if match.group(1).strip() in IDENTIFIERS}
        # The source-pointer form is accepted only on a recognized error line.
        identifier = next(iter(identifiers)) if len(identifiers) == 1 and category != 'unknown' else None
        if module is not None or identifier is not None or frames:
            details.add((module, line, identifier))
    module, line, identifier = next(iter(details)) if len(details) == 1 else (None, None, None)
    if category == 'conflicting_evidence':
        module, line, identifier = None, None, None
    return {'category': category, 'module': module, 'line': line, 'identifier': identifier}


def stage_logs(evidence: Path, stage: str) -> list[Path]:
    if stage in {'load', 'redump', 'bootstrap', 'named_designer', 'verify'}:
        return [evidence / (stage + '.log'), evidence / (stage + '-console.log')]
    if stage == 'launcher_build':
        return [evidence / 'Launcher.designer.log', evidence / 'Launcher.designer-console.log']
    if stage == 'simple_epf':
        case = evidence / 'simple-case'
        names = ('enterprise.log', 'enterprise-console.log') if (case / 'enterprise-console.log').exists() else ('TestModule.designer.log', 'TestModule.designer-console.log')
        return [case / name for name in names]
    return []


def collect_diagnostics(evidence: Path, stage: str, manifest: dict | None,
                        exit_code: object = None) -> dict:
    result = empty_diagnostics()
    result.update(category='unknown', native_exit_code=bounded_exit_code(exit_code))
    candidates = []
    try:
        if stage in {'bootstrap', 'verify'} and manifest is not None:
            for hook in ('session', 'managed'):
                state, text = marker_error(evidence / (stage + '-' + hook + '.json'), stage, hook, manifest)
                result[hook + '_marker'] = state
                if text:
                    candidates.append((hook + '_marker', summarize_text(text)))
        for path in stage_logs(evidence, stage):
            try:
                candidates.append(('native_log', summarize_text(native_text(bounded_file(path, 1_048_576)))))
            except (OSError, ValueError, UnicodeError, RecursionError):
                continue
        # Only exact finite candidates survive. Conflicting specific categories
        # are reported as conflict; marker text is preferred only when consistent.
        meaningful = [(origin, item) for origin, item in candidates if item['category'] != 'unknown']
        categories = {item['category'] for _, item in meaningful} - {'runtime_error', 'startup_failed'}
        if 'conflicting_evidence' in categories or len(categories) > 1:
            result['category'] = 'conflicting_evidence'
        elif meaningful:
            choices = [(origin, item) for origin, item in meaningful if not categories or item['category'] in categories]
            origin, item = choices[0]
            result.update(item, origin=origin)
            detail_sets = {(candidate['module'], candidate['line'], candidate['identifier'])
                           for _, candidate in choices
                           if any(candidate[key] is not None for key in ('module', 'line', 'identifier'))}
            if len(detail_sets) > 1:
                result.update(module=None, line=None, identifier=None)
        elif any(item['module'] is not None or item['identifier'] is not None for _, item in candidates):
            origin, item = next((origin, item) for origin, item in candidates if item['module'] is not None or item['identifier'] is not None)
            result.update(item, origin=origin)
            detail_sets = {(candidate['module'], candidate['line'], candidate['identifier'])
                           for _, candidate in candidates
                           if any(candidate[key] is not None for key in ('module', 'line', 'identifier'))}
            if len(detail_sets) > 1:
                result.update(module=None, line=None, identifier=None)
        elif 'invalid' in (result['session_marker'], result['managed_marker']):
            result['category'] = 'evidence_invalid'
        validate_diagnostics(result, primary_kind='process_failed' if result['native_exit_code'] is not None else None)
        return result
    except Exception:
        # Diagnostic parsing can never replace the real failure or security state.
        fallback = empty_diagnostics()
        fallback.update(category='evidence_invalid', native_exit_code=bounded_exit_code(exit_code))
        return fallback

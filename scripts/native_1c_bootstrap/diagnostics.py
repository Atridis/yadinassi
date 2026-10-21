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
# Must match the trusted BSL sources; tests verify these exact limits.
SOURCE_LINE_LIMITS = {'SessionModule': 187, 'ManagedApplicationModule': 89}
MODULE_ALIASES = {'МодульСеанса': 'SessionModule', 'SessionModule': 'SessionModule',
                  'МодульУправляемогоПриложения': 'ManagedApplicationModule',
                  'ManagedApplicationModule': 'ManagedApplicationModule'}
IDENTIFIERS = frozenset({
    'ЗащитаОтОпасныхДействий', 'ОписаниеЗащитыОтОпасныхДействий',
    'ПредупреждатьОбОпасныхДействиях', 'АутентификацияСтандартная',
    'ПользователиИнформационнойБазы', 'ПолучитьПользователей', 'ТекущийПользователь',
    'СоздатьПользователя', 'НайтиПоИмени', 'Записать', 'Роли', 'Количество',
    'Имя', 'ПолноеИмя', 'ТипЗнч', 'Тип', 'СистемнаяИнформация', 'ВерсияПриложения',
    'ЧтениеJSON', 'ЗаписьJSON', 'ОткрытьФайл', 'ПрочитатьJSON', 'ЗаписатьJSON',
    'Закрыть', 'Файл', 'Существует', 'ПараметрЗапуска', 'УстановкаПараметровСеанса',
    'ПриНачалеРаботыСистемы', 'ЗавершитьРаботуСистемы', 'NativeПрочитатьJSON',
    'NativeЗаписатьJSON', 'NativeПроверитьПользователя', 'NativeТипЗащиты',
    'NativeНаблюдатьЗащиту', 'ПодробноеПредставлениеОшибки',
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
CONTEXT_IDENTIFIER_PATTERN = re.compile(
    r'(?:ошибка при вызове метода контекста|error calling context method)\s*\(([^()\r\n]{1,96})\)', re.I)
CONTEXT_IDENTIFIER_ALIASES = {'Write': 'Записать'}
MAX_SOURCE_FRAMES = 4
LOCATION_PATTERN = re.compile(r'\{(' + '|'.join(map(re.escape, MODULE_ALIASES)) +
                              r')\(([0-9]{1,4})(?:,\s*[0-9]{1,4})?\)\}')


# Exact reviewed-language vocabulary. No stemming or arbitrary source tokens.
CONTEXT_WORDS = {
    'not': "not|не|ни|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|hasn't|haven't|hadn't|won't|wouldn't|shouldn't|mustn't|needn't",
    'no': 'no|нет',
    'without': 'without|без',
    'cannot': "cannot|can't|couldn't|нельзя|невозможно|невозможен|невозможна",
    'must': 'must|должен|должна|должно|должны|необходимо',
    'required': 'required|requires|require|требуется|требуются|требует|необходим|необходима|необходимы|обязательно',
    'forbidden': 'forbidden|prohibited|запрещено|запрещен|запрещена',
    'allowed': 'allowed|permitted|разрешено|разрешен|разрешена',
    'only': 'only|только',
    'at_least': 'at least|хотя бы|как минимум',
    'one': 'one|один|одна|одно|одного|одной|одним|одному',
    'first': 'first|первый|первая|первого|первой|первым',
    'last': 'last|последний|последняя|последнего|последней|последним',
    'all': 'all|все|всех|всеми',
    'none': 'none|ни одного',
    'empty': 'empty|пустой|пустая|пустое|пустым|пустого',
    'has': 'has|have|having|имеет|имеют|имеющего|имеющий|имеющими|имеющих',
    'user': 'user|users|пользователь|пользователя|пользователю|пользователем|пользователи|пользователей|пользователями|пользователе',
    'infobase': 'infobase|информационная база|информационной базы|информационной базе|информационную базу',
    'role': 'role|roles|роль|роли|ролью|ролей|ролями',
    'administrative': 'administrative|административный|административная|административные|административных|административными|административного|административным',
    'administration': 'administration|администрирование|администрирования|администрированием',
    'administrator': 'administrator|administrators|администратор|администратора|администратору|администратором|администраторов',
    'rights': 'right|rights|права|прав|правами|право',
    'configuration': 'configuration|конфигурация|конфигурации|конфигурацию',
    'designer': 'designer|конфигуратор|конфигуратора|конфигураторе',
    'enterprise': 'enterprise|предприятие|предприятия',
    'authentication': 'authentication|аутентификация|аутентификации|аутентификацию|аутентификацией',
    'standard': 'standard|стандартная|стандартной|стандартную|стандартный',
    'operating_system': 'operating system|операционная система|операционной системы|операционной системой',
    'password': 'password|passwords|пароль|пароля|паролю|паролем|пароли|паролей',
    'length': 'length|длина|длины|длине|длину',
    'complexity': 'complexity|сложность|сложности',
    'reuse': 'reuse|reused|повторное использование|повторного использования',
    'compromised': 'compromised|скомпрометирован|скомпрометированного|скомпрометированный',
    'protection': 'protection|защита|защиты|защиту|защитой',
    'dangerous': 'dangerous|опасные|опасных|опасными',
    'actions': 'action|actions|действие|действия|действий|действиями',
    'transaction': 'transaction|transactions|транзакция|транзакции|транзакцию|транзакций',
    'active': 'active|активная|активной|активную|активный',
    'read_only': 'read-only|read only|только для чтения',
    'license': 'license|licence|licenses|лицензия|лицензии|лицензию|лицензий',
    'duplicate': 'duplicate|дублируется|дублирование|дублирования',
    'exists': 'exists|exist|existing|существует|существуют|существующий|существующего',
    'missing': 'missing|absent|отсутствует|отсутствуют|отсутствие|отсутствия',
    'assigned': 'assigned|назначен|назначена|назначены|назначенных',
    'write': 'write|writing|written|записать|записи|запись|записан|записана',
    'create': 'create|creating|created|создать|создание|создания|создан|создана|создании',
    'delete': 'delete|deleting|deleted|удалить|удаление|удаления|удален|удалена',
    'modify': 'modify|change|changing|изменить|изменение|изменения|изменен|изменена',
    'access': 'access|доступ|доступа|доступом',
    'insufficient': 'insufficient|недостаточно|недостаточный|недостаточными',
    'enabled': 'enabled|включен|включена|включено',
    'disabled': 'disabled|выключен|выключена|отключен|отключена|отключено',
    'unavailable': 'unavailable|недоступен|недоступна|недоступно',
    'error': 'error|ошибка|ошибки|ошибке',
    'save': 'save|saving|saved|сохранить|сохранение|сохранения|сохранен|сохранена',
}

MAX_CONTEXT_TOKENS = 64
CONTEXT_SENTINELS = frozenset({'unknown', 'redacted', 'line_break', 'sentence_end', 'clause_break'})
CONTEXT_TOKENS = frozenset(CONTEXT_WORDS) | CONTEXT_SENTINELS
CONTEXT_LITERALS = {literal: token for token, words in CONTEXT_WORDS.items()
                    for literal in words.split('|')}
# Opaque values are masked BEFORE vocabulary matching. Neither their contents
# nor their lengths are returned. Unknown unquoted words are also never returned.
CONTEXT_OPAQUE = re.compile(
    # Sensitive field labels consume the whole line, including punctuation in
    # the value. This intentionally overredacts technical-looking secret text.
    r'(?<![\w.-])(?:password|passwd|pwd|passphrase|token|access[ _-]?token|'
    r'refresh[ _-]?token|secret|client[ _-]?secret|credentials?|api[ _-]?key|'
    r'authorization|cookie|пароль|токен|секрет|уч[её]тные[ \t]+данные|ключ[ \t]+api)'
    r'[ \t]*[:=][^\r\n]*|(?<!\w)(?:bearer|basic)[ \t]+[^\r\n]*|'
    r'"(?:\\.|[^"\\])*(?:"|$)|'
    r"(?<!\w)'(?:\\.|[^'\\])*(?:'|$)|"
    r'(?<!\w)’[^’]*(?:’|$)|`[^`]*(?:`|$)|«[^»]*(?:»|$)|“[^”]*(?:”|$)|‘[^’]*(?:’|$)|'
    r'\{[^{}\r\n]*\}|'
    r'(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*://[^\s]+|(?<![^\s<>"\x27])[^\s<>"\x27@]+@[^\s<>"\x27]+|'
    r'\b(?:user\s+name|username|name|user|имя\s+пользователя|имя|пользователь|'
    r'database|infobase|база)\s*:\s*[^,;\r\n]+|'
    r'\b\w+\s*=\s*[^,;\r\n]+|'
    r'(?:[A-Za-z]:[\\/]|\\\\|(?:\.{1,2}|~)/|/)[^\s,;]+|'
    r'(?<![\w.-])[\w.-]+[/\\][^\s,;]+|(?<![\w.])\w+(?:\.\w+)+', re.I)
CONTEXT_LEXEMES = re.compile(r"\r\n|\r|\n|[^\W]+(?:[-'’][^\W]+)*|[^\s]", re.UNICODE)


def empty_rendered_context() -> dict:
    return {'origin': 'none', 'representation': 'none', 'head': [], 'tail': [],
            'omitted_middle': False}


def validate_rendered_context(value: object, markers: dict) -> dict:
    if type(value) is not dict or set(value) != set(empty_rendered_context()):
        raise ValueError('rendered context keys')
    if value == empty_rendered_context():
        # Equality alone would accept 0 as False; check this even for empty form.
        if type(value['omitted_middle']) is not bool:
            raise ValueError('rendered context omission')
        return value
    if (type(value['origin']) is not str or value['origin'] not in {'session_marker', 'managed_marker'}
            or markers[value['origin']] != 'error'
            or value['representation'] != 'detailed_error_text'
            or type(value['omitted_middle']) is not bool):
        raise ValueError('rendered context provenance')
    for key in ('head', 'tail'):
        if (type(value[key]) is not list or len(value[key]) > MAX_CONTEXT_TOKENS
                or any(type(token) is not str or token not in CONTEXT_TOKENS for token in value[key])):
            raise ValueError('rendered context vocabulary')
    if value['omitted_middle']:
        if len(value['head']) != MAX_CONTEXT_TOKENS // 2 or len(value['tail']) != MAX_CONTEXT_TOKENS // 2:
            raise ValueError('rendered context truncated shape')
    elif not value['head'] or value['tail']:
        raise ValueError('rendered context full shape')
    return value


def rendered_context(text: str, origin: str) -> dict:
    """Project complete bounded private text, NOT an ErrorInfo.Cause hierarchy."""
    if not text.strip():
        return empty_rendered_context()
    pieces = []
    start = 0
    for match in CONTEXT_OPAQUE.finditer(text):
        pieces.extend(CONTEXT_LEXEMES.findall(text[start:match.start()].casefold()))
        pieces.append(None)  # Internal opaque sentinel; never parse its contents.
        start = match.end()
    pieces.extend(CONTEXT_LEXEMES.findall(text[start:].casefold()))
    tokens = []
    index = 0
    while index < len(pieces):
        piece = pieces[index]
        consumed = 1
        if piece is None:
            token = 'redacted'
        elif piece in {'\r', '\n', '\r\n'}:
            token = 'line_break'
        elif piece in {'.', '!', '?'}:
            token = 'sentence_end'
        elif piece in {',', ';', ':'}:
            token = 'clause_break'
        else:
            token = 'unknown'
            for width in (3, 2, 1):
                parts = pieces[index:index + width]
                if len(parts) == width and all(type(part) is str for part in parts):
                    literal = ' '.join(parts).replace('’', "'")
                    if literal in CONTEXT_LITERALS:
                        token, consumed = CONTEXT_LITERALS[literal], width
                        break
        if token not in {'unknown', 'redacted'} or not tokens or tokens[-1] != token:
            tokens.append(token)
        index += consumed
    omitted = len(tokens) > MAX_CONTEXT_TOKENS
    return {'origin': origin, 'representation': 'detailed_error_text',
            'head': tokens[:MAX_CONTEXT_TOKENS // 2] if omitted else tokens,
            'tail': tokens[-MAX_CONTEXT_TOKENS // 2:] if omitted else [],
            'omitted_middle': omitted}


def empty_diagnostics() -> dict:
    return {'category': 'none', 'origin': 'none', 'module': None, 'line': None,
            'identifier': None, 'native_exit_code': None,
            'source_frames': [], 'source_frames_truncated': False,
            'rendered_context': empty_rendered_context(),
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
    validate_rendered_context(value['rendered_context'], value)
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
    frames = value['source_frames']
    if type(frames) is not list or len(frames) > MAX_SOURCE_FRAMES or type(value['source_frames_truncated']) is not bool:
        raise ValueError('diagnostic source frames')
    seen = set()
    for frame in frames:
        if (type(frame) is not dict or set(frame) != {'module', 'line'}
                or type(frame['module']) is not str or frame['module'] not in SOURCE_LINE_LIMITS
                or type(frame['line']) is not int or not 1 <= frame['line'] <= SOURCE_LINE_LIMITS[frame['module']]):
            raise ValueError('diagnostic source frame')
        key = (frame['module'], frame['line'])
        if key in seen:
            raise ValueError('duplicate diagnostic source frame')
        seen.add(key)
    if value['source_frames_truncated'] and len(frames) != MAX_SOURCE_FRAMES:
        raise ValueError('diagnostic frame truncation')
    if value['origin'] == 'none' and frames:
        raise ValueError('unobserved diagnostic source frames')
    if module is not None and not value['source_frames_truncated'] and (module, line) not in seen:
        raise ValueError('single location absent from source frames')
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


def matching_marker(path: Path, stage: str, hook: str, manifest: dict) -> dict:
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
    if type(value.get('error')) is not str or (value['status'] == 'ok' and value['error'] != ''):
        raise ValueError('marker error')
    return value


def marker_error(path: Path, stage: str, hook: str, manifest: dict) -> tuple[str, str | None]:
    try:
        if not path.exists() and not path.is_symlink():
            return 'absent', None
        value = matching_marker(path, stage, hook, manifest)
        return value['status'], value['error'] if value['status'] == 'error' else None
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        return 'invalid', None


PROTECTION_TYPES = frozenset({'not_observed', 'UnsafeOperationProtectionDescription',
                              'Boolean', 'Undefined', 'other'})


def empty_protection_observation() -> dict:
    return {'stage': None, 'property_type': 'not_observed', 'warning_type': 'not_observed'}


def validate_protection_observation(value: object) -> dict:
    if type(value) is not dict or set(value) != set(empty_protection_observation()):
        raise ValueError('protection observation keys')
    for key in ('property_type', 'warning_type'):
        if type(value[key]) is not str or value[key] not in PROTECTION_TYPES:
            raise ValueError('protection observation type')
    if value['stage'] is None:
        if value != empty_protection_observation():
            raise ValueError('protection observation without stage')
    elif type(value['stage']) is not str or value['stage'] not in {'bootstrap', 'verify'}:
        raise ValueError('protection observation stage')
    elif value['property_type'] == 'not_observed':
        raise ValueError('protection observation without property')
    if (value['property_type'] != 'UnsafeOperationProtectionDescription'
            and value['warning_type'] != 'not_observed'):
        raise ValueError('warning observation without descriptor')
    return value


def collect_protection_observation(evidence: Path, stage: str, manifest: dict) -> dict:
    try:
        if stage not in {'bootstrap', 'verify'}:
            raise ValueError('protection observation stage')
        marker = matching_marker(evidence / (stage + '-session.json'), stage, 'session', manifest)
        result = {'stage': stage, 'property_type': marker.get('observed_protection_type'),
                  'warning_type': marker.get('observed_warning_type')}
        return validate_protection_observation(result)
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        return empty_protection_observation()


def source_frames(text: str) -> tuple[list[dict], bool]:
    # Preserve first-observed stack order, not a guessed error/call hierarchy.
    seen = set()
    frames = []
    for match in LOCATION_PATTERN.finditer(text):
        module, line = MODULE_ALIASES[match[1]], int(match[2])
        if not 1 <= line <= SOURCE_LINE_LIMITS[module] or (module, line) in seen:
            continue
        seen.add((module, line))
        if len(frames) == MAX_SOURCE_FRAMES:
            return frames, True
        frames.append({'module': module, 'line': line})
    return frames, False


def summarize_text(text: str) -> dict:
    lowered = text.casefold()
    categories = [key for key, phrases in PHRASES.items() if any(phrase in lowered for phrase in phrases)]
    # Generic context/runtime wrappers do not conflict with a more specific cause.
    specific = set(categories) - {'runtime_error', 'startup_failed'}
    category = next(iter(specific)) if len(specific) == 1 else 'conflicting_evidence' if len(specific) > 1 else categories[0] if categories else 'unknown'
    # A single location or source-pointer identifier belongs to a category
    # line, not an unrelated stack frame. Known context-method wrappers are
    # separately accepted elsewhere in this same source below.
    relevant = [line for line in text.splitlines()
                if category == 'unknown' or any(phrase in line.casefold()
                                               for phrase in PHRASES.get(category, ()))]
    details = set()
    observed_identifiers = set()
    unrecognized_context = False
    # A known context method can wrap a more specific cause on another line
    # of this same source. Retain it without reclassifying that underlying cause.
    for record in text.splitlines():
        for match in CONTEXT_IDENTIFIER_PATTERN.finditer(record):
            token = match.group(1).strip()
            token = CONTEXT_IDENTIFIER_ALIASES.get(token, token)
            if token in IDENTIFIERS:
                observed_identifiers.add(token)
            else:
                # Preserve ambiguity as a finite sentinel, never the unknown token.
                unrecognized_context = True
    for record in relevant:
        locations = {(MODULE_ALIASES[match[1]], int(match[2])) for match in LOCATION_PATTERN.finditer(record)
                     if 1 <= int(match[2]) <= SOURCE_LINE_LIMITS[MODULE_ALIASES[match[1]]]}
        frames = re.findall(r'\{[^{}\r\n]{1,200}\([0-9]{1,4}(?:,\s*[0-9]{1,4})?\)\}', record)
        module, line = next(iter(locations)) if len(locations) == 1 and len(frames) == 1 else (None, None)
        identifiers = {match.group(1).strip() for pattern in IDENTIFIER_PATTERNS
                       for match in re.finditer(pattern, record, re.I)
                       if match.group(1).strip() in IDENTIFIERS}
        for match in CONTEXT_IDENTIFIER_PATTERN.finditer(record):
            token = match.group(1).strip()
            token = CONTEXT_IDENTIFIER_ALIASES.get(token, token)
            if token in IDENTIFIERS:
                identifiers.add(token)
        # The source-pointer form is accepted only on a recognized error line.
        if category != 'unknown':
            observed_identifiers.update(identifiers)
        identifier = next(iter(identifiers)) if len(identifiers) == 1 and category != 'unknown' else None
        if module is not None or identifier is not None or frames:
            details.add((module, line, identifier))
    module, line, identifier = next(iter(details)) if len(details) == 1 else (None, None, None)
    identifier = next(iter(observed_identifiers)) if len(observed_identifiers) == 1 and not unrecognized_context else None
    frames, truncated = source_frames(text)
    if category == 'conflicting_evidence':
        module, line, identifier = None, None, None
        frames, truncated = [], False
    return {'category': category, 'module': module, 'line': line, 'identifier': identifier,
            'source_frames': frames, 'source_frames_truncated': truncated,
            '_identifier_candidates': sorted(observed_identifiers) + ([None] if unrecognized_context else [])}


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
                    if result['rendered_context']['origin'] == 'none':
                        result['rendered_context'] = rendered_context(text, hook + '_marker')
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
            result.update({key: value for key, value in item.items() if key != '_identifier_candidates'}, origin=origin)
            detail_sets = {(candidate['module'], candidate['line'], candidate['identifier'])
                           for _, candidate in choices
                           if any(candidate[key] is not None for key in ('module', 'line', 'identifier'))}
            if len(detail_sets) > 1:
                result.update(module=None, line=None)
            identifiers = {identifier for _, candidate in choices for identifier in candidate['_identifier_candidates']}
            result['identifier'] = item['identifier'] if identifiers == {item['identifier']} else None
        elif any(item['module'] is not None or item['identifier'] is not None or item['source_frames'] for _, item in candidates):
            origin, item = next((origin, item) for origin, item in candidates if item['module'] is not None or item['identifier'] is not None or item['source_frames'])
            result.update({key: value for key, value in item.items() if key != '_identifier_candidates'}, origin=origin)
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

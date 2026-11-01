"""Bounded Data hashing family measurement wire grammar; no native expected semantic values."""
import re

SOURCE_SHA256 = 'cdc0e9ea099a9b967bb2e30e599f22f7008fb7f1565b62916c08b717f06e3983'
CASE_COUNT = 40
MAX_STRING_UNITS = 40
MAX_OUTPUT_BYTES = 8192
CALIBRATION = b'HF-C1: [S0:]\nHF-C2: [S6:004100a0003b0022d83dde00]\n'
# Fixed ASCII label/framing + maximum two-digit length + four hex digits per unit.
MAX_RECORD_BYTES = len(b'HF-00: [ok|S40:') + MAX_STRING_UNITS * 4 + len(b']\n')
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES
SOURCE_LINE_COUNT = 89
MAX_FAILURE_DIAGNOSTIC_BYTES = 16384
RESULT_FAILURE_CATEGORIES = frozenset(('result_json', 'result_shape', 'result_error',
                                     'result_encoding', 'result_limit'))
RESULT_ERROR_KINDS = frozenset(('identifier', 'function', 'type', 'method',
                                'syntax', 'module', 'other'))
# This dictionary is fixed public source/error vocabulary, NEVER learned from a
# run. IDs (not input text) cross the failure-only boundary; 0 means redacted.
PUBLIC_SOURCE_IDENTIFIERS = (
    'DataHashing', 'HashFunction', 'CRC32', 'MD5', 'SHA1', 'SHA256', 'SHA512',
    'Append', 'AppendFile', 'HashSum', 'HFEncode', 'HFKey', 'HFAlgorithm',
    'HFVector', 'HFFile', 'HFCase', 'HFObserve', 'GetTempFileName', 'CreateDirectory',
    'GetBinaryDataFromString', 'GetBinaryDataFromBinaryDataBuffer', 'Base64String',
    'BinaryDataBuffer', 'MemoryStream', 'OpenStreamForRead', 'GetReadonlyStream',
    'PositionInStream', 'CurrentPosition', 'FindFiles', 'DeleteFiles',
    'TypeOf', 'String', 'Number', 'CharCode', 'StrLen', 'Format', 'Left', 'Right',
    'Empty', 'Expected', 'Before', 'Root', 'Path', 'Exists', 'Write', 'Close',
    'Count', 'Size', 'Seek', 'Set')
PUBLIC_ERROR_WORDS = tuple(('ошибка при вызове метода контекста создать по причине '
    'процедура или функция модуль объекта объект не определена определен обнаружен '
    'доступен недоступен поле имя переменная уже объявлена объявление повторное '
    'недопустимое неизвестное использование значения значение типа тип в качестве '
    'безопасном режиме запрещено слишком много мало фактических параметров параметр '
    'недостаточно памяти ожидается выражение завершение возврат несоответствие '
    'синтаксическая инициализации выполнения обработчика подключения файл ошибкаформата '
    'error exception when calling context method create caused by procedure or '
    'function module object variable field name is not defined found available '
    'unavailable already declared declaration invalid unknown using value type as '
    'safe mode forbidden too many few actual parameters parameter insufficient '
    'memory expected expression return mismatch syntax initialization execution '
    'handler connection file format failed unexpected '
    'идентификатор идентификатора имени переменной процедуры функции зарезервированного '
    'слова ключевого оператора параметра неверное reserved identifier keyword statement '
    'argument cannot undefined compilation').split())
FAILURE_TOKEN_WORDS = tuple(dict.fromkeys(word.casefold() for word in
    PUBLIC_SOURCE_IDENTIFIERS + PUBLIC_ERROR_WORDS))
_FAILURE_TOKEN_IDS = {word: index + 1 for index, word in enumerate(FAILURE_TOKEN_WORDS)}
_SOURCE_IDENTIFIERS = frozenset(word.casefold() for word in PUBLIC_SOURCE_IDENTIFIERS)
MAX_FAILURE_TOKENS = 64
_REDACTION_QUOTES = {'"': '"', "'": "'", '`': '`',
                     '«': '»', '“': '”', '‘': '’', '„': '“', '‹': '›'}

class ObservationError(ValueError):
    pass

class AvailabilityError(ObservationError):
    pass


def validate_failure_diagnostic(value):
    """Finite failed-only witness; case holds an owned source line, never text."""
    if value is None: return
    if (type(value) is not dict or set(value) != {'site', 'case', 'category', 'calibration'}
            or type(value['category']) is not str):
        raise ObservationError('data_hashing_diagnostic_invalid')
    kind = value['calibration']
    if type(kind) is dict:
        validate_failure_projection(kind)
        if value['category'] != 'result_error': raise ObservationError('data_hashing_diagnostic_invalid')
        kind = kind['kind']
    if kind is not None and (value['category'] != 'result_error'
            or type(kind) is not str or kind not in RESULT_ERROR_KINDS):
        raise ObservationError('data_hashing_diagnostic_invalid')
    if value['category'] == 'record_count':
        if type(value['site']) is str and value['site'] in ('server', 'client') and value['case'] is None: return
    elif value['category'] in RESULT_FAILURE_CATEGORIES and type(value['site']) is str and value['site'] == 'server':
        line = value['case']
        if line is None or (value['category'] == 'result_error' and type(line) is int and 1 <= line <= SOURCE_LINE_COUNT): return
    raise ObservationError('data_hashing_diagnostic_invalid')


def failure_projection(error, messages, kind):
    """Fixed token IDs and phase booleans only; no raw string is returned."""
    if type(error) is not str or len(error) > MAX_FAILURE_DIAGNOSTIC_BYTES:
        raise ObservationError('data_hashing_diagnostic_invalid')
    if type(messages) is not list:
        raise ObservationError('data_hashing_diagnostic_invalid')
    inspected = messages if len(messages) <= CASE_COUNT + 2 else []
    if (any(type(item) is not str for item in inspected)
            or sum(len(item) for item in inspected) > MAX_FAILURE_DIAGNOSTIC_BYTES):
        raise ObservationError('data_hashing_diagnostic_invalid')
    tokens = []
    def add(token):
        value = _FAILURE_TOKEN_IDS.get(token.casefold(), 0)
        if len(tokens) < MAX_FAILURE_TOKENS and (value != 0 or not tokens or tokens[-1] != 0):
            tokens.append(value)
    i = 0
    while i < len(error) and len(tokens) < MAX_FAILURE_TOKENS:
        if error[i].isspace(): i += 1; continue
        char = error[i]
        if char in _REDACTION_QUOTES:
            quote = _REDACTION_QUOTES[char]; i += 1
            while i < len(error):
                if error[i] == '\\': i += 2; continue
                if error[i] == quote: i += 1; break
                i += 1
            add(''); continue
        if char in '{[(':
            pairs = {'{': '}', '[': ']', '(': ')'}
            stack = [pairs[char]]; end = i + 1
            while end < len(error) and stack:
                current = error[end]
                if current in _REDACTION_QUOTES:
                    quote = _REDACTION_QUOTES[current]; end += 1
                    while end < len(error):
                        if error[end] == '\\': end += 2; continue
                        if error[end] == quote: break
                        end += 1
                elif current in pairs: stack.append(pairs[current])
                elif current == stack[-1]: stack.pop()
                if stack: end += 1
            if stack: add(''); break
            inside = error[i+1:end]
            # Only an exact single already-public source identifier may survive
            # parentheses; quoted values, frames and all other regions redact.
            add(inside if char == '(' and inside.casefold() in _SOURCE_IDENTIFIERS else '')
            i = end + 1; continue
        # An unquoted whitespace-delimited path/URI chunk is uncertain, even if
        # its final component is a public API identifier. Keep quote state when
        # a quoted region begins inside such a chunk.
        end = i
        while end < len(error) and not error[end].isspace(): end += 1
        chunk = error[i:end]
        if '/' in chunk or '\\' in chunk or '://' in chunk:
            quotes = [chunk.find(q) for q in _REDACTION_QUOTES if q in chunk]
            add(''); i = i + min(quotes) if quotes else end; continue
        end = i
        while end < len(error) and not error[end].isspace() and error[end] not in _REDACTION_QUOTES and error[end] not in '{[(':
            end += 1
        add(error[i:end].strip('.,;:!?'))
        i = end
    controls = CALIBRATION.decode('ascii').splitlines()
    frame = re.compile(r'HF-(0[1-9]|[1-3][0-9]|40): \[(?:action-error|observer-error|ok\|S(0|[1-9]|[1-3][0-9]|40):([0-9a-f]{0,160}))\]')
    def case_record(item):
        if len(item) > MAX_RECORD_BYTES: return None
        match = frame.fullmatch(item)
        if match is None or (match[2] is not None and len(match[3]) != 4 * int(match[2])): return None
        return int(match[1])
    ids = [case_record(item) for item in inspected]
    bitmap = 0
    for case in ids:
        if case is not None: bitmap |= 1 << (case - 1)
    prefix = 0
    if inspected[:2] == controls:
        for case in ids[2:]:
            if case != prefix + 1: break
            prefix += 1
    result = {'kind': kind, 'tokens': tokens,
              'phase': {'messages': len(messages) if len(messages) <= CASE_COUNT + 2 else None,
                        'c1': controls[0] in inspected, 'c2': controls[1] in inspected,
                        'case': bitmap != 0, 'case_bitmap': bitmap, 'ordered_prefix': prefix}}
    validate_failure_projection(result)
    return result


def validate_failure_projection(value):
    if (type(value) is not dict or set(value) != {'kind', 'tokens', 'phase'}
            or type(value['kind']) is not str or value['kind'] not in RESULT_ERROR_KINDS
            or type(value['tokens']) is not list or len(value['tokens']) > MAX_FAILURE_TOKENS
            or any(type(item) is not int or not 0 <= item <= len(FAILURE_TOKEN_WORDS) for item in value['tokens'])):
        raise ObservationError('data_hashing_diagnostic_invalid')
    phase = value['phase']
    if (type(phase) is not dict or set(phase) != {'messages', 'c1', 'c2', 'case', 'case_bitmap', 'ordered_prefix'}
            or any(type(phase[key]) is not bool for key in ('c1', 'c2', 'case'))
            or type(phase['case_bitmap']) is not int or not 0 <= phase['case_bitmap'] < (1 << CASE_COUNT)
            or type(phase['ordered_prefix']) is not int or not 0 <= phase['ordered_prefix'] <= CASE_COUNT
            or phase['case'] != bool(phase['case_bitmap'])
            or (phase['ordered_prefix'] > 0 and (not phase['c1'] or not phase['c2']
                or phase['messages'] is None or type(phase['messages']) is not int
                or phase['messages'] < phase['ordered_prefix'] + 2))
            or (phase['case_bitmap'] & ((1 << phase['ordered_prefix']) - 1)) != (1 << phase['ordered_prefix']) - 1
            or not (phase['messages'] is None or type(phase['messages']) is int and 0 <= phase['messages'] <= CASE_COUNT + 2)):
        raise ObservationError('data_hashing_diagnostic_invalid')


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationError('data_hashing_family_output_invalid')
    if not raw.startswith(CALIBRATION):
        raise ObservationError('data_hashing_family_calibration_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('data_hashing_family_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'HF-{case:02d}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('data_hashing_family_record_invalid')
        payload = line[len(prefix):-2]
        if payload in (b'action-error', b'observer-error'):
            records.append({'case': case, 'status': payload.decode('ascii'), 'units': None})
            continue
        match = re.fullmatch(rb'ok\|S(0|[1-9][0-9]?):([0-9a-f]*)', payload)
        if match is None:
            raise ObservationError('data_hashing_family_string_invalid')
        count = int(match[1])
        encoded = match[2]
        if count > MAX_STRING_UNITS or len(encoded) != count * 4:
            raise ObservationError('data_hashing_family_length_invalid')
        units = tuple(int(encoded[i:i+4], 16) for i in range(0, len(encoded), 4))
        records.append({'case': case, 'status': 'ok', 'units': units})
    return tuple(records)


def require_available(raw):
    records = validate_output(raw)
    if any(record['status'] != 'ok' for record in (records[index] for index in range(CASE_COUNT))):
        raise AvailabilityError('data_hashing_family_positive_controls_failed')
    if any(record['status'] == 'observer-error' for record in records):
        raise AvailabilityError('data_hashing_family_observer_failed')
    return records

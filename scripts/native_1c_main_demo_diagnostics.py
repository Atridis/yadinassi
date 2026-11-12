"""Конечная классификация приватного Designer /Out, без экспорта текста."""
import re
import stat

MAX_BYTES = 65536
STATES = ('not_reached', 'classified', 'unavailable')
REASONS = ('none', 'missing', 'unsafe_file', 'budget', 'encoding', 'read_failed')
CODES = ('xml_parse', 'format_version', 'unknown_property', 'type_conversion',
         'metadata_reference', 'unclassified')
# Labels describe recognized wording, not a claim about the root cause.
PATTERNS = (
    ('xml_parse', r'ошибка.*(?:xml|чтени[яе].*файл)|xml.*(?:error|parse)|error.*xml'),
    ('format_version', r'верси[яию].*(?:формат|выгруз)|(?:format|dump).*version|version.*format'),
    ('unknown_property', r'(?:неизвестн|недопустим|неверн).*(?:свойств|элемент)|unknown.*(?:property|element)|invalid.*property'),
    ('type_conversion', r'преобразован.*тип|type.*conversion|cannot.*convert'),
    ('metadata_reference', r'(?:не найден|не существ).*(?:объект|метадан)|(?:metadata|object).*(?:not found|does not exist)'),
)


def empty():
    return dict(state='not_reached', reason='none', codes=[], file_ids=[])


def classify(path, filenames):
    def unavailable(reason):
        return dict(state='unavailable', reason=reason, codes=[], file_ids=[])
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return unavailable('unsafe_file')
        if info.st_size > MAX_BYTES:
            return unavailable('budget')
        with path.open('rb') as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return unavailable('budget')
    except FileNotFoundError:
        return unavailable('missing')
    except OSError:
        return unavailable('read_failed')
    try:
        text = raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
    except UnicodeError:
        return unavailable('encoding')
    normalized = text.casefold().replace('\\', '/')
    codes = [code for code, pattern in PATTERNS if re.search(pattern, normalized)]
    # Export only public fixed inventory ordinals, never source/error fragments.
    ids = [i for i, name in enumerate(filenames) if name.casefold() in normalized]
    return dict(state='classified', reason='none', codes=codes or ['unclassified'], file_ids=ids)


def valid(value, file_count):
    if type(value) is not dict or set(value) != {'state', 'reason', 'codes', 'file_ids'}:
        return False
    state, reason, codes, ids = (value[k] for k in ('state', 'reason', 'codes', 'file_ids'))
    if (type(state) is not str or state not in STATES or type(reason) is not str or reason not in REASONS
            or type(codes) is not list or len(codes) > len(CODES)
            or any(type(c) is not str or c not in CODES for c in codes)
            or len(set(codes)) != len(codes) or type(ids) is not list or len(ids) > file_count
            or any(type(i) is not int or not 0 <= i < file_count for i in ids)
            or ids != sorted(set(ids))):
        return False
    if state == 'classified':
        return reason == 'none' and bool(codes) and ('unclassified' not in codes or codes == ['unclassified'])
    return not codes and not ids and (reason == 'none' if state == 'not_reached' else reason != 'none')

# Reconstructed diagnostic vocabulary, never arbitrary substrings from the log.
WORDS = frozenset("""ошибка ошибки ошибку загрузки загрузка выгрузки метаданных конфигурации
конфигурация файл файла файле формат формата потока чтения записи версия версии
не неверный неверная неверное недопустимый недопустимая недопустимое неизвестный
неизвестная неизвестное свойство свойства элемент элемента объект объекта найден
найдена существует отсутствует ожидается требуется значение значения тип типа
преобразования преобразование данных проверка синтаксиса лицензия лицензии
лицензирования подключения соединения сервер сервера клиент клиента памяти
недостаточно доступ доступа отказ отказано поврежден повреждена исключение
внутренняя ошибка и в на для из при с к
error failed failure loading load metadata configuration file format stream
read reading write writing version invalid unknown property element object
not found does exist missing expected required value type conversion data
syntax check license licensing connection server client memory insufficient
access denied corrupted internal exception to of in the a is
xml internalinfo generatedtype properties childobjects title document form
receipt issue stock units states""".split())
HIDDEN = '[hidden]'
CHANNEL_STATES = ('not_reached', 'empty', 'read', 'missing', 'unsafe_file', 'budget', 'encoding', 'read_failed')
ENCODINGS = ('none', 'utf8', 'utf16')
CHANNELS = ('out', 'stdout', 'stderr', 'result')


def sanitized_lines(text):
    """At most three reconstructed lines of public vocabulary, not raw text."""
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        # Entire credential-like assignments are omitted, even if a password
        # happens to be made entirely of allowed dictionary words.
        if re.search(r'(?i)(token|secret|password|пароль|authorization|cookie|api.?key)\s*[:=]', line):
            result.append(HIDDEN)
        else:
            line = re.sub(r'(?:https?://|[A-Za-z]:[\\/]|/|\\\\)\S+|\S+@\S+', ' ', line)
            tokens = []
            for token in re.findall(r'[^\s,;:(){}<>="\x27]+', line.casefold()):
                word = token.strip('.!?[]')
                safe = word if word in WORDS else HIDDEN
                if safe != HIDDEN or not tokens or tokens[-1] != HIDDEN:
                    tokens.append(safe)
                if len(' '.join(tokens)) > 220:
                    tokens.pop()
                    break
            result.append(' '.join(tokens) or HIDDEN)
        if len(result) == 3:
            break
    return result


def channel(path):
    def unavailable(state, size=None):
        return dict(state=state, bytes=size, encoding='none', lines=[], result='unknown')
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return unavailable('unsafe_file')
        if info.st_size > MAX_BYTES:
            return unavailable('budget')
        with path.open('rb') as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return unavailable('budget')
    except FileNotFoundError:
        return unavailable('missing')
    except OSError:
        return unavailable('read_failed')
    if not raw:
        return unavailable('empty', 0)
    encoding = 'utf16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf8'
    try:
        text = raw.decode('utf-16' if encoding == 'utf16' else 'utf-8-sig')
    except UnicodeError:
        return unavailable('encoding', len(raw))
    result = ('zero' if text.strip() == '0' else 'nonzero'
              if re.fullmatch(r'-?[0-9]{1,6}', text.strip()) else 'unknown')
    return dict(state='read', bytes=len(raw), encoding=encoding,
                lines=sanitized_lines(text), result=result)


def channels_empty():
    return dict(exit_code=None, channels={})


def capture(root, phase, exit_code):
    return dict(exit_code=exit_code, channels={
        name:channel(root/(phase+suffix))
        for name,suffix in (('out','.log'),('stdout','.stdout'),('stderr','.stderr'),('result','.result'))})


def channels_valid(value):
    if type(value) is not dict or set(value) != {'exit_code','channels'}:
        return False
    code, channels = value['exit_code'], value['channels']
    if code is not None and (type(code) is not int or not -128 <= code <= 255):
        return False
    if type(channels) is not dict:
        return False
    if not channels:
        return code is None
    if set(channels) != set(CHANNELS):
        return False
    for data in channels.values():
        if type(data) is not dict or set(data) != {'state','bytes','encoding','lines','result'}:
            return False
        state,size,enc,lines,result = (data[k] for k in ('state','bytes','encoding','lines','result'))
        if (type(state) is not str or state not in CHANNEL_STATES or type(enc) is not str
                or enc not in ENCODINGS or type(result) is not str or result not in ('zero','nonzero','unknown')
                or (size is not None and (type(size) is not int or not 0 <= size <= MAX_BYTES))
                or type(lines) is not list or len(lines)>3):
            return False
        for line in lines:
            if (type(line) is not str or not line or len(line)>240
                    or any(t not in WORDS and t != HIDDEN for t in line.split(' '))):
                return False
        if state == 'read':
            if type(size) is not int or size == 0 or enc == 'none':
                return False
        elif enc != 'none' or lines or result != 'unknown':
            return False
        if state == 'empty' and size != 0:
            return False
        if state not in ('read','empty','encoding') and size is not None:
            return False
    return True

# Only for this public synthetic source in an isolated, credential-free container.
# Not a general-purpose redactor for private configurations or user databases.
CHECK_REASONS = ('none', 'missing', 'unsafe_file', 'budget', 'encoding', 'read_failed', 'sensitive')

def check_empty():
    return dict(state='not_reached', reason='none', lines=[])


def _check_text(text, filenames):
    import unicodedata
    if any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in text):
        raise ValueError('sensitive')
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        # Omit the whole assignment/header, not just a guessed token fragment.
        if re.search(r'(?i)(password|passwd|secret|token|authorization|cookie|api.?key|пароль|секрет)\s*[:=]', line):
            lines.append('[redacted credential]')
            continue
        if re.search(r'(?i)\bBearer\s+\S+|-----BEGIN .*PRIVATE KEY|\b(?:gh[pousr]_|github_pat_|sk-|AKIA)[A-Za-z0-9_/-]+|\beyJ[A-Za-z0-9_-]+\.', line):
            raise ValueError('sensitive')
        normalized = line.replace('\\', '/')
        # Replace only exact known source paths; never emit their private prefix.
        for i, name in sorted(enumerate(filenames), key=lambda item: -len(item[1])):
            normalized = re.sub(r'(?:[A-Za-z]:)?(?:/[^\s\"\'{}<>]*)?'+re.escape(name)+r'(?=$|[\s\"\'{}():,])',
                                '[source:'+str(i)+']', normalized)
        normalized = re.sub(r'https?://[^\s<>\"\']+|\b[^\s@]+@[^\s@]+', '[redacted address]', normalized, flags=re.I)
        normalized = re.sub(r'(?:[A-Za-z]:/|/|\.\.?/)[^\s\"\'{}<>]+', '[redacted path]', normalized)
        # Relative filesystem fragments not associated with the pinned inventory.
        normalized = re.sub(r'\b[^\s/\"\'{}<>]+/[^\s\"\'{}<>]+', '[redacted path]', normalized)
        if re.search(r'[A-Za-z0-9_+=-]{40,}|\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b', normalized):
            raise ValueError('sensitive')
        lines.append(normalized.strip())
    # Scan/redact the entire bounded input before truncation, so a late secret
    # cannot be hidden by the output budget. Preserve a useful diagnostic prefix.
    if len(lines) > 32 or len('\n'.join(lines).encode('utf-8')) > 8192:
        prefix = []
        marker = '[diagnostic truncated]'
        for line in lines:
            if len(prefix) >= 31 or len('\n'.join(prefix + [line, marker]).encode('utf-8')) > 8192:
                break
            prefix.append(line)
        return prefix + [marker]
    return lines


def check_excerpt(path, filenames):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('unsafe_file')
        if info.st_size > 16384:
            raise ValueError('budget')
        raw = path.read_bytes()
        if len(raw) > 16384:
            raise ValueError('budget')
        try:
            text = raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
        except UnicodeError:
            raise ValueError('encoding') from None
        return dict(state='read', reason='none', lines=_check_text(text, filenames))
    except FileNotFoundError:
        reason = 'missing'
    except OSError:
        reason = 'read_failed'
    except ValueError as error:
        reason = str(error) if str(error) in CHECK_REASONS else 'sensitive'
    return dict(state='unavailable', reason=reason, lines=[])


def check_valid(value, filenames):
    if type(value) is not dict or set(value) != {'state','reason','lines'}:
        return False
    state, reason, lines = value['state'], value['reason'], value['lines']
    if (type(state) is not str or state not in ('not_reached','read','unavailable')
            or type(reason) is not str or reason not in CHECK_REASONS
            or type(lines) is not list or any(type(x) is not str or not x or '\n' in x or '\r' in x for x in lines)):
        return False
    if state != 'read':
        return not lines and (reason == 'none' if state == 'not_reached' else reason != 'none')
    if reason != 'none':
        return False
    if any(not 0 <= int(i) < len(filenames) for line in lines for i in re.findall(r'\[source:([0-9]+)\]', line)):
        return False
    try:
        return _check_text('\n'.join(lines), filenames) == lines
    except ValueError:
        return False

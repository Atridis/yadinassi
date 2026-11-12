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

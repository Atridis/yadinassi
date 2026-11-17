"""Russian display labels only; do not rewrite machine-readable report data."""
import re

ROUTES = {'default': 'обычный API', 'prepared': 'подготовленное исполнение'}
LAYERS = {'python': 'Python', 'python_classes': 'Классы yadinassi', 'bsl': 'BSL'}
STATUSES = {'unsupported': 'не поддерживается', 'not_comparable': 'несопоставимо'}
NOTES = {
    'Warm filesystem/page cache; no fsync/durability claim; identical 4096-byte payload. Size baseline opens/fstats/closes a regular file; BSL adds its access validation.':
        'Прогретый файловый кеш ОС; без гарантий fsync и сохранности при сбое. Одинаковые 4096 байт. Базовый замер размера открывает обычный файл, вызывает fstat и закрывает его; BSL дополнительно проверяет доступ.',
    'Host XML classes supported; all paths retain consumed numeric attributes for ordered validation. Current direct constructor may be unsupported. No legacy fallback.':
        'XML-классы доступны из Python. Все пути сохраняют прочитанные числовые атрибуты для проверки порядка. Конструктор прямого BSL может не поддерживаться; обход через legacy не используется.',
    'Read/modify/write one existing catalog item; canonical persisted-value readback after every sample; no raw-SQL speed ratio.':
        'Чтение, изменение и запись существующего элемента справочника; после каждого замера сохранённое значение повторно читается через штатный API. Коэффициент относительно сырого SQL не рассчитывается.',
    'Actual direct form lifecycle; event session setup excluded, open case includes construction/compilation. Only the default table includes this lifecycle; it is not execute_prepared.':
        'Настоящий жизненный цикл формы. Подготовка сеанса исключена из замера события; открытие включает создание и компиляцию. Сценарий есть только в таблице обычного API: это не execute_prepared.',
}
REASONS = {
    'Raw SQLite UPDATE omits catalog writer semantics.': 'Сырой SQLite UPDATE не воспроизводит семантику записи справочника.',
    'No equivalent native/classes managed-form lifecycle.': 'Нет эквивалентного жизненного цикла управляемой формы у обычного Python и отдельно вызванных классов.',
}


def note(text):
    if text in NOTES:
        return NOTES[text]
    match = re.fullmatch(r'Same SQLite file and (\d+) catalog rows\. Raw SQL baseline excludes BSL catalog/query admission\.', text)
    if match:
        return ('Один файл SQLite, строк справочника: ' + match.group(1)
                + '. Сырой SQL не включает проверки допуска к каталогу и запросам BSL.')
    return text  # Preserve an unknown future explanation rather than conceal it.


def reason(text):
    if 'python-direct: constructor XMLWriter;' in text:
        return 'Прямой BSL не поддерживает конструктор XMLWriter; обход через legacy не выполнялся.'
    return REASONS.get(text, text)


def api(text):
    return {
        'FormSession.dispatch(command) + snapshot': 'FormSession.dispatch(command) + снимок состояния',
        'FormSession construction + open + close': 'FormSession: создание, открытие и закрытие',
    }.get(text, text)

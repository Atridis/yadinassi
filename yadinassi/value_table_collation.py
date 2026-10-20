"""Pinned DUCET 6.0 empirical data for bounded collection sorting.

The official, unmodified data reproduces the owner's two locale checkpoints;
this is evidence for this bounded implementation, not proof that 1C uses UCA6.
ValueList sorting separately selects key strength from its own native evidence.
Existing String/StrCompare UCA10 behavior is intentionally independent.
The adjacent data and license must ship in wheels and frozen applications.
"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import unicodedata

from pyuca.collator import Collator_6_3_0

TABLE_NAME = 'allkeys-6.0.0.txt'
TABLE_VERSION = '6.0.0'
TABLE_SHA256 = 'b6e440cff4c0b71215bb8a12dd64d56c95b5c973097377697a388ba7289b085d'
TABLE_SIZE = 1_655_669
MAX_STRING_LENGTH = 4096
MAX_NORMALIZED_LENGTH = 16384


class _DUCET60(Collator_6_3_0):
    # The shared pyuca parser/implicit-weight implementation covers this bounded
    # non-CJK alphabet. Do not claim complete UCA6 conformance for other scripts.
    UCA_VERSION = TABLE_VERSION


@lru_cache(maxsize=1)
def _collator():
    path = Path(__file__).with_name('data') / TABLE_NAME
    try:
        data = path.read_bytes()
        if (len(data) != TABLE_SIZE or sha256(data).hexdigest() != TABLE_SHA256
                or b'\n@version 6.0.0\n' not in data):
            raise ValueError('Сортировка: изменена таблица сравнения UCA 6.0.0')
        return _DUCET60(str(path))
    except OSError as error:
        raise ValueError('Сортировка: недоступна таблица сравнения UCA 6.0.0') from error


def caseless_string_key(value):
    """No user-string cache; bound both input and normalized collation work."""
    if len(value) > MAX_STRING_LENGTH:
        raise ValueError('Сортировка: превышен предел длины строки Yadinassi')
    normalized = unicodedata.normalize('NFD', value)
    if len(normalized) > MAX_NORMALIZED_LENGTH:
        raise ValueError('Сортировка: превышен предел нормализации Yadinassi')
    # Already normalized and checked; avoid a second normalization pass.
    collator = _collator()
    key = collator.sort_key_from_collation_elements(collator.collation_elements(normalized))
    second_separator = key.index(0, key.index(0) + 1)
    return key[:second_separator]

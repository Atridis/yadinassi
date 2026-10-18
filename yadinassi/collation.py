"""Fixed UCA 10 DUCET ordering, not a claim of complete 1C locale parity.

Keep exact BSL equality separate. Canonically equivalent spellings can have
equal collation keys without being identical strings. No per-string cache is
retained; the single lazily loaded, read-only table is shared by all callers.
"""

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import unicodedata

from pyuca.collator import Collator_10_0_0
import pyuca


TABLE_NAME = "allkeys-10.0.0.txt"
TABLE_SHA256 = "d4c477aaeb59e026f34688ffb48096c7505aa48ce044757977ace647d0429a17"
MAX_STRING_LENGTH = 4096
MAX_NORMALIZED_LENGTH = 16384


@lru_cache(maxsize=1)
def _collator() -> Collator_10_0_0:
    path = Path(pyuca.__file__).with_name(TABLE_NAME)
    try:
        if sha256(path.read_bytes()).hexdigest() != TABLE_SHA256:
            raise ValueError("Изменена таблица сравнения строк UCA 10.0.0")
        return Collator_10_0_0(str(path))
    except OSError as error:
        raise ValueError("Недоступна таблица сравнения строк UCA 10.0.0") from error


def string_key(value: str) -> tuple[int, ...]:
    # pyuca's prefix lookup copies suffixes. Bound work before normalization
    # and again before the quadratic collation pass, rather than caching input.
    if len(value) > MAX_STRING_LENGTH:
        raise ValueError("Сравнение строк: превышен ресурсный предел 4096 символов")
    normalized = unicodedata.normalize("NFD", value)
    if len(normalized) > MAX_NORMALIZED_LENGTH:
        raise ValueError("Сравнение строк: превышен ресурсный предел нормализации")
    return _collator().sort_key(normalized)


def caseless_string_key(value: str) -> tuple[int, ...]:
    """Primary and secondary UCA weights; native-backed subset, not locale ICU.

    Tertiary weights distinguish case (and other variants). Keep secondary
    weights: sharp-s/SS and dotted-I/i are unequal in the owner's native probes.
    Reuse the pinned table, NFD and both resource limits without case expansion.
    """
    key = string_key(value)
    second_separator = key.index(0, key.index(0) + 1)
    return key[:second_separator]

"""Lightweight text ordering for user-facing sorts, not string equality."""

_RUSSIAN_ALPHABET = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'


def _russian_translation():
    # Reuse Russian code points as weights; no weight collides with a
    # character outside this alphabet. Both cases use the same weight.
    cases = _RUSSIAN_ALPHABET + _RUSSIAN_ALPHABET.upper()
    ranks = dict(zip(map(ord, cases), map(ord, sorted(cases)[:len(_RUSSIAN_ALPHABET)] * 2)))
    return tuple(ranks.get(code, code) for code in range(max(ranks) + 1))


def text_sort_key(value: str, _translation=_russian_translation()) -> str:
    """Order Russian letters alphabetically, leaving other characters intact."""
    return value if value.isascii() else value.translate(_translation)

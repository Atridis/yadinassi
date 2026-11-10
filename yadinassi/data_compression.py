"""Deflation settings and bounded private ValueStorage payload compression.

This is not the platform's physical storage format, a wire codec or a public
compression/decompression API. Only snapshot string/binary payloads use zlib;
the existing immutable snapshot graph and its validation remain authoritative.
"""
from dataclasses import dataclass
from decimal import Decimal
import zlib

from .values import BSLObject


@dataclass(frozen=True, eq=False, init=False)
class BSLDeflation(BSLObject):
    _degree: int

    def __init__(self, degree=None):
        if degree is None:
            degree = Decimal(-1)
        if (type(degree) is not Decimal or not degree.is_finite()
                or degree < -1 or degree > 9 or degree != degree.to_integral_value()):
            raise ValueError('СжатиеДанных: ожидается целая степень от -1 до 9')
        object.__setattr__(self, '_degree', int(degree))

    def __str__(self):
        raise ValueError('СжатиеДанных: строковое представление пока не поддерживается')


def compression_degree(settings):
    if settings is None:
        return 0
    if type(settings) is not BSLDeflation:
        raise TypeError('ХранилищеЗначения: ожидается СжатиеДанных')
    try:
        degree = object.__getattribute__(settings, '_degree')
    except AttributeError:
        raise ValueError('СжатиеДанных: отсутствует степень сжатия') from None
    if type(degree) is not int or not -1 <= degree <= 9:
        raise ValueError('СжатиеДанных: повреждена степень сжатия')
    return degree


def compress_payload(data, degree):
    """Called only after the existing capture budget admitted exact bytes."""
    return zlib.compress(data, degree)


def expand_payload(data, expected, limit):
    """Bound output before zlib allocation and reject suffixes/truncation."""
    if (type(data) is not bytes or type(expected) is not int
            or expected < 0 or expected > limit):
        raise ValueError('invalid compressed snapshot framing')
    try:
        decoder = zlib.decompressobj()
        result = decoder.decompress(data, expected + 1)
        if (len(result) != expected or not decoder.eof or decoder.unused_data
                or decoder.unconsumed_tail):
            raise ValueError('invalid compressed snapshot payload')
        return result
    except zlib.error:
        raise ValueError('invalid compressed snapshot payload') from None

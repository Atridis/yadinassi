"""Bounded, certified binary64 Exp independent of host libm underflow."""

from decimal import Context, Decimal, ROUND_HALF_EVEN
import math

from .math_conversion import UnsupportedConversionRange


_PRECISIONS = (80, 160, 320)


def binary_exp(value: float) -> float:
    """Return correctly rounded binary64 exp(value), or reject uncertainty.

    Decimal.exp is correctly rounded with ROUND_HALF_EVEN. The adjacent
    decimal numbers therefore enclose the exact exponential. Converting both
    endpoints to the same positive binary64 value certifies that rounding;
    no assumption that 80 decimal digits are universally enough is needed.

    Safe monotonic outer bounds avoid work proportional to extreme inputs:
    exp(-746) < 2**-1075, half the least positive binary64 subnormal, while
    exp(710) exceeds the binary64 overflow threshold. Evaluated arguments
    remain in [-746, 710], so exponent limits [-999, 999] keep every Decimal
    result normal. These are numerical bounds, not input-specific answers.
    """
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("Exp: ожидается конечный двоичный аргумент")
    if value < -746.0:
        return 0.0
    if value > 710.0:
        return math.inf

    argument = Decimal.from_float(value)
    for precision in _PRECISIONS:
        # Specify every setting, including traps/flags, rather than inherit
        # a hostile caller context or a modified decimal.DefaultContext.
        context = Context(prec=precision, rounding=ROUND_HALF_EVEN,
                          Emin=-999, Emax=999, capitals=1, clamp=0,
                          traps=[], flags=[])
        rounded = context.exp(argument)
        lower = float(context.next_minus(rounded))
        upper = float(context.next_plus(rounded))
        # The exponential and both bounds are positive. Equality therefore
        # also means identical binary64 bits (including zero and infinity).
        if lower == upper:
            return lower
    raise UnsupportedConversionRange(
        "Exp: округление двоичного результата не установлено в пределах "
        "точности Yadinassi (320 десятичных разрядов)")

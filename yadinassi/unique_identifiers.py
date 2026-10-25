"""Provisional UUID scalar; native parity has NOT been established.

The canonical-only grammar, lowercase presentation, zero/filled and generated
v4 policy are local candidate choices pending the independent native checkpoint.
No host UUID parser, codecs, descriptor coercion or transport is implied.
"""
from dataclasses import dataclass
import re
import secrets

from .values import BSLObject

_CANONICAL = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
_OMITTED = object()
_ZERO = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True, slots=True, init=False)
class BSLUUID(BSLObject):
    text: str

    def __init__(self, value=_OMITTED):
        if value is _OMITTED:
            # Explicit local generation policy, NOT evidence of 1C's default
            # version. The native probe only compares stable projections.
            data = bytearray(secrets.token_bytes(16))
            data[6] = (data[6] & 0x0f) | 0x40
            data[8] = (data[8] & 0x3f) | 0x80
            raw = data.hex()
            text = f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
        else:
            if type(value) is not str:
                raise TypeError("УникальныйИдентификатор: ожидается строка")
            # Check length before regex/lowercase: bounded work even for huge
            # inputs; exact type prevents hostile host str-subclass hooks.
            if len(value) != 36 or _CANONICAL.fullmatch(value) is None:
                raise ValueError("УникальныйИдентификатор: поддерживается только каноническая строка UUID")
            text = value.lower()
        object.__setattr__(self, "text", text)

    def __str__(self):
        return self.text

    def is_filled(self):
        return self.text != _ZERO

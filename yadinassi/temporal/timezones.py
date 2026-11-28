"""Explicit local-calendar policy backed by the pinned, bundled IANA database.

YADINASSI_TIMEZONE selects an IANA key such as Europe/Warsaw. If it is absent,
the host's time.localtime remains authoritative, including its platform limits.
No process timezone setting is changed. Explicit zones are loaded from tzdata
resources rather than ZoneInfo's ambient system search path. Seasonal offsets
are computed for the converted instant, never copied from the current date.

This is a standalone configuration contract, not additional native 1C evidence.
The explicit-zone envelope requires both UTC and local years in 1..9999.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
import os
import re
from struct import error as StructError
import time
from zoneinfo import ZoneInfo

import tzdata


TIMEZONE_ENV = "YADINASSI_TIMEZONE"
MAX_ZONE_NAME_LENGTH = 255
_MAX_ZONE_CATALOG_BYTES = 65536
_MAX_ZONE_CATALOG_ENTRIES = 1024
_ZONE_NAME = re.compile(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*\Z")
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MIN_UNIX_SECONDS = -62135596800
_MAX_UNIX_SECONDS = 253402300799


class TimezoneConfigurationError(ValueError):
    """An explicit timezone cannot be used; host/UTC fallback is not allowed."""


def _validate_zone_name(name):
    # Validate before splitting, resource traversal or an LRU lookup. Exact
    # types also avoid executing a supplied object's conversion/hash hooks.
    if type(name) is not str:
        raise TimezoneConfigurationError(f"{TIMEZONE_ENV}: ожидается имя часового пояса IANA")
    if len(name) > MAX_ZONE_NAME_LENGTH:
        raise TimezoneConfigurationError(
            f"{TIMEZONE_ENV}: превышен предел {MAX_ZONE_NAME_LENGTH} символов")
    if not _ZONE_NAME.fullmatch(name):
        raise TimezoneConfigurationError(f"{TIMEZONE_ENV}: недопустимое имя часового пояса IANA")
    return name


@lru_cache(maxsize=1)
def _zone_names():
    # Filesystem lookup is case-insensitive on some supported platforms. The
    # bundled catalogue establishes exact, portable IANA spelling before any
    # per-zone lookup, including cache hits. Bound both reads and retained data.
    try:
        path = resources.files(tzdata).joinpath("zones")
        with path.open("rb") as stream:
            raw = stream.read(_MAX_ZONE_CATALOG_BYTES + 1)
        if len(raw) > _MAX_ZONE_CATALOG_BYTES:
            raise ValueError("превышен предел размера каталога")
        names = raw.decode("ascii").splitlines()
        if not names or len(names) > _MAX_ZONE_CATALOG_ENTRIES:
            raise ValueError("недопустимый размер каталога")
        result = frozenset(_validate_zone_name(name) for name in names)
        if len(result) != len(names):
            raise ValueError("повторяющиеся записи каталога")
        return result
    except (OSError, ValueError, EOFError, StructError) as error:
        raise TimezoneConfigurationError(
            f"{TIMEZONE_ENV}: недоступен каталог часовых поясов IANA") from error


@lru_cache(maxsize=16)
def _load_zone(name):
    try:
        path = resources.files(tzdata).joinpath("zoneinfo", *name.split("/"))
        with path.open("rb") as stream:
            return ZoneInfo.from_file(stream, key=name)
    except (OSError, ValueError, EOFError, StructError) as error:
        raise TimezoneConfigurationError(
            f"{TIMEZONE_ENV}: недоступен часовой пояс IANA {name}") from error


def local_parts(seconds: int) -> tuple[int, int, int, int, int, int]:
    """Return six local calendar fields for exact integer Unix seconds.

    Unset configuration preserves host conversion exceptions. Invalid explicit
    configuration raises TimezoneConfigurationError. Explicit UTC/local date
    overflow raises OverflowError, for the caller's existing range handling.
    Each invocation reads the setting again; only up to 16 zone objects persist.
    """
    if type(seconds) is not int:
        raise TypeError("Часовой пояс: ожидается целое число секунд Unix")
    name = os.environ.get(TIMEZONE_ENV)
    if name is None:
        return time.localtime(seconds)[:6]
    name = _validate_zone_name(name)
    # Bound before timedelta construction and before reading package resources.
    # In particular, huge exact integers cannot cause large intermediate work.
    if not _MIN_UNIX_SECONDS <= seconds <= _MAX_UNIX_SECONDS:
        raise OverflowError("Часовой пояс: дата UTC вне поддержанного диапазона")
    if name not in _zone_names():
        raise TimezoneConfigurationError(
            f"{TIMEZONE_ENV}: неизвестный часовой пояс IANA {name}")
    zone = _load_zone(name)
    local = (_UNIX_EPOCH + timedelta(seconds=seconds)).astimezone(zone)
    return (local.year, local.month, local.day, local.hour, local.minute, local.second)

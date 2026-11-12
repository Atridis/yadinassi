"""Bounded observation framing, deliberately separate from semantic acceptance.

A record contains measured values, not expected-success booleans. This parser
cannot establish configuration installation, lifecycle, ownership or cleanup.
"""
import re

PROFILE = 'configuration-owned-enum-forms-v1'
GROUPS = ('catalog_default', 'catalog_change', 'catalog_reopen', 'document_header',
          'document_rows', 'conversion_post', 'conversion_unpost', 'independent_forms')
MAX_OUTPUT = 8192
_TOKEN = re.compile(r'[A-Za-z0-9_.:-]{1,96}\Z', re.ASCII)


def parse_records(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_OUTPUT:
        raise ValueError('bounded observation bytes required')
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError:
        raise ValueError('ASCII observation framing required') from None
    parts = text.split('\n')
    if len(parts) != len(GROUPS) + 1 or parts[-1] != '':
        raise ValueError('complete observation framing required')
    result = []
    for group, line in zip(GROUPS, parts[:-1]):
        name, separator, payload = line.partition('=')
        values = payload.split(';')
        if (name != group or separator != '=' or not 1 <= len(values) <= 16
                or any(_TOKEN.fullmatch(value) is None for value in values)):
            raise ValueError('invalid observation record')
        result.append((group, tuple(values)))
    return tuple(result)

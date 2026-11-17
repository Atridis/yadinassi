"""Lossless payload comparison; callers explicitly choose allowed codec fields.

Only pair order in the four associative container types is ignored. No output
rewriting, global string decoding, runtime decoder, or inferred object identity.
The historical typed-map-order-v1 profile remains unchanged.
"""
# The native host injects its securely fresh-loaded grammar before exec.
if 'grammar' not in globals():
    from scripts import native_1c_map_contract as grammar


def signature(payload, *, expected_root=None, expected_count=None):
    if type(payload) is str:
        payload = payload.encode('utf-8', errors='strict')
    if type(payload) is not bytes or len(payload) > grammar.MAX_RECORD:
        raise ValueError('payload_limit')
    try:
        payload.decode('utf-8', errors='strict')
        parser = grammar._Parser(payload)
        parser.whitespace()
        prefix = payload[:parser.cursor]
        root = parser.parse()
        if expected_root is not None:
            fields = grammar._group(root)
            if (len(fields) != 3 or grammar._atom(fields[0], quoted=True) != b'"#"'
                    or grammar._atom(fields[1]) != expected_root):
                raise ValueError('payload_root_mismatch')
            if expected_count is not None:
                body = grammar._group(fields[2])
                if grammar._atom(body[0]) != str(expected_count).encode('ascii'):
                    raise ValueError('payload_count_mismatch')
        end = parser.cursor
        parser.whitespace()
        if parser.cursor != len(payload):
            raise grammar._Reject('unsupported_payload')
        return prefix, grammar._value(root, associative=True), payload[end:]
    except (grammar._Reject, UnicodeError) as error:
        raise ValueError(str(error)) from None


def equivalent(left, right):
    """Validate BOTH payloads even if byte-identical; unsupported layouts reject."""
    return signature(left) == signature(right)


# Explicit fields in the authenticated historical collections program. Strings
# printed by unrelated programs never acquire serialization semantics by shape.
HISTORICAL_PAYLOAD_LABELS = frozenset(
    base + suffix
    for base in ('internal.map.typed-keys', 'internal.map.typed-keys-again',
                 'internal.map.reverse-insertion', 'internal.array.nested',
                 'internal.structure.order-ab', 'internal.structure.order-ba')
    for suffix in ('.payload', '.roundtrip.payload')
)


def compare_historical_collections(native, actual, source):
    from scripts.native_historical_replay import (
        git_blob, HISTORICAL_COLLECTIONS_BLOB, HISTORICAL_COLLECTIONS_OUTPUT_BLOB,
    )
    result = {'status': 'rejected', 'raw_equal': native == actual,
              'accepted_labels': [], 'reason': 'none'}
    try:
        if (git_blob(source) != HISTORICAL_COLLECTIONS_BLOB
                or git_blob(native) != HISTORICAL_COLLECTIONS_OUTPUT_BLOB):
            raise ValueError('source_or_fixture_mismatch')
        left = grammar._records(native, expected_count=None)
        right = grammar._records(actual, expected_count=len(left))
        accepted = []
        for a, b in zip(left, right):
            if a[0] != b[0]:
                raise ValueError('record_mismatch')
            if a[0] in HISTORICAL_PAYLOAD_LABELS:
                root = (grammar._ARRAY if a[0].startswith('internal.array.') else
                        b'4238019d-7e49-4fc9-91db-b6b951d5cf8e' if a[0].startswith('internal.structure.')
                        else grammar._MAP)
                if signature(a[2], expected_root=root) != signature(b[2], expected_root=root):
                    raise ValueError('typed_difference')
                if a[1] != b[1]:
                    accepted.append(a[0])
            elif a[1] != b[1]:
                raise ValueError('ineligible_difference')
        if not HISTORICAL_PAYLOAD_LABELS.issubset({a[0] for a in left}):
            raise ValueError('record_mismatch')
        result.update(status='equivalent', accepted_labels=accepted)
    except (grammar._Reject, ValueError, TypeError) as error:
        result['reason'] = str(error)
    return result


DESCRIPTOR_HISTORY_LABELS = frozenset(
    'table.descriptor-key.codec-' + kind + '-' + variant
    for kind in ('mutable', 'fixed')
    for variant in ('single', 'unequal', 'duplicate-equal')
)
_DESCRIPTOR_STEPS = ('insert-first', 'count-first', 'get-first', 'index-first',
    'get-second-before', 'index-second-before', 'insert-second',
    'codec-source-count', 'codec-fixed', 'codec-write', 'codec-read', 'codec-count',
    'codec-first', 'codec-second', 'codec-index-first', 'codec-index-second')


def _unescape_compact(value):
    escapes = {92: b'\\', 110: b'\n', 114: b'\r', 116: b'\t'}
    out = bytearray(); index = 0
    while index < len(value):
        c = value[index]; index += 1
        if c == 92:
            if index == len(value) or value[index] not in escapes:
                raise ValueError('invalid_compact_escape')
            out.extend(escapes[value[index]]); index += 1
        elif c in (10, 13, 9):
            raise ValueError('noncanonical_compact_escape')
        else:
            out.append(c)
    return bytes(out)


def _string_field(node):
    children = grammar._group(node)
    if len(children) != 2 or grammar._atom(children[0], quoted=True) != b'"S"':
        raise ValueError('history_string_expected')
    raw = grammar._atom(children[1], quoted=True)
    return raw[1:-1].replace(b'""', b'"')


def codec_history_signature(payload, *, expected_root=None, expected_count=None):
    """Only measured descriptor history: ordered steps, one codec-write field.

    Decode exactly two known compact-string layers. Everything outside that
    payload, including step names, values, escaping and separators, stays exact.
    No ordinary string acquires codec semantics from resembling a stream.
    """
    if type(payload) is str:
        payload = payload.encode('utf-8')
    if type(payload) is not bytes or len(payload) > grammar.MAX_RECORD:
        raise ValueError('payload_limit')
    if not payload.startswith(b'[') or not payload.endswith(b']'):
        raise ValueError('history_array_expected')
    parser = grammar._Parser(payload, max_scalar=grammar.MAX_RECORD)
    parser.cursor = 1
    entries = []; gaps = []; start = 1
    try:
        while parser.cursor < len(payload) - 1:
            parser.whitespace()
            gaps.append(payload[start:parser.cursor])
            begin = parser.cursor
            node = parser.parse()
            raw = payload[begin:parser.cursor]
            value = _unescape_compact(_string_field(node))
            name, separator, result = value.partition(b':ok:')
            if separator != b':ok:' or name.decode('ascii') not in _DESCRIPTOR_STEPS:
                raise ValueError('history_step_invalid')
            if name == b'codec-write':
                inner = grammar._Parser(result, max_scalar=grammar.MAX_RECORD)
                inner_node = inner.parse()
                if inner.cursor != len(result):
                    raise ValueError('history_trailing_data')
                codec = _unescape_compact(_string_field(inner_node))
                entries.append((name, node.gaps, inner_node.gaps, signature(
                    codec, expected_root=expected_root, expected_count=expected_count)))
            else:
                if expected_count is not None and name in (b'codec-source-count', b'codec-count'):
                    if result != b'{"N",' + str(expected_count).encode('ascii') + b'}':
                        raise ValueError('history_count_mismatch')
                entries.append((name, raw))
            start = parser.cursor
            parser.whitespace()
            if parser.cursor == len(payload) - 1:
                gaps.append(payload[start:parser.cursor]); break
            if payload[parser.cursor:parser.cursor + 1] != b';':
                raise ValueError('history_separator')
            parser.cursor += 1
            if parser.cursor >= len(payload) - 1:
                raise ValueError('history_trailing_separator')
            gaps.append(payload[start:parser.cursor]); start = parser.cursor
        names = tuple(name.decode('ascii') for name, *_ in entries)
        allowed = tuple(tuple(n for n in _DESCRIPTOR_STEPS if n not in omitted)
                        for omitted in ((), ('insert-second',), ('codec-fixed',),
                                        ('insert-second', 'codec-fixed')))
        if names not in allowed:
            raise ValueError('history_coverage')
        return tuple(gaps), tuple(entries)
    except (grammar._Reject, UnicodeError) as error:
        raise ValueError(str(error)) from None


def equivalent_codec_history(left, right):
    return codec_history_signature(left) == codec_history_signature(right)


PROFILE = 'associative-order-v2'
SOURCE_SHA256 = grammar.SOURCE_SHA256
RECORD_COUNT = grammar.RECORD_COUNT
REASONS = grammar.REASONS
ELIGIBLE_LABELS = tuple(sorted(HISTORICAL_PAYLOAD_LABELS | DESCRIPTOR_HISTORY_LABELS))
_CHECKS_EXTRA = {296: 'internal.structure.order-ab.roundtrip.type',
                 297: 'internal.structure.order-ab.roundtrip.count',
                 300: 'internal.structure.order-ba.roundtrip.type',
                 301: 'internal.structure.order-ba.roundtrip.count'}
_PINNED_EXTRA = {295: 'internal.structure.order-ab.payload',
                 298: 'internal.structure.order-ab.roundtrip.payload',
                 299: 'internal.structure.order-ba.payload',
                 302: 'internal.structure.order-ba.roundtrip.payload'}
_PINNED_EXTRA.update({822 + index: 'table.descriptor-key.codec-' + kind + '-' + variant
                     for index, (variant, kind) in enumerate(
                         (variant, kind) for variant in ('single', 'unequal', 'duplicate-equal')
                         for kind in ('mutable', 'fixed'))})


def compare_collections(native, actual, source_sha256):
    """Source-bound full-run relation; original output hashes stay caller-owned.

    v1 remains separate. This v2 adds only the named Structure codec records and
    descriptor codec-write fields, not arbitrary string or XML normalization.
    """
    result = {'status': 'rejected', 'profile': PROFILE, 'records': 0,
              'byte_equal_records': 0, 'accepted_labels': [], 'reason': 'none'}
    try:
        if type(source_sha256) is not str or source_sha256 != SOURCE_SHA256:
            raise grammar._Reject('source_mismatch')
        left, right = grammar._records(native), grammar._records(actual)
        accepted = []; equal = 0; seen = set(); payloads = ({}, {})
        for ordinal, (a, b) in enumerate(zip(left, right), 1):
            if a[0] != b[0]:
                raise grammar._Reject('record_mismatch')
            pinned = grammar._ELIGIBLE.get(ordinal, grammar._CHECKS.get(ordinal, _PINNED_EXTRA.get(ordinal, _CHECKS_EXTRA.get(ordinal))))
            if pinned is not None and a[0] != pinned:
                raise grammar._Reject('record_mismatch')
            if (ordinal in grammar._CHECKS or ordinal in _CHECKS_EXTRA) and (a[2] != b'true' or b[2] != b'true'):
                raise grammar._Reject('roundtrip_failed')
            label = a[0]
            if label in HISTORICAL_PAYLOAD_LABELS:
                root = (grammar._ARRAY if label.startswith('internal.array.') else
                        b'4238019d-7e49-4fc9-91db-b6b951d5cf8e' if label.startswith('internal.structure.')
                        else grammar._MAP)
                x, y = (signature(data, expected_root=root) for data in (a[2], b[2]))
                payloads[0][label], payloads[1][label] = x, y
                if x != y:
                    raise grammar._Reject('typed_difference')
                seen.add(label)
            elif label in DESCRIPTOR_HISTORY_LABELS:
                root = grammar._MAP if '-mutable-' in label else grammar._FIXED_MAP
                count = 2 if label.endswith('-unequal') else 1
                x, y = (codec_history_signature(data, expected_root=root, expected_count=count)
                        for data in (a[2], b[2]))
                omitted = set()
                if '-mutable-' in label: omitted.add('codec-fixed')
                if label.endswith('-single'): omitted.add('insert-second')
                names = tuple(name.encode('ascii') for name in _DESCRIPTOR_STEPS if name not in omitted)
                if any(tuple(entry[0] for entry in tree[1]) != names for tree in (x, y)):
                    raise grammar._Reject('unsupported_payload')
                if x != y:
                    raise grammar._Reject('typed_difference')
                seen.add(label)
            elif a[1] != b[1]:
                raise grammar._Reject('ineligible_difference')
            if a[1] != b[1]: accepted.append(label)
            equal += a[1] == b[1]
        if seen != set(ELIGIBLE_LABELS):
            raise grammar._Reject('record_mismatch')
        for side in payloads:
            for label, tree in side.items():
                if label.endswith('.roundtrip.payload'):
                    original = label.removesuffix('.roundtrip.payload') + '.payload'
                    if tree != side[original]:
                        raise grammar._Reject('roundtrip_failed')
        result.update(status='equivalent', records=RECORD_COUNT,
                      byte_equal_records=equal, accepted_labels=sorted(accepted))
    except grammar._Reject as error:
        result['reason'] = str(error)
    except (ValueError, UnicodeError, TypeError):
        result['reason'] = 'unsupported_payload'
    return result

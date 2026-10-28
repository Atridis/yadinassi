"""Strict bounded observation grammar, not LoadColumn behavior or a serializer.

Both native and interpreter observations must pass independently. Equal setup,
calibration or observer failures are never evidence of behavioral parity.
"""
ALPHABET = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
IDENTITIES = ALPHABET[:60]
BASE_RECORDS = 976
RECORD_COUNT = 45
MAX_MESSAGE_UNITS = 3525
SNAPSHOT_SIZE = 59
MUTATIONS = frozenset((37, 38, 39, 40))
SOURCE_KINDS = {10: b"F", 26: b"S", 27: b"N", 28: b"U", 29: b"L", 30: b"R"}
SCALAR_CODES = b"ULFT01234567abcdefghij"


class ObservationError(ValueError):
    """Finite diagnostic only; never include observed values in the error."""


def _reject():
    raise ObservationError("tree_load_observation_invalid")


def _value(code, identities, registry):
    if len(code) != 2:
        _reject()
    if code[0] in SCALAR_CODES and code[1:] == b"_":
        return
    if code[0] in b"PQR" and code[1] in IDENTITIES:
        identifier = code[1]
        if identifier not in registry:
            if len(registry) >= len(IDENTITIES) or identifier != IDENTITIES[len(registry)]:
                _reject()
            registry.add(identifier)
        if identifier in identities and identities[identifier] != code[0]:
            _reject()
        identities[identifier] = code[0]
        return
    _reject()


def _snapshot(payload, case, registry):
    if len(payload) != SNAPSHOT_SIZE:
        _reject()
    shape = b"E" if case in (5, 19) else b"N" if case == 6 else b"B"
    if payload[:2] != shape * 2:
        _reject()
    identities = {}
    cells = payload[2:50]
    if shape != b"B":
        if cells != b"." * 48:
            _reject()
    else:
        for offset in range(0, 48, 2):
            _value(cells[offset:offset + 2], identities, registry)
    kind, identity, count = payload[50:51], payload[51:52], payload[52:53]
    if kind != SOURCE_KINDS.get(case, b"A") or count not in (b"0", b"1", b"2", b"3"):
        _reject()
    count = count[0] - 48
    if kind in (b"A", b"F"):
        if identity not in (b"1", b"2"):
            _reject()
    elif identity != b"0" or count != 1:
        _reject()
    slots = payload[53:]
    for index in range(3):
        value = slots[index * 2:index * 2 + 2]
        if index < count:
            _value(value, identities, registry)
        elif value != b"..":
            _reject()
    first = slots[:1]
    if (kind == b"S" and first[0] not in b"abcdefghij"
            or kind == b"N" and first[0] not in b"01234567"
            or kind == b"U" and first != b"U"
            or kind == b"L" and first != b"L"
            or kind == b"R" and first[0] not in b"PQR"):
        _reject()
    return identities


def validate_payload(payload, case):
    """Validate one exact case; action exceptions are observations, not failures."""
    if type(case) is not int or not 1 <= case <= RECORD_COUNT or type(payload) is not bytes:
        _reject()
    expected_length = 6 + SNAPSHOT_SIZE + (1 + SNAPSHOT_SIZE if case in MUTATIONS else 0)
    if len(payload) != expected_length or payload[:2] != b"1" + ALPHABET[case - 1:case]:
        _reject()
    action, mutation, result = payload[2:3], payload[3:4], payload[4:6]
    if action not in (b"0", b"1"):
        _reject()
    registry = {IDENTITIES[0]} if case in (30, 37, 38) else set()
    if case in MUTATIONS:
        if mutation not in ((b"1", b"2") if action == b"0" else (b"3",)):
            _reject()
        if payload[65:66] != b"|":
            _reject()
        _snapshot(payload[6:65], case, registry)
        identities = _snapshot(payload[66:], case, registry)
    else:
        if mutation != b"0":
            _reject()
        identities = _snapshot(payload[6:], case, registry)
    if case != 34 or action == b"1":
        if result != b"--":
            _reject()
    else:
        _value(result, identities, registry)


def validate_records(records):
    """Validate the whole suffix of production-framed collections records.

    The framing parser is supplied by the caller. No splitlines, suffix search,
    normalization or inference of expected action outcomes is performed here.
    """
    if type(records) is not list or len(records) != BASE_RECORDS + RECORD_COUNT:
        _reject()
    units = 0
    for case, record in enumerate(records[BASE_RECORDS:], 1):
        if type(record) is not tuple or len(record) != 3:
            _reject()
        label, framed, payload = record
        expected_label = f"TL{case:02d}"
        if label != expected_label or type(framed) is not bytes or type(payload) is not bytes:
            _reject()
        if framed != expected_label.encode("ascii") + b": [" + payload + b"]\n":
            _reject()
        validate_payload(payload, case)
        units += len(framed) - 1  # One LF already reserved by the capture guard.
    if units > MAX_MESSAGE_UNITS:
        _reject()
    return {"records": RECORD_COUNT, "message_units": units}

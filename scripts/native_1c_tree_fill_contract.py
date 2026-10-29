"""Strict standalone FillValues observation grammar; no assumed action semantics."""

CASE_COUNT = 32
SNAPSHOT_SIZE = 59
PAYLOAD_SIZE = 1 + 3 * SNAPSHOT_SIZE
MAX_OUTPUT_BYTES = 8192
SCALARS = frozenset('ULTF01234567abcdefghij')
REFERENCES = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwx'


class ObservationError(ValueError):
    pass


def reject():
    raise ObservationError('tree_fill_observation_invalid')


def baseline(case):
    if case in (6, 7):
        cells = ('EE' if case == 6 else 'NN') + '.' * 48
    else:
        cells = 'BB' + ''.join(str(p + 1) + '_' + ('0_' if case in (29, 30, 32) else 'b_')
                              + ('c_' if p in (0, 2, 3) else 'd_') + 'e_' for p in range(6))
    tail = {25: 'S01i_....', 26: 'U01U_....', 27: 'L01L_....',
            28: 'B01T_....', 29: 'S01j_....', 30: 'S01h_....',
            31: 'R01P0....', 32: 'B01T_....'}.get(case, 'N014_....')
    return cells + tail


def cell(value):
    if len(value) != 2:
        reject()
    if value[0] in SCALARS and value[1] == '_':
        return ('scalar', value[0])
    if value[0] in 'PQR' and value[1] in REFERENCES:
        return ('reference', value[0], REFERENCES.index(value[1]))
    reject()


def snapshot(text, case):
    if len(text) != SNAPSHOT_SIZE:
        reject()
    if case in (6, 7):
        if text[:50] != baseline(case)[:50]:
            reject()
        values = ()
    else:
        if text[:2] != 'BB':
            reject()
        values = tuple(cell(text[p:p + 2]) for p in range(2, 50, 2))
    if case == 31:
        if text[50:53] != 'R01' or text[53:55] not in ('P0', 'Q0', 'R0') or text[55:] != '....':
            reject()
    elif text[50:] != baseline(case)[50:]:
        reject()
    return values


def validate_payload(payload, case):
    if type(case) is not int or not 1 <= case <= CASE_COUNT or type(payload) is not bytes:
        reject()
    try:
        text = payload.decode('ascii')
    except UnicodeDecodeError:
        reject()
    if len(text) != PAYLOAD_SIZE or text[0] not in 'SE':
        reject()
    before, after, shared = (text[1 + i * SNAPSHOT_SIZE:1 + (i + 1) * SNAPSHOT_SIZE] for i in range(3))
    if before != baseline(case):
        reject()
    decoded = tuple(snapshot(value, case) for value in (before, after, shared))
    # The emitter's registry is append-only across before/after/shared. Source
    # case31 registers reference0 after the first cell scan, even if no cells
    # reference it. Reject identities the emitter cannot actually produce.
    next_reference = 0
    for cells, raw_snapshot in zip(decoded, (before, after, shared)):
        marks = {}
        references = [item for item in cells if item[0] == 'reference']
        if case == 31:
            references.append(('reference', raw_snapshot[53], 0))
        for _, mark, identity in references:
            if identity > next_reference:
                reject()
            if identity == next_reference:
                next_reference += 1
            if identity in marks and marks[identity] != mark:
                reject()
            marks[identity] = mark
    if case != 31 and after != shared:
        reject()
    if case == 31 and shared[50:] != 'R01Q0....':
        reject()
    if case == 31:
        # Between these scans the observer changes only Source.Mark. No tree
        # operation runs: scalar cells and every non-source reference must
        # remain unchanged, while all aliases of source identity0 see Q.
        expected_shared = tuple(('reference', 'Q', 0)
                                if item[0] == 'reference' and item[2] == 0 else item
                                for item in decoded[1])
        if decoded[2] != expected_shared:
            reject()
    return {'case': case, 'outcome': 'success' if text[0] == 'S' else 'exception',
            'before': decoded[0], 'after': decoded[1], 'shared': decoded[2]}


API_CASE_COUNT = 16
API_PAYLOAD_SIZE = 1 + API_CASE_COUNT * 5


def validate_api_payload(payload):
    if type(payload) is not bytes or len(payload) != API_PAYLOAD_SIZE or payload[:1] != b'1':
        reject()
    observations = []
    for case in range(1, API_CASE_COUNT + 1):
        value = payload[1 + (case - 1) * 5:1 + case * 5]
        if value[0] not in b'SMAO' or value[1] not in b'U01234R' or any(c not in b'01234' for c in value[2:]):
            reject()
        if value[0] != ord('S') and value[1] != ord('U'):
            reject()
        observations.append((case, value.decode('ascii')))
    return tuple(observations)


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES or b'\r' in raw:
        reject()
    lines = raw.splitlines(keepends=True)
    if len(lines) != CASE_COUNT + 2 or lines[0] != b'TF-C: [-]\n':
        reject()
    answers = []
    for case, line in enumerate(lines[1:CASE_COUNT + 1], 1):
        prefix = f'TF-{case}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n'):
            reject()
        answers.append(validate_payload(line[len(prefix):-2], case))
    line = lines[-1]
    if not line.startswith(b'TF-A: [') or not line.endswith(b']\n'):
        reject()
    validate_api_payload(line[7:-2])
    return tuple(answers)

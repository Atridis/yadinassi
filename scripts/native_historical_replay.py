"""Source-bound complete Windows replay; live CI runs full current source."""
import hashlib

# Windows capture 4a3f55f8 predates the final cache and field-reference probes.
# Keep its entire source and output coverage; never truncate observed output.
HISTORICAL_COLLECTIONS_BLOB = "137dca5e4b6a47ea083a0dfe989e07c22d91a9e6"
HISTORICAL_COLLECTIONS_OUTPUT_BLOB = "97e90791a4011bd7f6ef2922533f92f698557cbd"
FINAL_PROBE_BLOCKS = (
    ("// Начало заключительных проб пустой строки кэша списка.\n",
     "// Конец заключительных проб пустой строки кэша списка.\n\n"),
    ("// Начало заключительных наблюдений пустой строки кэша списка.\n",
     "// Конец заключительных наблюдений пустой строки кэша списка.\n"),
)


FIELD_REFERENCE_BLOCKS = (
    ("// Begin ValueList field reference helpers.\n",
     "// End ValueList field reference helpers.\n\n"),
    ("// Begin ValueList field reference observations.\n",
     "// End ValueList field reference observations.\n"),
)


def without_field_reference_probes(text):
    """Remove only the pending additions; callers retain historical hash binding."""
    for start, end in FIELD_REFERENCE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("field reference probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


DESCRIPTOR_MAP_PROBE_BLOCKS = (
    ('// Begin descriptor Map-key checkpoint helpers.\n',
     '// End descriptor Map-key checkpoint helpers.\n\n'),
    ('// Begin descriptor Map-key checkpoint observations.\n',
     '// End descriptor Map-key checkpoint observations.\n'),
)


def without_descriptor_map_probes(text):
    """Restore every byte of the native-verified 797-message source."""
    for start, end in DESCRIPTOR_MAP_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('descriptor map probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'f8a5be47e937e39500c51a2b9c8fdaaf4becd68aa908cf7e99abe068a6c8cd4a':
        raise ValueError('descriptor map baseline source binding changed')
    return text


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def historical_collections_source(source, output):
    """Exact source-bound replay, not a current-output prefix exception.

    The complete current scenario is separately mandatory in live Docker CI.
    Only line-ending transport is normalized, including for source binding.
    """
    source = source.replace(b"\r\n", b"\n")
    output = output.replace(b"\r\n", b"\n")
    if git_blob(output) != HISTORICAL_COLLECTIONS_OUTPUT_BLOB:
        raise ValueError("historical collections output binding changed")
    text = without_field_reference_probes(without_descriptor_map_probes(source.decode("utf-8-sig")))
    for start, end in FINAL_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("historical collections probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    replay = ("\ufeff" + text).encode("utf-8")
    if git_blob(replay) != HISTORICAL_COLLECTIONS_BLOB:
        raise ValueError("historical collections source binding changed")
    return replay



# The six historical Windows captures are immutable. Live CI executes all probes.
HISTORICAL_VALUES_BLOB = '5b7f3976c2d6de30930c83063079d7e2e41317e5'
HISTORICAL_VALUES_OUTPUT_BLOB = '016f30d6f3bdb1a814e86a70e3bcf424383a0d27'
CHARS_PROBE_BLOCKS = (('// Begin Chars namespace helpers.\n', '// End Chars namespace helpers.\n\n'), ('// Begin Chars namespace observations.\n', '// End Chars namespace observations.\n'))


def without_chars_probes(text):
    """Remove only bounded Chars additions; historical caller checks exact hash."""
    for start, end in CHARS_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("Chars probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


FIXED_STRING_PROBE_BLOCKS = (
    ('// Begin fixed String default helpers.\n', '// End fixed String default helpers.\n\n'),
    ('// Begin fixed String default observations.\n', '// End fixed String default observations.\n'),
)


SERVICE_FILLED_PROBE_BLOCK = (
    '// Begin service ValueIsFilled observations.\n',
    '// End service ValueIsFilled observations.\n',
)


def without_service_filled_probes(text):
    """Restore the exact native-verified 377-record source, not an output prefix."""
    start, end = SERVICE_FILLED_PROBE_BLOCK
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("service filled probe boundaries changed")
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'eaf36b0deed933ea1c3eabcfbde0be59f2f1d8bf6b07b5533f4df2e8cc967b45':
        raise ValueError("service filled baseline source binding changed")
    return text


def without_fixed_string_probes(text):
    """Restore the exact native-verified 361-record Chars source."""
    if any(boundary in text for boundary in SERVICE_FILLED_PROBE_BLOCK):
        text = without_service_filled_probes(text)
    for start, end in FIXED_STRING_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("fixed String probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '5fd00b472332044f4bae4c12973bcc66c074b27f7c98fe58b21b149088166fff':
        raise ValueError("fixed String baseline source binding changed")
    return text


def historical_values_source(source, output):
    """Reconstruct every byte of original values source, never an output prefix."""
    source = source.replace(b"\r\n", b"\n")
    output = output.replace(b"\r\n", b"\n")
    if git_blob(output) != HISTORICAL_VALUES_OUTPUT_BLOB:
        raise ValueError("historical values output binding changed")
    replay = without_chars_probes(without_fixed_string_probes(source.decode("utf-8"))).encode("utf-8")
    if git_blob(replay) != HISTORICAL_VALUES_BLOB:
        raise ValueError("historical values source binding changed")
    return replay


# Windows dates capture predates the appended fixed-GMT fractional probes.
HISTORICAL_DATES_BLOB = '1527fe4c52feab97bc6ed8ba007cf664b4565cc6'
CURRENT_DATES_BLOB = 'd6d03bd014466f41d49ab566c003ac680cd052b2'
HISTORICAL_DATES_OUTPUT_BLOB = '05d23c46540b301820f2ac81c8a67fc0e1273dc8'

def historical_dates_source(source: bytes, output: bytes) -> bytes:
    """Reconstruct the exact captured source, never filter observed output."""
    source = source.replace(b'\r\n', b'\n')
    output = output.replace(b'\r\n', b'\n')
    if git_blob(source) != CURRENT_DATES_BLOB or git_blob(output) != HISTORICAL_DATES_OUTPUT_BLOB:
        raise ValueError('Historical dates source/output identity mismatch')
    historical = source[:15403]
    if git_blob(historical) != HISTORICAL_DATES_BLOB:
        raise ValueError('Historical dates reconstruction mismatch')
    return historical


# Windows numbers capture predates the exact-half division source-only suffix.
HISTORICAL_NUMBERS_BLOB = 'abc35547f3603ce67e958a127aeb2f3bb42acca3'
CURRENT_NUMBERS_BLOB = '25931bcb4a9636c6fcf22b16cb9023a243708751'
HISTORICAL_NUMBERS_OUTPUT_BLOB = 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13'


def historical_numbers_source(source: bytes, output: bytes) -> bytes:
    """Replay all 350 captured observations against their exact original source."""
    source = source.replace(b'\r\n', b'\n')
    output = output.replace(b'\r\n', b'\n')
    if git_blob(source) != CURRENT_NUMBERS_BLOB or git_blob(output) != HISTORICAL_NUMBERS_OUTPUT_BLOB:
        raise ValueError('Historical numbers source/output identity mismatch')
    historical = source[:42360]
    if git_blob(historical) != HISTORICAL_NUMBERS_BLOB:
        raise ValueError('Historical numbers reconstruction mismatch')
    return historical

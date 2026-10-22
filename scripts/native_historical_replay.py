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
    text = without_field_reference_probes(source.decode("utf-8-sig"))
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


def historical_values_source(source, output):
    """Reconstruct every byte of original values source, never an output prefix."""
    source = source.replace(b"\r\n", b"\n")
    output = output.replace(b"\r\n", b"\n")
    if git_blob(output) != HISTORICAL_VALUES_OUTPUT_BLOB:
        raise ValueError("historical values output binding changed")
    replay = without_chars_probes(source.decode("utf-8")).encode("utf-8")
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

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


FILL_EXCLUDE_ORDER_PROBE_BLOCKS = (
    ('// Begin FillPropertyValues EXCLUDE source-order discriminator helpers.\n',
     '// End FillPropertyValues EXCLUDE source-order discriminator helpers.\n\n'),
    ('// Begin FillPropertyValues EXCLUDE source-order discriminator observations.\n',
     '// End FillPropertyValues EXCLUDE source-order discriminator observations.\n'),
)


TREE_FINDROWS_HELPERS_START = '// Begin bounded ValueTree FindRows helpers (measurement only; no native answers).\n'
TREE_FINDROWS_HELPERS_END = '// End bounded ValueTree FindRows helpers.\n\n'
TREE_FINDROWS_CALLS_START = '// Begin bounded ValueTree FindRows observations (measurement only; no native answers).\n'
TREE_FINDROWS_CALLS_END = '// End bounded ValueTree FindRows observations.\n'


def without_tree_findrows_probes(text):
    """Exact source-only collections902 -> 866 inverse; never edit native output."""
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782':
        raise ValueError('tree FindRows source binding changed')
    if not text.endswith(TREE_FINDROWS_CALLS_END):
        raise ValueError('tree FindRows tail changed')
    for begin, end in ((TREE_FINDROWS_HELPERS_START, TREE_FINDROWS_HELPERS_END),
                       (TREE_FINDROWS_CALLS_START, TREE_FINDROWS_CALLS_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError('tree FindRows boundaries changed')
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != 'b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27':
        raise ValueError('tree FindRows baseline binding changed')
    return text


VALUE_TREE_START = '// Begin bounded ValueTree core observations (candidate; not native evidence).\n'
VALUE_TREE_END = '// End bounded ValueTree core observations.\n'


def without_value_tree_probes(text):
    """Exact source inverse for old captures only; never truncate native output."""
    if TREE_FINDROWS_HELPERS_START in text or TREE_FINDROWS_CALLS_START in text:
        text = without_tree_findrows_probes(text)
    raw = text.encode('utf-8-sig') if not text.startswith('\ufeff') else text.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != 'b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27':
        raise ValueError('value tree source binding changed')
    if text.count(VALUE_TREE_START) != 1 or text.count(VALUE_TREE_END) != 1 or not text.endswith(VALUE_TREE_END):
        raise ValueError('value tree boundaries changed')
    result = text.split(VALUE_TREE_START, 1)[0]
    raw = result.encode('utf-8-sig') if not result.startswith('\ufeff') else result.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != '42c1fedddb8a689f3ba2ca6a241b1d19d38c0bea4da8a29e5934b3082a43fdfb':
        raise ValueError('value tree baseline binding changed')
    return result


def without_fill_exclude_order_probes(text):
    """Restore the exact 852-record PR87 source, never truncate native outputs."""
    if VALUE_TREE_START in text or VALUE_TREE_END in text:
        text = without_value_tree_probes(text)
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != '42c1fedddb8a689f3ba2ca6a241b1d19d38c0bea4da8a29e5934b3082a43fdfb':
        raise ValueError('fill exclude order source binding changed')
    for start, end in FILL_EXCLUDE_ORDER_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('fill exclude order probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9':
        raise ValueError('fill exclude order baseline binding changed')
    return text


FILL_EXCLUDE_PROBE_BLOCKS = (
    ('// Begin FillPropertyValues EXCLUDE checkpoint helpers.\n',
     '// End FillPropertyValues EXCLUDE checkpoint helpers.\n\n'),
    ('// Begin FillPropertyValues EXCLUDE checkpoint observations.\n',
     '// End FillPropertyValues EXCLUDE checkpoint observations.\n'),
)


def without_fill_exclude_probes(text):
    """Restore all 841 records' source; never truncate observed output."""
    if any(boundary in text for pair in FILL_EXCLUDE_ORDER_PROBE_BLOCKS for boundary in pair):
        text = without_fill_exclude_order_probes(text)
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9':
        raise ValueError('fill exclude source binding changed')
    for start, end in FILL_EXCLUDE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('fill exclude probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232':
        raise ValueError('fill exclude baseline source binding changed')
    return text


FILL_INCLUDE_PROBE_BLOCKS = (
    ('// Begin FillPropertyValues INCLUDE checkpoint helpers.\n',
     '// End FillPropertyValues INCLUDE checkpoint helpers.\n\n'),
    ('// Begin FillPropertyValues INCLUDE checkpoint observations.\n',
     '// End FillPropertyValues INCLUDE checkpoint observations.\n'),
)


def without_fill_include_probes(text):
    """Restore all 828 native-verified records' source with an exact byte pin."""
    if any(boundary in text for pair in (*FILL_EXCLUDE_ORDER_PROBE_BLOCKS, *FILL_EXCLUDE_PROBE_BLOCKS) for boundary in pair):
        text = without_fill_exclude_probes(text)
    for start, end in FILL_INCLUDE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('fill include probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'b3bf181de84a575335ce7e4794ced459ad252eb7853cc42095fb62521dc6a409':
        raise ValueError('fill include baseline source binding changed')
    return text


DESCRIPTOR_MAP_PROBE_BLOCKS = (
    ('// Begin descriptor Map-key checkpoint helpers.\n',
     '// End descriptor Map-key checkpoint helpers.\n\n'),
    ('// Begin descriptor Map-key checkpoint observations.\n',
     '// End descriptor Map-key checkpoint observations.\n'),
)


def without_descriptor_map_probes(text):
    """Restore every byte of the native-verified 797-message source."""
    if any(boundary in text for pair in FILL_INCLUDE_PROBE_BLOCKS for boundary in pair):
        text = without_fill_include_probes(text)
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


NSTR_PROBE_BLOCKS = (
    ('// Begin bounded NStr helpers (measurement only; no native answers).\n', '// End bounded NStr helpers.\n\n'),
    ('// Begin bounded NStr observations (measurement only; no native answers).\n', '// End bounded NStr observations.\n'),
)


NSTR_DISCRIMINATOR_BLOCK = (
    '// Begin bounded NStr discriminators (measurement only; no native answers).\n',
    '// End bounded NStr discriminators.\n',
)


def without_nstr_discriminators(text):
    """Exact values534-to-521 source inverse; never edit any native output."""
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5':
        raise ValueError('NStr discriminator candidate source binding changed')
    start, end = NSTR_DISCRIMINATOR_BLOCK
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('NStr discriminator boundaries changed')
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '9e1af33c93352aebf9166bf5f702f526f221df7e9945ba139ccbc3d1fd0a34e4':
        raise ValueError('NStr discriminator historical source binding changed')
    return text


def without_nstr_probes(text):
    """Exact values521-to-485 source inverse; never filter output or admit old input."""
    if any(boundary in text for boundary in NSTR_DISCRIMINATOR_BLOCK):
        text = without_nstr_discriminators(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '9e1af33c93352aebf9166bf5f702f526f221df7e9945ba139ccbc3d1fd0a34e4':
        raise ValueError('NStr candidate source binding changed')
    for start, end in NSTR_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('NStr probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76':
        raise ValueError('NStr historical source binding changed')
    return text


TEXT_DOCUMENT_PROBE_BLOCKS = (
    ('// Begin bounded TextDocument helpers (measurement only; no native answers).\n', '// End bounded TextDocument helpers.\n\n\n'),
    ('// Begin bounded TextDocument observations (measurement only; no native answers).\n', '// End bounded TextDocument observations.\n'),
)


def without_text_document_probes(text):
    """Restore exact values441 source; never filter outputs or admit old source."""
    if any(boundary in text for pair in NSTR_PROBE_BLOCKS for boundary in pair):
        text = without_nstr_probes(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76':
        raise ValueError('TextDocument candidate source binding changed')
    for start, end in TEXT_DOCUMENT_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('TextDocument probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c':
        raise ValueError('TextDocument historical source binding changed')
    return text


UUID_PROBE_BLOCKS = (
    ('// Begin bounded UUID codec helpers (candidate; not native evidence).\n', '// End bounded UUID codec helpers.\n\n'),
    ('// Begin bounded UUID codec observations (candidate; not native evidence).\n', '// End bounded UUID codec observations.\n'),
    ('// Begin bounded UUID helpers (candidate; not native evidence).\n', '// End bounded UUID helpers.\n\n'),
    ('// Begin bounded UUID observations (candidate; not native evidence).\n', '// End bounded UUID observations.\n'),
)


def without_uuid_probes(text):
    """Offline historical replay only; exact input/output hashes, never admission."""
    if any(boundary in text for pair in TEXT_DOCUMENT_PROBE_BLOCKS for boundary in pair):
        text = without_text_document_probes(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c':
        raise ValueError('UUID candidate source binding changed')
    for start, end in UUID_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('UUID probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12':
        raise ValueError('UUID historical source binding changed')
    return text


def without_service_filled_probes(text):
    """Restore the exact native-verified 377-record source, not an output prefix."""
    if any(boundary in text for pair in UUID_PROBE_BLOCKS for boundary in pair):
        text = without_uuid_probes(text)
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


# Only the new exception source is removed for the complete frozen 88-record replay.
# Native full-suite runs never call this projection and always execute all probes.
HISTORICAL_FUNCTIONS_BLOB = 'c83e860364555a0f6290e3b34d7cf8a8eb40df9f'
HISTORICAL_FUNCTIONS_OUTPUT_BLOB = '6df192ac9d10c07755948d7c14cfed9e2311c65f'
EXTENDED_EXCEPTION_PROBE_BLOCKS = (
    ('// Begin extended exception checkpoint helpers.\n',
     '// End extended exception checkpoint helpers.\n\n'),
    ('// Begin extended exception checkpoint observations.\n',
     '// End extended exception checkpoint observations.\n'),
)


def without_extended_exception_probes(text):
    """Restore the exact complete source of all 88 historical function records."""
    if any(boundary in text for pair in EXCEPTION_CONTEXT_PROBE_BLOCKS for boundary in pair):
        text = without_exception_context_probes(text)
    for start, end in EXTENDED_EXCEPTION_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('extended exception probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != HISTORICAL_FUNCTIONS_BLOB:
        raise ValueError('extended exception baseline source binding changed')
    return text


def historical_functions_source(source, output):
    """Replay the complete immutable Windows capture, not an output-prefix pass."""
    source = source.replace(b'\r\n', b'\n')
    output = output.replace(b'\r\n', b'\n')
    if git_blob(output) != HISTORICAL_FUNCTIONS_OUTPUT_BLOB:
        raise ValueError('historical functions output binding changed')
    return without_extended_exception_probes(source.decode('utf-8')).encode('utf-8')


EXCEPTION_CONTEXT_BASE_BLOB = '540d0fa68f212cef2963da7e1e59565a0a56edb6'
EXCEPTION_CONTEXT_PROBE_BLOCKS = (
    ('// Begin exception context checkpoint helpers.\n',
     '// End exception context checkpoint helpers.\n\n'),
    ('// Begin exception context checkpoint observations.\n',
     '// End exception context checkpoint observations.\n'),
)


def without_exception_context_probes(text):
    """Restore the exact 111-record source native-audited on PR88, not its output."""
    if any(boundary in text for pair in EXPORTED_VARIABLE_PROBE_BLOCKS for boundary in pair):
        text = without_exported_variable_probes(text)
    for start, end in EXCEPTION_CONTEXT_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exception context probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != EXCEPTION_CONTEXT_BASE_BLOB:
        raise ValueError('exception context baseline source binding changed')
    return text


EXPORTED_VARIABLE_BASE_BLOB = '6a56f0f5bbca057bbdd9d9f339ab5a0c59d90650'
EXPORTED_VARIABLE_PROBE_BLOCKS = (('// Begin exported variable checkpoint declarations.\n', '// End exported variable checkpoint declarations.\n\n'), ('// Begin exported variable checkpoint helpers.\n', '// End exported variable checkpoint helpers.\n\n'), ('// Begin exported variable checkpoint observations.\n', '// End exported variable checkpoint observations.\n'))

def without_exported_variable_probes(text):
    """Exact prior 116-record source, never a native-output truncation."""
    if any(boundary in text for pair in EXPORTED_CONTEXT_PROBE_BLOCKS for boundary in pair):
        text = without_exported_context_probes(text)
    for start, end in EXPORTED_VARIABLE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exported variable probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != EXPORTED_VARIABLE_BASE_BLOB:
        raise ValueError('exported variable baseline source binding changed')
    return text


EXPORTED_CONTEXT_BASE_BLOB = '0c0cfae158f10fec2343992fbbc7642cd5ced6bc'
EXPORTED_CONTEXT_PROBE_BLOCKS = (
    ('// Begin exported variable discriminator helpers.\n',
     '// End exported variable discriminator helpers.\n\n'),
    ('// Begin exported variable discriminator observations.\n',
     '// End exported variable discriminator observations.\n'),
)


def without_exported_context_probes(text):
    """Restore the complete native-audited PR89 131-record source, not output."""
    if ("NativePostCreate" in text or any(
            boundary in text for pair in EXPORTED_POSTCREATE_PROBE_BLOCKS for boundary in pair)):
        text = without_exported_postcreate_probes(text)
    for start, end in EXPORTED_CONTEXT_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exported context probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != EXPORTED_CONTEXT_BASE_BLOB:
        raise ValueError('exported context baseline source binding changed')
    return text


EXPORTED_POSTCREATE_DIRECTIVE = '// NativePostCreate: ExportProbeAfterCreate\n'
EXPORTED_POSTCREATE_BASE_BLOB = '259abc1315cbcca8642e1a49b44f4ac24a33500e'
EXPORTED_POSTCREATE_BASE_SHA256 = 'c6b33e07818ce7e4abd8153feb3d8538d48737d5a543312b18f1fb8e7c5a65cd'
EXPORTED_POSTCREATE_PROBE_BLOCKS = (
    ('// Begin exported variable post-create declarations.\n',
     '// End exported variable post-create declarations.\n\n'),
    ('// Begin exported variable post-create helpers.\n',
     '// End exported variable post-create helpers.\n\n'),
)


def without_exported_postcreate_probes(text):
    """Restore every byte of the audited 136-record source, never its output."""
    if any(boundary in text for pair in TRAILING_OMITTED_PROBE_BLOCKS for boundary in pair):
        text = without_trailing_omitted_probes(text)
    if not text.startswith(EXPORTED_POSTCREATE_DIRECTIVE) or text.count(EXPORTED_POSTCREATE_DIRECTIVE) != 1:
        raise ValueError('exported post-create directive changed')
    text = text[len(EXPORTED_POSTCREATE_DIRECTIVE):]
    for start, end in EXPORTED_POSTCREATE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exported post-create probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if (git_blob(raw) != EXPORTED_POSTCREATE_BASE_BLOB
            or hashlib.sha256(raw).hexdigest() != EXPORTED_POSTCREATE_BASE_SHA256):
        raise ValueError('exported post-create baseline source binding changed')
    return text


# Measurement-only additions to the complete 136-record initialization source.
# This projection is only for historical/checkpoint replay, never live comparison.
TRAILING_OMITTED_BASE_BLOB = '0393cf93cf5380b0231a9b36ce067e3af682d532'
TRAILING_OMITTED_BASE_SHA256 = '21d53297530d86c260b75659f7fdab2e35acddf82e53ab9056f9991a4195a3ab'
TRAILING_OMITTED_SOURCE_SHA256 = 'b1862eb7569e23e054c4abc14711a4faa53b1e26fd16212502317e592caf98a3'
TRAILING_OMITTED_PROBE_BLOCKS = (
    ('// Begin trailing omitted argument checkpoint declarations.\n',
     '// End trailing omitted argument checkpoint declarations.\n\n'),
    ('// Begin trailing omitted argument checkpoint helpers.\n',
     '// End trailing omitted argument checkpoint helpers.\n\n'),
    ('// Begin trailing omitted argument checkpoint observations.\n',
     '// End trailing omitted argument checkpoint observations.\n'),
)


def without_trailing_omitted_probes(text):
    """Restore every byte of the prior source; never trim observed output."""
    if any(boundary in text for boundary in TRAILING_OMITTED_DIRECT_BLOCK):
        text = without_trailing_omitted_direct_probe(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != TRAILING_OMITTED_SOURCE_SHA256:
        raise ValueError('trailing omitted source binding changed')
    for start, end in TRAILING_OMITTED_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('trailing omitted probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if (git_blob(raw) != TRAILING_OMITTED_BASE_BLOB
            or hashlib.sha256(raw).hexdigest() != TRAILING_OMITTED_BASE_SHA256):
        raise ValueError('trailing omitted baseline source binding changed')
    return text


# The fresh literal positive witness adds no output and has an exact inverse to
# the independently audited Execute measurement, whose source pin stays intact.
TRAILING_OMITTED_DIRECT_SOURCE_SHA256 = 'b180494a704f59bc959cc07afecb9e568cd0fa64bb73109e45f7ae52b003bfbb'
TRAILING_OMITTED_DIRECT_BLOCK = (
    '    // Begin trailing omitted direct positive witness.\n',
    '    // End trailing omitted direct positive witness.\n',
)


def without_trailing_omitted_direct_probe(text):
    """Restore the complete captured measurement source, not projected output."""
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != TRAILING_OMITTED_DIRECT_SOURCE_SHA256:
        raise ValueError('trailing omitted direct source binding changed')
    start, end = TRAILING_OMITTED_DIRECT_BLOCK
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('trailing omitted direct boundaries changed')
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    result = before + after
    old_note = '// Measurement only: native expected token remains unknown until audited capture.'
    new_note = '// Audited Execute token retained; the direct positive witness requires fresh native validation.'
    if result.count(new_note) != 1:
        raise ValueError('trailing omitted direct observation note changed')
    result = result.replace(new_note, old_note, 1)
    if hashlib.sha256(result.encode('utf-8')).hexdigest() != TRAILING_OMITTED_SOURCE_SHA256:
        raise ValueError('trailing omitted captured source binding changed')
    return result

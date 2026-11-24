"""Closed UTF-8/UTF-16 qualifier witness for optional SQL proofs."""


def valid_utf8_text(value, unit_limit):
    # SQLite receives a bounded BLOB. Strict decoding rejects ill-formed
    # UTF-8, including surrogate encodings. Unlike fetching TEXT, an invalid
    # encoding cannot raise in the driver before this proof chooses its residual.
    try:
        text = value.decode('utf-8')
    except UnicodeDecodeError:
        return 0
    # SQL length(TEXT) stops at NUL; handling it still needs the residual
    # so that its Python character budget and error order stay authoritative.
    if '\0' in text:
        return 0
    return int(len(text.encode('utf-16-le')) <= 2 * unit_limit)


def text_check(column, length, *, nonempty=False):
    bytes_ = f'CAST({column} AS BLOB)'
    chars = f'length({column})'
    size = f'length({bytes_})'
    # Keep ordinary ASCII callback-free. For the bounded Unicode branch
    # require UTF-8 database encoding inside this statement (CAST uses the
    # database's encoding, not Python's), and never decode oversized blobs.
    return (f"CASE WHEN typeof({column})!='text' OR {chars} NOT BETWEEN {int(nonempty)} AND {length} THEN 0 "
            f"WHEN {size}={chars} AND {column} NOT GLOB '*[^ -~]*' THEN 1 "
            f"WHEN {size}>{3*length} OR CAST('a' AS BLOB)!=x'61' THEN 0 "
            f"ELSE yadinassi_valid_utf8_text_v1({bytes_},{length}) END")

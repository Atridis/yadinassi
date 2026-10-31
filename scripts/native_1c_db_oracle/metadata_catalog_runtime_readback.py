"""Public BSL adapter readback for an already frozen, owned native postimage.

This does not launch 1C or establish quiescence/integrity. Acquisition must call
it inside inspect_frozen_catalog's before/after hash and quiescence envelope,
then bind that summary to the native postimage. Unlike CONFIG projection this
path deliberately opens the image through actual FileDBContext + Interpreter.
The full unchanged source probe is executed: excluded Attribute controls remain
visible, and never contribute to a claimed 24-case API agreement.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import metadata_catalog_probe_contract as wire

PROBE_SHA256 = 'acb83b5ae6e5de3630cce70fe1214f9027439e8ee505a52a29e7697a3d5f5785'
SUPPORTED_IDS = tuple(i for i in range(1, 27) if i not in (7, 8))
EXCLUDED = {7: 'Attributes API not implemented; native applied-view discriminator only',
            8: 'Attributes API not implemented; native applied-view discriminator only'}


def _execute(context):
    """Whole original probe; context injection is solely the unit-test seam."""
    from yadinassi import Interpreter
    from yadinassi.native_targets import LINUX_8_3_27_1508
    path = Path(__file__).with_name('modules') / 'MetadataCatalogProbe.bsl'
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != PROBE_SHA256:
        raise ValueError('metadata runtime probe source changed')
    output = []
    interpreter = Interpreter(output=output.append, database_context=context,
                              native_target=LINUX_8_3_27_1508)
    try:
        interpreter.execute(source.decode('utf-8'), source='MetadataCatalogProbe.bsl')
    finally:
        interpreter.close()
    raw = ('\n'.join(output) + '\n').encode('ascii')
    wire.validate_output(raw)
    return raw


def compare_readback(actual_wire: bytes, native_wire: bytes) -> dict:
    actual = wire.validate_output(actual_wire)
    native = wire.require_available(native_wire)
    if any(row['status'] == 'observer-error' for row in actual):
        raise ValueError('metadata runtime observer failed')
    matched = [i for i in SUPPORTED_IDS if actual[i-1] == native[i-1]]
    mismatched = [i for i in SUPPORTED_IDS if i not in matched]
    return {'supported_ids': list(SUPPORTED_IDS), 'matched_ids': matched,
            'mismatched_ids': mismatched, 'supported_match': not mismatched,
            'excluded_controls': [{'id': i, 'reason': EXCLUDED[i],
                'runtime_status': actual[i-1]['status'],
                'native_status': native[i-1]['status']} for i in EXCLUDED]}


def readback(database: Path, *, native_wire: bytes) -> dict:
    """No expected native values are supplied to the runtime/CONFIG adapter."""
    from yadinassi.database_context import FileDBContext
    wire.require_available(native_wire)
    actual = _execute(FileDBContext(database))
    return {'probe_sha256': PROBE_SHA256, 'wire': actual.decode('ascii'),
            'comparison': compare_readback(actual, native_wire)}

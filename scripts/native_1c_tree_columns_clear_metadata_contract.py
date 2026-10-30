"""CD3 uses unchanged CC snapshots; only setup, never reset answers, is gated."""
import importlib.util
from pathlib import Path

_spec=importlib.util.spec_from_file_location('tree_columns_clear_metadata_basis',
    Path(__file__).with_name('native_1c_tree_columns_clear_contract.py'))
_basis=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_basis)
ObservationError=_basis.ObservationError
AvailabilityError=_basis.AvailabilityError
CASE_COUNT=3
MAX_OUTPUT_BYTES=8192
CALIBRATION_RECORD=b'CD-C1: [-]\n'
snapshot_size=_basis.snapshot_size


def need(condition):
    if not condition:raise ObservationError('tree_columns_clear_metadata_observation_invalid')


def maximum_record_size(case):
    need(type(case) is int and 1<=case<=CASE_COUNT)
    return _basis.maximum_record_size(1)


MAX_ENCODED_BYTES=len(CALIBRATION_RECORD)+sum(maximum_record_size(i) for i in range(1,4))


def validate_payload(payload,case):
    need(type(case) is int and 1<=case<=CASE_COUNT)
    result=_basis.validate_payload(payload,1)
    return {**result,'case':case}


def validate_output(raw):
    need(type(raw) is bytes and len(raw)<=MAX_OUTPUT_BYTES)
    need(all(c==10 or 32<=c<=126 for c in raw))
    lines=raw.splitlines(keepends=True);need(len(lines)==4 and lines[0]==CALIBRATION_RECORD)
    records=[]
    for case,line in enumerate(lines[1:],1):
        prefix=f'CD-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n') and len(line)<=maximum_record_size(case))
        records.append(validate_payload(line[len(prefix):-2],case))
    return tuple(records)


def setup_valid(records):
    before=records[2]['snapshots'][0]
    if not before['schema'] or not before['nodes']:return False
    column,metadata=before['schema'][0]
    queries=before['queries']
    # Independent active schema and original retained-reference queries prove
    # initialization. No case3 result/status/after metadata is prescribed.
    return (metadata[1:3]=='d9' and queries[14]==('I',column)
            and queries[16]==('W','d') and queries[17]==('N',9))


def controls_valid(records):
    return _basis.controls_valid(records) and setup_valid(records)


def require_available(raw):
    records=validate_output(raw)
    if not controls_valid(records):raise AvailabilityError('tree_columns_clear_metadata_positive_controls_failed')
    return records

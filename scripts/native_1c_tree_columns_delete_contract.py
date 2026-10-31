"""DL14: fixed Delete cases reuse CC snapshots, never CC lifetime conclusions."""
import importlib.util
from pathlib import Path

_spec=importlib.util.spec_from_file_location('tree_columns_delete_basis',
    Path(__file__).with_name('native_1c_tree_columns_clear_contract.py'))
_basis=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_basis)
ObservationError=_basis.ObservationError
AvailabilityError=_basis.AvailabilityError
CASE_COUNT=14
MAX_OUTPUT_BYTES=8192
CALIBRATION_RECORD=b'DL-C1: [-]\n'
# Only header shapes are shared: ordinary, expression, follow-up, phased rebuild.
_HEADER_CASES=(1,1,1,1,1,1,1,1,1,8,9,9,9,12)


def need(condition):
    if not condition:raise ObservationError('tree_columns_delete_observation_invalid')


def maximum_record_size(case):
    need(type(case) is int and 1<=case<=CASE_COUNT)
    return len(f'DL-{case}: [')+5+2+2*_basis.snapshot_size()+2


MAX_ENCODED_BYTES=len(CALIBRATION_RECORD)+sum(maximum_record_size(i) for i in range(1,CASE_COUNT+1))


def validate_payload(payload,case):
    need(type(case) is int and 1<=case<=CASE_COUNT)
    result=_basis.validate_payload(payload,_HEADER_CASES[case-1])
    return {**result,'case':case}


def validate_output(raw):
    need(type(raw) is bytes and len(raw)<=MAX_OUTPUT_BYTES)
    need(all(c==10 or 32<=c<=126 for c in raw))
    lines=raw.splitlines(keepends=True)
    need(len(lines)==CASE_COUNT+1 and lines[0]==CALIBRATION_RECORD)
    records=[]
    for case,line in enumerate(lines[1:],1):
        prefix=f'DL-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n') and len(line)<=maximum_record_size(case))
        records.append(validate_payload(line[len(prefix):-2],case))
    return tuple(records)


def setup_valid(records):
    for record in records:
        if record['case']==6:continue
        before=record['snapshots'][0]
        if not before['schema']:return False
        column,metadata=before['schema'][0]
        if (metadata[1:3]!='d9' or before['queries'][14]!=('I',column)
                or before['queries'][16:18]!=(('W','d'),('N',9))):return False
    return True


def controls_valid(records):
    # Positive EN/RU controls remove one selected column. Row lifetime and held
    # metadata remain independently observed, never inferred from Clear.
    for record in records[:2]:
        before,after=record['snapshots']
        if record['status']!='S' or len(before['schema'])!=2 or not before['nodes']:return False
        removed=before['schema'][0][0]
        if len(after['schema'])!=1 or any(column==removed for column,_ in after['schema']):return False
    return setup_valid(records)


def require_available(raw):
    records=validate_output(raw)
    if not controls_valid(records):raise AvailabilityError('tree_columns_delete_positive_controls_failed')
    return records

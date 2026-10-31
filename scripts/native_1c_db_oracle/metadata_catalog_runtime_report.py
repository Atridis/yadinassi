"""Separate bounded public-runtime envelope; original measurement policy retained."""
import copy
import json
import protocol
import metadata_catalog_inputs as baseline_inputs
import metadata_catalog_report as baseline
import metadata_catalog_runtime_inputs as inputs
from metadata_catalog_runtime_acquisition import MAX_READBACK_STATE_BYTES
from metadata_catalog_runtime_readback import PROBE_SHA256, compare_readback
from snapshots import OracleError

MAX_READBACKS_BYTES = 6 * MAX_READBACK_STATE_BYTES + 7
MAX_REPORT_BYTES = baseline.MAX_REPORT_BYTES + MAX_READBACKS_BYTES + 2048


def _encoded(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def _validate_postimage(value):
    # Python equality alone aliases integer byte counts with floats/booleans.
    # Enforce the same finite summary schema as native acquisition first.
    protocol.exact(value, ('bytes', 'sha256'))
    protocol.require(type(value['bytes']) is int and 0 < value['bytes'] <= 67108864
                     and protocol.digest(value['sha256']), 'invalid_marker')


def _measurement(value, provenance):
    result = {key: copy.deepcopy(item) for key, item in value.items()
              if key not in ('runtime_readbacks', 'runtime_identity')}
    result['lane'] = baseline_inputs.LANE
    expected = dict(provenance, sources={name: provenance['sources'][name]
                                       for name in baseline_inputs.SOURCE_FILES})
    result['lifecycle']['provenance']['sources'] = expected['sources']
    if result['measurement_failure'] is not None and result['measurement_failure']['phase'] == 'runtime':
        result['measurement_failure']['phase'] = 'reader'
    return result, expected


def empty_report(nonce, provenance):
    value = baseline.empty_report(nonce, provenance)
    value.update(lane=inputs.LANE, runtime_readbacks=[],
                 runtime_identity=inputs.runtime_identity(provenance))
    return value


def encode_report(value):
    protocol.encode(value['lifecycle'])
    protocol.require(type(value['runtime_readbacks']) is list and len(value['runtime_readbacks']) <= 6)
    protocol.require(all(len(_encoded(row)) <= MAX_READBACK_STATE_BYTES
                         for row in value['runtime_readbacks']), 'artifact_limit')
    protocol.require(len(_encoded(value['runtime_readbacks'])) <= MAX_READBACKS_BYTES, 'artifact_limit')
    measurement, _ = _measurement(value, value['lifecycle']['provenance'])
    baseline.encode_report(measurement)
    protocol.require(len(_encoded(value['runtime_identity'])) <= 2048, 'artifact_limit')
    raw = _encoded(value)
    protocol.require(len(raw) + 1 <= MAX_REPORT_BYTES, 'artifact_limit')
    return raw


def validate_report(raw, *, nonce, provenance, final=False):
    protocol.require(type(raw) is bytes and 0 < len(raw) <= MAX_REPORT_BYTES, 'artifact_limit')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=protocol.unique,
            parse_constant=lambda _: protocol.require(False))
    except (ValueError, UnicodeError, RecursionError):
        raise OracleError('transport_invalid') from None
    protocol.exact(value, ('schema','lane','lifecycle','states','verdict','helpers',
        'measurement_failure','runtime_readbacks','runtime_identity'))
    protocol.require(value['lane'] == inputs.LANE)
    inputs.validate_source_identity(provenance)
    protocol.validate_report(protocol.encode(value['lifecycle']), nonce=nonce,
                             provenance=provenance, final=final)
    protocol.require(value['runtime_identity'] == inputs.runtime_identity(provenance), 'provenance_mismatch')
    failure = value['measurement_failure']
    if failure is not None:
        protocol.exact(failure, ('snapshot','context','phase'))
        protocol.require(failure['phase'] in ('origin','native','freeze','reader','runtime','postimage','cleanup','compare'))
    measurement, expected = _measurement(value, provenance)
    baseline.validate_report(baseline.encode_report(measurement), nonce=nonce,
                             provenance=expected, final=final)
    rows = value['runtime_readbacks']
    protocol.require(type(rows) is list and len(rows) == len(value['states']))
    for native, actual in zip(value['states'], rows):
        protocol.exact(actual, ('snapshot','context','token','postimage','probe_sha256','wire','comparison'))
        _validate_postimage(actual['postimage'])
        protocol.require(all(actual[key] == native[key] for key in ('snapshot','context','token','postimage')),
                         'snapshot_changed')
        protocol.require(actual['probe_sha256'] == PROBE_SHA256, 'provenance_mismatch')
        protocol.require(type(actual['wire']) is str)
        try:
            comparison = compare_readback(actual['wire'].encode('ascii'), native['wire'].encode('ascii'))
        except (ValueError, UnicodeError):
            raise OracleError('invalid_marker') from None
        protocol.require(json.dumps(actual['comparison'], sort_keys=True, allow_nan=False)
            == json.dumps(comparison, sort_keys=True, allow_nan=False), 'logical_mismatch')
        if value['lifecycle']['status'] == 'ok':
            protocol.require(comparison['supported_match'], 'logical_mismatch')
    if value['lifecycle']['status'] == 'ok':
        protocol.require(len(rows) == 6, 'logical_mismatch')
    if not all(value['lifecycle']['cleanup'][key] for key in ('native_processes_stopped','raw_files_removed')):
        protocol.require(not rows)
    encode_report(value)
    return value

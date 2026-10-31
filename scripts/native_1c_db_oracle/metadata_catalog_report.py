"""Bounded measurement envelope; lifecycle success is not BSL API acceptance."""
import json
import re
import protocol
import metadata_catalog_acquisition as measurement
import metadata_catalog_probe_contract as wire
from metadata_catalog_inputs import LANE, SOURCE_FILES
from snapshots import OracleError

MAX_ENVELOPE_BYTES=1024
MAX_REPORT_BYTES=protocol.MAX_REPORT_BYTES + measurement.MAX_CAPTURE_BYTES + MAX_ENVELOPE_BYTES


def encode_report(value):
    def encoded(item):
        return json.dumps(item,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')
    protocol.encode(value['lifecycle'])  # Existing 32768-byte lifecycle cap, unchanged.
    protocol.require(type(value['states']) is list and len(value['states'])<=6)
    protocol.require(all(len(encoded(s))<=measurement.MAX_STATE_BYTES for s in value['states']), 'artifact_limit')
    protocol.require(len(encoded(value['states']))<=measurement.MAX_CAPTURE_BYTES, 'artifact_limit')
    protocol.require(len(encoded(dict(value,lifecycle=None,states=None)))<=MAX_ENVELOPE_BYTES, 'artifact_limit')
    raw=encoded(value)
    protocol.require(len(raw)+1<=MAX_REPORT_BYTES, 'artifact_limit')
    return raw


def empty_report(nonce, provenance):
    return dict(schema=1,lane=LANE,lifecycle=protocol.empty_report(nonce,provenance),
                states=[],verdict='not_established',helpers=None,measurement_failure=None)


def validate_report(raw, *, nonce, provenance, final=False):
    protocol.require(type(raw) is bytes and 0<len(raw)<=MAX_REPORT_BYTES, 'artifact_limit')
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=protocol.unique,
            parse_constant=lambda _:protocol.require(False))
    except (ValueError,UnicodeError,RecursionError):
        raise OracleError('transport_invalid') from None
    protocol.exact(value,('schema','lane','lifecycle','states','verdict','helpers','measurement_failure'))
    protocol.require(type(value['schema']) is int and value['schema']==1 and value['lane']==LANE)
    protocol.require(set(provenance['sources'])==set(SOURCE_FILES), 'provenance_mismatch')
    lifecycle=protocol.validate_report(protocol.encode(value['lifecycle']),nonce=nonce,
        provenance=provenance,final=final)
    helpers=value['helpers']
    if helpers is not None:
        import hashlib
        from inject_metadata import _module
        expected={context:hashlib.sha256(_module(name,nonce,'/tmp/onec-db-oracle/evidence',
            metadata_catalog_probe=True)).hexdigest() for context,name in (
                ('client','ManagedApplicationModule.bsl'),('server','NativeOracleServer.bsl'))}
        protocol.require(helpers==expected, 'provenance_mismatch')
    failure=value['measurement_failure']
    if failure is not None:
        protocol.exact(failure,('snapshot','context','phase'))
        protocol.require(failure['snapshot'] in measurement.TARGETS
            and failure['context'] in ('client','server','both')
            and failure['phase'] in ('origin','native','freeze','reader','postimage','cleanup','compare')
            and lifecycle['status']=='failed'
            and lifecycle['failed_stage']==measurement.TARGETS[failure['snapshot']])
    states=value['states']
    protocol.require(not states or helpers is not None, 'provenance_mismatch')
    protocol.require(type(states) is list and len(states)<=6)
    expected=[(s,c) for s in measurement.TARGETS for c in measurement.CONTEXTS]
    snapshots={s['id']:s['physical'] for s in lifecycle['snapshots']}
    tokens=set()
    for index,state in enumerate(states):
        protocol.require(len(protocol.encode(state))<=measurement.MAX_STATE_BYTES, 'artifact_limit')
        protocol.exact(state,('snapshot','context','token','origin','postimage','marker_sha256',
                              'wire','config','comparison'))
        protocol.require((state['snapshot'],state['context'])==expected[index])
        token=state['token']
        protocol.require(type(token) is str and re.fullmatch('[0-9a-f]{32}',token) is not None
                         and token not in tokens)
        tokens.add(token)
        measurement._summary(state['origin']);measurement._summary(state['postimage'])
        protocol.require(state['snapshot'] in snapshots)
        snapshot=snapshots[state['snapshot']]
        protocol.require(state['origin']=={k:snapshot[k] for k in ('bytes','sha256')}, 'snapshot_changed')
        protocol.require(protocol.digest(state['marker_sha256']))
        protocol.exact(state['config'],('count','name','payload_length','applied_state'))
        config=state['config']
        protocol.require(type(config['count']) is int and config['count']==1
            and type(config['name']) is str and 1<=len(config['name'])<=64
            and all(ord(c)>=32 and ord(c)!=127 for c in config['name'])
            and type(config['payload_length']) is int and 0<=config['payload_length']<=65535
            and config['applied_state']=='not_observed')
        protocol.require(type(state['wire']) is str)
        try: records=wire.validate_output(state['wire'].encode('ascii'))
        except (ValueError,UnicodeError):raise OracleError('invalid_marker') from None
        comparison=measurement.compare(records,config)
        protocol.require(type(state['comparison']) is dict
            and state['comparison']==comparison
            and all(type(v) is bool for v in state['comparison'].values()))
    protocol.require(value['verdict'] in ('not_established','owned_payload_applied_view_32_32_64_observed'))
    if value['verdict']!='not_established':
        protocol.require(measurement.applied_view_verdict(states)==value['verdict'])
    if lifecycle['status']=='ok':
        protocol.require(value['verdict']=='owned_payload_applied_view_32_32_64_observed')
    if not all(lifecycle['cleanup'][k] for k in ('native_processes_stopped','raw_files_removed')):
        protocol.require(not states and value['verdict']=='not_established')
    encode_report(value)  # Recheck constructive aggregate budgets after parsing.
    return value

"""Finite report for 2 identity sets × 2 states × 2 native contexts.

A successful measurement is not production admission or parity. Retain mismatch
facts, unavailable contexts, raw mixed-schema bytes and setup Query witnesses.
"""
import hashlib
import json
import re
import protocol
from protocol import require, exact
from linked_card_inputs import LANE, SOURCE_FILES
import linked_card_fixture as fixture
from linked_card_packet import linked as batch

MAX_REPORT_BYTES = 4 * 1024 * 1024


def encode_report(value):
    raw = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    require(len(raw)+1 <= MAX_REPORT_BYTES, 'artifact_limit')
    return raw


def empty_report(nonce, provenance):
    return dict(schema=1, lane=LANE, nonce=nonce, provenance=provenance,
        lifecycle=dict(status='failed', failure_kind='unexpected_failure', accepted=False,
            cleanup=dict(native_processes_stopped=False,raw_files_removed=False,
                         container_removed=False,private_staging_removed=False)),
        installations=[], states=[], failure_context=None, native_failure=None, install_failure=None, verdict='measurement_only_not_production_admission')


def digest_summary(value):
    exact(value, ('bytes','sha256'))
    require(type(value['bytes']) is int and 0 < value['bytes'] <= 67108864 and protocol.digest(value['sha256']), 'invalid_marker')


def capture(value, *, setup, b, state=None):
    exact(value, ('token','marker_sha256','outputs','assessment'))
    require(type(value['token']) is str and re.fullmatch('[0-9a-f]{32}', value['token']) is not None
            and protocol.digest(value['marker_sha256']), 'invalid_marker')
    outputs = value['outputs']
    require(type(outputs) is dict and set(outputs) == ({'setup'} if setup else set(fixture.BLOCKS)), 'invalid_marker')
    assessment = {}
    for block, output in outputs.items():
        require(type(output) is str and len(output) <= 8192, 'artifact_limit')
        raw = output.encode('ascii')
        if setup:
            batch.require_setup_evidence(raw,b,state)
            assessment[block] = 'query_witnesses_validated'
        else: assessment[block] = fixture.validate_capture(raw,b,block)
    require(encode_report(value['assessment']) == encode_report(assessment), 'logical_mismatch')


def validate_report(raw, *, nonce, provenance, final=False):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_REPORT_BYTES, 'artifact_limit')
    try: value = json.loads(raw.decode('ascii'),object_pairs_hook=protocol.unique,parse_constant=lambda _:require(False))
    except (ValueError,UnicodeError,RecursionError): raise protocol.OracleError('transport_invalid') from None
    exact(value, ('schema','lane','nonce','provenance','lifecycle','installations','states','failure_context','native_failure','install_failure','verdict'))
    require(type(value['schema']) is int and value['schema'] == 1 and value['lane'] == LANE
            and value['nonce'] == nonce and type(nonce) is str and re.fullmatch('[0-9a-f]{32}',nonce) is not None and value['verdict'] == 'measurement_only_not_production_admission')
    protocol.validate_provenance(value['provenance'], provenance)
    require(set(provenance['sources']) == set(SOURCE_FILES), 'provenance_mismatch')
    life = value['lifecycle']; exact(life, ('status','failure_kind','accepted','cleanup'))
    require(life['status'] in ('ok','failed') and life['failure_kind'] in protocol.FAILURES
            and type(life['accepted']) is bool)
    exact(life['cleanup'], ('native_processes_stopped','raw_files_removed','container_removed','private_staging_removed'))
    require(all(type(v) is bool for v in life['cleanup'].values()))
    require(life['accepted'] == (final and life['status'] == 'ok' and all(life['cleanup'].values())))
    failure = value['failure_context']
    if failure is not None:
        exact(failure,('repeat','state','context','phase'))
        require(life['status'] == 'failed' and failure['repeat'] in (None,1,2)
                and type(failure['repeat']) in (int,type(None)) and failure['state'] in (None,*fixture.STATES)
                and failure['context'] in (None,'client','server')
                and failure['phase'] in ('seed','install','setup','native','freeze','offline'))
    native_failure = value['native_failure']
    if native_failure is not None:
        require(life['status'] == 'failed' and failure is not None)
        from linked_card_diagnostics import validate
        validate(native_failure)
    install_failure=value['install_failure']
    if install_failure is not None:
        require(life['status']=='failed' and failure is not None and failure['phase']=='install' and failure['repeat'] in (1,2))
        _,_,files=fixture.load(failure['repeat'])
        from linked_card_diagnostics import validate_install_failure
        validate_install_failure(install_failure,{n:raw for n,raw in files.items() if n.endswith('.xml')})
    installs = value['installations']; states = value['states']
    require(type(installs) is list and len(installs) <= 2 and type(states) is list and len(states) <= 8)
    for repeat, installation in enumerate(installs,1):
        exact(installation, ('repeat','helpers','applied','audit','mapping'))
        audit=installation['audit']
        exact(audit,('token','actual_version','user','role_verified','users_verified','nonprivileged'))
        require(type(audit['token']) is str and re.fullmatch('[0-9a-f]{32}',audit['token']) is not None
                and audit['actual_version'] == protocol.VERSION and audit['user'] == 'NativeOracleSetup'
                and all(audit[k] is True for k in ('role_verified','users_verified','nonprivileged')), 'permission_mismatch')
        require(type(installation['repeat']) is int and installation['repeat'] == repeat)
        digest_summary(installation['applied'])
        exact(installation['helpers'], ('NativeOracleServer.bsl','ManagedApplicationModule.bsl'))
        b, manifest, files = fixture.load(repeat)
        fragments={name:raw for name,raw in files.items() if name.endswith('.xml')}
        require(installation['mapping']==fixture.actual_mapping(b,manifest['schema'],fragments),'metadata_rejected')
        from inject_metadata import _module
        from linked_card_instrument import instrument
        for name, digest in installation['helpers'].items():
            source = _module(name, nonce, '/tmp/onec-db-oracle/evidence')
            expected = instrument(source,name,b,files,nonce=nonce,evidence='/tmp/onec-db-oracle/evidence')
            require(digest == hashlib.sha256(expected).hexdigest(), 'provenance_mismatch')
    expected = [(r,s,c) for r in (1,2) for s in fixture.STATES for c in ('client','server')]
    native_tokens = {item['audit']['token'] for item in installs}
    require(len(native_tokens)==len(installs),'stale_evidence')
    setup_tokens = {}; origins = {}
    for index, state in enumerate(states):
        exact(state, ('repeat','state','context','setup','origin','postimage','native','offline'))
        require(type(state['repeat']) is int and (state['repeat'],state['state'],state['context']) == expected[index])
        require(state['repeat'] <= len(installs))
        b, manifest, _ = fixture.load(state['repeat'])
        digest_summary(state['origin']); digest_summary(state['postimage'])
        capture(state['setup'],setup=True,b=b,state=state['state']); capture(state['native'],setup=False,b=b)
        pair = (state['repeat'],state['state'])
        if pair in setup_tokens:
            require(state['setup'] == setup_tokens[pair] and state['origin'] == origins[pair], 'snapshot_changed')
        else:
            require(state['setup']['token'] not in native_tokens and
                    all(state['setup']['token'] != other['token'] for other in setup_tokens.values()), 'stale_evidence')
            setup_tokens[pair] = state['setup']; origins[pair] = state['origin']
        token = state['native']['token']
        require(token not in native_tokens and all(token != other['token'] for other in setup_tokens.values()), 'stale_evidence')
        native_tokens.add(token)
        offline = state['offline']; exact(offline, ('physical','outputs','comparison'))
        # Measurement helper supplies its own closed physical validator.
        from linked_card_physical import validate_observation
        validate_observation(offline['physical'],manifest['schema'],installs[state['repeat']-1]['mapping'])
        require(type(offline['outputs']) is dict and set(offline['outputs']) == set(fixture.BLOCKS))
        require(type(offline['comparison']) is dict and set(offline['comparison']) == set(fixture.BLOCKS))
        from linked_card_readback import compare
        for block, output in offline['outputs'].items():
            require(type(output) is str and len(output) <= 8192,'artifact_limit')
            fixture.validate_capture(output.encode('ascii'),b,block)
            expected_comparison = compare(output.encode('ascii'),state['native']['outputs'][block].encode('ascii'),b,block)
            require(encode_report(offline['comparison'][block]) == encode_report(expected_comparison), 'logical_mismatch')
    if life['status'] == 'ok':
        require(value['provenance']['actual_version'] == protocol.VERSION
                and life['failure_kind'] == 'none' and len(states) == 8 and len(installs) == 2
                and life['cleanup']['native_processes_stopped'] and life['cleanup']['raw_files_removed'])
    else: require(life['failure_kind'] != 'none')
    if not life['cleanup']['native_processes_stopped'] or not life['cleanup']['raw_files_removed']:
        require(not states and not installs)
    encode_report(value)
    return value

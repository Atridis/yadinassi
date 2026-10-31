"""Opt-in owned Metadata acquisition; no BSL API or native acceptance claim.

Every context has a distinct disposable clone and a reader of its own frozen
postimage. Only the three preexisting lifecycle snapshots are admitted. This
module deliberately does not call the baseline-only metadata observation route.
"""
from __future__ import annotations
import hashlib
import secrets

import config_framing_reader as framing
import filedb_catalog
import metadata_catalog_probe_contract as wire
from protocol import decode, encode, exact, require
from snapshots import OracleError, freeze_database, inspect_frozen_catalog

TARGETS = {'updated': 'update', 'loaded': 'load_cf', 'applied': 'apply_cf'}
CONTEXTS = ('client', 'server')
OPERATIONS = tuple('metadata_catalog_' + context for context in CONTEXTS)
MAX_MARKER_BYTES = 16384
MAX_CAPTURE_BYTES = 65536
MAX_STATE_BYTES = (MAX_CAPTURE_BYTES - 7) // 6  # six records, five commas, two brackets


def _summary(value):
    exact(value, ('bytes', 'sha256'))
    require(type(value['bytes']) is int and 0 < value['bytes'] <= 67108864,
            'invalid_marker')
    from protocol import digest
    require(digest(value['sha256']), 'invalid_marker')
    return value


def validate_marker(raw, *, nonce, token, context):
    require(context in CONTEXTS, 'invalid_input')
    require(type(raw) is bytes and len(raw) <= MAX_MARKER_BYTES, 'artifact_limit')
    value = decode(raw)
    exact(value, ('schema', 'nonce', 'token', 'operation', 'status', 'output'))
    require(type(value['schema']) is int and value['schema'] == 1
            and value['nonce'] == nonce and value['token'] == token
            and value['operation'] == 'metadata_catalog_' + context
            and value['status'] == 'ok' and type(value['output']) is str, 'invalid_marker')
    try:
        output = value['output'].encode('ascii')
        records = wire.validate_output(output)
    except (ValueError, UnicodeError):
        require(False, 'invalid_marker')
    return records


def read_projection(read_at, file_size, *, limits):
    """Decode CONFIG without any expected native name, UUID, version or value."""
    result = framing.observe_config_catalog_attributes(read_at, file_size,
        profile=framing.ConfigCatalogAttributeProfile(framing.DECLARATIONS, '0', 0),
        limits=framing.ConfigFramingLimits(max_slots=4096, max_record_bytes=4096),
        chain_limits=framing.ConfigBlobChainLimits(),
        content_limits=framing.ConfigContentDecodeLimits(), catalog_limits=limits)
    require(type(result) is framing.ConfigCatalogAttributeObservation
            and result.catalog_declared_count == result.catalog_resolved_count
            == result.catalog_positive_count == len(result.private_fields), 'invalid_marker')
    # Admission of this owned fixture is separate from the general projector.
    require(len(result.private_fields) == 1, 'metadata_rejected')
    key, identity, attributes = result.private_fields[0]
    require(key == identity.metadata_uuid, 'metadata_rejected')
    payload = [item for item in attributes.attributes if item.name == 'Payload']
    require(len(payload) == 1 and payload[0].type_token == 'S'
            and len(payload[0].qualifiers) == 2, 'metadata_rejected')
    return {'count': len(result.private_fields), 'name': identity.name,
            'payload_length': payload[0].qualifiers[0],
            'applied_state': result.applied_state}


def compare(records, projected):
    """Finite comparison, retaining mismatch facts instead of masking loaded-v2.

    FullName is compared between RU/EN calls, not claimed as an on-disk field.
    The decoded identity name and Payload length come solely from CONFIG.
    """
    def scalar(index, kind, expected):
        row = records[index-1]
        if kind == 'string': expected = tuple(map(ord, expected))
        return row == {'id': index, 'status': 'ok', 'kind': kind, 'value': expected}
    return {
        'count_matches': all(scalar(i, 'number', projected['count']) for i in (1, 2)),
        'name_matches': all(scalar(i, 'string', projected['name']) for i in (3, 4)),
        'payload_matches': all(scalar(i, 'number', projected['payload_length']) for i in (7, 8)),
        'fullname_alias_matches': records[4]['status'] == records[5]['status'] == 'ok'
            and records[4]['kind'] == records[5]['kind'] == 'string'
            and records[4]['value'] == records[5]['value'],
        'observer_complete': not any(r['status'] == 'observer-error' for r in records),
    }


def acquire(backend, identifier, *, launch):
    """Run through Native resource primitives; launch is the closed helper route.

    Caller must already have frozen identifier and must retain it until return.
    Exception cleanup preserves primary errors; global Controller cleanup remains
    mandatory. A successful acquisition does not imply behavioral equivalence.
    """
    require(identifier in TARGETS and backend.stage == TARGETS[identifier], 'invalid_input')
    from run import absent
    states = []
    baseline = backend.physical_summary(backend.artifacts / identifier / '1Cv8.1CD')
    baseline = _summary({k:baseline[k] for k in ('bytes','sha256')})
    for context in CONTEXTS:
        backend.metadata_attempt = dict(snapshot=identifier, context=context, phase='origin')
        backend.remaining()
        with backend.temporary_clone(identifier, 'auditor') as database:
            origin = backend.physical_summary(database / '1Cv8.1CD')
            origin = _summary({k:origin[k] for k in ('bytes','sha256')})
            require(origin == baseline, 'snapshot_changed')
            token = secrets.token_hex(16)
            backend.metadata_attempt['phase']='native'
            raw = launch(database, context=context, token=token)
            records = validate_marker(raw, nonce=backend.nonce, token=token, context=context)
            backend.metadata_attempt['phase']='freeze'
            frozen = backend.artifacts / 'auditor_frozen'
            absent(frozen)
            try:
                with backend.command_context('snapshot_freeze'):
                    backend.budgets(backend.physical_summary(database / '1Cv8.1CD')['bytes'])
                    postimage = freeze_database(database, frozen, quiescent=backend.quiescent)
                    backend.budgets()
                backend.metadata_attempt['phase']='reader'
                try:
                    summary, projected = inspect_frozen_catalog(frozen, quiescent=backend.quiescent,
                        read_catalog=read_projection, limits=filedb_catalog.CatalogLimits(),
                        before_read=backend.remaining)
                except filedb_catalog.ResourceLimit:
                    raise OracleError('artifact_limit') from None
                except filedb_catalog.CatalogError:
                    raise OracleError('metadata_rejected') from None
                backend.metadata_attempt['phase']='postimage'
                require(summary == {k: postimage[k] for k in ('bytes', 'sha256')}, 'snapshot_changed')
                capture = {'snapshot': identifier, 'context': context, 'token': token,
                    'origin': origin, 'postimage': _summary(summary),
                    'marker_sha256': hashlib.sha256(raw).hexdigest(),
                    'wire': decode(raw)['output'], 'config': projected, 'comparison': compare(records, projected)}
                require(len(encode(capture)) <= MAX_STATE_BYTES, 'artifact_limit')
                states.append(capture)
            except BaseException:
                try: backend.remove(frozen)
                except BaseException: pass
                raise
            else:
                backend.metadata_attempt['phase']='cleanup'
                backend.remove(frozen)
    backend.metadata_attempt = None
    return states


def applied_view_verdict(states):
    """Only admit all six contexts and the discriminating 32/32/64 sequence."""
    require(type(states) is list and len(states) == 6, 'invalid_marker')
    pairs = [(s['snapshot'], s['context']) for s in states]
    require(pairs == [(s, c) for s in TARGETS for c in CONTEXTS], 'invalid_marker')
    require(len({s['token'] for s in states}) == 6, 'stale_evidence')
    for state in states:
        measured = compare(wire.require_available(state['wire'].encode('ascii')), state['config'])
        require(state['comparison'] == measured and all(measured.values()), 'logical_mismatch')
        expected = 64 if state['snapshot'] == 'applied' else 32
        require(state['config']['payload_length'] == expected, 'logical_mismatch')
    return 'owned_payload_applied_view_32_32_64_observed'

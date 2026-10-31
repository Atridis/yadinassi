"""Separate opt-in native/public-runtime acquisition; base measurement unchanged."""
import hashlib
import secrets
import filedb_catalog
from protocol import decode, encode, require
from snapshots import OracleError, freeze_database, inspect_frozen_catalog
from metadata_catalog_acquisition import (TARGETS, CONTEXTS, _summary, validate_marker,
    read_projection, compare, MAX_STATE_BYTES)

MAX_READBACK_STATE_BYTES = 8192

def acquire(backend, identifier, *, launch):
    """Run through Native resource primitives; launch is the closed helper route.

    Caller must already have frozen identifier and must retain it until return.
    Exception cleanup preserves primary errors; global Controller cleanup remains
    mandatory. A successful acquisition does not imply behavioral equivalence.
    """
    require(identifier in TARGETS and backend.stage == TARGETS[identifier], 'invalid_input')
    from run import absent
    states = []
    readbacks = []
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
                backend.metadata_attempt['phase']='runtime'
                # Outer pinned descriptor hashes/checks surround an independent
                # actual FileDBContext open on this same immutable postimage.
                from metadata_catalog_runtime_readback import readback
                def public_reader(_read_at, _file_size, *, limits):
                    backend.remaining()
                    return readback(frozen, native_wire=decode(raw)['output'].encode('ascii'))
                runtime_summary, runtime = inspect_frozen_catalog(frozen,
                    quiescent=backend.quiescent, read_catalog=public_reader,
                    limits=filedb_catalog.CatalogLimits(), before_read=backend.remaining)
                require(runtime_summary == summary, 'snapshot_changed')
                backend.metadata_attempt['phase']='postimage'
                require(summary == {k: postimage[k] for k in ('bytes', 'sha256')}, 'snapshot_changed')
                capture = {'snapshot': identifier, 'context': context, 'token': token,
                    'origin': origin, 'postimage': _summary(summary),
                    'marker_sha256': hashlib.sha256(raw).hexdigest(),
                    'wire': decode(raw)['output'], 'config': projected, 'comparison': compare(records, projected)}
                require(len(encode(capture)) <= MAX_STATE_BYTES, 'artifact_limit')
                states.append(capture)
                readbacks.append(dict(snapshot=identifier, context=context,
                    token=token, postimage=_summary(runtime_summary), **runtime))
                require(len(encode(readbacks[-1])) <= MAX_READBACK_STATE_BYTES, 'artifact_limit')
                require(runtime['comparison']['supported_match'], 'logical_mismatch')
            except BaseException:
                try: backend.remove(frozen)
                except BaseException: pass
                raise
            else:
                backend.metadata_attempt['phase']='cleanup'
                backend.remove(frozen)
    backend.metadata_attempt = None
    return states, readbacks


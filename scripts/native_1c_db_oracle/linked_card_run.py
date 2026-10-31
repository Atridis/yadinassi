"""Closed batched Catalog experiment using the existing process/clone lifecycle."""
import hashlib
import re
import secrets
import shutil
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as lifecycle
from protocol import require, exact, decode
from snapshots import freeze_database, inspect_frozen_catalog
import linked_card_fixture as fixture
from linked_card_packet import linked as batch

MAX_MARKER = 96 * 1024


def validate_marker(raw, *, nonce, token, operation, b):
    import json
    from protocol import unique
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MARKER, 'artifact_limit')
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)
    exact(value, ('schema', 'nonce', 'token', 'operation', 'status', 'outputs'))
    require(type(value['schema']) is int and value['schema'] == 1 and value['nonce'] == nonce
            and value['token'] == token and value['operation'] == operation and value['status'] == 'ok', 'invalid_marker')
    outputs = value['outputs']
    keys = ('setup',) if operation.startswith('linked_card_setup_') else fixture.BLOCKS
    require(type(outputs) is dict and set(outputs) == set(keys), 'invalid_marker')
    for block, text in outputs.items():
        require(type(text) is str and len(text) <= 8192, 'artifact_limit')
        raw_output = text.encode('ascii')
        if block == 'setup': batch.require_setup_evidence(raw_output, b, operation.removeprefix('linked_card_setup_'))
        else: fixture.validate_capture(raw_output, b, block)
    return outputs


class Native(lifecycle.Native):
    def install(self, database, repeat):
        """Extend a verified baseline, apply and compare an exact saved redump."""
        from inject_metadata import _inventory, _canonical, read_xml, MODULE_FILES
        import linked_card_instrument as instrument
        b, manifest, files = fixture.load(repeat)
        target = self.root / ('catalog-source-' + str(repeat))
        lifecycle.absent(target)
        shutil.copytree(self.v1, target)
        fragments = {n: raw for n, raw in files.items() if n.endswith('.xml')}
        changed = batch.extend_sources(b, manifest['schema'], fragments,
            lifecycle.regular_bytes(target / 'Configuration.xml', 1048576),
            lifecycle.regular_bytes(target / 'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml', 65536))
        for name, raw in changed.items(): (target / name).write_bytes(raw)
        helpers = {}
        for name in ('NativeOracleServer.bsl', 'ManagedApplicationModule.bsl'):
            path = target / MODULE_FILES[name]
            raw = instrument.instrument(lifecycle.regular_bytes(path, 1048576), name, b, files,
                                        nonce=self.nonce, evidence=self.evidence)
            path.write_bytes(raw); helpers[name] = hashlib.sha256(raw).hexdigest()
        self.batch(database, ['/LoadConfigFromFiles', str(target)], 'seed-import')
        self.batch(database, ['/UpdateDBCfg'], 'seed-apply')
        redump = self.root / ('catalog-redump-' + str(repeat)); lifecycle.absent(redump)
        self.batch(database, ['/DumpConfigToFiles', str(redump), '-Format', 'Hierarchical'], 'redump')
        try:
            left, right = _inventory(target), _inventory(redump)
            require(left == right, 'metadata_rejected')
            redumped={name:lifecycle.regular_bytes(redump/name,65536) for name in fragments}
            batch.verify_redump(b, manifest['schema'], fragments, redumped)
            mapping=fixture.actual_mapping(b,manifest['schema'],redumped)
            for name, kind in left.items():
                if kind == 'directory' or name == 'ConfigDumpInfo.xml': continue
                a, c = target / name, redump / name
                if name.endswith('.xml'):
                    require(_canonical(read_xml(a)[1]) == _canonical(read_xml(c)[1]), 'metadata_rejected')
                else:
                    require(a.read_text(encoding='utf-8-sig') == c.read_text(encoding='utf-8-sig'), 'metadata_rejected')
        finally:
            shutil.rmtree(redump)
        audit = self.enterprise(database, 'audit')
        require(audit['role_verified'] is True and audit['users_verified'] is True
                and audit['nonprivileged'] is True and audit['user'] == lifecycle.SETUP_USER, 'permission_mismatch')
        return b, helpers, {key:audit[key] for key in ('token','actual_version','user','role_verified','users_verified','nonprivileged')}, mapping

    def launch(self, database, *, operation, b):
        require(operation in ('linked_card_client', 'linked_card_server',
                *('linked_card_setup_' + s for s in fixture.STATES)), 'invalid_input')
        self.catalog_native_failure = None
        token = secrets.token_hex(16)
        control = self.evidence / 'control.json'; result = self.evidence / 'result.json'
        completion = self.evidence / 'completion.json'; pending = self.evidence / 'completion.pending.json'
        lifecycle.absent(control, result, completion, pending)
        from protocol import encode
        control.write_bytes(encode(dict(schema=1, nonce=self.nonce, token=token, operation=operation)))
        try:
            log = self.evidence / f'{self.counter+1:03}-{operation}.log'; lifecycle.absent(log)
            self.process(self.command('ENTERPRISE', database, lifecycle.CRUD_USER) +
                         ['/RunModeManagedApplication', '/C', token, '/Out', str(log)], operation)
            lifecycle.absent(pending)
            completed = decode(lifecycle.regular_bytes(completion, 4096))
            exact(completed, ('schema', 'nonce', 'token', 'operation', 'phase', 'status'))
            require(type(completed['schema']) is int and completed['schema'] == 1 and completed['nonce'] == self.nonce
                    and completed['token'] == token, 'invalid_marker')
            from linked_card_diagnostics import PHASES as phases
            require(completed['phase'] in phases and completed['status'] in ('ok','error'), 'invalid_marker')
            self.catalog_native_failure = dict(site='completion', phase=completed['phase'],
                status=completed['status'], operation_matches=completed['operation'] == operation)
            require(completed['operation'] == operation and completed['phase'] == 'complete'
                    and completed['status'] == 'ok', 'invalid_marker')
            raw = lifecycle.regular_bytes(result, MAX_MARKER)
            self.catalog_native_failure = dict(site='output',phase='complete',status='ok',operation_matches=True)
            outputs = validate_marker(raw, nonce=self.nonce, token=token, operation=operation, b=b)
            assessment = ({'setup':'query_witnesses_validated'} if operation.startswith('linked_card_setup_') else
                          {block:fixture.validate_capture(text.encode('ascii'),b,block) for block,text in outputs.items()})
            self.catalog_native_failure = None
            return dict(token=token, marker_sha256=hashlib.sha256(raw).hexdigest(), outputs=outputs, assessment=assessment)
        except BaseException:
            from linked_card_diagnostics import collect
            try:self.catalog_native_failure=collect(self,database,self.catalog_native_failure)
            except BaseException:self.catalog_native_failure=None
            raise
        finally:
            for path in (control, result, completion, pending): path.unlink(missing_ok=True)


def summary(backend, path):
    value = backend.physical_summary(path / '1Cv8.1CD')
    return {k: value[k] for k in ('bytes', 'sha256')}


def acquire(backend, *, readback):
    """Two states per repeat; four readonly blocks per context/session."""
    captures = []; installations = []
    backend.catalog_captures = captures; backend.catalog_installations = installations
    backend.catalog_attempt = dict(repeat=None,state=None,context=None,phase='seed')
    backend.begin_stage('seed_v1')
    seed = backend.seed()
    backend.begin_stage('baseline')
    backend.freeze(seed, 'catalog_baseline')
    for repeat in (1, 2):
        b, _, _ = fixture.load(repeat)
        backend.catalog_attempt = dict(repeat=repeat,state=None,context=None,phase='install')
        with backend.temporary_clone('catalog_baseline', 'catalog_install') as installed:
            b, helpers, audit, mapping = backend.install(installed, repeat)
            applied = 'catalog_applied_' + str(repeat)
            applied_summary = backend.freeze(installed, applied)
        installations.append(dict(repeat=repeat, helpers=helpers, audit=audit, mapping=mapping,
                                  applied={k: applied_summary[k] for k in ('bytes', 'sha256')}))
        for state in fixture.STATES:
            backend.catalog_attempt = dict(repeat=repeat,state=state,context=None,phase='setup')
            with backend.temporary_clone(applied, 'catalog_setup') as database:
                before = summary(backend, database)
                require(before == installations[-1]['applied'], 'snapshot_changed')
                setup = backend.launch(database, operation='linked_card_setup_' + state, b=b)
                frozen_setup = 'catalog_state'
                baseline = backend.freeze(database, frozen_setup)
            try:
                for context in ('client', 'server'):
                    backend.catalog_attempt = dict(repeat=repeat,state=state,context=context,phase='native')
                    with backend.temporary_clone(frozen_setup, 'catalog_observe') as database:
                        origin = summary(backend, database)
                        require(origin == {k: baseline[k] for k in ('bytes', 'sha256')}, 'snapshot_changed')
                        native = backend.launch(database, operation='linked_card_' + context, b=b)
                        frozen = backend.artifacts / 'catalog_postimage'; lifecycle.absent(frozen)
                        try:
                            backend.catalog_attempt['phase'] = 'freeze'
                            with backend.command_context('snapshot_freeze'):
                                backend.budgets(summary(backend, database)['bytes'])
                                postimage = freeze_database(database, frozen, quiescent=backend.quiescent)
                                backend.budgets()
                            # Both offline measurements execute under the same pinned
                            # descriptor's before/after full digest and process census.
                            def reader(read_at, size, *, limits):
                                return readback(read_at, size, frozen, b, native['outputs'], mapping)
                            import filedb_catalog
                            backend.catalog_attempt['phase'] = 'offline'
                            stable, offline = inspect_frozen_catalog(frozen, quiescent=backend.quiescent,
                                read_catalog=reader, limits=filedb_catalog.CatalogLimits(), before_read=backend.remaining)
                            require(stable == {k: postimage[k] for k in ('bytes', 'sha256')}, 'snapshot_changed')
                            captures.append(dict(repeat=repeat, state=state, context=context, setup=setup,
                                origin=origin, postimage=stable, native=native, offline=offline))
                        finally:
                            backend.remove(frozen)
            finally:
                backend.discard(frozen_setup)
        backend.discard(applied)
    backend.discard('catalog_baseline')
    backend.catalog_attempt = None
    return installations, captures


def main():
    if not sys.flags.isolated or not sys.flags.no_site: return 2
    if len(sys.argv) != 3 or sys.argv[1] != '--invocation-nonce' or re.fullmatch('[0-9a-f]{32}', sys.argv[2]) is None: return 2
    import linked_card_inputs as inputs
    import linked_card_report as policy
    backend = None
    try:
        nonce = sys.argv[2]; provenance = inputs.verify_inputs(Path('/oracle'), nonce)
        inputs.activate_runtime(Path('/oracle'))
        from linked_card_readback import readback
        report = policy.empty_report(nonce, provenance)
        backend = Native(nonce, provenance)
        try:
            backend.preflight()
            report['installations'], report['states'] = acquire(backend, readback=readback)
            report['lifecycle'].update(status='ok', failure_kind='none')
        except BaseException as error:
            report['states'] = getattr(backend,'catalog_captures',[])
            report['installations'] = getattr(backend,'catalog_installations',[])
            report['failure_context'] = getattr(backend,'catalog_attempt',None)
            report['native_failure'] = getattr(backend,'catalog_native_failure',None)
            report['lifecycle']['failure_kind'] = error.kind if isinstance(error, lifecycle.OracleError) else 'unexpected_failure'
        finally:
            stopped, removed = backend.cleanup()
            report['lifecycle']['cleanup'].update(native_processes_stopped=stopped, raw_files_removed=removed)
            if not stopped or not removed:
                report['states'] = []; report['installations'] = []
                report['lifecycle'].update(status='failed', failure_kind='cleanup_unverified')
        raw = policy.encode_report(report)
        policy.validate_report(raw, nonce=nonce, provenance=provenance)
        sys.stdout.buffer.write(raw + b'\n'); sys.stdout.buffer.flush()
        return 0 if report['lifecycle']['status'] == 'ok' else 1
    except BaseException:
        if backend is not None: backend.cleanup()
        return 1


if __name__ == '__main__': raise SystemExit(main())

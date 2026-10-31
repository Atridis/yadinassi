"""Dedicated container entrypoint; lifecycle/cleanup remain the existing runner."""
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from protocol import require, decode, exact, empty_report
import run as lifecycle
import metadata_catalog_acquisition as measurement


class Native(lifecycle.Native):
    def __init__(self, nonce, provenance):
        super().__init__(nonce,provenance)
        self.metadata_catalog_probe=True
        self.metadata_attempt=None
        self.metadata_helpers=None

    def seed(self):
        database=super().seed()
        import hashlib
        self.metadata_helpers={context:hashlib.sha256(lifecycle.regular_bytes(self.v1/path,1048576)).hexdigest()
            for context,path in (('client','Ext/ManagedApplicationModule.bsl'),
                                 ('server','CommonModules/NativeOracleServer/Ext/Module.bsl'))}
        return database

    def launch_metadata(self, database, *, context, token):
        require(context in measurement.CONTEXTS and self.stage in measurement.TARGETS.values()
                and type(token) is str and re.fullmatch('[0-9a-f]{32}',token) is not None, 'invalid_input')
        operation='metadata_catalog_'+context
        control=self.evidence/'control.json';result=self.evidence/'result.json'
        completion=self.evidence/'completion.json';pending=self.evidence/'completion.pending.json'
        lifecycle.absent(control,result,completion,pending)
        from protocol import encode
        control.write_bytes(encode(dict(schema=1,nonce=self.nonce,token=token,operation=operation)))
        try:
            log=self.evidence/f'{self.counter+1:03}-{operation}.log';lifecycle.absent(log)
            self.process(self.command('ENTERPRISE',database,lifecycle.SETUP_USER)+[
                '/RunModeManagedApplication','/C',token,'/Out',str(log)],operation)
            lifecycle.absent(pending)
            finished=decode(lifecycle.regular_bytes(completion,4096))
            exact(finished,('schema','nonce','token','operation','phase','status'))
            require(type(finished['schema']) is int and finished['schema']==1
                    and finished['nonce']==self.nonce and finished['token']==token
                    and finished['operation']==operation, 'invalid_marker')
            require(finished['status']=='ok' and finished['phase']=='complete', 'process_failed')
            raw=lifecycle.regular_bytes(result,measurement.MAX_MARKER_BYTES)
            measurement.validate_marker(raw,nonce=self.nonce,token=token,context=context)
            return raw
        finally:
            for path in (control,result,completion,pending):
                if path.exists(): path.unlink()


class Controller(lifecycle.Controller):
    def __init__(self, backend, report):
        super().__init__(backend,report)
        self.metadata_states=[]
        self.metadata_verdict='not_established'
        self.metadata_failure=None

    def snapshot(self, database, identifier):
        super().snapshot(database,identifier)
        if identifier in measurement.TARGETS:
            try:
                self.metadata_states.extend(measurement.acquire(self.backend,identifier,
                    launch=self.backend.launch_metadata))
                if identifier=='applied':
                    self.backend.metadata_attempt=dict(snapshot=identifier,context='both',phase='compare')
                    self.metadata_verdict=measurement.applied_view_verdict(self.metadata_states)
                    self.backend.metadata_attempt=None
            except BaseException:
                self.metadata_failure=self.backend.metadata_attempt
                raise


def main():
    if len(sys.argv)!=3 or sys.argv[1]!='--invocation-nonce' or re.fullmatch('[0-9a-f]{32}',sys.argv[2]) is None:
        return 2
    try:
        from metadata_catalog_inputs import verify_inputs
        from metadata_catalog_report import encode_report, validate_report
        nonce=sys.argv[2];provenance=verify_inputs(Path('/oracle'),nonce)
        controller=Controller(Native(nonce,provenance),empty_report(nonce,provenance))
        report=controller.run()
        if not all(report['cleanup'][k] for k in ('native_processes_stopped','raw_files_removed')):
            controller.metadata_states=[];controller.metadata_verdict='not_established'
        value={'schema':1,'lane':'owned_metadata_catalog_applied_view_v1',
            'lifecycle':report,'states':controller.metadata_states,'verdict':controller.metadata_verdict,
            'helpers':controller.backend.metadata_helpers,'measurement_failure':controller.metadata_failure}
        raw=encode_report(value)
        validate_report(raw,nonce=nonce,provenance=provenance)
        sys.stdout.buffer.write(raw+b'\n');sys.stdout.buffer.flush()
        return 0 if report['status']=='ok' else 1
    except BaseException:
        return 1


if __name__=='__main__': raise SystemExit(main())

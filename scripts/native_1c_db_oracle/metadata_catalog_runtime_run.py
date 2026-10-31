"""Opt-in source-bound public-runtime lane using the existing native lifecycle."""
import re
import sys
from pathlib import Path
sys.dont_write_bytecode = True
# -I deliberately removes the script directory. The container invokes this
# fixed file from its verified read-only /oracle mount; no caller path is used.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import empty_report
import run as lifecycle
import metadata_catalog_run as baseline
import metadata_catalog_acquisition as measurement
import metadata_catalog_runtime_acquisition as acquisition


class Controller(baseline.Controller):
    def __init__(self, backend, report):
        super().__init__(backend, report)
        self.runtime_readbacks = []

    def snapshot(self, database, identifier):
        lifecycle.Controller.snapshot(self, database, identifier)
        if identifier in measurement.TARGETS:
            try:
                states, readbacks = acquisition.acquire(self.backend, identifier,
                    launch=self.backend.launch_metadata)
                self.metadata_states.extend(states)
                self.runtime_readbacks.extend(readbacks)
                if identifier == 'applied':
                    self.backend.metadata_attempt = dict(snapshot=identifier, context='both', phase='compare')
                    self.metadata_verdict = measurement.applied_view_verdict(self.metadata_states)
                    self.backend.metadata_attempt = None
            except BaseException:
                self.metadata_failure = self.backend.metadata_attempt
                raise


def main():
    if not sys.flags.isolated or not sys.flags.no_site:
        return 2
    if len(sys.argv) != 3 or sys.argv[1] != '--invocation-nonce' or re.fullmatch('[0-9a-f]{32}', sys.argv[2]) is None:
        return 2
    try:
        import metadata_catalog_runtime_inputs as inputs
        import metadata_catalog_runtime_report as policy
        nonce = sys.argv[2]
        provenance = inputs.verify_inputs(Path('/oracle'), nonce)
        inputs.activate_runtime(Path('/oracle'))
        controller = Controller(baseline.Native(nonce, provenance), empty_report(nonce, provenance))
        report = controller.run()
        if not all(report['cleanup'][key] for key in ('native_processes_stopped','raw_files_removed')):
            controller.metadata_states = []; controller.runtime_readbacks = []
            controller.metadata_verdict = 'not_established'
        value = dict(schema=1, lane=inputs.LANE, lifecycle=report,
            states=controller.metadata_states, verdict=controller.metadata_verdict,
            helpers=controller.backend.metadata_helpers, measurement_failure=controller.metadata_failure,
            runtime_readbacks=controller.runtime_readbacks, runtime_identity=inputs.runtime_identity(provenance))
        raw = policy.encode_report(value)
        policy.validate_report(raw, nonce=nonce, provenance=provenance)
        sys.stdout.buffer.write(raw + b'\n'); sys.stdout.buffer.flush()
        return 0 if report['status'] == 'ok' else 1
    except BaseException:
        return 1


if __name__ == '__main__': raise SystemExit(main())

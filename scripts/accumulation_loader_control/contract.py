"""Closed one-case diagnostic transport, distinct from the 16-case acquisition."""
from accumulation_register_behavior import route as source_route

PROFILE = 'accumulation-loader-control-v1'
SCHEMA = 'native-1c-accumulation-loader-control-envelope-v1'
STAGE_SCHEMA = 'native-1c-accumulation-loader-control-stage-v1'
HOST_SCHEMA = 'native-1c-accumulation-loader-control-host-v1'
MANIFEST = 'accumulation-loader-control-inputs.json'
COUNT = 1
MAX_TRANSPORT = 32768
PHASES = ('prerequisites', 'inputs', 'baseline', 'load', 'redump', 'final')
FLAGS = frozenset(('entered', 'load_completed', 'redump_completed', 'config_verified',
                   'source_verified', 'process_exited', 'quiet', 'completed'))
ACCEPTANCE_FLAGS = frozenset(('native_measurement_accepted', 'semantic_measurement_accepted',
                             'runtime_parity_accepted'))
HASH_FIELDS = frozenset(('prepared_sha256', 'redump_sha256'))
STAGE_KEYS = FLAGS | ACCEPTANCE_FLAGS | HASH_FIELDS | {
    'schema', 'profile', 'nonce', 'status', 'failure_kind', 'failure_phase',
    'input_sha256', 'case_count', 'completed_case_count', 'configuration_validation',
    'redump_diagnostic', 'install_diagnostics', 'process_diagnostics'}


def install_diagnostic(text, label, **facts):
    if label not in ('before', 'load', 'after'):
        raise ValueError('loader control diagnostic step')
    return source_route.install_diagnostic(text, label, **facts)


def valid_install_diagnostic(value):
    return (source_route.valid_install_diagnostic(value)
            and value['step'] in ('before', 'load', 'after'))

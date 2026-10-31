"""Same bounded compiler/marker projection with 24 fixed setup witness phases."""
import catalog_read_diagnostics as base
from protocol import require
PHASES=base.PHASES+tuple(f'setup-witness-{i:02}' for i in range(13,25))


def validate(value):
    phase=value.get('phase')
    require(phase is None or phase in PHASES)
    projected=dict(value)
    if phase not in base.PHASES and phase is not None:projected['phase']='setup'
    base.validate(projected)


def collect(backend,database,previous):
    projected=None if previous is None else dict(previous)
    phase=None if previous is None else previous['phase']
    require(phase is None or phase in PHASES)
    if projected is not None and phase not in base.PHASES:projected['phase']='setup'
    result=base.collect(backend,database,projected)
    if previous is not None:result['phase']=phase
    validate(result)
    return result

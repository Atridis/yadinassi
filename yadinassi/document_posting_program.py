"""Read-only compilation of source-bound synchronous document callbacks.

No initializer is run, and compilation does not grant transaction authority.
Callers must first canonically admit the corresponding source configuration.
"""
from hashlib import sha256

from .configuration_modules import compile_module
from .configuration_diagnostics import location

MAX_SOURCE = 65536
_EVENTS = {
    'before': (('beforewrite', 'передзаписью'), 3),
    'after': (('onwrite', 'призаписи'), 1),
    'posting': (('posting', 'обработкапроведения'), 2),
    'undo': (('undoposting', 'обработкаудаленияпроведения'), 1),
}


def compile_handlers(configuration):
    files = dict(configuration.files)
    programs, handlers = {}, {}
    for identity, path, digest in configuration.handlers:
        with location(stage='compile', file=path):
            raw = files[path]
            if len(raw) > MAX_SOURCE or sha256(raw).hexdigest() != digest:
                raise ValueError('document source binding')
            program = compile_module(raw, path, 'server', common=True)
            names = [routine.name.casefold() for routine in program]
            if len(names) != len(set(names)):
                raise ValueError('duplicate document routine')
            events = {}
            for event, (aliases, arity) in _EVENTS.items():
                selected = [routine for routine in program if routine.name.casefold() in aliases]
                if len(selected) > 1:
                    raise ValueError('duplicate document handler')
                routine = selected[0] if selected else None
                if routine is not None and (routine.is_function or len(routine.parameters) != arity
                        or any(parameter.default is not None for parameter in routine.parameters)
                        or routine.parameters[0].by_value):
                    raise ValueError('document handler signature')
                events[event] = routine
            programs[identity] = program
            handlers[identity] = events
    return programs, handlers

"""Compatibility validation for the sole accepted backend name. No runtime selection."""
from contextlib import contextmanager

BACKENDS = ('python-direct',)

def current_backend():
    return BACKENDS[0]

@contextmanager
def execution_backend_policy(backend):
    if type(backend) is not str or backend not in BACKENDS:
        raise ValueError('unsupported execution backend')
    yield

UI_BACKENDS = BACKENDS

def ui_backend(backend=None):
    mode = current_backend() if backend is None else backend
    if type(mode) is not str or mode not in UI_BACKENDS:
        raise ValueError('UI execution backend must be python-direct')
    return mode


def backend_entrypoint(function):
    """Consume the compatibility option, preserving launcher first-argument routing.

    This is deliberately an argv protocol, not an environment variable. Options
    after ``--`` remain application data and cannot select an execution mode.
    """
    import argparse
    from functools import wraps
    import sys
    @wraps(function)
    def selected(argv=None, *args, **kwargs):
        arguments = list(sys.argv[1:] if argv is None else argv)
        boundary = arguments.index('--') if '--' in arguments else len(arguments)
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        selection_group=parser.add_mutually_exclusive_group()
        selection_group.add_argument('--execution-backend', choices=UI_BACKENDS)
        for argument in arguments[:boundary]:
            name = argument.split('=', 1)[0]
            if name.startswith('--') and name != '--execution-backend' and '--execution-backend'.startswith(name):
                parser.error('use the exact --execution-backend option')
        selection, remaining = parser.parse_known_args(arguments[:boundary])
        try:
            ui_backend(selection.execution_backend)
        except ValueError as error:
            parser.error(str(error))
        remaining.extend(arguments[boundary:])
        return function(remaining, *args, **kwargs)
    return selected

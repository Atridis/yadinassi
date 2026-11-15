"""Scoped backend selection for materialized interpreter families, not authority."""
from contextvars import ContextVar
from contextlib import contextmanager

BACKENDS = ('interpreter', 'hybrid', 'compiled-strict')
_POLICY = ContextVar('yadinassi_execution_backend', default='interpreter')

def current_backend():
    return _POLICY.get()

@contextmanager
def execution_backend_policy(backend):
    if type(backend) is not str or backend not in BACKENDS:
        raise ValueError('unsupported execution backend')
    token = _POLICY.set(backend)
    try:
        yield
    finally:
        _POLICY.reset(token)

UI_BACKENDS = ('interpreter', 'compiled-strict')

def ui_backend(backend=None):
    mode = current_backend() if backend is None else backend
    if type(mode) is not str or mode not in UI_BACKENDS:
        raise ValueError('UI execution backend must be interpreter or compiled-strict')
    return mode


def backend_entrypoint(function):
    """Explicit UI/stdio selection, preserving launcher first-argument routing.

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
        parser.add_argument('--execution-backend', choices=UI_BACKENDS)
        for argument in arguments[:boundary]:
            name = argument.split('=', 1)[0]
            if name.startswith('--') and name != '--execution-backend' and '--execution-backend'.startswith(name):
                parser.error('use the exact --execution-backend option')
        selection, remaining = parser.parse_known_args(arguments[:boundary])
        try:
            mode = ui_backend(selection.execution_backend)
        except ValueError as error:
            parser.error(str(error))
        remaining.extend(arguments[boundary:])
        with execution_backend_policy(mode):
            return function(remaining, *args, **kwargs)
    return selected

"""Shared first-argument mode dispatch for installed, module and frozen builds."""
import sys

from .cli import main as cli_main
from .ui import database_launch, editor_stdio, form_app, configuration_app


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    # BSL code, filenames and everything after -- never select a UI mode.
    if arguments and arguments[0] == '--ui':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        if '--configuration-source' in arguments[1:] or any(arg.startswith('--configuration-source=') for arg in arguments[1:]):
            from .ui import source_shell
            return source_shell.main(arguments[1:])
        return database_launch.main(arguments[1:])
    # Private child protocols, retained for frozen process isolation.
    if arguments and arguments[0] == '--catalog-ui-runtime':
        return editor_stdio.main(arguments[1:])
    if arguments and arguments[0] == '--form-ui':
        return form_app.main(arguments[1:])
    if arguments and arguments[0] == '--form-ui-runtime':
        return form_app.main(['--runtime'] + arguments[1:])
    if arguments and arguments[0] == '--configuration-ui':
        return configuration_app.main(arguments[1:])
    if arguments and arguments[0] == '--configuration-ui-runtime':
        return configuration_app.main(['--runtime'] + arguments[1:])
    return cli_main(arguments)

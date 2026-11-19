"""Shared first-argument mode dispatch for installed, module and frozen builds."""
import sys
from .cli import main as cli_main



def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Reject incompatible modes before importing/initializing any UI entry point.
    from .cli import _option_arguments
    if any(option.partition('=')[0] == '--emit-python'
           for option, _ in _option_arguments(arguments)):
        return cli_main(arguments)
    # BSL code, filenames and everything after -- never select a UI mode.
    if arguments and arguments[0] == '--ui':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        if '--configuration-source' in arguments[1:] or any(arg.startswith('--configuration-source=') for arg in arguments[1:]):
            from .ui import source_shell
            return source_shell.main(arguments[1:])
        from .ui import database_launch
        return database_launch.main(arguments[1:])
    # Private child protocols, retained for frozen process isolation.
    if arguments and arguments[0] == '--catalog-ui-runtime':
        from .ui import editor_stdio
        return editor_stdio.main(arguments[1:])
    if arguments and arguments[0] == '--form-ui':
        from .ui import form_app
        return form_app.main(arguments[1:])
    if arguments and arguments[0] == '--form-ui-runtime':
        from .ui import form_app
        return form_app.main(['--runtime'] + arguments[1:])
    if arguments and arguments[0] == '--configuration-ui':
        from .ui import configuration_app
        return configuration_app.main(arguments[1:])
    if arguments and arguments[0] == '--configuration-ui-runtime':
        from .ui import configuration_app
        return configuration_app.main(['--runtime'] + arguments[1:])
    return cli_main(arguments)

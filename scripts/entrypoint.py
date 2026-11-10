"""Explicit frozen launcher; plain invocations preserve the BSL CLI."""

import sys

from yadinassi.cli import main as cli_main
from yadinassi.ui import editor_stdio, local_app, form_app, configuration_app


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Only the very first argument selects a mode. In particular, a BSL file,
    # -c payload, or arguments after -- are never interpreted as UI options.
    if arguments and arguments[0] == '--catalog-ui':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        return local_app.main(arguments[1:])
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


if __name__ == "__main__":
    raise SystemExit(main())

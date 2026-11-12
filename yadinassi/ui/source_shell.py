"""Diagnostic source shell, not an arbitrary configuration-form renderer.

Execution is an explicit one-shot CLI choice, never a browser RPC capability.
The runtime is closed before the shell opens. Source inventory remains readable
when startup fails; no database/profile authority is inferred from admission.
"""
import argparse
from collections import Counter
from pathlib import Path
import sys
import webbrowser

from ..configuration_source import load_source_directory, load_source_archive
from ..configuration_source_runtime import SourceApplication
from ..errors import BSLError
from .local_app import LocalUIServer, _Handler

PROTOCOL = 'yadinassi-source-diagnostics/1'


class SourceShell:
    def __init__(self, source, *, run_startup=False, scratch_database=None, compatibility_target=None):
        if not run_startup and (scratch_database is not None or compatibility_target is not None):
            raise ValueError('scratch database and compatibility target require explicit startup')
        self.closed = False
        self.messages = []
        self.omitted_messages = 0
        self.outcome = 'not-run'
        self.error = None
        self.name = source.name
        self.files = len(source.files)
        families = sorted(Counter(item.family for item in source.metadata).items())
        self.families = [{'family': key[:128], 'count': count} for key, count in families[:64]]
        self.omitted_families = max(0, len(families) - 64)
        from ..source_system_info import validate_target
        self.target = validate_target(compatibility_target)
        if run_startup:
            app = None
            try:
                app = SourceApplication(source, output=self._output, scratch_database=scratch_database,
                                        compatibility_target=compatibility_target)
                self.outcome = 'completed' if app.start() else 'cancelled'
            except (BSLError, ValueError, TypeError, OSError, RecursionError) as error:
                self.outcome = 'failed'
                self.error = str(error).encode('utf-8', errors='replace')[:8192].decode('utf-8', errors='ignore')
            finally:
                if app is not None:
                    app.close()

    def _output(self, message):
        if len(self.messages) < 16:
            self.messages.append(str(message)[:512])
        else:
            self.omitted_messages += 1

    def close(self):
        self.closed = True

    def exchange(self, request):
        if (type(request) is not dict or set(request) != {'jsonrpc', 'id', 'method', 'params'}
                or request['jsonrpc'] != '2.0' or type(request['id']) is not int
                or request['params'] != {} or type(request['params']) is not dict
                or request['method'] not in ('source.snapshot', 'source.close')):
            raise ValueError('invalid source shell request')
        if request['method'] == 'source.close':
            self.close()
        state = {'kind': 'closed' if self.closed else 'diagnostics', 'name': self.name,
                 'startup': self.outcome, 'runtime_active': False, 'files': self.files,
                 'families': self.families, 'omitted_families': self.omitted_families, 'messages': self.messages,
                 'omitted_messages': self.omitted_messages, 'error': self.error,
                 'compatibility_target': self.target}
        return {'jsonrpc': '2.0', 'id': request['id'], 'result': {'protocol': PROTOCOL, 'state': state}}


class SourceHandler(_Handler):
    asset_directory = 'source'
    methods = ('source.snapshot', 'source.close')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Source diagnostics, not configuration UI or a database editor.')
    parser.add_argument('--configuration-source', required=True, metavar='PATH')
    parser.add_argument('--run-startup', action='store_true', help='Execute startup once before opening diagnostics')
    parser.add_argument('--source-scratch-db', metavar='NEW_SQLITE_FILE')
    parser.add_argument('--source-compatibility-target', metavar='VERSION')
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args(argv)
    if not args.run_startup and (args.source_scratch_db or args.source_compatibility_target is not None):
        parser.error('scratch database and compatibility target require --run-startup')
    server = shell = None
    try:
        path = Path(args.configuration_source)
        source = load_source_directory(path) if path.is_dir() else load_source_archive(path)
        shell = SourceShell(source, run_startup=args.run_startup,
                            scratch_database=args.source_scratch_db,
                            compatibility_target=args.source_compatibility_target)
        server = LocalUIServer(shell, handler=SourceHandler)
        print('Диагностика источника. Это не UI конфигурации: формы и CRUD не активированы; '
              'попытка runtime завершена, активного сеанса нет.')
        if args.source_compatibility_target is not None:
            print('Экспериментальный target: ' + args.source_compatibility_target + '; не установленная 1С.')
        print(server.launch_url, flush=True)
        if args.open_browser:
            webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except (BSLError, ValueError, TypeError, OSError, RecursionError) as error:
        print('yadinassi: source diagnostics: ' + str(error), file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.server_close()
        if shell is not None:
            shell.close()

"""Loopback launcher for the single canonical main demo and its two surfaces."""
import argparse
from importlib.resources import files
import sys
import webbrowser

from ..sqlite_catalog import SQLiteCatalogBackend
from .database_launch import binding, verify_binding
from .local_app import LocalUIServer, _Handler
from .main_demo import require_backend
from .main_demo_host import MainDemoHost

_ASSETS = {
    '/':('main-demo','index.html','text/html; charset=utf-8'),
    '/app.js':('main-demo','app.js','text/javascript; charset=utf-8'),
    '/style.css':('main-demo','style.css','text/css; charset=utf-8'),
    '/catalog.js':('catalog','app.js','text/javascript; charset=utf-8'),
    '/catalog.css':('catalog','style.css','text/css; charset=utf-8'),
    '/configuration.js':('configuration','app.js','text/javascript; charset=utf-8'),
    '/configuration.css':('configuration','style.css','text/css; charset=utf-8'),
    '/LICENSE.txt':('catalog','LICENSE.txt','text/plain; charset=utf-8'),
}

class MainDemoHandler(_Handler):
    methods = ('demo.hello','demo.snapshot','demo.select','demo.dispatch','demo.close')

    def do_GET(self):
        if not self._host(): return self._reply(403)
        asset = _ASSETS.get(self.path)
        if asset is None: return self._reply(404)
        directory, name, kind = asset
        try:
            body = files('yadinassi.ui').joinpath('assets', directory, name).read_bytes()
        except (OSError, ValueError): return self._reply(503)
        # Existing dependency-free bundle keeps a closed export map. Expose its
        # already-declared mount only on this exact endpoint, without eval.
        if self.path == '/configuration.js':
            body += b'\nexport const mountApplication = __configurationApp.mountApplication;\n'
        return self._reply(200, body, kind)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open the canonical unified demo.')
    parser.add_argument('--f', required=True)
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--launch-binding', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    host = server = None
    try:
        backend = SQLiteCatalogBackend(args.f, read_only=True)
        try:
            require_backend(backend)
            expected = binding(backend.launch_snapshot())
            if args.launch_binding is not None:
                verify_binding(backend, args.launch_binding, route='main-demo')
                expected = args.launch_binding
        finally: backend.close()
        host = MainDemoHost(args.f, expected)
        server = LocalUIServer(host, handler=MainDemoHandler, browser_session=True,
                               idle_close=host.idle_close)
        print('Unified demo. Open this private per-launch URL:')
        print(server.launch_url, flush=True)
        if args.open_browser: webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Main demo UI unavailable. No import or fallback was performed.', file=sys.stderr)
        return 1
    finally:
        try:
            if server is not None: server.server_close()
        finally:
            if host is not None: host.close()

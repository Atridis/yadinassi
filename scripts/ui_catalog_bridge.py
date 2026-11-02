"""Source-tree-only stdio example: python scripts/ui_catalog_bridge.py FILE.

One host-selected SQLite file, opened read-only. No socket, GUI or write route.
This deliberately adds no flag to the yadinassi CLI or packaged entry point.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.browser import CatalogBrowserSession
from yadinassi.ui.catalog_view import CatalogRepository
from yadinassi.ui.protocol import MAX_LINE_BYTES, encode_line, error_response


def main(argv=None, *, source=None, target=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1 or not arguments[0]:
        print('Expected one existing SQLite database file.', file=sys.stderr)
        return 2
    source = sys.stdin.buffer if source is None else source
    target = sys.stdout.buffer if target is None else target
    backend = repository = None
    try:
        backend = SQLiteCatalogBackend(arguments[0], read_only=True)
        repository = CatalogRepository(backend)
        session = CatalogBrowserSession(repository)
        while True:
            raw = source.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return 0
            if len(raw) > MAX_LINE_BYTES:
                target.write(encode_line(error_response(None, 'message_limit')))
                target.flush()
                return 1  # Do not drain an attacker-controlled unbounded line.
            for response in session.exchange(raw):
                target.write(response)
            target.flush()
    except Exception:  # Host boundary: never expose backend/path exception text.
        print('Headless catalog source unavailable; check the supported SQLite profile.', file=sys.stderr)
        return 1
    finally:
        try:
            if repository is not None:
                repository.close()
            elif backend is not None:
                # Ownership transfers only after successful repository construction.
                backend.close()
        except Exception:
            print('Headless catalog cleanup failed.', file=sys.stderr)
            return 1  # A failed release must not preserve an earlier success exit.


if __name__ == '__main__':
    raise SystemExit(main())

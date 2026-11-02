"""Source-tree-only stdio example: python scripts/ui_catalog_bridge.py DIRECTORY.

One caller-owned, consistent offline database. No socket, GUI or write route.
This deliberately adds no flag to the yadinassi CLI or packaged entry point.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yadinassi.database_context import FileDBContext
from yadinassi.ui.browser import CatalogBrowserSession
from yadinassi.ui.catalog_view import CatalogRepository
from yadinassi.ui.protocol import MAX_LINE_BYTES, encode_line, error_response


def main(argv=None, *, source=None, target=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1 or not arguments[0]:
        print('Expected one offline database directory.', file=sys.stderr)
        return 2
    source = sys.stdin.buffer if source is None else source
    target = sys.stdout.buffer if target is None else target
    session = CatalogBrowserSession(CatalogRepository(FileDBContext(arguments[0])))
    try:
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
    except (BrokenPipeError, OSError):
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

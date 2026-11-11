"""Packaged explicit local editor NDJSON entrypoint; no GUI or network."""
import sys

from ..database_context import SQLiteDBContext
from .catalog_editor import CatalogEditorApplication
from .editor_protocol import CatalogEditorSession
from .protocol import MAX_LINE_BYTES


def main(argv=None, *, source=None, target=None):
    args = sys.argv[1:] if argv is None else argv
    binding = None
    if len(args) == 3 and args[1] == '--launch-binding':
        binding = args[2]; args = args[:1]
    if len(args) != 1 or not args[0]:
        print('Expected one existing SQLite application file.', file=sys.stderr)
        return 2
    source = sys.stdin.buffer if source is None else source
    target = sys.stdout.buffer if target is None else target
    context = application = None
    try:
        context = SQLiteDBContext(args[0])
        if binding is not None:
            from .database_launch import verify_binding
            verify_binding(context.backend, binding, route='catalog')
        application = CatalogEditorApplication(context)
        session = CatalogEditorSession(application)
        while True:
            raw = source.readline(MAX_LINE_BYTES + 1)
            if not raw: return 0
            if len(raw) > MAX_LINE_BYTES:
                target.write(session.exchange(raw)); target.flush()
                return 1
            target.write(session.exchange(raw)); target.flush()
    except Exception:
        print('Catalog editor unavailable; check the supported SQLite profile.', file=sys.stderr)
        return 1
    finally:
        try:
            if application is not None: application.close()
            elif context is not None: context.close()
        except Exception:
            print('Catalog editor cleanup failed.', file=sys.stderr)
            return 1


if __name__ == '__main__': raise SystemExit(main())

"""Reuse owned captured CONFIG/rows inside invented transport, never user data."""
from pathlib import Path
import tempfile

import test_linked_catalog_native_replay as linked
from yadinassi.database_context import FileDBContext
from yadinassi.ui.catalog_view import CatalogRepository


def repository(test, *, empty=False):
    state = next(item for item in linked.CAPTURE['states']
                 if item['repeat'] == 1 and item['state'] == ('empty' if empty else 'filled'))
    value = linked.image(state)
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    path = Path(temporary.name) / '1Cv8.1CD'
    with path.open('wb') as stream:
        for number in range(value.page_count):
            stream.write(value.pages.get(number, bytes(linked.base.P)))
    before = path.read_bytes()
    repo = CatalogRepository(FileDBContext(path.parent))
    return repo, path, before, state

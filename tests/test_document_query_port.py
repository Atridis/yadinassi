"""Owned document scan port; no claim of native 1C compatibility evidence."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_sqlite_documents as fixtures
from sqlite_catalog_fixture import configuration_files
from yadinassi.catalog_backend import BackendError, CatalogKey, CatalogScanRequest
from yadinassi.configuration_xml import import_configuration
from yadinassi.document_backend import DocumentKey, DocumentScanRequest, DocumentSelection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class DocumentQueryPortTests(unittest.TestCase):
    setUp = fixtures.SQLiteDocumentTests.setUp
    tearDown = fixtures.SQLiteDocumentTests.tearDown
    object = fixtures.SQLiteDocumentTests.object
    sql = fixtures.SQLiteDocumentTests.sql

    def seed(self, count=3):
        """Clone one valid encoded card in a single bounded fixture transaction."""
        obj = self.object()
        obj.write()
        row = self.sql('SELECT document_id,record_id,revision,number,date,deletion_mark,values_json,sections_json FROM document_record')[0]
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executemany('INSERT INTO document_record VALUES(?,?,?,?,?,?,?,?)',
                ((row[0], str(uuid4()), row[2], str(i).zfill(9), *row[4:])
                 for i in range(2, count + 1)))

    def view(self):
        view = self.context.backend.begin_query_read()
        self.addCleanup(view.close)
        return view

    def test_paging_beyond_selection_limit_is_complete_and_ordered(self):
        self.seed(1001)
        view = self.view()
        first = view.scan_documents(self.schema.identity, DocumentScanRequest())
        self.assertEqual(len(first.rows), 1000)
        self.assertIsNotNone(first.continuation)
        last = view.scan_documents(self.schema.identity, DocumentScanRequest(continuation=first.continuation))
        self.assertEqual(len(last.rows), 1)
        self.assertIsNone(last.continuation)
        numbers = [card.number for card in (*first.rows, *last.rows)]
        self.assertEqual(numbers, [str(i).zfill(9) for i in range(1, 1002)])
        self.assertEqual(len({card.key for card in (*first.rows, *last.rows)}), 1001)

    def test_selection_limit_remains_unchanged(self):
        self.seed(1001)
        view = self.view()
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            view.select_documents(self.schema.identity, DocumentSelection())
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.select_documents(self.schema.identity, DocumentSelection(limit=1001))
        self.assertEqual(len(view.scan_documents(self.schema.identity, DocumentScanRequest()).rows), 1000)

    def test_date_precedes_number_in_scan_order(self):
        self.seed()
        self.sql('UPDATE document_record SET date=? WHERE number=?', ('20261108000000', '000000003'))
        view = self.view()
        page = view.scan_documents(self.schema.identity, DocumentScanRequest())
        self.assertEqual([card.number for card in page.rows], ['000000003', '000000001', '000000002'])

    def test_continuations_are_single_use_and_page_size_bound(self):
        self.seed()
        view = self.view()
        request = DocumentScanRequest(page_size=1)
        first = view.scan_documents(self.schema.identity, request)
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_documents(self.schema.identity, DocumentScanRequest(2, first.continuation))
        second = view.scan_documents(self.schema.identity, replace(request, continuation=first.continuation))
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_documents(self.schema.identity, replace(request, continuation=first.continuation))
        last = view.scan_documents(self.schema.identity, replace(request, continuation=second.continuation))
        self.assertIsNone(last.continuation)
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_documents(self.schema.identity, replace(request, continuation=second.continuation))

    def test_tokens_do_not_cross_views_or_restarted_scans(self):
        self.seed()
        view = self.view()
        first = view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_documents(self.schema.identity, DocumentScanRequest(1, first.continuation))
        view.close()
        other = self.view()
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            other.scan_documents(self.schema.identity, DocumentScanRequest(1, first.continuation))

    def test_document_tokens_are_rejected_by_catalog_scans_and_invalidated(self):
        self.seed()
        view = self.view()
        first = view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        catalog = self.imported.catalogs[0]
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_catalog_values(catalog.identity, CatalogScanRequest(page_size=1, continuation=first.continuation), ('code',))
        view.scan_catalog_values(catalog.identity, CatalogScanRequest(), ('code',))
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_documents(self.schema.identity, DocumentScanRequest(1, first.continuation))

    def test_catalog_tokens_are_rejected_by_document_scans(self):
        self.vm.execute('For I=1 To 2 Do C=Catalogs.Categories.CreateItem();C.Code=String(I);C.Write();EndDo;')
        view = self.view()
        page = view.scan_catalog_values(self.imported.catalogs[0].identity, CatalogScanRequest(page_size=1), ('code',))
        self.assertIsNotNone(page.continuation)
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            view.scan_documents(self.schema.identity, DocumentScanRequest(1, page.continuation))

    def test_wrong_collection_and_key_kinds_are_rejected(self):
        view = self.view()
        for identity in (self.imported.catalogs[0].identity, uuid4()):
            with self.subTest(identity=identity), self.assertRaisesRegex(BackendError, 'not_found'):
                view.scan_documents(identity, DocumentScanRequest())
        for identity in (str(self.schema.identity), CatalogKey(view.database_id, self.schema.identity, uuid4()),
                         DocumentKey(view.database_id, self.schema.identity, uuid4())):
            with self.subTest(identity=identity), self.assertRaisesRegex(BackendError, 'invalid_input'):
                view.scan_documents(identity, DocumentScanRequest())
        with self.assertRaisesRegex(BackendError, 'not_found'):
            view.scan_catalog_values(self.schema.identity, CatalogScanRequest(), ('code',))

    def test_malformed_requests_fail_even_for_empty_documents(self):
        view = self.view()
        requests = [None, (), DocumentSelection()]
        requests += [DocumentScanRequest(page_size=size) for size in (True, False, 0, -1, 1001, 1.0, '1')]
        requests += [DocumentScanRequest(continuation=token) for token in (False, 123, '', 'x'*31, 'x'*32, 'x'*33)]
        for request in requests:
            with self.subTest(request=request), self.assertRaisesRegex(BackendError, 'invalid_input'):
                view.scan_documents(self.schema.identity, request)
        page = view.scan_documents(self.schema.identity, DocumentScanRequest())
        self.assertEqual(page.rows, ())
        self.assertIsNone(page.continuation)

    def test_read_only_backend_supports_query_scans(self):
        self.seed()
        self.context.close()
        self.context._backend = SQLiteCatalogBackend(self.path, read_only=True)
        view = self.view()
        self.assertEqual(len(view.scan_documents(self.schema.identity, DocumentScanRequest()).rows), 3)
        self.assertEqual(view.catalog_schema(self.imported.catalogs[0].identity), self.imported.catalogs[0])
        view.close()
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            self.context.backend.begin_document_write(uuid4())
        self.assertIsNone(self.context.backend._active)

    def test_scan_rejects_mutable_write_transactions(self):
        view = self.context.backend.begin_document_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                view.scan_documents(self.schema.identity, DocumentScanRequest())
        finally:
            view.rollback()
        self.assertIsNone(self.context.backend._active)

    def test_catalog_first_snapshot_blocks_independent_writer_until_close(self):
        self.seed()
        view = self.view()
        view.scan_catalog_values(self.imported.catalogs[0].identity, CatalogScanRequest(), ('code',))
        with closing(sqlite3.connect(self.path, timeout=0)) as writer:
            writer.execute('UPDATE document_record SET deletion_mark=1')
            page = view.scan_documents(self.schema.identity, DocumentScanRequest(1))
            self.assertFalse(page.rows[0].deletion_mark)
            with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                writer.commit()
            rest = view.scan_documents(self.schema.identity, DocumentScanRequest(1, page.continuation))
            self.assertFalse(rest.rows[0].deletion_mark)
            view.close()
            writer.commit()
        other = self.view()
        self.assertTrue(all(card.deletion_mark for card in other.scan_documents(self.schema.identity, DocumentScanRequest()).rows))

    def test_close_discards_cursor_and_releases_owned_connection(self):
        self.seed()
        view = self.view()
        page = view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        connection = view._connection
        view.close()
        view.close()
        self.assertIsNone(view._view._scan_cursor)
        self.assertIsNone(self.context.backend._active)
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            connection.execute('SELECT 1')
        with self.assertRaisesRegex(BackendError, 'closed'):
            view.scan_documents(self.schema.identity, DocumentScanRequest(1, page.continuation))
        self.assertEqual(len(self.view().scan_documents(self.schema.identity, DocumentScanRequest()).rows), 3)

    def test_malformed_later_card_fails_before_first_page_and_can_close(self):
        self.seed()
        self.sql('UPDATE document_record SET date=? WHERE number=?', ('20261309000000', '000000003'))
        view = self.view()
        with self.assertRaisesRegex(BackendError, 'integrity'):
            view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        self.assertIsNone(view._view._scan_cursor)
        view.close()
        self.assertIsNone(self.context.backend._active)
        self.sql('UPDATE document_record SET date=?', ('20261109000000',))
        self.assertEqual(len(self.view().scan_documents(self.schema.identity, DocumentScanRequest()).rows), 3)

    def test_query_view_constructor_failure_releases_transaction(self):
        with patch('yadinassi.sqlite_catalog.DocumentView', side_effect=BackendError('integrity')):
            with self.assertRaisesRegex(BackendError, 'integrity'):
                self.context.backend.begin_query_read()
        self.assertIsNone(self.context.backend._active)
        self.assertEqual(self.view().documents(), self.imported.documents)

    def test_legacy_query_view_does_not_upgrade_storage_or_begin_read(self):
        backend = SQLiteCatalogBackend.create(Path(self.temp.name)/'legacy.sqlite', import_configuration(configuration_files()))
        try:
            version = backend.storage_version
            with closing(backend.begin_query_read()) as view:
                self.assertEqual(view.documents(), ())
                self.assertEqual(view.catalog_schema(backend._schemas[0].identity), backend._schemas[0])
                with self.assertRaisesRegex(BackendError, 'not_found'):
                    view.scan_documents(self.schema.identity, DocumentScanRequest())
            with closing(backend.begin_read()) as original:
                self.assertFalse(hasattr(original, 'scan_documents'))
            self.assertEqual(backend.storage_version, version)
            with closing(sqlite3.connect(backend.path)) as connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone(), (version,))
                self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name='document_record'").fetchall(), [])
        finally:
            backend.close()

    def test_stream_reuses_one_ordered_select_and_retains_one_lookahead(self):
        self.seed(5)
        view = self.view()
        statements = []
        view._connection.set_trace_callback(statements.append)
        request = DocumentScanRequest(1)
        numbers = []
        while True:
            page = view.scan_documents(self.schema.identity, request)
            numbers.extend(card.number for card in page.rows)
            if page.continuation is None: break
            self.assertIsInstance(view._view._document_scan_stream, sqlite3.Cursor)
            self.assertEqual(len(view._view._document_scan_lookahead), 7)
            self.assertEqual(len(view._view._scan_cursor), 2)
            request = replace(request, continuation=page.continuation)
        self.assertEqual(numbers, [str(i).zfill(9) for i in range(1, 6)])
        self.assertEqual(sum('ORDER BY date,number,record_id' in sql for sql in statements), 1)
        self.assertIsNone(view._view._document_scan_stream)
        self.assertIsNone(view._view._document_scan_lookahead)

    def test_restarting_or_exhausting_scan_explicitly_closes_stream(self):
        self.seed()
        view = self.view()
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        old = view._view._document_scan_stream
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        current = view._view._document_scan_stream
        self.assertIsNot(old, current)
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            old.fetchone()
        view.scan_documents(self.schema.identity, DocumentScanRequest())
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            current.fetchone()
        self.assertIsNone(view._view._document_scan_stream)

    def test_catalog_scan_and_section_scan_close_document_stream(self):
        self.seed()
        view = self.view()
        catalog = self.imported.catalogs[0]
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        stream = view._view._document_scan_stream
        view.scan_catalog_values(catalog.identity, CatalogScanRequest(), ('code',))
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            stream.fetchone()
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        stream = view._view._document_scan_stream
        with self.assertRaisesRegex(BackendError, 'not_found'):
            view.scan_catalog_section(catalog.identity, uuid4(), CatalogScanRequest())
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            stream.fetchone()
        self.assertIsNone(view._view._document_scan_lookahead)

    def test_decode_error_closes_live_stream_and_token(self):
        self.seed()
        view = self.view()
        page = view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        stream = view._view._document_scan_stream
        with patch.object(view, '_card', side_effect=BackendError('integrity')):
            with self.assertRaisesRegex(BackendError, 'integrity'):
                view.scan_documents(self.schema.identity, DocumentScanRequest(1, page.continuation))
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            stream.fetchone()
        self.assertIsNone(view._view._document_scan_stream)
        self.assertIsNone(view._view._document_scan_lookahead)
        self.assertIsNone(view._view._scan_cursor)
        view.close()
        self.assertIsNone(self.context.backend._active)

    def test_backend_close_and_rollback_close_live_stream(self):
        self.seed()
        view = self.view()
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        stream = view._view._document_scan_stream
        view.rollback()
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            stream.fetchone()
        view = self.view()
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        stream = view._view._document_scan_stream
        self.context.backend.close()
        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
            stream.fetchone()
        self.assertIsNone(view._view._document_scan_stream)
        self.assertIsNone(self.context.backend._active)

        # Cleanup must release the connection without replacing an interruption
        # from its owned stream with a later ordinary rollback failure.
        from types import SimpleNamespace
        from yadinassi.sqlite_catalog import _close_owned_connection
        class Stream:
            def close(self): raise MemoryError('stream interruption')
        class Connection:
            in_transaction = True
            closed = False
            def execute(self, text): raise ValueError('rollback failure')
            def close(self): self.closed = True
        connection = Connection()
        owner = SimpleNamespace(_connection=connection, _document_scan_stream=Stream(),
                                _backend=SimpleNamespace(_active=None))
        owner._backend._active = owner
        with self.assertRaisesRegex(MemoryError, 'stream interruption'):
            _close_owned_connection(owner)
        self.assertTrue(connection.closed)
        self.assertIsNone(owner._backend._active)

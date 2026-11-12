"""Короткие logical-port leases и полностью проверенные detached списки."""
from dataclasses import replace, FrozenInstanceError
from unittest import TestCase, mock
from uuid import UUID
from yadinassi.catalog_backend import (Capabilities, CatalogSchema, CatalogKey,
    CatalogValueRow, CatalogValuePage, BackendError)
from yadinassi.ui.catalog_view import CatalogRepository
from yadinassi.ui.protocol import UIError
from ui_catalog_fixture import repository


class SummaryTests(TestCase):
    def fixture(self, count=3):
        schema = CatalogSchema(UUID(int=2), 'Items', 32, 64)
        view = mock.Mock(database_id=UUID(int=1), configuration_generation=1)
        view.catalogs.return_value = (schema,)
        view.catalog_schema.return_value = schema
        rows = tuple(CatalogValueRow(CatalogKey(UUID(int=1), schema.identity, UUID(int=i+10)),
                     (f'{i:04}', f'Item {i}', False)) for i in range(count))
        def scan(target, request, fields):
            self.assertEqual(fields, ('code', 'description', 'deletion_mark'))
            start = 0 if request.continuation is None else int(request.continuation, 16)
            end = min(start+256, len(rows))
            return CatalogValuePage(rows[start:end], f'{end:032x}' if end < len(rows) else None)
        view.scan_catalog_values.side_effect = scan
        backend = mock.Mock()
        backend.capabilities.return_value = Capabilities()
        backend.begin_read.return_value = view
        repo = CatalogRepository(backend, own_backend=False)
        return repo, view, backend, str(schema.identity), rows

    def test_real_sqlite_summary_and_fresh_card(self):
        repo, _, _, state = repository(self)
        summary = repo.load_summary(state['product'])
        self.assertIsNone(repo._view)
        self.assertEqual(len(summary.cards), 3)
        self.assertEqual(len(summary.cards[0].fields), 3)
        full = repo.load(state['product'], record=UUID(summary.cards[0].reference.record))
        self.assertGreater(len(full.cards[0].fields), 3)

    def test_over_thousand_detached_search_sort_and_short_lease(self):
        repo, view, backend, identity, _ = self.fixture(1001)
        result = repo.load_summary(identity)
        view.close.assert_called_once()
        backend.close.assert_not_called()
        self.assertEqual(len(result.cards), 1001)
        self.assertEqual(len(result.select(query='ITEM 1000').cards), 1)
        self.assertEqual(result.select(order='description').page()['total'], 1001)
        with self.assertRaises(FrozenInstanceError): result.cards = ()
        view.select_catalog.assert_not_called()

    def test_full_snapshot_limits_before_search(self):
        for setting, limit in [('MAX_SUMMARY_ROWS', 2), ('MAX_SUMMARY_BYTES', 1)]:
            repo, view, _, identity, _ = self.fixture()
            with mock.patch('yadinassi.ui.catalog_view.'+setting, limit):
                with self.assertRaisesRegex(UIError, 'message_limit'): repo.load_summary(identity)
            view.close.assert_called_once()

    def test_bad_rows_and_duplicate_ids(self):
        for change in ['foreign', 'duplicate', 'boolean', 'unicode', 'length']:
            repo, view, _, identity, rows = self.fixture()
            bad = rows[0]
            if change == 'foreign': bad = replace(bad, key=replace(bad.key, database_id=UUID(int=9)))
            elif change == 'boolean': bad = replace(bad, values=('A', 'B', 1))
            elif change == 'unicode': bad = replace(bad, values=('A', '\ud800', False))
            elif change == 'length': bad = replace(bad, values=('A'*33, 'B', False))
            view.scan_catalog_values.side_effect = None
            view.scan_catalog_values.return_value = CatalogValuePage((bad, bad) if change == 'duplicate' else (bad,), None)
            with self.assertRaises(UIError): repo.load_summary(identity)
            view.close.assert_called_once()

    def test_cursor_loop_empty_and_malformed(self):
        for token, empty in [('f'*32, False), ('f'*32, True), ('bad', False)]:
            repo, view, _, identity, rows = self.fixture()
            view.scan_catalog_values.side_effect = None
            view.scan_catalog_values.return_value = CatalogValuePage(() if empty else rows, token)
            with self.assertRaises(UIError): repo.load_summary(identity)
            view.close.assert_called_once()

    def test_identity_and_schema_change_refused(self):
        for mode in ['identity', 'schema']:
            repo, view, _, identity, _ = self.fixture()
            original = view.catalogs.return_value
            def catalogs():
                if view.scan_catalog_values.call_count:
                    if mode == 'identity': view.configuration_generation = 2
                    else: return (replace(original[0], name='Changed'),)
                return original
            view.catalogs.side_effect = catalogs
            with self.assertRaises(UIError): repo.load_summary(identity)
            view.close.assert_called_once()

    def test_unsupported_scan_and_close_failure(self):
        repo, view, _, identity, _ = self.fixture()
        view.scan_catalog_values = None
        with self.assertRaisesRegex(UIError, 'catalog_unavailable'): repo.load_summary(identity)
        view.close.assert_called_once()
        repo, view, _, identity, _ = self.fixture()
        view.close.side_effect = BackendError('storage_error')
        with self.assertRaisesRegex(UIError, 'catalog_unavailable'): repo.load_summary(identity)
        view.close.assert_called_once()

    def test_query_and_order_exact_types_and_closed_repository(self):
        repo, _, _, identity, _ = self.fixture()
        result = repo.load_summary(identity)
        for query in [None, 'x'*129, '\x00', '\ud800']:
            with self.assertRaises(UIError): result.select(query=query)
        for order in [None, 'ref', True]:
            with self.assertRaises(UIError): result.select(order=order)
        repo.close()
        with self.assertRaises(UIError): repo.load_summary(identity)

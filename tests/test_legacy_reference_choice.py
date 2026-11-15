"""Host chooser: no writes, live leases or renderer-selected record grants."""
from unittest import TestCase, mock
from uuid import UUID
from yadinassi.ui.catalog_view import CatalogInfo, CatalogSummaryView, CatalogCardSnapshot, CatalogView
from yadinassi.ui.protocol import CatalogRef, UIError
from yadinassi.ui.legacy_reference_choice import LegacyReferenceChooser


class LegacyChoiceTests(TestCase):
    def fixture(self, count=65):
        target = UUID(int=2)
        self.pin = ('editor-1', 'field', 'source-1', 'old-value')
        rows = tuple(CatalogCardSnapshot(CatalogRef(str(target), str(UUID(int=i+10))),
                     'Items', (), (f'{i:04}', f'Item {i}', False)) for i in range(count))
        snapshot = CatalogSummaryView(CatalogInfo(str(target), 'Items'), rows)
        chooser = LegacyReferenceChooser(object(), target, lambda: self.pin)
        chooser._load = mock.Mock(return_value=snapshot)
        return chooser, snapshot

    def test_pages_search_and_revocation(self):
        chooser, _ = self.fixture()
        first = chooser.begin(); ticket = first['ticket']
        self.assertEqual(first['navigation']['total'], 65)
        second = chooser.page(ticket, first['navigation']['next'])
        self.assertEqual(second['navigation']['page'], 2)
        with self.assertRaises(UIError): chooser.page(ticket, first['navigation']['next'])
        with self.assertRaises(UIError): chooser.apply(ticket, first['rows'][0]['choice'])
        found = chooser.search(ticket, 'ITEM 64')
        self.assertEqual(len(found['rows']), 1)
        chooser._load.assert_called_once()

    def test_apply_fresh_read_and_no_write(self):
        chooser, snapshot = self.fixture()
        first = chooser.begin()
        with mock.patch('yadinassi.ui.legacy_reference_choice.CatalogRepository') as cls:
            cls.return_value.load.return_value = CatalogView(snapshot.catalog, snapshot.cards[:1])
            result = chooser.apply(first['ticket'], first['rows'][0]['choice'])
            self.assertEqual(result, snapshot.cards[0].reference)
            cls.return_value.close.assert_called_once()
            self.assertTrue(cls.return_value.load.call_args.kwargs['summary_only'])
        with self.assertRaises(UIError): chooser.clear(first['ticket'])

    def test_deleted_or_missing_apply_refused(self):
        for deleted in (False, True):
            chooser, snapshot = self.fixture()
            first = chooser.begin()
            rows = () if not deleted else (CatalogCardSnapshot(snapshot.cards[0].reference, 'Items', (), ('0','Item',True)),)
            with mock.patch('yadinassi.ui.legacy_reference_choice.CatalogRepository') as cls:
                cls.return_value.load.return_value = CatalogView(snapshot.catalog, rows)
                with self.assertRaises(UIError): chooser.apply(first['ticket'], first['rows'][0]['choice'])
                cls.return_value.close.assert_called_once()

    def test_changed_owner_row_source_or_value_fail_closed(self):
        for index in range(4):
            chooser, _ = self.fixture()
            first = chooser.begin()
            pin = list(self.pin); pin[index] = 'changed'; self.pin = tuple(pin)
            with self.assertRaises(UIError): chooser.search(first['ticket'], '')
            with self.assertRaises(UIError): chooser.clear(first['ticket'])

    def test_preflight_failure_preserves_page(self):
        chooser, _ = self.fixture()
        first = chooser.begin()
        chooser._preflight = mock.Mock(side_effect=UIError('message_limit'))
        with self.assertRaises(UIError): chooser.page(first['ticket'], first['navigation']['next'])
        chooser._preflight = lambda value: None
        self.assertEqual(chooser.page(first['ticket'], first['navigation']['next'])['navigation']['page'], 2)

    def test_refresh_new_snapshot_cancel_and_clear(self):
        chooser, snapshot = self.fixture()
        first = chooser.begin()
        chooser._load.return_value = CatalogSummaryView(snapshot.catalog, ())
        fresh = chooser.refresh(first['ticket'])
        self.assertEqual(fresh['rows'], [])
        with self.assertRaises(UIError): chooser.apply(first['ticket'], first['rows'][0]['choice'])
        self.assertEqual(chooser.clear(first['ticket']).record, str(UUID(int=0)))
        with self.assertRaises(UIError): chooser.refresh(first['ticket'])

    def test_deleted_rows_not_published_and_invalid_witness(self):
        chooser, snapshot = self.fixture(1)
        chooser._load.return_value = CatalogSummaryView(snapshot.catalog,
            (CatalogCardSnapshot(snapshot.cards[0].reference, 'Items', (), ('A','B',True)),))
        self.assertEqual(chooser.begin()['navigation']['total'], 0)
        self.pin = ('owner', [])
        with self.assertRaises(UIError): chooser.begin()

    def test_changed_witness_during_capture_never_publishes(self):
        chooser, snapshot = self.fixture()
        def load():
            self.pin = ('changed',)
            return snapshot
        chooser._load.side_effect = load
        with self.assertRaises(UIError): chooser.begin()
        self.assertIsNone(chooser._ticket)

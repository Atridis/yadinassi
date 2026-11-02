"""Actual FileDBContext reads on synthetic transport; no new native evidence."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ui_catalog_fixture import repository
from yadinassi.database_context import FileDBContext
from yadinassi.ui.catalog_view import CatalogRepository
from yadinassi.ui.protocol import CatalogRef, UIError, encode_line


class UICatalogViewTests(unittest.TestCase):
    def test_real_parser_inventory_list_card_and_link(self):
        repo, path, before, state = repository(self)
        inventory = repo.inventory()
        self.assertEqual(len(inventory), 2)
        product = repo.load(state['physical']['catalogs'][0]['metadata_uuid'])
        category = repo.load(state['physical']['catalogs'][1]['metadata_uuid'])
        self.assertEqual(len(product.cards), 3)
        self.assertEqual(len(category.cards), 1)
        self.assertEqual([card.values[0] for card in product.cards], ['10', '20', '30'])
        found = []
        for card in product.cards:
            for field, value in zip(card.fields, card.values):
                if type(value) is CatalogRef and value == category.cards[0].reference:
                    found.append((card, field, value))
        self.assertTrue(found)
        card, field, value = found[0]
        self.assertIs(product.card(card.reference), card)
        self.assertEqual(card.value(field.name.swapcase()), value)
        self.assertIs(category.card(value), category.cards[0])
        encode_line(card.wire())
        self.assertEqual(path.read_bytes(), before)

    def test_metadata_and_card_snapshots_are_immutable(self):
        repo, _, _, _ = repository(self)
        info = repo.inventory()[0]
        view = repo.load(info.identity)
        card = view.cards[0]
        for target, name, value in ((info, 'name', 'changed'), (view, 'cards', ()),
                                    (card, 'values', ()), (card.fields[0], 'name', 'changed')):
            with self.assertRaises(FrozenInstanceError): setattr(target, name, value)
        detached = card.wire()
        detached['fields'][0]['value'] = {'type': 'String', 'value': 'changed'}
        self.assertNotEqual(card.wire(), detached)

    def test_pages_empty_and_boundaries(self):
        repo, path, before, _ = repository(self)
        view = repo.load(repo.inventory()[0].identity)
        self.assertEqual(view.page(1, 1)['rows'][0]['reference']['record'],
                         view.cards[1].reference.record)
        self.assertEqual(view.page(len(view.cards), 1)['rows'], [])
        for offset, limit in ((-1, 1), (4, 1), (0, 0), (0, 65), (False, 1), (0, True)):
            with self.assertRaises(UIError): view.page(offset, limit)
        self.assertEqual(path.read_bytes(), before)
        empty, _, _, _ = repository(self, empty=True)
        view = empty.load(empty.inventory()[0].identity)
        self.assertEqual(view.cards, ())
        self.assertEqual(view.page()['total'], 0)

    def test_missing_empty_and_wrong_catalog_refs_are_not_default_cards(self):
        repo, _, _, _ = repository(self)
        infos = repo.inventory(); view = repo.load(infos[0].identity)
        for reference, reason in ((CatalogRef(infos[1].identity, view.cards[0].reference.record), 'catalog_identity'),
                                  (CatalogRef(infos[0].identity, '00000000-0000-0000-0000-000000000000'), 'empty_reference'),
                                  (CatalogRef(infos[0].identity, '00000000-0000-0000-0000-000000000001'), 'record_not_found')):
            with self.assertRaisesRegex(UIError, '^' + reason + '$'): view.card(reference)
        with self.assertRaisesRegex(UIError, 'catalog_not_found'):
            repo.load('00000000-0000-0000-0000-000000000001')

    def test_source_changes_are_detected_between_reads(self):
        repo, path, before, _ = repository(self)
        info = repo.inventory()[0]
        view = repo.load(info.identity)
        path.write_bytes(before + b'changed')
        for operation in (repo.inventory, repo.check_source, lambda: repo.load(info.identity)):
            with self.assertRaisesRegex(UIError, 'catalog_unavailable'): operation()
        self.assertEqual(len(view.cards), 3)  # Detached old snapshot is immutable.

    def test_failed_initial_read_pins_source_generation(self):
        repo, path, before, _ = repository(self)
        original = repo._metadata._snapshot
        def changed():
            result = original()
            path.write_bytes(before + b'changed')
            return result
        with mock.patch.object(repo._metadata, '_snapshot', side_effect=changed):
            with self.assertRaises(UIError): repo.inventory()
        with self.assertRaisesRegex(UIError, 'catalog_unavailable'): repo.inventory()

    def test_missing_invalid_source_does_not_leak_path(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = CatalogRepository(FileDBContext(directory))
            with self.assertRaisesRegex(UIError, '^catalog_unavailable$'): repo.inventory()
            Path(directory, '1Cv8.1CD').write_bytes(b'not a database')
            with self.assertRaisesRegex(UIError, '^metadata_unavailable$'): repo.inventory()
        with self.assertRaises(TypeError): CatalogRepository(object())

    def test_unsupported_path_never_reaches_stat_or_database_reader(self):
        for directory in ('\\\\blocked-host\\share', '//blocked-host/share', 'invalid"path'):
            repo = CatalogRepository(FileDBContext(directory))
            with mock.patch('yadinassi.ui.catalog_view.os.stat', side_effect=AssertionError('must not stat')), \
                 mock.patch.object(repo._metadata, '_snapshot', side_effect=AssertionError('must not read')):
                with self.assertRaisesRegex(UIError, '^catalog_unavailable$'): repo.inventory()

    def test_all_operations_are_readonly_and_no_commit_stub(self):
        repo, path, before, _ = repository(self)
        info = repo.inventory()[0]
        view = repo.load(info.identity)
        capabilities = repo.capabilities()
        self.assertFalse(capabilities['canWrite'])
        self.assertFalse(capabilities['canEdit'])
        self.assertFalse(capabilities['actual1CForms'])
        capabilities['canWrite'] = True
        self.assertFalse(repo.capabilities()['canWrite'])
        with self.assertRaisesRegex(UIError, '^write_unsupported$'): repo.commit(view.cards[0])
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__': unittest.main()

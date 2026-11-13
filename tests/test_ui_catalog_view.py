"""Logical UI adapter on real owned SQLite files; no native-format fixtures."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import ast
import tempfile
import unittest
from unittest import mock
from uuid import UUID

from ui_catalog_fixture import configuration_files, repository
from yadinassi.catalog_backend import BackendError, CatalogSelection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.catalog_view import CatalogRepository
from yadinassi.ui.protocol import CatalogRef, UIError, encode_line


class UICatalogViewTests(unittest.TestCase):
    def test_sqlite_reopen_inventory_list_card_and_link(self):
        repo, path, before, state = repository(self)
        self.assertTrue(state['source_removed'])
        self.assertEqual([item.name for item in repo.inventory()], ['Categories', 'Products'])
        product = repo.load(state['product'])
        category = repo.load(state['category'])
        self.assertEqual(len(product.cards), 3)
        self.assertEqual(len(category.cards), 1)
        self.assertEqual([card.values[0] for card in product.cards], ['10', '20', '30'])
        card = product.cards[0]
        self.assertIs(product.card(card.reference), card)
        value = card.value('cATEGORY')
        self.assertEqual(value, category.cards[0].reference)
        self.assertIs(category.card(value), category.cards[0])
        self.assertEqual(card.value('Amount').as_tuple().exponent, -2)
        self.assertEqual(str(card.value('Moment')), '29.02.2024 12:30:45')
        encode_line(card.wire())
        repo.close()
        reopened = SQLiteCatalogBackend(path, read_only=True)
        try:
            self.assertEqual(reopened.export_configuration(), configuration_files())
        finally:
            reopened.close()
        self.assertEqual(path.read_bytes(), before)

    def test_metadata_and_card_snapshots_are_immutable(self):
        repo, _, _, state = repository(self)
        info = next(item for item in repo.inventory() if item.identity == state['product'])
        view = repo.load(info.identity)
        card = view.cards[0]
        for target, name, value in ((info, 'name', 'changed'), (view, 'cards', ()),
                                    (card, 'values', ()), (card.fields[0], 'name', 'changed')):
            with self.assertRaises(FrozenInstanceError): setattr(target, name, value)
        detached = card.wire()
        detached['fields'][0]['value'] = {'type': 'String', 'value': 'changed'}
        self.assertNotEqual(card.wire(), detached)

    def test_pages_empty_and_boundaries(self):
        repo, path, before, state = repository(self)
        view = repo.load(state['product'])
        self.assertEqual(view.page(1, 1)['rows'][0]['reference']['record'],
                         view.cards[1].reference.record)
        self.assertEqual(view.page(len(view.cards), 1)['rows'], [])
        for offset, limit in ((-1, 1), (4, 1), (0, 0), (0, 65), (False, 1), (0, True)):
            with self.assertRaises(UIError): view.page(offset, limit)
        self.assertEqual(path.read_bytes(), before)
        empty, _, _, state = repository(self, empty=True)
        view = empty.load(state['product'])
        self.assertEqual(view.cards, ())
        self.assertEqual(view.page()['total'], 0)

    def test_missing_empty_and_wrong_catalog_refs_are_not_default_cards(self):
        repo, _, _, state = repository(self)
        view = repo.load(state['product'])
        for reference, reason in ((CatalogRef(state['category'], view.cards[0].reference.record), 'catalog_identity'),
                                  (CatalogRef(state['product'], str(UUID(int=0))), 'empty_reference'),
                                  (CatalogRef(state['product'], str(UUID(int=1))), 'record_not_found')):
            with self.assertRaisesRegex(UIError, '^' + reason + '$'): view.card(reference)
        with self.assertRaisesRegex(UIError, 'catalog_not_found'): repo.load(str(UUID(int=1)))

    def test_closed_view_refuses_reads_and_old_snapshot_stays_detached(self):
        repo, _, _, state = repository(self)
        view = repo.load(state['product'])
        repo.close(); repo.close()
        for operation in (repo.inventory, repo.check_source, lambda: repo.load(state['product'])):
            with self.assertRaisesRegex(UIError, 'catalog_unavailable'): operation()
        self.assertEqual(len(view.cards), 3)
        self.assertEqual(view.cards[0].values[0], '10')

    def test_port_errors_are_finite_and_no_partial_metadata_is_cached(self):
        repo, _, _, _ = repository(self)
        repo.inventory()
        with mock.patch.object(repo._view, 'catalogs', side_effect=BackendError('schema_changed')):
            with self.assertRaisesRegex(UIError, '^catalog_unavailable$'): repo.inventory()
        self.assertEqual(len(repo.inventory()), 2)
        with self.assertRaises(TypeError): CatalogRepository(object())

    def test_readonly_open_never_creates_missing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing.sqlite'
            with self.assertRaises(BackendError): SQLiteCatalogBackend(missing, read_only=True)
            self.assertFalse(missing.exists())

    def test_cross_database_rows_and_field_refs_are_rejected(self):
        repo, _, _, state = repository(self)
        repo.inventory()
        rows = repo._view.select_catalog(UUID(state['product']), CatalogSelection())
        wrong_database = UUID(int=42)
        forged_row = replace(rows[0], key=replace(rows[0].key, database_id=wrong_database))
        forged_ref = replace(rows[0], values=rows[0].values[:-1] +
                             (replace(rows[0].values[-1], database_id=wrong_database),))
        for forged in (forged_row, forged_ref):
            with mock.patch.object(repo._view, 'select_catalog', return_value=(forged,)):
                with self.assertRaisesRegex(UIError, '^catalog_identity$'): repo.load(state['product'])

    def test_wrong_schema_and_overflow_refuse_without_a_partial_list(self):
        repo, _, _, state = repository(self)
        repo.inventory()
        category = repo._view.catalog_schema(UUID(state['category']))
        with mock.patch.object(repo._view, 'catalog_schema', return_value=category):
            with self.assertRaisesRegex(UIError, '^metadata_unavailable$'): repo.load(state['product'])
        with mock.patch.object(repo._view, 'select_catalog', side_effect=BackendError('unsupported')):
            with self.assertRaisesRegex(UIError, '^catalog_unavailable$'): repo.load(state['product'])
        self.assertEqual(len(repo.load(state['product']).cards), 3)

    def test_all_operations_are_readonly_even_with_writable_backend(self):
        repo, path, before, state = repository(self)
        repo.close()
        backend = SQLiteCatalogBackend(path)
        repo = CatalogRepository(backend)
        self.addCleanup(repo.close)
        view = repo.load(state['product'])
        self.assertTrue(backend.capabilities().catalog_update)
        capabilities = repo.capabilities()
        self.assertFalse(capabilities['canWrite'])
        self.assertFalse(capabilities['canEdit'])
        self.assertFalse(capabilities['actual1CForms'])
        capabilities['canWrite'] = True
        self.assertFalse(repo.capabilities()['canWrite'])
        with mock.patch.object(backend, 'begin_write', side_effect=AssertionError('must not write')):
            with self.assertRaisesRegex(UIError, '^write_unsupported$'): repo.commit(view.cards[0])
        self.assertEqual(path.read_bytes(), before)

    def test_adapter_has_only_logical_backend_dependencies(self):
        import yadinassi.ui.catalog_view as module
        tree = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertTrue({'catalog_backend', 'dates', 'protocol'}.issubset(imported))
        self.assertFalse({'database_context', 'sqlite_catalog', 'catalogs', 'catalog_types',
                          'storage', 'metadata'}.intersection(imported))
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
        self.assertFalse({'sqlite3', 'os', 'stat'}.intersection(names))


if __name__ == '__main__': unittest.main()

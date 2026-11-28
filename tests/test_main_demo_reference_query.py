"""Warehouse validation uses one typed projection on the caller's SQLite view."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_main_demo_owned_handler_write as support
from test_main_demo_configuration import source
from yadinassi.configuration.demos.product_list_check import check_product_list
from yadinassi import BSLRuntimeError
from yadinassi.db.catalog.catalog_object_preparation import CatalogWriteRefused, prepare_catalog_object
from yadinassi.db.database_transactions import current
from yadinassi.db.sqlite import sqlite_section_delta
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.execution.direct.python_direct_catalog_reference_query import ReferenceQuery
from yadinassi.forms.form_event_simulation import simulate_product_form_event
import unittest


class MainDemoReferenceQueryTests(unittest.TestCase):
    setUp = support.MainDemoOwnedHandlerWriteTests.setUp

    def record_marks(self):
        calls = []
        original = _View._read_catalog_reference_marks

        def observe(view, schema, references):
            self.assertIs(view, self.backend._active)
            self.assertTrue(view._connection.in_transaction)
            trace = []
            view._connection.set_trace_callback(trace.append)
            try:
                return original(view, schema, references)
            finally:
                view._connection.set_trace_callback(None)
                calls.append((view, references, trace))
        return calls, patch.object(_View, '_read_catalog_reference_marks', observe)

    def test_programmatic_and_form_keep_row_order_for_empty_missing_deleted_and_duplicates(self):
        warehouse = self.vm.variables['склад']
        warehouse.set_member('DeletionMark', True)
        warehouse.write()
        missing = warehouse._manager._ref(uuid4())
        known = warehouse.get_member('Ref')
        rows = self.card.get_member('Склады')
        rows.clear()
        for ref in (None, missing, known, warehouse._manager._ref(known.reference_uuid)):
            row = rows.add()
            if ref is not None: row.set_member('Склад', ref)
        expected = [
            ('Заполните склад в строке 1.', 'Склады[].Склад'),
            ('Выбранный склад не существует.', 'Склады[1].Склад'),
            ('Склад помечен на удаление. Выберите другой склад.', 'Склады[2].Склад'),
            ('Этот склад уже указан в строке 3. Удалите повторяющуюся строку.', 'Склады[3].Склад'),
        ]
        calls, observed = self.record_marks()
        with observed, self.assertRaises(CatalogWriteRefused) as refused:
            self.card.write()
        self.assertEqual([(m.text, m.field) for m in refused.exception.messages], expected)
        self.assertEqual(len(calls), 1)
        view, references, trace = calls[0]
        self.assertIsNotNone(view._operation_id)
        self.assertEqual(references, (missing.reference_uuid, known.reference_uuid, known.reference_uuid))
        self.assertEqual(len(trace), 1)
        self.assertIn('SELECT record_id,deletion_mark', trace[0])
        self.assertIn('record_id IN (', trace[0])

        files = source()
        base = 'Catalogs/Номенклатура/'
        object_source = files[base + 'Ext/ObjectModule.bsl']
        calls, observed = self.record_marks()
        with observed:
            result = simulate_product_form_event(files[base + 'Forms/ФормаЭлемента/Ext/Form/Module.bsl'],
                object_source, self.card, event='BeforeWriteAtServer')
        self.assertTrue(result.cancel)
        self.assertEqual([(m.text, m.field) for m in result.messages], expected)
        self.assertEqual((len(calls), len(calls[0][2])), (1, 1))
        self.assertIsNone(calls[0][0]._operation_id)
        # Historical bytes are not another executable grant on a MainDemo DB.
        old = Path(__file__).with_name('fixtures').joinpath('legacy_demo_object_module.bsl').read_bytes()
        with self.assertRaisesRegex(ValueError, 'original source required'):
            simulate_product_form_event(files[base + 'Forms/ФормаЭлемента/Ext/Form/Module.bsl'],
                old, self.card, event='BeforeWriteAtServer')

    def test_list_reuses_same_read_view_and_preserves_deletion_diagnostic(self):
        warehouse = self.vm.variables['склад']
        warehouse.set_member('DeletionMark', True)
        warehouse.write()
        calls, observed = self.record_marks()
        with closing(self.backend.begin_read()) as view:
            sources = view.product_list_sources(self.card._key.catalog_id)
            with observed, patch.object(self.backend, '_connect', side_effect=AssertionError('extra connection')):
                result = check_product_list(self.card._manager, self.card.get_member('Ref'), view, *sources)
            self.assertIs(calls[0][0], view)
            self.assertEqual((len(calls), len(calls[0][2])), (1, 1))
        self.assertIn(('Склад помечен на удаление. Выберите другой склад.', 'Склады[].Склад'),
                      [(m.text, m.field) for m in result])

    def test_provider_respects_bind_limit_and_deduplicates_across_chunks(self):
        warehouse = self.vm.variables['склад']
        manager = warehouse._manager
        with closing(self.backend.begin_read()) as view:
            calls, observed = self.record_marks()
            with observed, patch.object(sqlite_section_delta, '_limit', return_value=1):
                rows = view._read_catalog_reference_marks(manager._schema,
                    (warehouse._key.record_id, uuid4(), warehouse._key.record_id))
            self.assertEqual(rows, ((warehouse._key.record_id, False),))
            self.assertEqual(len(calls[0][2]), 2)
            self.assertTrue(all('record_id IN (' in sql for sql in calls[0][2]))

    def test_actual_transaction_borrows_lease_and_uses_no_new_connection(self):
        original = _View._read_catalog_reference_marks
        admitted = []

        def observe(lease, *args):
            writer = current(self.backend).unit._view
            self.assertIs(self.backend._active, writer)
            self.assertIsNot(lease, writer)
            self.assertIs(lease._connection, writer._connection)
            self.assertIsNone(lease._operation_id)
            admitted.append(lease)
            with patch.object(self.backend, '_connect', side_effect=AssertionError('extra connection')):
                return original(lease, *args)

        with patch.object(_View, '_read_catalog_reference_marks', observe):
            self.vm.execute('НачатьТранзакцию(); Карточка.Записать(); ОтменитьТранзакцию();')
        self.assertEqual(len(admitted), 1)
        self.assertTrue(admitted[0]._closed)
        self.assertIsNone(self.backend._active)

    def test_wrong_catalog_is_refused_before_any_projection(self):
        text = source()['Catalogs/Номенклатура/Ext/ObjectModule.bsl'].decode('utf-8-sig')
        wrong = text.replace('ИЗ Справочник.Склады', 'ИЗ Справочник.ВидыНоменклатуры')
        with patch.object(_View, '_read_catalog_reference_marks') as sql:
            with self.assertRaisesRegex(BSLRuntimeError, 'same catalog reference required'):
                prepare_catalog_object(wrong, self.card)
            sql.assert_not_called()

    def test_other_query_shapes_and_non_array_parameters_are_not_admitted(self):
        prefix = 'SELECT Ref, DeletionMark FROM Catalog.Склады WHERE '
        for text in (prefix+'Description IN (&Refs)', prefix+'Ref = &Refs',
                     prefix+'Ref IN (&A, &B)', prefix+'Ref IN (&Refs) ORDER BY Ref',
                     prefix+'Ref IN (&Refs); SELECT Ref FROM Catalog.Склады',
                     'SELECT Ref, Description FROM Catalog.Склады WHERE Ref IN (&Refs)'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                ReferenceQuery(text)
        q = ReferenceQuery(prefix+'Ref IN (&Refs)')
        for values in ((), 1, [None]*1001):
            with self.assertRaises((ValueError, TypeError)):
                q.set_parameter('Refs', values)

"""Pinned original demo form handlers over disposable catalog buffers."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi.catalog_backend import BackendError, FieldSchema
from yadinassi.form_event_simulation import simulate_product_form_event
import test_catalog_object_preparation as fixture

BASE = Path(__file__).parent / 'fixtures/demo_cf/source/Catalogs/Номенклатура'
FORM = (BASE / 'Forms/ФормаЭлемента/Ext/Form/Module.bsl').read_bytes()
OBJECT = (BASE / 'Ext/ObjectModule.bsl').read_bytes()


class ProductFormEventTests(unittest.TestCase):
    setUp = fixture.CatalogObjectPreparationTests.setUp

    def run_event(self, event, **kwargs):
        return simulate_product_form_event(FORM, OBJECT, self.card, event=event, **kwargs)

    def test_description_original_trims_and_warns_without_write(self):
        self.card.set_member('Description', ' x ')
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('write')):
            result = self.run_event('DescriptionOnChange')
        self.assertEqual(self.card.get_member('Description'), 'x')
        self.assertEqual([m.field for m in result.messages], ['Объект.Наименование'])
        self.assertFalse(result.cancel)
        self.assertFalse(result.native_parity)
        self.assertTrue(self.card.is_new())

    def test_kind_empty_and_filled(self):
        self.assertEqual(self.run_event('KindOnChange').messages, ())
        self.vm.execute('Карточка.ВидНоменклатуры=Справочники.ВидыНоменклатуры.ПустаяСсылка();')
        self.assertEqual(self.run_event('KindOnChange').messages[0].field, 'Объект.ВидНоменклатуры')

    def test_current_row_missing_empty_and_duplicate(self):
        self.assertEqual(self.run_event('WarehouseOnChange').messages, ())
        row = self.card.get_member('Склады').add()
        result = self.run_event('WarehouseOnChange', current_row_id=row._identity)
        self.assertEqual(result.messages[0].field, 'Объект.Склады[1].Склад')
        row.set_member('Склад', self.vm.variables['склад'].get_member('Ref'))
        result = self.run_event('WarehouseOnChange', current_row_id=row._identity)
        self.assertIn('строке 1', result.messages[0].text)
        self.assertEqual(result.messages[0].field, 'Объект.Склады[1].Склад')

    def test_row_identity_tracks_current_order_and_deleted_row_fails(self):
        section = self.card.get_member('Склады')
        row = section.add()
        section.delete(section._rows[0])
        result = self.run_event('WarehouseOnChange', current_row_id=row._identity)
        # Original Формат renders zero as empty in this unmeasured runtime slice.
        self.assertEqual(result.messages[0].field, 'Объект.Склады[].Склад')
        section.delete(row)
        with self.assertRaises(ValueError):
            self.run_event('WarehouseOnChange', current_row_id=row._identity)

    def test_server_calls_original_object_preparation_and_never_writes(self):
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('write')):
            result = self.run_event('BeforeWriteAtServer')
        self.assertEqual(result.messages, ())
        self.assertFalse(result.cancel)
        self.assertEqual(self.card.get_member('Description'), 'Кабель USB-C')
        self.assertTrue(self.card.is_new())
        self.vm.execute('Карточка.ВидНоменклатуры=Справочники.ВидыНоменклатуры.ПустаяСсылка(); Карточка.Склады.Очистить();')
        result = self.run_event('BeforeWriteAtServer')
        self.assertTrue(result.cancel)
        self.assertEqual([m.field for m in result.messages], ['ВидНоменклатуры', 'Склады'])

    def test_server_preserves_cancellation_and_deletion_skip(self):
        self.assertTrue(self.run_event('BeforeWriteAtServer', cancel=True).cancel)
        self.card.set_member('Description', ' x ')
        self.card.set_member('DeletionMark', True)
        self.assertFalse(self.run_event('BeforeWriteAtServer').cancel)
        self.assertEqual(self.card.get_member('Description'), ' x ')

    def test_rejects_tampered_sources_before_candidate_mutation(self):
        for form, source in ((FORM+b' ', OBJECT), (FORM, OBJECT+b' '), (FORM.decode(), OBJECT)):
            with self.assertRaises(ValueError):
                simulate_product_form_event(form, source, self.card, event='DescriptionOnChange')
        self.assertEqual(self.card.get_member('Description'), '  Кабель USB-C  ')

    def test_rejects_wrong_event_row_and_flag(self):
        for event, kwargs in (('OnChange', {}), ('DescriptionOnChange', {'cancel': True}),
                ('BeforeWriteAtServer', {'cancel': 1}),
                ('KindOnChange', {'current_row_id': uuid4()}),
                ('WarehouseOnChange', {'current_row_id': str(uuid4())}),
                ('WarehouseOnChange', {'current_row_id': uuid4()})):
            with self.subTest(event=event, kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                self.run_event(event, **kwargs)

    def test_rejects_pending_write(self):
        self.card._pending_write = ('pending',)
        with self.assertRaises(BackendError) as caught:
            self.run_event('DescriptionOnChange')
        self.assertEqual(caught.exception.code, 'uncertain_commit')

    def test_rejects_extra_schema_member_and_excess_rows(self):
        schema = self.card._manager._schema
        self.card._manager._schema = replace(schema, fields=schema.fields + (
            FieldSchema(uuid4(), 'Write', 'string', (32,)),))
        with self.assertRaises(ValueError): self.run_event('DescriptionOnChange')
        self.card._manager._schema = schema
        for _ in range(32): self.card.get_member('Склады').add()
        with self.assertRaises(ValueError): self.run_event('WarehouseOnChange')

    def test_server_duplicate_separately_materialized_references(self):
        from yadinassi.unique_identifiers import BSLUUID
        original = self.card.get_member('Склады')._rows[0].get_member('Склад')
        manager = self.vm.variables['склад']._manager
        separate = manager.get_ref(BSLUUID(str(original.reference_uuid)))
        self.assertIsNot(separate, original)
        self.card.get_member('Склады').add().set_member('Склад', separate)
        result = self.run_event('BeforeWriteAtServer')
        self.assertTrue(result.cancel)
        self.assertIn('уже указан', result.messages[0].text)

    def test_reference_map_scope_and_replacement(self):
        from yadinassi.maps import BSLMap, BSLFixedMap
        from yadinassi.catalog_types import BSLCatalogReference, BSLCatalogType
        from uuid import uuid4
        reference = self.card.get_member('Склады')._rows[0].get_member('Склад')
        same = BSLCatalogReference(reference.value_type, reference.reference_uuid)
        other_record = BSLCatalogReference(reference.value_type, uuid4())
        other_snapshot = BSLCatalogReference(BSLCatalogType(reference.value_type.metadata_uuid,
            reference.value_type.name, object()), reference.reference_uuid)
        other_catalog = BSLCatalogReference(BSLCatalogType(uuid4(), 'Other',
            reference.value_type.snapshot), reference.reference_uuid)
        mapping = BSLMap(); mapping.set(reference, 'first'); mapping.set(same, 'second')
        self.assertEqual(mapping.get(reference), 'second')
        self.assertEqual(len(mapping._items), 1)
        self.assertEqual(BSLFixedMap(mapping).get(same), 'second')
        for other in (other_record, other_snapshot, other_catalog):
            self.assertIsNone(mapping.get(other))

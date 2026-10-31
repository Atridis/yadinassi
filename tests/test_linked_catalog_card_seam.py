"""Logical mixed-field seam only; no new CONFIG/physical codec acceptance."""
from dataclasses import FrozenInstanceError
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import UUID
import unittest

from yadinassi import Interpreter
from yadinassi.catalogs import CatalogCardField
from yadinassi.dates import BSLDate, date
from yadinassi.storage.catalog_metadata import CatalogMetadataIdentity

PRODUCTS = UUID(int=11)
CATEGORIES = UUID(int=22)
SHARED = UUID(int=33)
ABSENT = UUID(int=44)


def row(identity, code, description, **values):
    fields = {'_CODE': code, '_DESCRIPTION': description, '_MARKED': False, **values}
    return NS(reference_uuid=identity, physical_record=NS(fields=tuple(
        NS(declaration=NS(name=name), value=value) for name, value in fields.items())))


def result(identity, name, attributes, rows):
    return NS(identity=NS(metadata_uuid=str(identity), name=name),
              binding=NS(code_type=1, attributes=attributes), rows=rows)


class LinkedCatalogCardSeamTests(unittest.TestCase):
    def runtime(self):
        fields = (CatalogCardField('Label', '_FLD1', 'string'),
                  CatalogCardField('Price', '_FLD2', 'number'),
                  CatalogCardField('Enabled', '_FLD3', 'boolean'),
                  CatalogCardField('Effective', '_FLD4', 'datetime'),
                  CatalogCardField('Category', '_FLD5', 'catalog_ref', CATEGORIES))
        source = {
            'Products': result(PRODUCTS, 'Products', fields, tuple(
                row(identity, code, label, _FLD1=label, _FLD2=Decimal('12.50'),
                    _FLD3=enabled, _FLD4=effective, _FLD5=category)
                for identity, code, label, enabled, effective, category in (
                    (SHARED, '30', 'Present', True, date('20261031123456'), SHARED),
                    (UUID(int=34), '10', 'Empty', False, BSLDate(0), UUID(int=0)),
                    (UUID(int=35), '20', 'Absent', True, date('20261031123456'), ABSENT)))),
            'Categories': result(CATEGORIES, 'Categories', (), (row(SHARED, '10', 'Hardware'),)),
        }
        context = Mock()
        context.catalog_metadata.return_value = tuple(
            CatalogMetadataIdentity(str(identity), name)
            for identity, name in ((PRODUCTS, 'Products'), (CATEGORIES, 'Categories')))
        context.catalog_rows.side_effect = lambda name: source[name]
        output = []; runtime = Interpreter(output.append, database_context=context)
        self.addCleanup(runtime.close)
        return runtime, context, output, source

    def test_product_to_category_complete_bsl_read_flow(self):
        vm, context, output, _ = self.runtime()
        vm.execute('''
S = Catalogs.Products.Select();
While S.Next() Do
 Message(S.Code); Message(S.Label); Message(S.Price); Message(S.Enabled);
 Message(TypeOf(S.Effective) = Type("Date"));
 Message(ValueIsFilled(S.Effective));
 Message(TypeOf(S.Category) = Type("CatalogRef.Categories"));
 Message(ValueIsFilled(S.Category)); Message(S.Category.Description);
 Message(S.Category.Metadata() = Metadata.Catalogs.Categories);
EndDo;
P = Catalogs.Products.FindByCode("30");
Message(P.Category = Catalogs.Categories.FindByCode("10"));
Message(P <> P.Category);
Message(P.UUID() = P.Category.UUID());
Message(P.Category.Ref = P.Category);
''')
        self.assertEqual(output, [
            '10', 'Empty', '12,5', 'Нет', 'Да', 'Нет', 'Да', 'Нет', '', 'Да',
            '20', 'Absent', '12,5', 'Да', 'Да', 'Да', 'Да', 'Да', '', 'Да',
            '30', 'Present', '12,5', 'Да', 'Да', 'Да', 'Да', 'Да', 'Hardware', 'Да',
            'Да', 'Да', 'Да', 'Да'])
        context.catalog_metadata.assert_called_once_with()

    def test_missing_product_defaults_preserve_declared_types(self):
        vm, _, output, _ = self.runtime()
        vm.execute('''
P = Catalogs.Products.GetRef(New UUID("00000000-0000-0000-0000-000000000099"));
Message(P.Label = ""); Message(P.Price = 0); Message(P.Enabled = False);
Message(TypeOf(P.Effective) = Type("Date")); Message(ValueIsFilled(P.Effective));
Message(P.Category.IsEmpty());
Message(TypeOf(P.Category) = Type("CatalogRef.Categories"));
''')
        self.assertEqual(output, ['Да', 'Да', 'Да', 'Да', 'Нет', 'Да', 'Да'])

    def test_attribute_order_is_metadata_driven_and_count_is_bounded(self):
        vm, _, _, source = self.runtime()
        product = source['Products']
        product.binding.attributes = tuple(reversed(product.binding.attributes))
        self.assertEqual(vm.execute('Catalogs.Products.FindByCode("30").Category.Description'), 'Hardware')
        product.binding.attributes = product.binding.attributes * 13
        with self.assertRaisesRegex(Exception, 'bounded profile'):
            vm.execute('Catalogs.Products.FindByCode("30").Category.Description')

    def test_target_type_uuid_is_not_assumed_to_be_catalog_metadata_uuid(self):
        vm, _, _, source = self.runtime()
        source['Products'].binding.attributes = (
            CatalogCardField('Category', '_FLD5', 'catalog_ref', UUID(int=999)),)
        with self.assertRaisesRegex(Exception, 'target metadata identity'):
            vm.execute('P = Catalogs.Products.FindByCode("30"); Message(P.Category);')

    def test_no_physical_bytes_or_scalar_coercion_guessed(self):
        vm, _, _, _ = self.runtime()
        for kind, invalid in (('boolean', Decimal(1)), ('number', True),
                              ('datetime', b'\0'*8), ('string', None),
                              ('catalog_ref', SHARED.bytes)):
            descriptor = CatalogCardField('Field', '_FLD1', kind,
                                          CATEGORIES if kind == 'catalog_ref' else None)
            with self.subTest(kind=kind), self.assertRaises(TypeError):
                descriptor.project(invalid, vm._catalogs)
        with self.assertRaises(ValueError):
            CatalogCardField('Value', '_FLD1', 'number').project(Decimal('NaN'), vm._catalogs)

    def test_descriptor_is_closed_immutable_and_reads_remain_readonly(self):
        field = CatalogCardField('Enabled', '_FLD1', 'boolean')
        with self.assertRaises(FrozenInstanceError): field.kind = 'string'
        for kind in ('composite', 'hierarchy', 'tablepart'):
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                CatalogCardField('Value', '_FLD1', kind)
        vm, _, _, _ = self.runtime()
        with self.assertRaises(Exception):
            vm.execute('Catalogs.Products.FindByCode("30").Enabled = False;')

if __name__ == '__main__': unittest.main()

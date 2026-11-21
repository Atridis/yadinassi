"""Direct property transfer uses existing database object storage and ownership."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections.structures import BSLStructure
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508, target_context
from yadinassi.types.errors import BSLRuntimeError
import test_property_transfer as fixture


class DirectFillDatabaseTests(unittest.TestCase):
    def setUp(self):
        fixture.PropertyTransferObjectTests.setUp(self)
        self.addCleanup(self.vm.close)

    def test_catalog_document_and_section_use_typed_buffer_setters(self):
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('catalog write')), \
             patch.object(self.context.backend, 'begin_document_write', side_effect=AssertionError('document write')):
            self.vm.execute(
                'R=Catalogs.Categories.EmptyRef();'
                'FillPropertyValues(C,New Structure("Category,Наименование,Amount",R,"Local",1.234));'
                'ЗаполнитьЗначенияСвойств(D,New Structure("Номер,Text","42","Doc"));'
                'L=C.Lines.Add();FillPropertyValues(L,New Structure("Text,Amount","Row",3.456));'
                'DL=D.Lines.Add();FillPropertyValues(DL,New Structure("Flag",True));'
                'Out=New Structure("Наименование,Amount");FillPropertyValues(Out,C);'
            )
        self.assertIs(self.catalog.get_member('Category'), self.vm.variables['r'])
        self.assertEqual(self.vm.execute('Out.Наименование'), 'Local')
        self.assertEqual(self.vm.execute('Out.Amount'), Decimal('1.23'))
        self.assertEqual(self.document.get_member('Number'), '42')
        self.assertEqual(self.document.get_member('Text'), 'Doc')
        self.assertEqual(self.vm.execute('L.Amount'), Decimal('3.46'))
        self.assertIs(self.vm.execute('DL.Flag'), True)
        self.assertTrue(self.catalog.is_new() and self.document.is_new())

    def test_database_inclusion_is_validated_before_any_write_on_linux(self):
        with target_context(LINUX_8_3_27_1508), self.assertRaisesRegex(BSLRuntimeError, 'включенное свойство отсутствует'):
            self.vm.execute('FillPropertyValues(C,New Structure("Text", "must not land"),"Missing,Text");')
        self.assertEqual(self.catalog.get_member('Text'), '')

    def test_same_database_foreign_endpoints_denied_before_transfer(self):
        independent = Interpreter(database_context=self.context)
        self.addCleanup(independent.close)
        foreign = independent.execute('C=Catalogs.Products.CreateItem();C.Text="Private";C')
        self.vm.variables.update(foreign=foreign, host=BSLStructure('Text', 'Local'))
        self.vm.execute('Local=New Structure("Text","Local");')
        for call in ('FillPropertyValues(Foreign,Local);', 'FillPropertyValues(Local,Foreign);',
                     'FillPropertyValues(Foreign,Host);', 'FillPropertyValues(Host,Foreign);',
                     'FillPropertyValues(C,Foreign);'):
            with self.subTest(call=call), self.assertRaisesRegex(BoundaryViolation, 'foreign database receiver'):
                self.vm.execute(call)
        self.assertEqual(self.vm.execute('Local.Text'), 'Local')
        self.assertEqual(self.vm.execute('Host.Text'), 'Local')
        self.assertEqual(self.catalog.get_member('Text'), '')
        self.assertEqual(foreign.get_member('Text'), 'Private')

    def test_foreign_reference_value_rejected_by_canonical_setter(self):
        independent = Interpreter(database_context=self.context)
        self.addCleanup(independent.close)
        self.vm.variables['foreign'] = independent.execute('Catalogs.Categories.EmptyRef()')
        before = self.catalog.get_member('Category')
        with self.assertRaisesRegex(BSLRuntimeError, 'same database target'):
            self.vm.execute('FillPropertyValues(C,New Structure("Category",Foreign));')
        self.assertIs(self.catalog.get_member('Category'), before)

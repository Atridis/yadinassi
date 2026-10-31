"""Local adapter regressions; synthetic cursor rows are not native evidence."""
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import UUID
import unittest

from yadinassi.runtime import Interpreter
from yadinassi.catalogs import BSLCatalogSelection
from yadinassi.storage.catalog_metadata import CatalogMetadataIdentity

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
U = '33333333-3333-4333-8333-333333333333'
V = '44444444-4444-4444-8444-444444444444'


def result(rows=(), metadata=A):
    def row(uid, code, description, marked=False):
        values = {'_CODE': code, '_DESCRIPTION': description, '_MARKED': marked,
                  '_FLD7': 'payload', '_FLD8': Decimal('1.25')}
        return NS(reference_uuid=UUID(uid), physical_record=NS(fields=tuple(
            NS(declaration=NS(name=name), value=value) for name, value in values.items())))
    return NS(identity=NS(name='Products', metadata_uuid=metadata),
              binding=NS(attributes=(NS(name='TextValue', physical_name='_FLD7'),
                                     NS(name='Amount', physical_name='_FLD8'))),
              rows=tuple(row(*values) for values in rows))


class CatalogScenarioTests(unittest.TestCase):
    def setup_runtime(self, rows=()):
        context = Mock()
        context.catalog_metadata.return_value = (CatalogMetadataIdentity(A, 'Products'),
                                                  CatalogMetadataIdentity(B, 'Other'))
        context.catalog_rows.return_value = result(rows)
        output = []
        runtime = Interpreter(output.append, database_context=context)
        return runtime, context, output

    def test_one_snapshot_managers_refs_types_and_metadata(self):
        runtime, context, output = self.setup_runtime()
        runtime.execute('''
M = Catalogs.Products;
R = M.GetRef(New UUID("33333333-3333-4333-8333-333333333333"));
Message(TypeOf(R) = Type("CatalogRef.Products"));
Message(TypeOf(TypeOf(R)) = Type("Type"));
Message(R.Metadata() = Metadata.Catalogs.Products);
Message(ValueIsFilled(R));
Message(ValueIsFilled(M.EmptyRef()));
Message(R = Catalogs.Other.GetRef(R.UUID()));
''')
        self.assertEqual(output, ['Да', 'Да', 'Да', 'Да', 'Нет', 'Нет'])
        context.catalog_metadata.assert_called_once_with()
        context.catalog_rows.assert_not_called()

    def test_actual_bsl_select_and_lookup(self):
        runtime, context, output = self.setup_runtime(((U, '002', 'Second', True),))
        runtime.execute('''
M = Catalogs["Products"];
S = M.Select();
While S.Next() Do
 Message(S.Code); Message(S.Description); Message(S.TextValue);
 Message(S.Amount); Message(S.DeletionMark);
 Message(S.Ref = M.FindByCode(S.Code));
 Message(S.Ref = M.FindByDescription(S.Description, True));
EndDo;
Message(M.FindByCode("absent").IsEmpty());
Message(S.Next());
S.Reset(); Message(S.Next());
''')
        self.assertEqual(output, ['002', 'Second', 'payload', '1,25', 'Да',
                                  'Да', 'Да', 'Да', 'Нет', 'Да'])

    def test_cursor_empty_and_synthetic_multiple_state_machine(self):
        runtime, _, _ = self.setup_runtime()
        manager = runtime._catalogs.get_index('Products')
        empty = BSLCatalogSelection(manager, result())
        self.assertFalse(empty.next()); empty.reset(); self.assertFalse(empty.next())
        cursor = BSLCatalogSelection(manager, result(((U, '2', 'B'), (V, '1', 'A'))))
        with self.assertRaisesRegex(ValueError, 'not positioned'):
            cursor.get_member('Code')
        self.assertTrue(cursor.next()); self.assertEqual(cursor.get_member('Code'), '2')
        self.assertTrue(cursor.next()); self.assertEqual(cursor.get_member('Code'), '1')
        self.assertFalse(cursor.next()); self.assertFalse(cursor.next())
        cursor.reset(); self.assertTrue(cursor.next())

    def test_database_is_lazy_and_untaken_branches_stay_lazy(self):
        runtime = Interpreter(lambda value: None)
        runtime.execute('If False Then S = Catalogs.Products.Select(); EndIf; Message(Type("String"));')
        with self.assertRaisesRegex(Exception, 'db required'):
            runtime.execute('S = Catalogs.Products;')

    def test_changed_catalog_identity_cannot_supply_rows(self):
        runtime, context, _ = self.setup_runtime()
        context.catalog_rows.return_value = result(metadata=B)
        with self.assertRaisesRegex(Exception, 'identity changed'):
            runtime.execute('S = Catalogs.Products.Select();')

    def test_unsupported_partial_lookup_and_writes(self):
        runtime, _, _ = self.setup_runtime()
        for source in ('Catalogs.Products.FindByDescription("a");',
                       'Catalogs.Products.CreateItem();',
                       'Catalogs.Products.EmptyRef().Code = "x";',
                       'R = New (Type("CatalogRef.Products"));'):
            with self.subTest(source=source), self.assertRaises(Exception):
                runtime.execute(source)

if __name__ == '__main__': unittest.main()

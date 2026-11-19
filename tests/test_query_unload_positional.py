"""Query reports use the canonical positional table, not legacy row dictionaries."""
from decimal import Decimal
import unittest
from unittest.mock import patch

import test_catalog_queries as fixtures
from yadinassi.db.query.queries import BSLQuery
from yadinassi.types.values import NULL
from yadinassi.collections.structures import BSLStructure
from yadinassi.collections.plain_table_storage import validate_row
from yadinassi.collections.plain_value_table_runtime import BSLValueTableRow


class QueryUnloadPositionalTests(unittest.TestCase):
    setUp=fixtures.CatalogQueryTests.setUp
    tearDown=fixtures.CatalogQueryTests.tearDown

    def test_default_bsl_alias_null_and_detachment(self):
        self.vm.execute('Q=New Query("SELECT Amount AS N,CASE WHEN Amount<0 THEN Amount ELSE NULL END AS Missing FROM Catalog.Products ORDER BY Amount");'
                        'T=Q.Execute().Unload();Message(T[0].N);Message(T[0].Missing=Null);'
                        'T[0].N=99;Message(T[0].N);Message(Catalogs.Products.FindByCode("1").Amount);')
        self.assertEqual(self.output,['10','Да','99','10'])

    def test_scalar_table_storage_and_lazy_index(self):
        result=BSLQuery(self.vm._catalogs,'SELECT Amount AS N FROM Catalog.Products ORDER BY Amount').execute()
        table=result.unload()
        table._storage.validate()
        row=table.rows[0]
        validate_row(row,table._storage.schema,table,row_type=BSLValueTableRow)
        table.indexes.add('N')
        selection=BSLStructure();selection.insert('N',Decimal(10))
        self.assertEqual(table.find_rows(selection).items,[row])
        row.set_member('N',Decimal(99))
        self.assertEqual(table.find_rows(selection).items,[])
        self.assertEqual(result._rows[0],(Decimal(10),))

    def test_reference_null_and_owned_binding_detached(self):
        result=BSLQuery(self.vm._catalogs,'SELECT Ref AS Item,CASE WHEN Amount<0 THEN Amount ELSE NULL END AS Missing FROM Catalog.Products').execute()
        table=result.unload();table._storage.validate()
        self.assertIs(table.rows[0].get_member('Item'),result._rows[0][0])
        self.assertIs(table.rows[0].get_member('Missing'),NULL)
        self.assertIs(table.columns.items[0].value_type._query_reference,result._columns[0].reference_binding)
        table.rows[0].set_member('Missing','local')
        self.assertIs(result._rows[0][1],NULL)

    def test_result_wide_growth_preflight_precedes_rows(self):
        result=BSLQuery(self.vm._catalogs,'SELECT Ref AS Item,Amount FROM Catalog.Products').execute()
        with patch('yadinassi.collections.plain_value_table_runtime._MAX_CELLS',5),patch.object(BSLValueTableRow,'__init__',side_effect=AssertionError('no rows before preflight')):
            with self.assertRaisesRegex(ValueError,'growth limit'):result.unload()

    def test_duplicate_casefold_and_nontext_names_refused_before_rows(self):
        from dataclasses import replace
        from yadinassi.db.query.queries import BSLQueryResult
        result=BSLQuery(self.vm._catalogs,'SELECT Amount AS N FROM Catalog.Products').execute()
        column=result._columns[0]
        duplicate=BSLQueryResult((column,replace(column,name='n')),
                                 tuple((values[0],values[0]) for values in result._rows))
        with patch.object(BSLValueTableRow,'__init__',side_effect=AssertionError('no rows before schema')):
            with self.assertRaises(ValueError):duplicate.unload()
            invalid=BSLQueryResult((replace(column,name=None),),result._rows)
            with self.assertRaises(TypeError):invalid.unload()

"""Query reports use the canonical positional table, not legacy row dictionaries."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import BSLRuntimeError

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

    def test_invalid_row_shape_rejected_before_allocating_rows(self):
        from yadinassi.db.query.query_table_materialization import materialize
        result=BSLQuery(self.vm._catalogs,'SELECT Ref AS Item,Amount FROM Catalog.Products').execute()
        with patch.object(BSLValueTableRow,'__init__',side_effect=AssertionError('no rows before preflight')):
            with self.assertRaisesRegex(TypeError,'Invalid query result shape'):
                materialize(result._columns,(None,None),(result._rows[0],()))

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

    def test_nullable_materialization_does_not_request_default(self):
        from yadinassi.types.type_descriptions import BSLTypeDescription
        from yadinassi.collections.plain_value_table_runtime import BSLValueTable
        result=BSLQuery(self.vm._catalogs,'SELECT CASE WHEN Amount<0 THEN Amount ELSE NULL END AS Missing FROM Catalog.Products').execute()
        with patch.object(BSLTypeDescription, 'adjust_value', side_effect=AssertionError('materialized values need no coercion')):
            table=result.unload()
        self.assertIs(table.rows[0].get_member('Missing'), NULL)
        description=table.columns.items[0].value_type
        self.assertIsNotNone(description._query_scalar)
        # Public default/coercion support is not widened by detached capture.
        with self.assertRaises(ValueError): description.adjust_value()
        with self.assertRaises(ValueError): BSLValueTable().columns.add('N', description)

    def test_direct_blank_rows_remain_closed_until_query_columns_are_removed(self):
        self.vm.execute('Q=New Query("SELECT Amount AS N,Amount AS M FROM Catalog.Products");'
                        'T=Q.Execute().Unload();T.Columns.Add("Local",New TypeDescription("Number"));')
        table=self.vm.variables['t']
        def denied():
            original=tuple(table.rows);epoch=table._storage.epoch
            for call in ('T.Add()', 'T.Insert(0)'):
                with self.subTest(call=call), self.assertRaisesRegex(BSLRuntimeError,'default row values'):
                    self.vm.execute(call+';')
            self.assertEqual(tuple(table.rows),original)
            self.assertEqual(table._storage.epoch,epoch)
        denied()
        self.vm.execute('T.Columns.Delete("N");')
        denied()
        self.vm.execute('T.Columns.Delete("M");R=T.Insert(0);')
        self.assertEqual(self.vm.variables['r'].get_member('Local'),Decimal(0))

    def test_copy_stays_closed_for_query_schema_but_ordinary_projection_is_detached(self):
        self.vm.execute('Q=New Query("SELECT Amount AS N FROM Catalog.Products");T=Q.Execute().Unload();')
        table=self.vm.variables['t']
        for copy in (table.copy,table.copy_columns):
            with self.assertRaisesRegex(ValueError,'Null для колонки запроса'):copy()
        table.columns.add('Local')
        table.rows[0].set_member('Local','first')
        copied=table.copy(columns='Local')
        self.assertEqual(copied.rows[0].get_member('Local'),'first')
        self.assertIsNone(copied.add().get_member('Local'))
        self.assertIsNot(copied.rows[0],table.rows[0])

    def test_ordinary_materialized_columns_have_their_regular_defaults(self):
        from yadinassi.db.query.query_table_materialization import materialize
        from yadinassi.types.type_descriptions import BSLTypeDescription
        result=BSLQuery(self.vm._catalogs,'SELECT Amount AS N,Amount AS U,Amount AS V FROM Catalog.Products').execute()
        descriptions=(BSLTypeDescription('Number'),BSLTypeDescription('Number,String'),BSLTypeDescription())
        table=materialize(result._columns,descriptions,result._rows)
        self.assertEqual(tuple(table.add()),(Decimal(0),None,None))
        self.assertEqual(tuple(table.insert(0)),(Decimal(0),None,None))

    def test_materializer_rejects_noncanonical_description(self):
        from yadinassi.db.query.query_table_materialization import materialize
        result=BSLQuery(self.vm._catalogs,'SELECT Amount AS N FROM Catalog.Products').execute()
        with patch.object(BSLValueTableRow,'__init__',side_effect=AssertionError('no rows before metadata')):
            with self.assertRaisesRegex(TypeError,'Invalid query column metadata'):
                materialize(result._columns,(object(),),result._rows)

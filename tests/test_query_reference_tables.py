"""Owned report roundtrip; explicit host contract, not native default parity."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.queries import BSLQuery
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.values import NULL, BSLType
import test_catalog_queries as catalogs
import test_document_queries as documents


class ReferenceReportTests(unittest.TestCase):
    setUp = catalogs.CatalogQueryTests.setUp
    tearDown = catalogs.CatalogQueryTests.tearDown

    def query(self, text, table=None, manager=None):
        q = BSLQuery(self.vm._catalogs, text)
        if table is not None: q.set_parameter('Input', table)
        if manager is not None: q.set_member('TempTablesManager', manager)
        return q

    def table(self):
        return self.query('SELECT Ref AS Item,Category,Amount FROM Catalog.Products').execute().unload()

    def test_catalog_roundtrip_external_temp_join(self):
        t = self.table()
        q = self.query('SELECT Item,Category,Amount INTO Prepared FROM &Input; '
                       'SELECT C.Code AS Code,SUM(T.Amount) AS Total FROM Prepared AS T '
                       'JOIN Catalog.Categories AS C ON T.Category=C.Ref GROUP BY C.Code', t)
        self.assertEqual(q.execute()._rows, (('01', Decimal(60)),))

    def test_empty_output_keeps_reference_domain(self):
        t = self.query('SELECT Ref AS Item FROM Catalog.Products WHERE Code="missing"').execute().unload()
        self.assertEqual(t.rows, [])
        d = t.columns.items[0].value_type
        self.assertTrue(d.contains_type(self.vm._catalogs.get_index('Products')._value_type))
        self.assertTrue(d.contains_type(BSLType.NULL))
        self.assertEqual(d.get_types().items, [self.vm._catalogs.get_index('Products')._value_type, BSLType.NULL])
        self.assertEqual(self.query('SELECT Item FROM &Input', t).execute()._rows, ())

    def test_add_and_default_remain_closed(self):
        t = self.table()
        for action in (t.add, lambda: t.columns.items[0].value_type.adjust_value(),
                       lambda: BSLTypeDescription(t.columns.items[0].value_type)):
            with self.assertRaises((TypeError, ValueError)): action()
        self.assertEqual(len(t.rows), 3)
        self.vm.variables['report'] = t
        from yadinassi import BSLRuntimeError
        for code in ('ValueToStringInternal(Report)', 'New ValueStorage(Report)'):
            with self.assertRaises(BSLRuntimeError): self.vm.execute(code)

    def test_same_domain_assignment_but_no_cast(self):
        t = self.table()
        ref = t.rows[1].get_member('Item')
        t.rows[0].set_member('Item', ref)
        self.assertIs(t.rows[0].get_member('Item'), ref)
        for value in (NULL, 'x', Decimal(0), self.vm._catalogs.get_index('Categories').empty_ref()):
            with self.assertRaises((TypeError, ValueError)): t.rows[0].set_member('Item', value)

    def test_foreign_snapshot_rejected_even_empty(self):
        t = self.query('SELECT Ref AS Item FROM Catalog.Products WHERE Code="missing"').execute().unload()
        other = Interpreter(database_context=self.context)
        q = BSLQuery(other._catalogs, 'SELECT Item FROM &Input')
        q.set_parameter('Input', t)
        with self.assertRaises((TypeError, ValueError)): q.execute()

    def test_forged_callback_rejected_in_unprojected_column(self):
        t = self.table()
        c = t.columns.items[0]
        good = t.rows[0].cells[c]
        t.rows[0].cells[c] = replace(good, read_member=lambda *_: None)
        with self.assertRaises((TypeError, ValueError)):
            self.query('SELECT TOP 1 Amount FROM &Input WHERE Amount<0', t).execute()

    def test_null_from_left_join_preserved(self):
        t = self.query('SELECT C.Ref AS Missing FROM Catalog.Products AS P '
                       'LEFT JOIN Catalog.Categories AS C ON P.Code=C.Code').execute().unload()
        self.assertTrue(all(row.get_member('Missing') is NULL for row in t.rows))
        self.assertEqual(self.query('SELECT Missing FROM &Input', t).execute()._rows, ((NULL,),)*3)

    def test_union_null_first_preserves_binding(self):
        t = self.query('SELECT NULL AS Item FROM Catalog.Products WHERE Code="1" '
                       'UNION ALL SELECT Ref FROM Catalog.Products').execute().unload()
        self.assertIs(t.rows[0].get_member('Item'), NULL)
        self.assertEqual(len(self.query('SELECT Item FROM &Input', t).execute()._rows), 4)

    def test_failed_package_preserves_manager(self):
        m = BSLTempTablesManager()
        self.query('SELECT Item INTO Saved FROM &Input', self.table(), m).execute()
        before = m._tables
        with self.assertRaises((TypeError, ValueError)):
            self.query('DESTROY Saved; SELECT Missing FROM &Input', self.table(), m).execute()
        self.assertIs(m._tables, before)

    def test_source_mutation_after_execution_does_not_change_temp(self):
        m = BSLTempTablesManager()
        t = self.table()
        self.query('SELECT Item INTO Saved FROM &Input', t, m).execute()
        before = self.query('SELECT Item FROM Saved', manager=m).execute()._rows
        t.rows[0].set_member('Item', t.rows[1].get_member('Item'))
        self.assertEqual(self.query('SELECT Item FROM Saved', manager=m).execute()._rows, before)

    def test_generic_reference_descriptor_still_cannot_create_column(self):
        from yadinassi.type_descriptions import _reference_description
        from yadinassi.value_tables import BSLValueTable
        d = _reference_description(self.vm._catalogs.get_index('Products')._value_type)
        with self.assertRaises((TypeError, ValueError)): BSLValueTable().columns.add('Ref', d)


    def test_reference_external_only_opens_one_view_no_row_scan(self):
        from yadinassi.sqlite_catalog import _View
        t = self.table()
        backend = self.context.backend
        with patch.object(backend, 'begin_read', wraps=backend.begin_read) as reads, \
                patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('no existence scan')):
            self.assertEqual(len(self.query('SELECT Item FROM &Input', t).execute()._rows), 3)
        self.assertEqual(reads.call_count, 1)

    def test_reference_external_and_catalog_share_view(self):
        t = self.table()
        backend = self.context.backend
        with patch.object(backend, 'begin_read', wraps=backend.begin_read) as reads:
            self.query('SELECT T.Item FROM &Input AS T JOIN Catalog.Products AS P ON T.Item=P.Ref', t).execute()
        self.assertEqual(reads.call_count, 1)

    def test_scalar_external_still_zero_io(self):
        t = self.query('SELECT Amount FROM Catalog.Products').execute().unload()
        with patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('scalar I/O')):
            self.assertEqual(len(self.query('SELECT Amount FROM &Input', t).execute()._rows), 3)

    def test_unload_inspection_assignment_do_not_open_view(self):
        result = self.query('SELECT Ref AS Item FROM Catalog.Products').execute()
        with patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('detached I/O')):
            t = result.unload()
            t.columns.items[0].value_type.get_types()
            t.rows[0].set_member('Item', t.rows[1].get_member('Item'))

    def test_closed_context_refused_even_empty(self):
        from yadinassi.catalog_backend import BackendError
        t = self.query('SELECT Ref AS Item FROM Catalog.Products WHERE Code="missing"').execute().unload()
        self.context.close()
        with self.assertRaises(BackendError): self.query('SELECT Item FROM &Input', t).execute()

    def test_changed_generation_refused_even_empty(self):
        import sqlite3
        from yadinassi.catalog_backend import BackendError
        t = self.query('SELECT Ref AS Item FROM Catalog.Products WHERE Code="missing"').execute().unload()
        with closing(sqlite3.connect(self.context.path)) as connection:
            with connection:
                connection.execute('UPDATE database_info SET generation=generation+1')
        with self.assertRaises(BackendError): self.query('SELECT Item FROM &Input', t).execute()

    def test_all_domains_validated_not_only_projected(self):
        from yadinassi.sqlite_catalog import _View
        from yadinassi.catalog_backend import BackendError
        t = self.table()
        category = self.vm._catalogs.get_index('Categories')._schema.identity
        original = _View.catalog_schema
        def schema(view, identity):
            if identity == category: raise BackendError('schema_changed')
            return original(view, identity)
        with patch.object(_View, 'catalog_schema', schema):
            with self.assertRaises(BackendError): self.query('SELECT Amount FROM &Input', t).execute()

    def test_view_close_failure_does_not_publish_temps(self):
        from yadinassi.sqlite_catalog import _View
        t = self.table()
        manager = BSLTempTablesManager()
        original = _View.close
        def close(view):
            original(view)
            raise ValueError('close failure')
        with patch.object(_View, 'close', close):
            with self.assertRaisesRegex(ValueError, 'close failure'):
                self.query('SELECT Item INTO Saved FROM &Input', t, manager).execute()
        self.assertEqual(manager._tables, {})


class DocumentReportTests(unittest.TestCase):
    setUp = documents.DocumentQueryTests.setUp
    tearDown = documents.DocumentQueryTests.tearDown
    seed = documents.DocumentQueryTests.seed

    def test_document_roundtrip_to_package(self):
        self.seed()
        q = BSLQuery(self.vm._catalogs, 'SELECT Ref AS Document,Category,Amount FROM Document.Orders',
                     documents=self.vm._documents)
        t = q.execute().unload()
        q.set_parameter('Input', t)
        q.set_member('Text', 'SELECT Document,Category,Amount INTO Prepared FROM &Input; '
                     'SELECT T.Document,T.Amount FROM Prepared AS T '
                     'JOIN Document.Orders AS D ON T.Document=D.Ref ORDER BY T.Amount')
        result = q.execute().unload()
        self.assertEqual([r.get_member('Amount') for r in result.rows], list(map(Decimal, (10,20,30))))


if __name__ == '__main__': unittest.main()

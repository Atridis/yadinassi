"""Scalar catalog reference access retains full point integrity admission."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_catalog_tabular_runtime as fixtures
from yadinassi.catalog_backend import BackendError
from yadinassi.errors import BSLRuntimeError
from yadinassi.sqlite_catalog import _View
from yadinassi.sqlite_catalog_layout import quote_identifier


class CatalogPointProjectionTests(unittest.TestCase):
    setUp=fixtures.CatalogTabularRuntimeTests.setUp
    def seed(self):
        self.vm.execute('O=Catalogs.Products.CreateItem();O.Code="1";O.Description="Visible";'
            'O.Text="header";For I=1 To 64 Do L=O.Lines.Add();L.Text="line";EndDo;O.Write();R=O.Ref;')
        return self.vm.execute('R')
    def sql(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as connection,connection:
            return connection.execute(sql,args).fetchall()
    def test_cold_scalar_does_not_materialize_card_and_getobject_still_does(self):
        self.seed()
        with patch.object(_View,'_card',side_effect=AssertionError('full card')):
            self.assertEqual(self.vm.execute('R.Description'),'Visible')
            self.assertEqual(self.vm.execute('R.Text'),'header')
        self.assertEqual(self.vm.execute('R.GetObject().Lines.Count()'),64)
    def test_warm_scalar_does_not_fetch_sections_or_unselected_fields(self):
        self.seed();self.vm.execute('R.Description')
        backend=self.context.backend; trace=[]
        original=backend.begin_read
        def begin():
            view=original();view._connection.set_trace_callback(trace.append);return view
        with patch.object(backend,'begin_read',side_effect=begin), \
                patch.object(_View,'_section_scan',side_effect=AssertionError('warm sections')), \
                patch.object(_View,'_scalar',side_effect=AssertionError('warm full scalar')):
            self.assertEqual(self.vm.execute('R.Наименование'),'Visible')
        reads=[s for s in trace if s.startswith('SELECT record_id,"description"')]
        self.assertEqual(len(reads),1)
        self.assertFalse(any('row_number' in s for s in trace))
    def test_external_section_corruption_invalidates_old_point_proof(self):
        ref=self.seed();self.vm.execute('R.Description')
        schema=self.vm._catalogs.get_index('Products')._schema
        section=schema.tabular_sections[0]
        table=quote_identifier(self.context.backend._section_layout.table_name(schema.identity,section.identity))
        self.sql('UPDATE '+table+' SET row_number=999 WHERE row_number=1')
        with self.assertRaises(BSLRuntimeError):self.vm.execute('R.Description')
    def test_write_commit_invalidates_cached_scalars(self):
        self.seed();self.assertEqual(self.vm.execute('R.Description'),'Visible')
        self.vm.execute('O.Description="Changed";O.Write();')
        self.assertEqual(self.vm.execute('R.Description'),'Changed')
    def test_unrelated_corrupt_record_does_not_expand_point_validation_scope(self):
        self.seed();self.vm.execute('X=Catalogs.Products.CreateItem();X.Code="2";X.Write();')
        schema=self.vm._catalogs.get_index('Products')._schema
        table=quote_identifier(self.context.backend._layout.table_name(schema.identity))
        self.sql('UPDATE '+table+' SET description=? WHERE code=?',('x'*1000,'2'))
        self.assertEqual(self.vm.execute('R.Description'),'Visible')
    def test_projection_denies_writer_and_closed_view(self):
        ref=self.seed();manager=self.vm._catalogs.get_index('Products')
        key=manager._key(ref.reference_uuid)
        with closing(self.context.backend.begin_write(uuid4())) as view:
            with self.assertRaisesRegex(BackendError,'unsupported'):view.read_catalog_values(key,('description',))
        with self.assertRaisesRegex(BackendError,'closed'):view.read_catalog_values(key,('description',))
    def test_empty_reference_and_bilingual_scalar_defaults_preserved(self):
        self.seed()
        self.assertEqual(self.vm.execute('Catalogs.Products.EmptyRef().Description'),'')
        self.assertFalse(self.vm.execute('Catalogs.Products.EmptyRef().ПометкаУдаления'))


import test_inventory_enum_runtime_binding as enum_fixtures

class EnumCatalogPointProjectionTests(unittest.TestCase):
    setUp=enum_fixtures.InventoryEnumRuntimeBindingTests.setUp
    def test_scalar_and_enum_getters_and_transaction_transfer_boundary(self):
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="P";C.Description="Product";'
                        'C.Unit=Enums.Units.Piece;C.Write();')
        self.assertEqual(self.vm.execute('C.Ref.Description'),'Product')
        self.assertIs(self.vm.execute('C.Ref.Unit'),self.ref)
        for member in ('Description','Unit'):
            with self.assertRaisesRegex(BSLRuntimeError,'unsupported'):
                self.vm.execute('BeginTransaction();V=C.Ref.'+member+';RollbackTransaction();')
    def test_lexical_witness_still_refuses_unregistered_view_subclass(self):
        from yadinassi.inventory_enum_runtime import read_snapshot
        class ForeignView(_View): pass
        with closing(self.context.backend.begin_read()) as view:
            foreign=object.__new__(ForeignView);foreign.__dict__.update(view.__dict__)
            with self.assertRaisesRegex(BackendError,'unsupported'):
                with read_snapshot(self.vm._metadata,foreign):pass

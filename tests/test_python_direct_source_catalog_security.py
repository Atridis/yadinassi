"""Exact direct catalog owner seals and retained-export lifetime."""
from uuid import uuid4
import unittest
from unittest.mock import patch
import test_python_direct_source_storage_guards as fixtures
import test_python_direct_source_query as query_fixtures
from test_source_catalog_object_modules import source
from yadinassi.source_references import SourceReferenceManager
from yadinassi.source_catalog_runtime import SourceCatalogObject,_ObjectInterpreter,create_object
from yadinassi.python_direct_source_storage import finish
from yadinassi.python_direct_source_catalog import check_object,bind_export
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class DirectCatalogSecurity(unittest.TestCase):
    app=fixtures.DirectSourceStorageGuards.app
    boundary=query_fixtures.DirectSourceQueryTests.boundary

    def test_legacy_attached_object_rejected_without_seal(self):
        app,caller=self.app(source('Function Answer() Export Return 1; EndFunction'),catalog=True)
        manager=SourceReferenceManager(app,'Catalog','Items')
        obj=SourceCatalogObject(manager,app.constant_store.catalog('Items'))
        vm=_ObjectInterpreter(obj,app);self.addCleanup(vm.close);obj.interpreter=vm
        with self.assertRaisesRegex(BoundaryViolation,'admission'):check_object(obj,caller)

    def test_retained_export_rechecks_identity_signature_and_close(self):
        app,caller=self.app(source('Description="initial"; Function Answer() Export Return Description; EndFunction'),catalog=True)
        with self.boundary(app,caller) as boundary:
            obj=finish(create_object(caller,SourceReferenceManager(app,'Catalog','Items'),app.constant_store.catalog('Items')))
            bound=bind_export(boundary,obj,'Answer',require_value=True,argument_count=0)
            self.assertEqual(bound(),'initial')
            identity=obj.identity;obj.identity=uuid4()
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:obj.identity=identity
            fields=obj.fields;obj.fields=dict(fields)
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:obj.fields=fields
            node=obj.interpreter.server_routines['answer'];original=node.is_function;node.is_function=False
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:node.is_function=original
            obj._closed=True
            with self.assertRaises(BoundaryViolation):bound()

    def test_fake_store_and_field_equality_rejected_before_callbacks(self):
        app,caller=self.app(source('Function Answer() Export Return 1; EndFunction'),catalog=True)
        effects=[]
        class FakeStore:
            def catalog(self,name):effects.append('catalog')
        class FakeField:
            def __eq__(self,other):effects.append('equality');return True
        with self.boundary(app,caller):
            obj=finish(create_object(caller,SourceReferenceManager(app,'Catalog','Items'),app.constant_store.catalog('Items')))
            store=app.constant_store;app.constant_store=FakeStore()
            try:
                with self.assertRaises(BoundaryViolation):check_object(obj,caller)
            finally:app.constant_store=store
            field=obj.fields['code'];obj.fields['code']=FakeField()
            try:
                with self.assertRaises(BoundaryViolation):check_object(obj,caller)
            finally:obj.fields['code']=field
        self.assertEqual(effects,[])

    def test_foreign_object_rejected_before_export_lookup(self):
        package=source('Function Answer() Export Return 1; EndFunction')
        app,caller=self.app(package,catalog=True);other,other_caller=self.app(package,catalog=True)
        with self.boundary(other,other_caller):
            obj=finish(create_object(other_caller,SourceReferenceManager(other,'Catalog','Items'),other.constant_store.catalog('Items')))
        with self.boundary(app,caller) as boundary,patch.object(obj,'exported_routine',side_effect=AssertionError('foreign lookup')):
            with self.assertRaises(BoundaryViolation):bind_export(boundary,obj,'Answer')


if __name__=='__main__':unittest.main()

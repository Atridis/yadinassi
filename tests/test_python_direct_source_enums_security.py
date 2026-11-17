"""Owned enum metadata, delayed methods and foreign reference guards."""
import unittest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import test_python_direct_source_query as fixtures
from test_source_enumeration_runtime import package
from yadinassi.configuration_source_runtime import SourceApplication,_SourceInterpreter
from yadinassi import python_direct_source_enums as bridge
from yadinassi.enum_types import BSLEnumReference
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class DirectSourceEnumsSecurity(unittest.TestCase):
    boundary=fixtures.DirectSourceQueryTests.boundary
    def app(self):
        app=SourceApplication(package());self.addCleanup(app.close);app.start()
        caller=_SourceInterpreter(app,family_owner=app.interpreter);self.addCleanup(caller.close)
        caller._logical_side='server';caller._context_stack.append('server');self.addCleanup(caller._context_stack.pop)
        return app,caller

    def test_foreign_manager_reference_metadata_refused_before_callback(self):
        app,caller=self.app();other,_=self.app();foreign=other.enumerations.get_member('Status')
        with self.boundary(app,caller) as boundary:
            for value in (foreign,foreign._values[0],foreign._metadata):
                with self.subTest(kind=type(value).__name__),self.assertRaises(BoundaryViolation):bridge.get(boundary,value,'Name')
            with patch.object(foreign,'get_method',side_effect=AssertionError('foreign method')):
                with self.assertRaises(BoundaryViolation):bridge.resolve(boundary,foreign,'Count')

    def test_delayed_method_revokes_after_registry_replacement_and_close(self):
        app,caller=self.app()
        with self.boundary(app,caller) as boundary:
            manager=bridge.get(boundary,bridge.namespace(boundary,'enums'),'Status')
            bound=bridge.resolve(boundary,manager,'Count');self.assertEqual(bound(),Decimal(2))
            del app.enumerations._managers['status']
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:app.enumerations._managers['status']=manager
        with self.assertRaises(BoundaryViolation):bound()

    def test_class_and_instance_hooks_rejected_without_callback(self):
        from yadinassi.enumerations import BSLEnumManager
        app,caller=self.app();effects=[]
        with self.boundary(app,caller) as boundary:
            manager=app.enumerations.get_member('Status')
            for target in (manager,BSLEnumManager):
                with self.subTest(target=type(target).__name__),patch.object(target,'get_method',lambda *args:effects.append('called')):
                    with self.assertRaises(BoundaryViolation):bridge.resolve(boundary,manager,'Count')
        self.assertEqual(effects,[])

    def test_named_reference_cannot_retarget_foreign_owner(self):
        app,caller=self.app();other,_=self.app()
        with self.boundary(app,caller) as boundary:
            manager=app.enumerations.get_member('Status');original=manager._named['active']
            manager._named['active']=other.enumerations.get_member('Status')._values[0]
            try:
                with self.assertRaises(BoundaryViolation):bridge.get(boundary,manager,'Active')
            finally:manager._named['active']=original

    def test_metadata_collection_cannot_return_substituted_scalar(self):
        app,caller=self.app()
        with self.boundary(app,caller) as boundary:
            collection=app.enumerations.get_member('Status')._metadata._values
            item=collection._items['active'];collection._items['active']='fake'
            try:
                with self.assertRaises(BoundaryViolation):bridge.get(boundary,collection,'Active')
            finally:collection._items['active']=item

    def test_empty_reference_cannot_retarget_nonempty_value(self):
        app,caller=self.app()
        with self.boundary(app,caller) as boundary:
            manager=app.enumerations.get_member('Status');empty=manager._empty
            manager._empty=manager._values[0]
            try:
                with self.assertRaises(BoundaryViolation):bridge.resolve(boundary,manager,'EmptyRef')
            finally:manager._empty=empty

    def test_unknown_uuid_and_readonly_and_wrongarity(self):
        app,caller=self.app()
        with self.boundary(app,caller) as boundary:
            manager=app.enumerations.get_member('Status')
            forged=BSLEnumReference(manager._value_type,uuid4(),manager._metadata)
            with self.assertRaises(BoundaryViolation):bridge.resolve(boundary,forged,'IsEmpty')
            with self.assertRaises(TypeError):bridge.resolve(boundary,manager,'Count',argument_count=1)
            with self.assertRaises(ValueError):bridge.set_member(boundary,manager,'Active')(manager._empty)
            self.assertFalse(bridge.supports(boundary,app.metadata.get_member('Catalogs')))


if __name__=='__main__':unittest.main()

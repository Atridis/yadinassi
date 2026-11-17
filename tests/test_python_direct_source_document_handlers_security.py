"""Exact document handler owner and replaceable section lifetime checks."""
import unittest
from uuid import uuid4
from unittest.mock import patch
import test_python_direct_source_document_guards as fixtures
import test_python_direct_source_query as query_fixtures
from test_source_document_object_modules import package
from yadinassi.source_document_runtime import SourceDocumentObject,_ObjectInterpreter,create_object
from yadinassi.python_direct_source_storage import finish
from yadinassi.python_direct_source_document import check_object,bind_export
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class DirectDocumentHandlersSecurity(unittest.TestCase):
    app=fixtures.DirectDocumentGuards.app
    boundary=query_fixtures.DirectSourceQueryTests.boundary

    def test_legacy_object_without_seal_rejected(self):
        app,caller,manager=self.app(package('Function Answer() Export Return 1; EndFunction'))
        obj=SourceDocumentObject(manager,app.constant_store.document('Invoice'))
        vm=_ObjectInterpreter(obj,app);self.addCleanup(vm.close);obj.interpreter=vm
        with self.assertRaisesRegex(BoundaryViolation,'admission'):check_object(obj,caller)

    def test_replaced_sections_allowed_foreign_or_malformed_sections_denied(self):
        app,caller,manager=self.app(package('Function Answer() Export Return 1; EndFunction',sections=True),section=True)
        with self.boundary(app,caller) as boundary:
            obj=finish(create_object(caller,manager,app.constant_store.document('Invoice')))
            other=finish(create_object(caller,manager,app.constant_store.document('Invoice')))
            bound=bind_export(boundary,obj,'Answer',require_value=True,argument_count=0)
            old=obj.sections['lines'];obj.replace_sections({'lines':()})
            self.assertFalse(old.live);self.assertEqual(bound(),1)
            valid=obj.sections['lines'];obj.sections['lines']=other.sections['lines']
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:obj.sections['lines']=valid
            fields=valid.fields;valid.fields=dict(fields);valid.fields['flag']=object()
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:valid.fields=fields
            identity=obj.identity;obj.identity=uuid4()
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:obj.identity=identity

    def test_foreign_object_rejected_before_export_callback(self):
        config=package('Function Answer() Export Return 1; EndFunction')
        app,caller,manager=self.app(config);other,other_caller,other_manager=self.app(config)
        with self.boundary(other,other_caller):obj=finish(create_object(other_caller,other_manager,other.constant_store.document('Invoice')))
        with self.boundary(app,caller) as boundary,patch.object(obj,'exported_routine',side_effect=AssertionError('foreign callback')):
            with self.assertRaises(BoundaryViolation):bind_export(boundary,obj,'Answer')


if __name__=='__main__':unittest.main()

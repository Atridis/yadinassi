"""Finite document capabilities retain owner, VM and row-lifetime checks."""
from dataclasses import replace
import unittest
from unittest.mock import patch
import test_python_direct_source_document_guards as fixtures
import test_python_direct_source_query as query_fixtures
import test_source_document_sections as sections
from yadinassi.execution.direct.source import python_direct_source_storage as storage
from yadinassi.db.document.source_document_runtime import create_object,SourceDocumentCall
from yadinassi.db.document.source_document_sections import SourceDocumentSectionCall
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction


class DirectDocumentSecurity(unittest.TestCase):
    app=fixtures.DirectDocumentGuards.app
    boundary=query_fixtures.DirectSourceQueryTests.boundary

    def object(self,app,caller,manager):
        obj=create_object(caller,manager,app.constant_store.document('Invoice'))
        row=SourceDocumentSectionCall(obj.sections['lines'],'add').invoke(caller,[])
        row.property_write(caller,'Flag',True)
        return obj,obj.sections['lines'],row

    def test_legacy_attached_object_section_row_rejected_before_sql_or_vm(self):
        app,caller,manager=self.app(sections.package(),section=True)
        with self.boundary(app,caller) as boundary:
            obj,section,row=self.object(app,caller,manager)
            obj.interpreter=object()
            with patch.object(app.constant_store,'write_document_bundle',side_effect=AssertionError('SQL write')):
                for receiver,name in ((obj,'Write'),(section,'Clear'),(row,'Flag')):
                    with self.subTest(name=name),self.assertRaisesRegex(BoundaryViolation,'not direct-owned'):
                        storage.get(boundary,receiver,name)
                with self.assertRaisesRegex(BoundaryViolation,'not direct-owned'):
                    storage.captured(boundary,HostFunction('Write',SourceDocumentCall(obj,'write')))
        self.assertEqual(app.constant_store.read_documents('Invoice'),[])

    def test_captured_document_and_section_markers_cannot_retarget(self):
        app,caller,manager=self.app(sections.package(),section=True)
        with self.boundary(app,caller) as boundary:
            obj,section,row=self.object(app,caller,manager)
            other,other_section,_=self.object(app,caller,manager)
            for marker,field,new in ((SourceDocumentCall(obj,'new'),'receiver',other),
                                     (SourceDocumentSectionCall(section,'clear'),'section',other_section)):
                with self.subTest(kind=type(marker).__name__):
                    bound=storage.captured(boundary,HostFunction('Bound',marker),argument_count=0)
                    setattr(marker,field,new)
                    with self.assertRaisesRegex(BoundaryViolation,'operation changed'):bound()
            self.assertEqual(len(section.rows),1);self.assertEqual(len(other_section.rows),1)

    def test_foreign_and_callback_references_rejected_even_for_neutral_members(self):
        from uuid import UUID
        app,caller,manager=self.app(sections.package(),section=True)
        foreign,_,_=self.app(sections.package(),section=True);effects=[]
        owned=app.references.ref('Document','Invoice',UUID(int=0))
        values=(foreign.references.ref('Document','Invoice',UUID(int=0)),
                replace(owned,read_member=lambda *args:effects.append('read')),
                replace(owned,get_object=lambda *args:effects.append('load')))
        with self.boundary(app,caller) as boundary:
            for value in values:
                for name in ('IsEmpty','Metadata','GetObject','Number'):
                    with self.subTest(name=name),self.assertRaisesRegex(TypeError,'canonical owned identity'):
                        storage.get(boundary,value,name)
        self.assertEqual(effects,[])

    def test_row_reference_and_iterator_revalidate_after_clear(self):
        app,caller,manager=self.app(sections.package(),section=True)
        with self.boundary(app,caller) as boundary:
            obj,section,row=self.object(app,caller,manager)
            reference=boundary.reference_member(row,'Flag')
            iterator=storage.iterate(boundary,section);self.assertIs(next(iterator),row)
            SourceDocumentSectionCall(section,'clear').invoke(caller,[])
            for operation in (reference.get,lambda:reference.set(False)):
                with self.assertRaisesRegex(ValueError,'detached section row'):operation()
            # Iteration may finish at the final row; returned references still revoke.
            self.assertEqual(list(iterator),[])
            self.assertEqual(row.values,{'flag':True})


if __name__=='__main__':unittest.main()
